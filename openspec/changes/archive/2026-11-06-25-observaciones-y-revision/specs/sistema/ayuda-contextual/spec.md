## ADDED Requirements

### Requirement: Las pantallas de revisión explican la bandeja y los rechazos

`/admin` DEBE tener las claves de ayuda `revision.bandeja` (en «Observaciones»), `revision.resolver` (en el diálogo de resolución), `revision.rechazadas` (en «Rechazadas»), `revision.cuarentena` (junto al origen «Teléfono dado de baja»), `revision.vinculo` (en «Vincular con») y `stock.rechazadasDeLaJornada` (en el aviso de la pantalla de conteo y del detalle de la jornada, que explica que la rendición espera a que se resuelvan); el área de ruta, `ruta.rechazoResuelto` (junto a «Resuelta por administración»). Se revisan `ventas.observaciones`, `cobranzas.observaciones`, `ruta.ventaRechazada` y los temas «Ver más» `ventas-observaciones` y `cobranzas-observaciones`, con los textos aprobados, sin ejemplos, citando sus reglas. Todo ID citado DEBE existir en `01-dominio.md` o en `docs/adr/` (`design.md` D13).

#### Scenario: Ayuda de la bandeja
- **WHEN** la Supervisora abre la ayuda de «Observaciones» o de «Resolver»
- **THEN** lee que resolver no cambia la operación y que las correcciones son operaciones nuevas, sin ejemplo
- **Regla:** SYN-08; ADR-051

#### Scenario: Ayuda de las rechazadas
- **WHEN** abre la ayuda de «Rechazadas», de «Teléfono dado de baja» o de «Vincular con»
- **THEN** lee que lo rechazado no se registró ni se reenvía, y que el vínculo es opcional
- **Regla:** SYN-06; SYN-09; ADR-069

#### Scenario: Ayuda de las rechazadas de la jornada
- **WHEN** la Supervisora abre la ayuda junto al aviso de la pantalla de conteo
- **THEN** lee que la jornada no se rinde hasta resolver todas sus operaciones rechazadas, que así la venta cargada de nuevo se descuenta una sola vez y que lo que no ocurrió se resuelve sin vincular, sin ejemplo
- **Regla:** RUT-05; SYN-06; ADR-069

#### Scenario: Textos revisados
- **WHEN** se abre el tema «Avisos de los pagos cargados sin señal»
- **THEN** ya no dice que la bandeja llega más adelante y nombra «Revisión»
- **Regla:** SYN-08

#### Scenario: Clave o ID inexistente
- **WHEN** una pantalla usa una clave que no existe o un texto cita un ID que no está en `docs/`
- **THEN** la prueba de claves de ayuda falla
- **Regla:** ADR-051
