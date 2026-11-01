## MODIFIED Requirements

### Requirement: Una versión nueva no se aplica con un carrito abierto

Mientras la pantalla de venta tiene un carrito con alguna línea o una confirmación en curso, el aviso de versión nueva NO DEBE ofrecer "Actualizar" y DEBE decir que se instala al terminar la venta; al confirmar o descartar el carrito, "Actualizar" DEBE volver. Salir de la pantalla de venta con líneas DEBE pedir confirmación por cualquier camino de la aplicación: el menú inferior, «Cancelar», un enlace del cuerpo de la pantalla, el botón atrás del navegador o del teléfono. Recargar o cerrar la pestaña con líneas DEBE pedir el aviso del navegador. Ir a «Venta guardada» al confirmar NO DEBE pedir confirmación (`design.md` D12 del 22a; `design.md` D10 del 22b; `02` §13.5).

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

#### Scenario: Botón atrás con un pedido a medias
- **GIVEN** un carrito con líneas
- **WHEN** el vendedor toca el botón atrás del navegador o del teléfono
- **THEN** se pregunta "¿Descartar la venta?"; si no acepta, sigue en la venta con el carrito igual y, si acepta, vuelve a la pantalla anterior sin el carrito
- **Regla:** VTA-07; `02` §13.5

#### Scenario: Enlace del cuerpo con un pedido a medias
- **GIVEN** un carrito con líneas
- **WHEN** el vendedor toca un enlace dentro de la pantalla de venta, como «Ver más» de una ayuda
- **THEN** se pregunta "¿Descartar la venta?" antes de salir
- **Regla:** VTA-07

#### Scenario: Recargar con un pedido a medias
- **GIVEN** un carrito con líneas
- **WHEN** el vendedor recarga la página
- **THEN** el navegador pide confirmar antes de salir
- **Regla:** VTA-07

#### Scenario: Confirmar no pregunta
- **GIVEN** un carrito con líneas
- **WHEN** el vendedor confirma la venta
- **THEN** pasa a «Venta guardada» sin que se pregunte "¿Descartar la venta?"
- **Regla:** VTA-07
