# Substation Asset Health Monitoring Platform

> End-to-end AI + full-stack platform for transformer health monitoring across a large utility fleet.  
> **Python · FastAPI · React.js · Oracle ADB (OCI) · Azure OpenAI · Azure AI Vision · Azure AI Search · SQL**

---

## Overview

This platform monitors the health of **900+ power transformers** across **400+ substations** for a utility client. It replaces reactive, siloed monitoring with a unified AI-powered system: from raw sensor data ingestion through to a live React dashboard with an embedded RAG diagnostic chatbot.

**Key results:**
- ~60% reduction in manual analysis time for field engineers
- ~40% improvement in early fault detection vs prior reactive approach

> ⚠️ **Note:** This repository uses sanitized mock data and placeholder credentials. All real OCI, Azure, and Fulcrum credentials have been replaced with environment variable references. Proprietary business logic has been abstracted.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA LAYER (OCI)                             │
│  Oracle Autonomous DB — sensor historian, inspection reports,       │
│  work orders, transformer master, weather-weighted ambient temps    │
└────────────────────────────┬────────────────────────────────────────┘
                             │ mTLS wallet (ewallet.pem)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     PIPELINE LAYER (Python)                         │
│  pipeline/health_metrics.py  — FAA thermal aging, hotspot,         │
│  overload severity, tap changer stress, composite 0–100 score      │
│  pipeline/vision_scoring.py  — Azure AI Vision defect scoring      │
│  pipeline/rag_indexing.py    — Azure AI Search vector indexing     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     BACKEND LAYER (FastAPI)                         │
│                                                                     │
│  GET  /api/images  ── substation health records + scores           │
│  GET  /api/report  ── work order summaries per asset               │
│  GET  /api/photo   ── Fulcrum inspection image proxy (BFF)         │
│  POST /api/chat    ── RAG chatbot endpoint (BFF)                   │
│         └── Azure OpenAI (embed + GPT-4) + Azure AI Search        │
│                                                                     │
│  BFF Pattern: Oracle, Fulcrum, and Azure credentials               │
│  NEVER reach the React frontend                                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │ JSON / HTTP
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FRONTEND LAYER (React.js)                        │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │  KPI Cards   │  │ Health Trend │  │   Substation Table       │ │
│  │ Fleet totals │  │ Chart (time) │  │ Searchable / sortable    │ │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘ │
│  ┌──────────────────────────┐  ┌─────────────────────────────────┐ │
│  │  Inspection Images       │  │   RAG Chat Panel                │ │
│  │  (via /api/photo proxy)  │  │   Engineer Q&A — grounded GPT-4 │ │
│  └──────────────────────────┘  └─────────────────────────────────┘ │
│                                                                     │
│  Promise.all([/api/images, /api/report]) — parallel load           │
│  Sequential: ~4s  →  Parallel: ~2s                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.10, FastAPI, Uvicorn |
| Database | Oracle Autonomous DB (OCI), python-oracledb, mTLS wallet |
| AI — Vision | Azure AI Vision (image defect scoring) |
| AI — Language | Azure OpenAI (GPT-4, text-embedding-ada-002) |
| AI — Search | Azure AI Search (vector index, RAG retrieval) |
| Frontend | React.js 18, Recharts, CSS |
| Pipeline | Python, Pandas, NumPy, OpenCV (headless), Pillow |
| Containerisation | Docker, docker-compose |
| Auth | OCI Resource Principal, mTLS (Oracle), BFF proxy (Azure/Fulcrum) |

---

## Health Metrics

Six domain-driven metrics computed per transformer, feeding a composite **0–100 risk score**:

| Metric | Method | Standard |
|---|---|---|
| Mean Winding Temperature | Rolling 24hr average | Direct sensor |
| Hotspot Temperature | Thermal model or direct sensor | IEEE C57.91: θ_H = θ_A + Δθ_TO + Δθ_H |
| Thermal Aging Factor (FAA) | Insulation life consumption | IEC 60076-7: exp(15000/383 − 15000/(273+θ_H)) |
| Overload Severity | Excess load above nameplate | MVA_actual / MVA_rated |
| Tap Changer Stress | Cumulative tap ops (TPOSC delta) | Daily mechanical wear |
| Load-Temperature Sensitivity | Pearson r (load vs temp) | Rolling window correlation |

Risk bands: **GREEN** (score > 70) · **AMBER** (40–70) · **RED** (< 40)

---

## Repository Structure

```
Asset-Health-Monitoring/
│
├── backend/                        # FastAPI backend
│   ├── main.py                     # App entry point, CORS, router registration
│   ├── db.py                       # Oracle ADB connection (mTLS wallet)
│   ├── endpoints/
│   │   ├── images.py               # GET /api/images
│   │   ├── report.py               # GET /api/report
│   │   ├── photo.py                # GET /api/photo (Fulcrum BFF proxy)
│   │   └── chat.py                 # POST /api/chat (RAG chatbot BFF)
│   ├── rag/
│   │   └── pipeline.py             # Azure OpenAI + AI Search RAG logic
│   └── requirements.txt
│
├── frontend/                       # React.js dashboard
│   ├── public/
│   │   └── index.html              # HTML entry point
│   ├── src/
│   │   ├── index.js                # React DOM mount point
│   │   ├── index.css               # Full stylesheet — all component styles
│   │   ├── App.js                  # Root component, data fetching, layout
│   │   ├── components/
│   │   │   ├── KpiCards.jsx        # Fleet summary cards (total/RED/AMBER/GREEN)
│   │   │   ├── HealthTrendChart.jsx # Fleet health score over time (Recharts)
│   │   │   ├── SubstationTable.jsx  # Searchable sortable asset table
│   │   │   ├── InspectionImage.jsx  # Inspection photo via BFF proxy
│   │   │   └── ChatPanel.jsx        # Embedded RAG chat panel
│   │   ├── api/
│   │   │   └── client.js           # Promise.all parallel fetch + image proxy
│   │   └── mockData/               # JSON files imported directly in mock mode
│   │       ├── health_scores.json
│   │       └── work_orders.json
│   └── package.json
│
├── pipeline/                       # Offline data pipeline
│   ├── health_metrics.py           # FAA, hotspot, overload, tap changer, sensitivity
│   ├── composite_score.py          # Weighted 0–100 score + risk banding
│   ├── vision_scoring.py           # Azure AI Vision — defect scoring + quality filter
│   ├── rag_indexing.py             # Azure AI Search — chunk, embed, upsert
│   └── requirements.txt
│
├── notebooks/
│   └── health_metrics_demo.ipynb   # Full metric walkthrough on mock data
│
├── docs/
│   └── architecture.md             # Full system architecture write-up
│
├── sample_data/
│   ├── README.md                   # Schema documentation
│   ├── transformers.csv            # Mock transformer master records
│   ├── sensor_readings.csv         # Mock 15-min interval sensor data
│   ├── work_orders.json            # Mock work order records
│   ├── health_scores.csv           # Mock computed health scores
│   └── health_scores.json          # Same data as JSON (imported by React)
│
├── Dockerfile                      # FastAPI backend container
├── docker-compose.yml              # Backend + frontend together
├── .env.example                    # All required env vars with placeholders
├── .gitignore
└── README.md
```

---

## How to Run Locally

### Option A — Quickest: Docker Compose (mock mode, no credentials)

```bash
git clone https://github.com/your-username/Asset-Health-Monitoring.git
cd Asset-Health-Monitoring

docker-compose up
# Backend:  http://localhost:5000
# Frontend: http://localhost:3000
```

Both services start in mock mode by default. The full dashboard renders with sample data — no Oracle, Azure, or Fulcrum accounts needed.

---

### Option B — Without Docker (mock mode)

```bash
git clone https://github.com/your-username/Asset-Health-Monitoring.git
cd Asset-Health-Monitoring

# Terminal 1 — Backend
cd backend
pip install -r requirements.txt
MOCK_MODE=true uvicorn main:app --host 0.0.0.0 --port 5000 --reload

# Terminal 2 — Frontend
cd frontend
npm install
REACT_APP_MOCK_MODE=true npm start
# Opens at http://localhost:3000
```

Pipeline scripts in mock mode (no Oracle or Azure):

```bash
cd pipeline
pip install -r requirements.txt
python health_metrics.py --mock
python vision_scoring.py --mock
python rag_indexing.py --mock
```

Jupyter notebook (fully local):

```bash
cd notebooks
jupyter notebook health_metrics_demo.ipynb
```

---

### Option C — Live Mode (real credentials)

```bash
cp .env.example .env
# Fill in OCI, Azure OpenAI, Azure AI Search, Azure AI Vision, Fulcrum credentials

# One-time: build RAG index
cd pipeline
python rag_indexing.py

# Start backend (live Oracle + Azure)
cd backend
uvicorn main:app --host 0.0.0.0 --port 5000 --reload

# Start frontend (calls real backend)
cd frontend
npm start
```

> **Jupyter + OCI note:** If running FastAPI inside a Jupyter notebook on OCI Compute (to reuse Resource Principal auth), add `import nest_asyncio; nest_asyncio.apply()` before `uvicorn.run()`.

---

## Key Engineering Challenges Solved

| Challenge | Solution |
|---|---|
| VM DNS blocking OCI hostname | Set DNS to 8.8.8.8; verified port 1522 with `Test-NetConnection` |
| OCI Resource Principal outside OCI | Run FastAPI inside Jupyter with `nest_asyncio.apply()` |
| Wallet path resolution | Wallet folder placed inside `backend/` to match expected relative path |
| Fulcrum two-step image fetch | Metadata call → extract `large` URL → second call for image bytes |
| Corporate SSL proxy (Azure calls) | `verify=False` + `urllib3.disable_warnings()` for internal network |
| asyncio event loop conflict in Jupyter | `nest_asyncio.apply()` before `uvicorn.run()` |
| Azure credentials exposed in React | BFF pattern — all Azure calls proxied through `/api/chat` |
| CORS (React :3000 → FastAPI :5000) | `CORSMiddleware` allowing `localhost:3000` |

---

## Security Design (BFF Pattern)

All external API credentials stay server-side. React is a pure presentation layer.

```
React (browser)                FastAPI (server)
─────────────────────────────────────────────────
POST /api/chat                 → Azure OpenAI key  ✓
  { "question": "..." }        → Azure Search key  ✓
  ← { "answer": "..." }        → Oracle creds      ✓
                               → Fulcrum API key   ✓
GET /api/photo?id=xxx
  ← image bytes               (none reach browser)
```

---

## Roadmap

- [ ] Agentic AI layer — continuous monitoring, auto-alert on RED band transition
- [ ] Auto work order generation from agentic triggers
- [ ] Server-side pagination for 500+ substation image requests
- [ ] OCI Vault integration for credential management
- [ ] Nginx reverse proxy for production React build

---

## License

This repository contains sanitized, non-proprietary code samples for portfolio and technical demonstration purposes. No client data, real credentials, or proprietary business logic is included.
