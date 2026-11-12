# ADR-072 — Backups completos: retención 14 + 8, copia externa cifrada y restauración probada

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-11-08 |
| Referenciado en | `openspec/changes/27b-backups-y-runbook-completo/design.md` D0 a D16 y `specs/sistema/respaldos`, `specs/sistema/despliegue`; `00-vision-y-alcance.md` §9 criterio 12; `01-dominio.md` INV-05; `02-arquitectura.md` §16.2, §17, §18; `04-roadmap-changes.md` §12; ADR-020, ADR-063, ADR-071 |

**Change 27b. Gobernanza: dominio ALTO (backups y restauración de datos de usuarios). CRÍTICAS: D3, D13. ALTAS: D1, D2, D4, D5, D7, D8, D12. Aprobado por el usuario el 2026-11-08 (tarea 0.1): opción (A) en D0–D16; D3 Backblaze B2 (cuenta a abrir más adelante); D13 fuera de alcance → VPS. Vigente desde el 2026-11-10 (archivo del change 27b).**

## Contexto

`02` §16.2 pide retención de 14 diarios y 8 semanales, copia a almacenamiento externo y una restauración probada en un entorno separado antes de salir a producción y luego al menos una vez por mes (`00` §9 criterio 12). El 27a (ADR-071) dejó backups diarios verificados con retención de los últimos 7, en la misma PC que la base, con el contenedor de backup como root, y difirió al 27b la restauración probada, el runbook de restauración y la mudanza de los datos de la PC a un VPS. `docs/` no resuelve: cómo contar los semanales, adónde y con qué se copia, si se cifra y quién guarda la clave, cómo se restaura sin riesgo, cómo se comprueba que los datos coinciden, cómo se garantiza la prueba mensual, cómo se muda y qué hacer con el acceso desde la calle.

## Decisión propuesta (opciones A de `design.md`, aprobadas el 2026-11-08)

1. **Alcance (D0).** Un change en cuatro lotes.
2. **Retención (D1).** El más reciente de cada uno de los 14 días con backup y de cada una de las 8 semanas (lunes a domingo, `TZ`) con backup; fecha tomada del nombre; nunca se borra por calendario. `BACKUP_DIARIOS` y `BACKUP_SEMANALES` reemplazan `BACKUP_RETENCION`.
3. **Retención externa (D2).** La copia solo sube; no replica borrados; aplica la misma regla en el destino.
4. **Destino (D3, CRÍTICA, de negocio).** Almacenamiento de objetos compatible con S3, configurado por variables (recomendado Backblaze B2; elección final del usuario, Q2).
5. **Herramienta (D4).** rclone con versión fijada en un servicio aparte `copia-externa`: sin credenciales de base, `BACKUP_DIR` solo lectura, red nueva `salida`; `backup` sigue sin internet.
6. **Cifrado (D5).** `crypt` de rclone en el equipo antes de salir (contenido y nombres); la clave nunca va al destino.
7. **Frecuencia y salud (D6).** Cada hora sube lo que falta y lo comprueba (`cryptcheck`); no sano si la copia más reciente tiene más de 26 horas.
8. **Custodia (D7, de negocio).** Clave y accesos en el archivo de entorno y en custodia del dueño fuera de la PC (hoja de recuperación).
9. **Restauración (D8).** Servicio `restauracion` en un perfil aparte, como `app_migrations` (no superusuario), solo sobre una base vacía y sin otras conexiones, en una sola transacción; conserva dueños y permisos (INV-05).
10. **Comprobación (D9).** Filas por tabla del archivo contra la base, permisos de libros y versión de Alembic.
11. **Prueba mensual (D10).** Servicio `prueba-restauracion` sin red ni credenciales, con un Postgres temporal propio **en el disco del contenedor** (se borra tras cada prueba) y **sin aviso externo**; no sano a los 35 días sin prueba buena. La primera prueba, a mano desde la copia externa.
12. **Sin root (D11).** Los servicios de respaldo corren como `999:999` (configurable); en Linux la carpeta pertenece a ese usuario.
13. **Mudanza (D12).** Backup a pedido con el backend detenido y la cola de cada teléfono vacía; restauración en el equipo nuevo sin sembrar; el viejo se conserva 30 días.
14. **Acceso desde la calle (D13, CRÍTICA, de negocio).** Fuera del change; el camino es el VPS. Q1 abierta, no bloquea.
15. **Aviso (D14).** `AVISO_URL` opcional (servicio de «hombre muerto») que usa solo `copia-externa`; vacío, no hace nada. La prueba mensual no avisa (sin red): su señal es la salud en `dc ps`, atrapada por la revisión semanal del runbook.
16. **Runbooks (D15).** `docs/runbook/restauracion.md` nuevo y ajustes de `puesta-en-marcha.md`.
17. **Pruebas (D16).** `backend/tests/infra/` con Testcontainers (destino local cifrado y `rclone serve s3`, dos Postgres para restaurar) y prueba manual con la hoja de recuperación.

## Consecuencias

- Perder la PC ya no pierde los datos, siempre que la hoja de recuperación esté en custodia; sin la clave, las copias externas no se pueden leer.
- El compose suma `copia-externa`, `prueba-restauracion` y `restauracion` (perfil) y la red `salida`; el archivo de entorno suma las variables de la copia y la clave de cifrado (sin valores por defecto).
- Enmienda ADR-071: D12 (la restauración probada queda resuelta aquí), D13 (retención 14 + 8 en lugar de 7) y la limitación «el contenedor `backup` corre como root».
- ADR-020 no cambia: la restauración usa el rol dueño del esquema; ningún servicio nuevo recibe credenciales de `app_runtime`.

## Precisiones del apply

Decisiones del usuario del 2026-11-09: (1) `prueba-restauracion` queda con `network_mode: none` y sin aviso externo; si la prueba mensual falla, el servicio figura `unhealthy` en `dc ps` y la revisión semanal del runbook lo atrapa. (2) El Postgres temporal de la prueba corre en el disco del contenedor, no en memoria, y se borra tras cada prueba.

- **Lote 1.** Retención en `infra/backup/retencion.sh`; `BACKUP_RETENCION` reemplazada por `BACKUP_DIARIOS` (14) y `BACKUP_SEMANALES` (8). Servicios como `${BACKUP_UID:-999}:${BACKUP_GID:-999}`; 999:999 escribe bien en un montaje de Windows.
- **Lote 2.** `infra/copia/`: rclone 1.68.2, solo por variables (`local` o `s3` + `crypt`). Verificación por archivo con `rclone check --download --one-way` en lugar de `cryptcheck` (la 1.68.2 no trae `--download` en `cryptcheck`; equivalente y más estricta). Montaje extra `${BACKUP_DIR}/bajados:/bajados` para `bajar`; volumen `copia_local` / `COPIA_LOCAL_DIR` para el ensayo local (claves de acceso `no-aplica`). Salud: backup más reciente del destino con más de 26 h o última corrida fallida por credenciales o clave; un corte de red solo no. Variables: `COPIA_ACCESS_KEY_ID`, `COPIA_SECRET_ACCESS_KEY`, `COPIA_CLAVE_CIFRADO`, `COPIA_SAL_CIFRADO` (ofuscadas con `rclone obscure`), `COPIA_TIPO`, `COPIA_RUTA`, `COPIA_S3_ENDPOINT`, `COPIA_S3_REGION`, `COPIA_S3_PROVEEDOR`, `COPIA_LOCAL_DIR`, `AVISO_URL`.
- **Lote 3.** D8 confirmada: `app_migrations` alcanza para restaurar el archivo completo, sin privilegios extra (ADR-020 intacto). Baranda de «otras conexiones» por `datid` y `usename IS NOT NULL`. Salud de la prueba: 35 días. Volumen `estado_prueba`. Variables `PRUEBA_DIA` (1) y `PRUEBA_HORA` (04:00).
- **Lote 4.** `docs/runbook/restauracion.md` (restaurar, prueba mensual, mudanza) y ajustes de `puesta-en-marcha.md`. Mejora posible: un comando `listar` en la copia externa (hoy el runbook usa `rclone lsf` dentro del contenedor para ver los nombres).

**Ajustes de la prueba manual (2026-11-10).** (1) Actualizando desde 27a en Windows, la carpeta de backups creada por el servicio de entonces (root) queda con metadatos de dueño 0 y los servicios nuevos (999:999) fallan con `Permission denied`: el runbook indica un `docker run … alpine chown -R 999:999` único para carpetas existentes (una nueva no necesita nada) y una lista de actualización desde 0.27.x. (2) El entorno separado de ensayo no puede levantar `caddy` junto a la oficina por la subred fija de `frente` (ADR-071 D5) y los puertos 80/443; el diseño de redes no cambia: restaurar y migrar se hace con la oficina andando y, para comparar en `/admin`, se baja la oficina con `dc down` (sin `-v`). (3) `restauracion` fija `TZ` como los demás servicios de respaldo.
