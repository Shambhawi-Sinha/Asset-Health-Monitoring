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
| Database | Oracle Autonomous DB (OCI), cx_Oracle / python-oracledb, mTLS wallet |
| AI — Vision | Azure AI Vision (image defect scoring) |
| AI — Language | Azure OpenAI (GPT-4, text-embedding-ada-002) |
| AI — Search | Azure AI Search (vector index, RAG retrieval) |
| Frontend | React.js (CRA), Recharts, Axios |
| Pipeline | Python, Pandas, NumPy, Scipy |
| Auth | OCI Resource Principal, mTLS (Oracle), BFF proxy pattern (Azure/Fulcrum) |
| Infrastructure | OCI Compute, Oracle Autonomous DB (Phoenix region) |

---

## Health Metrics

Six domain-driven metrics computed per transformer, feeding a composite **0–100 risk score** with Green / Amber / Red banding:

| Metric | Method | Formula / Standard |
|---|---|---|
| Mean Winding Temperature | Rolling 24hr / 7-day average | Direct sensor avg |
| Hotspot Temperature | Thermal model or direct sensor | IEEE C57.91: θ_H = θ_A + Δθ_TO + Δθ_H |
| Thermal Aging Factor (FAA) | Insulation life consumption rate | IEC 60076-7: exp(15000/383 − 15000/(273+θ_H)) |
| Overload Severity | Load vs nameplate MVA ratio | MVA_actual / MVA_rated |
| Tap Changer Stress | Cumulative tap operations (TPOSC) | Daily TPOSC delta vs threshold |
| Load-Temperature Sensitivity | Pearson correlation (load ↔ temp) | Rolling window correlation coefficient |

FAA = 1.0 → aging at design rate. FAA > 4.0 → critical.

---

## Repository Structure

```
substation-health-platform/
│
├── backend/                    # FastAPI backend
│   ├── main.py                 # App entry point, CORS, router registration
│   ├── db.py                   # Oracle ADB connection (mTLS wallet)
│   ├── endpoints/
│   │   ├── images.py           # GET /api/images
│   │   ├── report.py           # GET /api/report
│   │   ├── photo.py            # GET /api/photo (Fulcrum BFF proxy)
│   │   └── chat.py             # POST /api/chat (RAG chatbot BFF)
│   ├── rag/
│   │   └── pipeline.py         # Azure OpenAI + AI Search RAG logic
│   └── requirements.txt
│
├── frontend/                   # React.js dashboard
│   ├── src/
│   │   ├── App.js
│   │   ├── components/
│   │   │   ├── KpiCards.jsx
│   │   │   ├── HealthTrendChart.jsx
│   │   │   ├── SubstationTable.jsx
│   │   │   ├── InspectionImage.jsx
│   │   │   └── ChatPanel.jsx   # Embedded RAG chat panel
│   │   └── api/
│   │       └── client.js       # Promise.all parallel fetch logic
│   └── package.json
│
├── pipeline/                   # Offline data pipeline
│   ├── health_metrics.py       # FAA, hotspot, overload, tap changer
│   ├── composite_score.py      # Weighted 0–100 score + risk banding
│   ├── vision_scoring.py       # Azure AI Vision image analysis
│   └── rag_indexing.py         # Azure AI Search document indexing
│
├── notebooks/
│   └── health_metrics_demo.ipynb   # Walkthrough with mock data
│
├── docs/
│   └── architecture.md         # Full system architecture write-up
│
├── sample_data/
│   ├── transformers.csv        # Mock transformer master records
│   ├── sensor_readings.csv     # Mock 15-min interval sensor data
│   ├── work_orders.json        # Mock work order records
│   └── health_scores.csv       # Mock computed health scores output
│
├── .env.example                # All required env vars with placeholders
├── .gitignore
└── README.md
```

---

## How to Run Locally

### Prerequisites

- Python 3.10+
- Node.js 18+
- Oracle Instant Client (for cx_Oracle / python-oracledb)
- OCI Autonomous DB wallet files (not included — use mock mode)

### 1. Clone and configure environment

```bash
git clone https://github.com/your-username/substation-health-platform.git
cd substation-health-platform
cp .env.example .env
# Edit .env with your credentials
```

### 2. Start the FastAPI backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

> In constrained environments (e.g. Jupyter), use `nest_asyncio` — see `notebooks/health_metrics_demo.ipynb`.

### 3. Start the React frontend

```bash
cd frontend
npm install
npm start
# Opens at http://localhost:3000
```

### 4. Run the pipeline (mock data mode)

```bash
cd pipeline
python health_metrics.py --mock
```

---

## Key Engineering Challenges Solved

| Challenge | Solution |
|---|---|
| VM DNS blocking OCI hostname | Set DNS to 8.8.8.8; flushed cache; verified port 1522 with `Test-NetConnection` |
| OCI Resource Principal auth outside OCI | Run FastAPI inside Jupyter using `nest_asyncio.apply()` to reuse authenticated OCI session |
| Wallet path resolution | Wallet folder moved inside `backend/` to match relative path expected by `ADBQuery.py` |
| Fulcrum two-step image fetch | First call returns metadata JSON → extract `large` URL → second call fetches image bytes |
| Corporate SSL proxy (Azure calls) | `requests.get(..., verify=False)` + `urllib3.disable_warnings()` for internal calls |
| asyncio event loop conflict in Jupyter | `nest_asyncio.apply()` before `uvicorn.run()` |
| Azure credentials in React | BFF pattern: all Azure calls proxied through `/api/chat` — React sends only question string |
| CORS (React port 3000 → FastAPI port 5000) | `CORSMiddleware` allowing `localhost:3000` |

---

## Security Design (BFF Pattern)

All external API credentials stay server-side. The React frontend is a pure presentation layer.

```
React (browser)                FastAPI (server)
─────────────────────────────────────────────────
POST /api/chat                 → Azure OpenAI API key ✓
  { "question": "..." }        → Azure AI Search key  ✓
  ← { "answer": "..." }        → Oracle wallet/creds  ✓
                               → Fulcrum API key      ✓
GET /api/photo?id=xxx          (none of these ever    
  ← image bytes                 reach the browser)   
```

---

## Roadmap / Extensions

- [ ] Agentic AI layer — continuous health score monitoring, auto-alert on Red band transition
- [ ] Auto work order generation from agentic triggers
- [ ] Server-side pagination for 500+ substation image load
- [ ] OCI Vault integration for credential management
- [ ] Containerise with Docker + deploy on OCI Compute

---

## License

This repository contains sanitized, non-proprietary code samples for portfolio and technical demonstration purposes. No client data, real credentials, or proprietary business logic is included.
