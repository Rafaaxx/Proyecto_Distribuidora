"""INV-21 (`docs/01-dominio.md` §20; `design.md` D1 del change 02): ratchet
de rutas.

Recorre dinámicamente las rutas registradas de FastAPI (`app.openapi()["paths"]`,
que refleja el path completo con prefijo, a diferencia de `app.routes` cuyas
rutas anidadas no exponen el path resuelto en esta versión de FastAPI) y
falla nombrando ruta y método si aparece una ruta de negocio que no está en
`COBERTURA_DE_AISLAMIENTO`.

Tarea 12.1 (change 03) cierra lo que el change 02 dejó parcial (`design.md`
D1 de ese change: "hoy la prueba de rutas pasa sin ejercitar nada de
negocio... el change 03 no puede agregar su primer endpoint sin que la
suite se ponga roja hasta cubrirlo"): las rutas de negocio del grupo 10.7
(usuarios, roles, PIN, dispositivos, desbloqueo) ya están declaradas en
`COBERTURA_DE_AISLAMIENTO`, cada una con su prueba real en
`test_identidad_api_usuarios.py` / `test_inv21_aislamiento_endpoints_identidad.py`
(HTTP, con `login` real de un usuario de otra organización, nunca un JWT
fabricado a mano con `emitir_access_token`). Las rutas de `/auth` quedan
exentas en `RUTAS_DE_AUTENTICACION`, separadas de `RUTAS_DE_SISTEMA`,
porque operan sin organización en contexto (spec `aislamiento-multiorganizacion`,
escenario "Las rutas de autenticación quedan exentas por operar sin
organización en contexto").

CÓMO DECLARAR UNA RUTA NUEVA (tarea 9.2/12.1, para los changes siguientes):
cuando un módulo agrega una ruta de negocio, agregar la tupla
`(metodo, "/api/v1/<ruta>")` a `COBERTURA_DE_AISLAMIENTO` en este archivo,
junto con la prueba de integración que demuestra su aislamiento real:
- dos organizaciones, cada una con su propio usuario autenticado por
  `POST /api/v1/auth/login` (login real, NUNCA un access token fabricado a
  mano con `emitir_access_token`, porque eso no prueba que el flujo de
  autenticación real produzca un contexto correcto);
- el usuario de la organización B ejerce la ruta sobre un recurso de la
  organización A (o, para una ruta de alta, con una referencia -- p. ej.
  `rol_id` -- que pertenece a la organización A);
- la respuesta indica "no encontrado", nunca un error de infraestructura ni
  un 200/201/204 que hubiera modificado o expuesto el recurso ajeno.
Sin esa prueba, no agregar la tupla: agregarla sin probar el aislamiento
real es exactamente la falsa sensación de cobertura que este ratchet existe
para evitar.
"""

from __future__ import annotations

import os

from app.core.config import Settings
from app.main import crear_app

# Listas enumerables y explícitas (`design.md` D1 del change 02): nunca un
# patrón de nombre. Separadas porque representan dos motivos de exención
# distintos: sistema (sin negocio en absoluto) vs. autenticación (negocio de
# identidad, pero sin organización todavía en contexto -- tarea 12.1).
RUTAS_DE_SISTEMA = frozenset(
    {
        ("get", "/api/v1/salud"),
        ("get", "/api/v1/version"),
    }
)

RUTAS_DE_AUTENTICACION = frozenset(
    {
        ("post", "/api/v1/auth/login"),
        ("post", "/api/v1/auth/refresh"),
        ("post", "/api/v1/auth/logout"),
    }
)

# Ver "CÓMO DECLARAR UNA RUTA NUEVA" arriba. Las siete rutas de negocio del
# grupo 10.7, cada una con su prueba de aislamiento real (login real, dos
# organizaciones, "no encontrado" sobre el recurso ajeno):
# - `test_identidad_api_usuarios.py`: composición de rol, rotación de PIN,
#   desbloqueo manual.
# - `test_inv21_aislamiento_endpoints_identidad.py`: listado y revocación de
#   dispositivos, listado y alta de usuarios (incluida el alta con un
#   `rol_id` de otra organización).
COBERTURA_DE_AISLAMIENTO: frozenset[tuple[str, str]] = frozenset(
    {
        ("get", "/api/v1/identidad/dispositivos"),
        ("delete", "/api/v1/identidad/dispositivos/{dispositivo_id}"),
        ("get", "/api/v1/identidad/usuarios"),
        ("post", "/api/v1/identidad/usuarios"),
        ("put", "/api/v1/identidad/roles/{rol_id}/permisos"),
        ("post", "/api/v1/identidad/usuarios/{usuario_id}/pin"),
        ("post", "/api/v1/identidad/usuarios/{usuario_id}/desbloqueo"),
        # Change 04, grupo 8 (`sync/api.py`, tarea 8.6): a diferencia de las
        # rutas de arriba, `POST /sync/comandos` no tiene un "recurso ajeno"
        # por id -- `organizacion_id`/`usuario_id`/`dispositivo_id` salen
        # siempre del token (nunca del cuerpo, `sobre.py`), así que no hay
        # forma de pedir la cola de otra organización con esta ruta: el
        # aislamiento es estructural, no una verificación en tiempo de
        # ejecución sobre un id ajeno. Su prueba real de aislamiento no
        # sigue el patrón de "recurso de otra organización -> 404" de las
        # rutas de arriba, sino el de "cola ajena -> rechazada" (mismo
        # principio, SEG-02/SEG-07): `test_bus_lote_sincronizacion.py::
        # TestPropiedadDeLaCola` (otro usuario, otro dispositivo, sin
        # sesión) y `test_cuarentena_comandos.py::
        # test_la_cuarentena_de_otra_organizacion_no_es_alcanzable`
        # (tarea 8.9, aislamiento de `comando_cuarentena` entre
        # organizaciones).
        ("post", "/api/v1/sync/comandos"),
        # Change 05, grupo 9 (`catalogo/api.py`, tarea 9.1/9.2), cobertura
        # de tarea 11.1: las trece rutas nuevas, cada una con su prueba de
        # aislamiento real -- incluida la referencia ajena EN EL CONTENIDO
        # (categoría/marca/alícuota de otra organización), no solo el id
        # de la ruta -- en `test_inv21_aislamiento_endpoints_catalogo.py`.
        ("post", "/api/v1/catalogo/categorias"),
        ("get", "/api/v1/catalogo/categorias"),
        ("put", "/api/v1/catalogo/categorias/{categoria_id}"),
        ("post", "/api/v1/catalogo/marcas"),
        ("get", "/api/v1/catalogo/marcas"),
        ("put", "/api/v1/catalogo/marcas/{marca_id}"),
        ("post", "/api/v1/catalogo/productos"),
        ("get", "/api/v1/catalogo/productos"),
        ("put", "/api/v1/catalogo/productos/{producto_id}"),
        ("get", "/api/v1/catalogo/productos/{producto_id}"),
        ("post", "/api/v1/catalogo/productos/{producto_id}/presentaciones"),
        ("put", "/api/v1/catalogo/presentaciones/{presentacion_id}"),
        ("put", "/api/v1/catalogo/productos/{producto_id}/referencia"),
        # Change 05, grupo 9/11 (tarea 9.6/11.5, D12): la ruta de solo
        # lectura de `configuracion/api.py` -- cada organización lista solo
        # sus propias alícuotas, `test_configuracion_api.py::
        # TestAislamientoInv21`.
        ("get", "/api/v1/configuracion/alicuotas"),
        # Change 06, grupo 10/12 (`proveedores/api.py`, tarea 10.2),
        # cobertura de tarea 12.1: las ocho rutas nuevas, cada una con su
        # prueba de aislamiento real -- incluida la referencia ajena EN EL
        # CONTENIDO de `COSTO_INFORMAR` (`proveedor_id`, `producto_id`,
        # `presentacion_id` de otra organización) -- en
        # `test_inv21_aislamiento_endpoints_proveedores.py`. La misma
        # prueba cubre además `proveedor_id` ajeno en `PRODUCTO_CREAR`/
        # `PRODUCTO_MODIFICAR` v2 (`catalogo/api.py`, ya cubiertas arriba,
        # caso que las pruebas de la tarea 11.1 del change 05 no llegaban a
        # ejercitar porque `proveedor_id` no existía en el contrato).
        ("post", "/api/v1/proveedores"),
        ("get", "/api/v1/proveedores"),
        ("get", "/api/v1/proveedores/opciones"),
        ("get", "/api/v1/proveedores/{proveedor_id}"),
        ("put", "/api/v1/proveedores/{proveedor_id}"),
        ("post", "/api/v1/costos"),
        ("get", "/api/v1/costos/productos/{producto_id}/vigente"),
        ("get", "/api/v1/costos/productos/{producto_id}/historial"),
        # Change 06b, grupo 9, tarea 9.1 (`identidad/api.py::router_yo`,
        # ADR-027), con la prueba real en
        # `test_inv21_aislamiento_endpoints_identidad.py::TestAislamientoDeLaSesion`.
        # La 4.6 dejó esta ruta sin cobertura A PROPÓSITO (mismo precedente
        # que la 12.1 del change 02): el ratchet quedó en rojo nombrando
        # `[('get', '/api/v1/yo')]` desde que la ruta se registró hasta que
        # sus dos pruebas de aislamiento existen. Como `/yo` no recibe ningún
        # identificador (todo sale del token, D1-A), su aislamiento no sigue
        # el patrón "recurso de otra organización -> 404" de las rutas de
        # arriba, sino el inverso: dos organizaciones con login real, y el
        # usuario de B obtiene solo su usuario, su organización y su rol
        # (ningún id, nombre ni permiso de A), tanto si informa los
        # identificadores de A en la consulta y en encabezados como si no.
        ("get", "/api/v1/yo"),
        # Change 07, grupo 4 (`clientes/api.py`, tareas 4.2 y 4.3/4.4,
        # `design.md` D9 enmienda 2026-09-29): las tres rutas de lectura y
        # las cuatro rutas de escritura DEDICADAS (una por comando `ONLINE`,
        # mismo patrón que `proveedores/api.py`, en vez del despacho
        # genérico de `POST /sync/comandos`, ya cubierta arriba) -- con su
        # prueba real de aislamiento en
        # `test_inv21_aislamiento_endpoints_clientes.py::
        # TestAislamientoDeLasRutasDeClientes` (login real de dos
        # organizaciones, recurso ajeno -> 404, la referencia ajena EN EL
        # CONTENIDO de `CLIENTE_CREDITO_MODIFICAR`, y el caso propio de
        # `/consumidor-final`: el identificador ajeno sale de la
        # configuración de la otra organización, nunca de la petición).
        ("get", "/api/v1/clientes"),
        ("post", "/api/v1/clientes"),
        ("get", "/api/v1/clientes/consumidor-final"),
        ("post", "/api/v1/clientes/consumidor-final"),
        ("get", "/api/v1/clientes/{cliente_id}"),
        ("put", "/api/v1/clientes/{cliente_id}"),
        ("put", "/api/v1/clientes/{cliente_id}/credito"),
        # Change 08, grupo 6 (`cuentas_corrientes/api.py`, `clientes/api.py`,
        # `proveedores/api.py`, tareas 6.1 y 6.2): la ruta de escritura dedicada de
        # `SALDO_INICIAL_REGISTRAR` y las dos lecturas del estado de cuenta, cada
        # una con su prueba real de aislamiento (login real de dos organizaciones,
        # entidad ajena o inexistente -> 404 sin revelar saldo ni movimientos) en
        # `test_cuentas_corrientes_api.py::TestSaldoInicialRegistrar::
        # test_una_entidad_de_otra_organizacion_o_inexistente_responde_404`,
        # `TestEstadoDeCuentaDeUnCliente::
        # test_un_cliente_de_otra_organizacion_o_inexistente_responde_404_sin_datos`
        # y `TestEstadoDeCuentaDeUnProveedor::
        # test_un_proveedor_de_otra_organizacion_responde_404`. La tarea 8.4
        # agrega el archivo dedicado `test_inv21_aislamiento_endpoints_cuentas_
        # corrientes.py` con los mismos casos por ruta.
        ("post", "/api/v1/cuentas-corrientes/saldos-iniciales"),
        ("get", "/api/v1/clientes/{cliente_id}/cuenta-corriente"),
        ("get", "/api/v1/proveedores/{proveedor_id}/cuenta-corriente"),
        # Change 09, grupo 7 (`stock/api.py`, `catalogo/api.py`, tareas 7.1 a 7.3):
        # las tres escrituras dedicadas y las cuatro lecturas (ubicaciones, saldos,
        # kardex y costo promedio), cada una con su prueba real de aislamiento (login
        # real de dos organizaciones, recurso ajeno o inexistente -> 404 sin datos) en
        # `test_stock_api.py` (clases TestUbicacionModificar, TestStockInicialRegistrar,
        # TestSaldosDeUbicacion, TestKardex y TestCostoPromedioDeProducto; el alta y el
        # listado de ubicaciones solo filtran por la organizacion del token). La tarea
        # 9.5 agrega el archivo dedicado `test_inv21_aislamiento_endpoints_stock.py`.
        ("post", "/api/v1/stock/ubicaciones"),
        ("get", "/api/v1/stock/ubicaciones"),
        ("put", "/api/v1/stock/ubicaciones/{ubicacion_id}"),
        ("get", "/api/v1/stock/ubicaciones/{ubicacion_id}/saldos"),
        ("post", "/api/v1/stock/iniciales"),
        ("get", "/api/v1/stock/kardex"),
        ("get", "/api/v1/catalogo/productos/{producto_id}/costo"),
        # Change 10, grupo 4 (`importacion/api.py`, tarea 4.3): la escritura dedicada de
        # `IMPORTACION_REGISTRAR` (multipart), el historial y la plantilla, cada una con
        # su prueba real de aislamiento (login real de dos organizaciones; la
        # organizacion sale solo del token, una columna `organizacion_id` en el archivo
        # se rechaza, un nombre de otra organizacion no cuenta como duplicado y el
        # historial no muestra nada ajeno) en
        # `test_inv21_aislamiento_endpoints_importacion.py`. Ninguna toma un
        # identificador de recurso en la ruta: el aislamiento es estructural.
        ("post", "/api/v1/importaciones/{tipo}"),
        ("get", "/api/v1/importaciones"),
        ("get", "/api/v1/importaciones/plantillas/{tipo}"),
        # Change 11, grupo 5 (`proveedores/api.py`, tarea 5.3): la escritura dedicada de
        # `COMPRA_CONFIRMAR`, con su prueba real de aislamiento (login real de dos
        # organizaciones; el proveedor, la ubicacion y el producto de otra organizacion
        # responden 404 sin efectos, la presentacion ajena se informa como
        # `PRESENTACION_INVALIDA` y un `organizacion_id` en el cuerpo no se usa) en
        # `test_compras_api.py` (`test_inv21_*` y `test_el_cuerpo_no_acepta_organizacion_id`).
        ("post", "/api/v1/compras"),
        # Change 11, grupo 9 (`proveedores/api.py`, tarea 9.3): la anulacion dedicada de
        # `COMPRA_ANULAR`, con su prueba real de aislamiento (login real de dos
        # organizaciones: anular la compra de otra organizacion responde 404 y la deja
        # `CONFIRMADA`; un motivo ajeno responde 404; `organizacion_id` en el cuerpo se
        # rechaza) en `test_compras_api.py`
        # (`test_inv21_anular_la_compra_de_otra_organizacion_responde_404` y
        # `test_la_anulacion_no_acepta_campos_ajenos`) y `test_compras_anular.py`.
        ("post", "/api/v1/compras/{compra_id}/anulacion"),
        # Change 11, grupo 10 (tarea 10.1, 10.2 y 10.3): las dos lecturas de compras, el
        # filtro `proveedor_id` del listado de productos y las dos lecturas de
        # configuracion, cada una con su prueba real de aislamiento en `test_compras_api.py`
        # (`test_inv21_el_listado_no_devuelve_compras_de_otra_organizacion`,
        # `test_inv21_el_detalle_de_una_compra_de_otra_organizacion_responde_404`,
        # `test_inv21_filtrar_por_el_proveedor_de_otra_organizacion_devuelve_lista_vacia`,
        # `test_medios_de_pago_devuelve_solo_los_activos_de_la_organizacion` y
        # `test_motivos_devuelve_solo_los_activos_del_ambito_pedido_de_la_organizacion`).
        ("get", "/api/v1/compras"),
        ("get", "/api/v1/compras/{compra_id}"),
        # Change 11b, grupo 5 (tareas 5.1 y 5.2): la escritura dedicada del cambio de
        # condición frente al IVA y las dos lecturas nuevas, cada una con su prueba real de
        # aislamiento (login real de dos organizaciones; la organización sale siempre del
        # token y se ignora la que venga en la petición) en `test_condicion_iva_api.py`
        # (`test_inv21_cada_organizacion_lee_solo_su_propia_configuracion_fiscal`,
        # `test_inv21_el_cambio_afecta_solo_a_la_organizacion_del_token` y
        # `test_inv21_el_resumen_cuenta_solo_los_costos_de_la_organizacion_del_token`).
        ("get", "/api/v1/configuracion/fiscal"),
        ("post", "/api/v1/configuracion/fiscal/condicion-iva"),
        ("get", "/api/v1/costos/resumen-regla-iva"),
        ("get", "/api/v1/configuracion/medios-pago"),
        ("get", "/api/v1/configuracion/motivos"),
        # Change 12, grupo 4 (`proveedores/api.py`, tarea 4.3): la escritura dedicada de
        # `PAGO_PROVEEDOR_REGISTRAR`, con su prueba real de aislamiento (login real de dos
        # organizaciones en ambos sentidos: el proveedor y el medio de la otra
        # organizacion responden 404 sin efectos --con el indice del medio en el Problem
        # Details-- y un `organizacion_id` en el cuerpo se ignora, nunca llega al comando)
        # en `test_pagos_proveedor_api.py` (`test_un_proveedor_ajeno_responde_404`,
        # `test_un_medio_ajeno_responde_404_con_el_medio` y
        # `test_el_cuerpo_no_acepta_organizacion_id`).
        ("post", "/api/v1/pagos-proveedores"),
        # Change 12, grupo 7 (tarea 7.1): las cuatro rutas nuevas -- la anulacion dedicada
        # de `PAGO_PROVEEDOR_ANULAR` y las tres lecturas (saldo del proveedor, listado y
        # detalle de pagos) -- con su prueba real de aislamiento en
        # `test_inv21_aislamiento_endpoints_proveedores.py::
        # TestAislamientoDePagosAProveedores`: login real de dos organizaciones y, en cada
        # prueba, los dos sentidos (la propia lee/anula lo suyo con 200, y la misma llamada
        # sobre un recurso de la otra responde 404 sin datos ni efectos). Ademas las tres
        # lecturas y la anulacion se exerten con un `organizacion_id` ajeno en la consulta o
        # en el cuerpo para confirmar que la organizacion sale siempre del token (INV-21,
        # TR-08). Este ratchet quedo en rojo nombrando las cuatro rutas desde que el grupo 6
        # las registro hasta que sus pruebas de aislamiento existen (mismo precedente que la
        # tarea 12.1 del change 02).
        ("post", "/api/v1/pagos-proveedores/{pago_id}/anulacion"),
        ("get", "/api/v1/pagos-proveedores"),
        ("get", "/api/v1/pagos-proveedores/{pago_id}"),
        ("get", "/api/v1/proveedores/{proveedor_id}/saldo"),
        # Change 13, grupo 5 (`precios/api.py`, tarea 5.4): las nueve rutas de listas, reglas
        # de margen y redondeos por categoria -- cinco escrituras dedicadas y cuatro lecturas
        # (listado, opciones, detalle y reglas) -- con su prueba real de aislamiento en
        # `test_precios_api.py::test_inv21_cada_organizacion_ve_solo_sus_listas_y_las_ajenas_
        # responden_404` (login real de dos organizaciones: la lista de otra organizacion
        # responde 404 en el detalle, las reglas, la modificacion, el alta de regla y el
        # redondeo, y el listado y las opciones solo traen las propias) y `test_inv21_una_
        # regla_con_una_entidad_de_otra_organizacion_responde_404` (la referencia ajena EN EL
        # CONTENIDO, para los cuatro alcances). El cuerpo no acepta `organizacion_id`
        # (`test_el_cuerpo_no_acepta_la_organizacion`). El grupo 11 agrega las rutas de los
        # lotes siguientes y el archivo dedicado `test_inv21_aislamiento_endpoints_precios.py`.
        ("post", "/api/v1/precios/listas"),
        ("get", "/api/v1/precios/listas"),
        ("get", "/api/v1/precios/listas/opciones"),
        ("get", "/api/v1/precios/listas/{lista_id}"),
        ("put", "/api/v1/precios/listas/{lista_id}"),
        ("get", "/api/v1/precios/listas/{lista_id}/reglas"),
        ("post", "/api/v1/precios/listas/{lista_id}/reglas"),
        ("put", "/api/v1/precios/listas/{lista_id}/reglas/{regla_id}"),
        ("put", "/api/v1/precios/listas/{lista_id}/redondeos-categoria/{categoria_id}"),
        # Change 13, grupo 7 (tarea 7.6): generar el borrador, fijar un precio manual y
        # consultar el borrador. Prueba real de aislamiento en `test_precios_api.py`:
        # `test_generar_sobre_una_lista_inactiva_responde_409_y_sobre_una_ajena_404`,
        # `test_inv21_fijar_sobre_la_lista_o_la_version_de_otra_organizacion_responde_404` y
        # `test_consultar_el_borrador_exige_gestionar_o_publicar_y_no_cruza_organizaciones`.
        ("post", "/api/v1/precios/listas/{lista_id}/borrador"),
        ("get", "/api/v1/precios/listas/{lista_id}/borrador"),
        ("put", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/precios/{producto_id}"),
        # Change 13, grupo 8 (tarea 8.6): publicar, anular y consultar versiones y sus precios.
        # Prueba real de aislamiento en `test_precios_api.py`: `test_publicar_exige_operation_id_
        # publicar_listas_y_no_cruza_organizaciones`, `test_inv21_anular_la_version_de_otra_
        # organizacion_responde_404` y `test_las_lecturas_de_versiones_exigen_un_permiso_de_
        # listas_y_no_cruzan_organizaciones`.
        ("post", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/publicar"),
        ("post", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/anular"),
        ("get", "/api/v1/precios/listas/{lista_id}/versiones"),
        ("get", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/precios"),
        # Change 13, grupo 9 (tarea 9.2): la versión vigente de una lista a un momento (PRC-20).
        # Prueba real de aislamiento en `test_precios_api.py::test_inv21_la_version_vigente_de_
        # una_lista_de_otra_organizacion_responde_404`.
        ("get", "/api/v1/precios/listas/{lista_id}/vigente"),
        # Change 13, grupo 10 (tarea 10.3): definir y leer la lista predeterminada de la
        # organizacion (`LISTA_PRECIO_PREDETERMINADA_DEFINIR`, PRC-20). Grupo 11 (tarea 11.1):
        # las diecinueve rutas de `precios` tienen su prueba dedicada de aislamiento en
        # `test_inv21_aislamiento_endpoints_precios.py` (login real de dos organizaciones; el
        # recurso de otra organizacion responde 404 sin efectos).
        ("put", "/api/v1/precios/lista-predeterminada"),
        ("get", "/api/v1/precios/lista-predeterminada"),
    }
)


def rutas_de_negocio_sin_cobertura(
    rutas_del_esquema: dict[str, dict[str, object]],
    *,
    rutas_exentas: frozenset[tuple[str, str]],
    cobertura: frozenset[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Devuelve las rutas `(metodo, path)` que son de negocio (no están en
    `rutas_exentas`) y no están cubiertas por `cobertura`."""
    todas = [(metodo, path) for path, metodos in rutas_del_esquema.items() for metodo in metodos]
    de_negocio = [ruta for ruta in todas if ruta not in rutas_exentas]
    return [ruta for ruta in de_negocio if ruta not in cobertura]


def _rutas_reales_del_esquema() -> dict[str, dict[str, object]]:
    app = crear_app(Settings())  # type: ignore[call-arg]
    schema = app.openapi()
    paths: dict[str, dict[str, object]] = schema["paths"]
    return paths


def test_inv21_toda_ruta_de_negocio_esta_cubierta_por_el_aislamiento(
    database_url: str,
) -> None:
    """Escenario 'Una ruta de negocio sin cobertura de aislamiento hace
    fallar la verificación'."""
    os.environ.setdefault("DATABASE_URL", database_url)
    rutas = _rutas_reales_del_esquema()
    rutas_exentas = RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        rutas, rutas_exentas=rutas_exentas, cobertura=COBERTURA_DE_AISLAMIENTO
    )

    total_de_negocio = len(
        [
            (metodo, path)
            for path, metodos in rutas.items()
            for metodo in metodos
            if (metodo, path) not in rutas_exentas
        ]
    )
    mensaje = (
        f"INV-21: {len(sin_cobertura)} ruta(s) de negocio sin cobertura de "
        f"aislamiento: {sin_cobertura}. Rutas de negocio cubiertas hoy: "
        f"{total_de_negocio - len(sin_cobertura)} de {total_de_negocio}."
    )
    assert sin_cobertura == [], mensaje


def test_inv21_las_rutas_de_sistema_no_requieren_organizacion(database_url: str) -> None:
    """Escenario 'Las rutas de sistema no requieren organización': las
    rutas de sistema están explícitamente exentas, no por patrón de nombre."""
    os.environ.setdefault("DATABASE_URL", database_url)
    rutas = _rutas_reales_del_esquema()

    rutas_presentes = {(metodo, path) for path, metodos in rutas.items() for metodo in metodos}
    for ruta_sistema in RUTAS_DE_SISTEMA:
        assert ruta_sistema in rutas_presentes, (
            f"Ruta de sistema {ruta_sistema} esperada pero no está registrada."
        )


def test_inv21_las_rutas_de_autenticacion_quedan_exentas_por_operar_sin_organizacion(
    database_url: str,
) -> None:
    """Escenario 'Las rutas de autenticación quedan exentas por operar sin
    organización en contexto' (tarea 12.1, spec `aislamiento-multiorganizacion`):
    `/auth/login`, `/auth/refresh` y `/auth/logout` están registradas, y
    quedan fuera de la exigencia de `COBERTURA_DE_AISLAMIENTO` por estar
    declaradas explícitamente en `RUTAS_DE_AUTENTICACION` -- una lista
    separada de `RUTAS_DE_SISTEMA`, porque el motivo de la exención es
    distinto (sin organización en contexto todavía, no "sin negocio")."""
    os.environ.setdefault("DATABASE_URL", database_url)
    rutas = _rutas_reales_del_esquema()

    rutas_presentes = {(metodo, path) for path, metodos in rutas.items() for metodo in metodos}
    for ruta_auth in RUTAS_DE_AUTENTICACION:
        assert ruta_auth in rutas_presentes, (
            f"Ruta de autenticación {ruta_auth} esperada pero no está registrada."
        )

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        rutas,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
        cobertura=COBERTURA_DE_AISLAMIENTO,
    )
    for ruta_auth in RUTAS_DE_AUTENTICACION:
        assert ruta_auth not in sin_cobertura, (
            f"{ruta_auth} no debería exigir cobertura de aislamiento: opera "
            "sin organización en contexto (tarea 12.1)."
        )


def test_inv21_una_ruta_de_autenticacion_no_declarada_no_queda_exenta_por_prefijo(
    database_url: str,
) -> None:
    """Verificación en negativo (tarea 12.1, mismo criterio que la de
    sistema/tarea 9.3): la exención de `/auth` es una lista enumerable, no
    un patrón de prefijo -- una ruta de negocio nueva bajo `/auth` que no
    esté declarada en `RUTAS_DE_AUTENTICACION` sigue exigiendo cobertura."""
    esquema_con_ruta_ficticia = {
        "/api/v1/salud": {"get": {}},
        "/api/v1/auth/login": {"post": {}},
        "/api/v1/auth/impersonar": {"post": {}},  # ruta de negocio ficticia bajo /auth
    }

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        esquema_con_ruta_ficticia,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
        cobertura=COBERTURA_DE_AISLAMIENTO,
    )

    assert sin_cobertura == [("post", "/api/v1/auth/impersonar")]


def test_inv21_detecta_una_ruta_de_negocio_ficticia_sin_cobertura() -> None:
    """Verificación en negativo (tarea 9.3, extendida en 12.6): una ruta de
    negocio no registrada en `COBERTURA_DE_AISLAMIENTO` debe ser detectada y
    nombrada -- el ratchet falla si se agrega a propósito una ruta de
    negocio sin declarar su cobertura de aislamiento."""
    esquema_con_ruta_ficticia = {
        "/api/v1/salud": {"get": {}},
        "/api/v1/version": {"get": {}},
        "/api/v1/venta": {"post": {}},  # ruta de negocio ficticia, sin cobertura
    }

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        esquema_con_ruta_ficticia,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
        cobertura=COBERTURA_DE_AISLAMIENTO,
    )

    assert sin_cobertura == [("post", "/api/v1/venta")]


def test_inv21_no_marca_una_ruta_de_negocio_que_si_tiene_cobertura_declarada() -> None:
    """Verificación complementaria: si una ruta de negocio SÍ está en
    `cobertura`, no se marca como infractora."""
    esquema = {
        "/api/v1/salud": {"get": {}},
        "/api/v1/venta": {"post": {}},
    }
    cobertura_de_prueba = frozenset({("post", "/api/v1/venta")})

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        esquema,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
        cobertura=cobertura_de_prueba,
    )

    assert sin_cobertura == []
