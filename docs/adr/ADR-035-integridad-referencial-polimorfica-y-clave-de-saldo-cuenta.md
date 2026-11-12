# ADR-035 — Integridad referencial polimórfica del libro de cuenta corriente, validación sin puertos y clave de `saldo_cuenta`

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-29 |
| Referenciado en | `openspec/changes/08-cuentas-corrientes/design.md` D6, D7 y D11 y `specs/cuentas-corrientes/saldo-de-cuenta`; `02-arquitectura.md` §5.3; `03-modelo-de-datos.md` §2.3, §2.4 y §12; INV-02, INV-21; ADR-015, ADR-023, ADR-025 |

**Decisiones (D6, D7 y D11, opción A en cada una) aprobadas por el usuario el 2026-09-29. Texto del ADR aprobado por el usuario el 2026-09-30; estado *Vigente*.**

## Contexto

`03` §2.4 exige que las claves foráneas entre entidades de negocio sean compuestas e incluyan `organizacion_id`, para que la base impida referencias entre organizaciones sin depender del código. Pero `cuenta_movimiento.entidad_id` (y `saldo_cuenta.entidad_id`) apuntan a `cliente` o a `proveedor` según `cuenta_tipo`, y una clave foránea común no puede apuntar a dos tablas. Además, `02` §5.3 dice que `cuentas_corrientes` no depende de ningún otro módulo de negocio (`clientes` y `proveedores` dependen de él, no al revés), así que el libro no puede preguntarle a esos módulos si una entidad existe. Por último, `03` §2.3 dice que toda tabla de negocio tiene `id`, y `03` §12 le da a `saldo_cuenta` una clave primaria compuesta sin `id`; la prueba genérica de INV-02 (`test_inv02_aislamiento_esquema.py`) exige `UNIQUE (organizacion_id, id)`.

Se registra como ADR porque fija una técnica poco habitual (FK sobre columnas generadas) y un reparto de responsabilidades entre módulos que 11, 12, 17 y 18a van a dar por sentado, y porque aclara `03` §2.3.

## Decisión

1. **Columnas generadas con FK compuestas (D6).** `cuenta_tipo` y `entidad_id` se mantienen como dice `03` §12. Se agregan dos columnas **generadas por PostgreSQL** en `cuenta_movimiento` y en `saldo_cuenta`: `cliente_id` (igual a `entidad_id` si `cuenta_tipo = CLIENTE`, si no nulo) y `proveedor_id` (ídem para `PROVEEDOR`). Cada una tiene su FK compuesta: `(organizacion_id, cliente_id) → cliente (organizacion_id, id)` y `(organizacion_id, proveedor_id) → proveedor (organizacion_id, id)`. Nadie escribe esas columnas. Con esto la base rechaza un movimiento que apunte a una entidad de otra organización, a una inexistente o a un proveedor con `cuenta_tipo = CLIENTE`.
2. **Efecto secundario buscado (D6).** Al insertar un movimiento o crear la fila de saldo, PostgreSQL toma un bloqueo liviano sobre la fila del cliente o del proveedor. Ese bloqueo serializa el saldo inicial con una reactivación concurrente del cliente (ADR-034 punto 4). Se prueba con commits reales.
3. **Aclaración de `03` §2.3.** La regla "toda tabla de negocio tiene `id`" no se aplica a una tabla cuya clave natural es compuesta y ninguna otra tabla referencia; el caso es `saldo_cuenta` (clave `(organizacion_id, cuenta_tipo, entidad_id)`). Lo que INV-02 exige es que la organización esté en la clave, y así queda. La FK sobre columnas generadas (punto 1) es una forma admitida de cumplir `03` §2.4 cuando una referencia es polimórfica.
4. **Validación de la entidad sin puertos (D7).** La escritura (`SALDO_INICIAL_REGISTRAR`, `POST /api/v1/cuentas-corrientes/saldos-iniciales`) vive en `cuentas_corrientes` y valida la entidad **por la FK del punto 1**: si la base rechaza la referencia, el repositorio lo traduce a `RecursoNoEncontradoError` (404, INV-21), como ya hace catálogo con el proveedor (ADR-025). El consumidor final se reconoce leyendo la configuración de la organización por `identidad/service.py` (dependencia permitida). No se registran puertos en `clientes` ni en `proveedores`.
5. **Las lecturas viven con su entidad (D7).** `GET /api/v1/clientes/{id}/cuenta-corriente` está en `clientes/api.py` y `GET /api/v1/proveedores/{id}/cuenta-corriente` en `proveedores/api.py`: esos módulos ya saben responder 404 para una entidad ajena o inexistente (antes de leer el libro, sin revelar saldo ni movimientos) y llaman a `cuentas_corrientes/service.py`, dependencia permitida por `02` §5.3. Coincide con `02` §11, que agrupa "clientes, estado de cuenta".
6. **Clave de `saldo_cuenta` (D11).** Se sigue `03` §12: clave primaria compuesta `(organizacion_id, cuenta_tipo, entidad_id)`, sin `id`. La prueba de INV-02 se **amplía** (no se exime a la tabla): además de `UNIQUE (organizacion_id, id)` y de `organizacion_id` como clave primaria entera, acepta una clave primaria compuesta **que empiece por** `organizacion_id`, y `saldo_cuenta` es el caso probado, con su caso negativo (una clave compuesta que no empieza por `organizacion_id` se detecta). Lo mismo servirá para `stock_saldo` y `costo_producto` en el change 09.

## Consecuencias

- Una referencia inválida (ajena, inexistente o de tipo cruzado) la rechaza la base aunque el servicio tuviera un error; una prueba de migración intenta las tres.
- La técnica es poco común y queda documentada aquí y probada: los cambios futuros sobre el libro deben mantener las columnas generadas y sus FK.
- `cuentas_corrientes` no necesita importar `clientes` ni `proveedores`; los contratos de import-linter lo verifican. La contrapartida es que el libro no puede distinguir entre "no existe" y "es de otra organización", y ambos casos responden 404, que es lo que pide INV-21.
- Un cliente o un proveedor con movimientos no se puede borrar de la base (la FK lo impide), coherente con CLI-04 (no se eliminan, se inactivan).
- Ninguna fila de `saldo_cuenta` es referenciada por otra tabla, así que no hace falta un `id` en ella.

## Alternativas consideradas

- **Reemplazar `entidad_id` por dos columnas normales `cliente_id` y `proveedor_id` nulables**, con un `CHECK` de que exactamente una está cargada y coincide con `cuenta_tipo`: descartada: equivalente en garantías, pero cambia el modelo de `03` §12 y el índice principal.
- **Sin FK, con la existencia y la organización validadas por el servicio**: descartada: contradice `03` §2.4 y la prueba genérica `test_inv02_ninguna_fk_entre_tablas_de_negocio_es_simple` pasaría sin proteger nada; un error del servicio dejaría deuda de una organización colgada de otra.
- **Puertos registrados por `clientes` y `proveedores`** que respondan "existe y en qué estado está" (el patrón de ADR-023 y ADR-025, con falla cerrada): descartada: solo hace falta si se exige leer el estado de la entidad, que ADR-034 punto 3 no exige; sería el tercer uso del patrón y ADR-025 ya advirtió que en ese caso convendría un mecanismo común, que agranda el change.
- **Dos comandos, uno en `clientes` y otro en `proveedores`**: descartada: se aparta de `02` §6.5 (un solo `SALDO_INICIAL_REGISTRAR`) y duplica la validación del importe y del sentido.
- **Agregar un `id` UUIDv7 a `saldo_cuenta`** con `UNIQUE (organizacion_id, id)` y `UNIQUE (organizacion_id, cuenta_tipo, entidad_id)`: descartada: agrega una columna que nadie usa.
- **Agregar `saldo_cuenta` a la lista de tablas exentas** de la prueba de INV-02: descartada: debilita la prueba; esa lista es solo para catálogos globales.
