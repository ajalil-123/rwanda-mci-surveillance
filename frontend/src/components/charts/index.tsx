"use client";

/**
 * Lazy chart entry point. Recharts is ~100 kB, so charts load in their own
 * chunk after the page shell renders. Casting back to the source component's
 * type keeps the generic prop typing that next/dynamic would otherwise erase.
 */
import dynamic from "next/dynamic";
import type { BarChart as BarChartComponent } from "./bar-chart";
import type { LineChart as LineChartComponent } from "./line-chart";

function ChartSkeleton() {
  return <div className="h-[280px] w-full animate-pulse rounded-md bg-muted/50" />;
}

export const BarChart = dynamic(() => import("./bar-chart").then((m) => m.BarChart), {
  ssr: false,
  loading: ChartSkeleton,
}) as typeof BarChartComponent;

export const LineChart = dynamic(() => import("./line-chart").then((m) => m.LineChart), {
  ssr: false,
  loading: ChartSkeleton,
}) as typeof LineChartComponent;

export { Heatmap } from "./heatmap";
export { SERIES_COLORS } from "./theme";
