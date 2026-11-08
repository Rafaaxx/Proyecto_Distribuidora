# Change 27a-despliegue-basico

## Qué resuelve este change

El sistema se puede levantar en un equipo con Docker Compose de producción (hoy una PC de la oficina con Windows y Docker Desktop; más adelante un VPS con dominio, cambiando solo el archivo de entorno) (Caddy con HTTPS, backend sin recarga, PostgreSQL sin puerto expuesto), con backups diarios verificados y un runbook de primera puesta en marcha. Deja el entorno de prueba con conexión que pide el cierre del hito 5.

## Why

`04` §9 y §10 (fila 27a). Hoy solo existe el entorno de desarrollo: imágenes con recarga, Postgres y backend con puertos publicados y un Caddy con `tls internal` (perfil `lan`, ADR-062); `infra/backup/` está vacío. Adelantar el despliegue hace aparecer los errores de configuración antes de que haya datos reales y ejercita los backups antes de la aceptación (`00` §9 criterio 12).

## What Changes

- **Compose de producción** separado del de desarrollo (D3): `caddy`, `backend`, `postgres`, `migraciones` (de una sola vez) y `backup`; dos redes internas; solo Caddy publica 80/443.
- **Caddy de producción** (D1, D2, D4): HTTPS para `{$DOMINIO}` con el emisor del certificado elegido por `CADDY_TLS` (`internal`: autoridad propia de Caddy para la PC de la oficina, con el certificado raíz instalado en cada teléfono; un correo: Let's Encrypt automático con dominio real), redirección a HTTPS, HSTS, la compilación del frontend dentro de la imagen de Caddy, `/api/*` al backend, mismo origen (`02` §11, §18).
- **Imagen de producción del backend** (D5, D6): sin dependencias de desarrollo, usuario no root, varios workers de uvicorn, `--proxy-headers` con la red de Caddy como única de confianza (nota de despliegue de ADR-018); validación de arranque en `ENVIRONMENT=production`.
- **Migraciones antes del backend** (D7): servicio de una sola vez con `app_migrations`; el backend no recibe `DATABASE_URL_MIGRATIONS` (ADR-020).
- **Secretos** (D8): archivo de entorno fuera del repositorio con plantilla versionada sin valores (`02` §16.2); ningún valor por defecto.
- **Backups diarios** (D10 a D13): `pg_dump` en formato personalizado con un rol de solo lectura, escritura atómica, verificación de integridad, retención mínima y salud del servicio según la antigüedad del último backup.
- **Primera puesta en marcha** (D9): `python -m app.seed` existente, con la contraseña pedida sin dejarla en el historial.
- **Salud, reinicio y registros** (D14), **actualización** (D15), **runbook** (D16) con dos escenarios: PC de la oficina con Windows y Docker Desktop, y VPS Linux con dominio.
- **ADR-071** (*Propuesto*) y `propuesta-docs.md` (`02` §16, `04` §10).

## Decisiones

`design.md` D0 a D17, **aprobadas el 2026-11-07** (tarea 0.1): todas en A; **D1** con una A híbrida (PC de la oficina ahora, VPS después, mismo compose; solo cambia el archivo de entorno). Q1 (proveedor y dominio) abierta, no bloquea. **CRÍTICA: D1**. **ALTAS: D2, D5, D7, D8, D10, D11, D12.** Sin textos de interfaz nuevos.

## No incluye

- Retención completa (14 diarios y 8 semanales), copia fuera del servidor, restauración probada en entorno separado y runbook de restauración: **27b**.
- CSP y el resto de los encabezados de seguridad, revisión de permisos de base, verificación diaria de consistencia, limpieza de `intento_login`: **28**.
- Contratar el servidor o el dominio, abrir puertos en el router de la oficina o configurar DNS dinámico (se documenta como limitación), endurecer SSH, monitoreo externo, imágenes en un registro, CI de despliegue.
- Datos de demostración: el entorno arranca con la siembra (D9).
- Usar el entorno con datos reales (`04` §9).

## Reglas e invariantes

- **INV-05 / ADR-020:** la aplicación sigue con `app_runtime` (sin `UPDATE`/`DELETE` en tablas de libro); las migraciones con `app_migrations`; el backup con un rol de solo lectura (D11). Prueba que lee el compose y verifica qué variables recibe cada servicio.
- **SEG / `02` §18:** HTTPS obligatorio y HSTS, mismo origen, base sin puerto expuesto, IP real del cliente para el límite del login (ADR-018 punto 5, ADR-057).
- **`02` §14:** migraciones antes de la nueva versión del backend.
- **`00` §9 criterio 12:** queda preparado (backups verificables); se cumple en el 27b.
- Sin cálculo, sin migración de Alembic, sin fixtures compartidos ni cambios de API.

## Capabilities

### New Capabilities

- `sistema/despliegue`: servicios de producción, HTTPS, secretos, migraciones al desplegar, primera puesta en marcha y actualización.
- `sistema/respaldos`: backup diario, integridad, retención mínima y salud del backup.

### Modified Capabilities

Ninguna.

## Impact

Nuevos: `docker-compose.prod.yml`, `infra/caddy/` (Caddyfile con emisor por `CADDY_TLS`, y Dockerfile), `infra/backup/`, `infra/postgres/20-init-backup-role.sh`, `infra/produccion.env.example`, `backend/Dockerfile.produccion`, `docs/runbook/puesta-en-marcha.md`, `backend/tests/infra/`. Cambia `core/config.py`. Desarrollo y perfil `lan` sin cambios.
