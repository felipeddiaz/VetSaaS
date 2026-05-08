import { Icon } from "../../components/icons";
import styles from "./medicalRecords.module.css";

const SPECIES_DOG = /perro|can[ei]|dog/i;
const SPECIES_CAT = /gato|fel[iy]|cat/i;

const getSpeciesBg = (species) => {
  if (!species) return "#f5f5f5";
  if (SPECIES_DOG.test(species)) return "#e8f5e9";
  if (SPECIES_CAT.test(species)) return "#fce4ec";
  return "#f5f5f5";
};

const getSpeciesIcon = (species, size = 24) => {
  if (!species) return <Icon.Paw s={size} />;
  if (SPECIES_DOG.test(species)) return <Icon.Dog s={size} />;
  if (SPECIES_CAT.test(species)) return <Icon.Cat s={size} />;
  return <Icon.Paw s={size} />;
};

const getAge = (birthDate) => {
  if (!birthDate) return null;
  const today = new Date();
  const birth = new Date(birthDate);
  let years = today.getFullYear() - birth.getFullYear();
  const m = today.getMonth() - birth.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) years--;
  return years;
};

const VITAL_FIELDS = [
  { field: "weight", label: "Peso", unit: "kg" },
  { field: "temperature", label: "Temp", unit: "°C", alertThreshold: 39.5 },
  { field: "heart_rate", label: "FC", unit: "bpm" },
  { field: "respiratory_rate", label: "FR", unit: "rpm" },
];

const PatientHeader = ({ pet, latestVitals, noPadding = false }) => {
  const species = (pet?.species || "").toLowerCase();
  const age = getAge(pet?.birth_date);

  const getValue = (vf) => {
    if (!latestVitals) return null;
    return latestVitals[vf.field] ?? null;
  };

  return (
    <div className={noPadding ? "" : styles.patientHeader}>
      <div className={styles.patientInfo}>
        <div className={styles.patientIcon} style={{ background: getSpeciesBg(species) }}>
          {getSpeciesIcon(species, 28)}
        </div>
        <div>
          <h1 className={styles.patientName}>{pet?.name ?? "—"}</h1>
          <div className={styles.patientMeta}>
            {pet?.species || "—"}
            {pet?.breed && <span> · {pet.breed}</span>}
            {age != null && <span> · {age} año{age !== 1 ? "s" : ""}</span>}
          </div>
        </div>
      </div>

      <div className={styles.vitalsBar}>
        <span className={styles.vitalsTitle}>Ultimos signos vitales registrados</span>
        {VITAL_FIELDS.map((vf) => (
          <div className={styles.vitalItem} key={vf.field}>
            <span className={styles.vitalLabel}>{vf.label}:</span>
            {getValue(vf) != null ? (
              <span className={styles.vitalValue}>
                {getValue(vf)} {vf.unit}
              </span>
            ) : (
              <span className={styles.vitalNullValue}>—</span>
            )}
            {vf.alertThreshold && getValue(vf) != null && getValue(vf) >= vf.alertThreshold && (
              <Icon.AlertTriangle s={14} c="#ef4444" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default PatientHeader;
