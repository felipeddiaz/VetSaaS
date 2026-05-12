export default function WaitingRoom({ items }) {
  if (!items || items.length === 0) {
    return (
      <div className="side-panel">
        <div className="side-title">Sala de espera</div>
        <div className="side-empty-ok">Sin pacientes en espera</div>
      </div>
    );
  }

  return (
    <div className="side-panel">
      <div className="side-title">
        Sala de espera
        <span className="wr-count">{items.length}</span>
      </div>

      <div className="wr-list">
        {items.slice(0, 4).map((p, i) => (
          <div key={i} className={`wr-item${p.is_late ? " wr-late" : ""}`}>
            {/* Avatar with initial */}
            <div className="wr-avatar">
              {(p.pet_name?.[0] || "?").toUpperCase()}
            </div>

            <div className="wr-left">
              <span className="wr-pet">{p.pet_name || "Anónimo"}</span>
              <span className="wr-meta">
                {p.time}
                {p.wait_minutes > 0 && (
                  <> · <span className={p.is_late ? "wr-wait-late" : "wr-wait"}>
                    {p.wait_minutes}min espera
                  </span></>
                )}
              </span>
            </div>

            <span className={`wr-status${p.is_late ? " wr-late-badge" : ""}`}>
              {p.is_late ? "Demora" : "Próximo"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
