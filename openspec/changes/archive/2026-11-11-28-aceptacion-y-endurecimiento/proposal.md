# Change 28-aceptacion-y-endurecimiento

## Qué resuelve este change

Cierra la etapa 1: una suite Playwright recorre la demostración de `00` §9 de punta a punta; una tarea diaria compara saldos con sus libros y avisa al administrador; Caddy envía encabezados de seguridad y CSP; los permisos de la base quedan revisados y fijados por prueba; `intento_login` se limpia a las 24 horas con un rol propio.

## Why

`04` §12 (fila 28; dependencias 26 y 27b archivadas). Hoy `frontend/tests/e2e/` está vacío y Playwright no está instalado; la verificación de consistencia existe solo como consulta (ADR-015, ADR-039); el Caddyfile envía solo HSTS (ADR-071 punto 3); la limpieza de `intento_login` no existe (ADR-018, ADR-057 punto 9) y `app_runtime` no tiene `DELETE`. Además, la CI no corre `tests/concurrency` (`02` §15 lo exige) ni Playwright en la rama principal.

## What Changes

- **Tareas periódicas (D2–D7):** servicio nuevo `tareas` (imagen del backend, red `datos`, sin puertos) que una vez por día verifica la consistencia (`saldo_cuenta`, `stock_saldo`, `stock_total`, promedio vigente) por organización, sin corregir nada, y borra los `intento_login` de más de 24 horas. Usa un **rol nuevo `app_mantenimiento`** con permisos mínimos.
- **Aviso al administrador (D5, D17):** el resultado queda en una tabla nueva; si hay diferencias, `/admin` muestra un aviso con su "(?)" a quien tenga el permiso nuevo de solo lectura `VER_CONSISTENCIA` (`Administrador` y `Administración`), el log registra un error crítico y la salud del servicio cae (aviso externo opcional, como en el 27b).
- **Encabezados de seguridad y CSP (D8, D9):** en Caddy, compartidos por producción y el perfil `lan`.
- **Revisión de permisos de base (D10):** una matriz explícita de privilegios por rol y tabla, verificada contra la base migrada.
- **Cobertura (D11, D12):** el ratchet de INV-21 exige que cada ruta declarada apunte a pruebas que existen y citan INV-21 (hoy 174 de 174 rutas declaradas); un ratchet de invariantes de `01` §20 para la etapa 1; `tests/concurrency` entra en la CI.
- **Aceptación (D13–D16):** Playwright contra el compose de producción en un proyecto aparte, con la siembra del escenario de aceptación (`02` §16.1) y los mismos nombres de usuario de desarrollo; los criterios 1 a 11 automatizados, el 12 mapeado a las pruebas del 27b; job en la rama principal.
- **Deuda del 14 (D1):** el motivo llega a la auditoría de `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` (AUD-02).

## Capabilities

### New Capabilities

- `sistema/verificacion-de-consistencia`: tarea diaria, resultado guardado, aviso en `/admin`, sin corrección automática.
- `sistema/permisos-de-base-de-datos`: matriz de privilegios por rol y tabla, atributos de los roles.
- `sistema/aceptacion-etapa-1`: suite Playwright de los 12 criterios y su entorno.

### Modified Capabilities

- `sistema/despliegue`: servicio `tareas`, rol `app_mantenimiento`, encabezados de seguridad y CSP.
- `sistema/integracion-continua`: concurrencia en cada push, Playwright en la principal, ratchet de invariantes.
- `organizacion/aislamiento-multiorganizacion`: la cobertura declarada apunta a pruebas reales.
- `identidad/autenticacion-y-sesion`: retención de 24 horas de `intento_login`.
- `auditoria/registro-de-auditoria`: motivo en las anulaciones de compra y de pago.

## Impact

- Reglas e invariantes: **INV-21** (todas las rutas, ratchet reforzado), **INV-12, INV-13** (verificación diaria), **INV-05** (matriz; `app_runtime` sigue sin `DELETE` en libros; el `DELETE` sobre `intento_login` es solo de `app_mantenimiento`), **INV-02** (la tarea filtra por organización), cobertura de todo `01` §20 salvo INV-09 e INV-20 (facturación, `04` §13). AUD-02, SEG-07, ADR-015, ADR-018, ADR-020, ADR-039, ADR-057, ADR-071.
- Código: `backend/app/tareas/`, dos migraciones (tabla y rol; permiso `VER_CONSISTENCIA`), `infra/` (rol, Caddy, compose, plantilla), `ci.yml`, `frontend/tests/e2e/`, `app/seed.py`, el inicio de `/admin`, `ayuda/textos.ts`, `docs/runbook/`.
- Endpoint nuevo de lectura (con su prueba de aislamiento). Sin fixtures compartidos (no toca cálculos). ADR-073 (*Propuesto*).

## No incluye

- Consulta de auditoría con motivo y el mecanismo común de los puertos de registro de `catalogo` (deuda del 14, partes 2b y 3): se proponen para la etapa 2 (D1).
- WebKit/iPhone en Playwright, Row Level Security (etapa 4), corrección automática de diferencias, contratar VPS o dominio (Q1 sigue abierta).
