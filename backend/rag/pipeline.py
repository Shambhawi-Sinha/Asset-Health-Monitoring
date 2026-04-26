"""
rag/pipeline.py — RAG pipeline: Azure OpenAI + Azure AI Search

Three-step pipeline called by /api/chat:
    1. Embed the question using Azure OpenAI text-embedding-ada-002
    2. Retrieve top-K relevant document chunks from Azure AI Search (vector search)
    3. Construct a grounded prompt and call Azure OpenAI GPT-4 for the answer

All credentials are read from environment variables — never hardcoded.

Azure AI Search index schema (expected):
    - id            : string (chunk ID)
    - content       : string (text chunk)
    - title         : string (source document name)
    - embedding     : Collection(Edm.Single) — 1536-dim vector field
"""

import os
import requests
import urllib3
from openai import AzureOpenAI

# Suppress SSL warnings for corporate proxy environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Azure OpenAI client ───────────────────────────────────────────────────────
_openai_client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
)

EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_EMBED", "text-embedding-ada-002")
GPT4_DEPLOYMENT  = os.getenv("AZURE_OPENAI_DEPLOYMENT_GPT4",  "gpt-4")

# ── Azure AI Search config ────────────────────────────────────────────────────
SEARCH_ENDPOINT  = os.getenv("AZURE_SEARCH_ENDPOINT")
SEARCH_API_KEY   = os.getenv("AZURE_SEARCH_API_KEY")
SEARCH_INDEX     = os.getenv("AZURE_SEARCH_INDEX_NAME", "substation-docs")
TOP_K            = 5   # number of chunks to retrieve


def run_rag_pipeline(question: str) -> dict:
    """
    Run the full RAG pipeline for a diagnostic question.

    Returns:
        {
            "answer": str,          # grounded GPT-4 answer
            "sources": list[str],   # document titles cited
        }
    """
    # ── Step 1: Embed the question ────────────────────────────────────────────
    embedding = _embed_question(question)

    # ── Step 2: Retrieve relevant chunks from Azure AI Search ─────────────────
    chunks = _vector_search(embedding)

    # ── Step 3: Generate grounded answer with GPT-4 ───────────────────────────
    answer = _generate_answer(question, chunks)

    sources = list({c["title"] for c in chunks if c.get("title")})
    return {"answer": answer, "sources": sources}


def _embed_question(question: str) -> list[float]:
    """Embed a question string using Azure OpenAI text-embedding-ada-002."""
    response = _openai_client.embeddings.create(
        model=EMBED_DEPLOYMENT,
        input=question,
    )
    return response.data[0].embedding


def _vector_search(embedding: list[float]) -> list[dict]:
    """
    Run vector search against Azure AI Search.

    Uses the REST API directly for flexibility with custom index configurations.
    """
    url = f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}/docs/search?api-version=2023-11-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": SEARCH_API_KEY,
    }
    body = {
        "vectorQueries": [
            {
                "kind": "vector",
                "vector": embedding,
                "fields": "embedding",
                "k": TOP_K,
            }
        ],
        "select": "id,content,title",
    }
    resp = requests.post(url, headers=headers, json=body, timeout=15, verify=False)
    resp.raise_for_status()
    return resp.json().get("value", [])


def _generate_answer(question: str, chunks: list[dict]) -> str:
    """
    Construct a grounded prompt and call GPT-4 to generate a cited answer.
    """
    context_blocks = "\n\n".join(
        f"[Source: {c.get('title', 'Unknown')}]\n{c.get('content', '')}"
        for c in chunks
    )

    system_prompt = (
        "You are a diagnostic assistant for power transformer health monitoring. "
        "Answer questions based strictly on the provided context. "
        "Cite the source document name when referencing specific information. "
        "If the context does not contain enough information to answer, say so clearly."
    )

    user_prompt = f"""Context:
{context_blocks}

Question: {question}

Answer (with citations from the context above):"""

    response = _openai_client.chat.completions.create(
        model=GPT4_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=800,
    )
    return response.choices[0].message.content.strip()
