# ADR-045 — Condición frente al IVA de la organización: regla de crédito fiscal en compras, congelamiento por registro y alcance de ADR-009

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-10-03 |
| Referenciado en | `openspec/changes/11b-condicion-iva-organizacion/design.md` D0 a D10 y `specs/organizacion/parametros-de-organizacion`, `specs/proveedores/costos-informados`, `specs/proveedores/compras`, `specs/proveedores/administracion-de-proveedores`, `specs/proveedores/administracion-de-compras`, `specs/importacion/importacion-de-maestros`; `01-dominio.md` §4, §6.1 (CST-02, CST-06), §6.3 (CMP-01, CMP-02), §16 (FAC-02, FAC-03, FAC-04, FAC-08), §19; `03-modelo-de-datos.md` §4 y §6; ADR-009 (enmendado), ADR-016, ADR-040, ADR-043 |

**Decisiones D0 a D10 (opción A en cada una, incluido el ID de regla nuevo CST-06) aprobadas por el usuario el 2026-10-03. Durante el apply se aprobaron además dos precisiones (ver puntos 14 y 15). Texto del ADR aprobado por el usuario el 2026-10-03; estado *Vigente*.**

## Contexto

`01` CST-02 y CMP-02 suponen que el IVA de una compra se recupera: el costo base lo descuenta cuando el valor incluye IVA y el total de factura sugerido lo suma de nuevo. La organización inicial es una distribuidora **monotributista**: no recupera el IVA de compra, así que para ella el IVA es costo. Además ADR-009 y FAC-02, FAC-03 y FAC-08 (modalidad CLIENTE/ABSORBIDO, utilidad neta de IVA) solo tienen sentido para un responsable inscripto: un monotributista emite Factura C, sin IVA discriminado. `docs/` tampoco dice qué pasa con lo ya registrado si la condición cambia (por ejemplo, el monotributista que pasa a inscripto). Este ADR enmienda ADR-009 y el cálculo de CST-02 y CMP-02.

## Decisión

1. **Una condición, una regla derivada (D1).** `configuracion_organizacion.condicion_iva text NOT NULL` con `CHECK IN ('RESPONSABLE_INSCRIPTO', 'MONOTRIBUTO', 'EXENTO')`. De ella se deriva una sola regla pura, **CST-06**: *computa crédito fiscal de IVA en compras* es verdadera solo para `RESPONSABLE_INSCRIPTO`. `EXENTO` se comporta como `MONOTRIBUTO` para el costo, pero se distingue para la facturación futura (Factura A/B o C). Toda parte del sistema que necesite saber si el IVA de una compra es costo usa la regla, no la condición.
2. **Alcance de ADR-009 (D2).** En una organización no inscripta el modo impositivo es `A` y la modalidad de IVA al facturar queda sin definir, por una restricción de base: `condicion_iva = 'RESPONSABLE_INSCRIPTO' OR (modo_impositivo = 'A' AND modalidad_iva_default IS NULL)`. **ADR-009 y FAC-02, FAC-03, FAC-04 y FAC-08 solo se aplican a responsables inscriptos.** El modo A (venta a precio final, sin IVA en la venta, VTA-04) es lo que hace un monotributista.
3. **La regla se congela en cada registro (D3).** `costo_informado` y `compra_linea` agregan `computa_credito_fiscal boolean NOT NULL`, tomada de la condición vigente al registrar, con `CHECK (computa_credito_fiscal OR NOT incluye_iva)`. Las filas existentes se migran con `true`. CST-02 queda `valor × (1 − bonificación) / (1 + alícuota si incluye IVA y computa crédito fiscal) / unidades`. El costo base ya se guarda: nada se recalcula nunca (TR-06). La regla no viaja en el comando: la decide el servidor.
4. **`incluye_iva` en una organización no inscripta (D4).** `COSTO_INFORMAR` y cada línea de `COMPRA_CONFIRMAR` con `incluye_iva = true` se rechazan con 422 `INCLUYE_IVA_NO_APLICA`, indicando la línea o la fila (TR-10). El valor cargado es siempre el pagado; la interfaz oculta la casilla, rotula "Valor pagado" y envía `false`.
5. **Total de factura sugerido (D5).** En una organización no inscripta el sugerido es la suma de los importes de las líneas, sin IVA agregado (la interfaz muestra "Total" y oculta "IVA sugerido"); sigue siendo editable. `compra.total_neto` conserva su nombre y en esa organización significa *total de costo*, con el IVA pagado incluido. La deuda sigue siendo el total de factura (ADR-043).
6. **Importación de costos (D6).** Para un responsable inscripto nada cambia: `incluye_iva` obligatoria (`S`/`N`; vacía es `VALOR_OBLIGATORIO`, otro texto `VALOR_INVALIDO`). Para uno no inscripto la columna es opcional: vacía o `N` se aceptan y `S` se rechaza en la fila con `INCLUYE_IVA_NO_APLICA`, con la regla de todo o nada (ADR-040). Es la misma regla que el alta individual. La plantilla explica "valor pagado". El costo del stock inicial, por unidad base, no cambia: para un monotributista es el pagado.
7. **Cambio de condición (D7).** Comando `ORGANIZACION_CONDICION_IVA_CAMBIAR` v1 (`ONLINE`), permiso `ADMIN_CONFIGURACION` (sin permiso nuevo), con una sola auditoría del bus (valor anterior y nuevo, AUD-01). No es retroactivo. Mismo valor: `CONDICION_IVA_SIN_CAMBIO`. Pasar a no inscripto con modo distinto de `A` o con modalidad definida: `MODO_IMPOSITIVO_INCOMPATIBLE`. Pasar a inscripto deja modo A y modalidad sin definir. Mismo `operation_id` y misma huella devuelven el resultado original (INV-06).
8. **Lectura de la condición (D8).** `GET /api/v1/configuracion/fiscal` devuelve `condicion_iva`, `computa_credito_fiscal`, `modo_impositivo` y `modalidad_iva_default` de la organización del token, a cualquier usuario autenticado (INV-21). `GET /api/v1/yo` no cambia (contrato cerrado del change 06b). La pantalla `/admin/configuracion/fiscal` muestra la condición y, con `ADMIN_CONFIGURACION`, permite cambiarla tras una confirmación.
9. **Valor inicial (D9).** La migración pone `RESPONSABLE_INSCRIPTO` a toda organización existente (sus costos y compras ya se calcularon con esa regla). La siembra de una organización inicial nueva usa `MONOTRIBUTO`, modo `A` y modalidad sin definir. La organización de desarrollo pasa a `MONOTRIBUTO` con el comando de D7, auditado.
10. **Costos vigentes al cambiar (D10).** Los costos informados vigentes calculados con la regla anterior siguen vigentes (CST-03). `GET /api/v1/costos/resumen-regla-iva?fecha=` (`ADMIN_CONFIGURACION` o `EDITAR_COSTOS`) cuenta, con SQL en la base, los costos vigentes por regla; la confirmación del cambio informa cuántos conviene volver a informar. No hay recálculo ni costos automáticos (CMP-04). **Es insumo del change 13** (precios, PRC-11): antes de fijar precios con un costo vigente hay que saber con qué regla se calculó.
11. **Dueño de la regla y dependencias.** `identidad` (dueño de `configuracion_organizacion`) expone `obtener_condicion_iva`, `organizacion_computa_credito_fiscal` y `cambiar_condicion_iva` en `service.py`, y la función pura en `domain/valores.py`. `proveedores` e `importacion` leen la condición **solo** por `identidad/service.py` (import-linter). `importacion` sigue registrando por `proveedores.informar_costos`, que valida D4.
12. **Bloqueos.** `cambiar_condicion_iva` toma `configuracion_organizacion FOR UPDATE`; `COSTO_INFORMAR` y `COMPRA_CONFIRMAR` leen la condición `FOR SHARE` al inicio. Una compra concurrente con el cambio usa una sola regla de punta a punta y dos cambios simultáneos al mismo valor dan uno aceptado y otro `CONDICION_IVA_SIN_CAMBIO`.
13. **Modelo de datos.** Una revisión de Alembic agrega las tres columnas y las restricciones de D2 y D3; `downgrade` las quita. Los permisos de `app_runtime` no cambian de forma que afecte a los libros (INV-05).
14. **Estados HTTP de los errores nuevos (aprobado durante el apply).** `CONDICION_IVA_SIN_CAMBIO` y `MODO_IMPOSITIVO_INCOMPATIBLE`: 409. Un valor de condición fuera del dominio cerrado: 422. `INCLUYE_IVA_NO_APLICA`: 422. Falta de `ADMIN_CONFIGURACION`: 403 `PERMISO_REQUERIDO`.
15. **Columna vacía en la importación de un inscripto (aprobado durante el apply).** El error es `VALOR_OBLIGATORIO` (no `VALOR_INVALIDO`); un valor no vacío distinto de `S`/`N` conserva `VALOR_INVALIDO`.

## Consecuencias

- Un monotributista carga lo que pagó y el costo base, el promedio y la deuda reflejan el IVA como costo; un responsable inscripto no ve ningún cambio (los fixtures de CST-02 y CMP-02 pasan intactos con `computa_credito_fiscal = true`).
- La historia queda reconstruible: cada costo y cada línea de compra dicen con qué regla se calcularon, y el historial y el detalle de compra muestran "IVA descontado: Sí/No" desde la columna congelada.
- La facturación (Factura C para un monotributista) y los changes 13 y 18a parten de una organización cuyo modo es `A` y cuya modalidad de IVA no existe si no es inscripta.
- Quien cambie de condición debe revisar los costos vigentes calculados con la otra regla antes de que el change 13 fije precios.
- Idea futura sin change asignado: un reporte de facturación de los últimos 12 meses contra el tope de la categoría del monotributo.
- Pregunta abierta no bloqueante: si los proveedores inscriptos facturan con el IVA discriminado o como total único; la interfaz funciona igual porque se carga el valor pagado por presentación.

## Alternativas consideradas

- **Un booleano `computa_credito_fiscal` sin la condición (B de D1):** descartada: pierde el dato que necesita la facturación.
- **Un modo impositivo nuevo `M` (C de D1):** descartada: mezcla cómo se venden los precios con lo que se recupera en compras.
- **Guardar modo y modalidad como están e ignorarlos (B de D2) o volverlos nulables (C de D2):** descartadas: dejan datos que dicen algo que el sistema no hace, o rompen el `NOT NULL` que leen los changes 13 y 18a.
- **Sin columna congelada, guardando `incluye_iva = false` (B de D3) o la condición en la cabecera (C de D3):** descartadas: no dejan rastro de por qué no se descontó el IVA ni permiten un `CHECK` por fila.
- **Aceptar e ignorar `incluye_iva = true` (B de D4) o ignorar la columna de la planilla (B de D6):** descartadas: engañan a quien cree que se descontó un IVA que no se descontó.
- **Seguir sugiriendo neto más IVA (B de D5):** descartada: duplica el IVA en la deuda.
- **Un permiso nuevo `CAMBIAR_CONDICION_IVA` (B de D7) o cambiar por SQL de operador (C de D7):** descartadas: más superficie para un cambio poco frecuente, o sin auditoría.
- **Agregar `condicion_iva` a `GET /yo` (B de D8):** descartada: reabre un contrato cerrado en el change 06b.
- **Migrar la organización inicial a `MONOTRIBUTO` (B de D9) o todas (C de D9):** descartadas: la migración tomaría una decisión de negocio sin auditoría y dejaría lo previo incoherente.
- **Bloquear el cambio con costos de la otra regla (B de D10) o regenerar costos automáticamente (C de D10):** descartadas: demasiado rígido, o contradice CMP-04.
