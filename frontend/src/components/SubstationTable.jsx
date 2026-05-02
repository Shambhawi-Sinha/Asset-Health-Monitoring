/**
 * SubstationTable.jsx — Searchable, sortable transformer health table
 *
 * Joins /api/images (health scores) with /api/report (work order summaries)
 * on asset_id to show a unified view per transformer.
 *
 * Features:
 *   - Client-side search by asset ID or substation name
 *   - Click column headers to sort ascending/descending
 *   - Risk band colour coding: RED / AMBER / GREEN
 *   - Open emergency WO count highlighted in red if > 0
 */

import { useState, useMemo } from "react";

const RISK_COLOURS = {
  RED:   { bg: "#fee2e2", text: "#991b1b", border: "#f87171" },
  AMBER: { bg: "#fef3c7", text: "#92400e", border: "#fbbf24" },
  GREEN: { bg: "#dcfce7", text: "#166534", border: "#4ade80" },
};

const COLUMNS = [
  { key: "asset_id",             label: "Asset ID",         sortable: true  },
  { key: "substation_name",      label: "Substation",       sortable: true  },
  { key: "health_score",         label: "Health Score",     sortable: true  },
  { key: "risk_band",            label: "Risk Band",        sortable: true  },
  { key: "hotspot_temp",         label: "Hotspot (°C)",     sortable: true  },
  { key: "thermal_aging_factor", label: "FAA",              sortable: true  },
  { key: "open_emergency_wos",   label: "Open Emergency WOs", sortable: true },
  { key: "last_inspection_date", label: "Last Inspection",  sortable: true  },
];

function RiskBadge({ band }) {
  const style = RISK_COLOURS[band] || {};
  return (
    <span
      className="risk-badge"
      style={{
        backgroundColor: style.bg,
        color: style.text,
        border: `1px solid ${style.border}`,
        padding: "2px 8px",
        borderRadius: "12px",
        fontSize: "0.75rem",
        fontWeight: 600,
      }}
    >
      {band}
    </span>
  );
}

export default function SubstationTable({ images, report }) {
  const [search,  setSearch]  = useState("");
  const [sortKey, setSortKey] = useState("health_score");
  const [sortAsc, setSortAsc] = useState(true);

  // Join images + report on asset_id
  const reportMap = useMemo(() => {
    const m = {};
    for (const r of report || []) m[r.asset_id] = r;
    return m;
  }, [report]);

  const rows = useMemo(() => {
    return (images || []).map((img) => ({
      ...img,
      open_emergency_wos: reportMap[img.asset_id]?.open_emergency_wos ?? 0,
      last_wo_type:       reportMap[img.asset_id]?.last_wo_type ?? "—",
    }));
  }, [images, reportMap]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter(
      (r) =>
        r.asset_id?.toLowerCase().includes(q) ||
        r.substation_name?.toLowerCase().includes(q)
    );
  }, [rows, search]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const va = a[sortKey] ?? "";
      const vb = b[sortKey] ?? "";
      if (typeof va === "number" && typeof vb === "number") {
        return sortAsc ? va - vb : vb - va;
      }
      return sortAsc
        ? String(va).localeCompare(String(vb))
        : String(vb).localeCompare(String(va));
    });
  }, [filtered, sortKey, sortAsc]);

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortAsc((prev) => !prev);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const fmt = (val, key) => {
    if (val === null || val === undefined) return "—";
    if (key === "health_score") return val.toFixed(1);
    if (key === "hotspot_temp" || key === "mean_winding_temp")
      return `${parseFloat(val).toFixed(1)}°C`;
    if (key === "thermal_aging_factor") return parseFloat(val).toFixed(2);
    return String(val);
  };

  return (
    <div className="substation-table-wrapper">
      <div className="table-controls">
        <input
          className="table-search"
          type="text"
          placeholder="Search by asset ID or substation name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="table-count">{sorted.length} of {rows.length} assets</span>
      </div>

      <div className="table-scroll">
        <table className="substation-table">
          <thead>
            <tr>
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className={`th ${col.sortable ? "th--sortable" : ""} ${sortKey === col.key ? "th--active" : ""}`}
                  onClick={() => col.sortable && handleSort(col.key)}
                >
                  {col.label}
                  {col.sortable && (
                    <span className="sort-indicator">
                      {sortKey === col.key ? (sortAsc ? " ▲" : " ▼") : " ⇅"}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={row.asset_id} className="tr">
                {COLUMNS.map((col) => (
                  <td key={col.key} className="td">
                    {col.key === "risk_band" ? (
                      <RiskBadge band={row.risk_band} />
                    ) : col.key === "open_emergency_wos" && row.open_emergency_wos > 0 ? (
                      <span style={{ color: "#dc2626", fontWeight: 700 }}>
                        {row.open_emergency_wos}
                      </span>
                    ) : (
                      fmt(row[col.key], col.key)
                    )}
                  </td>
                ))}
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="td td--empty">
                  No results match "{search}"
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
