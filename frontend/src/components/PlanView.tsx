import { useState } from "react";

import type { Contact, Plan } from "../api/types";
import { VerdictPanel } from "./VerdictPanel";

const GB = 1_000_000_000;

/**
 * The schedule, the requirement status, and everything that was discarded.
 *
 * The rejection list is not an appendix. "Why was my pass dropped?" is the
 * question an operator asks, and a planner that shows only its accepted
 * contacts answers "what shall I do?" while hiding "what did you decide on my
 * behalf?".
 */
export function PlanView({ plan }: { plan: Plan }) {
  // Clicking any contact -- scheduled or discarded -- opens the verdict that
  // produced that outcome. A plan you cannot interrogate is a plan you cannot
  // trust, and the checks are the whole reason this tool exists.
  const [open, setOpen] = useState<Contact | null>(null);

  return (
    <div className="stack">
      <div>
        <h3>Requirements</h3>
        <table>
          <thead>
            <tr>
              <th>Requirement</th>
              <th>Status</th>
              <th className="num">Delivered</th>
              <th className="num">Required</th>
              <th className="num">Contacts</th>
              <th className="num">Shortfall</th>
            </tr>
          </thead>
          <tbody>
            {plan.requirements.map((r) => (
              <tr key={r.name}>
                <td>{r.name}</td>
                <td>
                  <span className={`badge ${r.satisfied ? "pass" : "fail"}`}>
                    {r.satisfied ? "✓ satisfied" : "✕ unmet"}
                  </span>
                </td>
                <td className="num">{(r.delivered_bytes / GB).toFixed(3)} GB</td>
                <td className="num">{(r.required_bytes / GB).toFixed(3)} GB</td>
                <td className="num">{r.contact_count}</td>
                <td className="num">
                  {r.shortfall_bytes > 0
                    ? `${(r.shortfall_bytes / GB).toFixed(3)} GB`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <h3>Scheduled ({plan.scheduled.length})</h3>
        <div className="note" style={{ marginBottom: 6 }}>
          Listed in time order; “rank” is the order the scheduler allocated them,
          which is the ranking policy, not the clock. Click a row for its verdict.
        </div>
        {plan.scheduled.length === 0 ? (
          <div className="empty">No contact could be scheduled in this window.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th className="num">Rank</th>
                <th>AOS → LOS</th>
                <th className="num">NORAD</th>
                <th>Antenna</th>
                <th className="num">Max el</th>
                <th className="num">FSPL spread</th>
                <th className="num">Volume</th>
                <th className="num">Cumulative</th>
              </tr>
            </thead>
            <tbody>
              {plan.scheduled.map((s) => (
                <tr
                  key={`${s.rank}-${s.contact.pass.aos_utc}`}
                  className={`clickable${open === s.contact ? " selected" : ""}`}
                  onClick={() => setOpen(open === s.contact ? null : s.contact)}
                >
                  <td className="num">{s.rank}</td>
                  <td className="mono">
                    {s.contact.pass.aos_utc.slice(5, 16).replace("T", " ")} →{" "}
                    {s.contact.pass.los_utc.slice(11, 16)}
                  </td>
                  <td className="num">{s.contact.pass.satellite_norad_id}</td>
                  <td>{s.contact.antenna_id}</td>
                  <td className="num">{s.contact.pass.max_elevation_deg.toFixed(1)}°</td>
                  <td className="num">{s.contact.fspl_spread_db.toFixed(1)} dB</td>
                  <td className="num">{s.contact.volume.gigabytes.toFixed(3)} GB</td>
                  <td className="num">{(s.cumulative_bytes / GB).toFixed(3)} GB</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {plan.rejected.length > 0 ? (
        <details open>
          <summary style={{ cursor: "pointer" }}>
            <h3 style={{ display: "inline" }}>Not scheduled ({plan.rejected.length})</h3>
          </summary>
          <table style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th>AOS</th>
                <th className="num">NORAD</th>
                <th>Reason</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {plan.rejected.map((r, i) => (
                <tr
                  key={i}
                  className={`clickable${open === r.contact ? " selected" : ""}`}
                  onClick={() => setOpen(open === r.contact ? null : r.contact)}
                >
                  <td className="mono">
                    {r.contact.pass.aos_utc.slice(5, 16).replace("T", " ")}
                  </td>
                  <td className="num">{r.contact.pass.satellite_norad_id}</td>
                  <td>
                    <span className="badge fail">{r.reason}</span>
                  </td>
                  <td className="note" style={{ color: "var(--text-secondary)" }}>
                    {r.detail}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}

      {open ? (
        <div className="panel">
          <header>
            <h2>
              Verdict — {open.pass.aos_utc.slice(5, 16).replace("T", " ")}Z, NORAD{" "}
              {open.pass.satellite_norad_id}
            </h2>
            <span className="spacer" />
            <button
              className="secondary"
              style={{ width: "auto" }}
              onClick={() => setOpen(null)}
            >
              Close
            </button>
          </header>
          <div className="note" style={{ marginBottom: 10 }}>
            {open.volume.gigabytes.toFixed(3)} GB over{" "}
            {open.volume.usable_s.value.toFixed(0)} usable seconds of a{" "}
            {open.volume.closing_s.value.toFixed(0)} s closing interval · free-space
            loss varies {open.fspl_spread_db.toFixed(1)} dB across this pass
          </div>
          <VerdictPanel validation={open.validation} />
        </div>
      ) : null}

      {plan.notes.length > 0 ? (
        <div className="stack">
          {plan.notes.map((n, i) => (
            <div key={i} className="warning-banner">
              {n}
            </div>
          ))}
        </div>
      ) : null}

      <div className="note mono">{plan.scheduler_version}</div>
    </div>
  );
}
