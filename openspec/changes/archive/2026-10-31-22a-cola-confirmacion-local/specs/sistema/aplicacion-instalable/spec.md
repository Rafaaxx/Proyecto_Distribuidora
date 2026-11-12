## ADDED Requirements

### Requirement: Una versión nueva no se aplica con un carrito abierto

Mientras la pantalla de venta tiene un carrito con alguna línea o una confirmación en curso, el aviso de versión nueva NO DEBE ofrecer "Actualizar" y DEBE decir que se instala al terminar la venta; al confirmar o descartar el carrito, "Actualizar" DEBE volver. Salir de la pantalla de venta con líneas DEBE pedir confirmación (`design.md` D12; `02` §13.5).

#### Scenario: Versión nueva con carrito abierto
- **GIVEN** `vendedor` con un carrito de dos líneas y una versión nueva instalada en segundo plano
- **WHEN** aparece el aviso
- **THEN** dice "Hay una versión nueva: se instala al terminar la venta", sin botón, y la pantalla no se recarga
- **Regla:** `02` §13.5

#### Scenario: Después de confirmar
- **GIVEN** el aviso sin botón por un carrito abierto
- **WHEN** el vendedor confirma la venta
- **THEN** el aviso vuelve a ofrecer "Actualizar"
- **Regla:** `02` §13.5

#### Scenario: Salir con un pedido a medias
- **GIVEN** un carrito con líneas
- **WHEN** el vendedor intenta salir de la pantalla de venta
- **THEN** se pregunta "¿Descartar la venta?" y, si no acepta, el carrito sigue igual
- **Regla:** VTA-07
