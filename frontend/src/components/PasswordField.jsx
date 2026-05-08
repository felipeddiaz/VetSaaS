import { useState } from "react";
import { Field } from "./Field";
import { EyeIcon } from "./icons/EyeIcon";
import { EyeOffIcon } from "./icons/EyeOffIcon";

export function PasswordField({ value, onChange, label = "Contraseña", id = "password", autoComplete = "current-password", required = false }) {
  const [show, setShow] = useState(false);
  return (
    <Field
      id={id}
      label={label}
      type={show ? "text" : "password"}
      value={value}
      onChange={onChange}
      placeholder="••••••••"
      autoComplete={autoComplete}
      required={required}
    >
      <button
        type="button"
        className="field-toggle"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? "Ocultar contraseña" : "Mostrar contraseña"}
      >
        {show ? <EyeIcon /> : <EyeOffIcon />}
      </button>
    </Field>
  );
}
