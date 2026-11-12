# Verificación — 06b-permisos-efectivos-interfaz

> Documento en construcción a lo largo de las tareas del change (`tasks.md`
> 2.9, 8.6, 9.1-9.2, 10.1-10.5). Las secciones 2.9, 8.6, 8.7, 9.6 y
> 10.1-10.5 están completas. La 10.4 fue aplicada y aprobada por el usuario
> (2026-09-27). La 10.5 fue **ejecutada por el usuario** el 2026-09-28 de
> punta a punta (pasos 1-13): todo ✅ salvo un hallazgo en el paso 13 (D9,
> usuario inactivo), que no aterrizaba en el aviso "Iniciar sesión" y quedó
> cerrado con el grupo 11 (§11, re-verificado el mismo día).

## 2.9 — Por qué no hace falta una prueba de concurrencia para D9

La pregunta: ¿hace falta una prueba de concurrencia para la verificación de
usuario/rol activos que agrega este grupo (`exigir_sesion_habilitada`,
`listar_permisos_del_usuario`, `renovar_sesion`)?

**No.** Motivos:

1. **Es una lectura por petición, sin escritura concurrente nueva.**
   `exigir_sesion_habilitada` y `listar_permisos_del_usuario` solo leen
   `usuario`/`rol` (una consulta con `JOIN`, sin bloqueo) en cada petición;
   no agregan ninguna fila nueva que otra petición concurrente pueda
   disputar. El único camino de escritura que este grupo agrega
   (`revocar_sesiones_refresh_de_usuario` + la auditoría, dentro de
   `renovar_sesion`) ya corre bajo la misma transacción por petición que
   el resto de `renovar_sesion` -- ninguna petición nueva se solapa con
   otra escribiendo la MISMA fila de `sesion_refresh` de forma que dependa
   de un orden particular: la peor coincidencia posible es que dos
   renovaciones concurrentes del mismo usuario ya inactivo revoquen "en
   paralelo" un conjunto de filas que la base sirve de forma idempotente
   (un `UPDATE ... WHERE revocado_en IS NULL` que la segunda ejecución
   simplemente no toca, porque ya no hay filas que cumplan la condición).

2. **Misma carrera que un permiso quitado (ADR-017), ya aceptada sin
   prueba de concurrencia propia.** La verificación de permisos existente
   (`design.md` D5, tarea 10.5: "sin caché... una revocación tiene efecto
   inmediato en la petición siguiente") tampoco tiene una suite de
   concurrencia dedicada: la carrera "se te quita el permiso mientras tu
   petición ya estaba en vuelo" se resuelve, por diseño, en la PRÓXIMA
   petición, nunca en la que ya estaba en curso (no hay forma de
   "interrumpir" una petición que ya leyó sus permisos). D9 usa exactamente
   el mismo criterio: si la baja de un usuario ocurre mientras su petición
   ya estaba en curso, esa petición en curso no se corta a mitad de camino
   -- la siguiente sí la rechaza. No hay ninguna ventana nueva que este
   grupo abra respecto de la que ADR-017 ya aceptó para los permisos.

3. **Sin comando de baja todavía (D9.5), no hay una escritura de negocio
   real que dispare la baja concurrentemente con una lectura.** Las
   pruebas de este grupo siembran `INACTIVO`/`activo = false` directamente
   en la base de prueba (nota del grupo 2 en `tasks.md`), no a través de un
   comando del bus -- no existe, todavía, una operación concurrente real
   de "dar de baja" que competir con una lectura. El día que exista (D9.5,
   change de baja de usuarios/roles), esa función SÍ pasará por el bus de
   comandos con su propia transacción, y la pregunta de concurrencia se
   vuelve a evaluar en ese change con el mismo criterio de ADR-017.

**Conclusión:** no se agrega una suite de concurrencia para D9 en este
change. Si en el futuro se agrega el comando de baja (D9.5) y aparece una
carrera real de escritura (baja concurrente con una escritura de negocio en
curso, no solo con una lectura), esa suite se agrega en ese change, no en
este.

## 8.6 — Evidencia de `grep` en `frontend/src/areas/admin`

Tarea 8.6. Los tres chequeos pedidos, ejecutados sobre
`frontend/src/areas/admin/**/*.tsx`.

### 8.6.1 `PermisoRequerido…Error` solo en ramas de manejo del 403

```
CategoriasYMarcasScreen.tsx:16:  import { ErrorDeCatalogo, PermisoRequeridoCatalogoError } from '../../../features/catalogo/errores'
CategoriasYMarcasScreen.tsx:52:  * (`PermisoRequeridoCatalogoError`) se sigue tratando en cada sección, pero
CategoriasYMarcasScreen.tsx:125: {categorias.error instanceof PermisoRequeridoCatalogoError
CategoriasYMarcasScreen.tsx:225: {marcas.error instanceof PermisoRequeridoCatalogoError
ProductosListScreen.tsx:10:     import { PermisoRequeridoCatalogoError } from '../../../features/catalogo/errores'
ProductosListScreen.tsx:27:     * El 403 del servidor (`PermisoRequeridoCatalogoError`) se sigue
ProductosListScreen.tsx:76:     if (productos.error instanceof PermisoRequeridoCatalogoError) {
DispositivosScreen.tsx:6:       import { PermisoRequeridoError, useDispositivos } from './useDispositivos'
DispositivosScreen.tsx:61:      if (dispositivos.error instanceof PermisoRequeridoError) {
CostosCargaScreen.tsx:22:       import { ErrorDeProveedores, PermisoRequeridoProveedoresError } from '../../../features/proveedores/errores'
CostosCargaScreen.tsx:88:       if (proveedor.error instanceof PermisoRequeridoProveedoresError) {
CostosHistorialScreen.tsx:8:    import { PermisoRequeridoProveedoresError } from '../../../features/proveedores/errores'
CostosHistorialScreen.tsx:63:   (vigente.isError && vigente.error instanceof PermisoRequeridoProveedoresError) ||
CostosHistorialScreen.tsx:64:   (historial.isError && historial.error instanceof PermisoRequeridoProveedoresError)
ProveedoresListScreen.tsx:11:   import { PermisoRequeridoProveedoresError } from '../../../features/proveedores/errores'
ProveedoresListScreen.tsx:38:   * (`PermisoRequeridoProveedoresError`) se sigue tratando, pero **solo como
ProveedoresListScreen.tsx:64:   if (proveedores.error instanceof PermisoRequeridoProveedoresError) {
```

Clasificando las 15 coincidencias:

| Tipo | Cantidad | Dónde |
| --- | --- | --- |
| `import` de la clase de error | 6 | Solo imports; no deciden visibilidad. |
| Comentario de docstring | 3 | Describen el 403 como red de seguridad. |
| Rama de manejo del 403 (`isError`) | 6 | `DispositivosScreen:61`, `ProductosListScreen:76`, `CategoriasYMarcasScreen:125` y `:225`, `ProveedoresListScreen:64`, `CostosCargaScreen:88`, `CostosHistorialScreen:63-64`. |

**Ninguna** ocurrencia decide qué se ve: todas leen `.isError` de una consulta
que **ya se disparó**, y por lo tanto solo pueden activarse cuando el
servidor rechazó la petición. **Cumple 8.6.1.**

### 8.6.2 `useCostoVigente` ya no aparece en `ProductoFormScreen.tsx`

```
CostosHistorialScreen.tsx:9:  import { useCostoVigente, useHistorialDeCostos } from '../../../features/proveedores/useListados'
CostosHistorialScreen.tsx:59: const vigente = useCostoVigente(productoId)
```

Solo queda en `CostosHistorialScreen.tsx`, que **es** la pantalla de
historial de costos: ahí el costo vigente es un dato de la pantalla, no una
sonda de permiso. `ProductoFormScreen.tsx` no lo tiene, y sus pruebas
afirman que en ningún caso se pide `/costos/productos/{id}/vigente` (tarea
8.3). **Cumple 8.6.2.**

### 8.6.3 Las ocho pantallas de la 8.1-8.5 con el mecanismo compartido

```
DispositivosScreen.tsx:28:      <SiTienePermiso permiso="GESTIONAR_DISPOSITIVOS" fallback={<FaltaPermisoDeDispositivos />}>
ProductosListScreen.tsx:35:     <SiTienePermiso permiso="GESTIONAR_CATALOGO" fallback={<CatalogoSinPermiso />}>
CategoriasYMarcasScreen.tsx:58: <SiTienePermiso permiso="GESTIONAR_CATALOGO" fallback={<CatalogoSinPermiso />}>
ProductoFormScreen.tsx:459:     <SiTienePermiso permiso="VER_COSTOS">
ProveedoresListScreen.tsx:44:   <SiTienePermiso permiso="GESTIONAR_PROVEEDORES" fallback={<ProveedoresSinPermiso />}>
ProveedorFormScreen.tsx:50:     <SiTienePermiso permiso="GESTIONAR_PROVEEDORES" fallback={<ProveedoresSinPermiso />}>
ProveedorFormScreen.tsx:275:    <SiTienePermiso permiso="EDITAR_COSTOS">
CostosCargaScreen.tsx:67:       <SiTienePermiso permiso="EDITAR_COSTOS" fallback={<CostosSinPermiso />}>
CostosHistorialScreen.tsx:49:   <SiTienePermiso permiso="VER_COSTOS" fallback={<CostosSinPermiso />}>
```

Las siete pantallas que piden datos (todas menos `ProductoFormScreen`, que
solo envuelve un enlace) lo hacen con el gate en el **exterior**: los
componentes que llaman a `use…` viven dentro del hijo del gate, así que sin
el permiso no se montan y no disparan peticiones (**B2**, `design.md` D4-A).
`ProductoFormScreen` no se gatea entero a propósito: la 8.3 pide gatear solo
el enlace, y la pantalla es alcanzable con `GESTIONAR_CATALOGO` para
usuarios sin `VER_COSTOS`.

**Cumple 8.6.**

## 8.7 — Comandos contra la línea base de 1.1

Ejecutados en `frontend/` al cerrar el grupo 8.

| Comando | Línea base (tarea 1.1) | Resultado del grupo 8 | Estado |
| --- | --- | --- | --- |
| `npm run typecheck` | Sin errores | Sin salida de `tsc` | Verde |
| `npm run lint` | `0 errores`, `2` advertencias | `0 errores`, `2` advertencias (las mismas dos: `react-hooks/incompatible-library` por `watch()` de RHF en `ProductoFormScreen.tsx` y en `CostosCargaScreen.tsx`) | Verde |
| `npm run test` | `35` archivos, `257` pruebas | `35` archivos, `270` pruebas (`+13`) | Verde |
| `npm run build` | Verde | `✓ built in 824ms` | Verde |

Las `+13` son exactamente los casos nuevos de las tareas 8.1-8.5, sumados
sobre las ocho suites afectadas (`54` -> `67`):

| Suite | Casos al cerrar el grupo 8 |
| --- | --- |
| `DispositivosScreen.test.tsx` | 6 |
| `ProductosListScreen.test.tsx` | 7 |
| `CategoriasYMarcasScreen.test.tsx` | 7 |
| `ProductoFormScreen.test.tsx` | 17 |
| `ProveedoresListScreen.test.tsx` | 3 |
| `ProveedorFormScreen.test.tsx` | 7 |
| `CostosCargaScreen.test.tsx` | 9 |
| `CostosHistorialScreen.test.tsx` | 11 |

RED observado antes de implementar cada tarea, contra la línea base de 1.1:
8.1 `1 falló / 5 pasaron`; 8.2 `2 fallaron`; 8.3 `2 fallaron`; 8.4
`3 fallaron`; 8.5 `3 fallaron / 17 pasaron`. En cada caso el GREEN fue el
total de la suite. Ninguna prueba previa cambió de significado: el único
nombre retocado es el de `CostosCargaScreen`, que decía "permiso u otro
error general" y ahora nombra el caso que realmente cubre (un error que no
es de permiso, p. ej. `PROVEEDOR_INACTIVO`); el 403 de esa pantalla pasó a
tener su propio caso, que es lo que pedía la 8.5.

## 9.6 — Escenarios de backend, comandos y suite completa

Todo el grupo 9 se implementó sobre pruebas: no hubo que cambiar una sola
línea de producción, salvo la tupla de `COBERTURA_DE_AISLAMIENTO` que la 9.1
autoriza explícitamente.

### Escenario -> prueba

| Escenario (`identidad/permisos-efectivos`, y `inv21-aislamiento` de 06) | Prueba | Estado |
| --- | --- | --- |
| "Dos organizaciones, cada usuario ve solo lo suyo" | `test_inv21_aislamiento_endpoints_identidad.py::TestAislamientoDeLaSesion::test_yo_del_usuario_de_b_no_trae_nada_de_la_organizacion_a` | Verde |
| "Una organización o un usuario informados en la petición se ignoran" | `TestAislamientoDeLaSesion::test_yo_ignora_la_organizacion_y_el_usuario_de_a_informados` | Verde |
| "La ruta forma parte de la cobertura de aislamiento" | `test_inv21_ratchet_rutas.py::test_inv21_toda_ruta_de_negocio_esta_cubierta_por_el_aislamiento` | Verde (tras el RED de 4.6) |
| (9.2) La ruta no declara `organizacion_id` | `test_inv21_organizacion_siempre_del_token.py::test_la_recorrida_de_aislamiento_alcanza_la_consulta_de_la_sesion` | Verde |
| "Lo informado coincide con lo que el servidor autoriza" | `test_identidad_yo_api.py::TestLoInformadoCoincideConLoAutorizado` (2 pruebas: cada mitad del par) | Verde |
| "Quitar un permiso al rol se refleja en la consulta siguiente" | `TestLosPermisosDelRolSeReflejanEnLaConsultaSiguiente::test_quitar_un_permiso_al_rol_se_refleja_en_la_consulta_siguiente` | Verde |
| "Agregar un permiso al rol se refleja en la consulta siguiente" | `TestLosPermisosDelRolSeReflejanEnLaConsultaSiguiente::test_agregar_un_permiso_al_rol_se_refleja_en_la_consulta_siguiente` | Verde |
| "Consultar la sesión no escribe nada" | `TestLaConsultaDeLaSesionNoEscribe::test_tres_consultas_no_crean_filas_de_comando_ni_de_auditoria` | Verde |

Las escenas de `06` que ya estaban cubiertas (sin token, token con firma
alterada, token vencido, usuario dado de baja, rol desactivado, respuesta sin
secretos, orden de permisos, rol sin permisos) siguen siendo las primeras
nueve pruebas de `test_identidad_yo_api.py` y no se tocaron.

### Cómo se evita la prueba tautológica

Las cuatro pruebas de coherencia y de revocación contrastan `/yo` contra la
**respuesta del servidor**, no contra una lista esperada escrita a mano: la
misma prueba pide la ruta que exige el permiso que `/yo` afirma tener y la que
exige el que `/yo` afirma no tener. Si `/yo` leyera los permisos de un lado
distinto al que autoriza el servidor, el par 200/403 se rompería.

Dos detalles que sostienen esa lectura:

- El auxiliar `_crear_usuario_con_permisos` fija una composición **exacta** de
  permisos, en vez de partir de una plantilla de `01` §19. Con la plantilla
  `ADMINISTRACION` el resultado habría sido el mismo, pero la prueba no
  dependería de qué permisos trae cada plantilla el día de mañana.
- En la 9.4 el usuario que cambia la composición es el mismo que se consulta.
  Por eso el rol arranca con `ADMIN_USUARIOS` (que le permite seguir cambiando
  permisos) y sin `GESTIONAR_DISPOSITIVOS` (que es lo que la prueba va a
  agregar después). Al revocar, `/identidad/proveedores` pasa a 403 mientras
  `/identidad/usuarios` sigue en 200: eso prueba que se quitó *solo* el permiso
  revocado y no la sesión entera.

### Lectura pura: el recuento tiene que ser no trivial

La 9.5 cuenta filas de `comando` y `auditoria` en **toda** la tabla, sin
filtrar por organización (un filtro dejaría pasar filas que la prueba no está
mirando; como ambas tablas son de solo inserción —`AGENTS.md` §4— el recuento
solo puede subir, y la igualdad antes/después no deja pasar ni una fila propia
ni una ajena).

Además la prueba verifica que el punto de partida no es vacío: después del
login hay `comando == 0`, `auditoria == 1`, y esa única fila es la de
`INICIO_SESION` del propio login. Sin ese paso, "no escribió nada" sería el
resultado trivial de contar ceros sobre tablas vacías.

### Comandos

| Comando | Antes del grupo 9 | Resultado | Estado |
| --- | --- | --- | --- |
| `python -m ruff check .` | `All checks passed!` | `All checks passed!` | Verde |
| `python -m ruff format --check .` | `208 files already formatted` | `208 files already formatted` | Verde |
| `python -m mypy app` | `Success: no issues found in 79 source files` | `Success: no issues found in 79 source files` | Verde |
| Contratos de importación | `10 kept, 0 broken` (107 archivos, 442 dependencias) | `10 kept, 0 broken` | Verde |
| `pytest tests/unit tests/properties tests/fixtures_compartidos` | — | `383 passed`, 2 warnings | Verde |
| `pytest tests/integration -q -rsx` | No ejecutado en esta sesión (ver nota) | `573 passed`, 9 warnings en 556.62s | Verde |

Sobre los contratos: en este venv `python -m import_linter` no es invocable
(`No module named import_linter`); el ejecutable del mismo paquete,
`.venv\Scripts\lint-imports.exe`, corre el contrato completo y es el que da
las cifras de arriba.

**Nota sobre la línea base de la suite.** El árbol ya traía los grupos 3-8 sin
commit, y en esta sesión no se corrió la suite completa *antes* de editar. Lo
que sí se midió antes fue: el conjunto dirigido de los cuatro archivos que el
grupo toca (`23 passed`), y la suite de integración **excluyendo** esos cuatro
archivos (`541 tests collected`). Los cuatro archivos del grupo tenían `24`
pruebas antes del grupo 9 (`9` + `6` + `6` + `3`), o sea `565` preexistentes
contra los `573` de ahora: el delta de `+8` son exactamente los tests nuevos.
Los últimos números completos registrados en este change son `522` (1.1) y
`544` (2.10).

### Skip y xfail

`pytest tests/integration -q -rsx` no imprimió ninguna sección de skip ni de
xfail, y una búsqueda de `pytest.mark.skip`, `pytest.mark.skipif`,
`pytest.mark.xfail` y `pytest.skip` en todo `backend/tests/` no devuelve
coincidencias. No hay ninguna prueba omitida que justificar.

### RED observado

| Tarea | RED | GREEN |
| --- | --- | --- |
| 9.1 | El RED autorizado de 4.6: `AssertionError: INV-21: 1 ruta(s) de negocio sin cobertura de aislamiento: [('get', '/api/v1/yo')]. Rutas de negocio cubiertas hoy: 30 de 31.` — `1 failed, 5 passed in 7.25s` | `6 passed in 4.78s` (ratchet) y `8 passed` (aislamiento) |
| 9.2 | `AssertionError: assert {'authorization'} == set()`: expectativa equivocada de la prueba, no un defecto del código (OpenAPI declara el `authorization` de `HTTPBearer`) | `4 passed in 4.89s` |
| 9.3, 9.4, 9.5 | Sin RED propio: son pruebas de caracterización de comportamiento ya implementado, y pasaron al escribirlas | `14 passed in 10.34s` |

El 9.3 tuvo además un RED de andamiaje, ya corregido: el primer `_crear_producto`
dejaba `proveedor_id` en `None` y `producto.proveedor_id` es `NOT NULL`
(`03` §4), así que el `INSERT` falló con `NotNullViolation` hasta que el
auxiliar creó también un proveedor.

## 10.1 — Mapeo escenario → prueba de las seis specs delta

Las seis specs delta del change tienen **45 escenarios**. Los 45 están
cubiertos por pruebas reales. Dos estaban cubiertos solo **parcialmente** y
se cerraron con pruebas nuevas en este grupo; el resto ya tenía una prueba
que lo cubría.

**Ninguna prueba nueva requirió un cambio de producción.** Las dos brechas
encontradas eran de *cobertura*, no de comportamiento: el comportamiento ya
estaba implementado (grupos 2, 6 y 7) pero ninguna prueba afirmaba el efecto
completo que el escenario describe. Por lo tanto no hubo que detener el grupo
y consultar al usuario.

### `identidad/permisos-efectivos` (21 escenarios)

| # | Escenario | Prueba | Estado |
| --- | --- | --- | --- |
| 1 | "Un usuario de Administración obtiene sus permisos ordenados" | `test_identidad_yo_api.py::TestYoContrato::test_devuelve_la_forma_exacta_del_contrato_para_un_administracion` + `test_identidad_yo_service.py::TestObtenerYo::test_usuario_de_administracion_obtiene_sus_permisos_ordenados` | Verde |
| 2 | "Un usuario sin ningún permiso de administración igual obtiene su sesión" | `TestYoContrato::test_un_vendedor_repartidor_obtiene_200_sin_exigir_ningun_permiso` | Verde |
| 3 | "Un rol sin permisos devuelve la lista vacía" | `test_identidad_yo_service.py::TestObtenerYo::test_rol_con_la_composicion_vaciada_da_permisos_vacio` | Verde |
| 4 | "Sin access token la consulta se rechaza" | `TestYoContrato::test_sin_token_da_401_ausente` | Verde |
| 5 | "Un usuario dado de baja no obtiene su sesión (D9)" | `TestYoContrato::test_usuario_que_paso_a_inactivo_da_401_invalido_no_200` + `test_identidad_yo_service.py::TestObtenerYo::test_usuario_inactivo_da_el_mismo_401_nunca_200_con_lista_vacia` | Verde |
| 6 | "La respuesta no expone secretos" | `TestYoContrato::test_la_respuesta_no_expone_secretos_ni_login_ni_estado_ni_tope` | Verde |
| 7 | "Consultar la sesión no escribe nada" | `TestLaConsultaDeLaSesionNoEscribe::test_tres_consultas_no_crean_filas_de_comando_ni_de_auditoria` | Verde |
| 8 | "Lo informado coincide con lo que el servidor autoriza" | `TestLoInformadoCoincideConLoAutorizado::test_un_permiso_que_informa_es_el_que_el_servidor_autoriza` y `::test_el_contrario_tambien_coincide` | Verde |
| 9 | "Quitar un permiso al rol se refleja en la consulta siguiente" | `TestLosPermisosDelRolSeReflejanEnLaConsultaSiguiente::test_quitar_un_permiso_al_rol_se_refleja_en_la_consulta_siguiente` | Verde |
| 10 | "Agregar un permiso al rol se refleja en la consulta siguiente" | `TestLosPermisosDelRolSeReflejanEnLaConsultaSiguiente::test_agregar_un_permiso_al_rol_se_refleja_en_la_consulta_siguiente` | Verde |
| 11 | "Dos organizaciones, cada usuario ve solo lo suyo" | `test_inv21_aislamiento_endpoints_identidad.py::TestAislamientoDeLaSesion::test_yo_del_usuario_de_b_no_trae_nada_de_la_organizacion_a` | Verde |
| 12 | "Una organización o un usuario informados en la petición se ignoran" | `TestAislamientoDeLaSesion::test_yo_ignora_la_organizacion_y_el_usuario_de_a_informados` | Verde |
| 13 | "La ruta forma parte de la cobertura de aislamiento" | `test_inv21_ratchet_rutas.py::test_inv21_toda_ruta_de_negocio_esta_cubierta_por_el_aislamiento` | Verde |
| 14 | "Una sola consulta por sesión mientras no se renueve el token" | **`AdminScreenRenovacion.test.tsx::navega entre Catálogo, Proveedores y la ficha de un producto sin renovar el token…`** (nuevo) | Verde (**nuevo**) |
| 15 | "Tras renovar el token, la interfaz refleja un permiso quitado" | **`AdminScreenRenovacion.test.tsx::tras renovar el token, "Proveedores" desaparece del menú sin recargar la página…`** (nuevo) | Verde (**nuevo**) |
| 16 | "Si la renovación falla, los permisos se descartan" | `AdminScreen.test.tsx::AdminScreen: suscripción a cambios de token (tarea 6.5)::al limpiarse el token, descarta ["yo"]` + `httpClient.test.ts::una renovación rechazada avisa con null` | Verde |
| 17 | "Los permisos no quedan en el almacenamiento del navegador" | `usePermisos.test.tsx::tras cargar /yo, ninguna clave de localStorage ni sessionStorage contiene la respuesta` + `tokenStore.test.ts::fijar el token nunca escribe en localStorage ni en sessionStorage` y `::fijar el token nunca escribe en document.cookie` | Verde |
| 18 | "Administración ve Catálogo y Proveedores, no Dispositivos" | `AdminLayout.test.tsx::Administración ve Catálogo y Proveedores, y no Dispositivos` | Verde |
| 19 | "Supervisor comercial ve solo Dispositivos" | `AdminLayout.test.tsx::Supervisor comercial ve solo Dispositivos` | Verde |
| 20 | "Un usuario sin secciones de administración" | `AdminLayout.test.tsx::Vendedor/Repartidor no ve ninguna sección` | Verde |
| 21 | "Mientras la consulta de sesión carga, no se muestran secciones protegidas" | `AdminLayout.test.tsx::mientras /yo está pendiente se muestra el encabezado, pero ninguna sección protegida` | Verde |
| 22 | "Si la consulta de sesión falla, se informa y se puede reintentar" | `AdminLayout.test.tsx::si la consulta falla por un error del servidor, avisa que no pudo obtener los permisos y ofrece reintentar` y `::reintentar vuelve a consultar /yo y, si responde, muestra las secciones permitidas` | Verde |
| 23 | "Si la sesión terminó, se ofrece iniciar sesión" | `AdminLayout.test.tsx::si la consulta falla con 401 (la renovación del token fue rechazada), el aviso ofrece iniciar sesión y no reintentar` | Verde |
| 24 | "El encabezado identifica la sesión" | `AdminLayout.test.tsx::muestra "{usuario} · {organización} · {rol}" con los nombres de /yo` | Verde |
| 25 | "Entrar por URL a una pantalla sin permiso no consulta sus datos" | `DispositivosScreen.test.tsx::al entrar por URL sin el permiso muestra que falta y NO pide el listado de dispositivos` | Verde |
| 26 | "Con el permiso, la pantalla muestra sus datos y acciones" | `DispositivosScreen.test.tsx::lista los dispositivos con su estado, prefijo y último correlativo` | Verde |
| 27 | "Un 403 del servidor entre dos renovaciones se muestra como falta de permiso" | `DispositivosScreen.test.tsx::un 403 del servidor entre dos renovaciones se muestra como falta de permiso, sin listado y sin error genérico` | Verde |
| 28 | "Ocultar una acción no la protege" | `test_inv21_aislamiento_endpoints_identidad.py::TestLaFaltaDePermisoSeDistingueDeUnRecursoAjeno::test_sin_permiso_sobre_recurso_propio_es_403_no_404` | Verde |

### `identidad/autorizacion-por-permiso` (10 escenarios)

| # | Escenario | Prueba | Estado |
| --- | --- | --- | --- |
| 1 | "Con el permiso, la operación procede" | `test_identidad_yo_api.py::TestLoInformadoCoincideConLoAutorizado::test_un_permiso_que_informa_es_el_que_el_servidor_autoriza` | Verde |
| 2 | "Sin el permiso, la operación se rechaza con un código estable" | `test_ratchet_permiso_por_ruta.py` (par 200/403 del escenario 8 de `permisos-efectivos`) + `TestLaFaltaDePermisoSeDistingueDeUnRecursoAjeno::test_sin_permiso_sobre_recurso_propio_es_403_no_404` | Verde |
| 3 | "Una ruta de negocio sin permiso declarado no llega a existir" | `test_ratchet_permiso_por_ruta.py::test_toda_ruta_de_negocio_declara_el_permiso_que_exige` (ratchet, falla si aparece una ruta sin `dependencies`) | Verde |
| 4 | "Las rutas de autenticación y de sistema no exigen permiso" | `test_ratchet_permiso_por_ruta.py::test_las_rutas_de_sistema_y_autenticacion_no_exigen_permiso` | Verde |
| 5 | "La consulta de la propia sesión no exige permiso pero sí sesión" | `test_ratchet_permiso_por_ruta.py::test_la_consulta_de_la_propia_sesion_no_exige_permiso_pero_si_sesion` | Verde |
| 6 | "Un usuario dado de baja pierde el acceso en la petición siguiente" | `test_sesion_usuario_inactivo_api.py::TestUsuarioInactivo::test_lectura_responde_401_no_403` | Verde |
| 7 | "Una escritura de un usuario dado de baja no deja efectos" | `TestUsuarioInactivo::test_escritura_responde_401_y_no_deja_filas` | Verde |
| 8 | "Un rol desactivado corta el acceso de sus usuarios" | `TestRolInactivo::test_lectura_responde_401_con_rol_desactivado` | Verde |
| 9 | "Reactivar al usuario devuelve el acceso con el mismo token" | `TestUsuarioInactivo::test_reactivar_el_usuario_deja_pasar_el_mismo_access_token` | Verde |
| 10 | "La baja de un usuario no afecta a otra organización" | `test_identidad_sesion_habilitada.py::TestExigirSesionHabilitada::test_usuario_inactivo_de_una_organizacion_no_afecta_a_otra` | Verde |

### `identidad/autenticacion-y-sesion` (5 escenarios)

| # | Escenario | Prueba | Estado |
| --- | --- | --- | --- |
| 1 | "Un usuario dado de baja no puede renovar su sesión" (revoca **y** deja auditoría con usuario, dispositivo y motivo; la revocación persiste aunque la respuesta sea un error) | `test_identidad_refresh_service.py::TestRenovacionDeUsuarioORolInactivo::test_usuario_inactivo_se_rechaza_y_revoca_todas_sus_familias` + **`test_auth_api.py::TestRenovacionConSesionDeshabilitada::test_el_401_persiste_la_revocacion_de_todas_las_familias_del_usuario`** y **`::test_el_401_deja_una_auditoria_con_usuario_dispositivo_y_motivo`** (nuevas) | Verde (**parcial → verde**) |
| 2 | "Un rol desactivado impide renovar su sesión" | `TestRenovacionDeUsuarioORolInactivo::test_rol_inactivo_se_rechaza_con_motivo_rol_inactivo` + `TestRenovacionConSesionDeshabilitada::test_el_401_deja_una_auditoria_con_usuario_dispositivo_y_motivo` | Verde |
| 3 | "Reactivar al usuario no revive la sesión revocada" | `TestRenovacionDeUsuarioORolInactivo::test_reactivar_el_usuario_no_revive_las_familias_hace_falta_login` | Verde |
| 4 | "La baja de un usuario no toca la sesión de otro en el mismo dispositivo" | `TestRenovacionDeUsuarioORolInactivo::test_la_sesion_de_otro_usuario_activo_en_el_mismo_dispositivo_no_se_toca` | Verde |
| 5 | "Un usuario con rol inactivo no inicia sesión" | `test_auth_api.py::TestLoginConRolInactivo::test_login_con_rol_inactivo_da_el_mismo_rechazo_generico` y `::test_login_con_rol_inactivo_y_contrasena_incorrecta_da_el_mismo_mensaje` | Verde |

### `sync/lote-de-comandos` (1 escenario)

| # | Escenario | Prueba | Estado |
| --- | --- | --- | --- |
| 1 | "El lote de un usuario dado de baja no se rechaza en bloque" | `test_bus_lote_sincronizacion.py::TestUsuarioInactivoNoSeRechazaPorRuta::test_lote_vacio_de_usuario_inactivo_responde_lista_vacia` y `::test_tipo_desconocido_de_usuario_inactivo_da_rechazado_por_item` | Verde |

La spec declara explícitamente que el comportamiento futuro
`OFFLINE`/`ONLINE` **por comando** (el paso 4 de `02` §6.3: aceptar los
comandos `OFFLINE` del inactivo con `PERMISO_REVOCADO`) es **deuda para otro
change** y no se verifica acá. Es la deuda nominada de la 10.4.

### `catalogo/administracion-de-catalogo` (3 escenarios)

| # | Escenario | Prueba | Estado |
| --- | --- | --- | --- |
| 1 | "Usuario con permiso" (navega a `/admin/catalogo`) | `app-routing.test.tsx::navegar a /admin/inicio lleva a la primera sección permitida, sin quedarse en el índice` + `ProductosListScreen.test.tsx::lista los productos de la primera página` | Verde |
| 2 | "Usuario sin permiso" (`/admin/catalogo` y `/admin/catalogo/categorias-y-marcas` por URL) | `ProductosListScreen.test.tsx::sin el permiso en la consulta de sesión no pide datos de catálogo…` + `CategoriasYMarcasScreen.test.tsx::sin el permiso en la consulta de sesión no pide datos de catálogo y no muestra acciones de escritura` | Verde |
| 3 | "El servidor rechaza aunque la interfaz creía tener el permiso" | `ProductosListScreen.test.tsx::si el servidor rechaza aunque la interfaz creía tener el permiso…` + `CategoriasYMarcasScreen.test.tsx::si el servidor rechaza aunque la interfaz creía tener el permiso…` | Verde |

### `proveedores/administracion-de-proveedores` (5 escenarios)

| # | Escenario | Prueba | Estado |
| --- | --- | --- | --- |
| 1 | "Usuario con permisos" (entra a `/admin/proveedores`) | `ProveedoresListScreen.test.tsx::lista los proveedores de la primera página` | Verde |
| 2 | "Usuario sin permiso" (`/admin/proveedores`, carga de costos, historial de costos, por URL) | `ProveedoresListScreen.test.tsx::sin el permiso en la consulta de sesión no pide proveedores y no muestra la tabla` + `ProveedorFormScreen.test.tsx::sin GESTIONAR_PROVEEDORES no pide la ficha del proveedor…` + `CostosCargaScreen.test.tsx::sin EDITAR_COSTOS…` + `CostosHistorialScreen.test.tsx::sin VER_COSTOS…` | Verde |
| 3 | "Enlace al historial de costos desde la ficha del producto según el permiso" | `ProductoFormScreen.test.tsx::con VER_COSTOS en la consulta de sesión, muestra el enlace "Ver historial de costos" con el href correcto y no pide el costo vigente` y `::sin VER_COSTOS… no muestra el enlace ni pide el costo vigente para averiguarlo` | Verde |
| 4 | "Enlace 'Cargar costos' desde la ficha del proveedor según el permiso" | `ProveedorFormScreen.test.tsx::con GESTIONAR_PROVEEDORES y EDITAR_COSTOS muestra el enlace "Cargar costos" con el href correcto` y `::con GESTIONAR_PROVEEDORES pero sin EDITAR_COSTOS no muestra el enlace` | Verde |
| 5 | "El servidor rechaza aunque la interfaz creía tener el permiso" | `ProveedoresListScreen.test.tsx::si el servidor rechaza aunque la interfaz creía tener el permiso…` + `CostosHistorialScreen.test.tsx::si el servidor rechaza…` + `CostosCargaScreen.test.tsx::si el servidor rechaza…` | Verde |

### Las dos brechas y cómo se cerraron

**Brecha 1 — "la revocación persiste aunque la respuesta sea un error", leída
desde la capa equivocada.** El escenario 1 de `autenticacion-y-sesion` tenía
una prueba que revocaba y auditaba, pero leía el resultado desde la **misma**
sesión de la prueba que había llamado a `renovar_sesion`. Eso no distingue
"quedó confirmado" de "quedó en la transacción de la petición que después
falló" — que es exactamente lo que la cláusula pide comprobar. La brecha era
del lado de la prueba: la capa de servicio nunca confirma; confirma el
endpoint (`api_v1/auth.py::refresh` hace `sesion.commit()` en el
`except DomainError` antes de dejar subir la excepción, y eso no lo probaba
nadie).

Se cerraron dos escenarios con dos pruebas nuevas en
`test_auth_api.py::TestRenovacionConSesionDeshabilitada`, que leen con
`sesion.expire_all()`: la fixture `sesion` abre **su propio** `Engine`
contra `database_url`, distinto del que la app usa para atender la petición,
así que lo que se lee después de expirar es lo confirmado y no el estado
sucio de la petición que acaba de devolver 401. Es el mismo recurso que ya
usaba `test_refresh_reuso_persiste_la_revocacion_de_la_familia`, que sí
cubría el caso análogo del reuso.

La segunda de las dos pruebas cierra además la cláusula *"hay un registro de
auditoría con el usuario, **el dispositivo** y el motivo"*: la prueba
preexistente afirmaba `usuario_id` pero no `dispositivo_id` ni el motivo (que
vive en `Auditoria.observacion`, con el formato `Sesión deshabilitada
(ROL_INACTIVO): …`). Ninguna de las dos pruebas podía completarse sin tocar
producción: el `dispositivo_id` y el `observacion` ya los escribía
`renovar_sesion`.

**Brecha 2 — la renovación no tenía prueba de efecto observable.** El
escenario 15 ("Tras renovar el token, la interfaz refleja un permiso
quitado") solo tenía sus dos piezas sueltas: `AdminScreen.test.tsx` comprobaba
que se llamara a `invalidateQueries({queryKey: ['yo']}, {cancelRefetch:
false})` —un espía sobre el `QueryClient`— y `AdminLayout.test.tsx`
comprobaba que con `['yo']` sembrado el menú mostrara Catálogo y Proveedores.
Ninguna afirmaba lo que el escenario pide: que la entrada **desaparezca del
menú**, sin recargar, cuando la renovación devuelve permisos distintos. Y el
escenario 14 ("Una sola consulta por sesión mientras no se renueve el token",
con sus tres destinos: Catálogo, Proveedores y la ficha de un producto) no
tenía ninguna prueba que lo afirmara sobre el árbol real.

`AdminScreenRenovacion.test.tsx` monta el árbol real completo —`AdminScreen`
con su `QueryClient` interno y su suscripción a `tokenStore`, `AdminLayout` y
las áreas diferidas reales— y maneja la renovación con `fijarAccessToken`, que
es lo que `httpClient` llama tras un `POST /auth/refresh` exitoso. El archivo
usa `vi.resetModules()` por caso porque el `QueryClient` de `AdminScreen.tsx`
es un singleton de módulo y `usePermisos()` va con `staleTime: Infinity`
(ADR-027): sin reiniciar el registro de módulos el `['yo']` del caso anterior
seguiría cacheado y el archivo no mediría nada.

#### RED y GREEN de las tres pruebas nuevas

Las tres son **pruebas de caracterización de comportamiento ya
implementado**: no hay RED "natural" porque el código de producción nunca
cambió. Para no agregarlas en verde a ciegas, el RED se obtuvo al revés de
lo habitual: se afirmó lo contrario a propósito, se confirmó que la
aserción corría y fallaba, y recién ahí se corrigió a la expectativa real.

| Prueba | RED (deliberado) | GREEN |
| --- | --- | --- |
| `TestRenovacionConSesionDeshabilitada::test_el_401_persiste_la_revocacion_de_todas_las_familias_del_usuario` | `AssertionError: [('USUARIO_INACTIVO', datetime(…)), ('USUARIO_INACTIVO', datetime(…))]` sobre `all(motivo == "MOTIVO_INVENTADO" …)` — la aserción lee filas reales confirmadas con ambos motivos correctos | `2 passed`, luego `17 passed` en el archivo |
| `TestRenovacionConSesionDeshabilitada::test_el_401_deja_una_auditoria_con_usuario_dispositivo_y_motivo` | `AssertionError: assert UUID('547fcbe3-…') is None` sobre `filas[0].dispositivo_id` — la fila de auditoría existe y trae el dispositivo | ídem |
| `AdminScreenRenovacion.test.tsx::tras renovar el token, "Proveedores" desaparece…` | Con `fijarAccessToken` comentado, la prueba falla (`1 failed`, el `waitFor` del `queryByRole` nunca converge): el enlace sigue en el menú | `1 passed` con la renovación; `2 passed` en el archivo |

Un detalle que vale registrar: el primer intento de RED del caso de
frontend produjo una prueba **verde** en lugar de roja, porque se
había escrito `waitFor(() => expect(getByRole('Proveedores')).toBeInTheDocument())`
—una aserción que el `waitFor` da por cierta en el primer tick, antes de que
resuelva el refetch. Se detectó justamente por eso y se cambió a la
dirección correcta (`queryByRole(…)` `not.toBeInTheDocument()`), que sí
espera. Se anota porque es la forma fácil de escribir un RED que no prueba
nada.

### Cambios de producción del grupo 10

Ninguno. Solo se agregaron pruebas:
`backend/tests/integration/test_auth_api.py` (+2 casos) y
`frontend/tests/unit/areas/admin/AdminScreenRenovacion.test.tsx` (nuevo, +2
casos).

## 10.2 — `grep` de INV-21, SEG-06, ADR-027 y ADR-028

Los cuatro identificadores tienen pruebas que los citan por ID. Evidencia
literal (`Select-String` sobre `backend/tests/**` y `frontend/tests/**`;
`rg` no está disponible en este entorno).

### INV-21 (aislamiento por organización)

`Get-ChildItem -Path tests -Recurse -Include *.py | Select-String -Pattern "INV-21"`
→ **52 coincidencias en 26 archivos**. Las que sostienen este change:

```
tests\integration\test_identidad_yo_api.py:167: 404 queda solo para un producto inexistente o ajeno, INV-21).
tests\integration\test_identidad_yo_service.py:142: inexistente -- nunca datos parciales de otra organización (INV-21).
tests\integration\test_inv21_aislamiento_endpoints_identidad.py:1: """Tarea 12.2 (cierre de INV-21 para el grupo 10.7): cobertura de
tests\integration\test_inv21_aislamiento_endpoints_identidad.py:387: se ignoran"). Regla: INV-21, SEG-07, ADR-027."""
tests\integration\test_inv21_organizacion_siempre_del_token.py:127: Regla: `02` §8, INV-21, SEG-07, ADR-027.
tests\integration\test_identidad_sesion_habilitada.py:128: """INV-21: el usuario existe, pero no en la organización consultada."""
tests\integration\test_identidad_sesion_habilitada.py:139: """Triangulación (tarea 2.9, INV-21): la inactividad de un usuario
```

Ratchet estructural que impide que INV-21 se rompa por una ruta nueva:
`test_inv21_ratchet_rutas.py:202: f"INV-21: {len(sin_cobertura)} ruta(s) de negocio sin cobertura de …"`.

### SEG-06 (el servidor es quien autoriza)

`… Select-String -Pattern "SEG-06"` → **8 coincidencias en 6 archivos**
(backend) y **7 en 7 archivos** (frontend):

```
tests\integration\test_identidad_yo_api.py:508: Regla: SEG-06, ADR-027.
tests\integration\test_identidad_yo_api.py:603: poder hacerlo). Regla: ADR-017, ADR-027, SEG-06.
tests\integration\test_identidad_yo_api.py:694: Regla: ADR-022, ADR-027, SEG-06.
tests\integration\test_inv21_aislamiento_endpoints_identidad.py:312: SEG-06, SEG-07.
tests\integration\test_identidad_sesion_habilitada.py:11: si la causa fue el usuario, el rol, o que no existe (SEG-06, falla cerrada).
tests\integration\test_bus_entrada_rest.py:333: (SEG-06). La dependencia REST rechaza antes de que la petición
tests\integration\test_bus_lote_sincronizacion.py:645: """Escenario "Un lote sin sesión no se procesa" (SEG-06)."""
tests\integration\test_ratchet_permiso_por_ruta.py:64: # (SEG-06, `02` §6.3 paso 4), no de esta ruta. Sí exige sesión
```

Y en el frontend, la red de seguridad del 403 (si el servidor rechaza aunque
la interfaz creía tener el permiso):

```
tests\unit\areas\admin\catalogo\ProductosListScreen.test.tsx:166: it('si el servidor rechaza aunque la interfaz creía tener el permiso, … (red de seguridad, SEG-06)', …
tests\unit\areas\admin\catalogo\CategoriasYMarcasScreen.test.tsx:202: it('si el servidor rechaza aunque la interfaz creía tener el permiso, … (red de seguridad, SEG-06)', …
tests\unit\areas\admin\proveedores\ProveedoresListScreen.test.tsx:77: it('si el servidor rechaza aunque la interfaz creía tener el permiso, … (red de seguridad, SEG-06)', …
tests\unit\areas\admin\proveedores\CostosCargaScreen.test.tsx:368: it('si el servidor rechaza aunque la interfaz creía tener el permiso, … (red de seguridad, SEG-06)', …
tests\unit\areas\admin\proveedores\CostosHistorialScreen.test.tsx:312: it('si el servidor rechaza aunque la interfaz creía tener el permiso, … (red de seguridad, SEG-06)', …
tests\unit\areas\admin\dispositivos\DispositivosScreen.test.tsx:103: it('un 403 del servidor entre dos renovaciones se muestra como falta de permiso, sin listado y sin error genérico (red de seguridad, SEG-06)', …
tests\unit\utils\permisosDePrueba.ts:16:  * siendo quien decide (SEG-06). Si `01` §19 cambia, esta tabla se
```

### ADR-027 (`GET /yo` como fuente única de permisos)

`… Select-String -Pattern "ADR-027"` → **15 coincidencias en 6 archivos**
(backend) y **13 en 7 archivos** (frontend). Las que fijan su regla central
(un pedido por sesión):

```
tests\integration\test_identidad_yo_api.py:2: login reales (`design.md`, "Contrato de `GET /api/v1/yo`", D1, ADR-027).
tests\integration\test_identidad_yo_api.py:335: """`/yo` no exige ningún permiso (ADR-027): un VEN, sin ninguno de
tests\integration\test_identidad_yo_service.py:9: sean, por construcción, la misma función (ADR-027).
tests\integration\test_ratchet_permiso_por_ruta.py:68: # Change 06b, grupo 4 (`identidad/api.py::router_yo`, ADR-027): la
tests\integration\test_ratchet_permiso_por_ruta.py:185: SESIÓN (ADR-027)."""
```

```
tests\unit\areas\admin\AdminLayout.test.tsx:101: it('con los permisos ya sembrados no hace ninguna petición extra a /yo (ADR-027: una consulta por sesión)', …
tests\unit\areas\admin\dispositivos\DispositivosScreen.test.tsx:87: it('con el permiso sembrado no hace ninguna petición extra a /yo (ADR-027: una consulta por sesión)', …
tests\unit\features\identidad\usePermisos.test.tsx:124:  * que el access token (ADR-027, ADR-017).
tests\unit\areas\admin\AdminScreenRenovacion.test.tsx:39:  * (tarea 10.1 del grupo 10 del change 06b, ADR-027: "un pedido extra por
tests\unit\areas\admin\AdminScreenRenovacion.test.tsx:55:  * `staleTime: Infinity` (ADR-027), así que sin reiniciar el registro de
```

### ADR-028 (la sesión exige usuario y rol activos)

`… Select-String -Pattern "ADR-028"` → **16 coincidencias en 7 archivos**
(backend; el frontend no cita el ADR, porque no implementa la regla —la
exige el servidor):

```
tests\integration\test_identidad_sesion_habilitada.py:1: """ADR-028 / D9 (grupo 2 del change 06b): la sesión exige usuario y rol
tests\integration\test_identidad_sesion_habilitada.py:100: """ADR-028 D9.1/D9.2-A."""
tests\integration\test_identidad_sesion_habilitada.py:110: """ADR-028 D9.4-A: un rol con `activo = false` se trata igual que un
tests\integration\test_identidad_sesion_habilitada.py:153: inactivo (ADR-028, defensa en profundidad, D9.1 último punto): ningún
tests\integration\test_identidad_refresh_service.py:348: """ADR-028 D9.3-B (grupo 2, `tasks.md` 2.5): sin jornadas todavía (change
tests\integration\test_identidad_yo_api.py:397: """(D9) ADR-028 D9.2-A: un access token vigente de un usuario que
tests\integration\test_identidad_yo_api.py:426: """(D9) ADR-028 D9.4-A: un rol con `activo = false` se trata igual
tests\integration\test_identidad_yo_service.py:159: """(D9) ADR-028 D9.2-A: un usuario `INACTIVO` rechaza igual que uno
tests\integration\test_identidad_yo_service.py:172: """(D9) ADR-028 D9.4-A: mismo tratamiento que un usuario inactivo."""
tests\integration\test_sesion_usuario_inactivo_api.py:1: """ADR-028 / D9.1-D9.2 a nivel HTTP (grupo 2 del change 06b): con el access
tests\integration\test_sesion_usuario_inactivo_api.py:251: """ADR-028 D9.4-A: mismo tratamiento que un usuario inactivo."""
tests\integration\test_bus_lote_sincronizacion.py:742: """ADR-028 D9.3-B (grupo 2, `tasks.md` 2.7): a diferencia del resto de
tests\integration\test_auth_api.py:688: """ADR-028 D9.1 último punto (grupo 2, `tasks.md` 2.6): un usuario
tests\integration\test_auth_api.py:770: baja no puede renovar su sesión" (ADR-028 D9.2-A / D9.4-A), y el requisito
```

Las cuatro opciones aprobadas tienen al menos una prueba que las nombra:
D9.1/D9.2-A (`test_identidad_sesion_habilitada.py:100`,
`test_auth_api.py:688`), D9.3-B (`test_identidad_refresh_service.py:348`,
`test_bus_lote_sincronizacion.py:742`) y D9.4-A
(`test_identidad_sesion_habilitada.py:110`, `test_identidad_yo_api.py:426`).

## 10.3 — Suite completa contra la línea base de 1.1

### Backend

| Comando | Línea base (1.1) | Resultado del grupo 10 | Estado |
| --- | --- | --- | --- |
| `python -m ruff check .` | `All checks passed!` | `All checks passed!` | Verde |
| `python -m ruff format --check` (archivos tocados) | 1 archivo previo a reformatear (`app/modules/identidad/api.py`), **falla previa reportada, no de este change** | `1 file already formatted` (solo `tests/integration/test_auth_api.py`, el único archivo tocado) | Verde |
| `python -m mypy app` | `Success: no issues found in 79 source files` | `Success: no issues found in 79 source files` | Verde |
| `lint-imports` | `10 contratos, 0 rotos` | `Contracts: 10 kept, 0 broken` | Verde |
| `pytest tests/unit` | — | `322 passed` | Verde |
| `pytest tests/properties` | — | `5 passed` | Verde |
| `pytest tests/fixtures_compartidos` | `383 passed` (los tres juntos) | `56 passed` (los tres juntos: `322 + 5 + 56 = 383`) | Verde |
| `pytest tests/integration` | `522 passed` (1.1) / `573 passed` (9.6) | **`575 passed`**, 12 warnings, 155.71s | Verde |

Sobre el contrato de importaciones: en este venv `python -m import_linter`
no es invocable; el ejecutable del paquete,
`.venv\Scripts\lint-imports.exe`, corre el contrato completo y es el que da
las cifras de arriba (mismo criterio que se registró en 9.6).

Los `575` son los `573` de 9.6 más los `2` casos nuevos de
`test_auth_api.py` (`TestRenovacionConSesionDeshabilitada`).

### Frontend

| Comando | Línea base (1.1) | Resultado del grupo 10 | Estado |
| --- | --- | --- | --- |
| `npm run typecheck` | Limpio | Sin salida de `tsc` | Verde |
| `npm run lint` | `0 errores`, `2` warnings | `0 errores`, `2` warnings (las mismas dos: `react-hooks/incompatible-library` por `watch()` de RHF, en `ProductoFormScreen.tsx` y `CostosCargaScreen.tsx`) | Verde |
| `npm run test` | `208 passed, 1 failed` (flake, ver abajo) | `36 archivos`, **`272 passed`**, 0 fallidos | Verde |
| `npm run build` | Exitoso | `✓ built in 459ms` | Verde |

Los `272` son los `270` de 8.7 más los `2` casos nuevos de
`AdminScreenRenovacion.test.tsx`.

### Dos flakes preexistentes, reportados y **no** arreglados

Ninguno es una regresión de este grupo, y en los dos casos la 1.1 ya había
decidido no tocarlos ("se reporta como hallazgo, no se arregla acá"). Se
respetó esa decisión: no se modificó ni `app-routing.test.tsx` ni
`test_identidad_yo_api.py`.

1. **`app-routing.test.tsx` > "redirige /admin al inicio de sesión".**
   Ya registrado en 1.1. Se reproduce de forma intermitente cuando la suite
   corre completa: `AppRoutes` carga `AdminScreen` con `React.lazy` y el
   `findByRole` con el `timeout` por defecto de 1 s vence antes de que
   resuelva el chunk, dejando el árbol vacío (un `<div />`), no un error de
   ruteo. Al correr aislado pasa siempre. En este grupo se reprodujo **1 de
   5** corridas completas con `36` archivos; las otras 4 fueron `36 passed /
   272 passed`. El archivo se dejó intacto.
2. **`test_identidad_yo_api.py::TestYoContrato::test_token_con_firma_alterada_da_401_invalido`.**
   No estaba registrado antes. Falló **1 de 2** corridas completas de
   integración en la primera vez (`574 passed, 1 failed`) y pasó en las
   siguientes: `575 passed` dos veces, y `14 passed` al correr el archivo
   aislado. No se investigó más porque no es de este change y no es
   reproducible de forma estable; queda como hallazgo para el próximo change
   que toque el arnés de integración.

### Integración

No hubo migraciones, ni cambios de esquema, ni `docker compose restart`, ni
cambios en `docs/`. El único ajuste de este grupo fue `ruff format` sobre el
archivo de pruebas que se tocó.

## 10.4 — Documentación (aplicada el 2026-09-27)

> **Aplicada el 2026-09-27.** Esta tarea pedía *preparar* la actualización de la
> documentación; el usuario revisó las propuestas y aprobó un conjunto acotado.
> Se aplicaron cuatro ítems: (a) las dos celdas de la fila 06b, (b) la deuda
> nominada del paso 4 de `02` §6.3, (c) la nota D9.5, y (d) la línea de ADR-028 en
> `docs/02-arquitectura.md` §12.1. Abajo queda el texto exacto que se escribió,
> más lo que se descartó y por qué. `docs/referencia/` no se tocó, no se agregó
> ningún ADR nuevo, y ni ADR-027 ni ADR-028 fueron modificados.

### 10.4.1 ADR-028: confirmado *Vigente* con las opciones aprobadas

Verificado leyendo `docs/adr/ADR-028-sesion-exige-usuario-y-rol-activos.md`:

| Campo | Valor leído | Estado |
| --- | --- | --- |
| Estado | `Vigente` | Ya correcto, no hay nada que cambiar |
| Fecha | `2026-09-25` | Ya correcto |
| Opciones aprobadas | D9.1, D9.2-A, D9.3-B, D9.4-A | Registradas en el encabezado del ADR |
| Nota futura | D9.5 (change de baja de usuarios y roles) | Registrada como nota, no como decisión |
| Referenciado en | ADR-011, ADR-012, ADR-017, ADR-027; `01` SEG-01/06, SYN-05/06/09/10, RUT-05/09; `02` §6.3, §6.4, §12.1, §12.3; `03` §4; `design.md` D9 | Completo |

**Nada que proponer acá.** El ADR está en el estado correcto y ya fue aprobado
por el usuario; no hay enmienda pendiente ni un ADR nuevo que redactar. La
tarea 0.7 (enmienda de ADR-027 con B1/B2) quedó **rechazada** por el usuario el
2026-09-27, así que sigue `[ ]` y `docs/adr/ADR-027-permisos-efectivos-para-la-interfaz.md`
queda sin tocar.

### 10.4.2 Para `docs/04-roadmap-changes.md` — (a), (b) y (c) aplicadas

**(a) Fila 06b de la tabla de la etapa 1** (`docs/04-roadmap-changes.md`
L109). Antes de la decisión, la celda "Entrega" mencionaba solo ADR-027 y la de
"Invariantes que cierra" decía `INV-21 (sobre /yo)`. Se reemplazaron las dos
celdas por estas:

| # | Change | Entrega | Invariantes que cierra |
| --- | --- | --- | --- |
| 06b | `permisos-efectivos-interfaz` | `GET /api/v1/yo` (usuario, organización, rol y permisos efectivos, misma fuente que la autorización del servidor); en `/admin`, hook `usePermisos()` y `<SiTienePermiso>` para menú y pantallas, refrescados en cada renovación del access token; retiro del patrón "403 → ocultar" de las pantallas de los changes 03 a 06 (ADR-027); cierre de la brecha de sesión: toda petición autenticada exige usuario `ACTIVO` y rol `activo`, con revocación de las familias de refresh y auditoría, sin cerrar la cola offline (ADR-028) | INV-21 (sobre `GET /yo`) |

**(b) Deuda nominada para el change de permisos por comando en el lote.**
Agregada al bloque de deudas de la etapa 1, con la misma forma
("**Deuda nominada por el change 06b …**") que las de los changes 05 y 06 ya
presentes en el archivo (L119, L121, L123). Este es el texto final que se
escribió, con la corrección de encuadre de D9.3-B:

> **Deuda nominada por el change 06b (`permisos-efectivos-interfaz`) para el change 15 (`jornadas`) o el 18a (`venta-online-core`):** `POST /api/v1/sync/comandos` todavía no aplica el paso 4 de `02` §6.3 (permisos por comando, online y offline) — `sync/api.py` lo dejó para cuando existan comandos `OFFLINE` y jornadas (change 15). Cuando ese change implemente los permisos por comando, la parte offline de ADR-028 queda implementable: los comandos `OFFLINE` de un usuario `INACTIVO` o de un rol con `activo = false` se **aceptan con `PERMISO_REVOCADO`** (SYN-10), nunca se rechazan, y el lote se procesa ítem por ítem igual que para un usuario activo. Junto con eso hay que **implementar la excepción de renovación con jornada no cerrada** (D9.3-B), que quedó aprobada el 2026-09-25 junto con ADR-028 y cuya implementación se difiere al change de jornadas: hasta entonces, sin jornadas, un usuario dado de baja con cola pendiente ve su renovación rechazada sin más (D9.1/D9.2-A) porque no hay forma de distinguir "no tiene nada que subir" de "tiene la cola bloqueada"; cuando exista `jornada`, la renovación debe admitirse para que el lote de esa jornada pueda llegar al servidor. Lo que hoy está probado de D9.3-B es solo "el canal de la cola sigue abierto para el usuario inactivo" (`test_bus_lote_sincronizacion.py::TestUsuarioInactivoNoSeRechazaPorRuta`), no la excepción a la renovación.

> **Corrección de encuadre aplicada respecto de la propuesta.** El texto
> preparado decía que D9.3-B "no está aprobada" y ofrecía como "alternativa"
> una redacción que sí lo afirmaba. Ese encuadre era incorrecto:
> `docs/adr/ADR-028-sesion-exige-usuario-y-rol-activos.md` L9 y L77 registran
> que **D9.1, D9.2-A, D9.3-B y D9.4-A fueron aprobadas por el usuario el
> 2026-09-25**. Lo que se difiere al change de jornadas es la
> **implementación** de la excepción de renovación, no la decisión. Por eso
> "hay que resolver la excepción" pasó a "hay que **implementar** la
> excepción (D9.3-B), que quedó aprobada el 2026-09-25 junto con ADR-028 y
> cuya implementación se difiere al change de jornadas", y se eliminó la frase
> del "alternativa" (que queda registrada acá, y en la nota de `tasks.md`,
> como parte del rastro de auditoría). Todo el contenido técnico se conservó
> intacto: la brecha del paso 4 de `02` §6.3, los comandos `OFFLINE` de un
> usuario `INACTIVO` o de un rol con `activo = false` aceptados con
> `PERMISO_REVOCADO` (SYN-10) y nunca rechazados, el procesamiento del lote
> ítem por ítem, y el alcance real de lo que hoy está probado de D9.3-B.

**(c) Nota para el change de usuarios y roles (D9.5).** Agregada junto a la
deuda (b), como una entrada más del bloque de deudas de la etapa 1:

> **Nota del change 06b (`permisos-efectivos-interfaz`) para el change de usuarios y roles (D9.5):** hoy la brecha que ADR-028 cerró es **latente**, y por eso está cerrada antes de existir el comando que la abriría: ningún comando cambia `usuario.estado` ni desactiva un `rol.activo` (los de `identidad` son `USUARIO_CREAR`, `USUARIO_DESBLOQUEAR`, `ROL_PERMISOS_CAMBIAR`, `DISPOSITIVO_REVOCAR` y `PIN_AUTORIZACION_ROTAR`). Ese change, que nace con la baja de usuarios y la de roles, tiene que escribir por el bus de comandos y cumplir el mismo criterio de ADR-028 en cada caso: un usuario que pasa a `INACTIVO` pierde el acceso en la petición siguiente y sus familias de refresh quedan revocadas con auditoría `REVOCAR_SESIONES_REFRESH_USUARIO`; un rol con `activo = false` corta el acceso de sus usuarios igual que un usuario inactivo (D9.4-A); y la baja **no** puede rechazar la cola offline del dispositivo. Ese change es también el que tiene que decidir el motivo de auditoría de cada caso, que hoy solo existe para `USUARIO_INACTIVO` y `ROL_INACTIVO`.

### 10.4.3 Para `docs/02-arquitectura.md` — (d) aplicada, (e) rechazada

La tarea pide *evaluar con el usuario* si §12.1 o §12.3 suman una línea que
remita a ADR-028, como ya hacen con ADR-027. Leídas las dos secciones:

- **§12.1 Tokens** ya tiene la línea de ADR-027 ("Permisos para la interfaz
  (ADR-027): … Ocultar una acción nunca reemplaza la validación del servidor
  (SEG-06)"). Es el lugar natural para la regla de ADR-028, porque es la que
  define qué es una sesión válida. **Esta opción se aplicó** (ítem (d)), como
  línea nueva a continuación de la de ADR-027:

  > - **Sesión habilitada (ADR-028):** toda petición autenticada que no sea el lote de sincronización se rechaza si el usuario está `INACTIVO` o su rol tiene `activo = false`, en la petición siguiente y sin esperar al vencimiento del access token. `GET /api/v1/yo` rechaza en vez de devolver una lista vacía. La renovación (`refresh`) revoca las familias de refresh del usuario y deja auditoría antes de rechazar, para que la sesión revocada no pueda revivir con una reactivación.

- **§12.3 Sesión sin conexión** es donde está la tensión que ADR-028
  documenta (la cola del teléfono no debe quedar sin forma de subir), pero su
  texto actual ("la cola se conserva y se sincroniza cuando inicia sesión el
  mismo usuario") es la regla de siempre; el matiz de ADR-028 es que ese
  "el mismo usuario" tiene que poder renovar. Si se prefiere no duplicar la
  regla en dos lugares, la alternativa era una línea de remisión corta:

  > - El lote de sincronización es la única vía que acepta un usuario dado de baja (ADR-028, D9.3-B), y solo por ítem.

  **El usuario rechazó esta alternativa (ítem (e)) por duplicar (d)**: las dos
  formas dicen lo mismo de ADR-028 y `docs/02-arquitectura.md` queda con una
  sola mención. Por eso `docs/02-arquitectura.md` §12.3 **no se editó**. La
  línea de arriba queda registrada solo como propuesta descartada.

`docs/02-arquitectura.md` §12.1 sí se editó; §12.3 quedó intacto.

### 10.4.4 Estado (después de la decisión del usuario del 2026-09-27)

| Ítem | Preparado | Aplicado | Decisión del usuario |
| --- | --- | --- | --- |
| ADR-028 confirmado *Vigente* | Sí (10.4.1) | No hace falta: ya estaba *Vigente* | Ninguna, verificado en lectura |
| Fila 06b en `docs/04` (a) | Sí (10.4.2 a) | **Sí**, `docs/04-roadmap-changes.md` L109 | Aprobado |
| Deuda del paso 4 de `02` §6.3 (b) | Sí (10.4.2 b) | **Sí**, `docs/04-roadmap-changes.md` L125, con la corrección de D9.3-B | Aprobado, con corrección de encuadre |
| Nota D9.5 para usuarios y roles (c) | Sí (10.4.2 c) | **Sí**, `docs/04-roadmap-changes.md` L127 | Aprobado |
| Línea de ADR-028 en `docs/02` §12.1 (d) | Sí (10.4.3) | **Sí**, `docs/02-arquitectura.md` L487 | Aprobado |
| Línea de remisión en `docs/02` §12.3 (e) | Sí (10.4.3) | **No** | **Rechazada**: duplica (d) |
| Enmienda de ADR-027 con B1/B2 (0.7) | — | **No** | **Rechazada**: 0.7 sigue `[ ]` y ADR-027 queda intacto |

Archivos escritos: `docs/04-roadmap-changes.md` y `docs/02-arquitectura.md`.
Archivos explícitamente **no** tocados: `docs/referencia/`,
`docs/adr/ADR-027-permisos-efectivos-para-la-interfaz.md` y
`docs/adr/ADR-028-sesion-exige-usuario-y-rol-activos.md`. No se agregó ningún
ADR nuevo. Esta tarea no corrió la suite, `ruff`, `mypy` ni Docker: es solo
documentación.

## 10.5 — Verificación manual en el navegador (script para el usuario)

> **EJECUTADA por el usuario el 2026-09-28** (requiere navegador y una base
> levantada): pasos 1-13 completos. Todo ✅ salvo un hallazgo en el paso 13
> (D9), cerrado con el grupo 11 (§11) y re-verificado el mismo día. Los
> contratos de abajo son los reales del backend, corregidos con la ejecución
> (ver "Correcciones" al pie):
>
> | Dato | Fuente leída |
> | --- | --- |
> | `POST /api/v1/auth/login` → `{organizacion_slug, usuario, contrasena, dispositivo_id, nombre_dispositivo}` → `{access_token, token_type}` | `app/api_v1/auth.py::LoginRequest`, `::TokenResponse` |
> | Refresh en cookie `HttpOnly`, y `POST /api/v1/auth/refresh` → `{dispositivo_id}` | `app/api_v1/auth.py::_fijar_cookie_refresh`, `::RefreshRequest` |
> | `GET /api/v1/yo` con `Authorization: Bearer <access_token>` | `app/modules/identidad/api.py::router_yo` (prefix `/yo`, sin permiso) |
> | `POST /api/v1/identidad/usuarios` → `{usuario, nombre, email, password, rol_id}` | `app/modules/identidad/api.py::CrearUsuarioRequest` |
> | `PUT /api/v1/identidad/roles/{rol_id}/permisos` → `{permisos: [...]}` | `app/modules/identidad/api.py::ComposicionRolRequest` |
> | Escrituras de negocio exigen el encabezado `Operation-Id`, que **debe ser un UUID** (cualquier otro formato responde 400 `OPERATION_ID_INVALIDO`; SYN-01, TR-07) | `app/core/autenticacion.py:164` |
> | `dispositivo_id` es un UUID, no el prefijo legible; `nombre_dispositivo` es el nombre legible del dispositivo (requerido) | `app/api_v1/auth.py::LoginRequest`, `dispositivo` (ADR-011) |
> | Org `organizacion-inicial`, usuario `admin` | `app/seed.py:45`, `NOMBRE_USUARIO_ADMINISTRADOR = "admin"` |
> | Roles de plantilla: `Administración`, `Supervisor comercial` | `app/modules/identidad/domain/permisos.py` (`PLANTILLAS_DE_ROL`) |
> | Postgres en `localhost:5432`, base/usuario `distribuidora` | `docker-compose.yml` |
>
> **Correcciones de la ejecución (2026-09-28):** (1) el login lleva
> `nombre_dispositivo` — en el script original faltaba y el body sin ese campo
> daba error de decode en el backend; (2) los `Operation-Id` de ejemplo eran
> legibles (`06b-manual-…`) y el backend los rechaza con 400
> `OPERATION_ID_INVALIDO` — abajo van como `<UUID>`; (3) D9 se verifica
> **por petición**, no al vencimiento del token (sección 10); (4) matiz de
> "reactivar no revive la sesión" (paso 10.4).
>
> Formato tomado de la 13.5 del change 06
> (`openspec/changes/archive/2026-09-25-06-proveedores-y-costos-informados/verificacion.md`).
> Mismo formato, pasos de este change.

> **Si las pantallas de `/admin` se ven sin estilo** al abrir el navegador por
> primera vez: `docker compose restart frontend` y recargar (limitación conocida
> del *bind mount* de Vite en Docker Desktop sobre Windows, no un defecto de este
> change).

### 1. Preparación

> **Windows / PowerShell:** los comandos son `docker compose`/`psql`, iguales en
> cualquier shell, salvo `curl` (usar `curl.exe` en PowerShell, que es el que
> el `curl` de PowerShell no es). Pegar un comando por línea.

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec -e ADMIN_PASSWORD=CAMBIAR_ESTA_CLAVE backend python -m app.seed
curl.exe http://localhost:8000/api/v1/salud
```

> Este change **no agrego migraciones** (no toca el esquema), así que
> `alembic upgrade head` solo sirve si la base quedó de un change anterior. La
> siembra tampoco hace falta si la base ya viene sembrada: `app/seed.py` avisa
> "La organización inicial ya estaba sembrada: no se hizo nada" y sale.

### 2.0. Access token del ADM (por API, para los `curl` de escritura)

Los `curl.exe` de los pasos 2 y 6 necesitan el access token del ADM (el login
del navegador, paso 3, no produce token para la terminal). En PowerShell,
`curl.exe` se "come" las comillas dobles del `-d` y el backend responde error
de decode JSON; usar `Invoke-RestMethod`, que no tiene ese problema:

```powershell
$login = @{ organizacion_slug='organizacion-inicial'; usuario='admin'; contrasena='<ADMIN_PASSWORD>'; dispositivo_id=[guid]::NewGuid().ToString(); nombre_dispositivo='manual-verificacion' } | ConvertTo-Json
$resp = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/auth/login -ContentType 'application/json' -Body $login
$env:TOKEN_ADM = $resp.access_token
```

> `dispositivo_id` y `nombre_dispositivo` son obligatorios en el login
> (contrato corregido el 2026-09-28; en el borrador original faltaba
> `nombre_dispositivo`).

### 2. Usuarios de prueba (GES y SUP)

Con el ADM logueado, obtener los `rol_id` por `psql`:

```bash
docker compose exec postgres psql -U distribuidora -d distribuidora -c "SELECT nombre, id FROM rol WHERE organizacion_id = (SELECT id FROM organizacion WHERE slug = 'organizacion-inicial') ORDER BY nombre;"
```

Anotar el UUID de **Administración** (`ROL_GES`) y el de **Supervisor
comercial** (`ROL_SUP`). No se usan los nombres: `rol_id` es un UUID.

Luego, en **otra** terminal, con el access token del ADM
(`$TOKEN_ADM`, obtenido en el paso 2.0), crear un usuario GES y uno SUP. Cada
escritura de negocio lleva su propio `Operation-Id`, y un reenvío con el mismo
identificador devuelve el mismo resultado:

```bash
curl.exe -X POST http://localhost:8000/api/v1/identidad/usuarios -H "Authorization: Bearer <ACCESS_TOKEN_ADM>" -H "Content-Type: application/json" -H "Operation-Id: <UUID-1>" -d "{\"usuario\":\"ges01\",\"nombre\":\"Gestor 01\",\"email\":null,\"password\":\"CAMBIAR_ESTA_CLAVE\",\"rol_id\":\"<ROL_GES>\"}"
curl.exe -X POST http://localhost:8000/api/v1/identidad/usuarios -H "Authorization: Bearer <ACCESS_TOKEN_ADM>" -H "Content-Type: application/json" -H "Operation-Id: <UUID-2>" -d "{\"usuario\":\"sup01\",\"nombre\":\"Supervisor 01\",\"email\":null,\"password\":\"CAMBIAR_ESTA_CLAVE\",\"rol_id\":\"<ROL_SUP>\"}"
```

> Los `Operation-Id` **deben ser UUID**, p. ej. `[guid]::NewGuid().ToString()`
> en PowerShell (el borrador original usaba `06b-manual-…` y el backend
> responde 400 `OPERATION_ID_INVALIDO`).

- Las dos respuestas deben ser `201` con el usuario creado.
- Si una responde `409` (usuario duplicado), es que ya existía de una corrida
  anterior: seguir, no es un fallo.
- Un `403` acá sí es un fallo: el `POST /usuarios` exige `ADMIN_USUARIOS` y el
  encabezado `Operation-Id` (SYN-01).

### 3. Login ADM

- URL: `http://localhost:5173`
- Organización (slug): `organizacion-inicial`
- Usuario: `admin`
- Contraseña: la definida en `ADMIN_PASSWORD`

Verificar:

1. Aterriza en **Catálogo** (primera sección permitida de `/admin/inicio`).
2. El menú muestra **Catálogo, Proveedores y Dispositivos**.
3. El encabezado dice `Administrador · Organización inicial · Administrador`.
4. En la ficha de un producto (Catálogo → cualquier producto sembrado) ve el
   enlace **"Ver historial de costos"**.
5. En la pestaña **Red** de las devtools, al abrir esa ficha, **no** hay
   ningún pedido a `/costos/.../vigente`: el permiso sale de `GET /yo`, no de
   una consulta extra por pantalla (ADR-027, una consulta por sesión).

### 4. Login GES

- Cerrar sesión del ADM e iniciar con `ges01`.

1. Aterriza en **Catálogo** y el menú muestra **Catálogo y Proveedores**, sin
   **Dispositivos**.
2. Escribir `/admin/dispositivos` en la barra de direcciones muestra
   "No tenés permiso…" (no una pantalla vacía).
3. En la pestaña **Red**, tras ese intento, **no** aparece
   `GET /api/v1/identidad/dispositivos` (la pantalla no pide sus datos para
   después ocultarlos).

### 5. Login SUP

- Cerrar sesión e iniciar con `sup01`.

1. Aterriza en **Dispositivos** y el menú muestra **solo esa sección**.
2. Escribir `/admin/proveedores` y luego `/admin/catalogo` muestra el mensaje
   de falta de permiso, y en la pestaña **Red** no aparece ningún pedido de
   datos de catálogo ni de proveedores.
3. `/admin/dispositivos` sí lista los dispositivos con estado, prefijo y
   último correlativo.

### 6. Revocación en vivo (el corazón del change)

Con **GES** logueado, y el ADM disponible en otra terminal con su token:

```bash
curl.exe -X PUT http://localhost:8000/api/v1/identidad/roles/<ROL_GES>/permisos -H "Authorization: Bearer <ACCESS_TOKEN_ADM>" -H "Content-Type: application/json" -H "Operation-Id: <UUID-3>" -d "{\"permisos\":[\"GESTIONAR_CATALOGO\",\"GESTIONAR_CLIENTES\",\"GESTIONAR_CREDITO\",\"VER_COSTOS\",\"EDITAR_COSTOS\",\"VER_UTILIDAD\",\"GESTIONAR_LISTAS\",\"REGISTRAR_COMPRA\"]}"
```

(Se quita `GESTIONAR_PROVEEDORES` de la composición de Administración: es la
única diferencia con la plantilla de `app/modules/identidad/domain/permisos.py`.
Si la respuesta trae la lista de permisos tal como se mandaron, el comando
pasó.)

1. En GES, **antes** de que se renueve el access token, abrir
   `/admin/proveedores`: el servidor responde **403** y la pantalla muestra
   "No tenés permiso…" (no se queda en blanco ni muestra un error genérico de
   red).
2. **Después** de la renovación del access token, "Proveedores" **desaparece
   del menú sin recargar la página**. Para verlo sin esperar 15 minutos hay
   que producir el `401` que dispara la renovación: dejar vencer el token y
   hacer cualquier acción en `/admin`. **Lo que hay que comparar es el punto 1
   con este**: antes del refetch el servidor manda 403; después del refetch de
   `/yo` el enlace ni siquiera está.
3. **Restaurar el permiso** al terminar, o el resto del script queda con un
   rol Administración sin `GESTIONAR_PROVEEDORES`:

```bash
curl.exe -X PUT http://localhost:8000/api/v1/identidad/roles/<ROL_GES>/permisos -H "Authorization: Bearer <ACCESS_TOKEN_ADM>" -H "Content-Type: application/json" -H "Operation-Id: <UUID-4>" -d "{\"permisos\":[\"GESTIONAR_CATALOGO\",\"GESTIONAR_CLIENTES\",\"GESTIONAR_CREDITO\",\"GESTIONAR_PROVEEDORES\",\"VER_COSTOS\",\"EDITAR_COSTOS\",\"VER_UTILIDAD\",\"GESTIONAR_LISTAS\",\"REGISTRAR_COMPRA\"]}"
```

> Aclaración sobre el punto 2, para que no se lea como un fallo: en esta
> implementación la renovación del access token la dispara `httpClient` al
> recibir un `401`, y el `wait` de 15 minutos es del token, no de un botón.
> Si el access token de GES sigue vivo, la forma limpia de forzar el ciclo es
> expirarlo (esperar, o invalidarlo en la base con `UPDATE sesion…`), lo que
> produce el `401` que dispara la renovación. El script no inventa un disparador
> que la app no tiene.

### 7. `/yo` directo

Con el access token de GES (el del paso 4):

```bash
curl.exe http://localhost:8000/api/v1/yo -H "Authorization: Bearer <ACCESS_TOKEN_GES>"
```

1. Devuelve `200` con `usuario`, `organizacion`, `rol` y `permisos`, y los
   permisos **en orden alfabético**.
2. Sin encabezado `Authorization` devuelve **401**.
3. Con un token de firma alterada devuelve **401** con el mismo rechazo que
   uno inexistente (no revela cuál de los dos).
4. La respuesta **no** trae `password_hash`, ni `contrasena`, ni el estado del
   usuario, ni topes de crédito.

### 8. Almacenamiento

En las devtools → **Aplicación** → *Local Storage*, *Session Storage* e
*IndexedDB*, con GES logueado y después de navegar por Catálogo, Proveedores y
la ficha de un producto:

1. Ninguna clave contiene la respuesta de `/yo` ni los códigos de permiso.
2. El access token **no** está en `localStorage`, ni en `sessionStorage`, ni en
   `document.cookie`: vive solo en memoria.
3. Solo hay un `dispositivo_id` (UUID) en IndexedDB, que es lo permitido.

### 9. `/ruta`

Sin cambios visibles: entrar a `/ruta` sigue funcionando igual que antes del
change. Este change no toca el bootstrap de `/ruta` ni los permisos de la
pantalla de venta; usa los permisos del bootstrap (SYN-10, SYN-11) como ya
definía ADR-027. Si algo cambia acá, es un defecto de este change.

### 10. (D9) Usuario inactivo

Con el **GES** logueado en `/admin`, pasarlo a `INACTIVO` por `psql` (todavía
no hay comando de baja; por eso va directo a la base):

```bash
docker compose exec postgres psql -U distribuidora -d distribuidora -c "UPDATE usuario SET estado = 'INACTIVO' WHERE usuario = 'ges01' AND organizacion_id = (SELECT id FROM organizacion WHERE slug = 'organizacion-inicial');"
```

1. **La siguiente acción en `/admin` termina en el aviso de sesión
   terminada** con enlace a "iniciar sesión", no en un error de red ni en una
   pantalla vacía. Desde el grupo 11 el corte es inmediato y determinístico:
   la verificación de usuario activo es **por petición** (D9), así que
   cualquier acción con el usuario `INACTIVO` devuelve 401 en el acto — no
   hay que esperar el vencimiento del access token, como decía este script
   antes de la corrección del 2026-09-28 —; la renovación es rechazada, la
   app pasa a "sesión terminada" y el encabezado muestra el aviso "Iniciar
   sesión".
2. Iniciar sesión con `ges01` da el **mensaje genérico de credenciales**, el
   mismo que con una contraseña incorrecta: no revela que el usuario existe y
   está de baja.
3. `curl.exe` a `/yo` con el último access token de GES da **401**:

```bash
curl.exe http://localhost:8000/api/v1/yo -H "Authorization: Bearer <ACCESS_TOKEN_GES_ANTERIOR>"
```

4. Reactivar el usuario **no revive la sesión del navegador**: la app ya está
   en "sesión terminada" (el intento de renovación con el usuario inactivo
   revocó la familia del refresh, ADR-011) y hace falta un login nuevo. Matiz
   para `curl`: `/yo` lee el estado **por petición**, así que con el mismo
   access token (si sigue dentro de sus 15 minutos) y el usuario de nuevo en
   `ACTIVO`, vuelve a responder 200; el 401 persiste solo si el token ya
   venció. (El borrador original decía que el mismo token anterior sigue
   dando 401; eso vale para la sesión del navegador, no para el token
   stateless.)

```bash
docker compose exec postgres psql -U distribuidora -d distribuidora -c "UPDATE usuario SET estado = 'ACTIVO' WHERE usuario = 'ges01' AND organizacion_id = (SELECT id FROM organizacion WHERE slug = 'organizacion-inicial');"
```

> El `UPDATE` directo a la base es aceptable **solo** en este script manual:
> `usuario` no es una tabla de libro y el usuario de aplicación sí puede
> escribirla, pero la escritura de negocio tiene que pasar por el bus de
> comandos. Cuando exista el comando de baja (D9.5), esto deja de ser
> necesario — y ahí empieza la deuda que la 10.4 nombra.

### 11. Cierre (dejar el entorno como estaba)

Devolver lo que este script cambió:

- Restaurar `GESTIONAR_PROVEEDORES` en Administración (paso 6.3) — o el rol
  queda distinto de su plantilla.
- `ges01` y `sup01` en `ACTIVO` (ya hecho en el paso 10.5).
- Se pueden dejar los dos usuarios de prueba: no tienen permisos de
  escritura salvo `ges01` sobre catálogo, clientes, crédito y costos.

## 12 — Hallazgo de la 10.5 y su cierre (grupo 11)

> **Hallazgo (2026-09-28, paso 10 D9).** Con el usuario en `INACTIVO`, el
> backend responde 401 por petición y rechaza la renovación (correcto,
> ADR-028 D9). Pero el aviso de "Iniciar sesión" de la spec
> (`permisos-efectivos`, B1) no aparecía: una consulta de datos fallaba
> mostrando su propio error ("No se pudo obtener el producto") y al recargar
> con la sesión muerta la pantalla quedaba en blanco.
>
> **Causa raíz.** En TanStack Query v5, `queryClient.removeQueries(['yo'])`
> **destruye** la consulta, y el observer del menú queda suscrito a ese objeto
> destruido sin recrearlo: con la consulta en vuelo se cancela en silencio
> (observer en `pending` para siempre → blanco) y con datos viejos conserva el
> resultado (menú obsoleto). El aviso de `AdminLayout` solo se renderiza con
> `estado === 'error'`, así que nunca terminaba de aterrizar.
>
> **Cierre (grupo 11, 2026-09-28).** El corte de sesión ahora es
> determinístico e inmediato:
> - la renovación rechazada marca la sesión como terminada en el frontend
>   (`tokenStore.sesionTerminada()`);
> - la consulta `['yo']` se **resetea** (no se destruye) y falla con 401 en el
>   acto (`retry: false` + fast-fail en `obtenerYo` cuando la sesión terminó);
> - `AdminLayout` muestra el aviso con enlace "Iniciar sesión" sin depender de
>   qué pantalla disparó el 401;
> - la **restauración de sesión** queda protegida: en una recarga normal (sin
>   sesión terminada) el access token no está y la cookie del refresh sigue
>   viva, y `/yo` → 401 → renovación → reintento con token nuevo (test de
>   guarda).
>
> **Pruebas.** RED antes de tocar producción (11 fallos):
> `frontend/tests/unit/areas/admin/AdminScreenSesionTerminada.test.tsx`
> (integración: árbol real + `httpClient` real + `fetch` simulado; 4 casos:
> 401 en GET de datos, 401 en DELETE desde otra pantalla y otro rol, montaje
> sin token, recarga) + unit en `tokenStore`, `features/identidad/api`,
> `httpClient` y `usePermisos`. Gates: `typecheck` limpio, `lint` 0 errores,
> `test --run` 288/288, `build` OK.
>
> **Re-verificación (2026-09-28, por el usuario).** Con `ges01` en
> `INACTIVO`, la siguiente acción en `/admin` y la recarga aterrizan de
> inmediato en el aviso "Iniciar sesión". **Verificación completa.**



