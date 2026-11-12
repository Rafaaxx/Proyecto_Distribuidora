## Purpose

Demostrar automáticamente que la etapa 1 funciona de punta a punta: una suite de Playwright recorre los criterios de éxito de `00` §9 contra el sistema compilado como en producción, en una vista de PC y una de teléfono, incluido el corte de red (`02` §15, `04` §12).

## Requirements

### Requirement: La suite corre contra un entorno igual al de producción y desechable

La suite de aceptación DEBE correr contra el compose de producción levantado como un proyecto aparte, con una base nueva, HTTPS con la autoridad propia de Caddy y la compilación de producción del frontend (con su service worker). Antes de la suite, una siembra del escenario de aceptación DEBE dejar la organización, sus roles y los usuarios con los mismos nombres que se usan en desarrollo (`admin`, `ges01`, `sup01`, `vendedor`, `vendedor2`, entre otros), las ubicaciones y la configuración que la demostración necesita, y una segunda organización para el control de aislamiento. Al terminar, el entorno DEBE poder descartarse con sus datos sin tocar el de desarrollo ni el de producción (`02` §15, §16.1; `design.md` D13, D14).

#### Scenario: La siembra del escenario es repetible
- **GIVEN** una base nueva migrada
- **WHEN** se ejecuta la siembra del escenario de aceptación dos veces
- **THEN** la segunda no crea nada nuevo ni falla
- **Regla:** `02` §16.1 (datos de ejemplo cargables con un comando, con el escenario de la demo)

#### Scenario: El entorno de aceptación no toca otros datos
- **GIVEN** el entorno de desarrollo con sus datos
- **WHEN** se levanta, se usa y se descarta el entorno de aceptación
- **THEN** los datos de desarrollo siguen iguales
- **Regla:** `design.md` D13

### Requirement: Cada criterio de éxito de la etapa 1 tiene su prueba

La suite DEBE automatizar los criterios 1 a 11 de `00` §9 en el orden de la demostración, cada prueba nombrando su criterio. Los criterios 4 a 8 y la parte de ruta del 9 y del 10 DEBEN correr en una vista de teléfono, y el tramo 5 a 8 en un único teléfono continuo sin señal (la jornada es por usuario y dispositivo, ADR-005; un teléfono con conexión envía lo pendiente al arrancar); Playwright necesita `--ignore-certificate-errors` para registrar el service worker con el certificado interno de Caddy; los de administración, en una vista de PC. El criterio 12 DEBE quedar cubierto por las pruebas automáticas de restauración del change 27b. Una verificación DEBE fallar si alguno de los 12 criterios no tiene una prueba que lo nombre (`00` §9; `02` §15; `design.md` D14, D15).

#### Scenario: Criterio 1 — importación y saldos iniciales
- **GIVEN** las planillas de ejemplo de productos, clientes, proveedores, stock inicial y saldos iniciales
- **WHEN** `admin` las importa desde `/admin` (importar es de la plantilla `Administrador`, `01` §19: `IMPORTAR_DATOS`)
- **THEN** los maestros, el stock y los saldos quedan cargados y se ven en sus pantallas
- **Regla:** `00` §9 criterio 1

#### Scenario: Criterio 2 — compra a crédito con presentaciones y costos distintos
- **GIVEN** un proveedor, vino que se compra por caja y cerveza por unidad
- **WHEN** se registra una compra a crédito con costos distintos
- **THEN** el stock, el costo promedio y la deuda con el proveedor coinciden con los valores esperados de la prueba
- **Regla:** `00` §9 criterio 2; CST-11; INV-12; INV-13

#### Scenario: Criterio 3 — nueva versión de lista sin alterar ventas anteriores
- **GIVEN** una venta confirmada con la versión vigente de la lista
- **WHEN** se carga un costo nuevo y `admin` publica una versión nueva con margen y redondeo (`PUBLICAR_LISTAS` es de `Administrador`, `01` §19)
- **THEN** la venta anterior conserva su precio
- **Regla:** `00` §9 criterio 3; INV-10; INV-11

#### Scenario: Criterio 4 — transferencia al vehículo y apertura de jornada
- **GIVEN** el stock en el depósito (la prueba del criterio 4 carga todo el que usa el criterio 5: con la jornada abierta no se transfiere más al vehículo, STK-09)
- **WHEN** se transfiere mercadería al vehículo y `vendedor` toma la ubicación y abre la jornada en el teléfono
- **THEN** la jornada queda abierta y el stock del vehículo es el transferido
- **Regla:** `00` §9 criterio 4; INV-15; INV-16

#### Scenario: Criterio 5 — venta sin conexión con descuentos y cobro parcial
- **GIVEN** el teléfono con la red cortada y un cliente con saldo previo
- **WHEN** `vendedor` arma un pedido de cajas y unidades sueltas, se aplica una regla de volumen y un descuento manual permitido, y cobra una parte con efectivo y transferencia
- **THEN** la venta queda confirmada en el teléfono con el resto en cuenta corriente
- **Regla:** `00` §9 criterio 5; INV-08; INV-17

#### Scenario: Criterio 6 — exceso de crédito sin conexión
- **GIVEN** el teléfono sin conexión y un cliente sin crédito disponible suficiente
- **WHEN** se confirma una segunda venta que lo supera
- **THEN** se resuelve según la política configurada del cliente y no se rechaza por reglas de negocio
- **Regla:** `00` §9 criterio 6; INV-17

#### Scenario: Criterio 7 — nota de venta sin señal
- **GIVEN** el teléfono sin conexión y la venta del criterio 5
- **WHEN** se genera la nota de venta y se elige compartir
- **THEN** se genera el PDF y se invoca la hoja de compartir del sistema con ese archivo, sin red
- **Regla:** `00` §9 criterio 7

#### Scenario: Criterio 8 — doble sincronización deliberada
- **GIVEN** las ventas sin conexión de los criterios 5 y 6
- **WHEN** vuelve la red y el lote se envía dos veces
- **THEN** existe una sola venta por operación, con stock, saldo, costo y utilidad correctos
- **Regla:** `00` §9 criterio 8; INV-06

#### Scenario: Criterio 9 — anulación sin borrar historia
- **GIVEN** una venta confirmada
- **WHEN** un supervisor (`sup01`) la anula desde `/admin` (`Vendedor` no tiene `ANULAR_VENTA`, y anular exige `LIBERAR_UBICACION` por VTA-21)
- **THEN** el stock y el saldo vuelven a su estado anterior y la venta sigue visible como anulada
- **Regla:** `00` §9 criterio 9; INV-05; INV-19

#### Scenario: Criterio 10 — rendición con diferencia auditada
- **GIVEN** la jornada con ventas y un conteo del vehículo con una diferencia
- **WHEN** se rinde la jornada
- **THEN** la diferencia queda registrada como ajuste auditado y el stock esperado coincide con el resto del conteo
- **Regla:** `00` §9 criterio 10

#### Scenario: Criterio 11 — el reporte concilia
- **GIVEN** las operaciones registradas en la suite
- **WHEN** se abre el reporte de ventas del período
- **THEN** sus totales coinciden con los de las ventas no anuladas de la suite
- **Regla:** `00` §9 criterio 11; REP-02

#### Scenario: Un criterio sin prueba hace fallar la verificación
- **GIVEN** la lista de los 12 criterios de `00` §9 y las pruebas que los nombran
- **WHEN** falta la prueba de uno
- **THEN** la verificación de cobertura falla nombrando el criterio
- **Regla:** `02` §15 (punta a punta: criterios de `00` §9)

### Requirement: Aislamiento y permisos durante la demostración

La suite DEBE comprobar en el navegador que un usuario de la segunda organización no ve los datos de la demostración y que un vendedor no puede abrir pantallas ni ejecutar desde la API una acción que su rol no permite (`00` §9, párrafo final; INV-21; SEG-06).

#### Scenario: Usuario de otra organización
- **GIVEN** la demostración cargada en la organización inicial
- **WHEN** el administrador de la segunda organización abre la lista de clientes y pide por la API un cliente de la primera
- **THEN** la lista no muestra clientes de la primera y la API responde 404
- **Regla:** INV-21; SEG-07

#### Scenario: Acción no permitida
- **GIVEN** `vendedor` con sesión iniciada
- **WHEN** intenta por la API anular una compra
- **THEN** la API responde 403 y nada cambia
- **Nota:** la suite automática cubre solo la API (403); la parte de pantallas (que `vendedor` no vea ni abra las pantallas de administración) queda como paso manual nombrado en la tarea 9.1
- **Regla:** SEG-06; ADR-056

### Requirement: La suite no tolera errores de seguridad del navegador

Toda prueba de la suite DEBE fallar si el navegador informa una violación de la política de seguridad de contenido o un error no manejado de la página (`02` §18; `design.md` D9).

#### Scenario: Violación de CSP
- **GIVEN** una pantalla que intenta cargar un recurso que la política no permite
- **WHEN** corre su prueba
- **THEN** la prueba falla nombrando la directiva violada
- **Regla:** `02` §18 (política CSP restrictiva)
