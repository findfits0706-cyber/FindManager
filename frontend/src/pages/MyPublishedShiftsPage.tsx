import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { offsetToLabel } from "../lib/timeOffsets";
import type { MyPublishedShift, MyPublishedShiftsResponse } from "../lib/types";

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

export function MyPublishedShiftsPage() {
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [location, setLocation] = useState("");
  const [selectedShift, setSelectedShift] = useState<MyPublishedShift | null>(null);
  const [knownLocations, setKnownLocations] = useState<Array<{ id: string; name: string }>>([]);
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
      {!query.isLoading && !query.isError && shifts.length === 0 ? <p className="subtle-text">公開シフトはありません。</p> : null}
      {shifts.length ? (
        <div className="monthly-layout">
          <div className="monthly-grid-wrap">
            <table className="table">
              <thead>
                <tr><th>日付</th><th>曜日</th><th>拠点</th><th>勤務パターン</th><th>開始～終了</th><th>勤務時間</th><th>休憩時間</th><th>公開Version</th><th>公開日時</th></tr>
              </thead>
              <tbody>
                {shifts.map((shift) => {
                  const dateInfo = query.data?.dates.find((item) => item.date === shift.work_date);
                  return (
                    <tr key={shift.id} className={dateInfo?.is_saturday ? "saturday" : dateInfo?.is_sunday ? "sunday" : ""}>
                      <td><button type="button" className="btn-link" onClick={() => setSelectedShift(shift)}>{shift.work_date}</button></td>
                      <td>{dateInfo?.weekday_label ?? ""}</td>
                      <td>{shift.publication.location_name}</td>
                      <td>{shift.pattern_short_name_snapshot || shift.pattern_name_snapshot}</td>
                      <td>{shift.start_offset_minutes == null || shift.end_offset_minutes == null ? "-" : `${offsetToLabel(shift.start_offset_minutes)}~${offsetToLabel(shift.end_offset_minutes)}`}</td>
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
                <dt>Assignment備考</dt><dd>{selectedShift.notes}</dd>
                <dt>公開Version</dt><dd>v{selectedShift.publication.version}</dd>
                <dt>公開日時</dt><dd>{selectedShift.publication.published_at}</dd>
              </dl>
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
