# descuentos/administracion-de-descuentos Specification

## Purpose

Dar a quien administra la política comercial las pantallas de `/admin` para cargar, revisar, activar y pausar reglas de descuento y para definir el tope de descuento manual de cada rol, sin lógica de negocio en los componentes (DSC-01, DSC-02, DSC-06; `01` §18, §19; ADR-027).

## Requirements

### Requirement: El área de descuentos se decide con los permisos de la sesión

`/admin` DEBE ofrecer la sección "Descuentos" con las reglas a quien tenga `GESTIONAR_DESCUENTOS`, y dentro de ella "Topes por rol" a quien tenga `ADMIN_USUARIOS`, con `usePermisos()` como única fuente (ADR-027). Ocultar una acción NO DEBE reemplazar la validación del servidor (SEG-06).

#### Scenario: Administrador

- **GIVEN** un Administrador (`GESTIONAR_DESCUENTOS` y `ADMIN_USUARIOS`)
- **WHEN** abre `/admin`
- **THEN** ve "Descuentos" con "Reglas" y "Topes por rol"
- **Regla:** ADR-027; `01` §19

#### Scenario: Usuario sin permisos de descuentos

- **GIVEN** un usuario del rol Administración
- **WHEN** abre `/admin`
- **THEN** no ve "Descuentos", y la ruta directa muestra el aviso de falta de permiso sin pedir datos
- **Regla:** ADR-027; SEG-06

#### Scenario: Rol a medida con solo las reglas

- **GIVEN** un rol a medida con `GESTIONAR_DESCUENTOS` y sin `ADMIN_USUARIOS`
- **WHEN** abre "Descuentos"
- **THEN** ve "Reglas" y no ve "Topes por rol"
- **Regla:** ADR-027; `01` §19

### Requirement: Las reglas se cargan y se revisan desde la pantalla

La pantalla DEBE listar las reglas con una descripción legible de cada una (condición, acción, alcance, prioridad, si es acumulable, vigencia y estado, incluido `VENCIDA`) y DEBE permitir crear una regla y editarla mientras es borrador. El formulario DEBE ofrecer solo los tipos, medidas, operadores y acciones de la etapa 1, pedir los alcances solo cuando la regla es de alcance, y adaptar el umbral y el valor a la medida y a la acción elegidas. La persona escribe el porcentaje como porcentaje (`5`, `12,5`) y el comando lleva la fracción como cadena (`0.050000`); ningún importe ni porcentaje se convierte a número para calcular (INV-03). Los errores del servidor DEBEN mostrarse junto al campo que corresponde y conservar lo cargado.

#### Scenario: Descripción legible de una regla

- **GIVEN** una regla `VOLUMEN_OPERACION` con cajas equivalentes, `GTE`, umbral 20 y porcentaje `0.050000`
- **WHEN** el Administrador abre el listado
- **THEN** ve "Cajas equivalentes ≥ 20 → 5 %" con su prioridad, su estado y "No acumulable"
- **Regla:** DSC-01; DSC-03 (ejemplo de `01` §10)

#### Scenario: El porcentaje se escribe como porcentaje

- **GIVEN** el formulario de una regla con acción porcentaje
- **WHEN** el Administrador escribe `12,5` y guarda
- **THEN** el comando lleva `"0.125000"`
- **Regla:** TR-02; INV-03; `02` §10.2

#### Scenario: Los alcances se piden solo en reglas de alcance

- **GIVEN** el formulario de una regla
- **WHEN** el Administrador elige "Sobre toda la venta"
- **THEN** no se ofrece elegir productos, categorías ni marcas
- **AND** al elegir "Sobre productos, categorías o marcas" se exige al menos uno
- **Regla:** DSC-02; `03` §11

#### Scenario: Umbral según la medida

- **GIVEN** el formulario con la medida "Unidades base"
- **WHEN** el Administrador escribe un umbral con decimales
- **THEN** el formulario lo señala antes de enviar
- **Regla:** DSC-03; INV-04

#### Scenario: Error del servidor junto al campo

- **GIVEN** un formulario enviado con una vigencia hasta anterior a la desde
- **WHEN** el servidor responde `VIGENCIA_INVALIDA`
- **THEN** el mensaje aparece junto a la vigencia y lo cargado se conserva
- **Regla:** DSC-01; TR-10

#### Scenario: Reintento seguro

- **GIVEN** un alta de regla cuya respuesta se perdió por un error de red
- **WHEN** el Administrador reintenta sin cambiar nada
- **THEN** se envía el mismo `operation_id` y queda una sola regla
- **Regla:** SYN-02; INV-06

#### Scenario: Sin conexión

- **GIVEN** el navegador sin conexión
- **WHEN** el Administrador intenta guardar una regla
- **THEN** ve el aviso de que la operación requiere conexión y no se envía nada
- **Regla:** `02` §6.5

### Requirement: Activar y pausar se confirman desde la pantalla

El detalle de una regla DEBE ofrecer "Activar" sobre un borrador o una regla pausada y "Pausar" sobre una activa, cada una con confirmación. Una regla ya activada DEBE mostrarse en solo lectura, con la única edición de su vigencia hasta. La pantalla DEBE avisar, al activar, que la regla ya no se podrá editar.

#### Scenario: Activar con confirmación

- **GIVEN** una regla en borrador
- **WHEN** el Administrador elige "Activar" y confirma
- **THEN** la regla pasa a "Activa" y deja de ofrecer "Editar"
- **Regla:** `01` §18; `design.md` D15

#### Scenario: Pausar una regla activa

- **GIVEN** una regla activa
- **WHEN** el Administrador elige "Pausar" y confirma
- **THEN** la regla pasa a "Pausada" y ofrece "Activar"
- **Regla:** `01` §18

#### Scenario: Una regla activada es de solo lectura

- **GIVEN** una regla activa o pausada
- **WHEN** el Administrador abre su detalle
- **THEN** ve sus datos sin poder editarlos, salvo "Poner fin" para fijar su vigencia hasta
- **Regla:** TR-06; `design.md` D15, D16

#### Scenario: Estado cambiado por otra persona

- **GIVEN** una regla que otra persona pausó mientras la pantalla estaba abierta
- **WHEN** el Administrador elige "Pausar"
- **THEN** ve el mensaje de `REGLA_ESTADO_INVALIDO` y la pantalla muestra el estado actual
- **Regla:** `01` §18

### Requirement: El tope de descuento manual de cada rol se define desde la pantalla

"Topes por rol" DEBE listar los roles de la organización con su tope de descuento manual como porcentaje y permitir cambiarlo, con confirmación, a quien tenga `ADMIN_USUARIOS`. DEBE mostrar "Sin tope" cuando el tope es 100 % y avisar que un rol con tope 0 % necesita autorización para cualquier descuento manual (DSC-06).

#### Scenario: Definir el tope del Vendedor

- **GIVEN** el rol "Vendedor/Repartidor" con tope 0 %
- **WHEN** el Administrador escribe `5` y confirma
- **THEN** el comando lleva `"0.050000"` y el listado muestra 5 %
- **Regla:** DSC-06; `01` §19; TR-02

#### Scenario: Tope fuera de rango

- **GIVEN** el formulario de tope
- **WHEN** el Administrador escribe `120` o un valor negativo
- **THEN** el formulario lo señala y no envía nada
- **Regla:** TR-02; `01` §19

#### Scenario: Aviso de tope cero

- **GIVEN** un rol con `DESCUENTO_MANUAL` y tope 0 %
- **WHEN** el Administrador abre "Topes por rol"
- **THEN** ve el aviso de que ese rol necesita autorización para cualquier descuento manual
- **Regla:** DSC-06
