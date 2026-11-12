# Change 10-importacion-inicial

## Qué resuelve este change

Permite poner en marcha la organización desde planillas (CSV/Excel): alta masiva de proveedores, productos con sus presentaciones, clientes y costos informados, y carga de stock inicial valorizado y saldos iniciales, con un informe de errores por fila.

## Why

`00` §9 (criterio 1 de la etapa 1) exige importar productos, clientes y proveedores y cargar stock y saldos iniciales; `04` §4 lo pone después de 06, 07 y 09, cuyos servicios ya existen. Sin este change la carga inicial se hace pantalla por pantalla, y `04` §14 señala que es el punto donde se descubre si los datos reales entran en el modelo.

## What Changes

- **Módulo nuevo `importacion`** (`03` §3) que lee la planilla, valida cada fila y llama **solo a los `service.py` existentes** (sin reimplementar reglas): `proveedores::crear_proveedor`, `catalogo::crear_producto`, `clientes::crear_cliente`, `proveedores::informar_costos`, `stock::registrar_stock_inicial`, `cuentas_corrientes::registrar_saldo_inicial` (deudas nominadas por 06, 08 y 09 en `04` §6).
- **Tabla `importacion`** (`03` §13) con FK compuestas, `CHECK` de catálogo de `tipo` y columnas de operación.
- **Comando `IMPORTACION_REGISTRAR`** (solo `ONLINE`, permiso `IMPORTAR_DATOS`, `01` §19, ADR-033, ADR-036), idempotente por `operation_id` (INV-06), auditado una vez por el bus (ADR-022).
- **Informe de errores por fila**: número de fila de la planilla, columna, código de dominio estable y mensaje.
- **Plantillas descargables**, **historial** y **pantalla `/admin`** de importación.
- **Validaciones faltantes en el alta por pantalla** (agregado el 2026-10-01 a pedido del usuario, hallado en el lote 2): `PRODUCTO_CREAR` rechaza nombre, unidad base y nombre de presentación vacíos; `CLIENTE_CREAR` rechaza un `estado_facturacion_default` fuera de `NO_REQUIERE`/`PENDIENTE` con error de dominio (hoy termina en 500 por el `CHECK` de la base).

## Decisiones abiertas (bloqueantes)

`docs/` no resuelve varias decisiones y hay dos contradicciones entre documentos: ver `design.md` (D0 a D14), con opción recomendada y ejemplo. **No se implementa nada hasta su aprobación (tarea 0.1).** Clave: atomicidad (D1), lectura del archivo (D2), claves naturales (D4), fecha de corte (D7, heredada del 09) y costos frente a CST-05 (D8). Varias requieren **ADR pendiente**.

## No incluye

- Importación de **listas de precios** (`PRECIOS` en `03` §13 y "listas" en `00` §6.1): no existen hasta el change 13 (D9).
- Modificación o actualización masiva de registros ya existentes (solo altas, D6).
- Importación de categorías, marcas, ubicaciones o usuarios (se crean por pantalla).
- Importadores genéricos para otras organizaciones (`00` §6.4, etapa 4).
- Carga de stock inicial o saldos pasada la primera operación (STK-10, CC-08 lo prohíben).

## Reglas e invariantes

- Implementa: CAT-01 a CAT-03, CAT-06, CLI-01, CLI-05, CST-01, CST-02, CST-05, STK-10, CST-11, CST-12, CC-08, TR-01 a TR-05, TR-10.
- **INV-01**: una importación se registra completa o no se registra (D1); prueba con falla inyectada a mitad de archivo.
- **INV-03 / INV-04**: ningún valor pasa por `float` (D3); cantidades enteras.
- **INV-06**: mismo archivo y mismo `operation_id` no duplica efectos.
- **INV-12 / INV-13 / INV-18**: se mantienen porque solo se escribe por los servicios de 06, 08 y 09.
- **INV-02 / INV-21**: toda clave natural se resuelve dentro de la organización del token; un código ajeno es "no encontrado" en la fila.

**Fixtures compartidos:** no se agregan ni modifican (CST-02 y CST-11 los calculan los servicios existentes), salvo que D13 elija costo por caja.

## Capabilities

### New Capabilities

- `importacion/planillas`: formato de archivo, encabezados, lectura de celdas, conversión exacta de números, fechas y booleanos, límites y plantillas.
- `importacion/importacion-de-maestros`: proveedores, productos con presentaciones, clientes y costos informados.
- `importacion/puesta-en-marcha`: stock inicial valorizado y saldos iniciales de clientes y proveedores.
- `importacion/registro-de-importaciones`: comando, permiso, atomicidad, idempotencia, informe de errores e historial.
- `importacion/administracion-de-importaciones`: pantalla de `/admin`.

### Modified Capabilities

Los servicios reutilizados no cambian de comportamiento, salvo dos validaciones de entrada que faltaban (agregado 2026-10-01): alta de producto con textos obligatorios vacíos y alta de cliente con `estado_facturacion_default` inválido. Ambos casos hoy terminan en datos inválidos o en un 500; pasan a ser errores de dominio. Actualizar las specs vigentes de catálogo y clientes que correspondan.

## Impact

- Backend: módulo `importacion` nuevo, migración de `importacion`, contrato de import-linter (actualiza `02` §5.3, D10), posible dependencia para `.xlsx` (D2).
- API: `POST /api/v1/importaciones/{tipo}`, `GET /api/v1/importaciones`, `GET /api/v1/importaciones/plantillas/{tipo}`.
- Frontend: `frontend/src/areas/admin/importacion/`.
- Docs (con aprobación): `02` §5, `01` CST-05 (D8), ADR pendientes.
