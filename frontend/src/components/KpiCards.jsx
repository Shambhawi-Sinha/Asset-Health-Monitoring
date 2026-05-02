/**
 * KpiCards.jsx — Fleet-level KPI summary cards
 *
 * Displays four top-level metrics derived from /api/images data:
 *   - Total substations monitored
 *   - Critical (RED band) count
 *   - At-risk (AMBER band) count
 *   - Healthy (GREEN band) count
 *
 * Each card shows a count and a percentage of total fleet.
 * RED and AMBER cards are visually highlighted to draw attention.
 */

export default function KpiCards({ records }) {
  if (!records || records.length === 0) {
    return <div className="kpi-cards kpi-cards--empty">No data loaded.</div>;
  }

  const total  = records.length;
  const red    = records.filter((r) => r.risk_band === "RED").length;
  const amber  = records.filter((r) => r.risk_band === "AMBER").length;
  const green  = records.filter((r) => r.risk_band === "GREEN").length;
  const avgScore = (
    records.reduce((sum, r) => sum + (r.health_score || 0), 0) / total
  ).toFixed(1);

  const cards = [
    {
      label:    "Total Transformers",
      value:    total,
      sub:      `Avg health score: ${avgScore}`,
      variant:  "neutral",
    },
    {
      label:    "Critical — RED",
      value:    red,
      sub:      `${((red / total) * 100).toFixed(1)}% of fleet`,
      variant:  "red",
    },
    {
      label:    "At Risk — AMBER",
      value:    amber,
      sub:      `${((amber / total) * 100).toFixed(1)}% of fleet`,
      variant:  "amber",
    },
    {
      label:    "Healthy — GREEN",
      value:    green,
      sub:      `${((green / total) * 100).toFixed(1)}% of fleet`,
      variant:  "green",
    },
  ];

  return (
    <div className="kpi-cards">
      {cards.map((card) => (
        <div key={card.label} className={`kpi-card kpi-card--${card.variant}`}>
          <div className="kpi-card__label">{card.label}</div>
          <div className="kpi-card__value">{card.value}</div>
          <div className="kpi-card__sub">{card.sub}</div>
        </div>
      ))}
    </div>
  );
}
