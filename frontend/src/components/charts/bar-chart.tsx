"use client";

import {
  Bar,
  BarChart as RechartsBarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AXIS_PROPS, GRID_PROPS, TOOLTIP_PROPS, type Series } from "./theme";

export function BarChart<T extends object>({
  data,
  categoryKey,
  series,
  height = 280,
  horizontal = false,
  categoryWidth = 110,
  valueFormatter,
}: {
  data: T[];
  categoryKey: keyof T & string;
  series: Series<T>[];
  height?: number;
  /** Bars run left→right with categories on the Y axis (better for long labels). */
  horizontal?: boolean;
  categoryWidth?: number;
  valueFormatter?: (value: number) => string;
}) {
  const formatter = valueFormatter ? (v: unknown) => valueFormatter(Number(v)) : undefined;
  // Props are checked against T above; Recharts 3's TypedDataKey can't resolve a
  // generic keyof T, so hand it plain records with string keys.
  const rows = data as readonly Record<string, unknown>[];
  const category: string = categoryKey;

  return (
    <div className="text-muted-foreground" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsBarChart
          data={rows}
          layout={horizontal ? "vertical" : "horizontal"}
          margin={{ top: 8, right: 16, bottom: 0, left: 0 }}
        >
          <CartesianGrid {...GRID_PROPS} vertical={horizontal} horizontal={!horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" {...AXIS_PROPS} tickFormatter={formatter} />
              <YAxis type="category" dataKey={category} width={categoryWidth} {...AXIS_PROPS} />
            </>
          ) : (
            <>
              <XAxis dataKey={category} {...AXIS_PROPS} />
              <YAxis width={40} {...AXIS_PROPS} tickFormatter={formatter} />
            </>
          )}
          <Tooltip {...TOOLTIP_PROPS} formatter={formatter} />
          {series.length > 1 ? <Legend wrapperStyle={{ fontSize: 12 }} /> : null}
          {series.map((s) => (
            <Bar
              key={s.key}
              dataKey={s.key as string}
              name={s.label}
              fill={s.color}
              radius={horizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]}
              maxBarSize={36}
            />
          ))}
        </RechartsBarChart>
      </ResponsiveContainer>
    </div>
  );
}
