# ADR-066 — Anulación de venta sin conexión y corte de la venta con la jornada no abierta en el teléfono

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-11-03 |
| Referenciado en | `openspec/changes/22d-anulacion-sin-conexion/design.md` D0 a D13 y `specs/ventas/anulacion-de-venta`, `specs/sync/lote-de-comandos`, `specs/sync/cola-local`, `specs/sync/base-local`, `specs/sync/motor-de-sincronizacion`, `specs/ruta/area-de-ruta`, `specs/sistema/ayuda-contextual`; `01-dominio.md` VTA-13, VTA-20 a VTA-22, VTA-24, STK-09, RUT-03, RUT-09, CRE-08, SYN-03, SYN-06, SYN-07, SYN-09, SYN-10, INV-01, INV-05, INV-06, INV-19, INV-21; `02-arquitectura.md` §6.5, §13.2, §13.3; `03-modelo-de-datos.md` (`venta_anulacion`); ADR-051, ADR-054, ADR-058, ADR-063, ADR-064, ADR-065 |

**Change 22d. Gobernanza: D2 CRÍTICA; D1, D3 y D7 ALTAS. Decisiones D0 a D13 aprobadas por el usuario el 2026-11-03, todas en la opción A (tarea 0.1); textos de D9 a D12 aprobados sin ejemplos (tarea 0.2). Vigente desde el archivo del change (2026-11-03).**

**Precisiones del usuario (2026-11-03):** la prueba manual usa `sup01`; el rol Vendedor no recibe `ANULAR_VENTA` por defecto (puede concederse desde «Roles y permisos» si hiciera falta); no hay cambios de permisos.

## Contexto

ADR-058 dejó `VENTA_ANULAR` solo `ONLINE` y pidió habilitarlo sin conexión sin una v2 del comando (VTA-24: la regla de la jornada en curso y la venta inexistente como dependencia inexistente); ADR-065 lo reasignó al 22d. El usuario decidió el 2026-11-03 que el teléfono, cuando con conexión se entera de que su jornada ya no está `ABIERTA`, deje de ofrecer «Vender» y lo avise, sin cortar el envío de lo ya vendido. `docs/` no dice qué rechaza y qué acepta una anulación sin conexión, con qué jornada queda, cómo se guarda y cuenta en el teléfono, ni cómo se entera el teléfono del estado de su jornada.

## Decisión (opciones A de `design.md`, aprobadas el 2026-11-03)

1. **Alcance (D0).** Un solo change en cuatro lotes.
2. **Contrato (D1).** `VENTA_ANULAR` v1 admite `OFFLINE` por el lote, con la venta como operación observable; la venta debe ser de la jornada del sobre (`JORNADA_AJENA`); una venta inexistente o ajena es `VENTA_INEXISTENTE`.
3. **Reglas (D2).** Rechaza `VENTA_YA_ANULADA`, `DEVOLUCION_INVALIDA`, `CONSUMIDOR_FINAL_SIN_DEVOLUCION`, `OBSERVACION_INVALIDA`, `MOTIVO_INVALIDO` (otra organización u otro ámbito) y `UBICACION_INACTIVA`; acepta el motivo dado de baja después del bootstrap, `PERMISO_REVOCADO`, `JORNADA_LIBERADA` y la ubicación tomada al sincronizar con `UBICACION_TOMADA_AL_SINCRONIZAR`.
4. **Jornada y efectos (D3).** Mismo servicio, transacción y orden de bloqueo de ADR-058; `venta_anulacion.jornada_id` es la jornada del sobre.
5. **Por la cola (D4).** En `/ruta` la anulación siempre se encola.
6. **Qué se anula (D5).** Con `ANULAR_VENTA`, de la jornada de la sesión, no anulada, no «Rechazada», con la jornada no marcada como no abierta y la versión al día.
7. **Base local (D6).** Dexie v4 con `anulaciones`; movimientos `ANULACION_STOCK`, `ANULACION_CREDITO`, `ANULACION_COBRANZA_DEBITO`; una transacción.
8. **Disponibles (D7).** La anulación cuenta desde que se confirma por la regla de CRE-08; rechazada deja de contar salvo que su venta también esté rechazada.
9. **Jornada no abierta (D8, D9).** Consulta de la jornada en cada sincronización con señal, más `JORNADA_REQUERIDA` y `JORNADA_LIBERADA`; se guarda en `meta`; corta «Vender» y «Anular» con un aviso por estado.
10. **Pantallas, textos y ayuda (D10 a D12).** Ver `design.md`.
11. **Spec principal (D13).** Se restituye `openspec/specs/ventas/anulacion-de-venta/spec.md` desde el delta del change 19.

## Precisiones del apply

- **Códigos nuevos.** `VENTA_INEXISTENTE` (rechazo por dependencia inexistente, con su fila de comando) y, en `codigos-de-sincronizacion.json`, los rechazos y las observaciones de la anulación separados por tipo de operación; una prueba recorre el bus y `anular_venta` y falla si un código no tiene texto. Los textos y los avisos son los aprobados en 0.2 (sin ejemplos).
- **Sin cambios de permisos ni migración.** El Vendedor no recibe `ANULAR_VENTA` por defecto (se concede desde «Roles y permisos»); `venta_anulacion.jornada_id` ya era nulable.
- **Estado de la jornada en el teléfono.** Una consulta `ABIERTA`, sin red, con 403 (el usuario no tiene `ABRIR_JORNADA`), 404 o con un error no cambia nada, y tampoco «reabre» una jornada ya marcada; «desconocido» no pisa un estado conocido; un estado conocido reemplaza a «desconocido». El dato de otra jornada que la de la sesión se ignora al leer y se borra al aplicar el bootstrap de otra jornada. Un usuario sin `ABRIR_JORNADA` se entera igual por el bootstrap, los resultados del lote o la consulta al entrar.
- **Anulación local.** Solo se ofrece con `ANULAR_VENTA`, sobre una venta de la jornada de la sesión, no anulada, no «Rechazada» y con la jornada no marcada como no abierta; una «Sin enviar» se anula y queda detrás de su venta. Reconfirmar devuelve la existente. El consumidor final siempre devuelve; sin cobro no se pregunta la devolución.
- **Spec principal restituida (D13).** `openspec/specs/ventas/anulacion-de-venta/spec.md` se restituyó desde el delta del change 19; su escenario «Modo sin conexión todavía no admitido» pasó a «Por REST solo con conexión».
- **Cobertura.** `escenariosDe22d.test.ts` asocia cada escenario de las siete specs delta con su prueba (la clave lleva la capacidad porque varios nombres se repiten) y comprueba que INV-19, INV-01, INV-05, INV-06 e INV-21 los cita alguna prueba.
- **Docs.** Los cambios a `01`, `02`, `03` y `04` están en `openspec/changes/22d-anulacion-sin-conexion/propuesta-docs.md` y se aplican al archivar, con el visto bueno del usuario.

## Consecuencias

- Se salda la deuda de ADR-058 «al 22c» (reasignada al 22d por ADR-065) y la del 22c «al 22d».
- VTA-24, SYN-06, SYN-07, STK-09, RUT-09 y CRE-08 nombran la anulación sin conexión; `02` §6.5 y §13.2 a §13.3 cambian; `03` precisa `venta_anulacion.jornada_id`.
- El change 24 (rendición) cuenta las anulaciones por `venta_anulacion.jornada_id`.

## Alternativas consideradas

Ver `design.md` D0 a D13 (opciones B y C de cada decisión).
