import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import { buildOffsetOptions, offsetToLabel } from "../lib/timeOffsets";
import type { Location, Paginated, ShiftPattern, WorkArea, WorkType } from "../lib/types";

type SegmentForm = {
  id?: string;
  work_type: string;
  work_area: string;
  start_offset_minutes: number;
  end_offset_minutes: number;
  display_order: number;
  notes: string;
};

type PatternForm = {
  location: string;
  code: string;
  name: string;
  short_name: string;
  description: string;
  display_order: number;
  segments: SegmentForm[];
};

const emptyPattern: PatternForm = {
  location: "",
  code: "",
  name: "",
  short_name: "",
  description: "",
  display_order: 0,
  segments: [],
};

const timeOptions = buildOffsetOptions();

export function ShiftPatternsPage() {
  const { user } = useAuth();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const canView = canManage || roles.includes("supervisor");
  const [filters, setFilters] = useState({ location: "", is_active: "", search: "" });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PatternForm>(emptyPattern);
  const [isDirty, setIsDirty] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);

  const querySuffix = useMemo(
    () =>
      `?page_size=100${filters.location ? `&location=${filters.location}` : ""}${
        filters.is_active ? `&is_active=${filters.is_active}` : ""
      }${filters.search ? `&search=${encodeURIComponent(filters.search)}` : ""}`,
    [filters],
  );

  const patternQuery = useQuery({
    enabled: canView,
    queryKey: ["shift-patterns", filters],
    queryFn: () => api<Paginated<ShiftPattern>>(`/api/v1/shift-patterns/${querySuffix}`),
  });
  const locationQuery = useQuery({
    enabled: canView,
    queryKey: ["locations", "shift-options"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100&is_active=true"),
  });
  const workTypeQuery = useQuery({
    enabled: canView && Boolean(form.location),
    queryKey: ["work-types", "shift-options", form.location],
    queryFn: () => api<Paginated<WorkType>>(`/api/v1/work-types/?page_size=100&is_active=true&location=${form.location}`),
  });
  const workAreaQuery = useQuery({
    enabled: canView,
    queryKey: ["work-areas", "shift-options", form.location],
    queryFn: () => api<Paginated<WorkArea>>(`/api/v1/work-areas/?page_size=100&is_active=true${form.location ? `&location=${form.location}` : ""}`),
  });

  if (!canView) return <Navigate to="/403" replace />;

  const markForm = (patch: Partial<PatternForm>) => {
    setForm((current) => ({ ...current, ...patch }));
    setIsDirty(true);
  };

  const confirmDiscard = () => !isDirty || window.confirm("未保存の変更を破棄しますか？");

  const reset = () => {
    if (!confirmDiscard()) return;
    setEditingId(null);
    setForm(emptyPattern);
    setIsDirty(false);
    setError("");
    setMessage("");
  };

  const loadPattern = async (pattern: ShiftPattern) => {
    if (!confirmDiscard()) return;
    setError("");
    setMessage("");
    try {
      const detail = await api<ShiftPattern>(`/api/v1/shift-patterns/${pattern.id}/`);
      setEditingId(detail.id);
      setForm({
        location: detail.location,
        code: detail.code,
        name: detail.name,
        short_name: detail.short_name,
        description: detail.description,
        display_order: detail.display_order,
        segments:
          detail.segments
            ?.filter((segment) => segment.is_active)
            .map((segment) => ({
              id: segment.id,
              work_type: segment.work_type,
              work_area: segment.work_area ?? "",
              start_offset_minutes: segment.start_offset_minutes,
              end_offset_minutes: segment.end_offset_minutes,
              display_order: segment.display_order,
              notes: segment.notes,
            })) ?? [],
      });
      setIsDirty(false);
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : "詳細の取得に失敗しました。");
    }
  };

  const changeLocation = (location: string) => {
    markForm({
      location,
      segments: form.segments.map((segment) => ({ ...segment, work_type: "", work_area: "" })),
    });
  };

  const updateSegment = (index: number, patch: Partial<SegmentForm>) => {
    setForm((current) => ({
      ...current,
      segments: current.segments.map((segment, segmentIndex) => (segmentIndex === index ? { ...segment, ...patch } : segment)),
    }));
    setIsDirty(true);
  };

  const addSegment = () => {
    setForm((current) => ({
      ...current,
      segments: [
        ...current.segments,
        {
          work_type: "",
          work_area: "",
          start_offset_minutes: 540,
          end_offset_minutes: 600,
          display_order: (current.segments.length + 1) * 10,
          notes: "",
        },
      ],
    }));
    setIsDirty(true);
  };

  const removeSegment = (index: number) => {
    setForm((current) => ({ ...current, segments: current.segments.filter((_, segmentIndex) => segmentIndex !== index) }));
    setIsDirty(true);
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (isSubmitting) return;
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      await api(editingId ? `/api/v1/shift-patterns/${editingId}/` : "/api/v1/shift-patterns/", {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify({
          ...form,
          segments: form.segments.map((segment) => ({ ...segment, work_area: segment.work_area || null })),
        }),
      });
      setMessage("保存しました。");
      setEditingId(null);
      setForm(emptyPattern);
      setIsDirty(false);
      await patternQuery.refetch();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "保存に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleActive = async (pattern: ShiftPattern) => {
    const action = pattern.is_active ? "deactivate" : "reactivate";
    const label = pattern.is_active ? "無効化" : "再有効化";
    if (!window.confirm(`${pattern.name}を${label}しますか？`)) return;
    setActionId(pattern.id);
    setError("");
    try {
      await api(`/api/v1/shift-patterns/${pattern.id}/${action}/`, { method: "POST", body: JSON.stringify({ confirm: true }) });
      setMessage(`${label}しました。`);
      await patternQuery.refetch();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : `${label}に失敗しました。`);
    } finally {
      setActionId(null);
    }
  };

  const duplicate = async (pattern: ShiftPattern) => {
    const code = window.prompt("複製後のコード", `${pattern.code}_copy`);
    if (!code) return;
    const name = window.prompt("複製後の名称", `${pattern.name} コピー`);
    if (!name) return;
    const shortName = window.prompt("複製後の省略名", `${pattern.short_name}コピー`);
    if (!shortName) return;
    setActionId(pattern.id);
    try {
      await api(`/api/v1/shift-patterns/${pattern.id}/duplicate/`, {
        method: "POST",
        body: JSON.stringify({ code, name, short_name: shortName }),
      });
      setMessage("複製しました。");
      await patternQuery.refetch();
    } catch (duplicateError) {
      setError(duplicateError instanceof Error ? duplicateError.message : "複製に失敗しました。");
    } finally {
      setActionId(null);
    }
  };

  const workTypeMap = new Map((workTypeQuery.data?.results ?? []).map((item) => [item.id, item]));
  const previewSegments = [...form.segments].sort((a, b) => a.start_offset_minutes - b.start_offset_minutes);

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Shift settings</p>
          <h2>勤務パターン</h2>
        </div>
        {canManage ? <button type="button" onClick={reset}>新規作成</button> : null}
      </div>
      <div className="toolbar field-grid">
        <label>拠点<select value={filters.location} onChange={(e) => setFilters((c) => ({ ...c, location: e.target.value }))}><option value="">すべて</option>{locationQuery.data?.results.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label>
        <label>状態<select value={filters.is_active} onChange={(e) => setFilters((c) => ({ ...c, is_active: e.target.value }))}><option value="">すべて</option><option value="true">有効</option><option value="false">無効</option></select></label>
        <label>検索<input value={filters.search} onChange={(e) => setFilters((c) => ({ ...c, search: e.target.value }))} placeholder="名称・コード" /></label>
      </div>
      {patternQuery.isError ? <p className="error">一覧の取得に失敗しました。</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {patternQuery.isLoading ? <p>読み込み中...</p> : null}
      {!patternQuery.isLoading && patternQuery.data?.results.length === 0 ? <p className="subtle-text">勤務パターンはまだありません。</p> : null}
      <table className="table">
        <thead><tr><th>名称</th><th>拠点</th><th>時間</th><th>内訳</th><th>状態</th><th>操作</th></tr></thead>
        <tbody>
          {patternQuery.data?.results.map((pattern) => (
            <tr key={pattern.id}>
              <td><strong>{pattern.name}</strong><div className="subtle-text">{pattern.code} / {pattern.short_name}</div></td>
              <td>{pattern.location_name}</td>
              <td>{pattern.start_offset_minutes == null ? "-" : `${offsetToLabel(pattern.start_offset_minutes)} - ${offsetToLabel(pattern.end_offset_minutes ?? 0)}`}</td>
              <td>{pattern.segment_count}件 / 勤務{pattern.work_minutes}分 / 休憩{pattern.break_minutes}分</td>
              <td>{pattern.is_active ? "有効" : "無効"}</td>
              <td className="actions">
                <button type="button" onClick={() => void loadPattern(pattern)}>{canManage ? "編集" : "詳細"}</button>
                {canManage ? <button type="button" disabled={actionId === pattern.id} onClick={() => void duplicate(pattern)}>複製</button> : null}
                {canManage ? <button type="button" disabled={actionId === pattern.id} onClick={() => void toggleActive(pattern)}>{pattern.is_active ? "無効化" : "再有効化"}</button> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form className="form-grid compact-form" onSubmit={(event) => void save(event)}>
        <div className="section-header">
          <h3>{editingId ? "勤務パターン編集" : "勤務パターン新規作成"}</h3>
          {editingId ? <span className="subtle-text">拠点は作成後変更できません。別拠点用に複製してください。</span> : null}
        </div>
        <div className="field-grid">
          <label>拠点<select disabled={!canManage || Boolean(editingId)} value={form.location} onChange={(e) => changeLocation(e.target.value)}><option value="">選択してください</option>{locationQuery.data?.results.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label>
          <label>コード<input readOnly={!canManage} value={form.code} onChange={(e) => markForm({ code: e.target.value })} /></label>
          <label>名称<input readOnly={!canManage} value={form.name} onChange={(e) => markForm({ name: e.target.value })} /></label>
          <label>省略名<input readOnly={!canManage} value={form.short_name} onChange={(e) => markForm({ short_name: e.target.value })} /></label>
          <label>表示順<input readOnly={!canManage} type="number" value={form.display_order} onChange={(e) => markForm({ display_order: Number(e.target.value) })} /></label>
          <label className="full-width">説明<input readOnly={!canManage} value={form.description} onChange={(e) => markForm({ description: e.target.value })} /></label>
        </div>
        <div className="section-header"><h3>セグメント</h3>{canManage ? <button type="button" onClick={addSegment}>追加</button> : null}</div>
        {form.segments.map((segment, index) => (
          <div className="field-grid segment-row" key={`${segment.id ?? "new"}-${index}`}>
            <label>開始<select disabled={!canManage} value={segment.start_offset_minutes} onChange={(e) => updateSegment(index, { start_offset_minutes: Number(e.target.value) })}>{timeOptions.filter((option) => option.value < 2880).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
            <label>終了<select disabled={!canManage} value={segment.end_offset_minutes} onChange={(e) => updateSegment(index, { end_offset_minutes: Number(e.target.value) })}>{timeOptions.filter((option) => option.value > 0).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
            <label>業務種別<select disabled={!canManage} value={segment.work_type} onChange={(e) => updateSegment(index, { work_type: e.target.value })}><option value="">選択してください</option>{workTypeQuery.data?.results.map((workType) => <option key={workType.id} value={workType.id}>{workType.name}</option>)}</select></label>
            <label>業務エリア<select disabled={!canManage} value={segment.work_area} onChange={(e) => updateSegment(index, { work_area: e.target.value })}><option value="">全体</option>{workAreaQuery.data?.results.map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}</select></label>
            <label>備考<input readOnly={!canManage} value={segment.notes} onChange={(e) => updateSegment(index, { notes: e.target.value })} /></label>
            {canManage ? <div className="actions"><button type="button" onClick={() => removeSegment(index)}>削除</button></div> : null}
          </div>
        ))}
        <div className="timeline-preview">
          {previewSegments.map((segment, index) => {
            const workType = workTypeMap.get(segment.work_type);
            return <span key={`${segment.id ?? index}-preview`} className={`timeline-chip color-${workType?.color_key ?? "slate"}`}>{offsetToLabel(segment.start_offset_minutes)}-{offsetToLabel(segment.end_offset_minutes)} {workType?.short_name ?? "未選択"}</span>;
          })}
        </div>
        {canManage ? <button type="submit" disabled={isSubmitting}>{isSubmitting ? "保存中..." : "保存"}</button> : null}
      </form>
    </section>
  );
}
