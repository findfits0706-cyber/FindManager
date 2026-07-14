import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { offsetToLabel } from "../lib/timeOffsets";
import type {
  AttendanceClosingPreviewItem,
  AttendanceClosingRecordSnapshot,
  Location,
  MyAttendanceMonthlyItem,
  MyAttendanceMonthlyResponse,
  Paginated,
} from "../lib/types";

const today = new Date();

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    live: "未締め・速報値",
    draft: "未締め・速報値",
    review: "未締め・速報値",
    reopened: "未締め・速報値",
    closed: "締め済み",
  };
  return labels[status] ?? status;
}

function isSnapshot(item: AttendanceClosingPreviewItem | AttendanceClosingRecordSnapshot): item is AttendanceClosingRecordSnapshot {
  return "status_snapshot" in item;
}

function dailyStatus(item: AttendanceClosingPreviewItem | AttendanceClosingRecordSnapshot) {
  return isSnapshot(item) ? item.status_snapshot : item.status;
}

function dailySource(item: AttendanceClosingPreviewItem | AttendanceClosingRecordSnapshot) {
  return isSnapshot(item) ? item.source_snapshot : item.source;
}

function warningCodes(item: AttendanceClosingPreviewItem | AttendanceClosingRecordSnapshot) {
  return item.warnings.length ? item.warnings.map((warning) => warning.code).join(" / ") : "-";
}

function scheduledRange(item: AttendanceClosingPreviewItem | AttendanceClosingRecordSnapshot) {
  if (item.scheduled_start_offset_minutes == null || item.scheduled_end_offset_minutes == null) return "-";
  return `${offsetToLabel(item.scheduled_start_offset_minutes)}~${offsetToLabel(item.scheduled_end_offset_minutes)}`;
}

function actualRange(item: AttendanceClosingPreviewItem | AttendanceClosingRecordSnapshot) {
  if (item.actual_start_offset_minutes == null || item.actual_end_offset_minutes == null) return "-";
  return `${offsetToLabel(item.actual_start_offset_minutes)}~${offsetToLabel(item.actual_end_offset_minutes)}`;
}

export function MyAttendanceMonthlyPage() {
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [location, setLocation] = useState("");
  const [status, setStatus] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ year: String(year), month: String(month) });
    if (location) params.set("location", location);
    if (status) params.set("status", status);
    return params.toString();
  }, [location, month, status, year]);

  const locationsQuery = useQuery({
    queryKey: ["my-attendance-monthly-locations"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
  });
  const monthlyQuery = useQuery({
    queryKey: ["my-attendance-monthly", queryString],
    queryFn: () => api<MyAttendanceMonthlyResponse>(`/api/v1/my-attendance-monthly/?${queryString}`),
  });
  const items = monthlyQuery.data?.results ?? [];
  const selected: MyAttendanceMonthlyItem | null = items[selectedIndex] ?? items[0] ?? null;

  return (
    <section className="card monthly-page">
      <div className="section-header">
        <div>
          <p className="eyebrow">My monthly attendance</p>
          <h2>自分の月次勤怠</h2>
        </div>
      </div>
      <div className="toolbar field-grid">
        <label>年<input type="number" value={year} onChange={(event) => { setYear(Number(event.target.value)); setSelectedIndex(0); }} /></label>
        <label>月<input type="number" min={1} max={12} value={month} onChange={(event) => { setMonth(Number(event.target.value)); setSelectedIndex(0); }} /></label>
        <label>拠点<select value={location} onChange={(event) => { setLocation(event.target.value); setSelectedIndex(0); }}><option value="">すべて</option>{locationsQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>状態<select value={status} onChange={(event) => { setStatus(event.target.value); setSelectedIndex(0); }}><option value="">すべて</option><option value="closed">締め済み</option><option value="live">未締め・速報値</option><option value="reopened">再オープン</option></select></label>
      </div>
      {monthlyQuery.isLoading ? <p>読み込み中...</p> : null}
      {monthlyQuery.isError ? <p className="error">月次勤怠の取得に失敗しました。</p> : null}
      {!monthlyQuery.isLoading && !monthlyQuery.isError && items.length === 0 ? <p className="subtle-text">月次勤怠はありません。</p> : null}
      {items.length > 1 ? (
        <div className="actions">
          {items.map((item, index) => (
            <button key={`${item.location}-${item.period ?? index}`} type="button" disabled={index === selectedIndex} onClick={() => setSelectedIndex(index)}>
              {item.location_name}
            </button>
          ))}
        </div>
      ) : null}
      {selected ? (
        <section className="inline-alert">
          <h3>{selected.year}-{String(selected.month).padStart(2, "0")} {selected.location_name}</h3>
          <p className="subtle-text">{statusLabel(selected.status)}</p>
          {selected.summary ? (
            <dl>
              <dt>勤務日数</dt><dd>{selected.summary.worked_days}日</dd>
              <dt>勤務分</dt><dd>{selected.summary.worked_minutes}分</dd>
              <dt>休憩分</dt><dd>{selected.summary.break_minutes}分</dd>
              <dt>warning</dt><dd>{selected.summary.warning_count}</dd>
              <dt>未確定</dt><dd>{selected.summary.unconfirmed_count}</dd>
            </dl>
          ) : <p className="subtle-text">集計対象はありません。</p>}
          {selected.warnings.length ? (
            <p className="error">{selected.warnings.map((warning) => warning.code).join(" / ")}</p>
          ) : null}
          {selected.daily.length ? (
            <table className="table">
              <thead><tr><th>勤務日</th><th>状態</th><th>ソース</th><th>予定</th><th>実績</th><th>休憩</th><th>勤務</th><th>warning</th></tr></thead>
              <tbody>
                {selected.daily.map((item) => (
                  <tr key={`${item.work_date}-${isSnapshot(item) ? item.id : item.attendance_record ?? item.source}`}>
                    <td>{item.work_date}</td>
                    <td>{dailyStatus(item)}</td>
                    <td>{dailySource(item)}</td>
                    <td>{scheduledRange(item)}</td>
                    <td>{actualRange(item)}</td>
                    <td>{item.break_minutes}分</td>
                    <td>{item.worked_minutes}分</td>
                    <td>{warningCodes(item)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="subtle-text">日別明細はありません。</p>}
        </section>
      ) : null}
    </section>
  );
}
