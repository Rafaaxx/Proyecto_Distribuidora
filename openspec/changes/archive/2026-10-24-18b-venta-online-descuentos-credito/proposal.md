# Change 18b-venta-online-descuentos-credito

## Qué resuelve este change

La venta aplica las reglas de descuento y el descuento manual (con tope, motivo y autorización), evalúa el crédito del cliente con las tres políticas, verifica el PIN del supervisor y congela todo en la venta (DSC-05 a DSC-09, CRE-01 a CRE-10, SEG-05, INV-10).

## Why

`04` §9, fila 18b: completa la venta del hito 5. Le dejaron deudas nominadas el 16 (efecto del motor y del descuento manual, PIN, `venta_linea_descuento`, DSC-09, auditoría, comando de parámetros y motivos, tope visible), el 16b (ayuda), el 18a y ADR-054 (columnas `credito_*`, crédito y descuentos sin conexión, consumidor final frente al límite cero) y ADR-032 (cómo se aplica la tolerancia porcentual).

## What Changes

- **Descuentos en la venta** (DSC-05 a DSC-09): `VENTA_CONFIRMAR` llama a `descuentos/service.py` (reglas vigentes al momento, porcentaje manual general y propio por línea, una evaluación del tope por venta); con conexión rechaza si difieren (`DESCUENTO_DIFIERE`), sin conexión congela lo del dispositivo y observa. Tabla nueva `venta_linea_descuento` (DSC-08).
- **Crédito** (CRE-01 a CRE-10): motor puro nuevo en `clientes/domain/credito.py` con gemela en TypeScript y **fixtures compartidos nuevos `shared/fixtures/calculo/cre-01-credito.json`**, escritos antes del código; ADVERTIR, AUTORIZAR y BLOQUEAR con conexión; tolerancia y recálculo sin conexión (CRE-06, CRE-08, CRE-09); snapshot en columnas `credito_*` de `venta`.
- **PIN de supervisor con conexión** (SEG-05, ADR-011, ADR-019): verificación en el servidor sin que el PIN entre al contenido guardado ni a la huella; límite de intentos por quien intenta y autorizador, con tope general por autorizador, 15 minutos desde el último fallo (D3, revisada el 2026-10-22). Rechazo de PIN triviales (ADR-019). **"Mi PIN"** (D21 combinada): comando nuevo `PIN_AUTORIZACION_PROPIO_DEFINIR` para que quien tiene un permiso de autorización defina su propio PIN confirmando su contraseña.
- **Permiso de cada comando en todo camino** (SEG-06; D23, agregado el 2026-10-22, ADR-056): el catálogo de tipos declara el permiso de cada tipo y el bus lo exige por REST y por el lote (hoy 17 tipos, entre ellos `ROL_PERMISOS_CAMBIAR`, `USUARIO_CREAR` y `PIN_AUTORIZACION_ROTAR`, se ejecutan por el lote en `ONLINE` sin permiso); los tipos con secretos no entran por el lote; la contraseña de `USUARIO_CREAR` sale del contenido y de la huella.
- **Login** (ADR-018; D24, agregado el 2026-10-22): el bloqueo por intentos dura 15 minutos desde el último fallo y los intentos durante el bloqueo no lo extienden.
- **Parámetros y motivos:** comando de parámetros del descuento manual, motivos sembrados del ámbito `DESCUENTO_MANUAL`, validación del motivo; parámetros de crédito de la organización (D14).
- **Lecturas para vender:** el tope propio aplicable ("Podés descontar hasta 5 %; más pide autorización"), motivos, autorizadores y el crédito del cliente, sin `GET /yo` ni el token (decisión del usuario del 2026-10-15).
- **Auditoría** del descuento manual y de las autorizaciones de crédito (AUD-01, AUD-02).
- **Pantallas `/admin`:** "Nueva venta" con descuentos, crédito y autorización; detalle con el snapshot; configuración del descuento manual y del crédito; PIN de autorización (pestaña en Roles) y "Mi PIN". Ayuda contextual (ADR-051).

## Decisiones (bloqueantes)

`design.md` D0 a D22, **aprobadas por el usuario el 2026-10-21** (tarea 0.1): opción A en todas, salvo D21, que combina A (pestaña en Roles) y B ("Mi PIN"). **2026-10-22:** D3 revisada; D24 (login) aprobada; D23 (permiso por comando en todo camino) aprobada en principio, con la regla concreta pendiente de confirmación (tarea 0.3). **Críticas:** D2 (cómo viaja el PIN), D3 (intentos de PIN), D7 (crédito sin conexión), D10 (descuentos sin conexión), D18 (orden de la transacción), D23 (permiso por comando y secretos) y D24 (login). **Altas:** D1, D5, D6, D9, D11, D13, D14, D15, D16, D19 y D21. `docs/` no resuelve: la venta que no aumenta la deuda de un cliente ya excedido, el código de error de cada política, la observación de una autorización sin conexión (`02` §12.4 la exige y SYN-07 no tiene código), el "bootstrap" que el 18b nombra pero llega con el 21, y el porcentaje de tolerancia (ADR-032). Se registran en **ADR-055** (*Propuesto*); D23, por ser transversal al bus y a todos los módulos, en **ADR-056** (*Propuesto*); D24 como enmienda a ADR-018.

## Tamaño

Supera `04` §2. D0 recomienda un change en cinco lotes, con el camino sin conexión aislado.

## No incluye

Bootstrap, Dexie y verificación local del PIN en el teléfono (21, 22a). Autorización remota (CRE-11) y bloqueo por antigüedad (CRE-12), etapa 2. Notificación activa a administración de CRE-09 (queda la observación; bandeja en el 25). Tope propio por usuario (change de usuarios y roles). Anulación (19), nota de venta (20).

## Invariantes

- **INV-10:** `venta_linea_descuento` y las columnas `credito_*` sin `UPDATE` ni `DELETE` para `app_runtime`; prueba que lo cita.
- **INV-01:** descuentos, evaluación y snapshot en la misma transacción; falla inyectada.
- **INV-14:** neto = bruto − descuentos por línea, con `CHECK` y fixtures.
- **INV-17:** sin conexión nada se rechaza por descuento ni crédito.
- **INV-03, INV-06, INV-21:** porcentajes y importes como texto; doble envío; autorizador ajeno 404.

## Capabilities

### New Capabilities

- `ventas/descuentos-en-la-venta`: reglas y descuento manual en la venta, tope, motivo, autorización, DSC-09 y persistencia (DSC-05 a DSC-09).
- `ventas/credito-en-la-venta`: evaluación con las tres políticas, con y sin conexión, y snapshot (CRE-02 a CRE-10).
- `clientes/evaluacion-de-credito`: motor puro de crédito y sus casos compartidos (CRE-01, CRE-02, CRE-06).

### Modified Capabilities

- `ventas/calculo-de-venta`: el motor recibe el descuento manual.
- `ventas/administracion-de-ventas`: lecturas de tope, autorizadores y crédito; pantalla y detalle.
- `descuentos/descuento-manual`: motivo validado y parámetros definidos por comando.
- `identidad/pin-de-autorizacion`: verificación con conexión, intentos, pantalla, "Mi PIN" con reautenticación y rechazo de PIN triviales.
- `clientes/datos-de-credito`: la venta sí expone disponible y política aplicable.
- `organizacion/parametros-de-organizacion`: comandos de parámetros de descuento y crédito.
- `organizacion/catalogos-configurables`: motivos de descuento manual sembrados.
- `sync/observaciones`: observación de autorización sin conexión.
- `auditoria/registro-de-auditoria`: filas de descuento manual y de autorización de crédito.
- `sistema/ayuda-contextual`: ayuda de descuentos, crédito y PIN.
- `sistema/pipeline-de-comandos`: el permiso declarado en el catálogo se exige en todo camino (D23). *Spec delta por crear en la tarea 0.3.*
- `sync/lote-de-comandos`: tipos con secretos rechazados en el lote y fuera de la cuarentena (D23). *Por crear en 0.3.*
- `identidad/autenticacion-y-sesion`: bloqueo del login de 15 minutos desde el último fallo (D24). *Por crear en 0.3.*
- `identidad/usuarios-y-roles`: la contraseña del alta viaja fuera del contenido (D23). *Por crear en 0.3.*

## Impact

Backend: `ventas`, `descuentos`, `clientes` (dominio de crédito), `identidad` (PIN, parámetros, login, alta de usuario), `configuracion` (motivos), `app/commands` y `sync` (permiso por tipo en el bus, D23) y la declaración de todos los tipos de comando de los 12 módulos; una migración (enmendada en la rama). Frontend: `domain/credito/`, `domain/ventas/`, `areas/admin/ventas/`, `areas/admin/configuracion/`, `areas/admin/roles/`, `ayuda/textos.ts`. Fixtures: `cre-01-credito.json` (nuevo), `vta-04-totales.json` (casos con descuento manual). Docs, ADR-055, ADR-056 y enmiendas (ADR-012, ADR-018, ADR-052, entre otras). Gobernanza **crítica** en PIN, autorización, reautenticación de "Mi PIN", login, permisos del bus y crédito sin conexión.
