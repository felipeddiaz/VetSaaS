import { useMemo } from "react";
import { useAuth } from "../../auth/authContext";
import { useDashboardSummary } from "../../hooks/useDashboardSummary";
import { useFinancialSeries } from "../../hooks/useFinancialSeries";
import DashboardTopBar from "../../components/dashboard/DashboardTopBar";
import KpiStrip from "../../components/dashboard/KpiStrip";
import OperationalTimeline from "../../components/dashboard/OperationalTimeline";
import NowPanel from "../../components/dashboard/NowPanel";
import ClinicalBacklog from "../../components/dashboard/ClinicalBacklog";
import StockAlerts from "../../components/dashboard/StockAlerts";
import DashboardAnalytics from "../../components/dashboard/DashboardAnalytics";
import "./dashboard.css";

function revenueDeltaVsYesterday(finSeries, finToday) {
  if (!finToday?.metrics) return null;
  const today = Number(finToday.metrics.revenuePaid ?? 0);
  const sorted = [...(finSeries || [])]
    .filter((p) => p?.metrics)
    .sort((a, b) => (a.bucketDate > b.bucketDate ? 1 : -1));
  const yesterday = sorted[sorted.length - 1];
  if (!yesterday) return null;
  const prev = Number(yesterday.metrics.revenuePaid ?? 0);
  if (prev === 0) return today > 0 ? 100 : null;
  return ((today - prev) / prev) * 100;
}

function buildRevenueSpark(finSeries, finToday) {
  const fin = [...(finSeries || []), ...(finToday ? [finToday] : [])]
    .filter((p) => p && p.metrics)
    .sort((a, b) => (a.bucketDate > b.bucketDate ? 1 : -1))
    .slice(-7);
  return fin.map((p) => ({ v: Number(p.metrics.revenuePaid ?? 0) }));
}

function buildKpiItems(kpis, role) {
  const isAdmin   = role === "ADMIN" || role === "ADMIN_SAAS";
  const showStock = isAdmin || role === "VET";

  const arValue = isAdmin && kpis?.ar_outstanding != null
    ? Number(kpis.ar_outstanding)
    : 0;

  const stockCount = kpis?.low_stock_count ?? 0;

  const items = [
    {
      label: "En consulta",
      value: kpis?.in_progress_now ?? 0,
      tone: "default",
      live: true,
    },
    {
      label: "Citas hoy",
      value: kpis?.pending_today ?? 0,
      tone: "default",
    },
    ...(isAdmin
      ? [
          {
            label: "Pendiente cobro",
            value: arValue,
            tone: arValue > 0 ? "warning" : "default",
            format: "currency",
          },
        ]
      : []),
    ...(showStock
      ? [
          {
            label: "Stock bajo",
            value: stockCount,
            tone: stockCount > 0 ? "danger" : "default",
          },
        ]
      : []),
    {
      label: "Pacientes hoy",
      value: kpis?.patients_today ?? 0,
      tone: "default",
    },
  ];

  return items;
}

const Dashboard = () => {
  const { user } = useAuth();
  const { data, loading, error, refetch } = useDashboardSummary();
  const { series: finSeries, today: finToday } = useFinancialSeries(7, true);

  const revenueToday = finToday?.metrics?.revenuePaid ?? null;
  const revenueDelta = useMemo(
    () => revenueDeltaVsYesterday(finSeries, finToday),
    [finSeries, finToday]
  );
  const revenueSpark = useMemo(
    () => buildRevenueSpark(finSeries, finToday),
    [finSeries, finToday]
  );

  const kpiItems = useMemo(
    () => buildKpiItems(data?.kpis, user?.role),
    [data?.kpis, user?.role]
  );

  const renderSkeleton = () => (
    <div className="dash-page">
      <div className="dtop-wrap">
        <div className="skeleton-block sk-hero" />
      </div>
      <div className="dash-grid">
        <div className="dash-main">
          <div style={{
            display: "flex", flexWrap: "wrap",
            padding: "28px 0", gap: "8px",
          }}>
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="skeleton-block"
                style={{
                  flex: "1 1 140px", minHeight: 72,
                  borderRadius: "var(--r-md)",
                }}
              />
            ))}
          </div>
          <div className="skeleton-block sk-timeline" />
          <div className="skeleton-block sk-chart" />
        </div>
        <div className="dash-side">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton-block sk-side" />
          ))}
        </div>
      </div>
    </div>
  );

  if (loading && !data) return renderSkeleton();

  return (
    <div className="dash-page">
      <DashboardTopBar
        summary={data}
        revenueToday={revenueToday}
        revenueSpark={revenueSpark}
        revenueDelta={revenueDelta}
      />

      {error && (
        <div className="dash-error-banner">
          <span>No se pudieron cargar los datos del dashboard.</span>
          <button className="btn btn-ghost btn-xs" onClick={refetch}>Reintentar</button>
        </div>
      )}

      <div className="dash-grid">
        <main className="dash-main">
          <KpiStrip items={kpiItems} />

          <section className="card dash-timeline-card">
            <div className="dash-section-head">
              <h3 className="dash-section-title">Agenda de hoy</h3>
              <span className="dash-section-meta">8:00 – 20:00</span>
            </div>
            <OperationalTimeline slots={data?.timeline} />
          </section>

          <DashboardAnalytics />
        </main>

        <aside className="dash-side">
          <div className="card"><NowPanel summary={data} /></div>
          <div className="card"><ClinicalBacklog backlog={data?.backlog} /></div>
          <div className="card"><StockAlerts alerts={data?.stock_alerts} /></div>
        </aside>
      </div>
    </div>
  );
};

export default Dashboard;
