import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import { offsetToLabel } from "../lib/timeOffsets";
import type { AttendanceRecord, Location, Paginated, Staff } from "../lib/types";

const today = new Date();

function isoDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    open: "未打刻",
    clocked_in: "出勤済み",
    on_break: "休憩中",
    clocked_out: "退勤済み",
    pending_correction: "修正申請中",
    confirmed: "確定済み",
    void: "無効",
  };
  return labels[status] ?? status;
}

function offsetRange(record: AttendanceRecord) {
  if (record.actual_start_offset_minutes == null || record.actual_end_offset_minutes == null) return "-";
  return `${offsetToLabel(record.actual_start_offset_minutes)}~${offsetToLabel(record.actual_end_offset_minutes)}`;
}

const defaultAdjustForm = {
  actual_clock_in_at: "",
  actual_clock_out_at: "",
  break_minutes: "0",
  manager_note: "",
};

export function AttendancePage() {
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
  const [hasWarnings, setHasWarnings] = useState("");
  const [confirmed, setConfirmed] = useState("");
  const [selected, setSelected] = useState<AttendanceRecord | null>(null);
  const [form, setForm] = useState(defaultAdjustForm);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
    if (location) params.set("location", location);
    if (staff) params.set("staff", staff);
    if (status) params.set("status", status);
    if (hasWarnings) params.set("has_warnings", hasWarnings);
    if (confirmed) params.set("confirmed", confirmed);
    return params.toString();
  }, [confirmed, dateFrom, dateTo, hasWarnings, location, staff, status]);

  const locationsQuery = useQuery({
    queryKey: ["attendance-admin-locations"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
    enabled: canView,
  });
  const staffQuery = useQuery({
    queryKey: ["attendance-admin-staff"],
    queryFn: () => api<Paginated<Staff>>("/api/v1/staff/?page_size=100"),
    enabled: canView,
  });
  const attendanceQuery = useQuery({
    queryKey: ["attendance-records", queryString],
    queryFn: () => api<Paginated<AttendanceRecord>>(`/api/v1/attendance-records/?${queryString}`),
    enabled: canView,
  });
  const records = useMemo(() => attendanceQuery.data?.results ?? [], [attendanceQuery.data?.results]);

  useEffect(() => {
    if (selected && !records.some((item) => item.id === selected.id)) {
      setSelected(null);
    }
  }, [records, selected]);

  if (!loading && !canView) return <Navigate to="/403" replace />;

  const chooseRecord = (record: AttendanceRecord) => {
    setSelected(record);
    setForm(defaultAdjustForm);
    setMessage("");
    setError("");
  };

  const manualAdjust = async () => {
    if (!selected) return;
    setIsSubmitting(true);
    setMessage("");
    setError("");
    try {
      await api(`/api/v1/attendance-records/${selected.id}/manual-adjust/`, {
        method: "POST",
        body: JSON.stringify({
          actual_clock_in_at: form.actual_clock_in_at,
          actual_clock_out_at: form.actual_clock_out_at,
          break_minutes: Number(form.break_minutes || 0),
          manager_note: form.manager_note,
        }),
      });
      setMessage("勤怠を修正しました。");
      await queryClient.invalidateQueries({ queryKey: ["attendance-records"] });
      await queryClient.invalidateQueries({ queryKey: ["my-attendance"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "勤怠修正に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const recordAction = async (action: "confirm" | "unconfirm" | "void") => {
    if (!selected) return;
    setIsSubmitting(true);
    setMessage("");
    setError("");
    try {
      await api(`/api/v1/attendance-records/${selected.id}/${action}/`, {
        method: "POST",
        body: JSON.stringify({ manager_note: form.manager_note }),
      });
      setMessage(action === "confirm" ? "勤怠を確定しました。" : action === "unconfirm" ? "確定を解除しました。" : "勤怠を無効にしました。");
      await queryClient.invalidateQueries({ queryKey: ["attendance-records"] });
      await queryClient.invalidateQueries({ queryKey: ["my-attendance"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "勤怠操作に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="card monthly-page">
      <div className="section-header">
        <div>
          <p className="eyebrow">Attendance</p>
          <h2>勤怠管理</h2>
        </div>
      </div>
      <div className="toolbar field-grid">
        <label>開始<input type="date" value={dateFrom} onChange={(event) => { setDateFrom(event.target.value); setSelected(null); }} /></label>
        <label>終了<input type="date" value={dateTo} onChange={(event) => { setDateTo(event.target.value); setSelected(null); }} /></label>
        <label>拠点<select value={location} onChange={(event) => { setLocation(event.target.value); setSelected(null); }}><option value="">すべて</option>{locationsQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>スタッフ<select value={staff} onChange={(event) => { setStaff(event.target.value); setSelected(null); }}><option value="">すべて</option>{staffQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
        <label>状態<select value={status} onChange={(event) => { setStatus(event.target.value); setSelected(null); }}><option value="">すべて</option><option value="open">未打刻</option><option value="clocked_in">出勤済み</option><option value="on_break">休憩中</option><option value="clocked_out">退勤済み</option><option value="pending_correction">修正申請中</option><option value="confirmed">確定済み</option></select></label>
        <label>warning<select value={hasWarnings} onChange={(event) => { setHasWarnings(event.target.value); setSelected(null); }}><option value="">すべて</option><option value="true">あり</option><option value="false">なし</option></select></label>
        <label>確定<select value={confirmed} onChange={(event) => { setConfirmed(event.target.value); setSelected(null); }}><option value="">すべて</option><option value="true">確定済み</option><option value="false">未確定</option></select></label>
      </div>
      {attendanceQuery.isLoading ? <p>読み込み中...</p> : null}
      {attendanceQuery.isError ? <p className="error">勤怠一覧の取得に失敗しました。</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {!attendanceQuery.isLoading && !attendanceQuery.isError && records.length === 0 ? <p className="subtle-text">勤怠はありません。</p> : null}
      {records.length ? (
        <div className="monthly-layout">
          <div className="monthly-grid-wrap">
            <table className="table">
              <thead><tr><th>日付</th><th>拠点</th><th>スタッフ</th><th>状態</th><th>予定</th><th>実績</th><th>休憩</th><th>勤務</th><th>warning</th></tr></thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.id}>
                    <td><button type="button" className="btn-link" onClick={() => chooseRecord(record)}>{record.work_date}</button></td>
                    <td>{record.location_name}</td>
                    <td>{record.staff_display_name}</td>
                    <td>
                      {statusLabel(record.status)}
                      {record.is_month_closed ? <span className="status-badge">締め済み</span> : null}
                    </td>
                    <td>{record.scheduled_start_offset_minutes == null || record.scheduled_end_offset_minutes == null ? "-" : `${offsetToLabel(record.scheduled_start_offset_minutes)}~${offsetToLabel(record.scheduled_end_offset_minutes)}`}</td>
                    <td>{offsetRange(record)}</td>
                    <td>{record.break_minutes}分</td>
                    <td>{record.worked_minutes}分</td>
                    <td>{record.warning_count ? record.warnings.map((item) => item.code).join(" / ") : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {selected ? (
            <aside className="edit-panel">
              <h3>{selected.staff_display_name}</h3>
              <p className="subtle-text">
                {selected.work_date} / {selected.location_name} / {statusLabel(selected.status)}
                {selected.is_month_closed ? ` / ${selected.closing_period_name || "締め済み"}` : ""}
              </p>
              <dl>
                <dt>予定</dt><dd>{selected.scheduled_start_offset_minutes == null || selected.scheduled_end_offset_minutes == null ? "-" : `${offsetToLabel(selected.scheduled_start_offset_minutes)}~${offsetToLabel(selected.scheduled_end_offset_minutes)}`}</dd>
                <dt>実績</dt><dd>{offsetRange(selected)}</dd>
                <dt>差異</dt><dd>開始 {selected.difference_start_minutes ?? "-"} / 終了 {selected.difference_end_minutes ?? "-"} / 勤務 {selected.difference_worked_minutes ?? "-"}</dd>
                <dt>warning</dt><dd>{selected.warning_count ? selected.warnings.map((item) => item.message).join(" / ") : "-"}</dd>
                <dt>備考</dt><dd>{selected.manager_note || "-"}</dd>
              </dl>
              {canManage ? (
                <section className="inline-alert">
                  <h3>管理操作</h3>
                  <label>出勤<input type="datetime-local" disabled={isSubmitting || selected.status === "confirmed" || selected.is_month_closed} value={form.actual_clock_in_at} onChange={(event) => setForm({ ...form, actual_clock_in_at: event.target.value })} /></label>
                  <label>退勤<input type="datetime-local" disabled={isSubmitting || selected.status === "confirmed" || selected.is_month_closed} value={form.actual_clock_out_at} onChange={(event) => setForm({ ...form, actual_clock_out_at: event.target.value })} /></label>
                  <label>休憩分<input type="number" min={0} disabled={isSubmitting || selected.status === "confirmed" || selected.is_month_closed} value={form.break_minutes} onChange={(event) => setForm({ ...form, break_minutes: event.target.value })} /></label>
                  <label>管理メモ<textarea disabled={isSubmitting} value={form.manager_note} onChange={(event) => setForm({ ...form, manager_note: event.target.value })} /></label>
                  <div className="actions">
                    <button type="button" disabled={isSubmitting || selected.status === "confirmed" || selected.is_month_closed} onClick={() => void manualAdjust()}>manual adjust</button>
                    <button type="button" disabled={isSubmitting || selected.status === "confirmed" || selected.is_month_closed} onClick={() => void recordAction("confirm")}>confirm</button>
                    <button type="button" disabled={isSubmitting || selected.status !== "confirmed" || selected.is_month_closed} onClick={() => void recordAction("unconfirm")}>unconfirm</button>
                    <button type="button" disabled={isSubmitting || selected.status === "void" || selected.is_month_closed} onClick={() => void recordAction("void")}>void</button>
                  </div>
                </section>
              ) : <p className="subtle-text">閲覧のみです。</p>}
              <h3>打刻履歴</h3>
              <table className="table">
                <thead><tr><th>種別</th><th>時刻</th><th>offset</th><th>記録元</th></tr></thead>
                <tbody>{selected.events.map((event) => <tr key={event.id}><td>{event.event_type}</td><td>{event.occurred_at}</td><td>{offsetToLabel(event.offset_minutes)}</td><td>{event.source}</td></tr>)}</tbody>
              </table>
            </aside>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
