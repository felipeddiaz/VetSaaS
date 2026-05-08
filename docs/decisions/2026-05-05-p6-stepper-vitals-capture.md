# ADR: Captura de signos vitales en Stepper Paso 2

**Fecha**: 2026-05-05  
**Estado**: Implementado

## Contexto

Los signos vitales (peso, temperatura, frecuencia cardíaca, frecuencia respiratoria) son datos clínicos esenciales que se capturan durante la consulta. Originalmente:

1. El `PatientHeader` mostraba los vitales con `VitalsEditor` — inputs inline que guardaban automáticamente al escribir
2. El stepper NO tenía un paso para vitales
3. Los vitales solo podían capturarse **después** de crear la consulta, haciendo clic en la barra de vitales

## Problemas identificados

### 1. Vitals nunca se capturaban en la práctica

`VitalsEditor` requiere `recordId` no-nulo para editar. Pero `activeRecordId` en el orquestador solo se setea cuando:
- El usuario hace clic en una card del timeline
- O hace clic en "Editar" en una card expandida

**Flujo roto**:
```
1. Usuario crea consulta vía stepper
2. Stepper completa → no propaga recordId al orquestador
3. activeRecordId = null
4. PatientHeader vitales → no editables (handleClick retorna temprano)
5. Usuario ve "—" en todos los vitales, no puede capturar
```

### 2. "Sin consulta activa" siempre mostrado

El `SidePanel` muestra "Sin consulta activa" cuando `activeRecordId` es null. Como el stepper nunca propagaba su `recordId` local, el panel permanecía en estado vacío incluso después de crear una consulta exitosamente.

### 3. Dueño "no registrado" siempre

`PatientHeader` leía `pet.owner_name`, pero la API devuelve `pet.owner.name` (anidado). Resultado: `pet.owner_name` es siempre `undefined` → el fallback hardcodeado "Dueño no registrado" se muestra siempre, incluso si la mascota tiene dueño registrado.

## Decisiones implementadas

### 1. Stepper Paso 2: Grid de signos vitales

Se agregó un grid de 4 campos en el Paso 2 del stepper, **antes** del textarea de tratamiento:

```jsx
<div className={styles.vitalsGrid}>
  {[
    { field: "weight", label: "Peso (kg)", step: "0.01", min: "0.01", max: "200" },
    { field: "temperature", label: "Temperatura (°C)", step: "0.1", min: "30", max: "45" },
    { field: "heart_rate", label: "Frec. Cardíaca (bpm)", step: "1", min: "1", max: "300" },
    { field: "respiratory_rate", label: "Frec. Respiratoria (rpm)", step: "1", min: "1", max: "100" },
  ].map(v => (
    <div className={styles.vitalInputGroup} key={v.field}>
      <label>{v.label}</label>
      <input type="number" ... />
    </div>
  ))}
</div>
```

**Helper de conversión segura**:
```javascript
const toNumberOrNull = (v) => {
    if (v === "" || v == null) return null;
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
};
```

Esto maneja casos edge como `" "` (espacios) → `null`, `"0"` → `0` (válido).

### 2. Orden de escritura: record primero, vitales después

En `goNext(fromStep=2)`:

```javascript
// 1) PATCH del registro clínico (sin weight en step 2 — peso vive en VitalSigns)
const payload = {
    pet: pet.id,
    consultation_type: draft.consultation_type,
    diagnosis: draft.diagnosis,
    treatment: draft.treatment,
    notes: draft.notes,
};
if (fromStep !== 2) {
    payload.weight = toNumberOrNull(draft.weight);
}
await updateMedicalRecord(token, recordId, payload);

// 2) Signos vitales — solo step 2, solo si algún campo fue llenado
if (fromStep === 2) {
    const vitalFields = ["weight", "temperature", "heart_rate", "respiratory_rate"];
    const hasVitals = vitalFields.some(f => draft[f] !== "" && draft[f] != null);
    if (hasVitals) {
        await createVitals(recordId, {
            weight: toNumberOrNull(draft.weight),
            temperature: toNumberOrNull(draft.temperature),
            heart_rate: toNumberOrNull(draft.heart_rate),
            respiratory_rate: toNumberOrNull(draft.respiratory_rate),
        });
    }
}
```

**Razones**:
- Si el `updateMedicalRecord` falla, los vitales no se guardan (consistencia)
- `weight` no se envía en `updateMedicalRecord` desde step 2 — la fuente de verdad es `VitalSigns.weight`
- `hasVitals` usa `!== ""` en lugar de truthiness para no rechazar `"0"`

### 3. Stepper propaga `recordId` al orquestador

En `ConsultationStepper.jsx`:
```javascript
// handleCloseRecord
onComplete?.(recordId);
onClose?.(recordId);
```

En `index.jsx` (orquestador):
```javascript
const handleStepperComplete = async (recordId) => {
    setShowStepper(false);
    setEditingRecord(null);
    setActiveRecordId(recordId);  // ← propaga al orquestador
    await loadRecords();
    await loadAllData();
    setPanelRefreshKey(k => k + 1);
};

const handleStepperClose = async (recordId) => {
    setShowStepper(false);
    setEditingRecord(null);
    setActiveRecordId(recordId);  // ← propaga al orquestador
    await loadRecords();
    await loadAllData();
    setPanelRefreshKey(k => k + 1);
};
```

**Efecto**: Al cerrar el stepper, `activeRecordId` se setea → `PatientHeader` recibe `recordId` no-nulo → vitales editables (si se dejara inline) → `SidePanel` muestra summary.

### 4. PatientHeader: Solo lectura con título explícito

Se eliminó `VitalsEditor` del `PatientHeader`. Ahora es display estático:

```jsx
<div className={styles.vitalsBar}>
    <span className={styles.vitalsTitle}>Signos vitales (última consulta)</span>
    {VITAL_FIELDS.map((vf, i) => (
        <div className={styles.vitalItem} key={vf.field}>
            {i > 0 && SEPARATOR}
            <span className={styles.vitalLabel}>{vf.label}:</span>
            {getValue(vf) != null ? (
                <span className={styles.vitalValue}>{getValue(vf)} {vf.unit}</span>
            ) : (
                <span className={styles.vitalNullValue}>—</span>
            )}
            {/* alertThreshold icon si aplica */}
        </div>
    ))}
</div>
```

**Props eliminadas**: `recordId`, `onVitalsSaved`, `refreshKey` — ya no se usan.

**Título explícito**: "Signos vitales (última consulta)" deja claro que son datos históricos, no editables en este contexto.

### 5. Owner name: `pet.owner?.name` en lugar de `pet.owner_name`

En `PatientHeader.jsx`:
```jsx
const ownerName = pet?.owner?.name?.trim();
return ownerName ? (
    <div className={styles.patientMeta}>Dueño: {ownerName}</div>
) : (
    <div className={styles.patientMeta} style={{ color: "var(--c-text-4)", fontStyle: "italic" }}>
        Dueño no registrado
    </div>
);
```

En `PetSidebar.jsx` (filtro de búsqueda):
```jsx
p.owner?.name?.toLowerCase().includes(q)
// antes: p.owner_name?.toLowerCase().includes(q)
```

### 6. Edición: merge de `latest_vitals` con fallback a `record.weight`

En el `useState` del stepper (modo edición):
```javascript
const [draft, setDraft] = useState(() => {
    if (isEditing) {
        const v = initialRecord.latest_vitals || {};
        return {
            // ...
            weight: v.weight ?? initialRecord.weight ?? "",
            temperature: v.temperature != null ? String(v.temperature) : "",
            heart_rate: v.heart_rate != null ? String(v.heart_rate) : "",
            respiratory_rate: v.respiratory_rate != null ? String(v.respiratory_rate) : "",
        };
    }
    return { ...INITIAL_DRAFT };
});
```

**Razón**: `latest_vitals` es la fuente de verdad para signos vitales. `MedicalRecord.weight` es legacy (coexistencia v1). El fallback preserva datos históricos si no hay vitales.

## Flujo actual

```
1. "+ Nueva Consulta" → stepper abre
2. Paso 1 (Diagnóstico) → POST /medical-records/ → recordId creado
3. Paso 2 (Signos Vitales + Tratamiento)
   • Usuario llena grid de 4 vitales
   • Usuario llena tratamiento
   • Click "Siguiente"
   • PATCH /medical-records/{id}/ (sin weight)
   • POST /medical-records/{id}/vitals/ (si hay campos llenos)
4. Paso 3 (Productos) → ...
5. Paso 4 (Facturación) → Cerrar
6. Stepper cierra → setActiveRecordId(recordId) → SidePanel muestra summary
```

## Alternativas consideradas

### A: Mantener VitalsEditor inline en PatientHeader
**Rechazado**: Requería que el usuario hiciera clic en la card del timeline primero. La mayoría de usuarios no lo hacía → vitales nunca capturados.

### B: Agregar paso exclusivo de vitales (Paso 2, mover tratamiento a Paso 3)
**Considerado**: Más pasos = más fricción. Se decidió integrar vitales en el mismo Paso 2 junto con tratamiento.

### C: Auto-guardado de vitales en background mientras se escribe
**Rechazado**: Complejidad innecesaria. El usuario confirma al avanzar al siguiente paso.

## Deuda técnica

Ninguna. La captura de vitales en el stepper es el flujo clínico natural: se miden signos vitales **durante** la consulta, no después.

## Relación con otros ADRs

- **ADR-01** (No refactor de módulos en v1): Fix en el stepper, sin tocar modelos.
- **ADR-03** (Constantes para OrganizationSettings): Ídem — fix quirúrgico.
- **P3 ADR** (VitalSigns append-only): Los vitales del stepper son el primer registro de ese append-only log.
