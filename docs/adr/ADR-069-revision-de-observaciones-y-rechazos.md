# ADR-069 — Revisión de observaciones y rechazos: resolución con comentario, registro de rechazos sin conexión, cuarentena sin reenvío y aviso a administración

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-11-05 |
| Referenciado en | `openspec/changes/25-observaciones-y-revision/design.md` D0 a D13 y `specs/sync/revision-de-observaciones`, `specs/sync/rechazos-sin-conexion`, `specs/sync/observaciones`, `specs/sync/cuarentena-de-comandos`, `specs/sync/bootstrap`, `specs/sync/cola-local`, `specs/ruta/area-de-ruta`, `specs/stock/rendicion-de-jornada`, `specs/sistema/ayuda-contextual`; `01-dominio.md` SYN-06, SYN-07, SYN-08, SYN-09, SYN-11, CRE-08, CRE-09, RUT-05, RUT-06, `01` §18, §19, INV-01, INV-02, INV-05, INV-06, INV-17, INV-21; `02-arquitectura.md` §6.3, §6.4, §6.5, §11; `03-modelo-de-datos.md` §13; ADR-022, ADR-052, ADR-054, ADR-055, ADR-056, ADR-058, ADR-065, ADR-066, ADR-067, ADR-068 |

**Change 25. Gobernanza: D6 y D7 CRÍTICAS; D1, D2, D5, D8 y D9 ALTAS. Decisiones aprobadas por el usuario el 2026-11-05 (tarea 0.1): todas en la opción A salvo D9, elegida en B. Pasa a *Vigente* al archivar.**

## Contexto

SYN-08 dice que una observación queda pendiente hasta que alguien con `REVISAR_OBSERVACIONES` la resuelve con un comentario, sin modificar la operación; hasta el change 24 nadie podía resolverlas. El change 04 dejó sin decidir qué permiso revisa la cuarentena y si un comando en cuarentena puede reenviarse, y nombró `OBSERVACION_RESOLVER`. Los changes 17, 18a, 18b y 24 dejaron códigos para mostrar en la bandeja (`MEDIO_INACTIVO`, `REFERENCIA_FALTANTE`, `CONSUMIDOR_FINAL_CON_DEUDA`, `UBICACION_TOMADA_AL_SINCRONIZAR`, `VENTA_SIN_COSTO`, `AUTORIZACION_OFFLINE`, las causas de `DESCUENTO_DIFIERE`, `EXCESO_CREDITO_DETECTADO_SYNC` con la notificación de CRE-09, `JORNADA_RENDIDA`) y la venta con producto desactivado sin observación. Los changes 22c, 22d y 23 dejaron la resolución de las ventas, anulaciones y cobranzas rechazadas.

Un rechazo sin conexión revierte la transacción con la reserva de idempotencia: el servidor no guarda nada de él (salvo `VENTA_INEXISTENTE` de la anulación, con su fila de comando). Solo el teléfono lo tiene.

## Decisión propuesta (aprobada: opciones A de `design.md` salvo D9 = B)

1. **Alcance (D0).** Un change en siete lotes; excepción de tamaño anotada en `04` §2.
2. **`OBSERVACION_RESOLVER` v1 (D1).** Solo `ONLINE`, `REVISAR_OBSERVACIONES`: de 1 a 100 observaciones con un comentario de 1 a 500; todas de la organización y pendientes, o ninguna (`OBSERVACIONES_INVALIDAS`, `COMENTARIO_INVALIDO`, `OBSERVACION_YA_RESUELTA`, 404); `FOR UPDATE` en orden de `id`; no toca la operación ni los libros.
3. **Resolución inmutable (D2).** `UPDATE` de `observacion` y de `comando_cuarentena` solo sobre las columnas de la resolución, con `CHECK` de coherencia.
4. **Bandeja (D3, D4).** Una entrada por operación, con filtros y el detalle legible de cada código; el resumen de la operación por puertos que registra cada módulo.
5. **Aviso a administración (D5).** Contador en «Revisión» y tarjeta «Para revisar» en el inicio de `/admin`, con los excesos detectados al sincronizar aparte; se refresca solo. Es la notificación de CRE-09; sin correo en la etapa 1.
6. **Registro de rechazos (D6).** Tabla `comando_rechazado`: el lote guarda en transacción aparte cada comando `OFFLINE` rechazado (con su contenido y su código), salvo credenciales, cola ajena y dispositivo revocado; el reenvío no lo duplica; un fallo transitorio al guardarlo corta el lote.
7. **Rechazos y cuarentena (D7).** Los revisa y resuelve `REVISAR_OBSERVACIONES`. **Nada se reenvía ni se reprocesa.** `RECHAZO_RESOLVER` v1 (solo `ONLINE`) con comentario y vínculo opcional a la venta o la cobranza cargada con conexión que lo corrige; una anulación rechazada se resuelve solo con comentario, sin vínculo (precisión 8) (`VINCULO_INVALIDO`, `RECHAZO_YA_RESUELTO`).
8. **Teléfono (D8).** El bootstrap trae `rechazos_resueltos` de la jornada; la venta rechazada resuelta deja de contar en lo local y toda rechazada resuelta muestra «Resuelta por administración». Una «Rechazada» sigue sin anularse en el teléfono. Sin versión nueva de Dexie.
9. **Rendición (D9 = B).** `JORNADA_RENDIR` se rechaza con `RECHAZOS_PENDIENTES` (409, con la cantidad) mientras la jornada tenga filas `PENDIENTE` en `comando_rechazado`, de cualquier tipo; se comprueba con la jornada tomada `FOR UPDATE`, por un puerto que declara `stock/service.py` y registra `sync/service.py` (sin puerto, la rendición falla). Motivo: con un aviso sin bloqueo, una venta rechazada cargada con conexión después de rendir se descontaba dos veces (faltante `DIFERENCIA_RENDICION` y venta nueva); RUT-05 asegura que todo se envió, no que todo se aceptó. **La cuarentena no bloquea:** no tiene jornada en el registro y el teléfono dado de baja no puede entregar el día, así que su jornada no se rinde y se libera (RUT-05, RUT-09). **No se bloquean** la entrega del día, el cierre ni la liberación. `GET /api/v1/stock/jornadas/{id}` informa `rechazos_pendientes` (solo la cantidad); la pantalla de conteo y el detalle de la jornada avisan y deshabilitan «Registrar rendición», con acceso a «Rechazadas» filtrada para quien tiene `REVISAR_OBSERVACIONES`.
10. **Producto desactivado (D10).** Observación nueva `PRODUCTO_DESACTIVADO`, por línea, solo sin conexión.
11. **Pantallas, textos y ayuda (D11 a D13).** `/admin/revision` con «Observaciones» y «Rechazadas»; la resolución en solo lectura en cada detalle; siete claves de ayuda nuevas y cinco revisadas, sin ejemplos.
12. **Sin permisos nuevos.**

## Consecuencias

- Toda marca de revisión y todo rechazo tienen dueño, constancia y, si corresponde, la operación que los corrige.
- El servidor guarda el contenido de lo rechazado (como la cuarentena); nunca credenciales.
- Corregir es siempre cargar una operación nueva con sus propias reglas. Como la rendición espera a que se resuelvan los rechazos de la jornada, la corrección entra en el esperado y la mercadería se descuenta una sola vez; queda fuera solo una cuarentena de la misma jornada, cuya venta cargada después de rendir necesita un ajuste.
- Una jornada con un rechazo pendiente no se rinde y su ubicación sigue tomada hasta que alguien con `REVISAR_OBSERVACIONES` lo resuelve (basta un comentario si la operación no ocurrió) o se libera la jornada.
- Quien no entra a `/admin` no recibe el aviso.

## Enmiendas a ADR anteriores

- **ADR-065 D2:** la venta rechazada cuenta en lo local hasta el fin de la jornada **o hasta que el bootstrap la informa resuelta**.
- **ADR-066 punto 6:** se confirma que una «Rechazada» no se anula en el teléfono; la resuelve administración.
- **ADR-068 (RUT-05):** la rendición exige, además de la entrega del día, que la jornada no tenga rechazos sin conexión pendientes (`RECHAZOS_PENDIENTES`); la entrega no se bloquea.
- **ADR-054 punto 27:** la venta sin conexión de un producto o presentación desactivados se acepta **con** `PRODUCTO_DESACTIVADO`.

## Precisiones del apply

Hallazgos al implementar, que no cambian lo aprobado:

1. **Registro de resumidores en `core`.** El registro de resumidores (de las operaciones y del contenido rechazado) y los lectores de vínculo `VENTA` y `COBRANZA` viven en `app/core/resumen.py`: `import-linter` prohíbe `sync` ↔ `ventas`/`cobranzas`/`proveedores`, así que cada módulo registra el suyo y `sync` lee el registro. `sync.service.resumir_operaciones` es una fachada. La sesión se tipa `Any` en `core` (no importa SQLAlchemy). El puerto del contador de rechazos pendientes (D9) es el diseñado: lo declara `stock/service.py` y lo registra `sync/service.py`; sin registro la rendición falla con `RuntimeError` (falla cerrado).
2. **Orden de comprobaciones de la rendición.** `RECHAZOS_PENDIENTES` se comprueba después de las de estado de la jornada y de entrega. La consulta solo lee `comando_rechazado` (índice parcial): no toma la jornada ni el rechazo. La concurrencia quedó probada con commits reales: resolver el último rechazo y rendir a la vez terminan sin interbloqueo (la rendición se acepta solo si vio el rechazo ya resuelto); un `INSERT` de rechazo y la rendición no se esperan (`FOR KEY SHARE` de la clave foránea contra `FOR NO KEY UPDATE`), y la rendición se rechaza o se acepta según lo que había confirmado antes de su consulta, nunca habiendo un rechazo confirmado que no vio.
3. **Códigos y filtros.** Código nuevo `RECHAZO_YA_RESUELTO` (409). El listado de rechazos filtra por estado `PENDIENTE` (por defecto), `RESUELTO` o `TODOS`. El resumen de una referencia que ya no existe dice «(no existe)».
4. **`PRODUCTO_DESACTIVADO`.** Si el producto y la presentación están inactivos, el detalle indica `PRODUCTO`. Una prueba de la era del change 22 que afirmaba la aceptación sin observación se reemplazó.
5. **Bootstrap.** `rechazos_resueltos` va en el nivel superior de la respuesta (no dentro de `sesion`) y el teléfono lo guarda en `meta` de Dexie; la versión de Dexie no cambia (v5).
6. **Inicio de `/admin`.** Para quien tiene `REVISAR_OBSERVACIONES` el inicio es la tarjeta «Para revisar»; las cuarentenas pendientes se suman a «operaciones rechazadas» de la tarjeta.
7. **Detalles de operación.** Los endpoints de detalle de venta, cobranza, compra, transferencia y ajuste exponen la resolución de sus observaciones (`sync.service.listar_observaciones_con_resolucion`).
8. **Anulación rechazada sin vínculo (D7; aprobado el 2026-11-06 en la prueba manual, 26.1).** Un rechazo `VENTA_ANULAR` se resuelve solo con comentario: enviar un vínculo da `VINCULO_INVALIDO` (422). La venta ya la nombra el propio teléfono (se ve en la fila de «Rechazadas») y, si ya estaba anulada, no hay nada «vuelto a cargar con conexión». El vínculo sigue igual para `VENTA_CONFIRMAR` (venta) y `COBRANZA_REGISTRAR` (cobranza). Los lectores de vínculo de `core/resumen.py` dicen solo si la operación existe en la organización.
9. **Columna «Llegó» en «Rechazadas» (2026-11-06, prueba manual).** La lista de rechazos muestra cuándo llegó cada uno al servidor (`recibido_en`).
10. **Etiqueta «Vincular con (opcional)» (2026-11-06, prueba manual).** El grupo del diálogo de resolución dice «Vincular con (opcional)».
11. **Nombres en la bandeja (2026-11-06, revisión final).** Cada observación de la bandeja puede traer `nombres` (`autorizador`, `producto`, `linea`, `vendedor_de_jornada`), resueltos en el servidor con una consulta por tipo de entidad para la página y solo de la organización; un id que ya no existe es «(no existe)». La numeradora de líneas se registra en `core/resumen.py`. El texto de la ubicación tomada es «Tomada por la jornada de {vendedor}» (D12).
12. **Búsqueda de venta por número (2026-11-06, revisión final).** `GET /api/v1/ventas?numero=` (parcial, sin distinguir mayúsculas, hasta 50 caracteres) para el buscador de «Vincular con»; sin migración ni índice nuevo.

## Deudas nominadas

1. **Al 26 (reportes):** observaciones y rechazos por vendedor (`02` §20, riesgo de abuso del modo sin conexión).
2. **A la etapa 2:** aviso por correo u otro canal.

## Alternativas consideradas

Ver `design.md`: una observación por comando o por operación (D1); solo la aplicación (D2); una fila por observación (D3); resumen guardado o pedido por el frontend (D4); correo o solo el filtro (D5); nada en el servidor o reusar la cuarentena (D6); permiso nuevo y reproceso de la cuarentena, o vínculo obligatorio (D7); sin cambios en el teléfono o «Descartar» (D8); aviso sin bloqueo, la opción recomendada y no elegida, o nada (D9); cerrar la deuda sin observación (D10); resolver también desde cada detalle (D11).
