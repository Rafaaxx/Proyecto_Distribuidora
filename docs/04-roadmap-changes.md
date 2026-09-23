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
- **Tamaño:** entre medio día y tres días de trabajo. Un change más grande se divide.
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
| 07 clientes | 04 |
| 08 cuentas-corrientes | 04 |
| 09 stock-y-costeo | 05, 08 |
| 10 importacion-inicial | 06, 07, 09 |
| 11 compras-y-deuda-proveedor | 06, 09 |
| 12 pagos-a-proveedores | 08, 11 |
| 13 listas-de-precios | 06, 09 |
| 14 transferencias-y-ajustes | 09 |
| 15 jornadas | 09, 14 |
| 16 motor-de-descuentos | 05, 13 |
| 17 cobranzas | 07, 08 |
| 18a venta-online-core | 07, 08, 09, 13, 15, 17 |
| 18b venta-online-descuentos-credito | 16, 18a |
| 19 venta-anulacion | 18b |
| 20 nota-de-venta | 18b |
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
| 06 | `proveedores-y-costos-informados` | Proveedores, carga de costo en cualquier presentación con o sin IVA y bonificación, vigencias, historial, costo base derivado | — |
| 07 | `clientes` | Ficha completa, estados, lista asignada, campos de crédito sin evaluación, consumidor final | — |
| 08 | `cuentas-corrientes` | `cuenta_movimiento`, `saldo_cuenta`, comando de saldo inicial, estado de cuenta de cliente y proveedor, bloqueo de fila de saldo | INV-13 (Hypothesis), INV-05 (solo inserción) |
| 09 | `stock-y-costeo` | Ubicaciones, `stock_saldo`, `stock_movimiento`, `costo_producto` con `stock_total`, `costo_producto_mov`, comando de stock inicial valorizado, kardex, orden de bloqueo global (`02` §7.3) | INV-12 (Hypothesis), INV-04 |
| 10 | `importacion-inicial` | Importación de productos, clientes, proveedores y costos desde CSV/Excel; stock inicial y saldos iniciales; informe de errores por fila | — |

**CAT-03 e INV-18 cerrados por el change 05 (`catalogo`, verificación grupo 13):** CAT-03 (exactamente una presentación de referencia por producto, activa y usada en venta) queda garantizado en tres capas — el servicio (`catalogo/service.py`, validado antes de escribir), el índice único parcial `ux_presentacion__referencia` (`03` §5, que rechaza una segunda referencia escrita por fuera del servicio, incluso ante escrituras concurrentes) y el `CHECK` `ck_presentacion__referencia_venta` (una referencia siempre tiene `usar_en_venta = true`). Confirmado con `backend/tests/unit/test_catalogo_domain_presentaciones.py` (servicio, incluida la propiedad Hypothesis "todo conjunto aceptado tiene exactamente una referencia de venta"), `backend/tests/integration/test_catalogo_migracion.py::test_cat03_ux_presentacion_referencia_rechaza_segunda_referencia_directa` y `test_cat03_ck_referencia_venta_rechaza_referencia_sin_venta` (base), y `backend/tests/concurrency/test_catalogo_concurrencia.py::test_dos_cambios_de_referencia_simultaneos_dejan_exactamente_una_referencia` (dos transacciones con commits reales). INV-18 (las unidades base de una presentación ya usada no cambian) se resuelve con el puerto de verificadores de uso de `design.md` D2 del change 05-catalogo (ver ADR-023, vigente): `PRESENTACION_MODIFICAR` consulta a todos los verificadores registrados y rechaza con `UNIDADES_CONGELADAS` si alguno confirma uso. Confirmado con `backend/tests/unit/test_catalogo_domain_presentaciones.py::test_inv18_cambiar_unidades_de_presentacion_usada_es_congelado`, `backend/tests/integration/test_catalogo_service.py::test_inv18_cambiar_unidades_de_presentacion_usada_es_congelado` y, en la pantalla, `frontend/tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx` (mensaje del servidor mostrado al usuario). En este change no existe ningún módulo de operaciones (nace en 06, 11 y 18a): la lista de verificadores está vacía en producción y las pruebas registran uno de prueba. Este cierre no se reabre por las deudas nominadas abajo (que solo piden a los changes futuros registrar su propio verificador); es un cierre del mecanismo, no del universo de verificadores registrados.

**Deuda nominada por el change 05 (`catalogo`) para el change 06 (`proveedores-y-costos-informados`):** completar la FK compuesta y el `NOT NULL` de `producto.proveedor_id` (hoy columna `uuid` nulable y sin FK, `design.md` D1 del change 05-catalogo) — FK `NOT VALID` + `VALIDATE`, completar los productos sin proveedor y recién entonces `SET NOT NULL`, antes de que el change 10 cargue datos reales. Además, decidir si `costo_informado` debe registrar su verificador de uso de presentaciones (INV-18, `design.md` D2 del change 05-catalogo): ¿un costo informado cuenta como "uso" que congela las unidades de la presentación? `01` no lo resuelve.

**Al terminar el hito 2, cargar los datos reales de la distribuidora.** Los problemas de datos aparecen temprano y sin presión de venta. Es el momento más barato para descubrirlos.

## 7. Hito 3 — Compras, costos y precios

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 11 | `compras-y-deuda-proveedor` | Compra con líneas en cualquier presentación, ingreso de stock, recálculo de promedio, deuda o pago de contado, anulación con reversión | INV-01 (atómica), INV-07 (al menos una línea), CST-11 |
| 12 | `pagos-a-proveedores` | Pago con varios medios, anulación, saldo de proveedor | INV-08 |
| 13 | `listas-de-precios` | Listas, reglas de margen con precedencia, redondeo, generación de borrador, publicación, versiones anteriores, resolución de precio | INV-11 (versión inmutable), fixtures compartidos PRC-22 |

**Deuda nominada por el change 05 (`catalogo`) para el change 11 (`compras-y-deuda-proveedor`):** registrar el verificador de uso de presentaciones de `compra_linea` vía `catalogo/service.py::registrar_verificador_uso` (`design.md` D2 del change 05-catalogo), con una prueba que cite INV-18.

**Deuda nominada por el change 05 (`catalogo`) para el change 13 (`listas-de-precios`):** decidir por ADR qué pasa al cambiar la presentación de referencia de un producto con precios publicados — `precio_item` no congela las unidades de referencia, y el cambio altera el significado de `precio_referencia` (PRC-10, PRC-22; `design.md` D5 del change 05-catalogo). El ADR debe optar entre bloquear el cambio de referencia o congelar las unidades en `precio_item`.

**Punto de validación con el cliente después del change 13:** mostrarle cómo un costo nuevo genera una lista y qué precios salen. Es el momento más barato para corregir márgenes o redondeos.

## 8. Hito 4 — Operación de ruta

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 14 | `transferencias-y-ajustes` | Transferencia entre ubicaciones, ajuste con motivo, ambos atómicos | INV-15 |
| 15 | `jornadas` | Apertura con toma, bloqueo de ubicación, cierre, liberación auditada | INV-16 (dos aperturas simultáneas) |
| 16 | `motor-de-descuentos` | Reglas de volumen, alcance, prioridad, acumulabilidad; motor en Python y TypeScript; descuento manual con tope y autorización; fixtures compartidos DSC-05 | — |
| 17 | `cobranzas` | Cobranza independiente con varios medios, anulación, efecto en cuenta corriente | INV-08, CC-05 |

**Deuda heredada del change 04 para el change 15 (`jornadas`):** `comando.jornada_id` quedó como columna sin FK porque la tabla `jornada` todavía no existe (`design.md` D8 del change 04-pipeline-comandos). Agregar la FK compuesta (`organizacion_id`, `jornada_id`) hacia `jornada` como parte de este change.

**Deuda nominada por el change 05 (`catalogo`) para el change 17 (`cobranzas`):** resolver la firma de `registro.HandlerFuncion` (hoy sin contexto: la plantilla D7 del change 04 pasa `sesion`/`reloj` como kwargs con `# type: ignore[arg-type]`) para que el despacho por lote (`_procesar_item_de_lote`) reciba `sesion`/`reloj` en forma tipada, antes de declarar `COBRANZA_REGISTRAR`, el primer tipo de comando que admite `OFFLINE` (`design.md` D3 del change 05-catalogo).

## 9. Hito 5 — Venta

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 18a | `venta-online-core` | Composición del pedido en cajas y unidades, precio desde lista, cobranza en el acto, confirmación atómica (stock + costo + cuenta corriente + cobranza), numeración por dispositivo; sin descuentos automáticos ni evaluación de crédito todavía | INV-01, INV-14, INV-07 |
| 18b | `venta-online-descuentos-credito` | Descuentos automáticos y manuales en la venta, evaluación de crédito con las tres políticas, PIN de supervisor, snapshot de crédito congelado | INV-10 (snapshot inmutable), fixtures compartidos CRE-01 |
| 19 | `venta-anulacion` | Anulación con motivo, reversión de stock y cuenta corriente, decisión sobre el dinero cobrado | INV-19 |
| 20 | `nota-de-venta` | Generación del comprobante en el dispositivo, Web Share API, descarga de respaldo, reimpresión desde administración | VTA-13 |

**Deuda nominada por el change 05 (`catalogo`) para el change 18a (`venta-online-core`):** registrar el verificador de uso de presentaciones de `venta_linea` vía `catalogo/service.py::registrar_verificador_uso` (`design.md` D2 del change 05-catalogo), con una prueba que cite INV-18, y leer la presentación con `SELECT … FOR KEY SHARE` al congelar `unidades_presentacion` en la línea de venta (INV-18, PRC-23).

**Al terminar el hito 5, el sistema puede usarse en producción con conexión.** El despliegue básico (27a) va aquí, no al final.

## 10. Despliegue temprano

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 27a | `despliegue-basico` | Docker Compose de producción con Caddy, PostgreSQL y backend; backups diarios con retención mínima; HTTPS; runbook de primera puesta en marcha | — |

**Adelantar el despliegue aquí tiene dos ventajas:** los errores de configuración aparecen cuando hay poco dato histórico, y los backups empiezan a acumularse antes de la aceptación final, donde el criterio 12 pide restaurar uno.

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
