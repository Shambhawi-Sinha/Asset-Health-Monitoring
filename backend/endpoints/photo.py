"""
endpoints/photo.py — GET /api/photo
 
Backend-for-Frontend proxy for Fulcrum field inspection images.
 
Fulcrum's API requires an API key. This endpoint keeps that key server-side:
React calls /api/photo?record_id=xxx → FastAPI authenticates against Fulcrum
→ returns image bytes to the browser.
 
Two-step fetch pattern:
    Step 1: GET Fulcrum photo metadata → JSON with URLs (thumbnail/large/original)
    Step 2: GET the 'large' URL → actual image bytes
 
The React frontend never sees the Fulcrum API key or the original image URL.
 
Mock mode:
    Returns 404 for mock- prefixed record IDs (React InspectionImage component
    handles this gracefully by showing a coloured placeholder instead).
"""
 
import os
import requests
import urllib3
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
 
router = APIRouter()
 
FULCRUM_API_KEY  = os.getenv("FULCRUM_API_KEY")
FULCRUM_BASE_URL = os.getenv("FULCRUM_BASE_URL", "https://api.fulcrumapp.com/api/v2")
MOCK_MODE        = os.getenv("MOCK_MODE", "false").lower() == "true"
 
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
 
 
@router.get("/photo")
def get_photo(record_id: str = Query(..., description="Fulcrum photo record ID")):
    """
    Proxy a field inspection image from Fulcrum.
 
    In mock mode, returns 404 for mock- prefixed IDs so React renders
    its placeholder component instead.
    """
    # Mock mode — React InspectionImage handles 404 with a placeholder
    if MOCK_MODE or (record_id and record_id.startswith("mock-")):
        raise HTTPException(status_code=404, detail="Mock mode — no real image available")
 
    if not FULCRUM_API_KEY:
        raise HTTPException(status_code=500, detail="FULCRUM_API_KEY not configured")
 
    headers = {
        "X-ApiToken": FULCRUM_API_KEY,
        "Accept": "application/json",
    }
 
    # Step 1 — fetch photo metadata
    meta_url = f"{FULCRUM_BASE_URL}/photos/{record_id}.json"
    try:
        meta_resp = requests.get(meta_url, headers=headers, timeout=10, verify=False)
        meta_resp.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Fulcrum metadata fetch failed: {exc}")
 
    photo_meta = meta_resp.json()
    large_url = (
        photo_meta.get("photo", {}).get("large")
        or photo_meta.get("photo", {}).get("original")
    )
    if not large_url:
        raise HTTPException(status_code=404, detail="Image URL not found in Fulcrum response")
 
    # Step 2 — fetch image bytes
    try:
        img_resp = requests.get(large_url, headers=headers, timeout=15, verify=False)
        img_resp.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Fulcrum image fetch failed: {exc}")
 
    content_type = img_resp.headers.get("Content-Type", "image/jpeg")
    return Response(content=img_resp.content, media_type=content_type)
 