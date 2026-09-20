// Types mirroring the Culmen API DTOs.
//
// Hand-written rather than generated: the surface is small, and writing them
// out makes the unit suffixes visible at every call site, which is the same
// discipline the Python side enforces with a test.
//
// If this ever drifts from the server, `GET /openapi.json` is the source of
// truth and these should be regenerated from it.

export interface Computed {
  value: number;
  unit: string;
  formula_ref: string;
  inputs: Record<string, number>;
  assumptions: string[];
}

export interface Station {
  name: string;
  lat_deg: number;
  lon_deg: number;
  alt_m: number;
  min_elevation_deg: number;
  has_horizon_profile: boolean;
}

export interface Satellite {
  norad_id: number;
  name: string | null;
  cospar_id: string;
  epoch_utc: string;
  inclination_deg: number;
  eccentricity: number;
  mean_motion_rev_day: number;
  age_days: number;
  age_warning: string | null;
}

export interface Pass {
  satellite_norad_id: number;
  station_name: string;
  aos_utc: string;
  los_utc: string;
  duration_s: number;
  max_elevation_deg: number;
  max_elevation_utc: string;
  aos_az_deg: number;
  los_az_deg: number;
  max_el_az_deg: number;
  tle_epoch_utc: string;
  tle_age_days: number;
  propagator_version: string;
  warnings: string[];
}

export interface TimelineSample {
  t_utc: string;
  az_deg: number;
  el_deg: number;
  range_km: number;
  range_rate_km_s: number;
}

export interface GroundTrackSample {
  t_utc: string;
  lat_deg: number;
  lon_deg: number;
  alt_km: number;
}

export interface BudgetLine {
  label: string;
  value: number;
  unit: string;
}

export interface LinkBudget {
  range_km: number;
  freq_hz: number;
  eirp_dbw: Computed;
  fspl_db: Computed;
  other_losses_db: Computed;
  g_over_t_dbk: Computed;
  cn0_dbhz: Computed;
  ebn0_db: Computed | null;
  margin_db: Computed | null;
  doppler_hz: Computed | null;
  closes: boolean;
  lines: BudgetLine[];
  assumptions: string[];
}

export interface DataVolume {
  closing_s: Computed;
  usable_s: Computed;
  delivered_bytes: Computed;
  gigabytes: number;
  assumptions: string[];
}

export type CheckResult = "PASS" | "FAIL" | "WARN" | "SKIPPED";
export type Verdict = "VALID" | "CONDITIONALLY_VALID" | "INVALID";

export interface Check {
  name: string;
  result: CheckResult;
  message: string;
  expected: string;
  actual: string;
  unit: string;
  formula_ref: string;
}

export interface Suggestion {
  check_name: string;
  action: string;
  detail: string;
}

export interface Validation {
  verdict: Verdict;
  checks: Check[];
  suggestions: Suggestion[];
  assumptions: string[];
  engine_version: string;
}

export interface Contact {
  pass: Pass;
  antenna_id: string;
  volume: DataVolume;
  validation: Validation;
  fspl_spread_db: number;
}

export interface Scheduled {
  rank: number;
  contact: Contact;
  cumulative_bytes: number;
}

export interface Rejected {
  contact: Contact;
  reason: string;
  detail: string;
}

export interface RequirementStatus {
  name: string;
  required_bytes: number;
  delivered_bytes: number;
  satisfied: boolean;
  contact_count: number;
  shortfall_bytes: number;
}

export interface Plan {
  scheduled: Scheduled[];
  rejected: Rejected[];
  requirements: RequirementStatus[];
  all_satisfied: boolean;
  scheduler_version: string;
  notes: string[];
}

/** Everything the user can tune, held in one place so it can be round-tripped. */
export interface LinkConfig {
  freq_hz: number;
  power_w: number;
  tx_gain_dbi: number;
  line_loss_db: number;
  data_rate_bps: number;
  required_ebn0_db: number;
  rx_gain_dbi: number;
  system_noise_temp_k: number;
  atmospheric_db: number;
  polarization_db: number;
  pointing_db: number;
  implementation_db: number;
  framing_efficiency: number;
  acquisition_s: number;
  setup_s: number;
  required_gigabytes: number;
  min_margin_db: number;
  turnaround_s: number;
}

export const DEFAULT_CONFIG: LinkConfig = {
  freq_hz: 8.2e9,
  power_w: 20,
  tx_gain_dbi: 12,
  line_loss_db: 1,
  data_rate_bps: 25e6,
  required_ebn0_db: 4,
  rx_gain_dbi: 45.63,
  system_noise_temp_k: 150,
  atmospheric_db: 1.5,
  polarization_db: 0.5,
  pointing_db: 0.5,
  implementation_db: 1.0,
  framing_efficiency: 0.85,
  acquisition_s: 45,
  setup_s: 30,
  required_gigabytes: 2,
  min_margin_db: 3,
  turnaround_s: 600,
};
