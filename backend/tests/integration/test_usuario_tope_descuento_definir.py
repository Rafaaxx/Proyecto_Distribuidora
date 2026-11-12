# ruff: noqa: F811
"""Change 20b, tarea 5.1: `USUARIO_TOPE_DESCUENTO_DEFINIR` v1,
`PUT /api/v1/identidad/usuarios/{id}/tope-descuento` (spec `identidad/usuarios-y-roles`).

El tope propio reemplaza al del rol, sea mayor o menor; `null` vuelve a regir el del rol. Se
permite aunque el rol no tenga `DESCUENTO_MANUAL` (se guarda). Una fila de auditoría de entidad
con el valor anterior y el nuevo; el mismo valor se acepta sin auditoría de entidad.

Reglas citadas: DSC-06, AUD-01, TR-02, INV-03, INV-06, INV-21.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from usuarios_utiles import (
    URL_USUARIOS,
    EntornoUsuarios,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

CON_DESCUENTO = frozenset({"VENDER", "DESCUENTO_MANUAL"})


def _definir(entorno, cliente, quien, usuario_id, tope, operation_id=None):  # type: ignore[no-untyped-def]
    return entorno.enviar(
        cliente,
        "PUT",
        f"{URL_USUARIOS}/{usuario_id}/tope-descuento",
        quien,
        {"tope_descuento": tope},
        operation_id=operation_id,
    )


def _habilitar_descuento_manual(entorno: EntornoUsuarios) -> None:
    entorno.sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET descuento_manual_habilitado = true "
            "WHERE organizacion_id = :o"
        ),
        {"o": entorno.org},
    )
    entorno.sesion.commit()


def _tope_en_el_contexto(cliente: TestClient, abierta: Any) -> str | None:
    respuesta = cliente.get("/api/v1/ventas/contexto", headers=abierta.headers)
    assert respuesta.status_code == 200, respuesta.text
    tope = respuesta.json()["descuento_manual"]["tope"]
    return None if tope is None else str(tope)


def _con_tope_de_rol(
    entorno: EntornoUsuarios, tope_del_rol: str, permisos: frozenset[str] = CON_DESCUENTO
) -> tuple[UUID, str]:
    rol = entorno.crear_rol(f"Vendedor {uuid4().hex[:6]}", permisos)
    entorno.sesion.execute(
        text("UPDATE rol SET tope_descuento = :t WHERE id = :r"), {"t": tope_del_rol, "r": rol.id}
    )
    entorno.sesion.commit()
    return entorno.crear_usuario(rol)


def test_definir_el_tope_propio_rige_en_el_contexto_de_venta_y_deja_la_auditoria(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """DSC-06, AUD-01: de ningún tope propio (`null`) al 10 %."""
    entorno = EntornoUsuarios(sesion_real)
    _habilitar_descuento_manual(entorno)
    administrador = entorno.administrador(cliente_http)
    usuario_id, nombre = _con_tope_de_rol(entorno, "0.050000")
    del_usuario = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    assert _tope_en_el_contexto(cliente_http, del_usuario) == "0.050000"
    operation_id = uuid4()

    respuesta = _definir(entorno, cliente_http, administrador, usuario_id, "0.100000", operation_id)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["tope_descuento_override"] == "0.100000"
    assert _tope_en_el_contexto(cliente_http, del_usuario) == "0.100000"
    (auditoria,) = entorno.auditorias("TOPE_DESCUENTO_USUARIO", entidad_id=usuario_id)
    assert auditoria["origen"] == "COMANDO"
    assert auditoria["operation_id"] == operation_id
    assert auditoria["antes"] == {"tope_descuento_override": None}
    assert auditoria["despues"] == {"tope_descuento_override": "0.100000"}
    assert auditoria["usuario_id"] == administrador.usuario_id


def test_un_tope_propio_menor_que_el_del_rol_tambien_rige(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D12: puede ser mayor o menor que el del rol (`03` §4)."""
    entorno = EntornoUsuarios(sesion_real)
    _habilitar_descuento_manual(entorno)
    administrador = entorno.administrador(cliente_http)
    usuario_id, nombre = _con_tope_de_rol(entorno, "0.200000")
    del_usuario = entorno.abrir_sesion(cliente_http, usuario_id, nombre)

    assert _definir(entorno, cliente_http, administrador, usuario_id, "0.020000").status_code == 200

    assert _tope_en_el_contexto(cliente_http, del_usuario) == "0.020000"


def test_un_tope_propio_de_cero_es_un_tope_y_no_el_del_rol(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """Resolución del tope aplicable: el propio, aunque sea `0`, gana (`03` §4)."""
    entorno = EntornoUsuarios(sesion_real)
    _habilitar_descuento_manual(entorno)
    administrador = entorno.administrador(cliente_http)
    usuario_id, nombre = _con_tope_de_rol(entorno, "0.200000")
    del_usuario = entorno.abrir_sesion(cliente_http, usuario_id, nombre)

    assert _definir(entorno, cliente_http, administrador, usuario_id, "0").status_code == 200

    assert _tope_en_el_contexto(cliente_http, del_usuario) == "0.000000"
    assert entorno.usuario(usuario_id)["tope_descuento_override"] is not None


def test_quitar_el_tope_propio_con_null_vuelve_al_del_rol(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    _habilitar_descuento_manual(entorno)
    administrador = entorno.administrador(cliente_http)
    usuario_id, nombre = _con_tope_de_rol(entorno, "0.050000")
    del_usuario = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    _definir(entorno, cliente_http, administrador, usuario_id, "0.100000")

    respuesta = _definir(entorno, cliente_http, administrador, usuario_id, None)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["tope_descuento_override"] is None
    assert entorno.usuario(usuario_id)["tope_descuento_override"] is None
    assert _tope_en_el_contexto(cliente_http, del_usuario) == "0.050000"
    ultima = entorno.auditorias("TOPE_DESCUENTO_USUARIO", entidad_id=usuario_id)[-1]
    assert ultima["antes"] == {"tope_descuento_override": "0.100000"}
    assert ultima["despues"] == {"tope_descuento_override": None}


def test_un_usuario_sin_descuento_manual_en_su_rol_igual_lo_guarda(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D12: se permite aunque el rol no tenga `DESCUENTO_MANUAL` (la pantalla avisa que no tiene
    efecto mientras el rol no lo tenga)."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = _con_tope_de_rol(entorno, "0.000000", permisos=frozenset({"VENDER"}))

    respuesta = _definir(entorno, cliente_http, administrador, usuario_id, "0.150000")

    assert respuesta.status_code == 200, respuesta.text
    assert str(entorno.usuario(usuario_id)["tope_descuento_override"]) == "0.150000"


@pytest.mark.parametrize("tope", ["1.000001", "-0.010000", "0.1234567"])
def test_un_tope_fuera_de_rango_o_con_mas_de_seis_decimales_responde_422_y_no_cambia_nada(
    cliente_http: TestClient, sesion_real: Session, tope: str
) -> None:
    """TR-02, INV-03: de 0 a 1, hasta seis decimales, nunca redondeado en silencio."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = _con_tope_de_rol(entorno, "0.050000")

    respuesta = _definir(entorno, cliente_http, administrador, usuario_id, tope)

    assert respuesta.status_code == 422, respuesta.text
    assert entorno.usuario(usuario_id)["tope_descuento_override"] is None
    assert entorno.auditorias("TOPE_DESCUENTO_USUARIO") == []


@pytest.mark.parametrize("tope", ["abc", ""])
def test_un_texto_que_no_es_un_numero_responde_400_como_el_tope_del_rol(
    cliente_http: TestClient, sesion_real: Session, tope: str
) -> None:
    """INV-03: `EntradaNoEsDineroExactoError` (400), el mismo rechazo que
    `ROL_TOPE_DESCUENTO_DEFINIR` ("misma validación y código que el rol", D12)."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = _con_tope_de_rol(entorno, "0.050000")

    respuesta = _definir(entorno, cliente_http, administrador, usuario_id, tope)

    assert respuesta.status_code == 400, respuesta.text
    assert entorno.usuario(usuario_id)["tope_descuento_override"] is None
    assert entorno.auditorias("TOPE_DESCUENTO_USUARIO") == []


def test_un_numero_json_en_lugar_de_una_cadena_responde_422(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-03: un tope numérico no es válido."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = _con_tope_de_rol(entorno, "0.050000")

    respuesta = _definir(entorno, cliente_http, administrador, usuario_id, 0.1)

    assert respuesta.status_code == 422
    assert entorno.usuario(usuario_id)["tope_descuento_override"] is None


def test_el_mismo_valor_se_acepta_sin_auditoria_de_entidad(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = _con_tope_de_rol(entorno, "0.050000")
    assert _definir(entorno, cliente_http, administrador, usuario_id, "0.100000").status_code == 200

    repetido = _definir(entorno, cliente_http, administrador, usuario_id, "0.1")

    assert repetido.status_code == 200, repetido.text
    assert len(entorno.auditorias("TOPE_DESCUENTO_USUARIO")) == 1
    # Quitarlo cuando ya no hay tope propio tampoco audita.
    sin_tope, _ = _con_tope_de_rol(entorno, "0.050000")
    assert _definir(entorno, cliente_http, administrador, sin_tope, None).status_code == 200
    assert entorno.auditorias("TOPE_DESCUENTO_USUARIO", entidad_id=sin_tope) == []


def test_el_doble_envio_no_repite_la_auditoria(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = _con_tope_de_rol(entorno, "0.050000")
    operation_id = uuid4()

    primera = _definir(entorno, cliente_http, administrador, usuario_id, "0.100000", operation_id)
    segunda = _definir(entorno, cliente_http, administrador, usuario_id, "0.100000", operation_id)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    assert len(entorno.auditorias("TOPE_DESCUENTO_USUARIO")) == 1


def test_un_usuario_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21, SEG-07."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    ajeno_id, _ = _con_tope_de_rol(ajena, "0.050000")

    respuesta = _definir(propia, cliente_http, administrador, ajeno_id, "0.100000")

    assert respuesta.status_code == 404
    assert ajena.usuario(ajeno_id)["tope_descuento_override"] is None


def test_sin_el_permiso_responde_403(cliente_http: TestClient, sesion_real: Session) -> None:
    """SEG-06: nadie se sube el tope a sí mismo sin `ADMIN_USUARIOS`."""
    entorno = EntornoUsuarios(sesion_real)
    yo, nombre = _con_tope_de_rol(entorno, "0.050000")
    mi_sesion = entorno.abrir_sesion(cliente_http, yo, nombre)

    respuesta = _definir(entorno, cliente_http, mi_sesion, yo, "1.000000")

    assert respuesta.status_code == 403
    assert entorno.usuario(yo)["tope_descuento_override"] is None
