## MODIFIED Requirements

### Requirement: El PIN de un supervisor se verifica en el teléfono con límite de intentos

En `/ruta`, el PIN de autorización de un supervisor DEBE verificarse en el teléfono contra la derivación del bootstrap, sin señal y sin enviarlo. El permiso del supervisor para lo que autoriza DEBE revisarse antes del PIN. Los fallos DEBEN contarse por usuario del teléfono y supervisor: con `intentos_pin_max` fallos (5 por defecto) ese PIN NO DEBE poder usarse en ese teléfono hasta el próximo bootstrap (abrir la jornada o "Actualizar datos"), no por tiempo: el estado NO DEBE guardar ni comparar horas, de modo que cambiar el reloj del teléfono no lo levante; un intento durante el bloqueo no verifica ni cuenta y un acierto no reinicia la cuenta; cualquier bootstrap nuevo DEBE levantar el bloqueo y reiniciar a cero las cuentas de todos los pares. El límite DEBE valer para todo el teléfono, aunque los intentos se hagan a la vez desde varias pestañas: ningún fallo DEBE perderse, y una verificación que termina cuando el PIN ya quedó bloqueado DEBE responder «bloqueado» aunque el PIN sea correcto. El PIN NO DEBE guardarse en la base local ni viajar en el comando; la venta lleva solo el autorizador (`design.md` D10 del 22a; `design.md` D9 del 22b; `02` §12.4).

#### Scenario: PIN correcto sin señal
- **GIVEN** `vendedor` sin señal, con una venta que necesita autorización de descuento, y `sup01` con `AUTORIZAR_DESCUENTO` y PIN en el bootstrap
- **WHEN** `sup01` escribe su PIN en el teléfono
- **THEN** la venta se confirma con `sup01` como autorizador y el comando no lleva el PIN
- **Regla:** SEG-05; DSC-06; ADR-055

#### Scenario: PIN incorrecto
- **WHEN** `sup01` escribe un PIN equivocado
- **THEN** la venta no se confirma, se informa "PIN incorrecto" y la cuenta de fallos de ese supervisor en el teléfono sube en uno
- **Regla:** SEG-05

#### Scenario: Bloqueo por intentos
- **GIVEN** `intentos_pin_max` = 5 y cuatro fallos con el PIN de `sup01` en el teléfono
- **WHEN** falla una quinta vez
- **THEN** el PIN de `sup01` queda bloqueado en el teléfono hasta el próximo bootstrap; un intento con el PIN correcto durante el bloqueo no se verifica ni cuenta y la venta no se confirma
- **Regla:** SEG-05; `02` §12.4

#### Scenario: El reloj no levanta el bloqueo
- **GIVEN** el PIN de `sup01` bloqueado en el teléfono
- **WHEN** el reloj del teléfono se adelanta horas o días
- **THEN** el PIN correcto sigue sin verificarse y la venta no se confirma
- **Regla:** SEG-05; `02` §12.4

#### Scenario: El bootstrap levanta el bloqueo
- **GIVEN** el PIN de `sup01` bloqueado en el teléfono
- **WHEN** se abre la jornada o se usa "Actualizar datos" y el bootstrap termina
- **THEN** el PIN correcto de `sup01` vuelve a autorizar y la cuenta de fallos queda en cero
- **Regla:** SEG-05

#### Scenario: Cualquier bootstrap reinicia la cuenta
- **GIVEN** cuatro fallos contados contra `sup01`
- **WHEN** un bootstrap termina, traiga o no otra derivación del PIN de `sup01`
- **THEN** la cuenta de fallos de `sup01` vuelve a cero
- **Regla:** ADR-055

#### Scenario: Supervisor sin el permiso
- **GIVEN** una venta que necesita autorización de crédito y un supervisor sin `SUPERAR_CREDITO`
- **WHEN** se buscan autorizadores
- **THEN** ese supervisor no se ofrece y no se cuenta ningún fallo
- **Regla:** CRE-06; DSC-06

#### Scenario: Intentos simultáneos desde dos pestañas
- **GIVEN** `intentos_pin_max` = 5, dos pestañas de `/ruta` abiertas en el mismo teléfono y ningún fallo contado contra `sup01`
- **WHEN** se escriben a la vez tres PIN equivocados de `sup01` en cada pestaña
- **THEN** se cuentan exactamente 5 fallos, a lo sumo 5 intentos responden «PIN incorrecto» y el resto responde que el PIN está bloqueado
- **Regla:** SEG-05; `02` §12.4

#### Scenario: El bloqueo llega mientras otra pestaña verifica
- **GIVEN** cuatro fallos contados contra `sup01` y dos pestañas
- **WHEN** una pestaña falla por quinta vez mientras la otra verifica el PIN correcto
- **THEN** la segunda responde que el PIN está bloqueado y la venta no se confirma
- **Regla:** SEG-05

#### Scenario: Dos supervisores a la vez
- **GIVEN** dos pestañas
- **WHEN** en una se verifica el PIN de `sup01` y en la otra el de otro supervisor
- **THEN** cada verificación cuenta solo contra su supervisor y ninguna espera a la otra
- **Regla:** SEG-05
