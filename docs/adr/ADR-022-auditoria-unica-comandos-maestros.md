# ADR-022 — Auditoría única al envolver los servicios de identidad en comandos

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-22 |
| Referenciado en | `docs/04-roadmap-changes.md` (change 04), `design.md` D7 del change 04-pipeline-comandos |

> **Nota (2026-09-22, verificación grupo 16):** el change 04 reusó este mismo ADR para dos handlers más en las tareas 14.3-14.7 (`ROL_PERMISOS_CAMBIAR` sobre `cambiar_composicion_rol`, `USUARIO_DESBLOQUEAR` sobre `desbloquear_usuario`), envueltos con el mismo patrón `auditar: bool = True` / `auditar=False` desde el bus. El texto de abajo, escrito cuando solo existían los tres handlers del grupo 11, queda actualizado para reflejarlo; la decisión y sus consecuencias no cambian — son la misma regla aplicada dos veces más.

## Contexto

El change 04 (grupo 11, extendido en las tareas 14.3-14.7) envuelve cinco métodos ya existentes de `identidad/service.py` (`crear_usuario`, `revocar_dispositivo`, `establecer_pin_autorizacion`, `cambiar_composicion_rol`, `desbloquear_usuario`) como handlers del bus de comandos (`USUARIO_CREAR`, `DISPOSITIVO_REVOCAR`, `PIN_AUTORIZACION_ROTAR`, `ROL_PERMISOS_CAMBIAR`, `USUARIO_DESBLOQUEAR`), siguiendo D7: "se envuelve, no se reescribe — el cuerpo del servicio no se toca".

El grupo 10 ya cableó en `sync/service.py::procesar_comando` un registro de auditoría automático para todo comando aceptado (`origen="COMANDO"`, con `operation_id` del sobre), insertado antes del commit.

Los cinco métodos de servicio, sin embargo, ya auditan internamente su propia acción (`registrar_auditoria` con `origen` implícito `SISTEMA`, sin `operation_id`) — comportamiento correcto y necesario cuando esos métodos se llaman fuera del bus (seed, mantenimiento, cualquier llamada directa futura).

Envolver el método sin tocar su cuerpo, como pide D7 literalmente, deja **dos filas de auditoría por comando**: una `SISTEMA` sin `operation_id` (del servicio) y una `COMANDO` con `operation_id` (del bus). Esto contradice el escenario de la spec `identidad/dispositivos` ("un reenvío deja un solo registro de auditoría") si se lee como "un solo registro en total" por operación, no solo "no se duplica en reenvíos".

D7 mismo prevé esta situación: "si hiciera falta modificar el servicio, detenerse y reportarlo en vez de ajustarlo en silencio". Este ADR documenta esa excepción puntual.

## Decisión

Los cinco métodos de `identidad/service.py` ganan un parámetro `auditar: bool = True`:

- Llamados directamente (fuera del bus): `auditar` no se pasa, usa el default `True`, mantienen su auditoría interna actual sin cambios de comportamiento.
- Llamados desde los handlers del bus (`identidad/commands.py`, grupo 11): se pasa `auditar=False` explícito. El servicio omite su inserción interna de auditoría; la única fila que queda es la que el bus ya inserta automáticamente (`origen="COMANDO"`, con `operation_id`).

Esto es la única modificación al cuerpo de estos cinco métodos permitida por este ADR: agregar el parámetro y envolver su llamada interna a `registrar_auditoria` en el condicional `if auditar:`. No se toca ninguna otra parte de su lógica (validaciones, excepciones de dominio, permisos).

## Consecuencias

- Cada comando aceptado deja exactamente una fila de auditoría (`origen="COMANDO"`, con `operation_id`), igual que el resto de los comandos del bus (consistente con el grupo 10).
- Las llamadas directas a estos servicios (fuera del bus) no cambian su comportamiento observable: siguen auditando con `origen="SISTEMA"` como hoy.
- Cualquier handler futuro (changes 05-27) que envuelva un método de servicio existente con auditoría interna debe seguir el mismo patrón (`auditar: bool = True`, `auditar=False` desde el bus) en vez de dejar auditoría duplicada — se documenta como parte de la plantilla de D7 (tarea 11.8).
- El parámetro es puramente de control de infraestructura de auditoría, no de negocio: no se expone en ningún esquema de contenido de comando ni en la API pública del servicio salvo como argumento con default seguro.

## Alternativas consideradas

- **Aceptar las dos filas ("un solo registro" = "no se duplica en reenvíos").** Evita tocar el servicio, pero reinterpreta el escenario de la spec en el sentido más débil sin confirmarlo contra la intención original, y deja auditoría redundante y potencialmente confusa (dos entradas con acciones parecidas, orígenes distintos, una sin trazabilidad al comando). Descartado.
- **El bus detecta si el handler ya auditó y omite su propio registro.** Acopla `sync/service.py` al comportamiento interno de cada servicio de cada módulo (violaría "un módulo usa a otro solo a través de su service.py" en el sentido inverso: el bus tendría que inspeccionar efectos del handler). Reabre y complica una pieza (grupo 10) ya implementada y aprobada. Descartado.
