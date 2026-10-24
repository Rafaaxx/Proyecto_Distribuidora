# ruff: noqa: F811
"""Change 18b, apply del 2026-10-23 (spec `ventas/descuentos-en-la-venta`, escenario "El vendedor
ve los descuentos automáticos antes de confirmar"; ADR-050, ADR-055): `GET
/api/v1/ventas/descuentos-aplicables` con `VENDER` trae las reglas `ACTIVA` y vigentes ahora, con
su nombre y sus alcances, para que la pantalla calcule con la gemela del motor. El vendedor no
necesita `GESTIONAR_DESCUENTOS` (DSC-04).

Reglas citadas: DSC-01, DSC-04, DSC-05, SEG-06, INV-21.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_utiles import insertar_sql

URL = "/api/v1/ventas/descuentos-aplicables"


def _pedir(cliente_http: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    respuesta = cliente_http.get(URL, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    items: list[dict[str, Any]] = respuesta.json()["items"]
    return items


def test_dsc05_el_vendedor_sin_gestionar_descuentos_ve_la_regla_vigente_con_su_nombre(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    regla = s.entorno.crear_regla(porcentaje="0.050000", umbral="20")
    headers = s.entrar(cliente_http)

    (item,) = _pedir(cliente_http, headers)

    assert item["id"] == str(regla)
    assert item["nombre"] == f"Regla {regla.hex[:6]}"
    assert item["tipo"] == "VOLUMEN_OPERACION"
    assert item["medida"] == "CAJAS_EQUIVALENTES"
    assert item["operador"] == "GTE"
    assert Decimal(item["umbral"]) == Decimal("20")
    assert item["accion_tipo"] == "PORCENTAJE"
    assert item["accion_porcentaje"] == "0.050000"
    assert item["accion_importe"] is None
    assert item["acumulable"] is False
    assert item["prioridad"] == 1
    assert item["alcances"] == []


def test_dsc01_solo_las_activas_y_vigentes_ahora_no_borradores_pausadas_programadas_ni_vencidas(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    ahora = datetime.now(UTC)
    vigente = s.entorno.crear_regla(prioridad=2)
    s.entorno.crear_regla(estado="BORRADOR")
    s.entorno.crear_regla(estado="PAUSADA")
    s.entorno.crear_regla(desde=ahora + timedelta(days=1))
    s.entorno.crear_regla(desde=ahora - timedelta(days=10), hasta=ahora - timedelta(days=1))
    headers = s.entrar(cliente_http)

    items = _pedir(cliente_http, headers)

    assert [i["id"] for i in items] == [str(vigente)]


def test_dsc05_vienen_por_prioridad_y_con_sus_alcances(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Triangula: dos reglas ordenadas por prioridad; la segunda con alcance de producto."""
    s = Sesion(sesion)
    segunda = s.entorno.crear_regla(prioridad=5)
    primera = s.entorno.crear_regla(prioridad=1)
    producto_id, _ = s.entorno.producto_a("100")
    insertar_sql(
        sesion,
        "regla_descuento_alcance",
        {
            "id": uuid4(),
            "organizacion_id": s.entorno.org,
            "regla_id": segunda,
            "alcance_tipo": "PRODUCTO",
            "alcance_id": producto_id,
            "creado_en": datetime.now(UTC),
        },
    )
    sesion.commit()
    headers = s.entrar(cliente_http)

    items = _pedir(cliente_http, headers)

    assert [i["id"] for i in items] == [str(primera), str(segunda)]
    assert items[0]["alcances"] == []
    assert items[1]["alcances"] == [{"tipo": "PRODUCTO", "entidad_id": str(producto_id)}]


def test_inv21_las_reglas_de_otra_organizacion_no_figuran(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    ajena = s.entorno.otra_organizacion()
    sesion.execute(
        text(
            "INSERT INTO regla_descuento (id, organizacion_id, nombre, tipo, medida, operador, "
            "umbral, accion_tipo, accion_porcentaje, prioridad, acumulable, vigencia_desde, "
            "estado, creado_en, actualizado_en) VALUES (:id, :o, 'Ajena', 'VOLUMEN_OPERACION', "
            "'CAJAS_EQUIVALENTES', 'GTE', 1, 'PORCENTAJE', 0.1, 1, false, :d, 'ACTIVA', :d, :d)"
        ),
        {"id": uuid4(), "o": ajena, "d": datetime(2026, 1, 1, tzinfo=UTC)},
    )
    sesion.commit()
    headers = s.entrar(cliente_http)

    assert _pedir(cliente_http, headers) == []


def test_seg06_sin_vender_responde_403_y_sin_sesion_401(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    sesion.execute(
        text(
            "DELETE FROM rol_permiso WHERE permiso_codigo = 'VENDER' AND rol_id = "
            "(SELECT rol_id FROM usuario WHERE id = :u)"
        ),
        {"u": s.entorno.usuario_id},
    )
    sesion.commit()
    headers = s.entrar(cliente_http)

    sin_permiso = cliente_http.get(URL, headers=headers)
    assert sin_permiso.status_code == 403
    assert sin_permiso.json()["codigo"] == "PERMISO_REQUERIDO"
    assert cliente_http.get(URL).status_code == 401
