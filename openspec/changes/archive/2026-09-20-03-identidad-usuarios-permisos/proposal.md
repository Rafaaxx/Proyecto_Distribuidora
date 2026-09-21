## Qué resuelve este change

Crea la identidad del sistema: usuarios, roles y el catálogo de permisos de `01` §19; login con access token en memoria y refresh rotativo en cookie (ADR-017); dispositivos y PIN de autorización (ADR-011); la dependencia de permisos que todo handler posterior usa; y `auditoria` como libro de solo inserción.

## Why

Todo lo que viene después depende de esto. `02` §8 exige que `organizacion_id` salga del token, y hasta hoy no hay token: el change 02 no pudo exponer ninguna ruta de negocio y dejó INV-21 cerrado solo a nivel de datos (`04` §5, nota al pie). SEG-06 exige que el servidor valide permisos en cada comando, así que la dependencia de permisos existe antes del bus (change 04). AUD-01 manda auditar el inicio de sesión y los cambios de usuarios, roles, permisos y dispositivos: los primeros eventos auditables son los de este change, así que `auditoria` nace acá y con ella INV-05 (`03` §2.5, §15).

## What Changes

- **Tablas** de `03` §4: `usuario` (Argon2id, `tope_descuento_override`, PIN de autorización), `rol`, `permiso` (catálogo global, sin organización), `rol_permiso`, `dispositivo`, `sesion_refresh`; más `auditoria` de `03` §13.
- **Migración de catálogo** con los 39 permisos de `01` §19 y las cinco plantillas de rol (ADM, GES, SUP, VEN, CON) con su composición y topes (`03` §4).
- **Autenticación** (`02` §12.1, ADR-017): `POST /auth/login`, `/auth/refresh`, `/auth/logout`. Access JWT de 15 min con usuario, organización y dispositivo; refresh opaco rotativo en cookie `HttpOnly` `Secure` `SameSite=Strict` limitada a `/api/v1/auth`, 30 días deslizantes; reusar un refresh rotado revoca la familia del dispositivo. Los permisos **no** viajan en el token.
- **Dependencia de autenticación y permisos**: extrae organización, usuario y dispositivo del token (nunca del cuerpo), exige un permiso por ruta y responde `PERMISO_REQUERIDO` en RFC 9457 (`02` §11) o 404 ante un recurso ajeno (SEG-07).
- **Dispositivos** (SEG-02): registro en el primer login con prefijo asignado por el servidor (`02` §7.7); revocación con `GESTIONAR_DISPOSITIVOS`, que invalida sus refresh.
- **PIN de autorización de supervisor** (SEG-03, SEG-05, `02` §12.4): derivación PBKDF2 con sal e iteraciones, mínimo 6 dígitos, rotable.
- **Rate limit de login** por usuario y por IP (`02` §18) — ver B1.
- **Dos roles de base** (`02` §18, INV-05): uno dueño del esquema para migraciones, uno de aplicación sin `UPDATE`/`DELETE` sobre `auditoria`.
- **Primeros endpoints de negocio con cobertura de aislamiento**, que cierran INV-21 y estrenan el ratchet del change 02.
- **Pantallas** de login y de dispositivos en `/admin`.

## Bloqueantes (decisiones que `docs/` no resuelve)

- **B1 — Rate limit de login.** `02` §18 lo exige pero no fija umbral, ventana, duración del bloqueo ni dónde se cuentan los intentos; producción corre varios workers (`02` §16.2) y el stack no tiene almacén compartido. **Requiere ADR antes de implementar** (`04` §2). Ver `design.md` D1.
- **B2 — Quién deriva el PIN de autorización.** `02` §12.4 fija PBKDF2 con sal e "iteraciones altas", pero no si el PIN en claro llega al servidor. Es una propiedad de seguridad, no un detalle de implementación: **requiere confirmación humana** como extensión de ADR-011. Ver `design.md` D2.

## No incluye

- Bus de comandos, `operation_id`, huella e idempotencia: change 04. Las escrituras de este change van por servicio directo, permitido hasta el 04 (`04` §5).
- `GET /sync/bootstrap` y el envío de credenciales de supervisor al dispositivo (SYN-11): change 21.
- PIN de **desbloqueo** local y su límite de intentos (SEG-03, SEG-04): viven en el dispositivo, changes 21/22a. Acá va solo el PIN de **autorización**.
- Cuarentena de comandos de dispositivos revocados (SYN-06) y `PERMISO_REVOCADO` (SYN-10): changes 04 y 25.
- Permisos por usuario fuera del rol: etapa 4 (`03` §4).
- Fixtures compartidos de cálculo: este change no toca precios, descuentos ni costos.

## Invariantes

- **INV-05**: `auditoria` de solo inserción más el rol de aplicación sin `UPDATE`/`DELETE`, verificado por una prueba que intenta ambas y espera el rechazo de la base (`03` §15).
- **INV-21**: lo cierra por completo. La organización sale del token y cada endpoint nuevo queda declarado en el ratchet del change 02 con su prueba de acceso ajeno → 404.
- **INV-02**: las tablas nuevas siguen el patrón del change 02; `permiso` es catálogo global y se declara exenta explícitamente.

## Capabilities

### New Capabilities
- `identidad/usuarios-y-roles`: usuario, rol, catálogo de permisos, tope de descuento (`01` §19, `03` §4).
- `identidad/autenticacion-y-sesion`: login, access token, refresh rotativo, revocación de familia, logout, rate limit (ADR-017, `02` §12.1, §18).
- `identidad/dispositivos`: registro, prefijo de numeración, revocación (SEG-02, `02` §7.7, §12.2).
- `identidad/pin-de-autorizacion`: PIN de supervisor, derivación, rotación (SEG-03, SEG-05, `02` §12.4).
- `identidad/autorizacion-por-permiso`: la dependencia que exige permiso y extrae la organización del token (SEG-06, SEG-07).
- `auditoria/registro-de-auditoria`: qué se audita, con qué campos, y que no se modifica ni borra (AUD-01..AUD-03, INV-05).

### Modified Capabilities
- `organizacion/aislamiento-multiorganizacion`: el requisito de cobertura de rutas pasa de vacuidad a rutas reales; se agrega que la organización se obtiene del token y nunca de la petición, y se declara la exención del catálogo global `permiso` en la verificación estructural de INV-02.

## Impact

- Código nuevo: `backend/app/modules/identidad/` (api, schemas, domain, models, repository, service), `backend/app/core/seguridad.py`, dos revisiones de Alembic, pantallas de login y dispositivos en el frontend.
- Infraestructura: `docker-compose.yml`, `.env` y el arnés de Testcontainers provisionan dos roles de base — **gobernanza ALTA**, toca configuración de despliegue.
- Dependencias nuevas: `argon2-cffi` y `pyjwt` en el backend.
- Contrato: primer esquema de autenticación en el OpenAPI; los tipos del frontend se regeneran (`02` §11).
