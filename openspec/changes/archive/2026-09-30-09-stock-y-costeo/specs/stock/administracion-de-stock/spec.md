## Purpose

Ofrecer en el área `/admin` las pantallas de ubicaciones, stock por ubicación, kardex y stock inicial, mostradas según los permisos efectivos del usuario (ADR-027) y sin lógica de negocio en los componentes.

## ADDED Requirements

### Requirement: Sección Stock según permisos

El área `/admin` DEBE mostrar una sección "Stock" con las pantallas de ubicaciones, stock por ubicación, kardex y stock inicial, cada acción visible solo con su permiso (`design.md` D1-D3, D15) usando `usePermisos()` como única fuente (ADR-027). Ocultar una acción NO DEBE reemplazar la validación del servidor (SEG-06).

#### Scenario: Administrador ve todo

- **GIVEN** un Administrador
- **WHEN** abre `/admin`
- **THEN** ve la sección Stock con ubicaciones, stock, kardex y la acción "Registrar stock inicial"
- **Regla:** ADR-027

#### Scenario: Usuario sin permiso de stock inicial

- **GIVEN** un usuario sin el permiso de D1
- **WHEN** abre la pantalla de stock
- **THEN** no ve la acción "Registrar stock inicial"
- **Regla:** ADR-027; SEG-06

### Requirement: Cantidades en cajas y unidades, costos con decimal exacto

Las pantallas DEBEN mostrar las cantidades en cajas + unidades según CAT-08 y manejar costos solo con `decimal.js` y `lib/money.ts`, sin convertirlos a `number` para calcular (`CLAUDE.md` §4). Los costos DEBEN mostrarse solo con `VER_COSTOS`.

#### Scenario: Stock mostrado en cajas

- **GIVEN** 31 unidades de Vino A (caja x6)
- **WHEN** se muestra el stock
- **THEN** se lee "5 cajas + 1 unidad"
- **Regla:** CAT-08

#### Scenario: Stock negativo mostrado con signo

- **GIVEN** −8 unidades de Vino A (caja x6) llegadas de un change posterior
- **WHEN** se muestra el stock
- **THEN** se lee "−(1 caja + 2 unidades)"
- **Regla:** CAT-08

### Requirement: Formulario de stock inicial

El formulario DEBE permitir elegir la ubicación y cargar varias líneas con producto, cantidad escrita en cajas + unidades (convertida a unidad base con aritmética entera) y costo por unidad base; DEBE generar un `operation_id` nuevo por envío y reutilizarlo en el reintento, avisar que requiere conexión sin encolar, mostrar el mensaje del servidor ante un rechazo y, con `VER_COSTOS`, previsualizar el promedio resultante con la misma función que los fixtures de CST-11 (`design.md` D14).

#### Scenario: Envío aceptado

- **GIVEN** un Administrador en el formulario
- **WHEN** carga 10 cajas de Vino A (caja x6) a `"1000.000000"` y envía
- **THEN** se envía `cantidad_base` 60 y, al aceptarse, vuelve al stock de la ubicación
- **Regla:** CAT-08; STK-01

#### Scenario: Rechazo del servidor

- **GIVEN** un Administrador que envía una corrección mayor que el saldo
- **WHEN** el servidor responde `STOCK_INSUFICIENTE`
- **THEN** la pantalla muestra el mensaje y conserva lo cargado
- **Regla:** TR-10

#### Scenario: Reintento con el mismo `operation_id`

- **GIVEN** un envío que falló por red
- **WHEN** el usuario reintenta sin cambiar nada
- **THEN** se reutiliza el mismo `operation_id`
- **Regla:** TR-07; SYN-02
