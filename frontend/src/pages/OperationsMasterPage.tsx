import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type { Location, Paginated, WorkArea, WorkCategory } from "../lib/types";

type ResourceKey = "locations" | "work-areas" | "work-categories" | "work-types" | "work-type-availabilities";
type FormState = Record<string, string | boolean | null>;

type ResourceConfig = {
  title: string;
  endpoint: string;
  canAccess: (roles: string[]) => boolean;
  canManage: (roles: string[]) => boolean;
  initial: FormState;
};

const workTypeColorOptions = ["slate", "blue", "green", "amber", "red", "violet", "cyan", "pink"];

function toBoolean(value: string | boolean) {
  return value === true || value === "true";
}

export function OperationsMasterPage({ resource }: { resource: ResourceKey }) {
  const { user } = useAuth();
  const roles = user?.roles ?? [];
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  const config: ResourceConfig = useMemo(() => {
    const canViewOperations = (items: string[]) =>
      items.includes("system_admin") || items.includes("shift_manager") || items.includes("supervisor");
    const canManageMasters = (items: string[]) => items.includes("system_admin");
    return {
      locations: {
        title: "施設管理",
        endpoint: "/api/v1/locations/",
        canAccess: canViewOperations,
        canManage: canManageMasters,
        initial: { code: "", name: "", short_name: "", timezone: "Asia/Tokyo" } as FormState,
      },
      "work-areas": {
        title: "作業エリア",
        endpoint: "/api/v1/work-areas/",
        canAccess: canViewOperations,
        canManage: canManageMasters,
        initial: { location: "", code: "", name: "" } as FormState,
      },
      "work-categories": {
        title: "作業カテゴリ",
        endpoint: "/api/v1/work-categories/",
        canAccess: canViewOperations,
        canManage: canManageMasters,
        initial: { code: "", name: "" } as FormState,
      },
      "work-types": {
        title: "作業種別",
        endpoint: "/api/v1/work-types/",
        canAccess: canViewOperations,
        canManage: canManageMasters,
        initial: {
          category: "",
          code: "",
          name: "",
          short_name: "",
          default_duration_minutes: "60",
          minimum_staff_count: "1",
          maximum_staff_count: "",
          color_key: "blue",
          requires_capability: false,
          can_overlap: false,
          is_break: false,
          is_bookable: false,
          requires_customer: false,
        } as FormState,
      },
      "work-type-availabilities": {
        title: "作業種別適用",
        endpoint: "/api/v1/work-type-availabilities/",
        canAccess: canViewOperations,
        canManage: canManageMasters,
        initial: { work_type: "", location: "", work_area: "" } as FormState,
      },
    }[resource];
  }, [resource]);

  const [form, setForm] = useState<FormState>(config.initial);
  useEffect(() => {
    setForm(config.initial);
    setEditingId(null);
    setSearch("");
  }, [config.initial, resource]);

  const locationQuery = useQuery({
    queryKey: ["locations", "all"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
  });
  const categoryQuery = useQuery({
    queryKey: ["work-categories", "all"],
    queryFn: () => api<Paginated<WorkCategory>>("/api/v1/work-categories/?page_size=100"),
  });
  const workAreaQuery = useQuery({
    queryKey: ["work-areas", "all"],
    queryFn: () => api<Paginated<WorkArea>>("/api/v1/work-areas/?page_size=100"),
  });
  const workTypeQuery = useQuery({
    queryKey: ["work-types", "all"],
    queryFn: () => api<Paginated<Record<string, unknown>>>("/api/v1/work-types/?page_size=100"),
  });
  const listQuery = useQuery({
    queryKey: [resource, search],
    queryFn: () =>
      api<Paginated<Record<string, unknown>>>(
        `${config.endpoint}?page_size=100${search ? `&search=${encodeURIComponent(search)}&name=${encodeURIComponent(search)}&code=${encodeURIComponent(search)}` : ""}`,
      ),
  });

  if (!config.canAccess(roles)) {
    return <Navigate to="/403" replace />;
  }

  const canManage = config.canManage(roles);

  const resetForm = () => {
    setEditingId(null);
    setForm(config.initial);
    setError("");
  };

  const handleEdit = (item: Record<string, unknown>) => {
    setEditingId(String(item.id));
    setForm({
      ...config.initial,
      ...Object.fromEntries(
        Object.entries(item).filter(([key]) => !["id", "created_at", "updated_at", "is_active"].includes(key)),
      ),
    } as FormState);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const payload = Object.fromEntries(
        Object.entries(form)
          .filter(([, value]) => value !== "")
          .map(([key, value]) => {
            if (typeof value === "boolean") return [key, value];
            if (["default_duration_minutes", "minimum_staff_count", "maximum_staff_count", "display_order"].includes(key)) {
              return [key, value === "" ? null : Number(value)];
            }
            return [key, value];
          }),
      );
      const path = editingId ? `${config.endpoint}${editingId}/` : config.endpoint;
      const method = editingId ? "PATCH" : "POST";
      await api(path, { method, body: JSON.stringify(payload) });
      resetForm();
      await listQuery.refetch();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "保存に失敗しました。");
    }
  };

  const toggleActive = async (itemId: string, active: boolean) => {
    const action = active ? "deactivate" : "reactivate";
    await api(`${config.endpoint}${itemId}/${action}/`, { method: "POST", body: JSON.stringify({ confirm: true }) });
    await listQuery.refetch();
  };

  if (listQuery.isLoading) {
    return <div>読み込み中...</div>;
  }

  if (listQuery.isError) {
    return <div className="error">一覧の取得に失敗しました。</div>;
  }

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Operations</p>
          <h2>{config.title}</h2>
        </div>
      </div>
      <div className="toolbar">
        <input placeholder="名称・コード検索" value={search} onChange={(event) => setSearch(event.target.value)} />
        {editingId ? (
          <button type="button" onClick={resetForm}>
            編集をキャンセル
          </button>
        ) : null}
      </div>
      {canManage ? (
        <form className="form-grid compact-form" onSubmit={submit}>
          <div className="field-grid">
            {(resource === "locations" || resource === "work-categories") && (
              <>
                {resource === "locations" ? (
                  <>
                    <label>
                      コード
                      <input value={String(form.code ?? "")} onChange={(e) => setForm((current) => ({ ...current, code: e.target.value }))} />
                    </label>
                    <label>
                      施設名
                      <input value={String(form.name ?? "")} onChange={(e) => setForm((current) => ({ ...current, name: e.target.value }))} />
                    </label>
                    <label>
                      省略名
                      <input value={String(form.short_name ?? "")} onChange={(e) => setForm((current) => ({ ...current, short_name: e.target.value }))} />
                    </label>
                    <label>
                      タイムゾーン
                      <input value={String(form.timezone ?? "")} onChange={(e) => setForm((current) => ({ ...current, timezone: e.target.value }))} />
                    </label>
                  </>
                ) : (
                  <>
                    <label>
                      コード
                      <input value={String(form.code ?? "")} onChange={(e) => setForm((current) => ({ ...current, code: e.target.value }))} />
                    </label>
                    <label>
                      カテゴリ名
                      <input value={String(form.name ?? "")} onChange={(e) => setForm((current) => ({ ...current, name: e.target.value }))} />
                    </label>
                  </>
                )}
              </>
            )}
            {resource === "work-areas" && (
              <>
                <label>
                  施設
                  <select value={String(form.location ?? "")} onChange={(e) => setForm((current) => ({ ...current, location: e.target.value }))}>
                    <option value="">選択してください</option>
                    {locationQuery.data?.results.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  コード
                  <input value={String(form.code ?? "")} onChange={(e) => setForm((current) => ({ ...current, code: e.target.value }))} />
                </label>
                <label>
                  エリア名
                  <input value={String(form.name ?? "")} onChange={(e) => setForm((current) => ({ ...current, name: e.target.value }))} />
                </label>
              </>
            )}
            {resource === "work-types" && (
              <>
                <label>
                  カテゴリ
                  <select value={String(form.category ?? "")} onChange={(e) => setForm((current) => ({ ...current, category: e.target.value }))}>
                    <option value="">選択してください</option>
                    {categoryQuery.data?.results.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  コード
                  <input value={String(form.code ?? "")} onChange={(e) => setForm((current) => ({ ...current, code: e.target.value }))} />
                </label>
                <label>
                  業務名
                  <input value={String(form.name ?? "")} onChange={(e) => setForm((current) => ({ ...current, name: e.target.value }))} />
                </label>
                <label>
                  表示名
                  <input value={String(form.short_name ?? "")} onChange={(e) => setForm((current) => ({ ...current, short_name: e.target.value }))} />
                </label>
                <label>
                  所要時間
                  <input type="number" value={String(form.default_duration_minutes ?? "")} onChange={(e) => setForm((current) => ({ ...current, default_duration_minutes: e.target.value }))} />
                </label>
                <label>
                  最少人数
                  <input type="number" value={String(form.minimum_staff_count ?? "")} onChange={(e) => setForm((current) => ({ ...current, minimum_staff_count: e.target.value }))} />
                </label>
                <label>
                  最大人数
                  <input type="number" value={String(form.maximum_staff_count ?? "")} onChange={(e) => setForm((current) => ({ ...current, maximum_staff_count: e.target.value }))} />
                </label>
                <label>
                  カラー
                  <select value={String(form.color_key ?? "")} onChange={(e) => setForm((current) => ({ ...current, color_key: e.target.value }))}>
                    {workTypeColorOptions.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="checkbox">
                  <input type="checkbox" checked={toBoolean(form.requires_capability ?? false)} onChange={(e) => setForm((current) => ({ ...current, requires_capability: e.target.checked }))} />
                  対応可能業務必須
                </label>
                <label className="checkbox">
                  <input type="checkbox" checked={toBoolean(form.can_overlap ?? false)} onChange={(e) => setForm((current) => ({ ...current, can_overlap: e.target.checked }))} />
                  重複可
                </label>
                <label className="checkbox">
                  <input type="checkbox" checked={toBoolean(form.is_break ?? false)} onChange={(e) => setForm((current) => ({ ...current, is_break: e.target.checked }))} />
                  休憩
                </label>
                <label className="checkbox">
                  <input type="checkbox" checked={toBoolean(form.is_bookable ?? false)} onChange={(e) => setForm((current) => ({ ...current, is_bookable: e.target.checked }))} />
                  予約対象
                </label>
                <label className="checkbox">
                  <input type="checkbox" checked={toBoolean(form.requires_customer ?? false)} onChange={(e) => setForm((current) => ({ ...current, requires_customer: e.target.checked }))} />
                  顧客必須
                </label>
              </>
            )}
            {resource === "work-type-availabilities" && (
              <>
                <label>
                  作業種別
                  <select value={String(form.work_type ?? "")} onChange={(e) => setForm((current) => ({ ...current, work_type: e.target.value }))}>
                    <option value="">選択してください</option>
                    {workTypeQuery.data?.results.map((item) => (
                      <option key={String(item.id)} value={String(item.id)}>
                        {String(item.name)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  施設
                  <select value={String(form.location ?? "")} onChange={(e) => setForm((current) => ({ ...current, location: e.target.value }))}>
                    <option value="">選択してください</option>
                    {locationQuery.data?.results.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  作業エリア
                  <select value={String(form.work_area ?? "")} onChange={(e) => setForm((current) => ({ ...current, work_area: e.target.value }))}>
                    <option value="">全体共通</option>
                    {workAreaQuery.data?.results.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
          </div>
          {error ? <p className="error">{error}</p> : null}
          <div className="actions">
            <button type="submit">{editingId ? "更新" : "新規作成"}</button>
          </div>
        </form>
      ) : null}
      <table className="table">
        <thead>
          <tr>
            <th>名称</th>
            <th>コード</th>
            <th>状態</th>
            <th>更新日時</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {listQuery.data?.results.map((item) => (
            <tr key={String(item.id)}>
              <td>{String(item.name ?? item.short_name ?? item.id)}</td>
              <td>{String(item.code ?? "-")}</td>
              <td>{item.is_active ? "有効" : "無効"}</td>
              <td>{String(item.updated_at ?? "-")}</td>
              <td className="actions">
                {canManage ? (
                  <>
                    <button type="button" onClick={() => handleEdit(item)}>
                      編集
                    </button>
                    <button type="button" onClick={() => void toggleActive(String(item.id), Boolean(item.is_active))}>
                      {item.is_active ? "無効化" : "再有効化"}
                    </button>
                  </>
                ) : (
                  <span className="subtle-text">閲覧のみ</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
