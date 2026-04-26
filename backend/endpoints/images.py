"""
endpoints/images.py — GET /api/images

Returns substation health records: asset metadata, computed health scores,
risk banding, and inspection image references.

Called by React on dashboard load as part of Promise.all parallel fetch.
"""

import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"


class SubstationRecord(BaseModel):
    asset_id: str
    substation_id: str
    substation_name: str
    health_score: float                  # 0–100, higher = healthier
    risk_band: str                       # GREEN | AMBER | RED
    mean_winding_temp: float | None
    hotspot_temp: float | None
    thermal_aging_factor: float | None   # FAA — dimensionless
    overload_severity: float | None      # ratio: actual / rated MVA
    tap_changer_stress: float | None     # cumulative daily tap ops
    load_temp_sensitivity: float | None  # Pearson r, load vs temp
    last_inspection_date: str | None
    photo_record_id: str | None          # Fulcrum record ID for /api/photo


@router.get("/images", response_model=list[SubstationRecord])
def get_images():
    """
    Fetch substation health records from Oracle ADB.

    In mock mode, returns records from sample_data/health_scores.csv.
    In live mode, queries the SUBSTATION_HEALTH_VW view.
    """
    if MOCK_MODE:
        return _load_mock_records()
    return _query_oracle()


def _query_oracle() -> list[dict]:
    from db import query_to_dicts
    sql = """
        SELECT
            ASSET_ID,
            SUBSTATION_ID,
            SUBSTATION_NAME,
            HEALTH_SCORE,
            RISK_BAND,
            MEAN_WINDING_TEMP,
            HOTSPOT_TEMP,
            THERMAL_AGING_FACTOR,
            OVERLOAD_SEVERITY,
            TAP_CHANGER_STRESS,
            LOAD_TEMP_SENSITIVITY,
            TO_CHAR(LAST_INSPECTION_DATE, 'YYYY-MM-DD') AS LAST_INSPECTION_DATE,
            PHOTO_RECORD_ID
        FROM SUBSTATION_HEALTH_VW
        ORDER BY HEALTH_SCORE ASC
    """
    try:
        return query_to_dicts(sql)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Oracle query failed: {exc}")


def _load_mock_records() -> list[dict]:
    import csv, pathlib
    path = pathlib.Path(__file__).parents[2] / "sample_data" / "health_scores.csv"
    with open(path) as f:
        reader = csv.DictReader(f)
        records = []
        for row in reader:
            records.append({
                "asset_id":              row["asset_id"],
                "substation_id":         row["substation_id"],
                "substation_name":       row["substation_name"],
                "health_score":          float(row["health_score"]),
                "risk_band":             row["risk_band"],
                "mean_winding_temp":     float(row["mean_winding_temp"]) if row.get("mean_winding_temp") else None,
                "hotspot_temp":          float(row["hotspot_temp"]) if row.get("hotspot_temp") else None,
                "thermal_aging_factor":  float(row["thermal_aging_factor"]) if row.get("thermal_aging_factor") else None,
                "overload_severity":     float(row["overload_severity"]) if row.get("overload_severity") else None,
                "tap_changer_stress":    float(row["tap_changer_stress"]) if row.get("tap_changer_stress") else None,
                "load_temp_sensitivity": float(row["load_temp_sensitivity"]) if row.get("load_temp_sensitivity") else None,
                "last_inspection_date":  row.get("last_inspection_date"),
                "photo_record_id":       row.get("photo_record_id"),
            })
    return records
