const MissingState = () => (
  <span
    className="missing-state"
    title="Datos aún no disponibles. Se generarán en el próximo snapshot nocturno."
  >
    <span className="missing-state-dash">—</span>
    <span className="missing-state-label">Sin datos</span>
  </span>
);

export default MissingState;
