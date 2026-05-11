import { useNavigate } from "react-router-dom";
import { Icon } from "../icons";

const EmptyDashboard = () => {
  const navigate = useNavigate();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "64px 24px",
        textAlign: "center",
        minHeight: "50vh",
      }}
    >
      <div
        style={{
          width: "64px",
          height: "64px",
          borderRadius: "var(--r-xl)",
          background: "var(--c-primary-light)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: "24px",
        }}
      >
        <Icon.Activity s={28} c="var(--c-primary)" />
      </div>
      <h2
        style={{
          fontSize: "18px",
          fontWeight: "600",
          color: "var(--c-text)",
          marginBottom: "8px",
          fontFamily: "var(--font-body)",
        }}
      >
        No hay suficientes datos todavía
      </h2>
      <p
        style={{
          fontSize: "13px",
          color: "var(--c-text-2)",
          maxWidth: "360px",
          lineHeight: "1.6",
          marginBottom: "24px",
        }}
      >
        Las métricas aparecerán después de registrar actividad en la clínica.
        Agenda citas, registra consultas y completa atenciones para ver tu dashboard.
      </p>
      <button
        className="btn btn-primary btn-md"
        onClick={() => navigate("/appointments")}
        style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}
      >
        <Icon.CalendarClock s={15} />
        Agendar primera cita
      </button>
    </div>
  );
};

export default EmptyDashboard;
