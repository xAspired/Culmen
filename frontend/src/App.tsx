import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "./api/client";
import {
  DEFAULT_CONFIG,
  type GroundTrackSample,
  type LinkBudget,
  type LinkConfig,
  type Pass,
  type Plan,
  type Satellite,
  type Station,
  type TimelineSample,
} from "./api/types";
import { BudgetTable } from "./components/BudgetTable";
import { ConfigPanel } from "./components/ConfigPanel";
import { GroundTrack } from "./components/GroundTrack";
import { PlanView } from "./components/PlanView";
import { PolarPlot } from "./components/PolarPlot";
import { TimeSeries } from "./components/TimeSeries";

type Tab = "pass" | "plan";

export default function App() {
  const [stations, setStations] = useState<Station[]>([]);
  const [stationSearch, setStationSearch] = useState("");
  const [stationTotal, setStationTotal] = useState(0);
  const [satellites, setSatellites] = useState<Satellite[]>([]);
  const [satelliteSearch, setSatelliteSearch] = useState("");
  const [satelliteTotal, setSatelliteTotal] = useState(0);
  const [stationName, setStationName] = useState<string>("");
  const [noradId, setNoradId] = useState<number | null>(null);
  const [windowHours, setWindowHours] = useState(24);
  const [startUtc, setStartUtc] = useState<string>("");

  const [passes, setPasses] = useState<Pass[]>([]);
  const [selected, setSelected] = useState<Pass | null>(null);
  const [timeline, setTimeline] = useState<TimelineSample[]>([]);
  const [budgets, setBudgets] = useState<LinkBudget[]>([]);
  const [track, setTrack] = useState<GroundTrackSample[]>([]);
  const [plan, setPlan] = useState<Plan | null>(null);

  const [config, setConfig] = useState<LinkConfig>(DEFAULT_CONFIG);
  const [tab, setTab] = useState<Tab>("pass");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tleText, setTleText] = useState("");

  const station = stations.find((s) => s.name === stationName) ?? null;
  const satellite = satellites.find((s) => s.norad_id === noradId) ?? null;

  const run = useCallback(async (what: string, fn: () => Promise<void>) => {
    setBusy(what);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }, []);

  // Initial load.
  useEffect(() => {
    void run("loading", async () => {
      const [st, sats] = await Promise.all([api.stations(), api.satellites()]);
      setStations(st.rows);
      setStationTotal(st.total);
      setSatellites(sats.rows);
      setSatelliteTotal(sats.total);
      if (st.rows.length > 0 && st.rows[0]) setStationName(st.rows[0].name);
      if (sats.rows.length > 0 && sats.rows[0]) {
        const first = sats.rows[0];
        setNoradId(first.norad_id);
        // Default the window to the element-set epoch: with historical
        // verification data, "now" would be tens of thousands of days away
        // and every result would be meaningless.
        setStartUtc(first.epoch_utc.slice(0, 16));
      }
    });
  }, [run]);

  const endUtc = useMemo(() => {
    if (!startUtc) return "";
    const start = new Date(`${startUtc}:00Z`);
    return new Date(start.getTime() + windowHours * 3600_000).toISOString();
  }, [startUtc, windowHours]);

  const startIso = startUtc ? new Date(`${startUtc}:00Z`).toISOString() : "";

  const searchPasses = () =>
    run("searching passes", async () => {
      if (!station || noradId === null) throw new ApiError(0, "pick a station and a satellite");
      const found = await api.searchPasses(station.name, noradId, startIso, endUtc);
      setPasses(found);
      setSelected(found[0] ?? null);
      setPlan(null);
      const gt = await api.groundTrack(noradId, startIso, endUtc, 120);
      setTrack(gt);
    });

  const buildPlan = () =>
    run("planning", async () => {
      if (!station || noradId === null) throw new ApiError(0, "pick a station and a satellite");
      setPlan(await api.plan(config, station.name, [noradId], startIso, endUtc));
      setTab("plan");
    });

  const importTle = () =>
    run("importing", async () => {
      const imported = await api.importTle(tleText);
      const refreshed = await api.satellites(satelliteSearch);
      setSatellites(refreshed.rows);
      setSatelliteTotal(refreshed.total);
      if (imported[0]) {
        setNoradId(imported[0].norad_id);
        setStartUtc(imported[0].epoch_utc.slice(0, 16));
      }
      setTleText("");
    });

  // Load the detail of whichever pass is selected.
  useEffect(() => {
    if (!selected || !station) {
      setTimeline([]);
      setBudgets([]);
      return;
    }
    void run("loading pass", async () => {
      const samples = await api.timeline(
        station.name,
        selected.satellite_norad_id,
        selected.aos_utc,
        selected.los_utc,
        15,
      );
      setTimeline(samples);
      // The budget is evaluated at every sample, never at the peak alone.
      setBudgets(
        await Promise.all(
          samples.map((s) => api.linkBudget(config, s.range_km, s.range_rate_km_s)),
        ),
      );
    });
  }, [selected, station, config, run]);

  const t0 = selected ? Date.parse(selected.aos_utc) : 0;
  const secondsFromAos = (iso: string) => (Date.parse(iso) - t0) / 1000;

  const elevationSeries = {
    label: "Elevation",
    unit: "°",
    color: "var(--series-1)",
    points: timeline.map((s) => ({ x: secondsFromAos(s.t_utc), y: s.el_deg })),
    ...(station ? { threshold: { value: station.min_elevation_deg, label: "mask" } } : {}),
  };

  const marginSeries = {
    label: "Link margin",
    unit: "dB",
    color: "var(--series-2)",
    points: budgets
      .map((b, i) => ({
        x: timeline[i] ? secondsFromAos(timeline[i]!.t_utc) : i,
        y: b.margin_db?.value ?? Number.NaN,
      }))
      .filter((p) => Number.isFinite(p.y)),
    threshold: { value: config.min_margin_db, label: "required" },
  };

  const worstBudget = useMemo(() => {
    if (budgets.length === 0) return null;
    return budgets.reduce((worst, b) =>
      (b.margin_db?.value ?? b.cn0_dbhz.value) <
      (worst.margin_db?.value ?? worst.cn0_dbhz.value)
        ? b
        : worst,
    );
  }, [budgets]);

  const passTrack = useMemo(() => {
    if (!selected) return undefined;
    const aos = Date.parse(selected.aos_utc);
    const los = Date.parse(selected.los_utc);
    return track.filter((s) => {
      const t = Date.parse(s.t_utc);
      return t >= aos && t <= los;
    });
  }, [track, selected]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Culmen</h1>
          <span className="tagline">contact planning &amp; validation</span>
        </div>
        <span className="spacer" />
        {busy ? <span className="note">{busy}…</span> : null}
        <span className="note mono">
          {stationTotal} station{stationTotal === 1 ? "" : "s"} ·{" "}
          {satelliteTotal} satellite{satelliteTotal === 1 ? "" : "s"}
        </span>
      </header>

      <aside className="sidebar">
        <div className="stack">
          <fieldset>
            <legend>Scenario</legend>
            <div className="stack">
              <div>
                <label htmlFor="station-search">
                  Ground station
                  {stationTotal > stations.length
                    ? ` — ${stations.length} of ${stationTotal} shown`
                    : ` — ${stationTotal}`}
                </label>
                <input
                  id="station-search"
                  type="search"
                  placeholder="filter by name"
                  value={stationSearch}
                  onChange={(e) => {
                    const next = e.target.value;
                    setStationSearch(next);
                    void run("filtering", async () => {
                      const found = await api.stations(next);
                      setStations(found.rows);
                      setStationTotal(found.total);
                      if (
                        found.rows.length > 0 &&
                        !found.rows.some((s) => s.name === stationName)
                      ) {
                        setStationName(found.rows[0]!.name);
                      }
                    });
                  }}
                  style={{ marginBottom: 6 }}
                />
                <select
                  id="station"
                  value={stationName}
                  onChange={(e) => setStationName(e.target.value)}
                >
                  {stations.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.name} ({s.min_elevation_deg.toFixed(0)}° mask)
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="satellite-search">
                  Satellite
                  {satelliteTotal > satellites.length
                    ? ` — ${satellites.length} of ${satelliteTotal} shown`
                    : ` — ${satelliteTotal}`}
                </label>
                <input
                  id="satellite-search"
                  type="search"
                  placeholder="filter by name or NORAD id"
                  value={satelliteSearch}
                  onChange={(e) => {
                    const next = e.target.value;
                    setSatelliteSearch(next);
                    void run("filtering", async () => {
                      const found = await api.satellites(next);
                      setSatellites(found.rows);
                      setSatelliteTotal(found.total);
                      if (
                        found.rows.length > 0 &&
                        !found.rows.some((s) => s.norad_id === noradId)
                      ) {
                        setNoradId(found.rows[0]!.norad_id);
                      }
                    });
                  }}
                  style={{ marginBottom: 6 }}
                />
                <select
                  id="satellite"
                  value={noradId ?? ""}
                  onChange={(e) => setNoradId(Number(e.target.value))}
                >
                  {satellites.length === 0 ? <option value="">none imported</option> : null}
                  {satellites.map((s) => (
                    <option key={s.norad_id} value={s.norad_id}>
                      {s.name ?? `NORAD ${s.norad_id}`}
                    </option>
                  ))}
                </select>
              </div>

              <div className="field-grid">
                <div>
                  <label htmlFor="start">Start (UTC)</label>
                  <input
                    id="start"
                    type="datetime-local"
                    value={startUtc}
                    onChange={(e) => setStartUtc(e.target.value)}
                  />
                </div>
                <div>
                  <label htmlFor="hours">Window (h)</label>
                  <input
                    id="hours"
                    type="number"
                    min={1}
                    max={168}
                    value={windowHours}
                    onChange={(e) => setWindowHours(Number(e.target.value))}
                  />
                </div>
              </div>

              {satellite?.age_warning ? (
                <div className="warning-banner">{satellite.age_warning}</div>
              ) : null}

              <div className="row">
                <button onClick={searchPasses} disabled={busy !== null || !station}>
                  Find passes
                </button>
                <button
                  className="secondary"
                  onClick={buildPlan}
                  disabled={busy !== null || !station}
                >
                  Plan
                </button>
              </div>
            </div>
          </fieldset>

          <fieldset>
            <legend>Import TLE</legend>
            <div className="stack">
              <div className="note">
                Paste element sets. Culmen never fetches them for you: rate limits and
                attribution are yours to respect.
              </div>
              <textarea
                value={tleText}
                onChange={(e) => setTleText(e.target.value)}
                placeholder={"NAME\n1 ...\n2 ..."}
                spellCheck={false}
              />
              <button
                className="secondary"
                onClick={importTle}
                disabled={busy !== null || tleText.trim().length < 100}
              >
                Import
              </button>
            </div>
          </fieldset>

          <ConfigPanel config={config} onChange={setConfig} />
        </div>
      </aside>

      <main className="main">
        {error ? <div className="error-banner">{error}</div> : null}

        <div className="panel">
          <header>
            <h2>Passes</h2>
            <span className="spacer" />
            <div className="row">
              <button
                className={tab === "pass" ? "" : "secondary"}
                style={{ width: "auto" }}
                onClick={() => setTab("pass")}
              >
                Detail
              </button>
              <button
                className={tab === "plan" ? "" : "secondary"}
                style={{ width: "auto" }}
                onClick={() => setTab("plan")}
              >
                Plan
              </button>
            </div>
          </header>

          {passes.length === 0 ? (
            <div className="empty">
              No passes loaded. Choose a station and a satellite, then “Find passes”.
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>AOS</th>
                  <th>LOS</th>
                  <th className="num">Duration</th>
                  <th className="num">Max el</th>
                  <th className="num">Az AOS→LOS</th>
                  <th className="num">TLE age</th>
                </tr>
              </thead>
              <tbody>
                {passes.map((p, i) => (
                  <tr
                    key={p.aos_utc}
                    className={`clickable${selected?.aos_utc === p.aos_utc ? " selected" : ""}`}
                    onClick={() => {
                      setSelected(p);
                      setTab("pass");
                    }}
                  >
                    <td className="num">{i + 1}</td>
                    <td className="mono">{p.aos_utc.slice(5, 19).replace("T", " ")}</td>
                    <td className="mono">{p.los_utc.slice(11, 19)}</td>
                    <td className="num">{(p.duration_s / 60).toFixed(1)} min</td>
                    <td className="num">{p.max_elevation_deg.toFixed(1)}°</td>
                    <td className="num">
                      {p.aos_az_deg.toFixed(0)}° → {p.los_az_deg.toFixed(0)}°
                    </td>
                    <td className="num">{p.tle_age_days.toFixed(1)} d</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {tab === "plan" && plan ? (
          <div className="panel">
            <header>
              <h2>Plan</h2>
            </header>
            <PlanView plan={plan} />
          </div>
        ) : null}

        {tab === "pass" && selected ? (
          <>
            <div className="grid-2">
              <div className="panel">
                <PolarPlot
                  samples={timeline}
                  maskDeg={station?.min_elevation_deg ?? 0}
                />
              </div>
              <div className="panel stack">
                <TimeSeries
                  title="Elevation across the pass"
                  series={elevationSeries}
                  formatX={formatSeconds}
                />
                <TimeSeries
                  title="Link margin across the pass — the worst point is what decides"
                  series={marginSeries}
                  formatX={formatSeconds}
                />
              </div>
            </div>

            <div className="panel">
              <header>
                <h2>Ground track</h2>
              </header>
              <GroundTrack
                track={track}
                station={station}
                {...(passTrack ? { highlight: passTrack } : {})}
              />
            </div>

            {worstBudget ? (
              <div className="panel">
                <header>
                  <h2>Link budget — worst case across the pass</h2>
                </header>
                <BudgetTable budget={worstBudget} />
              </div>
            ) : null}
          </>
        ) : null}
      </main>
    </div>
  );
}

function formatSeconds(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}
