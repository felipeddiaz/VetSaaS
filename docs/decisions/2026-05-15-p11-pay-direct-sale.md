# ADR p11: Pago inmediato para ventas directas (direct-pay)

**Fecha**: 2026-05-15
**Estado**: Implementado
**Documentos relacionados**:
- `docs/modules/billing.md`
- `docs/dashboard-metrics-contract.md`
- ADR `2026-04-28-generic-client-direct-sale.md`
- ADR `2026-05-09-p9-analytics-anchor-authority.md`

## Contexto

En el flujo de consulta, confirmar y pagar son acciones separadas con sentido
operativo real: el veterinario termina la atencion y define cargos, y luego
recepcion revisa y cobra. El estado `confirmed` tiene valor operativo.

En venta directa (`direct_sale`), quien arma la venta es el mismo que cobra,
y el flujo ocurre en segundos. El estado `confirmed` es artificial desde la
perspectiva del cajero — lo unico que quiere hacer es agregar items y cobrar.

Sin embargo, eliminar `confirmed` del todo para `direct_sale` romperia simetria
interna: analytics, accrual, audit trail, event authority, `confirmed_at`,
lifecycle consistency. Muchos sistemas POS reales mantienen `sale_created →
sale_finalized → payment_captured` internamente, pero colapsan la UX.

## Decision

Mantener la maquina de estados completa para todos los tipos de factura, pero
colapsar el UX de las ventas directas en un solo paso: **draft → paid**.

### 1. Servicio `pay_direct_sale()`

Nuevo servicio en `billing/services.py`:

```python
@transaction.atomic
def pay_direct_sale(invoice, user, payment_method):
    # Un solo select_for_update()
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    # Validar: solo direct_sale, solo draft
    _confirm_locked_invoice(invoice, user)    # stock, confirmed_at, audit log
    return _pay_locked_invoice(invoice, user, payment_method)  # paid_at, audit log
```

Internamente ejecuta `draft → confirmed → paid` con ambos anchors
(`confirmed_at`, `paid_at`) y ambos audit logs. El usuario externo solo ve
`draft → paid`.

### 2. Extraccion de internals para eliminar double-lock

`confirm_invoice()` y `pay_invoice()` fueron refactorizados en dos capas:

```python
# Internals: sin @transaction.atomic, asumen invoice YA lockeada
_confirm_locked_invoice(invoice, user)
_pay_locked_invoice(invoice, user, payment_method)

# Wrappers publicos: con @transaction.atomic y su propio lock
@transaction.atomic
def confirm_invoice(invoice, user):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    _confirm_locked_invoice(invoice, user)

@transaction.atomic
def pay_invoice(invoice, user, payment_method):
    ...
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    return _pay_locked_invoice(invoice, user, payment_method)
```

`pay_direct_sale()` hace un solo `select_for_update()` y llama ambos internals,
eliminando los 3 locks que ocurririan si se invocaran los wrappers anidados.
Los wrappers publicos preservan comportamiento backward-compatible.

### 3. Endpoint `POST /api/billing/invoices/<uuid>/direct-pay/`

- **Metodo**: POST (accion de dominio, misma convencion que `/confirm/`, `/pay/`, `/cancel/`)
- **Permiso**: `invoice.pay` (mismo que el pago regular — reusa codigo RBAC existente)
- **Body**: `{"payment_method": "cash|card|transfer|other"}`
- **Validaciones**: solo `direct_sale`, solo `draft`, requiere al menos 1 item activo, stock suficiente

### 4. Frontend — Modal "+ Cobro" con estado local

- Los items se acumulan en estado local del frontend sin crear factura en backend
- Al hacer clic en "Cobrar": `POST createInvoice → POST addItem × N → POST direct-pay`
- Si `direct-pay` falla (stock insuficiente, metodo invalido): modal permanece abierto, error visible, permite retry
- Si el usuario cierra el modal sin cobrar: confirm dialog, items se descartan sin facturas draft huerfanas
- El owner generico se carga una vez al montar la pagina de billing (`GET /owners/?is_generic=true`), no en cada apertura del modal

## Alternativas consideradas

### 1. Eliminar `confirmed` para `direct_sale` a nivel DB

Descartada.

Romperia la simetria de la maquina de estados. Las CHECK constraints,
snapshots, audit logs y el contrato analitico asumen que toda factura
pasa por `confirmed`. Tener dos maquinas de estados distintas duplica
la complejidad de cada feature que toca billing (reversos, refunds,
reportes, export).

### 2. Modificar el endpoint `pay/` existente para aceptar `draft` en `direct_sale`

Descartada.

Mezcla dos comportamientos semanticamente distintos en un solo endpoint.
`/pay/` tiene un contrato claro: requiere `confirmed`. Romper ese contrato
segun el `invoice_type` hace el codigo mas dificil de razonar y testear.
Un endpoint separado `/direct-pay/` hace explicito que es una operacion
diferente.

### 3. Hacer que el frontend llame `confirm/` y `pay/` en secuencia

Descartada.

Ralentiza la UX (2 round-trips), expone estados intermedios (el usuario
podria ver "Confirmada" brevemente), y no es atomico (si `pay/` falla
despues de `confirm/`, el stock ya fue descontado y la factura queda
en `confirmed`).

## Consecuencias

Positivas:
- La UX de venta directa es un solo paso: agregar items → cobrar
- La maquina de estados, CHECK constraints, analytics y audit trail permanecen intactos
- Un solo `select_for_update()` (vs 3 con wrappers anidados) — menos queries, sin riesgo de deadlock
- Sin facturas draft huerfanas (los items son estado local hasta el cobro exitoso)
- Sin nuevo codigo RBAC requerido
- Backward compatible: `confirm_invoice()` y `pay_invoice()` no cambiaron su firma publica

Costos:
- `confirmed_at` y `paid_at` son casi identicos para `direct_sale` (ms de diferencia).
  Las curvas de accrual y cash coinciden para este tipo — comportamiento documentado y
  distinto al de `consultation`.
- El endpoint `/direct-pay/` es `POST` mientras que `/confirm/`, `/pay/`, `/cancel/`
  existentes usan `PATCH` (inconsistencia preexistente). Unificar a `POST` en todos
  los command endpoints es un refactor futuro.
- Las cancelaciones de `direct_sale` pagadas seguiran el camino normal de cancelacion
  (no desde `paid`). Un mecanismo de refund/void para liquidacion instantanea es una
  necesidad futura (v2).

## Implicacion analytics

Para `direct_sale`, `confirmed_at ≈ paid_at`. Esto significa que:

- `revenue_accrual` y `revenue_paid` producen el mismo valor para facturas `direct_sale`
- El `done_to_invoice_conversion` no se ve afectado (direct_sale no tiene cita)
- Los snapshots diarios reflejan correctamente ambos anchors aunque sean casi identicos

Ver `docs/dashboard-metrics-contract.md` §3.1 para las definiciones formales de metricas.

## Notas de implementacion

- `billing/services.py`: `_confirm_locked_invoice()`, `_pay_locked_invoice()`, `pay_direct_sale()`
- `billing/views.py`: `direct_pay_invoice` FBV con `@api_view(['POST'])`
- `billing/urls.py`: ruta `billing/invoices/<str:pk>/direct-pay/`
- `frontend/src/api/billing.js`: `directPayInvoice(id, paymentMethod)`
- `frontend/src/pages/billing.jsx`: `NewInvoiceModal` con estado local + cobro atomico
- Tests: `DirectPayInvoiceTests` (8 API), `DirectPayAnchorTests` (3 service)
- Total: 11 tests nuevos, 59 tests totales en el suite de billing

## Relacion con otros ADRs

- **ADR p9** (analytics anchor authority): ambos anchors (`confirmed_at`, `paid_at`) se escriben
  desde `services.py` con `_source='service'`. Sin bypasses.
- **ADR 2026-04-28** (generic client direct sale): el modal "+ Cobro" usa el owner generico
  y `invoice_type='direct_sale'` tal como se definio en ese ADR.
- **ADR p7** (lazy invoice creation): la venta directa NO usa lazy creation — crea la factura
  explicitamente al cobrar. Son flujos distintos que no interfieren.
