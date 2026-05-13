import { memo, useState, useMemo, useLayoutEffect, Component } from "react";
import {
  ComposedChart, Bar, Line, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import LiveIndicator from "./LiveIndicator";

/* ── CSS var resolver — SVG attrs can't use var() natively ─── */
const readCssVar = (name, fallback) => {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
};

/* ── Pure helpers (outside component) ─────────────────────── */
const MONTH_ABBR = ["ENE","FEB","MAR","ABR","MAY","JUN","JUL","AGO","SEP","OCT","NOV","DIC"];

const fmtDate = (iso) => {
  if (!iso) return "";
  const [, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTH_ABBR[m - 1]}`;
};

const fmtInt = (v) => Number(v ?? 0).toLocaleString("es-MX");

const resolveBarColor = (entry, primary, accent) => {
  if (entry.isMissing)     return "transparent";
  if (entry.isLive)        return accent;
  if (entry.isProvisional) return `${primary}88`;
  return primary;
};

const transformOpsData = (points) =>
  points.map((p) => ({
    label:         fmtDate(p.bucketDate),
    fullDate:      p.bucketDate,
    total:         (p.isMissing || !p.metrics) ? 0   : (p.metrics.appointmentsTotal || 0),
    done:          (p.isMissing || !p.metrics) ? NaN : (p.metrics.appointmentsDone  || 0),
    isMissing:     !!p.isMissing,
    isLive:        !!p.isLive,
    isProvisional: !!p.isProvisional,
  }));

/* ── Tooltip ───────────────────────────────────────────────── */
const OpsTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;

  const extras = [];
  if (d.isLive)        extras.push({ label: "HOY",         cls: "chart-tooltip-live" });
  if (d.isProvisional) extras.push({ label: "Provisional", cls: "chart-tooltip-provisional" });
  if (d.isMissing)     extras.push({ label: "Sin datos",   cls: "chart-tooltip-missing" });

  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip-title">
        {d.fullDate}
        {extras.map((e) => (
          <span key={e.label} className={`chart-tooltip-meta ${e.cls}`}>
            {" · "}{e.label}
          </span>
        ))}
      </p>
      {d.isMissing ? (
        <p className="chart-tooltip-meta chart-tooltip-missing">Sin datos disponibles</p>
      ) : (
        <>
          <div className="chart-tooltip-row">
            <span className="chart-tooltip-dot" style={{ "--dot-color": readCssVar("--c-primary", "#1a4434") }} />
            <span>Citas totales</span>
            <span className="chart-tooltip-val">{fmtInt(d.total)}</span>
          </div>
          <div className="chart-tooltip-row">
            <span className="chart-tooltip-dot" style={{ "--dot-color": readCssVar("--c-accent", "#d67b5c") }} />
            <span>Completadas</span>
            <span className="chart-tooltip-val">{isNaN(d.done) ? "—" : fmtInt(d.done)}</span>
          </div>
        </>
      )}
    </div>
  );
};

/* ── Component ─────────────────────────────────────────────── */
function DashboardChart({ allPoints, hasCorrupt }) {
  const [chartError, setChartError] = useState(false);

  // Resolve CSS vars once after mount — SVG attrs don't support var()
  const [colors, setColors] = useState({
    primary: "#1a4434",
    accent:  "#d67b5c",
    text3:   "#8a8a7f",
    border:  "#d9d2be",
  });
  useLayoutEffect(() => {
    setColors({
      primary: readCssVar("--c-primary", "#1a4434"),
      accent:  readCssVar("--c-accent",  "#d67b5c"),
      text3:   readCssVar("--c-text-3",  "#8a8a7f"),
      border:  readCssVar("--c-border",  "#d9d2be"),
    });
  }, []);

  const chartData = useMemo(() => transformOpsData(allPoints ?? []), [allPoints]);
  const hasLive   = useMemo(() => (allPoints ?? []).some((p) => p.isLive), [allPoints]);

  if (chartError) {
    return (
      <div className="chart-state-wrap">
        <div className="chart-state-msg">
          No se pudo cargar la gráfica.
          <br />
          <button className="btn btn-ghost btn-xs chart-retry-btn" onClick={() => setChartError(false)}>
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  if (!chartData.length) {
    return (
      <div className="chart-state-wrap">
        <div className="chart-state-empty">Sin datos para el periodo seleccionado.</div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Actividad diaria · 30 días</span>
        <span className="chart-legend-inline">
          <span className="chart-legend-item">
            <span className="chart-dot chart-dot-primary" />Citas totales
          </span>
          <span className="chart-legend-item">
            <span className="chart-dot chart-dot-accent-line" />Completadas
          </span>
        </span>
      </div>
      <div className="db-chart-area">
        <ErrorCatcher onError={() => setChartError(true)}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <XAxis
                dataKey="label"
                tick={{ fontSize: 9, fill: colors.text3 }}
                axisLine={{ stroke: colors.border }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 10, fill: colors.text3 }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip content={<OpsTooltip />} />
              <Bar dataKey="total" name="Citas" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                {chartData.map((entry, i) => (
                  <Cell key={i} fill={resolveBarColor(entry, colors.primary, colors.accent)} />
                ))}
              </Bar>
              <Line
                dataKey="done"
                name="Completadas"
                stroke={colors.accent}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 5, fill: colors.accent }}
                connectNulls={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </ErrorCatcher>
      </div>
      <div className="db-chart-footer">
        {hasLive && <LiveIndicator />}
      </div>
      {hasCorrupt && (
        <div className="chart-corrupt-banner">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>Algunos datos no están disponibles. Se está regenerando la información. Si persiste, contacta a soporte.</span>
        </div>
      )}
    </div>
  );
}

class ErrorCatcher extends Component {
  constructor(props) { super(props); this.state = { err: false }; }
  static getDerivedStateFromError() { return { err: true }; }
  componentDidCatch(err) { this.props.onError?.(); console.warn("[Chart]", err.message); }
  render() { return this.state.err ? null : this.props.children; }
}

export default memo(DashboardChart);
