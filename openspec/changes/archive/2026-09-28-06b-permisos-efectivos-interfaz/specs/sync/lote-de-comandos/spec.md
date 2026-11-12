## ADDED Requirements

### Requirement: La baja de un usuario no cierra el canal de su cola pendiente

> **(D9)** Requisito del cierre de la brecha de sesión (ADR-028, dominio CRÍTICO, aprobado por el usuario el 2026-09-25). Refleja la opción aprobada D9.3-B.

El lote de sincronización NO DEBE rechazar en bloque, por ruta, a un usuario autenticado que está `INACTIVO` o cuyo rol está inactivo. DEBE procesar su lote comando por comando, igual que el de un usuario activo, para que una venta o cobranza registrada sin conexión nunca quede sin forma de llegar al servidor (`00` §3, SYN-05, SYN-09).

Cuando exista la verificación de permisos por comando del lote (paso 4 de `02` §6.3), para ese usuario:

- un comando `OFFLINE` DEBE aceptarse con la observación `PERMISO_REVOCADO` (SYN-10);
- un comando `ONLINE` DEBE rechazarse, igual que en REST.

Esa parte queda como deuda nominada para el change que agregue ese paso. Sus escenarios nacen en ese change, no en el 06b, porque acá no podrían tener una prueba (`tasks.md` 10.1).

#### Scenario: El lote de un usuario dado de baja no se rechaza en bloque
- **GIVEN** un usuario con un access token todavía vigente, que pasó a `INACTIVO`
- **WHEN** envía un lote de sincronización
- **THEN** el lote no se rechaza como no autenticado por la ruta
- **AND** cada comando recibe su propio resultado, como en el lote de un usuario activo
- **Regla:** ADR-028 (D9.3-B); SYN-05; SYN-09
