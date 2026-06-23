export function offsetToLabel(value: number): string {
  const dayPrefix = value >= 1440 ? "翌" : "";
  const minutesInDay = value % 1440;
  const hours = Math.floor(minutesInDay / 60)
    .toString()
    .padStart(2, "0");
  const minutes = (minutesInDay % 60).toString().padStart(2, "0");
  return `${dayPrefix}${hours}:${minutes}`;
}

export function labelToOffset(value: string): number {
  const nextDay = value.startsWith("翌");
  const normalized = value.replace("翌", "");
  const [hours, minutes] = normalized.split(":").map(Number);
  return (nextDay ? 1440 : 0) + hours * 60 + minutes;
}

export function buildOffsetOptions(): Array<{ value: number; label: string }> {
  const options: Array<{ value: number; label: string }> = [];
  for (let value = 0; value <= 2880; value += 15) {
    options.push({ value, label: offsetToLabel(value) });
  }
  return options;
}
