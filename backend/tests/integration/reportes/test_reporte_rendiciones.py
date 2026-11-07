"""Tareas 4.1 y 4.2 (change 26, spec `reportes/rendicion-por-vendedor`; `design.md` D7):
`GET /api/v1/reportes/rendiciones` (las jornadas abiertas en el período con su dinero y sus
diferencias, y los totales por vendedor) y `GET /api/v1/reportes/rendiciones/{jornada_id}` (el
resumen de RUT-07 de una jornada por `stock/service.py`).

PostgreSQL real y login real. Todo se siembra por SQL. Cada fila de la lista se compara con el
resumen de esa jornada (`stock.service.obtener_resumen_de_jornada`): la lista suma en SQL y el
detalle usa `stock`, así que esa prueba evita dos implementaciones distintas de RUT-07.

Reglas citadas: RUT-07, RUT-09, INV-03, INV-21, `01` §19, TR-04.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from reportes_utiles import (
    ABRIR_REPORTES,
    LineaContada,
    LineaDePrueba,
    Vendedor,
    anular_venta,
    crear_vendedor,
    dia,
    fijar_reloj,
    sembrar_cobranza,
    sembrar_jornada,
    sembrar_rendicion,
    sembrar_venta,
)
from sqlalchemy.orm import Session
from stock_utiles import crear_presentacion_referencia_sql, crear_producto_sql
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import usuario_con

from app.modules.cobranzas import service as _cobranzas  # noqa: F401  (registra su lector)
from app.modules.stock import service as stock_service
from app.modules.ventas import service as _ventas  # noqa: F401  (registra su lector)

URL = "/api/v1/reportes/rendiciones"
NOVIEMBRE = {"desde": "2026-11-01", "hasta": "2026-11-30"}
CON_COSTOS = frozenset({"VER_REPORTES", "VER_COSTOS"})


def _pedir(cliente_http: TestClient, headers: dict[str, str], **filtros: str) -> dict[str, Any]:
    respuesta = cliente_http.get(URL, params=filtros, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def _lector(cliente_http: TestClient, sesion: Session, s: Sesion) -> dict[str, str]:
    return usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)


def _lector_con_costos(cliente_http: TestClient, sesion: Session, s: Sesion) -> dict[str, str]:
    return usuario_con(cliente_http, sesion, s, CON_COSTOS)


def _por_jornada(cuerpo: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {fila["jornada_id"]: fila for fila in cuerpo["jornadas"]["filas"]}


class Rendida:
    """La jornada rendida del spec: Juan, tres ventas (una anulada en la misma jornada),
    cobranzas en efectivo y transferencia, y un conteo con un faltante de 2 y un sobrante de 1."""

    def __init__(
        self, sesion: Session, s: Sesion, *, nombre: str = "Juan", ubicacion: str | None = None
    ) -> None:
        self.sesion, self.s = sesion, s
        self.vendedor: Vendedor = crear_vendedor(sesion, s, nombre)
        self.jornada_id = sembrar_jornada(
            sesion, s, vendedor=self.vendedor, estado="CERRADA", ubicacion=ubicacion
        )
        self.producto_extra = crear_producto_sql(sesion, s.entorno.org, nombre="Agua 500")
        self.vender("1000.00", 10)
        self.vender("2000.00", 11)
        anulada = self.vender("500.00", 12)
        anular_venta(
            sesion,
            s,
            anulada,
            anulada_en=dia(11, 3, 13),
            jornada_id=self.jornada_id,
        )
        e = s.entorno
        sembrar_cobranza(
            sesion,
            s,
            self.jornada_id,
            [(e.efectivo_id, "300.00"), (e.transferencia_id, "200.00")],
            cuando=dia(11, 3, 14),
            vendedor=self.vendedor,
        )
        sembrar_cobranza(
            sesion,
            s,
            self.jornada_id,
            [(e.efectivo_id, "100.00")],
            cuando=dia(11, 3, 15),
            vendedor=self.vendedor,
        )
        self.corte = sembrar_rendicion(
            sesion,
            s,
            self.jornada_id,
            vendedor=self.vendedor,
            lineas=[
                LineaContada(e.vino_id, esperada=10, contada=8),
                LineaContada(self.producto_extra, esperada=5, contada=6),
            ],
        )

    def vender(self, neto: str, hora: int, **cambios: Any) -> UUID:
        venta = sembrar_venta(
            self.sesion,
            self.s,
            vendedor_id=self.vendedor.usuario_id,
            occurred_at=dia(11, 3, hora),
            lineas=[LineaDePrueba(neto=neto)],
            modo_confirmacion="OFFLINE",
            jornada_id=self.jornada_id,
            **cambios,
        )
        return venta.venta_id


def _coincide_con_el_resumen(fila: dict[str, Any], resumen: Any, *, con_costos: bool) -> None:
    """Cada cifra de la fila es igual a la del resumen de esa jornada (RUT-07)."""

    def total(bloque: dict[str, Any]) -> tuple[int, Decimal]:
        return bloque["cantidad"], Decimal(bloque["total"])

    def medios(bloque: dict[str, Any]) -> dict[str, Decimal]:
        return {m["nombre"]: Decimal(m["total"]) for m in bloque["por_medio"]}

    dinero = resumen.dinero
    assert fila["estado"] == resumen.estado
    assert fila["con_conteo"] is resumen.con_conteo
    assert total(fila["ventas"]) == (dinero.ventas.cantidad, dinero.ventas.total)
    assert total(fila["anuladas"]) == (dinero.anuladas.cantidad, dinero.anuladas.total)
    assert total(fila["cobranzas"]) == (dinero.cobranzas.cantidad, dinero.cobranzas.total)
    assert medios(fila["cobranzas"]) == {m.nombre: m.total for m in dinero.cobranzas.por_medio}
    tardio = resumen.despues_de_la_rendicion
    if tardio is None:
        assert fila["despues_de_la_rendicion"] is None
    else:
        despues = fila["despues_de_la_rendicion"]
        assert total(despues["ventas"]) == (tardio.ventas.cantidad, tardio.ventas.total)
        assert total(despues["anuladas"]) == (tardio.anuladas.cantidad, tardio.anuladas.total)
        assert total(despues["cobranzas"]) == (tardio.cobranzas.cantidad, tardio.cobranzas.total)
        assert medios(despues["cobranzas"]) == {
            m.nombre: m.total for m in tardio.cobranzas.por_medio
        }
    if resumen.con_conteo:
        diferencias = [linea.diferencia for linea in resumen.lineas]
        assert fila["faltantes"] == sum(-d for d in diferencias if d is not None and d < 0)
        assert fila["sobrantes"] == sum(d for d in diferencias if d is not None and d > 0)
        esperado = resumen.valor_de_diferencias if con_costos else None
        assert (
            None if fila["valor_de_diferencias"] is None else Decimal(fila["valor_de_diferencias"])
        ) == esperado
    else:
        assert fila["faltantes"] is None and fila["sobrantes"] is None
        assert fila["valor_de_diferencias"] is None


def _resumen(sesion: Session, s: Sesion, jornada_id: UUID, *, con_costos: bool) -> Any:
    sesion.commit()
    return stock_service.obtener_resumen_de_jornada(
        s.entorno.org, sesion, jornada_id=jornada_id, con_costos=con_costos
    )


# --- las jornadas del período (RUT-07) --------------------------------------------------------


def test_la_jornada_rendida_informa_ventas_anuladas_cobrado_y_diferencias(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Jornada rendida»: 2 ventas vigentes, 1 anulada, lo cobrado por medio, 2
    unidades faltantes y 1 sobrante."""
    s = Sesion(sesion)
    rendida = Rendida(sesion, s, ubicacion="Camioneta 1")
    headers = _lector(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    (fila,) = cuerpo["jornadas"]["filas"]
    assert fila["jornada_id"] == str(rendida.jornada_id)
    assert (fila["vendedor_id"], fila["vendedor_nombre"]) == (
        str(rendida.vendedor.usuario_id),
        "Juan",
    )
    assert fila["ubicacion_nombre"] == "Camioneta 1"
    assert (fila["estado"], fila["en_curso"], fila["con_conteo"]) == ("CERRADA", False, True)
    assert fila["ventas"] == {"cantidad": 2, "total": "3000.00"}
    assert fila["anuladas"] == {"cantidad": 1, "total": "500.00"}
    assert fila["cobranzas"]["cantidad"] == 2
    assert fila["cobranzas"]["total"] == "600.00"
    assert {m["nombre"]: m["total"] for m in fila["cobranzas"]["por_medio"]} == {
        "Efectivo": "400.00",
        "Transferencia": "200.00",
    }
    assert (fila["faltantes"], fila["sobrantes"]) == (2, 1)
    assert fila["despues_de_la_rendicion"]["ventas"] == {"cantidad": 0, "total": "0.00"}


def test_cada_fila_coincide_con_el_resumen_de_su_jornada(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Riesgo «dos implementaciones de RUT-07»: rendida, con lo tardío, liberada, abierta y
    de otro vendedor; la lista y `stock.service.obtener_resumen_de_jornada` dan lo mismo."""
    s = Sesion(sesion)
    rendida = Rendida(sesion, s)
    rendida.vender("700.00", 18, registered_at=dia(11, 3, 18))
    sembrar_cobranza(
        sesion,
        s,
        rendida.jornada_id,
        [(s.entorno.efectivo_id, "50.00")],
        cuando=dia(11, 3, 19),
        vendedor=rendida.vendedor,
    )
    otro = crear_vendedor(sesion, s, "Ana")
    liberada = sembrar_jornada(sesion, s, vendedor=otro, estado="LIBERADA")
    sembrar_venta(
        sesion,
        s,
        vendedor_id=otro.usuario_id,
        occurred_at=dia(11, 3, 10),
        lineas=[LineaDePrueba(neto="250.00")],
        modo_confirmacion="OFFLINE",
        jornada_id=liberada,
    )
    sembrar_cobranza(
        sesion,
        s,
        liberada,
        [(s.entorno.transferencia_id, "125.00")],
        cuando=dia(11, 3, 11),
        vendedor=otro,
    )
    tercero = crear_vendedor(sesion, s, "Beto")
    abierta = sembrar_jornada(sesion, s, vendedor=tercero, estado="ABIERTA")
    headers = _lector_con_costos(cliente_http, sesion, s)

    filas = _por_jornada(_pedir(cliente_http, headers, **NOVIEMBRE))

    assert set(filas) == {str(rendida.jornada_id), str(liberada), str(abierta)}
    for jornada_id in (rendida.jornada_id, liberada, abierta):
        resumen = _resumen(sesion, s, jornada_id, con_costos=True)
        _coincide_con_el_resumen(filas[str(jornada_id)], resumen, con_costos=True)


def test_lo_registrado_despues_de_la_rendicion_va_aparte(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Lo registrado después de la rendición»: la venta sin conexión que llegó tarde
    se informa en «Después de la rendición» y no en las vigentes."""
    s = Sesion(sesion)
    rendida = Rendida(sesion, s)
    tardia = rendida.vender("700.00", 18, registered_at=rendida.corte.replace(hour=23))
    anular_venta(
        sesion,
        s,
        rendida.vender("90.00", 9),
        anulada_en=dia(11, 3, 9),
        jornada_id=rendida.jornada_id,
        registered_at=rendida.corte.replace(hour=23),
    )
    sembrar_cobranza(
        sesion,
        s,
        rendida.jornada_id,
        [(s.entorno.efectivo_id, "40.00")],
        cuando=rendida.corte.replace(hour=23),
        vendedor=rendida.vendedor,
    )
    headers = _lector(cliente_http, sesion, s)

    (fila,) = _pedir(cliente_http, headers, **NOVIEMBRE)["jornadas"]["filas"]

    assert tardia is not None
    assert fila["ventas"] == {"cantidad": 2, "total": "3000.00"}
    despues = fila["despues_de_la_rendicion"]
    assert despues["ventas"] == {"cantidad": 1, "total": "700.00"}
    assert despues["anuladas"] == {"cantidad": 1, "total": "90.00"}
    assert despues["cobranzas"]["total"] == "40.00"
    assert [m["total"] for m in despues["cobranzas"]["por_medio"]] == ["40.00"]


def test_la_jornada_liberada_sale_sin_conteo(cliente_http: TestClient, sesion: Session) -> None:
    """Escenario «Jornada liberada sin conteo»: estado LIBERADA, sus ventas y cobranzas, y sin
    faltantes ni sobrantes."""
    s = Sesion(sesion)
    vendedor = crear_vendedor(sesion, s, "Juan")
    jornada = sembrar_jornada(sesion, s, vendedor=vendedor, estado="LIBERADA")
    sembrar_venta(
        sesion,
        s,
        vendedor_id=vendedor.usuario_id,
        occurred_at=dia(11, 3, 10),
        lineas=[LineaDePrueba(neto="800.00")],
        modo_confirmacion="OFFLINE",
        jornada_id=jornada,
    )
    sembrar_cobranza(
        sesion,
        s,
        jornada,
        [(s.entorno.efectivo_id, "800.00")],
        cuando=dia(11, 3, 11),
        vendedor=vendedor,
    )
    headers = _lector_con_costos(cliente_http, sesion, s)

    (fila,) = _pedir(cliente_http, headers, **NOVIEMBRE)["jornadas"]["filas"]

    assert (fila["estado"], fila["con_conteo"]) == ("LIBERADA", False)
    assert fila["ventas"] == {"cantidad": 1, "total": "800.00"}
    assert fila["cobranzas"]["total"] == "800.00"
    assert fila["faltantes"] is None and fila["sobrantes"] is None
    assert fila["valor_de_diferencias"] is None
    assert fila["despues_de_la_rendicion"] is None


def test_una_jornada_abierta_se_marca_en_curso(cliente_http: TestClient, sesion: Session) -> None:
    s = Sesion(sesion)
    vendedor = crear_vendedor(sesion, s, "Juan")
    sembrar_jornada(sesion, s, vendedor=vendedor, estado="ABIERTA")
    cerrada = Rendida(sesion, s, nombre="Ana")
    headers = _lector(cliente_http, sesion, s)

    filas = _pedir(cliente_http, headers, **NOVIEMBRE)["jornadas"]["filas"]

    assert {f["vendedor_nombre"]: (f["estado"], f["en_curso"]) for f in filas} == {
        "Juan": ("ABIERTA", True),
        "Ana": ("CERRADA", False),
    }
    assert cerrada.jornada_id


def test_el_valor_de_las_diferencias_solo_lo_ve_quien_tiene_ver_costos(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Valor de las diferencias según permiso»: -2 x 100 y +1 x 100 = `-100.00`."""
    s = Sesion(sesion)
    Rendida(sesion, s)
    con_costos = _lector_con_costos(cliente_http, sesion, s)
    sin_costos = _lector(cliente_http, sesion, s)

    (con,) = _pedir(cliente_http, con_costos, **NOVIEMBRE)["jornadas"]["filas"]
    (sin,) = _pedir(cliente_http, sin_costos, **NOVIEMBRE)["jornadas"]["filas"]
    por_vendedor_con = _pedir(cliente_http, con_costos, **NOVIEMBRE)["por_vendedor"]
    por_vendedor_sin = _pedir(cliente_http, sin_costos, **NOVIEMBRE)["por_vendedor"]

    assert con["valor_de_diferencias"] == "-100.00"
    assert sin["valor_de_diferencias"] is None
    assert (sin["faltantes"], sin["sobrantes"]) == (2, 1)
    assert por_vendedor_con[0]["valor_de_diferencias"] == "-100.00"
    assert por_vendedor_sin[0]["valor_de_diferencias"] is None


def test_una_diferencia_sin_costo_no_suma_en_el_valor(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Triangulación del valor: la línea sin costo unitario no aporta (como en el resumen)."""
    s = Sesion(sesion)
    vendedor = crear_vendedor(sesion, s, "Juan")
    jornada = sembrar_jornada(sesion, s, vendedor=vendedor, estado="CERRADA")
    sembrar_rendicion(
        sesion,
        s,
        jornada,
        vendedor=vendedor,
        lineas=[
            LineaContada(s.entorno.vino_id, esperada=10, contada=7, costo_unitario="250.500000"),
            LineaContada(
                crear_producto_sql(sesion, s.entorno.org, nombre="Sin costo"),
                esperada=4,
                contada=1,
                costo_unitario=None,
            ),
        ],
    )
    headers = _lector_con_costos(cliente_http, sesion, s)

    (fila,) = _pedir(cliente_http, headers, **NOVIEMBRE)["jornadas"]["filas"]

    assert (fila["faltantes"], fila["sobrantes"]) == (6, 0)
    assert fila["valor_de_diferencias"] == "-751.50"
    _coincide_con_el_resumen(fila, _resumen(sesion, s, jornada, con_costos=True), con_costos=True)


def test_los_filtros_de_vendedor_y_estado(cliente_http: TestClient, sesion: Session) -> None:
    """Escenario «Filtros por vendedor y estado»."""
    s = Sesion(sesion)
    uno = Rendida(sesion, s, nombre="Juan")
    dos = Rendida(sesion, s, nombre="Ana")
    abierta = sembrar_jornada(sesion, s, vendedor=crear_vendedor(sesion, s, "Beto"))
    anterior = sembrar_jornada(
        sesion, s, vendedor=dos.vendedor, estado="CERRADA", abierta_en=dia(11, 2, 8)
    )
    sembrar_jornada(sesion, s, vendedor=dos.vendedor, estado="ABIERTA", abierta_en=dia(11, 4, 8))
    headers = _lector(cliente_http, sesion, s)

    filtradas = _pedir(
        cliente_http,
        headers,
        vendedor_id=str(dos.vendedor.usuario_id),
        estado="CERRADA",
        **NOVIEMBRE,
    )
    solo_abiertas = _pedir(cliente_http, headers, estado="ABIERTA", **NOVIEMBRE)

    assert {f["jornada_id"] for f in filtradas["jornadas"]["filas"]} == {
        str(dos.jornada_id),
        str(anterior),
    }
    assert [v["vendedor_nombre"] for v in filtradas["por_vendedor"]] == ["Ana"]
    assert filtradas["por_vendedor"][0]["jornadas"] == 2
    assert {f["vendedor_nombre"] for f in solo_abiertas["jornadas"]["filas"]} == {"Beto", "Ana"}
    assert str(uno.jornada_id) not in {f["jornada_id"] for f in solo_abiertas["jornadas"]["filas"]}
    assert str(abierta) in {f["jornada_id"] for f in solo_abiertas["jornadas"]["filas"]}


def test_el_periodo_es_por_la_fecha_de_negocio_de_la_apertura(
    cliente_http: TestClient, sesion: Session
) -> None:
    """TR-04: la jornada abierta el 31/10 a las 23:00 (Mendoza) es de octubre; el reloj
    inyectable fija el mes en curso cuando no hay fechas."""
    s = Sesion(sesion)
    vendedor = crear_vendedor(sesion, s, "Juan")
    de_octubre = sembrar_jornada(
        sesion, s, vendedor=vendedor, estado="CERRADA", abierta_en=dia(10, 31, 23)
    )
    de_noviembre = sembrar_jornada(
        sesion, s, vendedor=vendedor, estado="CERRADA", abierta_en=dia(11, 1, 0)
    )
    headers = _lector(cliente_http, sesion, s)
    fijar_reloj(cliente_http, dia(11, 15))

    en_noviembre = _pedir(cliente_http, headers, **NOVIEMBRE)
    sin_fechas = _pedir(cliente_http, headers)
    octubre = _pedir(cliente_http, headers, desde="2026-10-01", hasta="2026-10-31")

    assert [f["jornada_id"] for f in en_noviembre["jornadas"]["filas"]] == [str(de_noviembre)]
    assert [f["jornada_id"] for f in sin_fechas["jornadas"]["filas"]] == [str(de_noviembre)]
    assert sin_fechas["periodo"]["desde"] == "2026-11-01"
    assert [f["jornada_id"] for f in octubre["jornadas"]["filas"]] == [str(de_octubre)]


def test_un_periodo_sin_jornadas_devuelve_listas_vacias(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = _lector(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    assert (cuerpo["jornadas"]["filas"], cuerpo["por_vendedor"]) == ([], [])


def test_el_periodo_invertido_y_el_demasiado_largo_se_rechazan(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = _lector(cliente_http, sesion, s)

    invertido = cliente_http.get(
        URL, params={"desde": "2026-11-30", "hasta": "2026-11-01"}, headers=headers
    )
    largo = cliente_http.get(
        URL, params={"desde": "2025-01-01", "hasta": "2026-11-01"}, headers=headers
    )

    assert (invertido.status_code, invertido.json()["codigo"]) == (422, "RANGO_DE_FECHAS_INVALIDO")
    assert (largo.status_code, largo.json()["codigo"]) == (422, "PERIODO_DEMASIADO_LARGO")


# --- totales por vendedor (RUT-07) ------------------------------------------------------------


def test_los_totales_por_vendedor_suman_sus_jornadas(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Dos jornadas del mismo vendedor»: 2 jornadas, la suma de ventas, anuladas,
    cobrado por medio y diferencias; otro vendedor aparte."""
    s = Sesion(sesion)
    primera = Rendida(sesion, s, nombre="Juan")
    segunda_jornada = sembrar_jornada(
        sesion, s, vendedor=primera.vendedor, estado="CERRADA", abierta_en=dia(11, 5, 8)
    )
    sembrar_venta(
        sesion,
        s,
        vendedor_id=primera.vendedor.usuario_id,
        occurred_at=dia(11, 5, 10),
        lineas=[LineaDePrueba(neto="400.00")],
        modo_confirmacion="OFFLINE",
        jornada_id=segunda_jornada,
    )
    sembrar_cobranza(
        sesion,
        s,
        segunda_jornada,
        [(s.entorno.efectivo_id, "70.00"), (s.entorno.transferencia_id, "30.00")],
        cuando=dia(11, 5, 12),
        vendedor=primera.vendedor,
    )
    sembrar_rendicion(
        sesion,
        s,
        segunda_jornada,
        vendedor=primera.vendedor,
        lineas=[LineaContada(s.entorno.vino_id, esperada=3, contada=0)],
    )
    Rendida(sesion, s, nombre="Ana")
    headers = _lector_con_costos(cliente_http, sesion, s)

    por_vendedor = {
        v["vendedor_nombre"]: v for v in _pedir(cliente_http, headers, **NOVIEMBRE)["por_vendedor"]
    }

    juan = por_vendedor["Juan"]
    assert juan["jornadas"] == 2
    assert juan["ventas"] == {"cantidad": 3, "total": "3400.00"}
    assert juan["anuladas"] == {"cantidad": 1, "total": "500.00"}
    assert juan["cobranzas"]["total"] == "700.00"
    assert {m["nombre"]: m["total"] for m in juan["cobranzas"]["por_medio"]} == {
        "Efectivo": "470.00",
        "Transferencia": "230.00",
    }
    assert (juan["faltantes"], juan["sobrantes"]) == (5, 1)
    assert juan["valor_de_diferencias"] == "-400.00"
    assert list(por_vendedor) == ["Ana", "Juan"]
    assert por_vendedor["Ana"]["jornadas"] == 1
    assert por_vendedor["Ana"]["ventas"] == {"cantidad": 2, "total": "3000.00"}


# --- aislamiento (INV-21) ---------------------------------------------------------------------


def test_inv21_la_lista_no_incluye_jornadas_de_otra_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = Sesion(sesion)
    ajena = Sesion(sesion)
    mia = Rendida(sesion, propia, nombre="Juan")
    Rendida(sesion, ajena, nombre="Ajeno")
    headers = _lector(cliente_http, sesion, propia)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    assert [f["jornada_id"] for f in cuerpo["jornadas"]["filas"]] == [str(mia.jornada_id)]
    assert [v["vendedor_nombre"] for v in cuerpo["por_vendedor"]] == ["Juan"]


def test_inv21_filtrar_por_un_vendedor_ajeno_devuelve_vacio(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = Sesion(sesion)
    ajena = Sesion(sesion)
    Rendida(sesion, propia, nombre="Juan")
    otra = Rendida(sesion, ajena, nombre="Ajeno")
    headers = _lector(cliente_http, sesion, propia)

    cuerpo = _pedir(cliente_http, headers, vendedor_id=str(otra.vendedor.usuario_id), **NOVIEMBRE)

    assert (cuerpo["jornadas"]["filas"], cuerpo["por_vendedor"]) == ([], [])


# --- el detalle de una jornada (tarea 4.2; RUT-07, INV-21) -------------------------------------


def test_el_detalle_es_el_resumen_de_rut07_sin_el_valor_para_quien_no_ve_costos(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Detalle sin permisos de jornadas»: `consulta` (solo `VER_REPORTES`) recibe el
    resumen sin el valor de las diferencias."""
    s = Sesion(sesion)
    rendida = Rendida(sesion, s)
    headers = _lector(cliente_http, sesion, s)

    respuesta = cliente_http.get(f"{URL}/{rendida.jornada_id}", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["jornada_id"] == str(rendida.jornada_id)
    assert (cuerpo["estado"], cuerpo["con_conteo"]) == ("CERRADA", True)
    assert "valor_de_diferencias" not in cuerpo
    assert all("valor_diferencia" not in linea for linea in cuerpo["lineas"])
    assert {linea["diferencia"] for linea in cuerpo["lineas"]} == {-2, 1}
    assert cuerpo["dinero"]["ventas"] == {"cantidad": 2, "total": "3000.00"}
    assert cuerpo["dinero"]["anuladas"]["total"] == "500.00"
    assert {m["nombre"]: m["total"] for m in cuerpo["dinero"]["cobranzas"]["por_medio"]} == {
        "Efectivo": "400.00",
        "Transferencia": "200.00",
    }


def test_el_detalle_trae_el_valor_con_ver_costos(cliente_http: TestClient, sesion: Session) -> None:
    s = Sesion(sesion)
    rendida = Rendida(sesion, s)
    headers = _lector_con_costos(cliente_http, sesion, s)

    cuerpo = cliente_http.get(f"{URL}/{rendida.jornada_id}", headers=headers).json()

    assert cuerpo["valor_de_diferencias"] == "-100.00"
    assert {linea["valor_diferencia"] for linea in cuerpo["lineas"]} == {"-200.00", "100.00"}


def test_inv21_el_detalle_de_una_jornada_ajena_o_inexistente_es_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Jornada de otra organización»."""
    propia = Sesion(sesion)
    ajena = Sesion(sesion)
    de_otra = Rendida(sesion, ajena, nombre="Ajeno")
    headers = _lector(cliente_http, sesion, propia)

    ajeno = cliente_http.get(f"{URL}/{de_otra.jornada_id}", headers=headers)
    inexistente = cliente_http.get(f"{URL}/{uuid4()}", headers=headers)

    assert ajeno.status_code == 404
    assert inexistente.status_code == 404
    assert ajeno.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


def test_el_detalle_nombra_cada_producto_y_trae_su_referencia_sin_pedir_el_catalogo(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Un lector solo con `VER_REPORTES` no puede leer el catálogo: el detalle trae el código, el
    nombre y la presentación de referencia de cada línea (RUT-07, INV-21)."""
    s = Sesion(sesion)
    rendida = Rendida(sesion, s)
    crear_presentacion_referencia_sql(
        sesion, s.entorno.org, rendida.producto_extra, unidades_base=12
    )
    headers = _lector(cliente_http, sesion, s)

    cuerpo = cliente_http.get(f"{URL}/{rendida.jornada_id}", headers=headers).json()

    por_producto = {linea["producto_id"]: linea for linea in cuerpo["lineas"]}
    extra = por_producto[str(rendida.producto_extra)]
    assert extra["producto_nombre"] == "Agua 500"
    assert extra["producto_codigo"].startswith("COD-")
    assert (extra["unidades_referencia"], extra["nombre_referencia"]) == (12, "Caja x12")
    vino = por_producto[str(s.entorno.vino_id)]
    assert vino["producto_nombre"] and vino["producto_codigo"]
    assert (vino["unidades_referencia"], vino["nombre_referencia"]) == (6, "Caja x6")


def test_un_producto_sin_presentacion_de_referencia_viaja_con_su_nombre_y_sin_referencia(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    rendida = Rendida(sesion, s)
    headers = _lector(cliente_http, sesion, s)

    cuerpo = cliente_http.get(f"{URL}/{rendida.jornada_id}", headers=headers).json()

    extra = {linea["producto_id"]: linea for linea in cuerpo["lineas"]}[str(rendida.producto_extra)]
    assert extra["producto_nombre"] == "Agua 500"
    assert (extra["unidades_referencia"], extra["nombre_referencia"]) == (None, None)
