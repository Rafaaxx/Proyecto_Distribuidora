## Purpose

Definir las lecturas de ventas y de apoyo a la venta y las pantallas de `/admin` con las que se arma, confirma y consulta una venta (VTA-01 a VTA-12, `01` §19). Escrita con las opciones recomendadas (A) de `design.md` D4, D19 y D21, pendientes de aprobación.

## Requirements

### Requirement: Las ventas se consultan por organización

`GET /api/v1/ventas` (filtros de cliente, usuario, jornada, ubicación y fechas de negocio, con cursor y límite) y `GET /api/v1/ventas/{id}` (líneas en su presentación, totales, cobranza, observaciones) DEBEN exigir `VENDER` o `ANULAR_VENTA` y alcanzar a todas las ventas de la organización. Los costos de cada línea DEBEN viajar solo con `VER_COSTOS` (nulos sin él). Importes como string. Una venta de otra organización responde 404.

#### Scenario: Listado con filtros
- **GIVEN** tres ventas de Juan y una de Ana
- **WHEN** un Supervisor lista con el filtro de usuario Juan
- **THEN** recibe las tres ventas de Juan, más recientes primero, con número, cliente, total y estado
- **Regla:** `01` §19; TR-04

#### Scenario: Detalle sin costos
- **WHEN** un Vendedor abre el detalle de una venta
- **THEN** ve líneas, totales y cobranza, y `costo_unitario` y `costo_total` en nulo
- **Regla:** `01` §19; VER_COSTOS

#### Scenario: Detalle con costos
- **WHEN** un Administrador abre el mismo detalle
- **THEN** ve `"1050.000000"` y `"75600.00"` en la línea del ejemplo de CST-11
- **Regla:** VTA-05; `01` §19

#### Scenario: Sin permiso y ajena
- **WHEN** un usuario de Consulta lista ventas, y un Supervisor pide una venta de otra organización
- **THEN** el primero recibe 403 y el segundo 404
- **Regla:** SEG-06; INV-21

### Requirement: Quien vende lee precios, clientes, stock y numeración sin administrar

Con `VENDER`, solo en lectura, DEBEN abrirse: `GET /api/v1/ventas/precios` (una página de productos activos, buscable por nombre o código con `q`, con `producto_id`, `cursor` y `limite`, con precio de la versión aplicable, con sus presentaciones de venta y, con `ubicacion_id`, el stock de la ubicación; sin costos; los productos sin precio marcados; sin `USAR_LISTA_ANTERIOR` solo la versión vigente de la lista que la venta usaría por defecto para el cliente, y otra lista u otra versión es 403 `PERMISO_REQUERIDO`), `GET /api/v1/ventas/numeracion` (prefijo y último correlativo del dispositivo de la sesión), `GET /clientes/opciones`, `GET /clientes/{id}/saldo`, `GET /precios/listas/opciones` y las ubicaciones activas. `GET /api/v1/ventas/versiones?lista_id=` (versiones elegibles) DEBE exigir `USAR_LISTA_ANTERIOR` (`design.md` D6, D19).

#### Scenario: Precios para vender
- **GIVEN** un Vendedor sin `GESTIONAR_LISTAS`
- **WHEN** pide los precios para Kiosco La Esquina en "Depósito central"
- **THEN** recibe Vino A a `"12500.00"` con unidades de referencia 6, presentaciones "Botella" y "Caja x6", stock 48, sin costo de referencia ni margen
- **Regla:** PRC-20; PRC-22; `01` §19

#### Scenario: Precios sin permiso de lista anterior
- **GIVEN** un Vendedor sin `USAR_LISTA_ANTERIOR` y un cliente con lista Mayorista (versión 2 vigente)
- **WHEN** pide los precios del cliente sin lista ni versión, y luego pide otra lista o la versión 1
- **THEN** el primer pedido responde 200 con la versión 2 y los otros dos responden 403 `PERMISO_REQUERIDO`
- **Regla:** PRC-21; `design.md` D6, D19

#### Scenario: Búsqueda y páginas de precios
- **GIVEN** cinco productos activos
- **WHEN** el Vendedor pide los precios con `limite=2` y sigue el cursor, y busca `q=girasol`
- **THEN** recibe tres páginas de 2, 2 y 1 productos por código sin repetir, la última sin cursor, y la búsqueda trae solo los productos cuyo nombre o código contiene el texto, sin distinguir mayúsculas
- **Regla:** CAT-05; `design.md` D19

#### Scenario: Numeración del dispositivo
- **WHEN** la PC `V01` pide la numeración
- **THEN** recibe prefijo `"V01"` y último correlativo 41
- **Regla:** VTA-06; `design.md` D4

#### Scenario: Versiones sin permiso
- **WHEN** un Vendedor pide las versiones elegibles
- **THEN** recibe 403
- **Regla:** PRC-21

### Requirement: La pantalla de venta arma el pedido en cajas y unidades y confirma lo que muestra

La sección "Ventas" de `/admin` DEBE aparecer con `VENDER` o `ANULAR_VENTA`. "Nueva venta" (con `VENDER`) DEBE permitir elegir cliente (con su saldo), la ubicación o tomar la de la jornada abierta, cargar por producto cajas y unidades sueltas (solo si existe una presentación de 1 unidad), ver el bruto de cada línea, el total, la cobranza con la suma de medios en vivo y el saldo resultante, todo con `decimal.js`; pedir confirmación explícita si el saldo queda a favor; y proponer el número. Ante `PRECIO_DIFIERE` DEBE mostrar los valores nuevos y pedir confirmar de nuevo; ante `NUMERO_DUPLICADO`, releer la numeración y proponer el siguiente. Los componentes no contienen lógica de negocio.

#### Scenario: Composición en la pantalla
- **WHEN** el usuario carga 2 cajas y 3 unidades de Vino A
- **THEN** la pantalla muestra dos líneas con brutos $25.000,00 y $6.250,00 y total $31.250,00, igual que el servidor
- **Regla:** VTA-02; PRC-22; CAT-08

#### Scenario: Precio que cambió
- **WHEN** la confirmación responde `PRECIO_DIFIERE`
- **THEN** la pantalla muestra el precio y el total nuevos y no reenvía hasta que el usuario confirme
- **Regla:** `design.md` D2

#### Scenario: Número tomado por otra pestaña
- **WHEN** la confirmación responde `NUMERO_DUPLICADO`
- **THEN** la pantalla propone el número siguiente y el usuario confirma de nuevo
- **Regla:** VTA-06; `design.md` D4

#### Scenario: Reintento con el mismo `Operation-Id`
- **WHEN** la red falla después de enviar y el usuario reintenta
- **THEN** la pantalla reenvía el mismo `Operation-Id`, venta y número, y no queda una segunda venta
- **Regla:** INV-06

#### Scenario: Sin permiso
- **WHEN** un usuario de Consulta navega a "Ventas"
- **THEN** no ve la sección en el menú y la ruta muestra el aviso de falta de permiso
- **Regla:** SEG-06; ADR-027

### Requirement: El detalle muestra la venta como quedó congelada

El detalle DEBE mostrar número, fecha de negocio, cliente, vendedor, ubicación, jornada, lista y versión (con motivo si se eligió otra), líneas en su presentación con cantidad CAT-08, totales, cobranza con enlace a su detalle, estado de facturación y observaciones junto a su línea; los costos solo con `VER_COSTOS`.

#### Scenario: Venta con observaciones
- **WHEN** se abre una venta con `STOCK_NEGATIVO` en una línea
- **THEN** la marca "Stock negativo" aparece junto a esa línea con el saldo resultante
- **Regla:** SYN-07; STK-05
