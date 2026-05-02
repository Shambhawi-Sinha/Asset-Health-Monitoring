"""
pipeline/rag_indexing.py — Build the Azure AI Search vector index for RAG

Reads work order descriptions, inspection notes, and asset history from Oracle
ADB, chunks the text, embeds each chunk via Azure OpenAI text-embedding-ada-002,
and upserts to the Azure AI Search index.

This is a one-time (or periodic refresh) operation — not a real-time pipeline.
The index built here is what /api/chat queries at runtime.

Index schema (created automatically if it doesn't exist):
    id          Edm.String  — chunk ID (asset_id + source + chunk_index)
    content     Edm.String  — text chunk (searchable)
    title       Edm.String  — source document label (filterable)
    asset_id    Edm.String  — filterable for asset-specific queries
    embedding   Collection(Edm.Single) — 1536-dim vector (text-embedding-ada-002)

Run modes:
    --mock   Uses sample_data/work_orders.json (no Oracle or Azure calls)
    --live   Requires OCI + Azure credentials in environment
"""

import os
import json
import time
import hashlib
import logging
import argparse
import requests
import urllib3
from openai import AzureOpenAI

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
SEARCH_API_KEY  = os.getenv("AZURE_SEARCH_API_KEY")
SEARCH_INDEX    = os.getenv("AZURE_SEARCH_INDEX_NAME", "substation-docs")
SEARCH_API_VER  = "2023-11-01"

EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_EMBED", "text-embedding-ada-002")
EMBED_DIM        = 1536

CHUNK_SIZE       = 400    # characters per chunk
CHUNK_OVERLAP    = 80     # overlap between consecutive chunks
BATCH_SIZE       = 16     # embeddings per API call (cost + rate limit control)


# ── Azure OpenAI client ───────────────────────────────────────────────────────
def _get_openai_client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    )


# ── Text chunking ─────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping character-level chunks.
    Overlap preserves context across chunk boundaries.
    """
    if not text or not text.strip():
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start += chunk_size - overlap
    return [c for c in chunks if len(c) > 20]   # drop tiny tail chunks


def make_chunk_id(asset_id: str, source: str, index: int) -> str:
    raw = f"{asset_id}::{source}::{index}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


# ── Document preparation ──────────────────────────────────────────────────────

def prepare_documents_from_work_orders(work_orders: list[dict]) -> list[dict]:
    """
    Convert work order records into indexable text chunks.

    Each WO description becomes one or more chunks. The title field identifies
    the source so the RAG answer can cite it properly.
    """
    docs = []
    for wo in work_orders:
        asset_id = wo.get("asset_id", "UNKNOWN")
        text = (
            f"Asset: {asset_id} | Substation: {wo.get('substation_id', '')} | "
            f"Type: {wo.get('wo_type', '')} | Priority: {wo.get('priority', '')} | "
            f"Failure Code: {wo.get('failure_code', 'N/A')} | "
            f"Date: {wo.get('created_date', '')} | "
            f"Status: {'Open' if not wo.get('completion_date') else 'Closed'} | "
            f"Description: {wo.get('description', '')}"
        )
        title = f"Work Order {wo.get('wo_id', '')} — {asset_id}"

        for i, chunk in enumerate(chunk_text(text)):
            docs.append({
                "id":       make_chunk_id(asset_id, wo.get("wo_id", "wo"), i),
                "content":  chunk,
                "title":    title,
                "asset_id": asset_id,
            })
    return docs


def prepare_documents_from_health_scores(health_records: list[dict]) -> list[dict]:
    """
    Convert health score records into indexable text for RAG context.

    Engineers asking "why is TRF045 in the Red band?" need context that
    includes the metric values and their interpretation.
    """
    docs = []
    for rec in health_records:
        asset_id = rec.get("asset_id", "UNKNOWN")
        faa = rec.get("thermal_aging_factor")
        faa_str = f"{faa:.2f} (aging {faa:.1f}× faster than normal)" if faa else "N/A"

        text = (
            f"Asset {asset_id} at {rec.get('substation_name', '')} has a health score of "
            f"{rec.get('health_score', 'N/A')}/100 and is in the {rec.get('risk_band', 'N/A')} band. "
            f"Thermal Aging Factor (FAA): {faa_str}. "
            f"Hotspot Temperature: {rec.get('hotspot_temp', 'N/A')}°C. "
            f"Mean Winding Temperature: {rec.get('mean_winding_temp', 'N/A')}°C. "
            f"Overload Severity score: {rec.get('overload_severity', 'N/A')}. "
            f"Tap Changer Stress (daily ops): {rec.get('tap_changer_stress', 'N/A')}. "
            f"Load-Temperature Sensitivity (Pearson r): {rec.get('load_temp_sensitivity', 'N/A')}. "
            f"Last inspection: {rec.get('last_inspection_date', 'N/A')}."
        )
        docs.append({
            "id":       make_chunk_id(asset_id, "health_score", 0),
            "content":  text,
            "title":    f"Health Score Record — {asset_id}",
            "asset_id": asset_id,
        })
    return docs


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_documents(docs: list[dict], client: AzureOpenAI) -> list[dict]:
    """
    Add embedding vectors to each document dict.
    Processes in batches to respect Azure OpenAI rate limits.
    """
    texts = [d["content"] for d in docs]
    all_embeddings = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i: i + BATCH_SIZE]
        log.info(f"  Embedding batch {i // BATCH_SIZE + 1} ({len(batch)} chunks)…")
        try:
            response = client.embeddings.create(model=EMBED_DEPLOYMENT, input=batch)
            all_embeddings.extend([r.embedding for r in response.data])
        except Exception as exc:
            log.error(f"  Embedding failed for batch starting at {i}: {exc}")
            # Pad with zero vectors so indexing can continue
            all_embeddings.extend([[0.0] * EMBED_DIM] * len(batch))
        time.sleep(0.5)   # gentle rate limiting

    for doc, emb in zip(docs, all_embeddings):
        doc["embedding"] = emb

    return docs


# ── Azure AI Search index management ─────────────────────────────────────────

def ensure_index_exists():
    """Create the Azure AI Search index if it doesn't already exist."""
    url = f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}?api-version={SEARCH_API_VER}"
    headers = {"api-key": SEARCH_API_KEY, "Content-Type": "application/json"}

    check = requests.get(url, headers=headers, verify=False)
    if check.status_code == 200:
        log.info(f"Index '{SEARCH_INDEX}' already exists — skipping creation")
        return

    schema = {
        "name": SEARCH_INDEX,
        "fields": [
            {"name": "id",       "type": "Edm.String",  "key": True,  "searchable": False},
            {"name": "content",  "type": "Edm.String",  "searchable": True, "analyzer": "en.microsoft"},
            {"name": "title",    "type": "Edm.String",  "searchable": True, "filterable": True},
            {"name": "asset_id", "type": "Edm.String",  "filterable": True, "searchable": False},
            {
                "name": "embedding",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "dimensions": EMBED_DIM,
                "vectorSearchProfile": "default-profile",
            },
        ],
        "vectorSearch": {
            "profiles":    [{"name": "default-profile", "algorithm": "default-hnsw"}],
            "algorithms":  [{"name": "default-hnsw",    "kind": "hnsw"}],
        },
    }

    resp = requests.put(url, headers=headers, json=schema, verify=False)
    resp.raise_for_status()
    log.info(f"Created index '{SEARCH_INDEX}'")


def upload_documents(docs: list[dict]):
    """Upsert documents to Azure AI Search in batches of 100."""
    url = f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}/docs/index?api-version={SEARCH_API_VER}"
    headers = {"api-key": SEARCH_API_KEY, "Content-Type": "application/json"}

    for i in range(0, len(docs), 100):
        batch = docs[i: i + 100]
        body  = {"value": [{"@search.action": "mergeOrUpload", **d} for d in batch]}
        resp  = requests.post(url, headers=headers, json=body, verify=False)
        resp.raise_for_status()
        log.info(f"  Uploaded batch {i // 100 + 1} ({len(batch)} docs)")


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_rag_indexing(mock: bool = False):
    """
    Build the RAG index from work orders and health scores.

    Args:
        mock: if True, use sample_data files and skip Azure calls
    """
    if mock:
        log.info("Running in MOCK MODE — reading sample_data, skipping Azure calls")
        import csv, pathlib
        base = pathlib.Path(__file__).parent.parent / "sample_data"

        with open(base / "work_orders.json") as f:
            work_orders = json.load(f)

        with open(base / "health_scores.csv") as f:
            health_records = list(csv.DictReader(f))

        wo_docs     = prepare_documents_from_work_orders(work_orders)
        health_docs = prepare_documents_from_health_scores(health_records)
        all_docs    = wo_docs + health_docs

        log.info(f"Prepared {len(all_docs)} document chunks from mock data")
        for doc in all_docs[:3]:
            log.info(f"  [{doc['title']}] {doc['content'][:80]}…")
        log.info("Mock indexing complete — no vectors uploaded (no Azure connection)")
        return

    # Live mode
    from db import query_to_dicts

    log.info("Fetching work orders from Oracle…")
    wo_rows = query_to_dicts("""
        SELECT WO_ID, ASSET_ID, SUBSTATION_ID, WO_TYPE, PRIORITY,
               DESCRIPTION, FAILURE_CODE, TO_CHAR(CREATED_DATE, 'YYYY-MM-DD') AS CREATED_DATE,
               TO_CHAR(COMPLETION_DATE, 'YYYY-MM-DD') AS COMPLETION_DATE
        FROM WORK_ORDERS
        ORDER BY CREATED_DATE DESC
    """)

    log.info("Fetching health scores from Oracle…")
    health_rows = query_to_dicts("SELECT * FROM SUBSTATION_HEALTH_VW")

    wo_docs     = prepare_documents_from_work_orders(wo_rows)
    health_docs = prepare_documents_from_health_scores(health_rows)
    all_docs    = wo_docs + health_docs
    log.info(f"Prepared {len(all_docs)} document chunks")

    client = _get_openai_client()

    log.info("Embedding documents…")
    all_docs = embed_documents(all_docs, client)

    log.info("Ensuring index exists…")
    ensure_index_exists()

    log.info("Uploading to Azure AI Search…")
    upload_documents(all_docs)

    log.info(f"RAG indexing complete. {len(all_docs)} chunks indexed in '{SEARCH_INDEX}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Run with mock data (no Oracle/Azure)")
    args = parser.parse_args()
    run_rag_indexing(mock=args.mock)
