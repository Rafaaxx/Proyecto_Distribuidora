# Propuesta de cambios a `docs/` — change 27a `despliegue-basico`

> **Borrador con las opciones A de `design.md`, aprobadas el 2026-11-07 (0.1; D1 híbrida: PC de la oficina ahora, VPS después, mismo compose).** Se completa con las precisiones del apply (tarea 4.3). Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia. Las decisiones van en `docs/adr/ADR-071-despliegue-basico-y-backups-minimos.md`.
>
> Orden: `02` §16.2, §18; `04` §10.

---

## `02-arquitectura.md`

### §16.2 Producción (etapa 1) — D3, D7, D10, D13, D15

**Actual**

> | `backup` | `pg_dump` diario comprimido, retención de 14 diarios y 8 semanales, copia a almacenamiento externo |
>
> - Los secretos se cargan desde un archivo de entorno fuera del repositorio.
> - El despliegue ejecuta las migraciones antes de iniciar la nueva versión del backend.

**Propuesto**

> | `migraciones` | De una sola vez: `alembic upgrade head` con `app_migrations` antes de iniciar el backend |
> | `backup` | `pg_dump` diario comprimido con un rol de solo lectura, verificado al generarse; retención de 14 diarios y 8 semanales y copia a almacenamiento externo (27b; el 27a conserva los últimos 7) |
>
> - Archivo `docker-compose.prod.yml`, independiente del de desarrollo; redes `frente` (Caddy y backend) y `datos` (interna: backend, Postgres, migraciones y backup); solo Caddy publica puertos (ADR-071).
> - El mismo compose corre en una PC de la oficina o en un servidor con dominio: `DOMINIO` y `CADDY_TLS` (autoridad propia de Caddy o Let's Encrypt) se fijan en el archivo de entorno (ADR-071).
> - Los secretos se cargan desde un archivo de entorno fuera del repositorio (`infra/produccion.env.example` es la plantilla, sin valores).
> - El despliegue ejecuta las migraciones antes de iniciar la nueva versión del backend (servicio `migraciones`); el backend no recibe la credencial de migraciones.
> - Los backups se escriben en un directorio del equipo, fuera de los volúmenes de Docker.
> - Primera puesta en marcha y actualización: `docs/runbook/puesta-en-marcha.md`.

### §18 Seguridad — D2, D5, D11

**Actual**

> - El usuario de base de datos de la aplicación no es superusuario ni dueño del esquema; las migraciones usan un usuario distinto.

**Propuesto**

> - El usuario de base de datos de la aplicación no es superusuario ni dueño del esquema; las migraciones usan un usuario distinto, y el backup un tercero de solo lectura (`pg_read_all_data`) (ADR-020, ADR-071).
> - HSTS de un año sin `includeSubDomains` ni `preload` desde el 27a (también con la autoridad propia de Caddy); el backend confía en `X-Forwarded-For` solo desde la red del proxy (ADR-018 punto 5, ADR-071).

## `04-roadmap-changes.md`

### §10 — fila 27a

Agregar debajo de la tabla el párrafo de cierre del change (entrega, decisiones, deudas al 27b y al 28, prueba manual), como en los changes anteriores. Deudas previstas al **27b**: retención 14 + 8, copia externa, restauración probada y `docs/runbook/restauracion.md`; Q1 (servidor y dominio reales) si no se resolvió; acceso desde la calle mientras el entorno siga en la PC de la oficina (*port forwarding*, DNS dinámico o paso al VPS).

---

## Precisiones del apply (tarea 4.3)

Se suman a la propuesta anterior; todo se aplica al archivar, con el visto bueno del usuario.

### `02-arquitectura.md` §15 (CI) — D17

Agregar a los pasos de CI que el trabajo de integracion con Testcontainers tambien corre `backend/tests/infra` (compose de produccion, Caddyfile en los dos modos de `CADDY_TLS`, imagen de backup, roles de base).

### `02-arquitectura.md` §16.2 — precisiones

- Agregar al compose de produccion: imagenes propias `distribuidora-backend`, `distribuidora-migraciones`, `distribuidora-caddy` y `distribuidora-backup`, todas etiquetadas con `APP_VERSION`; `backend` y `migraciones` comparten `Dockerfile.produccion` pero llevan nombres de imagen distintos.
- La configuracion del backend se valida al arrancar en produccion (`JWT_SECRET` de al menos 32 caracteres, `APP_VERSION` con forma `X.Y.Z`): el contenedor sale con codigo 1 y nombra la variable, nunca su valor (`python -m app.core.verificar_config`).
- Backups: archivos `distribuidora-AAAAMMDD-HHMMSS.dump`, verificados con `pg_restore --list` (las cuatro tablas de libro); un archivo ilegible pasa a `.dump.fallido`; la salud del servicio `backup` falla si el ultimo backup valido tiene mas de 26 horas.

### `04-roadmap-changes.md` §10 — precisiones al parrafo de cierre del 27a

- Entrega: `docs/runbook/puesta-en-marcha.md` con dos escenarios (PC de la oficina con Windows + Docker Desktop y VPS con dominio).
- Deudas al **27b**: ademas de lo previsto, `docs/runbook/restauracion.md` y la restauracion de un backup para pasar los datos de la PC a un VPS.
- Prueba manual del 27a: ensayo con `DOMINIO=localhost` y puesta en marcha en la PC del usuario con un telefono en el Wi-Fi de la oficina (certificado raiz de Caddy instalado); resultados en `design.md`.

### `README.md`

Ya enlaza al runbook (hecho en la tarea 4.1; no es parte de `docs/`).

---

## Ajustes de la prueba manual (2026-11-08) — D18, D19, D20

### `02-arquitectura.md` §18 Seguridad

Agregar:

> - El frontend recorta los espacios de los extremos de organización y usuario en el login (no de la contraseña); el servidor sigue comparando tal cual (ADR-057, enmienda 2026-11-08).
> - Limitación conocida del entorno en Docker Desktop para Windows: todos los clientes llegan con la misma IP al backend, así que el límite de 20 fallos de login por IP cuenta a toda la oficina; con servidor Linux se ve la IP real de cada cliente (ADR-071).

### `02-arquitectura.md` §13.5 (actualización de versión)

Agregar:

> - Si falla la carga de una pantalla diferida (por ejemplo tras un despliegue nuevo, cuando desaparecieron los archivos con hash viejo), el área muestra «Hay una versión nueva del sistema» con un botón «Recargar» en lugar de la pantalla de error por defecto del enrutador (change 27a, D19).
