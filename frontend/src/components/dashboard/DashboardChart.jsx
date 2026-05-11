import { useState, useMemo, Component } from "react";
import { Chart } from "react-chartjs-2";
import "../../utils/registerCharts";
import LiveIndicator from "./LiveIndicator";

const MONTH_ABBR = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"];

function fmtDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTH_ABBR[m - 1]}`;
}

function fmtInt(v) {
  return Number(v ?? 0).toLocaleString("es-MX");
}

function cssVar(name) {
  try {
    if (typeof window === "undefined") return "";
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  } catch {
    return "";
  }
}

function buildChartData(allPoints) {
  if (!allPoints?.length) return null;
  const labels = allPoints.map((p) => fmtDate(p.bucketDate));
  const meta = allPoints.map((p) => ({
    fullDate: p.bucketDate,
    isMissing: p.isMissing,
    isLive: p.isLive,
    isProvisional: p.isProvisional,
  }));
  const totalData = allPoints.map((p) => {
    if (p.isMissing || !p.metrics) return 0;
    return p.metrics.appointmentsTotal || 0;
  });
  const doneData = allPoints.map((p) => {
    if (p.isMissing || !p.metrics) return NaN;
    return p.metrics.appointmentsDone || 0;
  });
  const primary = cssVar("--c-primary") || "#1a4434";
  const accent = cssVar("--c-accent") || "#d67b5c";
  const barColors = allPoints.map((p) => {
    if (p.isMissing) return "transparent";
    if (p.isLive) return accent;
    if (p.isProvisional) return `${primary}88`;
    return primary;
  });
  return {
    labels,
    meta,
    datasets: [
      {
        type: "bar", label: "Citas", data: totalData,
        backgroundColor: barColors, borderColor: barColors.map(() => "transparent"),
        borderWidth: 0, borderRadius: 3, order: 2,
      },
      {
        type: "line", label: "Completadas", data: doneData,
        borderColor: accent, backgroundColor: accent,
        borderWidth: 2, pointRadius: 0, pointHoverRadius: 5,
        pointHoverBackgroundColor: accent, pointHoverBorderColor: cssVar("--c-surface") || "#fbf8f1",
        pointHoverBorderWidth: 2, spanGaps: false, tension: 0.2, order: 1,
      },
    ],
  };
}

const DashboardChart = ({ allPoints, hasCorrupt }) => {
  const [chartError, setChartError] = useState(false);
  const chartData = useMemo(() => {
    try { return buildChartData(allPoints); }
    catch { return null; }
  }, [allPoints]);

  const hasLive = allPoints.some((p) => p.isLive);

  const options = useMemo(() => ({
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: cssVar("--c-surface") || "#fff",
        titleColor: cssVar("--c-text") || "#1a1a1a",
        bodyColor: cssVar("--c-text-2") || "#3a3a3a",
        borderColor: cssVar("--c-border") || "#e0dcd0",
        borderWidth: 1, cornerRadius: 8, padding: 10,
        titleFont: { size: 11 }, bodyFont: { size: 11 },
        callbacks: {
          title(items) {
            if (!items?.length) return "";
            const idx = items[0]?.dataIndex;
            const m = chartData?.meta?.[idx];
            if (!m) return "";
            const extras = [];
            if (m.isLive) extras.push("HOY");
            if (m.isProvisional) extras.push("Provisional");
            if (m.isMissing) extras.push("Sin datos");
            return `${m.fullDate}${extras.length ? " · " + extras.join(" · ") : ""}`;
          },
          label(ctx) {
            if (ctx.dataset?.type === "line" && isNaN(ctx.raw)) return "Completadas: —";
            const label = ctx.dataset?.label || "";
            const val = ctx.raw != null ? fmtInt(ctx.raw) : "—";
            return `${label}: ${val}`;
          },
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { font: { size: 9 }, color: cssVar("--c-text-3") || "#8a8a7f", maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
        border: { color: cssVar("--c-border") || "#e0dcd0" },
      },
      y: {
        grid: { color: cssVar("--c-border") || "#e0dcd0", drawTicks: false },
        ticks: { font: { size: 10 }, color: cssVar("--c-text-3") || "#8a8a7f", precision: 0 },
        border: { display: false }, beginAtZero: true,
      },
    },
  }), [chartData]);

  if (chartError) {
    return (
      <div className="card" style={{ minHeight: 220, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: "var(--c-text-3)", fontSize: "12px", textAlign: "center" }}>
          No se pudo cargar la gráfica.
          <br />
          <button className="btn btn-ghost btn-xs" onClick={() => setChartError(false)} style={{ marginTop: "8px" }}>
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  if (!chartData) {
    return (
      <div className="card" style={{ minHeight: 220, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: "var(--c-text-4)", fontSize: "13px" }}>Sin datos para el periodo seleccionado.</div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Actividad diaria · 30 días</span>
        <span style={{ display: "flex", gap: "14px", fontSize: "11px", color: "var(--c-text-2)", fontFamily: "var(--font-display)", fontWeight: "500" }}>
          <span className="db-legend-item"><span className="db-legend-swatch" style={{ background: "var(--c-primary)" }} />Citas totales</span>
          <span className="db-legend-item"><span className="db-legend-swatch" style={{ background: "var(--c-accent)", width: "14px", height: "2px", borderRadius: "1px" }} />Completadas</span>
        </span>
      </div>
      <div className="db-chart-area" style={{ height: 220 }}>
        <ErrorCatcher onError={() => setChartError(true)}>
          <Chart type="bar" data={chartData} options={options} />
        </ErrorCatcher>
      </div>
      <div className="db-chart-footer">
        {hasLive && <LiveIndicator />}
      </div>
      {hasCorrupt && (
        <div style={{ marginTop: "8px", padding: "10px 14px", borderRadius: "8px", background: "var(--c-warning-bg)", border: "1px solid var(--c-warning-border)", display: "flex", alignItems: "center", gap: "10px", fontSize: "11.5px", color: "var(--c-warning-text)", fontWeight: "500" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--c-warning-text)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>Algunos datos no están disponibles. Se está regenerando la información. Si persiste, contacta a soporte.</span>
        </div>
      )}
    </div>
  );
};

class ErrorCatcher extends Component {
  constructor(props) { super(props); this.state = { err: false }; }
  static getDerivedStateFromError() { return { err: true }; }
  componentDidCatch(err) { this.props.onError?.(); console.warn("[Chart]", err.message); }
  render() { return this.state.err ? null : this.props.children; }
}

export default DashboardChart;
