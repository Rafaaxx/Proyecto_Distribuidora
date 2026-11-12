## ADDED Requirements

### Requirement: Las pantallas de venta, configuración y PIN explican descuentos, crédito y autorización

Las pantallas de venta, de configuración del descuento manual y del crédito, del PIN de autorización y "Mi PIN" DEBEN traer su ayuda contextual: descuento general, descuento propio, tope, autorización, motivo, descuentos automáticos, crédito del cliente, política de crédito, configuración del descuento manual, configuración del crédito, PIN de autorización y Mi PIN, más una página "Ver más" sobre el crédito de los clientes. Cada texto DEBE citar su regla y los que citan DSC-06 o ADR-050 DEBEN revisarse contra lo que la venta muestra.

#### Scenario: El tope en la venta

- **GIVEN** la pantalla "Nueva venta"
- **WHEN** el usuario abre el "(?)" del tope
- **THEN** ve el texto aprobado con su ejemplo y la cita DSC-06, y "Ver más" lleva al tema de topes
- **Regla:** DSC-06; ADR-051

#### Scenario: El tema del crédito

- **WHEN** se abre "Ver más" del crédito
- **THEN** explica disponible, consumo, las tres políticas, la tolerancia sin señal y lo que queda guardado, citando CRE-01 a CRE-10
- **Regla:** CRE-01; CRE-10; ADR-051

#### Scenario: Toda clave usada existe y cita reglas existentes

- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva existe en el archivo de textos y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051

#### Scenario: Mi PIN

- **GIVEN** la pantalla "Mi PIN" de un supervisor
- **WHEN** abre el "(?)"
- **THEN** ve el texto aprobado de `cuenta.miPin` con su ejemplo y las citas SEG-05, ADR-011 y ADR-019
- **Regla:** SEG-05; ADR-051
