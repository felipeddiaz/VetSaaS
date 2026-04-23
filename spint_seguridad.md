# Sprint: Cierre seguro RBAC + Aislamiento Multitenant
Fecha: 2026-04-23  
Estado: Plan aprobado para ejecución  
Contexto: Sistema en riesgo operativo (datos sensibles + facturación/inventario con impacto real)
---
## 1) Objetivo del sprint
Cerrar el riesgo operativo de seguridad e integridad en producción mediante una secuencia verificable:
1. Observabilidad real del comportamiento RBAC/tenant
2. Validación de aislamiento multitenant y matriz de permisos
3. Migración controlada a permisos híbridos
4. Corte definitivo del esquema estático solo con evidencia
5. Postergar mejoras de dominio no críticas hasta cerrar seguridad
---
## 2) Diagnóstico base (sin suavizar)
- El sistema ya no está en etapa de bugs visuales.
- Cualquier error en este punto implica riesgo de:
  - fuga de datos entre organizaciones,
  - acceso indebido,
  - inconsistencias de negocio (facturación/inventario).
- RBAC actual está en transición (estático + híbrido), por lo que el comportamiento puede variar por endpoint.
---
## 3) Principios de ejecución
- No se cierran permisos sin métricas.
- No se corta fallback sin evidencia en logs reales.
- Aislamiento multitenant es prioridad superior a mejoras de dominio.
- Cada fase tiene criterios de entrada/salida (gates).
---
## 4) Alcance del sprint
Incluye:
- Instrumentación de eventos RBAC y tenant
- Pruebas de aislamiento entre organizaciones
- Pruebas de permisos 200/403 por rol y endpoint crítico
- Migración progresiva de vistas a `HybridPermission`
- Definición de corte RBAC
No incluye (hasta cerrar seguridad):
- Cambios v2 de dominio (ej. obligatoriedad `presentation` en `InvoiceItem`)
- Mejoras UX/documentación no críticas
---
## 5) Fases del sprint
## Fase 1 — Observabilidad (obligatoria, antes de tocar lógica)
### Objetivo
Tener visibilidad auditable para decidir con datos.
### Entregables
- Eventos estructurados RBAC:
  - `RBAC_DB_ALLOWED`
  - `RBAC_FALLBACK_ALLOWED`
  - `RBAC_DENIED`
- Evento de seguridad tenant:
  - `TENANT_MISMATCH_DENY`
- Campos mínimos por evento:
  - `timestamp`
  - `user_id`
  - `organization_id`
  - `role`
  - `path`
  - `method`
  - `required_permission`
  - `decision`
- Lista de endpoints críticos etiquetados:
  - billing, inventory, appointments, medical_records, staff, dashboard
### Criterio de salida
- Logs visibles en entorno real
- Consultas por endpoint/rol disponibles
- Se puede calcular `fallback_rate` sin ambigüedad
---
## Fase 2 — Seguridad base (prioridad máxima)
### Objetivo
Probar que no hay fugas entre organizaciones ni accesos indebidos.
### Entregables
- Suite de pruebas cross-tenant:
  - usuario Org A no puede listar/ver/editar recursos Org B
- Matriz de permisos por rol (200/403):
  - ADMIN, VET, ASSISTANT
  - endpoints críticos
- Pruebas de objeto (`has_object_permission`) con objetos de otra organización
### Criterio de salida
- 0 fugas de tenant
- 0 bypass de permisos en endpoints críticos
- Matriz mínima en verde
---
## Fase 3 — Migración RBAC controlada
### Objetivo
Eliminar comportamiento mixto de permisos de forma gradual y medible.
### Entregables
- Migración módulo a módulo a `HybridPermission`
- Reporte de fallback por endpoint/rol
- Corrección de asignaciones de `Role/UserRole` faltantes
### Criterio de salida
- Todos los endpoints críticos ya usan enfoque híbrido
- `fallback_rate` en descenso sostenido
---
## Fase 4 — Corte RBAC (solo con evidencia)
### Objetivo
Cerrar la transición y dejar una sola fuente de verdad.
### Requisitos obligatorios para ejecutar corte
- `fallback_rate = 0` sostenido en ventana acordada (ej. 7 días)
- `tenant_mismatch_count = 0`
- Matriz de permisos y pruebas cross-tenant en verde
### Acciones de corte
- Eliminar fallback estático
- Retirar `RolePermission`
- Planificar retiro de dependencia en `User.role` (con migración segura)
---
## Fase 5 — Dominio (post-cierre de seguridad)
### Objetivo
Reanudar mejoras funcionales sin riesgo estructural abierto.
### Candidatos
- `InvoiceItem.presentation` obligatorio (v2)
- Inventario avanzado por fases
---
## 6) Métricas (KPI) del sprint
- `fallback_rate = fallback_allowed / (db_allowed + fallback_allowed)` por endpoint y rol
- `tenant_mismatch_count` diario (objetivo: 0)
- `unexpected_403_count` en pruebas automáticas (objetivo: 0)
- `critical_endpoint_coverage` (objetivo: 100%)
---
## 7) Riesgos y mitigación
- Riesgo: migración incompleta por módulo
  - Mitigación: checklist por endpoint crítico, no por app “general”
- Riesgo: falso “fallback 0” por falta de tráfico
  - Mitigación: ventana de observación con tráfico real suficiente
- Riesgo: ruptura en producción por corte prematuro
  - Mitigación: gates obligatorios y rollback definido
---
## 8) Definición de Done del sprint
Se considera terminado solo si:
1. Hay observabilidad operativa de RBAC/tenant con métricas reales
2. No existen fugas cross-tenant en pruebas críticas
3. Matriz de permisos crítica pasa (200/403 esperado)
4. `fallback_rate` y `tenant_mismatch_count` cumplen umbral de corte
5. Existe decisión técnica documentada de “corte aprobado” o “corte bloqueado con causas”
---
## 9) Orden de ejecución recomendado (resumen)
1. Instrumentar observabilidad  
2. Ejecutar y cerrar pruebas de aislamiento/permisos  
3. Migrar endpoints a híbrido por módulos críticos  
4. Verificar métricas de corte  
5. Cortar RBAC estático solo con evidencia  
6. Pasar a mejoras de dominio