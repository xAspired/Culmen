import type { LinkConfig } from "../api/types";

interface Props {
  config: LinkConfig;
  onChange: (next: LinkConfig) => void;
}

interface FieldSpec {
  key: keyof LinkConfig;
  label: string;
  step?: number;
  scale?: number;
  suffix?: string;
}

/** Fields are grouped the way a link budget is read, top to bottom. */
const GROUPS: { legend: string; fields: FieldSpec[]; note?: string }[] = [
  {
    legend: "Transmitter",
    fields: [
      { key: "freq_hz", label: "Frequency", scale: 1e9, suffix: "GHz", step: 0.1 },
      { key: "power_w", label: "TX power", suffix: "W", step: 1 },
      { key: "tx_gain_dbi", label: "TX gain", suffix: "dBi", step: 0.5 },
      { key: "line_loss_db", label: "Line loss", suffix: "dB", step: 0.1 },
      { key: "data_rate_bps", label: "Data rate", scale: 1e6, suffix: "Mbps", step: 1 },
      { key: "required_ebn0_db", label: "Required Eb/N₀", suffix: "dB", step: 0.5 },
    ],
  },
  {
    legend: "Receiver",
    fields: [
      { key: "rx_gain_dbi", label: "RX gain", suffix: "dBi", step: 0.5 },
      { key: "system_noise_temp_k", label: "T system", suffix: "K", step: 10 },
    ],
  },
  {
    legend: "Losses",
    note: "All positive dB. A field left at 0 is optimistic, and the API says so in its assumptions.",
    fields: [
      { key: "atmospheric_db", label: "Atmospheric", suffix: "dB", step: 0.1 },
      { key: "polarization_db", label: "Polarization", suffix: "dB", step: 0.1 },
      { key: "pointing_db", label: "Pointing", suffix: "dB", step: 0.1 },
      { key: "implementation_db", label: "Implementation", suffix: "dB", step: 0.1 },
    ],
  },
  {
    legend: "Transfer",
    note: "Overhead is subtracted from the interval where the link actually closes.",
    fields: [
      { key: "framing_efficiency", label: "Framing eff.", step: 0.01 },
      { key: "acquisition_s", label: "Acquisition", suffix: "s", step: 5 },
      { key: "setup_s", label: "Setup / slew", suffix: "s", step: 5 },
    ],
  },
  {
    legend: "Requirement",
    fields: [
      { key: "required_gigabytes", label: "Volume", suffix: "GB", step: 0.5 },
      { key: "min_margin_db", label: "Min margin", suffix: "dB", step: 0.5 },
      { key: "turnaround_s", label: "Turnaround", suffix: "s", step: 60 },
    ],
  },
];

export function ConfigPanel({ config, onChange }: Props) {
  return (
    <div className="stack">
      {GROUPS.map((group) => (
        <fieldset key={group.legend}>
          <legend>{group.legend}</legend>
          {group.note ? (
            <div className="note" style={{ marginBottom: 10 }}>
              {group.note}
            </div>
          ) : null}
          <div className="field-grid">
            {group.fields.map((field) => {
              const scale = field.scale ?? 1;
              return (
                <div key={String(field.key)}>
                  <label htmlFor={String(field.key)}>
                    {field.label}
                    {field.suffix ? ` (${field.suffix})` : ""}
                  </label>
                  <input
                    id={String(field.key)}
                    type="number"
                    step={field.step ?? 1}
                    value={round(config[field.key] / scale)}
                    onChange={(e) => {
                      const raw = Number(e.target.value);
                      if (Number.isNaN(raw)) return;
                      onChange({ ...config, [field.key]: raw * scale });
                    }}
                  />
                </div>
              );
            })}
          </div>
        </fieldset>
      ))}
    </div>
  );
}

function round(v: number): number {
  return Math.abs(v) < 1 ? Number(v.toFixed(4)) : Number(v.toFixed(3));
}
