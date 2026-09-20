import type { Check, Validation } from "../api/types";

/**
 * The verdict, its reasoning, and what to change.
 *
 * The rule this component exists to enforce: a verdict is never shown without
 * the checks that produced it. Rendering "INVALID" alone would throw away the
 * one thing Culmen has that other tools do not.
 */
export function VerdictPanel({ validation }: { validation: Validation }) {
  return (
    <div className="stack">
      <div className="row">
        <span className={`badge ${validation.verdict.toLowerCase()}`}>
          {icon(validation.verdict)} {validation.verdict.replace(/_/g, " ")}
        </span>
        <span className="spacer" />
        <span className="note mono">{validation.engine_version}</span>
      </div>

      <table>
        <thead>
          <tr>
            <th>Check</th>
            <th>Result</th>
            <th>Detail</th>
            <th className="num">Expected</th>
            <th className="num">Actual</th>
          </tr>
        </thead>
        <tbody>
          {validation.checks.map((check) => (
            <CheckRow key={check.name} check={check} />
          ))}
        </tbody>
      </table>

      {validation.suggestions.length > 0 ? (
        <div>
          <h3>Suggested alternatives</h3>
          <ul className="note" style={{ paddingLeft: 18, marginTop: 6 }}>
            {validation.suggestions.map((s, i) => (
              <li key={i} style={{ marginBottom: 4 }}>
                <strong style={{ color: "var(--text-primary)" }}>{s.action}</strong>
                {": "}
                {s.detail}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {validation.assumptions.length > 0 ? (
        <details className="provenance">
          <summary>{validation.assumptions.length} declared assumptions</summary>
          <ul>
            {validation.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function CheckRow({ check }: { check: Check }) {
  return (
    <tr>
      <td className="mono">{check.name}</td>
      <td>
        <span className={`badge ${check.result.toLowerCase()}`}>
          {icon(check.result)} {check.result}
        </span>
      </td>
      <td className="note" style={{ color: "var(--text-secondary)" }}>
        {check.message}
      </td>
      <td className="num">{check.expected ? `${check.expected}${check.unit}` : "—"}</td>
      <td className="num">{check.actual ? `${check.actual}${check.unit}` : "—"}</td>
    </tr>
  );
}

/** Status is never carried by colour alone. */
function icon(state: string): string {
  switch (state) {
    case "PASS":
    case "VALID":
      return "✓";
    case "FAIL":
    case "INVALID":
      return "✕";
    case "WARN":
    case "CONDITIONALLY_VALID":
      return "!";
    default:
      return "–";
  }
}
