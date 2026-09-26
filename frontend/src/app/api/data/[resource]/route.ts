import { NextResponse, type NextRequest } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import * as q from "@/server/queries";

/** Integer query param, clamped to [min, max]; falls back when missing or invalid. */
function intParam(params: URLSearchParams, name: string, fallback: number, min: number, max: number): number {
  const n = Number.parseInt(params.get(name) ?? "", 10);
  return Number.isNaN(n) ? fallback : Math.min(max, Math.max(min, n));
}

const RESOURCES: Record<string, (params: URLSearchParams) => Promise<unknown>> = {
  incidents: () => q.allIncidents(),
  map: (p) => q.mapIncidents(intParam(p, "min_deaths", 0, 0, 10_000)),
  hotspots: () => q.hotspots(),
  "mci-hotspots": () => q.mciHotspots(),
  "mci-stats": () => q.mciStats(),
  monthly: (p) => q.monthlyTrend(intParam(p, "years", 5, 1, 20)),
  seasonal: () => q.seasonalPattern(),
  heatmap: () => q.monthlyHeatmap(),
  cfr: () => q.caseFatalityRate(),
  yoy: () => q.yearOverYear(),
  "peak-months": () => q.peakMonths(),
  "source-tiers": () => q.sourceTiers(),
};

export async function GET(request: NextRequest, { params }: { params: Promise<{ resource: string }> }) {
  // The proxy only guards pages, so API routes check the session themselves
  if (!(await getServerSession(authOptions))) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { resource } = await params;
  const handler = Object.hasOwn(RESOURCES, resource) ? RESOURCES[resource] : undefined;
  if (!handler) return NextResponse.json({ error: "Not found" }, { status: 404 });

  try {
    const data = await handler(request.nextUrl.searchParams);
    return NextResponse.json(data, { headers: { "Cache-Control": "private, max-age=60" } });
  } catch (error) {
    console.error(`GET /api/data/${resource} failed`, error);
    return NextResponse.json({ error: "Database query failed" }, { status: 500 });
  }
}
