import type { TimelineRange } from "./timeline";
import type { ShiftTimelineResponse } from "./types";

type TimelineRow = ShiftTimelineResponse["rows"][number];

export function printSlotWidthForRange(range: TimelineRange): number {
  const slotCount = (range.end - range.start) / 15;
  return Math.max(3, Math.min(8, 800 / slotCount));
}

export function estimatePrintRowHeight(row: TimelineRow, date: string): number {
  const segments = row.days[date]?.segments ?? [];
  const laneCount = Math.max(1, ...segments.map((segment) => segment.lane_count));
  return laneCount * 28 + 12;
}

export function chunkRowsForPrint(
  rows: TimelineRow[],
  date: string,
  maxEstimatedHeight = 560,
  maxRows = 12,
): TimelineRow[][] {
  const chunks: TimelineRow[][] = [];
  let current: TimelineRow[] = [];
  let currentHeight = 0;

  for (const row of rows) {
    const rowHeight = estimatePrintRowHeight(row, date);
    const shouldStartNextPage =
      current.length > 0 && (current.length >= maxRows || currentHeight + rowHeight > maxEstimatedHeight);
    if (shouldStartNextPage) {
      chunks.push(current);
      current = [];
      currentHeight = 0;
    }
    current.push(row);
    currentHeight += rowHeight;
  }

  if (current.length) {
    chunks.push(current);
  }
  return chunks;
}
