# Changelog

## 2026-04-27

### Agregado

- Componente global `SearchSelect` (`frontend/src/components/SearchSelect.jsx`): typeahead con debounce 300ms, proteccion contra respuestas stale, estado de carga, reset externo via `value?.id`. Reemplaza todos los `<select>` de lookup de datos en el sistema.
- Backend: `GET /api/pets/` ahora acepta `?search=<nombre>` (icontains) y `?owner=<id>` (combinables, limite 20 resultados).
- Backend: `GET /api/owners/` ahora acepta `?search=<nombre>` (limite 20).
- Backend: `GET /api/billing/services/` ahora acepta `?search=<nombre>` (combinable con `?active=true` existente).
- Guardia de integridad owner↔pet en `AppointmentSerializer.validate()`: si el frontend envia `owner_id`, el backend valida que `pet.owner_id` coincida.
- Sistema de notificaciones global via Sonner (`<Toaster>` en `App.jsx`): todo feedback transaccional y de validacion ahora es toast.

### Cambiado

- **Citas**: seleccion de mascota en `SidebarForm` y `WalkInModal` migrada a `SearchSelect`. Ya no se carga la lista completa de mascotas al montar la pagina — se busca contra el backend al escribir.
- **Historial clinico**: seleccion de mascota en modal Nueva Consulta migrada a `SearchSelect` con filtrado client-side sobre el array ya cargado (pets sidebar). Se agrego estado `isLoadingPets` que deshabilita el campo mientras carga.
- **Cobros**: seleccion de propietario y mascota en modal Nuevo Cobro migradas a `SearchSelect` con dependencia propietario→mascota. La mascota se deshabilita hasta seleccionar propietario. `owners` y `pets` ya no se cargan globalmente al montar el modulo.
- **PrescriptionForm**: seleccion de mascota migrada a `SearchSelect` con `getPets` importado directamente en el componente. Cuando `lockedPet=true` muestra texto estatico en lugar del campo. No requiere cambios en los sitios de llamada.
- **API `pets.js`**: firmas actualizadas — `getPets(params={})` y `getOwners(params={})` aceptan objeto de parametros opcionales.
- Todas las alertas de tipo `<div className="alert">` y `<div className="form-alert">` eliminadas del sistema. Reemplazadas por:
  - `toast.error()` para validaciones y errores de servidor
  - `toast.success()` para confirmaciones
  - `toast.promise()` para operaciones asincronas con loading/success/error

### Corregido

- La advertencia "No puedes crear una cita pasada" dejaba de mostrarse como banner siempre visible. Ahora es condicional: solo aparece cuando el slot seleccionado en el calendario es una fecha anterior a hoy.
- `handleAddPrescriptionSuggestion` en cobros no ejecutaba la llamada a la API por referencia a variable eliminada (`setError` huerfano). Corregido.
- Import de `SearchSelect` faltante en `billing.jsx` causaba crash de render (ErrorBoundary). Corregido.

## 2026-04-25

### Agregado
- Estado clinico en `MedicalRecord` con `status`, `closed_at` y `closed_by`.
- Endpoint idempotente `POST /api/medical-records/<id>/close/` para finalizar consulta.
- Policy de dominio en `backend/apps/medical_records/policies.py` para ownership y bloqueo por consulta cerrada.
- Permiso `medicalrecord.close` en el catalogo RBAC.
- Modelo `MedicalRecordService` con sus endpoints para agregar y quitar servicios desde la consulta.
- Flags `can_modify_charges` y `can_close` expuestos al frontend desde serializers.
- Componente compartido `PrescriptionForm` para reutilizar el formulario de recetas sin duplicar logica.
- Documentacion inicial en `docs/decisions/` y `docs/modules/`.

### Corregido
- El flujo de productos usados en consulta dejo de depender de `inventory.create` y ahora se alinea al recurso clinico `medicalrecord`.
- La eliminacion de productos usados en consulta ahora ajusta o elimina el `InvoiceItem` asociado para no dejar facturacion inconsistente.
- La consulta cerrada ahora bloquea `update/delete` tambien en el endpoint principal del medical record.
- El frontend ahora muestra estado `Cerrada`, permite finalizar consulta, oculta `Editar/Eliminar` y bloquea mutaciones de productos cuando la consulta ya no es editable.
- La creacion de recetas desde historial clinico ahora ocurre en un modal contextual sin navegar fuera de la consulta.
- Si crear receta falla, el modal conserva los datos y muestra el error sin cerrarse.
- El historial clinico ahora muestra el detalle de la receta asociada y separa visualmente receta medica vs productos consumidos en consulta.
- Agregar el mismo producto a una consulta ahora acumula cantidad en lugar de fallar por unicidad.
- El calculo de `can_close` y `can_modify_charges` ahora considera permiso RBAC real ademas de ownership/policy.

### Decisiones tecnicas
- El cierre de consulta se resuelve de forma explicita y no por eventos de facturacion.
- Una consulta `closed` se considera inmutable para todos los roles.
- El endpoint de cierre responde `200` de forma idempotente incluso si la consulta ya estaba cerrada.

### Pendiente
- Agregar prueba de concurrencia real con requests paralelos para el cierre de consulta.
- Extender la UI para gestionar servicios usados desde historial clinico con el mismo nivel de soporte visual que productos.
