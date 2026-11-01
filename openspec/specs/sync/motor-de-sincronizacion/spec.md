# sync/motor-de-sincronizacion Specification

## Purpose
Lleva al servidor, en orden y sin duplicar, las operaciones que el teléfono confirmó sin esperar a la red: envía la cola del usuario autenticado en lotes, una sola sincronización a la vez, escribe el resultado de cada operación, reintenta los cortes con espera exponencial y respeta la versión mínima de la aplicación (`02` §6.4, §6.6, §13.3).

## Requirements

### Requirement: El teléfono envía solo la cola propia, en orden y por lotes

El motor DEBE enviar los comandos pendientes cuyo usuario es el de la sesión local y cuyo dispositivo es el del teléfono, de cualquier jornada, en orden de secuencia y en lotes de hasta 50 por `POST /api/v1/sync/comandos`, repitiendo hasta vaciar la cola propia o hasta un corte. Los comandos de otro usuario NO DEBEN enviarse ni modificarse. Un comando con resultado NO DEBE volver a enviarse (`design.md` D1).

#### Scenario: Orden de envío
- **GIVEN** `vendedor` con tres ventas sin enviar de secuencias 8, 9 y 10
- **WHEN** el teléfono sincroniza
- **THEN** el lote lleva las tres en el orden 8, 9, 10
- **Regla:** SYN-03; `02` §6.4

#### Scenario: Más de 50 pendientes
- **GIVEN** 120 comandos pendientes de `vendedor`
- **WHEN** el teléfono sincroniza con señal estable
- **THEN** envía tres lotes de 50, 50 y 20, en orden, y la cola propia queda sin pendientes
- **Regla:** `02` §6.4

#### Scenario: Cola de otro usuario
- **GIVEN** una venta sin enviar de `vendedor` y `vendedor2` con la sesión abierta en el mismo teléfono
- **WHEN** el teléfono sincroniza
- **THEN** el lote no lleva la venta de `vendedor`, que sigue «Sin enviar», y el servidor no responde `COLA_AJENA`
- **Regla:** `02` §6.4; SYN-09

#### Scenario: Venta de una jornada anterior
- **GIVEN** una venta sin enviar de `vendedor` de una jornada anterior, liberada desde administración
- **WHEN** `vendedor` sincroniza en una jornada nueva
- **THEN** esa venta se envía y se acepta con `JORNADA_LIBERADA`
- **Regla:** RUT-09; RUT-05

#### Scenario: Un rechazado no se reenvía solo
- **GIVEN** una venta con resultado `RECHAZADO`
- **WHEN** el teléfono vuelve a sincronizar
- **THEN** esa venta no viaja en el lote y sigue visible como «Rechazada»
- **Regla:** SYN-09

### Requirement: Una sola sincronización a la vez en el teléfono

El teléfono NO DEBE ejecutar dos sincronizaciones a la vez, aunque haya varias pestañas abiertas. Si otra pestaña está sincronizando, la que recibe el disparador NO DEBE enviar y DEBE mostrar que la sincronización está en curso en otra pestaña. Un disparador que llega mientras la propia pestaña sincroniza DEBE producir una vuelta más al terminar. En un navegador sin bloqueo entre pestañas, dos envíos simultáneos NO DEBEN duplicar efectos (`design.md` D2; `02` §13.3).

#### Scenario: Dos pestañas a la vez
- **GIVEN** dos pestañas de `/ruta` abiertas con dos ventas sin enviar
- **WHEN** las dos disparan la sincronización al mismo tiempo
- **THEN** sale un solo lote y la otra pestaña muestra «Sincronizando en otra pestaña» y luego las dos ventas enviadas
- **Regla:** `02` §13.3; INV-06

#### Scenario: Venta confirmada durante el envío
- **GIVEN** una sincronización en curso
- **WHEN** el vendedor confirma otra venta
- **THEN** al terminar el envío en curso se hace una vuelta más que envía la venta nueva
- **Regla:** `02` §13.3

### Requirement: El resultado de cada operación se escribe en el teléfono

Por cada resultado del lote, identificado por su `operation_id` y nunca por su posición, el teléfono DEBE dejar el comando con su resultado y su código de error, y la venta con el estado de envío «Enviada» (`ACEPTADO`), «Con observaciones» (`ACEPTADO_CON_OBSERVACIONES`) o «Rechazada» (`RECHAZADO`). Los resultados de un lote DEBEN escribirse todos o ninguno. Un error transitorio y los ítems que el servidor no llegó a procesar DEBEN quedar «Sin enviar». Ninguna venta, cobranza, movimiento ni comando DEBE borrarse por recibir su resultado (`design.md` D3).

#### Scenario: Venta aceptada
- **GIVEN** la venta V03-000142 sin enviar
- **WHEN** el servidor responde `ACEPTADO`
- **THEN** la venta queda «Enviada» y su comando con resultado `ACEPTADO`, y los dos siguen en el teléfono
- **Regla:** SYN-04; SYN-09

#### Scenario: Venta con observaciones
- **GIVEN** una venta sin conexión que superó el crédito por tolerancia
- **WHEN** el servidor responde `ACEPTADO_CON_OBSERVACIONES`
- **THEN** la venta queda «Con observaciones»
- **Regla:** SYN-04; SYN-05; SYN-07

#### Scenario: Venta rechazada
- **GIVEN** una venta cuyo sobre llega con una jornada inexistente
- **WHEN** el servidor responde `RECHAZADO` con `JORNADA_INEXISTENTE`
- **THEN** la venta queda «Rechazada» con ese código y sigue visible en el teléfono
- **Regla:** SYN-06; SYN-09

#### Scenario: Corte a mitad del lote
- **GIVEN** un lote de tres ventas
- **WHEN** el servidor acepta la primera y responde `ERROR_TRANSITORIO` en la segunda
- **THEN** la primera queda «Enviada» y la segunda y la tercera siguen «Sin enviar»
- **Regla:** SYN-03; `02` §6.4

#### Scenario: Falla al escribir los resultados
- **GIVEN** una respuesta de lote con dos resultados
- **WHEN** la escritura local falla después del primero
- **THEN** ninguna de las dos ventas cambia de estado y el próximo envío las manda otra vez
- **Regla:** INV-01; INV-06

### Requirement: Sincronizar dos veces no duplica la operación

Enviar dos veces el mismo comando, por una respuesta perdida, por dos sincronizaciones seguidas o por dos pestañas, DEBE dejar en el servidor una sola operación con sus efectos una sola vez, y en el teléfono una sola venta con su resultado (`design.md` D12; `00` §9 criterio 8).

#### Scenario: Respuesta perdida
- **GIVEN** un lote que el servidor procesó y cuya respuesta se perdió por un corte de red
- **WHEN** el teléfono reenvía el mismo comando con el mismo `operation_id`
- **THEN** el servidor devuelve el resultado original y en el teléfono la venta queda «Enviada» una sola vez
- **Regla:** INV-06; SYN-02

#### Scenario: Dos lotes simultáneos con la misma venta
- **GIVEN** una venta sin conexión de 2 cajas y 3 botellas de Vino A
- **WHEN** llegan al servidor dos lotes simultáneos con el mismo comando
- **THEN** existe una sola venta, el stock baja una sola vez, el saldo del cliente sube una sola vez y el costo congelado y la utilidad son los de un solo envío
- **Regla:** INV-06; SYN-02

#### Scenario: Sincronizar dos veces deliberadamente
- **GIVEN** dos ventas enviadas y aceptadas
- **WHEN** el vendedor toca «Sincronizar» otra vez
- **THEN** no se envía ningún lote con esas ventas y en administración siguen siendo dos
- **Regla:** INV-06; SYN-09

### Requirement: Los cortes se reintentan con espera exponencial

Un corte de red, una respuesta 5xx o 429 o un ítem `ERROR_TRANSITORIO` DEBEN cortar el ciclo y programar el próximo intento automático con espera exponencial de 5 s, 10 s, 20 s, 40 s, 80 s y luego 120 s, con una variación al azar. Una sesión vencida (401 tras la renovación) NO DEBE reintentarse sola y DEBE pedir iniciar sesión con señal. Un 403, un 422 u otro error del pedido NO DEBEN reintentarse con espera: se informan con su código y se vuelve a probar con el próximo disparador. Un ciclo sin corte DEBE registrarse como sincronización exitosa y volver la espera a cero; «Sincronizar» y la vuelta de la señal también la vuelven a cero (`design.md` D5).

#### Scenario: Sin señal
- **GIVEN** una venta sin enviar y el servidor inalcanzable
- **WHEN** fallan tres intentos seguidos
- **THEN** las esperas entre ellos son de unos 5 s, 10 s y 20 s y la venta sigue «Sin enviar»
- **Regla:** `02` §13.3

#### Scenario: Vuelve la señal
- **GIVEN** la espera en 80 s por cortes anteriores
- **WHEN** el navegador informa que volvió la conexión
- **THEN** el teléfono sincroniza en el momento y, si termina sin corte, la espera vuelve a cero
- **Regla:** `02` §13.3

#### Scenario: Sesión vencida
- **GIVEN** el refresh token vencido
- **WHEN** el teléfono intenta sincronizar
- **THEN** no reintenta solo, muestra «Iniciá sesión con señal para enviar las ventas» y la cola sigue intacta
- **Regla:** `02` §12.3; SYN-09

#### Scenario: Error del pedido
- **GIVEN** un lote que el servidor responde con 422
- **WHEN** termina el intento
- **THEN** se muestra «No se pudo enviar» con el código, no se programa un reintento con espera y las ventas siguen «Sin enviar»
- **Regla:** SYN-06

#### Scenario: Sincronización exitosa
- **GIVEN** dos ventas sin enviar
- **WHEN** el servidor acepta el lote y no queda nada pendiente
- **THEN** «Última sincronización» muestra la hora de ese ciclo
- **Regla:** `02` §13.3

### Requirement: La sincronización se dispara sola y a pedido

Con la sesión local desbloqueada, el teléfono DEBE sincronizar al abrir la aplicación (al desbloquear o al terminar el login), cuando la aplicación vuelve a primer plano, cuando vuelve la conexión, después de cada venta confirmada si hay conexión, cada 2 minutos mientras la aplicación está abierta y con el botón «Sincronizar». Con la sesión bloqueada o sin usuario local NO DEBE sincronizar, y la aplicación oculta NO DEBE disparar por volver a primer plano. Todo disparador DEBE pasar por la misma sincronización única: varios disparadores durante un envío NO DEBEN producir más de una vuelta adicional. La vuelta a primer plano, como «Sincronizar» y la vuelta de la conexión, DEBE volver la espera exponencial a cero y enviar en el momento; el disparador posterior a una venta y el periódico DEBEN respetar la espera vigente (`design.md` D6 = B, D2, D5; `02` §13.3).

#### Scenario: Después de una venta
- **GIVEN** `vendedor` con señal
- **WHEN** confirma una venta
- **THEN** el teléfono la envía sin que el vendedor toque nada
- **Regla:** `02` §13.3

#### Scenario: Cada 2 minutos
- **GIVEN** la aplicación abierta con una venta sin enviar y sin cortes
- **WHEN** pasan 2 minutos desde la última sincronización
- **THEN** el teléfono vuelve a sincronizar
- **Regla:** `02` §13.3

#### Scenario: Sesión bloqueada
- **GIVEN** la aplicación abierta en la pantalla del PIN de desbloqueo
- **WHEN** vuelve la conexión
- **THEN** no se envía nada hasta desbloquear
- **Regla:** SEG-03; `02` §6.4

#### Scenario: Vuelta a primer plano
- **GIVEN** `vendedor` con la sesión desbloqueada, señal y una venta sin enviar, con la aplicación en segundo plano
- **WHEN** vuelve a la aplicación y queda visible
- **THEN** el teléfono sincroniza sin que el vendedor toque nada
- **Regla:** `02` §13.3; ADR-064

#### Scenario: Vuelta a primer plano con la sesión bloqueada
- **GIVEN** la aplicación en segundo plano con la sesión local bloqueada y una venta sin enviar
- **WHEN** vuelve a primer plano en la pantalla del PIN de desbloqueo
- **THEN** no se envía nada hasta desbloquear
- **Regla:** SEG-03; ADR-064

#### Scenario: Aplicación oculta
- **GIVEN** `vendedor` con la sesión desbloqueada y una venta sin enviar
- **WHEN** la aplicación pasa a segundo plano
- **THEN** ese cambio no dispara una sincronización
- **Regla:** ADR-064

#### Scenario: Disparadores durante un envío
- **GIVEN** una sincronización en curso en la pestaña
- **WHEN** llegan, antes de que termine, la vuelta a primer plano y una venta confirmada
- **THEN** al terminar se hace una sola vuelta más
- **Regla:** `02` §13.3; ADR-064

### Requirement: Por debajo de la versión mínima se envía la cola pero no se vende

En cada sincronización el teléfono DEBE consultar la versión mínima publicada y guardar la última conocida, de modo que el bloqueo valga sin señal. Si la versión de la aplicación es menor que la mínima, el teléfono DEBE seguir enviando la cola y NO DEBE confirmar ventas nuevas: «Vender» queda deshabilitado con el aviso de versión desactualizada y la confirmación también lo revisa, sin descartar el carrito. Si alguna de las dos versiones no tiene el formato `X.Y.Z` o no hay mínima, NO DEBE haber restricción (`design.md` D7; `02` §6.6).

#### Scenario: Aplicación desactualizada con ventas pendientes
- **GIVEN** la aplicación en 1.2.0, la mínima publicada en 1.3.0 y dos ventas sin enviar
- **WHEN** el teléfono sincroniza
- **THEN** las dos ventas se envían y «Vender» queda deshabilitado con «Esta versión ya no puede confirmar ventas nuevas: actualizá la aplicación»
- **Regla:** `02` §6.6

#### Scenario: Sin señal después de conocer la mínima
- **GIVEN** la mínima 1.3.0 ya conocida por el teléfono y la aplicación en 1.2.0
- **WHEN** el vendedor, sin señal, intenta vender
- **THEN** «Vender» sigue deshabilitado
- **Regla:** `02` §6.6

#### Scenario: Aviso con el carrito abierto
- **GIVEN** un carrito con líneas y la mínima recién conocida por encima de la versión de la aplicación
- **WHEN** el vendedor toca «Confirmar venta»
- **THEN** la venta no se confirma, el carrito sigue igual y se muestra el aviso de versión desactualizada
- **Regla:** `02` §6.6; VTA-07

#### Scenario: Versión sin formato
- **GIVEN** la aplicación compilada con la versión `dev`
- **WHEN** el servidor publica la mínima 1.3.0
- **THEN** el teléfono vende con normalidad
- **Regla:** `02` §6.6
