# Diseño técnico — 20c-catalogos-de-configuracion

> **Estado: APROBADAS (2026-10-30, opción A en D0 a D15, tras la explicación de D9 y D10). Los seis textos de ayuda de D14 quedaron aprobados tal como están escritos (tarea 0.2).** Cada decisión trae dos o tres opciones, sus consecuencias y la recomendada, que fue la elegida. Lo aprobado se documenta en **ADR-061** (borrador *Propuesto* en `docs/adr/ADR-061-catalogos-de-configuracion.md`) y en `propuesta-docs.md`.
>
> **Gobernanza del change: BAJA** (`04` §9). Por decisión: **MEDIA:** D4, D6, D8, D9 (tocan reglas que usan otros módulos: anulaciones, ajustes, productos, importación). **BAJA:** el resto. **De negocio** (el agente solo recomienda; decide el usuario): **D1, D2, D4, D5, D6, D8, D10, D11**.
>
> **Revisión.** El usuario revisa con todo el change implementado; no se frena entre lotes.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **`configuracion`** (changes 02, 11, 17b): tablas `alicuota_iva` (`nombre`, `valor numeric(9,6)`, `activo`, `creado_en`, `actualizado_en`, `actualizado_por_id`), `motivo` (`ambito`, `nombre`, `activo`, mismos sellos) y `medio_pago`. `alicuota_iva` y `motivo` tienen `UNIQUE (organizacion_id, id)` y **ninguna** unicidad de nombre ni de valor. `ck_motivo__ambito` fija la lista cerrada de diez ámbitos (`AMBITOS_MOTIVO` en `domain/valores.py`). `app_runtime` tiene `SELECT, INSERT, UPDATE` sin `DELETE` sobre las tres. `service.py` ya tiene `crear_alicuota`, `desactivar_alicuota`, `obtener_alicuota_por_id`, `buscar_alicuotas_por_valor` (importación, IMP-04), `crear_motivo`, `obtener_motivo`, `listar_motivos_por_ambito`, `desactivar_motivo`, y validadores puros (`validar_ambito_motivo`, `validar_valor_alicuota`: `Decimal`, no negativo, hasta 6 decimales). **No hay comandos** de motivos ni de alícuotas.
- **Patrón de medios de pago (17b, ADR-053)**: `MEDIO_PAGO_CREAR` y `MEDIO_PAGO_MODIFICAR` (reemplazo completo, incluido `activo`), `NOMBRE_INVALIDO` 422, `NOMBRE_DUPLICADO` 409 (traducido desde el índice único `lower(nombre)`), `ULTIMO_MEDIO_ACTIVO` 409 con bloqueo `FOR UPDATE` de los medios de la organización antes de contar, lectura `/todos` con `ADMIN_CONFIGURACION`, dos filas de auditoría por comando (la del bus y la de la entidad con antes y después), pestaña en Configuración. Este change lo **repite** para motivos y alícuotas.
- **Lecturas actuales:** `GET /configuracion/motivos?ambito=` (activos, cualquier sesión, ADR-043); `GET /configuracion/alicuotas` (paginada, activas e inactivas, con `GESTIONAR_CATALOGO` o `REGISTRAR_COMPRA`).
- **Quién usa motivos:** ajuste de stock (STK-08), anulaciones de compra, pago, cobranza, venta, transferencia y ajuste, liberación de jornada (RUT-09), descuento manual (DSC-06, obligatorio si la organización lo exige) y lista anterior (PRC-21, obligatorio por defecto). Todos validan "motivo activo del ámbito" y guardan solo el `motivo_id`.
- **Quién usa alícuotas:** el producto (`alicuota_id`, CAT-01; `catalogo/service.py::_resolver_alicuota_activa` rechaza una inactiva en el alta y en **toda** modificación del producto), la importación (por porcentaje, IMP-04), la compra (congela `alicuota_aplicada`) y la venta (congela `alicuota`). Ninguna operación confirmada relee el valor.
- **Redondeo por defecto:** `configuracion_organizacion.redondeo_multiplo numeric(14,2)` y `redondeo_direccion` ya existen, nulos, con `CHECK` de la dirección pero **sin** `CHECK` de múltiplo positivo ni de coherencia "los dos o ninguno". La tabla vive en `identidad` (como los demás parámetros: `NOTA_VENTA_CONFIGURAR`, `ORGANIZACION_DATOS_CONFIGURAR`, `CREDITO_ORGANIZACION_CONFIGURAR`, todos en `identidad/commands.py` con `ADMIN_CONFIGURACION`). `identidad/domain/valores.py` ya tiene `validar_redondeo_direccion`. El formulario de lista nueva (`ListaFormScreen.tsx`) precarga hoy **100 / ARRIBA fijos en el código**.
- **Verificador de uso (ADR-023, CAT-04):** `catalogo/service.py::registrar_verificador_uso` es el precedente de un puerto que el módulo de abajo expone y el de arriba registra, sin romper `lint-imports` (`catalogo` importa `configuracion`, nunca al revés).

Lo que `docs/` **no** resuelve (cada punto es una decisión): quién administra (D1); qué se edita de un motivo y de una alícuota (D2, D6); unicidad (D3, D7); reglas de la baja (D4, D8); qué ámbitos se administran (D5); cómo sabe `configuracion` que un producto usa una alícuota (D9); el comando del redondeo y qué precarga el formulario sin redondeo (D10, D11); pantallas, auditoría y ayuda (D12 a D14); lo que necesita el 21 (D15).

## Goals / Non-Goals

**Goals:** que un administrador cree, renombre, dé de baja y reactive motivos y alícuotas desde `/admin`, por el bus, sin borrar nada y sin dejar una operación imposible (un ámbito sin motivos, un producto con alícuota de baja); que defina el redondeo por defecto y la lista nueva lo precargue.

**Non-Goals:** ámbitos nuevos; cambiar el porcentaje de una alícuota existente ni pasar productos en masa a otra; tocar listas existentes; bootstrap y uso sin conexión (21, 22a); reportes por motivo (26).

## Decisions

### D0 — Tamaño y lotes · alcance · BAJA

**APROBADA 2026-10-30, opción A.**

- **A (recomendada). Un change en tres lotes**, sin frenar entre lotes: **Lote 1** migración y motivos (backend); **Lote 2** alícuotas y redondeo por defecto (backend); **Lote 3** pantallas, ayuda, concurrencia, cobertura, ADR, docs y prueba manual. Consecuencia: entra en `04` §2 (dos a tres días); un ADR y una prueba manual.
- **B. Dos changes** (20c motivos y alícuotas; 20d redondeo). Consecuencia: el redondeo es chico y quedaría un change de medio día; el 21 solo espera al primero.
- **C. Un lote único.** Consecuencia: sin cortes naturales para el resumen de comprobaciones.

### D1 — Quién administra · negocio · BAJA · ADR-061

**APROBADA 2026-10-30, opción A.**

**Contexto.** `01` §19: `ADMIN_CONFIGURACION` = "Configuración de la organización" (solo Administrador); `GESTIONAR_CATALOGO` (Administrador y Administración) lee hoy las alícuotas para los productos; `GESTIONAR_LISTAS` (Administrador y Administración) incluye "redondeo" de las listas.

- **A (recomendada). `ADMIN_CONFIGURACION` para los tres** (motivos, alícuotas y redondeo por defecto), y `01` §19 lo nombra. Consecuencia: sin permiso nuevo; las tres pestañas van en "Configuración", como medios de pago (ADR-053); Administración no las toca.
- **B. Repartido:** motivos con `ADMIN_CONFIGURACION`, alícuotas con `GESTIONAR_CATALOGO` y redondeo por defecto con `GESTIONAR_LISTAS`. Consecuencia: Administración podría crear alícuotas y cambiar el redondeo por defecto; tres permisos distintos para una misma área.
- **C. Permiso nuevo `GESTIONAR_CATALOGOS_CONFIGURABLES`.** Consecuencia: agrega un permiso al catálogo (migración, plantillas, `01` §19) para tres pantallas chicas.

### D2 — Comandos de motivos y qué se cambia · negocio · BAJA · ADR-061

**APROBADA 2026-10-30, opción A.**

- **A (recomendada). `MOTIVO_CREAR` (ámbito, nombre) y `MOTIVO_MODIFICAR` (reemplazo completo: nombre y activo)**, v1, solo `ONLINE`, igual que medios de pago. El **ámbito no cambia** después del alta (un motivo usado en anulaciones de venta no puede pasar a ajustes). Renombrar está permitido: las operaciones guardan el id y muestran el nombre nuevo. El nombre se recorta; vacío o de solo espacios → `NOMBRE_INVALIDO` (422). Ámbito fuera de la lista → `AMBITO_INVALIDO` (422, el mismo código de la lectura por ámbito; el validador puro existente usa `CONFIGURACION_AMBITO_MOTIVO_INVALIDO` y la ruta lo traduce). Ajeno o inexistente → 404. Un motivo nace activo.
- **B. Como A, pero el ámbito también se modifica.** Consecuencia: la historia de un ámbito quedaría con motivos de otro; las validaciones de "motivo del ámbito" dejarían de describir lo que pasó.
- **C. Como A, pero sin renombrar una vez usado.** Consecuencia: protege la lectura de la historia, pero una falta de ortografía obliga a crear otro y dar de baja el viejo.

### D3 — Nombre único de motivo · técnica · BAJA

**APROBADA 2026-10-30, opción A.**

- **A (recomendada). Único por organización y ámbito, sin distinguir mayúsculas, activo o no** (`ux_motivo__nombre` sobre `(organizacion_id, ambito, lower(nombre))`; `NOMBRE_DUPLICADO` 409). "Otro" puede existir en cada ámbito (la siembra ya lo hace). La migración aborta con la lista si hay repetidos. Consecuencia: un motivo de baja con el mismo nombre se reactiva, no se duplica.
- **B. Único solo entre los activos** (índice parcial). Consecuencia: dos "Rotura" en la historia, una de baja.
- **C. Sin unicidad.** Consecuencia: dos "Rotura" iguales en el desplegable del ajuste.

### D4 — Reglas de la baja de motivos · negocio · MEDIA · ADR-061

**APROBADA 2026-10-30, opción A.**

**Contexto.** CAT-05/TR-06: no se borra; los inactivos no se ofrecen y se leen por id. Casi todos los ámbitos exigen un motivo siempre (STK-08, CMP-05, PAG-03, COB-05, VTA-20, RUT-09); `DESCUENTO_MANUAL` y `LISTA_ANTERIOR` solo si la organización lo exige.

- **A (recomendada). Baja y reactivación libres, salvo que el ámbito se quede sin ningún motivo activo** (`ULTIMO_MOTIVO_ACTIVO`, 409), en los diez ámbitos por igual. Para que dos bajas simultáneas no dejen cero, el comando bloquea `FOR UPDATE` los motivos de ese ámbito de la organización antes de contar. Consecuencia: ninguna operación queda imposible por falta de motivo; regla simple, igual a la de medios.
- **B. Como A, pero solo en los ámbitos donde el motivo es obligatorio en ese momento.** Consecuencia: el resultado dependería de la configuración (`motivo_obligatorio_descuento`, `motivo_obligatorio_lista`); si después se vuelve obligatorio, el ámbito puede estar vacío.
- **C. Sin restricción.** Consecuencia: se puede dejar sin motivos `AJUSTE_STOCK` y nadie puede ajustar stock hasta reactivar uno.

**Sin conexión.** Un teléfono que guardó un motivo luego dado de baja: el descuento manual ya lo marca con `DESCUENTO_DIFIERE` causa `MOTIVO` (DSC-09). La lista anterior y las demás operaciones sin conexión llegan con el 22: se nomina al 22a/22c (Open Questions).

### D5 — Qué ámbitos se administran · negocio · BAJA

**APROBADA 2026-10-30, opción A.**

- **A (recomendada). Los diez de la lista cerrada**, con la lista **fija** (los ámbitos son del sistema: cada uno corresponde a una operación del código; TR-09 se cumple con los motivos, no con los ámbitos). La pantalla los nombra en castellano ("Ajuste de stock", "Anulación de venta"…).
- **B. Solo `AJUSTE_STOCK`**, el único que `01` §4 nombra. Consecuencia: las anulaciones, la liberación de jornada, el descuento manual y la lista anterior siguen sin poder agregar motivos (deuda del 18b sin saldar).
- **C. Los diez y además ámbitos nuevos definidos por la organización.** Consecuencia: un ámbito sin operación que lo use no sirve; exigiría cambiar `ck_motivo__ambito` y el código.

### D6 — Qué se edita de una alícuota · negocio · MEDIA · ADR-061

**APROBADA 2026-10-30, opción A.**

**Contexto.** El producto apunta a la alícuota por id; las compras y ventas confirmadas congelan el porcentaje. Cambiar el valor de una alícuota existente cambiaría, desde ese momento y sin aviso, el IVA de todos sus productos: en una organización que computa crédito fiscal, el costo base de las compras (CST-02, CMP-02); en modo B, el IVA de la venta (VTA-04); y la importación (IMP-04) la busca por porcentaje.

- **A (recomendada). `ALICUOTA_CREAR` (nombre, valor) y `ALICUOTA_MODIFICAR` (reemplazo completo de nombre y activo; el valor no cambia)**, v1, solo `ONLINE`. Para otra tasa se crea una alícuota nueva, se pasan los productos (editándolos) y se da de baja la vieja. Errores: `NOMBRE_INVALIDO` 422, `CONFIGURACION_VALOR_ALICUOTA_INVALIDO` 422 (código existente), `NOMBRE_DUPLICADO` y `VALOR_DUPLICADO` 409 (D7), `ALICUOTA_EN_USO` y `ULTIMA_ALICUOTA_ACTIVA` 409 (D8), ajena → 404. Un `valor` distinto del guardado en `ALICUOTA_MODIFICAR` → `VALOR_NO_MODIFICABLE` (422).
- **B. El valor también se modifica.** Consecuencia: un cambio de tasa es un solo paso, pero cambia en silencio el cálculo de compras y ventas futuras de todos sus productos; la historia confirmada no cambia (está congelada).
- **C. Solo alta y baja** (sin renombrar). Consecuencia: corregir "10.5%" a "10,5%" obliga a crear otra y mover los productos.

### D7 — Unicidad y dominio del valor · técnica · BAJA

**APROBADA 2026-10-30, opción A.**

- **A (recomendada).** Nombre único por organización sin distinguir mayúsculas (`ux_alicuota_iva__nombre`) y **valor único por organización, activa o no** (`ux_alicuota_iva__valor` sobre `(organizacion_id, valor)`), para que la importación por porcentaje (IMP-04) no sea ambigua. Valor: fracción `0 <= valor < 1` con hasta 6 decimales (TR-02), viaja como string (`"0.105000"`, INV-03); `CHECK (valor >= 0 AND valor < 1)`. La pantalla lo pide como porcentaje ("10,5") y lo convierte a fracción con `decimal.js` sin redondear (una división exacta por 100; más de 4 decimales en el porcentaje → inválido). La migración aborta si ya hay nombres o valores repetidos (la siembra no los tiene).
- **B. Solo nombre único.** Consecuencia: dos alícuotas de 21 %; la importación responde ambigua.
- **C. Valor único solo entre activas.** Consecuencia: una de 21 % de baja y otra activa; la importación debe elegir.

### D8 — Reglas de la baja de una alícuota · negocio · MEDIA · ADR-061

**APROBADA 2026-10-30, opción A.**

**Contexto.** Hoy un producto con alícuota inactiva no se puede modificar (cualquier cambio exige alícuota activa), aunque solo se le cambie el nombre.

- **A (recomendada). No se da de baja una alícuota que usa algún producto activo** (`ALICUOTA_EN_USO`, 409, con la cantidad de productos), **ni la última activa** (`ULTIMA_ALICUOTA_ACTIVA`, 409). Los productos inactivos no lo impiden (si se reactivan, piden otra alícuota). La baja bloquea `FOR UPDATE` la alícuota y las activas de la organización; el alta y la modificación de un producto leen su alícuota con `FOR SHARE`, así no se cruzan (D9). Consecuencia: ningún producto activo queda con una alícuota de baja.
- **B. Baja libre;** los productos la conservan y deben cambiarla en su próxima edición. Consecuencia: el caso "no puedo editar el nombre de un producto por su alícuota" que hoy no ocurre empezaría a ocurrir.
- **C. Baja que pasa los productos a otra alícuota elegida.** Consecuencia: un cambio masivo de productos dentro de un comando de configuración; fuera del alcance (`proposal.md`, No incluye).

### D9 — Cómo sabe `configuracion` que un producto usa una alícuota · técnica · MEDIA

**APROBADA 2026-10-30, opción A.**

- **A (recomendada). Puerto registrado (precedente ADR-023):** `configuracion/service.py` expone `registrar_verificador_uso_alicuota(nombre, funcion)` y `contar_productos_activos_con_alicuota`; `catalogo` registra su función, que cuenta en SQL. `catalogo/service.py::_resolver_alicuota_activa` pasa a leer con `FOR SHARE` por una función nueva de `configuracion/service.py`. Consecuencia: `configuracion` no importa `catalogo`; contratos de `lint-imports` sin cambios.
- **B. El handler de `ALICUOTA_MODIFICAR` vive en `catalogo`.** Consecuencia: un comando de configuración en el módulo de productos.
- **C. SQL sobre `producto` desde `configuracion/repository.py`.** Consecuencia: rompe la regla de módulos (`CLAUDE.md` §4).

### D10 — Comando del redondeo por defecto · negocio · BAJA · ADR-061

**APROBADA 2026-10-30, opción A.**

- **A (recomendada). `REDONDEO_POR_DEFECTO_DEFINIR` v1**, solo `ONLINE`, `ADMIN_CONFIGURACION` (D1), en `identidad` como los demás parámetros. Contenido `{multiplo: string | null, direccion: "ARRIBA" | "CERCANO" | "ABAJO" | null}`: los dos o ninguno (los dos nulos = vuelve a "sin definir"). Mismo dominio que la lista (PRC-01, PRC-14): múltiplo mayor que cero con hasta dos decimales (`REDONDEO_INVALIDO`, 422, el código que ya usa `precios`; la dirección inválida también responde `REDONDEO_INVALIDO`, y el validador de `identidad`, que hoy usa `IDENTIDAD_REDONDEO_DIRECCION_INVALIDA`, se alinea). Migración: `CHECK ((redondeo_multiplo IS NULL) = (redondeo_direccion IS NULL))` y `CHECK (redondeo_multiplo > 0)`. **No** toca listas existentes ni el cálculo del precio. Consecuencia: sin fixtures compartidos.
- **B. Como A, pero una vez definido no se puede vaciar.** Consecuencia: no hay forma de volver a "sin definir".
- **C. Solo el múltiplo, con dirección fija `ARRIBA`.** Consecuencia: contradice `01` §4 ("múltiplo y dirección").

### D11 — Qué precarga el formulario y quién lo lee · negocio · BAJA

**APROBADA 2026-10-30, opción A.**

**Contexto.** `01` §4: "solo precarga el formulario de una lista nueva cuando esté definido". Hoy el formulario trae 100 / ARRIBA escritos en el código. Quien crea listas tiene `GESTIONAR_LISTAS` (también Administración, sin `ADMIN_CONFIGURACION`).

- **A (recomendada).** Lectura `GET /configuracion/redondeo-por-defecto` con `ADMIN_CONFIGURACION` **o** `GESTIONAR_LISTAS` (`multiplo` y `direccion`, o nulos). Definido → el formulario de lista nueva lo precarga. **Sin definir → múltiplo vacío y dirección sin elegir** (obligatorios, PRC-01): se quita el 100 / ARRIBA del código. La edición de una lista existente muestra siempre su propio redondeo.
- **B. Como A, pero sin definir sigue precargando 100 / ARRIBA.** Consecuencia: el valor fijo en el código convive con el parámetro; quien no lo define no nota diferencia.
- **C. Sin lectura nueva:** el redondeo viaja en `GET /yo` o en la lectura de configuración existente. Consecuencia: mezcla un dato de precios con la sesión o exige `ADMIN_CONFIGURACION` para leerlo.

### D12 — Pantallas y lecturas · interfaz · BAJA

**APROBADA 2026-10-30, opción A.**

- **A (recomendada).** Tres pestañas nuevas en Configuración, dentro de `SiTienePermiso("ADMIN_CONFIGURACION")`:
  - **"Motivos"** (`/admin/configuracion/motivos`): selector de ámbito con nombres en castellano; lista con nombre y estado; alta, cambio de nombre, baja y reactivación con confirmación; lectura `GET /configuracion/motivos/todos?ambito=` (activos e inactivos, por nombre; `ADMIN_CONFIGURACION`). `GET /configuracion/motivos` queda igual.
  - **"Alícuotas de IVA"** (`/admin/configuracion/alicuotas`): lista con nombre, porcentaje y estado; alta (nombre y porcentaje); cambio de nombre, baja y reactivación; `ALICUOTA_EN_USO` con la cantidad de productos. Lectura: la ruta existente `GET /configuracion/alicuotas` suma `ADMIN_CONFIGURACION` a sus permisos (ya devuelve activas e inactivas).
  - **"Redondeo por defecto"** (`/admin/configuracion/redondeo`): múltiplo y dirección, botón "Quitar" para dejarlo sin definir.
  Reintento con el mismo `Operation-Id`; al guardar se invalidan las consultas de motivos (`['motivos', ambito]`) y de alícuotas que usan las demás pantallas. Sin lógica de negocio en los componentes (los nombres de ámbitos y la conversión de porcentaje viven en `domain/configuracion/`).
- **B. Una sola pestaña "Catálogos"** con tres secciones. Consecuencia: una pantalla larga; el redondeo nada tiene que ver con motivos.
- **C. El redondeo en el área de listas de precios** (con `GESTIONAR_LISTAS`). Consecuencia: coherente con B de D1, no con A.

### D13 — Auditoría · trazabilidad · BAJA · AUD-01

**APROBADA 2026-10-30, opción A.**

- **A (recomendada).** Igual que medios de pago (`02` §6.5): por comando, la fila genérica del bus y la de la entidad (`motivo`, `alicuota_iva`, `configuracion_organizacion`) con `despues` en el alta y `antes` y `despues` en la modificación y en el redondeo. Un rechazo no deja cambios, solo la fila del comando rechazado.
- **B. Solo la fila del bus.** Consecuencia: no se sabe qué cambió (AUD-01 pide "cambios de configuración").

### D14 — Ayuda contextual · interfaz · BAJA · ADR-051

**APROBADA 2026-10-30, opción A.**

**A (recomendada).** Seis claves nuevas en `frontend/src/ayuda/textos.ts`, **sin ejemplos**, solo donde la regla no es obvia, sin tema "Ver más" (textos a aprobar en 0.2):

| Clave | Pantalla y campo | Reglas | Texto propuesto |
| --- | --- | --- | --- |
| `motivos.ambito` | Motivos · selector de ámbito | TR-09; ADR-061 | "Cada motivo sirve para un solo tipo de operación: los de un ámbito solo se ofrecen en esa operación. El ámbito no se cambia después de crear el motivo." |
| `motivos.nombre` | Motivos · "Nombre" | ADR-061 | "Si le cambiás el nombre, las operaciones anteriores que lo usaron muestran el nombre nuevo. No puede haber dos motivos con el mismo nombre en un ámbito." |
| `motivos.baja` | Motivos · "Dar de baja" | CAT-05; TR-06; ADR-061 | "Deja de ofrecerse en operaciones nuevas. No se borra: las anteriores lo siguen mostrando y lo podés volver a activar. Cada ámbito tiene que conservar al menos un motivo activo." |
| `alicuotas.valor` | Alícuotas · "Porcentaje" | TR-02; CAT-01; ADR-061 | "El porcentaje no se cambia una vez creada la alícuota. Si cambia la tasa, creá una nueva, pasá los productos a ella y dá de baja la anterior. Las compras y ventas ya hechas conservan el porcentaje con que se hicieron." |
| `alicuotas.baja` | Alícuotas · "Dar de baja" | CAT-05; ADR-061 | "Deja de ofrecerse al crear o editar productos. No se puede dar de baja mientras la use un producto activo, ni si es la última activa." |
| `configuracion.redondeoPorDefecto` | Redondeo por defecto | PRC-01; PRC-14; ADR-061 | "Es el redondeo que aparece cargado al crear una lista de precios nueva; en cada lista lo podés cambiar. Cambiarlo no modifica las listas que ya existen ni sus precios. Sin definir, la lista nueva empieza con el redondeo vacío." |

**B. Solo `motivos.baja`, `alicuotas.valor` y `configuracion.redondeoPorDefecto`.** Consecuencia: el ámbito fijo y la unicidad quedan sin explicar.

**Precisión de la spec de ayuda.** El requisito vigente "El texto es corto, trae un ejemplo y cita su regla" pide un ejemplo "cuando la regla tiene números"; ninguna de estas reglas tiene números, así que estos textos lo cumplen sin ejemplo (como los del 20b).

### D15 — Lo que necesita el 21 · contrato · BAJA

**APROBADA 2026-10-30, opción A.**

- **A (recomendada).** El 20c deja públicas en `configuracion/service.py`, sin ruta de bootstrap: `listar_motivos_activos(organizacion_id)` (todos los ámbitos, con `ambito` y `actualizado_en`) y `listar_alicuotas_activas`; y en `identidad/service.py` la lectura del redondeo por defecto. Se nomina al 21: bajar motivos y alícuotas activos (SYN-11), y al 22a/22c qué pasa con un motivo dado de baja usado sin conexión fuera del descuento manual.
- **B. Ruta `GET /configuracion/catalogos` ya en el 20c.** Consecuencia: un contrato público que el 21 quizá reemplace.

## Risks / Trade-offs

- **[D6-A: un cambio de tasa son varios pasos]** → la ayuda lo explica; la tasa casi no cambia (monotributo, `01` §4). Si se vuelve frecuente, un change aparte con "pasar productos a otra alícuota".
- **[D8-A: la baja de una alícuota se cruza con el alta de un producto]** → `FOR SHARE` en la lectura del producto y `FOR UPDATE` en la baja; prueba de concurrencia con commits reales.
- **[D4-A y D8-A: dos bajas simultáneas]** → bloqueo de los motivos del ámbito / de las alícuotas activas antes de contar; prueba de concurrencia.
- **[D11-A cambia el formulario de lista nueva]** → sin redondeo definido, el usuario lo carga a mano; la pantalla de redondeo por defecto lo resuelve una vez.
- **[Renombrar cambia cómo se lee la historia]** (D2-A, D6-A) → aceptado, como en medios de pago (ADR-053).
- **[La migración aborta si hay nombres o valores repetidos]** → mensaje con la organización y el valor; la siembra no los tiene.

## Migration Plan

Una revisión de Alembic sobre `f1a2b3c4d5e6` (change 20b): (1) verifica que no haya motivos repetidos por `(organizacion_id, ambito, lower(nombre))`, ni alícuotas repetidas por `lower(nombre)` o por `valor`, ni filas de configuración con el redondeo a medias o con múltiplo no positivo; si hay, aborta con la lista; (2) crea `ux_motivo__nombre`, `ux_alicuota_iva__nombre` y `ux_alicuota_iva__valor`; (3) agrega `ck_alicuota_iva__valor` (`valor >= 0 AND valor < 1`), `ck_configuracion_organizacion__redondeo_coherente` y `ck_configuracion_organizacion__redondeo_multiplo_positivo`. `downgrade` borra índices y `CHECK`; no hay datos que revertir. Sin columnas nuevas ni cambios de privilegios (`app_runtime` sigue sin `DELETE`).

## Open Questions

- Al 22a/22c: un motivo de `LISTA_ANTERIOR` (u otro ámbito) dado de baja que llega en un comando sin conexión. Hoy solo el descuento manual tiene su causa (`MOTIVO` en `DESCUENTO_DIFIERE`); la venta sin conexión con lista anterior no existe todavía.
