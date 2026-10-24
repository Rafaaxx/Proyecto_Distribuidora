# ruff: noqa: F811
"""Tarea 11.1 (change 18b, `design.md` D15; spec `ventas/administracion-de-ventas`):
`GET /api/v1/ventas/contexto` con `VENDER` trae lo que la pantalla de venta necesita saber de quien
vende: si el descuento manual está habilitado y exige motivo, su permiso y su tope (el propio o el
de su rol, como fracción de texto), si puede autorizar descuentos y superar el crédito, los motivos
activos del ámbito `DESCUENTO_MANUAL` y los autorizadores posibles (activos, con rol activo, con PIN
definido y con `AUTORIZAR_DESCUENTO` o `SUPERAR_CREDITO`, sin el propio usuario y nunca con la
derivación del PIN). El tope no se agrega a `GET /yo`.

Reglas citadas: DSC-06, SYN-11, SEG-06, SEG-07, ADR-011, INV-21.
"""

from __future__ import annotations

from datetime import UTC, datetime
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

from app.modules.identidad import service as identidad_service

URL = "/api/v1/ventas/contexto"


class _Reloj:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC)


def _contexto(cliente_http: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    respuesta = cliente_http.get(URL, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo: dict[str, Any] = respuesta.json()
    return cuerpo


def _vendedor(sesion: Session) -> Sesion:
    s = Sesion(sesion)
    s.entorno.configurar(descuento_manual_habilitado=True, motivo_obligatorio_descuento=True)
    sesion.commit()
    return s


def test_dsc06_el_vendedor_ve_su_tope_de_rol_como_fraccion_y_sus_permisos(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "El vendedor ve su tope": Pedro, con tope de rol 5 %, recibe `"0.050000"`."""
    s = _vendedor(sesion)
    s.entorno.permitir("DESCUENTO_MANUAL")
    s.entorno.fijar_tope("0.05")
    headers = s.entrar(cliente_http)

    contexto = _contexto(cliente_http, headers)

    assert contexto["descuento_manual"] == {
        "habilitado": True,
        "motivo_obligatorio": True,
        "tiene_permiso": True,
        "tope": "0.050000",
        "puede_autorizar": False,
    }
    assert contexto["credito"] == {"puede_superar": False}


def test_dsc06_el_tope_propio_reemplaza_al_del_rol_y_los_permisos_de_autorizar_se_reflejan(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Triangulación: tope propio 12 % sobre el del rol; con `AUTORIZAR_DESCUENTO` y
    `SUPERAR_CREDITO` puede autorizar y superar; el motivo deja de ser obligatorio."""
    s = _vendedor(sesion)
    s.entorno.configurar(motivo_obligatorio_descuento=False)
    s.entorno.permitir("DESCUENTO_MANUAL", "AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO")
    s.entorno.fijar_tope("0.05")
    sesion.execute(
        text("UPDATE usuario SET tope_descuento_override = 0.12 WHERE id = :u"),
        {"u": s.entorno.usuario_id},
    )
    sesion.commit()
    headers = s.entrar(cliente_http)

    contexto = _contexto(cliente_http, headers)

    assert contexto["descuento_manual"] == {
        "habilitado": True,
        "motivo_obligatorio": False,
        "tiene_permiso": True,
        "tope": "0.120000",
        "puede_autorizar": True,
    }
    assert contexto["credito"] == {"puede_superar": True}


def test_dsc06_sin_descuento_manual_no_hay_permiso_ni_tope(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Sin permiso de descuento manual" y organización con el descuento deshabilitado
    (un `motivo_obligatorio_descuento` sin valor equivale a no exigirlo)."""
    s = _vendedor(sesion)
    s.entorno.configurar(descuento_manual_habilitado=False, motivo_obligatorio_descuento=None)
    sesion.commit()
    headers = s.entrar(cliente_http)

    contexto = _contexto(cliente_http, headers)

    assert contexto["descuento_manual"] == {
        "habilitado": False,
        "motivo_obligatorio": False,
        "tiene_permiso": False,
        "tope": None,
        "puede_autorizar": False,
    }


def test_dsc06_los_motivos_son_solo_los_activos_del_ambito_de_descuento_manual_propio(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = _vendedor(sesion)
    cortesia = s.entorno.crear_motivo("DESCUENTO_MANUAL", "Cortesía")
    inactivo = s.entorno.crear_motivo("DESCUENTO_MANUAL", "Promo vieja")
    s.entorno.crear_motivo("ANULACION_COMPRA", "Otro ámbito")
    ajena = s.entorno.otra_organizacion()
    s.entorno.crear_motivo("DESCUENTO_MANUAL", "De otra organización", org=ajena)
    sesion.execute(text("UPDATE motivo SET activo = false WHERE id = :m"), {"m": inactivo})
    sesion.commit()
    headers = s.entrar(cliente_http)

    contexto = _contexto(cliente_http, headers)

    motivos = {m["id"]: m["nombre"] for m in contexto["motivos"]}
    assert motivos.get(str(cortesia)) == "Cortesía"
    assert str(inactivo) not in motivos
    assert "Otro ámbito" not in motivos.values()
    assert "De otra organización" not in motivos.values()


def test_syn11_los_autorizadores_traen_nombre_y_lo_que_pueden_autorizar_sin_la_derivacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Los autorizadores no traen el PIN": Marta (descuento), Luis (crédito) y una
    tercera persona (ambos), todos con PIN."""
    s = _vendedor(sesion)
    marta = s.entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin="482913")
    luis = s.entorno.crear_usuario(frozenset({"SUPERAR_CREDITO"}), pin="739158")
    ambos = s.entorno.crear_usuario(
        frozenset({"AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO"}), pin="615284"
    )
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.get(URL, headers=headers)

    assert respuesta.status_code == 200
    por_id = {a["id"]: a for a in respuesta.json()["autorizadores"]}
    assert set(por_id) == {str(marta), str(luis), str(ambos)}
    assert (
        por_id[str(marta)]["puede_autorizar_descuento"],
        por_id[str(marta)]["puede_superar_credito"],
    ) == (True, False)
    assert (
        por_id[str(luis)]["puede_autorizar_descuento"],
        por_id[str(luis)]["puede_superar_credito"],
    ) == (False, True)
    assert (
        por_id[str(ambos)]["puede_autorizar_descuento"],
        por_id[str(ambos)]["puede_superar_credito"],
    ) == (True, True)
    assert por_id[str(marta)]["nombre"] == "Supervisor de prueba"
    for autorizador in por_id.values():
        assert set(autorizador) == {
            "id",
            "nombre",
            "puede_autorizar_descuento",
            "puede_superar_credito",
        }
    for secreto in ("hash", "sal", "iteraciones", "482913", "739158", "615284"):
        assert secreto not in respuesta.text


def test_syn11_no_son_autorizadores_los_que_no_cumplen_las_condiciones(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Sin PIN, usuario inactivo, rol inactivo, sin permiso de descuento ni de crédito (solo
    `VENDER_CLIENTE_SUSPENDIDO`), de otra organización (INV-21) y el propio usuario (aunque tenga
    el permiso y un PIN)."""
    s = _vendedor(sesion)
    s.entorno.permitir("AUTORIZAR_DESCUENTO")
    identidad_service.establecer_pin_autorizacion(
        s.entorno.org,
        sesion,
        _Reloj(),
        usuario_id=s.entorno.usuario_id,
        pin="482913",
        actor_id=s.entorno.usuario_id,
    )
    valido = s.entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin="518294")
    sin_pin = s.entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}))
    inactivo = s.entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin="739158")
    rol_inactivo = s.entorno.crear_usuario(frozenset({"SUPERAR_CREDITO"}), pin="615284")
    sin_permiso = s.entorno.crear_usuario(frozenset({"VENDER_CLIENTE_SUSPENDIDO"}), pin="841926")
    ajena = s.entorno.otra_organizacion()
    de_otra = s.entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin="926418", org=ajena)
    sesion.execute(text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :u"), {"u": inactivo})
    sesion.execute(
        text("UPDATE rol SET activo = false WHERE id = (SELECT rol_id FROM usuario WHERE id = :u)"),
        {"u": rol_inactivo},
    )
    sesion.commit()
    headers = s.entrar(cliente_http)

    contexto = _contexto(cliente_http, headers)

    ids = {a["id"] for a in contexto["autorizadores"]}
    assert ids == {str(valido)}
    assert str(s.entorno.usuario_id) not in ids
    for excluido in (sin_pin, inactivo, rol_inactivo, sin_permiso, de_otra):
        assert str(excluido) not in ids


def test_seg06_sin_vender_responde_403_y_sin_sesion_401(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = _vendedor(sesion)
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
    sin_sesion = cliente_http.get(URL)

    assert sin_permiso.status_code == 403
    assert sin_permiso.json()["codigo"] == "PERMISO_REQUERIDO"
    assert sin_sesion.status_code == 401


def test_seg07_get_yo_no_cambia_y_no_trae_el_tope(
    cliente_http: TestClient, sesion: Session
) -> None:
    """El tope no se agrega a `GET /yo` ni al token (decisión del 2026-10-15)."""
    s = _vendedor(sesion)
    s.entorno.permitir("DESCUENTO_MANUAL")
    s.entorno.fijar_tope("0.05")
    headers = s.entrar(cliente_http)

    yo = cliente_http.get("/api/v1/yo", headers=headers)

    assert set(yo.json()) == {"usuario", "organizacion", "rol", "permisos"}
    assert "tope" not in yo.text
