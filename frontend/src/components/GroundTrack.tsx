import { useMemo } from "react";

import type { GroundTrackSample, Station } from "../api/types";

interface Props {
  track: GroundTrackSample[];
  station: Station | null;
  /** Highlighted segment, e.g. the selected pass. */
  highlight?: GroundTrackSample[];
}

const W = 720;
const H = 360;

/**
 * Ground track on an equirectangular grid.
 *
 * No globe and no basemap: a 3D globe needs a tile provider and an access
 * token, which would make the project depend on a third-party service to draw
 * a picture. A graticule with the track on it answers the same question --
 * where does this orbit go, and does it come over my station -- and it works
 * offline, which is the standard the rest of Culmen holds itself to.
 *
 * The one thing that must not be got wrong here is the antimeridian: longitude
 * wraps from +180 to -180 and a naive polyline draws a horizontal streak
 * across the whole map. The path is split wherever consecutive samples jump
 * more than 180 degrees.
 */
export function GroundTrack({ track, station, highlight }: Props) {
  const toXY = (lat: number, lon: number) => ({
    x: ((lon + 180) / 360) * W,
    y: ((90 - lat) / 180) * H,
  });

  const segments = useMemo(() => splitAtAntimeridian(track, toXY), [track]);
  const hotSegments = useMemo(
    () => (highlight ? splitAtAntimeridian(highlight, toXY) : []),
    [highlight],
  );

  const stationXY = station ? toXY(station.lat_deg, station.lon_deg) : null;

  return (
    <div className="chart">
      <div className="chart-title">
        Ground track — equirectangular, {track.length} samples
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Sub-satellite ground track on a world grid"
      >
        <rect width={W} height={H} fill="var(--surface-2)" rx={6} />

        <g className="grid">
          {[-60, -30, 0, 30, 60].map((lat) => {
            const y = toXY(lat, 0).y;
            return (
              <g key={lat}>
                <line
                  x1={0}
                  x2={W}
                  y1={y}
                  y2={y}
                  stroke={lat === 0 ? "var(--border)" : "var(--surface-3)"}
                  strokeWidth={lat === 0 ? 1.5 : 1}
                />
                <text
                  x={4}
                  y={y - 3}
                  fontSize={9}
                  fill="var(--text-muted)"
                  fontFamily="var(--mono)"
                >
                  {lat}°
                </text>
              </g>
            );
          })}
          {[-120, -60, 0, 60, 120].map((lon) => {
            const x = toXY(0, lon).x;
            return (
              <line
                key={lon}
                x1={x}
                x2={x}
                y1={0}
                y2={H}
                stroke={lon === 0 ? "var(--border)" : "var(--surface-3)"}
                strokeWidth={lon === 0 ? 1.5 : 1}
              />
            );
          })}
        </g>

        {segments.map((d, i) => (
          <path
            key={`t${i}`}
            d={d}
            fill="none"
            stroke="var(--text-muted)"
            strokeWidth={1.5}
          />
        ))}

        {hotSegments.map((d, i) => (
          <path
            key={`h${i}`}
            d={d}
            fill="none"
            stroke="var(--series-1)"
            strokeWidth={2.5}
            strokeLinecap="round"
          />
        ))}

        {stationXY ? (
          <g>
            <circle
              cx={stationXY.x}
              cy={stationXY.y}
              r={5}
              fill="var(--series-2)"
              stroke="var(--surface-2)"
              strokeWidth={2}
            />
            <text
              x={stationXY.x + 9}
              y={stationXY.y + 4}
              fontSize={11}
              fill="var(--text-primary)"
            >
              {station?.name}
            </text>
          </g>
        ) : null}
      </svg>

      <div className="legend">
        <span>
          <span className="swatch" style={{ background: "var(--text-muted)" }} />
          orbit
        </span>
        <span>
          <span className="swatch" style={{ background: "var(--series-1)" }} />
          selected pass
        </span>
        <span>
          <span
            className="swatch"
            style={{ background: "var(--series-2)", height: 8, width: 8, borderRadius: 4 }}
          />
          station
        </span>
      </div>
    </div>
  );
}

function splitAtAntimeridian(
  samples: GroundTrackSample[],
  toXY: (lat: number, lon: number) => { x: number; y: number },
): string[] {
  const out: string[] = [];
  let current: string[] = [];

  samples.forEach((s, i) => {
    const previous = samples[i - 1];
    const wrapped = previous !== undefined && Math.abs(s.lon_deg - previous.lon_deg) > 180;
    if (wrapped && current.length > 1) {
      out.push(current.join(" "));
      current = [];
    }
    const p = toXY(s.lat_deg, s.lon_deg);
    current.push(`${current.length === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`);
  });

  if (current.length > 1) out.push(current.join(" "));
  return out;
}
