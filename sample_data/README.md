# Sample Data

This directory contains **mock data only** — no real client data, no real asset identifiers, no real coordinates.

It is used for:
- Running the backend in `MOCK_MODE=true` (FastAPI endpoints read from these files instead of Oracle ADB)
- Running the React dashboard in `REACT_APP_MOCK_MODE=true` (imports JSON directly, no network calls)
- Running the pipeline scripts with `--mock` flag (no Oracle or Azure calls)
- The Jupyter notebook walkthrough (`notebooks/health_metrics_demo.ipynb`)

---

## Files

### `transformers.csv`
Transformer master table — one row per asset. Schema:

| Column | Type | Description |
|---|---|---|
| asset_id | string | Unique transformer identifier (e.g. TRF001) |
| substation_id | string | Parent substation (e.g. SUB001) |
| transformer_name | string | Human-readable name |
| mva_rated | float | Nameplate MVA capacity — used to normalise all load metrics |
| voltage_class_kv | float | Operating voltage class |
| manufacturer | string | OEM manufacturer |
| year_commissioned | int | Year of installation |
| cooling_type | string | ONAN / ONAF / OFAF |
| latitude | float | Substation coordinates (mock — not real locations) |
| longitude | float | Substation coordinates (mock — not real locations) |
| insulation_class | string | Insulation class (A = standard, B = upgraded) |

### `sensor_readings.csv`
15-minute interval sensor data — one row per asset per timestamp. In production this is sourced from the SCADA/PI historian at 15-min intervals covering 900+ transformers. Schema:

| Column | Type | Description |
|---|---|---|
| asset_id | string | Links to transformer master |
| timestamp | datetime | UTC timestamp (15-min intervals) |
| winding_temp_c | float | Primary winding temperature (°C) |
| oil_temp_c | float | Bulk oil / top-oil temperature (°C) |
| hotspot_temp_c | float | Direct hotspot sensor reading (°C) — not all assets have this |
| mva_actual | float | Actual load (MVA) |
| mva_rated | float | Nameplate capacity — denormalised here for convenience |
| ambient_temp_c | float | IDW-weighted ambient temperature from nearby weather stations |
| tpos | int | Current tap position (e.g. 1–17) |
| tposc | int | Cumulative tap operation count (monotonically increasing odometer) |
| voltage_kv | float | Operating voltage (kV) |

### `work_orders.json`
Array of work order events. In production sourced from the enterprise work order management system. Schema per record:

| Field | Type | Description |
|---|---|---|
| wo_id | string | Unique work order ID |
| asset_id | string | Links to transformer master |
| substation_id | string | Parent substation |
| wo_type | string | PREVENTIVE / CORRECTIVE / EMERGENCY |
| priority | int | 1 (highest) to 5 (lowest) |
| description | string | Engineer-written free text — indexed into Azure AI Search for RAG |
| failure_code | string | Structured failure category (THERMAL_OVERLOAD, OIL_DEGRADATION, etc.) |
| created_date | string | YYYY-MM-DD |
| completion_date | string | YYYY-MM-DD or null if still open |

### `health_scores.csv` / `health_scores.json`
Pre-computed health scores output from `pipeline/composite_score.py`. The JSON version is imported directly by the React app in mock mode. Schema:

| Column | Type | Description |
|---|---|---|
| asset_id | string | Transformer identifier |
| substation_id | string | Parent substation |
| substation_name | string | Human-readable substation name |
| health_score | float | Composite 0–100 score (higher = healthier) |
| risk_band | string | GREEN (>70) / AMBER (40–70) / RED (<40) |
| mean_winding_temp | float | Rolling average winding temperature (°C) |
| hotspot_temp | float | Hotspot temperature (°C) |
| thermal_aging_factor | float | FAA — dimensionless (1.0 = normal rate) |
| overload_severity | float | Cumulative overload score |
| tap_changer_stress | float | Daily tap operations count |
| load_temp_sensitivity | float | Pearson r correlation (load vs winding temp) |
| last_inspection_date | string | YYYY-MM-DD |
| photo_record_id | string | Fulcrum photo record ID (mock- prefix = placeholder) |

---

## Important

- All `photo_record_id` values beginning with `mock-` are placeholders. In mock mode, `InspectionImage.jsx` renders coloured placeholder boxes instead of fetching from Fulcrum.
- Real asset coordinates, client names, and asset identifiers are not present in this directory.
- Do not commit real data here — `.gitignore` blocks `real_*` prefixed files as a safety measure.
