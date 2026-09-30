# ADR-034 — Reglas del saldo inicial, sentido fijo por tipo de movimiento, estado de cuenta y efecto en CLI-06

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-29 |
| Referenciado en | `openspec/changes/08-cuentas-corrientes/design.md` D3, D4, D8, D9 y D12 y `specs/cuentas-corrientes/saldo-inicial`, `specs/cuentas-corrientes/estado-de-cuenta`, `specs/cuentas-corrientes/saldo-de-cuenta`, `specs/clientes/fichas-de-cliente`; `01-dominio.md` CC-01 a CC-07, CLI-06 y §21; ADR-030 (CLI-06); `docs/03-modelo-de-datos.md` §12 |

**Decisiones D3, D4, D8, D9 y D12 (opción A en cada una) aprobadas por el usuario el 2026-09-29, junto con las decisiones de implementación aprobadas el mismo día que se detallan en los puntos 5 y 6. Texto del ADR aprobado por el usuario el 2026-09-30; estado *Vigente*.**

## Contexto

En la etapa 1 no existe el tipo `AJUSTE` (CC-02 lo deja para la etapa 2), así que `docs/` no dice cuántos saldos iniciales admite una cuenta, cómo se corrige uno mal cargado, hasta cuándo, ni a qué entidades se les puede cargar. Tampoco dice qué sentido corresponde a cada tipo de movimiento ni cómo se recorta y pagina un estado de cuenta (CC-07 solo pide orden por `occurred_at` con saldo acumulado calculado al consultar, y `02` §11 exige cursor y límite). Finalmente, la spec `clientes/fichas-de-cliente` dejó CLI-06 (un cliente `INACTIVO` con operaciones no se reactiva, ADR-030) latente hasta que un change registrara la primera operación; el change 08 puede ser ese change.

Se registra como ADR porque estas reglas las consumen los changes 10 (importación de saldos), 11, 12, 17, 18a y 19, y porque una de ellas (D3) es una regla de negocio nueva que se propone como CC-08 en `01` §12.1.

## Decisión

1. **Varios saldos iniciales por cuenta, corregibles con uno inverso (D3).** Una cuenta admite varios movimientos `SALDO_INICIAL`, cada uno con su sentido (`AUMENTA` o `REDUCE`). Un error de carga se corrige con otro `SALDO_INICIAL` en sentido contrario por la diferencia (por ejemplo, $20.000 `REDUCE` sobre un $150.000 `AUMENTA` cargado de más); los dos quedan visibles en el estado de cuenta y en la auditoría. No se agregan tipos nuevos: CC-02 y CC-03 quedan como están.
2. **Solo mientras la cuenta no tenga movimientos de otro tipo (D3).** Si la cuenta ya tiene cualquier movimiento que no sea `SALDO_INICIAL`, el comando se rechaza con `CUENTA_CON_OPERACIONES` y no cambia ninguna fila. Pasada la puesta en marcha, la corrección espera a los ajustes de la etapa 2. La comprobación se hace con la fila de saldo de la cuenta ya bloqueada, así que ningún movimiento de otro tipo puede colarse entre la lectura y la inserción. Se propone como **CC-08** en `01` §12.1.
3. **A qué entidades (D4).** A cualquier cliente (`ACTIVO`, `SUSPENDIDO` o `INACTIVO`) y a cualquier proveedor (activo o inactivo), **salvo el consumidor final**, que se rechaza con `CONSUMIDOR_FINAL_SIN_CUENTA`: es un cliente genérico con límite cero (CLI-03) que no identifica a ningún deudor. La deuda previa existe aunque la entidad esté suspendida o dada de baja. El consumidor final se reconoce por la configuración de la organización, leída por `identidad/service.py`; el libro no lee el estado de `clientes` ni de `proveedores`.
4. **Un saldo inicial es una operación para CLI-06 (D8).** Un cliente tiene operaciones si su cuenta corriente tiene **cualquier** movimiento, incluido un saldo inicial. El handler de `CLIENTE_MODIFICAR` lo consulta a `cuentas_corrientes/service.py::cuenta_tiene_movimientos` después de bloquear la fila del cliente y solo cuando la transición es `INACTIVO → ACTIVO`; con movimientos, se rechaza con `CLIENTE_CON_OPERACIONES` (ADR-030). Como ventas y cobranzas también escriben en el mismo libro, la misma consulta las cubre cuando lleguen. Un cliente dado de baja por error al que ya se le cargó un saldo inicial no se puede reactivar. La concurrencia entre una reactivación y un saldo inicial queda serializada por la FK compuesta de `cuenta_movimiento` y de `saldo_cuenta` hacia `cliente` (ADR-035) y se prueba con commits reales.

   **Enmienda a ADR-030, punto 3.** ADR-030 fijó que la comprobación de "no tiene operaciones" usaría el mecanismo de verificadores de uso de ADR-023 (cada módulo que introduce operaciones registra un verificador). Este ADR lo reemplaza: **no se registra un verificador**; el handler de `CLIENTE_MODIFICAR` consulta directamente al libro a través de `cuentas_corrientes/service.py::cuenta_tiene_movimientos` y se lo pasa a `clientes/service.py` como la función `verificar_operaciones`. El motivo es que todas las operaciones de un cliente que cuentan para CLI-06 (saldo inicial, ventas, anulaciones, cobranzas) escriben en el mismo libro de cuenta corriente, así que una sola consulta al libro cubre las presentes y las futuras sin que cada módulo tenga que registrar nada. El resto de ADR-030 (puntos 1, 2 y 4) sigue vigente sin cambios. El mecanismo de ADR-023 sigue vigente para su uso original (CAT-04, presentaciones usadas).
5. **Sentido fijo por tipo de movimiento, verificado solo en el dominio.** El sentido de cada tipo es fijo:
   - **Aumentan** el saldo: `VENTA` y `ANULACION_COBRANZA` (cuenta de cliente), `COMPRA` y `ANULACION_PAGO` (cuenta de proveedor).
   - **Reducen** el saldo: `ANULACION_VENTA` y `COBRANZA` (cliente), `ANULACION_COMPRA` y `PAGO` (proveedor).
   - `SALDO_INICIAL` admite los dos sentidos (punto 1).

   Un movimiento cuyo sentido contradice al de su tipo se rechaza en el dominio (`SENTIDO_INVALIDO`). **No hay `CHECK` en la base** para esta regla: la base sigue verificando el catálogo de `tipo`, el de `sentido`, la coherencia entre `cuenta_tipo` y `tipo` y que el importe sea positivo (D12), pero no el emparejamiento tipo–sentido. Lo aprobado es que esa regla viva solo en el dominio (`cuentas_corrientes/domain/`, función pura) y se pruebe allí.
6. **Estado de cuenta (D9).**
   - Filtro opcional `desde` y `hasta`: son **fechas de negocio en la zona horaria de la organización** (TR-04), y `hasta` es **inclusivo** (incluye todo ese día). `desde` posterior a `hasta` se rechaza con `RANGO_DE_FECHAS_INVALIDO`.
   - La respuesta trae `saldo_anterior` (suma SQL de lo anterior a `desde`, o `0.00`), el saldo actual y los movimientos en orden ascendente `(occurred_at, id)` con el saldo acumulado calculado con `SUM(...) OVER (ORDER BY occurred_at, id)` sobre la cuenta completa y filtrado después, de modo que el acumulado siempre es el real (CC-07). La respuesta incluye la zona horaria de la organización para que la pantalla muestre las fechas en ella.
   - **Cursor** opaco: `base64` de `occurred_at|id` del último movimiento de la página. Uno ilegible se rechaza con `CURSOR_INVALIDO`.
   - **Límite** por página: 50 por defecto y máximo 200. **La API rechaza con 422 un límite fuera de 1 a 200** (no lo recorta en silencio); el servicio, como red de seguridad para otros llamadores, recorta a 200.
   - Los importes y saldos viajan como string (`CLAUDE.md` §4) y la suma la hace la base.
7. **Catálogo de tipos (D12).** El `CHECK` de la base declara desde ahora todos los tipos de la etapa 1 de CC-02 (`SALDO_INICIAL`, `VENTA`, `ANULACION_VENTA`, `COBRANZA`, `ANULACION_COBRANZA`) y CC-03 (`SALDO_INICIAL`, `COMPRA`, `ANULACION_COMPRA`, `PAGO`, `ANULACION_PAGO`), sin los de IVA (`IVA_FACTURA`, `ANULACION_IVA_FACTURA`), que agrega el módulo de facturación con su migración. En el change 08 solo `SALDO_INICIAL` tiene comando.
8. **Rótulos de negocio en la interfaz.** El saldo se muestra con rótulos y no con signos: en clientes, **"Nos debe"** (saldo positivo) y **"Saldo a favor"** (negativo); en proveedores, **"Le debemos"** (positivo) y **"Saldo a nuestro favor"** (negativo). El sentido del saldo inicial se ofrece con esos mismos rótulos.

## Consecuencias

- El estado de cuenta puede mostrar dos o tres líneas de saldo inicial en lugar de una cuando hubo una corrección.
- Ningún change posterior necesita migrar el `CHECK` de `tipo` para los tipos de la etapa 1; los tipos de IVA sí requieren su propia migración (change de facturación).
- La regla "solo sin otras operaciones" queda latente hasta que los changes 11, 17 o 18a escriban otros tipos; en el change 08 se prueba insertando un movimiento de otro tipo por el servicio.
- Un cliente `INACTIVO` con saldo inicial cargado no se puede reactivar: hay que dar de alta otro cliente. Es el espíritu de ADR-030 (no revivir deudores por error).
- Como el sentido de cada tipo no lo garantiza la base, cualquier código que escriba en `cuenta_movimiento` fuera de `cuentas_corrientes/service.py` podría insertar un sentido contradictorio; la protección es que solo el servicio escribe el libro (`02` §5.3) y que la prueba de dominio cubre el catálogo completo.
- `clientes` depende de `cuentas_corrientes/service.py` para la reactivación (dependencia en un solo sentido; `cuentas_corrientes` no importa `clientes`). Si en el futuro una operación de cliente que deba contar para CLI-06 no escribiera en el libro de cuenta corriente, habría que ampliar esta consulta o volver a un verificador.
- El change 10 (importación de saldos) reutiliza `registrar_saldo_inicial` fila por fila, de modo que hereda las reglas 1 a 3.

## Alternativas consideradas

- **Un único saldo inicial por cuenta** (índice único parcial), sin forma de corregirlo en la etapa 1: descartada: un error de carga quedaría para siempre en la cuenta hasta la etapa 2, o se "compensaría" con operaciones falsas, que es peor.
- **Un único saldo inicial más un comando de anulación** con un tipo nuevo `ANULACION_SALDO_INICIAL`: descartada: cambia el catálogo de tipos de `01` (CC-02 y CC-03) y agrega un comando más.
- **Saldo inicial solo a entidades activas**: descartada: un cliente dado de baja con deuda no se podría cargar, y obligaría al libro a leer el estado de `clientes` y `proveedores` (ADR-035).
- **Saldo inicial también al consumidor final**: descartada: permitiría deuda en una cuenta sin titular, que nadie podría cobrar.
- **Los saldos iniciales no cuentan como operación para CLI-06** (solo ventas, cobranzas y compras): descartada: un cliente inactivo con deuda previa podría reactivarse sin revisión, que es lo que ADR-030 quiso evitar.
- **Mantener el verificador de uso de ADR-023 para CLI-06** (ADR-030 punto 3): `cuentas_corrientes` registraría un verificador en `clientes`: descartada: agrega un registro global y una dependencia invertida para una consulta que hoy es una sola y cubre todas las operaciones de cliente, porque todas pasan por el libro.
- **Cuenta como operación solo si el saldo actual es distinto de cero**: descartada: un cliente que debía y saldó a cero podría revivirse, y la regla dependería de un número que cambia.
- **Un `CHECK` de la base para el emparejamiento tipo–sentido**: no adoptada; el usuario aprobó que la regla se verifique solo en el dominio.
- **Estado de cuenta sin filtro de período** (todo el historial paginado por cursor) o **sin paginación**: descartadas: la primera obliga a recorrer todas las páginas para ver el mes actual de un cliente viejo; la segunda contradice `02` §11.
