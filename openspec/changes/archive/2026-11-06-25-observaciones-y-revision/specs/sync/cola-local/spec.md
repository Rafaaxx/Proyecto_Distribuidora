## ADDED Requirements

### Requirement: La venta rechazada resuelta deja de contar en lo local

Una venta «Rechazada» sigue contando completa en el stock y el saldo locales (CRE-08) hasta que termina la jornada o hasta que un bootstrap posterior trae su `operation_id` en `rechazos_resueltos`; desde entonces NO DEBE contar más (ni su stock, ni su débito, ni su cobro en el momento). La operación local NO DEBE borrarse: solo deja de contar (SYN-09). El teléfono NO DEBE ofrecer anular una venta «Rechazada» (ADR-066), resuelta o no (`design.md` D8).

#### Scenario: Corrección cargada en la oficina
- **GIVEN** la venta rechazada de Juan de 12 latas, que el teléfono descuenta del stock local
- **AND** la Supervisora cargó la venta con conexión y resolvió el rechazo
- **WHEN** el teléfono actualiza los datos
- **THEN** el stock local muestra lo que trae el bootstrap, sin restar otra vez las 12 latas
- **AND** la venta sigue guardada como «Rechazada»
- **Regla:** CRE-08; SYN-09; RUT-04

#### Scenario: Rechazo todavía pendiente
- **GIVEN** la venta rechazada sin resolver
- **WHEN** el teléfono actualiza los datos
- **THEN** la sigue contando completa
- **Regla:** CRE-08

#### Scenario: Falla al aplicar el bootstrap
- **GIVEN** que aplicar el bootstrap falla a mitad de camino
- **WHEN** se revierte
- **THEN** la lista de rechazos resueltos anterior y los datos anteriores siguen iguales
- **Regla:** INV-01

#### Scenario: Doble actualización
- **WHEN** el teléfono actualiza los datos dos veces con el mismo rechazo resuelto
- **THEN** la venta deja de contar una sola vez
- **Regla:** INV-06; CRE-08
