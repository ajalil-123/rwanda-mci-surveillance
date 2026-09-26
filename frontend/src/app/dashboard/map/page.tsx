"use client";

import { useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import useSWR from "swr";
import { api, errorText } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { SEVERITY_LEVELS, SEVERITY_ORDER } from "@/lib/severity";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const IncidentMap = dynamic(() => import("@/components/incident-map"), {
  ssr: false,
  loading: () => <MapMessage>Loading map…</MapMessage>,
});

const DEATH_FILTERS = [
  { value: 0, label: "All incidents" },
  { value: 1, label: "1+ deaths" },
  { value: 3, label: "3+ deaths (MCI)" },
  { value: 10, label: "10+ deaths" },
] as const;

function MapMessage({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "error" }) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex h-full items-center justify-center text-sm",
        tone === "error" ? "text-destructive" : "text-muted-foreground"
      )}
    >
      {children}
    </div>
  );
}

export default function MapPage() {
  const [minDeaths, setMinDeaths] = useState(0);
  // keepPreviousData: changing the filter must not unmount the map (keeps zoom/pan)
  const { data, error, isLoading } = useSWR(["map", minDeaths], () => api.incidentsMap(minDeaths), {
    keepPreviousData: true,
  });

  return (
    <div className="flex h-full flex-col gap-4 p-6 lg:p-8">
      <PageHeader
        title="Incident Map"
        description="Geo-tagged incidents across Rwanda. Circle size reflects deaths; colour reflects severity."
        actions={
          <Select value={String(minDeaths)} onValueChange={(v) => setMinDeaths(Number(v))}>
            <SelectTrigger className="w-44" aria-label="Minimum deaths">
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
        }
      />

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
        <span>
          Showing <span className="font-medium text-foreground">{formatNumber(data?.length ?? 0)}</span> mapped
          incidents
        </span>
        <span aria-hidden>·</span>
        {SEVERITY_ORDER.map((lvl) => (
          <span key={lvl} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: SEVERITY_LEVELS[lvl].color }}
            />
            {SEVERITY_LEVELS[lvl].label}
          </span>
        ))}
      </div>

      {/* isolate keeps Leaflet's high z-index panes below the Select popover */}
      <div className="isolate min-h-[480px] flex-1 overflow-hidden rounded-lg border border-border bg-muted/30">
        {error ? (
          <MapMessage tone="error">{errorText(error)}</MapMessage>
        ) : isLoading ? (
          <MapMessage>Loading incidents…</MapMessage>
        ) : (
          <IncidentMap incidents={data ?? []} />
        )}
      </div>
    </div>
  );
}
