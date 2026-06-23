import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type { Location, Paginated, ShiftPattern, StaffLocation, WeeklyShiftTemplate } from "../lib/types";

type TemplateForm = {
  location: string;
  code: string;
  name: string;
  description: string;
  display_order: number;
  staffIds: string[];
  assignments: Record<string, Record<number, string>>;
};

const emptyTemplate: TemplateForm = {
  location: "",
  code: "",
  name: "",
  description: "",
  display_order: 0,
  staffIds: [],
  assignments: {},
};

const weekdays = ["月", "火", "水", "木", "金", "土", "日"];

export function WeeklyTemplatesPage() {
  const { user } = useAuth();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const canView = canManage || roles.includes("supervisor");
  const [filters, setFilters] = useState({ location: "", is_active: "", search: "" });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<TemplateForm>(emptyTemplate);
  const [isDirty, setIsDirty] = useState(false);
  const [staffSearch, setStaffSearch] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [staffNames, setStaffNames] = useState<Record<string, string>>({});

  const querySuffix = useMemo(
    () =>
      `?page_size=100${filters.location ? `&location=${filters.location}` : ""}${
        filters.is_active ? `&is_active=${filters.is_active}` : ""
      }${filters.search ? `&search=${encodeURIComponent(filters.search)}` : ""}`,
    [filters],
  );

  const templateQuery = useQuery({
    enabled: canView,
    queryKey: ["weekly-shift-templates", filters],
    queryFn: () => api<Paginated<WeeklyShiftTemplate>>(`/api/v1/weekly-shift-templates/${querySuffix}`),
  });
  const locationQuery = useQuery({
    enabled: canView,
    queryKey: ["locations", "weekly-options"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100&is_active=true"),
  });
  const patternQuery = useQuery({
    enabled: canView && Boolean(form.location),
    queryKey: ["shift-patterns", "weekly-options", form.location],
    queryFn: () => api<Paginated<ShiftPattern>>(`/api/v1/shift-patterns/?page_size=100&is_active=true&location=${form.location}`),
  });
  const staffLocationQuery = useQuery({
    enabled: canView && Boolean(form.location),
    queryKey: ["staff-locations", "weekly-options", form.location, staffSearch],
    queryFn: () =>
      api<Paginated<StaffLocation>>(
        `/api/v1/staff-locations/?page_size=100&is_active=true&location=${form.location}${
          staffSearch ? `&staff_search=${encodeURIComponent(staffSearch)}` : ""
        }`,
      ),
  });

  if (!canView) return <Navigate to="/403" replace />;

  const staffOptions = Array.from(
    new Map((staffLocationQuery.data?.results ?? []).map((item) => [item.staff, item.staff_display_name ?? item.staff])).entries(),
  ).map(([id, name]) => ({ id, name }));

  const staffName = (staffId: string) =>
    staffOptions.find((staff) => staff.id === staffId)?.name
    ?? staffLocationQuery.data?.results.find((item) => item.staff === staffId)?.staff_display_name
    ?? staffNames[staffId]
    ?? staffId;

  const rememberStaffNames = (entries: Array<{ staff: string; staff_display_name?: string }>) => {
    setStaffNames((current) => {
      const next = { ...current };
      for (const entry of entries) {
        next[entry.staff] = entry.staff_display_name ?? next[entry.staff] ?? entry.staff;
      }
      return next;
    });
  };

  const markForm = (patch: Partial<TemplateForm>) => {
    setForm((current) => ({ ...current, ...patch }));
    setIsDirty(true);
  };

  const confirmDiscard = () => !isDirty || window.confirm("未保存の変更を破棄しますか？");

  const reset = () => {
    if (!confirmDiscard()) return;
    setEditingId(null);
    setForm(emptyTemplate);
    setStaffSearch("");
    setIsDirty(false);
    setError("");
    setMessage("");
  };

  const loadTemplate = async (template: WeeklyShiftTemplate) => {
    if (!confirmDiscard()) return;
    setError("");
    setMessage("");
    try {
      const detail = await api<WeeklyShiftTemplate>(`/api/v1/weekly-shift-templates/${template.id}/`);
      const assignments: Record<string, Record<number, string>> = {};
      const staffIds: string[] = [];
      const activeEntries = detail.entries?.filter((item) => item.is_active) ?? [];
      rememberStaffNames(activeEntries);
      for (const entry of activeEntries) {
        if (!staffIds.includes(entry.staff)) staffIds.push(entry.staff);
        assignments[entry.staff] = { ...(assignments[entry.staff] ?? {}), [entry.weekday]: entry.shift_pattern };
      }
      setEditingId(detail.id);
      setForm({
        location: detail.location,
        code: detail.code,
        name: detail.name,
        description: detail.description,
        display_order: detail.display_order,
        staffIds,
        assignments,
      });
      setIsDirty(false);
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : "詳細の取得に失敗しました。");
    }
  };

  const changeLocation = (location: string) => {
    markForm({ location, staffIds: [], assignments: {} });
  };

  const addStaff = (staffId: string) => {
    if (!staffId || form.staffIds.includes(staffId)) return;
    const option = staffOptions.find((staff) => staff.id === staffId);
    if (option) setStaffNames((current) => ({ ...current, [staffId]: option.name }));
    markForm({ staffIds: [...form.staffIds, staffId], assignments: { ...form.assignments, [staffId]: {} } });
  };

  const removeStaff = (staffId: string) => {
    markForm({ staffIds: form.staffIds.filter((id) => id !== staffId) });
  };

  const setAssignment = (staffId: string, weekday: number, patternId: string) => {
    markForm({
      assignments: {
        ...form.assignments,
        [staffId]: { ...(form.assignments[staffId] ?? {}), [weekday]: patternId },
      },
    });
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (isSubmitting) return;
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const detail = editingId ? await api<WeeklyShiftTemplate>(`/api/v1/weekly-shift-templates/${editingId}/`) : null;
      const entryIdMap = new Map((detail?.entries ?? []).map((entry) => [`${entry.staff}:${entry.weekday}`, entry.id]));
      const entries = form.staffIds.flatMap((staffId) =>
        weekdays
          .map((_, weekday) => {
            const patternId = form.assignments[staffId]?.[weekday];
            if (!patternId) return null;
            const id = entryIdMap.get(`${staffId}:${weekday}`);
            return { ...(id ? { id } : {}), weekday, staff: staffId, shift_pattern: patternId, notes: "", display_order: weekday * 10 };
          })
          .filter(Boolean),
      );
      await api(editingId ? `/api/v1/weekly-shift-templates/${editingId}/` : "/api/v1/weekly-shift-templates/", {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify({
          location: form.location,
          code: form.code,
          name: form.name,
          description: form.description,
          display_order: form.display_order,
          entries,
        }),
      });
      setMessage("保存しました。");
      setEditingId(null);
      setForm(emptyTemplate);
      setIsDirty(false);
      await templateQuery.refetch();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "保存に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleActive = async (template: WeeklyShiftTemplate) => {
    const action = template.is_active ? "deactivate" : "reactivate";
    const label = template.is_active ? "無効化" : "再有効化";
    if (!window.confirm(`${template.name}を${label}しますか？`)) return;
    setActionId(template.id);
    setError("");
    try {
      await api(`/api/v1/weekly-shift-templates/${template.id}/${action}/`, { method: "POST", body: JSON.stringify({ confirm: true }) });
      setMessage(`${label}しました。`);
      await templateQuery.refetch();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : `${label}に失敗しました。`);
    } finally {
      setActionId(null);
    }
  };

  const duplicate = async (template: WeeklyShiftTemplate) => {
    const code = window.prompt("複製後のコード", `${template.code}_copy`);
    if (!code) return;
    const name = window.prompt("複製後の名称", `${template.name} コピー`);
    if (!name) return;
    setActionId(template.id);
    try {
      await api(`/api/v1/weekly-shift-templates/${template.id}/duplicate/`, { method: "POST", body: JSON.stringify({ code, name }) });
      setMessage("複製しました。");
      await templateQuery.refetch();
    } catch (duplicateError) {
      setError(duplicateError instanceof Error ? duplicateError.message : "複製に失敗しました。");
    } finally {
      setActionId(null);
    }
  };

  return (
    <section className="card">
      <div className="section-header">
        <div><p className="eyebrow">Shift settings</p><h2>週間テンプレート</h2></div>
        {canManage ? <button type="button" onClick={reset}>新規作成</button> : null}
      </div>
      <div className="toolbar field-grid">
        <label>拠点<select value={filters.location} onChange={(e) => setFilters((c) => ({ ...c, location: e.target.value }))}><option value="">すべて</option>{locationQuery.data?.results.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label>
        <label>状態<select value={filters.is_active} onChange={(e) => setFilters((c) => ({ ...c, is_active: e.target.value }))}><option value="">すべて</option><option value="true">有効</option><option value="false">無効</option></select></label>
        <label>検索<input value={filters.search} onChange={(e) => setFilters((c) => ({ ...c, search: e.target.value }))} placeholder="名称・コード" /></label>
      </div>
      {templateQuery.isError ? <p className="error">一覧の取得に失敗しました。</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {templateQuery.isLoading ? <p>読み込み中...</p> : null}
      {!templateQuery.isLoading && templateQuery.data?.results.length === 0 ? <p className="subtle-text">週間テンプレートはまだありません。</p> : null}
      <table className="table">
        <thead><tr><th>名称</th><th>拠点</th><th>件数</th><th>状態</th><th>操作</th></tr></thead>
        <tbody>
          {templateQuery.data?.results.map((template) => (
            <tr key={template.id}>
              <td><strong>{template.name}</strong><div className="subtle-text">{template.code}</div></td>
              <td>{template.location_name}</td>
              <td>{template.staff_count}名 / {template.entry_count}件</td>
              <td>{template.is_active ? "有効" : "無効"}</td>
              <td className="actions">
                <button type="button" onClick={() => void loadTemplate(template)}>{canManage ? "編集" : "詳細"}</button>
                {canManage ? <button type="button" disabled={actionId === template.id} onClick={() => void duplicate(template)}>複製</button> : null}
                {canManage ? <button type="button" disabled={actionId === template.id} onClick={() => void toggleActive(template)}>{template.is_active ? "無効化" : "再有効化"}</button> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form className="form-grid compact-form" onSubmit={(event) => void save(event)}>
        <div className="section-header">
          <h3>{editingId ? "週間テンプレート編集" : "週間テンプレート新規作成"}</h3>
          {editingId ? <span className="subtle-text">拠点は作成後変更できません。別拠点用に複製してください。</span> : null}
        </div>
        <div className="field-grid">
          <label>拠点<select disabled={!canManage || Boolean(editingId)} value={form.location} onChange={(e) => changeLocation(e.target.value)}><option value="">選択してください</option>{locationQuery.data?.results.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label>
          <label>コード<input readOnly={!canManage} value={form.code} onChange={(e) => markForm({ code: e.target.value })} /></label>
          <label>名称<input readOnly={!canManage} value={form.name} onChange={(e) => markForm({ name: e.target.value })} /></label>
          <label>表示順<input readOnly={!canManage} type="number" value={form.display_order} onChange={(e) => markForm({ display_order: Number(e.target.value) })} /></label>
          <label className="full-width">説明<input readOnly={!canManage} value={form.description} onChange={(e) => markForm({ description: e.target.value })} /></label>
        </div>
        {canManage ? <div className="field-grid"><label>スタッフ検索<input value={staffSearch} onChange={(e) => setStaffSearch(e.target.value)} placeholder="スタッフ名で検索" /></label><label>スタッフ追加<select value="" onChange={(e) => addStaff(e.target.value)}><option value="">選択してください</option>{staffOptions.filter((staff) => !form.staffIds.includes(staff.id)).map((staff) => <option key={staff.id} value={staff.id}>{staff.name}</option>)}</select></label></div> : null}
        <div className="weekly-grid-wrap">
          <table className="table weekly-grid">
            <thead><tr><th>スタッフ</th>{weekdays.map((day) => <th key={day}>{day}</th>)}{canManage ? <th>操作</th> : null}</tr></thead>
            <tbody>
              {form.staffIds.map((staffId) => (
                <tr key={staffId}>
                  <td>{staffName(staffId)}</td>
                  {weekdays.map((day, weekday) => (
                    <td key={`${staffId}-${day}`}>
                      <select disabled={!canManage} value={form.assignments[staffId]?.[weekday] ?? ""} onChange={(e) => setAssignment(staffId, weekday, e.target.value)}>
                        <option value="">勤務なし</option>
                        {patternQuery.data?.results
                          .filter((pattern) => pattern.location === form.location)
                          .map((pattern) => <option key={pattern.id} value={pattern.id}>{pattern.short_name}</option>)}
                      </select>
                    </td>
                  ))}
                  {canManage ? <td><button type="button" onClick={() => removeStaff(staffId)}>行削除</button></td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {form.staffIds.length === 0 ? <p className="subtle-text">スタッフを追加してください。</p> : null}
        {canManage ? <button type="submit" disabled={isSubmitting}>{isSubmitting ? "保存中..." : "保存"}</button> : null}
      </form>
    </section>
  );
}
