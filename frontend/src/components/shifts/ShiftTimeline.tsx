import { offsetToLabel } from "../../lib/timeOffsets";
import { timelineWidth, type TimelineRange } from "../../lib/timeline";
import { chunkRowsForPrint, printSlotWidthForRange } from "../../lib/timelinePrint";
import type { ShiftTimelineResponse, TimelineAssignment, TimelineSegment } from "../../lib/types";
import { TimelineRow } from "./TimelineRow";
import type { CSSProperties } from "react";

type Selection = {
  staffId: string;
  staffName: string;
  date: string;
  assignment: TimelineAssignment | null;
  segments: TimelineSegment[];
};

type Props = {
  data: ShiftTimelineResponse;
  mode: "day" | "week";
  range: TimelineRange;
  slotWidth: number;
  staffWidth?: number;
  onSelect: (selection: Selection) => void;
};

function hourMarks(range: TimelineRange) {
  const marks = [];
  const first = Math.ceil(range.start / 60) * 60;
  for (let offset = first; offset <= range.end; offset += 60) {
    marks.push(offset);
  }
  return marks;
}

function Header({ range, slotWidth, staffWidth = 180 }: { range: TimelineRange; slotWidth: number; staffWidth?: number }) {
  const hourStyle = {
    width: timelineWidth(range, slotWidth),
    "--timeline-quarter": `${slotWidth}px`,
    "--timeline-hour": `${slotWidth * 4}px`,
  } as CSSProperties;
  return (
    <div
      className="timeline-header"
      style={{ minWidth: timelineWidth(range, slotWidth) + staffWidth, gridTemplateColumns: `${staffWidth}px 1fr` }}
    >
      <div className="timeline-staff timeline-header-staff" style={{ width: staffWidth }}>
        スタッフ
      </div>
      <div className="timeline-hours" style={hourStyle}>
        {hourMarks(range).map((offset) => (
          <span key={offset} style={{ left: `${((offset - range.start) / 15) * slotWidth}px` }}>
            {offsetToLabel(offset)}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ShiftTimeline({ data, mode, range, slotWidth, staffWidth = 180, onSelect }: Props) {
  if (!data.rows.length) {
    return <p className="empty-state">表示できるスタッフがいません。</p>;
  }

  return (
    <div className={`shift-timeline shift-timeline-${mode}`}>
      <Header range={range} slotWidth={slotWidth} staffWidth={staffWidth} />
      {mode === "day"
        ? data.rows.map((row) => (
            <TimelineRow
              key={row.staff}
              row={row}
              date={data.dates[0].date}
              range={range}
              slotWidth={slotWidth}
              staffWidth={staffWidth}
              onSelect={onSelect}
            />
          ))
        : data.dates.map((date) => (
            <section key={date.date} className={`timeline-day-section ${date.is_saturday ? "saturday" : date.is_sunday ? "sunday" : ""}`}>
              <h3>
                {date.day}日（{date.weekday_label}）
              </h3>
              {data.rows.map((row) => (
                <TimelineRow
                  key={`${date.date}-${row.staff}`}
                  row={row}
                  date={date.date}
                  range={range}
                  slotWidth={slotWidth}
                  staffWidth={staffWidth}
                  onSelect={onSelect}
                />
              ))}
            </section>
          ))}
    </div>
  );
}

type PrintProps = {
  data: ShiftTimelineResponse;
  mode: "day" | "week";
  range: TimelineRange;
  printedAt: string;
  rowsPerPage: number;
};

export function PrintTimeline({ data, mode, range, printedAt, rowsPerPage }: PrintProps) {
  const staffWidth = 140;
  const slotWidth = printSlotWidthForRange(range);
  const dates = mode === "day" ? [data.dates[0]] : data.dates;
  const pages = dates.flatMap((date) =>
    chunkRowsForPrint(data.rows, date.date, 560, rowsPerPage).map((rows, chunkIndex) => ({ date, rows, chunkIndex })),
  );
  return (
    <div className="print-timeline" aria-label="印刷用タイムライン">
      {pages.map((page, pageIndex) => (
        <section
          key={`${page.date.date}-${page.chunkIndex}`}
          className={`print-page ${pageIndex === pages.length - 1 ? "print-page-last" : ""}`}
          data-testid="print-page"
        >
          <div className="print-page-header">
            <strong>ファインドスポーツクラブ</strong>
            <span>
              {data.plan.location_name} / {page.date.date}（{page.date.weekday_label}） / {mode === "day" ? "日別" : "週別"} /{" "}
              {offsetToLabel(range.start)}-{offsetToLabel(range.end)}
            </span>
            <span>{printedAt ? `印刷日時：${printedAt}` : "印刷日時：-"}</span>
          </div>
          <Header range={range} slotWidth={slotWidth} staffWidth={staffWidth} />
          {page.rows.map((row) => (
            <TimelineRow
              key={`${page.date.date}-${row.staff}`}
              row={row}
              date={page.date.date}
              range={range}
              slotWidth={slotWidth}
              staffWidth={staffWidth}
              onSelect={() => undefined}
            />
          ))}
        </section>
      ))}
    </div>
  );
}
