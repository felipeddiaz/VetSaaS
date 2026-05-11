import { useNavigate } from "react-router-dom";

export default function ClinicalBacklog({ backlog }) {
  const navigate = useNavigate();

  if (!backlog) return null;

  const stale    = backlog.stale_24h ?? 0;
  const noDiag   = backlog.without_diagnosis ?? 0;
  const hasIssues = stale > 0 || noDiag > 0;

  return (
    <div className="side-panel">
      <div className="side-title">Backlog clínico</div>

      {!hasIssues ? (
        <div className="side-empty-ok">Sin consultas pendientes</div>
      ) : (
        <>
          {/* Counter pills */}
          <div className="bl-counters">
            {stale > 0 && (
              <div className="bl-counter bl-counter-danger">
                {stale} abierta{stale > 1 ? "s" : ""} &gt;24h
              </div>
            )}
            {noDiag > 0 && (
              <div className="bl-counter bl-counter-warning">
                {noDiag} sin diagnóstico
              </div>
            )}
          </div>

          {/* Top stale record */}
          {backlog.top_stale && (
            <div className="bl-top">
              <span className="bl-top-pet">
                {backlog.top_stale.pet_name || "Sin mascota"}
              </span>
              <span className="bl-top-meta">
                {[
                  backlog.top_stale.veterinarian_name,
                  backlog.top_stale.hours_open != null
                    ? `${Math.round(backlog.top_stale.hours_open)}h abierta`
                    : null,
                ].filter(Boolean).join(" · ")}
              </span>
              {!backlog.top_stale.has_diagnosis && (
                <span className="bl-top-warn">Sin diagnóstico registrado</span>
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
