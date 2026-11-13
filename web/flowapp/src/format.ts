// Shared formatting for every view. null means unknown and is shown as such, never as 0.
export const UNKNOWN = "unknown";

export function fmtDuration(s: number | null | undefined): string {
  if (s === null || s === undefined) return UNKNOWN;
  const v = Math.max(0, Math.round(s));
  if (v >= 3600) return `${Math.floor(v / 3600)}h ${String(Math.floor((v % 3600) / 60)).padStart(2, "0")}m`;
  if (v >= 60) return `${Math.floor(v / 60)}m ${String(v % 60).padStart(2, "0")}s`;
  return `${v}s`;
}

export function fmtCost(c: number | null | undefined): string {
  if (c === null || c === undefined) return UNKNOWN;
  return `$${c.toFixed(2)}`;
}

/** Exact count with thousands separators ("5,330,357"). */
export function fmtCount(n: number | null | undefined): string {
  if (n === null || n === undefined) return UNKNOWN;
  return Math.round(n).toLocaleString("en-US");
}

/** Short token count ("1.20M", "43.0k", "120"). */
export function fmtTokens(n: number | null | undefined): string {
  if (n === null || n === undefined) return UNKNOWN;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}
