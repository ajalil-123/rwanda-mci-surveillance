"use client";

import { useState } from "react";
import useSWR from "swr";
import { ArrowDownRight, ArrowUpRight } from "@phosphor-icons/react";
import { api, errorText } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { PageHeader, DataState } from "@/components/page-header";
import { StatCard } from "@/components/stat-card";
import { BarChart, Heatmap, LineChart, SERIES_COLORS } from "@/components/charts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableMessage,
  TableRow,
} from "@/components/ui/table";

export default function TrendsPage() {
  return (
    <div className="space-y-6 p-6 lg:p-8">
      <PageHeader
        title="Trends"
        description="When incidents happen: calendar heatmap, seasonal pattern, monthly trend and year-over-year change."
      />
      <PeakSummary />
      <HeatmapCard />
      <MonthlyTrend />
      <div className="grid gap-6 xl:grid-cols-2">
        <Seasonal />
        <YearOverYear />
      </div>
    </div>
  );
}

function PeakSummary() {
  const { data, isLoading } = useSWR("peak-months", api.peakMonths);
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <StatCard loading={isLoading} label="Peak month" value={data?.peak_month ?? "N/A"} hint={data?.peak_month_avg_inc != null ? `${data.peak_month_avg_inc} incidents / yr avg` : undefined} />
      <StatCard loading={isLoading} label="Quietest month" value={data?.low_month ?? "N/A"} accent="muted" />
      <StatCard
        loading={isLoading}
        label="Rainy vs dry season"
        value={data?.rainy_vs_dry_ratio != null ? `${data.rainy_vs_dry_ratio}×` : "N/A"}
        accent="warning"
        hint="Incident rate ratio"
      />
      <StatCard
        loading={isLoading}
        label="Deadliest year"
        value={data?.worst_year ?? "N/A"}
        accent="destructive"
        hint={data?.worst_year_deaths != null ? `${formatNumber(data.worst_year_deaths)} deaths` : undefined}
      />
    </div>
  );
}

function HeatmapCard() {
  const [metric, setMetric] = useState<"incidents" | "deaths">("incidents");
  const { data, error, isLoading } = useSWR("heatmap", api.heatmap);

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-4">
        <div className="space-y-1.5">
          <CardTitle>Monthly heatmap</CardTitle>
          <CardDescription>Each cell is one month. Darker cells mean more {metric}.</CardDescription>
        </div>
        <Select value={metric} onValueChange={(v) => setMetric(v as "incidents" | "deaths")}>
          <SelectTrigger className="w-36" aria-label="Heatmap metric">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="incidents">Incidents</SelectItem>
            <SelectItem value="deaths">Deaths</SelectItem>
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent>
        <DataState isLoading={isLoading} error={error} isEmpty={data?.length === 0} height={240}>
          <Heatmap cells={data ?? []} metric={metric} />
        </DataState>
      </CardContent>
    </Card>
  );
}

const YEAR_RANGES = [1, 3, 5, 10] as const;

function MonthlyTrend() {
  const [years, setYears] = useState<number>(5);
  const { data, error, isLoading } = useSWR(["monthly", years], () => api.monthly(years));

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-4">
        <div className="space-y-1.5">
          <CardTitle>Monthly trend</CardTitle>
          <CardDescription>Incidents and deaths per month, with a 3-month rolling average of deaths.</CardDescription>
        </div>
        <Select value={String(years)} onValueChange={(v) => setYears(Number(v))}>
          <SelectTrigger className="w-36" aria-label="Time range">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {YEAR_RANGES.map((y) => (
              <SelectItem key={y} value={String(y)}>
                Last {y} {y === 1 ? "year" : "years"}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent>
        <DataState isLoading={isLoading} error={error} isEmpty={data?.length === 0} height={300}>
          <LineChart
            data={data ?? []}
            categoryKey="month"
            height={300}
            series={[
              { key: "incidents", label: "Incidents", color: SERIES_COLORS.incidents },
              { key: "deaths", label: "Deaths", color: SERIES_COLORS.deaths },
              { key: "deaths_3m_avg", label: "Deaths (3-mo avg)", color: SERIES_COLORS.neutral },
            ]}
          />
        </DataState>
      </CardContent>
    </Card>
  );
}

function Seasonal() {
  const { data, error, isLoading } = useSWR("seasonal", api.seasonal);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Seasonal pattern</CardTitle>
        <CardDescription>Average incidents and deaths per calendar month across all years.</CardDescription>
      </CardHeader>
      <CardContent>
        <DataState isLoading={isLoading} error={error} isEmpty={data?.length === 0}>
          <BarChart
            data={data ?? []}
            categoryKey="month_name"
            series={[
              { key: "avg_incidents", label: "Avg incidents", color: SERIES_COLORS.incidents },
              { key: "avg_deaths", label: "Avg deaths", color: SERIES_COLORS.deaths },
            ]}
          />
        </DataState>
      </CardContent>
    </Card>
  );
}

function PctChange({ value }: { value: number | null }) {
  if (value == null) return <span className="text-muted-foreground">N/A</span>;
  // More incidents/deaths is bad, so increases are shown in red
  const up = value > 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={cn("inline-flex items-center gap-0.5", up ? "text-destructive" : "text-green-600")}>
      <Icon size={12} weight="bold" aria-hidden />
      {Math.abs(value)}%
    </span>
  );
}

function YearOverYear() {
  const { data, error, isLoading } = useSWR("yoy", api.yoy);
  const rows = data ? [...data].reverse() : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Year over year</CardTitle>
        <CardDescription>Change against the previous year. Red means an increase.</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Year</TableHead>
              <TableHead className="text-right">Incidents</TableHead>
              <TableHead className="text-right">Δ</TableHead>
              <TableHead className="text-right">Deaths</TableHead>
              <TableHead className="text-right">Δ</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {error ? <TableMessage colSpan={5} tone="error">{errorText(error)}</TableMessage> : null}
            {isLoading ? <TableMessage colSpan={5}>Loading…</TableMessage> : null}
            {rows.map((r) => (
              <TableRow key={r.year}>
                <TableCell className="font-mono font-medium">{r.year}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{formatNumber(r.incidents)}</TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  <PctChange value={r.inc_pct_change} />
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">{formatNumber(r.deaths)}</TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  <PctChange value={r.dth_pct_change} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
