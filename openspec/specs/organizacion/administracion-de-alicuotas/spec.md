# organizacion/administracion-de-alicuotas Specification

## Purpose
Permite que la organización administre sus alícuotas de IVA (alta, cambio de nombre, baja y reactivación) desde `/admin`, por el bus de comandos, sin cambiar el porcentaje de una alícuota existente y sin dejar un producto activo con una alícuota de baja (TR-09, CAT-01, CAT-05, ADR-061).

## Requirements

### Requirement: Una alícuota se crea por comando

El sistema DEBE crear una alícuota solo mediante `ALICUOTA_CREAR` v1 (`ONLINE`, `ADMIN_CONFIGURACION`), con nombre y valor. El nombre DEBE guardarse recortado (vacío → `NOMBRE_INVALIDO`, 422). El valor DEBE llegar como string decimal y ser una fracción mayor o igual que cero y menor que uno con hasta 6 decimales (`CONFIGURACION_VALOR_ALICUOTA_INVALIDO`, 422). El nombre (sin distinguir mayúsculas) y el valor DEBEN ser únicos en la organización, entre activas e inactivas (`NOMBRE_DUPLICADO`, `VALOR_DUPLICADO`, 409). La alícuota DEBE nacer activa (`design.md` D6, D7).

#### Scenario: Alta de una alícuota
- **GIVEN** la organización A con 21 %, 10,5 % y 0 % (`01` §4)
- **WHEN** un administrador crea "27%" con valor `"0.270000"`
- **THEN** se crea activa y se ofrece al crear productos de A
- **Regla:** TR-09; TR-02

#### Scenario: Valor repetido
- **WHEN** se crea "IVA general" con valor `"0.210000"`
- **THEN** se rechaza con `VALOR_DUPLICADO` y no se crea nada
- **Regla:** `design.md` D7; IMP-04

#### Scenario: Valor fuera de rango o con más decimales
- **WHEN** se crea una alícuota con valor `"1.000000"`, `"-0.010000"` o `"0.2100001"`
- **THEN** se rechaza con `CONFIGURACION_VALOR_ALICUOTA_INVALIDO` (422)
- **Regla:** TR-02; INV-03

#### Scenario: Valor como número de punto flotante
- **WHEN** el contenido trae el valor como número JSON en lugar de string
- **THEN** se rechaza por contenido inválido y no se crea nada
- **Regla:** INV-03

#### Scenario: Sin permiso y doble envío
- **WHEN** un usuario sin `ADMIN_CONFIGURACION` envía `ALICUOTA_CREAR`, o un administrador lo envía dos veces con el mismo `operation_id`
- **THEN** el primero recibe `PERMISO_REQUERIDO`; el segundo deja una sola alícuota
- **Regla:** SEG-06; INV-06

### Requirement: Una alícuota se renombra, se da de baja y se reactiva sin cambiar su valor

El sistema DEBE modificar una alícuota solo mediante `ALICUOTA_MODIFICAR` v1 (`ONLINE`, `ADMIN_CONFIGURACION`), con reemplazo completo de nombre y estado activo. El valor NO DEBE cambiar: un valor distinto del guardado DEBE rechazarse con `VALOR_NO_MODIFICABLE` (422). La baja DEBE rechazarse con `ALICUOTA_EN_USO` (409, con la cantidad de productos) si algún producto activo de la organización la usa, y con `ULTIMA_ALICUOTA_ACTIVA` (409) si es la última activa. Los productos inactivos NO DEBEN impedir la baja. Las compras y ventas confirmadas NO DEBEN cambiar. Ajena o inexistente → 404. Ningún comando DEBE borrar una alícuota (`design.md` D6, D8).

#### Scenario: Renombrar
- **WHEN** "10,5%" pasa a llamarse "IVA reducido 10,5%"
- **THEN** los productos que la usan la muestran con el nombre nuevo y su valor sigue `"0.105000"`
- **Regla:** `design.md` D6

#### Scenario: El valor no se cambia
- **WHEN** `ALICUOTA_MODIFICAR` de "21%" trae valor `"0.270000"`
- **THEN** se rechaza con `VALOR_NO_MODIFICABLE` y nada cambia
- **Regla:** `design.md` D6; INV-01

#### Scenario: En uso por un producto activo
- **GIVEN** un producto activo con la alícuota 21 %
- **WHEN** se da de baja 21 %
- **THEN** se rechaza con `ALICUOTA_EN_USO` indicando un producto, y la alícuota sigue activa
- **Regla:** `design.md` D8; CAT-01

#### Scenario: Solo la usan productos inactivos
- **GIVEN** 0 % solo la usa un producto inactivo
- **WHEN** se da de baja 0 %
- **THEN** se acepta; deja de ofrecerse al crear o editar productos y sigue legible por id
- **Regla:** CAT-05; TR-06

#### Scenario: Última activa
- **GIVEN** una organización con una sola alícuota activa sin productos activos que la usen
- **WHEN** se la da de baja
- **THEN** se rechaza con `ULTIMA_ALICUOTA_ACTIVA`
- **Regla:** `design.md` D8

#### Scenario: La historia no cambia
- **GIVEN** una compra confirmada con `alicuota_aplicada = 0.210000`
- **WHEN** la alícuota 21 % se renombra y, ya sin productos activos que la usen, se da de baja
- **THEN** la compra conserva su alícuota aplicada
- **Regla:** TR-06; VTA-03

#### Scenario: Otra organización y auditoría
- **WHEN** un administrador de B modifica una alícuota de A; luego un administrador de A la renombra
- **THEN** el primero responde 404; el segundo deja una fila de auditoría de `alicuota_iva` con `antes` y `despues`
- **Regla:** INV-21; AUD-01

### Requirement: La baja de una alícuota no se cruza con el alta de un producto

La baja de una alícuota y el alta o modificación de un producto que la elige DEBEN serializarse: ningún producto activo DEBE quedar con una alícuota inactiva, y dos bajas simultáneas NO DEBEN dejar la organización sin alícuotas activas (`design.md` D8, D9).

#### Scenario: Baja y alta de producto simultáneas
- **GIVEN** la alícuota 10,5 % sin productos activos
- **WHEN** al mismo tiempo, con commits reales, se da de baja 10,5 % y se crea un producto con 10,5 %
- **THEN** o el producto se crea y la baja responde `ALICUOTA_EN_USO`, o la baja se acepta y el producto responde `ALICUOTA_INACTIVA`
- **Regla:** CAT-01; CAT-05; INV-01

#### Scenario: Bajas simultáneas de las dos últimas
- **GIVEN** dos alícuotas activas sin productos activos
- **WHEN** se dan de baja las dos al mismo tiempo
- **THEN** una se acepta y la otra responde `ULTIMA_ALICUOTA_ACTIVA`
- **Regla:** `design.md` D8

### Requirement: La pantalla de alícuotas de IVA

`/admin` DEBE ofrecer, con `ADMIN_CONFIGURACION`, la pestaña "Alícuotas de IVA" en Configuración, con la lista (nombre, porcentaje y estado), el alta pidiendo el porcentaje (que la pantalla convierte a fracción sin redondear), el cambio de nombre y la baja y reactivación con confirmación. La lectura `GET /configuracion/alicuotas` DEBE admitir también `ADMIN_CONFIGURACION`. Los errores DEBEN explicarse en palabras simples; `ALICUOTA_EN_USO` con la cantidad de productos (`design.md` D12).

#### Scenario: Alta con porcentaje
- **WHEN** un administrador carga "10,5" como porcentaje con un nombre nuevo pero el valor ya existe
- **THEN** el comando viaja con `"0.105000"` y la pantalla explica que ya hay una alícuota con ese porcentaje
- **Regla:** TR-02; `design.md` D7

#### Scenario: Más de cuatro decimales en el porcentaje
- **WHEN** se carga "10,12345"
- **THEN** el formulario lo marca inválido y no envía el comando
- **Regla:** TR-02; TR-10

#### Scenario: En uso explicado
- **WHEN** la baja responde `ALICUOTA_EN_USO` con 12 productos
- **THEN** la pantalla dice que 12 productos activos la usan y que primero hay que pasarlos a otra alícuota
- **Regla:** `design.md` D8
