"""Change 17, tarea 10.1: `GET /api/v1/cobranzas` y `GET /api/v1/cobranzas/{id}` por HTTP.

Permiso aprobado por el usuario el 2026-10-16 (`design.md` D14, opción A): `REGISTRAR_COBRANZA`
o `ANULAR_COBRANZA`, y se ven todas las cobranzas de la organización. Mismo arnés que
`test_cobranzas_api.py` (PostgreSQL real, login real).

Reglas citadas: COB-01, COB-02, COB-05, INV-03, INV-21, SEG-06, SEG-07, SYN-07, TR-04.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_cobranzas_api`)

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_cobranzas_api import (  # noqa: F401
    ANULADOR,
    MOMENTO,
    PASSWORD,
    URL_COBRANZAS,
    Entorno,
    _con_op,
    _crear_motivo,
    _limpiar_datos_confirmados,
    _registrar,
    cliente_http,
    sesion,
)

from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.modules.identidad import repository as identidad_repository

SOLO_ANULA = frozenset({"ANULAR_COBRANZA"})
SIN_COBRANZAS = frozenset({"GESTIONAR_CLIENTES"})


def test_el_listado_trae_las_cobranzas_con_importes_como_string(
    cliente_http: TestClient, sesion: Session
) -> None:
    """COB-01, INV-03."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente_http)
    cobranza_id = _registrar(cliente_http, entorno, headers)

    respuesta = cliente_http.get(URL_COBRANZAS, headers=headers)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["cursor_siguiente"] is None
    (item,) = cuerpo["items"]
    assert item["cobranza_id"] == cobranza_id
    assert item["cliente_id"] == str(entorno.cliente_id)
    assert item["cliente_nombre"] == "Kiosco La Esquina"
    assert item["importe"] == "50000.00"
    assert item["estado"] == "CONFIRMADA"
    assert item["origen"] == "INDEPENDIENTE"
    assert item["usuario_nombre"]
    assert item["jornada_id"] is None


def test_con_solo_anular_cobranza_tambien_se_leen_todas(
    cliente_http: TestClient, sesion: Session
) -> None:
    """D14: `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA` alcanza (triangulación del permiso)."""
    cobrador = Entorno(sesion, permisos=ANULADOR)
    headers_cobrador = cobrador.entrar(cliente_http)
    cobranza_id = _registrar(cliente_http, cobrador, headers_cobrador)
    # Otro usuario de la MISMA organización que solo anula.
    _otro_usuario(sesion, cobrador, "anulador1", SOLO_ANULA)
    headers = _entrar(cliente_http, cobrador, "anulador1")

    lista = cliente_http.get(URL_COBRANZAS, headers=headers)
    detalle = cliente_http.get(f"{URL_COBRANZAS}/{cobranza_id}", headers=headers)

    assert [i["cobranza_id"] for i in lista.json()["items"]] == [cobranza_id]
    assert detalle.status_code == 200


def test_sin_permiso_de_cobranza_responde_403(cliente_http: TestClient, sesion: Session) -> None:
    """SEG-06."""
    entorno = Entorno(sesion, permisos=SIN_COBRANZAS)
    headers = entorno.entrar(cliente_http)

    assert cliente_http.get(URL_COBRANZAS, headers=headers).status_code == 403
    assert cliente_http.get(f"{URL_COBRANZAS}/{uuid4()}", headers=headers).status_code == 403


def test_sin_sesion_responde_401(cliente_http: TestClient) -> None:
    assert cliente_http.get(URL_COBRANZAS).status_code == 401


def test_un_limite_fuera_de_rango_o_un_cursor_ilegible_responde_422(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente_http)

    assert cliente_http.get(f"{URL_COBRANZAS}?limite=0", headers=headers).status_code == 422
    assert cliente_http.get(f"{URL_COBRANZAS}?limite=201", headers=headers).status_code == 422
    ilegible = cliente_http.get(f"{URL_COBRANZAS}?cursor=xx", headers=headers)
    assert ilegible.status_code == 422
    assert ilegible.json()["codigo"] == "CURSOR_INVALIDO"
    invertido = cliente_http.get(
        f"{URL_COBRANZAS}?desde=2026-10-10&hasta=2026-10-01", headers=headers
    )
    assert invertido.status_code == 422
    assert invertido.json()["codigo"] == "RANGO_DE_FECHAS_INVALIDO"
    estado = cliente_http.get(f"{URL_COBRANZAS}?estado=BORRADA", headers=headers)
    assert estado.status_code == 422


def test_la_pagina_devuelve_cursor_y_la_siguiente_completa_el_listado(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente_http)
    creadas = {_registrar(cliente_http, entorno, headers) for _ in range(3)}

    primera = cliente_http.get(f"{URL_COBRANZAS}?limite=2", headers=headers).json()
    segunda = cliente_http.get(
        f"{URL_COBRANZAS}?limite=2&cursor={primera['cursor_siguiente']}", headers=headers
    ).json()

    vistas = [i["cobranza_id"] for i in primera["items"] + segunda["items"]]
    assert len(vistas) == 3 and set(vistas) == creadas
    assert segunda["cursor_siguiente"] is None


def test_el_detalle_trae_medios_anulacion_y_observaciones(
    cliente_http: TestClient, sesion: Session
) -> None:
    """COB-02, COB-05, SYN-07: medios con nombre, anulación con motivo y observaciones."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    motivo = _crear_motivo(sesion, entorno.org)
    headers = entorno.entrar(cliente_http)
    cobranza_id = _registrar(cliente_http, entorno, headers)

    confirmada = cliente_http.get(f"{URL_COBRANZAS}/{cobranza_id}", headers=headers).json()
    cliente_http.post(
        f"{URL_COBRANZAS}/{cobranza_id}/anulacion",
        json={"motivo_id": str(motivo), "observacion": "cheque sin fondos"},
        headers=_con_op(headers),
    )
    anulada = cliente_http.get(f"{URL_COBRANZAS}/{cobranza_id}", headers=headers).json()

    assert [(m["medio_nombre"], m["importe"], m["referencia"]) for m in confirmada["medios"]] == [
        ("Efectivo", "30000.00", None),
        ("Transferencia", "20000.00", "0042"),
    ]
    assert confirmada["anulacion"] is None
    assert confirmada["observaciones"] == []
    assert anulada["estado"] == "ANULADA"
    assert anulada["anulacion"]["observacion"] == "cheque sin fondos"
    assert anulada["anulacion"]["motivo_id"] == str(motivo)
    assert anulada["anulacion"]["usuario_nombre"]


def test_el_detalle_muestra_las_observaciones_de_sincronizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    """SYN-07: una observación guardada para la cobranza aparece en su detalle."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente_http)
    cobranza_id = _registrar(cliente_http, entorno, headers)
    comando_id = sesion.execute(
        text("SELECT id FROM comando WHERE organizacion_id = :o"), {"o": entorno.org}
    ).scalar_one()
    sesion.execute(
        text(
            "INSERT INTO observacion (id, organizacion_id, comando_id, operacion_tipo, "
            "operacion_id, codigo, detalle, estado) VALUES (:id, :o, :c, 'COBRANZA', :op, "
            "'MEDIO_INACTIVO', CAST(:d AS jsonb), 'PENDIENTE')"
        ),
        {
            "id": uuid4(),
            "o": entorno.org,
            "c": comando_id,
            "op": cobranza_id,
            "d": '{"linea": 1, "importe": "20000.00"}',
        },
    )
    sesion.commit()

    detalle = cliente_http.get(f"{URL_COBRANZAS}/{cobranza_id}", headers=headers).json()

    (observacion,) = detalle["observaciones"]
    assert observacion["codigo"] == "MEDIO_INACTIVO"
    assert observacion["estado"] == "PENDIENTE"
    assert observacion["detalle"] == {"linea": 1, "importe": "20000.00"}


def test_inv21_el_detalle_y_el_listado_no_cruzan_organizaciones(
    cliente_http: TestClient, sesion: Session
) -> None:
    """INV-21, SEG-07: la cobranza de otra organización responde 404 como una inexistente."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    ajeno = Entorno(sesion, permisos=ANULADOR, usuario="otro1")
    headers_ajeno = ajeno.entrar(cliente_http)
    cobranza_ajena = _registrar(cliente_http, ajeno, headers_ajeno)
    headers = entorno.entrar(cliente_http)

    detalle = cliente_http.get(f"{URL_COBRANZAS}/{cobranza_ajena}", headers=headers)
    inexistente = cliente_http.get(f"{URL_COBRANZAS}/{uuid4()}", headers=headers)
    lista = cliente_http.get(URL_COBRANZAS, headers=headers)

    assert detalle.status_code == 404
    assert inexistente.status_code == 404
    assert lista.json()["items"] == []


def _otro_usuario(
    sesion: Session, entorno: Entorno, usuario: str, permisos: frozenset[str]
) -> None:
    """Un segundo usuario de la misma organización con otros permisos."""
    rol = identidad_repository.crear_rol(
        entorno.org,
        sesion,
        rol_id=nuevo_id(),
        nombre=f"Rol {usuario}",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    for codigo in permisos:
        identidad_repository.asignar_permiso_a_rol(
            entorno.org, sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    identidad_repository.crear_usuario(
        entorno.org,
        sesion,
        usuario_id=nuevo_id(),
        usuario=usuario,
        nombre="Persona anuladora",
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    sesion.commit()


def _entrar(cliente_http: TestClient, entorno: Entorno, usuario: str) -> dict[str, str]:
    respuesta = cliente_http.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": entorno.slug,
            "usuario": usuario,
            "contrasena": PASSWORD,
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "PC",
        },
    )
    assert respuesta.status_code == 200
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}
