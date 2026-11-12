# ADR-025 — `catalogo` valida el proveedor del producto mediante un puerto de consulta (CAT-01, CAT-05, CAT-06)

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-23 |
| Referenciado en | `openspec/changes/06-proveedores-y-costos-informados/design.md` D9 (y D5, D8, D13, D14, D16); `02` §5.3; ADR-023 |

**Decisión de diseño (D9, opción A) aprobada por el usuario el 2026-09-23. Texto del ADR aprobado por el usuario el 2026-09-23; estado *Vigente*.**

## Contexto

El change 06 hace obligatorio el proveedor del producto (CAT-01, CAT-06) y exige que el proveedor asignado esté activo (D5: un proveedor inactivo no se asigna a un producto, salvo conservar el actual en `PRODUCTO_MODIFICAR`). Quien valida la asignación es `catalogo` (`PRODUCTO_CREAR` y `PRODUCTO_MODIFICAR` v2), pero `02` §5.3 fija `proveedores ──► catalogo` y `catalogo ──► (sin dependencias de negocio)`: `catalogo` no puede importar `proveedores` sin crear un ciclo.

La **existencia** y la **pertenencia** a la organización del proveedor las garantiza la base con la clave foránea compuesta `fk_producto__proveedor` `(organizacion_id, proveedor_id) → proveedor` (el repositorio de catálogo traduce su violación a 404, D6 del change 05). La **actividad** del proveedor, en cambio, no la expresa ninguna restricción de base, y TR-10 exige que el servidor valide todo lo que la regla pide.

ADR-023 ya resolvió un problema análogo (verificadores de uso de presentaciones) con un puerto de registro en `catalogo/service.py`. Este caso usa el mismo mecanismo con otra firma y, sobre todo, otra semántica ante la ausencia de registro: ADR-023 tolera la lista vacía (ningún módulo de operaciones existe todavía), mientras que aquí la ausencia de la consulta dejaría asignar proveedores sin validar. Por eso no se asume cubierto por ADR-023.

## Decisión

`catalogo/service.py` expone un puerto de registro de una única consulta:

```python
def registrar_consulta_proveedor(
    funcion: Callable[[UUID, UUID, Session], EstadoProveedor | None],
) -> None
```

`funcion(organizacion_id, proveedor_id, sesion)` devuelve `None` si el proveedor no existe en la organización y, si existe, su estado. `EstadoProveedor` es un value object con `activo: bool` y `nombre: str`. `proveedores` la registra al arrancar la aplicación (mismo momento que los handlers del bus y los verificadores de ADR-023) y lee el proveedor con `FOR SHARE`, para serializar con `PROVEEDOR_MODIFICAR`, que lo toma con `FOR UPDATE` (D14).

`nombre` se agregó a `EstadoProveedor` (además de `activo`) para resolver, sin ampliar el alcance de este ADR, la Open Question de `design.md` sobre cómo el formulario de producto muestra el proveedor actual cuando está inactivo (D8, opción B aprobada por el usuario el 2026-09-23): el detalle de producto (`catalogo`) usa este mismo puerto para obtener el nombre real del proveedor asignado, en vez de mostrar un texto genérico, sin que `catalogo` lea la tabla `proveedor` ni se amplíe el permiso de `GET /proveedores/opciones`.

`crear_producto` y `modificar_producto` usan la consulta así:

- `None` (inexistente o ajeno) → 404 (INV-21).
- Inactivo y distinto del proveedor actual del producto → `PROVEEDOR_INACTIVO`.
- Inactivo e igual al actual en `PRODUCTO_MODIFICAR` → se acepta (conservar la asignación).
- **Sin consulta registrada → la operación falla con un error de configuración** (falla cerrado): nunca se acepta un proveedor sin validarlo.

La clave foránea compuesta se mantiene como garantía de base independiente del puerto.

## Consecuencias

- Sin ciclo de importación: `catalogo` no conoce `proveedores`; `02` §5.3 se respeta y el contrato de import-linter `catalogo-solo-por-service-ajeno` prohíbe `app.modules.proveedores` completo.
- Validación completa en el servidor (TR-10): existencia y pertenencia por la base, actividad por el puerto.
- Una desactivación de proveedor y una asignación simultáneas se serializan por el par `FOR UPDATE` / `FOR SHARE`: nunca queda un producto activo recién asignado a un proveedor recién desactivado (complementa ADR-026).
- Riesgo: un arranque que no importe `proveedores` deja el puerto vacío. Mitigado por la semántica de falla cerrada y por una prueba de arranque que verifica que `app.main` registra la consulta.
- Segundo uso del patrón de puertos de ADR-023; si aparece un tercero, conviene evaluar un mecanismo común de registro.

## Alternativas consideradas

- **Solo la clave foránea, sin chequeo de actividad.** Descartada: permite asignar proveedores inactivos, contra D5 y TR-10.
- **`catalogo` importa `proveedores.service`.** Descartada: ciclo prohibido por `02` §5.3.
- **`catalogo` consulta por SQL directo la tabla `proveedor`.** Descartada: viola `02` §5.2 (la única excepción documentada es `reportes`).
- **Puerto que acepta sin validar si no hay consulta registrada** (semántica de ADR-023). Descartada: un error de arranque se convertiría en datos inválidos en silencio.
