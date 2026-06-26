export function formatLocalIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function parseLocalIsoDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function addDaysToIsoDate(value: string, days: number): string {
  const date = parseLocalIsoDate(value);
  date.setDate(date.getDate() + days);
  return formatLocalIsoDate(date);
}

export function yearMonthFromIsoDate(value: string): { year: number; month: number } {
  const date = parseLocalIsoDate(value);
  return { year: date.getFullYear(), month: date.getMonth() + 1 };
}

export function formatLocalDateTime(date: Date): string {
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}年${month}月${day}日 ${hours}:${minutes}`;
}
