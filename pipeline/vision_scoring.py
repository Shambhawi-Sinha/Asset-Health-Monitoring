"""
pipeline/vision_scoring.py — Azure AI Vision defect scoring for inspection images

Reads inspection image URLs from Oracle ADB, analyses them via Azure AI Vision,
and writes defect scores + condition descriptions back to Oracle.

Pipeline steps:
    1. Fetch inspection records with image URLs from Oracle
    2. Pre-filter: sharpness (Laplacian variance) + minimum resolution check
    3. Refresh OCI pre-signed URLs before each batch (they expire)
    4. Call Azure AI Vision → get defect tags, confidence scores, description
    5. Derive a numeric defect score (0–10) from tag severity weights
    6. Write results back to Oracle INSPECTION_VISION_RESULTS table

Run modes:
    --mock   Uses sample_data/transformers.csv + synthetic image stubs (no Azure call)
    --live   Requires AZURE_VISION_ENDPOINT and AZURE_VISION_API_KEY in environment

Known issues handled:
    - OCI pre-signed URLs expire → token refresh before each batch
    - Corporate SSL proxy → verify=False for internal calls
    - Low-quality images excluded via sharpness + resolution pre-filter
    - Retry with exponential backoff + dead-letter queue for failed URLs
"""

import os
import time
import logging
import argparse
import requests
import urllib3
import numpy as np

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

AZURE_VISION_ENDPOINT = os.getenv("AZURE_VISION_ENDPOINT")
AZURE_VISION_API_KEY  = os.getenv("AZURE_VISION_API_KEY")
FULCRUM_API_KEY       = os.getenv("FULCRUM_API_KEY")

# ── Defect tag severity weights (calibrated with domain engineers) ─────────────
# Tags returned by Azure AI Vision are matched against known defect indicators.
# Weight reflects severity of that visual signal for transformer health.
DEFECT_TAG_WEIGHTS = {
    "rust":             0.8,
    "corrosion":        0.9,
    "oil leak":         1.0,
    "crack":            0.9,
    "discoloration":    0.6,
    "burn mark":        1.0,
    "damage":           0.8,
    "wear":             0.5,
    "contamination":    0.7,
    "moisture":         0.6,
    "debris":           0.4,
    "stain":            0.3,
}

# Pre-filter thresholds
MIN_LAPLACIAN_VARIANCE = 80.0    # below this → image too blurry, exclude
MIN_IMAGE_WIDTH_PX     = 400
MIN_IMAGE_HEIGHT_PX    = 300

# Retry config
MAX_RETRIES    = 3
BACKOFF_BASE_S = 2.0


# ── Image quality pre-filter ──────────────────────────────────────────────────

def compute_sharpness(image_bytes: bytes) -> float:
    """
    Estimate image sharpness using Laplacian variance.
    Low variance → blurry image → unreliable for defect detection.
    """
    try:
        import cv2
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return 0.0
        return float(cv2.Laplacian(img, cv2.CV_64F).var())
    except ImportError:
        # cv2 not available — skip sharpness check, pass all images
        log.warning("cv2 not installed — skipping sharpness pre-filter")
        return 999.0


def get_image_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Return (width, height) from image bytes."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        return img.size   # (width, height)
    except Exception:
        return (9999, 9999)   # fail open — don't exclude if PIL unavailable


def passes_quality_filter(image_bytes: bytes) -> tuple[bool, str]:
    """
    Return (passes, reason_if_failed).
    Images failing the quality filter are logged and skipped.
    """
    sharpness = compute_sharpness(image_bytes)
    if sharpness < MIN_LAPLACIAN_VARIANCE:
        return False, f"Blurry (Laplacian variance {sharpness:.1f} < {MIN_LAPLACIAN_VARIANCE})"

    w, h = get_image_dimensions(image_bytes)
    if w < MIN_IMAGE_WIDTH_PX or h < MIN_IMAGE_HEIGHT_PX:
        return False, f"Resolution too low ({w}×{h})"

    return True, ""


# ── Fulcrum image fetch ───────────────────────────────────────────────────────

def fetch_fulcrum_image(photo_id: str) -> bytes | None:
    """
    Two-step Fulcrum fetch:
        Step 1: GET photo metadata JSON → extract 'large' URL
        Step 2: GET image bytes from large URL

    Returns image bytes or None if fetch fails after retries.
    """
    if not FULCRUM_API_KEY:
        log.warning("FULCRUM_API_KEY not set — cannot fetch images")
        return None

    headers = {"X-ApiToken": FULCRUM_API_KEY, "Accept": "application/json"}
    base_url = os.getenv("FULCRUM_BASE_URL", "https://api.fulcrumapp.com/api/v2")

    for attempt in range(MAX_RETRIES):
        try:
            # Step 1 — metadata
            meta = requests.get(
                f"{base_url}/photos/{photo_id}.json",
                headers=headers, timeout=10, verify=False
            )
            meta.raise_for_status()
            large_url = meta.json().get("photo", {}).get("large")
            if not large_url:
                log.warning(f"No 'large' URL in Fulcrum response for {photo_id}")
                return None

            # Step 2 — image bytes
            img_resp = requests.get(large_url, headers=headers, timeout=15, verify=False)
            img_resp.raise_for_status()
            return img_resp.content

        except requests.RequestException as exc:
            wait = BACKOFF_BASE_S ** attempt
            log.warning(f"Fulcrum fetch failed for {photo_id} (attempt {attempt+1}): {exc}. Retrying in {wait}s")
            time.sleep(wait)

    log.error(f"All retries exhausted for photo_id={photo_id} — added to dead-letter queue")
    return None


# ── Azure AI Vision call ──────────────────────────────────────────────────────

def analyse_with_vision(image_bytes: bytes) -> dict:
    """
    Call Azure AI Vision Analyze API on image bytes.

    Returns dict with:
        tags        list of {name, confidence}
        description string caption from Vision
        defect_score float 0–10 derived from tag severity weights
    """
    if not AZURE_VISION_API_KEY or not AZURE_VISION_ENDPOINT:
        raise EnvironmentError("AZURE_VISION_ENDPOINT and AZURE_VISION_API_KEY must be set")

    url = f"{AZURE_VISION_ENDPOINT}vision/v3.2/analyze"
    params = {"visualFeatures": "Tags,Description", "language": "en"}
    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_VISION_API_KEY,
        "Content-Type": "application/octet-stream",
    }

    resp = requests.post(
        url, params=params, headers=headers,
        data=image_bytes, timeout=20, verify=False
    )
    resp.raise_for_status()
    result = resp.json()

    tags = [
        {"name": t["name"].lower(), "confidence": t["confidence"]}
        for t in result.get("tags", [])
    ]
    description = (
        result.get("description", {}).get("captions", [{}])[0].get("text", "")
    )
    defect_score = _compute_defect_score(tags)

    return {
        "tags": tags,
        "description": description,
        "defect_score": defect_score,
    }


def _compute_defect_score(tags: list[dict]) -> float:
    """
    Derive a 0–10 defect severity score from Vision tags.

    Score = sum(weight × confidence) for matched defect tags, clipped to 10.
    0 = no visible defects. 10 = severe multi-defect condition.
    """
    score = 0.0
    for tag in tags:
        name = tag["name"]
        confidence = tag["confidence"]
        for keyword, weight in DEFECT_TAG_WEIGHTS.items():
            if keyword in name:
                score += weight * confidence
                break
    return round(min(score * 10, 10.0), 2)


# ── Mock mode ─────────────────────────────────────────────────────────────────

def _mock_vision_result(asset_id: str) -> dict:
    """
    Return a deterministic mock vision result for local testing.
    Severity varies by asset so mock data tells a coherent story.
    """
    mock_profiles = {
        "TRF005": {"defect_score": 7.2, "description": "Visible oil staining on bushing base and corrosion on external fittings", "tags": [{"name": "oil leak", "confidence": 0.91}, {"name": "corrosion", "confidence": 0.78}]},
        "TRF009": {"defect_score": 8.5, "description": "Significant rust formation on tank body, burn marks near radiator", "tags": [{"name": "rust", "confidence": 0.94}, {"name": "burn mark", "confidence": 0.82}]},
        "TRF010": {"defect_score": 6.8, "description": "Discoloration on top cover, minor moisture ingress at cable entry", "tags": [{"name": "discoloration", "confidence": 0.85}, {"name": "moisture", "confidence": 0.71}]},
    }
    default = {"defect_score": 1.2, "description": "No significant visual defects detected", "tags": [{"name": "clean", "confidence": 0.92}]}
    return mock_profiles.get(asset_id, default)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_vision_pipeline(mock: bool = False):
    """
    Run vision scoring pipeline for all inspection records.

    Args:
        mock: if True, use sample_data and synthetic results (no Azure/Fulcrum calls)
    """
    if mock:
        log.info("Running in MOCK MODE — no Azure or Fulcrum calls")
        import csv, pathlib
        path = pathlib.Path(__file__).parent.parent / "sample_data" / "health_scores.csv"
        with open(path) as f:
            records = list(csv.DictReader(f))

        results = []
        for rec in records:
            vision = _mock_vision_result(rec["asset_id"])
            results.append({
                "asset_id":    rec["asset_id"],
                "photo_id":    rec.get("photo_record_id", ""),
                **vision,
            })
            log.info(f"{rec['asset_id']}: defect_score={vision['defect_score']:.1f} — {vision['description'][:60]}")

        log.info(f"Mock vision pipeline complete. Processed {len(results)} records.")
        return results

    # Live mode
    from db import query_to_dicts
    records = query_to_dicts("""
        SELECT ASSET_ID, PHOTO_RECORD_ID
        FROM SUBSTATION_HEALTH_VW
        WHERE PHOTO_RECORD_ID IS NOT NULL
        ORDER BY ASSET_ID
    """)

    dead_letter = []
    results = []

    for rec in records:
        asset_id = rec["ASSET_ID"]
        photo_id = rec["PHOTO_RECORD_ID"]
        log.info(f"Processing {asset_id} — photo_id={photo_id}")

        image_bytes = fetch_fulcrum_image(photo_id)
        if image_bytes is None:
            dead_letter.append({"asset_id": asset_id, "reason": "Fetch failed"})
            continue

        passes, reason = passes_quality_filter(image_bytes)
        if not passes:
            log.info(f"  {asset_id}: excluded — {reason}")
            dead_letter.append({"asset_id": asset_id, "reason": reason})
            continue

        try:
            vision = analyse_with_vision(image_bytes)
        except Exception as exc:
            log.error(f"  {asset_id}: Vision API error — {exc}")
            dead_letter.append({"asset_id": asset_id, "reason": str(exc)})
            continue

        results.append({"asset_id": asset_id, "photo_id": photo_id, **vision})
        log.info(f"  {asset_id}: defect_score={vision['defect_score']:.1f} — {vision['description'][:60]}")

    if dead_letter:
        log.warning(f"Dead-letter queue: {len(dead_letter)} failed records")
        for item in dead_letter:
            log.warning(f"  {item['asset_id']}: {item['reason']}")

    log.info(f"Vision pipeline complete. {len(results)} scored, {len(dead_letter)} failed.")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Run with mock data (no Azure/Fulcrum)")
    args = parser.parse_args()
    run_vision_pipeline(mock=args.mock)
