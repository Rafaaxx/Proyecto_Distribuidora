> Orden de trabajo: dentro de cada grupo se escribe primero la prueba que falla y después el código mínimo que la pasa (modo TDD estricto). Los grupos están ordenados por dependencia: esquema → modelos → repositorios → servicios → siembra → aislamiento.

## 1. Estructura de los dos módulos

- [x] 1.1 Crear `backend/app/modules/identidad/` con `__init__.py`, `models.py`, `repository.py`, `service.py` y `domain/` (sin `api.py`, `commands.py` ni `queries.py`: este change no expone rutas ni pasa por el bus, `design.md` D1).
- [x] 1.2 Crear `backend/app/modules/configuracion/` con la misma estructura.
- [x] 1.3 Agregar los contratos de import-linter para los dos módulos: `domain/` no importa FastAPI, SQLAlchemy ni nada de `app.core.db`; ningún módulo importa `models.py` ni `repository.py` del otro (`02` §5.2). Verificar con `python -m import_linter` que los contratos fallan si se introduce el import prohibido a propósito.

## 2. Migración de Alembic (antes de los modelos)

- [x] 2.1 Escribir la revisión de Alembic que crea `organizacion` con las columnas de `03` §4 (`id` uuid PK, `nombre`, `cuit` nulable, `moneda`, `zona_horaria`, `estado`), más `creado_en`, `actualizado_en` y `actualizado_por_id` de `03` §2.3 (es tabla maestra), y la restricción de dominio sobre `estado` (`ACTIVA`, `SUSPENDIDA`).
- [x] 2.2 Agregar en la misma revisión `configuracion_organizacion` con `organizacion_id` como PK y FK a `organizacion (id)`, y las 16 columnas restantes de `03` §4 con sus tipos exactos: `tolerancia_offline_valor` y `redondeo_multiplo` como `numeric(14,2)`, `intentos_pin_max` y `desvio_reloj_max_segundos` como `integer`, el resto `text`/`boolean`/`uuid`. Restricciones de dominio sobre `modo_impositivo`, `politica_credito_default`, `tolerancia_offline_tipo`, `redondeo_direccion`, `estado_facturacion_default` y `modalidad_iva_default`.
- [x] 2.3 Dejar `lista_precio_default_id` y `cliente_consumidor_final_id` nulables y **sin** clave foránea, con un comentario en la migración que nombre los changes 13 y 07 como responsables de agregar la FK compuesta (`design.md` D3).
- [x] 2.4 Agregar en la misma revisión `alicuota_iva` (`nombre`, `valor` `numeric(9,6)`, `activo`), `medio_pago` (`nombre`, `requiere_referencia` `boolean`, `activo`) y `motivo` (`ambito`, `nombre`, `activo`), cada una con `id`, `organizacion_id`, las columnas comunes de `03` §2.3 y la restricción de dominio de `ambito` sobre la lista cerrada de siete valores (`03` §4).
- [x] 2.5 Agregar a las cuatro tablas con `organizacion_id` la restricción `UNIQUE (organizacion_id, id)` y la FK de `organizacion_id` a `organizacion (id)` (`03` §2.4).
- [x] 2.6 Escribir el `downgrade` que elimina las cinco tablas en orden inverso y verificar `upgrade head` → `downgrade base` → `upgrade head` contra PostgreSQL real (`04` §2.1, punto 4).

## 3. Verificación estructural del esquema (spec `aislamiento-multiorganizacion`)

- [x] 3.1 Escribir en `backend/tests/integration/` la prueba que recorre `information_schema` sobre la base migrada y exige, para **toda** tabla de negocio (no una lista fija de nombres): `organizacion_id NOT NULL` y restricción única sobre `(organizacion_id, id)`. Citar `INV-02` en el nombre o docstring (`02` §15). Escenarios "Una tabla de negocio sin organización no llega a la base".
- [x] 3.2 Extender la prueba anterior para exigir que toda FK entre dos tablas de negocio incluya `organizacion_id`, exceptuando la propia referencia de `organizacion_id` a `organizacion (id)`. Escenario "El esquema no tiene referencias simples entre entidades de negocio".
- [x] 3.3 Verificar ambas comprobaciones en negativo: crear dentro de la prueba una tabla temporal que viole cada regla y comprobar que la verificación la detecta y nombra tabla y columna.
- [x] 3.4 Escribir la prueba de integración que confirma que la base rechaza: insertar con `organizacion_id` nulo, insertar con una organización inexistente, y una segunda fila de `configuracion_organizacion` para la misma organización. Escenarios homónimos de las specs `aislamiento-multiorganizacion` y `parametros-de-organizacion`.

## 4. Modelos SQLAlchemy

- [x] 4.1 Definir en `identidad/models.py` los modelos `Organizacion` y `ConfiguracionOrganizacion`, con `id` UUIDv7 desde `core/ids.py`, `timestamptz` en todos los momentos y carga de relaciones explícita (la carga diferida implícita está desactivada).
- [x] 4.2 Definir en `configuracion/models.py` `AlicuotaIva`, `MedioPago` y `Motivo` con el mismo criterio.
- [x] 4.3 Verificar con una prueba de integración que los modelos y la migración coinciden: `alembic revision --autogenerate` sobre la base migrada no produce ninguna operación.
- [x] 4.4 Confirmar que la prueba de INV-03 heredada de `01b` (catálogo de columnas sin punto flotante) sigue pasando con las cinco tablas nuevas, en particular `valor`, `tolerancia_offline_valor` y `redondeo_multiplo`.

## 5. Dominio puro

- [x] 5.1 Escribir en `identidad/domain/` las enumeraciones y validaciones puras de `estado`, `modo_impositivo`, `politica_credito_default`, `tolerancia_offline_tipo`, `redondeo_direccion`, `estado_facturacion_default` y `modalidad_iva_default`, con errores de dominio propios derivados de `DomainError` (`core/errors.py`) y código estable. Sin importar SQLAlchemy ni FastAPI (`02` §5.2).
- [x] 5.2 Escribir en `configuracion/domain/` la enumeración cerrada de `ambito` de `motivo` y la validación de `valor` de alícuota: debe ser `Decimal` exacto de hasta 6 decimales y rechazar `float` (INV-03, TR-02).
- [x] 5.3 Escribir las unitarias de dominio de 5.1 y 5.2, incluidos los escenarios de error de las specs: estado desconocido, política de crédito fuera de dominio, ámbito fuera de la lista cerrada, alícuota recibida como punto flotante, medio de pago con nombre vacío.
- [x] 5.4 Escribir la unitaria que fija `0.210000` como representación del 21 % y `0.000000` como alícuota válida (TR-02, `01` §4), sin inventar otros valores.

## 6. Repositorios con organización obligatoria

- [x] 6.1 Escribir `identidad/repository.py` con `organizacion_id` como **primer parámetro obligatorio** de todo método, incluido el filtro en cada consulta (`02` §8). Operaciones: crear organización, obtener organización por id, crear configuración, obtener configuración, actualizar configuración.
- [x] 6.2 Escribir `configuracion/repository.py` con el mismo contrato: crear, obtener por id, listar activos, listar por ámbito (solo `motivo`) y desactivar, para las tres tablas de catálogo. Ninguna operación de borrado (spec `catalogos-configurables`, "No existe operación de borrado de catálogo").
- [x] 6.3 Escribir la prueba que inspecciona por introspección las firmas de todos los métodos públicos de ambos repositorios y falla nombrando el método que no exige `organizacion_id` como primer parámetro. Escenario "Una operación de acceso a datos sin organización no llega a existir".
- [x] 6.4 Escribir la prueba de integración de aislamiento a nivel de datos: crear dos organizaciones con filas homónimas en cada catálogo y verificar que listar, obtener por id y desactivar desde una nunca alcanzan filas de la otra, y que la búsqueda con la organización equivocada devuelve "no encontrado" sin revelar existencia. Citar `INV-21` y `TR-08` en el nombre o docstring. Escenarios "Una consulta nunca ve filas de otra organización", "Buscar por identificador con la organización equivocada no encuentra nada", "Modificar con la organización equivocada no cambia nada", "Desactivar un elemento de otra organización no hace nada".
- [x] 6.5 Escribir la prueba de integración que confirma que la base rechaza una referencia compuesta cruzada entre organizaciones aunque el código no valide nada. Escenario "Una referencia cruzada entre organizaciones se rechaza en la base".

## 7. Servicios (interfaz pública de cada módulo)

- [x] 7.1 Escribir `identidad/service.py` exponiendo la lectura de organización y de configuración para otros módulos, y el alta de organización con su configuración en una sola operación. Sin `commit`: la transacción la gestiona quien llama (`02` §5.2); en este change, la sesión de la siembra o de la prueba.
- [x] 7.2 Escribir `configuracion/service.py` exponiendo alta, listado de activos, listado por ámbito y desactivación de los tres catálogos.
- [x] 7.3 Escribir la prueba que verifica que `identidad` y `configuracion` no se importan mutuamente por fuera de `service.py`, además del contrato de import-linter de 1.3.
- [x] 7.4 Escribir la prueba de integración que cubre el escenario "La configuración de una organización no es legible desde otra" a través del servicio, no solo del repositorio.
- [x] 7.5 Verificar que la lectura de la fecha de negocio a partir de `occurred_at` y la zona horaria de la organización usa el reloj inyectable de `core/clock.py`, con una prueba que fija la hora. Escenario "La fecha de negocio se deriva de la zona horaria de la organización".

## 8. Siembra de la organización inicial (`design.md` D4)

- [x] 8.1 Escribir el comando de siembra idempotente (`python -m app.seed`) que usa los servicios de 7.1 y 7.2, nunca SQL suelto, y que falla con error explícito si las tablas no existen. Escenario "Sembrar sobre una base sin migrar falla explícitamente".
- [x] 8.2 Sembrar la organización inicial con los valores de la columna "Organización inicial" de `01` §4: moneda `ARS`, zona horaria `America/Argentina/Mendoza`, estado `ACTIVA`, modo impositivo `A`, política de crédito `AUTORIZAR`, descuento manual habilitado, motivo obligatorio al usar lista no vigente `Sí`, estado de facturación inicial `NO_REQUIERE`, `intentos_pin_max` = 5.
- [x] 8.3 Dejar **sin valor** (nulos) los parámetros que `01` §4 marca como "A definir al configurar": tolerancia de crédito sin conexión (tipo y valor), motivo obligatorio en descuento manual, redondeo (múltiplo y dirección), venta a consumidor final genérico y modalidad de IVA al facturar. No inventar valores por omisión. Escenario "Un parámetro sin valor definido queda explícitamente sin definir".
- [x] 8.4 Dejar `lista_precio_default_id` y `cliente_consumidor_final_id` nulos: las tablas destino llegan en los changes 13 y 07 (`design.md` D3).
- [x] 8.5 Sembrar los catálogos de `01` §4: alícuotas `21%` (`0.210000`), `10,5%` (`0.105000`) y `0%` (`0.000000`); medios de pago efectivo, transferencia, cheque, billetera y tarjeta; motivos de ámbito `AJUSTE_STOCK`: rotura, vencimiento, muestra, consumo interno, diferencia de inventario y otro.
- [x] 8.6 Escribir la prueba de integración de idempotencia: sembrar, cambiar a mano la política de crédito a `BLOQUEAR`, sembrar de nuevo, y verificar que no hay organización ni configuración duplicada y que la política sigue en `BLOQUEAR`. Escenario "Sembrar dos veces no duplica ni pisa".
- [x] 8.7 Escribir la prueba de integración que verifica los seis motivos de `AJUSTE_STOCK` al listar por ámbito y que ninguno de otro ámbito aparece, y la de desactivación (el elemento deja de ofrecerse pero sigue siendo legible por id). Escenarios "Los motivos se listan por ámbito" y "Un elemento desactivado deja de ofrecerse".
- [x] 8.8 Documentar en `backend/README.md` que la siembra es un paso posterior a `alembic upgrade head`, con el comando exacto.

## 9. Ratchet de INV-21 sobre las rutas (`design.md` D1)

- [x] 9.1 Escribir en `backend/tests/integration/` la prueba que recorre dinámicamente `app.routes` (`02` §15), clasifica cada ruta como de sistema o de negocio contra una lista **enumerable y explícita** de rutas de sistema (`/salud`, `/version`, `/openapi.json`, `/docs`, `/redoc`) y falla nombrando ruta y método si aparece una ruta de negocio no declarada en la cobertura de aislamiento. Citar `INV-21` en el nombre o docstring. Escenarios "Una ruta de negocio sin cobertura de aislamiento hace fallar la verificación" y "Las rutas de sistema no requieren organización".
- [x] 9.2 Hacer que el mensaje de la prueba informe cuántas rutas de negocio cubrió (hoy, cero), para que la cobertura nula sea visible y no se confunda con cobertura completa (`design.md`, Risks).
- [x] 9.3 Verificar el ratchet en negativo: registrar dentro de la prueba una ruta de negocio ficticia y comprobar que la verificación falla nombrándola.
- [x] 9.4 Dejar en el archivo de la prueba un comentario que indique cómo un change futuro declara una ruta nueva en la cobertura, para que el change 03 no tenga que reinterpretarlo.

## 10. Cierre y verificación

- [x] 10.1 Correr la suite completa: `python -m pytest`, `python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy app`, `python -m import_linter`. Todo en verde, sin `Any` sin justificación. Verificado: 141 tests, ruff, mypy y `lint-imports` (3 contratos) limpios.
- [x] 10.2 Verificar que la CI de `.github/workflows/ci.yml` pasa con los dos módulos nuevos, sin cambios en el workflow. Confirmado: `.github/workflows/ci.yml` no requirió cambios; solo se agregaron excepciones al contrato de import-linter en `pyproject.toml` (ver nota de verificación abajo).
- [x] 10.3 Verificación manual del flujo principal: este change **no entrega pantalla** (`design.md` D5), así que el punto 5 de `04` §2.1 se declara no aplicable y se sustituye por: levantar `docker compose up`, correr `alembic upgrade head` y `python -m app.seed` contra la base de desarrollo, y comprobar con `psql` que existen la organización inicial, su fila de configuración, las 3 alícuotas, los 5 medios de pago y los 6 motivos, y que `/salud` sigue respondiendo. Verificado con `psql` real: organización "Organización inicial" (ARS, America/Argentina/Mendoza, ACTIVA), configuración con modo_impositivo A / política AUTORIZAR / intentos_pin_max 5 y los parámetros "a definir" (`tolerancia_offline_tipo`, `redondeo_direccion`) correctamente en blanco, 3 alícuotas, 5 medios de pago, 6 motivos, `/salud` → `{"estado":"ok"}`.
- [x] 10.4 Anotar en `docs/04-roadmap-changes.md` que INV-21 queda cerrado **parcialmente** (ratchet instalado, cero rutas de negocio cubiertas) y que el change 03 lo completa con su primer endpoint. Hecho: fila del change 02 en `04` §5 marcada `INV-21 (parcial)*` con nota al pie explicando la razón (D1) y qué lo completa.
- [x] 10.5 Señalar a revisión humana el ADR pendiente de `design.md` D2 (precedencia de `03` §3 sobre `02` §5.1 para la ubicación de tablas). No redactarlo desde este change. Resuelto por el usuario sin ADR: corrigió directamente `docs/02-arquitectura.md` §5.1 para que coincida con `03` §3 (organización y su configuración bajo `identidad`; `configuracion` solo con los tres catálogos). Es una corrección de redacción entre documentos que ya coincidían en sustancia, no una decisión de arquitectura nueva.

### Nota de verificación (orquestador, tras un agente de apply que se colgó a mitad de cierre)

El agente que implementó este change completó los grupos 1-9 correctamente pero se colgó (timeout de 600s sin progreso) antes de correr la verificación final y marcar `tasks.md`. Al retomar, la verificación encontró y corrigió tres problemas reales que el agente no había cerrado:

1. **`import-linter` roto de verdad** (no solo un warning): `identidad/service.py` y `configuracion/service.py` importan `sqlalchemy.orm.Session` como type hint (no hay bus de comandos hasta el change 04, así que `service.py` recibe la sesión directamente). Faltaban las excepciones `app.modules.{identidad,configuracion}.service -> sqlalchemy` en `pyproject.toml`, agregadas junto a las de `models`/`repository`.
2. **Fuga de estado entre tests de integración**: `test_alembic_integracion.py` (heredado de `01a`/`01b`) corre `upgrade → downgrade → upgrade → downgrade` contra la base compartida de la sesión de pytest y terminaba en `downgrade base` (sin tablas). Con el esquema real de este change, cualquier test que corriera después fallaba con `relation "organizacion" does not exist` según el orden de recolección. Se agregó un `upgrade head` final para dejar la base como la encontró.
3. **Warning de SQLAlchemy por transacción ya desasociada** en `db_session` (conftest.py): un `IntegrityError` esperado en una prueba negativa dejaba la sesión en estado "solo rollback" y el rollback del fixture en el teardown chocaba con eso. Se agregó `join_transaction_mode="create_savepoint"` a la sesión de prueba (patrón estándar de SQLAlchemy 2.0 para este caso).

Con las tres correcciones, ruff, ruff format, mypy, `lint-imports` (3 contratos) y `pytest` (141 tests, en cualquier orden, sin warnings de fuga) pasan limpio, y `docker compose build backend` confirma que las dependencias están completas fuera del `.venv` local.
