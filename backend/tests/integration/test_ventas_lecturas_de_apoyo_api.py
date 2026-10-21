"""Tarea 9.2 (change 18a, `design.md` D4, D6, D7, D19): lecturas de apoyo a la venta.

`GET /api/v1/ventas/precios` (`VENDER`), `GET /api/v1/ventas/numeracion` (`VENDER`) y
`GET /api/v1/ventas/versiones` (`USAR_LISTA_ANTERIOR`). Tabla de permisos y las tres precisiones
aprobadas por el usuario el 2026-10-20: los precios NUNCA llevan costos (ni con `VER_COSTOS`) y
una ubicación inactiva responde `UBICACION_INACTIVA` (409), una ajena 404.

Ajustes aprobados por el usuario el 2026-10-20 (D19, D6): sin `USAR_LISTA_ANTERIOR` los precios
solo se consultan en la versión vigente de la lista que la venta usaría por defecto (403
`PERMISO_REQUERIDO` si no); y `GET /ventas/precios` busca (`q`), pagina (`cursor`, `limite`) y
trae un producto (`producto_id`) en el servidor.

Reglas citadas: VTA-06, VTA-10, PRC-10, PRC-20, PRC-21, PRC-22, CAT-05, STK-01, INV-21, SEG-06,
REP-04.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_ubicacion_sql
from test_ventas_api import (  # noqa: F401
    URL_VENTAS,
    Sesion,
    _con_op,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import usuario_con

URL_PRECIOS = f"{URL_VENTAS}/precios"
URL_NUMERACION = f"{URL_VENTAS}/numeracion"
URL_VERSIONES = f"{URL_VENTAS}/versiones"
SOLO_ANTERIOR = frozenset({"USAR_LISTA_ANTERIOR"})
VENDE_Y_VE_COSTOS = frozenset({"VENDER", "VER_COSTOS", "USAR_LISTA_ANTERIOR"})
AYER = datetime(2026, 10, 19, tzinfo=UTC)
FUTURO = datetime(2099, 1, 1, tzinfo=UTC)


def _item(cuerpo: dict[str, Any], producto_id: Any) -> dict[str, Any]:
    (item,) = [i for i in cuerpo["items"] if i["producto_id"] == str(producto_id)]
    return item


def _claves(valor: Any) -> set[str]:
    """Todas las claves de un JSON, a cualquier profundidad."""
    if isinstance(valor, dict):
        return set(valor) | {c for v in valor.values() for c in _claves(v)}
    if isinstance(valor, list):
        return {c for v in valor for c in _claves(v)}
    return set()


# --- GET /ventas/precios (PRC-20, PRC-22, CAT-05, STK-01) -------------------------------------


def test_prc22_los_precios_para_vender_traen_precio_presentaciones_y_stock_sin_costos(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Precios para vender": Vino A a `12500.00`, unidades de referencia 6,
    presentaciones "Botella" y "Caja x6" y stock 48 en "Depósito central"."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.get(
        URL_PRECIOS,
        params={
            "cliente_id": str(s.entorno.cliente_id),
            "ubicacion_id": str(s.entorno.deposito_id),
        },
        headers=headers,
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["lista_id"] == str(s.entorno.lista_id)
    assert cuerpo["version_id"] == str(s.entorno.version_id)
    assert cuerpo["version_numero"] == 1
    assert cuerpo["ubicacion_id"] == str(s.entorno.deposito_id)
    vino = _item(cuerpo, s.entorno.vino_id)
    assert vino["nombre"] == "Vino A"
    assert vino["precio_referencia"] == "12500.00"
    assert vino["unidades_referencia"] == 6
    assert vino["sin_precio"] is False
    assert vino["stock_base"] == 48
    por_nombre = {p["nombre"]: p for p in vino["presentaciones"]}
    assert len(vino["presentaciones"]) == 2
    assert por_nombre["Botella"]["es_referencia"] is False
    assert por_nombre["Botella"]["presentacion_id"] == str(s.entorno.botella_id)
    assert por_nombre["Botella"]["unidades_base"] == 1
    assert [p["unidades_base"] for p in vino["presentaciones"]] == sorted(
        p["unidades_base"] for p in vino["presentaciones"]
    )


def test_los_precios_nunca_llevan_costos_ni_con_ver_costos(
    cliente_http: TestClient, sesion: Session
) -> None:
    """`01` §19, D19: NUNCA costos, aunque el usuario tenga `VER_COSTOS`."""
    s = Sesion(sesion)
    con_costos = usuario_con(cliente_http, sesion, s, VENDE_Y_VE_COSTOS)
    sin_costos = s.entrar(cliente_http)

    for headers in (con_costos, sin_costos):
        cuerpo = cliente_http.get(
            URL_PRECIOS, params={"ubicacion_id": str(s.entorno.deposito_id)}, headers=headers
        ).json()
        assert not {c for c in _claves(cuerpo) if "costo" in c or "margen" in c or "utilidad" in c}


def test_sin_ubicacion_el_stock_no_viaja_y_con_ubicacion_sin_saldo_es_cero(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Triangulación de STK-01: sin `ubicacion_id` el stock es nulo; con una ubicación donde el
    producto nunca tuvo movimientos, 0."""
    s = Sesion(sesion)
    vacia = crear_ubicacion_sql(sesion, s.entorno.org, nombre="Camioneta 1")
    sesion.commit()
    headers = s.entrar(cliente_http)

    sin = cliente_http.get(URL_PRECIOS, headers=headers).json()
    en_vacia = cliente_http.get(
        URL_PRECIOS, params={"ubicacion_id": str(vacia)}, headers=headers
    ).json()

    assert _item(sin, s.entorno.vino_id)["stock_base"] is None
    assert sin["ubicacion_id"] is None
    assert _item(en_vacia, s.entorno.vino_id)["stock_base"] == 0


def test_vta10_un_producto_sin_precio_en_la_version_se_marca_y_uno_inactivo_no_figura(
    cliente_http: TestClient, sesion: Session
) -> None:
    """VTA-10, PRC-10, CAT-05: el producto sin precio sale marcado; el inactivo no sale."""
    s = Sesion(sesion)
    sin_precio, _ = s.entorno.crear_producto("Aceite sin precio")
    inactivo, _ = s.entorno.crear_producto("Producto dado de baja")
    sesion.execute(
        text("UPDATE producto SET activo = false WHERE organizacion_id = :o AND id = :p"),
        {"o": s.entorno.org, "p": inactivo},
    )
    sesion.commit()
    headers = s.entrar(cliente_http)

    cuerpo = cliente_http.get(URL_PRECIOS, headers=headers).json()

    marcado = _item(cuerpo, sin_precio)
    assert marcado["sin_precio"] is True
    assert marcado["precio_referencia"] is None
    assert marcado["unidades_referencia"] is None
    assert _item(cuerpo, s.entorno.vino_id)["sin_precio"] is False
    assert str(inactivo) not in {i["producto_id"] for i in cuerpo["items"]}


def test_prc20_la_lista_asignada_al_cliente_manda_sobre_la_predeterminada(
    cliente_http: TestClient, sesion: Session
) -> None:
    """PRC-20: con `cliente_id` se usa la lista del cliente; sin él, la predeterminada."""
    s = Sesion(sesion)
    mayorista = s.entorno.crear_lista("Mayorista")
    v_mayorista = s.entorno.crear_version(mayorista, 1, AYER, precio_vino="11000.00")
    cliente = s.entorno.crear_cliente(nombre="Almacén Don Pepe")
    s.entorno.actualizar_cliente(cliente, lista_precio_id=mayorista)
    sesion.commit()
    headers = s.entrar(cliente_http)

    del_cliente = cliente_http.get(
        URL_PRECIOS, params={"cliente_id": str(cliente)}, headers=headers
    )
    sin_cliente = cliente_http.get(URL_PRECIOS, headers=headers)

    assert del_cliente.json()["lista_id"] == str(mayorista)
    assert del_cliente.json()["version_id"] == str(v_mayorista)
    assert _item(del_cliente.json(), s.entorno.vino_id)["precio_referencia"] == "11000.00"
    assert sin_cliente.json()["lista_id"] == str(s.entorno.lista_id)
    assert _item(sin_cliente.json(), s.entorno.vino_id)["precio_referencia"] == "12500.00"


def test_prc21_una_version_elegida_trae_sus_precios_y_una_programada_no_se_acepta(
    cliente_http: TestClient, sesion: Session
) -> None:
    """PRC-21: la versión histórica elegida da su precio; la vigente es la nueva; una versión
    programada o de otra lista es `VERSION_NO_PERMITIDA` (409)."""
    s = Sesion(sesion)
    nueva = s.entorno.crear_version(s.entorno.lista_id, 2, AYER, precio_vino="13000.00")
    programada = s.entorno.crear_version(s.entorno.lista_id, 3, FUTURO, precio_vino="14000.00")
    otra_lista = s.entorno.crear_lista("Otra")
    de_otra = s.entorno.crear_version(otra_lista, 1, AYER, precio_vino="9000.00")
    sesion.commit()
    headers = usuario_con(cliente_http, sesion, s, VENDE_Y_VE_COSTOS)

    vigente = cliente_http.get(URL_PRECIOS, headers=headers).json()
    historica = cliente_http.get(
        URL_PRECIOS, params={"version_id": str(s.entorno.version_id)}, headers=headers
    ).json()
    por_programada = cliente_http.get(
        URL_PRECIOS, params={"version_id": str(programada)}, headers=headers
    )
    por_ajena_a_la_lista = cliente_http.get(
        URL_PRECIOS,
        params={"lista_id": str(s.entorno.lista_id), "version_id": str(de_otra)},
        headers=headers,
    )

    assert vigente["version_id"] == str(nueva)
    assert _item(vigente, s.entorno.vino_id)["precio_referencia"] == "13000.00"
    assert historica["version_id"] == str(s.entorno.version_id)
    assert _item(historica, s.entorno.vino_id)["precio_referencia"] == "12500.00"
    assert por_programada.status_code == 409
    assert por_programada.json()["codigo"] == "VERSION_NO_PERMITIDA"
    assert por_ajena_a_la_lista.status_code == 409
    assert por_ajena_a_la_lista.json()["codigo"] == "VERSION_NO_PERMITIDA"


def test_una_ubicacion_inactiva_responde_ubicacion_inactiva_409(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Precisión 3 del 2026-10-20: se reutiliza el código de `stock` y el 409."""
    s = Sesion(sesion)
    cerrada = crear_ubicacion_sql(sesion, s.entorno.org, nombre="Depósito viejo", activo=False)
    sesion.commit()
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.get(
        URL_PRECIOS, params={"ubicacion_id": str(cerrada)}, headers=headers
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "UBICACION_INACTIVA"


def test_inv21_una_ubicacion_cliente_o_lista_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    """INV-21, SEG-07: ni confirma que existen (quien elige lista tiene `USAR_LISTA_ANTERIOR`;
    sin él una lista que no sea la suya es 403, D6)."""
    s = Sesion(sesion)
    ajena = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, VENDE_Y_VE_COSTOS)

    por_ubicacion = cliente_http.get(
        URL_PRECIOS, params={"ubicacion_id": str(ajena.entorno.deposito_id)}, headers=headers
    )
    por_cliente = cliente_http.get(
        URL_PRECIOS, params={"cliente_id": str(ajena.entorno.cliente_id)}, headers=headers
    )
    por_lista = cliente_http.get(
        URL_PRECIOS, params={"lista_id": str(ajena.entorno.lista_id)}, headers=headers
    )

    assert por_ubicacion.status_code == 404
    assert por_cliente.status_code == 404
    assert por_lista.status_code == 404


def test_seg06_los_precios_exigen_vender(cliente_http: TestClient, sesion: Session) -> None:
    s = Sesion(sesion)
    sin_vender = usuario_con(cliente_http, sesion, s, SOLO_ANTERIOR)

    assert cliente_http.get(URL_PRECIOS, headers=sin_vender).status_code == 403
    assert cliente_http.get(URL_PRECIOS).status_code == 401


# --- D6 (mínimo privilegio): sin USAR_LISTA_ANTERIOR solo la vigente de la lista aplicable -----


def _escenario_con_lista_aplicable(s: Sesion) -> dict[str, Any]:
    """Cliente con lista `Mayorista` (v1 histórica a 11000, v2 vigente a 11500) y otra lista
    `Otra` con una versión vigente: la aplicable del cliente es `Mayorista`."""
    mayorista = s.entorno.crear_lista("Mayorista")
    v1 = s.entorno.crear_version(
        mayorista, 1, datetime(2026, 9, 1, tzinfo=UTC), precio_vino="11000.00"
    )
    v2 = s.entorno.crear_version(mayorista, 2, AYER, precio_vino="11500.00")
    otra = s.entorno.crear_lista("Otra")
    v_otra = s.entorno.crear_version(otra, 1, AYER, precio_vino="9000.00")
    cliente = s.entorno.crear_cliente(nombre="Almacén Mayorista")
    s.entorno.actualizar_cliente(cliente, lista_precio_id=mayorista)
    s.sesion.commit()
    return {
        "mayorista": mayorista,
        "v1": v1,
        "v2": v2,
        "otra": otra,
        "v_otra": v_otra,
        "cliente": cliente,
    }


def test_d6_sin_usar_lista_anterior_los_parametros_por_defecto_traen_la_vigente_de_su_lista(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Escenario: "Precios sin permiso de lista anterior"
    """D6, PRC-20: el Vendedor consulta con el cliente solo (200) y también nombrando su propia
    lista aplicable y su versión vigente (200): es lo mismo que la venta usaría por defecto."""
    s = Sesion(sesion)
    e = _escenario_con_lista_aplicable(s)
    headers = s.entrar(cliente_http)

    por_defecto = cliente_http.get(
        URL_PRECIOS, params={"cliente_id": str(e["cliente"])}, headers=headers
    )
    explicita = cliente_http.get(
        URL_PRECIOS,
        params={
            "cliente_id": str(e["cliente"]),
            "lista_id": str(e["mayorista"]),
            "version_id": str(e["v2"]),
        },
        headers=headers,
    )

    assert por_defecto.status_code == 200
    assert por_defecto.json()["version_id"] == str(e["v2"])
    assert _item(por_defecto.json(), s.entorno.vino_id)["precio_referencia"] == "11500.00"
    assert explicita.status_code == 200
    assert explicita.json()["version_id"] == str(e["v2"])


def test_d6_sin_usar_lista_anterior_otra_lista_responde_403_permiso_requerido(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Escenario: "Precios sin permiso de lista anterior"
    """D6: otra lista, aunque exista y sea de la organización, es 403 `PERMISO_REQUERIDO`; con
    el cliente (lista aplicable distinta) o sin él (la predeterminada)."""
    s = Sesion(sesion)
    e = _escenario_con_lista_aplicable(s)
    headers = s.entrar(cliente_http)

    con_cliente = cliente_http.get(
        URL_PRECIOS,
        params={"cliente_id": str(e["cliente"]), "lista_id": str(e["otra"])},
        headers=headers,
    )
    sin_cliente = cliente_http.get(
        URL_PRECIOS, params={"lista_id": str(e["otra"])}, headers=headers
    )

    assert con_cliente.status_code == 403
    assert con_cliente.json()["codigo"] == "PERMISO_REQUERIDO"
    assert sin_cliente.status_code == 403
    assert sin_cliente.json()["codigo"] == "PERMISO_REQUERIDO"


def test_d6_sin_usar_lista_anterior_una_version_no_vigente_responde_403(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Escenario: "Precios sin permiso de lista anterior"
    """D6, PRC-21: la versión histórica de su propia lista es 403; la de otra lista también."""
    s = Sesion(sesion)
    e = _escenario_con_lista_aplicable(s)
    headers = s.entrar(cliente_http)

    historica = cliente_http.get(
        URL_PRECIOS,
        params={"cliente_id": str(e["cliente"]), "version_id": str(e["v1"])},
        headers=headers,
    )
    de_otra_lista = cliente_http.get(
        URL_PRECIOS,
        params={"cliente_id": str(e["cliente"]), "version_id": str(e["v_otra"])},
        headers=headers,
    )

    assert historica.status_code == 403
    assert historica.json()["codigo"] == "PERMISO_REQUERIDO"
    assert de_otra_lista.status_code == 403


def test_d6_con_usar_lista_anterior_cualquier_lista_y_version_elegible_responde_200(
    cliente_http: TestClient, sesion: Session
) -> None:
    """D6, PRC-21: con el permiso, otra lista y una versión histórica se consultan; una versión
    no elegible sigue siendo `VERSION_NO_PERMITIDA` (409)."""
    s = Sesion(sesion)
    e = _escenario_con_lista_aplicable(s)
    programada = s.entorno.crear_version(e["mayorista"], 3, FUTURO, precio_vino="12000.00")
    sesion.commit()
    headers = usuario_con(cliente_http, sesion, s, VENDE_Y_VE_COSTOS)

    otra_lista = cliente_http.get(
        URL_PRECIOS,
        params={"cliente_id": str(e["cliente"]), "lista_id": str(e["otra"])},
        headers=headers,
    )
    historica = cliente_http.get(
        URL_PRECIOS,
        params={"cliente_id": str(e["cliente"]), "version_id": str(e["v1"])},
        headers=headers,
    )
    no_elegible = cliente_http.get(
        URL_PRECIOS,
        params={"cliente_id": str(e["cliente"]), "version_id": str(programada)},
        headers=headers,
    )

    assert otra_lista.status_code == 200
    assert otra_lista.json()["lista_id"] == str(e["otra"])
    assert historica.status_code == 200
    assert _item(historica.json(), s.entorno.vino_id)["precio_referencia"] == "11000.00"
    assert no_elegible.status_code == 409
    assert no_elegible.json()["codigo"] == "VERSION_NO_PERMITIDA"


# --- búsqueda y paginación en el servidor (D19, ajuste del 2026-10-20) ------------------------


def _codigo_de(sesion: Session, producto_id: Any) -> str:
    return str(
        sesion.execute(
            text("SELECT codigo FROM producto WHERE id = :p"), {"p": producto_id}
        ).scalar_one()
    )


def _dar_de_baja(sesion: Session, s: Sesion, producto_id: Any) -> None:
    sesion.execute(
        text("UPDATE producto SET activo = false WHERE organizacion_id = :o AND id = :p"),
        {"o": s.entorno.org, "p": producto_id},
    )


def test_q_busca_por_nombre_sin_distinguir_mayusculas_y_por_codigo(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Escenario: "Búsqueda y páginas de precios"
    """CAT-05: `q` filtra en SQL por nombre o código, sin distinguir mayúsculas; sin
    coincidencias, página vacía sin cursor."""
    s = Sesion(sesion)
    aceite, _ = s.entorno.crear_producto("Aceite Girasol")
    sesion.commit()
    headers = s.entrar(cliente_http)

    por_nombre = cliente_http.get(URL_PRECIOS, params={"q": "gIRaSOL"}, headers=headers).json()
    por_codigo = cliente_http.get(
        URL_PRECIOS, params={"q": _codigo_de(sesion, aceite).lower()}, headers=headers
    ).json()
    sin_coincidencia = cliente_http.get(
        URL_PRECIOS, params={"q": "no-existe-xyz"}, headers=headers
    ).json()

    assert [i["producto_id"] for i in por_nombre["items"]] == [str(aceite)]
    assert [i["producto_id"] for i in por_codigo["items"]] == [str(aceite)]
    assert sin_coincidencia["items"] == []
    assert sin_coincidencia["cursor_siguiente"] is None


def test_q_trata_los_comodines_de_like_como_texto_literal(
    cliente_http: TestClient, sesion: Session
) -> None:
    """`%` y `_` en `q` no son comodines: no traen todo el catálogo."""
    s = Sesion(sesion)
    s.entorno.crear_producto("Oferta 50% off")
    s.entorno.crear_producto("Producto común")
    sesion.commit()
    headers = s.entrar(cliente_http)

    porcentaje = cliente_http.get(URL_PRECIOS, params={"q": "50%"}, headers=headers).json()
    guion = cliente_http.get(URL_PRECIOS, params={"q": "_"}, headers=headers).json()

    assert [i["nombre"] for i in porcentaje["items"]] == ["Oferta 50% off"]
    assert guion["items"] == []


def test_la_paginacion_recorre_todos_los_activos_por_codigo_sin_repetir(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Escenario: "Búsqueda y páginas de precios"
    """Cursor por código: páginas de 2 sobre 5 productos activos (el inactivo no figura); cada
    página trae su precio y su stock; la última no trae cursor."""
    s = Sesion(sesion)
    for n in range(4):
        s.entorno.crear_producto(f"Producto {n}")
    inactivo, _ = s.entorno.crear_producto("Dado de baja")
    _dar_de_baja(sesion, s, inactivo)
    sesion.commit()
    headers = s.entrar(cliente_http)
    esperados = [
        r[0]
        for r in sesion.execute(
            text(
                "SELECT id::text FROM producto WHERE organizacion_id = :o AND activo "
                "ORDER BY codigo"
            ),
            {"o": s.entorno.org},
        )
    ]

    vistos: list[str] = []
    cursor: str | None = None
    paginas = 0
    while True:
        params: dict[str, Any] = {"limite": 2, "ubicacion_id": str(s.entorno.deposito_id)}
        if cursor is not None:
            params["cursor"] = cursor
        pagina = cliente_http.get(URL_PRECIOS, params=params, headers=headers).json()
        assert len(pagina["items"]) <= 2
        vistos += [i["producto_id"] for i in pagina["items"]]
        for item in pagina["items"]:
            if item["producto_id"] == str(s.entorno.vino_id):
                assert item["precio_referencia"] == "12500.00"
                assert item["stock_base"] == 48
            else:
                assert item["stock_base"] == 0
        paginas += 1
        cursor = pagina["cursor_siguiente"]
        if cursor is None:
            break

    assert vistos == esperados
    assert len(esperados) == 5 and paginas == 3
    assert str(inactivo) not in vistos


def test_q_y_cursor_se_combinan_y_el_limite_se_valida(
    cliente_http: TestClient, sesion: Session
) -> None:
    """`q` con paginación (3 coincidencias en páginas de 2); `limite` fuera de 1..200 es 422 y
    un cursor ilegible, 422 `CURSOR_INVALIDO`."""
    s = Sesion(sesion)
    for n in range(3):
        s.entorno.crear_producto(f"Gaseosa {n}")
    s.entorno.crear_producto("Cerveza")
    sesion.commit()
    headers = s.entrar(cliente_http)

    primera = cliente_http.get(
        URL_PRECIOS, params={"q": "gaseosa", "limite": 2}, headers=headers
    ).json()
    segunda = cliente_http.get(
        URL_PRECIOS,
        params={"q": "gaseosa", "limite": 2, "cursor": primera["cursor_siguiente"]},
        headers=headers,
    ).json()
    ilegible = cliente_http.get(URL_PRECIOS, params={"cursor": "xx"}, headers=headers)

    assert [len(primera["items"]), len(segunda["items"])] == [2, 1]
    assert segunda["cursor_siguiente"] is None
    assert {i["nombre"] for i in primera["items"] + segunda["items"]} == {
        "Gaseosa 0",
        "Gaseosa 1",
        "Gaseosa 2",
    }
    assert cliente_http.get(URL_PRECIOS, params={"limite": 0}, headers=headers).status_code == 422
    assert cliente_http.get(URL_PRECIOS, params={"limite": 201}, headers=headers).status_code == 422
    assert ilegible.status_code == 422
    assert ilegible.json()["codigo"] == "CURSOR_INVALIDO"


def test_producto_id_trae_un_solo_producto_con_su_precio_y_stock(
    cliente_http: TestClient, sesion: Session
) -> None:
    """`producto_id`: solo ese producto; uno inactivo o de otra organización, página vacía."""
    s = Sesion(sesion)
    ajena = Sesion(sesion)
    otro, _ = s.entorno.crear_producto("Otro producto")
    inactivo, _ = s.entorno.crear_producto("Producto inactivo")
    _dar_de_baja(sesion, s, inactivo)
    sesion.commit()
    headers = s.entrar(cliente_http)

    vino = cliente_http.get(
        URL_PRECIOS,
        params={"producto_id": str(s.entorno.vino_id), "ubicacion_id": str(s.entorno.deposito_id)},
        headers=headers,
    ).json()
    sin_precio = cliente_http.get(
        URL_PRECIOS, params={"producto_id": str(otro)}, headers=headers
    ).json()
    de_baja = cliente_http.get(URL_PRECIOS, params={"producto_id": str(inactivo)}, headers=headers)
    de_otra_org = cliente_http.get(
        URL_PRECIOS, params={"producto_id": str(ajena.entorno.vino_id)}, headers=headers
    )

    assert [i["producto_id"] for i in vino["items"]] == [str(s.entorno.vino_id)]
    assert vino["items"][0]["precio_referencia"] == "12500.00"
    assert vino["items"][0]["stock_base"] == 48
    assert vino["cursor_siguiente"] is None
    assert [(i["producto_id"], i["sin_precio"]) for i in sin_precio["items"]] == [(str(otro), True)]
    assert de_baja.status_code == 200 and de_baja.json()["items"] == []
    assert de_otra_org.status_code == 200 and de_otra_org.json()["items"] == []


def test_una_pagina_vacia_igual_valida_la_ubicacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Con `q` sin coincidencias, `UBICACION_INACTIVA` (409) y el 404 de lo ajeno siguen
    respondiéndose: la validación no depende de que haya items."""
    s = Sesion(sesion)
    ajena = Sesion(sesion)
    cerrada = crear_ubicacion_sql(sesion, s.entorno.org, nombre="Depósito viejo", activo=False)
    sesion.commit()
    headers = s.entrar(cliente_http)

    inactiva = cliente_http.get(
        URL_PRECIOS, params={"q": "no-existe-xyz", "ubicacion_id": str(cerrada)}, headers=headers
    )
    ajena_ub = cliente_http.get(
        URL_PRECIOS,
        params={"q": "no-existe-xyz", "ubicacion_id": str(ajena.entorno.deposito_id)},
        headers=headers,
    )

    assert inactiva.status_code == 409
    assert inactiva.json()["codigo"] == "UBICACION_INACTIVA"
    assert ajena_ub.status_code == 404


# --- GET /ventas/numeracion (VTA-06, D4) ------------------------------------------------------


def test_vta06_la_numeracion_trae_el_prefijo_el_ultimo_correlativo_y_el_siguiente_numero(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Numeración del dispositivo": prefijo del dispositivo de la sesión; el último
    correlativo sube con cada venta (triangulación 0 -> 1)."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)

    inicial = cliente_http.get(URL_NUMERACION, headers=headers)
    vendida = cliente_http.post(URL_VENTAS, json=s.cuerpo(), headers=_con_op(headers))
    despues = cliente_http.get(URL_NUMERACION, headers=headers)

    assert inicial.status_code == 200
    assert inicial.json() == {
        "prefijo": s.prefijo,
        "ultimo_correlativo": 0,
        "siguiente_numero": f"{s.prefijo}-000001",
    }
    assert vendida.status_code == 201
    assert despues.json() == {
        "prefijo": s.prefijo,
        "ultimo_correlativo": 1,
        "siguiente_numero": f"{s.prefijo}-000002",
    }


def test_la_numeracion_es_la_del_dispositivo_de_la_sesion_y_exige_vender(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Otra sesión (otro dispositivo) ve su propio prefijo; sin `VENDER`, 403."""
    s = Sesion(sesion)
    primera = s.entrar(cliente_http)
    primer_prefijo = s.prefijo
    segunda = s.entrar(cliente_http)
    sin_vender = usuario_con(cliente_http, sesion, s, SOLO_ANTERIOR)

    uno = cliente_http.get(URL_NUMERACION, headers=primera).json()["prefijo"]
    dos = cliente_http.get(URL_NUMERACION, headers=segunda).json()["prefijo"]

    assert uno == primer_prefijo
    assert dos == s.prefijo and dos != uno
    assert cliente_http.get(URL_NUMERACION, headers=sin_vender).status_code == 403


# --- GET /ventas/versiones (PRC-21, D6) -------------------------------------------------------


def test_prc21_sin_usar_lista_anterior_las_versiones_responden_403(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Versiones sin permiso": el Vendedor recibe 403."""
    s = Sesion(sesion)
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.get(
        URL_VERSIONES, params={"lista_id": str(s.entorno.lista_id)}, headers=headers
    )

    assert respuesta.status_code == 403


def test_prc21_con_el_permiso_trae_solo_las_versiones_elegibles_de_la_mas_nueva_a_la_mas_vieja(
    cliente_http: TestClient, sesion: Session
) -> None:
    """D6: vigente e históricas; las programadas y las anuladas no figuran."""
    s = Sesion(sesion)
    nueva = s.entorno.crear_version(s.entorno.lista_id, 2, AYER, precio_vino="13000.00")
    s.entorno.crear_version(s.entorno.lista_id, 3, FUTURO, precio_vino="14000.00")
    s.entorno.crear_version(
        s.entorno.lista_id, 4, datetime(2026, 10, 19, 6, tzinfo=UTC), estado="ANULADA"
    )
    sesion.commit()
    headers = usuario_con(cliente_http, sesion, s, VENDE_Y_VE_COSTOS)

    respuesta = cliente_http.get(
        URL_VERSIONES, params={"lista_id": str(s.entorno.lista_id)}, headers=headers
    )

    assert respuesta.status_code == 200
    items = respuesta.json()["items"]
    assert [(i["version_id"], i["numero"], i["estado"]) for i in items] == [
        (str(nueva), 2, "VIGENTE"),
        (str(s.entorno.version_id), 1, "HISTORICA"),
    ]


def test_inv21_las_versiones_de_una_lista_ajena_responden_404_y_lista_id_es_obligatorio(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    ajena = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, SOLO_ANTERIOR)

    por_ajena = cliente_http.get(
        URL_VERSIONES, params={"lista_id": str(ajena.entorno.lista_id)}, headers=headers
    )
    inexistente = cliente_http.get(
        URL_VERSIONES, params={"lista_id": str(uuid4())}, headers=headers
    )
    sin_lista = cliente_http.get(URL_VERSIONES, headers=headers)

    assert por_ajena.status_code == 404
    assert inexistente.status_code == 404
    assert sin_lista.status_code == 422


def test_inv21_los_precios_de_una_version_de_otra_organizacion_responden_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Versión ajena": se piden los precios de una versión de otra organización, sola
    o junto con la lista propia; responde como inexistente (404) y no como `VERSION_NO_PERMITIDA`
    (que es lo de una versión propia de otra lista)."""
    s = Sesion(sesion)
    ajena = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, VENDE_Y_VE_COSTOS)

    por_version = cliente_http.get(
        URL_PRECIOS, params={"version_id": str(ajena.entorno.version_id)}, headers=headers
    )
    con_lista_propia = cliente_http.get(
        URL_PRECIOS,
        params={"lista_id": str(s.entorno.lista_id), "version_id": str(ajena.entorno.version_id)},
        headers=headers,
    )
    con_lista_ajena = cliente_http.get(
        URL_PRECIOS,
        params={
            "lista_id": str(ajena.entorno.lista_id),
            "version_id": str(ajena.entorno.version_id),
        },
        headers=headers,
    )

    assert por_version.status_code == 404
    assert con_lista_propia.status_code == 404
    assert con_lista_ajena.status_code == 404
