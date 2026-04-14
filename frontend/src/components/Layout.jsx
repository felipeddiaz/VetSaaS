import { useAuth } from "../auth/authContext";
import { useNavigate, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";

const PAGE_TITLES = {
    "/":               "Dashboard",
    "/pets":           "Mascotas",
    "/appointments":   "Citas",
    "/medical-records":"Historial Clínico",
    "/inventory":      "Inventario",
    "/billing":        "Facturación",
    "/staff":          "Equipo",
    "/config":         "Configuración",
    "/prescriptions":  "Recetas",
};

const Layout = ({ children }) => {
    const { logout, user, initializing } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();

    if (initializing) {
        return (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", background: "var(--c-bg)" }}>
                <div style={{ textAlign: "center", color: "var(--c-text-3)" }}>
                    <div style={{ fontSize: "24px", marginBottom: "8px" }}>✦</div>
                    <p style={{ fontSize: "13px" }}>Cargando...</p>
                </div>
            </div>
        );
    }

    const handleLogout = () => { logout(); navigate("/login"); };

    // Get page title from exact match or prefix match
    const pageTitle = PAGE_TITLES[location.pathname] ||
        (location.pathname.startsWith("/pets/") ? "Ficha de Mascota" : "");

    return (
        <div style={{ minHeight: "100vh", backgroundColor: "var(--c-bg)" }}>
            <Sidebar onLogout={handleLogout} />

            <main style={{ marginLeft: "var(--sidebar-width)", minHeight: "100vh", display: "flex", flexDirection: "column" }}>
                {/* Top bar */}
                <header style={{
                    height: "52px",
                    backgroundColor: "var(--c-surface)",
                    borderBottom: "1px solid var(--c-border)",
                    display: "flex",
                    alignItems: "center",
                    padding: "0 28px",
                    gap: "8px",
                    position: "sticky", top: 0, zIndex: 50,
                    boxShadow: "var(--shadow-xs)",
                }}>
                    <span style={{ fontSize: "14px", fontWeight: "600", color: "var(--c-text)" }}>
                        {pageTitle}
                    </span>
                    <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "10px" }}>
                        <div style={{
                            width: "30px", height: "30px",
                            borderRadius: "50%",
                            background: "linear-gradient(135deg, var(--c-primary-light), #99f6e4)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: "12px", fontWeight: "700", color: "var(--c-primary-dark)",
                            border: "1.5px solid #99f6e4",
                        }}>
                            {(user?.first_name?.[0] || user?.username?.[0] || "U").toUpperCase()}
                        </div>
                    </div>
                </header>

                {/* Page content */}
                <div style={{ padding: "28px", flex: 1 }}>
                    {children}
                </div>
            </main>
        </div>
    );
};

export default Layout;
