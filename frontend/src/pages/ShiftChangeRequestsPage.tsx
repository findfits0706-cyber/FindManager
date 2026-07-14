import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import { formatLocalIsoDate } from "../lib/localDate";
import { offsetToLabel } from "../lib/timeOffsets";
import type { Paginated, ShiftChangeRequest, Staff } from "../lib/types";

const today = new Date();
const emptyRequests: ShiftChangeRequest[] = [];
const requestTypes: Array<{ value: ShiftChangeRequest["request_type"] | ""; label: string }> = [
  { value: "", label: "すべて" },
  { value: "drop_shift", label: "勤務辞退" },
  { value: "swap_shift", label: "勤務交換" },
  { value: "cover_request", label: "代行依頼" },
  { value: "change_time", label: "時間変更" },
  { value: "change_assignment", label: "業務変更" },
  { value: "manager_adjustment", label: "管理者調整" },
  { value: "note", label: "相談メモ" },
];
const statuses: Array<{ value: ShiftChangeRequest["status"] | ""; label: string }> = [
  { value: "", label: "すべて" },
  { value: "draft", label: "draft" },
  { value: "submitted", label: "submitted" },
  { value: "approved", label: "approved" },
  { value: "rejected", label: "rejected" },
  { value: "cancelled", label: "cancelled" },
  { value: "applied", label: "applied" },
  { value: "closed", label: "closed" },
];
const priorities: Array<ShiftChangeRequest["priority"] | ""> = ["", "high", "normal", "low"];

function defaultFilters() {
  return {
    date_from: formatLocalIsoDate(new Date(today.getFullYear(), today.getMonth(), 1)),
    date_to: formatLocalIsoDate(new Date(today.getFullYear(), today.getMonth() + 1, 0)),
    location: "",
    status: "",
    request_type: "",
    priority: "",
    requester: "",
    target_staff: "",
    requested_staff: "",
  };
}

function actionPayload(item: ShiftChangeRequest, managerNote: string) {
  return {
    requested_staff: item.requested_staff || null,
    requested_work_date: item.requested_work_date || null,
    requested_shift_pattern: item.requested_shift_pattern || null,
    requested_start_offset_minutes: item.requested_start_offset_minutes,
    requested_end_offset_minutes: item.requested_end_offset_minutes,
    manager_note: managerNote,
  };
}

export function ShiftChangeRequestsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const [filters, setFilters] = useState(defaultFilters);
  const [selected, setSelected] = useState<ShiftChangeRequest | null>(null);
  const [form, setForm] = useState<ShiftChangeRequest | null>(null);
  const [managerNote, setManagerNote] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const queryString = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString();

  const requestsQuery = useQuery({
    queryKey: ["shift-change-requests", filters],
    queryFn: () => api<Paginated<ShiftChangeRequest>>(`/api/v1/shift-change-requests/?${queryString}`),
  });
  const staffQuery = useQuery({
    queryKey: ["shift-change-admin-staff"],
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
    setManagerNote(item.manager_note ?? "");
    setMessage("");
    setError("");
  };

  const runAction = async (kind: "approve" | "reject" | "cancel" | "apply" | "close") => {
    if (!selected || !form) return;
    if (kind === "reject" && !managerNote.trim()) {
      setError("却下理由を入力してください。");
      return;
    }
    setIsSubmitting(true);
    setError("");
    try {
      const body =
        kind === "approve" ? actionPayload(form, managerNote) : { manager_note: managerNote };
      const updated = await api<ShiftChangeRequest>(`/api/v1/shift-change-requests/${selected.id}/${kind}/`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setSelected(updated);
      setForm({ ...updated });
      setManagerNote(updated.manager_note);
      setMessage(`${kind} を実行しました。`);
      await queryClient.invalidateQueries({ queryKey: ["shift-change-requests"] });
      await queryClient.invalidateQueries({ queryKey: ["monthly-matrix"] });
      await queryClient.invalidateQueries({ queryKey: ["monthly-plans"] });
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
          <p className="eyebrow">Shift change request management</p>
          <h2>シフト変更申請管理</h2>
        </div>
      </div>
      <div className="toolbar field-grid">
        <label>開始<input type="date" value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} /></label>
        <label>終了<input type="date" value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} /></label>
        <label>拠点<input value={filters.location} onChange={(event) => setFilters({ ...filters, location: event.target.value })} /></label>
        <label>status<select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>{statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>種別<select value={filters.request_type} onChange={(event) => setFilters({ ...filters, request_type: event.target.value })}>{requestTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>優先度<select value={filters.priority} onChange={(event) => setFilters({ ...filters, priority: event.target.value })}>{priorities.map((item) => <option key={item || "all"} value={item}>{item || "すべて"}</option>)}</select></label>
      </div>
      {requestsQuery.isLoading ? <p>読み込み中...</p> : null}
      {requestsQuery.isError ? <p className="error">申請一覧の取得に失敗しました。</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {!requestsQuery.isLoading && !requestsQuery.isError && requests.length === 0 ? <p className="subtle-text">申請はありません。</p> : null}
      <div className="monthly-layout">
        <div className="monthly-grid-wrap">
          <table className="table">
            <thead><tr><th>日付</th><th>拠点</th><th>申請者</th><th>対象</th><th>種別</th><th>status</th><th>優先度</th><th>候補</th><th></th></tr></thead>
            <tbody>
              {requests.map((item) => (
                <tr key={item.id}>
                  <td>{item.work_date}</td>
                  <td>{item.location_name}</td>
                  <td>{item.requester_display_name}</td>
                  <td>{item.target_staff_display_name}</td>
                  <td>{item.request_type}</td>
                  <td>{item.status}</td>
                  <td>{item.priority}</td>
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
              <dt>申請者</dt><dd>{selected.requester_display_name}</dd>
              <dt>対象スタッフ</dt><dd>{selected.target_staff_display_name}</dd>
              <dt>元勤務</dt><dd>{selected.original_pattern_short_name_snapshot || selected.original_pattern_name_snapshot} {selected.original_start_offset_minutes == null ? "" : `${offsetToLabel(selected.original_start_offset_minutes)}~${offsetToLabel(selected.original_end_offset_minutes ?? selected.original_start_offset_minutes)}`}</dd>
              <dt>理由</dt><dd>{selected.reason}</dd>
            </dl>
            <label>代行/交換スタッフ<select disabled={!canManage || isSubmitting} value={form.requested_staff ?? ""} onChange={(event) => setForm({ ...form, requested_staff: event.target.value || null })}><option value="">未指定</option>{staffOptions.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
            <label>希望日<input type="date" readOnly={!canManage || isSubmitting} value={form.requested_work_date ?? ""} onChange={(event) => setForm({ ...form, requested_work_date: event.target.value || null })} /></label>
            <label>希望開始<input type="number" step={15} readOnly={!canManage || isSubmitting} value={form.requested_start_offset_minutes ?? ""} onChange={(event) => setForm({ ...form, requested_start_offset_minutes: event.target.value ? Number(event.target.value) : null })} /></label>
            <label>希望終了<input type="number" step={15} readOnly={!canManage || isSubmitting} value={form.requested_end_offset_minutes ?? ""} onChange={(event) => setForm({ ...form, requested_end_offset_minutes: event.target.value ? Number(event.target.value) : null })} /></label>
            <label>管理メモ<textarea readOnly={!canManage || isSubmitting} value={managerNote} onChange={(event) => setManagerNote(event.target.value)} /></label>
            {selected.status === "applied" ? <p className="inline-alert">変更反映済み。再公開が必要です。</p> : null}
            {canManage ? (
              <div className="actions">
                {selected.can_approve ? <button type="button" disabled={isSubmitting} onClick={() => void runAction("approve")}>承認</button> : null}
                <button type="button" disabled={isSubmitting || !["submitted", "approved"].includes(selected.status)} onClick={() => void runAction("reject")}>却下</button>
                {selected.can_cancel ? <button type="button" disabled={isSubmitting} onClick={() => void runAction("cancel")}>取消</button> : null}
                {selected.can_apply ? <button type="button" disabled={isSubmitting} onClick={() => void runAction("apply")}>反映</button> : null}
                {selected.request_type === "note" && !["closed", "cancelled", "rejected"].includes(selected.status) ? <button type="button" disabled={isSubmitting} onClick={() => void runAction("close")}>完了</button> : null}
              </div>
            ) : <p className="subtle-text">閲覧のみです。</p>}
          </aside>
        ) : null}
      </div>
    </section>
  );
}
