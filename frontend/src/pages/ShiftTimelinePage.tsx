import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { ShiftDetailPanel, type TimelineSelection } from "../components/shifts/ShiftDetailPanel";
import { PrintTimeline, ShiftTimeline } from "../components/shifts/ShiftTimeline";
import { useAuth } from "../features/auth/AuthContext";
import { addDaysToIsoDate, formatLocalDateTime, formatLocalIsoDate, yearMonthFromIsoDate } from "../lib/localDate";
import { offsetToLabel } from "../lib/timeOffsets";
import type {
  Location,
  MonthlyShiftAssignment,
  MonthlyShiftPlan,
  Paginated,
  ShiftTimelineResponse,
  WorkArea,
  WorkType,
} from "../lib/types";

const today = new Date();

export function ShiftTimelinePage() {
  const { user } = useAuth();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const canView = canManage || roles.includes("supervisor");
  const [location, setLocation] = useState("");
  const [mode, setMode] = useState<"day" | "week">("day");
  const [anchorDate, setAnchorDate] = useState(formatLocalIsoDate(today));
  const [{ year, month }, setYearMonth] = useState(yearMonthFromIsoDate(formatLocalIsoDate(today)));
  const [staffSearch, setStaffSearch] = useState("");
  const [assignedOnly, setAssignedOnly] = useState(true);
  const [workType, setWorkType] = useState("");
  const [workArea, setWorkArea] = useState("");
  const [includeBreaks, setIncludeBreaks] = useState(true);
  const [rangeMode, setRangeMode] = useState<"auto" | "business" | "full" | "next">("auto");
  const [zoom, setZoom] = useState<"compact" | "normal" | "wide">("normal");
  const [selection, setSelection] = useState<TimelineSelection | null>(null);
  const [printedAt, setPrintedAt] = useState("");

  const locationQuery = useQuery({
    enabled: canView,
    queryKey: ["locations", "timeline"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100&is_active=true"),
  });
  useEffect(() => {
    if (!location && locationQuery.data?.results.length) setLocation(locationQuery.data.results[0].id);
  }, [location, locationQuery.data?.results]);

  const planQuery = useQuery({
    enabled: canView && Boolean(location),
    queryKey: ["monthly-shift-plans", "timeline", location, year, month],
    queryFn: () =>
      api<Paginated<MonthlyShiftPlan>>(
        `/api/v1/monthly-shift-plans/?page_size=10&location=${location}&year=${year}&month=${month}&is_active=true`,
      ),
  });
  const plan = planQuery.data?.results[0] ?? null;

  const dateFrom = anchorDate;
  const dateTo = mode === "day" ? anchorDate : addDaysToIsoDate(anchorDate, 6);
  const timelineQuery = useQuery({
    enabled: canView && Boolean(plan),
    queryKey: ["shift-timeline", plan?.id, dateFrom, dateTo, staffSearch, assignedOnly, workType, workArea, includeBreaks],
    queryFn: () => {
      const params = new URLSearchParams({
        date_from: dateFrom,
        date_to: dateTo,
        assigned_only: String(assignedOnly),
        include_breaks: String(includeBreaks),
      });
      if (staffSearch) params.set("staff_search", staffSearch);
      if (workType) params.set("work_type", workType);
      if (workArea) params.set("work_area", workArea);
      return api<ShiftTimelineResponse>(`/api/v1/monthly-shift-plans/${plan?.id}/timeline/?${params.toString()}`);
    },
  });
  const workTypeQuery = useQuery({
    enabled: canView && Boolean(location),
    queryKey: ["work-types", "timeline", location],
    queryFn: () => api<Paginated<WorkType>>(`/api/v1/work-types/?page_size=100&is_active=true&location=${location}`),
  });
  const workAreaQuery = useQuery({
    enabled: canView && Boolean(location),
    queryKey: ["work-areas", "timeline", location],
    queryFn: () => api<Paginated<WorkArea>>(`/api/v1/work-areas/?page_size=100&is_active=true&location=${location}`),
  });
  const selectedAssignmentId = selection?.assignment?.id ?? "";
  const assignmentDetailQuery = useQuery({
    enabled: Boolean(selectedAssignmentId),
    queryKey: ["monthly-shift-assignment-detail", selectedAssignmentId],
    queryFn: () => api<MonthlyShiftAssignment>(`/api/v1/monthly-shift-assignments/${selectedAssignmentId}/`),
  });

  const slotWidth = zoom === "compact" ? 8 : zoom === "wide" ? 16 : 12;
  useEffect(() => {
    setSelection(null);
  }, [plan?.id, dateFrom, dateTo, mode, staffSearch, assignedOnly, workType, workArea, includeBreaks, location]);
  useEffect(() => {
    if (!selection) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelection(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selection]);
  const range = useMemo(() => {
    if (rangeMode === "business") return { start: 360, end: 1440 };
    if (rangeMode === "full") return { start: 0, end: 1440 };
    if (rangeMode === "next") return { start: 0, end: Math.min(2880, Math.max(1440, timelineQuery.data?.range.suggested_end_offset ?? 1440)) };
    return {
      start: timelineQuery.data?.range.suggested_start_offset ?? 360,
      end: timelineQuery.data?.range.suggested_end_offset ?? 1440,
    };
  }, [rangeMode, timelineQuery.data?.range.suggested_end_offset, timelineQuery.data?.range.suggested_start_offset]);

  if (!canView) return <Navigate to="/403" replace />;

  const move = (days: number) => {
    const next = addDaysToIsoDate(anchorDate, days);
    setAnchorDate(next);
    setYearMonth(yearMonthFromIsoDate(next));
    setSelection(null);
  };
  const setToday = () => {
    const next = formatLocalIsoDate(new Date());
    setAnchorDate(next);
    setYearMonth(yearMonthFromIsoDate(next));
  };
  const print = () => {
    setPrintedAt(formatLocalDateTime(new Date()));
    const runPrint = () => window.print();
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(runPrint);
      return;
    }
    window.setTimeout(runPrint, 0);
  };

  return (
    <section className="timeline-page">
      <div className="print-title">
        <h1>ファインドスポーツクラブ</h1>
        <p>
          {timelineQuery.data?.plan.location_name ?? ""} / {timelineQuery.data?.range.date_from ?? dateFrom}
          {mode === "week" ? `-${timelineQuery.data?.range.date_to ?? dateTo}` : ""} / {mode === "day" ? "日別" : "週別"} /{" "}
          {offsetToLabel(range.start)}-{offsetToLabel(range.end)}
          {printedAt ? ` / 印刷日時：${printedAt}` : ""}
        </p>
      </div>
      <div className="section-header no-print">
        <div>
          <p className="eyebrow">Shift timeline</p>
          <h2>日別・週別シフト</h2>
        </div>
        <button type="button" disabled={!timelineQuery.data} onClick={print}>
          印刷
        </button>
      </div>
      <div className="timeline-controls field-grid no-print">
        <label>
          拠点
          <select
            value={location}
            onChange={(event) => {
              setLocation(event.target.value);
              setWorkType("");
              setWorkArea("");
            }}
          >
            <option value="">選択してください</option>
            {locationQuery.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          日付
          <input
            type="date"
            value={anchorDate}
            onChange={(event) => {
              setAnchorDate(event.target.value);
              setYearMonth(yearMonthFromIsoDate(event.target.value));
            }}
          />
        </label>
        <label>
          表示
          <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
            <option value="day">日別</option>
            <option value="week">週別</option>
          </select>
        </label>
        <button type="button" onClick={() => move(mode === "day" ? -1 : -7)}>
          {mode === "day" ? "前日" : "前週"}
        </button>
        <button type="button" onClick={() => move(mode === "day" ? 1 : 7)}>
          {mode === "day" ? "翌日" : "翌週"}
        </button>
        <button type="button" onClick={setToday}>
          今日
        </button>
        <label>
          スタッフ検索
          <input value={staffSearch} onChange={(event) => setStaffSearch(event.target.value)} />
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={assignedOnly} onChange={(event) => setAssignedOnly(event.target.checked)} />
          勤務ありのみ
        </label>
        <label>
          WorkType
          <select value={workType} onChange={(event) => setWorkType(event.target.value)}>
            <option value="">すべて</option>
            {workTypeQuery.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          WorkArea
          <select value={workArea} onChange={(event) => setWorkArea(event.target.value)}>
            <option value="">すべて</option>
            {workAreaQuery.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={includeBreaks} onChange={(event) => setIncludeBreaks(event.target.checked)} />
          休憩を表示
        </label>
        <label>
          表示時間範囲
          <select value={rangeMode} onChange={(event) => setRangeMode(event.target.value as typeof rangeMode)}>
            <option value="auto">自動</option>
            <option value="business">06:00-24:00</option>
            <option value="full">00:00-24:00</option>
            <option value="next">翌日まで</option>
          </select>
        </label>
        <label>
          表示倍率
          <select value={zoom} onChange={(event) => setZoom(event.target.value as typeof zoom)}>
            <option value="compact">コンパクト</option>
            <option value="normal">標準</option>
            <option value="wide">拡大</option>
          </select>
        </label>
      </div>
      {locationQuery.isError ? <p className="error">Location APIの取得に失敗しました。</p> : null}
      {planQuery.isError ? <p className="error">Plan APIの取得に失敗しました。</p> : null}
      {workTypeQuery.isError ? <p className="error">WorkType APIの取得に失敗しました。</p> : null}
      {workAreaQuery.isError ? <p className="error">WorkArea APIの取得に失敗しました。</p> : null}
      {!plan && !planQuery.isLoading && !planQuery.isError ? <p className="empty-state">対象月の月間シフトがありません。</p> : null}
      {timelineQuery.isLoading ? <p>読み込み中...</p> : null}
      {timelineQuery.isError ? <p className="error">Timeline APIの取得に失敗しました。</p> : null}
      <div className="timeline-layout">
        <div className="timeline-scroll screen-timeline">
          {timelineQuery.data ? <ShiftTimeline data={timelineQuery.data} mode={mode} range={range} slotWidth={slotWidth} onSelect={setSelection} /> : null}
        </div>
        {timelineQuery.data ? (
          <PrintTimeline data={timelineQuery.data} mode={mode} range={range} printedAt={printedAt} rowsPerPage={12} />
        ) : null}
        {timelineQuery.data ? (
          <ShiftDetailPanel
            plan={timelineQuery.data.plan}
            selection={selection}
            assignmentDetail={assignmentDetailQuery.data ?? null}
            isLoading={assignmentDetailQuery.isLoading}
            isError={assignmentDetailQuery.isError}
            canManage={canManage}
            onClose={() => setSelection(null)}
          />
        ) : null}
      </div>
      {assignmentDetailQuery.isError ? <p className="error">Assignment詳細APIの取得に失敗しました。</p> : null}
      {timelineQuery.data?.legend.length ? (
        <div className="timeline-legend">
          {timelineQuery.data.legend.map((item) => (
            <span key={`${item.work_type}-${item.name}-${item.color_key}-${item.is_break}`} className={`legend-item color-${item.color_key}`}>
              {item.short_name} {item.name}
              {item.is_break ? " / 休憩" : ""}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
