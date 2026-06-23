import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import { buildOffsetOptions, offsetToLabel } from "../lib/timeOffsets";
import type {
  Location,
  MonthlyShiftAssignment,
  MonthlyShiftMatrix,
  MonthlyShiftPlan,
  MonthlyShiftSegment,
  Paginated,
  ShiftPattern,
  TemplateGenerationResult,
  WeeklyShiftTemplate,
  WorkArea,
  WorkType,
} from "../lib/types";

type CellSelection = {
  staff: string;
  staffName: string;
  workDate: string;
  assignmentId?: string;
};

type SegmentForm = {
  id?: string;
  work_type: string;
  work_area: string | null;
  start_offset_minutes: number;
  end_offset_minutes: number;
  display_order: number;
  notes: string;
};

const today = new Date();
const defaultYear = today.getFullYear();
const defaultMonth = today.getMonth() + 1;
const timeOptions = buildOffsetOptions();

function toSegmentForm(segment: MonthlyShiftSegment): SegmentForm {
  return {
    id: segment.id,
    work_type: segment.work_type,
    work_area: segment.work_area,
    start_offset_minutes: segment.start_offset_minutes,
    end_offset_minutes: segment.end_offset_minutes,
    display_order: segment.display_order,
    notes: segment.notes,
  };
}

export function MonthlyShiftsPage() {
  const { user } = useAuth();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const canView = canManage || roles.includes("supervisor");
  const [location, setLocation] = useState("");
  const [year, setYear] = useState(defaultYear);
  const [month, setMonth] = useState(defaultMonth);
  const [plan, setPlan] = useState<MonthlyShiftPlan | null>(null);
  const [staffSearch, setStaffSearch] = useState("");
  const [assignedOnly, setAssignedOnly] = useState(false);
  const [selected, setSelected] = useState<CellSelection | null>(null);
  const [assignment, setAssignment] = useState<MonthlyShiftAssignment | null>(null);
  const [selectedPattern, setSelectedPattern] = useState("");
  const [segments, setSegments] = useState<SegmentForm[]>([]);
  const [notes, setNotes] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [existingMode, setExistingMode] = useState<"skip_existing" | "replace_template_generated">("skip_existing");
  const [invalidMode, setInvalidMode] = useState<"strict" | "skip_invalid">("strict");
  const [preview, setPreview] = useState<TemplateGenerationResult | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const locationQuery = useQuery({
    enabled: canView,
    queryKey: ["locations", "monthly"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100&is_active=true"),
  });
  const planQuery = useQuery({
    enabled: canView && Boolean(location),
    queryKey: ["monthly-shift-plans", location, year, month],
    queryFn: () =>
      api<Paginated<MonthlyShiftPlan>>(
        `/api/v1/monthly-shift-plans/?page_size=10&location=${location}&year=${year}&month=${month}&is_active=true`,
      ),
  });
  const matrixQuery = useQuery({
    enabled: canView && Boolean(plan),
    queryKey: ["monthly-shift-matrix", plan?.id, staffSearch, assignedOnly],
    queryFn: () =>
      api<MonthlyShiftMatrix>(
        `/api/v1/monthly-shift-plans/${plan?.id}/matrix/?staff_search=${encodeURIComponent(staffSearch)}${
          assignedOnly ? "&assigned_only=true" : ""
        }`,
      ),
  });
  const patternQuery = useQuery({
    enabled: canView && Boolean(plan?.location),
    queryKey: ["shift-patterns", "monthly", plan?.location],
    queryFn: () => api<Paginated<ShiftPattern>>(`/api/v1/shift-patterns/?page_size=100&is_active=true&location=${plan?.location}`),
  });
  const templateQuery = useQuery({
    enabled: canView && Boolean(plan?.location),
    queryKey: ["weekly-shift-templates", "monthly", plan?.location],
    queryFn: () =>
      api<Paginated<WeeklyShiftTemplate>>(`/api/v1/weekly-shift-templates/?page_size=100&is_active=true&location=${plan?.location}`),
  });
  const workTypeQuery = useQuery({
    enabled: canView && Boolean(plan?.location),
    queryKey: ["work-types", "monthly", plan?.location],
    queryFn: () => api<Paginated<WorkType>>(`/api/v1/work-types/?page_size=100&is_active=true&location=${plan?.location}`),
  });
  const workAreaQuery = useQuery({
    enabled: canView && Boolean(plan?.location),
    queryKey: ["work-areas", "monthly", plan?.location],
    queryFn: () => api<Paginated<WorkArea>>(`/api/v1/work-areas/?page_size=100&is_active=true&location=${plan?.location}`),
  });

  const selectedPatternSegments = useMemo(
    () => patternQuery.data?.results.find((pattern) => pattern.id === selectedPattern)?.segments ?? [],
    [patternQuery.data?.results, selectedPattern],
  );

  if (!canView) return <Navigate to="/403" replace />;

  const changeMonth = (delta: number) => {
    const next = new Date(year, month - 1 + delta, 1);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
    setPlan(null);
    setSelected(null);
  };

  const openOrCreatePlan = async () => {
    setError("");
    setMessage("");
    const existing = planQuery.data?.results[0];
    if (existing) {
      setPlan(existing);
      return;
    }
    if (!canManage) return;
    try {
      const locationName = locationQuery.data?.results.find((item) => item.id === location)?.name ?? "";
      const created = await api<MonthlyShiftPlan>("/api/v1/monthly-shift-plans/", {
        method: "POST",
        body: JSON.stringify({ location, year, month, name: `${year}年${month}月 ${locationName}シフト`, notes: "" }),
      });
      setPlan(created);
      setMessage("月間表を作成しました。");
      await planQuery.refetch();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "月間表の作成に失敗しました。");
    }
  };

  const loadAssignment = async (selection: CellSelection) => {
    if (isDirty && !window.confirm("未保存の変更を破棄しますか？")) return;
    setSelected(selection);
    setError("");
    setMessage("");
    if (!selection.assignmentId) {
      setAssignment(null);
      setSelectedPattern("");
      setSegments([]);
      setNotes("");
      setIsDirty(false);
      return;
    }
    try {
      const detail = await api<MonthlyShiftAssignment>(`/api/v1/monthly-shift-assignments/${selection.assignmentId}/`);
      setAssignment(detail);
      setSelectedPattern(detail.source_shift_pattern ?? "");
      setSegments((detail.segments ?? []).filter((segment) => segment.is_active).map(toSegmentForm));
      setNotes(detail.notes);
      setIsDirty(false);
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : "勤務詳細の取得に失敗しました。");
    }
  };

  const choosePattern = (patternId: string) => {
    if (assignment && patternId && patternId !== selectedPattern && !window.confirm("現在の勤務内訳を選択したパターンで置き換えます。")) {
      return;
    }
    setSelectedPattern(patternId);
    setIsDirty(true);
  };

  const updateSegment = (index: number, patch: Partial<SegmentForm>) => {
    setSegments((current) => current.map((segment, i) => (i === index ? { ...segment, ...patch } : segment)));
    setIsDirty(true);
  };

  const addSegment = () => {
    setSegments((current) => [
      ...current,
      { work_type: "", work_area: null, start_offset_minutes: 540, end_offset_minutes: 600, display_order: current.length * 10, notes: "" },
    ]);
    setIsDirty(true);
  };

  const removeSegment = (index: number) => {
    setSegments((current) => current.filter((_, i) => i !== index));
    setIsDirty(true);
  };

  const saveAssignment = async () => {
    if (!selected || !plan || isSubmitting) return;
    setIsSubmitting(true);
    setError("");
    try {
      if (assignment) {
        await api<MonthlyShiftAssignment>(`/api/v1/monthly-shift-assignments/${assignment.id}/`, {
          method: "PATCH",
          body: JSON.stringify({
            notes,
            ...(selectedPattern && selectedPattern !== assignment.source_shift_pattern
              ? { shift_pattern: selectedPattern }
              : { segments }),
          }),
        });
      } else {
        await api<MonthlyShiftAssignment>("/api/v1/monthly-shift-assignments/", {
          method: "POST",
          body: JSON.stringify({
            monthly_shift_plan: plan.id,
            work_date: selected.workDate,
            staff: selected.staff,
            shift_pattern: selectedPattern,
            notes,
          }),
        });
      }
      setMessage("保存しました。");
      setIsDirty(false);
      await matrixQuery.refetch();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "保存に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const deactivateAssignment = async () => {
    if (!assignment || !window.confirm("勤務を解除しますか？")) return;
    setIsSubmitting(true);
    try {
      await api(`/api/v1/monthly-shift-assignments/${assignment.id}/deactivate/`, { method: "POST", body: JSON.stringify({}) });
      setSelected(null);
      setAssignment(null);
      setMessage("勤務を解除しました。");
      await matrixQuery.refetch();
    } catch (deactivateError) {
      setError(deactivateError instanceof Error ? deactivateError.message : "解除に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const previewTemplate = async () => {
    if (!plan || !templateId) return;
    setError("");
    try {
      const result = await api<TemplateGenerationResult>(`/api/v1/monthly-shift-plans/${plan.id}/preview-template-generation/`, {
        method: "POST",
        body: JSON.stringify({ weekly_shift_template: templateId, existing_mode: existingMode, invalid_mode: invalidMode }),
      });
      setPreview(result);
    } catch (previewError) {
      setError(previewError instanceof Error ? previewError.message : "生成プレビューに失敗しました。");
    }
  };

  const applyTemplate = async () => {
    if (!plan || !templateId || isSubmitting) return;
    if (existingMode === "replace_template_generated" && !window.confirm("テンプレート生成済み勤務を置換します。")) return;
    setIsSubmitting(true);
    setError("");
    try {
      const result = await api<TemplateGenerationResult>(`/api/v1/monthly-shift-plans/${plan.id}/apply-template/`, {
        method: "POST",
        body: JSON.stringify({ weekly_shift_template: templateId, existing_mode: existingMode, invalid_mode: invalidMode }),
      });
      setPreview(result);
      setMessage("テンプレートを適用しました。");
      await matrixQuery.refetch();
    } catch (applyError) {
      setError(applyError instanceof Error ? applyError.message : "テンプレート適用に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="card monthly-page">
      <div className="section-header">
        <div><p className="eyebrow">Shift planning</p><h2>月間シフト</h2></div>
      </div>
      <div className="toolbar field-grid">
        <label>拠点<select value={location} onChange={(event) => { setLocation(event.target.value); setPlan(null); }}><option value="">選択してください</option>{locationQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>年<input type="number" value={year} onChange={(event) => { setYear(Number(event.target.value)); setPlan(null); }} /></label>
        <label>月<input type="number" min={1} max={12} value={month} onChange={(event) => { setMonth(Number(event.target.value)); setPlan(null); }} /></label>
        <button type="button" onClick={() => changeMonth(-1)}>前月</button>
        <button type="button" onClick={() => changeMonth(1)}>次月</button>
        <button type="button" disabled={!location} onClick={() => void openOrCreatePlan()}>{planQuery.data?.results[0] ? "月間表を開く" : "新規作成"}</button>
      </div>
      <div className="toolbar field-grid">
        <label>週間テンプレート<select value={templateId} disabled={!plan} onChange={(event) => setTemplateId(event.target.value)}><option value="">選択してください</option>{templateQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>既存<select value={existingMode} onChange={(event) => setExistingMode(event.target.value as typeof existingMode)}><option value="skip_existing">既存を保持</option><option value="replace_template_generated">生成済みを置換</option></select></label>
        <label>不正候補<select value={invalidMode} onChange={(event) => setInvalidMode(event.target.value as typeof invalidMode)}><option value="strict">strict</option><option value="skip_invalid">skip_invalid</option></select></label>
        <button type="button" disabled={!templateId || !plan} onClick={() => void previewTemplate()}>生成プレビュー</button>
        {canManage ? <button type="button" disabled={!preview || (invalidMode === "strict" && preview.summary.error_count > 0) || isSubmitting} onClick={() => void applyTemplate()}>テンプレート適用</button> : null}
      </div>
      <div className="toolbar field-grid">
        <label>スタッフ検索<input value={staffSearch} onChange={(event) => setStaffSearch(event.target.value)} /></label>
        <label><input type="checkbox" checked={assignedOnly} onChange={(event) => setAssignedOnly(event.target.checked)} /> 勤務ありのみ</label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {matrixQuery.isError ? <p className="error">月間表の取得に失敗しました。</p> : null}
      {!plan ? <p className="subtle-text">拠点と年月を選び、月間表を開いてください。</p> : null}
      {plan && matrixQuery.isLoading ? <p>読み込み中...</p> : null}
      <div className="monthly-layout">
        <div className="monthly-grid-wrap">
          <table className="table monthly-grid">
            <thead>
              <tr><th className="sticky-col">スタッフ</th>{matrixQuery.data?.dates.map((item) => <th key={item.date} className={item.is_saturday ? "saturday" : item.is_sunday ? "sunday" : ""}>{item.day}<br />{item.weekday_label}</th>)}</tr>
            </thead>
            <tbody>
              {matrixQuery.data?.rows.map((row) => (
                <tr key={row.staff}>
                  <th className="sticky-col">{row.staff_display_name}<div className="subtle-text">{row.employee_code}</div></th>
                  {matrixQuery.data.dates.map((item) => {
                    const cell = row.assignments[item.date];
                    return (
                      <td key={`${row.staff}-${item.date}`} className={item.is_saturday ? "saturday" : item.is_sunday ? "sunday" : ""}>
                        <button type="button" className="shift-cell" disabled={!canManage && !cell} onClick={() => void loadAssignment({ staff: row.staff, staffName: row.staff_display_name, workDate: item.date, assignmentId: cell?.id })}>
                          {cell ? <><strong>{cell.pattern_short_name}</strong><span>{cell.start_offset_minutes != null ? offsetToLabel(cell.start_offset_minutes) : ""}~{cell.end_offset_minutes != null ? offsetToLabel(cell.end_offset_minutes) : ""}</span>{cell.is_customized ? <em>調整</em> : null}{cell.warning_count ? <em>警告</em> : null}</> : <span className="subtle-text">+</span>}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selected ? (
          <aside className="edit-panel">
            <h3>{selected.staffName}</h3>
            <p className="subtle-text">{selected.workDate}</p>
            <label>勤務パターン<select disabled={!canManage} value={selectedPattern} onChange={(event) => choosePattern(event.target.value)}><option value="">選択してください</option>{patternQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            {selectedPatternSegments.length ? <p className="subtle-text">選択パターン: {selectedPatternSegments.length} セグメント</p> : null}
            <label>備考<input readOnly={!canManage} value={notes} onChange={(event) => { setNotes(event.target.value); setIsDirty(true); }} /></label>
            <div className="section-header"><h3>勤務内訳</h3>{canManage ? <button type="button" onClick={addSegment}>追加</button> : null}</div>
            {segments.map((segment, index) => (
              <div className="segment-editor" key={segment.id ?? index}>
                <label>開始<select disabled={!canManage} value={segment.start_offset_minutes} onChange={(event) => updateSegment(index, { start_offset_minutes: Number(event.target.value) })}>{timeOptions.filter((item) => item.value < 2880).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
                <label>終了<select disabled={!canManage} value={segment.end_offset_minutes} onChange={(event) => updateSegment(index, { end_offset_minutes: Number(event.target.value) })}>{timeOptions.filter((item) => item.value > 0).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
                <label>業務<select disabled={!canManage} value={segment.work_type} onChange={(event) => updateSegment(index, { work_type: event.target.value })}><option value="">選択</option>{workTypeQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label>エリア<select disabled={!canManage} value={segment.work_area ?? ""} onChange={(event) => updateSegment(index, { work_area: event.target.value || null })}><option value="">全体</option>{workAreaQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label>備考<input readOnly={!canManage} value={segment.notes} onChange={(event) => updateSegment(index, { notes: event.target.value })} /></label>
                {canManage ? <button type="button" onClick={() => removeSegment(index)}>削除</button> : null}
              </div>
            ))}
            {canManage ? <div className="actions"><button type="button" disabled={isSubmitting || (!assignment && !selectedPattern)} onClick={() => void saveAssignment()}>{isSubmitting ? "保存中..." : "保存"}</button>{assignment ? <button type="button" disabled={isSubmitting} onClick={() => void deactivateAssignment()}>勤務解除</button> : null}</div> : null}
          </aside>
        ) : null}
      </div>
      {preview ? (
        <section className="preview-panel">
          <h3>生成プレビュー</h3>
          <p>候補 {preview.summary.candidate_count} / 作成 {preview.summary.create_count} / 置換 {preview.summary.replace_count} / 既存スキップ {preview.summary.skip_existing_count} / 保護スキップ {preview.summary.skip_manual_count} / エラー {preview.summary.error_count} / 警告 {preview.summary.warning_count}</p>
          {preview.summary.created_count != null ? <p className="success">適用結果: 作成 {preview.summary.created_count} / 置換 {preview.summary.replaced_count} / スキップ {preview.summary.skipped_count}</p> : null}
          <table className="table"><thead><tr><th>日付</th><th>スタッフ</th><th>勤務</th><th>action</th><th>issue</th></tr></thead><tbody>{preview.items.slice(0, 80).map((item) => <tr key={`${item.work_date}-${item.staff}-${item.shift_pattern}`}><td>{item.work_date}</td><td>{item.staff_display_name}</td><td>{item.shift_pattern_short_name}</td><td>{item.action}</td><td>{item.issues.map((issue) => `${issue.severity}:${issue.message}`).join(" / ")}</td></tr>)}</tbody></table>
        </section>
      ) : null}
    </section>
  );
}
