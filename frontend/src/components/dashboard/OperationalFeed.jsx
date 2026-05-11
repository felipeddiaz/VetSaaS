import { useNavigate } from "react-router-dom";
import { Icon } from "../icons";

const REC_TYPE = {
  general: "General",
  surgery: "Cirugía",
  vaccine: "Vacuna",
  emergency: "Emergencia",
};

const OperationalFeed = ({ openRecords }) => {
  const navigate = useNavigate();
  const { records: list, loading, error, refetch } = openRecords;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <Icon.FileHeart s={14} c="var(--c-primary)" />
          Consultas abiertas
        </span>
        {!loading && !error && list.length > 0 && (
          <span className="pill pill-in_progress">{list.length}</span>
        )}
      </div>

      {loading && <div style={{ color: "var(--c-text-3)", fontSize: "11px", textAlign: "center", padding: "16px 0" }}>Cargando...</div>}

      {error && (
        <div style={{ color: "var(--c-danger-text)", fontSize: "11px", padding: "12px 0", display: "flex", alignItems: "center", gap: "8px" }}>
          <Icon.AlertTriangle s={12} c="var(--c-danger-text)" />
          <span>{error}</span>
          <button className="btn btn-ghost btn-xs" onClick={refetch}>
            <Icon.Refresh s={10} /> Reintentar
          </button>
        </div>
      )}

      {!loading && !error && list.length === 0 && (
        <div style={{ color: "var(--c-text-3)", fontSize: "11px", textAlign: "center", padding: "16px 0" }}>
          No hay consultas abiertas.
        </div>
      )}

      {!loading && !error && list.length > 0 && (
        <>
          {list.slice(0, 5).map((r) => (
            <button
              key={r.id || r.public_id}
              className="records-item"
              onClick={() => navigate(`/medical-records?record=${r.public_id || r.id}`)}
            >
              <div className="records-item-left">
                <span className="records-item-pet" title={r.pet_name}>
                  {r.pet_name || "Sin paciente"}
                </span>
                <span className="records-item-meta" title={REC_TYPE[r.consultation_type]}>
                  {REC_TYPE[r.consultation_type] || r.consultation_type || "—"}
                  {r.veterinarian_name ? ` · ${r.veterinarian_name}` : ""}
                </span>
              </div>
              <Icon.ChevronRight s={12} c="var(--c-text-4)" />
            </button>
          ))}
          {list.length > 5 && (
            <button className="records-more-btn" onClick={() => navigate("/medical-records?status=open")}>
              Ver todas ({list.length})
            </button>
          )}
        </>
      )}
    </div>
  );
};

export default OperationalFeed;
