import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { offsetToLabel } from "../lib/timeOffsets";
import type { MyPublishedShift, MyPublishedShiftsResponse, ShiftChangeRequest, Staff, Paginated } from "../lib/types";

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

const today = new Date();
const emptyShifts: MyPublishedShift[] = [];
const defaultRequestForm = {
  request_type: "drop_shift" as ShiftChangeRequest["request_type"],
  priority: "normal" as ShiftChangeRequest["priority"],
  requested_staff: "",
  requested_work_date: "",
  requested_start_offset_minutes: "",
  requested_end_offset_minutes: "",
  requested_notes: "",
  reason: "",
};

function attendanceStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    open: "未打刻",
    clocked_in: "出勤済み",
    on_break: "休憩中",
    clocked_out: "退勤済み",
    pending_correction: "修正申請中",
    confirmed: "確定済み",
    void: "無効",
  };
  return status ? labels[status] ?? status : "未打刻";
}

function attendanceRange(shift: MyPublishedShift) {
  const attendance = shift.attendance;
  if (!attendance || attendance.actual_start_offset_minutes == null || attendance.actual_end_offset_minutes == null) {
    return "-";
  }
  return `${offsetToLabel(attendance.actual_start_offset_minutes)}~${offsetToLabel(attendance.actual_end_offset_minutes)}`;
}

export function MyPublishedShiftsPage() {
  const queryClient = useQueryClient();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [location, setLocation] = useState("");
  const [selectedShift, setSelectedShift] = useState<MyPublishedShift | null>(null);
  const [knownLocations, setKnownLocations] = useState<Array<{ id: string; name: string }>>([]);
  const [requestForm, setRequestForm] = useState(defaultRequestForm);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const range = monthRange(year, month);
  const query = useQuery({
    queryKey: ["my-published-shifts", year, month, location],
    queryFn: () =>
      api<MyPublishedShiftsResponse>(
        `/api/v1/my-published-shifts/?date_from=${encodeURIComponent(range.from)}&date_to=${encodeURIComponent(range.to)}${
          location ? `&location=${encodeURIComponent(location)}` : ""
        }`,
      ),
  });
  const shifts = query.data?.shifts ?? emptyShifts;
  const staffQuery = useQuery({
    queryKey: ["my-published-change-staff"],
    queryFn: () => api<Paginated<Staff>>("/api/v1/staff/?page_size=100"),
    retry: false,
  });
  const staffOptions = staffQuery.data?.results ?? [];
  useEffect(() => {
    if (!query.data) return;
    setKnownLocations((current) => {
      const result = new Map(current.map((item) => [item.id, item.name]));
      for (const shift of query.data.shifts) {
        result.set(shift.publication.location, shift.publication.location_name);
      }
      return Array.from(result.entries()).map(([id, name]) => ({ id, name }));
    });
  }, [query.data]);
  useEffect(() => {
    if (query.isError) {
      setSelectedShift(null);
      return;
    }
    if (selectedShift && !shifts.some((shift) => shift.id === selectedShift.id)) {
      setSelectedShift(null);
    }
  }, [query.data, query.isError, selectedShift, shifts]);
  const locationOptions = useMemo(() => {
    const result = new Map(knownLocations.map((item) => [item.id, item.name]));
    for (const shift of shifts) {
      result.set(shift.publication.location, shift.publication.location_name);
    }
    return Array.from(result.entries()).map(([id, name]) => ({ id, name }));
  }, [knownLocations, shifts]);

  const changeMonth = (delta: number) => {
    const next = new Date(year, month - 1 + delta, 1);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
    setSelectedShift(null);
  };

  const goThisMonth = () => {
    setYear(today.getFullYear());
    setMonth(today.getMonth() + 1);
    setSelectedShift(null);
  };

  const chooseShift = (shift: MyPublishedShift) => {
    setSelectedShift(shift);
    setRequestForm(defaultRequestForm);
    setMessage("");
    setError("");
  };

  const submitChangeRequest = async (submit: boolean) => {
    if (!selectedShift) return;
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      await api<ShiftChangeRequest>("/api/v1/my-shift-change-requests/", {
        method: "POST",
        body: JSON.stringify({
          publication_assignment: selectedShift.id,
          request_type: requestForm.request_type,
          priority: requestForm.priority,
          requested_staff: requestForm.requested_staff || null,
          requested_work_date: requestForm.requested_work_date || null,
          requested_start_offset_minutes: requestForm.requested_start_offset_minutes
            ? Number(requestForm.requested_start_offset_minutes)
            : null,
          requested_end_offset_minutes: requestForm.requested_end_offset_minutes
            ? Number(requestForm.requested_end_offset_minutes)
            : null,
          requested_notes: requestForm.requested_notes,
          reason: requestForm.reason,
          submit,
        }),
      });
      setMessage(submit ? "変更申請を提出しました。" : "変更申請を下書き保存しました。");
      setRequestForm(defaultRequestForm);
      await queryClient.invalidateQueries({ queryKey: ["my-published-shifts"] });
      await queryClient.invalidateQueries({ queryKey: ["my-shift-change-requests"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "変更申請に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const runAttendanceAction = async (
    shift: MyPublishedShift,
    action: "clock-in" | "break-start" | "break-end" | "clock-out",
  ) => {
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const path =
        action === "clock-in"
          ? "/api/v1/my-attendance/clock-in/"
          : `/api/v1/my-attendance/${shift.attendance?.id}/${action}/`;
      const body =
        action === "clock-in"
          ? { location: shift.publication.location, work_date: shift.work_date }
          : {};
      await api(path, { method: "POST", body: JSON.stringify(body) });
      setMessage("打刻しました。");
      await queryClient.invalidateQueries({ queryKey: ["my-published-shifts"] });
      await queryClient.invalidateQueries({ queryKey: ["my-attendance"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "打刻に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const createAttendanceCorrection = async (shift: MyPublishedShift) => {
    if (!shift.attendance) return;
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      await api("/api/v1/my-attendance-corrections/", {
        method: "POST",
        body: JSON.stringify({
          attendance_record: shift.attendance.id,
          reason: "公開シフト画面から作成",
        }),
      });
      setMessage("勤怠修正申請を下書き作成しました。");
      await queryClient.invalidateQueries({ queryKey: ["my-attendance-corrections"] });
      await queryClient.invalidateQueries({ queryKey: ["my-published-shifts"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "勤怠修正申請に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="card monthly-page">
      <div className="section-header">
        <div>
          <p className="eyebrow">Published shifts</p>
          <h2>自分のシフト</h2>
        </div>
      </div>
      <div className="toolbar field-grid">
        <label>年<input type="number" value={year} onChange={(event) => { setYear(Number(event.target.value)); setSelectedShift(null); }} /></label>
        <label>月<input type="number" min={1} max={12} value={month} onChange={(event) => { setMonth(Number(event.target.value)); setSelectedShift(null); }} /></label>
        <button type="button" onClick={() => changeMonth(-1)}>前月</button>
        <button type="button" onClick={() => changeMonth(1)}>次月</button>
        <button type="button" onClick={goThisMonth}>今月</button>
        <label>拠点<select value={location} onChange={(event) => { setLocation(event.target.value); setSelectedShift(null); }}><option value="">すべて</option>{locationOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      </div>
      {query.isLoading ? <p>読み込み中...</p> : null}
      {query.isError ? <p className="error">公開シフトの取得に失敗しました。</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {!query.isLoading && !query.isError && shifts.length === 0 ? <p className="subtle-text">公開シフトはありません。</p> : null}
      {shifts.length ? (
        <div className="monthly-layout">
          <div className="monthly-grid-wrap">
            <table className="table">
              <thead>
                <tr><th>日付</th><th>曜日</th><th>拠点</th><th>勤務パターン</th><th>開始～終了</th><th>勤怠</th><th>打刻</th><th>変更申請</th><th>勤務時間</th><th>休憩時間</th><th>公開Version</th><th>公開日時</th></tr>
              </thead>
              <tbody>
                {shifts.map((shift) => {
                  const dateInfo = query.data?.dates.find((item) => item.date === shift.work_date);
                  return (
                    <tr key={shift.id} className={dateInfo?.is_saturday ? "saturday" : dateInfo?.is_sunday ? "sunday" : ""}>
                      <td><button type="button" className="btn-link" onClick={() => chooseShift(shift)}>{shift.work_date}</button></td>
                      <td>{dateInfo?.weekday_label ?? ""}</td>
                      <td>{shift.publication.location_name}</td>
                      <td>{shift.pattern_short_name_snapshot || shift.pattern_name_snapshot}</td>
                      <td>{shift.start_offset_minutes == null || shift.end_offset_minutes == null ? "-" : `${offsetToLabel(shift.start_offset_minutes)}~${offsetToLabel(shift.end_offset_minutes)}`}</td>
                      <td>{attendanceStatusLabel(shift.attendance?.status)}{shift.attendance?.warning_count ? ` / warning ${shift.attendance.warning_count}` : ""}</td>
                      <td>
                        {!shift.attendance || shift.attendance.status === "open" ? <button type="button" disabled={isSubmitting} onClick={() => void runAttendanceAction(shift, "clock-in")}>出勤</button> : null}
                        {shift.attendance?.status === "clocked_in" ? <button type="button" disabled={isSubmitting} onClick={() => void runAttendanceAction(shift, "break-start")}>休憩開始</button> : null}
                        {shift.attendance?.status === "on_break" ? <button type="button" disabled={isSubmitting} onClick={() => void runAttendanceAction(shift, "break-end")}>休憩終了</button> : null}
                        {shift.attendance?.status === "clocked_in" ? <button type="button" disabled={isSubmitting} onClick={() => void runAttendanceAction(shift, "clock-out")}>退勤</button> : null}
                      </td>
                      <td>{shift.shift_change_requests.length ? shift.shift_change_requests.map((item) => item.status).join(" / ") : <button type="button" onClick={() => chooseShift(shift)}>変更申請</button>}</td>
                      <td>{shift.work_minutes}分</td>
                      <td>{shift.break_minutes}分</td>
                      <td>v{shift.publication.version}</td>
                      <td>{shift.publication.published_at}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {selectedShift ? (
            <aside className="edit-panel">
              <h3>{selectedShift.work_date}</h3>
              <p className="subtle-text">{selectedShift.publication.location_name}</p>
              <dl>
                <dt>勤務パターン</dt><dd>{selectedShift.pattern_short_name_snapshot || selectedShift.pattern_name_snapshot}</dd>
                <dt>開始～終了</dt><dd>{selectedShift.start_offset_minutes == null || selectedShift.end_offset_minutes == null ? "-" : `${offsetToLabel(selectedShift.start_offset_minutes)}~${offsetToLabel(selectedShift.end_offset_minutes)}`}</dd>
                <dt>勤務時間</dt><dd>{selectedShift.work_minutes}分</dd>
                <dt>休憩時間</dt><dd>{selectedShift.break_minutes}分</dd>
                <dt>勤怠状態</dt><dd>{attendanceStatusLabel(selectedShift.attendance?.status)}</dd>
                <dt>実績</dt><dd>{attendanceRange(selectedShift)}</dd>
                <dt>実績休憩</dt><dd>{selectedShift.attendance?.break_minutes ?? 0}分</dd>
                <dt>実績勤務</dt><dd>{selectedShift.attendance?.worked_minutes ?? 0}分</dd>
                <dt>勤怠warning</dt><dd>{selectedShift.attendance?.warnings.length ? selectedShift.attendance.warnings.map((item) => item.code).join(" / ") : "-"}</dd>
                <dt>Assignment備考</dt><dd>{selectedShift.notes}</dd>
                <dt>公開Version</dt><dd>v{selectedShift.publication.version}</dd>
                <dt>公開日時</dt><dd>{selectedShift.publication.published_at}</dd>
              </dl>
              {selectedShift.shift_change_requests.length ? (
                <section className="inline-alert">
                  <h3>既存の変更申請</h3>
                  <ul>
                    {selectedShift.shift_change_requests.map((item) => (
                      <li key={item.id}>{item.request_type} / {item.status} / {item.reason}</li>
                    ))}
                  </ul>
                </section>
              ) : null}
              {selectedShift.attendance ? (
                <div className="actions">
                  <button type="button" disabled={isSubmitting || selectedShift.attendance.status === "confirmed"} onClick={() => void createAttendanceCorrection(selectedShift)}>勤怠修正申請</button>
                </div>
              ) : null}
              <section className="inline-alert">
                <h3>変更申請</h3>
                <label>種別<select disabled={isSubmitting || selectedShift.shift_change_requests.length > 0} value={requestForm.request_type} onChange={(event) => setRequestForm({ ...requestForm, request_type: event.target.value as ShiftChangeRequest["request_type"] })}><option value="drop_shift">勤務辞退</option><option value="swap_shift">勤務交換</option><option value="cover_request">代行依頼</option><option value="change_time">時間変更</option><option value="change_assignment">業務変更</option><option value="note">相談メモ</option></select></label>
                <label>優先度<select disabled={isSubmitting || selectedShift.shift_change_requests.length > 0} value={requestForm.priority} onChange={(event) => setRequestForm({ ...requestForm, priority: event.target.value as ShiftChangeRequest["priority"] })}><option value="high">high</option><option value="normal">normal</option><option value="low">low</option></select></label>
                <label>代行候補<select disabled={isSubmitting || selectedShift.shift_change_requests.length > 0} value={requestForm.requested_staff} onChange={(event) => setRequestForm({ ...requestForm, requested_staff: event.target.value })}><option value="">未指定</option>{staffOptions.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
                <label>希望日<input type="date" readOnly={isSubmitting || selectedShift.shift_change_requests.length > 0} value={requestForm.requested_work_date} onChange={(event) => setRequestForm({ ...requestForm, requested_work_date: event.target.value })} /></label>
                <label>希望開始<input type="number" step={15} readOnly={isSubmitting || selectedShift.shift_change_requests.length > 0} value={requestForm.requested_start_offset_minutes} onChange={(event) => setRequestForm({ ...requestForm, requested_start_offset_minutes: event.target.value })} /></label>
                <label>希望終了<input type="number" step={15} readOnly={isSubmitting || selectedShift.shift_change_requests.length > 0} value={requestForm.requested_end_offset_minutes} onChange={(event) => setRequestForm({ ...requestForm, requested_end_offset_minutes: event.target.value })} /></label>
                <label>理由<textarea readOnly={isSubmitting || selectedShift.shift_change_requests.length > 0} value={requestForm.reason} onChange={(event) => setRequestForm({ ...requestForm, reason: event.target.value })} /></label>
                <label>備考<textarea readOnly={isSubmitting || selectedShift.shift_change_requests.length > 0} value={requestForm.requested_notes} onChange={(event) => setRequestForm({ ...requestForm, requested_notes: event.target.value })} /></label>
                <div className="actions">
                  <button type="button" disabled={isSubmitting || selectedShift.shift_change_requests.length > 0} onClick={() => void submitChangeRequest(false)}>下書き保存</button>
                  <button type="button" disabled={isSubmitting || selectedShift.shift_change_requests.length > 0} onClick={() => void submitChangeRequest(true)}>提出</button>
                </div>
              </section>
              <h3>勤務内訳</h3>
              <table className="table">
                <thead><tr><th>開始～終了</th><th>業務名</th><th>業務エリア</th><th>備考</th><th>休憩区分</th></tr></thead>
                <tbody>
                  {selectedShift.segments.map((segment) => (
                    <tr key={segment.id}>
                      <td>{offsetToLabel(segment.start_offset_minutes)}~{offsetToLabel(segment.end_offset_minutes)}</td>
                      <td>{segment.work_type_name_snapshot}</td>
                      <td>{segment.work_area_name_snapshot || "-"}</td>
                      <td>{segment.notes}</td>
                      <td>{segment.work_type_is_break_snapshot ? "休憩" : "勤務"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </aside>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
