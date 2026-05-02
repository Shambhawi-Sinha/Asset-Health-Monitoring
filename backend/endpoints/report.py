"""
endpoints/report.py — GET /api/report
 
Returns work order summaries per asset. Used by React for the substation
detail view — shows maintenance history, failure codes, open emergency WOs.
 
Called in parallel with /api/images via Promise.all in the React dashboard.
"""
 
import os
import json
import pathlib
from typing import Optional, List
from collections import defaultdict, Counter
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
 
router = APIRouter()
 
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"
 
 
class WorkOrderSummary(BaseModel):
    asset_id: str
    substation_id: str
    total_work_orders: int
    open_emergency_wos: int                    # unresolved emergency orders — risk signal
    last_wo_date: Optional[str] = None
    last_wo_type: Optional[str] = None         # PREVENTIVE | CORRECTIVE | EMERGENCY
    last_wo_description: Optional[str] = None
    dominant_failure_code: Optional[str] = None
 
 
@router.get("/report", response_model=List[WorkOrderSummary])
def get_report():
    if MOCK_MODE:
        return _load_mock_report()
    return _query_oracle()
 
 
def _query_oracle() -> List[dict]:
    from db import query_to_dicts
    sql = """
        SELECT
            w.ASSET_ID,
            w.SUBSTATION_ID,
            COUNT(*)                                        AS TOTAL_WORK_ORDERS,
            SUM(CASE WHEN w.WO_TYPE = 'EMERGENCY'
                      AND w.COMPLETION_DATE IS NULL
                     THEN 1 ELSE 0 END)                    AS OPEN_EMERGENCY_WOS,
            TO_CHAR(MAX(w.CREATED_DATE), 'YYYY-MM-DD')     AS LAST_WO_DATE,
            MAX(w.WO_TYPE) KEEP (
                DENSE_RANK LAST ORDER BY w.CREATED_DATE
            )                                               AS LAST_WO_TYPE,
            MAX(w.DESCRIPTION) KEEP (
                DENSE_RANK LAST ORDER BY w.CREATED_DATE
            )                                               AS LAST_WO_DESCRIPTION,
            STATS_MODE(w.FAILURE_CODE)                      AS DOMINANT_FAILURE_CODE
        FROM WORK_ORDERS w
        GROUP BY w.ASSET_ID, w.SUBSTATION_ID
        ORDER BY OPEN_EMERGENCY_WOS DESC, TOTAL_WORK_ORDERS DESC
    """
    try:
        return query_to_dicts(sql)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Oracle query failed: {exc}")
 
 
def _load_mock_report() -> List[WorkOrderSummary]:
    path = pathlib.Path(__file__).parents[2] / "sample_data" / "work_orders.json"
    with open(path) as f:
        raw = json.load(f)
 
    agg = defaultdict(lambda: {
        "total_work_orders": 0,
        "open_emergency_wos": 0,
        "last_wo_date": None,
        "last_wo_type": None,
        "last_wo_description": None,
        "failure_codes": [],
    })
 
    for wo in raw:
        key = wo["asset_id"]
        a = agg[key]
        a["asset_id"] = wo["asset_id"]
        a["substation_id"] = wo["substation_id"]
        a["total_work_orders"] += 1
        if wo["wo_type"] == "EMERGENCY" and not wo.get("completion_date"):
            a["open_emergency_wos"] += 1
        if not a["last_wo_date"] or wo["created_date"] > a["last_wo_date"]:
            a["last_wo_date"] = wo["created_date"]
            a["last_wo_type"] = wo["wo_type"]
            a["last_wo_description"] = wo["description"]
        if wo.get("failure_code"):
            a["failure_codes"].append(wo["failure_code"])
 
    results = []
    for a in agg.values():
        dominant = Counter(a["failure_codes"]).most_common(1)
        results.append(WorkOrderSummary(
            asset_id=a["asset_id"],
            substation_id=a["substation_id"],
            total_work_orders=a["total_work_orders"],
            open_emergency_wos=a["open_emergency_wos"],
            last_wo_date=a["last_wo_date"],
            last_wo_type=a["last_wo_type"],
            last_wo_description=a["last_wo_description"],
            dominant_failure_code=dominant[0][0] if dominant else None,
        ))
    return results
 