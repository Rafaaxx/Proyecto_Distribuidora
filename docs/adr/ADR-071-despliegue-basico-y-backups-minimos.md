# ADR-071 — Despliegue básico de producción con Docker Compose y backups diarios mínimos

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-11-08 |
| Referenciado en | `openspec/changes/27a-despliegue-basico/design.md` D0 a D17 y `specs/sistema/despliegue`, `specs/sistema/respaldos`; `00-vision-y-alcance.md` §9 criterio 12; `01-dominio.md` INV-05; `02-arquitectura.md` §6.6, §8, §11, §14, §16.2, §17, §18; `04-roadmap-changes.md` §9, §10, §12; ADR-018, ADR-020, ADR-021, ADR-057, ADR-062 |

**Change 27a. Gobernanza: dominio ALTO (despliegue, secretos, backups). CRÍTICA: D1. ALTAS: D2, D5, D7, D8, D10, D11, D12. Decisiones aprobadas el 2026-11-07 (tarea 0.1): todas en A, con D1 híbrida. Pasa a *Vigente* al archivar.**

## Contexto

`04` §9 pide que al terminar el hito 5 el sistema quede desplegado en un entorno de prueba con conexión, y §10 define el 27a: compose de producción con Caddy, PostgreSQL y backend, backups diarios con retención mínima, HTTPS y runbook de primera puesta en marcha. `02` §16.2 fija los servicios y que los secretos viven fuera del repositorio y las migraciones corren antes del backend, pero no resuelve: dónde corre, cómo llega el frontend, cómo se confía en el proxy, cómo se migra al desplegar, con qué rol se hace el backup, cómo se verifica, qué es la retención mínima, cómo se actualiza ni dónde vive el runbook.

## Decisión propuesta (opciones A de `design.md`, aprobadas el 2026-11-07; D1 híbrida)

1. **Alcance (D0).** Un change en cuatro lotes.
2. **Entorno (D1, híbrida).** Un solo compose de producción para una PC de la oficina (Windows + Docker Desktop) ahora y un VPS Linux con dominio después, sin cambiar código: solo cambia el archivo de entorno. `DOMINIO` es un dominio, la IP fija de la PC en la red local o `localhost`; `CADDY_TLS` elige el emisor del certificado (`internal`: autoridad propia de Caddy, cuyo certificado raíz se instala en cada teléfono como en el perfil `lan` de ADR-062; un correo: Let's Encrypt automático). Mecanismo previsto: `tls {$CADDY_TLS}` en el Caddyfile, verificado con `caddy validate` en el apply (si no, fragmentos importados por variable). En la PC, los teléfonos solo llegan dentro de la red de la oficina (*port forwarding* y DNS dinámico quedan documentados como limitación, no implementados). Proveedor y dominio (Q1) abiertos, sin bloquear; ensayo local con `DOMINIO=localhost` y `CADDY_TLS=internal`.
3. **HTTPS (D2).** Certificado de Caddy según `CADDY_TLS`, redirección y HSTS (también con `internal`) de un año sin `includeSubDomains` ni `preload`; CSP y demás encabezados en el 28.
4. **Compose (D3).** `docker-compose.prod.yml` independiente; redes `frente` (subred fija) y `datos` (interna); solo Caddy publica puertos.
5. **Frontend (D4).** Imagen propia de Caddy con la compilación adentro, versión por `APP_VERSION`.
6. **Backend (D5).** `backend/Dockerfile.produccion`, usuario no root, uvicorn con varios workers y `--proxy-headers` confiando solo en la red `frente`.
7. **Arranque (D6).** En producción, `JWT_SECRET` de al menos 32 caracteres y `APP_VERSION` `X.Y.Z`, o no arranca.
8. **Migraciones (D7).** Servicio `migraciones` de una sola vez con `app_migrations`; el backend no recibe esa credencial.
9. **Secretos (D8).** Archivo de entorno fuera del repositorio: `/etc/distribuidora/produccion.env` (`600`) en el VPS, una carpeta de Windows con acceso solo para el usuario en la PC; plantilla versionada sin valores (`CADDY_TLS` en lugar de `ACME_EMAIL`); `ADMIN_PASSWORD` fuera del archivo.
10. **Puesta en marcha (D9).** Siembra existente (`organizacion-inicial`), sin datos de demostración.
11. **Backup (D10).** Servicio propio sobre `postgres:17`, `pg_dump -Fc` diario a `BACKUP_HORA` en `TZ`, escritura atómica, directorio del equipo fuera de los volúmenes (permisos `700`/`600` comprobados solo en Linux); a pedido con `ahora`.
12. **Rol de backup (D11).** Tercer rol `app_backup` con `pg_read_all_data` (amplía ADR-020: migraciones, runtime y backup).
13. **Verificación (D12).** `pg_restore --list` con las cuatro tablas de libro en cada backup; una restauración de humo en el ensayo; la restauración probada es del 27b.
14. **Retención (D13).** Los últimos 7 backups válidos; el 27b la lleva a 14 diarios y 8 semanales con copia externa.
15. **Operación (D14).** Reinicio automático, verificaciones de salud (la del backup, por antigüedad de 26 horas) y rotación de registros; sin límites de recursos.
16. **Actualización (D15).** En el equipo desde el repositorio (mismos pasos en la PC y en el VPS): backup, `checkout`, `build`, `run --rm migraciones` y, solo si salió bien, `up -d` (ver Precisión del paso 18).
17. **Runbook (D16).** `docs/runbook/puesta-en-marcha.md`, con la jerga explicada y dos escenarios: PC de la oficina (Windows + Docker Desktop, certificado raíz en Android e iPhone) y VPS Linux con dominio.
18. **Pruebas (D17).** `backend/tests/infra/` (compose, Caddyfile validado en los dos modos de `CADDY_TLS`, imagen de backup con Testcontainers, roles), ensayo local y puesta en marcha en la PC del usuario.

## Consecuencias

- El entorno de prueba queda listo para el 27b y para la aceptación; los backups viven en el mismo equipo hasta el 27b.
- Mientras corre en la PC de la oficina, los vendedores sincronizan solo en el Wi-Fi de la oficina (la venta en ruta sigue sin conexión) y cada teléfono confía en la autoridad de Caddy; pasar al VPS es cambiar `DOMINIO` y `CADDY_TLS`.
- ADR-020 pasa de dos a tres roles de base (el de backup, solo lectura).
- `02` §16.2 suma el servicio `migraciones`, las redes y la retención mínima del 27a; `02` §18 suma el rol de backup.

## Precisiones del apply

- **Precisión (ensayo, 2026-11-07, paso 18; D15).** Si `migraciones` falla durante `up -d`, Compose igualmente recrea `backend` y `caddy` y quedan en `Created`: el sistema queda caído (no sigue la versión vieja). El procedimiento de actualización (punto 16) pasa a: backup, `checkout`, `APP_VERSION`, `build`, `run --rm migraciones` (con el backend viejo aún en servicio) y solo si salió bien, `up -d`. Sin impacto de negocio; las migraciones siguen siendo compatibles hacia adelante (`02` §14).

(Completadas en la tarea 4.2; el resultado del ensayo manual de 5.2 se anota en `design.md`.)

- **Lote 1 (D5).** `uvicorn==0.53.0` acepta una red CIDR en `--forwarded-allow-ips` (probado: con `172.30.10.0/24`, una conexión de la red toma cliente y esquema de `X-Forwarded-*` y una de fuera no). La imagen construye, corre como usuario `app` (uid 10001), sin `tests/` ni `pytest`, con dos workers. El `CMD` usa forma de shell con `exec` para resolver `WEB_CONCURRENCY` y `FORWARDED_ALLOW_IPS` (por defecto `172.30.10.0/24`). Se agregó `backend/.dockerignore` (también aplica a la imagen de desarrollo, que monta el código por volumen: sin efecto).
- **Lote 1 (D5, revisión de workers).** Sin estado de negocio en memoria del proceso: lo que hay son registros de cableado que se llenan al importar los módulos (iguales en cada worker) y el contador de `core/ids.py` (aceptable, ya anotado).
- **Lote 1 (D6) — hallazgo, resuelto en el paso 0 del Lote 2 (ver abajo).** `app/main.py` (líneas finales) atrapa `ValidationError` al construir `app` y deja `app = None`. Con `ENVIRONMENT=production` y `APP_VERSION=dev`, el contenedor **arranca igual** (uvicorn levanta sin aplicación y los pedidos fallan), en lugar de no arrancar como pide la spec. `Settings` ya valida (probado); falta que `main.py` no silencie el error en producción.
- **Paso 0 (D6).** `main.py` atrapaba el `ValidationError` para poder importar el módulo sin variables de entorno (pruebas, generación del OpenAPI, import-linter). Ahora lo relanza cuando `ENVIRONMENT=production`, y el `CMD` de `Dockerfile.produccion` corre antes `python -m app.core.verificar_config` (sale con 1 nombrando la variable, nunca el valor) para que el contenedor caiga sin que uvicorn reintente la importación en bucle.
- **Lote 2 (D1).** `tls {$CADDY_TLS}` funciona en los dos modos (`caddy validate` y `caddy adapt`: `internal` da un emisor interno; un correo da emisores ACME con ese correo, Let's Encrypt y ZeroSSL de respaldo). No hizo falta el mecanismo de fragmentos.
- **Lote 2 (D3, D7).** `migraciones` y `backend` usan el mismo Dockerfile y contexto, con nombres de imagen distintos (con el mismo nombre, la construcción en paralelo falla). Redes: `frente` con subred fija `172.30.10.0/24` (igual a `FORWARDED_ALLOW_IPS` del backend, comprobado por una prueba) y `datos` interna.
- **Lote 2 (D4, D14).** La imagen de Caddy se construye con el repositorio como contexto y un `Dockerfile.dockerignore`. La salud de `caddy` consulta `127.0.0.1:2019` (el punto de administración escucha solo en IPv4).
- **Lote 2 (D8).** `.gitignore` suma `*.env` salvo `*.env.example`; `infra/produccion.env.example` no trae valores en los secretos y suma `POSTGRES_USER` y `POSTGRES_DB`.
- **Lote 3 (D11).** `pg_read_all_data` alcanza para un `pg_dump -Fc` completo, secuencias incluidas (`SEQUENCE SET` presente en el listado), probado contra Postgres 17 con el esquema migrado y datos. `app_backup` no puede `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE` ni `nextval`; `app_runtime` sigue sin `DELETE` ni `UPDATE` sobre `auditoria`. El rol lo crea `infra/postgres/20-init-backup-role.sh` (la contrasena viaja como variable de psql, no pegada en el SQL), montado solo en `docker-compose.prod.yml`.
- **Lote 3 (D10, D12, D13).** Cada corrida escribe `.tmp`, lista con `pg_restore --list` (deben estar las cuatro tablas de libro), renombra a `.dump` y aplica la retencion; un archivo ilegible pasa a `.dump.fallido`, un corte a mitad borra el `.tmp`, y en ambos casos no se borra nada. El comando a pedido es `docker compose … run --rm backup ahora`. En el ensayo local con carpeta de Windows montada, el contenedor fija `700`/`600` y el sistema de Windows lo ignora sin error. El contenedor corre como root (la imagen base lo hace por defecto) para poder escribir en la carpeta montada cualquiera sea su dueno; en Linux los archivos quedan de root con `600`.
- **Lote 3 (D14).** Salud: `salud.sh` cuenta solo `.dump`; sin ninguno, es sano hasta **una hora despues de la primera corrida programada** (la que registra `programar.sh` al arrancar). Intervalo de la verificacion: 5 minutos.
- **Lote 3 (saltos de linea).** El arbol de trabajo de Windows usa CRLF (`autocrlf`) y un `.sh` con CRLF no corre en Linux. Se agrego `.gitattributes` (`*.sh` y `Dockerfile*` con `eol=lf`), el `Dockerfile` del backup quita los CR de sus scripts, y una prueba falla si algun `.sh` de `infra/` tiene CRLF. `Caddyfile` y `Caddyfile.dev` se sumaron en el Lote 4 (ver abajo).
- **Lote 3 (hallazgo `date`).** En `programar.sh`, `date -d "03:00 + 1 day"` lee `+ 1` como zona horaria y corre la hora 4 horas: se suma el dia a la fecha sola. Cubierto por pruebas (antes y despues de la hora, medianoche y cambio de hora de verano de otra zona).
- **Lote 4 (saltos de linea, Caddyfile).** `.gitattributes` suma `Caddyfile* text eol=lf`. `Caddyfile.dev` ya estaba en LF en el indice (`git ls-files --eol`: `i/lf`); solo el arbol de trabajo de Windows lo tenia en CRLF, asi que la regla no cambia su contenido versionado.
- **Lote 4 (D16, runbook).** `docs/runbook/puesta-en-marcha.md`: terminos basicos, Escenario 1 (PC de Windows con Docker Desktop, `CADDY_TLS=internal`, IP fija por reserva DHCP, Firewall, `icacls`, certificado raiz de Caddy en Android e iPhone), Escenario 2 (VPS con dominio, `CADDY_TLS=<correo>`, aviso de Let's Encrypt) y pasos comunes (clonado, secretos, atajo `dc`, primer arranque, siembra con contrasena oculta, backup a pedido, salud y registros, actualizacion, SQL de `app_backup`, paso del escenario 1 al 2). El certificado raiz se exporta con `docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt`; en Git Bash se antepone `MSYS_NO_PATHCONV=1`. Pruebas de lectura del runbook en `backend/tests/infra/test_runbook_y_ci.py`.
- **Lote 4 (D17, CI).** El trabajo de integracion de `.github/workflows/ci.yml` corre ahora `tests/integration tests/infra` (el runner de GitHub trae Docker). La corrida en CI la ve el usuario al subir.
- **Lote 4 (consecuencia operativa en Windows).** `docker compose cp` y los comandos con rutas de contenedor necesitan `MSYS_NO_PATHCONV=1` en Git Bash; `curl -w %{http_code}` puede imprimir `000` por el manejo de certificados de Windows (usar el navegador o `curl -v`); los permisos `700`/`600` no se comprueban sobre carpetas de Windows montadas: la proteccion es `icacls` sobre la carpeta.

## Limitaciones conocidas y ajustes de la prueba manual (2026-11-08)

- **IP única en Docker Desktop para Windows (Escenario 1).** Todos los clientes llegan al backend con la misma IP (se observó `172.30.10.1`, la puerta de enlace de la red `frente`). El límite de 20 fallos de login por IP en 15 minutos (ADR-018, ADR-057) cuenta a toda la oficina junta y el desbloqueo manual del administrador no lo reinicia (solo el del par usuario/organización); se resuelve solo a los 15 minutos. En el Escenario 2 (VPS Linux) se ve la IP real de cada teléfono. Sin cambios de código ni de umbral; documentado en el runbook (E1.5).
- **El contenedor `backup` corre como root.** Aceptado en el 27a; se endurece en el 27b.
- **Hora de gracia del backup.** Recién instalado, `backup` no pasa a `unhealthy` hasta una hora después de la primera hora programada; se recomienda `run --rm backup ahora` tras instalar.
- **`run --rm migraciones` puede recrear `postgres`** si cambió una variable de su entorno (corte de segundos); en una actualización normal no cambia (D15).
- **Frontend (sin cambio de API).** Recorte de organización y usuario en el login (enmienda de ADR-057) y pantalla de error de ruta «Hay una versión nueva del sistema» con «Recargar» ante un fallo de carga de módulo tras un despliegue (design D18 y D19).

- **Enmienda (2026-11-10, change 27b, ADR-072).** Sin cambiar lo decidido aquí: ADR-072 enmienda D12 (restauración probada), D13 (retención 14 + 8) y la limitación del contenedor `backup` como root (que pasa a usuario sin privilegios).

- **Enmienda (2026-11-11, change 28, ADR-073).** Punto 3: la CSP y los demás encabezados de seguridad quedaron implementados en Caddy en el change 28 (ADR-073).
