# Verificación — 08-cuentas-corrientes

> Documento de verificación del change (`tasks.md` grupos 8 y 9). Las secciones 8 y 9.2 están completas y ejecutadas por el agente. **Quedan pendientes del usuario:** 9.1 (revisar y aprobar el texto de los ADR-033 a ADR-035 y de `propuesta-docs.md`, antes de tocar `docs/`), 9.3 (recorrido manual en el navegador, no delegable) y una decisión sobre 8.7 (un hallazgo de lint previo al change, ver §8.7). Todo lo que depende de esas tres cosas figura como *pendiente* en la definición de terminado de §9.2.

## 8. Pruebas backend — resumen de evidencia

Detalle por tarea en `tasks.md` 8.1 a 8.7. Metodología: las pruebas del grupo 8 caracterizan código ya construido (grupos 2 a 6, en TDD estricto). Cada prueba nueva se probó capaz de fallar antes de darla por buena: mutando temporalmente el código de producción (y restaurándolo, verificado con `diff`) o, donde la regla la sostienen dos capas, contra una expectativa equivocada.

| Tarea | Resultado |
| --- | --- |
| 8.1 (comandos de `SALDO_INICIAL_REGISTRAR`) | Los 17 escenarios de `saldo-inicial` estaban cubiertos por los grupos 4 a 6, salvo tres brechas que se cerraron: rechazo real del bus al modo `OFFLINE` (`procesar_lote` → `RECHAZADO` / `MODO_NO_ADMITIDO_PARA_TIPO`, sin reserva ni movimiento), estados admitidos por el bus (cliente `ACTIVO`/`SUSPENDIDO`/`INACTIVO`, proveedor activo/inactivo) y `sentido = SUMA` por HTTP (422 sin efectos). |
| 8.2 (INV-13 con Hypothesis en PostgreSQL) | `tests/properties/test_inv13_saldo_cuenta_postgres.py`: 2 propiedades (30 ejemplos cada una; cuatro cuentas, todo el catálogo de tipos, momentos con empates) más falla inyectada a mitad de operación (INV-01). |
| 8.3 (INV-05) | `cuenta_movimiento` en `TABLAS_DE_LIBRO_DECLARADAS`; privilegios exactos comprobados; `UPDATE` y `DELETE` rechazados por la base. |
| 8.4 (INV-02 / INV-21) | Archivo dedicado con 6 pruebas de aislamiento de las tres rutas; `test_inv02` exige PK compuesta que empiece por `organizacion_id` (D11) con caso negativo; dispositivo inexistente agregado a la migración. |
| 8.5 (concurrencia) | `tests/concurrency/test_cuentas_corrientes_concurrencia.py`: 6 pruebas con commits reales. |
| 8.6 (migración con datos) | Ciclo `upgrade → downgrade -1 → upgrade` con movimientos y saldos confirmados. |
| 8.7 (suite completa) | Todo en verde salvo el hallazgo previo de `ruff check` descrito abajo. |

### Evidencia RED (mutación o expectativa equivocada) de las pruebas nuevas

| Prueba nueva | Cómo se probó que puede fallar | Resultado |
| --- | --- | --- |
| `test_inv05_*` (3) | `GRANT SELECT, INSERT, UPDATE` sobre `cuenta_movimiento` en la migración | 3 fallan (`DID NOT RAISE`, privilegios distintos) |
| `test_inv21_aislamiento_endpoints_cuentas_corrientes.py` (6) | Sin traducción de la FK a 404 en el repositorio; sin el 404 previo en las dos lecturas; expectativas invertidas en las dos restantes (una regla que sostienen dos capas) | 6 fallan |
| `test_inv02_detecta_una_pk_compuesta_que_no_empieza_por_organizacion_id` | Se desactiva la comprobación de orden de la clave | falla |
| `test_un_dispositivo_inexistente_se_rechaza` | Se envía un dispositivo existente | falla |
| `test_inv13_*_postgres` (2) | El servicio deja de aplicar el efecto de los movimientos que reducen | 2 fallan |
| Concurrencia: primera fila | Se quita `ON CONFLICT DO NOTHING` | `IntegrityError` (`pk_saldo_cuenta`) |
| Concurrencia: cuentas distintas | `LOCK TABLE saldo_cuenta` al bloquear (bloqueo global) | "B tuvo que esperar a A" (tras 30 s) |
| Concurrencia: misma cuenta | Lectura sin bloqueo más escritura no atómica del saldo | falla la variante de 6 hilos (actualización perdida); la de 2 hilos no alcanza a exponerla |
| Concurrencia: reactivación | El servicio deja de consultar `verificar_operaciones` | falla el orden determinista |
| `test_el_ciclo_de_migracion_con_datos_...` | La bajada además vacía `proveedor` | falla (`assert 0 >= 1`) |
| Bus `OFFLINE` | `admite_offline=True` en la declaración del tipo | falla |
| Estados admitidos | Expectativa de saldo distinta | falla |
| `sentido = SUMA` por HTTP | El esquema deja de restringir el sentido | **pasa igual**: el dominio (`validar_sentido`) vuelve a rechazarlo con 422. Es defensa en profundidad y no un defecto de la prueba: la prueba fija el comportamiento observable, que sigue siendo 422 sin efectos. |
| `test_cuentas_corrientes_libro_sin_rutas_de_edicion.py` | Se agrega una ruta `DELETE` al `api.py` del módulo | falla; además una prueba en negativo con una app sintética |

### 8.7 — Suite completa

| Comando | Resultado |
| --- | --- |
| `python -m pytest -q --ignore=tests/concurrency` | **1644 passed** (baseline del grupo 7: 1623; +21 de este grupo) y, agregada después, la prueba de rutas: **1646** en total (778 en `tests/unit` + `tests/properties` corridos de nuevo) |
| `python -m pytest tests/concurrency` (aparte) | **17 passed** (11 previas + 6 nuevas) |
| `python -m pytest tests/fixtures_compartidos/` | **56 passed**, sin cambios en los fixtures |
| `python -m ruff format --check .` | 261 archivos ya formateados (más el archivo de la prueba de rutas, formateado) |
| `python -m mypy app` | sin errores (104 archivos) |
| `lint-imports` | 14 contratos cumplidos, 0 rotos |
| `python -m ruff check .` | **1 hallazgo previo al change:** `I001` (orden de imports) en `backend/tests/fixtures_compartidos/test_cst02_costo_base_fixtures.py`. Ya ocurre sobre una copia limpia de `HEAD` (commit del change 06) con ruff 0.16.8, cuya versión no está fijada en `requirements-dev.txt`. **No se tocó.** Corrección de una línea (`ruff check --fix` sobre ese archivo) a criterio del usuario. Todo lo demás pasa. |

Frontend: no se modificó en este grupo; sigue vigente el resultado del grupo 7 (typecheck, lint sin errores, 411 pruebas, build).

Pruebas inestables conocidas, no tocadas: `test_identidad_commands_maestros.py` (rotación de PIN) y `app-routing.test.tsx` bajo carga. No fallaron en las corridas de este grupo.

Hallazgos de código de producción por las pruebas nuevas: **ninguno** (no hubo defectos que corregir).

## 2.1 — Cobertura de escenarios por spec (`docs/04` §2.1 punto 2)

Las cinco specs delta tienen 61 escenarios. Cada uno tiene al menos una prueba; la tabla nombra la prueba principal.

| Spec | Escenarios | Pruebas principales |
| --- | --- | --- |
| `cuentas-corrientes/saldo-inicial` | 17 | `test_cuentas_corrientes_comandos.py`, `test_cuentas_corrientes_api.py::TestSaldoInicialRegistrar`, `test_cuentas_corrientes_service.py` (estados, corrección, `CUENTA_CON_OPERACIONES`, consumidor final) |
| `cuentas-corrientes/libro-de-cuenta-corriente` | 17 | `test_cuentas_corrientes_service.py` (datos del movimiento, saldo, catálogos, entidad ajena, consistencia), `test_cuentas_corrientes_migracion.py` (importe positivo, FK, `CHECK`), `test_inv05_dos_roles.py`, `test_cuentas_corrientes_libro_sin_rutas_de_edicion.py`, `test_inv13_saldo_cuenta_postgres.py`, `test_cuentas_corrientes_concurrencia.py` |
| `cuentas-corrientes/estado-de-cuenta` | 10 | `test_cuentas_corrientes_service.py` (orden, período, paginación, empates) y `test_cuentas_corrientes_api.py::TestEstadoDeCuentaDe...` (permisos, 404 ajeno, límite) |
| `cuentas-corrientes/administracion-de-cuentas-corrientes` | 9 | `CuentaCorrienteScreen.test.tsx`, `SaldoInicialScreen.test.tsx`, `ClienteFormScreen.test.tsx` y `ProveedorFormScreen.test.tsx` (frontend, grupo 7) |
| `clientes/fichas-de-cliente` (delta CLI-06) | 8 | `test_clientes_comandos.py` (reactivar con y sin movimientos), `test_cuentas_corrientes_concurrencia.py::TestReactivacionDeClienteContraSaldoInicial` y las pruebas existentes del change 07 |

## 9.1 — ADR y `docs/` (PENDIENTE de revisión del usuario)

- `docs/adr/ADR-033-permisos-de-cuenta-corriente.md` (D1, D2), `docs/adr/ADR-034-reglas-del-saldo-inicial-y-del-libro-de-cuenta-corriente.md` (D3, D4, D8, D9, D12, más las decisiones de implementación aprobadas el 2026-09-29: sentido fijo por tipo solo en el dominio, reglas del estado de cuenta y rótulos de la interfaz) y `docs/adr/ADR-035-integridad-referencial-polimorfica-y-clave-de-saldo-cuenta.md` (D6, D7, D11). Los tres con estado *Propuesto*.
- `openspec/changes/08-cuentas-corrientes/propuesta-docs.md`: el texto exacto propuesto (antes/después) para `docs/01-dominio.md` (CC-08 en §12.1; alcance de tres permisos en §19) y `docs/03-modelo-de-datos.md` §12 (`dispositivo_id`, columnas generadas y FK de `cuenta_movimiento`; clave, columnas generadas y carga perezosa de `saldo_cuenta`).
- `docs/01-dominio.md` y `docs/03-modelo-de-datos.md` **no se editaron**. Al aprobar: los ADR pasan a *Vigente*, se aplica el texto de `propuesta-docs.md` y se marca 9.1.

## 9.2 — Definición de terminado (`docs/04-roadmap-changes.md` §2.1)

| # | Criterio | Estado |
| --- | --- | --- |
| 1 | Las pruebas que exige `02` §15 para su alcance pasan en CI | Cumple en local: unit, integration, properties (1646) y concurrency (17) en verde; frontend 411 (grupo 7); `ruff format`, `mypy` y `lint-imports` limpios. **Reserva:** `ruff check .` marca un `I001` previo al change (§8.7), a criterio del usuario. |
| 2 | Cada escenario de sus specs tiene al menos una prueba que lo cubre | Cumple: 61 escenarios, ver tabla de §2.1 (la auditoría del grupo 8 cerró cuatro brechas: bus `OFFLINE`, estados admitidos, `sentido = SUMA` por HTTP y "no existe ruta que edite o borre movimientos"). |
| 3 | Los invariantes que toca tienen prueba que los cita por ID | Cumple: INV-01 (falla inyectada, concurrencia), INV-02 y INV-21 (esquema y endpoints), INV-03 (`test_inv03_sin_punto_flotante.py`, sin cambios), INV-05 (libro sin `UPDATE`/`DELETE`), INV-06 (doble envío) e INV-13 (Hypothesis de dominio y contra PostgreSQL). |
| 4 | La migración de Alembic sube y baja limpia sobre una base con datos | Cumple: `test_el_ciclo_de_migracion_con_datos_sube_baja_y_sube_sin_tocar_lo_ajeno` (8.6) y `test_downgrade_elimina_ambas_tablas_y_upgrade_las_recrea`. |
| 5 | Se probó a mano el flujo principal en el navegador | **PENDIENTE:** lo ejecuta el usuario (§9.3). |
| 6 | Las specs delta se archivaron en `openspec/specs/` y `04-roadmap-changes.md` quedó actualizado | **PENDIENTE:** se hace en `/opsx archive`, después de 9.1 y 9.3. La nota de roadmap para el change 10 está más abajo. |
| 7 | Si se tomó una decisión nueva, quedó como ADR | **Redactado, PENDIENTE de aprobación:** ADR-033, ADR-034 y ADR-035 en estado *Propuesto* (§9.1). D14 (`dispositivo_id`) queda reflejada en `docs/03` por `propuesta-docs.md`, sin ADR propio (así lo fija `design.md`). |

**Conclusión:** el trabajo de código y de pruebas está terminado. El change queda listo para `/opsx archive` cuando el usuario (a) apruebe los ADR y el texto de `propuesta-docs.md` (9.1), (b) ejecute el recorrido de §9.3 y (c) decida sobre el `I001` previo (8.7).

### Nota de roadmap para el change 10

Para `docs/04-roadmap-changes.md`, en la fila del change 10 (`importacion-inicial`), al archivar con confirmación del usuario:

> **Deuda nominada por el change 08 (`cuentas-corrientes`) para el change 10 (`importacion-inicial`):** la importación de saldos iniciales reutiliza `cuentas_corrientes/service.py::registrar_saldo_inicial` fila por fila, con el permiso `IMPORTAR_DATOS` (ADR-033). Hereda CC-08 y ADR-034: varias filas por cuenta son válidas mientras la cuenta no tenga movimientos de otro tipo (`CUENTA_CON_OPERACIONES` en caso contrario); el consumidor final se rechaza (`CONSUMIDOR_FINAL_SIN_CUENTA`); una entidad ajena o inexistente responde 404 (no hay puertos: la FK compuesta lo decide, ADR-035); el importe es positivo con hasta dos decimales y el sentido es `AUMENTA` o `REDUCE`. Cada fila rechazada se traduce a su número de fila en el informe de errores. Como `SALDO_INICIAL_REGISTRAR` es solo online, la importación corre en el servidor.

## 9.3 — Recorrido manual en el navegador (PENDIENTE — lo ejecuta el usuario)

### Preparación del entorno

1. Verificar que existe un `.env` en la raíz del repo con `APP_MIGRATIONS_DB_PASSWORD`, `APP_RUNTIME_DB_PASSWORD`, `JWT_SECRET` y `ADMIN_PASSWORD` (`CLAUDE.md` §4: ningún secreto por defecto).
2. Levantar el stack:
   ```bash
   docker compose up -d
   ```
3. Aplicar las migraciones (incluye `cuenta_movimiento` y `saldo_cuenta` de este change):
   ```bash
   docker compose exec backend alembic upgrade head
   ```
4. Sembrar la organización inicial, los cinco roles y el usuario `admin` (idempotente):
   ```bash
   docker compose exec -e ADMIN_PASSWORD=<la contraseña de .env> backend python -m app.seed
   ```
   Organización: slug `organizacion-inicial`. Administrador: `admin`.
5. Abrir el frontend en `http://localhost:5173` (el API responde en `http://localhost:8000`; `docker compose ps` si el puerto es otro). Si el contenedor del frontend no refleja los cambios, reiniciarlo solo si el polling de archivos está desactivado.

### Crear un usuario con el rol "Administración" (`GESTIONAR_CLIENTES` y `GESTIONAR_PROVEEDORES`, sin `IMPORTAR_DATOS`)

No hay pantalla de usuarios todavía, así que se crea por API (mismo procedimiento que el change 07; en PowerShell se usa `Invoke-RestMethod` con los mismos campos).

1. Buscar el `id` del rol:
   ```bash
   docker compose exec postgres psql -U distribuidora -d distribuidora -c \
     "SELECT id, nombre FROM rol WHERE nombre = 'Administración';"
   ```
2. Login como `admin` y copiar el `access_token`:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"organizacion_slug":"organizacion-inicial","usuario":"admin","contrasena":"<ADMIN_PASSWORD>","dispositivo_id":"00000000-0000-0000-0000-000000000001","nombre_dispositivo":"Verificación 08"}'
   ```
3. Crear el usuario `administracion`:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/identidad/usuarios \
     -H "Authorization: Bearer <access_token>" \
     -H "Operation-Id: 0193a000-0000-7000-8000-000000000801" \
     -H "Content-Type: application/json" \
     -d '{"usuario":"administracion","nombre":"Administración de Prueba","email":null,"password":"una-contrasena-larga-123","rol_id":"<id del paso 1>"}'
   ```

### Flujo con `admin` (Administrador: tiene `IMPORTAR_DATOS`)

Entrar en el frontend como `admin` / `organizacion-inicial`.

| # | Paso | Resultado esperado |
| --- | --- | --- |
| 1 | En "Clientes", dar de alta `Kiosco La Esquina` (dirección y contacto cualquiera) y abrir su ficha | La ficha muestra el bloque "Cuenta corriente" con el saldo en cero y el enlace "Cuenta corriente" |
| 2 | Entrar a "Cuenta corriente" | Título "Cuenta corriente", estado de cuenta vacío con saldo cero, y el botón "Registrar saldo inicial" a la vista |
| 3 | "Registrar saldo inicial": importe `150000.00`, sentido "Nos debe", enviar | Vuelve a la cuenta corriente; una línea "Saldo inicial" que aumenta `$ 150.000,00` con saldo acumulado `$ 150.000,00`; el saldo dice "Nos debe $ 150.000,00" |
| 4 | Corregir el error de carga: "Registrar saldo inicial" con importe `20000.00` y sentido "Saldo a favor del cliente" | Dos líneas de saldo inicial (la segunda reduce `$ 20.000,00`); acumulados `$ 150.000,00` y `$ 130.000,00`; el saldo dice "Nos debe $ 130.000,00". Ninguna línea se edita ni se borra |
| 5 | Filtro de período: en "Desde" poner la fecha de mañana y "Filtrar" | Sin movimientos y "Saldo anterior" en `$ 130.000,00` |
| 6 | Filtro con "Desde" = hoy | Las dos líneas, con el acumulado que arranca de cero; los importes y las fechas en la zona horaria de la organización |
| 7 | Poner "Desde" posterior a "Hasta" | El formulario avisa el error de período y no pide nada al servidor |
| 8 | "Quitar filtro" | Vuelve la cuenta completa |
| 9 | Intentar registrar un saldo inicial con importe `0`, `10.005` y `abc` | Cada uno se rechaza junto al campo y no se envía nada |
| 10 | Registrar un saldo inicial y, sin recargar, repetir el envío con el botón mientras la red está cortada (opcional: DevTools → Offline) | Avisa que se requiere conexión y que no se encola; al volver la red, el reintento del mismo dato no duplica el movimiento (mismo `operation_id`) |
| 11 | En "Proveedores", dar de alta un proveedor, abrir su ficha y su "Cuenta corriente" | Bloque de saldo en cero y enlace a su cuenta |
| 12 | Registrar un saldo inicial de `80000.00` con sentido "Le debemos" | El saldo dice "Le debemos $ 80.000,00" |
| 13 | Registrar uno inverso de `5000.00` con el sentido "Saldo a favor nuestro" | Dos líneas; el saldo dice "Le debemos $ 75.000,00". (Observación: en el formulario el rótulo del sentido de proveedor que reduce es "Saldo a favor nuestro" y en la línea de saldo "Saldo a nuestro favor"; anotar si querés uniformarlos.) |
| 14 | Volver al cliente. Inactivarlo (pide escribir el nombre completo) y luego intentar reactivarlo (`estado = ACTIVO`) | El servidor lo rechaza con `CLIENTE_CON_OPERACIONES` y el mensaje se muestra; el cliente sigue `INACTIVO` |
| 15 | Contraste: dar de alta otro cliente sin movimientos, inactivarlo y reactivarlo | Se reactiva sin problema (no tiene operaciones) |
| 16 | Al cliente `INACTIVO` del paso 14 registrarle otro saldo inicial (`100.00`, "Nos debe") | Se acepta (un saldo inicial se admite en cualquier estado) |
| 17 | Verificar la consistencia en la base: `docker compose exec postgres psql -U distribuidora -d distribuidora -c "SELECT s.entidad_id, s.saldo, COALESCE(SUM(CASE m.sentido WHEN 'AUMENTA' THEN m.importe ELSE -m.importe END),0) AS suma FROM saldo_cuenta s LEFT JOIN cuenta_movimiento m USING (organizacion_id, cuenta_tipo, entidad_id) GROUP BY s.entidad_id, s.saldo;"` | En cada fila `saldo` es igual a `suma` |

### Flujo con `administracion` (rol Administración: ve la cuenta, no tiene `IMPORTAR_DATOS`)

Cerrar sesión y entrar como `administracion` / `organizacion-inicial`.

| # | Paso | Resultado esperado |
| --- | --- | --- |
| 1 | Abrir la ficha de `Kiosco La Esquina` | Ve el saldo y el enlace "Cuenta corriente" (tiene `GESTIONAR_CLIENTES`) |
| 2 | Entrar a "Cuenta corriente" | Ve el estado de cuenta completo y **no** aparece el botón "Registrar saldo inicial" |
| 3 | Ir directo a la URL `/admin/clientes/<id del cliente>/cuenta-corriente/saldo-inicial` | Avisa la falta de permiso y no muestra el formulario |
| 4 | Intentar el comando por API con el token de este usuario (login como `administracion` para obtenerlo): `curl -s -X POST http://localhost:8000/api/v1/cuentas-corrientes/saldos-iniciales -H "Authorization: Bearer <token>" -H "Operation-Id: 0193a000-0000-7000-8000-000000000802" -H "Content-Type: application/json" -d '{"cuenta_tipo":"CLIENTE","entidad_id":"<id del cliente>","importe":"100.00","sentido":"AUMENTA"}'` | `403` con código `PERMISO_REQUERIDO`; el saldo del cliente no cambia |
| 5 | Abrir la cuenta corriente de un proveedor | La ve (tiene `GESTIONAR_PROVEEDORES`), sin la acción de saldo inicial |

### Qué reportar

Para cada paso: ✅ si el resultado coincide, o el desvío observado (con captura si es posible). Si algo no coincide, no se marca 9.3 y se documenta acá antes de archivar.

### Resultado del recorrido (2026-09-30)

El usuario ejecutó el recorrido completo. Todo coincidió con lo esperado salvo el paso 14 del flujo `admin`: al reactivar el cliente inactivo con movimientos, el servidor respondía `CLIENTE_CON_OPERACIONES` pero el mensaje no se mostraba en pantalla.

- **Causa raíz:** `ClienteFormScreen.tsx` mapea el código a `estado` con `setError('estado', ...)` (`features/clientes/mapaErrorACampo.ts`), pero el `<Campo id="estado">` no recibía `error={errors.estado?.message}`. Aplicaba igual a `TRANSICION_ESTADO_INVALIDA`, `ESTADO_INVALIDO` y `CONSUMIDOR_FINAL_NO_INACTIVABLE`.
- **Corrección:** se pasó `error={errors.estado?.message}` al `Campo` de estado.
- **Pruebas:** dos casos nuevos en `frontend/tests/unit/areas/admin/clientes/ClienteFormScreen.test.tsx` (`CLIENTE_CON_OPERACIONES` y `TRANSICION_ESTADO_INVALIDA`): el mensaje se muestra junto al campo y no hay navegación. Frontend: 413 pruebas en verde, typecheck y lint sin errores.
