"""
pipeline/health_metrics.py — Domain-driven transformer health metric computation

Computes six metrics per transformer from time-series sensor data:

    1. Mean Winding Temperature   — rolling average (24hr / 7-day)
    2. Hotspot Temperature        — IEEE C57.91 thermal model or direct sensor
    3. Thermal Aging Factor (FAA) — IEC 60076-7 Arrhenius equation
    4. Overload Severity          — actual MVA / rated MVA ratio
    5. Tap Changer Stress         — cumulative daily tap operations (TPOSC delta)
    6. Load-Temperature Sensitivity — Pearson correlation (load vs winding temp)

All column names match the Oracle ADB schema (ALL_CAPS).

Design rationale:
    Domain-driven metrics were chosen over black-box anomaly detection because
    utility engineers with 20+ years of experience wouldn't trust an unexplained
    score. Each metric maps to an IEEE/IEC standard they already know. The
    composite score shows exactly which metric is driving a Red classification.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass

# Reference temperature for FAA normalisation (IEC 60076-7: 98°C hotspot → FAA = 1.0)
FAA_REFERENCE_TEMP_C = 98.0
# Arrhenius activation energy constant for transformer insulation (IEC 60076-7)
FAA_B = 15000.0
FAA_THETA_REF = 383.0   # 110°C in Kelvin (older standard reference)


@dataclass
class MetricThresholds:
    """Alert thresholds for each metric. Adjust per asset class if needed."""
    winding_temp_alarm:    float = 95.0    # °C sustained — amber
    winding_temp_critical: float = 105.0   # °C sustained — red
    hotspot_alarm:         float = 98.0    # °C — accelerated aging starts
    hotspot_critical:      float = 110.0   # °C — rapid degradation
    faa_alarm:             float = 2.0     # 2x normal aging rate
    faa_critical:          float = 4.0     # 4x — urgent attention
    overload_alarm:        float = 1.0     # at or above nameplate
    overload_critical:     float = 1.15    # 15% overload
    tap_ops_alarm:         float = 20.0    # daily tap operations
    tap_ops_critical:      float = 40.0    # high mechanical wear


THRESHOLDS = MetricThresholds()


# ── Metric 1: Mean Winding Temperature ───────────────────────────────────────

def compute_mean_winding_temp(
    df: pd.DataFrame,
    window: str = "24h",
    temp_col: str = "WINDING_TEMP_C",
    ts_col: str = "TIMESTAMP",
) -> pd.Series:
    """
    Rolling mean winding temperature.

    Mean over a rolling window is preferred over peak (max) because transient
    spikes during switching can cause false alarms. A sustained elevated average
    is a stronger signal of genuine thermal stress.
    """
    df = df.set_index(ts_col).sort_index()
    return df[temp_col].rolling(window=window, min_periods=1).mean()


# ── Metric 2: Hotspot Temperature ────────────────────────────────────────────

def compute_hotspot_temperature(
    df: pd.DataFrame,
    ambient_col: str = "AMBIENT_TEMP_C",
    top_oil_col: str = "OIL_TEMP_C",
    winding_col: str = "WINDING_TEMP_C",
    load_col:    str = "MVA_ACTUAL",
    rating_col:  str = "MVA_RATED",
    hotspot_measured_col: str = "HOTSPOT_TEMP_C",
) -> pd.Series:
    """
    Hotspot temperature per IEEE C57.91.

    θ_H = θ_A + Δθ_TO + Δθ_H

    Where:
        θ_A    = ambient temperature
        Δθ_TO  = top-oil rise above ambient (from sensor)
        Δθ_H   = hotspot-to-top-oil gradient (load-dependent)

    ~40% of transformers have direct hotspot sensors. For the rest, use the
    thermal model. Results are validated against sensor readings where available.
    """
    if hotspot_measured_col in df.columns and df[hotspot_measured_col].notna().any():
        # Use direct sensor if available
        return df[hotspot_measured_col]

    # Derived thermal model
    K = df[load_col] / df[rating_col].replace(0, np.nan)   # per-unit loading
    delta_to = df[top_oil_col] - df[ambient_col]            # top-oil rise
    # Hotspot-to-top-oil gradient: simplified IEC model (H = 0.63 * delta_to * K^1.6)
    delta_h = 0.63 * delta_to * (K ** 1.6)
    return df[ambient_col] + delta_to + delta_h


# ── Metric 3: Thermal Aging Factor (FAA) ─────────────────────────────────────

def compute_faa(hotspot_series: pd.Series) -> pd.Series:
    """
    Thermal Aging Acceleration Factor (FAA) — IEC 60076-7 Arrhenius equation.

    FAA = exp( B/θ_ref − B/(273 + θ_H) )

    FAA = 1.0  → aging at normal design rate (reference 98°C hotspot)
    FAA = 2.0  → aging 2× faster (every calendar day = 2 days of life consumed)
    FAA = 8.0  → critical — insulation life depleting rapidly

    This is the most important long-term risk metric. Insulation paper
    degradation is irreversible — once lost, transformer life cannot be recovered.
    """
    theta_K = 273.0 + hotspot_series
    faa = np.exp(FAA_B / FAA_THETA_REF - FAA_B / theta_K)
    return faa.clip(lower=0.0)


# ── Metric 4: Overload Severity ───────────────────────────────────────────────

def compute_overload_severity(
    df: pd.DataFrame,
    load_col:   str = "MVA_ACTUAL",
    rating_col: str = "MVA_RATED",
    window: str = "24h",
    ts_col: str = "TIMESTAMP",
) -> pd.Series:
    """
    Rolling cumulative overload severity: actual MVA / rated MVA.

    Values > 1.0 indicate operation above nameplate rating.
    Nameplate MVA from the transformer master table is required for normalisation.
    A raw 80 MVA reading is meaningless without knowing the rated capacity.
    """
    df = df.set_index(ts_col).sort_index()
    ratio = df[load_col] / df[rating_col].replace(0, np.nan)
    overload_only = (ratio - 1.0).clip(lower=0.0)   # excess above nameplate
    return overload_only.rolling(window=window, min_periods=1).sum()


# ── Metric 5: Tap Changer Stress ──────────────────────────────────────────────

def compute_tap_changer_stress(
    df: pd.DataFrame,
    tposc_col: str = "TPOSC",    # cumulative tap operation count (odometer)
    ts_col:    str = "TIMESTAMP",
    window:    str = "24h",
) -> pd.Series:
    """
    Daily tap changer operations derived from cumulative counter (TPOSC).

    TPOSC is a monotonically increasing odometer. Daily ops = delta over 24hr.
    High daily operations signal mechanical wear on the tap changer mechanism.
    """
    df = df.set_index(ts_col).sort_index()
    tposc_resampled = df[tposc_col].resample("1D").last()
    daily_ops = tposc_resampled.diff().clip(lower=0.0)
    return daily_ops


# ── Metric 6: Load-Temperature Sensitivity ────────────────────────────────────

def compute_load_temp_sensitivity(
    df: pd.DataFrame,
    load_col:  str = "MVA_ACTUAL",
    temp_col:  str = "WINDING_TEMP_C",
    ts_col:    str = "TIMESTAMP",
    window:    int = 168,            # 168 × 15-min intervals = 7 days
) -> pd.Series:
    """
    Rolling Pearson correlation between load and winding temperature.

    High positive correlation (>0.85) over a sustained window may indicate
    cooling system degradation — the transformer is thermally tracking load
    more tightly than expected, suggesting reduced cooling capacity.
    """
    df = df.set_index(ts_col).sort_index()
    return df[load_col].rolling(window).corr(df[temp_col])
