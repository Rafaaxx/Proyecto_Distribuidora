# ADR-030 — Un cliente `INACTIVO` se revierte solo si no tiene operaciones (CLI-06)

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-28 |
| Referenciado en | `openspec/changes/07-clientes/design.md` D7 y `specs/clientes/fichas-de-cliente`; `01-dominio.md` CLI-06 y §18; ADR-023 (verificadores de uso) |

**Decisión (D7, opción C) aprobada por el usuario el 2026-09-28. Texto del ADR aprobado por el usuario el 2026-09-28; estado *Vigente*.**

## Contexto

`01` §18 enumera las transiciones del cliente (`ACTIVO ↔ SUSPENDIDO`, hacia `INACTIVO`) pero no dice con qué estado nace ni si `INACTIVO` se revierte. CLI-04 fija el espíritu: los clientes con operaciones no se eliminan, se inactivan — no se trata de revivir deudores por error. Como el change 07 es el primer maestro de clientes y todavía no existen operaciones (ventas, cobranzas, compras), un error de inactivación hoy es barato de corregir; con operaciones, en cambio, revivir un cliente con deuda sería un abuso posible. Afecta a más de un change futuro (cuenta corriente del 08, compras del 11, ventas del 18a), por eso se registra como ADR en vez de dejarlo solo en `design.md`.

## Decisión

1. `CLIENTE_CREAR` no acepta estado inicial: el cliente nace siempre `ACTIVO` y el estado se cambia con `CLIENTE_MODIFICAR`.
2. `INACTIVO` admite una sola salida: `INACTIVO → ACTIVO`, y solo si el cliente no tiene operaciones. Con operaciones, la transición no existe: `CLIENTE_MODIFICAR` con `estado = ACTIVO` se rechaza (`CLIENTE_CON_OPERACIONES`).
3. La comprobación de "no tiene operaciones" usa el mecanismo de verificadores de uso de ADR-023: cada módulo que introduce operaciones registra un verificador. Sin verificadores registrados —el caso de este change— la reactivación se acepta; la restricción se activa automáticamente cuando exista la primera operación, sin comando ni permiso nuevo.
4. La pantalla de administración exige una confirmación tipeada —el **nombre completo del cliente**— antes de enviar `CLIENTE_MODIFICAR` con `estado = INACTIVO`. Es una guarda de interfaz, solo frontend: el texto confirmado no viaja en el comando, y la protección real queda en la máquina de estados, el verificador y la auditoría (AUD-01).

## Consecuencias

- Un error de inactivación se corrige hoy con un envío (ningún módulo registra operaciones); cuando existan ventas o deuda, el `INACTIVO` queda terminal sin tocar este change.
- El diálogo muestra código y documento para desambiguar nombres repetidos (CLI-01/CLI-05 permite nombres iguales).
- La confirmación tipeada es el primer patrón de guarda de acciones irreversibles del frontend y se reutiliza para futuras acciones terminales.

## Alternativas consideradas

- **`INACTIVO` terminal absoluto**: descartada por el usuario: un error de inactivación no tendría vuelta atrás, y no permite el caso del cliente que reabre o arregla su deuda.
- **`INACTIVO` reactivable libremente con `GESTIONAR_CLIENTES`**: descartada: permite revivir clientes con deuda sin revisión alguna.
- **Reingreso de contraseña para inactivar**: descartada: la sesión ya está autenticada (access token de 15 minutos + ADR-028), el riesgo protegido es el clic accidental y no un atacante; pedirla en cada inactivación molesta en la tablet de ruta, y el hash de contraseña vive en `identidad` y no debe consultarse desde un comando de negocio.