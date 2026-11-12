"""Tarea 5.1 (change 26, spec `reportes/observaciones-por-vendedor`; `design.md` D9):
`GET /api/v1/reportes/observaciones`: por vendedor, las ventas sin conexión, los avisos por código
(total y pendientes), las operaciones rechazadas (total y pendientes) y los excesos de crédito
detectados al sincronizar, contados en la base.

PostgreSQL real y login real. Reglas citadas: SYN-06, SYN-07, CRE-09, TR-04, INV-21.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from reportes_utiles import (
    ABRIR_REPORTES,
    LineaDePrueba,
    Vendedor,
    crear_vendedor,
    dia,
    fijar_reloj,
    sembrar_jornada,
    sembrar_venta,
)
from revision_utiles import resolver_por_sql, sembrar_observaciones, sembrar_rechazo
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import usuario_con

URL = "/api/v1/reportes/observaciones"
NOVIEMBRE = {"desde": "2026-11-01", "hasta": "2026-11-30"}
EXCESO = "EXCESO_CREDITO_DETECTADO_SYNC"


def _pedir(cliente_http: TestClient, headers: dict[str, str], **filtros: str) -> dict[str, Any]:
    respuesta = cliente_http.get(URL, params=filtros, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def _lector(cliente_http: TestClient, sesion: Session, s: Sesion) -> dict[str, str]:
    return usuario_con(cliente_http, sesion, s, ABRIR_REPORTES)


def _por_nombre(cuerpo: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {v["vendedor_nombre"]: v for v in cuerpo["vendedores"]}


def _avisos_por_codigo(vendedor: dict[str, Any]) -> dict[str, tuple[int, int]]:
    return {a["codigo"]: (a["total"], a["pendientes"]) for a in vendedor["avisos_por_codigo"]}


def _ventas_sin_conexion(
    sesion: Session, s: Sesion, vendedor: Vendedor, cantidad: int, *, cuando: datetime
) -> UUID:
    jornada = sembrar_jornada(sesion, s, vendedor=vendedor, estado="CERRADA", abierta_en=cuando)
    for _ in range(cantidad):
        sembrar_venta(
            sesion,
            s,
            vendedor_id=vendedor.usuario_id,
            occurred_at=cuando,
            lineas=[LineaDePrueba(neto="100.00")],
            modo_confirmacion="OFFLINE",
            jornada_id=jornada,
        )
    return jornada


def _avisar(
    sesion: Session, s: Sesion, vendedor: Vendedor, *codigos: str, cuando: datetime
) -> UUID:
    resultado = sembrar_observaciones(
        sesion,
        s.entorno.org,
        usuario_id=vendedor.usuario_id,
        dispositivo_id=vendedor.dispositivo_id,
        codigos=codigos,
        registered_at=cuando,
    )
    sesion.commit()
    return resultado.operacion_id


def _rechazar(
    sesion: Session, s: Sesion, vendedor: Vendedor, *, cuando: datetime, resuelto: bool = False
) -> None:
    rechazo = sembrar_rechazo(
        sesion,
        s.entorno.org,
        usuario_id=vendedor.usuario_id,
        dispositivo_id=vendedor.dispositivo_id,
        recibido_en=cuando,
    )
    if resuelto:
        sesion.execute(
            text(
                "UPDATE comando_rechazado SET estado = 'RESUELTO', resuelto_por_id = :u, "
                "resuelto_en = :m, comentario = 'Se cargó a mano' "
                "WHERE organizacion_id = :o AND id = :r"
            ),
            {"u": s.entorno.usuario_id, "m": cuando, "o": s.entorno.org, "r": rechazo},
        )
    sesion.commit()


def test_el_vendedor_con_avisos_y_rechazos_se_cuenta_en_su_fila(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Vendedor con avisos y rechazos»: 3 ventas sin conexión, `STOCK_NEGATIVO` 2 (1
    pendiente), 1 exceso detectado (pendiente) y 1 rechazada (pendiente)."""
    s = Sesion(sesion)
    juan = crear_vendedor(sesion, s, "Juan")
    _ventas_sin_conexion(sesion, s, juan, 3, cuando=dia(11, 3))
    resuelta = _avisar(sesion, s, juan, "STOCK_NEGATIVO", cuando=dia(11, 3, 10))
    _avisar(sesion, s, juan, "STOCK_NEGATIVO", cuando=dia(11, 3, 11))
    _avisar(sesion, s, juan, EXCESO, cuando=dia(11, 3, 12))
    resolver_por_sql(sesion, s.entorno.org, resuelta, s.entorno.usuario_id)
    _rechazar(sesion, s, juan, cuando=dia(11, 3, 13))
    headers = _lector(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    (fila,) = cuerpo["vendedores"]
    assert (fila["vendedor_id"], fila["vendedor_nombre"]) == (str(juan.usuario_id), "Juan")
    assert fila["ventas_sin_conexion"] == 3
    assert _avisos_por_codigo(fila) == {"STOCK_NEGATIVO": (2, 1), EXCESO: (1, 1)}
    assert fila["avisos"] == {"total": 3, "pendientes": 2}
    assert fila["excesos_de_credito_detectados"] == {"total": 1, "pendientes": 1}
    assert fila["rechazadas"] == {"total": 1, "pendientes": 1}
    assert cuerpo["periodo"]["desde"] == "2026-11-01"


def test_cada_vendedor_tiene_su_fila_y_solo_cuentan_las_ventas_sin_conexion_vigentes(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Triangulación: otro vendedor con otras cifras; una venta con conexión no es «sin
    conexión»; el vendedor sin actividad no aparece; las filas van por nombre."""
    s = Sesion(sesion)
    juan = crear_vendedor(sesion, s, "Juan")
    ana = crear_vendedor(sesion, s, "Ana")
    crear_vendedor(sesion, s, "Beto")
    _ventas_sin_conexion(sesion, s, juan, 1, cuando=dia(11, 3))
    sembrar_venta(
        sesion,
        s,
        vendedor_id=ana.usuario_id,
        occurred_at=dia(11, 4),
        lineas=[LineaDePrueba(neto="100.00")],
    )
    _rechazar(sesion, s, ana, cuando=dia(11, 4), resuelto=True)
    _rechazar(sesion, s, ana, cuando=dia(11, 5))
    _avisar(sesion, s, ana, "PERMISO_REVOCADO", "VENTA_SIN_COSTO", cuando=dia(11, 5))
    headers = _lector(cliente_http, sesion, s)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    assert [v["vendedor_nombre"] for v in cuerpo["vendedores"]] == ["Ana", "Juan"]
    filas = _por_nombre(cuerpo)
    assert filas["Ana"]["ventas_sin_conexion"] == 0
    assert filas["Ana"]["rechazadas"] == {"total": 2, "pendientes": 1}
    assert _avisos_por_codigo(filas["Ana"]) == {
        "PERMISO_REVOCADO": (1, 1),
        "VENTA_SIN_COSTO": (1, 1),
    }
    assert filas["Ana"]["avisos"] == {"total": 2, "pendientes": 2}
    assert filas["Ana"]["excesos_de_credito_detectados"] == {"total": 0, "pendientes": 0}
    assert filas["Juan"]["ventas_sin_conexion"] == 1
    assert filas["Juan"]["avisos_por_codigo"] == []
    assert filas["Juan"]["rechazadas"] == {"total": 0, "pendientes": 0}


def test_lo_que_cae_fuera_del_periodo_no_se_cuenta(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Fuera del período»: aviso, rechazo y ventas del mes anterior; el reloj
    inyectable fija el mes en curso cuando no se piden fechas."""
    s = Sesion(sesion)
    juan = crear_vendedor(sesion, s, "Juan")
    _ventas_sin_conexion(sesion, s, juan, 2, cuando=dia(10, 20))
    _avisar(sesion, s, juan, "STOCK_NEGATIVO", cuando=dia(10, 20))
    _rechazar(sesion, s, juan, cuando=dia(10, 31, 23))
    _avisar(sesion, s, juan, "STOCK_NEGATIVO", cuando=dia(11, 2))
    headers = _lector(cliente_http, sesion, s)
    fijar_reloj(cliente_http, dia(11, 15))

    en_noviembre = _pedir(cliente_http, headers)
    en_octubre = _pedir(cliente_http, headers, desde="2026-10-01", hasta="2026-10-31")

    (noviembre,) = en_noviembre["vendedores"]
    assert noviembre["ventas_sin_conexion"] == 0
    assert _avisos_por_codigo(noviembre) == {"STOCK_NEGATIVO": (1, 1)}
    assert noviembre["rechazadas"] == {"total": 0, "pendientes": 0}
    (octubre,) = en_octubre["vendedores"]
    assert octubre["ventas_sin_conexion"] == 2
    assert _avisos_por_codigo(octubre) == {"STOCK_NEGATIVO": (1, 1)}
    assert octubre["rechazadas"] == {"total": 1, "pendientes": 1}


def test_un_periodo_sin_operaciones_devuelve_la_lista_vacia(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = _lector(cliente_http, sesion, s)

    assert _pedir(cliente_http, headers, **NOVIEMBRE)["vendedores"] == []


def test_el_periodo_invertido_se_rechaza(cliente_http: TestClient, sesion: Session) -> None:
    s = Sesion(sesion)
    headers = _lector(cliente_http, sesion, s)

    respuesta = cliente_http.get(
        URL, params={"desde": "2026-11-30", "hasta": "2026-11-01"}, headers=headers
    )

    assert (respuesta.status_code, respuesta.json()["codigo"]) == (422, "RANGO_DE_FECHAS_INVALIDO")


def test_inv21_no_cuenta_observaciones_ni_rechazos_de_otra_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Otra organización»."""
    propia = Sesion(sesion)
    ajena = Sesion(sesion)
    mio = crear_vendedor(sesion, propia, "Juan")
    otro = crear_vendedor(sesion, ajena, "Ajeno")
    _avisar(sesion, propia, mio, "STOCK_NEGATIVO", cuando=dia(11, 3))
    _avisar(sesion, ajena, otro, "STOCK_NEGATIVO", "VENTA_SIN_COSTO", cuando=dia(11, 3))
    _rechazar(sesion, ajena, otro, cuando=dia(11, 3))
    _ventas_sin_conexion(sesion, ajena, otro, 4, cuando=dia(11, 3))
    headers = _lector(cliente_http, sesion, propia)

    cuerpo = _pedir(cliente_http, headers, **NOVIEMBRE)

    (fila,) = cuerpo["vendedores"]
    assert fila["vendedor_nombre"] == "Juan"
    assert _avisos_por_codigo(fila) == {"STOCK_NEGATIVO": (1, 1)}
    assert (fila["ventas_sin_conexion"], fila["rechazadas"]["total"]) == (0, 0)
