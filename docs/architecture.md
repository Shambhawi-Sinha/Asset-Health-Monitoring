# Architecture — Substation Asset Health Monitoring Platform

## System Overview

End-to-end AI + full-stack platform for monitoring power transformer health across a large utility fleet. The system ingests multi-source sensor, inspection, and maintenance data; computes domain-driven health metrics; surfaces insights through a React dashboard; and provides an embedded RAG diagnostic chatbot.

All data persists in OCI (Oracle Cloud Infrastructure). Azure AI services are consumed as REST APIs from the Python backend. The React frontend is a pure presentation layer — it never calls Oracle, Azure, or Fulcrum directly.

---

## Architectural Layers

### 1. Data Layer — Oracle Autonomous Database (OCI)

All raw and processed data lives in Oracle ADB in the OCI Phoenix region.

**Data sources ingested:**

| Source | Granularity | Key Signals |
|---|---|---|
| Operational Historian (SCADA) | 15-min intervals | Winding temp, oil temp, MVA load, voltage, TPOS, TPOSC, hotspot |
| Field Inspection Reports (Fulcrum) | Per inspection event | Image URLs, engineer notes, asset condition ratings |
| Enterprise Work Order System | Per WO event | WO type, priority, failure code, description (free text), completion status |
| Airport Weather (IDW-weighted) | Hourly | Ambient temperature, humidity, wind speed — weighted to substation lat/lon |
| Transformer Master Table | Static reference | Asset ID, substation ID, MVA rating, voltage class, cooling type, coordinates |

**Sensor data quality handling:**
- Missing intervals (sensor dropout): forward-fill for gaps ≤ 2 hours; flagged and excluded for gaps > 2 hours
- Sensor drift: isolated using rolling baselines per asset
- Incomplete signal coverage: conditional metric computation — assets missing a sensor are scored on available metrics only
- Tag-to-transformer mapping: separate lookup table with effective dating for sensor reassignments

---

### 2. Pipeline Layer — Python

Runs on OCI Compute. Reads from Oracle ADB, calls Azure AI APIs, writes results back to Oracle.

**`pipeline/health_metrics.py`** — Six metric computations:

```
1. Mean Winding Temperature    rolling 24hr/7-day average (sustained stress, not spike)
2. Hotspot Temperature         IEEE C57.91: θ_H = θ_A + Δθ_TO + Δθ_H (or direct sensor)
3. Thermal Aging Factor (FAA)  IEC 60076-7: exp(B/θ_ref − B/(273 + θ_H))
4. Overload Severity           cumulative (MVA_actual/MVA_rated − 1) over rolling window
5. Tap Changer Stress          daily TPOSC delta (mechanical wear odometer)
6. Load-Temperature Sensitivity rolling Pearson r(load, winding_temp) — cooling signal
```

**`pipeline/composite_score.py`** — Weighted penalty aggregation:

```
Weights (calibrated with domain experts against historical failure data):
  Thermal Aging Factor   30%   — irreversible insulation damage, highest weight
  Hotspot Temperature    25%   — direct insulation stress
  Overload Severity      20%   — excess load above nameplate
  Tap Changer Stress     10%   — mechanical wear
  Mean Winding Temp      10%   — corroborative thermal signal
  Load-Temp Sensitivity   5%   — cooling degradation indicator

Score = 100 − (weighted sum of normalised penalties × 100)
Risk Band:  > 70 → GREEN | 40–70 → AMBER | < 40 → RED
```

**`pipeline/vision_scoring.py`** — Azure AI Vision integration:
- Fetches Fulcrum image URLs from Oracle
- Pre-filters: Laplacian variance (sharpness) + minimum resolution check
- Calls Azure AI Vision → generates defect score + condition description
- Writes image analysis results back to Oracle
- Handles OCI pre-signed URL expiry with token refresh before each batch

**`pipeline/rag_indexing.py`** — Azure AI Search vector indexing:
- Chunks work order descriptions, inspection notes, and asset history
- Embeds chunks via Azure OpenAI text-embedding-ada-002 (1536-dim vectors)
- Upserts to Azure AI Search index for RAG retrieval

---

### 3. Backend Layer — FastAPI (Python)

Runs inside a Jupyter notebook on OCI Compute using `nest_asyncio` to coexist with the OCI Resource Principal authentication event loop.

**Why Jupyter + nest_asyncio:**  
OCI Resource Principal auth (used by `ADBQuery.py`) initialises inside a Jupyter kernel. `nest_asyncio.apply()` allows `uvicorn.run()` to share that event loop, enabling FastAPI to inherit the authenticated OCI session without re-authentication.

**Endpoints:**

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/images` | GET | Substation health records + scores from Oracle |
| `/api/report` | GET | Work order summaries per asset from Oracle |
| `/api/photo` | GET | Fulcrum inspection image proxy (BFF pattern) |
| `/api/chat` | POST | RAG chatbot endpoint — question → grounded answer (BFF pattern) |
| `/health` | GET | Liveness check |

**Backend-for-Frontend (BFF) Security Pattern:**

Three credential classes are proxied:
1. **Oracle credentials** — DB user/pass + mTLS wallet files stay in Python process
2. **Fulcrum API key** — `/api/photo` fetches image bytes; React receives only the image
3. **Azure OpenAI + AI Search keys** — `/api/chat` runs full RAG pipeline; React sends only the question string

React DevTools network inspection reveals no credentials — only question strings and JSON responses.

**Oracle connection (mTLS wallet):**  
Wallet files: `ewallet.pem`, `tnsnames.ora`, `sqlnet.ora`  
Library: `python-oracledb` (thin mode — no Oracle Instant Client required)

---

### 4. Frontend Layer — React.js

Create React App, running on `localhost:3000` in development.

**Dashboard components:**

| Component | Data source | Notes |
|---|---|---|
| `KpiCards.jsx` | `/api/images` | Fleet totals: GREEN/AMBER/RED counts + overall average score |
| `HealthTrendChart.jsx` | `/api/images` (time-grouped) | Average fleet health score over time (Recharts LineChart) |
| `SubstationTable.jsx` | `/api/images` + `/api/report` | Searchable, sortable table — score, band, last WO, open emergencies |
| `InspectionImage.jsx` | `/api/photo` (per record) | Renders field photos via BFF proxy; Fulcrum key stays server-side |
| `ChatPanel.jsx` | `/api/chat` | Embedded RAG chat — question → GPT-4 answer + source citations |

**Parallel data loading (`api/client.js`):**

```javascript
// Sequential (naive):  images(2s) + report(2s) = 4s
// Parallel:            MAX(images, report) = 2s  ✓
Promise.all([fetch('/api/images'), fetch('/api/report')])
  .then(([imagesData, reportData]) => { /* render */ });
```

Load time is displayed in the dashboard header (`2s PARALLEL LOAD`) to demonstrate the optimisation.

---

## Engineering Challenges Solved

### DNS Resolution (OCI Hostname on Corporate VM)

**Problem:** Oracle ADB hostname (`adb.us-phoenix-1.oraclecloud.com`) failed to resolve on the company-managed VMware VM.  
**Solution:** Changed VM DNS to `8.8.8.8`, flushed cache (`ipconfig /flushdns`), verified port 1522 connectivity (`Test-NetConnection -ComputerName <host> -Port 1522 → TcpTestSucceeded: True`).

### OCI Resource Principal Outside OCI

**Problem:** `ADBQuery.py` uses OCI Resource Principal auth — designed to run inside OCI. Running standalone FastAPI breaks the auth flow.  
**Solution:** Run FastAPI inside the Jupyter kernel using `nest_asyncio.apply()` before `uvicorn.run()`. The notebook kernel already has a valid Resource Principal session; FastAPI inherits it.

### Fulcrum Two-Step Image Fetch

**Problem:** Fulcrum's photo endpoint returns a metadata JSON (with URL fields), not image bytes directly. React cannot call Fulcrum directly (API key exposure).  
**Solution:**  
```
Step 1: GET /api/v2/photos/{id}.json → { "photo": { "large": "...", ... } }
Step 2: GET <large_url> with X-ApiToken header → image bytes
FastAPI returns bytes to React as Response(content=img_bytes, media_type="image/jpeg")
```

### SSL Certificate Errors (Corporate Proxy)

**Problem:** Corporate SSL inspection proxy intercepts HTTPS to Azure endpoints, causing SSL verification failures.  
**Solution:** `requests.get(..., verify=False)` + `urllib3.disable_warnings()` for all internal-network calls. Remove in production with properly configured certificates.

### asyncio Event Loop Conflict in Jupyter

**Problem:** `uvicorn.run()` inside Jupyter raises `RuntimeError: This event loop is already running`.  
**Solution:** `pip install nest-asyncio` → `nest_asyncio.apply()` before `uvicorn.run()`. Allows uvicorn to nest its event loop inside the existing Jupyter loop.

### CORS (React :3000 → FastAPI :5000)

**Problem:** Browser blocks cross-origin requests from `localhost:3000` to `localhost:5000`.  
**Solution:** `fastapi.middleware.cors.CORSMiddleware` with `allow_origins=["http://localhost:3000"]`.

---

## Data Flow Diagram

```
┌─────────────────┐     15-min poll      ┌──────────────────────┐
│  SCADA Historian │ ──────────────────►  │                      │
└─────────────────┘                       │  Oracle Autonomous   │
┌─────────────────┐     per inspection    │  Database (OCI)      │
│  Fulcrum App    │ ──────────────────►  │  Phoenix region      │
└─────────────────┘                       │                      │
┌─────────────────┐     per WO event      │  - sensor_readings   │
│  Work Order Sys │ ──────────────────►  │  - inspections       │
└─────────────────┘                       │  - work_orders       │
┌─────────────────┐     hourly            │  - transformer_master│
│  Airport Weather│ ──────────────────►  │  - health_scores     │
└─────────────────┘                       └──────────┬───────────┘
                                                     │ mTLS wallet
                                                     ▼
                                          ┌──────────────────────┐
                                          │  Python Pipeline     │
                                          │  (OCI Compute)       │◄─── Azure AI Vision
                                          │                      │◄─── Azure OpenAI (embed)
                                          │  health_metrics.py   │◄─── Azure AI Search
                                          │  composite_score.py  │
                                          │  vision_scoring.py   │
                                          │  rag_indexing.py     │
                                          └──────────┬───────────┘
                                                     │ writes back to Oracle
                                                     │
                                          ┌──────────▼───────────┐
                                          │  FastAPI Backend     │
                                          │  (Jupyter + uvicorn) │
                                          │                      │
                                          │  /api/images ────────┼──► Oracle query
                                          │  /api/report ────────┼──► Oracle query
                                          │  /api/photo  ────────┼──► Fulcrum proxy
                                          │  /api/chat   ────────┼──► Azure OpenAI
                                          │                      │    + Azure AI Search
                                          └──────────┬───────────┘
                                                     │ JSON / HTTP
                                                     ▼
                                          ┌──────────────────────┐
                                          │  React Dashboard     │
                                          │  localhost:3000       │
                                          │                      │
                                          │  KPI Cards           │
                                          │  Health Trend Chart  │
                                          │  Substation Table    │
                                          │  Inspection Images   │
                                          │  RAG Chat Panel      │
                                          └──────────────────────┘
```

---

## Deployment Path (Production)

Current: FastAPI runs inside Jupyter on OCI Compute VM (dev/demo setup).

To productionise:

1. **Oracle auth** — Replace Resource Principal with service account credentials (`cx_Oracle.SessionPool` or `python-oracledb` connection pool with explicit user/pass). Wallet files mount as OCI File Storage volume.

2. **Containerise FastAPI** — Dockerfile with `uvicorn main:app` as entrypoint. Deploy to OCI Container Instances or Kubernetes.

3. **React build** — `npm run build` → serve static files from Nginx on OCI Compute, reverse-proxied to FastAPI.

4. **Secrets** — All API keys and wallet password migrated to OCI Vault. Injected as environment variables at container startup.

5. **Pagination** — Server-side pagination in `/api/images` (OFFSET/FETCH in Oracle SQL), React lazy-loads images on scroll — removes 500+ concurrent photo requests.
