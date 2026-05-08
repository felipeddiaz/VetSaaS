# ADR: Hardening UX frontend P2

**Fecha**: 2026-05-02  
**Estado**: Implementado

## Contexto

Tras P1 (logica de negocio backend), P2 audito la capa frontend para:
- Evitar acciones duplicadas por doble click o Enter repetido
- Garantizar que los IDs usados en llamadas a la API sean los correctos (public_id UUID, no PK entero)
- Unificar el patron de confirmacion de acciones destructivas
- Completar los estados de carga en formularios que quedaron incompletos

## Hallazgos y decisiones

### 1. billing.jsx usaba el PK entero en todas las llamadas de items (bug critico)

**Problema**: Todos los calls a `confirmInvoice`, `payInvoice`, `addInvoiceItem`, `deleteInvoiceItem`, `updateInvoice` y `getInvoice` pasaban `selectedInvoice.id` (entero). Tras P1, las rutas de items migraron a `<str:invoice_pk>` con `resolve_public_id()`. Con `ALLOW_LEGACY_ID_LOOKUP=False` (default en codigo), estas llamadas retornaban 404.

**Decision**: Reemplazar todos los argumentos de invoice en llamadas a la API por `invoice.public_id` / `selectedInvoice.public_id` (UUID). El display visual `Cobro #${selectedInvoice.id}` conserva el entero como numero de referencia para el usuario — no es una URL, no es un riesgo de seguridad.

Archivos afectados: `src/pages/billing.jsx` (11 reemplazos).

**Regla derivada**: Al agregar nuevas llamadas a la API de facturas, usar siempre `invoice.public_id`, nunca `invoice.id`.

---

### 2. Tres formularios sin proteccion contra doble submit

**Problema**: `staff.jsx`, `config.jsx` y `medicalRecords.jsx` tenian botones de submit que no se deshabilitaban durante la operacion. Un doble click o Enter rapido enviaba dos requests identicos.

`toast.promise` muestra el loading en el toast pero no bloquea el boton — son ortogonales.

**Decision**: Agregar `const [saving, setSaving] = useState(false)` en cada componente afectado, `setSaving(true)` antes del try y `setSaving(false)` en finally. Botones con `disabled={saving}` y texto `{saving ? "Guardando..." : "Guardar"}`.

Patron estandar aplicado:
```jsx
setSaving(true);
try {
    await toast.promise(apiCall(), { loading: "...", success: "...", error: "..." });
    // on success
} catch (err) {
} finally {
    setSaving(false);
}

<button disabled={saving}>
    {saving ? "Guardando..." : "Guardar"}
</button>
```

---

### 3. config.jsx usaba window.confirm() para eliminar servicios

**Problema**: Mientras todas las demas paginas usan `useConfirm` (modal personalizado con estilos del sistema), `config.jsx` usaba `window.confirm()` nativo del navegador. Inconsistencia visual y de UX.

**Decision**: Importar `useConfirm` y reemplazar `window.confirm` por el patron `await confirm({ message, confirmText, dangerMode: true })`. Mismo patron que `billing.jsx`, `inventory.jsx`, `medicalRecords.jsx`, `pets.jsx`, `prescriptions.jsx`, `staff.jsx`, `appointments.jsx`.

---

## Patron UX estandar (referencia)

Todos los formularios del sistema siguen este patron. No desviarse:

```javascript
// 1. Validacion temprana — ANTES de setLoading
if (!field.trim()) { toast.error("Campo requerido"); return; }

// 2. Lock de UI
setSaving(true);

// 3. Llamada a API con feedback visual
try {
    await toast.promise(apiCall(payload), {
        loading: "Procesando...",
        success: "Operacion exitosa",
        error: (err) => apiError(err, "Error inesperado"),
    });
    // refetch / reset form
} catch (err) {
    // modal permanece abierto, toast ya mostro el error
} finally {
    setSaving(false);
}

// 4. Botones bloqueados
<button disabled={saving}>{saving ? "Guardando..." : "Guardar"}</button>
<button disabled={saving} onClick={onCancel}>Cancelar</button>
```

Para confirmaciones de acciones destructivas:
```javascript
const ok = await confirm({ message: "¿...", confirmText: "Eliminar", dangerMode: true });
if (!ok) return;
```

## Estado del patron por pagina

| Pagina / Componente       | saving state | disabled botones | useConfirm | apiError en catch |
|---------------------------|:------------:|:----------------:|:----------:|:-----------------:|
| appointments.jsx          | ✅           | ✅               | ✅         | ✅               |
| billing.jsx               | ✅           | ✅               | ✅         | ✅               |
| config.jsx                | ✅ (P2)      | ✅ (P2)          | ✅ (P2)    | ✅               |
| inventory.jsx             | ✅           | ✅               | ✅         | ✅               |
| medicalRecords.jsx        | ✅ (P2)      | ✅ (P2)          | ✅         | ✅               |
| pets.jsx                  | ✅           | ✅               | ✅         | ✅               |
| prescriptions.jsx         | ✅           | ✅               | ✅         | ✅               |
| staff.jsx                 | ✅ (P2)      | ✅ (P2)          | ✅         | ✅               |
| PrescriptionForm.jsx      | ✅           | ✅               | n/a        | ✅               |
| LoginForm / useLoginForm  | ✅           | ✅               | n/a        | ✅               |
