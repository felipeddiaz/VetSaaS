import { memo, useId, useMemo } from "react";
import {
  AreaChart, Area,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import { useFinancialSeries } from "../../hooks/useFinancialSeries";

/* ── Pure helpers (outside component) ─────────────────────── */
const DAYS_SHORT = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

const dayLabel = (dateStr) => {
  const d = new Date(dateStr + "T12:00:00");
  return `${DAYS_SHORT[d.getDay()]} ${d.getDate()}`;
};

const fmtMXN = (v) =>
  v != null ? `$${Number(v).toLocaleString("es-MX")}` : "—";

const transformRevenueData = (points) =>
  points.map((p) => ({
    label:    dayLabel(p.bucketDate),
    paid:     p.metrics?.revenuePaid     ?? null,
    accrual:  p.metrics?.revenueAccrual  ?? null,
  }));

/* ── Tooltip ───────────────────────────────────────────────── */
const RevenueTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip-title">{label}</p>
      {payload.map((p) => (
        <div key={p.dataKey} className="chart-tooltip-row">
          <span
            className="chart-tooltip-dot"
            style={{ "--dot-color": p.stroke }}
          />
          <span>{p.name}</span>
          <span className="chart-tooltip-val">{fmtMXN(p.value)}</span>
        </div>
      ))}
    </div>
  );
};

/* ── Component ─────────────────────────────────────────────── */
function RevenueLineChart({ rangeDays = 30 }) {
  const uid = useId();
  const gPaid    = `${uid}-paid`;
  const gAccrual = `${uid}-accrual`;

  const { series, today, loading } = useFinancialSeries(rangeDays, true);

  const points = useMemo(() => {
    const all = [...(series ?? [])];
    if (today) all.push(today);
    return all.sort((a, b) => (a.bucketDate > b.bucketDate ? 1 : -1));
  }, [series, today]);

  const chartData = useMemo(() => transformRevenueData(points ?? []), [points]);

  if (loading && points.length === 0) {
    return <div className="chart-area"><div className="skeleton-block sk-chart" /></div>;
  }

  return (
    <div className="chart-area">
      <div className="chart-legend">
        <span className="chart-legend-item">
          <span className="chart-dot chart-dot-primary" /> Cobrado
        </span>
        <span className="chart-legend-item">
          <span className="chart-dot chart-dot-accent-line" /> Devengado
        </span>
      </div>
      <div className="chart-canvas-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={chartData}
            margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id={gPaid} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="var(--c-primary)" stopOpacity={0.15} />
                <stop offset="95%" stopColor="var(--c-primary)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id={gAccrual} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="var(--c-accent)" stopOpacity={0.12} />
                <stop offset="95%" stopColor="var(--c-accent)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="label"
              tick={{ fontSize: 9 }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={fmtMXN}
              width={72}
            />
            <Tooltip content={<RevenueTooltip />} />
            <Area
              dataKey="paid"
              name="Cobrado"
              stroke="var(--c-primary)"
              fill={`url(#${gPaid})`}
              strokeWidth={2}
              dot={{ r: 2, fill: "var(--c-primary)" }}
              activeDot={{ r: 4 }}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Area
              dataKey="accrual"
              name="Devengado"
              stroke="var(--c-accent)"
              fill={`url(#${gAccrual})`}
              strokeWidth={1.5}
              strokeDasharray="5 3"
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default memo(RevenueLineChart);
