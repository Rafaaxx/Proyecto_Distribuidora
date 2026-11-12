# Verificación — 07-clientes

> Documento de verificación del change (`tasks.md` grupos 6 y 7). Las
> secciones 6.1-6.6 están completas y ejecutadas por el agente. La sección
> 7.1 es el recorrido manual en el navegador: **queda pendiente, la ejecuta
> el usuario** (no es delegable — requiere ojos humanos sobre la interfaz
> real). La 7.2 registra los ADR y la actualización de `docs/03` §10. La 7.3
> repasa la definición de terminado de `docs/04-roadmap-changes.md` §2.1.

## 6. Pruebas backend — resumen de evidencia

Ver el detalle completo en `tasks.md` 6.1-6.6. Resumen:

| Tarea | Resultado |
| --- | --- |
| 6.1 (unitarias `domain/`) | Ya cubierto por `tests/unit/test_clientes_domain.py` (43 pruebas). Sin brechas. |
| 6.2 (integración de los 4 comandos) | Brecha real: faltaba `COMANDO_INCONSISTENTE` para `CLIENTE_CREAR` y `CLIENTE_CREDITO_MODIFICAR`. Se agregaron 2 pruebas en `tests/integration/test_clientes_api.py`. |
| 6.3 (aislamiento INV-21) | Ya cubierto por `tests/integration/test_inv21_aislamiento_endpoints_clientes.py` (8 pruebas). Sin brechas. |
| 6.4 (concurrencia) | Brecha real: no existía `tests/concurrency/test_clientes_concurrencia.py`. Se creó con 2 pruebas (documento duplicado, código duplicado), ambas con commits reales de dos hilos. |
| 6.5 (invariantes) | INV-05, INV-03 e INV-02 ya cubiertos (nombres de archivo distintos a los que citaba la tarea; ver el detalle en `tasks.md`). Fixtures compartidos sin cambios: `pytest tests/fixtures_compartidos/` → 56 passed. |
| 6.6 (suite completa) | `pytest -q --ignore=tests/concurrency` → **1323 passed**; `pytest tests/concurrency` → **11 passed** (corrido aparte, `pytest_plugins` de su `conftest.py`); `ruff check .` limpio; `ruff format --check .` → 232 archivos; `mypy app` limpio (91 archivos); `lint-imports` → 12/12 contratos. |

## 7.1 — Recorrido manual en el navegador (PENDIENTE — lo ejecuta el usuario)

### Preparación del entorno

1. Verificar que existe un `.env` en la raíz del repo con `APP_MIGRATIONS_DB_PASSWORD`, `APP_RUNTIME_DB_PASSWORD`, `JWT_SECRET` y `ADMIN_PASSWORD` definidos (`CLAUDE.md` §4: ningún secreto por defecto). Si no existe, crearlo con valores de desarrollo antes de continuar.
2. Levantar todo el stack:
   ```bash
   docker compose up -d
   ```
3. Aplicar las migraciones (incluye la tabla `cliente` de este change):
   ```bash
   docker compose exec backend alembic upgrade head
   ```
4. Sembrar la organización inicial, sus catálogos, los cinco roles y el usuario `admin` (si la base ya estaba sembrada, este paso no hace nada — es idempotente):
   ```bash
   docker compose exec -e ADMIN_PASSWORD=<la contraseña que pusiste en .env> backend python -m app.seed
   ```
   Organización: slug `organizacion-inicial`. Usuario administrador: `admin`, con la contraseña de `ADMIN_PASSWORD`.
5. Abrir el frontend (según `docker-compose.yml`, normalmente `http://localhost:5173` en desarrollo, o el puerto que exponga el servicio `frontend`; revisar `docker compose ps` si no es ese).

### Crear un segundo usuario para el rol "Supervisor comercial" (GESTIONAR_CLIENTES sin GESTIONAR_CREDITO)

No existe todavía una pantalla de administración de usuarios (esa gestión es el change D9.5, no `07-clientes`), así que este usuario se crea por API. El rol "Supervisor comercial" ya existe por la siembra (`crear_plantillas_de_rol_iniciales`), con `GESTIONAR_CLIENTES` y **sin** `GESTIONAR_CREDITO` — exactamente lo que pide el segundo recorrido de la 7.1.

1. Buscar el `id` del rol "Supervisor comercial" de la organización inicial, conectándose a la base:
   ```bash
   docker compose exec postgres psql -U distribuidora -d distribuidora -c \
     "SELECT id, nombre FROM rol WHERE nombre = 'Supervisor comercial';"
   ```
2. Loguearse como `admin` para obtener un access token (`LoginRequest` exige `organizacion_slug`, `usuario`, `contrasena`, `dispositivo_id` y `nombre_dispositivo` — ver `backend/app/api_v1/auth.py`):
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{
       "organizacion_slug": "organizacion-inicial",
       "usuario": "admin",
       "contrasena": "<ADMIN_PASSWORD>",
       "dispositivo_id": "00000000-0000-0000-0000-000000000001",
       "nombre_dispositivo": "Verificación 07-clientes"
     }'
   ```
   Copiar el `access_token` de la respuesta.
3. Crear el usuario `supervisor` con ese rol:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/identidad/usuarios \
     -H "Authorization: Bearer <access_token>" \
     -H "Operation-Id: 0193a000-0000-7000-8000-000000000701" \
     -H "Content-Type: application/json" \
     -d '{
       "usuario": "supervisor",
       "nombre": "Supervisor Comercial de Prueba",
       "email": null,
       "password": "una-contrasena-larga-123",
       "rol_id": "<id del paso 1>"
     }'
   ```

### Flujo con `admin` (tiene `GESTIONAR_CLIENTES` y `GESTIONAR_CREDITO`, y es el único con `ADMIN_CONFIGURACION`)

Loguearse en el frontend como `admin` / `organizacion-inicial` y recorrer:

| # | Paso | Resultado esperado |
| --- | --- | --- |
| 1 | Entrar a la sección "Clientes" del menú de administración | La sección aparece (D3/ADR-028: la decide el permiso efectivo de `/yo`, no un 403) |
| 2 | Alta de cliente: nombre `Kiosco La Esquina`, dirección, contacto, documento `DNI` `30111222` | Se crea, aparece en el listado `ACTIVO`, sin selector de lista de precios ni campos de crédito en el formulario (D2, D3) |
| 3 | Editar la ficha (nombre, dirección, contacto) sin tocar el estado | Se guarda; el listado refleja el cambio |
| 4 | Abrir la ficha del cliente y usar el botón de crédito | Se ve el botón (tiene `GESTIONAR_CREDITO`); fijar límite `150000.00`, política `AUTORIZAR`, guardar | La ficha muestra `150000.00` con dos decimales (`lib/money.ts`) |
| 5 | Suspender el cliente (`estado = SUSPENDIDO`) desde la ficha | No pide confirmación tipeada (solo `INACTIVO` la exige); el listado lo muestra `SUSPENDIDO` |
| 6 | Reactivarlo (`estado = ACTIVO`) | Vuelve a `ACTIVO` sin fricción (CLI-06: sin operaciones, la transición es libre en este change) |
| 7 | Inactivar el cliente | El diálogo de confirmación tipeada pide el **nombre completo** (`Kiosco La Esquina`), muestra código/documento y explica la consecuencia; con el botón de guardar deshabilitado hasta escribirlo correcto (D7). Al confirmarlo, el cliente queda `INACTIVO` |
| 8 | Intentar reactivarlo de nuevo | Se acepta (sin operaciones registradas, CLI-06) |
| 9 | Filtrar el listado por texto (`Esquina`) y por estado (`ACTIVO`) | Cada filtro trae solo lo que corresponde |
| 10 | Habilitar el consumidor final (pantalla de configuración, requiere `ADMIN_CONFIGURACION`) con nombre `Consumidor final` | Se crea el cliente con límite `0.00`, marcado como consumidor final; la pantalla lo confirma |
| 11 | Intentar habilitarlo de nuevo | Se rechaza (`CONSUMIDOR_FINAL_YA_HABILITADO`) |

### Flujo con `supervisor` (`GESTIONAR_CLIENTES`, sin `GESTIONAR_CREDITO`, sin `ADMIN_CONFIGURACION`)

Cerrar sesión y loguearse como `supervisor` / `organizacion-inicial`:

| # | Paso | Resultado esperado |
| --- | --- | --- |
| 1 | Entrar a "Clientes" | La sección aparece (tiene `GESTIONAR_CLIENTES`) |
| 2 | Abrir la ficha de `Kiosco La Esquina` | Ve el límite de crédito y la política **en solo lectura**, sin botón de "editar crédito" (D3) |
| 3 | Buscar la ruta de la pantalla de crédito directamente por URL | La pantalla no la ofrece (sin el botón) y, si de todos modos se intenta escribir el comando de crédito, la API responde 403 `PERMISO_REQUERIDO` |
| 4 | Buscar en el menú la pantalla de "consumidor final" / configuración | No aparece (no tiene `ADMIN_CONFIGURACION`); si se llega por URL, la escritura responde 403 |
| 5 | Dar de alta un cliente nuevo y editar la ficha de uno existente | Funciona con normalidad (tiene `GESTIONAR_CLIENTES`) |

### Qué reportar

Para cada paso: ✅ si el resultado coincide, o el desvío observado (con captura si es posible). Si algo no coincide, no se marca 7.1 y se documenta acá antes de continuar con el archivado.

### Resultado de la primera pasada (2026-09-29)

El usuario ejecutó el recorrido descripto arriba. Resultado:

- **Flujo con `admin`** (pasos 1 a 11 de la tabla "Flujo con `admin`"): ✅ los once pasos coinciden con lo esperado.
- **Flujo con `supervisor`**, paso 5 (verificación por API de que la escritura de crédito y de consumidor final responden 403 sin el permiso, en vez del recorrido completo por pantalla): ✅ se confirmaron dos rechazos `403 PERMISO_REQUERIDO`, uno al intentar `CLIENTE_CREDITO_MODIFICAR` sin `GESTIONAR_CREDITO` y otro al intentar `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` sin `ADMIN_CONFIGURACION`.
  - Nota operativa: la creación del usuario `supervisor` del paso "Crear un segundo usuario..." se hizo en la práctica con un script PowerShell (`Invoke-RestMethod`) en vez del `curl` de este documento, porque la sesión de verificación corría en PowerShell. El resultado es equivalente; el `curl` de arriba queda como referencia portable, y se puede agregar la variante PowerShell si hace falta repetirlo seguido.
- Durante el recorrido con `supervisor` (paso 2, ficha en solo lectura) se encontraron **tres desvíos**, ya corregidos en el grupo 8 de `tasks.md` (ver ahí el detalle de implementación y de pruebas):
  1. **Bug vs. spec**: la ficha (`ClienteFormScreen.tsx`) no mostraba el crédito en solo lectura para quien tiene `GESTIONAR_CLIENTES` sin `GESTIONAR_CREDITO` (escenario "La ficha muestra el crédito en solo lectura" de `specs/clientes/administracion-de-clientes/spec.md`, `design.md` D3). Corregido: bloque "Crédito" de solo lectura en la ficha, visible para quien puede ver la ficha; el enlace de edición sigue exigiendo `GESTIONAR_CREDITO` (tarea 8.1).
  2. Después de guardar (alta, edición de ficha, edición de crédito) la pantalla no volvía a un lugar útil para seguir trabajando. Corregido en clientes y, por decisión del usuario, también en proveedores fuera del alcance original del 07 (tarea 8.2).
  3. En los listados, solo el nombre y el enlace "Editar" abrían la ficha; el resto de la fila no reaccionaba al clic. Corregido en `ClientesListScreen` y `ProveedoresListScreen` (tarea 8.3).
- **Segunda pasada (2026-09-29) ✅**: el usuario volvió a recorrer los tres puntos corregidos en el navegador (ficha en solo lectura sin `GESTIONAR_CREDITO`, navegación después de guardar en clientes y proveedores, y fila clicable en ambos listados) y los confirmó. 7.1 marcada.

## 7.2 — ADR y `docs/03-modelo-de-datos.md` §10

- `docs/adr/ADR-029-consumidor-final-habilitacion-y-ciclo-de-vida.md` (D4) y `docs/adr/ADR-030-cliente-inactivo-reactivable-solo-sin-operaciones.md` (D7) ya existían en el árbol de trabajo antes de esta sesión; se leyeron y no se modificaron.
- Se crearon dos ADR nuevos para las decisiones aprobadas que todavía no tenían uno:
  - `docs/adr/ADR-031-separacion-de-permisos-clientes-y-credito.md` (D3: `GESTIONAR_CLIENTES` para la ficha, `GESTIONAR_CREDITO` para el crédito, comandos separados).
  - `docs/adr/ADR-032-tolerancia-offline-cliente-numeric-14-2.md` (D6: `tolerancia_offline_valor` del cliente en `numeric(14,2)`, igual que la organización).
- D1 (identidad del cliente), D2 (`lista_precio_id` sin FK) y D5 (`condicion_iva` no se crea) no tienen ADR propio: son la aplicación directa de precedentes ya registrados (ADR-025 para D2; D1 sigue el mismo criterio que el ADR de unicidad del proveedor del change 06 sin agregar una decisión nueva; D5 es "no hacer nada todavía", documentado alcanza). Están anotados en `design.md` con fecha de aprobación.
- `docs/03-modelo-de-datos.md` §10 (`cliente`) se actualizó: unicidad parcial de `codigo` y de `(documento_tipo, documento_numero)` (D1), la nota de que `lista_precio_id` no tiene FK hasta el change 13 (D2), la nota de que `condicion_iva` no existe todavía y la agrega el change de facturación (D5), y la referencia a ADR-029/030/031/032 en las columnas que corresponden.
- No se tocó `docs/referencia/` ni `openspec/changes/archive/`.

## 7.3 — Definición de terminado (`docs/04-roadmap-changes.md` §2.1)

| # | Criterio | Estado |
| --- | --- | --- |
| 1 | Las pruebas que exige `02` §15 para su alcance pasan en CI | Cumple: unit+integration+properties (1323) y concurrency (11) en verde, ver 6.6 |
| 2 | Cada escenario de sus specs tiene al menos una prueba que lo cubre | Cumple: las cuatro specs delta (`administracion-de-clientes`, `consumidor-final`, `datos-de-credito`, `fichas-de-cliente`) tienen sus escenarios cubiertos por los grupos 3, 4 y 6; las dos brechas reales encontradas en el grupo 6 (`COMANDO_INCONSISTENTE`, concurrencia) se cerraron con pruebas nuevas |
| 3 | Los invariantes que toca tienen prueba que los cita por ID | Cumple: INV-01 (concurrencia), INV-02/INV-21 (aislamiento), INV-03 (sin punto flotante), INV-05 (sin `DELETE`), INV-06/SYN-02 (idempotencia) — ver 6.2-6.5 |
| 4 | La migración de Alembic sube y baja limpia sobre una base con datos | Cumple: `test_clientes_migracion.py` corre contra una base migrada real (Testcontainers) y pasa; la migración es de solo agregado (una tabla nueva), sin dato preexistente que migrar |
| 5 | Se probó a mano el flujo principal en el navegador | ✅ Hecho por el usuario el 2026-09-29 (§7.1, dos pasadas) |
| 6 | Las specs delta se archivaron en `openspec/specs/` y `04-roadmap-changes.md` quedó actualizado | Se hace en `/opsx archive`, no en este documento; `docs/04-roadmap-changes.md` ya tiene la fila `07 clientes` con su dependencia (`04, 06b`) |
| 7 | Si se tomó una decisión nueva, quedó como ADR | Cumple: ADR-029, ADR-030 (ya existentes) y ADR-031, ADR-032 (nuevos en esta sesión) |

**Conclusión:** todos los criterios están satisfechos salvo el punto 5, que requiere la verificación manual del usuario (sección 7.1 de este documento). El change queda listo para `/opsx archive` en cuanto el usuario confirme el recorrido manual.
