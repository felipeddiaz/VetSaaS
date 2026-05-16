import { useMemo } from "react";
import { Icon } from "../icons";

function nextUpSlot(timeline) {
  if (!timeline || timeline.length === 0) return null;
  const now = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();
  for (const slot of timeline) {
    const appt = slot.appointment;
    if (!appt) continue;
    if (appt.status !== "scheduled" && appt.status !== "confirmed") continue;
    const [h, m] = (slot.time || "00:00").split(":").map(Number);
    if (h * 60 + m >= nowMin) {
      return { time: slot.time, pet: appt.pet_name, vet: appt.veterinarian_name };
    }
  }
  return null;
}

function currentInProgress(timeline) {
  if (!timeline) return null;
  const slot = timeline.find((s) => s.appointment?.status === "in_progress");
  if (!slot) return null;
  return {
    time: slot.time,
    pet:  slot.appointment.pet_name,
    vet:  slot.appointment.veterinarian_name,
  };
}

export default function NowPanel({ summary }) {
  const enCurso  = summary?.kpis?.in_progress_now ?? 0;
  const current  = useMemo(() => currentInProgress(summary?.timeline), [summary?.timeline]);
  const nextUp   = useMemo(() => nextUpSlot(summary?.timeline), [summary?.timeline]);

  return (
    <div className="dsp">
      <div className="dsp-head">
        <h3 className="dsp-title">Ahora</h3>
        <span className="dsp-live">
          <span className="dsp-live-dot" /> En vivo
        </span>
      </div>

      <ul className="dsp-rows">
        <li className={`dsp-row ${enCurso > 0 ? "is-active" : ""}`}>
          <span className="dsp-row-ico"><Icon.Activity s={13} /></span>
          <div className="dsp-row-body">
            <span className="dsp-row-lbl">En consulta</span>
            <span className="dsp-row-meta">
              {current
                ? `${current.pet} · ${current.vet}`
                : enCurso === 0 ? "Sin consultas activas" : `${enCurso} en curso`}
            </span>
          </div>
          <span className="dsp-row-num">{enCurso}</span>
        </li>

        <li className="dsp-row">
          <span className="dsp-row-ico"><Icon.CalendarClock s={13} /></span>
          <div className="dsp-row-body">
            <span className="dsp-row-lbl">Próximo turno</span>
            <span className="dsp-row-meta">
              {nextUp ? `${nextUp.pet} · ${nextUp.vet}` : "Sin citas próximas"}
            </span>
          </div>
          <span className="dsp-row-num dsp-row-num-time">
            {nextUp ? nextUp.time : "—"}
          </span>
        </li>
      </ul>
    </div>
  );
}
