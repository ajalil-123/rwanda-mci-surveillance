"use client";

import { useState } from "react";
import useSWR from "swr";
import { Warning } from "@phosphor-icons/react";
import { api, errorText, type Hotspot, type MciHotspot } from "@/lib/api";
import { cleanTitle, formatDate, formatIncidentType, formatNumber } from "@/lib/format";
import { PageHeader, DataState } from "@/components/page-header";
import { TierBadge } from "@/components/tier-badge";
import { BarChart, SERIES_COLORS } from "@/components/charts";
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

type HotspotScope = "all" | "mci";

export default function AnalyticsPage() {
  return (
    <div className="space-y-6 p-6 lg:p-8">
      <PageHeader
        title="Analytics"
        description="MCI vs non-MCI comparison, district hotspots, lethality by incident type and source credibility."
      />
      <MciComparison />
      <Hotspots />
      <div className="grid gap-6 xl:grid-cols-2">
        <CaseFatality />
        <SourceTiers />
      </div>
    </div>
  );
}

function MciComparison() {
  const { data, error, isLoading } = useSWR("mci-stats", api.mciStats);

  const rows = data
    ? ([
        ["Incidents", data.mci.count, data.non_mci.count],
        ["Share of all incidents", `${data.mci.pct}%`, `${data.non_mci.pct}%`],
        ["Deaths", data.mci.deaths, data.non_mci.deaths],
        ["Injured", data.mci.injured, data.non_mci.injured],
      ] as const)
    : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>MCI vs Non-MCI</CardTitle>
        <CardDescription>
          {data
            ? `An incident is classified as an MCI when it records ${data.threshold} or more deaths.`
            : "Split of verified incidents by the MCI death threshold."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Metric</TableHead>
              <TableHead className="text-right">MCI</TableHead>
              <TableHead className="text-right">Non-MCI</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {error ? <TableMessage colSpan={3} tone="error">{errorText(error)}</TableMessage> : null}
            {isLoading ? <TableMessage colSpan={3}>Loading…</TableMessage> : null}
            {rows.map(([label, mci, nonMci]) => (
              <TableRow key={label}>
                <TableCell className="font-medium">{label}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {typeof mci === "number" ? formatNumber(mci) : mci}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                  {typeof nonMci === "number" ? formatNumber(nonMci) : nonMci}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {data?.worst_mci ? (
          <div className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
            <Warning size={18} weight="fill" className="mt-0.5 shrink-0 text-destructive" />
            <div>
              <div className="font-medium">Deadliest recorded MCI: {cleanTitle(data.worst_mci.title)}</div>
              <div className="text-xs text-muted-foreground">
                {formatDate(data.worst_mci.event_date)} · {data.worst_mci.district || "Unknown district"} ·{" "}
                <span>{formatIncidentType(data.worst_mci.incident_type)}</span> ·{" "}
                <span className="font-semibold text-destructive">{formatNumber(data.worst_mci.deaths)} deaths</span>
              </div>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Hotspots() {
  const [scope, setScope] = useState<HotspotScope>("mci");
  const all = useSWR(scope === "all" ? "hotspots" : null, api.hotspots);
  const mci = useSWR(scope === "mci" ? "mci-hotspots" : null, api.mciHotspots);
  const { data, error, isLoading } = scope === "all" ? all : mci;

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-4">
        <div className="space-y-1.5">
          <CardTitle>Hotspots by district</CardTitle>
          <CardDescription>
            {scope === "all"
              ? "Ranked by risk score = incidents + 2 × deaths + 1.5 × average severity."
              : "Districts ranked by total deaths from MCI events (top 20)."}
          </CardDescription>
        </div>
        <Select value={scope} onValueChange={(v) => setScope(v as HotspotScope)}>
          <SelectTrigger className="w-44" aria-label="Hotspot scope">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="mci">MCI events only</SelectItem>
            <SelectItem value="all">All incidents</SelectItem>
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">#</TableHead>
              <TableHead>District</TableHead>
              <TableHead>Province</TableHead>
              <TableHead className="text-right">Incidents</TableHead>
              <TableHead className="text-right">Deaths</TableHead>
              <TableHead className="text-right">Injured</TableHead>
              <TableHead className="text-right">{scope === "all" ? "Risk score" : "Max deaths"}</TableHead>
              <TableHead>Incident types</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {error ? <TableMessage colSpan={8} tone="error">{errorText(error)}</TableMessage> : null}
            {isLoading ? <TableMessage colSpan={8}>Loading…</TableMessage> : null}
            {data && data.length === 0 ? <TableMessage colSpan={8}>No district data yet.</TableMessage> : null}
            {data?.map((h: Hotspot | MciHotspot, idx) => (
              <TableRow key={h.district}>
                <TableCell className="font-mono text-xs text-muted-foreground">{idx + 1}</TableCell>
                <TableCell className="font-medium">{h.district}</TableCell>
                <TableCell className="text-muted-foreground">{h.province || "—"}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{formatNumber(h.incident_count)}</TableCell>
                <TableCell className="text-right font-mono font-semibold tabular-nums text-destructive">
                  {formatNumber(h.total_deaths)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums text-amber-600">
                  {formatNumber(h.total_injured)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {"risk_score" in h ? h.risk_score.toFixed(1) : formatNumber(h.max_deaths)}
                </TableCell>
                <TableCell className="max-w-xs truncate text-xs text-muted-foreground" title={h.types ?? ""}>
                  {h.types ? h.types.split(",").map(formatIncidentType).join(", ") : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function CaseFatality() {
  const { data, error, isLoading } = useSWR("cfr", api.cfr);
  const chartData = (data ?? []).map((r) => ({
    type: formatIncidentType(r.incident_type),
    cfr: r.case_fatality_rate,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Case fatality rate by type</CardTitle>
        <CardDescription>Deaths ÷ (deaths + injured) — how lethal each incident type is.</CardDescription>
      </CardHeader>
      <CardContent>
        <DataState isLoading={isLoading} error={error} isEmpty={chartData.length === 0} height={320}>
          <BarChart
            data={chartData}
            categoryKey="type"
            series={[{ key: "cfr", label: "CFR", color: SERIES_COLORS.deaths }]}
            horizontal
            height={Math.max(220, chartData.length * 32)}
            valueFormatter={(v) => `${v}%`}
          />
        </DataState>
      </CardContent>
    </Card>
  );
}

function SourceTiers() {
  const { data, error, isLoading } = useSWR("source-tiers", api.sourceTiers);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Source credibility tiers</CardTitle>
        <CardDescription>Incidents and deaths attributed to each source tier.</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tier</TableHead>
              <TableHead className="text-right">Sources</TableHead>
              <TableHead className="text-right">Incidents</TableHead>
              <TableHead className="text-right">Deaths</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {error ? <TableMessage colSpan={4} tone="error">{errorText(error)}</TableMessage> : null}
            {isLoading ? <TableMessage colSpan={4}>Loading…</TableMessage> : null}
            {data?.map((t) => (
              <TableRow key={t.tier}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <TierBadge tier={t.tier} size="md" />
                    <div>
                      <div className="font-medium">{t.label}</div>
                      <div className="text-xs text-muted-foreground">{t.credibility}</div>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">{formatNumber(t.unique_sources)}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{formatNumber(t.incidents)}</TableCell>
                <TableCell className="text-right font-mono tabular-nums text-destructive">
                  {formatNumber(t.deaths)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
