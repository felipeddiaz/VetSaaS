import { useAuth } from "../../auth/authContext";
import { Icon } from "../icons";

function KpiCard({ color, icon, label, value, live, onClick }) {
  return (
    <div
      className={`kpi-card-v2 kpi-${color}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className={`kpi-icon-v2 kpi-icon-${color}`}>
        {icon}
      </div>
      <div className="kpi-val-v2">{value ?? "—"}</div>
      <div className="kpi-lbl-v2">{label}</div>
      {live && <div className="kpi-live-dot" />}
    </div>
  );
}

export default function KpiStrip({ kpis, user }) {
  const role = user?.role;
  const isAdmin = role === "ADMIN" || role === "ADMIN_SAAS";

  return (
    <div className="kpiStrip-v2">
      <KpiCard
        color="primary"
        icon={<Icon.Activity s={16} />}
        label="En consulta"
        value={kpis?.in_progress_now}
        live
      />
      <KpiCard
        color="info"
        icon={<Icon.CalendarClock s={16} />}
        label="Pendientes"
        value={kpis?.pending_today}
        live
      />
      {(isAdmin || role === "VET") && (
        <KpiCard
          color="danger"
          icon={<Icon.Package s={16} />}
          label="Stock bajo"
          value={kpis?.low_stock_count}
        />
      )}
      {isAdmin && (
        <KpiCard
          color="warning"
          icon={<Icon.Receipt s={16} />}
          label="Cobros pend."
          value={kpis?.ar_outstanding ? `$${Number(kpis.ar_outstanding).toLocaleString("es-MX")}` : "$0"}
        />
      )}
      <KpiCard
        color="purple"
        icon={<Icon.PawPrint s={16} />}
        label="Pacientes hoy"
        value={kpis?.patients_today}
        live
      />
    </div>
  );
}
