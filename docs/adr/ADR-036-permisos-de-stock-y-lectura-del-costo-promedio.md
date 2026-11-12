# ADR-036 — Permisos de stock: `IMPORTAR_DATOS` registra el stock inicial, `ADMIN_CONFIGURACION` administra ubicaciones, `TRANSFERIR_STOCK` lee stock y kardex y `VER_COSTOS` lee el costo, desde `catalogo`

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-30 |
| Referenciado en | `openspec/changes/09-stock-y-costeo/design.md` D1, D2 y D3 (con su enmienda del 2026-09-30) y `specs/stock/stock-inicial`, `specs/stock/ubicaciones`, `specs/stock/kardex`, `specs/costeo/costo-promedio`, `specs/stock/administracion-de-stock`; `01-dominio.md` §19 (permisos) y §21 (stock inicial); `02-arquitectura.md` §5.3; ADR-027 (permisos efectivos); ADR-033 (permisos de cuenta corriente) |

**Decisiones D1, D2 y D3 (opción A en cada una) y la enmienda a D3 (ruta del costo en `catalogo`) aprobadas por el usuario el 2026-09-30, junto con las aclaraciones de implementación de los puntos 5 a 7. Texto del ADR aprobado por el usuario el 2026-09-30; estado *Vigente*.**

## Contexto

`01` §19 lista los permisos del sistema, pero no tiene uno para registrar un stock inicial, ni para administrar ubicaciones, ni para ver el stock, el kardex o el costo promedio. El change 09 introduce las capacidades: los comandos `STOCK_INICIAL_REGISTRAR`, `UBICACION_CREAR` y `UBICACION_MODIFICAR` (solo online, `02` §6.5), las lecturas de ubicaciones, saldos y kardex y la lectura del costo promedio vigente de un producto. El bus declara un permiso por tipo de comando y el ratchet de rutas exige un permiso por ruta, así que había que elegir cuáles.

Se registra como ADR porque el reparto afecta a más de un change: el change 10 (importación) cargará el stock inicial por el mismo camino, y los changes 11, 14, 15, 18a y 26 leen o muestran stock y costos con sus propios permisos. La enmienda, además, agrega una dependencia entre módulos que `02` §5.3 no listaba (`catalogo -> costeo`).

## Decisión

1. **Registrar un stock inicial** (`STOCK_INICIAL_REGISTRAR`) exige `IMPORTAR_DATOS` ("Importaciones y puesta en marcha", `01` §19), igual que el saldo inicial (ADR-033). Un stock inicial cambia stock y promedio sin que haya una compra detrás: es una tarea de puesta en marcha, no de operación diaria.
2. **Administrar ubicaciones** (`UBICACION_CREAR` y `UBICACION_MODIFICAR`, incluida su desactivación) exige `ADMIN_CONFIGURACION`: las ubicaciones son estructura de la organización, se cambian rara vez y un vehículo nuevo condiciona jornadas (RUT-01) y tomas.
3. **Leer stock** exige `TRANSFERIR_STOCK`: `GET /api/v1/stock/ubicaciones`, `GET /api/v1/stock/ubicaciones/{id}/saldos` y `GET /api/v1/stock/kardex`. Quien mueve stock necesita verlo.
4. **Ver costos.** Los campos de costo de esas respuestas (`costo_unitario` de cada movimiento del kardex y `costo_promedio` de cada línea de stock) **se omiten** si el usuario no tiene `VER_COSTOS` (`01` §19: el vendedor "no ve costos"). El costo promedio vigente de un producto se lee en una ruta propia con `VER_COSTOS`.
5. **La ruta del costo vive en `catalogo`:** `GET /api/v1/catalogo/productos/{producto_id}/costo`. `catalogo` resuelve primero el producto en la organización del token (404 si no existe o es de otra organización, INV-21, SEG-07, sin revelar nada) y después llama a `costeo/service.py`. Un producto sin ingresos con costo responde 200 con `costo_promedio` nulo y `stock_total` 0 (ADR-039). `costeo` no importa a `catalogo`: no hay ciclo. Es el mismo criterio que ADR-035 punto 5 (las lecturas viven con su entidad): `costeo` no puede distinguir por sí solo un producto inexistente (404) de uno sin ingresos (200 con nulo) sin depender de `catalogo`. `stock` sigue sirviendo ubicaciones, saldos y kardex.
6. **Las respuestas de saldos y kardex incluyen** `producto_codigo` y `producto_nombre` (y el kardex, `unidades_referencia`, para mostrar cajas + unidades, CAT-08). Un Vendedor (`TRANSFERIR_STOCK`, sin acceso al catálogo) puede así leerlas sin consultar `GET /catalogo/productos`.
7. **No se agrega ningún permiso nuevo** al catálogo `permiso`: no hay migración de permisos ni cambio de plantillas de rol.

## Consecuencias

- Con las plantillas actuales, solo el Administrador (ADM) registra un stock inicial y administra ubicaciones. Administración (GES) no puede, salvo que la organización agregue `IMPORTAR_DATOS` o `ADMIN_CONFIGURACION` a su rol: es un cambio de plantilla, no de código.
- Con las plantillas actuales, ADM, GES, SUP y VEN leen stock y kardex; el rol Consulta/Dirección (CON) no los ve en `/admin` (le llegarán por reportes, `VER_REPORTES`, change 26). Como la sección "Stock" del menú de `/admin` se muestra con `TRANSFERIR_STOCK`, **el Vendedor ve el menú "Stock"** (ubicaciones, saldos y kardex sin costos); no ve la acción de stock inicial ni el costo.
- **El selector de productos del formulario de stock inicial usa `GET /api/v1/catalogo/productos`, que exige `GESTIONAR_CATALOGO`.** Se acepta porque solo el Administrador tiene `IMPORTAR_DATOS` y también tiene `GESTIONAR_CATALOGO`. Si una organización le da `IMPORTAR_DATOS` a un rol sin `GESTIONAR_CATALOGO`, ese rol verá el formulario pero no podrá elegir productos: habría que agregar una lectura propia de productos para la puesta en marcha.
- La respuesta de saldos y de kardex depende de un segundo permiso (`VER_COSTOS`): se prueba con Administrador y con Vendedor. El tipo generado del OpenAPI marca los campos de costo como opcionales.
- Se agrega la dependencia `catalogo -> costeo` a `02` §5.3 (hoy dice `cuentas_corrientes, costeo, catalogo ──► (sin dependencias de negocio)`). Se registra el texto exacto en `propuesta-docs.md`. El contrato de import-linter lo permite y prohíbe la inversa.
- Si más adelante se necesita que otro rol cargue o vea stock o costos sin heredar el resto de los permisos, se agrega un permiso nuevo en `01` §19 con su migración del catálogo; hoy no hay motivo.

## Alternativas consideradas

- **`AJUSTAR_STOCK` para registrar el stock inicial** (ADM, GES): descartada: un ajuste no toca el promedio (CST-12) y el stock inicial sí (CST-11): mezcla dos poderes distintos.
- **Permiso nuevo `REGISTRAR_STOCK_INICIAL`:** descartada: agrega un permiso y una migración del catálogo para una tarea que se hace una vez en la vida de la organización.
- **`GESTIONAR_CATALOGO` o un permiso nuevo `GESTIONAR_UBICACIONES` para las ubicaciones:** descartadas: la primera haría que el catálogo de productos gobernara la estructura de stock; la segunda exige decidir su reparto por rol sin una necesidad concreta.
- **`VER_REPORTES` para leer stock y kardex:** descartada: el vendedor no vería el stock del depósito antes de cargar el vehículo.
- **Permiso nuevo `VER_STOCK`:** descartada: agrega permiso y migración sin necesidad concreta.
- **La ruta del costo en `costeo` (`GET /api/v1/costeo/productos/{id}`):** descartada (era la redacción original de D3): obligaba a `costeo` a depender de `catalogo` para responder 404 a un producto inexistente, o a responder 200 con nulo para cualquier id, revelando nada pero mezclando "no existe" con "sin ingresos".
