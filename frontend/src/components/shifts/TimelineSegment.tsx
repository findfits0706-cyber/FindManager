import { offsetToLabel } from "../../lib/timeOffsets";
import { segmentStyle, type TimelineRange } from "../../lib/timeline";
import type { TimelineAssignment, TimelineSegment as TimelineSegmentType } from "../../lib/types";

type Props = {
  assignment: TimelineAssignment;
  segment: TimelineSegmentType;
  range: TimelineRange;
  slotWidth: number;
  onOpen: () => void;
};

export function TimelineSegment({ assignment, segment, range, slotWidth, onOpen }: Props) {
  const { clamped, style } = segmentStyle(segment, range, slotWidth);
  if (!clamped.isVisible) return null;
  const timeLabel = `${offsetToLabel(segment.start_offset_minutes)}-${offsetToLabel(segment.end_offset_minutes)}`;
  const label = segment.work_type_short_name || assignment.pattern_short_name || segment.work_type_name;
  return (
    <button
      type="button"
      className={`timeline-segment color-${segment.work_type_color_key} ${segment.work_type_is_break ? "is-break" : ""}`}
      style={style}
      aria-label={`${segment.work_type_name} ${timeLabel}`}
      onClick={onOpen}
    >
      <span className="segment-main">
        {clamped.continuesLeft ? "< " : ""}
        {label}
        {clamped.continuesRight ? " >" : ""}
      </span>
      <span className="segment-meta">{timeLabel}</span>
    </button>
  );
}
