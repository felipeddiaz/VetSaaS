import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { getDashboardStats } from "../api/dashboard";
import { formatDateTime } from "../utils/datetime";

const Dashboard = () => {
    const { user, token } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);

    const loadStats = async () => {
        if (!token) return;
        try {
            const data = await getDashboardStats();
            setStats(data);
        } catch (_) {
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        setLoading(true);
        loadStats();
    }, [token, location.key]);

    useEffect(() => {
        const refresh = () => loadStats();
        const onVisibility = () => {
            if (document.visibilityState === "visible") refresh();
        };

        window.addEventListener("focus", refresh);
        window.addEventListener("dashboard:refresh", refresh);
        document.addEventListener("visibilitychange", onVisibility);

        return () => {
            window.removeEventListener("focus", refresh);
            window.removeEventListener("dashboard:refresh", refresh);
            document.removeEventListener("visibilitychange", onVisibility);
        };
    }, [token]);

    const greeting = () => {
        const h = new Date().getHours();
        if (h < 12) return "Buenos días";
        if (h < 19) return "Buenas tardes";
        return "Buenas noches";
    };

    if (loading) {
        return (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
                <p style={{ color: "var(--c-text-3)", fontSize: "13px" }}>Cargando...</p>
            </div>
        );
    }

    return (
        <div>
            {/* Greeting */}
            <div style={{ marginBottom: "28px" }}>
                <h1 style={{ fontSize: "20px", fontWeight: "700", color: "var(--c-text)", marginBottom: "4px" }}>
                    {greeting()}, {user?.first_name || user?.username}
                </h1>
                <p style={{ fontSize: "13px", color: "var(--c-text-2)" }}>
                    {new Date().toLocaleDateString("es-ES", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
                </p>
            </div>

            {stats && (
                <>
                    {/* Stat Cards */}
                    <div style={{ display: "flex", gap: "16px", marginBottom: "28px", flexWrap: "wrap" }}>
                        <div className="stat-card">
                            <p className="stat-label">Citas hoy</p>
                            <p className="stat-value" style={{ color: stats.appointments_today > 0 ? "var(--c-primary-dark)" : "var(--c-text)" }}>
                                {stats.appointments_today}
                            </p>
                            <p className="stat-sub">programadas o completadas</p>
                        </div>
                        <div className="stat-card">
                            <p className="stat-label">Consultas recientes</p>
                            <p className="stat-value" style={{ color: "#059669" }}>
                                {stats.recent_records.length}
                            </p>
                            <p className="stat-sub">últimas registradas</p>
                        </div>
                        <div className="stat-card">
                            <p className="stat-label">Stock bajo</p>
                            <p className="stat-value" style={{ color: stats.low_stock_count > 0 ? "#dc2626" : "#059669" }}>
                                {stats.low_stock_count}
                            </p>
                            <p className="stat-sub">{stats.low_stock_count > 0 ? "productos requieren atención" : "todo en orden"}</p>
                        </div>
                    </div>

                    {/* Alertas stock bajo */}
                    {stats.low_stock_count > 0 && (
                        <div style={{ marginBottom: "28px" }}>
                            <div className="page-header" style={{ marginBottom: "12px" }}>
                                <h2 style={{ fontSize: "14px", fontWeight: "600" }}>Alertas de inventario</h2>
                                <button className="btn btn-ghost btn-sm" onClick={() => navigate("/inventory")}>
                                    Ver inventario →
                                </button>
                            </div>
                            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                                {stats.low_stock_products.map(p => (
                                    <div key={p.id} className="card" style={{ padding: "12px 16px", minWidth: "160px", borderColor: "var(--c-danger-border)", background: "var(--c-danger-bg)" }}>
                                        <p style={{ fontWeight: "600", fontSize: "13px", color: "var(--c-danger-text)", marginBottom: "3px" }}>{p.name}</p>
                                        <p style={{ fontSize: "12px", color: "#c2410c" }}>
                                            Stock: {p.stock} {p.unit} · Mín: {p.min_stock}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Consultas recientes */}
                    {stats.recent_records.length > 0 && (
                        <div>
                            <div className="page-header" style={{ marginBottom: "12px" }}>
                                <h2 style={{ fontSize: "14px", fontWeight: "600" }}>Consultas recientes</h2>
                                <button className="btn btn-ghost btn-sm" onClick={() => navigate("/medical-records")}>
                                    Ver historial →
                                </button>
                            </div>
                            <div className="table-wrap">
                                <table className="table">
                                    <thead>
                                        <tr>
                                            <th>Mascota</th>
                                            <th>Diagnóstico</th>
                                            <th>Veterinario</th>
                                            <th>Fecha</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {stats.recent_records.map(record => (
                                            <tr key={record.id}>
                                                <td style={{ fontWeight: "600" }}>{record.pet_name}</td>
                                                <td style={{ color: "var(--c-text-2)", maxWidth: "280px" }}>
                                                    {record.diagnosis.length > 70 ? record.diagnosis.slice(0, 70) + "…" : record.diagnosis}
                                                </td>
                                                <td style={{ color: "var(--c-text-2)" }}>
                                                    {record.veterinarian_name ? `Dr. ${record.veterinarian_name}` : "—"}
                                                </td>
                                                <td style={{ color: "var(--c-text-3)", whiteSpace: "nowrap" }}>
                                                    {formatDateTime(record.created_at, user?.organization_timezone || stats.effective_timezone || "UTC")}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {stats.appointments_today === 0 && stats.recent_records.length === 0 && stats.low_stock_count === 0 && (
                        <div className="empty-state">
                            <p className="empty-state-title">No hay actividad por mostrar hoy.</p>
                            <p className="empty-state-sub">Registra citas, consultas o productos para ver el resumen aquí.</p>
                        </div>
                    )}
                </>
            )}
        </div>
    );
};

export default Dashboard;
