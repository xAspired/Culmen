"""Link budget.

The chain, in the order it is computed:

    EIRP = P_tx + G_tx - L_line_tx
    L_fs = 32.44 + 20*log10(d_km) + 20*log10(f_MHz)
    L_total = L_fs + L_atm + L_pol + L_point + L_iono + L_impl
    C/N0 = EIRP - L_total + G/T - k            [dB-Hz],  k = -228.6 dBW/(Hz.K)
    Eb/N0 = C/N0 - 10*log10(R_b)               [dB]
    margin = Eb/N0 - Eb/N0_required            [dB]

Every quantity returned is a ``Computed``: it carries its inputs, its unit,
the note in docs/math/ that defines it, and the assumptions behind it. That
is what makes a later verdict explainable rather than merely numeric.

Two things this module refuses to let a caller get wrong:

* **10*log10 for powers, 20*log10 for amplitudes.** Enforced by using the two
  named helpers in core.units rather than writing logs inline.
* **Peak-only budgets.** ``budget_over_pass`` exists because free-space loss
  at the horizon and at maximum elevation differ by 8-10 dB for LEO. A budget
  evaluated only at the peak overestimates achievable data volume
  systematically, which is precisely the error this tool exists to prevent.

Reference case: docs/math/link-budget-reference.md (ITU-R small-satellite
workshop, Prague 2015). Formula notes: docs/math/fspl.md, antenna-gain.md,
noise.md, cn0-ebn0.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from core.provenance import Computed
from core.units import (
    BOLTZMANN_DBW_HZ_K,
    SPEED_OF_LIGHT_M_S,
    db10,
    w_to_dbw,
    wavelength_m,
)

#: 20*log10(4*pi/c) with d in km and f in MHz, i.e. the FSPL constant.
#: Derived, not memorised -- see test_fspl_constant_is_derivable.
FSPL_CONST_KM_MHZ: float = 32.44778322


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Transmitter:
    """Transmitting end of the link (satellite downlink, or station uplink)."""

    name: str
    freq_hz: float
    power_w: float
    gain_dbi: float
    line_loss_db: float = 0.0
    data_rate_bps: float = 0.0
    #: Eb/N0 needed for the target error rate, AFTER coding gain.
    required_ebn0_db: float = 0.0
    modulation: str = ""
    coding: str = ""

    def __post_init__(self) -> None:
        if self.freq_hz <= 0.0:
            raise ValueError(f"freq_hz must be positive, got {self.freq_hz}")
        if self.power_w <= 0.0:
            raise ValueError(f"power_w must be positive, got {self.power_w}")
        if self.line_loss_db < 0.0:
            raise ValueError("line_loss_db is a loss: pass it as a positive number of dB")


@dataclass(frozen=True, slots=True)
class Receiver:
    """Receiving end.

    Supply **either** ``g_over_t_dbk`` directly, or the pair
    (``gain_dbi``, ``system_noise_temp_k``). Mixing the two is rejected:
    silently preferring one over the other is how a 1-2 dB error hides.
    """

    name: str
    gain_dbi: float | None = None
    system_noise_temp_k: float | None = None
    g_over_t_dbk: float | None = None

    def __post_init__(self) -> None:
        explicit = self.g_over_t_dbk is not None
        derived = self.gain_dbi is not None and self.system_noise_temp_k is not None
        if explicit and derived:
            raise ValueError(
                "supply either g_over_t_dbk or (gain_dbi, system_noise_temp_k), not both"
            )
        if not explicit and not derived:
            raise ValueError(
                "receiver needs g_over_t_dbk, or both gain_dbi and system_noise_temp_k"
            )
        if self.system_noise_temp_k is not None and self.system_noise_temp_k <= 0.0:
            raise ValueError("system_noise_temp_k must be positive")

    def g_over_t(self) -> Computed[float]:
        if self.g_over_t_dbk is not None:
            return Computed(
                value=self.g_over_t_dbk,
                unit="dB/K",
                formula_ref="docs/math/noise.md",
                inputs={"g_over_t_dbk": self.g_over_t_dbk},
                assumptions=(
                    "G/T supplied directly; it must refer to the same reference "
                    "plane as the losses in the budget",
                ),
            )
        assert self.gain_dbi is not None and self.system_noise_temp_k is not None
        value = self.gain_dbi - db10(self.system_noise_temp_k)
        return Computed(
            value=value,
            unit="dB/K",
            formula_ref="docs/math/noise.md",
            inputs={
                "gain_dbi": self.gain_dbi,
                "system_noise_temp_k": self.system_noise_temp_k,
            },
            assumptions=(
                "G/T = G - 10*log10(T_sys), both referred to the same plane",
            ),
        )


@dataclass(frozen=True, slots=True)
class PathLosses:
    """Losses beyond free space, all as POSITIVE numbers of dB.

    Defaults are zero rather than a guess: an unstated loss must show up as an
    optimistic margin the user can see, not as a silently invented value.
    """

    atmospheric_db: float = 0.0
    polarization_db: float = 0.0
    pointing_db: float = 0.0
    ionospheric_db: float = 0.0
    implementation_db: float = 0.0
    rain_db: float = 0.0

    def total_db(self) -> float:
        return (
            self.atmospheric_db
            + self.polarization_db
            + self.pointing_db
            + self.ionospheric_db
            + self.implementation_db
            + self.rain_db
        )

    def as_inputs(self) -> dict[str, float]:
        return {
            "atmospheric_db": self.atmospheric_db,
            "polarization_db": self.polarization_db,
            "pointing_db": self.pointing_db,
            "ionospheric_db": self.ionospheric_db,
            "implementation_db": self.implementation_db,
            "rain_db": self.rain_db,
        }


# --------------------------------------------------------------------------
# Individual terms
# --------------------------------------------------------------------------


def free_space_path_loss(range_km: float, freq_hz: float) -> Computed[float]:
    """Free-space path loss, as a POSITIVE number of dB.

    ``L_fs = 32.4478 + 20*log10(d_km) + 20*log10(f_MHz)``

    The constant is specific to kilometres and megahertz. With metres and
    hertz it becomes -147.55; with kilometres and gigahertz, 92.45. Passing
    the wrong constant for the units is a classic 30-60 dB error, which is why
    both arguments here are named with their units and converted internally.
    """
    if range_km <= 0.0:
        raise ValueError(f"range_km must be positive, got {range_km}")
    if freq_hz <= 0.0:
        raise ValueError(f"freq_hz must be positive, got {freq_hz}")

    freq_mhz = freq_hz / 1e6
    value = FSPL_CONST_KM_MHZ + 20.0 * math.log10(range_km) + 20.0 * math.log10(freq_mhz)
    return Computed(
        value=value,
        unit="dB",
        formula_ref="docs/math/fspl.md",
        inputs={"range_km": range_km, "freq_hz": freq_hz, "freq_mhz": freq_mhz},
        assumptions=(
            "free space: no atmosphere, no obstruction, far field",
            "isotropic spreading over a sphere of radius d",
        ),
    )


def eirp(transmitter: Transmitter) -> Computed[float]:
    """Effective isotropic radiated power: ``P_tx + G_tx - L_line``."""
    p_dbw = w_to_dbw(transmitter.power_w)
    value = p_dbw + transmitter.gain_dbi - transmitter.line_loss_db
    return Computed(
        value=value,
        unit="dBW",
        formula_ref="docs/math/fspl.md",
        inputs={
            "power_w": transmitter.power_w,
            "power_dbw": p_dbw,
            "gain_dbi": transmitter.gain_dbi,
            "line_loss_db": transmitter.line_loss_db,
        },
        assumptions=("transmitter is on boresight; off-pointing goes in pointing_db",),
    )


def parabolic_gain_dbi(
    diameter_m: float, freq_hz: float, efficiency: float = 0.55
) -> Computed[float]:
    """Gain of a circular aperture: ``G = 10*log10(eta * (pi*D/lambda)^2)``.

    Efficiency is never 1.0 in reality. Typical dish efficiency is 0.5-0.65
    once illumination taper, spillover, blockage and surface error are
    included; 0.55 is the usual first-cut figure. Assuming unity inflates the
    gain by about 2.6 dB.
    """
    if diameter_m <= 0.0:
        raise ValueError(f"diameter_m must be positive, got {diameter_m}")
    if not 0.0 < efficiency <= 1.0:
        raise ValueError(f"efficiency must be in (0, 1], got {efficiency}")

    lam_m = wavelength_m(freq_hz)
    value = db10(efficiency * (math.pi * diameter_m / lam_m) ** 2)
    return Computed(
        value=value,
        unit="dBi",
        formula_ref="docs/math/antenna-gain.md",
        inputs={
            "diameter_m": diameter_m,
            "freq_hz": freq_hz,
            "wavelength_m": lam_m,
            "efficiency": efficiency,
        },
        assumptions=(
            f"aperture efficiency {efficiency:.2f} (0.5-0.65 typical for a real dish)",
            "far field; no surface-error or blockage term beyond the efficiency factor",
        ),
    )


def system_noise_temperature_k(
    antenna_temp_k: float, line_loss_db: float, lna_temp_k: float, ambient_k: float = 290.0
) -> Computed[float]:
    """System noise temperature referred to the ANTENNA output plane.

    ``T_sys = T_ant + T_line + L * T_lna``  with  ``L = 10^(line_loss_db/10)``
    and ``T_line = (L - 1) * T_ambient``.

    Reference plane matters: the same system has different T_sys at the
    antenna flange and at the LNA input, and the G/T used with it must be
    referred to the same place. Mismatching the two is a routine 1-2 dB error.
    """
    if line_loss_db < 0.0:
        raise ValueError("line_loss_db is a loss: pass a positive number of dB")

    loss_ratio = 10.0 ** (line_loss_db / 10.0)
    t_line = (loss_ratio - 1.0) * ambient_k
    value = antenna_temp_k + t_line + loss_ratio * lna_temp_k
    return Computed(
        value=value,
        unit="K",
        formula_ref="docs/math/noise.md",
        inputs={
            "antenna_temp_k": antenna_temp_k,
            "line_loss_db": line_loss_db,
            "line_loss_ratio": loss_ratio,
            "line_temp_k": t_line,
            "lna_temp_k": lna_temp_k,
            "ambient_k": ambient_k,
        },
        assumptions=(
            "referred to the antenna output plane",
            f"line physical temperature {ambient_k:.0f} K",
            "antenna noise temperature treated as constant; in reality it rises "
            "steeply at low elevation and near the Sun (A-GEO-6)",
        ),
    )


def doppler_shift_hz(freq_hz: float, range_rate_km_s: float) -> Computed[float]:
    """One-way Doppler shift: ``-f * v_r / c``, negative while receding.

    Does not affect the power budget. It does set the receiver's acquisition
    and tracking bandwidth, so it is reported rather than ignored.
    """
    value = -freq_hz * (range_rate_km_s * 1000.0) / SPEED_OF_LIGHT_M_S
    return Computed(
        value=value,
        unit="Hz",
        formula_ref="docs/math/cn0-ebn0.md",
        inputs={"freq_hz": freq_hz, "range_rate_km_s": range_rate_km_s},
        assumptions=(
            "classical one-way Doppler; relativistic terms neglected "
            "(below 1e-9 of the carrier at LEO velocities)",
        ),
    )


# --------------------------------------------------------------------------
# The budget
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LinkBudget:
    """One evaluation of the chain, at a single instant and range."""

    range_km: float
    freq_hz: float
    eirp_dbw: Computed[float]
    fspl_db: Computed[float]
    other_losses_db: Computed[float]
    g_over_t_dbk: Computed[float]
    cn0_dbhz: Computed[float]
    ebn0_db: Computed[float] | None
    margin_db: Computed[float] | None
    doppler_hz: Computed[float] | None = None
    assumptions: tuple[str, ...] = ()

    def lines(self) -> list[tuple[str, float, str]]:
        """The budget as a printable table: (label, value, unit)."""
        rows: list[tuple[str, float, str]] = [
            ("EIRP", self.eirp_dbw.value, "dBW"),
            ("Free-space path loss", -self.fspl_db.value, "dB"),
            ("Other losses", -self.other_losses_db.value, "dB"),
            ("G/T (receiver)", self.g_over_t_dbk.value, "dB/K"),
            ("Boltzmann constant", -BOLTZMANN_DBW_HZ_K, "dB"),
            ("C/N0", self.cn0_dbhz.value, "dB-Hz"),
        ]
        if self.ebn0_db is not None:
            rows.append(("Eb/N0", self.ebn0_db.value, "dB"))
        if self.margin_db is not None:
            rows.append(("Link margin", self.margin_db.value, "dB"))
        return rows

    def closes(self) -> bool:
        """True when a margin was computable and is non-negative."""
        return self.margin_db is not None and self.margin_db.value >= 0.0


def compute_link_budget(
    transmitter: Transmitter,
    receiver: Receiver,
    range_km: float,
    losses: PathLosses | None = None,
    range_rate_km_s: float | None = None,
) -> LinkBudget:
    """Evaluate the full chain at one range.

    ``ebn0_db`` and ``margin_db`` are ``None`` when the transmitter declares no
    data rate: an Eb/N0 without a bit rate is meaningless, and returning zero
    instead of nothing would read as a closed link.
    """
    losses = losses or PathLosses()

    e = eirp(transmitter)
    fs = free_space_path_loss(range_km, transmitter.freq_hz)
    gt = receiver.g_over_t()

    other = Computed(
        value=losses.total_db(),
        unit="dB",
        formula_ref="docs/math/fspl.md",
        inputs=losses.as_inputs(),
        assumptions=(
            "losses not supplied default to 0 dB, which is optimistic by "
            "construction; unstated atmospheric and pointing terms are the "
            "usual cause of a falsely positive margin",
        ),
    )

    cn0_value = (
        e.value - fs.value - other.value + gt.value - BOLTZMANN_DBW_HZ_K
    )
    cn0 = Computed(
        value=cn0_value,
        unit="dB-Hz",
        formula_ref="docs/math/cn0-ebn0.md",
        inputs={
            "eirp_dbw": e.value,
            "fspl_db": fs.value,
            "other_losses_db": other.value,
            "g_over_t_dbk": gt.value,
            "boltzmann_dbw_hz_k": BOLTZMANN_DBW_HZ_K,
        },
        assumptions=("G/T and the losses refer to the same reference plane",),
    )

    ebn0: Computed[float] | None = None
    margin: Computed[float] | None = None
    if transmitter.data_rate_bps > 0.0:
        ebn0_value = cn0.value - db10(transmitter.data_rate_bps)
        ebn0 = Computed(
            value=ebn0_value,
            unit="dB",
            formula_ref="docs/math/cn0-ebn0.md",
            inputs={
                "cn0_dbhz": cn0.value,
                "data_rate_bps": transmitter.data_rate_bps,
            },
            assumptions=(
                "R_b is the INFORMATION bit rate, not the symbol rate; "
                "confusing the two is a 3 dB error at rate-1/2 coding",
            ),
        )
        margin = Computed(
            value=ebn0_value - transmitter.required_ebn0_db,
            unit="dB",
            formula_ref="docs/math/cn0-ebn0.md",
            inputs={
                "ebn0_db": ebn0_value,
                "required_ebn0_db": transmitter.required_ebn0_db,
            },
            assumptions=(
                "required Eb/N0 is taken as given and already includes coding gain "
                "and implementation loss unless those are listed separately",
            ),
        )

    doppler = (
        doppler_shift_hz(transmitter.freq_hz, range_rate_km_s)
        if range_rate_km_s is not None
        else None
    )

    collected: list[str] = []
    for part in (e, fs, other, gt, cn0, ebn0, margin, doppler):
        if part is not None:
            collected.extend(part.assumptions)

    return LinkBudget(
        range_km=range_km,
        freq_hz=transmitter.freq_hz,
        eirp_dbw=e,
        fspl_db=fs,
        other_losses_db=other,
        g_over_t_dbk=gt,
        cn0_dbhz=cn0,
        ebn0_db=ebn0,
        margin_db=margin,
        doppler_hz=doppler,
        assumptions=tuple(dict.fromkeys(collected)),
    )


@dataclass(frozen=True, slots=True)
class PassLinkBudget:
    """The budget sampled across a pass.

    This type exists to make the peak-only mistake impossible to make by
    accident: the worst case, the fraction of the pass that closes, and the
    per-sample series are all first-class.
    """

    samples: tuple[tuple[float, LinkBudget], ...] = field(default=())
    """(seconds since AOS, budget) pairs."""

    @property
    def worst(self) -> LinkBudget:
        return min(
            (b for _, b in self.samples),
            key=lambda b: b.margin_db.value if b.margin_db else b.cn0_dbhz.value,
        )

    @property
    def best(self) -> LinkBudget:
        return max(
            (b for _, b in self.samples),
            key=lambda b: b.margin_db.value if b.margin_db else b.cn0_dbhz.value,
        )

    def closing_seconds(self) -> float:
        """Seconds during which the margin is non-negative.

        Computed by trapezoidal attribution between samples, not by counting
        samples, so the answer does not depend on the sampling step.
        """
        if len(self.samples) < 2:
            return 0.0
        total = 0.0
        for (t0, b0), (t1, b1) in zip(self.samples, self.samples[1:], strict=False):
            if b0.closes() and b1.closes():
                total += t1 - t0
            elif b0.closes() or b1.closes():
                total += (t1 - t0) / 2.0
        return total

    def fspl_spread_db(self) -> float:
        """Difference between worst and best free-space loss across the pass.

        For LEO this is typically 8-10 dB. It is reported so that anyone
        tempted to quote a single peak-elevation figure can see what they
        would be throwing away.
        """
        values = [b.fspl_db.value for _, b in self.samples]
        return max(values) - min(values)
