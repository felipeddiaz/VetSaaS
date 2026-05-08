import { Brand } from "../components/Brand";
import { HeroPanel } from "../components/HeroPanel";
import { LoginForm } from "../components/LoginForm";
import { useAuth } from "../auth/authContext";
import "../styles/login.css";

export default function Login() {
  const { initializing } = useAuth();

  if (initializing) {
    return (
      <div className="login-loading">
        Cargando...
      </div>
    );
  }

  return (
    <div className="login-page">
      <section className="login-left">
        <Brand />
        <div className="left-body">
          <HeroPanel />
        </div>
        <div className="login-foot">
          © 2026 SaaSly — Todos los derechos reservados.
        </div>
      </section>

      <section className="login-right">
        <div className="login-card">
          <h2 className="login-title">Iniciar sesión</h2>
          <p className="login-subtitle">
            Bienvenido de vuelta. Ingresa tus credenciales para acceder al sistema.
          </p>

          <LoginForm />

          <div className="login-signup-link">
            ¿No tienes una cuenta? <a href="#" onClick={e => e.preventDefault()}>Solicitar acceso</a>
          </div>
        </div>
      </section>
    </div>
  );
}
