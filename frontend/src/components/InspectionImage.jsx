/**
 * InspectionImage.jsx — Field inspection photo via BFF proxy
 *
 * Fetches a Fulcrum inspection image through the FastAPI /api/photo endpoint.
 * The Fulcrum API key stays server-side — React only receives image bytes.
 *
 * In mock mode (REACT_APP_MOCK_MODE=true), renders a placeholder instead
 * of making a real /api/photo call.
 */

import { useEffect, useState } from "react";
import { fetchInspectionImage } from "../api/client";

const MOCK_MODE = process.env.REACT_APP_MOCK_MODE === "true";

// Coloured placeholder for mock/demo mode
function MockImagePlaceholder({ assetId, riskBand }) {
  const colours = { RED: "#fee2e2", AMBER: "#fef3c7", GREEN: "#dcfce7" };
  return (
    <div
      className="inspection-image inspection-image--mock"
      style={{ backgroundColor: colours[riskBand] || "#f3f4f6" }}
      title={`Mock inspection image — ${assetId}`}
    >
      <span className="mock-label">📷 {assetId}</span>
      <span className="mock-sub">{riskBand} band</span>
    </div>
  );
}

export default function InspectionImage({ recordId, assetId, riskBand }) {
  const [src,     setSrc]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(false);

  useEffect(() => {
    if (MOCK_MODE || !recordId || recordId.startsWith("mock-")) {
      setLoading(false);
      return;
    }

    let objectUrl = null;

    fetchInspectionImage(recordId)
      .then((url) => {
        objectUrl = url;
        setSrc(url);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));

    // Revoke blob URL on unmount to prevent memory leak
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [recordId]);

  if (MOCK_MODE || (recordId && recordId.startsWith("mock-"))) {
    return <MockImagePlaceholder assetId={assetId} riskBand={riskBand} />;
  }

  if (loading) {
    return <div className="inspection-image inspection-image--loading">Loading…</div>;
  }

  if (error || !src) {
    return (
      <div className="inspection-image inspection-image--error" title={`Image unavailable for ${assetId}`}>
        No image
      </div>
    );
  }

  return (
    <img
      className="inspection-image"
      src={src}
      alt={`Field inspection — ${assetId}`}
      loading="lazy"
    />
  );
}
