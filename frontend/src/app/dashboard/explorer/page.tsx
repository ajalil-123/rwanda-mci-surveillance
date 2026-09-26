"use client";

import { useDeferredValue, useMemo, useState } from "react";
import useSWR from "swr";
import { format } from "date-fns";
import { ArrowSquareOut, CaretDown, CaretUp, DownloadSimple, MagnifyingGlass } from "@phosphor-icons/react";
import { api, type Incident } from "@/lib/api";
import { toCsv, downloadCsv } from "@/lib/csv";
import { formatDate, formatIncidentType, formatNumber, incidentDate, isKnownDistrict } from "@/lib/format";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { SeverityDot } from "@/components/severity-dot";
import { TierBadge } from "@/components/tier-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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

const PAGE_SIZE = 50;
const ALL = "all";

type SortKey = "date" | "title" | "incident_type" | "district" | "deaths" | "injured" | "severity";
type SortDir = "asc" | "desc";

const CSV_COLUMNS = [
  "id",
  "event_date",
  "detected_at",
  "title",
  "incident_type",
  "district",
  "province",
  "latitude",
  "longitude",
  "deaths",
  "injured",
  "missing",
  "severity",
  "source_name",
  "source_url",
  "source_tier",
  "status",
] as const satisfies readonly (keyof Incident)[];

function sortValue(i: Incident, key: SortKey): string | number {
  switch (key) {
    case "date":
      return incidentDate(i);
    case "deaths":
    case "injured":
    case "severity":
      return i[key] ?? 0;
    default:
      return (i[key] ?? "").toLowerCase();
  }
}

function uniqueSorted(values: (string | null)[]): string[] {
  return [...new Set(values.filter((v): v is string => Boolean(v)))].sort();
}

export default function ExplorerPage() {
  const { data, error, isLoading } = useSWR("data-all", api.dataAll);

  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [type, setType] = useState(ALL);
  const [province, setProvince] = useState(ALL);
  const [year, setYear] = useState(ALL);
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: "date", dir: "desc" });
  const [page, setPage] = useState(0);

  const options = useMemo(() => {
    const rows = data ?? [];
    return {
      types: uniqueSorted(rows.map((r) => r.incident_type)),
      provinces: uniqueSorted(rows.map((r) => r.province)),
      years: uniqueSorted(rows.map((r) => incidentDate(r).slice(0, 4))).reverse(),
    };
  }, [data]);

  const filtered = useMemo(() => {
    const q = deferredSearch.trim().toLowerCase();
    const rows = (data ?? []).filter((r) => {
      if (type !== ALL && r.incident_type !== type) return false;
      if (province !== ALL && r.province !== province) return false;
      if (year !== ALL && !incidentDate(r).startsWith(year)) return false;
      if (!q) return true;
      return [r.title, r.district, r.province, r.incident_type, r.source_name].some((v) =>
        v?.toLowerCase().includes(q)
      );
    });
    const factor = sort.dir === "asc" ? 1 : -1;
    return rows.sort((a, b) => {
      const va = sortValue(a, sort.key);
      const vb = sortValue(b, sort.key);
      return (va < vb ? -1 : va > vb ? 1 : 0) * factor;
    });
  }, [data, deferredSearch, type, province, year, sort]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pageRows = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  // Any filter change returns to the first page
  function withReset<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setPage(0);
    };
  }

  function toggleSort(key: SortKey) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }));
    setPage(0);
  }

  function exportCsv() {
    downloadCsv(`rwanda_mci_${format(new Date(), "yyyyMMdd")}.csv`, toCsv(filtered, CSV_COLUMNS));
  }

  const hasFilters = search !== "" || type !== ALL || province !== ALL || year !== ALL;

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <PageHeader
        title="Data Explorer"
        description="All recorded incidents. Search, filter and sort, then export exactly what you see to CSV."
        actions={
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={filtered.length === 0}>
            <DownloadSimple size={16} />
            Export CSV ({formatNumber(filtered.length)})
          </Button>
        }
      />

      <Card className="flex flex-wrap items-center gap-3 p-4">
        <div className="relative min-w-[220px] flex-1">
          <MagnifyingGlass
            size={14}
            aria-hidden
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            value={search}
            onChange={(e) => withReset(setSearch)(e.target.value)}
            placeholder="Search title, district, source…"
            aria-label="Search incidents"
            className="pl-8"
          />
        </div>
        <FilterSelect label="Incident type" value={type} onChange={withReset(setType)} options={options.types} format={formatIncidentType} />
        <FilterSelect label="Province" value={province} onChange={withReset(setProvince)} options={options.provinces} />
        <FilterSelect label="Year" value={year} onChange={withReset(setYear)} options={options.years} />
        {hasFilters ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSearch("");
              setType(ALL);
              setProvince(ALL);
              setYear(ALL);
              setPage(0);
            }}
          >
            Clear
          </Button>
        ) : null}
      </Card>

      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <SortableHead label="Date" sortKey="date" sort={sort} onSort={toggleSort} />
              <SortableHead label="Incident" sortKey="title" sort={sort} onSort={toggleSort} />
              <SortableHead label="Type" sortKey="incident_type" sort={sort} onSort={toggleSort} />
              <SortableHead label="Location" sortKey="district" sort={sort} onSort={toggleSort} />
              <SortableHead label="Deaths" sortKey="deaths" sort={sort} onSort={toggleSort} align="right" />
              <SortableHead label="Injured" sortKey="injured" sort={sort} onSort={toggleSort} align="right" />
              <SortableHead label="Severity" sortKey="severity" sort={sort} onSort={toggleSort} align="center" />
              <TableHead>Source</TableHead>
              <TableHead className="text-center">Tier</TableHead>
              <TableHead>
                <span className="sr-only">Link</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {error ? (
              <TableMessage colSpan={10} tone="error">
                Failed to load. The backend may be starting up.
              </TableMessage>
            ) : null}
            {isLoading ? <TableMessage colSpan={10}>Loading…</TableMessage> : null}
            {data && filtered.length === 0 ? (
              <TableMessage colSpan={10}>No incidents match the current filters.</TableMessage>
            ) : null}
            {pageRows.map((i) => (
              <TableRow key={i.id}>
                <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                  {formatDate(incidentDate(i))}
                </TableCell>
                <TableCell className="max-w-md">
                  <div className="line-clamp-2">{i.title}</div>
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs capitalize text-muted-foreground">
                  {formatIncidentType(i.incident_type)}
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs">
                  {isKnownDistrict(i.district) ? i.district : <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell className="text-right font-mono font-semibold tabular-nums text-destructive">
                  {formatNumber(i.deaths)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums text-amber-600">
                  {i.injured ? formatNumber(i.injured) : "—"}
                </TableCell>
                <TableCell className="text-center">
                  <SeverityDot level={i.severity} />
                </TableCell>
                <TableCell className="max-w-[160px] truncate text-xs text-muted-foreground" title={i.source_name ?? ""}>
                  {i.source_name || "—"}
                </TableCell>
                <TableCell className="text-center">
                  <TierBadge tier={i.source_tier} />
                </TableCell>
                <TableCell>
                  {i.source_url ? (
                    <a
                      href={i.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex text-muted-foreground hover:text-foreground"
                      aria-label={`Open source article: ${i.title}`}
                    >
                      <ArrowSquareOut size={14} />
                    </a>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {filtered.length > PAGE_SIZE ? (
          <div className="flex items-center justify-between border-t border-border px-4 py-3 text-xs text-muted-foreground">
            <span>
              {formatNumber(currentPage * PAGE_SIZE + 1)}–
              {formatNumber(Math.min((currentPage + 1) * PAGE_SIZE, filtered.length))} of{" "}
              {formatNumber(filtered.length)}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage(currentPage - 1)} disabled={currentPage === 0}>
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(currentPage + 1)}
                disabled={currentPage >= pageCount - 1}
              >
                Next
              </Button>
            </div>
          </div>
        ) : null}
      </Card>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  format: formatOption = (v: string) => v,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  format?: (v: string) => string;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-40 capitalize" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>All {label.toLowerCase()}s</SelectItem>
        {options.map((o) => (
          <SelectItem key={o} value={o} className="capitalize">
            {formatOption(o)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function SortableHead({
  label,
  sortKey,
  sort,
  onSort,
  align = "left",
}: {
  label: string;
  sortKey: SortKey;
  sort: { key: SortKey; dir: SortDir };
  onSort: (key: SortKey) => void;
  align?: "left" | "right" | "center";
}) {
  const active = sort.key === sortKey;
  const Icon = active && sort.dir === "asc" ? CaretUp : CaretDown;
  return (
    <TableHead
      aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
      className={cn(align === "right" && "text-right", align === "center" && "text-center")}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          "inline-flex items-center gap-1 uppercase tracking-wider hover:text-foreground",
          active && "text-foreground"
        )}
      >
        {label}
        <Icon size={10} weight="bold" aria-hidden className={active ? "opacity-100" : "opacity-30"} />
      </button>
    </TableHead>
  );
}
