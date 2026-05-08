export function Checkbox({ checked, onChange, children }) {
  return (
    <label className="checkbox">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="checkbox-box" aria-hidden="true" />
      <span>{children}</span>
    </label>
  );
}
