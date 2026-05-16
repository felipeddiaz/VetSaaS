import { AnimatePresence, motion } from "framer-motion";
import { Icon } from "../../components/icons";
import styles from "./medicalRecords.module.css";

const MONTHS = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];

const truncate = (t, n) => (!t ? "" : t.length > n ? t.slice(0, n) + "…" : t);

const getVetName = (r) => {
  const v = r.veterinarian;
  if (!v) return null;
  return [v.first_name, v.last_name].filter(Boolean).join(" ") || v.username || null;
};

const TimelineCard = ({
  record, typeMeta, isExpanded, onToggle,
  onClose, onEdit, onDelete,
  onCreatePrescription, onDownloadPrescription,
  onDownloadRecordPdf, downloadingRecordPdfId,
  downloadingPrescriptionId, user, canCreate,
}) => {
  const d        = new Date(record.latest_vitals?.recorded_at || record.created_at);
  const dateStr  = `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  const vetName  = getVetName(record);
  const isClosed = record.status === "closed";
  const hasPrx   = !!record.prescription_summary?.id;
  const vitals   = record.latest_vitals;
  const userRole = user?.role;
  const canEdit  = record.can_modify_charges;
  const canClose = record.can_close;
  const canDel   = !!record.can_delete;

  const hasExpandable = !!(
    record.notes ||
    record.products_used?.length > 0 ||
    (hasPrx && record.prescription_summary?.items?.length > 0)
  );
  const canDownloadRecord = !!record.public_id;
  const hasActions = hasPrx || canDownloadRecord || (!hasPrx && !isClosed && canCreate) || canEdit || canClose || canDel;

  return (
    <article
      className={`${styles.txCard} ${isExpanded ? styles.txCardOpen : ""}`}
      style={{ "--tx-color": typeMeta.color, "--tx-soft": typeMeta.soft || "#f0f9f4" }}
    >
      {/* ── Header: tipo · fecha · vet | badges · chevron ── */}
      <div
        className={`${styles.txHead} ${hasExpandable ? styles.txHeadClickable : ""}`}
        onClick={() => hasExpandable && onToggle?.()}
      >
        <div className={styles.txHeadLeft}>
          <span
            className={styles.txTypePill}
            style={{ color: typeMeta.color, background: typeMeta.soft || "var(--c-subtle)" }}
          >
            {typeMeta.label}
          </span>
          <span className={styles.txDate}>{dateStr}</span>
          {vetName && <span className={styles.txVet}>· Dr. {vetName}</span>}
        </div>

        <div className={styles.txHeadRight}>
          <span className={isClosed ? styles.txBadgeClosed : styles.txBadgeOpen}>
            {isClosed ? "Cerrada" : "Abierta"}
          </span>
          {hasPrx && (
            <span className={styles.txBadgeGreen}>
              <Icon.Pill s={10} /> Receta
            </span>
          )}
          {record.invoice_status && (
            <span className={styles.txBadgeBlue}>
              <Icon.Receipt s={10} /> Cobro
            </span>
          )}
          {hasExpandable && (
            <button
              className={styles.txToggle}
              onClick={(e) => { e.stopPropagation(); onToggle?.(); }}
              title={isExpanded ? "Ocultar detalles" : "Ver notas y más"}
            >
              {isExpanded ? <Icon.ChevronUp s={14} /> : <Icon.ChevronDown s={14} />}
            </button>
          )}
        </div>
      </div>

      {/* ── Contenido principal: diagnóstico · tratamiento · vitales ── */}
      <div className={styles.txContent}>
        <p className={styles.txDiagnosis}>
          {record.diagnosis
            ? truncate(record.diagnosis, 180)
            : <span className={styles.txNone}>Sin diagnóstico registrado</span>}
        </p>

        {record.treatment && (
          <p className={styles.txTreatment}>{truncate(record.treatment, 130)}</p>
        )}

        {vitals && (
          <div className={styles.txVitals}>
            {vitals.weight        != null && <span><Icon.ArrowUp s={10} /> {Number(vitals.weight).toFixed(1)} kg</span>}
            {vitals.temperature   != null && <span><Icon.Activity s={10} /> {Number(vitals.temperature).toFixed(1)} °C</span>}
            {vitals.heart_rate    != null && <span><Icon.Heart s={10} /> FC {vitals.heart_rate}</span>}
            {vitals.respiratory_rate != null && <span>FR {vitals.respiratory_rate}</span>}
          </div>
        )}
      </div>

      {/* ── Acciones — siempre visibles ── */}
      {hasActions && (
        <div className={styles.txFooter}>
          {hasPrx && (
            <button
              className={styles.txBtn}
              disabled={downloadingPrescriptionId === record.prescription_summary.public_id}
              onClick={(e) => { e.stopPropagation(); onDownloadPrescription?.(record.prescription_summary.public_id); }}
            >
              {downloadingPrescriptionId === record.prescription_summary.public_id
                ? <Icon.Loader s={13} /> : <Icon.Download s={13} />}
              Descargar receta
            </button>
          )}
          {canDownloadRecord && (
            <button
              className={styles.txBtn}
              disabled={downloadingRecordPdfId === record.public_id}
              onClick={(e) => { e.stopPropagation(); onDownloadRecordPdf?.(record.public_id); }}
            >
              {downloadingRecordPdfId === record.public_id
                ? <Icon.Loader s={13} /> : <Icon.Download s={13} />}
              Descargar PDF resumen
            </button>
          )}
          {!hasPrx && !isClosed && canCreate && (
            <button
              className={styles.txBtn}
              onClick={(e) => { e.stopPropagation(); onCreatePrescription?.(); }}
            >
              <Icon.Pill s={13} /> Nueva receta
            </button>
          )}
          {canEdit && (
            <button
              className={styles.txBtn}
              onClick={(e) => { e.stopPropagation(); onEdit?.(); }}
            >
              <Icon.Edit s={13} /> Editar
            </button>
          )}
          {canClose && (
            <button
              className={styles.txBtn}
              onClick={(e) => { e.stopPropagation(); onClose?.(); }}
            >
              <Icon.CheckCircle s={13} /> Finalizar
            </button>
          )}
          {canDel && (
            <button
              className={`${styles.txBtn} ${styles.txBtnDanger}`}
              onClick={(e) => { e.stopPropagation(); onDelete?.(); }}
            >
              <Icon.Trash s={13} /> Eliminar
            </button>
          )}
        </div>
      )}

      {/* ── Expand: notas · productos · receta (sin repetir diagnóstico) ── */}
      <AnimatePresence initial={false}>
        {isExpanded && hasExpandable && (
          <motion.div
            className={styles.txExpanded}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className={styles.txExpandedInner}>
              {record.notes && (
                <div className={styles.txSection}>
                  <p className={styles.txLabel}>Notas clínicas</p>
                  <p className={styles.txText}>{record.notes}</p>
                </div>
              )}
              {record.products_used?.length > 0 && (
                <div className={styles.txSection}>
                  <p className={styles.txLabel}>Productos utilizados</p>
                  <div className={styles.txChips}>
                    {record.products_used.map((p, i) => (
                      <span key={i} className={styles.txChip}>
                        {p.product_name} · {p.quantity} {p.base_unit_display || ""}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {hasPrx && record.prescription_summary.items?.length > 0 && (
                <div className={styles.txSection}>
                  <p className={styles.txLabel}>Medicamentos recetados</p>
                  <div className={styles.txPrxList}>
                    {record.prescription_summary.items.map((item, i) => (
                      <div key={i} className={styles.txPrxRow}>
                        <span className={styles.txPrxName}>{item.product_name}</span>
                        <div className={styles.txPrxMeta}>
                          {item.dose     && <span>{item.dose}</span>}
                          {item.duration && <span>{item.duration}</span>}
                          {item.quantity && <span>×{item.quantity}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </article>
  );
};

export default TimelineCard;
