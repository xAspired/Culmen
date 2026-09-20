// Thin fetch wrapper over the Culmen API.
//
// One rule: an error from the server is surfaced with the server's own
// message. FastAPI puts a usable explanation in `detail` — "no element set for
// NORAD 1; loaded: 6251, 28057" — and replacing that with "Request failed"
// would throw away the most useful part of the response.

import type {
  GroundTrackSample,
  LinkBudget,
  LinkConfig,
  Pass,
  Plan,
  Satellite,
  Station,
  TimelineSample,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (cause) {
    throw new ApiError(
      0,
      "cannot reach the Culmen API — is the server running on port 8000?",
    );
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        // Pydantic validation errors come back as a list of field errors.
        detail = body.detail
          .map((e) => {
            const item = e as { loc?: unknown[]; msg?: string };
            const where = (item.loc ?? []).slice(1).join(".");
            return where ? `${where}: ${item.msg}` : (item.msg ?? "invalid");
          })
          .join("; ");
      }
    } catch {
      // Body was not JSON; the status line above is the best we have.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

const GB = 1_000_000_000;

export const api = {
  health: () =>
    request<{ status: string; stations: number; satellites: number }>("/health"),

  stations: async (
    search = "",
    limit = 200,
  ): Promise<{ rows: Station[]; total: number }> => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (search.trim()) query.set("search", search.trim());
    const response = await fetch(`/api/v1/ground-stations?${query}`);
    if (!response.ok) throw new ApiError(response.status, await response.text());
    const rows = (await response.json()) as Station[];
    const header = response.headers.get("X-Total-Count");
    return { rows, total: header ? Number(header) : rows.length };
  },

  /** Returns the page and how many matched before the cap. */
  satellites: async (
    search = "",
    limit = 200,
  ): Promise<{ rows: Satellite[]; total: number }> => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (search.trim()) query.set("search", search.trim());
    const path = `/api/v1/satellites?${query}`;
    // The count lives in a header, so this one call cannot go through
    // request() -- which is why it is the only place that touches fetch.
    const response = await fetch(path);
    if (!response.ok) throw new ApiError(response.status, await response.text());
    const rows = (await response.json()) as Satellite[];
    const header = response.headers.get("X-Total-Count");
    return { rows, total: header ? Number(header) : rows.length };
  },

  importTle: (text: string, source = "ui") =>
    request<Satellite[]>("/api/v1/satellites/import-tle", {
      method: "POST",
      body: JSON.stringify({ text, source }),
    }),

  searchPasses: (
    station: string,
    noradId: number,
    startUtc: string,
    endUtc: string,
    minElevationDeg?: number,
  ) =>
    request<Pass[]>("/api/v1/passes/search", {
      method: "POST",
      body: JSON.stringify({
        station,
        norad_id: noradId,
        start_utc: startUtc,
        end_utc: endUtc,
        ...(minElevationDeg === undefined
          ? {}
          : { min_elevation_deg: minElevationDeg }),
      }),
    }),

  timeline: (
    station: string,
    noradId: number,
    startUtc: string,
    endUtc: string,
    stepS = 15,
  ) =>
    request<TimelineSample[]>(
      `/api/v1/passes/timeline?${new URLSearchParams({
        station,
        norad_id: String(noradId),
        start_utc: startUtc,
        end_utc: endUtc,
        step_s: String(stepS),
      })}`,
    ),

  groundTrack: (noradId: number, startUtc: string, endUtc: string, stepS = 60) =>
    request<GroundTrackSample[]>(
      `/api/v1/satellites/${noradId}/ground-track?${new URLSearchParams({
        start_utc: startUtc,
        end_utc: endUtc,
        step_s: String(stepS),
      })}`,
    ),

  linkBudget: (cfg: LinkConfig, rangeKm: number, rangeRateKmS?: number) =>
    request<LinkBudget>("/api/v1/link-budget/compute", {
      method: "POST",
      body: JSON.stringify({
        transmitter: transmitterOf(cfg),
        receiver: receiverOf(cfg),
        range_km: rangeKm,
        losses: lossesOf(cfg),
        ...(rangeRateKmS === undefined ? {} : { range_rate_km_s: rangeRateKmS }),
      }),
    }),

  plan: (
    cfg: LinkConfig,
    station: string,
    noradIds: number[],
    startUtc: string,
    endUtc: string,
  ) =>
    request<Plan>("/api/v1/plan", {
      method: "POST",
      body: JSON.stringify({
        station,
        norad_ids: noradIds,
        start_utc: startUtc,
        end_utc: endUtc,
        transmitter: transmitterOf(cfg),
        receiver: receiverOf(cfg),
        losses: lossesOf(cfg),
        profile: {
          framing_efficiency: cfg.framing_efficiency,
          acquisition_s: cfg.acquisition_s,
          setup_s: cfg.setup_s,
        },
        requirement: {
          name: "downlink",
          required_bytes: cfg.required_gigabytes * GB,
          deadline_utc: endUtc,
          min_margin_db: cfg.min_margin_db,
        },
        antenna: {
          rx_freq_min_hz: cfg.freq_hz * 0.95,
          rx_freq_max_hz: cfg.freq_hz * 1.05,
          min_elevation_deg: 5,
          max_elevation_deg: 85,
        },
        antenna_id: "ANT-1",
        sample_step_s: 15,
        turnaround_s: cfg.turnaround_s,
      }),
    }),
};

function transmitterOf(cfg: LinkConfig) {
  return {
    name: "downlink",
    freq_hz: cfg.freq_hz,
    power_w: cfg.power_w,
    gain_dbi: cfg.tx_gain_dbi,
    line_loss_db: cfg.line_loss_db,
    data_rate_bps: cfg.data_rate_bps,
    required_ebn0_db: cfg.required_ebn0_db,
  };
}

function receiverOf(cfg: LinkConfig) {
  return {
    name: "ground station",
    gain_dbi: cfg.rx_gain_dbi,
    system_noise_temp_k: cfg.system_noise_temp_k,
  };
}

function lossesOf(cfg: LinkConfig) {
  return {
    atmospheric_db: cfg.atmospheric_db,
    polarization_db: cfg.polarization_db,
    pointing_db: cfg.pointing_db,
    implementation_db: cfg.implementation_db,
  };
}
