# Modulo: Frontend

## Stack

- React 19 + Vite (JavaScript, sin TypeScript)
- Estilos: CSS modules por pagina + variables globales en `tokens.css`
- Toasts: `sonner` (configurado en `App.jsx`)
- Auth: Context propio (`src/auth/authContext.jsx`) con JWT + refresh automatico
- HTTP: Axios con interceptores (`src/api/client.js`)
- Confirmaciones: `useConfirm` hook (`src/components/ConfirmDialog.jsx`)

## Estructura de directorios

```
src/
├── api/           — funciones de llamada a la API por dominio
├── auth/          — context de autenticacion + login
├── components/    — componentes reutilizables
├── hooks/         — hooks compartidos
├── pages/         — vistas completas por ruta
│   └── medicalRecords/
│       ├── index.jsx            — orquestador de la página
│       ├── PetSidebar.jsx       — sidebar izquierdo (lista de mascotas)
│       ├── PatientHeader.jsx    — header con datos del paciente + vitales (solo lectura)
│       ├── VitalsEditor.jsx     — editor inline de vitales (ya no se usa en PatientHeader)
│       ├── Timeline.jsx         — lista de consultas agrupadas por año/mes
│       ├── TimelineCard.jsx     — card individual de consulta (expandible)
│       ├── SidePanel.jsx        — panel derecho con summary (3 modos: live/patient/empty)
│       ├── ConsultationStepper.jsx — stepper de 4 pasos (crear/editar consulta)
│       └── *.module.css         — estilos modulares
├── routes/        — proteccion de rutas privadas
└── utils/         — helpers (apiError, datetime)
```

## Reglas de UX (no negociables)

### Prevenir doble submit

Todo formulario con llamada a la API usa el patron:

```javascript
const [saving, setSaving] = useState(false);

// validar ANTES de setLoading
if (!field.trim()) { toast.error("Campo requerido"); return; }

setSaving(true);
try {
    await toast.promise(apiCall(payload), {
        loading: "Procesando...",
        success: "Listo",
        error: (err) => apiError(err, "Error inesperado"),
    });
    // reset / refetch
} catch (err) {
} finally {
    setSaving(false);
}
```

Botones durante la operacion:
```jsx
<button disabled={saving}>{saving ? "Guardando..." : "Guardar"}</button>
<button disabled={saving} onClick={onCancel}>Cancelar</button>
```

### Confirmaciones de acciones destructivas

Usar siempre `useConfirm`, nunca `window.confirm`:

```javascript
const confirm = useConfirm();
const ok = await confirm({ message: "¿Eliminar?", confirmText: "Eliminar", dangerMode: true });
if (!ok) return;
```

Tambien se usa para transiciones con peso operativo fuerte aunque no sean destructivas, por ejemplo `in_progress -> done` en citas.

Patron recomendado para transiciones terminales:
- confirmar primero con `useConfirm`
- ejecutar la mutacion
- mantener el contexto abierto si el siguiente paso esperado requiere un CTA inmediato

### Manejo de errores

Todos los `catch` usan `apiError` de `src/utils/apiError.js`:

```javascript
toast.error(apiError(err, "Error inesperado"));
// o en toast.promise:
error: (err) => apiError(err, "Error inesperado")
```

`apiError` extrae el primer mensaje legible en este orden: 429 → detail → error → errors[] → errors{} → message → fallback.

### Manejo centralizado de errores de formularios

- Utilities:
  - `src/utils/handleFormError.js`: centraliza la lógica para mapear errores DRF a `formErrors` y mostrar toasts globales.
  - `src/utils/mapFieldErrors.js`: normaliza la respuesta de errores DRF a claves planas (soporta colisiones y nested keys).

- Convenciones obligatorias:
  - Todos los formularios POST/PATCH deben usar `handleFormError(err, setFormErrors)` dentro del `catch`.
  - Al abrir un modal con formulario limpiar errores: `setFormErrors({})`.
  - Usar modo merge limpiando las claves a reemplazar antes de fusionar para evitar errores "stale".

Implementación pragmática en CI:
- El script `scripts/check-handle-errors.sh` detecta archivos con `catch(` en `frontend/src` y filtra aquellos que no importan `handleFormError`.
- Mejoras futuras: pasar a análisis AST para evitar falsos positivos (recomendado a mediano plazo).

### IDs en llamadas a la API

Los modelos con `public_id` exponen UUID en las URLs del backend. Usar siempre `item.public_id` en las llamadas, nunca `item.id`:

```javascript
// Correcto
getInvoice(invoice.public_id)
confirmInvoice(selectedInvoice.public_id)

// Incorrecto — falla con ALLOW_LEGACY_ID_LOOKUP=False
getInvoice(invoice.id)
```

Modelos con `public_id` en el frontend: `Invoice`, `Pet`, `Owner`, `Appointment`, `MedicalRecord`, `Prescription`, `Product`, `Presentation`, `Service`.

El campo `id` (entero) puede usarse para display (ej. "Cobro #123") pero no como argumento de URL en la API.

### Refetch despues de mutaciones

Despues de crear, editar o eliminar, siempre refrescar la lista local:

```javascript
await createItem(payload);
await loadItems();   // no asumir que el estado local refleja la DB
```

### PATCH en lugar de PUT para actualizaciones parciales

**Convención**: Todos los endpoints de actualización usan `PATCH`, no `PUT`.

```javascript
// api/medicalRecords.js
export const updateMedicalRecord = async (token, id, data) => {
    const res = await api.patch(`medical-records/${id}/`, data);  // ← PATCH, no PUT
    return res.data;
};
```

**Razones**:
1. **Semántica HTTP**: `PUT` = reemplazo completo, `PATCH` = actualización parcial
2. **Seguridad multi-tenant**: `organization` es `read_only` en el backend — nunca debe venir del cliente
3. **Robustez**: Si se agrega un campo requerido al serializer, `PATCH` no se rompe (solo los campos enviados se validan)

**Archivos que siguen esta convención**:
- `api/medicalRecords.js` — `updateMedicalRecord`
- `api/pets.js` — `updatePet`
- `api/inventory.js` — `updateProduct`
- `api/prescriptions.js` — `updatePrescription`
- `api/billing.js` — `updateService`
- `api/appointments.js` — `updateAppointment`

## Infraestructura de API

### client.js

- Base URL desde `VITE_API_URL`
- Interceptor request: inyecta `Authorization: Bearer <token>`
- Interceptor response: maneja 401 (logout automatico) y 500+ (alert global)

### authContext.jsx

- Decodifica el JWT para leer `exp`, `role`, `organization`
- Programa refresh del token 5 minutos antes de que expire
- En init: refetch `/api/me/` para datos frescos de usuario y org
- Persiste tokens en `localStorage`

## Componentes compartidos

### SearchSelect

Combobox con busqueda asincrona. Debounce de 250ms. Maneja race conditions con `reqId`. Props clave: `value`, `onChange`, `onSearch`, `disabled`, `prefetchOnFocus`.

### ConfirmDialog / useConfirm

Modal de confirmacion. `dangerMode: true` pone el boton de confirmacion en rojo. Retorna `Promise<boolean>`.

### QuickPatientForm

Form embebido para crear paciente anonimo dentro del flujo de citas walk-in o nueva cita. No valida internamente; la validacion la hace el componente padre.

### PrescriptionForm

Formulario de receta reutilizable. Acepta `lockedPet` y `lockedMedicalRecord` para bloquear campos cuando viene desde el flujo de historial clinico.

## Toaster

Configurado en `App.jsx`:
```jsx
<Toaster richColors position="top-right" toastOptions={{ duration: 4000 }} visibleToasts={3} />
```

Usar `toast.promise` para operaciones asincronas con feedback de progreso.
Usar `toast.error(apiError(err, fallback))` en catch blocks.

## Rutas

| Ruta                | Pagina              | Acceso       |
|---------------------|---------------------|--------------|
| `/`                 | Dashboard           | Privada      |
| `/login`            | Login               | Publica      |
| `/pets`             | Mascotas            | Privada      |
| `/pets/:id`         | Ficha mascota       | Privada      |
| `/appointments`     | Citas               | Privada      |
| `/medical-records`  | Historial clinico   | Privada      |
| `/inventory`        | Inventario          | Privada      |
| `/billing`          | Facturacion         | Privada      |
| `/prescriptions`    | Recetas             | Privada      |
| `/staff`            | Equipo              | Solo ADMIN   |
| `/config`           | Configuracion       | Solo ADMIN   |
