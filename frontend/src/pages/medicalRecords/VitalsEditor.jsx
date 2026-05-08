import { useState, useRef, useEffect, useCallback } from "react";
import { createVitals } from "../../api/vitals";
import { toast } from "sonner";
import styles from "./vitals.module.css";

const VitalsEditor = ({ recordId, field, value, label, unit, onSaved }) => {
  const timerRef = useRef(null);
  const localValueRef = useRef("");

  const [editing, setEditing] = useState(false);
  const [localValue, setLocalValue] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    localValueRef.current = localValue;
  }, [localValue]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const doSave = useCallback(async (val) => {
    const trimmed = val.trim();
    let valueOrNull = null;
    if (trimmed !== "") {
      const num = Number(trimmed);
      if (isNaN(num)) {
        toast.error(`Valor inválido para ${label}`);
        return;
      }
      if (field === "weight" && num < 0.01) {
        toast.error("El peso debe ser mayor a 0.01 kg");
        return;
      }
      if (num < 0) {
        toast.error(`El valor de ${label} no puede ser negativo`);
        return;
      }
      valueOrNull = num;
    }
    setSaving(true);
    try {
      await createVitals(recordId, { [field]: valueOrNull });
      if (onSaved) onSaved();
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || `Error al guardar ${label}`;
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }, [recordId, field, label, onSaved]);

  const flush = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
      const currentVal = localValueRef.current;
      if (currentVal !== String(value ?? "")) {
        doSave(currentVal);
      }
    }
  }, [doSave, value]);

  const scheduleSave = useCallback((val) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      doSave(val);
    }, 600);
  }, [doSave]);

  const handleClick = () => {
    if (!recordId) return;
    setEditing(true);
    setLocalValue(value != null ? String(value) : "");
  };

  const handleChange = (e) => {
    const val = e.target.value;
    setLocalValue(val);
    scheduleSave(val);
  };

  const handleBlur = () => {
    flush();
    setEditing(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      e.target.blur();
    }
    if (e.key === "Escape") {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
      setEditing(false);
      setLocalValue(value != null ? String(value) : "");
    }
  };

  const isInteger = field === "heart_rate" || field === "respiratory_rate";
  const step = isInteger ? "1" : "0.01";

  if (editing) {
    return (
      <div
        className={`${styles.vitalField} ${styles.vitalEditing} ${saving ? styles.vitalSaving : ""}`}
      >
        <span className={styles.vitalLabel}>{label}:</span>
        <input
          className={styles.vitalInput}
          type="number"
          step={step}
          min="0"
          value={localValue}
          onChange={handleChange}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          autoFocus
        />
        <span className={styles.vitalLabel}>{unit}</span>
      </div>
    );
  }

  return (
    <div
      className={styles.vitalField}
      onClick={handleClick}
      style={!recordId ? { cursor: "default" } : undefined}
    >
      <span className={styles.vitalLabel}>{label}:</span>
      {value != null ? (
        <span className={styles.vitalValue}>
          {value} {unit}
        </span>
      ) : (
        <span className={`${styles.vitalValue} ${styles.vitalNull}`}>—</span>
      )}
    </div>
  );
};

export default VitalsEditor;
