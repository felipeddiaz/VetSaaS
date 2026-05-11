import { useRef, useEffect, useMemo } from "react";
import { Chart, registerables } from "chart.js";
import { useDashboardSeries } from "../../hooks/useDashboardSeries";

Chart.register(...registerables);

const DAYS_SHORT = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

function dayLabel(dateStr) {
  const d = new Date(dateStr + "T12:00:00");
  return DAYS_SHORT[d.getDay()];
}

function isCorrupt(dp) {
  return dp?.lifecycleState === "corrupt";
}

export default function ActivityAreaChart({ rangeDays = 7 }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);
  const { allPoints, loading } = useDashboardSeries(rangeDays, true);

  const points = useMemo(() => {
    if (!allPoints || allPoints.length === 0) return [];
    return allPoints
      .filter((p) => p && !p.isMissing)
      .sort((a, b) => (a.bucketDate > b.bucketDate ? 1 : -1));
  }, [allPoints]);

  const hasCorrupt = useMemo(() => points.some(isCorrupt), [points]);

  useEffect(() => {
    if (!canvasRef.current || points.length === 0) return;
    if (chartRef.current) chartRef.current.destroy();

    const labels = points.map((p) => dayLabel(p.bucketDate));
    const doneData = points.map((p) =>
      isCorrupt(p) ? null : (p.metrics?.appointmentsDone ?? 0)
    );
    const noShowData = points.map((p) =>
      isCorrupt(p) ? null : (p.metrics?.appointmentsNoShow ?? 0)
    );
    const totalData = points.map((p) =>
      isCorrupt(p) ? null : (p.metrics?.appointmentsTotal ?? 0)
    );

    const style = getComputedStyle(document.documentElement);
    const primary = style.getPropertyValue("--c-primary").trim() || "#1a4434";
    const accent = style.getPropertyValue("--c-accent").trim() || "#d67b5c";
    const muted = style.getPropertyValue("--c-text-3").trim() || "#8a8a7f";
    const grid = "rgba(15, 42, 31, 0.06)";

    chartRef.current = new Chart(canvasRef.current, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Completadas",
            data: doneData,
            backgroundColor: primary,
            borderRadius: 4,
            barPercentage: 0.6,
          },
          {
            label: "No-show",
            data: noShowData,
            backgroundColor: muted,
            borderRadius: 4,
            barPercentage: 0.6,
          },
          {
            label: "Total",
            data: totalData,
            type: "line",
            borderColor: accent,
            backgroundColor: "transparent",
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: accent,
            tension: 0.3,
            spanGaps: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(ctx) {
                if (ctx.raw === null) return "Datos no disponibles";
                return `${ctx.dataset.label}: ${ctx.raw}`;
              },
            },
          },
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { font: { size: 10 } } },
          y: { stacked: true, beginAtZero: true, grid: { color: grid }, ticks: { font: { size: 10 } } },
        },
      },
    });

    return () => {
      if (chartRef.current) chartRef.current.destroy();
    };
  }, [points]);

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
        <span className="chart-legend-item"><span className="chart-dot" style={{ background: "var(--c-primary)" }} /> Completadas</span>
        <span className="chart-legend-item"><span className="chart-dot" style={{ background: "var(--c-text-3)" }} /> No-show</span>
        <span className="chart-legend-item"><span className="chart-dot chart-dot-line" style={{ borderColor: "var(--c-accent)" }} /> Total</span>
      </div>
      <div style={{ height: 220 }}>
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}
