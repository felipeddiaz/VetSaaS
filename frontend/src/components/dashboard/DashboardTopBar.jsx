import { useAuth } from "../../auth/authContext";
import { useNavigate } from "react-router-dom";
import { Icon } from "../icons";
import "./DashboardTopBar.css";

const DAYS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const MONTHS = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

function formatToday() {
  const d = new Date();
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

function tzShort(tz) {
  if (!tz) return "";
  const parts = tz.split("/");
  const city = parts[parts.length - 1];
  return city.replace(/_/g, " ");
}

export default function DashboardTopBar({ summary }) {
  const { user } = useAuth();
  const navigate = useNavigate();

  const alerts = [];
  if ((summary?.backlog?.stale_24h ?? 0) > 0) {
    alerts.push(`${summary.backlog.stale_24h} consultas abiertas >24h`);
  }
  if ((summary?.stock_alerts ?? []).some((a) => a.severity === "critical")) {
    const critical = summary.stock_alerts.filter((a) => a.severity === "critical").length;
    alerts.push(`${critical} productos agotados`);
  }

  return (
    <header className="dtop">
      <div className="dtop-left">
        <button className="dtop-qa" onClick={() => navigate("/appointments")} title="Nueva cita">
          <Icon.Plus s={15} />
        </button>
        <button className="dtop-qa" onClick={() => navigate("/appointments")} title="Walk-in">
          <Icon.CalendarClock s={15} />
        </button>
      </div>

      <div className="dtop-center">
        <span className="dtop-date">{formatToday()}</span>
      </div>

      <div className="dtop-right">
        {alerts.length > 0 && (
          <span className="dtop-alerts">
            <Icon.AlertCircle s={14} c="var(--c-warning-text)" />
            <span>{alerts[0]}</span>
            {alerts.length > 1 && <span className="dtop-alerts-more">+{alerts.length - 1}</span>}
          </span>
        )}
        <span className="dtop-tz">{tzShort(summary?.effective_timezone)}</span>
        <div className="dtop-avatar">
          {(user?.first_name?.[0] || user?.username?.[0] || "U").toUpperCase()}
        </div>
      </div>
    </header>
  );
}
