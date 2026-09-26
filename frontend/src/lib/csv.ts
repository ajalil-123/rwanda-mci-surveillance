/**
 * Minimal RFC 4180 CSV builder.
 *
 * Values that start with = + - @ (or tab/CR) are prefixed with an apostrophe:
 * titles come from scraped news, and Excel would otherwise execute them as
 * formulas (CSV injection).
 */
function escapeCell(value: unknown): string {
  if (value == null) return "";
  let s = String(value);
  if (typeof value === "string" && /^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv<T extends object>(rows: readonly T[], columns: readonly (keyof T & string)[]): string {
  const lines = [columns.join(",")];
  for (const row of rows) lines.push(columns.map((c) => escapeCell(row[c])).join(","));
  return lines.join("\r\n");
}

export function downloadCsv(filename: string, csv: string): void {
  // BOM so Excel detects UTF-8 (Kinyarwanda / French characters)
  const blob = new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
