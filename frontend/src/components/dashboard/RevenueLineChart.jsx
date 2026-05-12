import { useRef, useEffect, useMemo } from "react";
import { Chart, registerables } from "chart.js";
import { useFinancialSeries } from "../../hooks/useFinancialSeries";

Chart.register(...registerables);

const DAYS_SHORT = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

function dayLabel(dateStr) {
  const d = new Date(dateStr + "T12:00:00");
  return `${DAYS_SHORT[d.getDay()]} ${d.getDate()}`;
}

export default function RevenueLineChart({ rangeDays = 30 }) {
  const canvasRef = useRef(null);
  const chartRef  = useRef(null);
  const { series, today, loading } = useFinancialSeries(rangeDays, true);

  const points = useMemo(() => {
    const all = [...series];
    if (today) all.push(today);
    return all.sort((a, b) => (a.bucketDate > b.bucketDate ? 1 : -1));
  }, [series, today]);

  useEffect(() => {
    if (!canvasRef.current || points.length === 0) return;
    if (chartRef.current) chartRef.current.destroy();

    const style   = getComputedStyle(document.documentElement);
    const primary = style.getPropertyValue("--c-primary").trim() || "#1a4434";
    const accent  = style.getPropertyValue("--c-accent").trim()  || "#d67b5c";
    const grid    = "rgba(15, 42, 31, 0.06)";

    chartRef.current = new Chart(canvasRef.current, {
      type: "line",
      data: {
        labels: points.map((p) => dayLabel(p.bucketDate)),
        datasets: [
          {
            label: "Cobrado",
            data: points.map((p) => p.metrics?.revenuePaid ?? null),
            borderColor: primary,
            backgroundColor: primary + "20",
            fill: true,
            borderWidth: 2,
            pointRadius: 2,
            tension: 0.3,
            spanGaps: false,
          },
          {
            label: "Devengado",
            data: points.map((p) => p.metrics?.revenueAccrual ?? null),
            borderColor: accent,
            backgroundColor: accent + "20",
            fill: true,
            borderWidth: 1.5,
            borderDash: [5, 3],
            pointRadius: 0,
            tension: 0.3,
            spanGaps: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 9 }, maxTicksLimit: 12 } },
          y: {
            beginAtZero: true,
            grid: { color: grid },
            ticks: { font: { size: 10 }, callback: (v) => `$${v.toLocaleString("es-MX")}` },
          },
        },
      },
    });

    return () => { if (chartRef.current) chartRef.current.destroy(); };
  }, [points]);

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
          <span className="chart-dot chart-dot-dash chart-dot-accent" /> Devengado
        </span>
      </div>
      <div className="chart-canvas-wrap">
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}
