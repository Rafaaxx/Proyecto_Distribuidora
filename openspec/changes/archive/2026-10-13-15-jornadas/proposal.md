# Change 15-jornadas

## Qué resuelve este change

Crea la jornada: el vendedor abre, toma una ubicación en forma exclusiva, y la jornada se rinde, se cierra o se libera con auditoría. Mientras la ubicación está tomada, el libro de stock solo acepta movimientos de esa jornada (STK-09). Cierra INV-16.

## Why

`04` §8 (hito 4). Hoy `requiere_toma` es un indicador que nadie valida (ADR-038): cualquiera con `TRANSFERIR_STOCK` mueve stock de un vehículo ajeno, y `comando.jornada_id` y `stock_movimiento.jornada_id` no tienen tabla ni clave foránea. La venta (18a), la cobranza (17) y la rendición (24) necesitan la jornada.

## What Changes

- **Cuatro comandos solo `ONLINE`** (`02` §6.5), por el bus: `JORNADA_ABRIR` (`ABRIR_JORNADA`, RUT-01, RUT-03), `JORNADA_RENDIR` y `JORNADA_CERRAR` (`RENDIR_JORNADA`, RUT-08) y `JORNADA_LIBERAR` (`LIBERAR_UBICACION`, con motivo, RUT-09). Máquina de `01` §18: `ABIERTA → EN_RENDICION → CERRADA`; `ABIERTA/EN_RENDICION → LIBERADA`.
- **Tabla `jornada`** (`03` §9) con el índice único parcial que garantiza INV-16; la segunda apertura falla por la restricción (`02` §7.5).
- **Claves foráneas heredadas:** `stock_movimiento.jornada_id` (deuda del 09) y `comando.jornada_id` (deuda del 04), compuestas con `organizacion_id`. Un comando que nombra una jornada inexistente se rechaza (SYN-06).
- **STK-09 en la única puerta del libro — BREAKING para quien mueve stock de un vehículo tomado:** transferencia, sus anulaciones, ajuste, stock inicial, compra e importación sobre una ubicación tomada se rechazan con `UBICACION_TOMADA`, salvo que el movimiento sea de la jornada que la tomó o el usuario tenga `LIBERAR_UBICACION` (deudas del 09 y del 14).
- **Carga del vehículo (RUT-02):** reutiliza `STOCK_TRANSFERIR`, antes o después de abrir.
- **Ubicación tomada:** no se desactiva ni cambia de tipo o de indicador de toma.
- **Sesión (gobernanza crítica, ADR-028 D9.3-B):** un usuario o rol inactivo renueva la sesión solo si ese dispositivo tiene una jornada suya no cerrada.
- **Auditoría (gobernanza crítica):** la liberación lleva su motivo en la fila del bus, y el movimiento hecho por excepción con `LIBERAR_UBICACION` queda señalado.
- **Lecturas y pantallas `/admin`:** jornadas (listado, apertura, detalle, rendir, cerrar, liberar) y ubicación tomada visible en Stock.
- **Fixtures compartidos:** ninguno; no hay cálculo de precios, descuentos ni costos.

## Decisiones (bloqueantes)

`design.md` D0 a D22, **todas aprobadas el 2026-10-09** (opción A en todas; D1 como variante de A, ver abajo). De negocio y sin resolver en `docs/`: cierre sin rendición (D2), dónde se abre (D3), alcance de STK-09 (D6, D7), motivos de liberación (D13), lecturas (D15) y jornada `LIBERADA` frente a la renovación (D18). Requieren **ADR-049**.

**Organización del código (D1, variante de A):** las jornadas viven dentro del módulo `stock` (`02` §5.1), pero con archivos propios para su lógica (`stock/jornadas_casos.py`), su acceso a datos (`stock/jornadas_repository.py`) y sus handlers (`stock/jornadas_commands.py`), más `stock/domain/jornadas.py`; `stock/service.py` sigue siendo la única puerta pública y solo delega. Los archivos de movimientos no se parten. Es una excepción a la disposición de un archivo por rol de `CLAUDE.md` §7 que ADR-049 registra como convención para módulos grandes.

## Tamaño

Cuatro lotes. Supera `04` §2; D0 ofrece dividir en 15a/15b.

## No incluye

Bootstrap (change 21). Conteo físico, diferencias, resumen y remanente (RUT-05 a RUT-08, change 24). Venta y cobranza de ruta (17, 18a). Permisos por comando del lote y `PERMISO_REVOCADO` (SYN-10; pasa al 17, D17). Observación `JORNADA_LIBERADA` (D21). Firma de los handlers por lote (17, D22). Pantallas de `/ruta` (21). Baja de usuarios y roles.

## Invariantes

- **INV-16** (lo cierra): índice único parcial, prueba de base, propiedad Hypothesis y dos aperturas simultáneas con commits reales.
- **INV-01** (falla inyectada), **INV-05** (`jornada` sin `DELETE`, `UPDATE` solo de transición), **INV-12** (un rechazo por toma no deja rastro), **INV-02, INV-06, INV-21**.

## Capabilities

### New Capabilities

- `stock/jornadas`: apertura con toma, estados, rendición mínima, cierre, liberación auditada y consultas (RUT-01, RUT-03, RUT-08, RUT-09, INV-16).
- `stock/toma-de-ubicacion`: quién puede mover stock de una ubicación tomada (STK-09, RUT-02, RUT-04).

### Modified Capabilities

- `stock/libro-de-stock`: el movimiento referencia una jornada existente.
- `stock/ubicaciones`: una ubicación tomada no se desactiva ni cambia tipo o toma.
- `stock/administracion-de-stock`: pantallas de jornadas y ubicación tomada visible.
- `sistema/pipeline-de-comandos`: jornada inexistente en el sobre.
- `identidad/autenticacion-y-sesion`: excepción de renovación con jornada no cerrada.

## Impact

Backend: `stock/` (con los archivos nuevos `jornadas_repository.py`, `jornadas_casos.py`, `jornadas_commands.py` y `domain/jornadas.py`), `pyproject.toml` (import-linter), `main.py` (registro de handlers), `sync/` (bus, `comando`), `identidad/service.py` (renovación), `proveedores/` e `importacion/` (permiso hacia la puerta), `app/commands/auditoria.py`, siembra, una migración, ratchets. Frontend: `areas/admin/stock/`, `features/stock/`, `domain/stock/`. Docs `01` a `04` y ADR-049 al cierre. Gobernanza **media** (stock) con piezas **críticas** (sesión, auditoría) y **altas** (bus), con revisión explícita.
