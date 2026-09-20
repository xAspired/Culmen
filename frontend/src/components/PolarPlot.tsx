import { useState } from "react";

import type { TimelineSample } from "../api/types";

interface Props {
  samples: TimelineSample[];
  maskDeg: number;
}

const SIZE = 300;
const C = SIZE / 2;
const R = C - 26;

/**
 * Sky plot: the pass as seen from the station, north up, east right.
 *
 * Radius is 90 - elevation, so the zenith is the centre and the horizon the
 * rim -- the convention every operator already reads. The elevation mask is
 * drawn as a ring, and the part of the track below it is dimmed rather than
 * hidden: a pass clipped silently is a pass an operator cannot reason about.
 */
export function PolarPlot({ samples, maskDeg }: Props) {
  const [hover, setHover] = useState<TimelineSample | null>(null);

  const project = (azDeg: number, elDeg: number) => {
    const r = (R * (90 - Math.max(elDeg, 0))) / 90;
    const a = ((azDeg - 90) * Math.PI) / 180;
    return { x: C + r * Math.cos(a), y: C + r * Math.sin(a) };
  };

  const above = samples.filter((s) => s.el_deg >= maskDeg);
  const trackPath = (list: TimelineSample[]) =>
    list
      .map((s, i) => {
        const p = project(s.az_deg, s.el_deg);
        return `${i === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`;
      })
      .join(" ");

  const first = above[0] ?? samples[0];
  const last = above[above.length - 1] ?? samples[samples.length - 1];
  const peak = samples.reduce(
    (best, s) => (s.el_deg > best.el_deg ? s : best),
    samples[0] as TimelineSample,
  );

  const maskRadius = (R * (90 - maskDeg)) / 90;

  return (
    <div className="chart">
      <div className="chart-title">
        Sky track — north up, east right; radius is 90° − elevation
      </div>
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ maxWidth: SIZE }}
        role="img"
        aria-label="Azimuth and elevation track of the pass"
      >
        {[30, 60].map((el) => (
          <circle
            key={el}
            cx={C}
            cy={C}
            r={(R * (90 - el)) / 90}
            fill="none"
            stroke="var(--surface-3)"
          />
        ))}
        <circle cx={C} cy={C} r={R} fill="none" stroke="var(--border)" />

        {[0, 45, 90, 135, 180, 225, 270, 315].map((az) => {
          const p = project(az, 0);
          return (
            <line key={az} x1={C} y1={C} x2={p.x} y2={p.y} stroke="var(--surface-3)" />
          );
        })}

        {/* the mask: everything outside this ring is unusable */}
        <circle
          cx={C}
          cy={C}
          r={maskRadius}
          fill="none"
          stroke="var(--warning)"
          strokeWidth={1.5}
          strokeDasharray="4 4"
        />
        <text
          x={C}
          y={C - maskRadius - 4}
          textAnchor="middle"
          fontSize={9}
          fill="var(--warning)"
          fontFamily="var(--mono)"
        >
          {`mask ${maskDeg.toFixed(0)}°`}
        </text>

        {(["N", "E", "S", "W"] as const).map((label, i) => {
          const p = project(i * 90, -6);
          return (
            <text
              key={label}
              x={p.x}
              y={p.y + 3}
              textAnchor="middle"
              fontSize={11}
              fill="var(--text-muted)"
            >
              {label}
            </text>
          );
        })}

        {/* whole track, dimmed; then the usable part at full weight */}
        <path
          d={trackPath(samples)}
          fill="none"
          stroke="var(--text-muted)"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
        <path
          d={trackPath(above)}
          fill="none"
          stroke="var(--series-1)"
          strokeWidth={2.5}
          strokeLinecap="round"
        />

        {samples.map((s, i) => {
          const p = project(s.az_deg, s.el_deg);
          return (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={7}
              fill="transparent"
              onMouseEnter={() => setHover(s)}
              onMouseLeave={() => setHover(null)}
            />
          );
        })}

        {first ? <Marker at={project(first.az_deg, first.el_deg)} label="AOS" /> : null}
        {last ? <Marker at={project(last.az_deg, last.el_deg)} label="LOS" /> : null}
        {peak ? (
          <circle
            cx={project(peak.az_deg, peak.el_deg).x}
            cy={project(peak.az_deg, peak.el_deg).y}
            r={4}
            fill="var(--series-2)"
            stroke="var(--surface-1)"
            strokeWidth={2}
          />
        ) : null}

        {hover ? (
          <circle
            cx={project(hover.az_deg, hover.el_deg).x}
            cy={project(hover.az_deg, hover.el_deg).y}
            r={5}
            fill="var(--series-1)"
            stroke="var(--surface-1)"
            strokeWidth={2}
          />
        ) : null}
      </svg>

      {hover ? (
        <div className="tooltip" style={{ left: 8, top: 26 }}>
          {`${hover.t_utc.slice(11, 19)}Z\naz ${hover.az_deg.toFixed(1)}°  el ${hover.el_deg.toFixed(1)}°\n${hover.range_km.toFixed(0)} km`}
        </div>
      ) : null}

      <div className="legend">
        <span>
          <span className="swatch" style={{ background: "var(--series-1)" }} />
          above mask
        </span>
        <span>
          <span className="swatch" style={{ background: "var(--series-2)" }} />
          culmination
        </span>
        <span>
          <span className="swatch" style={{ background: "var(--text-muted)" }} />
          below mask
        </span>
      </div>
    </div>
  );
}

function Marker({ at, label }: { at: { x: number; y: number }; label: string }) {
  return (
    <g>
      <circle
        cx={at.x}
        cy={at.y}
        r={3.5}
        fill="var(--surface-1)"
        stroke="var(--series-1)"
        strokeWidth={2}
      />
      <text
        x={at.x}
        y={at.y - 8}
        textAnchor="middle"
        fontSize={9}
        fill="var(--text-secondary)"
        fontFamily="var(--mono)"
      >
        {label}
      </text>
    </g>
  );
}
