import { TimelineSegment } from "./TimelineSegment";
import { timelineWidth, type TimelineRange } from "../../lib/timeline";
import type { ShiftTimelineResponse, TimelineAssignment, TimelineSegment as TimelineSegmentType } from "../../lib/types";
import type { CSSProperties } from "react";

type Selection = {
  staffId: string;
  staffName: string;
  date: string;
  assignment: TimelineAssignment | null;
  segments: TimelineSegmentType[];
};

type Props = {
  row: ShiftTimelineResponse["rows"][number];
  date: string;
  range: TimelineRange;
  slotWidth: number;
  staffWidth?: number;
  onSelect: (selection: Selection) => void;
};

export function TimelineRow({ row, date, range, slotWidth, staffWidth = 180, onSelect }: Props) {
  const day = row.days[date] ?? { assignment: null, segments: [] };
  const assignment = day.assignment;
  const laneCount = Math.max(1, ...day.segments.map((segment) => segment.lane_count));
  const trackStyle = {
    width: timelineWidth(range, slotWidth),
    minHeight: laneCount * 28 + 12,
    "--timeline-quarter": `${slotWidth}px`,
    "--timeline-hour": `${slotWidth * 4}px`,
  } as CSSProperties;
  return (
    <div
      className="timeline-row"
      style={{ minWidth: timelineWidth(range, slotWidth) + staffWidth, gridTemplateColumns: `${staffWidth}px 1fr` }}
    >
      <button
        type="button"
        className="timeline-staff"
        style={{ width: staffWidth }}
        onClick={() =>
          onSelect({
            staffId: row.staff,
            staffName: row.staff_display_name,
            date,
            assignment: day.assignment,
            segments: day.segments,
          })
        }
      >
        <strong>{row.staff_display_name}</strong>
        <span>{row.employee_code}</span>
      </button>
      <div className="timeline-track" style={trackStyle}>
        {assignment
          ? day.segments.map((segment) => (
              <TimelineSegment
                key={segment.id}
                assignment={assignment}
                segment={segment}
                range={range}
                slotWidth={slotWidth}
                onOpen={() =>
                  onSelect({
                    staffId: row.staff,
                    staffName: row.staff_display_name,
                    date,
                    assignment: day.assignment,
                    segments: day.segments,
                  })
                }
              />
            ))
          : null}
      </div>
    </div>
  );
}
