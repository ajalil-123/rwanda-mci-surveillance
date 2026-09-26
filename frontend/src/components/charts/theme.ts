/**
 * Chart palette. Recharts writes colours as SVG attributes, where CSS custom
 * properties don't resolve reliably — so series use fixed hex values, and axes
 * use `currentColor` inherited from a Tailwind text colour on the wrapper.
 */
export const SERIES_COLORS = {
  incidents: "#388bfd",
  deaths: "#f85149",
  injured: "#d29922",
  neutral: "#8b949e",
} as const;

export interface Series<T> {
  key: keyof T & string;
  label: string;
  color: string;
}

export const AXIS_PROPS = {
  stroke: "currentColor",
  tick: { fill: "currentColor", fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

export const GRID_PROPS = {
  strokeDasharray: "3 3",
  stroke: "currentColor",
  strokeOpacity: 0.15,
  vertical: false,
} as const;

export const TOOLTIP_PROPS = {
  contentStyle: {
    background: "hsl(var(--popover))",
    border: "1px solid hsl(var(--border))",
    borderRadius: 6,
    fontSize: 12,
    color: "hsl(var(--popover-foreground))",
  },
  cursor: { fill: "currentColor", fillOpacity: 0.06 },
} as const;
