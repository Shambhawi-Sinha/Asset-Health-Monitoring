/**
 * HealthTrendChart.jsx — Average fleet health score over time
 *
 * Groups health score records by last_inspection_date and plots the
 * average score per date as a line chart using Recharts.
 *
 * Shows whether the fleet's overall health is improving or deteriorating.
 * A declining trend is a fleet-level risk signal even if no single transformer
 * has crossed into RED yet.
 *
 * Data source: /api/images (last_inspection_date + health_score per record)
 */

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Legend,
} from "recharts";

// Risk band reference lines — helps engineers read the chart at a glance
const AMBER_THRESHOLD = 70;
const RED_THRESHOLD   = 40;

function groupByDate(records) {
  const byDate = {};
  for (const rec of records) {
    const date = rec.last_inspection_date;
    if (!date) continue;
    if (!byDate[date]) byDate[date] = [];
    byDate[date].push(rec.health_score || 0);
  }
  return Object.entries(byDate)
    .map(([date, scores]) => ({
      date,
      avg_score: parseFloat(
        (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1)
      ),
      count: scores.length,
    }))
    .sort((a, b) => new Date(a.date) - new Date(b.date));
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__date">{label}</p>
      <p className="chart-tooltip__score">Avg Score: <strong>{d.avg_score}</strong></p>
      <p className="chart-tooltip__count">{d.count} transformer{d.count !== 1 ? "s" : ""} inspected</p>
    </div>
  );
}

export default function HealthTrendChart({ records }) {
  if (!records || records.length === 0) {
    return <div className="chart-empty">No inspection data available.</div>;
  }

  const data = groupByDate(records);

  if (data.length < 2) {
    return (
      <div className="chart-empty">
        Trend chart requires data from at least 2 inspection dates.
      </div>
    );
  }

  return (
    <div className="health-trend-chart">
      <h3 className="chart-title">Fleet Health Score Trend</h3>
      <p className="chart-subtitle">Average health score across all inspected assets by date</p>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />

          <XAxis
            dataKey="date"
            tick={{ fontSize: 12 }}
            tickFormatter={(d) => d.slice(5)}   // show MM-DD only
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 12 }}
            label={{ value: "Health Score", angle: -90, position: "insideLeft", offset: 10, fontSize: 12 }}
          />

          {/* Risk band reference lines */}
          <ReferenceLine y={AMBER_THRESHOLD} stroke="#f59e0b" strokeDasharray="6 3"
            label={{ value: "AMBER", position: "right", fontSize: 11, fill: "#f59e0b" }} />
          <ReferenceLine y={RED_THRESHOLD} stroke="#ef4444" strokeDasharray="6 3"
            label={{ value: "RED", position: "right", fontSize: 11, fill: "#ef4444" }} />

          <Tooltip content={<CustomTooltip />} />
          <Legend />

          <Line
            type="monotone"
            dataKey="avg_score"
            name="Avg Health Score"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={{ r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
