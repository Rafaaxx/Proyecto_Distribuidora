# ADR-067 — Cobranza sin conexión en el teléfono: cola, base local, saldo local y cobranza rechazada

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-11-03 |
| Referenciado en | `openspec/changes/23-cobranza-offline/design.md` D0 a D12 y `specs/sync/lote-de-comandos`, `specs/sync/cola-local`, `specs/sync/base-local`, `specs/sync/motor-de-sincronizacion`, `specs/ruta/area-de-ruta`, `specs/sistema/ayuda-contextual`; `01-dominio.md` COB-01 a COB-06, CC-04, CC-05, CRE-01, CRE-08, CLI-03, RUT-09, SYN-01 a SYN-07, SYN-09, SYN-10, INV-01, INV-03, INV-05, INV-06, INV-08, INV-17, INV-21; `02-arquitectura.md` §6.5, §6.6, §13.2, §13.3; ADR-051, ADR-052, ADR-062, ADR-063, ADR-064, ADR-065, ADR-066 |

**Change 23. Gobernanza: D2, D4 y D6 ALTAS; ninguna CRÍTICA. Decisiones D0 a D12 aprobadas por el usuario el 2026-11-03, todas en la opción A (tarea 0.1); todos los textos de la tarea 0.2 aprobados sin ejemplos, tal como están escritos en `design.md`. Estado *Vigente* desde el archivado del change.**

## Contexto

El servidor ya acepta `COBRANZA_REGISTRAR` en modo `OFFLINE` por el lote desde el change 17 (ADR-052: jornada del sobre, `PERMISO_REVOCADO`, `JORNADA_LIBERADA`, `MEDIO_INACTIVO`, `REFERENCIA_FALTANTE`, `CLIENTE_NO_HABILITADO`; INV-08 como malformado). ADR-052 dejó al change 23 «la pantalla de cobranza del vendedor y su cola local» (deuda 3), y ADR-065 (D2) dejó al 23 decidir si una cobranza suelta rechazada sigue contando en el saldo local. El teléfono ya tiene la tabla `cobranzas` (Dexie v3, solo para el cobro de una venta), el movimiento `COBRANZA_CREDITO`, la conciliación por secuencia procesada (ADR-065), la cola y el motor (ADR-063, ADR-064) y el corte por jornada no abierta (ADR-066).

`docs/` no resuelve: si la cobranza del teléfono va siempre por la cola; dónde se guarda; qué valida el teléfono antes de encolar; a qué clientes se cobra desde el teléfono; si una cobranza rechazada sigue contando en el saldo local; si «Cobrar» se corta con la jornada no abierta o la versión mínima; las pantallas, los textos y la ayuda.

## Decisión (propuesta: opciones A de `design.md`)

1. **Alcance (D0).** Un change en tres lotes: contrato y núcleo del teléfono; pantallas y ayuda; punta a punta, ADR, documentación, cobertura y prueba manual. Sin migración ni permisos nuevos.
2. **Siempre por la cola (D1).** Con o sin señal, la cobranza de `/ruta` se confirma en el teléfono y se encola `COBRANZA_REGISTRAR` v1 `OFFLINE` con la jornada de la sesión; con señal se dispara la sincronización enseguida.
3. **Servidor sin cambios de código (D2).** El contrato del sobre que arma el teléfono queda fijado por un fixture compartido (`shared/fixtures/sync/cobranza-registrar-offline.json`) que validan el lote y Vitest; pruebas de caracterización del lote mezclado (venta y cobranza) y de los rechazos posibles. Si alguna prueba exigiera cambiar el servidor, se detiene y se consulta.
4. **A quién y quién (D3).** Con `REGISTRAR_COBRANZA` en los permisos del bootstrap; a clientes del bootstrap (`ACTIVO` y `SUSPENDIDO`), de la cartera o no (ordena, no restringe); nunca al consumidor final (el teléfono lo bloquea; el servidor lo aceptaría con `CLIENTE_NO_HABILITADO` solo como red de seguridad). Un cliente inactivo no está en el teléfono: se le cobra desde `/admin`.
5. **Reglas locales (D4).** Importe mayor que cero con dos decimales; de 1 a 20 medios activos del bootstrap, con importe positivo; suma igual al importe (INV-08); referencia obligatoria donde el medio la exige (igual que el cobro de la venta en el teléfono); observación opcional de hasta 500. Muestra el saldo local actual y el resultante; si el resultante queda a favor del cliente pide una confirmación explícita (ADR-052 punto 5).
6. **Base local (D5).** Dexie v5 agrega índices a `cobranzas` (`operation_id`, `cliente_id`, `jornada_id`, `estado_envio`); la cobranza suelta se guarda con `venta_id` nulo, origen `INDEPENDIENTE`, cliente, momento, observación y estado de envío propio. Las filas existentes (cobro de una venta) no cambian. Una transacción escribe cobranza, movimiento `COBRANZA_CREDITO` (con el `operation_id` de la cobranza), comando y última secuencia; reconfirmar devuelve la existente.
7. **Saldo local y rechazo (D6).** La cobranza cuenta desde que se confirma por la regla de CRE-08 (secuencia propia contra secuencia procesada). **Una cobranza suelta «Rechazada» deja de contar** (lo conservador para el crédito: el servidor no la tiene). El cobro de una venta sigue la regla de su venta (ADR-065 D2, sin cambios).
8. **Corte (D7).** «Cobrar» se deshabilita, igual que «Vender», con la jornada marcada como no abierta (ADR-066) y por debajo de la versión mínima (`02` §6.6). La cola se sigue enviando.
9. **Pantallas (D8).** «Cobrar» en la ficha del cliente y en el inicio (con selector de cliente); pantalla de cobro; «Cobranza guardada» con su detalle y su explicación de envío; «Cobranzas de hoy». Guarda del formulario con datos frente a la salida y a la versión nueva del service worker.
10. **Sin comprobante (D9).** COB-06 es de la etapa 2: no hay comprobante compartible.
11. **Sincronización y pendientes (D10).** «Sincronización» lista las cobranzas con problemas como «Cobranza a {cliente}»; lo pendiente se dice «N ventas, M anulaciones y K cobranzas sin enviar» (omitiendo las partes en cero), también en los avisos de cierre de sesión y de pendientes de otro usuario.
12. **Textos (D11).** El fixture `codigos-de-sincronizacion.json` suma `rechazos_de_cobranza` y `observaciones_de_cobranza`; los textos se eligen por tipo de operación.
13. **Ayuda (D12).** Claves nuevas y revisadas sin ejemplos.

## Precisiones del apply

- **Servidor sin cambios (D2).** El fixture `cobranza-registrar-offline.json` (tres sobres) lo valida el esquema del lote (Python) y lo arma igual `armarSobreDeCobranza` (Vitest). Las pruebas de caracterización con PostgreSQL real (`test_cobranza_offline_desde_telefono.py`) pasaron sin tocar código de producción del servidor: sobre aceptado con la jornada del sobre, venta y cobranza del mismo cliente en orden, cliente o medio inexistente rechazado con el lote siguiendo, medios que no suman rechazados y doble envío igual. La lista de rechazos de la cobranza se fija recorriendo el bus y `registrar_cobranza`.
- **Códigos y textos (D11).** `codigos-de-sincronizacion.json` suma `rechazos_de_cobranza` y `observaciones_de_cobranza`; el texto se elige por tipo de operación y un código sin texto rompe una prueba. Los textos de los rechazos terminan en que el teléfono ya no descuenta la cobranza de la cuenta del cliente.
- **Base local v5 (D5).** Solo agrega índices a `cobranzas` (`operation_id`, `cliente_id`, `jornada_id`, `estado_envio`); las filas existentes (cobro de una venta) se leen como de origen `VENTA`. La cobranza suelta guarda también el nombre del cliente, los nombres de los medios y el nombre del vendedor (para los avisos de pendientes de otro usuario). El bootstrap y el cierre de sesión no tocan `cobranzas`.
- **Saldo local (D6).** La cobranza independiente rechazada deja de contar; el cobro de una venta sigue la suerte de su venta. La regla vive en `disponiblesLocales.ts` (la operación conciliable sabe si es una cobranza independiente).
- **Editor de medios.** Se extrajo de `PasoCobro.tsx` a `MediosDeCobro.tsx` y lo usan la venta y la cobranza; la suite de la venta no cambió sus aserciones.
- **Corte (D7).** «Cobrar» se deshabilita con la jornada marcada como no abierta y por debajo de la versión mínima; el aviso común pasó a «Lo que ya vendiste y cobraste se sigue enviando.» (también en «Vender» y «Anular venta»).
- **Textos no literales en `design.md`.** Los errores de formulario, los diálogos y los estados vacíos de las pantallas nuevas se redactaron en el apply y se listan para la revisión final del usuario.
- **Cobertura.** `escenariosDe23.test.ts` asocia cada escenario de las seis specs delta con su prueba y comprueba que INV-01, INV-05, INV-06, INV-08, INV-17 e INV-21 los cita alguna prueba. `escenariosDe22a` y `escenariosDe22d` buscaban «abre en v4» en `db.test.ts`; ahora buscan «abre en v5» (mismas pruebas, renombradas por la versión nueva).
- **Docs.** Al terminar el Lote 1 se comprobó que las filas CRE-08 y SYN-06 de `01` habían quedado truncadas por el archivo del 22d (rompían `ayuda/trazabilidad.test.ts`); se restauraron. Los cambios a `01`, `02` y `04` están en `openspec/changes/23-cobranza-offline/propuesta-docs.md` y se aplican al archivar, con el visto bueno del usuario. Sin cambios en `03` (no hay migración).
- **Sin migración ni permisos nuevos.** `REGISTRAR_COBRANZA` ya existía (ADR-052, ADR-053).

## Consecuencias

- El vendedor cobra con y sin señal con el mismo camino; el crédito disponible del cliente en el teléfono baja enseguida.
- Una cobranza rechazada (datos, no reglas de negocio) deja de liberar crédito en el teléfono; el dinero queda para administración.
- `02` §13.2 gana la v5 de Dexie y la cobranza suelta en `cobranzas`; CRE-08 y COB-04, la regla de la cobranza rechazada.

## Alternativas consideradas

Ver `design.md` (opciones B y C de cada decisión).

## Deudas nominadas

- **Al 24 (rendición):** las cobranzas de la jornada en el resumen y la cobranza que llega con la jornada `EN_RENDICION` o `CERRADA` (ya nominada por ADR-052, deuda 4).
- **Al 25 (observaciones y revisión):** la resolución de las cobranzas rechazadas.
- **Etapa 2:** COB-06 (comprobante de cobranza).
