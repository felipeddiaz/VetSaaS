import { useMemo, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const STATUS_LABELS = {
  scheduled:   "Programada",
  confirmed:   "Confirmada",
  in_progress: "En consulta",
  done:        "Completada",
  canceled:    "Cancelada",
  no_show:     "No se presentó",
};

const STATUS_BADGE = {
  scheduled:   "badge-info",
  confirmed:   "badge-purple",
  in_progress: "badge-warning",
  done:        "badge-success",
  canceled:    "badge-danger",
  no_show:     "badge-default",
};

const STATUS_DOT = {
  scheduled:   "dtl-dot-scheduled",
  confirmed:   "dtl-dot-confirmed",
  in_progress: "dtl-dot-active",
  done:        "dtl-dot-done",
  canceled:    "dtl-dot-canceled",
  no_show:     "dtl-dot-noshow",
};

const DAY_START = 8;
const DAY_END   = 20;
const HOURS = Array.from({ length: DAY_END - DAY_START + 1 }, (_, i) => DAY_START + i);

function timeToPct(time) {
  if (!time) return null;
  const [h, m] = time.split(":").map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  const mins = h * 60 + m;
  const start = DAY_START * 60;
  const end   = DAY_END * 60;
  if (mins < start || mins > end) return null;
  return ((mins - start) / (end - start)) * 100;
}

function nowPct() {
  const d = new Date();
  return timeToPct(`${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`);
}

export default function OperationalTimeline({ slots }) {
  const navigate = useNavigate();
  const [now, setNow] = useState(nowPct);

  useEffect(() => {
    const id = setInterval(() => setNow(nowPct()), 60_000);
    return () => clearInterval(id);
  }, []);

  const filled = useMemo(
    () => (slots || []).filter((s) => s.appointment && timeToPct(s.time) != null),
    [slots]
  );

  const upcoming = useMemo(() => {
    const d = new Date();
    const nowMin = d.getHours() * 60 + d.getMinutes();
    return filled
      .filter((s) => {
        const [h, m] = s.time.split(":").map(Number);
        return h * 60 + m >= nowMin
          && (s.appointment.status === "scheduled" || s.appointment.status === "confirmed");
      })
      .slice(0, 5);
  }, [filled]);

  if (!slots || slots.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-state-title">Sin citas programadas</p>
        <p className="empty-state-sub">No hay actividad agendada para hoy.</p>
      </div>
    );
  }

  return (
    <div className="dtl">
      <div className="dtl-track-wrap">
        <div className="dtl-axis">
          {HOURS.map((h) => (
            <span key={h} className="dtl-axis-tick">
              <span className="dtl-axis-lbl">{h.toString().padStart(2, "0")}</span>
            </span>
          ))}
        </div>

        <div className="dtl-track">
          {HOURS.map((h, i) => (
            <span key={h} className="dtl-gridline" style={{ left: `${(i / (HOURS.length - 1)) * 100}%` }} />
          ))}

          {now != null && (
            <div className="dtl-now" style={{ left: `${now}%` }} aria-label="Hora actual">
              <span className="dtl-now-lbl">Ahora</span>
            </div>
          )}

          {filled.map((s, i) => {
            const pct = timeToPct(s.time);
            const appt = s.appointment;
            return (
              <button
                key={i}
                className={`dtl-dot ${STATUS_DOT[appt.status] || ""}`}
                style={{ left: `${pct}%` }}
                onClick={() => navigate("/appointments")}
                aria-label={`${s.time} — ${appt.pet_name || "Cita"}`}
              >
                <span className="dtl-dot-pin" />
                <span className="dtl-dot-tip">
                  <span className="dtl-dot-tip-time">{s.time}</span>
                  <span className="dtl-dot-tip-pet">{appt.pet_name || "Paciente"}</span>
                  {appt.veterinarian_name && (
                    <span className="dtl-dot-tip-vet">{appt.veterinarian_name}</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="dtl-legend">
        <span><span className="dtl-leg dtl-dot-scheduled" /> Programada</span>
        <span><span className="dtl-leg dtl-dot-confirmed" /> Confirmada</span>
        <span><span className="dtl-leg dtl-dot-active" /> En consulta</span>
        <span><span className="dtl-leg dtl-dot-done" /> Completada</span>
        <span><span className="dtl-leg dtl-dot-canceled" /> Cancelada</span>
      </div>

      {upcoming.length > 0 && (
        <div className="dtl-upnext">
          <div className="dtl-upnext-title">Próximos turnos</div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 80 }}>Hora</th>
                  <th>Paciente</th>
                  <th>Motivo</th>
                  <th>Veterinario</th>
                  <th style={{ width: 110 }}>Estado</th>
                </tr>
              </thead>
              <tbody>
                {upcoming.map((s, i) => (
                  <tr key={i} onClick={() => navigate("/appointments")} style={{ cursor: "pointer" }}>
                    <td><strong>{s.time}</strong></td>
                    <td>{s.appointment.walk_in && "● "}{s.appointment.pet_name || "Paciente"}</td>
                    <td style={{ color: "var(--c-text-3)" }}>{s.appointment.reason || "—"}</td>
                    <td style={{ color: "var(--c-text-2)" }}>{s.appointment.veterinarian_name || "—"}</td>
                    <td>
                      <span className={`badge ${STATUS_BADGE[s.appointment.status] || "badge-default"}`}>
                        {STATUS_LABELS[s.appointment.status] || s.appointment.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
