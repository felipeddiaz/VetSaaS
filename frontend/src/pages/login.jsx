import { useState } from "react";
import { loginRequest, getMe } from "../auth/login";
import { useAuth } from "../auth/authContext";
import { useNavigate } from "react-router-dom";
import { Icon } from "../components/icons";

const Login = () => {
    const { login, setUserData, initializing } = useAuth();
    const navigate = useNavigate();

    const [form, setForm] = useState({ username: "", password: "" });
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    if (initializing) {
        return (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", background: "var(--c-bg)" }}>
                <p style={{ color: "var(--c-text-3)", fontSize: "13px" }}>Cargando...</p>
            </div>
        );
    }

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(""); setLoading(true);
        try {
            const data = await loginRequest(form.username, form.password);
            const userData = await getMe(data.access);
            login(data.access, data.refresh);
            setUserData(userData);
            navigate("/");
        } catch {
            setError("Usuario o contraseña incorrectos");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{
            minHeight: "100vh",
            background: "linear-gradient(135deg, #0c1422 0%, #0f2440 60%, #0c1422 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "24px",
        }}>
            {/* Decorative grid */}
            <div style={{
                position: "fixed", inset: 0, pointerEvents: "none",
                backgroundImage: "radial-gradient(circle at 1px 1px, rgba(45,212,191,0.07) 1px, transparent 0)",
                backgroundSize: "32px 32px",
            }} />

            <div style={{
                width: "100%", maxWidth: "380px",
                position: "relative", zIndex: 1,
                animation: "slideUp 0.3s ease",
            }}>
                {/* Logo */}
                <div style={{ textAlign: "center", marginBottom: "36px" }}>
                    <div style={{
                        width: "56px", height: "56px",
                        borderRadius: "16px",
                        background: "linear-gradient(135deg, #2dd4bf, #0d9488)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: "26px", margin: "0 auto 14px",
                        boxShadow: "0 8px 24px rgba(45,212,191,0.3)",
                    }}>
                        <Icon.Stethoscope s={28} c="#fff" />
                    </div>
                    <h1 style={{
                        fontSize: "22px", fontWeight: "700",
                        color: "#f1f5f9", marginBottom: "6px", letterSpacing: "-0.02em",
                    }}>
                        VetCare
                    </h1>
                    <p style={{ fontSize: "13.5px", color: "#64748b" }}>
                        Acceso al sistema de gestión
                    </p>
                </div>

                {/* Card */}
                <div style={{
                    background: "rgba(255,255,255,0.03)",
                    border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: "16px",
                    padding: "28px 28px 32px",
                    backdropFilter: "blur(12px)",
                    boxShadow: "0 24px 64px rgba(0,0,0,0.4)",
                }}>
                    {error && (
                        <div style={{
                            background: "rgba(239,68,68,0.12)",
                            border: "1px solid rgba(239,68,68,0.25)",
                            borderRadius: "8px",
                            padding: "10px 14px",
                            marginBottom: "18px",
                            fontSize: "13px",
                            color: "#fca5a5",
                        }}>
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleSubmit}>
                        <div style={{ marginBottom: "14px" }}>
                            <label style={{
                                display: "block", marginBottom: "6px",
                                fontSize: "12.5px", fontWeight: "600",
                                color: "#94a3b8", letterSpacing: "0.02em",
                            }}>
                                USUARIO
                            </label>
                            <input
                                value={form.username}
                                onChange={e => setForm({ ...form, username: e.target.value })}
                                placeholder="Tu nombre de usuario"
                                autoComplete="username"
                                style={{
                                    width: "100%", height: "42px",
                                    padding: "0 14px",
                                    background: "rgba(255,255,255,0.06)",
                                    border: "1.5px solid rgba(255,255,255,0.1)",
                                    borderRadius: "8px",
                                    color: "#f1f5f9",
                                    fontSize: "14px",
                                    outline: "none",
                                    fontFamily: "inherit",
                                    boxSizing: "border-box",
                                    transition: "border-color 150ms ease, box-shadow 150ms ease",
                                }}
                                onFocus={e => { e.target.style.borderColor = "#2dd4bf"; e.target.style.boxShadow = "0 0 0 3px rgba(45,212,191,0.15)"; }}
                                onBlur={e => { e.target.style.borderColor = "rgba(255,255,255,0.1)"; e.target.style.boxShadow = "none"; }}
                            />
                        </div>

                        <div style={{ marginBottom: "24px" }}>
                            <label style={{
                                display: "block", marginBottom: "6px",
                                fontSize: "12.5px", fontWeight: "600",
                                color: "#94a3b8", letterSpacing: "0.02em",
                            }}>
                                CONTRASEÑA
                            </label>
                            <input
                                type="password"
                                value={form.password}
                                onChange={e => setForm({ ...form, password: e.target.value })}
                                placeholder="••••••••"
                                autoComplete="current-password"
                                style={{
                                    width: "100%", height: "42px",
                                    padding: "0 14px",
                                    background: "rgba(255,255,255,0.06)",
                                    border: "1.5px solid rgba(255,255,255,0.1)",
                                    borderRadius: "8px",
                                    color: "#f1f5f9",
                                    fontSize: "14px",
                                    outline: "none",
                                    fontFamily: "inherit",
                                    boxSizing: "border-box",
                                    transition: "border-color 150ms ease, box-shadow 150ms ease",
                                }}
                                onFocus={e => { e.target.style.borderColor = "#2dd4bf"; e.target.style.boxShadow = "0 0 0 3px rgba(45,212,191,0.15)"; }}
                                onBlur={e => { e.target.style.borderColor = "rgba(255,255,255,0.1)"; e.target.style.boxShadow = "none"; }}
                            />
                        </div>

                        <button
                            type="submit"
                            disabled={loading || !form.username || !form.password}
                            style={{
                                width: "100%", height: "42px",
                                background: loading ? "rgba(45,212,191,0.4)" : "linear-gradient(135deg, #2dd4bf, #14b8a6)",
                                color: "white",
                                border: "none", borderRadius: "8px",
                                fontSize: "14px", fontWeight: "700",
                                cursor: loading ? "not-allowed" : "pointer",
                                fontFamily: "inherit",
                                letterSpacing: "0.02em",
                                transition: "opacity 150ms ease, transform 150ms ease",
                                boxShadow: "0 4px 14px rgba(45,212,191,0.3)",
                            }}
                            onMouseEnter={e => { if (!loading) e.currentTarget.style.opacity = "0.9"; }}
                            onMouseLeave={e => { e.currentTarget.style.opacity = "1"; }}
                        >
                            {loading ? "Verificando..." : "Iniciar sesión"}
                        </button>
                    </form>
                </div>

                <p style={{ textAlign: "center", marginTop: "20px", fontSize: "12px", color: "#334155" }}>
                    VetCare SaaS · Sistema de Gestión Veterinaria
                </p>
            </div>
        </div>
    );
};

export default Login;
