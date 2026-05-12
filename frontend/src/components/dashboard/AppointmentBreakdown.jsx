import { useNavigate } from "react-router-dom";
import { Icon } from "../icons";

const PILL_CLASS = {
  scheduled:   "pill-scheduled",
  confirmed:   "pill-confirmed",
  in_progress: "pill-in_progress",
  done:        "pill-done",
  canceled:    "pill-canceled",
  no_show:     "pill-no_show",
};

const STATUS_LABELS = {
  scheduled:   "Programada",
  confirmed:   "Confirmada",
  in_progress: "En consulta",
  done:        "Completada",
  canceled:    "Cancelada",
  no_show:     "No se presentó",
};

const AppointmentBreakdown = ({ byStatus, totals, statusOrder, selectedStatus }) => {
  const navigate = useNavigate();
  if (!statusOrder?.length) return null;

  const grandTotal = Object.values(totals || {}).reduce((a, b) => a + b, 0);
  const title = selectedStatus
    ? `${STATUS_LABELS[selectedStatus]} (${totals[selectedStatus] || 0})`
    : `Agenda (${grandTotal})`;

  return (
    <>
      <div className="card-header">
        <span className="card-title">{title}</span>
      </div>

      {statusOrder.map((status) => {
        const group     = byStatus[status];
        const total     = totals[status] || 0;
        const items     = group?.items || [];
        const hasMore   = group?.has_more;
        const remaining = group?.remaining;

        if (selectedStatus && selectedStatus !== status) return null;
        if (!selectedStatus && total === 0) return null;

        return (
          <div key={status}>
            <div className="breakdown-group-head">
              <span className={`pill ${PILL_CLASS[status] || "pill-scheduled"}`}>
                {STATUS_LABELS[status]} ({total})
              </span>
            </div>
            {items.map((a) => (
              <button
                key={a.public_id}
                className="breakdown-item"
                onClick={() => navigate(`/appointments?appointment=${a.public_id}`)}
              >
                <span className="breakdown-item-time">{a.start_time || "—"}</span>
                <span className="breakdown-item-pet" title={a.pet_name}>
                  {a.pet_name || "Sin paciente"}
                </span>
                <span className="breakdown-item-vet" title={a.veterinarian_name}>
                  {a.veterinarian_name || "—"}
                </span>
                <Icon.ChevronRight s={12} c="var(--c-text-4)" />
              </button>
            ))}
            {hasMore && (
              <button
                className="breakdown-more-btn"
                onClick={() => navigate(`/appointments?status=${status}`)}
              >
                + Ver {remaining} más
              </button>
            )}
          </div>
        );
      })}

      {statusOrder.every((s) => (totals[s] || 0) === 0) && (
        <div className="breakdown-empty">Sin citas en este periodo.</div>
      )}
    </>
  );
};

export default AppointmentBreakdown;
