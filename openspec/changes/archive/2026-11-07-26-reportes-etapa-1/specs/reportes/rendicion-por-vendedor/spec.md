## Purpose

Define el reporte de rendición por vendedor y jornada: qué vendió, anuló y cobró cada jornada del período, qué diferencias dejó el conteo y los totales por vendedor, con el resumen de RUT-07 de cada jornada (RUT-07; ADR-068).

## ADDED Requirements

### Requirement: Las jornadas del período con su dinero y sus diferencias

`GET /api/v1/reportes/rendiciones` (con `VER_REPORTES`; filtros: período por la fecha de negocio de `abierta_en`, `vendedor_id` y `estado`) DEBE devolver cada jornada abierta en el período, de cualquier estado, con: vendedor, ubicación, estado, apertura y, según corresponda, rendición, cierre o liberación; ventas vigentes (cantidad y total) y anuladas (cantidad y total, por la jornada de la anulación); cobrado por medio de pago (cobranzas confirmadas); lo registrado después de la rendición aparte (cantidad y total); faltantes y sobrantes en unidades base de `rendicion_linea` (o la marca de sin conteo) y, solo con `VER_COSTOS`, el valor de las diferencias. Cada fila DEBE coincidir con el resumen de esa jornada (RUT-07). Una `ABIERTA` DEBE marcarse en curso. La lista DEBE venir con la jornada más reciente primero (`abierta_en` descendente, desempate por el identificador de la jornada) y paginada de a 50 con `pagina` (`design.md` D7, D14).

#### Scenario: Jornada rendida
- **GIVEN** una jornada de `vendedor` abierta en el período, con tres ventas (una anulada en la misma jornada), cobranzas en efectivo y transferencia, y una rendición con un faltante de 2 unidades y un sobrante de 1
- **WHEN** se pide el reporte
- **THEN** la jornada informa 2 ventas vigentes con su total, 1 anulada con su total, lo cobrado por medio, 2 unidades faltantes y 1 sobrante
- **AND** cada cifra es igual a la del resumen de esa jornada
- **Regla:** RUT-07

#### Scenario: Lo registrado después de la rendición
- **GIVEN** una jornada rendida y una venta sin conexión de esa jornada que llegó después de la rendición
- **WHEN** se pide el reporte
- **THEN** esa venta se informa en «Después de la rendición» y no en las vigentes
- **Regla:** RUT-07; ADR-068

#### Scenario: Jornada liberada sin conteo
- **GIVEN** una jornada liberada en el período, sin rendición
- **WHEN** se pide el reporte
- **THEN** aparece con estado «Liberada», sus ventas y cobranzas, y «Sin conteo» en lugar de faltantes y sobrantes
- **Regla:** RUT-07; RUT-09

#### Scenario: Valor de las diferencias según permiso
- **GIVEN** una jornada rendida con diferencias
- **WHEN** `ges01` (con `VER_COSTOS`) y `consulta` (sin él) piden el reporte
- **THEN** `ges01` ve el valor de las diferencias como string y `consulta` lo recibe en `null`
- **Regla:** RUT-07; `01` §19 (VER_COSTOS)

#### Scenario: La jornada más reciente primero, en páginas
- **GIVEN** 52 jornadas abiertas en el período
- **WHEN** se pide el reporte sin `pagina`
- **THEN** vienen las 50 más recientes por apertura, empezando por la última abierta, con `total_filas` 52 y `paginas` 2
- **AND** los totales por vendedor suman las 52
- **Regla:** RUT-07; `design.md` D14

#### Scenario: Filtros por vendedor y estado
- **GIVEN** jornadas de `vendedor` y `vendedor2`, una abierta y otras cerradas
- **WHEN** se filtra por `vendedor2` y estado `CERRADA`
- **THEN** solo vienen las jornadas cerradas de `vendedor2`
- **Regla:** RUT-07

### Requirement: Totales por vendedor

La misma respuesta DEBE traer, sin paginar y sobre todas las jornadas del filtro (no solo las de la página pedida), por vendedor con jornadas en el período y respetando los filtros, la cantidad de jornadas, ventas vigentes, anuladas, cobrado por medio de pago, faltantes y sobrantes en unidades y, con `VER_COSTOS`, el valor de las diferencias, sumados en la base (`design.md` D7, D14).

#### Scenario: Dos jornadas del mismo vendedor
- **GIVEN** dos jornadas de `vendedor` en el período
- **WHEN** se pide el reporte
- **THEN** la fila de `vendedor` informa 2 jornadas y la suma de las ventas, lo cobrado por medio y las diferencias de las dos
- **Regla:** RUT-07

### Requirement: El detalle de una jornada desde el reporte

`GET /api/v1/reportes/rendiciones/{jornada_id}` (con `VER_REPORTES`) DEBE devolver el resumen de RUT-07 de la jornada con la misma implementación que el detalle de jornadas, el valor de las diferencias solo con `VER_COSTOS`, y responder 404 si la jornada no existe o es de otra organización (RUT-07, INV-21; `design.md` D7).

#### Scenario: Detalle sin permisos de jornadas
- **GIVEN** `consulta`, sin `ABRIR_JORNADA`, `RENDIR_JORNADA` ni `LIBERAR_UBICACION`
- **WHEN** pide el detalle de una jornada desde el reporte
- **THEN** recibe el resumen de RUT-07 sin el valor de las diferencias
- **Regla:** RUT-07; `01` §19

#### Scenario: Jornada de otra organización
- **WHEN** se pide el detalle de una jornada de otra organización
- **THEN** se responde 404
- **Regla:** INV-21

### Requirement: La pestaña «Rendiciones»

La pestaña DEBE mostrar la tabla por vendedor y la lista de jornadas (con la navegación entre páginas de `reportes/area-de-reportes`) con sus estados («Abierta» en curso como «En curso», «En rendición», «Cerrada», «Liberada»), «Sin conteo» donde no hay rendición y «Ver detalle», que abre el resumen de la jornada con el mismo componente que el detalle de jornadas; sin `VER_COSTOS`, sin la columna «Valor de las diferencias» (`design.md` D11, D12).

#### Scenario: Ver el detalle
- **GIVEN** `consulta` en «Rendiciones» con una jornada cerrada
- **WHEN** toca «Ver detalle»
- **THEN** ve el resumen de la jornada (stock, ventas, anuladas, cobranzas por medio y lo tardío) sin valores de costo
- **Regla:** RUT-07

#### Scenario: Sin jornadas
- **WHEN** elige un período sin jornadas
- **THEN** ve «Sin jornadas en el período.»
- **Regla:** RUT-07
