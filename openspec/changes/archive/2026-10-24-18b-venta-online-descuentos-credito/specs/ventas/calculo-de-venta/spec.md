## ADDED Requirements

### Requirement: El motor de venta recibe el descuento manual general y el propio de cada línea

El motor de venta DEBE recibir, además de las reglas, el porcentaje manual general de la venta y el propio de cada línea, y DEBE devolver por línea los descuentos con su origen y el mayor porcentaje manual aplicado, en el servidor y en el dispositivo. Los casos compartidos de totales DEBEN incluir ventas con descuento manual general, con propio y con los dos, escritos antes que el código.

#### Scenario: Automático y manual general en la misma línea

- **GIVEN** 15 botellas de Vino A con bruto $31.250,00, una regla de 5 % y un general de 5 %
- **WHEN** se calcula la venta
- **THEN** la línea lleva $1.562,50 automático y $1.484,38 manual, con neto $28.203,12 y total $28.203,12 en modo A
- **Regla:** DSC-05; DSC-07; VTA-04; INV-14

#### Scenario: Los casos de descuento manual corren en las dos suites

- **WHEN** corren los casos compartidos de totales
- **THEN** Python y TypeScript dan los mismos descuentos, netos, totales y porcentaje manual máximo
- **Regla:** ADR-016; DSC-05
