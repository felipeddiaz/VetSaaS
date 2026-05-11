import { useNavigate } from "react-router-dom";

export default function ClinicalBacklog({ backlog }) {
  const navigate = useNavigate();

  if (!backlog) return null;

  const hasIssues = (backlog.stale_24h ?? 0) > 0 || (backlog.without_diagnosis ?? 0) > 0;

  return (
    <div className="side-panel">
      <div className="side-title">Backlog clínico</div>
      {!hasIssues ? (
        <div className="side-empty-ok">Sin consultas pendientes</div>
      ) : (
        <>
          <div className="bl-counters">
            {(backlog.stale_24h ?? 0) > 0 && (
              <div className="bl-counter bl-counter-danger">
                {backlog.stale_24h} {backlog.stale_24h === 1 ? "abierta" : "abiertas"} &gt;24h
              </div>
            )}
            {(backlog.without_diagnosis ?? 0) > 0 && (
              <div className="bl-counter bl-counter-warning">
                {backlog.without_diagnosis} sin diagnóstico
              </div>
            )}
          </div>
          {backlog.top_stale && (
            <div className="bl-top">
              <span className="bl-top-pet">{backlog.top_stale.pet_name || "Sin mascota"}</span>
              <span className="bl-top-meta">
                {backlog.top_stale.veterinarian_name}
                {backlog.top_stale.hours_open != null &&
                  ` · ${Math.round(backlog.top_stale.hours_open)}h abierta`}
              </span>
              {!backlog.top_stale.has_diagnosis && (
                <span className="bl-top-warn">Sin diagnóstico</span>
              )}
            </div>
          )}
          <button
            className="side-link-btn"
            onClick={() => navigate("/medical-records")}
          >
            Gestionar →
          </button>
        </>
      )}
    </div>
  );
}
