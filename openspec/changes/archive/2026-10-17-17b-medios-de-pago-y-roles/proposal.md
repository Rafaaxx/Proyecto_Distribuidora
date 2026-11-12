# Change 17b-medios-de-pago-y-roles

## Qué resuelve este change

Permite que la organización administre sus medios de pago (alta, edición, baja y reactivación) y que cambie los permisos de sus roles desde `/admin`, sin tocar la base a mano. Corrige la siembra: Transferencia, Cheque y Tarjeta piden referencia.

## Why

Lo mostró la prueba manual del change 17 (2026-10-16): los medios de pago son un catálogo configurable (TR-09, `01` §4) pero solo existe `GET /configuracion/medios-pago`; todos nacen con `requiere_referencia = false`, así que COB-02 y PAG-01 nunca piden referencia; y `01` §19 dice que "la organización puede modificar la composición" de sus roles, pero solo hay `PUT /identidad/roles/{id}/permisos`, sin pantalla. Ningún change del roadmap es dueño de esto, y el 18a (venta con cobranza en el acto) usa los medios: va antes del 18a.

## What Changes

- **Medios de pago (D1 a D6):** comandos `MEDIO_PAGO_CREAR` y `MEDIO_PAGO_MODIFICAR` v1 (solo `ONLINE`, con `ADMIN_CONFIGURACION`, por el bus, con auditoría). La baja es desactivar, nunca borrar (TR-06, CAT-05); se puede reactivar. Nombre único por organización (sin distinguir mayúsculas). No se desactiva el último medio activo. Nueva lectura de todos los medios (activos e inactivos) para la pantalla.
- **Valores por defecto (D5, aprobado por el usuario):** Transferencia, Cheque y Tarjeta piden referencia; Efectivo y Billetera no. Siembra de organizaciones nuevas y migración de las existentes.
- **Permisos por rol (D7 a D9):** pantalla "Roles y permisos" sobre el comando existente `ROL_PERMISOS_CAMBIAR`, con la lectura nueva del catálogo de permisos. **Regla nueva (crítica):** ningún cambio puede dejar la organización sin un usuario activo que tenga `ADMIN_USUARIOS`.
- **Pantallas `/admin`:** "Configuración → Medios de pago" y la sección "Roles y permisos"; ayuda contextual (ADR-051, D11).
- **ADR-053** (*Propuesto*) y propuesta de cambios a `docs/01`, `03` y `04` (incluye sumar el 17b al roadmap).

## Decisiones (bloqueantes)

`design.md` D0 a D12, **APROBADAS** el 2026-10-17 (A en todas). Críticas: **D8** (la protección del último administrador) y **D7** (alcance de roles). Altas: D1 (permiso), D4 (reglas de la baja) y D5 (cómo llegan los valores por defecto a la organización que ya existe). El resto, medias o bajas. Ninguna está resuelta en `docs/`: requieren ADR-053.

## Tamaño

Dentro de `04` §2: un change en tres lotes, sin revisión entre lotes salvo las confirmaciones de las piezas críticas (D0).

## No incluye

Crear roles nuevos, desactivar roles o usuarios, cambiar el rol de un usuario y la pantalla de usuarios (el "change de usuarios y roles", D9.5 de ADR-028; D7). Administrar motivos y alícuotas (D10). Cambiar los topes de descuento (ya está en "Topes por rol", change 16). La lista de medios en el teléfono sin conexión (bootstrap, change 21). Reportes por medio (26).

## Reglas e invariantes

- **TR-09, `01` §4 (medios), CAT-05, TR-06:** catálogo propio, baja sin borrar, lectura por id de los inactivos.
- **COB-02, PAG-01:** la referencia obligatoria pasa a exigirse de verdad en los medios marcados; sin conexión, la falta queda como `REFERENCIA_FALTANTE` (SYN-07, change 17).
- **`01` §19, ADR-017, ADR-011:** cambio de permisos con efecto en la petición siguiente; invalidación del PIN cuando el rol pierde su último permiso de autorización (ya existe).
- **INV-02, INV-21:** todo por `organizacion_id` del token; otra organización → 404. **INV-06:** doble envío sin doble efecto. **INV-01:** el comando se aplica entero o no se aplica. **INV-05:** sin `DELETE` sobre `medio_pago`.
- No toca cálculos de precios, descuentos ni costos: **sin fixtures compartidos**.

## Capabilities

### New Capabilities

- `organizacion/administracion-de-medios-de-pago`: comandos, reglas de nombre y de baja, lectura completa y pantalla.
- `identidad/administracion-de-roles`: pantalla de permisos por rol, catálogo de permisos y protección del último administrador.

### Modified Capabilities

- `organizacion/catalogos-configurables`: los medios sembrados declaran su referencia obligatoria; organizaciones existentes por migración.
- `identidad/usuarios-y-roles`: el cambio de composición rechaza dejar la organización sin administrador.
- `sistema/ayuda-contextual`: pantallas de medios de pago y de roles.

## Impact

Backend: `configuracion/` (nuevo `commands.py`, dominio, API, repositorio), `identidad/` (servicio, API: `GET /identidad/permisos`), `app/seed.py`, una migración (índice único y datos), ratchets de rutas y comandos. Frontend: `areas/admin/configuracion/`, área nueva `areas/admin/roles/`, `features/identidad/secciones.ts`, `ayuda/textos.ts`. Gobernanza **alta**, con D7 y D8 **críticas**.
