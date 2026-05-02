/**
 * App.js — Root component
 *
 * Orchestrates the full dashboard:
 *   1. Fires Promise.all([/api/images, /api/report]) on mount
 *   2. Passes data to KpiCards, HealthTrendChart, SubstationTable
 *   3. Renders ChatPanel in a fixed sidebar
 *   4. Shows inspection images for worst-scoring assets via InspectionImage
 *
 * MOCK_MODE (REACT_APP_MOCK_MODE=true):
 *   Loads data from src/mockData/ JSON files — no backend or credentials needed.
 *   All components render fully. InspectionImage renders coloured placeholders.
 *
 * Load time displayed in header demonstrates the Promise.all parallel
 * optimisation (2s vs ~4s sequential).
 */

import { useEffect, useState } from "react";
import KpiCards             from "./components/KpiCards";
import HealthTrendChart     from "./components/HealthTrendChart";
import SubstationTable      from "./components/SubstationTable";
import ChatPanel            from "./components/ChatPanel";
import InspectionImage      from "./components/InspectionImage";
import { fetchDashboardData } from "./api/client";

import mockHealthScores from "./mockData/health_scores.json";
import mockWorkOrders   from "./mockData/work_orders.json";

const MOCK_MODE = process.env.REACT_APP_MOCK_MODE === "true";

// ── Helper components ──────────────────────────────────────────────────────

function LoadingSpinner() {
  return (
    <div className="loading-state">
      <div className="spinner" />
      <p>Connecting to Oracle ADB and loading fleet data…</p>
    </div>
  );
}

function ErrorBanner({ message }) {
  return (
    <div className="error-banner">
      <strong>Failed to load dashboard data.</strong> {message}
      <p>
        Check that the FastAPI backend is running on port 5000, or set{" "}
        <code>REACT_APP_MOCK_MODE=true</code> to run on sample data.
      </p>
    </div>
  );
}

// Shows inspection photos for the 6 worst-scoring assets
function CriticalAssetStrip({ records }) {
  const worst = [...records]
    .sort((a, b) => a.health_score - b.health_score)
    .slice(0, 6);

  if (worst.length === 0) return null;

  return (
    <div className="section">
      <h3 className="section-title">Critical & At-Risk Assets — Inspection Photos</h3>
      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
        {worst.map((rec) => (
          <div
            key={rec.asset_id}
            style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "6px" }}
          >
            <InspectionImage
              recordId={rec.photo_record_id}
              assetId={rec.asset_id}
              riskBand={rec.risk_band}
            />
            <span style={{ fontSize: "0.7rem", color: "#6b7280" }}>{rec.asset_id}</span>
            <span style={{
              fontSize: "0.68rem", fontWeight: 700,
              color: rec.risk_band === "RED" ? "#991b1b" : rec.risk_band === "AMBER" ? "#92400e" : "#166534",
            }}>
              {rec.risk_band} · {rec.health_score?.toFixed(1)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Root component ─────────────────────────────────────────────────────────

export default function App() {
  const [images,     setImages]     = useState([]);
  const [report,     setReport]     = useState([]);
  const [loadTimeMs, setLoadTimeMs] = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState(null);

  useEffect(() => {
    if (MOCK_MODE) {
      setImages(mockHealthScores);

      // Aggregate flat work_orders array into per-asset summary
      const woMap = {};
      for (const wo of mockWorkOrders) {
        if (!woMap[wo.asset_id]) {
          woMap[wo.asset_id] = {
            asset_id: wo.asset_id,
            substation_id: wo.substation_id,
            total_work_orders: 0,
            open_emergency_wos: 0,
            last_wo_date: null,
            last_wo_type: null,
            last_wo_description: null,
            dominant_failure_code: null,
          };
        }
        const s = woMap[wo.asset_id];
        s.total_work_orders += 1;
        if (wo.wo_type === "EMERGENCY" && !wo.completion_date) s.open_emergency_wos += 1;
        if (!s.last_wo_date || wo.created_date > s.last_wo_date) {
          s.last_wo_date        = wo.created_date;
          s.last_wo_type        = wo.wo_type;
          s.last_wo_description = wo.description;
          s.dominant_failure_code = wo.failure_code;
        }
      }
      setReport(Object.values(woMap));
      setLoadTimeMs(0);
      setLoading(false);
      return;
    }

    fetchDashboardData()
      .then(({ images, report, loadTimeMs }) => {
        setImages(images);
        setReport(report);
        setLoadTimeMs(loadTimeMs);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="app">

      <header className="app-header">
        <div className="header-left">
          <h1 className="header-title">Substation Asset Health Monitor</h1>
          <span className="header-sub">
            {MOCK_MODE
              ? "MOCK MODE — sample data · no credentials required"
              : images.length > 0
              ? `${images.length} transformers · ${loadTimeMs}ms PARALLEL LOAD`
              : "Connecting…"}
          </span>
        </div>
        <div className="header-right">
          <span className={`status-dot ${error ? "status-dot--error" : loading ? "status-dot--loading" : "status-dot--ok"}`} />
          <span className="status-label">{error ? "Error" : loading ? "Loading" : "Live"}</span>
        </div>
      </header>

      <div className="app-body">
        <main className="dashboard">
          {loading && <LoadingSpinner />}
          {error   && <ErrorBanner message={error} />}

          {!loading && !error && (
            <>
              <section className="section">
                <KpiCards records={images} />
              </section>

              <section className="section">
                <HealthTrendChart records={images} />
              </section>

              <CriticalAssetStrip records={images} />

              <section className="section">
                <h3 className="section-title">Asset Health Detail</h3>
                <SubstationTable images={images} report={report} />
              </section>
            </>
          )}
        </main>

        <aside className="chat-sidebar">
          <ChatPanel />
        </aside>
      </div>
    </div>
  );
}
