"""Tarea 3.1 (change 28, spec `sistema/verificacion-de-consistencia` y `organizacion/
aislamiento-multiorganizacion`; `design.md` D5): `GET /api/v1/sistema/consistencia` devuelve el
último resultado de la verificación de la organización del token, con el detalle y los nombres
de cuentas, productos y ubicaciones leídos por los servicios de cada módulo.

PostgreSQL real y login real. Reglas citadas: INV-21, SEG-06, SEG-07, ADR-015, `02` §7.6.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_api import (  # noqa: F401
    Sesion,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import usuario_con

URL = "/api/v1/sistema/consistencia"
VER = frozenset({"VER_CONSISTENCIA"})
SIN_EL_PERMISO = frozenset({"VER_REPORTES", "VENDER", "ADMIN_CONFIGURACION"})
MOMENTO = datetime(2026, 11, 10, 5, 0, tzinfo=UTC)
MAS_TARDE = datetime(2026, 11, 11, 5, 0, tzinfo=UTC)


def _guardar(
    sesion: Session,
    s: Sesion,
    diferencias: list[dict[str, object]],
    *,
    ejecutada_en: datetime = MOMENTO,
) -> None:
    sesion.execute(
        text(
            "INSERT INTO verificacion_consistencia (id, organizacion_id, ejecutada_en, resultado, "
            "diferencias, registered_at) VALUES (:id, :o, :e, :r, CAST(:d AS jsonb), :e)"
        ),
        {
            "id": uuid4(),
            "o": s.entorno.org,
            "e": ejecutada_en,
            "r": "CON_DIFERENCIAS" if diferencias else "SIN_DIFERENCIAS",
            "d": json.dumps(diferencias),
        },
    )
    sesion.commit()


def _nombre(sesion: Session, tabla: str, organizacion_id: UUID, id_: UUID) -> str:
    return str(
        sesion.execute(
            text(f"SELECT nombre FROM {tabla} WHERE organizacion_id = :o AND id = :i"),  # noqa: S608
            {"o": organizacion_id, "i": id_},
        ).scalar_one()
    )


def _pedir(cliente_http: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    respuesta = cliente_http.get(URL, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def _diferencia_de_cuenta(s: Sesion) -> dict[str, object]:
    return {
        "tipo": "SALDO_CUENTA",
        "cuenta_tipo": "CLIENTE",
        "entidad_id": str(s.entorno.cliente_id),
        "saldo_materializado": "1500.00",
        "suma_del_libro": "1450.00",
    }


def test_devuelve_el_ultimo_resultado_con_el_detalle_y_los_nombres(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «El administrador ve el aviso»: momento, cuenta afectada con su nombre y los
    importes como texto (INV-03), más producto y ubicación con nombre para el stock."""
    s = Sesion(sesion)
    org = s.entorno.org
    _guardar(
        sesion,
        s,
        [
            _diferencia_de_cuenta(s),
            {
                "tipo": "STOCK_SALDO",
                "producto_id": str(s.entorno.vino_id),
                "ubicacion_id": str(s.entorno.deposito_id),
                "materializado": 7,
                "esperado": 5,
            },
            {
                "tipo": "STOCK_TOTAL",
                "producto_id": str(s.entorno.vino_id),
                "ubicacion_id": None,
                "materializado": 9,
                "esperado": 5,
            },
            {
                "tipo": "PROMEDIO_COSTO",
                "producto_id": str(s.entorno.vino_id),
                "promedio_vigente": "10.500000",
                "promedio_historia": None,
            },
        ],
    )
    headers = usuario_con(cliente_http, sesion, s, VER)

    cuerpo = _pedir(cliente_http, headers)

    assert cuerpo["resultado"] == "CON_DIFERENCIAS"
    assert datetime.fromisoformat(cuerpo["ejecutada_en"]) == MOMENTO
    cuenta, stock, total, promedio = cuerpo["diferencias"]
    assert cuenta["tipo"] == "SALDO_CUENTA"
    assert cuenta["cuenta_tipo"] == "CLIENTE"
    assert cuenta["entidad_nombre"] == _nombre(sesion, "cliente", org, s.entorno.cliente_id)
    assert (cuenta["saldo_materializado"], cuenta["suma_del_libro"]) == ("1500.00", "1450.00")
    producto = _nombre(sesion, "producto", org, s.entorno.vino_id)
    ubicacion = _nombre(sesion, "ubicacion", org, s.entorno.deposito_id)
    assert (stock["producto_nombre"], stock["ubicacion_nombre"]) == (producto, ubicacion)
    assert (stock["materializado"], stock["esperado"]) == (7, 5)
    assert (total["tipo"], total["ubicacion_id"], total["ubicacion_nombre"]) == (
        "STOCK_TOTAL",
        None,
        None,
    )
    assert total["producto_nombre"] == producto
    assert (promedio["promedio_vigente"], promedio["promedio_historia"]) == ("10.500000", None)


def test_el_resultado_de_una_corrida_posterior_sin_diferencias_reemplaza_al_anterior(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «El aviso desaparece cuando una corrida posterior no encuentra diferencias»."""
    s = Sesion(sesion)
    _guardar(sesion, s, [_diferencia_de_cuenta(s)], ejecutada_en=MOMENTO)
    _guardar(sesion, s, [], ejecutada_en=MAS_TARDE)
    headers = usuario_con(cliente_http, sesion, s, VER)

    cuerpo = _pedir(cliente_http, headers)

    assert cuerpo["resultado"] == "SIN_DIFERENCIAS"
    assert cuerpo["diferencias"] == []
    assert datetime.fromisoformat(cuerpo["ejecutada_en"]) == MAS_TARDE


def test_sin_ninguna_corrida_todavia_no_hay_resultado(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    headers = usuario_con(cliente_http, sesion, s, VER)

    assert _pedir(cliente_http, headers) == {
        "ejecutada_en": None,
        "resultado": None,
        "diferencias": [],
    }


def test_un_usuario_sin_el_permiso_recibe_403_aunque_haya_diferencias(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «Un usuario sin el permiso no ve el aviso ni lee el resultado» (SEG-06):
    ni siquiera con `ADMIN_CONFIGURACION` (Q2: el permiso es otro)."""
    s = Sesion(sesion)
    _guardar(sesion, s, [_diferencia_de_cuenta(s)])
    headers = usuario_con(cliente_http, sesion, s, SIN_EL_PERMISO)

    respuesta = cliente_http.get(URL, headers=headers)

    assert respuesta.status_code == 403
    assert "1500.00" not in respuesta.text


def test_sin_sesion_responde_401(cliente_http: TestClient) -> None:
    assert cliente_http.get(URL).status_code == 401


def test_inv21_el_resultado_de_otra_organizacion_no_se_ve(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario «El resultado de otra organización no se ve» (INV-21, SEG-07): la A tiene una
    diferencia con su cliente; el administrador de la B recibe solo lo suyo, sin ningún dato de A
    (ni el id ni el nombre ni los importes)."""
    a = Sesion(sesion)
    b = Sesion(sesion)
    _guardar(sesion, a, [_diferencia_de_cuenta(a)], ejecutada_en=MAS_TARDE)
    _guardar(sesion, b, [], ejecutada_en=MOMENTO)
    headers_b = usuario_con(cliente_http, sesion, b, VER)

    cuerpo = _pedir(cliente_http, headers_b)

    assert cuerpo["resultado"] == "SIN_DIFERENCIAS"
    assert cuerpo["diferencias"] == []
    assert datetime.fromisoformat(cuerpo["ejecutada_en"]) == MOMENTO
    assert str(a.entorno.cliente_id) not in json.dumps(cuerpo)


def test_inv21_un_identificador_ajeno_en_el_detalle_no_revela_el_nombre(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Si el detalle guardado de la organización B nombrara una entidad de A (no debería
    pasar), el nombre se lee con la organización del token y no aparece: sale sin nombre."""
    a = Sesion(sesion)
    b = Sesion(sesion)
    _guardar(sesion, b, [_diferencia_de_cuenta(a)])
    headers_b = usuario_con(cliente_http, sesion, b, VER)

    cuerpo = _pedir(cliente_http, headers_b)

    assert cuerpo["diferencias"][0]["entidad_nombre"] is None
    nombre_ajeno = _nombre(sesion, "cliente", a.entorno.org, a.entorno.cliente_id)
    assert nombre_ajeno not in json.dumps(cuerpo)
