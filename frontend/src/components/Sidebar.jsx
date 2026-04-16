import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { Icon } from "./icons";

const NAV_ITEMS = [
    { path: "/",               label: "Dashboard",         icon: Icon.LayoutDashboard },
    { path: "/pets",           label: "Mascotas",          icon: Icon.PawPrint },
    { path: "/appointments",   label: "Citas",             icon: Icon.CalendarClock },
    { path: "/medical-records", label: "Historial Clínico", icon: Icon.FileHeart },
    { path: "/inventory",      label: "Inventario",        icon: Icon.Package },
    { path: "/billing",       label: "Cobros",            icon: Icon.Receipt },
];

const ADMIN_ITEMS = [
    { path: "/staff",  label: "Equipo",         icon: Icon.Users },
    { path: "/config",  label: "Configuración",  icon: Icon.Settings },
];

const ROLE_LABELS = {
    ADMIN: "Administrador",
    VET: "Veterinario",
    ASSISTANT: "Asistente",
    ADMIN_SAAS: "Super Admin",
};

const Sidebar = ({ onLogout }) => {
    const location = useLocation();
    const { user, initializing } = useAuth();

    if (initializing) return null;

    const isAdmin = user?.role === "ADMIN" || user?.role === "ADMIN_SAAS";

    const isActive = (path) =>
        path === "/" ? location.pathname === "/" : location.pathname.startsWith(path);

    const NavLink = ({ item }) => {
        const active = isActive(item.path);
        const IconComp = item.icon;
        return (
            <Link
                to={item.path}
                style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    padding: "9px 12px",
                    borderRadius: "6px",
                    color: active ? "#f1f5f9" : "var(--sidebar-text)",
                    backgroundColor: active ? "var(--sidebar-active)" : "transparent",
                    textDecoration: "none",
                    fontSize: "13.5px",
                    fontWeight: active ? "600" : "400",
                    marginBottom: "2px",
                    transition: "background 150ms ease, color 150ms ease",
                    borderLeft: active ? "2px solid var(--sidebar-accent)" : "2px solid transparent",
                    paddingLeft: active ? "10px" : "12px",
                }}
                onMouseEnter={e => { if (!active) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)"; }}
                onMouseLeave={e => { if (!active) e.currentTarget.style.backgroundColor = "transparent"; }}
            >
                <IconComp s={17} c={active ? "#f1f5f9" : "var(--sidebar-text)"} />
                {item.label}
            </Link>
        );
    };

    return (
        <aside style={{
            width: "var(--sidebar-width)",
            height: "100vh",
            backgroundColor: "var(--sidebar-bg)",
            position: "fixed",
            left: 0, top: 0,
            display: "flex",
            flexDirection: "column",
            padding: "0",
            borderRight: "1px solid rgba(255,255,255,0.04)",
            zIndex: 100,
        }}>
            {/* Brand */}
            <div style={{ padding: "22px 18px 18px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "9px" }}>
                    <div style={{
                        width: "30px", height: "30px",
                        borderRadius: "8px",
                        background: "linear-gradient(135deg, #2dd4bf, #0d9488)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        flexShrink: 0,
                    }}>
                        <Icon.Stethoscope s={17} c="#fff" />
                    </div>
                    <div>
                        <div style={{ fontSize: "13px", fontWeight: "700", color: "#f1f5f9", letterSpacing: "0.02em" }}>
                            VetCare
                        </div>
                        <div style={{ fontSize: "11px", color: "var(--sidebar-text)", marginTop: "1px", maxWidth: "130px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {user?.organization_name || "Sistema"}
                        </div>
                    </div>
                </div>
            </div>

            {/* Divider */}
            <div style={{ height: "1px", backgroundColor: "rgba(255,255,255,0.05)", marginBottom: "10px" }} />

            {/* Nav principal */}
            <nav style={{ flex: 1, padding: "0 10px", overflowY: "auto" }}>
                {NAV_ITEMS.map(item => <NavLink key={item.path} item={item} />)}

                {/* Admin items */}
                {isAdmin && (
                    <>
                        <div style={{ margin: "14px 4px 6px", fontSize: "10px", fontWeight: "600", color: "rgba(148,163,184,0.5)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
                            Admin
                        </div>
                        {ADMIN_ITEMS.map(item => <NavLink key={item.path} item={item} />)}
                    </>
                )}
            </nav>

            {/* User footer */}
            <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)", padding: "14px 12px" }}>
                <div style={{ marginBottom: "10px", padding: "0 4px" }}>
                    <div style={{ fontSize: "13px", fontWeight: "600", color: "#e2e8f0" }}>
                        {user?.first_name ? `${user.first_name} ${user.last_name || ""}`.trim() : user?.username}
                    </div>
                    <div style={{ fontSize: "11px", color: "var(--sidebar-text)", marginTop: "2px" }}>
                        {ROLE_LABELS[user?.role] || user?.role}
                    </div>
                </div>
                <button
                    onClick={onLogout}
                    style={{
                        width: "100%", padding: "8px 12px",
                        background: "rgba(255,255,255,0.04)",
                        color: "var(--sidebar-text)",
                        border: "1px solid rgba(255,255,255,0.07)",
                        borderRadius: "6px", cursor: "pointer",
                        fontSize: "12.5px", fontWeight: "500",
                        fontFamily: "inherit",
                        transition: "background 150ms ease, color 150ms ease",
                        textAlign: "left",
                        display: "flex", alignItems: "center", gap: "8px",
                    }}
                    onMouseEnter={e => { e.currentTarget.style.background = "rgba(239,68,68,0.12)"; e.currentTarget.style.color = "#fca5a5"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; e.currentTarget.style.color = "var(--sidebar-text)"; }}
                >
                    <Icon.LogOut s={15} c="currentColor" />
                    Cerrar sesión
                </button>
            </div>
        </aside>
    );
};

export default Sidebar;
