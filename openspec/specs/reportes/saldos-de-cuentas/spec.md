# Reportes - Saldos de cuentas

## Purpose

Define el reporte de saldos actuales de las cuentas corrientes de clientes y proveedores, con filtros y totales: los de clientes para quien tiene `VER_REPORTES` y los de proveedores para quien tiene además `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD` (CC-04, INV-13; ADR-033; ADR-070).

## Requirements

### Requirement: Saldos de clientes

`GET /api/v1/reportes/saldos/clientes` (con `VER_REPORTES`; filtros: `vendedor_id` asignado, `estado` del cliente, `saldo` = `DEUDORES` | `A_FAVOR` | `CON_SALDO` | `TODOS`, por defecto `CON_SALDO`, y búsqueda por código o razón social) DEBE devolver por cliente: código, razón social, vendedor asignado, estado, límite de crédito, saldo y disponible (límite menos saldo; nulo sin límite), con el saldo actual de `saldo_cuenta` (cero si la cuenta no tiene movimientos), ordenados por saldo descendente (desempate por nombre e identificador) y paginados de a 50 con `pagina`, y los totales «adeudado» (suma de los saldos positivos) y «a favor» (suma de los negativos) de todo lo filtrado, no solo de la página. Los importes DEBEN viajar como string (CC-04, INV-03, INV-13; `design.md` D8, D14).

#### Scenario: El saldo es la suma de los movimientos
- **GIVEN** un cliente con una venta de `"1500.00"` y una cobranza de `"500.00"`
- **WHEN** se pide el reporte
- **THEN** el cliente informa saldo `"1000.00"`, igual a la suma en SQL de sus movimientos en `cuenta_movimiento`
- **Regla:** CC-04; INV-13

#### Scenario: Deudores y saldo a favor
- **GIVEN** un cliente con saldo `"1000.00"`, otro con `"-200.00"` y otro sin movimientos
- **WHEN** se pide con `saldo` = `CON_SALDO`
- **THEN** vienen los dos primeros, con total adeudado `"1000.00"` y total a favor `"-200.00"`
- **AND** con `DEUDORES` viene solo el primero, con `A_FAVOR` solo el segundo y con `TODOS` los tres (el tercero con saldo `"0.00"`)
- **Regla:** CC-04; glosario (saldo)

#### Scenario: Límite y disponible
- **GIVEN** un cliente con límite `"5000.00"` y saldo `"1000.00"`, y otro sin límite
- **WHEN** se pide el reporte
- **THEN** el primero informa disponible `"4000.00"` y el segundo disponible nulo
- **Regla:** glosario (crédito disponible); CRE-01

#### Scenario: Filtro por vendedor asignado
- **GIVEN** clientes de la cartera de `vendedor` y de `vendedor2`
- **WHEN** se filtra por `vendedor`
- **THEN** vienen solo los clientes asignados a `vendedor`
- **Regla:** ADR-060

#### Scenario: Vendedores del filtro
- **GIVEN** un vendedor cuyos clientes están solo en la página 3 y otro vendedor de otra organización con clientes
- **WHEN** se pide la página 1, con o sin filtros
- **THEN** la respuesta trae `vendedores` con todos los de la organización que tienen clientes asignados (`id` y `nombre`, por nombre), sin los de otra organización y sin depender de la página ni de los filtros
- **Regla:** ADR-060, INV-21

### Requirement: Saldos de proveedores

`GET /api/v1/reportes/saldos/proveedores` (con `VER_REPORTES` y además al menos uno de `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD`; sin esa regla completa, 403 `PERMISO_REQUERIDO`; filtros: `estado`, `saldo` como en clientes y búsqueda por nombre) DEBE devolver por proveedor nombre, estado y saldo actual de `saldo_cuenta` (el proveedor no tiene código; ADR-070, precisión 6), ordenados por saldo descendente (desempate por nombre e identificador) y paginados de a 50 con `pagina`, con los totales «adeudado» y «a favor» de todo lo filtrado (CC-04, INV-13; `design.md` D8, D14).

#### Scenario: Deuda con un proveedor
- **GIVEN** un proveedor con una compra a crédito de `"8000.00"` y un pago de `"3000.00"`
- **WHEN** `consulta` pide el reporte
- **THEN** el proveedor informa saldo `"5000.00"`, igual a la suma de sus movimientos
- **Regla:** CC-04; INV-13; CC-03

#### Scenario: Supervisor con la plantilla actual
- **GIVEN** `sup01`, con `VER_REPORTES` y sin `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` ni `VER_UTILIDAD`
- **WHEN** pide `GET /api/v1/reportes/saldos/proveedores`
- **THEN** recibe 403 `PERMISO_REQUERIDO`
- **AND** `GET /api/v1/reportes/saldos/clientes` le responde 200
- **Regla:** `01` §19; ADR-033; `design.md` D8

#### Scenario: Consulta/Dirección entra por `VER_UTILIDAD`
- **GIVEN** `consulta`, con `VER_REPORTES` y `VER_UTILIDAD`, sin `GESTIONAR_PROVEEDORES` ni `REGISTRAR_PAGO_PROVEEDOR`
- **WHEN** pide `GET /api/v1/reportes/saldos/proveedores`
- **THEN** recibe 200 con los saldos de los proveedores de su organización
- **Regla:** `01` §19; ADR-033; `design.md` D8

#### Scenario: Solo `VER_REPORTES` no alcanza
- **GIVEN** un usuario con un rol que tiene `VER_REPORTES` y ninguno de `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD`
- **WHEN** pide `GET /api/v1/reportes/saldos/proveedores`
- **THEN** recibe 403 `PERMISO_REQUERIDO`
- **AND** con `REGISTRAR_PAGO_PROVEEDOR` agregado a su rol recibe 200
- **Regla:** `01` §19; `design.md` D8

### Requirement: Las pestañas de saldos

La pestaña «Saldos de proveedores» DEBE mostrarse solo a quien cumple la regla del reporte de proveedores (`VER_REPORTES` y además `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD`), calculada en `/admin` con los permisos de `usePermisos()`; sin ella la pestaña no aparece, sin ningún texto en su lugar, y ocultarla no reemplaza la validación del servidor. Las pestañas «Saldos de clientes» y «Saldos de proveedores» DEBEN mostrar los filtros, los totales «Total adeudado» y «Total a favor», la tabla con la navegación entre páginas (`reportes/area-de-reportes`) y, un saldo negativo, con la marca «a favor». «Ver estado de cuenta» DEBE ofrecerse solo con `GESTIONAR_CLIENTES` (clientes) o `GESTIONAR_PROVEEDORES` (proveedores). Sin resultados: «Sin clientes para mostrar.» o «Sin proveedores para mostrar.» (`design.md` D8, D11, D12; SEG-06).

#### Scenario: Enlace al estado de cuenta según permiso
- **GIVEN** `ges01` (con `GESTIONAR_CLIENTES`) y `consulta` (sin él)
- **WHEN** cada uno abre «Saldos de clientes»
- **THEN** `ges01` ve «Ver estado de cuenta» en cada fila y `consulta` no
- **Regla:** `01` §19; ADR-033

#### Scenario: Sin resultados
- **WHEN** la búsqueda no encuentra clientes
- **THEN** se muestra «Sin clientes para mostrar.»
- **Regla:** CC-04

#### Scenario: Pestaña de proveedores según la regla compuesta
- **GIVEN** `sup01` (con `VER_REPORTES`, sin ninguno de los tres) y `consulta` (con `VER_REPORTES` y `VER_UTILIDAD`)
- **WHEN** cada uno abre «Reportes»
- **THEN** `consulta` ve la pestaña «Saldos de proveedores» y `sup01` no la ve (sí ve «Saldos de clientes»)
- **AND** un usuario de un rol con solo `VER_REPORTES` tampoco la ve
- **Regla:** `01` §19; ADR-027; SEG-06; `design.md` D8
