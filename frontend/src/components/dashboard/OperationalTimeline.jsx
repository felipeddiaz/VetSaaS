import { useNavigate } from "react-router-dom";

const STATUS_LABELS = {
  scheduled: "Pendiente",
  confirmed: "Confirmada",
  in_progress: "En curso",
  done: "Completada",
  canceled: "Cancelada",
  no_show: "No asistió",
};

const STATUS_CLASS = {
  scheduled: "tl-scheduled",
  confirmed: "tl-confirmed",
  in_progress: "tl-active",
  done: "tl-done",
  canceled: "tl-canceled",
  no_show: "tl-noshow",
};

export default function OperationalTimeline({ slots }) {
  const navigate = useNavigate();

  if (!slots || slots.length === 0) {
    return (
      <div className="timeline-empty">
        <span>Sin citas programadas para hoy.</span>
      </div>
    );
  }

  return (
    <div className="timeline-list">
      {slots.map((slot, i) => {
        const appt = slot.appointment;
        if (!appt) {
          return (
            <div key={i} className="tl-row tl-free">
              <span className="tl-time">{slot.time}</span>
              <span className="tl-empty-label">— Disponible —</span>
              <span />
            </div>
          );
        }

        return (
          <div
            key={i}
            className={`tl-row ${STATUS_CLASS[appt.status] || ""}`}
            onClick={() => navigate(`/appointments`)}
          >
            <span className="tl-time">{slot.time}</span>
            <div className="tl-body">
              <span className="tl-pet">
                {appt.walk_in && "🚶 "}
                {appt.pet_name || "Paciente anónimo"}
              </span>
              {appt.reason && <span className="tl-reason">{appt.reason}</span>}
            </div>
            <div className="tl-meta">
              <span className="tl-vet">{appt.veterinarian_name}</span>
              <span className={`tl-status-badge ${STATUS_CLASS[appt.status] || ""}`}>
                {STATUS_LABELS[appt.status] || appt.status}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
