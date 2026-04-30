# ADR: La receta medica no es una factura

## Contexto

Al implementar el flujo de consulta medica completo, surgio la pregunta de como relacionar
los productos recetados con la factura del cliente.

La opcion tecnica directa era agregar automaticamente todos los items de la receta como
`InvoiceItem` al crear la prescripcion. Eso simplifica el flujo de cobros porque la factura
llega prellenada con todo lo recetado.

Sin embargo, esto no refleja el negocio real de una clinica veterinaria.

## Problema de negocio

En una farmacia o clinica real el cliente frecuentemente no lleva todos los medicamentos recetados.
Puede que los consiga mas baratos en otro lugar, que no pueda pagarlos todos ese dia, o que ya tenga algunos en casa.

Si la factura se prellenara con toda la receta, recepcion tendria que eliminar manualmente los items
que el cliente no quiere llevar, lo cual es peor experiencia y mas propenso a errores que no incluirlos
y agregarlos explicitamente.

## Decision

Se mantiene la separacion estricta entre dominio clinico y dominio financiero:

- la receta es lo que el veterinario indica clinicamente
- la factura es lo que el cliente decidio llevar y pagar

Los productos de la receta NO se agregan automaticamente a la factura.

En cambio, la factura en estado `draft` expone el campo `prescription_suggestions`:
una lista de los productos recetados disponibles con precio y dosis sugerida.
Recepcion puede agregar cada uno individualmente con un boton explicito.

Flujo en cobros:
1. la factura muestra servicios e insumos de la consulta como items automaticos (estos siempre se cobran)
2. aparece un panel "Productos recetados" con los items de la receta como sugerencias opcionales
3. recepcion agrega uno a uno segun lo que el cliente confirme que se lleva
4. al confirmar la factura, el panel desaparece

## Alternativas consideradas

### 1. Agregar toda la receta automaticamente como items de factura

Descartada.

Problemas:
- no refleja la realidad del negocio: el cliente puede no querer todos los medicamentos
- obliga a eliminar manualmente items que el cliente no lleva, peor experiencia
- genera facturas con items "fantasma" si no se revisan
- mezcla la decision clinica del veterinario con la decision economica del cliente

### 2. No mostrar ninguna sugerencia

Descartada.

Problemas:
- recepcion tendria que recordar o consultar la receta por separado para saber que ofrecer
- aumenta la posibilidad de no cobrar algo que el cliente si quiere llevar

## Consecuencias

Consecuencias positivas:
- la receta conserva su semantica clinica independiente
- la factura refleja exactamente lo que el cliente compro
- recepcion tiene visibilidad de lo recetado sin que se asuma que el cliente lo lleva
- el flujo de cobros es explicito y menos propenso a errores

Costos y restricciones:
- se requiere que la factura consulte la receta asociada al exponer `prescription_suggestions`
- el campo es de solo lectura, calculado en el serializer, no almacenado en DB
- solo se muestra cuando la factura esta en estado `draft`

## Notas de implementacion

- `Invoice.prescription_suggestions` se calcula en `InvoiceSerializer.get_prescription_suggestions`
- el campo solo se expone cuando `invoice.status == 'draft'` y hay `medical_record` asociado
- cada sugerencia incluye: `presentation_id`, `product_name`, `dose`, `suggested_quantity`, `unit_price`
- el frontend detecta si un item ya fue agregado para mostrar "Agregado" deshabilitado y evitar duplicados
- agregar una sugerencia usa el mismo endpoint que agregar cualquier otro item: `POST /api/billing/invoices/<id>/items/`
