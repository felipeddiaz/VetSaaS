import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon } from "../icons";

export default function ClinicalBacklog({ backlog }) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  if (!backlog) return null;

  const total     = backlog.open_total ?? 0;
  const needsAttn = backlog.needs_attention_count ?? 0;
  const noDiag    = backlog.without_diagnosis ?? 0;
  const records   = backlog.open_records ?? [];
  const hasIssues = needsAttn > 0 || noDiag > 0;

  if (total === 0) {
    return (
      <div className="dsp">
        <div className="dsp-head">
          <h3 className="dsp-title">Backlog clínico</h3>
        </div>
        <p className="dsp-empty">Sin consultas pendientes.</p>
      </div>
    );
  }

  return (
    <div className="dsp">
      <div className="dsp-head">
        <h3 className="dsp-title">Backlog clínico</h3>
        {needsAttn > 0 && (
          <span className="badge badge-danger">{needsAttn}</span>
        )}
      </div>

      {hasIssues && (
        <div className="dsp-chip-row">
          {needsAttn > 0 && (
            <span className="badge badge-danger">
              {needsAttn} necesita{needsAttn > 1 ? "n" : ""} atención
            </span>
          )}
          {noDiag > 0 && (
            <span className="badge badge-warning">
              {noDiag} sin diagnóstico
            </span>
          )}
        </div>
      )}

      {expanded && records.length > 0 && (
        <div className="dsp-backlog-list">
          {records.map((r) => (
            <div
              key={r.public_id}
              className="dsp-backlog-row"
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/medical-records?record=${r.public_id}`)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  navigate(`/medical-records?record=${r.public_id}`);
                }
              }}
            >
              <div className="dsp-callout-name">
                {r.pet_name || "Sin mascota"}
              </div>
              <div className="dsp-callout-meta">
                {r.veterinarian_name}
                {" · "}
                {r.days_open >= 1
                  ? `${r.days_open} ${r.days_open === 1 ? "día" : "días"} abierta`
                  : `${Math.round(r.hours_open)}h abierta`}
              </div>
              {!r.has_diagnosis && (
                <div className="dsp-callout-warn">
                  <Icon.AlertCircle s={12} /> Sin diagnóstico
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <button
        className="btn btn-ghost btn-xs dsp-action"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? "▲ Contraer" : `▼ Ver todas (${total})`}
      </button>

      <button
        className="btn btn-ghost btn-xs dsp-action"
        onClick={() => navigate("/medical-records")}
      >
        Gestionar consultas →
      </button>
    </div>
  );
}
