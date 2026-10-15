# 04 — Roadmap de changes

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Versión | 1.1 |
| Fecha | 2026-09-16 |
| Depende de | `00-vision-y-alcance.md`, `01-dominio.md`, `02-arquitectura.md`, `03-modelo-de-datos.md`, `docs/adr/` |

## 1. Propósito

Ordena la construcción de la etapa 1 en changes de OpenSpec, con sus dependencias y su contenido. Es el único documento que cambia seguido: se actualiza cuando un change se archiva, se divide o se reordena.

No reemplaza a las proposals. Cada change se detalla recién cuando le toca, con los documentos `00` a `03` y los ADRs como insumo y el código ya existente a la vista.

## 2. Convenciones de change

- **Nombre:** `NN-slug-en-espanol`, con el número indicando el orden previsto. Si un change se inserta después, toma un número con sufijo (`14b-…`) en lugar de renumerar todo.
- **Tamaño:** entre medio día y tres días de trabajo. Un change más grande se divide. Excepciones aceptadas por el usuario: el change 14 (`transferencias-y-ajustes`) se implementó en cuatro lotes con revisión entre cada uno, el change 15 (`jornadas`) en cuatro lotes, y el change 16 (`motor-de-descuentos`) en cuatro lotes sin revisión entre ellos, con la confirmación de alcance de sus piezas críticas, en lugar de dividirse (ADR-048, punto 1; ADR-049, punto 1; ADR-050, punto 1).
- **Contenido:** `proposal.md` (qué y por qué), `tasks.md` (pasos verificables), `design.md` solo si hay una decisión técnica no resuelta en `docs/`, y las specs delta por capacidad.
- **Trazabilidad:** todo requisito de una spec cita las reglas de `01-dominio.md` que implementa (`VTA-12`, `INV-13`).
- **Regla de oro:** si al escribir una proposal aparece una decisión que `docs/` no resuelve, se resuelve primero como ADR y después se sigue. El agente no inventa reglas de negocio.

### 2.1 Definición de terminado

Un change está terminado cuando:

1. Las pruebas que exige `02` §15 para su alcance pasan en CI.
2. Cada escenario de sus specs tiene al menos una prueba que lo cubre.
3. Los invariantes que toca tienen prueba que los cita por ID.
4. La migración de Alembic sube y baja limpia sobre una base con datos.
5. Se probó a mano el flujo principal en el navegador.
6. Las specs delta se archivaron en `openspec/specs/` y `04-roadmap-changes.md` quedó actualizado.
7. Si se tomó una decisión nueva, quedó como ADR.
8. Si el change trae funcionalidad no obvia, sus pantallas traen su ayuda contextual ("(?)" y, si el tema es largo, su página "Ver más") en el archivo único de textos, cada texto citando la regla de `01-dominio.md` o el ADR en que se apoya. Si el change modifica una regla o un ADR, se revisan los textos que lo citan (se buscan por su ID). Las tareas del change dicen qué claves agrega o revisa, o "no aplica" (ADR-051).

## 3. Reglas de orden

- **La base primero.** Organización, permisos y pipeline de comandos van antes que cualquier operación de negocio.
- **Los libros antes que sus operaciones.** Cuenta corriente y stock existen antes que ventas, compras y cobranzas.
- **Offline después, pero sobre estructura preparada.** La venta se construye desde el inicio como comando idempotente (ADR-012); el change de offline agrega cola, base local y sincronización, sin reescribir nada.
- **Producción temprana.** El despliegue básico va después del hito 5 (change 20), no al final.
- **Cada change deja algo verificable.** Preferentemente una pantalla usable; como mínimo, un endpoint con pruebas.

## 4. Tabla de dependencias

La tabla indica qué changes deben estar archivados antes de empezar cada uno.

| Change | Depende de |
| --- | --- |
| 01a fundacion-repo-base | — |
| 01b dinero-fixtures-ci | 01a |
| 02 organizacion-y-configuracion | 01b |
| 03 identidad-usuarios-permisos | 02 |
| 04 pipeline-comandos | 03 |
| 05 catalogo | 04 |
| 06 proveedores-y-costos | 04 |
| 06b permisos-efectivos-interfaz | 03, 06 |
| 07 clientes | 04, 06b |
| 08 cuentas-corrientes | 04 |
| 09 stock-y-costeo | 05, 08 |
| 10 importacion-inicial | 06, 07, 09 |
| 11 compras-y-deuda-proveedor | 06, 09 |
| 11b condicion-iva-organizacion | 02, 06, 10, 11 |
| 12 pagos-a-proveedores | 08, 11, 11b |
| 13 listas-de-precios | 06, 09, 11b |
| 14 transferencias-y-ajustes | 09 |
| 15 jornadas | 09, 14 |
| 16 motor-de-descuentos | 05, 13 |
| 16b ayuda-contextual | 13, 14, 15, 16 |
| 17 cobranzas | 07, 08, 15 |
| 18a venta-online-core | 07, 08, 09, 11b, 13, 15, 17 |
| 18b venta-online-descuentos-credito | 16, 18a |
| 19 venta-anulacion | 18b |
| 20 nota-de-venta | 11b, 18b |
| 27a despliegue-basico | 20 |
| 21 pwa-y-bootstrap | 20 |
| 22a cola-confirmacion-local | 21 |
| 22b motor-sincronizacion | 22a |
| 22c stock-credito-locales-y-conflictos | 22b |
| 23 cobranza-offline | 22a |
| 24 rendicion-de-jornada | 15, 22b |
| 25 observaciones-y-revision | 22c |
| 26 reportes-etapa-1 | 25 |
| 27b backups-y-runbook | 27a |
| 28 aceptacion-y-endurecimiento | 26, 27b |

**Change 18 es el nodo de convergencia:** necesita precios (13), jornadas (15), descuentos (16) y cobranzas (17) todos listos. Se divide en 18a (core sin descuentos) y 18b (descuentos + crédito + PIN) para que la complejidad sea manejable.

**Change 22 es el más riesgoso** y está dividido desde el inicio: 22a (cola + confirmación local atómica), 22b (motor de sincronización), 22c (stock/crédito locales + observaciones + pantalla de conflictos). Si 22b se desborda, se pausa y revisa antes de continuar con 22c.

## 5. Hito 1 — Base técnica

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 01a | `fundacion-repo-base` | Monorepo con estructura de `02` §4, Docker Compose de desarrollo, FastAPI con `/salud` y `/version`, aplicación Vite vacía, Alembic inicializado, logging estructurado en JSON con `request_id` (`02` §17) | — |
| 01b | `dinero-fixtures-ci` | `core/money.py` y `lib/money.ts` con `ROUND_HALF_UP` explícito, arnés de fixtures compartidos, Testcontainers funcionando, CI completa (lint, tipos, unitarias, integración, build) | INV-03 (prueba que recorre catálogo de columnas) |
| 02 | `organizacion-y-configuracion` | Tablas `organizacion`, `configuracion_organizacion`, catálogos (`alicuota_iva`, `medio_pago`, `motivo`); repositorios con `organizacion_id` obligatorio; prueba genérica de aislamiento que recorre todas las rutas | INV-02 |
| 03 | `identidad-usuarios-permisos` | Usuarios, roles, permisos, login, access token en memoria, refresh rotativo en cookie, registro y revocación de dispositivos, PIN de autorización, dependencia de permisos en handlers, tabla de auditoría, rate limit de login (`02` §18) | INV-05 (permisos de base sobre tablas de libro), INV-21 (cerrado por completo) |
| 04 | `pipeline-comandos` | Tabla `comando`, bus, sobre, huella canónica, reserva de idempotencia, `POST /sync/comandos`, `observacion`, `comando_cuarentena`, reintentos transitorios, logging de contexto de comando (`operation_id`, organización, usuario, dispositivo), compatibilidad de versiones de comando (`02` §6.6) | INV-06 (cerrado por completo) |

**Después del 04, ninguna escritura se implementa fuera del bus.**

**INV-06 cerrado por el change 04 (`pipeline-comandos`, verificación grupo 16):** la reserva de idempotencia (`UNIQUE (organizacion_id, operation_id)` sobre `comando`, `INSERT ... ON CONFLICT` bloqueante) garantiza que dos envíos concurrentes del mismo comando producen un solo efecto, sin depender de una consulta previa desde la aplicación. Confirmado con `backend/tests/integration/test_inv06_reserva_idempotencia.py` (reserva, reenvío idéntico, contenido distinto, rechazo reenviado) y, con commits reales de dos sesiones/hilos independientes (no una transacción externa con rollback), `backend/tests/concurrency/test_inv06_reserva_idempotencia_concurrencia.py`. La mención de INV-06 en la fila del change 22b (`motor-sincronizacion`, "doble sync no duplica") no reabre este cierre: ese change ejercita la misma garantía de punta a punta desde el cliente offline (cola local, Web Locks, reintentos), apoyándose en la reserva que ya cierra el change 04 del lado del servidor.

## 6. Hito 2 — Maestros y libros

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 05 | `catalogo` | Categorías, marcas, productos, presentaciones, presentación de referencia, alta y edición por comandos, pantalla de administración, visualización cajas + unidades | INV-18 (cerrado por completo), CAT-03 (cerrado por completo) |
| 06 | `proveedores-y-costos-informados` | Proveedores, carga de costo en cualquier presentación con o sin IVA y bonificación, vigencias, historial, costo base derivado, `producto.proveedor_id` obligatorio | — |
| 06b | `permisos-efectivos-interfaz` | `GET /api/v1/yo` (usuario, organización, rol y permisos efectivos, misma fuente que la autorización del servidor); en `/admin`, hook `usePermisos()` y `<SiTienePermiso>` para menú y pantallas, refrescados en cada renovación del access token; retiro del patrón "403 → ocultar" de las pantallas de los changes 03 a 06 (ADR-027); cierre de la brecha de sesión: toda petición autenticada exige usuario `ACTIVO` y rol `activo`, con revocación de las familias de refresh y auditoría, sin cerrar la cola offline (ADR-028) | INV-21 (sobre `GET /yo`) |
| 07 | `clientes` | Ficha completa, estados, lista asignada, campos de crédito sin evaluación, consumidor final | — |
| 08 | `cuentas-corrientes` | `cuenta_movimiento`, `saldo_cuenta`, comando de saldo inicial, estado de cuenta de cliente y proveedor, bloqueo de fila de saldo | INV-13 (Hypothesis), INV-05 (solo inserción) |
| 09 | `stock-y-costeo` | Ubicaciones, `stock_saldo`, `stock_movimiento`, `costo_producto` con `stock_total`, `costo_producto_mov`, comando de stock inicial valorizado, kardex, orden de bloqueo global (`02` §7.3) | INV-12 (Hypothesis), INV-04 |
| 10 | `importacion-inicial` | Importación de productos, clientes, proveedores y costos desde CSV/Excel; stock inicial y saldos iniciales; informe de errores por fila. No incluye listas de precios (`PRECIOS`, change 13) | — |

**CAT-03 e INV-18 cerrados por el change 05 (`catalogo`, verificación grupo 13):** CAT-03 (exactamente una presentación de referencia por producto, activa y usada en venta) queda garantizado en tres capas — el servicio (`catalogo/service.py`, validado antes de escribir), el índice único parcial `ux_presentacion__referencia` (`03` §5, que rechaza una segunda referencia escrita por fuera del servicio, incluso ante escrituras concurrentes) y el `CHECK` `ck_presentacion__referencia_venta` (una referencia siempre tiene `usar_en_venta = true`). Confirmado con `backend/tests/unit/test_catalogo_domain_presentaciones.py` (servicio, incluida la propiedad Hypothesis "todo conjunto aceptado tiene exactamente una referencia de venta"), `backend/tests/integration/test_catalogo_migracion.py::test_cat03_ux_presentacion_referencia_rechaza_segunda_referencia_directa` y `test_cat03_ck_referencia_venta_rechaza_referencia_sin_venta` (base), y `backend/tests/concurrency/test_catalogo_concurrencia.py::test_dos_cambios_de_referencia_simultaneos_dejan_exactamente_una_referencia` (dos transacciones con commits reales). INV-18 (las unidades base de una presentación ya usada no cambian) se resuelve con el puerto de verificadores de uso de `design.md` D2 del change 05-catalogo (ver ADR-023, vigente): `PRESENTACION_MODIFICAR` consulta a todos los verificadores registrados y rechaza con `UNIDADES_CONGELADAS` si alguno confirma uso. Confirmado con `backend/tests/unit/test_catalogo_domain_presentaciones.py::test_inv18_cambiar_unidades_de_presentacion_usada_es_congelado`, `backend/tests/integration/test_catalogo_service.py::test_inv18_cambiar_unidades_de_presentacion_usada_es_congelado` y, en la pantalla, `frontend/tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx` (mensaje del servidor mostrado al usuario). En este change no existe ningún módulo de operaciones (nace en 06, 11 y 18a): la lista de verificadores está vacía en producción y las pruebas registran uno de prueba. Este cierre no se reabre por las deudas nominadas abajo (que solo piden a los changes futuros registrar su propio verificador); es un cierre del mecanismo, no del universo de verificadores registrados.

**Deuda del change 05 (`catalogo`) para el change 06 saldada (2026-09-24):** el change 06 completó la FK compuesta y el `NOT NULL` de `producto.proveedor_id` en dos migraciones (`70dcb6dce507`: `proveedor`/`costo_informado` y la FK `NOT VALID` + `VALIDATE`, todavía `NULLABLE`; `8b9c0d1e2f3a`: por organización con productos huérfanos, un proveedor provisorio inactivo `"Proveedor a asignar"` asignado y recién entonces `SET NOT NULL`, `design.md` D2 del change 06). El ciclo completo de las dos migraciones (`upgrade head → downgrade hasta la revisión de catálogo → upgrade head`) está probado contra datos sembrados en `backend/tests/integration/test_ronda_dos_migraciones_proveedores_migracion.py`, que además deja explícita como aserción de prueba (no solo como riesgo nominado en `design.md`) la pérdida de historial de costos y de asignaciones de proveedor real que un rollback de dos migraciones acarrea por diseño. También se resolvió D1 (`design.md` D1 del change 06): un costo informado SÍ cuenta como "uso" que congela las unidades de la presentación (INV-18, `costo_base.py`/ADR-023), registrado por `proveedores/service.py` en el puerto de `catalogo/service.py::registrar_verificador_uso` — confirmado con `backend/tests/integration/test_proveedores_service.py::test_inv18_presentacion_con_costo_informado_es_congelada`.

**Deuda nominada por el change 06 (`proveedores-y-costos-informados`) para el change 10 (`importacion-inicial`):** la carga de costos por CSV/Excel del 10 reutiliza `proveedores/service.py::informar_costos` (el mismo camino que `COSTO_INFORMAR`, D3/D4/D12/D14), fila por fila o en lotes de hasta 200 (el límite de `design.md` D12 del change 06 sigue aplicando), traduciendo cada fila rechazada a su número de fila en el informe de errores (mismo mecanismo que el campo `fila` de `contrato-api.md` P9). La importación de proveedores en sí reutiliza `proveedores/service.py::crear_proveedor` fila por fila (sin comando de lote propio para proveedores, a diferencia de costos).

**Deuda nominada por el change 06 (`proveedores-y-costos-informados`) para el change 11 (`compras-y-deuda-proveedor`):** `GET /catalogo/productos` no admite un filtro `proveedor_id` en el servidor — `proveedores/CostosCargaScreen.tsx` (change 06) ya necesita "los productos de este proveedor" y hoy trae la página completa de productos y filtra del lado del cliente, lo que no escala más allá de un catálogo chico. El change 11 (selector de productos del proveedor al cargar una compra, mismo problema) debería agregar el filtro `proveedor_id` a `GET /catalogo/productos` (`catalogo/queries.py`/`api.py`) y hacer que `CostosCargaScreen.tsx` lo adopte en el mismo change, en vez de mantener dos pantallas con el mismo filtro resuelto de formas distintas. **Saldada por el change 11 (2026-10-02):** `GET /catalogo/productos` admite `proveedor_id`; el selector de la compra y `CostosCargaScreen.tsx` lo usan. La lectura del listado y del detalle también la abre `REGISTRAR_COMPRA` (ADR-043).

**Deuda nominada por el change 06 (`proveedores-y-costos-informados`) para el change 11 (`compras-y-deuda-proveedor`):** registrar el verificador de uso de presentaciones de `compra_linea` vía `catalogo/service.py::registrar_verificador_uso` (`design.md` D2 del change 05-catalogo) sigue pendiente (ver la deuda ya nominada más abajo, hito 3); el change 06 no la toca, pero deja precedente de cómo se registra (`proveedores/service.py`, al importarse, registra `_presentacion_tiene_costo_informado`) para que el 11 siga el mismo patrón con `_presentacion_tiene_compra`. **Saldada por el change 11 (2026-10-02):** ver la deuda homónima del change 05 más abajo (hito 3).

**Change 08 (`cuentas-corrientes`) archivado (2026-09-30, verificación completa):** se archivó con cuatro specs nuevas (`cuentas-corrientes/saldo-inicial`, `cuentas-corrientes/libro-de-cuenta-corriente`, `cuentas-corrientes/estado-de-cuenta` y `cuentas-corrientes/administracion-de-cuentas-corrientes`) y la delta de `clientes/fichas-de-cliente` (CLI-06: un saldo inicial cuenta como operación), sincronizadas a `openspec/specs/` (validate 34/34). Decisiones registradas en ADR-033, ADR-034 (enmienda el punto 3 de ADR-030) y ADR-035, todos *Vigentes*; `01` suma CC-08 y `03` §12 refleja `cuenta_movimiento` y `saldo_cuenta`. La verificación manual (9.3, ejecutada por el usuario) recorrió el flujo completo; su único hallazgo (paso 14: el rechazo `CLIENTE_CON_OPERACIONES` no se veía porque el campo `estado` de `ClienteFormScreen.tsx` no mostraba su error) se corrigió con prueba; frontend 413/413.

**Deuda nominada por el change 08 (`cuentas-corrientes`) para el change 10 (`importacion-inicial`):** la importación de saldos iniciales reutiliza `cuentas_corrientes/service.py::registrar_saldo_inicial` fila por fila, con el permiso `IMPORTAR_DATOS` (ADR-033). Hereda CC-08 y ADR-034: varias filas por cuenta son válidas mientras la cuenta no tenga movimientos de otro tipo (`CUENTA_CON_OPERACIONES` en caso contrario); el consumidor final se rechaza (`CONSUMIDOR_FINAL_SIN_CUENTA`); una entidad ajena o inexistente responde 404 (no hay puertos: la FK compuesta lo decide, ADR-035); el importe es positivo con hasta dos decimales y el sentido es `AUMENTA` o `REDUCE`. Cada fila rechazada se traduce a su número de fila en el informe de errores. Como `SALDO_INICIAL_REGISTRAR` es solo online, la importación corre en el servidor.

**Change 09 (`stock-y-costeo`) archivado (2026-09-30, verificación completa):** se archivó con seis specs nuevas y ninguna modificada (`stock/stock-inicial`, `stock/ubicaciones`, `stock/libro-de-stock`, `stock/kardex`, `stock/administracion-de-stock` y `costeo/costo-promedio`; 26 requisitos y 76 escenarios), sincronizadas a `openspec/specs/` (validate 40/40). Decisiones registradas en ADR-036, ADR-037, ADR-038 y ADR-039, todos *Vigentes* (ADR-039 matiza ADR-002: el promedio es nulo hasta el primer ingreso con costo); `01` suma STK-10 y amplía CST-12, §19 y §21, `02` §5.3 refleja `catalogo ──► costeo` y `03` refleja `ubicacion`, `stock_saldo`, `stock_movimiento`, `costo_producto` y `costo_producto_mov`. La verificación manual (10.3, ejecutada por el usuario) recorrió el flujo de `admin` (pasos 1 a 22) y el de `vendedor` (pasos 1 a 8) sin desvíos; las pruebas del grupo 9 no encontraron defectos de código de producción; frontend 574 pruebas, `ruff`, `mypy` y `lint-imports` limpios.

**Deuda nominada por el change 09 (`stock-y-costeo`) para el change 10 (`importacion-inicial`):** la importación de stock inicial reutiliza `stock/service.py::registrar_stock_inicial` fila por fila, con el permiso `IMPORTAR_DATOS` (ADR-036). Hereda STK-10 y ADR-037: varias filas por producto son válidas mientras el producto no tenga movimientos de otro tipo (`PRODUCTO_CON_OPERACIONES` en caso contrario); el costo es una cadena decimal positiva con hasta 6 decimales (`COSTO_INVALIDO`); una ubicación o un producto ajeno o inexistente responde 404; uno inactivo, 409 (`UBICACION_INACTIVA`, `PRODUCTO_INACTIVO`). Cada fila rechazada se traduce a su número de fila en el informe de errores. Como `STOCK_INICIAL_REGISTRAR` es solo online, la importación corre en el servidor. **Pregunta abierta para ese change:** si la importación necesita fechar el stock inicial al día de corte, se reabre el momento del movimiento (hoy, el `occurred_at` del sobre), como D5-C del change 08.

**Deuda nominada por el change 09 (`stock-y-costeo`) para el change 11 (`compras-y-deuda-proveedor`):** los ingresos y egresos de compra y de anulación de compra entran por `stock/service.py::registrar_movimientos` (único camino para cambiar stock, ADR-039), que toma el orden global de bloqueo; quien necesite `saldo_cuenta` lo bloquea antes de llamar. Queda **sin decidir** qué guarda `costo_producto_mov` en una `ANULACION_COMPRA` con `recalculado = false` (CMP-06): la tabla admite el origen y la columna, pero la regla de qué valores se registran al mantener el promedio es del change 11. **Saldada por el change 11 (2026-10-02) (ADR-044, estado *Propuesto*):** los ingresos y egresos de compra entran por `registrar_movimientos`; una `ANULACION_COMPRA` deja siempre una fila en `costo_producto_mov` (`cantidad` negativa, `costo_ingreso`, `promedio_nuevo = promedio_anterior` y `recalculado = false` cuando se mantiene el promedio).

**Deuda nominada por el change 09 (`stock-y-costeo`) para el change 15 (`jornadas`):** agregar la clave foránea compuesta de `stock_movimiento.jornada_id` a `jornada` (la columna nació nulable y sin FK, ADR-039 punto 7; el libro puede tener filas) y aplicar STK-09 en `stock/service.py::registrar_movimientos`. Un stock inicial en un vehículo con toma se acepta hoy sin jornada.

**Deuda nominada por el change 09 (`stock-y-costeo`) para el change 18a (`venta-online-core`):** `costo_producto.costo_promedio` es nulo hasta el primer ingreso con costo (ADR-039 punto 6). El change 18a decide cómo costea una venta de un producto sin promedio (rechazarla, costo cero con observación u otra regla); `costeo/service.py::aplicar_egreso` devuelve `costo_valorizacion` nulo en ese caso y no decide por su cuenta.

**Change 10 (`importacion-inicial`) archivado (2026-10-01, verificación completa):** se archivó con cinco specs nuevas (`importacion/planillas`, `importacion/importacion-de-maestros`, `importacion/puesta-en-marcha`, `importacion/registro-de-importaciones` e `importacion/administracion-de-importaciones`) y las deltas de `catalogo/productos-y-presentaciones` y `clientes/fichas-de-cliente`, sincronizadas a `openspec/specs/`. Decisiones registradas en ADR-040 (todo o nada con savepoints por fila), ADR-041 (lectura de planillas en el servidor y exactitud decimal) y ADR-042 (módulo `importacion` y sus dependencias), todos *Vigentes*; `01` suma IMP-01 a IMP-06 y amplía CST-05, CAT-01, CAT-02 y CLI-01, `02` suma el módulo `importacion` y `IMPORTACION_REGISTRAR`, y `03` §13 refleja la tabla `importacion`. La verificación manual (11.3, ejecutada por el usuario) no encontró desvíos.

**Deuda nominada por el change 06b (`permisos-efectivos-interfaz`) para el change 15 (`jornadas`) o el 18a (`venta-online-core`):** `POST /api/v1/sync/comandos` todavía no aplica el paso 4 de `02` §6.3 (permisos por comando, online y offline) — `sync/api.py` lo dejó para cuando existan comandos `OFFLINE` y jornadas (change 15). Cuando ese change implemente los permisos por comando, la parte offline de ADR-028 queda implementable: los comandos `OFFLINE` de un usuario `INACTIVO` o de un rol con `activo = false` se **aceptan con `PERMISO_REVOCADO`** (SYN-10), nunca se rechazan, y el lote se procesa ítem por ítem igual que para un usuario activo. Junto con eso hay que **implementar la excepción de renovación con jornada no cerrada** (D9.3-B), que quedó aprobada el 2026-09-25 junto con ADR-028 y cuya implementación se difiere al change de jornadas: hasta entonces, sin jornadas, un usuario dado de baja con cola pendiente ve su renovación rechazada sin más (D9.1/D9.2-A) porque no hay forma de distinguir "no tiene nada que subir" de "tiene la cola bloqueada"; cuando exista `jornada`, la renovación debe admitirse para que el lote de esa jornada pueda llegar al servidor. Lo que hoy está probado de D9.3-B es solo "el canal de la cola sigue abierto para el usuario inactivo" (`test_bus_lote_sincronizacion.py::TestUsuarioInactivoNoSeRechazaPorRuta`), no la excepción a la renovación.

**Deuda del change 06b repartida por el change 15 (`jornadas`) (ADR-049, puntos 18 y 19):** (a) la **excepción de renovación con jornada no cerrada** (ADR-028 D9.3-B) queda **saldada** por el change 15: un usuario o rol inactivo con una jornada `ABIERTA` o `EN_RENDICION` en ese dispositivo renueva su sesión, con auditoría por cada renovación, y la revocación en bloque la respeta; no alcanza a las jornadas `LIBERADA`. (b) El **paso 4 de `02` §6.3** (permisos por comando en `POST /sync/comandos`) y **`PERMISO_REVOCADO`** (SYN-10) **pasan al change 17**, el primero con un tipo `OFFLINE`, y no al 18a. Hasta entonces la excepción de renovación no tiene efecto visible: el token no abre ninguna ruta de negocio.

**Nota del change 06b (`permisos-efectivos-interfaz`) para el change de usuarios y roles (D9.5):** hoy la brecha que ADR-028 cerró es **latente**, y por eso está cerrada antes de existir el comando que la abriría: ningún comando cambia `usuario.estado` ni desactiva un `rol.activo` (los de `identidad` son `USUARIO_CREAR`, `USUARIO_DESBLOQUEAR`, `ROL_PERMISOS_CAMBIAR`, `DISPOSITIVO_REVOCAR` y `PIN_AUTORIZACION_ROTAR`). Ese change, que nace con la baja de usuarios y la de roles, tiene que escribir por el bus de comandos y cumplir el mismo criterio de ADR-028 en cada caso: un usuario que pasa a `INACTIVO` pierde el acceso en la petición siguiente y sus familias de refresh quedan revocadas con auditoría `REVOCAR_SESIONES_REFRESH_USUARIO`; un rol con `activo = false` corta el acceso de sus usuarios igual que un usuario inactivo (D9.4-A); y la baja **no** puede rechazar la cola offline del dispositivo. Ese change es también el que tiene que decidir el motivo de auditoría de cada caso, que hoy solo existe para `USUARIO_INACTIVO` y `ROL_INACTIVO`.

**Change 06b (`permisos-efectivos-interfaz`) archivado (2026-09-28, verificación completa):** se archivó con la spec nueva `identidad/permisos-efectivos` (6 requisitos, 28 escenarios) y los delta specs de `autorizacion-por-permiso`, `autenticacion-y-sesion`, `administracion-de-catalogo`, `administracion-de-proveedores` y `lote-de-comandos` sincronizados a `openspec/specs/` (validate 26/26). La verificación manual (10.5, pasos 1-13, ejecutada por el usuario) cerró el flujo completo: login por usuario, pantallas por permiso, mensaje de falta de permiso sin pedir datos, revocación en vivo (403 antes de renovar, menú sin la sección tras renovar, sin recargar), `/yo` directo (permisos ordenados, 401 sin token y con firma alterada, sin `password_hash`), almacenamiento limpio y `/ruta` intacta. **Hallazgo del paso 13 (D9, usuario inactivo)** — la sesión cortada no aterrizaba en el aviso "Iniciar sesión" (pantalla en blanco o menú obsoleto, porque `removeQueries(['yo'])` destruye la consulta de TanStack y el observer quedaba colgado de un objeto destruido) — se cerró en el grupo 11 con un corte determinístico de sesión: renovación rechazada → la consulta `['yo']` se resetea y falla con 401 en el acto → `AdminLayout` avisa con enlace "Iniciar sesión" sin depender de qué pantalla disparó el 401; la restauración de sesión en una recarga normal queda protegida por un test de guarda. Gates finales: `frontend` 288/288 (37 archivos), typecheck y lint limpios, build OK. Quedan pendientes de este change solo las deudas ya nominadas arriba: permisos por comando con `PERMISO_REVOCADO` (change 15 o 18a) y la baja de usuarios y roles (change D9.5).

**Al terminar el hito 2, cargar los datos reales de la distribuidora.** Los problemas de datos aparecen temprano y sin presión de venta. Es el momento más barato para descubrirlos.

## 7. Hito 3 — Compras, costos y precios

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 11 | `compras-y-deuda-proveedor` | Compra con líneas en cualquier presentación, ingreso de stock, recálculo de promedio, deuda o pago de contado, anulación con reversión | INV-01 (atómica), INV-07 (al menos una línea), CST-11 |
| 11b | `condicion-iva-organizacion` | Condición de la organización frente al IVA (`RESPONSABLE_INSCRIPTO`, `MONOTRIBUTO`, `EXENTO`) y la regla derivada de crédito fiscal en compras (CST-06): costo base y total sugerido según la regla, regla congelada por costo y por línea, cambio de condición auditado y sin efecto retroactivo, importación de costos y pantallas ajustadas | CST-06, TR-06, INV-05, INV-06 |
| 12 | `pagos-a-proveedores` | Pago independiente con 1 a 20 medios, anulación con motivo propio, lectura liviana del saldo del proveedor (el reporte de saldos es del 26), área "Pagos a proveedores" | INV-08 (cerrado para pagos; sigue pendiente para cobranzas en el 17), INV-13 |
| 13 | `listas-de-precios` | Listas, reglas de margen con precedencia y unicidad, redondeo, generación de borrador único, precio manual, publicación con vigencia, anulación de versiones programadas, versiones anteriores de solo lectura, lista asignada al cliente y por defecto, resolución de precio (PRC-20). **No incluye el importador `PRECIOS`** (pasa al `13b`). | INV-11 (versión inmutable), fixtures compartidos PRC-22 |

**Deuda nominada por el change 05 (`catalogo`) para el change 11 (`compras-y-deuda-proveedor`):** registrar el verificador de uso de presentaciones de `compra_linea` vía `catalogo/service.py::registrar_verificador_uso` (`design.md` D2 del change 05-catalogo), con una prueba que cite INV-18. **Saldada por el change 11 (2026-10-02):** `proveedores/service.py` registra `_presentacion_tiene_compra` al importarse; una presentación usada en una compra, también anulada, congela sus unidades (`backend/tests/integration/test_compras_confirmar.py`, pruebas `test_inv18_*`).

**Deuda nominada por el change 11 (`compras-y-deuda-proveedor`) para el change 12 (`pagos-a-proveedores`):** el 11 ya creó `pago_proveedor` y `pago_proveedor_medio` (`03` §6) con `origen` (`COMPRA`, `INDEPENDIENTE`), `compra_id` y los campos de anulación; el 12 agrega el pago independiente (`PAGO_PROVEEDOR_REGISTRAR`, `origen = INDEPENDIENTE`) y `PAGO_PROVEEDOR_ANULAR` sobre las mismas tablas, sin migrar lo existente. Decisiones que el 12 debe tomar con un ADR: (a) el motivo de anulación de un pago (`anulacion_motivo_id` es nulable y `motivo.ambito` no tiene un ámbito para pagos de proveedor); (b) si un pago de origen `COMPRA` puede anularse por separado de su compra (hoy solo se anula con `COMPRA_ANULAR` y `devuelve_pago = true`); (c) cómo se compensa en pantalla el saldo a favor nuestro que deja una anulación con `devuelve_pago = false` o un pago de más. Los movimientos `PAGO` y `ANULACION_PAGO` de la cuenta del proveedor ya existen (ADR-034 punto 5) y los usa el 11 para el contado. **Saldada por el change 12 (2026-10-06) (ADR-046):** (a) ámbito de motivo `ANULACION_PAGO` con tres motivos sembrados y `CHECK` estricto de anulación; (b) el pago de una compra se anula por separado solo si la compra ya está anulada (`PAGO_DE_COMPRA_VIGENTE` en otro caso); (c) el saldo a nuestro favor se compensa solo por el saldo general, con confirmación explícita en el alta de pago y aviso en el alta de compra.

**Deuda del change 11 saldada por el change 14 (`transferencias-y-ajustes`, ADR-048):** un saldo negativo se regulariza con cualquier ingreso (compra, transferencia entrante o ajuste positivo), con la acción "Ajustar" del stock por ubicación; los ajustes nunca dejan negativo. `registrar_movimientos` admite `permitir_negativo` para `ANULACION_COMPRA` y `TRANSFERENCIA_SALIDA`, y para el inverso de un ajuste. Queda para el 18a cómo costea y valida una venta sobre un saldo negativo.

**Deuda nominada por el change 05 (`catalogo`) para el change 13 (`listas-de-precios`):** decidir por ADR qué pasa al cambiar la presentación de referencia de un producto con precios publicados — `precio_item` no congela las unidades de referencia, y el cambio altera el significado de `precio_referencia` (PRC-10, PRC-22; `design.md` D5 del change 05-catalogo). El ADR debe optar entre bloquear el cambio de referencia o congelar las unidades en `precio_item`. **Saldada por el change 13 (ADR-047 punto 2):** `precio_item` congela `unidades_referencia`; cambiar la referencia no altera ninguna versión.

**Deuda nominada por el change 06 (`proveedores-y-costos-informados`) para el change 13 (`listas-de-precios`):** `proveedores/service.py::obtener_costo_informado_vigente(organizacion_id, producto_id, fecha, sesion)` (CST-03, D4) y `listar_historial_costos` ya están listos para que el 13 los lea al generar un borrador de lista (PRC-11); no requieren cambios de forma. Queda abierta una **decisión de negocio** surgida en la verificación manual del 06 (2026-09-25): si un proveedor vende varias presentaciones de compra con distinto costo por unidad base (por ejemplo `Caja x6` y `Caja x12`), CST-03 toma como costo de referencia el último informado sin importar la presentación, y el precio pasa a depender del orden de carga. Antes de implementar PRC-11, el usuario decide, con un ADR, si se mantiene la regla actual, si el costo de referencia sale de una presentación de compra habitual marcada por producto, o si se usa el mayor de los vigentes por presentación (ya disponibles en `GET /costos/productos/{id}/vigente` → `por_presentacion`, enmienda P11 del 06). En el mismo ADR se decide si se admiten precios de venta no proporcionales entre presentaciones (hoy ADR-010 y PRC-10 los descartan). El usuario indicó que se revisa "si es necesario": puede resolverse manteniendo la regla actual. La deuda de referencia y precios publicados (`precio_item` no congela la referencia) sigue siendo la nominada por el change 05, sin relación con este punto. **Saldada por el change 13 (ADR-047 punto 3):** se mantiene CST-03 y los precios proporcionales; cada precio muestra de qué presentación salió el costo y avisa cuando los costos por presentación difieren.

**Deuda nominada por el change 10 (`importacion-inicial`) para el change 13 (`listas-de-precios`):** `00` §6.1 incluye "listas" en la importación inicial y `03` §13 declara el tipo `PRECIOS`, pero las listas nacen en el 13 (que no depende del 10). El change 10 deja el tipo `PRECIOS` en el `CHECK` de `importacion.tipo` y la API lo rechaza con 422 `TIPO_IMPORTACION_INVALIDO`. **Reasignada al change `13b-importacion-de-precios` (D0, ADR-047 punto 1):** el 13 deja el tipo `PRECIOS` rechazado con `TIPO_IMPORTACION_INVALIDO`. El `13b` debe decidir qué crea una planilla de precios (borrador, precios manuales o versión publicada) y resolver las referencias por clave natural (lista por nombre, producto por código); la presentación no se resuelve por nombre porque hay un único precio por producto sobre la referencia (PRC-10).

**Change 11b (`condicion-iva-organizacion`, ADR-045) — impacto en los changes siguientes:** la organización inicial es monotributista, así que el IVA de compra es costo (CST-06) y vende a precio final (modo A, Factura C sin IVA discriminado). Se inserta antes del 12 y del 13 porque cambia el significado del costo base y del total de la compra. (a) **Change 13 (`listas-de-precios`):** el costo informado vigente que alimenta PRC-11 puede haberse calculado con una u otra regla (`costo_informado.computa_credito_fiscal`); `GET /costos/resumen-regla-iva` cuenta los vigentes por regla y el 13 debe decidir qué hacer con los calculados con la regla anterior antes de fijar precios (D10 del 11b). **Saldada por el change 13 (ADR-047 punto 4):** los costos calculados con otra regla de IVA se usan y se señalan; no se bloquea la generación ni la publicación. (b) **Change 18a (`venta-online-core`):** una organización no inscripta tiene modo `A` y modalidad de IVA sin definir (restricción de base); el 18a no puede asumir `modalidad_iva_default` no nula. (c) **Change 20 (`nota-de-venta`) y la facturación:** ADR-009 y FAC-02, FAC-03, FAC-04 y FAC-08 solo se aplican a responsables inscriptos; para un monotributista la factura es Factura C, sin IVA discriminado. **Idea futura sin change asignado:** reporte de facturación de los últimos 12 meses contra el tope de la categoría del monotributo.

**Deuda nominada por el change 12 (`pagos-a-proveedores`):** (1) **Reporte de saldos de proveedores (change 26):** el 12 solo entrega `GET /proveedores/{id}/saldo`; no hay columna de saldo en el listado de proveedores. (2) **Corrección del saldo inicial después del primer pago (etapa 2):** desde el primer `PAGO` la cuenta rechaza `SALDO_INICIAL` (CC-08); la corrección espera a los ajustes de cuenta corriente. (3) **Imputación de pagos a compras y vencimientos (etapa 2, CMP-09):** el 12 no imputa (PAG-02); la observación libre del pago es el único vínculo con las facturas.

**Deuda nominada por el change 13 (`listas-de-precios`) para el change `13b-importacion-de-precios`:** el importador `PRECIOS` (ver arriba). Va con la misma política de todo o nada (ADR-040) y los mismos códigos de error que la pantalla.

**Deuda nominada por el change 13 (`listas-de-precios`) para el change 18a (`venta-online-core`):** consumir `precios/service.py` (`resolver_lista_aplicable`, `resolver_precios`, `calcular_bruto_de_linea`); implementar PRC-21 (`USAR_LISTA_ANTERIOR`, con motivo según configuración), PRC-23 (congelar por línea versión, precio y unidades de referencia) y la observación `LISTA_NO_VIGENTE`; decidir qué hace la venta con `SIN_LISTA_APLICABLE`, `LISTA_SIN_VERSION_VIGENTE` y un producto sin precio en la versión (VTA-10); completar los casos compartidos de §10.4 con descuentos y totales junto con el change 16.

**Deuda nominada por el change 13 (`listas-de-precios`) para el change 21 (`pwa-y-bootstrap`):** el bootstrap (SYN-11) debe incluir, de las listas, las versiones vigentes y las anteriores permitidas con sus `unidades_referencia`, sin campos de costo salvo `VER_COSTOS`; leerlas por `precios/service.py`. La lista predeterminada y la asignada de cada cliente ya están en `configuracion_organizacion` y `cliente`.

**Deuda: redondeo por defecto de la organización (`01` §4, "a definir"):** no hay comando que lo defina; solo precargaría el formulario de una lista nueva. Sin change asignado; se hace si molesta (decisión del usuario, 2026-10-07).

**Decidido (usuario, Lote 3, 2026-10-06):** un precio manual sobre un producto sin presentación de referencia se rechaza (404); no hay pregunta abierta.

**Punto de validación con el cliente después del change 13:** mostrarle cómo un costo nuevo genera una lista y qué precios salen. Es el momento más barato para corregir márgenes o redondeos.

## 8. Hito 4 — Operación de ruta

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 14 | `transferencias-y-ajustes` | Transferencia entre ubicaciones, ajuste con motivo, ambos atómicos | INV-15 |
| 15 | `jornadas` | Apertura con toma, bloqueo de ubicación, cierre, liberación auditada | INV-16 (dos aperturas simultáneas) |
| 16 | `motor-de-descuentos` | Reglas de volumen, alcance, prioridad, acumulabilidad y vigencia; motor en Python y TypeScript; descuento manual (general por venta y propio por línea) con tope y autorización; tope de descuento por rol; fixtures compartidos DSC-05 y DSC-06; pantallas de reglas y de topes. El efecto en la venta es del 18b | — |
| 16b | `ayuda-contextual` | Botón "(?)" accesible (clic, tap, teclado), archivo único de textos con IDs de regla y prueba de trazabilidad, páginas "Ver más" (descuentos, topes, precio de una lista) y ayuda en las pantallas de descuentos, topes, listas de precios, compras, costos, ubicaciones y jornadas. Adelanta la ayuda contextual de la etapa 4 (ADR-051) | — |
| 17 | `cobranzas` | Cobranza independiente con varios medios, anulación, efecto en cuenta corriente | INV-08, CC-05 |

**Deuda heredada del change 04 para el change 15 (`jornadas`):** `comando.jornada_id` quedó como columna sin FK porque la tabla `jornada` todavía no existe (`design.md` D8 del change 04-pipeline-comandos). Agregar la FK compuesta (`organizacion_id`, `jornada_id`) hacia `jornada` como parte de este change.

**Deuda nominada por el change 05 (`catalogo`) para el change 17 (`cobranzas`):** resolver la firma de `registro.HandlerFuncion` (hoy sin contexto: la plantilla D7 del change 04 pasa `sesion`/`reloj` como kwargs con `# type: ignore[arg-type]`) para que el despacho por lote (`_procesar_item_de_lote`) reciba `sesion`/`reloj` en forma tipada, antes de declarar `COBRANZA_REGISTRAR`, el primer tipo de comando que admite `OFFLINE` (`design.md` D3 del change 05-catalogo).

**Deuda nominada por el change 14 (`transferencias-y-ajustes`) para el change 15 (`jornadas`):** (1) aplicar STK-09 también a `STOCK_TRANSFERIR`, `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR` con vehículos tomados; hoy se puede transferir a un vehículo sin jornada y anular esa transferencia. (2) La carga del vehículo en la apertura (RUT-02) reutiliza `STOCK_TRANSFERIR`.

**Change 15 (`jornadas`) — deudas saldadas (ADR-049):** (1) `comando.jornada_id` y `stock_movimiento.jornada_id` tienen FK compuesta a `jornada` (deudas del 04 y del 09); la migración aborta si hay filas con `jornada_id`. (2) STK-09 se aplica en `registrar_movimientos` a todos los caminos que mueven stock: stock inicial (pantalla e importación), compra y su anulación, transferencia, ajuste y las dos anulaciones del 14 (deuda del 09 y deuda (1) del 14). (3) La carga del vehículo es un `STOCK_TRANSFERIR` aparte (deuda (2) del 14). (4) INV-16 queda cerrado: dos aperturas simultáneas con commits reales, tres índices únicos parciales y una máquina de estados de Hypothesis contra PostgreSQL. (5) La excepción de renovación de ADR-028 D9.3-B (deuda del 06b).

**Deudas nuevas del change 15:** **al change 17 (`cobranzas`):** el paso 4 de `02` §6.3 en el lote y `PERMISO_REVOCADO` (SYN-10); la foto de permisos al abrir la jornada, si hace falta; la validación de la jornada del sobre y la observación `JORNADA_LIBERADA` (RUT-09); y la firma de los handlers y el despacho por lote, que hoy tampoco funciona para los cuatro comandos de jornada (solo online). **Al change 21:** el bootstrap al abrir (RUT-03, SYN-11) y la apertura desde `/ruta`. **Al change 24:** el conteo como versión nueva de `JORNADA_RENDIR`, RUT-05, el destino de las jornadas cerradas sin conteo y el orden de bloqueo de la rendición (necesita la jornada `FOR UPDATE` antes que el stock y debe convivir con el nivel 5 `FOR SHARE` de los movimientos); el código de rendición dentro de `stock` sigue la convención de archivos propios por área (ADR-049, punto 2).

**Change 16 (`motor-de-descuentos`) — deudas saldadas (ADR-050):** la parte de descuentos de la deuda nominada por el change 13 al 18a ("completar los casos compartidos de §10.4 con descuentos") queda saldada con `dsc-05-descuentos.json` y `dsc-06-descuento-manual.json`; la parte de totales (VTA-04) sigue en el 18a. La migración `b5c6d7e8f9a0` baja borrando las dos tablas nuevas: pierde las reglas, sin pérdida de historia mientras ninguna venta las referencie.

**Deuda nominada por el change 14 para el change 24 (`rendicion`):** las diferencias de rendición (RUT-06) y el remanente (RUT-08) se escriben como movimientos `DIFERENCIA_RENDICION` por la única puerta; el motivo y la valorización siguen la regla de CST-12 (ADR-048).

**Deuda nominada por el change 14 para los changes 26 y 28 (reportes y auditoría):** (1) llevar el motivo a la fila de auditoría de `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` (hoy `motivo_id` nulo; el bus solo lo copia en tres comandos de stock). (2) Reportes de ajustes y pérdidas por motivo y consulta de auditoría con motivo. (3) Un mecanismo común para los tres puertos de registro de `catalogo` (ADR-023, ADR-025, verificador de stock).

**Deuda nominada por el change 14 para el change 17 (`cobranzas`):** a la deuda ya nominada sobre la firma de `registro.HandlerFuncion` se suma que los handlers de stock tampoco funcionan por el despacho por lote (`_procesar_item_de_lote` no les pasa `sesion` ni `reloj`); hoy no hay efecto porque son solo online.

**Deuda nominada por el change 14 (aceptada por el usuario el 2026-10-08):** el acceso a Ajustes desde el menú de `/admin` es un enlace dentro de la sección Stock (que se ofrece con `TRANSFERIR_STOCK`), así que un rol a medida con `AJUSTAR_STOCK` y sin `TRANSFERIR_STOCK` no llega desde el menú. Se deja así por ahora.

## 9. Hito 5 — Venta

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 18a | `venta-online-core` | Composición del pedido en cajas y unidades, precio desde lista, cobranza en el acto, confirmación atómica (stock + costo + cuenta corriente + cobranza), numeración por dispositivo; sin descuentos automáticos ni evaluación de crédito todavía | INV-01, INV-14, INV-07 |
| 18b | `venta-online-descuentos-credito` | Descuentos automáticos y manuales en la venta, evaluación de crédito con las tres políticas, PIN de supervisor, snapshot de crédito congelado. La pantalla de venta del vendedor le muestra su propio tope de descuento aplicable (p. ej. "Podés descontar hasta 5 %; más pide autorización"), recibido con el bootstrap (SYN-11). Hasta el 18b ningún usuario ve su tope; la pantalla "Topes por rol" es solo de administración (`ADMIN_USUARIOS` y `GESTIONAR_DESCUENTOS`). | INV-10 (snapshot inmutable), fixtures compartidos CRE-01 |
| 19 | `venta-anulacion` | Anulación con motivo, reversión de stock y cuenta corriente, decisión sobre el dinero cobrado | INV-19 |
| 20 | `nota-de-venta` | Generación del comprobante en el dispositivo, Web Share API, descarga de respaldo, reimpresión desde administración | VTA-13 |

**Deudas nuevas del change 16 (`motor-de-descuentos`):** **al change 18a (`venta-online-core`):** `ventas/domain/calculo.py` y `frontend/src/domain/calculo.ts` como orquestadores del bruto, los descuentos y los totales; casos compartidos de totales (VTA-04) sobre el formato de `dsc-05`. **Al change 18b (`venta-online-descuentos-credito`):** llamar al motor y a la evaluación del descuento manual (una evaluación por venta, con el `porcentaje_manual_maximo` que entrega el motor); la **pantalla de venta con un porcentaje manual general y uno propio por línea**, que muestra cuál lleva cada línea; una sola autorización y un solo motivo por venta, copiados a cada descuento `MANUAL`; verificar el PIN; persistir `venta_linea_descuento` con clave foránea compuesta a `regla_descuento`; DSC-09 y `DESCUENTO_DIFIERE`; la auditoría del descuento manual y de su autorización (AUD-01); el comando que define los parámetros del descuento manual, los motivos sembrados del ámbito `DESCUENTO_MANUAL` y la validación del motivo; que la pantalla de venta del vendedor le muestre **su propio tope aplicable** (p. ej. "Podés descontar hasta 5 %; más pide autorización"), recibido con el bootstrap (SYN-11) y no por `GET /yo` ni por el token (decisión del usuario, 2026-10-15: cada usuario no ve su tope hasta el 18b; "Topes por rol" queda solo para administración); y el comportamiento sin conexión (SYN-05, SYN-10). **Al change 21 (`pwa-y-bootstrap`):** el bootstrap incluye las reglas activas con sus alcances y los topes del usuario (SYN-11), y las líneas locales necesitan `categoria_id` y `marca_id` del producto. **Al change de usuarios y roles:** el tope propio por usuario. (La lectura de roles que incluye sus permisos se resolvió dentro del change 16, decisión del 2026-10-15, para que "Topes por rol" avise el tope 0 % solo en los roles con `DESCUENTO_MANUAL`.)

**Change 16b (`ayuda-contextual`) — deudas nuevas (ADR-051):** **al change 18b:** los "(?)" del descuento manual en la venta (porcentaje general y propio por línea, tope y autorización), reutilizando las claves y el tema `topes`. **Al change 21:** la ruta de ayuda en `/ruta` (`/ruta/ayuda/:tema`) con la misma página de tema, sin conexión; en la PWA instalada, "Ver más" navega a la ruta interna en lugar de abrir otra pestaña. **Duda abierta de `01`:** PRC-11 no dice de qué presentación sale el costo cuando hay "costos distintos por presentación"; la ayuda de esa señal no lo explica hasta que se precise.

**Deuda nominada por el change 05 (`catalogo`) para el change 18a (`venta-online-core`):** registrar el verificador de uso de presentaciones de `venta_linea` vía `catalogo/service.py::registrar_verificador_uso` (`design.md` D2 del change 05-catalogo), con una prueba que cite INV-18, y leer la presentación con `SELECT … FOR KEY SHARE` al congelar `unidades_presentacion` en la línea de venta (INV-18, PRC-23).

**Al terminar el hito 5, el sistema queda desplegado en un entorno de prueba con conexión.** No se usa con datos reales hasta la aceptación final: el sistema se entrega completo. El despliegue básico (27a) va aquí, no al final.

## 10. Despliegue temprano

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 27a | `despliegue-basico` | Docker Compose de producción con Caddy, PostgreSQL y backend; backups diarios con retención mínima; HTTPS; runbook de primera puesta en marcha | — |

**Adelantar el despliegue aquí tiene dos ventajas:** los errores de configuración aparecen antes de que haya datos reales, y la rutina de backups (con datos de prueba) queda ejercitada antes de la aceptación final, donde el criterio 12 pide restaurar uno.

## 11. Hito 6 — Offline

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 21 | `pwa-y-bootstrap` | Service worker con shell, base Dexie, endpoint y consumo de bootstrap, sesión local con PIN, almacenamiento persistente, pantallas de ruta leyendo de Dexie | — |
| 22a | `cola-confirmacion-local` | Confirmación local atómica en Dexie (venta + movimientos + cola en una transacción), generación local del comprobante, estado de sincronización visible | INV-01 (transacción Dexie) |
| 22b | `motor-sincronizacion` | Envío de lotes al servidor, bloqueo único con Web Locks, reintentos con espera exponencial, pantalla de estado (pendientes, última sync, errores) | INV-06 (doble sync no duplica) |
| 22c | `stock-credito-locales-y-conflictos` | Stock y crédito locales para operar sin señal, anulación offline (VTA-24), pantalla de conflictos y observaciones, métricas de tamaño de lote (`02` §17) | INV-17 (SYN-05) |
| 23 | `cobranza-offline` | Cobranza sin conexión y su efecto en el crédito disponible local | — |
| 24 | `rendicion-de-jornada` | Conteo físico, diferencias auditadas, resumen de jornada, devolución de remanente, cierre | RUT-05 (cola vacía antes de rendir) |
| 25 | `observaciones-y-revision` | Bandeja de observaciones pendientes, resolución con comentario, notificación de excesos detectados al sincronizar | SYN-08 (resolver no altera operación) |

**Deuda heredada del change 04 para el change 25 (`observaciones-y-revision`):** `01` §19 no resuelve qué permiso gobierna la revisión de un comando en cuarentena ni si un comando en cuarentena puede reenviarse — `design.md` D6 del change 04-pipeline-comandos dejó esta decisión explícitamente fuera de alcance. Este change debe registrar un ADR con esa decisión antes de implementar la resolución de cuarentena, y define `OBSERVACION_RESOLVER` (SYN-08).

**Probar en el teléfono real que va a usar el vendedor durante el change 21, no en el 28.** Si usa iPhone, las limitaciones de Safari (almacenamiento, Background Sync) aparecen ahí.

**Punto de validación en la calle después del change 24:** un día de ruta real con un vendedor antes de seguir con reportes. Lo que surja corrige los changes restantes sin presión.

**Si 22b o 22c se desbordan:** pausar, revisar el alcance y dividir antes de continuar. No apurar el change más riesgoso del proyecto.

## 12. Hito 7 — Cierre de la etapa 1

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 26 | `reportes-etapa-1` | Ventas por período con cantidades, importes y utilidad según permiso; rendición por vendedor y jornada; saldos de clientes y proveedores | REP-02, REP-04 |
| 27b | `backups-y-runbook-completo` | Retención completa (14 diarios, 8 semanales), copia a almacenamiento externo, restauración probada en entorno separado, runbook de restauración | — |
| 28 | `aceptacion-y-endurecimiento` | Suite Playwright con los 12 criterios de `00` §9, verificación diaria de consistencia, encabezados de seguridad y CSP, revisión de permisos de base de datos | INV-21 (todos los endpoints), todos los invariantes de `01` §20 cubiertos |

## 13. Fuera de este roadmap

- Etapa 2 (devoluciones parciales, fidelización, caja, reportes completos): se planifica cuando la etapa 1 lleve algunas semanas en uso.
- Módulo de facturación: roadmap propio, en paralelo a la etapa 2.
- Etapa 4 y evolución: ver `00` §6.

**Invariantes fuera de la etapa 1:** INV-09 (`importe_facturado ≤ total_neto`) e INV-20 (`facturar no genera deuda de mercadería`) pertenecen al módulo de facturación (FAC-01, FAC-07) y no tienen dueño en este roadmap. Se cubren en el roadmap del módulo de facturación. No son deuda de cobertura de la etapa 1.

## 14. Riesgos de secuencia

| Riesgo | Señal temprana | Respuesta |
| --- | --- | --- |
| El pipeline de comandos queda incompleto y alguna escritura lo esquiva | En el 18a aparece un endpoint que escribe sin pasar por el bus | Detener y corregir el 04 antes de seguir |
| Los datos reales no entran en el modelo | Errores masivos en el 10 | Ajustar modelo con ADR antes de construir encima |
| El motor de descuentos crece más de lo necesario | La proposal del 16 propone condiciones que el cliente no usa | Volver a las reglas reales; lo demás es etapa 2 |
| 22b o 22c superan holgadamente su estimación | Mitad del change sin entrega verificable | Dividir en ese punto, no al final |
| Limitaciones de PWA en iPhone aparecen tarde | — | Probar en dispositivo real durante el 21 |
| El cliente ve el sistema recién al final | — | Respetar los puntos de validación después del 13 y del 24 |
| Un invariante no tiene dueño asignado | La columna "invariantes que cierra" de las tablas no lo lista | Asignarlo al change más temprano que lo toca antes de implementar ese change |
| Sin despliegue real hasta el final | — | El 27a va después del 20; no negociable |

## 15. Cómo se trabaja cada change

1. Leer este documento (§4) para verificar que las dependencias están archivadas.
2. Leer los documentos de `docs/` y ADRs relevantes para el change.
3. Generar la proposal con `/opsx propose`.
4. **Revisar la proposal antes de implementar.** Si hay una decisión no resuelta, registrar un ADR primero.
5. Implementar siguiendo `tasks.md`.
6. Verificar con la definición de terminado (§2.1).
7. Archivar con `/opsx archive` y actualizar este documento.

No generar proposals de changes futuros hasta que el change actual esté archivado.
