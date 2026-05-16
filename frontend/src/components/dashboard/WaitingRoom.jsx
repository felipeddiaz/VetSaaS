export default function WaitingRoom({ items }) {
  if (!items || items.length === 0) {
    return (
      <div className="dsp">
        <div className="dsp-head">
          <h3 className="dsp-title">Sala de espera</h3>
        </div>
        <p className="dsp-empty">Sin pacientes en espera.</p>
      </div>
    );
  }

  return (
    <div className="dsp">
      <div className="dsp-head">
        <h3 className="dsp-title">Sala de espera</h3>
        <span className="badge badge-default">{items.length}</span>
      </div>

      <ul className="dsp-list">
        {items.slice(0, 5).map((p, i) => (
          <li key={i} className={`dsp-item ${p.is_late ? "is-late" : ""}`}>
            <div className="dsp-avatar">
              {(p.pet_name?.[0] || "?").toUpperCase()}
            </div>
            <div className="dsp-item-body">
              <span className="dsp-item-name">{p.pet_name || "Anónimo"}</span>
              <span className="dsp-item-meta">
                {p.time}
                {p.wait_minutes > 0 && ` · ${p.wait_minutes}min espera`}
              </span>
            </div>
            <span className={`badge ${p.is_late ? "badge-warning" : "badge-primary"}`}>
              {p.is_late ? "Demora" : "Próximo"}
            </span>
          </li>
        ))}
        {items.length > 5 && (
          <li className="dsp-overflow">+{items.length - 5} más</li>
        )}
      </ul>
    </div>
  );
}
