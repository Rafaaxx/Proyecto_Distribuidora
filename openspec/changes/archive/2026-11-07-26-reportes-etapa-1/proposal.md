# Change 26-reportes-etapa-1

## Qué resuelve este change

Dirección y administración ven en `/admin`, en solo lectura, las ventas del período (con cantidades, importes y utilidad según permiso), la rendición por vendedor y jornada, y los saldos de clientes y proveedores, calculados en la base desde las operaciones registradas (REP-01).

## Why

`04` §12 (fila 26; REP-02, REP-04) y `00` §9 criterio 11 («el reporte de ventas del período concilia con las operaciones registradas»). El permiso `VER_REPORTES` existe desde el change 03 y no abre nada: el rol Consulta/Dirección no tiene hoy ninguna pantalla (ADR-033, ADR-036 le prometen los saldos y el stock por reportes). Seis changes dejaron deudas «al 26».

## What Changes

- **Módulo `reportes`** (D6): solo lectura, SQL con agregaciones en la base (SQLAlchemy Core sobre las tablas de los demás módulos, `02` §5.2 excepción), sin comandos, sin vistas ni migración.
- **Período** (D1): fechas de negocio inclusivas en la zona de la organización (TR-04); sin período, el mes en curso; hasta 366 días.
- **Ventas por período** (D2 a D5): resumen, por día, por vendedor y por producto (cajas equivalentes, unidades base y detalle por presentación, REP-03), con los valores congelados (REP-05); las anuladas fuera de los totales y aparte (REP-02); costo vendido y utilidad solo con `VER_UTILIDAD` (REP-04), sin las líneas sin costo, que se informan aparte.
- **Rendiciones** (D7): jornadas del período por vendedor con ventas, anuladas, cobrado por medio, faltantes y sobrantes (valor con `VER_COSTOS`), totales por vendedor y el resumen de RUT-07 de cada jornada.
- **Saldos** (D8 = B): saldo actual de clientes (con límite y disponible) y de proveedores, con filtros y totales; los de clientes con `VER_REPORTES`, los de proveedores con `VER_REPORTES` y además `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD` (el Supervisor no los ve con la plantilla actual).
- **Observaciones por vendedor** (D9) y **ajustes por motivo** (D10): deudas del 25 y del 14.
- **Pantallas, textos y ayuda** (D11 a D13): sección «Reportes» con seis pestañas. Sin exportar (etapa 2).
- **Paginación y orden** (D14, pedido de la prueba manual del 2026-11-07): las listas largas («Por día», «Por producto», anuladas, jornadas, saldos de clientes y de proveedores) se paginan en el servidor de a 50 filas con «Anterior» / «Página {n} de {m}» / «Siguiente», con los totales de todo el período; jornadas, anuladas y «Por día» con lo más reciente primero. Excepción acotada al cursor de `02` §11 (Lote 7).
- **Sin migración, sin permisos nuevos (D8 = B combina permisos existentes en una regla de `01` §19), sin Dexie.** Regenerar `openapi` y `schema.gen.ts`. **ADR-070** (*Propuesto*) y `propuesta-docs.md`.

## Deudas heredadas y cómo se saldan

| Origen | Deuda | Cómo |
| --- | --- | --- |
| 12 / ADR-046 | Reporte de saldos de proveedores | D8 |
| 14 / ADR-048 punto 9 | Reportes de ajustes y pérdidas por motivo | D10; el motivo en la auditoría de `COMPRA_ANULAR`/`PAGO_PROVEEDOR_ANULAR` y el mecanismo común de puertos se reasignan al **28** |
| 18a / ADR-054 | Utilidad (fuera del detalle de la venta) y líneas sin costo aparte | D5 |
| 19 / ADR-058 | Excluir las anuladas e informarlas aparte | D2 |
| 24 / ADR-068 | Rendición por vendedor y jornada sobre `rendicion_linea` y el dinero por jornada | D7 |
| 25 / ADR-069 | Observaciones y rechazos por vendedor (`02` §20) | D9 |
| ADR-033, ADR-036 | Saldos para Consulta/Dirección | D8 (el stock sigue por `TRANSFERIR_STOCK`; no entra) |

## Decisiones

`design.md` D0 a D13, **aprobadas el 2026-11-06** (tarea 0.1): todas en A salvo **D8 = B**. Textos y ayudas de D12 y D13 aprobados el mismo día (tarea 0.2). **D14** (paginación y orden) y sus tres textos, aprobados el 2026-11-07 tras la prueba manual. **ALTAS: D2, D3, D5, D7, D8.** Ninguna CRÍTICA (solo lectura).

## No incluye

Exportación e impresión; utilidad por producto, cliente, proveedor o categoría, comparativos y filtros guardados (REP-06, etapa 2); saldo a una fecha pasada y antigüedad de deuda; facturación de los últimos 12 meses (ADR-045, sin change); stock en reportes; la consulta de auditoría (28).

## Reglas e invariantes

- **REP-01, REP-02, REP-03, REP-04, REP-05, TR-04, CC-04, RUT-07, CAT-08 (cajas equivalentes, glosario), `01` §19.**
- **INV-02/INV-21:** todo filtrado por `organizacion_id` del token; jornada ajena, 404. **INV-03:** importes, costos y cajas equivalentes como string. **INV-10/REP-05:** propiedad con SQL: cambiar precios y costos después no cambia el reporte. **INV-13:** el saldo informado es la suma de movimientos. **INV-14:** total = neto + IVA en los totales. **Criterio 11:** propiedad que concilia el reporte con las ventas confirmadas del período.
- Sin cálculo compartido nuevo ni fixture de cálculo: el cálculo lo hace solo la base y el frontend no recalcula.

## Capabilities

### New Capabilities

- `reportes/area-de-reportes`: acceso, período y aislamiento comunes.
- `reportes/ventas-por-periodo`: ventas, cantidades, anuladas y utilidad.
- `reportes/rendicion-por-vendedor`: jornadas y vendedores.
- `reportes/saldos-de-cuentas`: clientes y proveedores.
- `reportes/observaciones-por-vendedor`: avisos y rechazos por vendedor.
- `reportes/ajustes-por-motivo`: ajustes y diferencias de rendición.

### Modified Capabilities

- `sistema/ayuda-contextual`: claves nuevas de los reportes.

## Impact

Backend: `modules/reportes/` (nuevo), `stock/service.py` (expone el resumen de la jornada), `main.py` (router), contratos de `import-linter`, ratchet de permiso por ruta. Frontend: `areas/admin/reportes/`, `features/reportes/`, `features/identidad/secciones.ts`, `ayuda/textos.ts`, `api/schema.gen.ts`. Docs al archivar.
