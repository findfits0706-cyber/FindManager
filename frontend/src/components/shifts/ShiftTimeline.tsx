import { offsetToLabel } from "../../lib/timeOffsets";
import { timelineWidth, type TimelineRange } from "../../lib/timeline";
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

function Header({ range, slotWidth }: { range: TimelineRange; slotWidth: number }) {
  const hourStyle = {
    width: timelineWidth(range, slotWidth),
    "--timeline-quarter": `${slotWidth}px`,
    "--timeline-hour": `${slotWidth * 4}px`,
  } as CSSProperties;
  return (
    <div className="timeline-header" style={{ minWidth: timelineWidth(range, slotWidth) + 180 }}>
      <div className="timeline-staff timeline-header-staff">スタッフ</div>
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

export function ShiftTimeline({ data, mode, range, slotWidth, onSelect }: Props) {
  if (!data.rows.length || !data.summary.segment_count) {
    return <p className="empty-state">表示できる勤務がありません。</p>;
  }

  return (
    <div className={`shift-timeline shift-timeline-${mode}`}>
      <Header range={range} slotWidth={slotWidth} />
      {mode === "day"
        ? data.rows.map((row) => (
            <TimelineRow key={row.staff} row={row} date={data.dates[0].date} range={range} slotWidth={slotWidth} onSelect={onSelect} />
          ))
        : data.dates.map((date) => (
            <section key={date.date} className={`timeline-day-section ${date.is_saturday ? "saturday" : date.is_sunday ? "sunday" : ""}`}>
              <h3>
                {date.day}日（{date.weekday_label}）
              </h3>
              {data.rows.map((row) => (
                <TimelineRow key={`${date.date}-${row.staff}`} row={row} date={date.date} range={range} slotWidth={slotWidth} onSelect={onSelect} />
              ))}
            </section>
          ))}
    </div>
  );
}
