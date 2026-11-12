# ADR-063 — Venta en ruta confirmada en el teléfono, cola local atómica y PIN de supervisor verificado en el dispositivo

| Campo | Valor |
| --- | --- |
| Estado | Vigente (2026-10-31, archivo del change 22a) |
| Fecha | 2026-10-31 |
| Referenciado en | `openspec/changes/22a-cola-confirmacion-local/design.md` D0 a D17 y `specs/sync/cola-local`, `specs/ventas/venta-en-ruta`, `specs/sync/base-local`, `specs/identidad/pin-de-autorizacion`, `specs/ventas/nota-de-venta`, `specs/sistema/aplicacion-instalable`, `specs/ruta/area-de-ruta`; `01-dominio.md` VTA-06, VTA-07, VTA-11, VTA-13, CLI-02, CLI-03, PRC-21, DSC-06, CRE-04 a CRE-08, CRE-10, STK-06, RUT-04, SYN-01, SYN-03, SYN-05, SYN-09, SYN-10, SEG-05, INV-01, INV-03, INV-04, INV-06; `02-arquitectura.md` §6.2, §7.7, §12.4, §13.2, §13.5, §13.6; ADR-051, ADR-054, ADR-055, ADR-056, ADR-059, ADR-061, ADR-062 |

**Change 22a. Gobernanza ALTA en la verificación local del PIN de supervisor (D10); MEDIA en el resto. Decisiones aprobadas el 2026-10-31: A en todas salvo D6 = C y D10 = B. Estado Vigente desde el archivo del change (2026-10-31).**

## Contexto

`02` §13.2 exige que confirmar una venta local sea una transacción Dexie que escribe la venta, los movimientos locales y el comando, todo o nada, y §12.4 que el PIN de supervisor sin conexión tenga un límite de intentos en la interfaz. ADR-054 pide que el teléfono bloquee la venta al consumidor final con cobranza distinta del total; ADR-055, la evaluación local de crédito y descuentos; ADR-059, el adaptador desde Dexie de la nota; ADR-061 dejó abierto el motivo dado de baja en un comando sin conexión; ADR-062, las tablas de operaciones (Dexie v3) y la guarda del carrito. `docs/` no resuelve si la venta de `/ruta` va siempre por la cola, dónde se asignan número y secuencia, qué movimientos locales cuentan para el saldo y el stock, qué reglas aplica el teléfono antes de encolar, cómo se cuentan los fallos del PIN de supervisor en el teléfono ni qué datos congela la venta local para la nota.

## Decisión (aprobada el 2026-10-31: opciones recomendadas de `design.md`, salvo D6 = C y D10 = B)

1. **Lotes (D0).** Un change en cinco lotes.
2. **Un solo camino (D1).** Toda venta de `/ruta` se confirma en el teléfono y va por la cola como `VENTA_CONFIRMAR` `OFFLINE`, con o sin señal; la venta con conexión sigue en `/admin`.
3. **Sobre y contrato (D2).** El sobre del lote (`02` §6.2) sin credenciales y con el objeto `credito` completo; un fixture de contrato en `shared/fixtures/sync/` lo comparten Vitest y una prueba de integración del lote (`ACEPTADO`). Sin código nuevo en el servidor. Es la única verificación, antes del 22b, de que lo que arma el teléfono lo acepta el servidor; el 22b la reutiliza como base.
4. **Dexie v3 (D3).** `ventas`, `cobranzas`, `movimientos_locales`, `cola` e `intentos_pin`; `meta` suma `ultimo_correlativo` y `ultima_secuencia`; el bootstrap no las toca.
5. **Transacción (D4).** Número (`max(bootstrap, local) + 1`) y secuencia se asignan dentro de la única transacción de confirmación; cálculo y PIN antes de abrirla; reconfirmar con el mismo `operation_id` no encola otra venta. El correlativo de `/ruta` no usa `localStorage`.
6. **Saldo y stock locales (D5).** Bootstrap más los movimientos de las ventas de la jornada sin resultado del servidor (CRE-08, RUT-04); la conciliación tras sincronizar es del 22c.
7. **Stock (D6 = C).** La línea que supera el stock local del vehículo se bloquea salvo que el usuario tenga `PERMITIR_STOCK_NEGATIVO` (viene en los `permisos` del bootstrap). Con el permiso: aviso "Supera el stock del vehículo (quedan N)" y confirmación "Vender igual"; el servidor deja `STOCK_NEGATIVO` (STK-06) como red de seguridad. Sin el permiso no se confirma y se indica actualizar los datos con señal. **El alcance del permiso se extiende:** de "operar con stock negativo online" (STK-05) pasa a abarcar también la verificación en el teléfono de las ventas sin conexión; `01` §19 y STK-06 se actualizan (tarea 19.1). La descripción del permiso queda en la etiqueta corta "Operar con stock negativo" (decisión del usuario, 2026-10-31); el detalle del teléfono vive en STK-06, y la migración `b7d3f1a9c2e4` actualiza el texto en las bases ya migradas. Motivo: un superior puede salir a vender, pero no todos deberían dejar stock negativo.
8. **Reglas locales (D7).** Las mismas que con conexión con los datos y permisos del bootstrap, salvo stock y costo.
9. **Consumidor final (D8).** Cobranza exactamente igual al total, siempre.
10. **Crédito (D9).** `SIN_CONEXION` siempre, con la tolerancia.
11. **PIN de supervisor (D10).** PBKDF2 en el teléfono contra la derivación del bootstrap; fallos por par (usuario, autorizador) en `intentos_pin`; con `intentos_pin_max` fallos el PIN de ese supervisor queda bloqueado en ese teléfono hasta el próximo bootstrap (abrir la jornada o "Actualizar datos"), no por tiempo, porque el reloj del teléfono se puede adelantar; no se guardan horas. Un intento durante el bloqueo no verifica ni cuenta; un acierto no reinicia; cualquier bootstrap nuevo levanta el bloqueo y reinicia las cuentas. El PIN no se guarda ni viaja.
12. **Motivo dado de baja (D11).** Se cierra sin código nuevo: el teléfono ofrece los motivos activos del bootstrap y el servidor acepta uno dado de baja después (ya implementado para la lista anterior; la causa `MOTIVO` de `DESCUENTO_DIFIERE` para el descuento manual).
13. **Carrito (D12).** En memoria; con líneas, el aviso de versión nueva no ofrece "Actualizar".
14. **Estado de envío (D13).** `PENDIENTE`, `ACEPTADA`, `CON_OBSERVACIONES`, `RECHAZADA`; el 22a solo escribe `PENDIENTE`.
15. **Pantallas (D14).** Vender (cliente, pedido, cobro y confirmación), venta guardada, Ventas de hoy y pendientes en el inicio.
16. **Nota (D15).** La venta local congela los datos de la nota; adaptador puro a la misma función de armado.
17. **Cierre de sesión (D16).** Se permite con aviso; nada pendiente se borra.
18. **Ayuda (D17).** Claves de la venta reutilizadas y cinco claves nuevas de `/ruta`, sin ejemplos.

## Consecuencias

- El 22b solo envía la cola y cambia `estado_envio`; debe enviar únicamente la cola del usuario autenticado (`02` §6.4).
- El 22c debe excluir del saldo y del stock locales los movimientos de operaciones aceptadas que ya incluya un bootstrap posterior.
- `PERMITIR_STOCK_NEGATIVO` gana un uso en el teléfono: quien salga a vender y deba poder dejar stock negativo necesita ese permiso en su rol (roles configurables desde el 20b).
- Un vendedor sin señal cuyo supervisor llegó al máximo de intentos no puede usar ese PIN hasta actualizar los datos.
- Hasta el 22b, las ventas de `/ruta` quedan en el teléfono como "Sin enviar".
- `02` §7.7 y §13.2 quedan precisados (correlativo en Dexie, tablas v3); `02` §12.4 gana el detalle del límite local.

## Precisiones del apply

- **Sin servidor nuevo.** El 22a no agregó migración, endpoint ni handler: el contrato del sobre (D2) se verificó con `shared/fixtures/sync/venta-confirmar-offline.json`, validado por Vitest (`sync/sobre.test.ts`) y por pruebas del backend (`tests/unit` y `tests/integration/test_contrato_sobre_venta_offline.py`: el lote acepta el sobre, el reenvío no duplica y un sobre con credenciales se rechaza).
- **Nota congelada (D15).** La venta local guarda en Dexie los datos de la nota (`NotaCongelada`: organización, cliente, vendedor, nombres de producto, presentación y medio, saldo resultante); un bootstrap posterior no cambia la nota reimpresa (VTA-13).
- **Vendedor de cada pendiente.** `VentaLocal` no guarda el usuario; el conteo de ventas sin enviar de un usuario sale de `cola.sobre.usuario_id` y el nombre del anterior, de la nota congelada. El registro tras el login (`registrarUsuarioTrasLogin`) devuelve `pendientesDeOtro` para avisar sin borrar nada (D16).
- **Guarda del carrito (D12).** La aplicación usa `BrowserRouter`, que no admite `useBlocker`; "¿Descartar la venta?" intercepta el menú inferior y "Cancelar". Los enlaces del cuerpo de Vender y el botón atrás del navegador no se interceptan (deuda al 22b). El carrito vive en memoria, de modo que perderlo no deja nada confirmado a medias.
- **PIN de supervisor (D10 = B).** La cuenta de fallos es por par (usuario, autorizador) en `intentos_pin`; sin horas guardadas; el bloqueo no depende del reloj; cualquier bootstrap reinicia las cuentas de todos los pares; el PIN no se guarda ni viaja. Intentos simultáneos dentro de una misma pestaña se serializan con una cola de promesas.
- **Prueba de punta a punta.** `tests/unit/areas/ruta/FlujoVentaRuta.test.tsx` recorre login, PIN, jornada, bootstrap, la venta del criterio 5 sin red, la segunda venta resuelta con el PIN de `sup01` (criterio 6), la nota compartida (criterio 7), "2 ventas sin enviar" y "Actualizar datos" sin tocar la cola; y `tests/unit/cobertura/escenariosDe22a.test.ts` asocia cada requisito y escenario de las siete specs con su prueba.

## Alternativas consideradas

Las opciones B y C de cada decisión de `design.md`, con sus consecuencias.

## Deudas nominadas

- **Al 22b:** enviar la cola por secuencia, escribir `estado_envio`, la versión mínima de la aplicación (`02` §6.6) y el botón "Sincronizar".
- **Al 22b:** serializar los intentos de PIN de supervisor entre pestañas (hoy la cola de promesas solo protege dentro de una pestaña; usar Web Locks, que el 22b ya introduce para el envío), para que dos pestañas no esquiven el límite de `intentos_pin_max`.
- **Al 22b:** cubrir la guarda del carrito en los enlaces del cuerpo de Vender y en el botón atrás del navegador (requiere un enrutador de datos, `createBrowserRouter`, para `useBlocker`, o interceptar el historial); hoy solo se intercepta el menú inferior y "Cancelar" (D12).
- **Al 22c:** conciliar los movimientos locales con un bootstrap posterior a una sincronización aceptada.
