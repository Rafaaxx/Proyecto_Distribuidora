# ADR-038 — Reglas de la ubicación: nombre único, vehículo con toma impuesto por la base, desactivación solo sin stock, modificación por reemplazo completo y movimientos solo sobre activos

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-30 |
| Referenciado en | `openspec/changes/09-stock-y-costeo/design.md` D7 y D8 y `specs/stock/ubicaciones`, `specs/stock/stock-inicial`; `01-dominio.md` STK-02 y STK-09; `03-modelo-de-datos.md` §2.3 y §9; ADR-024 y ADR-026 (desactivación de entidades con operaciones); ADR-036 (permiso `ADMIN_CONFIGURACION`) |

**Decisiones D7 y D8 (opción A en cada una) aprobadas por el usuario el 2026-09-30, junto con la aclaración de implementación del punto 6 (modificación por `PUT`, aprobada el mismo día). Texto del ADR aprobado por el usuario el 2026-09-30; estado *Vigente*.**

## Contexto

STK-02 dice que una ubicación tiene nombre, tipo (depósito, vehículo, otro), estado e indicador de si requiere toma, y que "los vehículos requieren toma". No dice si la base lo impone, si el nombre es único, qué pasa al desactivar una ubicación con stock ni qué se puede hacer sobre una ubicación o un producto inactivo. Además `03` §9 lista `ubicacion` sin `actualizado_en`, que `03` §2.3 exige a los datos maestros.

## Decisión

1. **Nombre.** Se normaliza (se recortan los espacios) y es **único por organización, sin distinguir mayúsculas y activas o no** (`ux_ubicacion__nombre` sobre `(organizacion_id, lower(nombre))`; `NOMBRE_DUPLICADO`, 409), igual que D7 del change 06. Otra organización puede repetirlo.
2. **Vehículo con toma.** `CHECK (tipo <> 'VEHICULO' OR requiere_toma)` en la base (`ck_ubicacion__vehiculo_requiere_toma`), además del dominio (`VEHICULO_REQUIERE_TOMA`, 422): un vehículo sin toma no entra aunque falle el servicio. Para `DEPOSITO` y `OTRO` el indicador es libre, por defecto falso.
3. **Columnas de maestro.** `ubicacion` agrega `actualizado_en` y `actualizado_por_id`, como todo dato maestro (`03` §2.3); faltaban en `03` §9.
4. **Desactivación solo sin stock.** Una ubicación con algún `stock_saldo` distinto de cero no se desactiva (`UBICACION_CON_STOCK`, 409), mismo criterio que ADR-024 y ADR-026; se reactiva libremente. La comprobación toma la ubicación `FOR UPDATE` y lee las filas de saldo de esa ubicación `FOR SHARE`, para no competir con el orden global de bloqueo.
5. **Movimientos solo sobre activos.** Sobre una ubicación inactiva o un producto inactivo no se registran movimientos nuevos (`UBICACION_INACTIVA`, `PRODUCTO_INACTIVO`, 409; CAT-05: los inactivos no se ofrecen en operaciones nuevas). Los movimientos toman la ubicación `FOR SHARE` antes de sus costos y saldos, así que una desactivación simultánea se serializa con un ingreso: nunca queda stock en una ubicación recién desactivada.
6. **Modificar es reemplazar.** `UBICACION_MODIFICAR` se expone como `PUT /api/v1/stock/ubicaciones/{ubicacion_id}` con el **cuerpo completo** (`nombre`, `tipo`, `requiere_toma`, `activo`), no como `PATCH` parcial: la pantalla siempre tiene los cuatro campos y un reemplazo completo evita decidir qué significa "campo ausente" frente a "campo nulo". La tarea 7.1 del change hablaba de `PATCH`; se corrige a `PUT`.
7. **Permiso** `ADMIN_CONFIGURACION` (ADR-036). La lectura del listado usa `TRANSFERIR_STOCK`.

## Consecuencias

- Nada queda escondido en una ubicación invisible: para dar de baja un vehículo hay que vaciarlo antes (transferencia o ajuste, changes 14 y 15).
- La validación de toma para operar (STK-09) no se aplica todavía: nace con `jornada`, en el change 15. Hasta entonces `requiere_toma` es solo un indicador guardado.
- Una organización con un vehículo inactivo y otro activo con el mismo nombre no es posible: el nombre es único sin mirar el estado, así que para reutilizarlo hay que renombrar el viejo.
- El cliente HTTP que quiera cambiar un solo campo debe mandar los demás (la pantalla lo hace desde el formulario completo). Es una diferencia con la costumbre de `PATCH` de otros módulos; se documenta acá.
- `03` §9 se actualiza con `actualizado_en`, `actualizado_por_id`, el `CHECK` y el índice (texto exacto en `propuesta-docs.md`).

## Alternativas consideradas

- **La regla del vehículo solo en el dominio:** descartada: una migración o un SQL manual podrían romperla.
- **`requiere_toma` derivado del tipo (sin columna editable):** descartada: contradice STK-02, que lo pide como indicador propio.
- **Desactivar siempre, dejando el stock "congelado" hasta reactivar:** descartada: deja stock fuera de toda pantalla operativa.
- **No restringir movimientos sobre productos inactivos:** descartada: contradice CAT-05.
- **`PATCH` parcial para modificar:** descartada: ver punto 6.
