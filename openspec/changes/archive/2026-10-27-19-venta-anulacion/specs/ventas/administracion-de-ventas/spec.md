## ADDED Requirements

### Requirement: El detalle muestra la anulación y el listado filtra por estado

`GET /api/v1/ventas/{id}` DEBE traer, en una venta `ANULADA`, el bloque de anulación: momento, usuario (con su nombre), motivo (con su nombre), observación y si se devolvió el dinero (nulo si la venta no tenía cobro). `GET /api/v1/ventas` DEBE admitir el filtro `estado` (`CONFIRMADA` o `ANULADA`); otro valor es 422. Los permisos de lectura no cambian (`VENDER` o `ANULAR_VENTA`) (`design.md` D14).

#### Scenario: Detalle de una venta anulada
- **GIVEN** la venta V03-000142 anulada por `sup01` con el motivo "Error de carga" y devolución del dinero
- **WHEN** un usuario con `VENDER` abre su detalle
- **THEN** ve el estado `ANULADA` y el bloque de anulación con la fecha, "sup01", "Error de carga", la observación y `devuelve_dinero` verdadero, y la cobranza marcada `ANULADA`
- **Regla:** VTA-20; VTA-22; `01` §19

#### Scenario: Detalle de una venta sin anular
- **WHEN** se abre el detalle de una venta `CONFIRMADA`
- **THEN** el bloque de anulación es nulo
- **Regla:** VTA-20

#### Scenario: Filtro por estado
- **GIVEN** tres ventas confirmadas y una anulada
- **WHEN** se lista con `estado=ANULADA`
- **THEN** se recibe solo la anulada; con `estado=OTRO` responde 422
- **Regla:** REP-02; `01` §19

### Requirement: La pantalla de la venta permite anularla

El detalle de la venta en `/admin` DEBE ofrecer "Anular venta" solo a quien tiene `ANULAR_VENTA` y solo si la venta está `CONFIRMADA`. El diálogo DEBE pedir el motivo (obligatorio, de los motivos activos de `ANULACION_VENTA`) y una observación opcional y, solo si la venta tiene cobranza confirmada, si se devuelve el dinero; en el consumidor final la devolución DEBE estar fija y explicada. Antes de confirmar DEBE mostrar el efecto: la mercadería que vuelve por línea y a qué ubicación, cuánto baja la cuenta del cliente y, con devolución, cuánto sube por el cobro devuelto, calculado con los mismos casos compartidos que el servidor. Después de anular DEBE mostrar el saldo que devuelve el comando y el detalle actualizado. Los errores DEBEN mostrarse con su texto (`design.md` D16).

#### Scenario: Botón visible solo con permiso
- **GIVEN** una venta `CONFIRMADA`
- **WHEN** la abren `sup01` y `vendedor`
- **THEN** `sup01` ve "Anular venta" y `vendedor` no
- **Regla:** VTA-20; `01` §19

#### Scenario: Venta ya anulada
- **WHEN** se abre una venta `ANULADA`
- **THEN** no hay botón "Anular venta" y se ve el bloque "Anulación"
- **Regla:** VTA-20

#### Scenario: Resumen del efecto con devolución
- **GIVEN** una venta de $80.000 con cobranza de $20.000
- **WHEN** se elige "Sí, devolver" en el diálogo
- **THEN** el resumen dice que la cuenta del cliente baja $80.000 y sube $20.000 por el cobro devuelto
- **Regla:** VTA-21; VTA-22

#### Scenario: Venta sin cobro
- **WHEN** se abre el diálogo de una venta sin cobranza
- **THEN** no se pregunta por el dinero
- **Regla:** VTA-22; ADR-058

#### Scenario: Ubicación tomada
- **WHEN** `ges01` confirma la anulación de una venta de una camioneta tomada por otra jornada
- **THEN** ve el mensaje de ubicación tomada con quién la tiene y la venta sigue confirmada
- **Regla:** STK-09; ADR-058
