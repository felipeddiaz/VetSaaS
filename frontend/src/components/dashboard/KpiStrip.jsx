import { useEffect, useState } from "react";
import { useAuth } from "../../auth/authContext";
import { Icon } from "../icons";

/* ── Animated counter ──────────────────────────────────────── */
function useCounter(target, duration = 800) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    const n = Number(target);
    if (isNaN(n) || typeof target === "string") {
      setValue(target);
      return;
    }
    if (n === 0) { setValue(0); return; }
    let start = null;
    const step = (ts) => {
      if (!start) start = ts;
      const progress = Math.min((ts - start) / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(ease * n));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target, duration]);
  return value;
}

/* ── KPI Card ──────────────────────────────────────────────── */
function KpiCard({ color, icon, label, value, live, onClick, prefix = "", suffix = "" }) {
  const animated = useCounter(value);
  const display = value == null
    ? "—"
    : typeof value === "string"
      ? value
      : `${prefix}${animated}${suffix}`;

  return (
    <div
      className={`kpi-card-v2 kpi-${color}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === "Enter" && onClick() : undefined}
    >
      <div className={`kpi-icon-v2 kpi-icon-${color}`}>
        {icon}
      </div>
      <div className="kpi-val-v2">{display}</div>
      <div className="kpi-lbl-v2">{label}</div>
      {live && <div className="kpi-live-dot" />}
    </div>
  );
}

/* ── KPI Strip ─────────────────────────────────────────────── */
export default function KpiStrip({ kpis, user }) {
  const role    = user?.role;
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
        label="Pendientes hoy"
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
          value={
            kpis?.ar_outstanding != null
              ? `$${Number(kpis.ar_outstanding).toLocaleString("es-MX")}`
              : "$0"
          }
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
