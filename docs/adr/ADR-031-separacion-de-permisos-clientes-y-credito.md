# ADR-031 — Alta y edición de clientes van por `GESTIONAR_CLIENTES`; el crédito, por `GESTIONAR_CREDITO`, en un comando propio (`01` §19)

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-28 |
| Referenciado en | `openspec/changes/07-clientes/design.md` D3; `01-dominio.md` §19 (`GESTIONAR_CLIENTES`, `GESTIONAR_CREDITO`); CRE-01, CRE-03, CRE-06 |

**Decisión (D3, opción A) aprobada por el usuario el 2026-09-28. Texto del ADR aprobado por el usuario el 2026-09-28; estado *Vigente*.**

## Contexto

`01` §19 separa `GESTIONAR_CLIENTES` ("Alta y edición de clientes") de `GESTIONAR_CREDITO` ("Límite, política y tolerancia de clientes"), y el ratchet de rutas de `docs/02-arquitectura.md` exige un único permiso por ruta. La ficha completa de CLI-01, sin embargo, incluye los tres campos de crédito (límite, política, tolerancia) junto con los datos de la ficha. Sin una decisión explícita, cualquier implementación tiende a juntarlos en un solo comando y a licuar la separación que el catálogo de permisos ya declara.

La regla afecta a los comandos, a las rutas de la API y a las dos pantallas del frontend (ficha y crédito), y condiciona lo que un Supervisor comercial puede y no puede hacer con las plantillas de rol vigentes. Por eso se registra como ADR y no solo en `design.md`, con el mismo criterio que ADR-024/ADR-026 para separaciones de responsabilidad entre comandos.

## Decisión

1. `CLIENTE_CREAR` y `CLIENTE_MODIFICAR` (permiso `GESTIONAR_CLIENTES`) llevan únicamente los campos de la ficha; un contenido con `limite_credito`, `politica_credito`, `tolerancia_offline_tipo` o `tolerancia_offline_valor` se rechaza como malformado.
2. `CLIENTE_CREDITO_MODIFICAR` (permiso `GESTIONAR_CREDITO`) lleva únicamente los tres campos de crédito; un contenido con `nombre`, `direccion`, `contacto` o `estado` se rechaza como malformado.
3. Las lecturas (`GET /api/v1/clientes`, `GET /api/v1/clientes/{id}`) devuelven los tres campos de crédito a cualquier usuario con `GESTIONAR_CLIENTES`, tenga o no `GESTIONAR_CREDITO`: verlos no requiere el permiso de editarlos.
4. La edición del crédito es una pantalla separada de la ficha en el frontend, visible solo con `GESTIONAR_CREDITO` (`<SiTienePermiso>`), que envía su propio comando con su propio `operation_id`.

## Consecuencias

- Un Supervisor comercial (`GESTIONAR_CLIENTES`, sin `GESTIONAR_CREDITO`) puede dar de alta y editar clientes, y ver su crédito, pero no modificarlo — que es la razón de ser de los dos permisos del catálogo.
- Guardar la ficha y guardar el crédito son dos envíos independientes, con dos `operation_id`; un rechazo de uno no revierte el otro, porque cada uno es una transacción propia y completa en sí misma (a diferencia de la alternativa descartada de una sola acción de pantalla que aplicara los dos comandos).
- El catálogo de permisos de `01` §19 no cambia: no se amplía `GESTIONAR_CLIENTES` para incluir crédito.
- Sin cambio de esquema: la separación es de comandos y de rutas, no de columnas.

## Alternativas consideradas

- **Un solo comando `CLIENTE_MODIFICAR` con la ficha completa y un único permiso**, ampliando `GESTIONAR_CLIENTES` para que incluya el crédito. Descartada: contradice el texto ya implementado de `01` §19, y con las plantillas de rol vigentes el efecto real sería que un Supervisor comercial pudiera cambiar el límite de crédito de cualquier cliente.
- **Una acción de pantalla que aplica los dos comandos en el navegador.** Descartada: dos transacciones y dos `operation_id` dejan un estado intermedio posible (ficha guardada, crédito no) si el segundo comando se rechaza, sin que el usuario pueda revertir el primero desde la misma acción.
