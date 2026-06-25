import type { TimelineRange } from "./timeline";

export function printSlotWidthForRange(range: TimelineRange): number {
  const slotCount = (range.end - range.start) / 15;
  return Math.max(3, Math.min(8, 800 / slotCount));
}
