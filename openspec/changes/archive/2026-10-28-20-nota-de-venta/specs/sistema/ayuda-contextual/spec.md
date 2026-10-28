## ADDED Requirements

### Requirement: La nota de venta y su configuración explican sus reglas

Los botones de la nota en "Venta registrada" y en el detalle, y la sección "Nota de venta" de la configuración, DEBEN ofrecer ayuda en qué es la nota, en compartir o descargar, en la nota de una venta anulada, en "mostrar saldo" y en los datos de la organización. Los textos DEBEN vivir en el archivo único, citar su regla o ADR, seguir el estilo de ADR-051 y no llevar ejemplos, con los textos que apruebe el usuario (`design.md` D11).

#### Scenario: Qué es la nota
- **WHEN** se abre el "(?)" de la nota de venta
- **THEN** explica que es un comprobante interno, que no es factura y que al reimprimirla sale igual, sin ejemplo
- **Regla:** VTA-13; ADR-008

#### Scenario: Mostrar saldo
- **WHEN** se abre el "(?)" de "mostrar saldo"
- **THEN** explica que la nota muestra el saldo que quedó al registrar la venta y que no se muestra al consumidor final ni en una venta anulada
- **Regla:** VTA-13; CRE-02

#### Scenario: Venta anulada
- **WHEN** se abre el "(?)" de la nota en una venta anulada
- **THEN** explica que la nota sale con la marca de anulada, la fecha y el motivo
- **Regla:** ADR-058; ADR-059

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051
