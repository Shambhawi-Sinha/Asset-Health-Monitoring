"""
endpoints/chat.py — POST /api/chat

Backend-for-Frontend endpoint for the RAG diagnostic chatbot embedded in
the React dashboard.

Security: React sends only the question string. All Azure OpenAI and Azure
AI Search credentials stay in this Python process — they never reach the browser.

Flow:
    React: POST /api/chat { "question": "Why is TRF045 in the Red band?" }
        → FastAPI: embed question via Azure OpenAI
        → Azure AI Search: retrieve top-K relevant chunks
        → Azure OpenAI GPT-4: generate grounded answer with citations
    React: receives { "answer": "...", "sources": [...] }
"""

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from rag.pipeline import run_rag_pipeline

router = APIRouter()


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []    # document titles / chunk references cited


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Receive a natural language question from the React chat panel,
    run the RAG pipeline, and return a grounded answer with source citations.

    All Azure API credentials are accessed server-side inside run_rag_pipeline.
    """
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty")

    try:
        result = run_rag_pipeline(question=request.question)
        return ChatResponse(answer=result["answer"], sources=result.get("sources", []))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RAG pipeline error: {exc}")
