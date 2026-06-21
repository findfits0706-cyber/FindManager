import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type { Location, Paginated, Staff, WorkType } from "../lib/types";

type ResourceKey = "staff-locations" | "staff-capabilities";
type FormState = Record<string, string | boolean | null>;

export function StaffAssignmentsPage({ resource }: { resource: ResourceKey }) {
  const { user } = useAuth();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const canView = canManage || roles.includes("supervisor");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ staff: "", location: "", level: "", search: "" });

  const staffQuery = useQuery({
    enabled: canView,
    queryKey: ["staff", "options"],
    queryFn: () => api<Paginated<Staff>>("/api/v1/staff/?page_size=100"),
  });
  const locationQuery = useQuery({
    enabled: canView,
    queryKey: ["locations", "options"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
  });
  const workTypeQuery = useQuery({
    enabled: resource === "staff-capabilities" && canView,
    queryKey: ["work-types", "options"],
    queryFn: () => api<Paginated<WorkType>>("/api/v1/work-types/?page_size=100"),
  });

  const config = useMemo(() => {
    return resource === "staff-locations"
      ? {
          title: "スタッフ所属",
          endpoint: "/api/v1/staff-locations/",
          initial: { staff: "", location: "", is_primary: false, valid_from: "", valid_until: "" } as FormState,
        }
      : {
          title: "スタッフ対応可能業務",
          endpoint: "/api/v1/staff-capabilities/",
          initial: {
            staff: "",
            work_type: "",
            location: "",
            level: "trainee",
            valid_from: "",
            valid_until: "",
            notes: "",
          } as FormState,
        };
  }, [resource]);

  const [form, setForm] = useState<FormState>(config.initial);
  useEffect(() => {
    setForm(config.initial);
    setEditingId(null);
  }, [config.initial]);

  const listQuery = useQuery({
    enabled: canView,
    queryKey: [resource, filters],
    queryFn: () =>
      api<Paginated<Record<string, unknown>>>(
        `${config.endpoint}?page_size=100`
        + `${filters.staff ? `&staff=${encodeURIComponent(filters.staff)}` : ""}`
        + `${filters.location ? `&location=${encodeURIComponent(filters.location)}` : ""}`
        + `${resource === "staff-capabilities" && filters.level ? `&level=${encodeURIComponent(filters.level)}` : ""}`,
      ),
  });

  if (!canView) {
    return <Navigate to="/403" replace />;
  }

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
        Object.entries(item).filter(([key]) => !["id", "created_at", "updated_at", "is_active", "approved_by", "approved_at"].includes(key)),
      ),
    } as FormState);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const payload = Object.fromEntries(Object.entries(form).filter(([, value]) => value !== ""));
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
      <div className="toolbar field-grid">
        <label>
          スタッフ絞り込み
          <select value={filters.staff} onChange={(e) => setFilters((current) => ({ ...current, staff: e.target.value }))}>
            <option value="">すべて</option>
            {staffQuery.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.display_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          施設絞り込み
          <select value={filters.location} onChange={(e) => setFilters((current) => ({ ...current, location: e.target.value }))}>
            <option value="">すべて</option>
            {locationQuery.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        {resource === "staff-capabilities" && (
          <label>
            レベル絞り込み
            <select value={filters.level} onChange={(e) => setFilters((current) => ({ ...current, level: e.target.value }))}>
              <option value="">すべて</option>
              <option value="trainee">trainee</option>
              <option value="assisted">assisted</option>
              <option value="independent">independent</option>
              <option value="trainer">trainer</option>
            </select>
          </label>
        )}
      </div>
      {canManage ? (
        <form className="form-grid compact-form" onSubmit={submit}>
          <div className="field-grid">
            <label>
              スタッフ
              <select value={String(form.staff ?? "")} onChange={(e) => setForm((current) => ({ ...current, staff: e.target.value }))}>
                <option value="">選択してください</option>
                {staffQuery.data?.results.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.display_name}
                  </option>
                ))}
              </select>
            </label>
            {resource === "staff-locations" ? (
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
                  有効開始日
                  <input type="date" value={String(form.valid_from ?? "")} onChange={(e) => setForm((current) => ({ ...current, valid_from: e.target.value }))} />
                </label>
                <label>
                  有効終了日
                  <input type="date" value={String(form.valid_until ?? "")} onChange={(e) => setForm((current) => ({ ...current, valid_until: e.target.value }))} />
                </label>
                <label className="checkbox">
                  <input type="checkbox" checked={Boolean(form.is_primary)} onChange={(e) => setForm((current) => ({ ...current, is_primary: e.target.checked }))} />
                  主所属
                </label>
              </>
            ) : (
              <>
                <label>
                  作業種別
                  <select value={String(form.work_type ?? "")} onChange={(e) => setForm((current) => ({ ...current, work_type: e.target.value }))}>
                    <option value="">選択してください</option>
                    {workTypeQuery.data?.results.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  施設
                  <select value={String(form.location ?? "")} onChange={(e) => setForm((current) => ({ ...current, location: e.target.value }))}>
                    <option value="">共通</option>
                    {locationQuery.data?.results.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  レベル
                  <select value={String(form.level ?? "")} onChange={(e) => setForm((current) => ({ ...current, level: e.target.value }))}>
                    <option value="trainee">trainee</option>
                    <option value="assisted">assisted</option>
                    <option value="independent">independent</option>
                    <option value="trainer">trainer</option>
                  </select>
                </label>
                <label>
                  有効開始日
                  <input type="date" value={String(form.valid_from ?? "")} onChange={(e) => setForm((current) => ({ ...current, valid_from: e.target.value }))} />
                </label>
                <label>
                  有効終了日
                  <input type="date" value={String(form.valid_until ?? "")} onChange={(e) => setForm((current) => ({ ...current, valid_until: e.target.value }))} />
                </label>
                <label className="full-width">
                  備考
                  <input value={String(form.notes ?? "")} onChange={(e) => setForm((current) => ({ ...current, notes: e.target.value }))} />
                </label>
              </>
            )}
          </div>
          {error ? <p className="error">{error}</p> : null}
          <div className="actions">
            {editingId ? (
              <button type="button" onClick={resetForm}>
                編集をキャンセル
              </button>
            ) : null}
            <button type="submit">{editingId ? "更新" : "新規作成"}</button>
          </div>
        </form>
      ) : null}
      <table className="table">
        <thead>
          <tr>
            <th>スタッフ</th>
            <th>{resource === "staff-locations" ? "施設" : "作業種別"}</th>
            <th>{resource === "staff-locations" ? "主所属" : "レベル"}</th>
            <th>有効開始日</th>
            <th>有効終了日</th>
            <th>状態</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {listQuery.data?.results.map((item) => (
            <tr key={String(item.id)}>
              <td>{String(item.staff_display_name ?? item.staff ?? "-")}</td>
              <td>{String(item.location_name ?? item.work_type_name ?? item.work_type ?? "-")}</td>
              <td>{resource === "staff-locations" ? (item.is_primary ? "主所属" : "-") : String(item.level ?? "-")}</td>
              <td>{String(item.valid_from ?? "-")}</td>
              <td>{String(item.valid_until ?? "-")}</td>
              <td>{item.is_active ? "有効" : "無効"}</td>
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
