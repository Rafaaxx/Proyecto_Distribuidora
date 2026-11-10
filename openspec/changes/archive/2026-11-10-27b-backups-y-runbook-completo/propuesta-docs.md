# Propuesta de cambios a `docs/` — change 27b `backups-y-runbook-completo`

> **Borrador con las opciones A de `design.md`, pendientes de aprobación (0.1).** Se completa con las precisiones del apply (tarea 4.3). Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia. Las decisiones van en `docs/adr/ADR-072-backups-completos-copia-externa-y-restauracion.md`.
>
> Orden: `02` §16.2, §18; `04` §12; ADR-071 (nota de enmienda).

---

## `02-arquitectura.md`

### §16.2 Producción (etapa 1) — D1 a D12

**Actual**

> | `backup` | `pg_dump` diario comprimido con un rol de solo lectura, verificado al generarse; retención de 14 diarios y 8 semanales y copia a almacenamiento externo (27b; el 27a conserva los últimos 7) |

**Propuesto**

> | `backup` | `pg_dump` diario comprimido con un rol de solo lectura, verificado al generarse; retención del más reciente de cada uno de los 14 días y de cada una de las 8 semanas con backup (ADR-072) |
> | `copia-externa` | Sube cada backup conservado, cifrado en el equipo, a un almacenamiento externo compatible con S3; no replica borrados; misma retención en el destino; sin credenciales de base (ADR-072) |
> | `prueba-restauracion` | Una vez por mes, sin red y sin aviso externo, restaura el último backup en un Postgres temporal propio (en el disco del contenedor, que se borra tras la prueba) y comprueba que los datos coinciden; si falla, queda `unhealthy` (ADR-072) |
> | `restauracion` | A pedido (perfil aparte): restaura un backup solo en una base vacía, como `app_migrations` (ADR-072) |

Agregar a las viñetas:

> - Red `salida` solo para `copia-externa` (salida a internet, sin acceso a la base); `prueba-restauracion` sin red.
> - Los servicios de respaldo corren con un usuario sin privilegios.
> - Restauración, prueba mensual y mudanza a otro equipo: `docs/runbook/restauracion.md`.

Reemplazar la viñeta del DEBE por:

> - **DEBE:** una restauración de backup se prueba en un entorno separado antes de salir a producción (desde la copia externa, con la hoja de recuperación) y luego al menos una vez por mes; la prueba mensual es automática y su salud avisa a los 35 días sin una prueba buena (`00` §9, criterio 12; ADR-072).

### §18 Seguridad — D5, D7, D11

Agregar:

> - Las copias externas de los backups se cifran en el equipo antes de salir; la clave nunca se guarda en el almacenamiento externo y una copia queda en custodia del dueño fuera del equipo (ADR-072).
> - Los contenedores de respaldo no corren como root; el que sube copias a internet no tiene credenciales de la base (ADR-072).

---

## `04-roadmap-changes.md`

### §12 — fila 27b

Agregar debajo de la tabla el párrafo de cierre del change (entrega, decisiones, deudas al 28, prueba manual), como en los changes anteriores. Si D13 queda en A: «acceso desde la calle fuera de la etapa mientras el entorno siga en la PC; el camino es la mudanza al VPS (runbook de restauración)». Si Q1 sigue abierta, anotarlo.

---

## `docs/adr/ADR-071-despliegue-basico-y-backups-minimos.md`

Agregar al final una nota fechada (sin cambiar lo decidido): «Enmendado por ADR-072 (change 27b): D12 (restauración probada), D13 (retención 14 + 8) y la limitación del contenedor `backup` como root.»

---

## `openspec/specs/sistema/respaldos/spec.md` (al archivar)

Actualizar a mano el `## Purpose` (el delta no lo cambia): quitar «La retención completa, la copia fuera del servidor y la restauración probada son del change 27b» y describir la capacidad completa (retención 14 + 8, copia externa cifrada, restauración en base vacía y prueba mensual).

---

## Precisiones del apply (tarea 4.3)

Decisiones del usuario del 2026-11-09: `prueba-restauracion` sin aviso externo (su señal es la salud en `dc ps`, revisada cada semana según el runbook) y con el Postgres temporal en el disco del contenedor, no en memoria. `AVISO_URL` aplica solo a `copia-externa`.

- `02` §16.2: retención por `BACKUP_DIARIOS` (14) y `BACKUP_SEMANALES` (8); servicios de respaldo como `${BACKUP_UID:-999}:${BACKUP_GID:-999}`; `copia-externa` con rclone configurado solo por variables, verificación por archivo con `rclone check --download` y salud a 26 h (o fallo de credenciales/clave); `prueba-restauracion` con salud a 35 días y volumen de estado propio; `restauracion` (perfil) usa `app_migrations` (verificado: alcanza).
- `02` §18: la clave de cifrado son dos valores (`COPIA_CLAVE_CIFRADO`, `COPIA_SAL_CIFRADO`), ofuscados con `rclone obscure`.
- Mejora posible fuera del change: comando `listar` en `copia-externa` (hoy el runbook usa `rclone lsf` dentro del contenedor).
- Al archivar: actualizar a mano el `## Purpose` de `openspec/specs/sistema/respaldos/spec.md`.

## Precisiones del apply (ajustes de la prueba manual, 2026-11-10)

- Permisos de la carpeta de backups al actualizar desde 27a en Windows: `docker run --rm -v "C:/distribuidora/backups:/b" alpine chown -R 999:999 /b` (una sola vez; una carpeta nueva no lo necesita). Reflejarlo en `02` §16.2 si habla de dueños.
- El ensayo en un proyecto de Compose separado no puede levantar `caddy` con la oficina arriba (subred fija de `frente`, puertos 80/443): se baja la oficina con `dc down` sin `-v` durante la comparación. Sin cambio de diseño de redes.
- `restauracion` fija `TZ` igual que `backup`, `copia-externa` y `prueba-restauracion`.
