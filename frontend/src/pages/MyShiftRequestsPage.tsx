import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { offsetToLabel } from "../lib/timeOffsets";
import type { Paginated, ShiftRequestItem, ShiftRequestPeriod, ShiftRequestSubmission } from "../lib/types";

const emptyItem = (request_type: ShiftRequestItem["request_type"]): ShiftRequestItem => ({
  request_type,
  work_date: request_type === "note" ? null : new Date().toISOString().slice(0, 10),
  start_offset_minutes: request_type === "unavailable" || request_type === "prefer_time" ? 540 : null,
  end_offset_minutes: request_type === "unavailable" || request_type === "prefer_time" ? 600 : null,
  work_type: null,
  work_area: null,
  priority: "normal",
  reason: "",
  notes: "",
});

export function MyShiftRequestsPage() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [location, setLocation] = useState("");
  const [selectedPeriod, setSelectedPeriod] = useState<ShiftRequestPeriod | null>(null);
  const [submission, setSubmission] = useState<ShiftRequestSubmission | null>(null);
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<ShiftRequestItem[]>([]);
  const [error, setError] = useState("");
  const periodsQuery = useQuery({
    queryKey: ["my-shift-request-periods", year, month, location],
    queryFn: () =>
      api<ShiftRequestPeriod[]>(
        `/api/v1/my-shift-request-periods/?year=${year}&month=${month}${location ? `&location=${location}` : ""}`,
      ),
  });
  const locationQuery = useQuery({
    queryKey: ["locations", "my-shift-requests"],
    queryFn: () => api<Paginated<{ id: string; name: string }>>("/api/v1/locations/?page_size=100&is_active=true"),
  });

  const changeMonth = (delta: number) => {
    const next = new Date(year, month - 1 + delta, 1);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
    setSelectedPeriod(null);
    setSubmission(null);
  };

  const loadSubmission = async (period: ShiftRequestPeriod) => {
    setSelectedPeriod(period);
    setError("");
    try {
      const result = await api<ShiftRequestSubmission>(`/api/v1/my-shift-request-periods/${period.id}/submission/`);
      setSubmission(result);
      setNotes(result.notes);
      setItems(result.items);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "希望提出の取得に失敗しました。");
    }
  };

  const save = async () => {
    if (!selectedPeriod || !submission?.can_edit) return;
    const result = await api<ShiftRequestSubmission>(`/api/v1/my-shift-request-periods/${selectedPeriod.id}/submission/`, {
      method: "PUT",
      body: JSON.stringify({ notes, items }),
    });
    setSubmission(result);
    setItems(result.items);
    setNotes(result.notes);
  };

  const submit = async () => {
    if (!selectedPeriod) return;
    const result = await api<ShiftRequestSubmission>(`/api/v1/my-shift-request-periods/${selectedPeriod.id}/submit/`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    setSubmission(result);
  };

  const unsubmit = async () => {
    if (!selectedPeriod) return;
    const result = await api<ShiftRequestSubmission>(`/api/v1/my-shift-request-periods/${selectedPeriod.id}/unsubmit/`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    setSubmission(result);
  };

  const updateItem = (index: number, patch: Partial<ShiftRequestItem>) => {
    setItems((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  };

  return (
    <section className="card monthly-page">
      <div className="section-header"><div><p className="eyebrow">My shift requests</p><h2>希望提出</h2></div></div>
      <div className="toolbar field-grid">
        <label>年<input type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} /></label>
        <label>月<input type="number" min={1} max={12} value={month} onChange={(event) => setMonth(Number(event.target.value))} /></label>
        <button type="button" onClick={() => changeMonth(-1)}>前月</button>
        <button type="button" onClick={() => changeMonth(1)}>次月</button>
        <button type="button" onClick={() => { setYear(today.getFullYear()); setMonth(today.getMonth() + 1); }}>今月</button>
        <label>拠点<select value={location} onChange={(event) => setLocation(event.target.value)}><option value="">すべて</option>{locationQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {periodsQuery.isLoading ? <p>読み込み中...</p> : null}
      {periodsQuery.isError ? <p className="error">希望提出期間の取得に失敗しました。</p> : null}
      {!periodsQuery.isLoading && !periodsQuery.isError && periodsQuery.data?.length === 0 ? <p className="subtle-text">希望提出期間はありません。</p> : null}
      <table className="table"><thead><tr><th>拠点</th><th>年月</th><th>status</th><th>締切</th><th></th></tr></thead><tbody>{periodsQuery.data?.map((period) => <tr key={period.id}><td>{period.location_name}</td><td>{period.year}/{period.month}</td><td>{period.status}</td><td>{period.closes_at}</td><td><button type="button" onClick={() => void loadSubmission(period)}>開く</button></td></tr>)}</tbody></table>
      {submission ? <section className="preview-panel"><h3>{selectedPeriod?.name}</h3><p>提出status: {submission.status} / 締切 {submission.period.closes_at}</p>{submission.return_reason ? <p className="error">{submission.return_reason}</p> : null}
        <label>メモ<textarea readOnly={!submission.can_edit} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
        <div className="actions">
          <button type="button" disabled={!submission.can_edit} onClick={() => setItems((current) => [...current, emptyItem("day_off")])}>希望休追加</button>
          <button type="button" disabled={!submission.can_edit} onClick={() => setItems((current) => [...current, emptyItem("unavailable")])}>勤務不可時間追加</button>
          <button type="button" disabled={!submission.can_edit} onClick={() => setItems((current) => [...current, emptyItem("prefer_work")])}>勤務希望日追加</button>
          <button type="button" disabled={!submission.can_edit} onClick={() => setItems((current) => [...current, emptyItem("prefer_time")])}>勤務希望時間追加</button>
          <button type="button" disabled={!submission.can_edit} onClick={() => setItems((current) => [...current, emptyItem("note")])}>メモ追加</button>
        </div>
        {items.map((item, index) => <div className="segment-editor" key={`${item.id ?? "new"}-${index}`}>
          <label>種別<select disabled={!submission.can_edit} value={item.request_type} onChange={(event) => updateItem(index, { request_type: event.target.value as ShiftRequestItem["request_type"] })}><option value="day_off">希望休</option><option value="unavailable">勤務不可</option><option value="prefer_work">勤務希望日</option><option value="prefer_time">勤務希望時間</option><option value="note">メモ</option></select></label>
          <label>日付<input readOnly={!submission.can_edit} type="date" value={item.work_date ?? ""} onChange={(event) => updateItem(index, { work_date: event.target.value || null })} /></label>
          <label>開始<input readOnly={!submission.can_edit} type="number" step={15} min={0} max={2879} value={item.start_offset_minutes ?? ""} onChange={(event) => updateItem(index, { start_offset_minutes: event.target.value ? Number(event.target.value) : null })} /></label>
          <label>終了<input readOnly={!submission.can_edit} type="number" step={15} min={1} max={2880} value={item.end_offset_minutes ?? ""} onChange={(event) => updateItem(index, { end_offset_minutes: event.target.value ? Number(event.target.value) : null })} /></label>
          <span>{item.start_offset_minutes != null ? offsetToLabel(item.start_offset_minutes) : ""}~{item.end_offset_minutes != null ? offsetToLabel(item.end_offset_minutes) : ""}</span>
          <label>優先度<select disabled={!submission.can_edit} value={item.priority} onChange={(event) => updateItem(index, { priority: event.target.value as ShiftRequestItem["priority"] })}><option value="high">high</option><option value="normal">normal</option><option value="low">low</option></select></label>
          <label>理由<input readOnly={!submission.can_edit} value={item.reason} onChange={(event) => updateItem(index, { reason: event.target.value })} /></label>
          <label>備考<input readOnly={!submission.can_edit} value={item.notes} onChange={(event) => updateItem(index, { notes: event.target.value })} /></label>
          <button type="button" disabled={!submission.can_edit} onClick={() => setItems((current) => current.filter((_, itemIndex) => itemIndex !== index))}>削除</button>
        </div>)}
        <div className="actions"><button type="button" disabled={!submission.can_edit} onClick={() => void save()}>下書き保存</button><button type="button" disabled={!submission.can_submit} onClick={() => void submit()}>提出</button><button type="button" disabled={submission.status !== "submitted"} onClick={() => void unsubmit()}>提出取消</button></div>
      </section> : null}
    </section>
  );
}
