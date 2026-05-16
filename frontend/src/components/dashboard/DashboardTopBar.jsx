import { memo, useLayoutEffect, useMemo, useState } from "react";
import { AreaChart, Area, ResponsiveContainer } from "recharts";
import { useAuth } from "../../auth/authContext";
import { useNavigate } from "react-router-dom";
import { Icon } from "../icons";
import "./DashboardTopBar.css";

const readCssVar = (name, fallback) => {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
};

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Buenos días";
  if (h < 19) return "Buenas tardes";
  return "Buenas noches";
}

function fmtMXN(v) {
  if (v == null) return "—";
  const n = Number(v);
  return `$${Math.round(n).toLocaleString("es-MX")}`;
}

const MastSpark = memo(function MastSpark({ data, color }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="dtop-spark">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 1, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="dtop-spark-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"  stopColor={color} stopOpacity={0.30} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.4}
            fill="url(#dtop-spark-grad)"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
});

export default function DashboardTopBar({ summary, revenueToday, revenueSpark, revenueDelta }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin  = user?.role === "ADMIN" || user?.role === "ADMIN_SAAS";

  const [color, setColor] = useState("#1a4434");
  useLayoutEffect(() => { setColor(readCssVar("--c-primary", "#1a4434")); }, []);

  const dateLabel = useMemo(
    () => new Date().toLocaleDateString("es-ES", {
      weekday: "long", day: "numeric", month: "long", year: "numeric",
    }),
    []
  );

  const firstName  = user?.first_name || user?.username || "Equipo";
  const enCurso    = summary?.kpis?.in_progress_now ?? 0;
  const stockCrit  = (summary?.stock_alerts || []).filter(a => a.severity === "critical").length;
  const needsAttention = summary?.backlog?.needs_attention_count ?? 0;
  const totalAlert     = stockCrit + needsAttention;

  const deltaLabel = revenueDelta != null
    ? `${revenueDelta >= 0 ? "▲" : "▼"} ${Math.abs(Math.round(revenueDelta))}% vs ayer`
    : null;

  return (
    <div className="dtop-wrap">
      <div className="phead dtop-phead">
        <div>
          <span className="ptag">
            <span /> Operación · En vivo
          </span>
          <h1 className="ptitle">{getGreeting()}, {firstName}</h1>
          <p className="psub">{dateLabel} · {user?.organization_name || "Sistema"}</p>
        </div>

        <div className="pacts dtop-pacts">
          {totalAlert > 0 && (
            <span className="badge badge-warning dtop-alert-badge">
              <Icon.AlertCircle s={12} /> {totalAlert} alerta{totalAlert > 1 ? "s" : ""}
            </span>
          )}
          <button className="btn btn-primary btn-md" onClick={() => navigate("/appointments")}>
            <Icon.Plus s={14} /> Nueva cita
          </button>
        </div>
      </div>

      {isAdmin && (
        <div className="card dtop-revenue-card">
          <div className="dtop-revenue-head">
            <span className="dtop-revenue-lbl">Ingresos del día</span>
            {deltaLabel && (
              <span className={`badge ${revenueDelta >= 0 ? "badge-success" : "badge-danger"}`}>
                {deltaLabel}
              </span>
            )}
          </div>
          <div className="dtop-revenue-body">
            <div className="dtop-revenue-val">{fmtMXN(revenueToday)}</div>
            <div className="dtop-revenue-meta">
              <span><strong>{enCurso}</strong> en curso</span>
            </div>
          </div>
          <MastSpark data={revenueSpark} color={color} />
        </div>
      )}
    </div>
  );
}
