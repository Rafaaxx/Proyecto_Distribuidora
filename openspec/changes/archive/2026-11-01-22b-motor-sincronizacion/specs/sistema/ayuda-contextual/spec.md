## ADDED Requirements

### Requirement: La sincronización del área de ruta explica sus estados

Las pantallas de `/ruta` DEBEN ofrecer ayuda en «Sincronizar», en los estados «Con observaciones» y «Rechazada» y en el aviso de versión desactualizada, y la ayuda de «Sin enviar» DEBE nombrar el envío automático y el botón. Los textos DEBEN vivir en el archivo único, citar su regla o ADR, seguir el estilo de ADR-051 y no llevar ejemplos, con los textos que apruebe el usuario (`design.md` D13).

#### Scenario: Sincronizar
- **WHEN** se abre el "(?)" de «Sincronizar»
- **THEN** explica que envía las ventas sin enviar del usuario en orden, cuándo se hace sola (al abrir la aplicación o volver a ella, al volver la señal, después de cada venta y cada 2 minutos) y que enviar dos veces no duplica
- **Regla:** SYN-02; SYN-03; INV-06

#### Scenario: Con observaciones
- **WHEN** se abre el "(?)" del estado «Con observaciones»
- **THEN** explica que la venta se aceptó, que administración revisa lo anotado y que el vendedor no tiene que hacer nada
- **Regla:** SYN-04; SYN-05; SYN-08

#### Scenario: Rechazada
- **WHEN** se abre el "(?)" del estado «Rechazada»
- **THEN** explica que fue por un problema de datos, que sigue guardada y no se reenvía sola, y que hay que avisar a administración
- **Regla:** SYN-06; SYN-09

#### Scenario: Versión desactualizada
- **WHEN** se abre el "(?)" del aviso de versión desactualizada
- **THEN** explica que no se confirman ventas nuevas, que lo guardado se sigue enviando y que hay que actualizar
- **Regla:** ADR-064

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051
