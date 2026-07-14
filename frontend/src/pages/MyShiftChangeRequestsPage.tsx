import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { formatLocalIsoDate } from "../lib/localDate";
import { offsetToLabel } from "../lib/timeOffsets";
import type { Paginated, ShiftChangeRequest, Staff } from "../lib/types";

const today = new Date();
const emptyRequests: ShiftChangeRequest[] = [];
const requestTypeOptions: Array<{ value: ShiftChangeRequest["request_type"]; label: string }> = [
  { value: "drop_shift", label: "勤務辞退" },
  { value: "swap_shift", label: "勤務交換" },
  { value: "cover_request", label: "代行依頼" },
  { value: "change_time", label: "時間変更" },
  { value: "change_assignment", label: "業務変更" },
  { value: "note", label: "相談メモ" },
];
const statusOptions: Array<{ value: ShiftChangeRequest["status"] | ""; label: string }> = [
  { value: "", label: "すべて" },
  { value: "draft", label: "draft" },
  { value: "submitted", label: "submitted" },
  { value: "approved", label: "approved" },
  { value: "rejected", label: "rejected" },
  { value: "cancelled", label: "cancelled" },
  { value: "applied", label: "applied" },
  { value: "closed", label: "closed" },
];
const priorityOptions: ShiftChangeRequest["priority"][] = ["high", "normal", "low"];

function defaultFilters() {
  return {
    date_from: formatLocalIsoDate(new Date(today.getFullYear(), today.getMonth(), 1)),
    date_to: formatLocalIsoDate(new Date(today.getFullYear(), today.getMonth() + 1, 0)),
    location: "",
    status: "",
    request_type: "",
  };
}

function requestPayload(form: ShiftChangeRequest) {
  return {
    request_type: form.request_type,
    priority: form.priority,
    requested_staff: form.requested_staff || null,
    requested_work_date: form.requested_work_date || null,
    requested_shift_pattern: form.requested_shift_pattern || null,
    requested_start_offset_minutes: form.requested_start_offset_minutes,
    requested_end_offset_minutes: form.requested_end_offset_minutes,
    requested_notes: form.requested_notes,
    reason: form.reason,
  };
}

export function MyShiftChangeRequestsPage() {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState(defaultFilters);
  const [selected, setSelected] = useState<ShiftChangeRequest | null>(null);
  const [form, setForm] = useState<ShiftChangeRequest | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const queryString = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString();

  const requestsQuery = useQuery({
    queryKey: ["my-shift-change-requests", filters],
    queryFn: () => api<Paginated<ShiftChangeRequest>>(`/api/v1/my-shift-change-requests/?${queryString}`),
  });
  const staffQuery = useQuery({
    queryKey: ["shift-change-staff-options"],
    queryFn: () => api<Paginated<Staff>>("/api/v1/staff/?page_size=100"),
    retry: false,
  });
  const requests = requestsQuery.data?.results ?? emptyRequests;
  const staffOptions = staffQuery.data?.results ?? [];

  useEffect(() => {
    if (selected && !requests.some((item) => item.id === selected.id)) {
      setSelected(null);
      setForm(null);
    }
  }, [requests, selected]);

  const choose = (item: ShiftChangeRequest) => {
    setSelected(item);
    setForm({ ...item });
    setMessage("");
    setError("");
  };

  const saveDraft = async () => {
    if (!form) return;
    setIsSubmitting(true);
    setError("");
    try {
      const updated = await api<ShiftChangeRequest>(`/api/v1/my-shift-change-requests/${form.id}/`, {
        method: "PATCH",
        body: JSON.stringify(requestPayload(form)),
      });
      setSelected(updated);
      setForm({ ...updated });
      setMessage("下書きを保存しました。");
      await queryClient.invalidateQueries({ queryKey: ["my-shift-change-requests"] });
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "保存に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const action = async (kind: "submit" | "cancel") => {
    if (!selected) return;
    setIsSubmitting(true);
    setError("");
    try {
      const updated = await api<ShiftChangeRequest>(`/api/v1/my-shift-change-requests/${selected.id}/${kind}/`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setSelected(updated);
      setForm({ ...updated });
      setMessage(kind === "submit" ? "申請を提出しました。" : "申請を取消しました。");
      await queryClient.invalidateQueries({ queryKey: ["my-shift-change-requests"] });
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "操作に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="card monthly-page">
      <div className="section-header">
        <div>
          <p className="eyebrow">Shift change requests</p>
          <h2>シフト変更申請</h2>
        </div>
      </div>
      <div className="toolbar field-grid">
        <label>開始<input type="date" value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} /></label>
        <label>終了<input type="date" value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} /></label>
        <label>拠点<input value={filters.location} onChange={(event) => setFilters({ ...filters, location: event.target.value })} /></label>
        <label>status<select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>{statusOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>種別<select value={filters.request_type} onChange={(event) => setFilters({ ...filters, request_type: event.target.value })}><option value="">すべて</option>{requestTypeOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      </div>
      {requestsQuery.isLoading ? <p>読み込み中...</p> : null}
      {requestsQuery.isError ? <p className="error">申請一覧の取得に失敗しました。</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {!requestsQuery.isLoading && !requestsQuery.isError && requests.length === 0 ? <p className="subtle-text">申請はありません。</p> : null}
      <div className="monthly-layout">
        <div className="monthly-grid-wrap">
          <table className="table">
            <thead><tr><th>日付</th><th>種別</th><th>status</th><th>優先度</th><th>勤務</th><th>代行候補</th><th></th></tr></thead>
            <tbody>
              {requests.map((item) => (
                <tr key={item.id}>
                  <td>{item.work_date}</td>
                  <td>{item.request_type}</td>
                  <td>{item.status}</td>
                  <td>{item.priority}</td>
                  <td>{item.original_pattern_short_name_snapshot || item.original_pattern_name_snapshot}</td>
                  <td>{item.requested_staff_display_name}</td>
                  <td><button type="button" onClick={() => choose(item)}>詳細</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selected && form ? (
          <aside className="edit-panel">
            <h3>{selected.work_date}</h3>
            <p className="subtle-text">{selected.location_name} / v{selected.publication_version} / {selected.status}</p>
            <dl>
              <dt>対象スタッフ</dt><dd>{selected.target_staff_display_name}</dd>
              <dt>元勤務</dt><dd>{selected.original_pattern_short_name_snapshot || selected.original_pattern_name_snapshot} {selected.original_start_offset_minutes == null ? "" : `${offsetToLabel(selected.original_start_offset_minutes)}~${offsetToLabel(selected.original_end_offset_minutes ?? selected.original_start_offset_minutes)}`}</dd>
              <dt>管理メモ</dt><dd>{selected.manager_note}</dd>
            </dl>
            <label>種別<select disabled={!selected.can_edit || isSubmitting} value={form.request_type} onChange={(event) => setForm({ ...form, request_type: event.target.value as ShiftChangeRequest["request_type"] })}>{requestTypeOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
            <label>優先度<select disabled={!selected.can_edit || isSubmitting} value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value as ShiftChangeRequest["priority"] })}>{priorityOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label>代行候補<select disabled={!selected.can_edit || isSubmitting} value={form.requested_staff ?? ""} onChange={(event) => setForm({ ...form, requested_staff: event.target.value || null })}><option value="">未指定</option>{staffOptions.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
            <label>希望日<input type="date" readOnly={!selected.can_edit || isSubmitting} value={form.requested_work_date ?? ""} onChange={(event) => setForm({ ...form, requested_work_date: event.target.value || null })} /></label>
            <label>希望開始<input type="number" step={15} readOnly={!selected.can_edit || isSubmitting} value={form.requested_start_offset_minutes ?? ""} onChange={(event) => setForm({ ...form, requested_start_offset_minutes: event.target.value ? Number(event.target.value) : null })} /></label>
            <label>希望終了<input type="number" step={15} readOnly={!selected.can_edit || isSubmitting} value={form.requested_end_offset_minutes ?? ""} onChange={(event) => setForm({ ...form, requested_end_offset_minutes: event.target.value ? Number(event.target.value) : null })} /></label>
            <label>理由<textarea readOnly={!selected.can_edit || isSubmitting} value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} /></label>
            <label>備考<textarea readOnly={!selected.can_edit || isSubmitting} value={form.requested_notes} onChange={(event) => setForm({ ...form, requested_notes: event.target.value })} /></label>
            <div className="actions">
              {selected.can_edit ? <button type="button" disabled={isSubmitting} onClick={() => void saveDraft()}>下書き保存</button> : null}
              {selected.can_submit ? <button type="button" disabled={isSubmitting} onClick={() => void action("submit")}>提出</button> : null}
              {selected.can_cancel ? <button type="button" disabled={isSubmitting} onClick={() => void action("cancel")}>取消</button> : null}
            </div>
          </aside>
        ) : null}
      </div>
    </section>
  );
}
