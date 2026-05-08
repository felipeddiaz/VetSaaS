import { useEffect, useState } from "react";
import { Icon } from "../../components/icons";
import { getSummary } from "../../api/vitals";
import { toast } from "sonner";
import styles from "./panel.module.css";

const CONSULTATION_TYPE_LABELS = {
  general: "General",
  vaccine: "Vacuna",
  surgery: "Cirugía",
  emergency: "Urgencia",
};

const INVOICE_STATUS_LABELS = {
  draft: "Borrador",
  confirmed: "Confirmada",
  paid: "Pagada",
  cancelled: "Cancelada",
};

const getAge = (birthDate) => {
  if (!birthDate) return null;
  const now = new Date();
  const birth = new Date(birthDate);
  let years = now.getFullYear() - birth.getFullYear();
  let months = now.getMonth() - birth.getMonth();
  if (months < 0) {
    years--;
    months += 12;
  }
  return `${years} años, ${months} meses`;
};

const formatCurrency = (num) => {
  if (num == null) return "$0.00";
  return `\$${Number(num).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const formatDate = (ds) => {
  if (!ds) return null;
  return new Date(ds).toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" });
};

const getStatusBadgeStyle = (status) => {
  if (status === "open") {
    return { color: "var(--c-info-text)", background: "var(--c-info-bg)" };
  }
  return { color: "var(--c-text-3)", background: "var(--c-subtle)" };
};

const getInvoiceStatusBadgeStyle = (status) => {
  switch (status) {
    case "paid":
      return { color: "var(--c-success-text)", background: "var(--c-success-bg)" };
    case "confirmed":
      return { color: "var(--c-info-text)", background: "var(--c-info-bg)" };
    case "cancelled":
      return { color: "var(--c-danger-text)", background: "var(--c-danger-bg)" };
    case "draft":
    default:
      return { color: "var(--c-warning-text)", background: "var(--c-warning-bg)" };
  }
};

const getConsultationTypeStyle = (type) => {
  switch (type) {
    case "emergency":
      return { color: "var(--c-danger-text)", background: "var(--c-danger-bg)" };
    case "surgery":
      return { color: "var(--c-purple-text)", background: "var(--c-purple-bg)" };
    case "vaccine":
      return { color: "var(--c-warning-text)", background: "var(--c-warning-bg)" };
    case "general":
    default:
      return { color: "var(--c-success-text)", background: "var(--c-success-bg)" };
  }
};

const Skeleton = () => (
  <div className={styles.panelLoading}>
    <div style={{ height: 14, background: "var(--c-subtle)", borderRadius: 4, marginBottom: 10, width: "60%" }} />
    <div style={{ height: 12, background: "var(--c-subtle)", borderRadius: 4, marginBottom: 12, width: "80%" }} />
    <div style={{ height: 12, background: "var(--c-subtle)", borderRadius: 4, marginBottom: 6, width: "40%" }} />
    <div style={{ height: 12, background: "var(--c-subtle)", borderRadius: 4, marginBottom: 6, width: "50%" }} />
    <div style={{ height: 12, background: "var(--c-subtle)", borderRadius: 4, marginBottom: 12, width: "70%" }} />
    <div style={{ height: 10, background: "var(--c-subtle)", borderRadius: 4, width: "90%" }} />
  </div>
);

const SidePanel = ({ recordId, pet, refreshKey = 0, compact = false }) => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!recordId) {
      setSummary(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    getSummary(recordId)
      .then((data) => {
        if (cancelled) return;
        setSummary(data);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg = err?.response?.data?.detail || err?.message || "Error al cargar resumen";
        setError(msg);
        setLoading(false);
        toast.error(msg);
      });

    return () => { cancelled = true; };
  }, [recordId, refreshKey]);

  if (!recordId && !pet) {
    return (
      <aside className={`${styles.panel} ${compact ? styles.panelCompact : ''}`}>
        <div className={styles.panelSection}>
          <div className={styles.panelSectionTitle}>Paciente</div>
        </div>
        <p className={styles.panelEmpty}>Selecciona una mascota</p>
      </aside>
    );
  }

  if (!recordId && pet) {
    return (
      <aside className={`${styles.panel} ${compact ? styles.panelCompact : ''}`}>
        <div className={styles.panelSection}>
          <div className={styles.panelSectionTitle}>Paciente</div>
          <p className={styles.panelText}>
            <strong>{pet.name}</strong>
            <br />
            {pet.species}{pet.breed ? ` · ${pet.breed}` : ""}
            {pet.birth_date && <><br />{getAge(pet.birth_date)}</>}
          </p>
        </div>
      </aside>
    );
  }

  if (loading) {
    return (
      <aside className={`${styles.panel} ${compact ? styles.panelCompact : ''}`}>
        <div className={styles.panelSection}>
          <div className={styles.panelSectionTitle}>Resumen clínico</div>
        </div>
        <Skeleton />
      </aside>
    );
  }

  if (error && !summary) {
    return (
      <aside className={`${styles.panel} ${compact ? styles.panelCompact : ''}`}>
        <div className={styles.panelSection}>
          <div className={styles.panelSectionTitle}>Resumen clínico</div>
        </div>
        <p className={styles.panelEmpty}>Error al cargar el resumen</p>
      </aside>
    );
  }

  if (!summary) return null;

  const patient = summary.patient;
  const vitals = summary.last_vitals;
  const totals = summary.totals;

  return (
    <aside className={`${styles.panel} ${compact ? styles.panelCompact : ''}`}>
      {compact && (
        <div className={styles.panelSection}>
          <div className={styles.panelSectionTitle}>Paciente</div>
          <p className={styles.panelText}>
            <strong>{patient?.name}</strong>
            <br />
            {patient?.species}{patient?.breed ? ` · ${patient.breed}` : ""}
            {patient?.birth_date && <><br />{getAge(patient.birth_date)}</>}
          </p>
        </div>
      )}

      {!compact && (
        <div className={styles.panelSection}>
          <div className={styles.panelSectionTitle}>Resumen clínico</div>
        </div>
      )}

      {!compact && (
        <div className={styles.panelSection}>
          <div className={styles.panelSectionTitle}>Paciente</div>
          <p className={styles.panelText}>
            <strong>{patient?.name}</strong>
            <br />
            {patient?.species}{patient?.breed ? ` · ${patient.breed}` : ""}
            {patient?.birth_date && <><br />{getAge(patient.birth_date)}</>}
          </p>
        </div>
      )}

      <div className={styles.panelSection}>
        <div className={styles.panelSectionTitle}>Últimos signos vitales</div>
        {vitals?.has_vitals ? (
          <>
            {vitals.weight != null && (
              <div className={styles.panelVitalRow}>
                <span className={styles.panelVitalLabel}>Peso</span>
                <span className={styles.panelVitalValue}>{Number(vitals.weight).toFixed(2)} kg</span>
              </div>
            )}
            {vitals.temperature != null && (
              <div className={styles.panelVitalRow}>
                <span className={styles.panelVitalLabel}>Temperatura</span>
                <span className={styles.panelVitalValue}>{Number(vitals.temperature).toFixed(1)} °C</span>
              </div>
            )}
            {vitals.heart_rate != null && (
              <div className={styles.panelVitalRow}>
                <span className={styles.panelVitalLabel}>Frec. cardíaca</span>
                <span className={styles.panelVitalValue}>{vitals.heart_rate} bpm</span>
              </div>
            )}
            {vitals.respiratory_rate != null && (
              <div className={styles.panelVitalRow}>
                <span className={styles.panelVitalLabel}>Frec. respiratoria</span>
                <span className={styles.panelVitalValue}>{vitals.respiratory_rate} rpm</span>
              </div>
            )}
            {vitals.recorded_at && (
              <p className={styles.panelText} style={{ fontSize: 11, marginTop: 4 }}>
                {formatDate(vitals.recorded_at)}
              </p>
            )}
          </>
        ) : (
          <p className={styles.panelEmpty}>Sin signos vitales registrados</p>
        )}
      </div>

      <div className={styles.panelSection}>
        <div className={styles.panelSectionTitle}>Diagnóstico</div>
        <p className={styles.panelText}>
          {summary.diagnosis || <span className={styles.panelEmpty}>Sin diagnóstico</span>}
        </p>
      </div>

      <div className={styles.panelSection}>
        <div className={styles.panelSectionTitle}>Estado</div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <span className={styles.panelBadge} style={getConsultationTypeStyle(summary.consultation_type)}>
            {CONSULTATION_TYPE_LABELS[summary.consultation_type] || summary.consultation_type}
          </span>
          <span className={styles.panelBadge} style={getStatusBadgeStyle(summary.status)}>
            {summary.status === "open" ? "Abierta" : "Cerrada"}
          </span>
        </div>
      </div>

      <div className={styles.panelSection}>
        <div className={styles.panelSectionTitle}>Facturación</div>
        {totals ? (
          <>
            <div className={styles.panelVitalRow}>
              <span className={styles.panelVitalLabel}>Subtotal</span>
              <span className={styles.panelVitalValue}>{formatCurrency(totals.subtotal)}</span>
            </div>
            <div className={styles.panelVitalRow}>
              <span className={styles.panelVitalLabel}>Impuesto</span>
              <span className={styles.panelVitalValue}>{formatCurrency(totals.tax_amount)}</span>
            </div>
            <div className={styles.panelVitalRow}>
              <span className={styles.panelVitalLabel}>Total</span>
              <span className={styles.panelVitalValue}>{formatCurrency(totals.total)}</span>
            </div>
            <div style={{ marginTop: 4 }}>
              <span className={styles.panelBadge} style={getInvoiceStatusBadgeStyle(totals.status)}>
                {INVOICE_STATUS_LABELS[totals.status] || totals.status}
              </span>
            </div>
          </>
        ) : (
          <p className={styles.panelEmpty}>Sin factura</p>
        )}
      </div>

      <div className={styles.panelSection}>
        <div className={styles.panelSectionTitle}>Próxima vacuna</div>
        <p className={styles.panelText}>
          {summary.next_vaccine_date ? formatDate(summary.next_vaccine_date) : "Sin pendientes"}
        </p>
      </div>
    </aside>
  );
};

export default SidePanel;
