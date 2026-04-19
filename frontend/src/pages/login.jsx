import { useState } from "react";
import { loginRequest, getMe } from "../auth/login";
import { useAuth } from "../auth/authContext";
import { useNavigate } from "react-router-dom";
import s from "./login.module.css";

const Login = () => {
    const { login, setUserData, initializing } = useAuth();
    const navigate = useNavigate();

    const [form, setForm] = useState({ username: "", password: "" });
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    if (initializing) {
        return (
            <div className={s.root}>
                <p style={{ color: "rgba(245,241,232,0.4)", fontSize: "13px" }}>Cargando...</p>
            </div>
        );
    }

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            const data = await loginRequest(form.username, form.password);
            const userData = await getMe(data.access);
            login(data.access, data.refresh);
            setUserData(userData);
            navigate("/");
        } catch (err) {
            if (err.response?.status === 401) {
                setError("Usuario o contraseña incorrectos.");
            } else {
                setError("Error de conexión. Verifica tu internet e intenta de nuevo.");
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={s.root}>
            <div className={s.blobCorner} />

            {/* Marca sobre la tarjeta */}
            <div className={s.brand}>
                <div className={s.brandMark}>
                    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                        <path
                            d="M9 2C13 4 15 10 13 14C11 17 7 17 5 14C3 10 5 4 9 2Z"
                            fill="rgba(168,196,162,0.18)"
                            stroke="#a8c4a2"
                            strokeWidth="1.1"
                        />
                        <path
                            d="M3.5 9 L5.5 9 L7 6.5 L9 12 L11 6.5 L12.5 9 L14.5 9"
                            stroke="#a8c4a2"
                            strokeWidth="1.35"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        />
                    </svg>
                </div>
                <div className={s.brandName}>VetCare<sup>™</sup></div>
            </div>

            {/* Tarjeta */}
            <div className={s.card}>
                <h2 className={s.cardTitle}>
                    Iniciar<br /><em>sesión</em>
                </h2>
                <p className={s.cardSub}>
                    Accede a tu panel para gestionar citas, pacientes y tu equipo.
                </p>

                {error && <div className={s.errorAlert}>{error}</div>}

                <form onSubmit={handleSubmit}>
                    {/* Usuario */}
                    <div className={s.field}>
                        <input
                            type="text"
                            id="username"
                            placeholder=" "
                            autoComplete="username"
                            value={form.username}
                            onChange={e => setForm({ ...form, username: e.target.value })}
                        />
                        <label htmlFor="username">Usuario</label>
                        <span className={s.fieldIcon}>
                            <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                                <circle cx="8" cy="5.5" r="2.5" stroke="currentColor" strokeWidth="1.4" />
                                <path d="M2 13c0-3 2-4.5 6-4.5s6 1.5 6 4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                            </svg>
                        </span>
                    </div>

                    {/* Contraseña */}
                    <div className={s.field}>
                        <input
                            type={showPassword ? "text" : "password"}
                            id="password"
                            placeholder=" "
                            autoComplete="current-password"
                            value={form.password}
                            onChange={e => setForm({ ...form, password: e.target.value })}
                        />
                        <label htmlFor="password">Contraseña</label>
                        <span className={s.fieldIcon}>
                            <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                                <rect x="3" y="7" width="10" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
                                <path d="M5 7V5a3 3 0 0 1 6 0v2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                            </svg>
                        </span>
                        <button
                            type="button"
                            className={s.eyeBtn}
                            aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                            onClick={() => setShowPassword(v => !v)}
                        >
                            {showPassword ? (
                                <svg width="17" height="17" viewBox="0 0 18 18" fill="none">
                                    <path d="M2 2l14 14" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                                    <path d="M6.5 6.6A4 4 0 0 0 5 9c0 2.2 1.8 4 4 4a4 4 0 0 0 2.4-.8M8.1 5.1A4 4 0 0 1 13 9c0 .6-.1 1.1-.3 1.6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                                    <path d="M1.5 9C2.9 5.9 5.7 4 9 4M15.6 6.5C16.4 7.2 17 8 17 9c-1.5 3.5-4.5 5-8 5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                                </svg>
                            ) : (
                                <svg width="17" height="17" viewBox="0 0 18 18" fill="none">
                                    <path d="M1 9s3.2-5 8-5 8 5 8 5-3.2 5-8 5-8-5-8-5Z" stroke="currentColor" strokeWidth="1.3" />
                                    <circle cx="9" cy="9" r="2" stroke="currentColor" strokeWidth="1.3" />
                                </svg>
                            )}
                        </button>
                    </div>

                    {/* Extras */}
                    <div className={s.rowExtras}>
                        <label className={s.remember}>
                            <input type="checkbox" />
                            Recordarme
                        </label>
                        <a href="#" className={s.forgot} onClick={e => e.preventDefault()}>
                            ¿Olvidaste tu contraseña?
                        </a>
                    </div>

                    <button
                        type="submit"
                        className={s.btnSignin}
                        disabled={loading || !form.username || !form.password}
                    >
                        <span>{loading ? "Verificando..." : "Entrar al panel"}</span>
                        {!loading && (
                            <svg className={s.arrow} width="16" height="16" viewBox="0 0 18 18" fill="none">
                                <path d="M3 9h12M10 4l5 5-5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                        )}
                    </button>
                </form>

                <div className={s.cardFoot}>
                    <span>© 2025 VetCare</span>
                    <div>
                        <a href="#">Soporte</a>
                        <a href="#">Privacidad</a>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Login;
