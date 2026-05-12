import { useAuth } from "../../auth/authContext";
import { useDashboardSummary } from "../../hooks/useDashboardSummary";
import DashboardTopBar from "../../components/dashboard/DashboardTopBar";
import KpiStrip from "../../components/dashboard/KpiStrip";
import OperationalTimeline from "../../components/dashboard/OperationalTimeline";
import WaitingRoom from "../../components/dashboard/WaitingRoom";
import ClinicalBacklog from "../../components/dashboard/ClinicalBacklog";
import StockAlerts from "../../components/dashboard/StockAlerts";
import DashboardAnalytics from "../../components/dashboard/DashboardAnalytics";
import "./dashboard.css";

const Dashboard = () => {
  const { user } = useAuth();
  const { data, loading, error, refetch } = useDashboardSummary();

  const renderSkeleton = () => (
    <>
      {/* skeleton hero */}
      <div className="skeleton-block sk-hero" />
      <div className="dash-grid">
        <div className="dash-main">
          <div className="kpiStrip-v2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="skeleton-block sk-kpi" />
            ))}
          </div>
          <div className="dashboard-card">
            <div className="skeleton-block sk-timeline" />
          </div>
          <div className="dashboard-card">
            <div className="skeleton-block sk-chart" />
          </div>
        </div>
        <div className="dash-side">
          <div className="dashboard-card"><div className="skeleton-block sk-side" /></div>
          <div className="dashboard-card"><div className="skeleton-block sk-side" /></div>
          <div className="dashboard-card"><div className="skeleton-block sk-side" /></div>
        </div>
      </div>
    </>
  );

  if (loading && !data) return renderSkeleton();

  return (
    <>
      {/* TopBar slim + Hero greeting */}
      <DashboardTopBar summary={data} />

      {error && (
        <div className="dash-error-banner">
          <span>No se pudieron cargar los datos del dashboard.</span>
          <button className="btn btn-ghost btn-xs" onClick={refetch}>Reintentar</button>
        </div>
      )}

      <div className="dash-grid">
        <div className="dash-main">
          <KpiStrip kpis={data?.kpis} user={user} />
          <div className="dashboard-card">
            <div className="card-title-v2">Agenda de hoy</div>
            <OperationalTimeline slots={data?.timeline} />
          </div>
          <DashboardAnalytics />
        </div>
        <div className="dash-side">
          <div className="dashboard-card">
            <WaitingRoom items={data?.waiting_room} />
          </div>
          <div className="dashboard-card">
            <ClinicalBacklog backlog={data?.backlog} />
          </div>
          <div className="dashboard-card">
            <StockAlerts alerts={data?.stock_alerts} />
          </div>
        </div>
      </div>
    </>
  );
};

export default Dashboard;
