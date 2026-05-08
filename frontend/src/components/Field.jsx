export function Field({ label, id, type = "text", value, onChange, placeholder, autoComplete, children, required = false }) {
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      <div className="field-wrap">
        <input
          id={id}
          type={type}
          className={`field-input ${children ? "has-toggle" : ""}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete={autoComplete}
          required={required}
        />
        {children}
      </div>
    </div>
  );
}
