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
  const cfg = CARD_CONFIG[color] || CARD_CONFIG.primary;
  const Comp = cfg.icon;
  const isOperational = OPERATIONAL_KEYS.has(metricKey);

  if (!point) {
    return (
      <div className={`kpi-card ${cfg.className}`}>
        <span style={{ color: "var(--c-text-4)", fontSize: "12px" }}>—</span>
      </div>
    );
  }

  const isMissing = point.isMissing;
  const isLive = point.isLive;
  const showLive = isLive && !isMissing && isOperational;
  const rawValue = isMissing ? null : (point.metrics?.[metricKey] ?? null);

  return (
    <div className={`kpi-card ${cfg.className}`}>
      <div className={`kpi-icon ${cfg.iconBg}`}>
        <Comp s={13} c={cfg.iconColor} />
      </div>
      <div className="kpi-val" style={{ color: isMissing ? "var(--c-text-4)" : undefined }}>
        {isMissing ? <MissingState /> : rawValue == null ? "—" : fmtInt(rawValue)}
      </div>
      <div className="kpi-lbl">{label}</div>
      {showLive && (
        <div className="kpi-live">
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--c-success-text)", display: "inline-block", flexShrink: 0 }} />
          EN VIVO
        </div>
      )}
    </div>
  );
};

export default MetricCard;
