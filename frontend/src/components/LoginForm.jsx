import { useLoginForm } from "../hooks/useLoginForm";
import { Field } from "./Field";
import { PasswordField } from "./PasswordField";
import { Checkbox } from "./Checkbox";
import { GoogleIcon } from "./icons/GoogleIcon";

export function LoginForm() {
  const {
    username,
    setUsername,
    password,
    setPassword,
    remember,
    setRemember,
    loading,
    handleSubmit
  } = useLoginForm();

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <div className="field-group">
        <Field
          id="username"
          label="Usuario o Email"
          value={username}
          onChange={setUsername}
          placeholder="ej. veterinaria_central"
          autoComplete="username"
          required
        />

        <PasswordField
          id="password"
          value={password}
          onChange={setPassword}
          required
        />
      </div>

      <div className="form-meta">
        <Checkbox checked={remember} onChange={setRemember}>
          Recordarme
        </Checkbox>
        <a href="#" className="forgot-password" onClick={e => e.preventDefault()}>
          ¿Olvidaste tu contraseña?
        </a>
      </div>

      <button type="submit" className="btn-primary" disabled={loading || !username || !password}>
        {loading ? "Iniciando sesión..." : "Entrar al panel"}
      </button>

      <div className="or">o continúa con</div>

      <button type="button" className="btn-google" onClick={() => alert('Próximamente')}>
        <GoogleIcon />
        Google
      </button>
    </form>
  );
}
