## Purpose

Permite que cada organización administre sus propios medios de pago (alta, edición, baja y reactivación) por el bus de comandos y desde `/admin`, sin borrar nunca un medio usado en cobranzas o pagos (TR-09, TR-06, CAT-05).

## ADDED Requirements

### Requirement: Un medio de pago se crea por comando

El sistema DEBE ofrecer el comando `MEDIO_PAGO_CREAR` v1, solo `ONLINE`, por el bus, con el permiso `ADMIN_CONFIGURACION` (`design.md` D1, D2). Lleva nombre y si pide referencia; el medio nace activo y pertenece a la organización del token. El nombre DEBE guardarse recortado y NO DEBE quedar vacío ni de solo espacios (`NOMBRE_INVALIDO`, 422). El nombre DEBE ser único en la organización sin distinguir mayúsculas, entre activos e inactivos (`NOMBRE_DUPLICADO`, 409; D3). El alta DEBE dejar una fila de auditoría con el medio creado (AUD-01, D11).

#### Scenario: Alta de un medio
- **GIVEN** un usuario con `ADMIN_CONFIGURACION` de la organización A
- **WHEN** crea el medio " Mercado Pago " que pide referencia
- **THEN** A tiene el medio activo "Mercado Pago" con `requiere_referencia = true`, y aparece en `GET /configuracion/medios-pago`
- **AND** queda una fila de auditoría con el medio creado
- **Regla:** TR-09; `01` §4; AUD-01

#### Scenario: Nombre vacío
- **WHEN** se crea un medio con nombre "   "
- **THEN** la respuesta es 422 con `NOMBRE_INVALIDO` y no se crea nada
- **Regla:** `03` §4 (`medio_pago.nombre` obligatorio)

#### Scenario: Nombre repetido sin distinguir mayúsculas
- **GIVEN** la organización A con el medio "Efectivo" dado de baja
- **WHEN** se crea el medio "efectivo"
- **THEN** la respuesta es 409 con `NOMBRE_DUPLICADO` y no se crea nada
- **Regla:** TR-09; ADR-053

#### Scenario: El mismo nombre en otra organización
- **GIVEN** la organización B con el medio "Mercado Pago"
- **WHEN** un usuario de A crea "Mercado Pago"
- **THEN** se crea en A sin error
- **Regla:** TR-08; INV-02

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `ADMIN_CONFIGURACION`
- **WHEN** intenta crear un medio
- **THEN** la respuesta es 403 y no se crea nada
- **Regla:** `01` §19

#### Scenario: Doble envío
- **GIVEN** un alta de "Mercado Pago" ya aceptada con un `operation_id`
- **WHEN** se reenvía el mismo comando con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original y sigue habiendo un solo "Mercado Pago"
- **Regla:** INV-06

### Requirement: Un medio de pago se modifica, se da de baja y se reactiva por comando

El sistema DEBE ofrecer el comando `MEDIO_PAGO_MODIFICAR` v1, solo `ONLINE`, con `ADMIN_CONFIGURACION`, que reemplaza nombre, si pide referencia y si está activo (`design.md` D2). La baja es pasar a inactivo y NO DEBE borrar el medio (TR-06, CAT-05); un medio inactivo DEBE poder reactivarse. Se aplican las mismas reglas de nombre que en el alta. NO DEBE quedar la organización sin ningún medio activo (`ULTIMO_MEDIO_ACTIVO`, 409; D4), tampoco con dos bajas al mismo tiempo. Un medio de otra organización o inexistente DEBE responder 404. Cada modificación DEBE dejar una fila de auditoría con el valor anterior y el nuevo (AUD-01, D11).

#### Scenario: Marcar que pide referencia
- **GIVEN** el medio "Billetera" de A sin referencia obligatoria
- **WHEN** se lo modifica para que pida referencia
- **THEN** una cobranza con conexión que usa "Billetera" sin referencia responde `REFERENCIA_OBLIGATORIA`
- **AND** la auditoría guarda `requiere_referencia` antes `false` y después `true`
- **Regla:** COB-02; PAG-01; AUD-01

#### Scenario: Dar de baja un medio usado
- **GIVEN** el medio "Billetera" de A, usado en una cobranza de $10.000,00 confirmada
- **WHEN** se lo da de baja
- **THEN** ya no aparece en `GET /configuracion/medios-pago`
- **AND** la cobranza sigue mostrando el medio "Billetera" en su detalle
- **AND** una cobranza nueva con conexión con "Billetera" responde `MEDIO_PAGO_INACTIVO`
- **Regla:** CAT-05; TR-06; COB-01

#### Scenario: Reactivar un medio
- **GIVEN** el medio "Billetera" de A dado de baja
- **WHEN** se lo reactiva
- **THEN** vuelve a aparecer en `GET /configuracion/medios-pago`
- **Regla:** CAT-05; ADR-053

#### Scenario: Renombrar un medio
- **GIVEN** el medio "Billetera" usado en un pago a proveedor
- **WHEN** se lo renombra "Mercado Pago"
- **THEN** el detalle del pago muestra "Mercado Pago"
- **Regla:** TR-09; ADR-053

#### Scenario: Renombrar a un nombre que ya existe
- **GIVEN** A con "Efectivo" y "Billetera"
- **WHEN** se renombra "Billetera" a "EFECTIVO"
- **THEN** la respuesta es 409 con `NOMBRE_DUPLICADO` y "Billetera" queda como estaba
- **Regla:** ADR-053

#### Scenario: El último medio activo no se da de baja
- **GIVEN** A con un solo medio activo, "Efectivo"
- **WHEN** se lo da de baja
- **THEN** la respuesta es 409 con `ULTIMO_MEDIO_ACTIVO` y "Efectivo" sigue activo
- **Regla:** ADR-053

#### Scenario: Dos bajas al mismo tiempo
- **GIVEN** A con dos medios activos, "Efectivo" y "Transferencia"
- **WHEN** dos administradores dan de baja uno cada uno al mismo tiempo
- **THEN** una baja se acepta y la otra responde `ULTIMO_MEDIO_ACTIVO`; A queda con un medio activo
- **Regla:** ADR-053; INV-01

#### Scenario: Medio de otra organización
- **GIVEN** el medio "Efectivo" de la organización B
- **WHEN** un usuario de A intenta modificarlo
- **THEN** la respuesta es 404 y el medio de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: Ninguna operación borra un medio
- **GIVEN** el conjunto de comandos y rutas de medios de pago
- **WHEN** se lo enumera
- **THEN** ninguno borra filas y el usuario de aplicación no tiene `DELETE` sobre `medio_pago`
- **Regla:** TR-06; INV-05

#### Scenario: Doble envío de una baja
- **GIVEN** una baja de "Billetera" ya aceptada
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original sin una segunda fila de auditoría
- **Regla:** INV-06

### Requirement: La administración lee todos los medios de pago

El sistema DEBE exponer `GET /configuracion/medios-pago/todos`, con `ADMIN_CONFIGURACION`, que devuelve los medios activos e inactivos de la organización del token, ordenados por nombre, con si piden referencia y si están activos (`design.md` D6). `GET /configuracion/medios-pago` NO DEBE cambiar: solo activos, con cualquier sesión.

#### Scenario: Activos e inactivos
- **GIVEN** A con "Efectivo" activo y "Billetera" de baja, y B con "Cheque"
- **WHEN** un usuario de A con `ADMIN_CONFIGURACION` pide todos los medios
- **THEN** recibe "Billetera" (inactivo) y "Efectivo" (activo), y no "Cheque"
- **Regla:** TR-08; CAT-05

#### Scenario: Sin permiso
- **GIVEN** un usuario con sesión y sin `ADMIN_CONFIGURACION`
- **WHEN** pide todos los medios
- **THEN** la respuesta es 403
- **Regla:** `01` §19

### Requirement: La pantalla de medios de pago

El área "Configuración" de `/admin` DEBE tener la pestaña "Medios de pago", visible solo con `ADMIN_CONFIGURACION`: lista con nombre, "Pide referencia" y estado; alta; edición; baja y reactivación con confirmación; los errores de nombre y de último medio activo se muestran en palabras simples; un reintento usa el mismo `Operation-Id` (`design.md` D2, D4).

#### Scenario: Alta desde la pantalla
- **GIVEN** un usuario con `ADMIN_CONFIGURACION` en "Configuración → Medios de pago"
- **WHEN** agrega "Mercado Pago" con "Pide referencia" marcado
- **THEN** aparece en la lista como activo y con "Pide referencia: Sí"
- **Regla:** TR-09

#### Scenario: Baja con confirmación
- **WHEN** elige "Dar de baja" en "Billetera" y confirma
- **THEN** la lista lo muestra "De baja" con la opción "Reactivar"
- **Regla:** CAT-05

#### Scenario: Último medio activo
- **GIVEN** un solo medio activo
- **WHEN** intenta darlo de baja
- **THEN** la pantalla dice que tiene que quedar al menos un medio de pago activo y el medio sigue activo
- **Regla:** ADR-053

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `ADMIN_CONFIGURACION`
- **WHEN** entra a `/admin`
- **THEN** no ve la sección "Configuración" ni la pestaña
- **Regla:** ADR-027
