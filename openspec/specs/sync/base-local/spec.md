# sync/base-local Specification

## Purpose
Guarda en el teléfono, en la base local (IndexedDB), los datos maestros del bootstrap para que el área de ruta los lea siempre de ahí, con o sin conexión, y define cuándo y cómo se reemplazan sin perder nada que el dispositivo todavía no sincronizó (`02` §13.2, §13.4, ADR-006).

## Requirements

### Requirement: El bootstrap reemplaza los datos maestros en una sola transacción

Aplicar un bootstrap DEBE reemplazar, en una única transacción de la base local, todas las tablas maestras (sesión, configuración, productos, presentaciones, clientes, precios, reglas de descuento, stock, autorizadores y catálogos) por el contenido recibido, y registrar en `meta` la fecha del bootstrap y la jornada. Si algo falla, los datos anteriores DEBEN quedar intactos. El identificador del dispositivo NO DEBE cambiar. Las tablas de operaciones (ventas, cobranzas, movimientos locales y cola, que agrega el change 22a) NO DEBEN tocarse (`design.md` D10).

#### Scenario: Reemplazo completo
- **GIVEN** una base local con el bootstrap de ayer, que incluye un cliente que hoy está inactivo
- **WHEN** se aplica el bootstrap de hoy
- **THEN** el cliente inactivo ya no está, los demás datos son los de hoy y la fecha del bootstrap es la de hoy
- **Regla:** ADR-006; SYN-11

#### Scenario: Falla a mitad del reemplazo
- **GIVEN** una base local con el bootstrap de ayer
- **WHEN** la escritura del bootstrap de hoy falla después de vaciar los productos
- **THEN** la base local conserva completo el bootstrap de ayer
- **Regla:** INV-01; `02` §13.4

#### Scenario: El dispositivo conserva su identificador
- **GIVEN** un dispositivo con su `dispositivo_id` guardado
- **WHEN** se aplica un bootstrap
- **THEN** el `dispositivo_id` es el mismo
- **Regla:** `02` §12.2

#### Scenario: Doble aplicación
- **WHEN** se aplica dos veces seguidas el mismo bootstrap
- **THEN** la base local queda igual que tras la primera, sin filas duplicadas
- **Regla:** ADR-006

### Requirement: El bootstrap se ejecuta al abrir la jornada y a pedido

El dispositivo DEBE pedir y aplicar el bootstrap inmediatamente después de abrir la jornada desde `/ruta`; al iniciar sesión o desbloquear con conexión si la base local no tiene datos de la jornada abierta del usuario en ese dispositivo; y cuando el usuario toca "Actualizar datos" con conexión. Sin conexión, "Actualizar datos" DEBE estar deshabilitado con su motivo. Un bootstrap fallido DEBE mostrarse con la opción de reintentar, sin perder la jornada abierta (`design.md` D11).

#### Scenario: Después de abrir la jornada
- **GIVEN** `vendedor` sin jornada en `/ruta`, con conexión
- **WHEN** abre la jornada sobre "Camioneta 1"
- **THEN** el dispositivo descarga y aplica el bootstrap y el inicio muestra la hora de los datos
- **Regla:** RUT-03

#### Scenario: Jornada abierta desde administración
- **GIVEN** `vendedor` con su jornada abierta desde `/admin` en este teléfono y sin datos locales
- **WHEN** inicia sesión en `/ruta` con conexión
- **THEN** el dispositivo descarga el bootstrap sin pedir otra apertura
- **Regla:** RUT-03; `design.md` D11

#### Scenario: Actualizar sin conexión
- **GIVEN** el teléfono sin señal
- **WHEN** el vendedor mira "Actualizar datos"
- **THEN** está deshabilitado y dice que requiere conexión
- **Regla:** ADR-006

#### Scenario: Bootstrap fallido
- **GIVEN** la jornada recién abierta
- **WHEN** el bootstrap responde con un error del servidor
- **THEN** la jornada sigue abierta, el inicio muestra el error y "Reintentar" vuelve a pedirlo
- **Regla:** RUT-03; INV-01

### Requirement: Las pantallas de ruta leen siempre de la base local

Toda pantalla de `/ruta` que muestra datos de negocio DEBE leerlos de la base local, con o sin conexión, y DEBE mostrar la fecha y hora del último bootstrap. Sin bootstrap aplicado, DEBE indicar que no hay datos y cómo obtenerlos.

#### Scenario: Sin señal
- **GIVEN** un bootstrap aplicado y el teléfono sin señal
- **WHEN** el vendedor abre la lista de clientes
- **THEN** ve los clientes con su saldo del bootstrap y la hora de los datos
- **Regla:** `02` §13.1

#### Scenario: Sin datos
- **GIVEN** una base local sin bootstrap
- **WHEN** el vendedor abre Productos
- **THEN** ve un aviso de que no hay datos y que se descargan al abrir la jornada
- **Regla:** RUT-03
