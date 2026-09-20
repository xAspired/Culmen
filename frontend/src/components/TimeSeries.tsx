import { useMemo, useState } from "react";

/** One plotted quantity. Each chart carries exactly one: never two y-scales. */
export interface Series {
  label: string;
  unit: string;
  color: string;
  points: { x: number; y: number }[];
  /** Optional horizontal reference, e.g. an elevation mask or a required margin. */
  threshold?: { value: number; label: string };
}

interface Props {
  title: string;
  series: Series;
  /** x-axis tick formatter; x is seconds from the start of the window. */
  formatX?: (x: number) => string;
  height?: number;
}

const PAD = { top: 10, right: 12, bottom: 24, left: 46 };

/**
 * A single-series line chart with a crosshair and a tooltip.
 *
 * Deliberately one series per chart. Elevation and link margin share a time
 * axis but not a scale, so they are two stacked charts rather than one chart
 * with two y-axes -- a dual-axis plot invites a visual correlation that the
 * data does not support.
 */
export function TimeSeries({ title, series, formatX, height = 150 }: Props) {
  const [hover, setHover] = useState<{ i: number; px: number; py: number } | null>(
    null,
  );

  const width = 560;
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const empty = series.points.length < 2;

  const { xMin, xMax, yMin, yMax, path, ticksY, ticksX } = useMemo(() => {
    // An empty or single-point series would make Math.min/max return
    // +/-Infinity and poison every scale with NaN, which SVG rejects
    // attribute by attribute. Bail out with a valid but unused frame.
    if (series.points.length < 2) {
      return {
        xMin: 0,
        xMax: 1,
        yMin: 0,
        yMax: 1,
        path: "",
        ticksY: [] as { v: number; y: number }[],
        ticksX: [] as { v: number; x: number }[],
      };
    }
    const xs = series.points.map((p) => p.x);
    const ys = series.points.map((p) => p.y);
    if (series.threshold) ys.push(series.threshold.value);

    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs);
    let y0 = Math.min(...ys);
    let y1 = Math.max(...ys);
    if (y0 === y1) {
      y0 -= 1;
      y1 += 1;
    }
    const headroom = (y1 - y0) * 0.08;
    y0 -= headroom;
    y1 += headroom;

    const sx = (x: number) => PAD.left + ((x - x0) / (x1 - x0 || 1)) * plotW;
    const sy = (y: number) => PAD.top + plotH - ((y - y0) / (y1 - y0)) * plotH;

    const d = series.points
      .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(2)},${sy(p.y).toFixed(2)}`)
      .join(" ");

    const tickCount = 4;
    const ty = Array.from({ length: tickCount + 1 }, (_, i) => {
      const v = y0 + ((y1 - y0) * i) / tickCount;
      return { v, y: sy(v) };
    });
    const tx = Array.from({ length: 5 }, (_, i) => {
      const v = x0 + ((x1 - x0) * i) / 4;
      return { v, x: sx(v) };
    });

    return {
      xMin: x0,
      xMax: x1,
      yMin: y0,
      yMax: y1,
      path: d,
      ticksY: ty,
      ticksX: tx,
    };
  }, [series, plotW, plotH]);

  const sx = (x: number) => PAD.left + ((x - xMin) / (xMax - xMin || 1)) * plotW;
  const sy = (y: number) => PAD.top + plotH - ((y - yMin) / (yMax - yMin)) * plotH;

  function onMove(event: React.MouseEvent<SVGSVGElement>) {
    if (empty) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const scale = width / rect.width;
    const px = (event.clientX - rect.left) * scale;
    const target = xMin + ((px - PAD.left) / plotW) * (xMax - xMin);

    let best = 0;
    let bestDelta = Infinity;
    series.points.forEach((p, i) => {
      const delta = Math.abs(p.x - target);
      if (delta < bestDelta) {
        bestDelta = delta;
        best = i;
      }
    });
    const point = series.points[best];
    if (!point) return;
    setHover({ i: best, px: sx(point.x), py: sy(point.y) });
  }

  const hovered = hover ? series.points[hover.i] : undefined;

  if (empty) {
    return (
      <div className="chart">
        <div className="chart-title">{title}</div>
        <div className="empty">no samples yet</div>
      </div>
    );
  }

  return (
    <div className="chart">
      <div className="chart-title">{title}</div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${title}: ${series.label} in ${series.unit}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        <g className="grid">
          {ticksY.map((t, i) => (
            <line key={i} x1={PAD.left} x2={width - PAD.right} y1={t.y} y2={t.y} />
          ))}
        </g>

        {series.threshold ? (
          <>
            <line
              x1={PAD.left}
              x2={width - PAD.right}
              y1={sy(series.threshold.value)}
              y2={sy(series.threshold.value)}
              stroke="var(--warning)"
              strokeWidth={1.5}
              strokeDasharray="5 4"
            />
            <text
              x={width - PAD.right}
              y={sy(series.threshold.value) - 4}
              textAnchor="end"
              fontSize={10}
              fill="var(--warning)"
              fontFamily="var(--mono)"
            >
              {series.threshold.label}
            </text>
          </>
        ) : null}

        <path className="series" d={path} stroke={series.color} />

        <g className="axis">
          <line x1={PAD.left} x2={PAD.left} y1={PAD.top} y2={PAD.top + plotH} />
          <line
            x1={PAD.left}
            x2={width - PAD.right}
            y1={PAD.top + plotH}
            y2={PAD.top + plotH}
          />
          {ticksY.map((t, i) => (
            <text key={i} x={PAD.left - 6} y={t.y + 3} textAnchor="end">
              {formatTick(t.v)}
            </text>
          ))}
          {ticksX.map((t, i) => (
            <text key={i} x={t.x} y={height - 8} textAnchor="middle">
              {formatX ? formatX(t.v) : t.v.toFixed(0)}
            </text>
          ))}
        </g>

        {hover && hovered ? (
          <>
            <line
              x1={hover.px}
              x2={hover.px}
              y1={PAD.top}
              y2={PAD.top + plotH}
              stroke="var(--text-muted)"
              strokeWidth={1}
            />
            {/* 2px surface ring so the marker reads against the line */}
            <circle
              cx={hover.px}
              cy={hover.py}
              r={5}
              fill={series.color}
              stroke="var(--surface-1)"
              strokeWidth={2}
            />
          </>
        ) : null}
      </svg>

      {hover && hovered ? (
        <div
          className="tooltip"
          style={{
            left: `${(hover.px / width) * 100}%`,
            top: `${(hover.py / height) * 100}%`,
            transform: "translate(-50%, -130%)",
          }}
        >
          {`${formatX ? formatX(hovered.x) : hovered.x.toFixed(0)}\n${hovered.y.toFixed(2)} ${series.unit}`}
        </div>
      ) : null}
    </div>
  );
}

function formatTick(v: number): string {
  const a = Math.abs(v);
  if (a >= 1000) return v.toFixed(0);
  if (a >= 10) return v.toFixed(0);
  return v.toFixed(1);
}
