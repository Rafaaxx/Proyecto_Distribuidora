# ADR-029 — El consumidor final lo habilita solo el Administrador y su cliente no se inactiva (CLI-03)

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-28 |
| Referenciado en | `openspec/changes/07-clientes/design.md` D4; `01-dominio.md` CLI-03 y §18; `03` §4 (`configuracion_organizacion`) |

**Decisión (D4, opción A) aprobada por el usuario el 2026-09-28. Texto del ADR aprobado por el usuario el 2026-09-28; estado *Vigente*.**

## Contexto

CLI-03 dice "si la organización lo habilita, existe un cliente genérico consumidor final con límite de crédito cero", y `03` §4 ya tiene `permite_consumidor_final` y `cliente_consumidor_final_id`. `docs/` no dice quién lo habilita ni cómo nace el cliente, y no cubre qué pasa con el cliente consumidor final si se intenta inactivar: la referencia de la configuración quedaría apuntando a un cliente al que no se le puede vender (CLI-02). Por eso se registra como ADR en vez de dejarlo solo en `design.md`, con el mismo criterio que ADR-024 y ADR-026.

## Decisión

1. `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` (`ONLINE`, permiso `ADMIN_CONFIGURACION`) crea el cliente genérico con límite de crédito cero, le pone la marca, y fija `permite_consumidor_final` y `cliente_consumidor_final_id` en la misma transacción, a través de un setter nuevo en `identidad/service.py` (el módulo `clientes` alcanza a `identidad` solo por su `service.py`, contrato de import-linter). Con las plantillas de rol vigentes, solo el rol Administrador (`ADM`) puede ejecutarlo. La marca no se puede poner desde `CLIENTE_CREAR`, y un segundo intento se rechaza con `CONSUMIDOR_FINAL_YA_HABILITADO`.
2. El cliente consumidor final solo puede estar `ACTIVO` o `SUSPENDIDO`: `CLIENTE_MODIFICAR` con `estado = INACTIVO` sobre él se rechaza (`CONSUMIDOR_FINAL_NO_INACTIVABLE`). Para dejar de vender "de paso" se deshabilita la función con el mismo comando de configuración.
3. El nombre del cliente genérico lo recibe el comando como dato (default "Consumidor final"); cada organización puede elegirlo.

## Consecuencias

- No existe el estado en que la organización dice que tiene consumidor final sin cliente, ni el contrario, porque es una transacción.
- La configuración nunca queda apuntando a un cliente `INACTIVO`, al que no se le puede vender (CLI-02).
- Solo el Administrador habilita la función; si Administración necesita hacerlo, es un cambio de plantilla de rol, no de código.
- La FK compuesta desde `configuracion_organizacion.cliente_consumidor_final_id` a `cliente` se agrega en el change que defina el ciclo de vida completo del consumidor final (riesgo anotado en el design 07).

## Alternativas consideradas

- **Habilitación con `GESTIONAR_CLIENTES`**: descartada: lo que se escribe es configuración de la organización, y abriría el flag a cualquier rol de clientes para una decisión que la organización toma una vez.
- **Crear el cliente a mano y activar el flag aparte**: descartada: deja un cliente huérfano y un flag que puede apuntar a cualquier cliente, incluso con crédito (contradice CLI-03).
- **Crearlo en el seed de la organización**: descartada: contradice "si la organización lo habilita", y el seed no es lugar para una decisión de negocio.
- **Permitir inactivar el consumidor final**: descartada: deja la configuración apuntando a un cliente al que no se le puede vender sin que la pantalla explique por qué (CLI-02).