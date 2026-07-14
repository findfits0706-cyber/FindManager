import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type { AttendanceCorrectionRequest, Location, Paginated, Staff } from "../lib/types";

const today = new Date();

function isoDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    draft: "下書き",
    submitted: "提出済み",
    approved: "承認済み",
    rejected: "却下",
    cancelled: "取消",
    applied: "反映済み",
  };
  return labels[status] ?? status;
}

export function AttendanceCorrectionRequestsPage() {
  const { user, loading } = useAuth();
  const queryClient = useQueryClient();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const canView = canManage || roles.includes("supervisor");
  const [dateFrom, setDateFrom] = useState(isoDate(new Date(today.getFullYear(), today.getMonth(), 1)));
  const [dateTo, setDateTo] = useState(isoDate(new Date(today.getFullYear(), today.getMonth() + 1, 0)));
  const [location, setLocation] = useState("");
  const [staff, setStaff] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<AttendanceCorrectionRequest | null>(null);
  const [managerNote, setManagerNote] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
    if (location) params.set("location", location);
    if (staff) params.set("staff", staff);
    if (status) params.set("status", status);
    return params.toString();
  }, [dateFrom, dateTo, location, staff, status]);

  const locationsQuery = useQuery({
    queryKey: ["attendance-corrections-locations"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
    enabled: canView,
  });
  const staffQuery = useQuery({
    queryKey: ["attendance-corrections-staff"],
    queryFn: () => api<Paginated<Staff>>("/api/v1/staff/?page_size=100"),
    enabled: canView,
  });
  const correctionsQuery = useQuery({
    queryKey: ["attendance-correction-requests", queryString],
    queryFn: () => api<Paginated<AttendanceCorrectionRequest>>(`/api/v1/attendance-correction-requests/?${queryString}`),
    enabled: canView,
  });
  const corrections = correctionsQuery.data?.results ?? [];

  if (!loading && !canView) return <Navigate to="/403" replace />;

  const chooseCorrection = (correction: AttendanceCorrectionRequest) => {
    setSelected(correction);
    setManagerNote(correction.manager_note);
    setMessage("");
    setError("");
  };

  const action = async (actionName: "approve" | "reject" | "apply") => {
    if (!selected) return;
    if (actionName === "reject" && !managerNote.trim()) {
      setError("却下理由を入力してください。");
      return;
    }
    setIsSubmitting(true);
    setMessage("");
    setError("");
    try {
      await api(`/api/v1/attendance-correction-requests/${selected.id}/${actionName}/`, {
        method: "POST",
        body: JSON.stringify({ manager_note: managerNote }),
      });
      setMessage(actionName === "approve" ? "承認しました。" : actionName === "reject" ? "却下しました。" : "勤怠へ反映しました。");
      await queryClient.invalidateQueries({ queryKey: ["attendance-correction-requests"] });
      await queryClient.invalidateQueries({ queryKey: ["attendance-records"] });
      await queryClient.invalidateQueries({ queryKey: ["my-attendance"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "勤怠修正申請の操作に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="card monthly-page">
      <div className="section-header">
        <div>
          <p className="eyebrow">Attendance corrections</p>
          <h2>勤怠修正申請</h2>
        </div>
      </div>
      <div className="toolbar field-grid">
        <label>開始<input type="date" value={dateFrom} onChange={(event) => { setDateFrom(event.target.value); setSelected(null); }} /></label>
        <label>終了<input type="date" value={dateTo} onChange={(event) => { setDateTo(event.target.value); setSelected(null); }} /></label>
        <label>拠点<select value={location} onChange={(event) => { setLocation(event.target.value); setSelected(null); }}><option value="">すべて</option>{locationsQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>スタッフ<select value={staff} onChange={(event) => { setStaff(event.target.value); setSelected(null); }}><option value="">すべて</option>{staffQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
        <label>状態<select value={status} onChange={(event) => { setStatus(event.target.value); setSelected(null); }}><option value="">すべて</option><option value="draft">下書き</option><option value="submitted">提出済み</option><option value="approved">承認済み</option><option value="rejected">却下</option><option value="cancelled">取消</option><option value="applied">反映済み</option></select></label>
      </div>
      {correctionsQuery.isLoading ? <p>読み込み中...</p> : null}
      {correctionsQuery.isError ? <p className="error">勤怠修正申請の取得に失敗しました。</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {!correctionsQuery.isLoading && !correctionsQuery.isError && corrections.length === 0 ? <p className="subtle-text">勤怠修正申請はありません。</p> : null}
      {corrections.length ? (
        <div className="monthly-layout">
          <div className="monthly-grid-wrap">
            <table className="table">
              <thead><tr><th>日付</th><th>拠点</th><th>スタッフ</th><th>状態</th><th>希望出勤</th><th>希望退勤</th><th>休憩</th><th>理由</th></tr></thead>
              <tbody>
                {corrections.map((correction) => (
                  <tr key={correction.id}>
                    <td><button type="button" className="btn-link" onClick={() => chooseCorrection(correction)}>{correction.work_date}</button></td>
                    <td>{correction.location_name}</td>
                    <td>{correction.staff_display_name}</td>
                    <td>{statusLabel(correction.status)}</td>
                    <td>{correction.requested_clock_in_at ?? "-"}</td>
                    <td>{correction.requested_clock_out_at ?? "-"}</td>
                    <td>{correction.requested_break_minutes ?? "-"}</td>
                    <td>{correction.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {selected ? (
            <aside className="edit-panel">
              <h3>{selected.staff_display_name}</h3>
              <p className="subtle-text">{selected.work_date} / {selected.location_name} / {statusLabel(selected.status)}</p>
              <dl>
                <dt>希望出勤</dt><dd>{selected.requested_clock_in_at ?? "-"}</dd>
                <dt>希望退勤</dt><dd>{selected.requested_clock_out_at ?? "-"}</dd>
                <dt>希望休憩</dt><dd>{selected.requested_break_minutes ?? "-"}分</dd>
                <dt>本人備考</dt><dd>{selected.requested_staff_note || "-"}</dd>
                <dt>理由</dt><dd>{selected.reason || "-"}</dd>
                <dt>管理メモ</dt><dd>{selected.manager_note || "-"}</dd>
              </dl>
              {canManage ? (
                <section className="inline-alert">
                  <h3>管理操作</h3>
                  <label>管理メモ<textarea disabled={isSubmitting} value={managerNote} onChange={(event) => setManagerNote(event.target.value)} /></label>
                  <div className="actions">
                    <button type="button" disabled={isSubmitting || !selected.can_approve} onClick={() => void action("approve")}>approve</button>
                    <button type="button" disabled={isSubmitting || !(selected.status === "submitted" || selected.status === "approved")} onClick={() => void action("reject")}>reject</button>
                    <button type="button" disabled={isSubmitting || !selected.can_apply} onClick={() => void action("apply")}>apply</button>
                  </div>
                </section>
              ) : <p className="subtle-text">閲覧のみです。</p>}
            </aside>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
