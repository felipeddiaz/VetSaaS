import { useNavigate } from "react-router-dom";
import { Icon } from "../icons";

const EmptyDashboard = () => {
  const navigate = useNavigate();

  return (
    <div className="empty-dashboard">
      <div className="empty-dashboard-icon">
        <Icon.Activity s={28} c="var(--c-primary)" />
      </div>
      <h2 className="empty-dashboard-title">No hay suficientes datos todavía</h2>
      <p className="empty-dashboard-body">
        Las métricas aparecerán después de registrar actividad en la clínica.
        Agenda citas, registra consultas y completa atenciones para ver tu dashboard.
      </p>
      <button
        className="btn btn-primary btn-md empty-dashboard-cta"
        onClick={() => navigate("/appointments")}
      >
        <Icon.CalendarClock s={15} />
        Agendar primera cita
      </button>
    </div>
  );
};

export default EmptyDashboard;
