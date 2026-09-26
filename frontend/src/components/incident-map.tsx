"use client";

import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import type { MapIncident } from "@/lib/api";
import { cleanTitle, formatDate, formatIncidentType, formatNumber, incidentDate } from "@/lib/format";
import { SEVERITY_LEVELS, clampSeverity } from "@/lib/severity";
import { TierBadge } from "@/components/tier-badge";

const RWANDA_CENTER: [number, number] = [-1.94, 29.87];
const RWANDA_BOUNDS: [[number, number], [number, number]] = [
  [-2.95, 28.8],
  [-1.0, 30.95],
];

/** Radius grows with the death toll, sub-linearly so large events don't swamp the map. */
function radiusFor(deaths: number): number {
  return 5 + Math.min(20, Math.sqrt(Math.max(0, deaths)) * 3);
}

/**
 * Leaflet touches `window` on import — always load this through
 * next/dynamic with `ssr: false`.
 */
export default function IncidentMap({ incidents }: { incidents: MapIncident[] }) {
  return (
    <MapContainer
      center={RWANDA_CENTER}
      zoom={8}
      minZoom={7}
      maxBounds={RWANDA_BOUNDS}
      maxBoundsViscosity={0.8}
      scrollWheelZoom
      className="h-full w-full rounded-lg"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {incidents.map((i) => {
        const color = SEVERITY_LEVELS[clampSeverity(i.severity)].color;
        return (
          <CircleMarker
            key={i.id}
            center={[i.latitude, i.longitude]}
            radius={radiusFor(i.deaths)}
            pathOptions={{ color, fillColor: color, fillOpacity: 0.55, weight: 1 }}
          >
            <Popup>
              <div className="max-w-xs space-y-1.5 text-xs">
                <div className="text-sm font-semibold leading-snug">{cleanTitle(i.title, i.source_name)}</div>
                <div className="text-muted-foreground">
                  {formatDate(incidentDate(i))} · {i.district || "Unknown district"}
                  {i.province ? `, ${i.province}` : ""}
                </div>
                <div>{formatIncidentType(i.incident_type)}</div>
                <div className="flex gap-3 font-mono">
                  <span className="font-semibold text-destructive">{formatNumber(i.deaths)} deaths</span>
                  <span className="text-amber-600">{formatNumber(i.injured)} injured</span>
                </div>
                <div className="flex items-center gap-2">
                  <TierBadge tier={i.source_tier} />
                  <span className="text-muted-foreground">{i.source_name || "Unknown source"}</span>
                </div>
                {i.ai_summary ? <p className="border-t pt-1.5 text-muted-foreground">{i.ai_summary}</p> : null}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
