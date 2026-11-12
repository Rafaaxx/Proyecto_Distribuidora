# ADR-020 — Dos usuarios de PostgreSQL: migraciones y runtime

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/01` INV-05, `docs/02` §18, change 03 |

## Contexto

INV-05 exige que las tablas de libro (`cuenta_movimiento`, `stock_movimiento`, `costo_producto_mov`, `auditoria`) sean de solo inserción y que el usuario de la aplicación no tenga `UPDATE` ni `DELETE` sobre ellas. Con un único usuario dueño del esquema, esta garantía depende exclusivamente del código; la base no la impone.

## Decisión

Dos usuarios de PostgreSQL:

- **`app_migrations`**: dueño del esquema (`OWNER`). Solo lo usa Alembic al correr migraciones. Nunca lo usa la aplicación en runtime.
- **`app_runtime`**: usuario de la aplicación. Recibe permisos explícitos tabla por tabla, declarados en la migración que crea cada tabla.

Política de permisos por tipo de tabla:

| Tipo | Permisos de `app_runtime` |
| --- | --- |
| Tablas de libro (solo inserción) | `SELECT`, `INSERT` |
| Tablas de saldo (materializadas) | `SELECT`, `INSERT`, `UPDATE` |
| Tablas operacionales (sesiones, comandos, etc.) | `SELECT`, `INSERT`, `UPDATE`, `DELETE` |
| Tablas de auditoría | `SELECT`, `INSERT` |
| Tablas maestras | `SELECT`, `INSERT`, `UPDATE` (nunca `DELETE`) |

Los `GRANT` y `REVOKE` se declaran en cada migración de Alembic que crea o modifica una tabla. Las URLs de conexión de migraciones y runtime son variables de entorno distintas.

## Consecuencias

- INV-05 queda garantizado por la base, no solo por el código. Una prueba verifica los permisos reales del usuario de runtime contra cada tabla; si falta un `GRANT` o sobra un permiso, CI falla.
- Si se agrega una tabla nueva y se olvida el `GRANT`, la aplicación lanza un error de permisos en el primer uso; no es un fallo silencioso.
- Las migraciones de Alembic usan `app_migrations`; la aplicación usa `app_runtime`. Dos entradas distintas en `docker-compose.yml` y en la configuración de producción.
- El `downgrade` de Alembic también corre con `app_migrations` para poder hacer `DROP TABLE`.

## Alternativas consideradas

- **Un solo usuario dueño:** más simple de configurar, pero INV-05 queda como promesa del código. Descartado porque un error en un handler podría borrar historia sin que la base lo impida.
- **Row Level Security de PostgreSQL:** defensa adicional evaluada para la etapa 4 (aislamiento por organización a nivel de base). No reemplaza la separación de usuarios para INV-05.
