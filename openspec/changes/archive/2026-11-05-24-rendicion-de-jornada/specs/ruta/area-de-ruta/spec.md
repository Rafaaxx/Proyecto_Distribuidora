## ADDED Requirements

### Requirement: El vendedor termina el día desde el teléfono

Con la jornada abierta, `ABRIR_JORNADA` en los permisos del bootstrap y la versión mínima, el inicio DEBE ofrecer «Terminar el día» con confirmación. Confirmar DEBE, en una sola transacción de la base local, encolar `JORNADA_ENTREGAR` `OFFLINE` con la siguiente secuencia y guardar que la jornada quedó entregada, con o sin señal, y disparar la sincronización. Desde entonces el teléfono NO DEBE ofrecer «Vender», «Anular venta» ni «Cobrar» en esa jornada, también sin señal y después de recargar, y DEBE avisar «Terminaste el día. Pasá a rendir con tu supervisor.» y, con pendientes, «Lo que falta enviar se envía antes de la entrega.». «Sincronización» DEBE mostrar la entrega y su resultado (`design.md` D10, D11).

#### Scenario: Terminar el día sin señal
- **GIVEN** el vendedor con dos ventas «Sin enviar» y sin señal
- **WHEN** toca «Terminar el día» y confirma
- **THEN** la entrega queda encolada detrás de las dos ventas, «Vender», «Anular venta» y «Cobrar» se deshabilitan y ve los dos avisos
- **Regla:** RUT-05; SYN-03; INV-01

#### Scenario: La marca sobrevive a la recarga
- **GIVEN** el día terminado
- **WHEN** el vendedor recarga la aplicación sin señal
- **THEN** «Vender», «Anular venta» y «Cobrar» siguen deshabilitados con el aviso
- **Regla:** RUT-05

#### Scenario: Falla al terminar el día
- **WHEN** la escritura del comando de entrega falla
- **THEN** no queda la marca ni el comando, la secuencia no avanza y el vendedor puede seguir vendiendo
- **Regla:** INV-01

#### Scenario: Doble toque
- **GIVEN** el día ya terminado
- **WHEN** se confirma otra vez
- **THEN** no se encola otra entrega
- **Regla:** INV-06

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `ABRIR_JORNADA` en el bootstrap
- **WHEN** abre el inicio
- **THEN** no ve «Terminar el día»
- **Regla:** `01` §19; SEG-06

#### Scenario: Entrega rechazada
- **GIVEN** la jornada liberada antes de que llegue la entrega
- **WHEN** vuelve el resultado
- **THEN** «Sincronización» muestra «Entrega del día» rechazada con «La jornada ya no estaba abierta cuando llegó la entrega.» seguido de «Avisá a tu supervisor.»
- **Regla:** SYN-06; SYN-09; RUT-09

#### Scenario: Doble sincronización de la entrega
- **WHEN** el resultado de la entrega llega dos veces
- **THEN** la cola y la marca quedan igual
- **Regla:** SYN-02; INV-06
