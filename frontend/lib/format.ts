const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

export const money = (value: number | null | undefined): string =>
  typeof value === "number" && Number.isFinite(value) ? inr.format(value) : "-";

export function dateTime(value: string | null | undefined): string {
  if (!value) return "-";
  // The API returns UTC; SQLite-backed dev data can lack the zone suffix.
  const iso = /[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`;
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? "-"
    : date.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export const label = (value: string): string => value.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const tenderTypeLabel: Record<string, string> = {
  rfq: "RFQ (open quotes)",
  sealed: "Sealed bid",
  reverse_auction: "Reverse auction",
};

/** <input type="datetime-local"> value (local time) -> ISO string with the browser's UTC offset. */
export function localInputToIso(value: string): string {
  return new Date(value).toISOString();
}

export function isoToLocalInput(value: string): string {
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
