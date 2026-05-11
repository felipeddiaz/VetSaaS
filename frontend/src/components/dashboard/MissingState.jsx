const MissingState = () => (
  <span
    style={{
      display: "inline-flex",
      flexDirection: "column",
      alignItems: "center",
      gap: "2px",
      color: "var(--c-text-4)",
      fontFamily: "var(--font-display)",
      fontSize: "10px",
      fontWeight: "500",
      letterSpacing: "0.08em",
      lineHeight: "1.2",
    }}
    title="Datos aún no disponibles. Se generarán en el próximo snapshot nocturno."
  >
    <span style={{ fontSize: "inherit" }}>—</span>
    <span style={{ fontSize: "8px", opacity: 0.7, textTransform: "uppercase", letterSpacing: "0.12em" }}>
      Sin datos
    </span>
  </span>
);

export default MissingState;
