import type { Computed, LinkBudget } from "../api/types";

/**
 * The link budget, line by line, with its audit trail reachable.
 *
 * Every row is a number the server derived; the provenance block below lists,
 * for each derived quantity, the maths note that defines it and the inputs it
 * came from. That is the difference between a tool you can argue with and a
 * tool you have to trust.
 */
export function BudgetTable({ budget }: { budget: LinkBudget }) {
  const derived: [string, Computed | null][] = [
    ["EIRP", budget.eirp_dbw],
    ["Free-space path loss", budget.fspl_db],
    ["Other losses", budget.other_losses_db],
    ["G/T", budget.g_over_t_dbk],
    ["C/N₀", budget.cn0_dbhz],
    ["Eb/N₀", budget.ebn0_db],
    ["Link margin", budget.margin_db],
    ["Doppler shift", budget.doppler_hz],
  ];

  return (
    <div className="stack">
      <div className="row">
        <span className="note">
          at {budget.range_km.toFixed(0)} km · {(budget.freq_hz / 1e9).toFixed(3)} GHz
        </span>
        <span className="spacer" />
        <span className={`badge ${budget.closes ? "pass" : "fail"}`}>
          {budget.closes ? "✓ link closes" : "✕ link does not close"}
        </span>
      </div>

      <table>
        <thead>
          <tr>
            <th>Term</th>
            <th className="num">Value</th>
            <th>Unit</th>
          </tr>
        </thead>
        <tbody>
          {budget.lines.map((line) => {
            const emphasis =
              line.label === "Link margin" || line.label === "C/N0";
            return (
              <tr key={line.label}>
                <td style={emphasis ? { fontWeight: 600 } : undefined}>{line.label}</td>
                <td
                  className="num"
                  style={
                    line.label === "Link margin"
                      ? {
                          fontWeight: 700,
                          color: line.value >= 0 ? "var(--good)" : "var(--critical)",
                        }
                      : undefined
                  }
                >
                  {line.value >= 0 && line.label === "Link margin" ? "+" : ""}
                  {line.value.toFixed(2)}
                </td>
                <td className="note">{line.unit}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <details className="provenance">
        <summary>Provenance — where each number came from</summary>
        <ul>
          {derived
            .filter((entry): entry is [string, Computed] => entry[1] !== null)
            .map(([label, c]) => (
              <li key={label}>
                <strong style={{ color: "var(--text-primary)" }}>{label}</strong>{" "}
                <span className="mono">
                  {c.value.toFixed(3)} {c.unit}
                </span>
                {" — "}
                <code>{c.formula_ref}</code>
                {Object.keys(c.inputs).length > 0 ? (
                  <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {Object.entries(c.inputs)
                      .map(([k, v]) => `${k}=${formatInput(v)}`)
                      .join("  ")}
                  </div>
                ) : null}
              </li>
            ))}
        </ul>
      </details>

      {budget.assumptions.length > 0 ? (
        <details className="provenance">
          <summary>{budget.assumptions.length} declared assumptions</summary>
          <ul>
            {budget.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function formatInput(v: number): string {
  if (Math.abs(v) >= 1e6) return v.toExponential(3);
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(3);
}
