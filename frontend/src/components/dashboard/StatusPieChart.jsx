import { useState, useMemo, Component } from "react";
import { Doughnut } from "react-chartjs-2";
import "../../utils/registerCharts";

function cssVar(name) {
  try { if (typeof window === "undefined") return ""; return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  catch { return ""; }
}

const PIE_FILLS = {
  scheduled:   "#1e40af",
  confirmed:   "#5b21b6",
  in_progress: "#d67b5c",
  done:        "#1a5c3a",
  canceled:    "#991b1b",
  no_show:     "#8a8a7f",
};

const StatusPieChart = ({ pieData, grandTotal, onSelect, selectedKey }) => {
  const [chartError, setChartError] = useState(false);
  const [localActive, setLocalActive] = useState(null);
  const activeKey = selectedKey ?? localActive;

  const chartData = useMemo(() => {
    try {
      if (!pieData?.length) return null;
      return {
        labels: pieData.map((d) => d.name),
        datasets: [{
          data: pieData.map((d) => d.value),
          backgroundColor: pieData.map((d) => PIE_FILLS[d.key] || "#8a8a7f"),
          borderColor: pieData.map(() => cssVar("--c-surface") || "#fbf8f1"),
          borderWidth: 1.5,
          hoverBorderWidth: 2,
          hoverBorderColor: cssVar("--c-text") || "#1a1a1a",
          spacing: 2,
        }],
      };
    } catch { return null; }
  }, [pieData]);

  const options = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    cutout: "58%",
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          font: { size: 10 }, color: cssVar("--c-text-2") || "#3a3a3a",
          padding: 12, usePointStyle: true, pointStyleWidth: 8,
        },
      },
      tooltip: {
        backgroundColor: cssVar("--c-surface") || "#fff",
        titleColor: cssVar("--c-text") || "#1a1a1a",
        bodyColor: cssVar("--c-text-2") || "#3a3a3a",
        borderColor: cssVar("--c-border") || "#e0dcd0",
        borderWidth: 1, cornerRadius: 8, padding: 10,
        titleFont: { size: 11 }, bodyFont: { size: 11 },
        callbacks: {
          label(ctx) {
            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
            const pct = total > 0 ? Math.round((ctx.raw / total) * 100) : 0;
            return ` ${ctx.label}: ${ctx.raw}${grandTotal >= 10 ? ` (${pct}%)` : ""}`;
          },
        },
      },
    },
    onClick(_event, elements) {
      if (!elements?.length) {
        setLocalActive(null);
        onSelect?.(null);
        return;
      }
      const idx = elements[0]?.index;
      const key = pieData?.[idx]?.key;
      if (key) {
        const next = key === activeKey ? null : key;
        setLocalActive(next);
        onSelect?.(next);
      }
    },
  }), [pieData, grandTotal, activeKey, onSelect]);

  if (chartError) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--c-text-3)", fontSize: "11px", textAlign: "center" }}>
        No se pudo cargar la gráfica.
        <button className="btn btn-ghost btn-xs" onClick={() => setChartError(false)} style={{ marginLeft: "8px" }}>Reintentar</button>
      </div>
    );
  }

  if (!chartData) {
    return <div className="db-pie-empty">Sin citas en este periodo.</div>;
  }

  return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", width: "100%" }}>
      <div style={{ width: "100%", height: 200 }}>
        <ErrorCatcher onError={() => setChartError(true)}>
          <Doughnut data={chartData} options={options} />
        </ErrorCatcher>
      </div>
    </div>
  );
};

class ErrorCatcher extends Component {
  constructor(props) { super(props); this.state = { err: false }; }
  static getDerivedStateFromError() { return { err: true }; }
  componentDidCatch(err) { this.props.onError?.(); console.warn("[Pie]", err.message); }
  render() { return this.state.err ? null : this.props.children; }
}

export default StatusPieChart;
