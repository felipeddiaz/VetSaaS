import { memo, useMemo, useLayoutEffect, useState } from "react";
import {
  ComposedChart, Bar, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import { useDashboardSeries } from "../../hooks/useDashboardSeries";
import { Icon } from "../icons";

/* ── CSS var resolver — SVG attrs can't use var() natively ─── */
const readCssVar = (name, fallback) => {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
};

/* ── Pure helpers (outside component) ─────────────────────── */
const DAYS_SHORT = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

const dayLabel = (dateStr) => {
  if (!dateStr) return "—";
  const d = new Date(dateStr + "T12:00:00");
  const day = d.getDay();
  return isNaN(day) ? "—" : DAYS_SHORT[day];
};

const isCorrupt = (dp) => dp?.lifecycleState === "corrupt";

const transformActivityData = (points) =>
  (points || []).map((p) => ({
    label:   dayLabel(p?.bucketDate),
    done:    isCorrupt(p) ? null : (p.metrics?.appointmentsDone   ?? 0),
    noShow:  isCorrupt(p) ? null : (p.metrics?.appointmentsNoShow ?? 0),
    total:   isCorrupt(p) ? null : (p.metrics?.appointmentsTotal  ?? 0),
    corrupt: isCorrupt(p),
  }));

/* ── Tooltip ───────────────────────────────────────────────── */
const ActivityTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const entry = payload[0]?.payload;
  if (entry?.corrupt) {
    return (
      <div className="chart-tooltip">
        <p className="chart-tooltip-title">{label}</p>
        <p className="chart-tooltip-meta">Datos no disponibles</p>
      </div>
    );
  }
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip-title">{label}</p>
      {payload.map((p) => (
        <div key={p.dataKey} className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ "--dot-color": p.fill || p.stroke }} />
          <span>{p.name}</span>
          <span className="chart-tooltip-val">{p.value ?? "—"}</span>
        </div>
      ))}
    </div>
  );
};

/* ── Empty State / Onboarding Preview ─────────────────────── */
const ChartEmptyState = ({ colors }) => (
  <div className="chart-empty-premium">
    <div className="chart-empty-bg">
      {/* Faded mockup of a building chart */}
      <svg width="100%" height="120" viewBox="0 0 400 120" preserveAspectRatio="none" style={{ opacity: 0.15 }}>
        <path d="M0,100 L40,80 L80,90 L120,40 L160,60 L200,30 L240,50 L280,20 L320,40 L360,10 L400,30" 
              fill="none" stroke={colors.primary} strokeWidth="3" strokeDasharray="5,5" />
        <rect x="30" y="70" width="20" height="30" fill={colors.primary} opacity="0.4" />
        <rect x="70" y="80" width="20" height="20" fill={colors.primary} opacity="0.4" />
        <rect x="110" y="30" width="20" height="70" fill={colors.primary} opacity="0.4" />
      </svg>
    </div>
    <div className="chart-empty-content">
      <div className="chart-empty-icon"><Icon.TrendUp s={24} /></div>
      <h4 className="chart-empty-title">Construyendo tendencias</h4>
      <p className="chart-empty-text">
        Aún no hay suficiente actividad registrada para proyectar tendencias semanales. 
        Tus métricas aparecerán automáticamente conforme completes más consultas.
      </p>
    </div>
  </div>
);

/* ── Component ─────────────────────────────────────────────── */
function ActivityAreaChart({ rangeDays = 7 }) {
  const { allPoints, loading } = useDashboardSeries(rangeDays, true);

  const [colors, setColors] = useState({
    primary: "#10b981",
    accent:  "#d67b5c",
    muted:   "#8a8a7f",
  });
  useLayoutEffect(() => {
    setColors({
      primary: readCssVar("--c-success-text", "#10b981"),
      accent:  readCssVar("--c-accent",       "#d67b5c"),
      muted:   readCssVar("--c-text-3",       "#8a8a7f"),
    });
  }, []);

  const points = useMemo(
    () =>
      (allPoints ?? [])
        .filter((p) => p && !p.isMissing)
        .sort((a, b) => (a.bucketDate > b.bucketDate ? 1 : -1)),
    [allPoints]
  );

  const chartData  = useMemo(() => transformActivityData(points ?? []), [points]);
  const hasCorrupt = useMemo(() => points.some(isCorrupt), [points]);
  
  // Real data check: do we have at least 2 days with non-zero total activity?
  const hasData = useMemo(() => {
    return chartData.filter(d => (d.total || 0) > 0).length >= 2;
  }, [chartData]);

  if (loading && points.length === 0) {
    return <div className="chart-area"><div className="skeleton-block sk-chart" /></div>;
  }

  if (!hasData) {
    return <div className="chart-area"><ChartEmptyState colors={colors} /></div>;
  }

  return (
    <div className="chart-area">
      {hasCorrupt && (
        <div className="chart-corrupt-banner">
          Datos temporalmente no disponibles para algunas fechas.
        </div>
      )}
      <div className="chart-legend">
        <span className="chart-legend-item">
          <span className="chart-dot chart-dot-primary" /> Completadas
        </span>
        <span className="chart-legend-item">
          <span className="chart-dot chart-dot-muted" /> No-show
        </span>
        <span className="chart-legend-item">
          <span className="chart-dot chart-dot-line chart-dot-accent" /> Total
        </span>
      </div>
      <div className="chart-canvas-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 12, right: 12, left: -20, bottom: 0 }}
            barCategoryGap="35%"
          >
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fontWeight: 500, fill: colors.muted }}
              axisLine={false}
              tickLine={false}
              dy={8}
            />
            <YAxis
              tick={{ fontSize: 11, fontWeight: 500, fill: colors.muted }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
              dx={-8}
            />
            <Tooltip content={<ActivityTooltip />} />
            <Bar
              dataKey="done"
              name="Completadas"
              stackId="a"
              fill={colors.primary}
              radius={[0, 0, 0, 0]}
              isAnimationActive={true}
              animationDuration={1000}
            />
            <Bar
              dataKey="noShow"
              name="No-show"
              stackId="a"
              fill={colors.muted}
              radius={[3, 3, 0, 0]}
              isAnimationActive={true}
              animationDuration={1000}
            />
            <Line
              type="monotone"
              dataKey="total"
              name="Total"
              stroke={colors.accent}
              strokeWidth={3}
              dot={{ r: 4, fill: colors.accent, strokeWidth: 2, stroke: '#fff' }}
              activeDot={{ r: 6, strokeWidth: 0 }}
              connectNulls={false}
              isAnimationActive={true}
              animationDuration={1200}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default memo(ActivityAreaChart);
