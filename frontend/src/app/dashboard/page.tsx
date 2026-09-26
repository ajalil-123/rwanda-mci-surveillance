"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { ArrowSquareOut, Bandaids, Funnel, MapPin, Skull } from "@phosphor-icons/react";
import { api, errorText, type Incident, type SourceTier } from "@/lib/api";
import { cleanTitle, formatDate, formatIncidentType, formatNumber, incidentDate, isKnownDistrict } from "@/lib/format";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { StatCard } from "@/components/stat-card";
import { TierBadge } from "@/components/tier-badge";
import { Card } from "@/components/ui/card";
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

/** Must match MCI_THRESHOLD in backend/analytics.py. */
const MCI_THRESHOLD = 3;

const DEATH_FILTERS = [
  { value: 1, label: "1+ (any fatality)" },
  { value: MCI_THRESHOLD, label: `${MCI_THRESHOLD}+ (MCI threshold)` },
  { value: 5, label: "5+" },
  { value: 10, label: "10+" },
  { value: 25, label: "25+" },
  { value: 50, label: "50+ (major)" },
] as const;

const TIERS: readonly SourceTier[] = [1, 2, 3];

/**
 * MCI Classification — the default dashboard view.
 *
 * Shows incidents at or above the chosen death threshold (default: the national
 * MCI threshold). MCI vs non-MCI comparison and hotspots live under Analytics.
 */
export default function MciClassificationPage() {
  const [minDeaths, setMinDeaths] = useState<number>(MCI_THRESHOLD);
  const [tiers, setTiers] = useState<ReadonlySet<SourceTier>>(() => new Set(TIERS));

  const { data, isLoading, error } = useSWR("data-all", api.dataAll);

  const incidents = useMemo(
    () =>
      (data ?? [])
        .filter((i) => i.deaths >= minDeaths && tiers.has(i.source_tier ?? 3))
        // Latest first
        .sort((a, b) => incidentDate(b).localeCompare(incidentDate(a))),
    [data, minDeaths, tiers]
  );

  const summary = useMemo(() => {
    let deaths = 0;
    let injured = 0;
    const districts = new Set<string>();
    for (const i of incidents) {
      deaths += i.deaths;
      injured += i.injured;
      if (isKnownDistrict(i.district)) districts.add(i.district);
    }
    return { count: incidents.length, deaths, injured, districts: districts.size };
  }, [incidents]);

  function toggleTier(tier: SourceTier) {
    setTiers((prev) => {
      const next = new Set(prev);
      if (next.has(tier)) next.delete(tier);
      else next.add(tier);
      // Never allow an empty selection — it would silently hide everything
      return next.size > 0 ? next : prev;
    });
  }

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <PageHeader
        title="MCI Classification"
        description="Mass Casualty Incidents confirmed by media surveillance, filtered by death threshold and source credibility tier."
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard loading={isLoading} label="Matching incidents" value={summary.count} />
        <StatCard loading={isLoading} label="Total deaths" value={summary.deaths} accent="destructive" icon={<Skull size={16} weight="fill" />} />
        <StatCard loading={isLoading} label="Total injured" value={summary.injured} accent="warning" icon={<Bandaids size={16} weight="fill" />} />
        <StatCard loading={isLoading} label="Districts affected" value={summary.districts} accent="muted" icon={<MapPin size={16} weight="fill" />} />
      </div>

      <Card className="flex flex-wrap items-center gap-4 p-4">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Funnel size={16} className="text-muted-foreground" aria-hidden />
          Filters
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground" id="min-deaths-label">
            Deaths ≥
          </span>
          <Select value={String(minDeaths)} onValueChange={(v) => setMinDeaths(Number(v))}>
            <SelectTrigger className="w-44" aria-labelledby="min-deaths-label">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DEATH_FILTERS.map((f) => (
                <SelectItem key={f.value} value={String(f.value)}>
                  {f.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2" role="group" aria-label="Source tier">
          <span className="text-xs text-muted-foreground">Source tier:</span>
          {TIERS.map((t) => {
            const active = tiers.has(t);
            return (
              <button
                key={t}
                type="button"
                aria-pressed={active}
                onClick={() => toggleTier(t)}
                className={cn(
                  "rounded-md border px-2 py-1 text-xs font-medium transition-colors",
                  active ? "border-primary bg-primary/10" : "border-border text-muted-foreground hover:text-foreground"
                )}
              >
                T{t}
              </button>
            );
          })}
        </div>

        <div className="ml-auto text-xs text-muted-foreground">
          Showing <span className="font-medium text-foreground">{formatNumber(incidents.length)}</span> incidents
        </div>
      </Card>

      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Incident</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Location</TableHead>
              <TableHead className="text-right">Deaths</TableHead>
              <TableHead className="text-right">Injured</TableHead>
              <TableHead>Source</TableHead>
              <TableHead className="text-center">Tier</TableHead>
              <TableHead>
                <span className="sr-only">Link</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? <TableMessage colSpan={9}>Loading…</TableMessage> : null}
            {error ? (
              <TableMessage colSpan={9} tone="error">
                {errorText(error)}
              </TableMessage>
            ) : null}
            {data && incidents.length === 0 ? (
              <TableMessage colSpan={9}>No incidents match the current filter.</TableMessage>
            ) : null}
            {incidents.map((i) => (
              <MciRow key={i.id} inc={i} />
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

function MciRow({ inc }: { inc: Incident }) {
  return (
    <TableRow>
      <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
        {formatDate(incidentDate(inc))}
      </TableCell>
      <TableCell className="min-w-[280px] max-w-xl whitespace-normal font-medium leading-snug">
        {cleanTitle(inc.title, inc.source_name)}
      </TableCell>
      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
        {formatIncidentType(inc.incident_type)}
      </TableCell>
      <TableCell className="whitespace-nowrap text-xs">
        {isKnownDistrict(inc.district) ? inc.district : <span className="text-muted-foreground">N/A</span>}
      </TableCell>
      <TableCell className="text-right font-mono font-semibold tabular-nums text-destructive">
        {formatNumber(inc.deaths)}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums text-amber-600">
        {formatNumber(inc.injured)}
      </TableCell>
      <TableCell className="max-w-[160px] truncate text-xs text-muted-foreground" title={inc.source_name ?? ""}>
        {inc.source_name || "N/A"}
      </TableCell>
      <TableCell className="text-center">
        <TierBadge tier={inc.source_tier} />
      </TableCell>
      <TableCell>
        {inc.source_url ? (
          <a
            href={inc.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex text-muted-foreground hover:text-foreground"
            aria-label={`Open source article: ${inc.title}`}
          >
            <ArrowSquareOut size={14} />
          </a>
        ) : null}
      </TableCell>
    </TableRow>
  );
}
