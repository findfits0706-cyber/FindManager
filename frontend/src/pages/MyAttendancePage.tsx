import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { offsetToLabel } from "../lib/timeOffsets";
import type { AttendanceCorrectionRequest, AttendanceRecord, Location, Paginated } from "../lib/types";

const today = new Date();

function isoDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function monthRange(year: number, month: number) {
  return {
    from: isoDate(new Date(year, month - 1, 1)),
    to: isoDate(new Date(year, month, 0)),
  };
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

const defaultCorrectionForm = {
  requested_clock_in_at: "",
  requested_clock_out_at: "",
  requested_break_minutes: "",
  requested_staff_note: "",
  reason: "",
};

export function MyAttendancePage() {
  const queryClient = useQueryClient();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [location, setLocation] = useState("");
  const [selected, setSelected] = useState<AttendanceRecord | null>(null);
  const [form, setForm] = useState(defaultCorrectionForm);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const range = monthRange(year, month);

  const locationsQuery = useQuery({
    queryKey: ["attendance-locations"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
  });
  const attendanceQuery = useQuery({
    queryKey: ["my-attendance", year, month, location],
    queryFn: () =>
      api<Paginated<AttendanceRecord>>(
        `/api/v1/my-attendance/?date_from=${encodeURIComponent(range.from)}&date_to=${encodeURIComponent(range.to)}${
          location ? `&location=${encodeURIComponent(location)}` : ""
        }`,
      ),
  });
  const records = useMemo(() => attendanceQuery.data?.results ?? [], [attendanceQuery.data?.results]);

  useEffect(() => {
    if (selected && !records.some((item) => item.id === selected.id)) {
      setSelected(null);
    }
  }, [records, selected]);

  const selectRecord = (record: AttendanceRecord) => {
    setSelected(record);
    setForm(defaultCorrectionForm);
    setMessage("");
    setError("");
  };

  const saveCorrection = async (submit: boolean) => {
    if (!selected) return;
    setIsSubmitting(true);
    setMessage("");
    setError("");
    try {
      await api<AttendanceCorrectionRequest>("/api/v1/my-attendance-corrections/", {
        method: "POST",
        body: JSON.stringify({
          attendance_record: selected.id,
          requested_clock_in_at: form.requested_clock_in_at || null,
          requested_clock_out_at: form.requested_clock_out_at || null,
          requested_break_minutes: form.requested_break_minutes ? Number(form.requested_break_minutes) : null,
          requested_staff_note: form.requested_staff_note,
          reason: form.reason,
          submit,
        }),
      });
      setMessage(submit ? "勤怠修正申請を提出しました。" : "勤怠修正申請を下書き保存しました。");
      setForm(defaultCorrectionForm);
      await queryClient.invalidateQueries({ queryKey: ["my-attendance"] });
      await queryClient.invalidateQueries({ queryKey: ["my-attendance-corrections"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "勤怠修正申請に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const correctionAction = async (correction: AttendanceCorrectionRequest, action: "submit" | "cancel") => {
    setIsSubmitting(true);
    setMessage("");
    setError("");
    try {
      await api(`/api/v1/my-attendance-corrections/${correction.id}/${action}/`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setMessage(action === "submit" ? "勤怠修正申請を提出しました。" : "勤怠修正申請を取消しました。");
      await queryClient.invalidateQueries({ queryKey: ["my-attendance"] });
      await queryClient.invalidateQueries({ queryKey: ["my-attendance-corrections"] });
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
          <p className="eyebrow">My attendance</p>
          <h2>自分の勤怠</h2>
        </div>
      </div>
      <div className="toolbar field-grid">
        <label>年<input type="number" value={year} onChange={(event) => { setYear(Number(event.target.value)); setSelected(null); }} /></label>
        <label>月<input type="number" min={1} max={12} value={month} onChange={(event) => { setMonth(Number(event.target.value)); setSelected(null); }} /></label>
        <label>拠点<select value={location} onChange={(event) => { setLocation(event.target.value); setSelected(null); }}><option value="">すべて</option>{locationsQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      </div>
      {attendanceQuery.isLoading ? <p>読み込み中...</p> : null}
      {attendanceQuery.isError ? <p className="error">勤怠の取得に失敗しました。</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {!attendanceQuery.isLoading && !attendanceQuery.isError && records.length === 0 ? <p className="subtle-text">勤怠はありません。</p> : null}
      {records.length ? (
        <div className="monthly-layout">
          <div className="monthly-grid-wrap">
            <table className="table">
              <thead><tr><th>日付</th><th>拠点</th><th>状態</th><th>予定</th><th>実績</th><th>休憩</th><th>勤務</th><th>warning</th></tr></thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.id}>
                    <td><button type="button" className="btn-link" onClick={() => selectRecord(record)}>{record.work_date}</button></td>
                    <td>{record.location_name}</td>
                    <td>{statusLabel(record.status)}</td>
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
              <h3>{selected.work_date}</h3>
              <p className="subtle-text">{selected.location_name} / {statusLabel(selected.status)}</p>
              <dl>
                <dt>予定</dt><dd>{selected.scheduled_start_offset_minutes == null || selected.scheduled_end_offset_minutes == null ? "-" : `${offsetToLabel(selected.scheduled_start_offset_minutes)}~${offsetToLabel(selected.scheduled_end_offset_minutes)}`}</dd>
                <dt>実績</dt><dd>{offsetRange(selected)}</dd>
                <dt>差異</dt><dd>開始 {selected.difference_start_minutes ?? "-"} / 終了 {selected.difference_end_minutes ?? "-"} / 勤務 {selected.difference_worked_minutes ?? "-"}</dd>
                <dt>warning</dt><dd>{selected.warning_count ? selected.warnings.map((item) => item.message).join(" / ") : "-"}</dd>
              </dl>
              <section className="inline-alert">
                <h3>修正申請</h3>
                <label>希望出勤<input type="datetime-local" readOnly={isSubmitting || selected.status === "confirmed"} value={form.requested_clock_in_at} onChange={(event) => setForm({ ...form, requested_clock_in_at: event.target.value })} /></label>
                <label>希望退勤<input type="datetime-local" readOnly={isSubmitting || selected.status === "confirmed"} value={form.requested_clock_out_at} onChange={(event) => setForm({ ...form, requested_clock_out_at: event.target.value })} /></label>
                <label>希望休憩分<input type="number" min={0} readOnly={isSubmitting || selected.status === "confirmed"} value={form.requested_break_minutes} onChange={(event) => setForm({ ...form, requested_break_minutes: event.target.value })} /></label>
                <label>理由<textarea readOnly={isSubmitting || selected.status === "confirmed"} value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} /></label>
                <label>備考<textarea readOnly={isSubmitting || selected.status === "confirmed"} value={form.requested_staff_note} onChange={(event) => setForm({ ...form, requested_staff_note: event.target.value })} /></label>
                <div className="actions">
                  <button type="button" disabled={isSubmitting || selected.status === "confirmed"} onClick={() => void saveCorrection(false)}>下書き保存</button>
                  <button type="button" disabled={isSubmitting || selected.status === "confirmed"} onClick={() => void saveCorrection(true)}>提出</button>
                </div>
              </section>
              {selected.correction_requests.length ? (
                <section className="inline-alert">
                  <h3>申請履歴</h3>
                  <ul>
                    {selected.correction_requests.map((item) => (
                      <li key={item.id}>
                        {item.status} / {item.reason || item.manager_note}
                        {item.can_submit ? <button type="button" disabled={isSubmitting} onClick={() => void correctionAction(item, "submit")}>提出</button> : null}
                        {item.can_cancel ? <button type="button" disabled={isSubmitting} onClick={() => void correctionAction(item, "cancel")}>取消</button> : null}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
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
