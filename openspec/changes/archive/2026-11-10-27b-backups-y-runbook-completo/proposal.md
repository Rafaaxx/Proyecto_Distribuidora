# Change 27b-backups-y-runbook-completo

## Qué resuelve este change

Los backups dejan de vivir solo en el mismo equipo: se conservan 14 diarios y 8 semanales, se copian cifrados a un almacenamiento externo y se prueba (sola, una vez por mes, y a mano antes de salir a producción) que se pueden restaurar y que los datos coinciden. Queda escrito cómo restaurar y cómo mudar los datos de la PC de la oficina a un VPS.

## Why

`04` §12 (fila 27b) y las deudas del 27a (`04`, párrafo de cierre del 27a; ADR-071 D12, D13 y limitaciones). Hoy los backups están en la misma PC que la base: si la PC se rompe, se la roban o la cifra un virus, se pierden datos y backups juntos. Ninguna restauración se probó en un entorno separado (`00` §9 criterio 12; `02` §16.2: «antes de salir a producción y luego al menos una vez por mes»). El 28 depende de este change.

## What Changes

- **Retención completa (D1):** 14 diarios y 8 semanales, contados por días y semanas que tienen backup (nunca se queda sin backups si el servicio se detiene); reemplaza la retención de los últimos 7.
- **Copia externa (D2 a D7, D14):** servicio nuevo `copia-externa`, sin credenciales de la base, que sube cada backup cifrado en el equipo, aplica la misma retención en el destino sin replicar borrados y avisa por su salud si se atrasa. El proveedor es configuración (D3, decisión del usuario).
- **Restauración (D8, D9):** una orden que restaura **solo en una base vacía**, con el rol dueño del esquema (no el superusuario), y comprueba filas por tabla y los permisos de INV-05.
- **Prueba mensual (D10):** servicio `prueba-restauracion`, sin red, que restaura el último backup en un Postgres temporal propio, lo comprueba y lo descarta; su salud avisa a los 35 días sin prueba buena.
- **Endurecimiento (D11):** los contenedores de respaldo dejan de correr como root (deuda del 27a).
- **Runbooks (D12, D15):** `docs/runbook/restauracion.md` (prueba mensual, desastre y mudanza PC → VPS con la cola de cada teléfono vacía antes) y ajustes de `puesta-en-marcha.md`.
- **Acceso desde la calle (D13):** se recomienda dejarlo **fuera**; el camino es mudarse al VPS (D12). Q1 sigue abierta, no bloquea.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `sistema/respaldos`: retención 14 + 8 (reemplaza la mínima), copia externa cifrada con su retención y su salud, restauración en base vacía con comprobación, prueba periódica en entorno separado, contenedores no root, aviso externo opcional.
- `sistema/despliegue`: servicios nuevos y su exposición, secretos nuevos sin valor por defecto, roles por servicio (restauración con `app_migrations`), puesta en marcha con la copia externa y mudanza de los datos a otro equipo.

## Impact

- `infra/backup/`, imagen nueva `infra/copia/` (rclone), `docker-compose.prod.yml` (tres servicios, uno en perfil aparte; red `salida`), `infra/produccion.env.example` (`BACKUP_DIARIOS`/`BACKUP_SEMANALES` reemplazan `BACKUP_RETENCION`).
- `backend/tests/infra/` (pruebas nuevas con Testcontainers), `docs/runbook/`, `README.md`.
- ADR-072 (*Propuesto*), enmienda ADR-071 (D12, D13, limitación de root). **INV-05**: los permisos sobreviven a la restauración (probado) y ningún servicio nuevo usa roles de la aplicación; `00` §9 criterio 12; `02` §16.2, §17, §18.
- **Sin migración de Alembic, sin cambios de API ni de Dexie, sin textos de interfaz ni ayuda contextual** (ADR-051: no aplica). Sin fixtures compartidos (no toca cálculos).

## No incluye

- Acceso desde la calle a la PC de la oficina (*port forwarding*, DNS dinámico, túneles o VPN), salvo que el usuario elija otra opción en D13.
- Contratar el VPS o el dominio (Q1) y la mudanza real (queda documentada y probada en un ensayo).
- Backups más de una vez por día, réplica en caliente o recuperación a un instante (PITR).
- Monitoreo avanzado más allá del aviso opcional (D14); CSP y permisos de base (28).
