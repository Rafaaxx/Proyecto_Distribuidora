# ADR-023 — Puerto de verificadores de uso para congelar presentaciones (CAT-04, INV-18)

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-23 |
| Referenciado en | `openspec/changes/05-catalogo/design.md` D2; `03` §5; `02` §5.3 |

**Aprobado por el usuario el 2026-09-23**, generado durante la verificación del change 05 (grupo 13, tarea 13.4).

## Contexto

CAT-04 exige que las unidades base de una presentación ya "usada" en alguna operación no puedan modificarse (INV-18). Pero determinar si una presentación "fue usada" depende de tablas de módulos que **dependen de** `catalogo` (`costo_informado` del change 06, `compra_linea` del 11, `venta_linea` del 18a), y `02` §5.3 prohíbe que `catalogo` importe modelos o repositorios de módulos que dependen de él (evita el ciclo).

`01-dominio.md` no resuelve cómo un módulo de base (`catalogo`) puede consultar el estado de módulos que nacen después de él sin invertir la dependencia. El change 05 (`design.md` D2) resolvió esto con un mecanismo nuevo, reutilizable por al menos tres changes futuros (06, 11, 18a), lo que lo vuelve una decisión de arquitectura y no solo de secuencia (a diferencia de D1 del mismo change, que sí es una decisión de secuencia sin ADR).

## Decisión

`catalogo/service.py` expone un puerto de registro:

```python
def registrar_verificador_uso(nombre: str, funcion: Callable[[UUID, UUID, Session], bool]) -> None
```

Cada módulo que registra operaciones sobre presentaciones (costos informados, líneas de compra, líneas de venta) registra su propio verificador al arrancar la aplicación, igual que el patrón ya establecido para los handlers del bus de comandos (`commands/registro.py`).

`PRESENTACION_MODIFICAR` con unidades distintas a las actuales consulta **todos** los verificadores registrados; si alguno responde `True`, la escritura se rechaza con `UNIDADES_CONGELADAS`. En este change (05) la lista de verificadores está vacía en producción — no existe ningún módulo de operaciones todavía —, y las pruebas de INV-18 registran un verificador de prueba para ejercitar el camino de rechazo.

La ventana de carrera entre "se empieza a usar una presentación" y "se modifican sus unidades" no se cierra con un lock: se resuelve por diseño, porque `venta_linea` (y análogos) congelan `unidades_presentacion` en el momento de la operación (INV-18, PRC-23), así que una venta en vuelo conserva su valor aunque la presentación se modifique después. Los changes 06, 11 y 18a están nominados en `04-roadmap-changes.md` para registrar su propio verificador, con una prueba que cite INV-18 cada uno.

## Consecuencias

- Sin cambio de esquema (no agrega columnas a `presentacion`) y sin ciclo de importación entre módulos (`02` §5.3 se respeta).
- Ningún costo de contención adicional en las operaciones de venta/compra: el verificador solo se ejecuta cuando alguien intenta modificar las unidades de una presentación, no en cada operación que la usa.
- Riesgo nominado: un change futuro (06, 11, 18a) puede olvidar registrar su verificador y dejar INV-18 sin efecto para esa operación. Mitigado con la tarea nominada en `04-roadmap-changes.md` para cada uno y con una prueba que cite INV-18 por change.
- El registro ocurre en tiempo de arranque de la aplicación (mismo momento que el registro de handlers del bus), por lo que un módulo que no se importa nunca registra su verificador; esto es consistente con cómo ya funciona el registro de handlers (`commands/registro.py`) y no introduce un mecanismo nuevo de carga.

## Alternativas consideradas

- **Columna `presentacion.usada_desde timestamptz`** marcada por cada operación vía `catalogo/service.py`, con un trigger que impida cambiar `unidades_base` si no es nula. Descartada: agrega una columna que `03` no define (requeriría este mismo ADR y además actualizar `03`), y obliga a cada venta a escribir la fila de la presentación dentro de su propia transacción (contención adicional, un nivel más en el orden de bloqueo de `02` §7.3), incluso para ventas offline sincronizadas.
- **El catálogo consulta por SQL directo las tablas de los otros módulos.** Descartada de entrada: viola `02` §5.2 (la única excepción documentada es `reportes`).
