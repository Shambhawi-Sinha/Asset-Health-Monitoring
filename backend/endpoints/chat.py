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
 
Mock mode:
    Returns a friendly message instead of calling Azure APIs.
    No credentials required.
"""
 
import os
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
 
router = APIRouter()
 
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"
 
 
class ChatRequest(BaseModel):
    question: str
 
 
class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = []
 
 
@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Receive a natural language question from the React chat panel,
    run the RAG pipeline, and return a grounded answer with source citations.
 
    In mock mode, returns a placeholder response — no Azure credentials needed.
    In live mode, all Azure API credentials are accessed server-side inside
    run_rag_pipeline — nothing reaches the React frontend.
    """
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty")
 
    if MOCK_MODE:
        return ChatResponse(
            answer=(
                f"You asked: \"{request.question}\"\n\n"
                "The RAG diagnostic chatbot is running in mock mode. "
                "In production, this uses Azure OpenAI (GPT-4) and Azure AI Search "
                "to retrieve relevant work order history, inspection notes, and health "
                "metric context — then generates a grounded answer with source citations.\n\n"
                "To enable live chat: set MOCK_MODE=false and provide AZURE_OPENAI_API_KEY, "
                "AZURE_OPENAI_ENDPOINT, AZURE_SEARCH_ENDPOINT, and AZURE_SEARCH_API_KEY "
                "in your .env file."
            ),
            sources=["mock-mode"]
        )
 
    try:
        from rag.pipeline import run_rag_pipeline
        result = run_rag_pipeline(question=request.question)
        return ChatResponse(answer=result["answer"], sources=result.get("sources", []))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RAG pipeline error: {exc}")
 