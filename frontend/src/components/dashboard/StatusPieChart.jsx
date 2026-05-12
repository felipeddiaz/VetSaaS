import { memo, useState, useMemo, Component } from "react";
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";

/* ── Constants (outside component) ────────────────────────── */
const PIE_FILLS = {
  scheduled:   "#1e40af",
  confirmed:   "#5b21b6",
  in_progress: "#d67b5c",
  done:        "#1a5c3a",
  canceled:    "#991b1b",
  no_show:     "#8a8a7f",
};

/* ── Pure helpers ──────────────────────────────────────────── */
const transformPieData = (data) =>
  (data ?? []).map((d) => ({
    key:   d.key,
    name:  d.name,
    value: d.value,
    fill:  PIE_FILLS[d.key] || "#8a8a7f",
  }));

/* ── Tooltip ───────────────────────────────────────────────── */
const StatusTooltip = ({ active, payload, grandTotal }) => {
  if (!active || !payload?.length) return null;
  const { name, value, fill } = payload[0].payload;
  const total = grandTotal ?? 0;
  const pct   = total >= 10 && value != null
    ? ` (${Math.round((value / total) * 100)}%)`
    : "";
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-row">
        <span className="chart-tooltip-dot" style={{ "--dot-color": fill }} />
        <span>{name}</span>
        <span className="chart-tooltip-val">{value ?? "—"}{pct}</span>
      </div>
    </div>
  );
};

/* ── Component ─────────────────────────────────────────────── */
function StatusPieChart({ pieData, grandTotal, onSelect, selectedKey }) {
  const [chartError, setChartError] = useState(false);
  const [localActive, setLocalActive] = useState(null);
  const activeKey = selectedKey ?? localActive;

  const chartData = useMemo(() => transformPieData(pieData ?? []), [pieData]);

  const handleClick = (_, index) => {
    const key  = chartData[index]?.key;
    if (!key) return;
    const next = key === activeKey ? null : key;
    setLocalActive(next);
    onSelect?.(next);
  };

  const handleEmpty = () => {
    setLocalActive(null);
    onSelect?.(null);
  };

  if (chartError) {
    return (
      <div className="pie-state-wrap">
        No se pudo cargar la gráfica.
        <button
          className="btn btn-ghost btn-xs pie-retry-btn"
          onClick={() => setChartError(false)}
        >
          Reintentar
        </button>
      </div>
    );
  }

  if (!chartData.length) {
    return <div className="db-pie-empty">Sin citas en este periodo.</div>;
  }

  return (
    <div className="pie-chart-wrap">
      <ErrorCatcher onError={() => setChartError(true)}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart onClick={handleEmpty}>
            <Pie
              data={chartData}
              dataKey="value"
              nameKey="name"
              innerRadius="52%"
              outerRadius="80%"
              paddingAngle={2}
              onClick={handleClick}
              isAnimationActive={false}
            >
              {chartData.map((entry) => (
                <Cell
                  key={entry.key}
                  fill={entry.fill}
                  stroke={activeKey === entry.key ? "var(--c-text)" : "var(--c-surface)"}
                  strokeWidth={activeKey === entry.key ? 2 : 1.5}
                />
              ))}
            </Pie>
            <Tooltip
              content={(props) => (
                <StatusTooltip {...props} grandTotal={grandTotal} />
              )}
            />
            <Legend
              iconType="circle"
              iconSize={8}
              wrapperStyle={{ fontSize: "10px", color: "var(--c-text-2)" }}
            />
          </PieChart>
        </ResponsiveContainer>
      </ErrorCatcher>
    </div>
  );
}

class ErrorCatcher extends Component {
  constructor(props) { super(props); this.state = { err: false }; }
  static getDerivedStateFromError() { return { err: true }; }
  componentDidCatch(err) { this.props.onError?.(); console.warn("[Pie]", err.message); }
  render() { return this.state.err ? null : this.props.children; }
}

export default memo(StatusPieChart);
