import { useMemo } from "react";
import { Icon } from "../../components/icons";
import TimelineCard from "./TimelineCard";
import styles from "./medicalRecords.module.css";

const TYPE_META = {
  general:   { color: "#2563eb", soft: "#eff6ff", label: "Consulta general" },
  vaccine:   { color: "#16a34a", soft: "#f0fdf4", label: "Vacunación"        },
  surgery:   { color: "#dc2626", soft: "#fef2f2", label: "Cirugía"           },
  emergency: { color: "#ea580c", soft: "#fff7ed", label: "Urgencia"          },
};

const MONTHS = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];
const getDate = (r) => r.latest_vitals?.recorded_at || r.created_at;

const Timeline = ({
  records, expandedId, onToggleExpand,
  onCloseRecord, onEdit, onDelete,
  onCreatePrescription, onDownloadPrescription,
  downloadingPrescriptionId, user, canCreate,
}) => {
  const groups = useMemo(() => {
    if (!records?.length) return [];
    const sorted = [...records].sort((a, b) => new Date(getDate(b)) - new Date(getDate(a)));
    const map = new Map();
    sorted.forEach(r => {
      const d = new Date(getDate(r));
      const key = `${d.getFullYear()}-${d.getMonth()}`;
      if (!map.has(key)) map.set(key, { year: d.getFullYear(), month: d.getMonth(), records: [] });
      map.get(key).records.push(r);
    });
    const yearMap = new Map();
    map.forEach(g => {
      if (!yearMap.has(g.year)) yearMap.set(g.year, []);
      yearMap.get(g.year).push(g);
    });
    return Array.from(yearMap.entries())
      .sort(([a], [b]) => b - a)
      .map(([year, months]) => ({ year, months: months.sort((a, b) => b.month - a.month) }));
  }, [records]);

  if (!records?.length) {
    return (
      <div className={styles.emptyCenter}>
        <div className={styles.emptyIconWrap}><Icon.FileHeart s={32} /></div>
        <p className={styles.emptyTitle}>Sin consultas registradas</p>
        <p className={styles.emptySub}>El historial aparecerá aquí al registrar la primera consulta.</p>
      </div>
    );
  }

  return (
    <div className={styles.txList}>
      {groups.map(({ year, months }) => (
        <section key={year} className={styles.txYearSection}>
          <div className={styles.txYearHeader}>
            <span className={styles.txYearLabel}>{year}</span>
            <span className={styles.txYearLine} />
            <span className={styles.txYearCount}>
              {months.reduce((s, m) => s + m.records.length, 0)} consulta{months.reduce((s,m)=>s+m.records.length,0)!==1?"s":""}
            </span>
          </div>

          {months.map(({ month, records: mRecs }) => (
            <div key={month} className={styles.txMonthGroup}>
              <p className={styles.txMonthLabel}>{MONTHS[month]}</p>
              <div className={styles.txCards}>
                {mRecs.map(record => {
                  const meta = TYPE_META[record.consultation_type] || TYPE_META.general;
                  return (
                    <TimelineCard
                      key={record.public_id}
                      record={record}
                      typeMeta={meta}
                      isExpanded={expandedId === record.public_id}
                      onToggle={() => onToggleExpand(expandedId === record.public_id ? null : record.public_id)}
                      onClose={() => onCloseRecord(record)}
                      onEdit={() => onEdit(record)}
                      onDelete={() => onDelete(record.public_id)}
                      onCreatePrescription={() => onCreatePrescription(record)}
                      onDownloadPrescription={onDownloadPrescription}
                      downloadingPrescriptionId={downloadingPrescriptionId}
                      user={user}
                      canCreate={canCreate}
                    />
                  );
                })}
              </div>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
};

export default Timeline;
