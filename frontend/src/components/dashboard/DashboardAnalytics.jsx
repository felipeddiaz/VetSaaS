import { useAuth } from "../../auth/authContext";
import ActivityAreaChart from "./ActivityAreaChart";
import RevenueLineChart from "./RevenueLineChart";
import { useState } from "react";

const TABS = [
  { key: "weekly", label: "Semanal" },
  { key: "monthly", label: "Mensual" },
  { key: "financial", label: "Financiero", admin: true },
];

export default function DashboardAnalytics() {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN" || user?.role === "ADMIN_SAAS";
  const [tab, setTab] = useState("weekly");

  const visibleTabs = TABS.filter((t) => !t.admin || isAdmin);

  return (
    <div className="dashboard-card">
      <div className="analytics-tabs">
        <div className="card-title-v2" style={{ marginBottom: 0 }}>Analytics</div>
        <div className="analytics-tab-row">
          {visibleTabs.map((t) => (
            <button
              key={t.key}
              className={`analytics-tab-btn ${tab === t.key ? "analytics-tab-active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "weekly" && (
        <div className="chart-section">
          <ActivityAreaChart rangeDays={7} />
        </div>
      )}
      {tab === "monthly" && (
        <div className="chart-section">
          <ActivityAreaChart rangeDays={30} />
        </div>
      )}
      {tab === "financial" && isAdmin && (
        <div className="chart-section">
          <RevenueLineChart rangeDays={30} />
        </div>
      )}
    </div>
  );
}
