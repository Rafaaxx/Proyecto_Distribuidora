## ADDED Requirements

### Requirement: La rendición espera a que se resuelvan las operaciones rechazadas de la jornada

`JORNADA_RENDIR` DEBE rechazarse con `RECHAZOS_PENDIENTES` (409, con la cantidad pendiente en el detalle) y sin escribir nada mientras la jornada tenga rechazos sin conexión `PENDIENTE` en el registro de rechazos (cualquier tipo de comando cuyo sobre traía esa jornada). Lo comprueba después de tomar la jornada `FOR UPDATE`, en una consulta aparte, por un puerto que `stock/service.py` declara y `sync/service.py` registra; sin puerto registrado la rendición falla (no se rinde sin comprobar). Los comandos en cuarentena NO DEBEN bloquear la rendición (no tienen jornada en el registro y su teléfono dado de baja no puede entregar el día: RUT-05, RUT-09). La entrega del día (`JORNADA_ENTREGAR`), el cierre y la liberación NO DEBEN bloquearse por los rechazos. `GET /api/v1/stock/jornadas/{id}` DEBE devolver `rechazos_pendientes` (solo la cantidad) a quien puede leer la jornada; la pantalla de conteo y el detalle de la jornada DEBEN mostrar «Esta jornada tiene {N} operaciones rechazadas sin resolver. Hay que resolverlas antes de rendir.» (en singular con una) y deshabilitar «Registrar rendición»; el acceso «Ver rechazadas» a la lista filtrada por la jornada se muestra solo con `REVISAR_OBSERVACIONES` (`design.md` D9 = B).

#### Scenario: Rendición con una venta rechazada sin resolver
- **GIVEN** la jornada entregada de Juan con una venta sin conexión rechazada y `PENDIENTE`
- **WHEN** la Supervisora envía la rendición con el conteo completo
- **THEN** se rechaza con `RECHAZOS_PENDIENTES` (409) y la cantidad 1
- **AND** la jornada sigue `ABIERTA`, sin `DIFERENCIA_RENDICION` ni conteo, y el stock del vehículo no cambia
- **Regla:** RUT-05; RUT-06; SYN-06; ADR-069

#### Scenario: Rendición permitida cuando todo está resuelto
- **GIVEN** que la Supervisora cargó con conexión la venta rechazada y resolvió el rechazo vinculándola
- **WHEN** envía la rendición
- **THEN** se acepta; el esperado ya incluye la venta cargada y la mercadería se descuenta una sola vez
- **Regla:** RUT-05; RUT-06; SYN-08

#### Scenario: Resuelto sin vínculo
- **GIVEN** que el rechazo se resolvió sin vínculo («la venta no ocurrió»)
- **WHEN** envía la rendición
- **THEN** se acepta
- **Regla:** RUT-05; SYN-08

#### Scenario: La entrega del día no se bloquea
- **GIVEN** la jornada de Juan con un rechazo `PENDIENTE`
- **WHEN** Juan toca «Terminar el día» y el lote procesa `JORNADA_ENTREGAR`
- **THEN** la entrega se acepta igual
- **Regla:** RUT-05

#### Scenario: Rechazos de otra jornada o en cuarentena
- **GIVEN** rechazos `PENDIENTE` de otra jornada, rechazos sin jornada y comandos en cuarentena del mismo vendedor
- **WHEN** se rinde la jornada de Juan sin rechazos propios pendientes
- **THEN** se acepta
- **Regla:** RUT-05; SYN-06; INV-21

#### Scenario: Pantalla de conteo con rechazos pendientes
- **GIVEN** la jornada entregada con 2 rechazos pendientes
- **WHEN** la Supervisora abre la pantalla de conteo
- **THEN** ve «Esta jornada tiene 2 operaciones rechazadas sin resolver. Hay que resolverlas antes de rendir.», «Registrar rendición» deshabilitado y «Ver rechazadas», que abre «Rechazadas» de `/admin/revision` filtrada por la jornada
- **Regla:** RUT-05; SYN-06

#### Scenario: Sin permiso de revisión
- **GIVEN** un rol con `RENDIR_JORNADA` y sin `REVISAR_OBSERVACIONES`
- **WHEN** abre la pantalla de conteo de una jornada con rechazos pendientes
- **THEN** ve el aviso y «Registrar rendición» deshabilitado, con «Las resuelve quien revisa las observaciones.», sin «Ver rechazadas» y sin pedir la lista de rechazos
- **Regla:** `01` §19; SEG-06

#### Scenario: Sin rechazos pendientes
- **GIVEN** que los rechazos de la jornada ya se resolvieron
- **WHEN** abre la pantalla de conteo
- **THEN** no hay aviso y «Registrar rendición» está habilitado
- **Regla:** SYN-08

#### Scenario: Doble envío de una rendición rechazada
- **GIVEN** una rendición rechazada con `RECHAZOS_PENDIENTES`
- **WHEN** después de resolver los rechazos se envía otra vez con el mismo `operation_id`
- **THEN** se procesa de nuevo (el rechazo revirtió la reserva de idempotencia) y se acepta
- **Regla:** SYN-02; INV-06

#### Scenario: Resolución y rendición a la vez
- **WHEN** una persona resuelve el último rechazo de la jornada mientras otra envía la rendición
- **THEN** la rendición se acepta si ve el rechazo ya resuelto, o se rechaza con `RECHAZOS_PENDIENTES` y se puede reintentar; nunca hay interbloqueo
- **Regla:** INV-01; RUT-05
