# ruff: noqa: F811
"""Tarea 11.3 (change 18b; spec `ventas/administracion-de-ventas`, requisito "El detalle muestra
descuentos y crédito congelados"): `GET /api/v1/ventas/{id}` trae, por línea, cada descuento con su
origen, regla, porcentaje, importe, motivo y autorizador (con los nombres) y, en la cabecera, el
snapshot de crédito con el nombre de quien autorizó. Una venta anterior al change se muestra sin
snapshot y sin descuentos, y no falla.

Reglas citadas: DSC-08, CRE-10, INV-03, INV-10, INV-21.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import sembrar

PIN = "482913"


def _detalle(cliente_http: TestClient, headers: dict[str, str], venta_id: object) -> dict[str, Any]:
    respuesta = cliente_http.get(f"/api/v1/ventas/{venta_id}", headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo: dict[str, Any] = respuesta.json()
    return cuerpo


def _nombrar(s: Sesion, usuario_id: object, nombre: str) -> None:
    s.sesion.execute(
        text("UPDATE usuario SET nombre = :n WHERE id = :u"), {"n": nombre, "u": usuario_id}
    )
    s.sesion.commit()


def test_dsc08_el_detalle_de_una_venta_autorizada_muestra_a_los_dos_autorizadores(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Detalle de una venta autorizada": 8 % manual (tope 5 %) autorizado por Marta y
    exceso de crédito autorizado por Luis, cada uno con su nombre, y el motivo del descuento."""
    s = Sesion(sesion)
    e = s.entorno
    e.configurar(descuento_manual_habilitado=True, politica_credito_default="AUTORIZAR")
    e.permitir("DESCUENTO_MANUAL")
    e.fijar_tope("0.05")
    e.datos_de_credito(limite="160000.00", politica="AUTORIZAR")
    marta = e.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)
    luis = e.crear_usuario(frozenset({"SUPERAR_CREDITO"}), pin=PIN)
    _nombrar(s, marta, "Marta")
    _nombrar(s, luis, "Luis")
    motivo = e.crear_motivo("DESCUENTO_MANUAL", "Cortesía")
    sesion.commit()
    e.enviar(
        e.contenido(
            e.linea(
                descuentos=[
                    {
                        "origen": "MANUAL",
                        "regla_id": None,
                        "porcentaje": "0.080000",
                        "importe": "2500.00",
                    }
                ]
            ),
            total="28750.00",
            descuento_manual_general="0.08",
            descuento_autorizador_id=str(marta),
            motivo_descuento_id=str(motivo),
            credito={"autorizador_id": str(luis)},
        ),
        credenciales=(e.credencial(marta, PIN), e.credencial(luis, PIN)),
    )
    sesion.commit()
    (venta,) = e.ventas()
    headers = s.entrar(cliente_http)

    detalle = _detalle(cliente_http, headers, venta.id)

    (linea,) = detalle["lineas"]
    assert linea["descuentos"] == [
        {
            "origen": "MANUAL",
            "regla_id": None,
            "regla_nombre": None,
            "porcentaje": "0.080000",
            "importe": "2500.00",
            "motivo_id": str(motivo),
            "motivo_nombre": "Cortesía",
            "autorizador_id": str(marta),
            "autorizador_nombre": "Marta",
        }
    ]
    assert detalle["credito"] == {
        "limite": "160000.00",
        "saldo_considerado": "150000.00",
        "disponible": "10000.00",
        "exceso": "18750.00",
        "politica": "AUTORIZAR",
        "resolucion": "PIN_SUPERVISOR",
        "autorizador_id": str(luis),
        "autorizador_nombre": "Luis",
    }


def test_dsc08_un_descuento_automatico_trae_la_regla_y_nada_de_motivo_ni_autorizador(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Triangulación: el automático nombra su regla; sin límite el snapshot queda sin control
    (límite, disponible y exceso nulos) y la resolución es `SIN_EXCESO` (CRE-10)."""
    s = Sesion(sesion, stock_inicial=500)
    e = s.entorno
    e.datos_de_credito(limite=None, politica=None)
    regla = e.crear_regla()
    e.enviar(
        e.contenido(
            e.linea(
                cantidad=120,
                descuentos=[
                    {
                        "origen": "AUTOMATICO",
                        "regla_id": str(regla),
                        "porcentaje": "0.050000",
                        "importe": "12500.00",
                    }
                ],
            ),
            total="237500.00",
        )
    )
    sesion.commit()
    (venta,) = e.ventas()
    nombre_regla = sesion.scalar(
        text("SELECT nombre FROM regla_descuento WHERE id = :r"), {"r": regla}
    )
    headers = s.entrar(cliente_http)

    detalle = _detalle(cliente_http, headers, venta.id)

    (descuento,) = detalle["lineas"][0]["descuentos"]
    assert descuento["origen"] == "AUTOMATICO"
    assert descuento["regla_id"] == str(regla)
    assert descuento["regla_nombre"] == nombre_regla
    assert descuento["motivo_id"] is None
    assert descuento["motivo_nombre"] is None
    assert descuento["autorizador_id"] is None
    assert descuento["autorizador_nombre"] is None
    assert detalle["credito"]["limite"] is None
    assert detalle["credito"]["disponible"] is None
    assert detalle["credito"]["exceso"] is None
    assert detalle["credito"]["resolucion"] == "SIN_EXCESO"
    assert detalle["credito"]["autorizador_nombre"] is None


def test_cre10_una_venta_del_change_18a_se_muestra_sin_snapshot_y_sin_descuentos(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Venta del change anterior": sin columnas `credito_*` ni filas de descuento."""
    s = Sesion(sesion)
    vieja = sembrar(sesion, s)
    headers = s.entrar(cliente_http)

    detalle = _detalle(cliente_http, headers, vieja.venta_id)

    assert detalle["credito"] is None
    assert detalle["lineas"][0]["descuentos"] == []
