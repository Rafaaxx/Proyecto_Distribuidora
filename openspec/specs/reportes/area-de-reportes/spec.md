# Reportes - Area de reportes

## Purpose

Define lo común a todos los reportes de la etapa 1: quién entra, cómo se elige el período, que todo sale de la base con los valores registrados y que nada cruza organizaciones (REP-01, TR-04, INV-21).

## Requirements

### Requirement: Los reportes se leen con `VER_REPORTES` y no escriben nada

Todo endpoint bajo `/api/v1/reportes` DEBE exigir `VER_REPORTES` (403 `PERMISO_REQUERIDO` sin él; el de saldos de proveedores exige además la regla de `reportes/saldos-de-cuentas`, `design.md` D8) y NO DEBE escribir ninguna tabla ni tomar bloqueos. Las cifras DEBEN calcularse en la base con agregaciones SQL desde las operaciones registradas, nunca sumando filas en Python ni leyendo cifras mantenidas a mano (REP-01; `02` §14; `design.md` D6).

#### Scenario: Sin permiso de reportes
- **GIVEN** el usuario `vendedor`, sin `VER_REPORTES`
- **WHEN** pide `GET /api/v1/reportes/ventas`
- **THEN** recibe 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19 (VER_REPORTES); SEG-06

#### Scenario: Consulta/Dirección entra a los reportes
- **GIVEN** el usuario `consulta`, con `VER_REPORTES` y `VER_UTILIDAD`
- **WHEN** pide cualquiera de los seis reportes
- **THEN** recibe 200 con las cifras de su organización
- **Regla:** `01` §19; ADR-033

#### Scenario: Consultar un reporte no cambia nada
- **GIVEN** una base con ventas, cobranzas, jornadas y ajustes
- **WHEN** se piden todos los reportes
- **THEN** ninguna tabla cambia (mismas filas y mismos valores antes y después)
- **Regla:** REP-01; INV-05

### Requirement: El período usa fechas de negocio con el mes en curso por defecto

Los reportes con período DEBEN recibir `desde` y `hasta` opcionales (`aaaa-mm-dd`, inclusivas, en la zona horaria de la organización) y asignar cada operación por su `occurred_at` convertido a esa zona. Sin `desde` ni `hasta` DEBEN usar del día 1 del mes de la fecha de negocio de hoy hasta hoy, según el reloj del servidor; con solo `desde`, hasta hoy; con solo `hasta`, desde el día 1 de ese mes. Un rango invertido DEBE rechazarse con `RANGO_DE_FECHAS_INVALIDO` (422) y uno de más de 366 días con `PERIODO_DEMASIADO_LARGO` (422). La respuesta DEBE devolver el período aplicado y la zona horaria (TR-04, REP-02; `design.md` D1).

#### Scenario: Mes en curso por defecto
- **GIVEN** la organización en `America/Argentina/Mendoza` y el reloj en el 2026-11-06 a las 10:00 locales
- **WHEN** se pide el reporte de ventas sin fechas
- **THEN** el período aplicado es del 2026-11-01 al 2026-11-06
- **Regla:** TR-04; REP-02

#### Scenario: Venta cerca de la medianoche
- **GIVEN** una venta con `occurred_at` 2026-11-01T02:30Z (el 31 de octubre a las 23:30 en Mendoza)
- **WHEN** se piden las ventas del 2026-11-01 al 2026-11-30
- **THEN** la venta no entra; entra en el período de octubre
- **Regla:** TR-04; REP-02

#### Scenario: Rango invertido
- **WHEN** se pide un período con `desde` 2026-11-10 y `hasta` 2026-11-01
- **THEN** se responde 422 `RANGO_DE_FECHAS_INVALIDO`
- **Regla:** TR-04

#### Scenario: Período demasiado largo
- **WHEN** se pide un período del 2025-01-01 al 2026-01-02 (367 días)
- **THEN** se responde 422 `PERIODO_DEMASIADO_LARGO`
- **AND** del 2025-01-01 al 2026-01-01 (366 días) se acepta
- **Regla:** `design.md` D1

### Requirement: Ningún reporte cruza organizaciones

Toda consulta de un reporte DEBE filtrar por el `organizacion_id` del token. Un recurso de otra organización pedido por su identificador DEBE responder 404, y un filtro con un identificador de otra organización (vendedor, por ejemplo) DEBE devolver el reporte vacío, nunca datos ajenos (INV-02, INV-21).

#### Scenario: Datos de otra organización
- **GIVEN** dos organizaciones con ventas, saldos y jornadas en el mismo período
- **WHEN** un usuario de la primera pide cada reporte
- **THEN** solo ve cifras de la primera
- **Regla:** INV-02; INV-21

#### Scenario: Filtro con un vendedor ajeno
- **WHEN** un usuario filtra el reporte de ventas por el identificador de un vendedor de otra organización
- **THEN** recibe el reporte vacío, sin error ni datos ajenos
- **Regla:** INV-21

### Requirement: Las listas largas se paginan en el servidor de a 50 filas

Las listas «Por día», «Por producto» y «Ventas anuladas del período» del reporte de ventas, la lista de jornadas de las rendiciones y las de saldos de clientes y de proveedores DEBEN paginarse en el servidor de a **50 filas** por página, con un orden estable que termine en una clave única, y viajar en el sobre `filas`, `pagina`, `tamano` (50), `total_filas` y `paginas` (`ceil(total_filas / 50)`, 0 sin filas). La página DEBE pedirse con un entero desde 1 (`pagina` en rendiciones y saldos; `pagina_por_dia`, `pagina_por_producto` y `pagina_anuladas` en ventas, independientes entre sí), por defecto 1; 0 o un número negativo DEBE responder 422; una página posterior a la última DEBE devolver `filas` vacías con `total_filas` y `paginas` reales. El tamaño NO DEBE poder elegirlo el cliente. Los totales (resumen de ventas, cifras por vendedor, cantidad y total de anuladas, totales por vendedor de las rendiciones, total adeudado y total a favor) DEBEN calcularse sobre todo el período y los filtros, nunca sobre la página. «Por vendedor», «Ajustes por motivo» y «Observaciones por vendedor» NO se paginan. La paginación y los conteos DEBEN hacerse en la base (`LIMIT`/`OFFSET` y `count`), con `organizacion_id` (`02` §14; `design.md` D14).

#### Scenario: Más de una página
- **GIVEN** 120 clientes con saldo en la organización
- **WHEN** se pide `GET /api/v1/reportes/saldos/clientes?pagina=3`
- **THEN** vienen 20 filas (de la 101 a la 120 en el orden del reporte), con `pagina` 3, `tamano` 50, `total_filas` 120 y `paginas` 3
- **AND** el total adeudado y el total a favor son los de los 120 clientes
- **Regla:** CC-04; `design.md` D14

#### Scenario: Las páginas no repiten ni pierden filas
- **GIVEN** 60 jornadas del período, varias abiertas en el mismo instante
- **WHEN** se piden las páginas 1 y 2 de las rendiciones
- **THEN** entre las dos vienen las 60 jornadas, cada una una sola vez
- **Regla:** RUT-07; `design.md` D14

#### Scenario: Página fuera de rango
- **WHEN** se pide `pagina=0`
- **THEN** se responde 422
- **AND** con una página posterior a la última vienen `filas` vacías con el `total_filas` y las `paginas` reales
- **Regla:** `design.md` D14

#### Scenario: Cada lista del reporte de ventas se pagina por su lado
- **GIVEN** un período con 70 días con ventas y 3 productos vendidos
- **WHEN** se pide el reporte de ventas con `pagina_por_dia=2`
- **THEN** «Por día» trae la página 2 (20 días) y «Por producto» y las anuladas traen su página 1
- **AND** el resumen y «Por vendedor» son los de todo el período
- **Regla:** REP-01; `design.md` D14

### Requirement: La navegación entre páginas en `/admin`

Debajo de cada lista paginada, la pantalla DEBE mostrar «Anterior», «Página {n} de {m}» y «Siguiente», con «Anterior» deshabilitado en la primera página y «Siguiente» en la última, y NO DEBE mostrar la navegación cuando la lista tiene una sola página o ninguna fila. Cambiar el período, el vendedor u otro filtro DEBE volver todas las listas de la pestaña a la página 1; cambiar de página en una lista NO DEBE mover las demás. Los importes de los totales NO DEBEN cambiar al cambiar de página (`design.md` D12, D14).

#### Scenario: Recorrer las páginas
- **GIVEN** la pestaña «Saldos de clientes» con 120 clientes
- **WHEN** la persona toca «Siguiente»
- **THEN** ve «Página 2 de 3» y las filas de la página 2, con «Anterior» habilitado
- **AND** «Total adeudado» y «Total a favor» no cambian
- **Regla:** `design.md` D14

#### Scenario: Una sola página
- **GIVEN** una lista con 30 filas
- **WHEN** se muestra
- **THEN** no aparecen «Anterior», «Siguiente» ni «Página 1 de 1»
- **Regla:** `design.md` D14

#### Scenario: Cambiar un filtro vuelve a la primera página
- **GIVEN** la pestaña «Ventas» en la página 2 de «Por día» y la página 2 de «Por producto»
- **WHEN** la persona cambia el vendedor
- **THEN** el reporte se pide con las tres listas en la página 1
- **Regla:** `design.md` D14

### Requirement: La sección «Reportes» de `/admin`

`/admin` DEBE ofrecer la sección «Reportes» a quien tiene `VER_REPORTES`, en `/admin/reportes`, con las pestañas «Ventas», «Rendiciones», «Saldos de clientes», «Saldos de proveedores» (solo con la regla compuesta de `reportes/saldos-de-cuentas`), «Observaciones por vendedor» y «Ajustes por motivo». Las pestañas con período DEBEN abrir con el mes en curso que devuelve el servidor y recalcularse al cambiar un filtro; la pantalla DEBE validar «Desde» no posterior a «Hasta» antes de pedir. Quien solo tiene `VER_REPORTES` DEBE entrar a «Reportes» como primera sección. Ocultar la sección no reemplaza la validación del servidor (`design.md` D11; ADR-027; SEG-06).

#### Scenario: Menú con y sin permiso
- **GIVEN** `consulta` (con `VER_REPORTES`) y `vendedor` (sin él)
- **WHEN** cada uno entra a `/admin`
- **THEN** `consulta` ve «Reportes» y aterriza en ella; `vendedor` no la ve y `/admin/reportes` no le muestra datos
- **Regla:** `01` §19; ADR-027

#### Scenario: Cambiar el período
- **GIVEN** la pestaña «Ventas» abierta con el mes en curso
- **WHEN** la persona elige otro «Desde» y otro «Hasta»
- **THEN** el reporte se vuelve a pedir con esas fechas y muestra «Período: {desde} al {hasta}»
- **Regla:** TR-04

#### Scenario: Error del servidor
- **WHEN** el servidor responde `PERIODO_DEMASIADO_LARGO`
- **THEN** la pantalla muestra «El período no puede superar los 366 días.» y conserva los filtros
- **Regla:** `design.md` D1, D12
