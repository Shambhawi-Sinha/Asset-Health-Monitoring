"""
main.py — FastAPI application entry point

Registers all routers and configures CORS for the React frontend.

Note on running inside Jupyter (OCI Compute VM):
    import nest_asyncio
    nest_asyncio.apply()
    uvicorn.run(app, host="0.0.0.0", port=5000)

This is required because OCI Resource Principal authentication uses an existing
asyncio event loop inside Jupyter. nest_asyncio allows uvicorn to reuse it.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from endpoints.images import router as images_router
from endpoints.report import router as report_router
from endpoints.photo import router as photo_router
from endpoints.chat import router as chat_router

app = FastAPI(
    title="Substation Asset Health Monitoring API",
    description="Backend-for-Frontend proxy serving React dashboard and RAG chatbot.",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# React dev server runs on :3000; FastAPI on :5000.
# Without this, browsers block cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(images_router, prefix="/api")
app.include_router(report_router, prefix="/api")
app.include_router(photo_router,  prefix="/api")
app.include_router(chat_router,   prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok"}
