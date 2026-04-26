"""
pipeline/composite_score.py — Composite 0–100 health score + risk banding

Aggregates six domain metrics into a single transformer health score.

Score interpretation:
    100   = perfect health (all metrics nominal)
    0     = critical failure state
    > 70  = GREEN  — healthy, normal monitoring cadence
    40–70 = AMBER  — at risk, increase inspection frequency
    < 40  = RED    — critical, immediate engineering attention

Design decision — weighted sum over ML model:
    The weighted sum is transparent. Engineers can see exactly which metric
    drove a score change. A black-box model (even if slightly more accurate)
    would not have received engineering buy-in from the utility team.
    Each metric weight was calibrated with domain experts against historical
    failure data.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class MetricWeights:
    """
    Contribution of each metric to the composite penalty.
    Weights are normalised to sum to 1.0.
    """
    thermal_aging:        float = 0.30   # FAA — highest weight: irreversible damage
    hotspot_temp:         float = 0.25   # direct insulation stress
    overload_severity:    float = 0.20   # excess load above nameplate
    tap_changer_stress:   float = 0.10   # mechanical wear
    mean_winding_temp:    float = 0.10   # corroborative thermal signal
    load_temp_sensitivity: float = 0.05  # cooling system degradation signal

    def __post_init__(self):
        total = sum(self.__dict__.values())
        assert abs(total - 1.0) < 1e-6, f"Weights must sum to 1.0, got {total}"


WEIGHTS = MetricWeights()

# Normalisation ranges — maps raw metric values to 0–1 penalty
# (0 = no penalty, 1 = maximum penalty)
NORM_RANGES = {
    "faa":                 (1.0,  8.0),   # FAA: normal to critical
    "hotspot_temp":        (70.0, 140.0), # °C: nominal to failure threshold
    "overload_severity":   (0.0,  0.5),   # cumulative overload score
    "tap_changer_stress":  (0.0,  60.0),  # daily tap operations
    "mean_winding_temp":   (65.0, 110.0), # °C rolling average
    "load_temp_sensitivity": (0.5, 1.0),  # Pearson r: moderate to extreme coupling
}


def normalise_metric(value: float, metric_key: str) -> float:
    """
    Normalise a raw metric value to a [0, 1] penalty score.
    0 = healthy (no penalty), 1 = critical (maximum penalty).
    """
    low, high = NORM_RANGES[metric_key]
    if high == low:
        return 0.0
    penalty = (value - low) / (high - low)
    return float(np.clip(penalty, 0.0, 1.0))


def compute_composite_score(metrics: dict) -> float:
    """
    Compute the composite health score (0–100) from a dict of metric values.

    Score = 100 − (weighted sum of normalised penalties × 100)

    Args:
        metrics: dict with keys matching MetricWeights fields, raw metric values

    Returns:
        float in [0, 100] — higher is healthier
    """
    penalty_keys = {
        "thermal_aging":         ("faa",                  metrics.get("thermal_aging_factor")),
        "hotspot_temp":          ("hotspot_temp",          metrics.get("hotspot_temp")),
        "overload_severity":     ("overload_severity",     metrics.get("overload_severity")),
        "tap_changer_stress":    ("tap_changer_stress",    metrics.get("tap_changer_stress")),
        "mean_winding_temp":     ("mean_winding_temp",     metrics.get("mean_winding_temp")),
        "load_temp_sensitivity": ("load_temp_sensitivity", metrics.get("load_temp_sensitivity")),
    }

    weights = WEIGHTS.__dict__
    total_penalty = 0.0

    for weight_key, (norm_key, raw_value) in penalty_keys.items():
        if raw_value is None or np.isnan(raw_value):
            continue   # skip missing metrics — don't penalise for missing sensors
        penalty = normalise_metric(float(raw_value), norm_key)
        total_penalty += weights[weight_key] * penalty

    score = 100.0 * (1.0 - total_penalty)
    return round(float(np.clip(score, 0.0, 100.0)), 2)


def assign_risk_band(score: float) -> str:
    """
    Map a composite health score to a risk band label.

        GREEN  → score > 70
        AMBER  → 40 < score ≤ 70
        RED    → score ≤ 40
    """
    if score > 70:
        return "GREEN"
    elif score > 40:
        return "AMBER"
    else:
        return "RED"


def score_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply composite scoring to a DataFrame of pre-computed metrics.

    Input columns expected:
        thermal_aging_factor, hotspot_temp, overload_severity,
        tap_changer_stress, mean_winding_temp, load_temp_sensitivity

    Output columns added:
        health_score (float 0–100), risk_band (GREEN/AMBER/RED)
    """
    df = df.copy()
    df["health_score"] = df.apply(
        lambda row: compute_composite_score(row.to_dict()), axis=1
    )
    df["risk_band"] = df["health_score"].apply(assign_risk_band)
    return df
