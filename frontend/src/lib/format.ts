// Small display helpers. Costs arrive as decimal strings (the backend's Decimal) or null.

export function formatCost(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "n/a";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "n/a";
  if (n === 0) return "$0";
  if (Math.abs(n) < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}k`;
  return String(n);
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** "1-10" style line range, or one number for a single line. */
export function lineRange(start: number, end: number): string {
  return start === end ? String(start) : `${start}-${end}`;
}

/** Sum cost strings without floating drift in the common case of a few decimals. */
export function sumCosts(values: (string | null)[]): number {
  return values.reduce((total, v) => total + (v === null ? 0 : Number(v) || 0), 0);
}
