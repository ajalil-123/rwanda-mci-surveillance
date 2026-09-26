"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AXIS_PROPS, GRID_PROPS, TOOLTIP_PROPS, type Series } from "./theme";

export function LineChart<T extends object>({
  data,
  categoryKey,
  series,
  height = 280,
}: {
  data: T[];
  categoryKey: keyof T & string;
  series: Series<T>[];
  height?: number;
}) {
  // See bar-chart.tsx: Recharts 3 can't resolve a generic keyof T as a data key
  const rows = data as readonly Record<string, unknown>[];
  const category: string = categoryKey;

  return (
    <div className="text-muted-foreground" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsLineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis dataKey={category} {...AXIS_PROPS} minTickGap={24} />
          <YAxis width={40} {...AXIS_PROPS} />
          <Tooltip {...TOOLTIP_PROPS} />
          {series.length > 1 ? <Legend wrapperStyle={{ fontSize: 12 }} /> : null}
          {series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key as string}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls
            />
          ))}
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  );
}
