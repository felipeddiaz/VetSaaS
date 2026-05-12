import { Icon } from "../icons";
import MissingState from "./MissingState";

const fmtInt = (v) => Number(v ?? 0).toLocaleString("es-MX");

const CARD_CONFIG = {
  primary: { className: "kpi-primary", iconBg: "kpi-icon-primary", icon: Icon.CalendarClock, iconColor: "var(--c-primary-dark)" },
  accent:  { className: "kpi-accent",  iconBg: "kpi-icon-accent",  icon: Icon.CheckCircle,   iconColor: "var(--c-accent-hover)" },
  danger:  { className: "kpi-danger",  iconBg: "kpi-icon-danger",  icon: Icon.AlertTriangle, iconColor: "#ef4444" },
  purple:  { className: "kpi-purple",  iconBg: "kpi-icon-purple",  icon: Icon.FileHeart,     iconColor: "#7c3aed" },
};

const OPERATIONAL_KEYS = new Set(["appointmentsTotal", "appointmentsDone", "appointmentsNoShow"]);

const MetricCard = ({ label, point, metricKey, color = "primary" }) => {
  const cfg          = CARD_CONFIG[color] || CARD_CONFIG.primary;
  const Comp         = cfg.icon;
  const isOperational = OPERATIONAL_KEYS.has(metricKey);

  if (!point) {
    return (
      <div className={`kpi-card ${cfg.className}`}>
        <span className="kpi-empty">—</span>
      </div>
    );
  }

  const isMissing = point.isMissing;
  const isLive    = point.isLive;
  const showLive  = isLive && !isMissing && isOperational;
  const rawValue  = isMissing ? null : (point.metrics?.[metricKey] ?? null);

  return (
    <div className={`kpi-card ${cfg.className}`}>
      <div className={`kpi-icon ${cfg.iconBg}`}>
        <Comp s={13} c={cfg.iconColor} />
      </div>
      <div className={`kpi-val${isMissing ? " kpi-val-missing" : ""}`}>
        {isMissing ? <MissingState /> : rawValue == null ? "—" : fmtInt(rawValue)}
      </div>
      <div className="kpi-lbl">{label}</div>
      {showLive && (
        <div className="kpi-live">
          <span className="kpi-live-dot" />
          EN VIVO
        </div>
      )}
    </div>
  );
};

export default MetricCard;
