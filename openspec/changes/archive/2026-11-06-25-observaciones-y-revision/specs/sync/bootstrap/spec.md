## ADDED Requirements

### Requirement: El bootstrap informa los rechazos resueltos de la jornada

El bootstrap DEBE incluir `rechazos_resueltos`: los `operation_id` de los rechazos ya resueltos de la jornada del bootstrap, del usuario y del dispositivo de la sesión, leídos en la misma foto de la base; vacío si no hay. NO DEBE incluir el comentario ni el vínculo (SYN-11, `design.md` D8).

#### Scenario: Venta rechazada resuelta
- **GIVEN** la venta rechazada de Juan, resuelta por la Supervisora
- **WHEN** el teléfono de Juan pide el bootstrap de esa jornada
- **THEN** `rechazos_resueltos` trae el `operation_id` de esa venta
- **Regla:** SYN-11

#### Scenario: Pendiente o de otra jornada
- **GIVEN** un rechazo pendiente de Juan y uno resuelto de otra jornada
- **WHEN** pide el bootstrap
- **THEN** `rechazos_resueltos` no trae ninguno de los dos
- **Regla:** SYN-11; INV-21

#### Scenario: Doble pedido
- **WHEN** el teléfono pide el bootstrap dos veces sin cambios en el servidor
- **THEN** recibe la misma lista
- **Regla:** SYN-11
