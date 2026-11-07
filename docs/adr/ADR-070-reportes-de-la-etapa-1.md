# ADR-070 — Reportes de la etapa 1: ventas por período con utilidad según permiso, rendición por vendedor y jornada, saldos, observaciones por vendedor y ajustes por motivo

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-11-07 |
| Referenciado en | `openspec/changes/26-reportes-etapa-1/design.md` D0 a D14 y `specs/reportes/area-de-reportes`, `specs/reportes/ventas-por-periodo`, `specs/reportes/rendicion-por-vendedor`, `specs/reportes/saldos-de-cuentas`, `specs/reportes/observaciones-por-vendedor`, `specs/reportes/ajustes-por-motivo`, `specs/sistema/ayuda-contextual`; `01-dominio.md` REP-01 a REP-05, TR-04, CC-04, RUT-07, `01` §19, INV-02, INV-03, INV-10, INV-13, INV-14, INV-21; `02-arquitectura.md` §5.2, §5.3, §11, §14, §20; `03-modelo-de-datos.md` §16; ADR-033, ADR-036, ADR-046, ADR-048, ADR-054, ADR-058, ADR-068, ADR-069 |

**Change 26. Gobernanza: sin decisiones CRÍTICAS (solo lectura); D2, D3, D5, D7 y D8 ALTAS. Decisiones aprobadas por el usuario el 2026-11-06 (tarea 0.1): todas las opciones A salvo D8 = B. Textos y ayudas aprobados el mismo día (tarea 0.2). D14 (paginación y orden de las listas) y sus tres textos, aprobados el 2026-11-07 tras la prueba manual (20.1). Pasa a *Vigente* al archivar.**

## Contexto

`VER_REPORTES` existe desde el change 03 y no abre ninguna pantalla: Consulta/Dirección no tiene nada que mirar (ADR-033 y ADR-036 le prometen los saldos por reportes). REP-02 y REP-04 piden excluir las anuladas e informar la utilidad real solo con `VER_UTILIDAD`. Seis changes dejaron deudas al 26: saldos de proveedores (12), ajustes por motivo (14), utilidad y líneas sin costo (18a), anuladas aparte (19), rendición por vendedor y jornada (24) y observaciones por vendedor (25). `docs/` no fija el período por defecto, a qué período va una anulación posterior, qué desgloses entran sin pisar REP-06, qué referencia vale para las cajas equivalentes, quién ve el costo vendido, cómo entran las líneas sin costo ni el IVA absorbido (la tabla `ajuste_iva_absorbido` todavía no existe), ni si `VER_REPORTES` alcanza para los saldos de proveedores.

## Decisión propuesta (aprobada en 0.1 el 2026-11-06: opciones A de `design.md` salvo D8 = B)

1. **Alcance (D0).** Un change en seis lotes, un subagente por lote.
2. **Período (D1).** Fechas de negocio inclusivas en la zona de la organización; sin fechas, el mes en curso según el reloj del servidor; tope de 366 días (`PERIODO_DEMASIADO_LARGO`, 422); rango invertido `RANGO_DE_FECHAS_INVALIDO`.
3. **Anuladas (D2).** Por la fecha de la venta: fuera de todo total y desglose de su período, aunque se anulen después, y en una sección aparte con la fecha y el motivo de la anulación.
4. **Desgloses (D3).** Resumen, por día, por vendedor y por producto; utilidad en el resumen, por día y por vendedor; por producto solo cantidades y neto (la utilidad por producto es REP-06, etapa 2).
5. **Cantidades (D4).** Cajas equivalentes con las `unidades_referencia` congeladas de cada línea, suma exacta en la base y dos decimales «mitad hacia arriba» una sola vez por cifra (`core/money.py::redondear_cantidad`); detalle por presentación con las unidades congeladas.
6. **Utilidad (D5).** `importe_neto − costo_total − IVA absorbido asignado`, solo sobre líneas con costo; costo vendido y utilidad con `VER_UTILIDAD` (sin él, `null` y `ve_utilidad: false`); las líneas sin costo aparte (cantidad y neto); el IVA absorbido es una única expresión que vale cero hasta que la facturación cree `ajuste_iva_absorbido`; sin margen porcentual.
7. **Consultas (D6).** Módulo `reportes` de solo lectura con SQLAlchemy Core sobre las tablas de los demás módulos (excepción de `02` §5.2), sin comandos, sin vistas ni migración; el detalle de una jornada por `stock/service.py` (una sola implementación de RUT-07). `import-linter`: nadie importa `reportes`; `reportes` solo importa `models` y `service` ajenos. La vista `vista_venta_utilidad` de `03` §16 queda para REP-06 y la facturación.
8. **Rendición (D7).** Jornadas abiertas en el período, de cualquier estado, con ventas, anuladas, cobrado por medio, lo tardío aparte, faltantes y sobrantes y el valor con `VER_COSTOS`; totales por vendedor; el resumen de RUT-07 con `VER_REPORTES`.
9. **Saldos (D8 = B).** Saldo actual de clientes (con límite y disponible) y de proveedores desde `saldo_cuenta`; totales adeudado y a favor; «Ver estado de cuenta» solo con el permiso de la ficha. Los de clientes se leen con `VER_REPORTES`; los de proveedores, con `VER_REPORTES` **y además** al menos uno de `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD` (403 `PERMISO_REQUERIDO` sin la regla completa). Con la plantilla actual los ven Administrador, Administración y Consulta/Dirección (esta por `VER_UTILIDAD`); el Supervisor no. Motivo: el Supervisor es un rol operativo; se mantiene el criterio de ADR-033 de que no ve información de proveedores, y quitarle `VER_REPORTES` le ocultaría también ventas, rendiciones y observaciones por vendedor. El servidor combina las dependencias existentes `requiere_permiso` y `requiere_algun_permiso` (sin dependencia nueva); `/admin` repite la regla con los permisos de `GET /yo` y oculta la pestaña «Saldos de proveedores» a quien no la cumple.
10. **Observaciones por vendedor (D9).** Ventas sin conexión, avisos por código, rechazadas y excesos detectados por vendedor (`02` §20).
11. **Ajustes por motivo (D10).** Ajustes confirmados por motivo con entradas, salidas y valor con `VER_COSTOS`, y las diferencias de rendición aparte; el motivo en la auditoría de `COMPRA_ANULAR`/`PAGO_PROVEEDOR_ANULAR` y el mecanismo común de puertos de `catalogo` se reasignan al 28.
12. **Pantallas, textos y ayuda (D11 a D13).** Sección «Reportes» con seis pestañas; nueve claves de ayuda nuevas, sin ejemplos. Sin exportar ni imprimir.
13. **Sin permisos nuevos (D8 combina permisos existentes en una regla compuesta de `01` §19), sin migración, sin versión nueva de Dexie.**
14. **Paginación y orden de las listas (D14, aprobada el 2026-11-07).** En el servidor, de a **50 filas**: «Por día», «Por producto» y «Ventas anuladas del período», la lista de jornadas de las rendiciones y los saldos de clientes y de proveedores; «Por vendedor», «Ajustes por motivo» y «Observaciones por vendedor» no se paginan. Cada lista viaja en el sobre `filas`, `pagina`, `tamano` (50, fijo en el servidor, sin parámetro), `total_filas` y `paginas`; la página se pide desde 1 (`pagina` en rendiciones y saldos; `pagina_por_dia`, `pagina_por_producto` y `pagina_anuladas` en ventas, independientes, en el mismo endpoint); 0 responde 422 y una página posterior a la última viene vacía. `LIMIT`/`OFFSET` y `count` en SQL con orden estable que termina en una clave única. Los totales (resumen, por vendedor, cantidad y total de anuladas, totales por vendedor de las rendiciones, total adeudado y a favor) son de todo el período y los filtros, nunca de la página. Orden descendente: «Por día» por fecha; anuladas por la fecha de la venta (desempate `venta.id`); jornadas por `abierta_en` (desempate `jornada.id`). En `/admin`: «Anterior», «Página {n} de {m}» y «Siguiente», oculto con una sola página; cambiar un filtro vuelve todas las listas a la página 1. **Se aparta deliberadamente** del cursor con «Cargar más» del resto de `/admin` (`02` §11): los reportes son tablas grandes que el usuario quiere recorrer por páginas sin que la página crezca sin límite; es una excepción acotada a los reportes.

## Consecuencias

- Consulta/Dirección tiene su pantalla, con los saldos de proveedores; el Supervisor ve cantidades, importes y saldos de clientes, sin costo ni utilidad y sin los saldos de proveedores (una organización que quiera mostrárselos le agrega uno de los tres permisos o arma un rol).
- Un mes cerrado cambia si se anula después una venta de ese mes o llega tarde una venta sin conexión (REP-01, REP-02); la ayuda lo explica.
- El costo vendido agregado es visible con `VER_UTILIDAD` (se deduce de la utilidad); los costos unitarios siguen con `VER_COSTOS`.
- `02` §5.3 suma la dependencia de `reportes`; `03` §16 aclara que la vista llega con REP-06; `01` §19 suma la regla compuesta de los saldos de proveedores; `02` §11 anota la paginación por número de los reportes como excepción al cursor (D14).
- Los reportes tienen dos formas de paginar en `/admin` (los reportes por número, el resto por cursor); una fila puede cambiar de página entre dos pedidos si llega una operación tardía (REP-01: el reporte se recalcula siempre).

## Precisiones del apply

Hallazgos al implementar, que no cambian lo aprobado:

1. **`RANGO_DE_FECHAS_INVALIDO` duplicado en `reportes/domain`.** El error vive en el dominio de `reportes` con el mismo código estable y el mismo texto que el del estado de cuenta: `import-linter` prohíbe importar el `domain` ajeno. El frontend reutiliza el texto de `cuentas_corrientes`.
2. **Reloj inyectable en las lecturas.** Los reportes piden `obtener_reloj` como dependencia (sin `datetime.now()`): el mes en curso y «hoy» salen del reloj, y las pruebas lo fijan (TR-04).
3. **Neto, IVA y total de la cabecera; cajas, costo y utilidad de las líneas.** El resumen suma `venta.total_neto`, `venta.total_iva` y `venta.total` (así neto + IVA = total, INV-14, y concilia con el listado, REP-01); las cajas equivalentes, el costo vendido y la utilidad se suman de `venta_linea` (REP-03, REP-04).
4. **Diferencias de la rendición, por línea.** El valor de las diferencias de una jornada se valúa por línea (como `stock` en RUT-07) y el de los ajustes es la suma exacta redondeada una sola vez (TR-03); por eso la fila «Diferencias de rendición» de los ajustes y el valor de la rendición pueden diferir en centavos por redondeo de línea.
5. **Esquemas del resumen replicados.** `reportes` no importa los esquemas de `stock` (contrato de `import-linter`): repite la forma del resumen de jornada y lo arma desde `stock/service.py::obtener_resumen_de_jornada`, una sola implementación de la regla.
6. **Proveedores sin columna de código.** La tabla `proveedor` no tiene código: el reporte muestra el nombre, el estado sale de `activo`, y la búsqueda es por nombre (parámetro `texto`).
7. **«Razón social» de clientes.** La columna muestra `razon_social` y, si no tiene, el nombre.
8. **Etiquetas de estado de jornada.** `ABIERTA` → «En curso», `EN_RENDICION` → «En rendición», `CERRADA` → «Cerrada», `LIBERADA` → «Liberada»; las columnas de fecha son Abierta, Rendida, Cerrada y Liberada.
9. **Ajustes sin `VER_COSTOS`.** Se ocultan las columnas de valor y de «Sin costo» (no solo el valor): las unidades se informan siempre. **Confirmado sin cambios por el usuario en la prueba manual (2026-11-07):** el Supervisor no ve valores en «Ajustes por motivo».
10. **Aterrizaje de Consulta/Dirección.** Quien solo tiene `VER_REPORTES` aterriza en «Reportes» (primera sección permitida, ADR-027).
11. **Nombres de producto en el detalle de la rendición.** `GET /reportes/rendiciones/{jornada_id}` suma por línea `producto_codigo`, `producto_nombre` y la presentación de referencia (`unidades_referencia`, `nombre_referencia`), resueltos en SQL con `organizacion_id`: el detalle del reporte lo lee quien tiene `VER_REPORTES` sin el permiso del catálogo ni el de stock, así que la pantalla no pide `/catalogo/productos` ni los saldos (hallazgo del Lote 5; antes veía «Producto xxxxxxxx» y unidades en lugar de cajas). La pantalla de stock queda igual.
12. **Propiedades.** `tests/properties/test_reportes_propiedades.py` prueba contra PostgreSQL real que el reporte suma las `CONFIRMADA` y las anuladas van aparte (REP-01, REP-02, INV-14), que las cifras pasadas no cambian con costos ni precios posteriores (REP-05, INV-10) y que cada saldo es la suma del libro (INV-13).
13. **Textos e interpretaciones no literales de los Lotes 4 y 5, aceptados por el usuario en la prueba manual (2026-11-07):** estados de clientes y proveedores «Activo» / «Suspendido» / «Inactivo»; «Pendientes: N»; la columna «Código»; los prefijos «Ventas:», «Anuladas:» y «Cobrado:»; los `h2` repetidos entre pestañas; `razon_social ?? nombre`; el saldo negativo como «200,00 a favor»; el recálculo al cambiar un filtro, sin botón «Filtrar»; el proveedor sin código (precisión 6).
14. **Paginación (Lote 7, D14), detalles del apply.** El sobre se arma con una función pura de `reportes/domain/paginacion.py` (`TAMANO_DE_PAGINA = 50`, `desplazamiento_de`, `armar_sobre`); el `count` sale de SQL con los mismos filtros (fechas distintas para «Por día», productos distintos para «Por producto», filas del filtro para jornadas y saldos). El detalle por presentación de «Por producto» y el dinero y las diferencias de las jornadas se suman en SQL solo para los productos y las jornadas de la página (`IN` con los ids de la página); `por_vendedor` y los totales de saldos no pasan por `LIMIT`. En la pantalla, la página solo viaja desde la 2 (la 1 es el valor por defecto del servidor, así la URL sin paginar sigue siendo la de siempre); el texto de lista vacía depende de `total_filas === 0`, de modo que una página posterior a la última (por ejemplo, si bajó el total mientras se recorría) muestra la tabla sin filas y la navegación para volver, no el aviso de «sin resultados».
15. **Vendedores del filtro de «Saldos de clientes».** Resuelto: el servidor devuelve junto con el reporte `vendedores` (`id`, `nombre`), todos los vendedores con clientes asignados en la organización, por nombre, calculados en SQL e independientes de la página y de los filtros; el desplegable usa esa lista. En «Ventas» y «Rendiciones» no cambia: salen de «Por vendedor», que no se pagina.

## Alternativas descartadas (0.1, 2026-11-06)

- **Dos changes 26a/26b (D0 B):** Consulta/Dirección sin saldos un change más.
- **La anulación resta en su propio período (D2 B):** contradice REP-02.
- **Utilidad por producto (D3 B):** adelanta REP-06.
- **Cajas con la referencia actual (D4 B):** reescribe el pasado (REP-05).
- **Costo vendido solo con `VER_COSTOS` (D5 B) o líneas sin costo a costo cero (D5 C):** la primera es cosmética; la segunda infla la utilidad.
- **Vista por migración (D6 B):** la vista se rehace cuando exista la facturación.
- **Solo jornadas rendidas (D7 B):** las liberadas y en curso no se ven.
- **Saldos de proveedores con solo `VER_REPORTES` (D8 A, la recomendada):** el Supervisor vería los saldos de los proveedores, contra el criterio de ADR-033; la única salida para evitarlo era quitarle `VER_REPORTES`, lo que le ocultaba también los demás reportes.
- **Saldos con fecha de corte (D8 C):** recorre el libro en cada consulta; queda para la etapa 2.

## Alternativas descartadas (D14, 2026-11-07)

- **Cursor con «Cargar más», como el resto de `/admin`:** la página crece sin límite y no se sabe cuántas hay; es lo que el usuario pidió cambiar.
- **Rutas por lista (`/reportes/ventas/por-dia`, …):** más rutas en el ratchet y la pestaña «Ventas» pide cuatro veces.
- **Tamaño elegido por el cliente (`tamano`):** permite páginas sin límite.
- **Paginar en el frontend:** el servidor sigue mandando todas las filas.

## Deudas nuevas

1. **Al módulo de facturación:** sumar `ajuste_iva_absorbido` en la expresión del IVA absorbido del repositorio de `reportes` (REP-04, FAC-03).
2. **Al 28:** el motivo en la auditoría de `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` y el mecanismo común de los puertos de registro de `catalogo` (deuda del 14, partes 1 y 3).
3. **A la etapa 2 (REP-06):** utilidad por producto, cliente, proveedor y categoría, comparativos, exportación, filtros guardados y, si hace falta, `vista_venta_utilidad`; saldo a una fecha de corte.
