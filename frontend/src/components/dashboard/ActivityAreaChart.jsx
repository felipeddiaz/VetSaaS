import { memo, useMemo, useLayoutEffect, useState } from "react";
import {
  ComposedChart, Bar, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import { useDashboardSeries } from "../../hooks/useDashboardSeries";

/* ── CSS var resolver — SVG attrs can't use var() natively ─── */
const readCssVar = (name, fallback) => {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
};

/* ── Pure helpers (outside component) ─────────────────────── */
const DAYS_SHORT = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

const dayLabel = (dateStr) => {
  const d = new Date(dateStr + "T12:00:00");
  return DAYS_SHORT[d.getDay()];
};

const isCorrupt = (dp) => dp?.lifecycleState === "corrupt";

const transformActivityData = (points) =>
  points.map((p) => ({
    label:   dayLabel(p.bucketDate),
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

/* ── Component ─────────────────────────────────────────────── */
function ActivityAreaChart({ rangeDays = 7 }) {
  const { allPoints, loading } = useDashboardSeries(rangeDays, true);

  // Resolve CSS vars once after mount — SVG attrs don't support var()
  const [colors, setColors] = useState({
    primary: "#1a4434",
    accent:  "#d67b5c",
    muted:   "#8a8a7f",
  });
  useLayoutEffect(() => {
    setColors({
      primary: readCssVar("--c-primary", "#1a4434"),
      accent:  readCssVar("--c-accent",  "#d67b5c"),
      muted:   readCssVar("--c-text-3",  "#8a8a7f"),
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

  if (loading && points.length === 0) {
    return <div className="chart-area"><div className="skeleton-block sk-chart" /></div>;
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
            margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
            barCategoryGap="35%"
          >
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip content={<ActivityTooltip />} />
            <Bar
              dataKey="done"
              name="Completadas"
              stackId="a"
              fill={colors.primary}
              radius={[0, 0, 0, 0]}
              isAnimationActive={false}
            />
            <Bar
              dataKey="noShow"
              name="No-show"
              stackId="a"
              fill={colors.muted}
              radius={[3, 3, 0, 0]}
              isAnimationActive={false}
            />
            <Line
              dataKey="total"
              name="Total"
              stroke={colors.accent}
              strokeWidth={2}
              dot={{ r: 3, fill: colors.accent }}
              activeDot={{ r: 5 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default memo(ActivityAreaChart);
