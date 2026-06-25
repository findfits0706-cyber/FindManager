import type { TimelineSegment } from "./types";

export type TimelineRange = {
  start: number;
  end: number;
};

export function offsetToPosition(offset: number, rangeStart: number, slotWidth: number): number {
  return ((offset - rangeStart) / 15) * slotWidth;
}

export function durationToWidth(durationMinutes: number, slotWidth: number): number {
  return (durationMinutes / 15) * slotWidth;
}

export function clampSegmentToRange(segment: Pick<TimelineSegment, "start_offset_minutes" | "end_offset_minutes">, range: TimelineRange) {
  const start = Math.max(segment.start_offset_minutes, range.start);
  const end = Math.min(segment.end_offset_minutes, range.end);
  return {
    start,
    end,
    duration: Math.max(0, end - start),
    continuesLeft: segment.start_offset_minutes < range.start,
    continuesRight: segment.end_offset_minutes > range.end,
    isVisible: end > start,
  };
}

export function segmentStyle(segment: TimelineSegment, range: TimelineRange, slotWidth: number) {
  const clamped = clampSegmentToRange(segment, range);
  const width = durationToWidth(clamped.duration, slotWidth);
  const minimumWidth = Math.min(32, Math.max(slotWidth, width));
  return {
    clamped,
    style: {
      left: `${offsetToPosition(clamped.start, range.start, slotWidth)}px`,
      width: `${Math.max(width, minimumWidth)}px`,
      top: `${segment.lane * 28 + 4}px`,
      height: `${Math.max(22, 24 - Math.max(0, segment.lane_count - 1) * 2)}px`,
    },
  };
}

export function timelineWidth(range: TimelineRange, slotWidth: number): number {
  return Math.max(1, ((range.end - range.start) / 15) * slotWidth);
}
