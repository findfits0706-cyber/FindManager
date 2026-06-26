import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { offsetToLabel } from "../lib/timeOffsets";
import type { MyPublishedShift, Paginated } from "../lib/types";

function isoDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const today = new Date();
const defaultFrom = isoDate(new Date(today.getFullYear(), today.getMonth(), 1));
const defaultTo = isoDate(new Date(today.getFullYear(), today.getMonth() + 1, 0));

export function MyPublishedShiftsPage() {
  const [dateFrom, setDateFrom] = useState(defaultFrom);
  const [dateTo, setDateTo] = useState(defaultTo);
  const query = useQuery({
    queryKey: ["my-published-shifts", dateFrom, dateTo],
    queryFn: () =>
      api<Paginated<MyPublishedShift>>(
        `/api/v1/my-published-shifts/?date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}&page_size=100`,
      ),
  });
  const grouped = useMemo(() => {
    const rows = query.data?.results ?? [];
    const result = new Map<string, MyPublishedShift[]>();
    for (const row of rows) {
      result.set(row.work_date, [...(result.get(row.work_date) ?? []), row]);
    }
    return Array.from(result.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [query.data?.results]);

  return (
    <section className="card monthly-page">
      <div className="section-header">
        <div>
          <p className="eyebrow">Published shifts</p>
          <h2>自分の公開シフト</h2>
        </div>
      </div>
      <div className="toolbar field-grid">
        <label>開始日<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
        <label>終了日<input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
      </div>
      {query.isLoading ? <p>読み込み中...</p> : null}
      {query.isError ? <p className="error">公開シフトの取得に失敗しました。</p> : null}
      {!query.isLoading && !query.isError && grouped.length === 0 ? <p className="subtle-text">公開シフトはありません。</p> : null}
      {grouped.map(([workDate, shifts]) => (
        <section className="preview-panel" key={workDate}>
          <h3>{workDate}</h3>
          <table className="table">
            <thead>
              <tr><th>拠点</th><th>勤務</th><th>時間</th><th>内訳</th><th>備考</th></tr>
            </thead>
            <tbody>
              {shifts.map((shift) => (
                <tr key={shift.id}>
                  <td>{shift.publication.location_name}</td>
                  <td>{shift.pattern_short_name_snapshot || shift.pattern_name_snapshot}</td>
                  <td>
                    {shift.start_offset_minutes == null || shift.end_offset_minutes == null
                      ? "-"
                      : `${offsetToLabel(shift.start_offset_minutes)}~${offsetToLabel(shift.end_offset_minutes)}`}
                  </td>
                  <td>
                    {shift.segments
                      .map((segment) => `${offsetToLabel(segment.start_offset_minutes)} ${segment.work_type_short_name_snapshot}`)
                      .join(" / ")}
                  </td>
                  <td>{shift.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </section>
  );
}
