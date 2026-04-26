# Changelog

## 2026-04-25

### Agregado
- Estado clinico en `MedicalRecord` con `status`, `closed_at` y `closed_by`.
- Endpoint idempotente `POST /api/medical-records/<id>/close/` para finalizar consulta.
- Policy de dominio en `backend/apps/medical_records/policies.py` para ownership y bloqueo por consulta cerrada.
- Permiso `medicalrecord.close` en el catalogo RBAC.
- Modelo `MedicalRecordService` con sus endpoints para agregar y quitar servicios desde la consulta.
- Flags `can_modify_charges` y `can_close` expuestos al frontend desde serializers.
- Documentacion inicial en `docs/decisions/` y `docs/modules/`.
- Suite inicial de 14 tests para cierre de consulta, bloqueo por estado cerrado, logs y ownership.

### Corregido
- El flujo de productos usados en consulta dejo de depender de `inventory.create` y ahora se alinea al recurso clinico `medicalrecord`.
- La eliminacion de productos usados en consulta ahora ajusta o elimina el `InvoiceItem` asociado para no dejar facturacion inconsistente.
- La consulta cerrada ahora bloquea `update/delete` tambien en el endpoint principal del medical record.
- El frontend ahora muestra estado `Cerrada`, permite finalizar consulta, oculta `Editar/Eliminar` y bloquea mutaciones de productos cuando la consulta ya no es editable.

### Decisiones tecnicas
- El cierre de consulta se resuelve de forma explicita y no por eventos de facturacion.
- Una consulta `closed` se considera inmutable para todos los roles.
- El endpoint de cierre responde `200` de forma idempotente incluso si la consulta ya estaba cerrada.

### Pendiente
- Agregar prueba de concurrencia real con requests paralelos para el cierre de consulta.
- Extender la UI para gestionar servicios usados desde historial clinico con el mismo nivel de soporte visual que productos.
