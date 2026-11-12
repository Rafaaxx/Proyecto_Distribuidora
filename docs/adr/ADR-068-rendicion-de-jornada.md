# ADR-068 — Rendición de jornada: entrega del día por la cola, conteo, diferencias, resumen, remanente en el cierre y comandos tardíos

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-11-04 |
| Referenciado en | `openspec/changes/24-rendicion-de-jornada/design.md` D0 a D12 y `specs/stock/rendicion-de-jornada`, `specs/stock/jornadas`, `specs/stock/toma-de-ubicacion`, `specs/stock/libro-de-stock`, `specs/sync/lote-de-comandos`, `specs/sync/observaciones`, `specs/ruta/area-de-ruta`, `specs/sistema/ayuda-contextual`; `01-dominio.md` RUT-04 a RUT-09, STK-03, STK-04, STK-07, STK-09, CST-12, CST-13, SYN-03, SYN-05, SYN-07, AUD-01, `01` §18, §19, §21, INV-01, INV-03, INV-04, INV-05, INV-06, INV-12, INV-16, INV-17, INV-21; `02-arquitectura.md` §6.4, §6.5, §7.3, §13.3; `03-modelo-de-datos.md` §9; ADR-048, ADR-049, ADR-051, ADR-052, ADR-058, ADR-064, ADR-066, ADR-067 |

**Change 24. Gobernanza: D1 y D3 CRÍTICAS; D2, D4, D5 y D7 ALTAS. Decisiones D0 a D12 aprobadas por el usuario con la opción A el 2026-11-04 (tarea 0.1), con todos los textos literales aprobados (tarea 0.2); precisiones del apply incorporadas abajo. Pasa de *Propuesto* a *Vigente* al archivar.**

## Contexto

El change 15 dejó la rendición sin conteo: `JORNADA_RENDIR` v1 pasa `ABIERTA → EN_RENDICION` y `JORNADA_CERRAR` cierra y libera (ADR-049 punto 3). Quedaron para el 24: el conteo como versión nueva de `JORNADA_RENDIR`, RUT-05 (cola vacía), el destino de las jornadas cerradas sin conteo y el orden de bloqueo, que necesita la jornada antes que el stock y debe convivir con el nivel 5 `FOR SHARE` de los movimientos (ADR-049 deuda 3); las diferencias (RUT-06) y el remanente (RUT-08) por la única puerta con la valorización de CST-12 (ADR-048 punto 9); las anulaciones por `venta_anulacion.jornada_id` (ADR-058, ADR-066); las cobranzas en el resumen y la cobranza que llega con la jornada en rendición o cerrada (ADR-052 deuda 4, ADR-067).

`docs/` no resuelve: cómo sabe el servidor que el teléfono no tiene nada sin enviar (la secuencia es del dispositivo y un rechazo previo a la reserva no deja fila); qué lleva el conteo y qué pasa con lo no contado; el orden de bloqueo; qué es cada columna del resumen y qué se congela; el motivo y el costo de las diferencias; cómo se devuelve el remanente; qué pasa con lo que llega tarde; las jornadas sin conteo.

## Decisión (opciones A de `design.md`, aprobadas)

1. **Alcance (D0).** Un change en seis lotes (migración y dominio; entrega; rendición; cierre y resumen; pantallas; cierre del change). Excepción de tamaño anotada en `04` §2.
2. **Entrega del día por la cola (D1).** «Terminar el día» en el teléfono encola `JORNADA_ENTREGAR` v1 (`ABRIR_JORNADA`, modo `OFFLINE`, contenido vacío, la jornada del sobre) detrás de todo lo pendiente y corta «Vender», «Anular venta» y «Cobrar». Como el lote procesa en orden de secuencia y un error transitorio lo corta, cuando el servidor procesa la entrega todo lo anterior del dispositivo ya tiene resultado: RUT-05 se cumple por construcción. El handler exige la jornada propia `ABIERTA` y no entregada (`JORNADA_ESTADO_INVALIDO`, `JORNADA_YA_ENTREGADA`), la toma `FOR UPDATE` y guarda `entregada_en`, `entrega_occurred_at` y `entrega_secuencia`; la jornada sigue `ABIERTA`. Irrevocable en la etapa 1. Sin teléfono no hay rendición: se libera (RUT-09).
3. **Conteo (D2).** `JORNADA_RENDIR` v2 (solo `ONLINE`) exige la entrega (`JORNADA_SIN_ENTREGA`) y lleva, por producto, la cantidad contada (entera, ≥ 0) y el esperado visto; todo producto con saldo distinto de cero o con movimientos en la ubicación durante la jornada debe estar (`CONTEO_INCOMPLETO`); se admite un sobrante de un producto activo fuera de ese conjunto; un esperado distinto del del servidor es `ESPERADO_DIFIERE` sin escribir nada. Observación opcional de hasta 500. v1 se retira: el bus resuelve el handler antes de la idempotencia, así que un v1 (nuevo o reenviado de uno ya aceptado) responde `VERSION_DE_COMANDO_SIN_HANDLER`; aceptado porque la aplicación no se publicó y `/admin` solo usa v2.
4. **Orden de bloqueo (D3).** La rendición y el cierre toman primero la ubicación de la jornada `FOR UPDATE`, después la jornada `FOR NO KEY UPDATE` (precisión 13), leen los saldos y llaman una vez a la puerta, que sigue su orden de siempre; ninguno toma `saldo_cuenta`. La puerta suma `rendicion_de_jornada` (falla cerrado): las líneas de esa ubicación pasan STK-09 y llevan su `jornada_id`. La entrega solo toma la jornada.
5. **Resumen (D4).** Stock por producto con la ventana de la jornada por momento de registro: al abrir, ingresos (`TRANSFERENCIA_ENTRADA`), ventas, anulaciones, otros, esperado (que cuadra con el saldo), contado y diferencia, **congelados en `rendicion_linea` al rendir**; dinero en vivo por `jornada_id`: ventas vigentes y anuladas (por `venta_anulacion.jornada_id`), cobranzas confirmadas por medio y anuladas aparte; lo registrado después de la rendición, aparte; el valor de las diferencias solo con `VER_COSTOS`. `GET /api/v1/stock/jornadas/{id}/resumen` con cualquiera de los permisos que leen jornadas.
6. **Diferencias (D5).** Un `DIFERENCIA_RENDICION` por producto con diferencia, origen `RENDICION`, sin motivo (la línea de la rendición es el registro), al promedio vigente sin recalcularlo ni dejar historia (CST-12); un sobrante de un producto sin promedio entra con costo nulo; un producto inactivo con faltante se acepta y con sobrante se rechaza (`PRODUCTO_INACTIVO`: se reactiva antes; decisión del usuario 2026-11-05). El saldo final es lo contado.
7. **Remanente en el cierre (D6).** `JORNADA_CERRAR` v2 admite una devolución opcional (con `TRANSFERIR_STOCK`) a una ubicación activa sin toma: una transferencia común, anulable, en la misma transacción que el cierre; nunca deja negativo. v1 sigue registrada.
8. **Tardíos (D7).** Una venta, anulación o cobranza sin conexión cuya jornada está `EN_RENDICION` o `CERRADA` se acepta (INV-17) con la observación nueva `JORNADA_RENDIDA` (SYN-07); no entra en el conteo y el resumen la muestra aparte.
9. **Jornadas sin conteo (D8).** Sin migrar: las cerradas antes del 24 y las liberadas muestran el resumen con el stock calculado y «Esta jornada no tiene conteo.».
10. **Pantallas `/admin` (D9).** En el detalle de la jornada: la entrega, el resumen, la pantalla de conteo (`/admin/stock/jornadas/:id/rendicion`) y el diálogo de cierre con «Devolver el remanente a». Los productos activos se leen, solo en lectura, también con `RENDIR_JORNADA`.
11. **Teléfono (D10).** «Terminar el día» en el inicio, con confirmación, con o sin señal; la marca vive en `meta` con el estado local `ENTREGADA` (sin versión nueva de Dexie); «Entrega del día» en «Sincronización».
12. **Textos y ayuda (D11, D12).** Textos de `JORNADA_RENDIDA`, de los rechazos de la entrega y de los errores de `/admin`; siete claves nuevas y dos revisadas, sin ejemplos.
13. **Modelo de datos.** Tablas `rendicion` y `rendicion_linea` (solo `SELECT` e `INSERT`); tres columnas nuevas en `jornada` con `UPDATE` acotado; `CHECK` de observaciones con `JORNADA_RENDIDA`. Sin permisos nuevos.

## Precisiones del apply

Lo que el apply fijó sin cambiar ninguna decisión aprobada:

1. **Migración `d2f4a6c8e0b1`** (sobre el head anterior): crea `rendicion` y `rendicion_linea` y agrega a `jornada` `entregada_en`, `entrega_occurred_at` y `entrega_secuencia`. El `CHECK` `ck_jornada__entrega_coherente` admite la entrega también en una jornada `LIBERADA`, para que la liberación forzada de una jornada ya entregada (RUT-09) siga siendo posible. El `downgrade` aborta con un mensaje claro si hay rendiciones o entregas.
2. **`JORNADA_ENTREGAR` v1** es solo `OFFLINE`; su handler exige `ABRIR_JORNADA` (`PERMISO_REQUERIDO`) y responde `JORNADA_YA_ENTREGADA` a una segunda entrega con otro identificador. El lote no necesitó cambios: la entrega se procesa detrás de lo anterior del dispositivo, un error transitorio la deja sin procesar y un rechazo anterior no la impide.
3. **`JORNADA_RENDIR` v1 retirada (aceptado por el usuario el 2026-11-04):** el bus no cambió; un v1 nuevo o reenviado responde `VERSION_DE_COMANDO_SIN_HANDLER`.
4. **Puerta del libro:** acepta `DIFERENCIA_RENDICION` solo con origen `RENDICION` y el parámetro `rendicion_de_jornada` (falla cerrado; deja el `jornada_id`). El ingreso positivo usa `aplicar_ingreso_sin_recalculo` y la excepción no alcanza a `STOCK_TRANSFERIR`.
5. **Contenido de `JORNADA_RENDIR` v2:** las cantidades son enteros estrictos; un número con decimales se rechaza como contenido no serializable (422) y una cantidad negativa con `CANTIDAD_INVALIDA`. `ESPERADO_DIFIERE` informa los productos distintos y sus esperados. Un producto inactivo con sobrante es `PRODUCTO_INACTIVO`; con faltante o sin diferencia se acepta (decisión del usuario 2026-11-05).
6. **«Tardío»** es lo registrado después del momento de registro de la rendición; el resumen de una jornada rendida no cambia por ello y lo muestra aparte. La observación `JORNADA_RENDIDA` también cubre la anulación y la cobranza sin conexión.
7. **`JORNADA_CERRAR` v2** con devolución usa una transferencia común: una ubicación de destino con toma se rechaza con `UBICACION_CON_TOMA`; v1 sigue registrada.
8. **Resumen:** `GET /api/v1/stock/jornadas/{id}/resumen`. `stock` no puede importar `ventas` ni `cobranzas` (import-linter), así que sus lectores se registran como puertos en `stock/service.py` al importar el `service.py` de cada módulo.
9. **Lecturas:** `GET /api/v1/catalogo/productos` se abre, solo en lectura, a `RENDIR_JORNADA`; `GET /api/v1/stock/jornadas/{id}` ahora devuelve `entregada_en`.
10. **Archivos por área (ADR-049 punto 2):** `stock/domain/rendicion.py` y `stock/domain/resumen.py` (puros), `stock/rendicion_repository.py`, `stock/rendicion_casos.py` (no importa `service.py`) y `stock/rendicion_commands.py`.
11. **Frontend:** `RendicionScreen`, `ResumenDeJornada` y `CierreDeJornadaDialogo` en `areas/admin/stock/`; `sync/terminarDia.ts`; la marca `ENTREGADA` vive en `meta` de Dexie sin subir la versión; la entrega se excluye de los pendientes y se muestra aparte en «Sincronización»; siete claves de ayuda nuevas y dos revisadas.
12. **Concurrencia y propiedades:** la rendición contra una venta sin conexión, contra una liberación y contra otra rendición, el cierre con devolución contra una transferencia al mismo depósito y la entrega contra una liberación se prueban en los dos órdenes de llegada y en carrera libre, sin interbloqueos; las propiedades confirman que el stock de lo contado es lo contado, que el resumen cuadra y que los libros solo crecen.
13. **Bloqueo de la jornada `FOR NO KEY UPDATE` (precisión de D3, hallada en la prueba de concurrencia 17.1).** La fila de `comando` de una operación sin conexión referencia a la jornada y le toma un bloqueo de clave (`FOR KEY SHARE`) antes de pedir la ubicación. Con la jornada `FOR UPDATE` (que choca con ese bloqueo) la rendición, que ya tenía la ubicación, esperaba a la operación mientras la operación esperaba la ubicación: PostgreSQL detectaba un interbloqueo (el bus lo reintenta si la víctima es la operación, no si es la rendición). `jornadas_repository.bloquear_jornada(..., despues_de_la_ubicacion=True)` toma la jornada `FOR NO KEY UPDATE` (aprobado por el usuario el 2026-11-05): no choca con el bloqueo de clave y sí con el `FOR SHARE` de los movimientos y con otra transición, que es lo que la serialización necesita. Lo usan solo la rendición y el cierre con devolución (los que toman la ubicación primero); la entrega y la liberación siguen con `FOR UPDATE`. La prueba `test_con_la_venta_esperando_la_ubicacion_la_rendicion_toma_la_jornada_sin_interbloqueo` cuenta los interbloqueos de `pg_stat_database` (falla con `FOR UPDATE`).

## Consecuencias

- El conteo se compara contra un esperado que ya incluye todo lo que el vendedor vendió, anuló y cobró.
- El vendedor no puede volver a vender en una jornada entregada; para seguir, se rinde y se abre otra.
- Una jornada sin teléfono no se rinde; se libera y se ajusta.
- Mientras dura la rendición, los movimientos del vehículo esperan; ningún otro comando cambia su orden de bloqueo.
- Las diferencias no cambian el promedio; un sobrante sin costo queda con costo nulo hasta una compra.
- El resumen de una jornada rendida no cambia aunque después lleguen operaciones tardías.

## Enmiendas a ADR anteriores

- **ADR-049 punto 3:** la rendición registra el conteo y exige la entrega; `JORNADA_RENDIR` v1 se retira; el cierre admite la devolución del remanente.
- **ADR-049 punto 8 y `02` §7.3:** la rendición y el cierre toman la ubicación `FOR UPDATE` antes que la jornada; la puerta suma la excepción de la rendición.
- **ADR-048 punto 9:** las diferencias se registran como `DIFERENCIA_RENDICION` sin motivo; el remanente es una transferencia común dentro del cierre.
- **ADR-052 deuda 4 y ADR-067:** la cobranza tardía lleva `JORNADA_RENDIDA`.

## Deudas nominadas

1. **Al 25 (observaciones y revisión):** mostrar y resolver `JORNADA_RENDIDA`.
2. **Al 26 (reportes):** la rendición por vendedor y jornada (REP) sobre `rendicion_linea` y el dinero por `jornada_id`.
3. **A la etapa 2:** rendición de efectivo con caja y tesorería (RUT-10) y la rendición sin la entrega del teléfono.

## Alternativas consideradas

Ver `design.md`: la declaración del supervisor y el informe automático en cada lote (D1); lo no contado como cero o sin diferencia (D2); adelantar el nivel 5 o reintentar ante interbloqueo (D3); el resumen por `jornada_id` o todo en vivo (D4); motivo obligatorio o sobrante sin costo rechazado (D5); la devolución aparte en rendición o después del cierre (D6); tardíos sin observación o solo la cobranza (D7).
