import { memo, useMemo, useLayoutEffect, useState } from "react";
import { FunnelChart, Funnel, LabelList, Tooltip, ResponsiveContainer } from "recharts";
import { useDashboardSeries } from "../../hooks/useDashboardSeries";
import { useFinancialSeries } from "../../hooks/useFinancialSeries";

/* ── CSS var resolver ─────────────────────────────────────── */
const readCssVar = (name, fallback) => {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
};

function sumOps(points, key) {
  return (points || []).reduce((acc, p) => acc + (p?.metrics?.[key] ?? 0), 0);
}

function sumFin(series, today, key) {
  const arr = [...(series || []), ...(today ? [today] : [])];
  return arr.reduce((acc, p) => acc + Number(p?.metrics?.[key] ?? 0), 0);
}

const FunnelTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const { name, value, conv } = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip-title">{name}</p>
      <div className="chart-tooltip-row">
        <span>Volumen</span>
        <span className="chart-tooltip-val">{value}</span>
      </div>
      {conv != null && (
        <div className="chart-tooltip-row">
          <span>vs paso previo</span>
          <span className="chart-tooltip-val">{conv}%</span>
        </div>
      )}
    </div>
  );
};

function ConversionFunnel({ rangeDays = 30 }) {
  const { allPoints, loading: opsLoading } = useDashboardSeries(rangeDays, true);
  const { series: fin, today: finToday, loading: finLoading } = useFinancialSeries(rangeDays, true);

  const [colors, setColors] = useState({
    primary: "#1a4434",
    sage:    "#7faa78",
    accent:  "#d67b5c",
    amber:   "#e8b87a",
  });
  useLayoutEffect(() => {
    setColors({
      primary: readCssVar("--c-primary", "#1a4434"),
      sage:    readCssVar("--sage-500", "#7faa78"),
      accent:  readCssVar("--c-accent",  "#d67b5c"),
      amber:   readCssVar("--amber",     "#e8b87a"),
    });
  }, []);

  const usable = useMemo(
    () => (allPoints || []).filter((p) => p && !p.isMissing && p.metrics),
    [allPoints]
  );

  const totals = useMemo(() => {
    const citas    = sumOps(usable, "appointmentsTotal");
    const done     = sumOps(usable, "appointmentsDone");
    const closed   = sumOps(usable, "medicalRecordsClosed");
    const paid     = sumFin(fin, finToday, "invoicesPaidCount");
    return { citas, done, closed, paid };
  }, [usable, fin, finToday]);

  const data = useMemo(() => {
    const steps = [
      { name: "Citas",         value: totals.citas,  fill: colors.primary },
      { name: "Atendidas",     value: totals.done,   fill: colors.sage    },
      { name: "Consultas cerradas", value: totals.closed, fill: colors.amber },
      { name: "Facturas pagadas",   value: totals.paid,   fill: colors.accent },
    ];
    return steps.map((s, i) => {
      const prev = i > 0 ? steps[i - 1].value : null;
      const conv = prev && prev > 0 ? Math.round((s.value / prev) * 100) : null;
      return { ...s, conv };
    });
  }, [totals, colors]);

  const overallConv = totals.citas > 0
    ? Math.round((totals.paid / totals.citas) * 100)
    : 0;

  const loading = opsLoading || finLoading;

  if (loading && totals.citas === 0 && totals.paid === 0) {
    return <div className="chart-area"><div className="skeleton-block sk-chart" /></div>;
  }

  if (totals.citas === 0) {
    return (
      <div className="chart-area">
        <div className="chart-state-wrap">
          <p className="chart-state-msg">
            Sin actividad suficiente en los últimos {rangeDays} días.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="chart-area">
      <div className="funnel-header">
        <div className="funnel-headline">
          <span className="funnel-headline-val">{overallConv}%</span>
          <span className="funnel-headline-lbl">conversión global</span>
        </div>
        <div className="funnel-sub">
          {totals.citas} citas → {totals.paid} cobradas · últimos {rangeDays}d
        </div>
      </div>

      <div className="funnel-wrap">
        <div className="funnel-chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <FunnelChart>
              <Tooltip content={<FunnelTooltip />} />
              <Funnel
                dataKey="value"
                data={data}
                isAnimationActive={false}
                stroke="var(--c-surface)"
                strokeWidth={2}
              >
                <LabelList
                  position="right"
                  fill="var(--c-text-2)"
                  stroke="none"
                  dataKey="name"
                  fontSize={11}
                  fontFamily="var(--font-display)"
                  fontWeight={600}
                />
              </Funnel>
            </FunnelChart>
          </ResponsiveContainer>
        </div>

        <ol className="funnel-steps">
          {data.map((step, i) => (
            <li key={step.name} className="funnel-step">
              <span
                className="funnel-step-bar"
                style={{
                  "--bar-w": `${data[0].value > 0 ? (step.value / data[0].value) * 100 : 0}%`,
                  "--bar-c": step.fill,
                }}
              />
              <div className="funnel-step-body">
                <div className="funnel-step-name">
                  <span className="funnel-step-idx">{i + 1}</span>
                  {step.name}
                </div>
                <div className="funnel-step-meta">
                  {step.value.toLocaleString("es-MX")}
                  {step.conv != null && (
                    <span className="funnel-step-conv">{step.conv}%</span>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

export default memo(ConversionFunnel);
