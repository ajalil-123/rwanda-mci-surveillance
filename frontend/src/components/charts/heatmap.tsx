"use client";

import { useMemo } from "react";
import type { HeatmapCell } from "@/lib/api";
import { MONTH_NAMES, formatNumber } from "@/lib/format";
import { SERIES_COLORS } from "./theme";

type Metric = "incidents" | "deaths";

function alphaHex(alpha: number): string {
  return Math.round(Math.min(1, Math.max(0, alpha)) * 255)
    .toString(16)
    .padStart(2, "0");
}

/**
 * Year × month calendar heatmap. Plain CSS grid — no charting library needed,
 * and every cell carries an accessible label.
 */
export function Heatmap({ cells, metric = "incidents" }: { cells: HeatmapCell[]; metric?: Metric }) {
  const { years, lookup, max } = useMemo(() => {
    const lookup = new Map<string, number>();
    const years = new Set<string>();
    let max = 0;
    for (const c of cells) {
      const v = c[metric] ?? 0;
      lookup.set(`${c.year}-${c.month}`, v);
      years.add(c.year);
      if (v > max) max = v;
    }
    return { years: [...years].sort(), lookup, max };
  }, [cells, metric]);

  const color = metric === "deaths" ? SERIES_COLORS.deaths : SERIES_COLORS.incidents;

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-1 text-xs">
        <thead>
          <tr>
            <th scope="col" className="w-12 text-left font-medium text-muted-foreground">
              <span className="sr-only">Year</span>
            </th>
            {MONTH_NAMES.map((m) => (
              <th key={m} scope="col" className="font-medium text-muted-foreground">
                {m}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {years.map((year) => (
            <tr key={year}>
              <th scope="row" className="pr-2 text-left font-mono font-medium text-muted-foreground">
                {year}
              </th>
              {MONTH_NAMES.map((m, idx) => {
                const v = lookup.get(`${year}-${idx + 1}`) ?? 0;
                // sqrt scale keeps small counts visible next to rare large spikes
                const intensity = max > 0 ? Math.sqrt(v / max) : 0;
                const label = `${m} ${year}: ${formatNumber(v)} ${metric}`;
                return (
                  <td
                    key={m}
                    title={label}
                    aria-label={label}
                    className="h-7 min-w-[2rem] rounded-sm text-center font-mono tabular-nums"
                    style={{
                      // Alpha on the background only, so the number stays fully legible
                      backgroundColor: v > 0 ? `${color}${alphaHex(0.15 + intensity * 0.85)}` : undefined,
                      color: intensity > 0.55 ? "#fff" : undefined,
                    }}
                  >
                    {v > 0 ? v : <span className="text-muted-foreground/40">·</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
