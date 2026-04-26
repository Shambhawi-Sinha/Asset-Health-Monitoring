/**
 * api/client.js — Parallel data fetching for the React dashboard
 *
 * Both Oracle queries (health records + work order summaries) fire simultaneously
 * using Promise.all. This halves dashboard load time compared to sequential fetches.
 *
 * Sequential (naive):   /api/images (2s) → /api/report (2s) = 4s total
 * Parallel (this file): /api/images      +
 *                        /api/report      = MAX(2s, 2s) = 2s total  ✓
 *
 * The load time is displayed in the dashboard header for transparency
 * and to demonstrate the optimisation to the client team.
 */

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:5000";

/**
 * Fetch both dashboard datasets in parallel.
 *
 * @returns {{ images: Array, report: Array, loadTimeMs: number }}
 */
export async function fetchDashboardData() {
  const start = performance.now();

  const [imagesResponse, reportResponse] = await Promise.all([
    fetch(`${API_BASE}/api/images`),
    fetch(`${API_BASE}/api/report`),
  ]);

  if (!imagesResponse.ok) {
    throw new Error(`/api/images returned ${imagesResponse.status}`);
  }
  if (!reportResponse.ok) {
    throw new Error(`/api/report returned ${reportResponse.status}`);
  }

  const [images, report] = await Promise.all([
    imagesResponse.json(),
    reportResponse.json(),
  ]);

  const loadTimeMs = Math.round(performance.now() - start);

  return { images, report, loadTimeMs };
}

/**
 * Fetch a Fulcrum inspection image via the FastAPI BFF proxy.
 * Returns a blob URL safe for use in <img src="..." />.
 *
 * The Fulcrum API key never touches the browser — all auth happens in FastAPI.
 *
 * @param {string} recordId — Fulcrum photo record ID
 * @returns {Promise<string>} object URL for the image blob
 */
export async function fetchInspectionImage(recordId) {
  const response = await fetch(
    `${API_BASE}/api/photo?record_id=${encodeURIComponent(recordId)}`
  );
  if (!response.ok) {
    throw new Error(`/api/photo returned ${response.status} for record ${recordId}`);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}
