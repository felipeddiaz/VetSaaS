import { useAuth } from "../../auth/authContext";
import ActivityAreaChart from "./ActivityAreaChart";
import RevenueLineChart from "./RevenueLineChart";
import ConversionFunnel from "./ConversionFunnel";
import { useState } from "react";

const TABS = [
  { key: "weekly",    label: "Semanal" },
  { key: "monthly",   label: "Mensual" },
  { key: "financial", label: "Financiero", admin: true },
  { key: "funnel",    label: "Embudo",     admin: true },
];

export default function DashboardAnalytics() {
  const { user }  = useAuth();
  const isAdmin   = user?.role === "ADMIN" || user?.role === "ADMIN_SAAS";
  const [tab, setTab] = useState("weekly");

  const visibleTabs = TABS.filter((t) => !t.admin || isAdmin);

  return (
    <div className="card dash-analytics-card">
      <div className="dash-analytics-head">
        <h3 className="dash-analytics-title">Analítica</h3>
        <div className="tabs dash-analytics-tabs">
          {visibleTabs.map((t) => (
            <button
              key={t.key}
              className={`tab-btn${tab === t.key ? " active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "weekly"    && <div className="dash-chart-section"><ActivityAreaChart rangeDays={7}  /></div>}
      {tab === "monthly"   && <div className="dash-chart-section"><ActivityAreaChart rangeDays={30} /></div>}
      {tab === "financial" && isAdmin && <div className="dash-chart-section"><RevenueLineChart rangeDays={30} /></div>}
      {tab === "funnel"    && isAdmin && <div className="dash-chart-section"><ConversionFunnel rangeDays={30} /></div>}
    </div>
  );
}
