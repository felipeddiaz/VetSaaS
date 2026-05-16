import styles from "./KpiStrip.module.css";

function formatValue(item) {
  const v = item.value;
  if (v == null) return "—";
  if (item.format === "currency") {
    return `$${Number(v).toLocaleString("es-MX")}`;
  }
  return v;
}

const TONE_CLASS = {
  default: styles.numberDefault,
  warning: styles.numberWarning,
  danger:  styles.numberDanger,
};

export default function KpiStrip({ items }) {
  if (!items || items.length === 0) return null;

  return (
    <div className={styles.strip}>
      {items.map((item, i) => {
        const isLast  = i === items.length - 1;
        const isZero  = item.value == null || Number(item.value) === 0;
        const toneKey = isZero ? "default" : (item.tone || "default");
        const numberClass = `${styles.number} ${TONE_CLASS[toneKey] || styles.numberDefault}`;
        const blockClass  = isLast
          ? `${styles.block} ${styles.blockLast}`
          : styles.block;

        return (
          <div key={item.label} className={blockClass}>
            <span className={numberClass}>{formatValue(item)}</span>
            <span className={styles.label}>{item.label}</span>
            {item.live && (
              <span className={styles.pill}>
                <span className={styles.pillDot} />
                en vivo
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
