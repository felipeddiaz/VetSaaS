import { useAuth } from "../../auth/authContext";
import { useNavigate } from "react-router-dom";
import { Icon } from "../icons";
import "./DashboardTopBar.css";

const DAYS   = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const MONTHS = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];

function formatToday() {
  const d = new Date();
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

function tzShort(tz) {
  if (!tz) return "";
  const parts = tz.split("/");
  return parts[parts.length - 1].replace(/_/g, " ");
}

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Buenos días";
  if (h < 19) return "Buenas tardes";
  return "Buenas noches";
}

export default function DashboardTopBar({ summary }) {
  const { user } = useAuth();
  const navigate  = useNavigate();

  const alerts = [];
  if ((summary?.backlog?.stale_24h ?? 0) > 0)
    alerts.push(`${summary.backlog.stale_24h} consultas abiertas >24h`);
  if ((summary?.stock_alerts ?? []).some(a => a.severity === "critical")) {
    const n = summary.stock_alerts.filter(a => a.severity === "critical").length;
    alerts.push(`${n} producto${n > 1 ? "s" : ""} agotado${n > 1 ? "s" : ""}`);
  }

  const firstName = user?.first_name || user?.username || "";

  return (
    <>
      {/* ── Slim action bar ── */}
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
              <Icon.AlertCircle s={13} c="var(--c-warning-text)" />
              <span>{alerts[0]}</span>
              {alerts.length > 1 && (
                <span className="dtop-alerts-more">+{alerts.length - 1}</span>
              )}
            </span>
          )}
          {summary?.effective_timezone && (
            <span className="dtop-tz">{tzShort(summary.effective_timezone)}</span>
          )}
          <div className="dtop-avatar">
            {(firstName[0] || "U").toUpperCase()}
          </div>
        </div>
      </header>

      {/* ── Hero greeting ── */}
      <div className="dash-hero">
        <div className="dash-hero-left">
          <p className="dash-hero-eyebrow">{getGreeting()}</p>
          <h1 className="dash-hero-name">{firstName}</h1>
          <p className="dash-hero-date">
            {new Date().toLocaleDateString("es-ES", {
              weekday: "long", year: "numeric", month: "long", day: "numeric",
            })}
          </p>
        </div>
        <div className="dash-hero-right">
          <span className="dash-hero-org">
            {user?.organization_name || "Sistema"}
          </span>
        </div>
      </div>
    </>
  );
}
