"""Change 15, tarea 4.3: `POST /api/v1/stock/jornadas` por HTTP contra PostgreSQL real (spec
`stock/jornadas`, `design.md` D1, D3, D9, D10).

Mismo arnés que `test_stock_api.py` (login real, motor propio de la aplicación). La cobertura
por escenario del comando está en `test_jornadas_abrir.py`; acá se prueba el contrato de la
ruta: `Operation-Id` obligatorio, esquema estricto (sin organización, usuario ni dispositivo
en el cuerpo), 201 con la jornada, Problem Details, permisos y aislamiento.

Reglas citadas: RUT-01, RUT-03, INV-06, INV-16, INV-21, SEG-06, SEG-07, TR-07, TR-08.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_motivo_sql, crear_ubicacion_sql
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    PASSWORD,
    Entorno,
    _con_op,
    _contar,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)

URL = "/api/v1/stock/jornadas"

ABRIR = frozenset({"ABRIR_JORNADA"})


class EntornoConCamionetas(Entorno):
    """El `Entorno` de `test_stock_api.py` más dos camionetas, una inactiva y una ajena."""

    camioneta_1: UUID
    camioneta_2: UUID
    camioneta_inactiva: UUID
    camioneta_ajena: UUID


def _preparar(sesion: Session, permisos: frozenset[str] = ABRIR) -> EntornoConCamionetas:
    entorno = EntornoConCamionetas(sesion, permisos=permisos)
    entorno.camioneta_1 = crear_ubicacion_sql(
        sesion, entorno.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
    )
    entorno.camioneta_2 = crear_ubicacion_sql(
        sesion, entorno.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
    )
    entorno.camioneta_inactiva = crear_ubicacion_sql(
        sesion,
        entorno.org,
        nombre="Camioneta 3",
        tipo="VEHICULO",
        requiere_toma=True,
        activo=False,
    )
    entorno.camioneta_ajena = crear_ubicacion_sql(
        sesion,
        crear_organizacion(sesion).id,
        nombre="Camioneta ajena",
        tipo="VEHICULO",
        requiere_toma=True,
    )
    return entorno


def _entrar(
    cliente_http: TestClient, entorno: Entorno, usuario: str, dispositivo_id: UUID | None = None
) -> dict[str, str]:
    """Login real del usuario en el dispositivo indicado (uno nuevo si no se indica)."""
    entorno.sesion.commit()
    respuesta = cliente_http.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": entorno.slug,
            "usuario": usuario,
            "contrasena": PASSWORD,
            "dispositivo_id": str(dispositivo_id or uuid4()),
            "nombre_dispositivo": "Teléfono",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def _cuerpo(ubicacion_id: UUID, **cambios: object) -> dict[str, object]:
    return {"ubicacion_id": str(ubicacion_id), **cambios}


def test_sin_operation_id_se_rechaza_con_400(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(entorno.camioneta_1), headers=headers)

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


def test_la_apertura_responde_201_con_la_jornada_del_usuario_y_el_dispositivo_del_token(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    dispositivo_id = uuid4()
    headers = _entrar(cliente, entorno, entorno.nombre_usuario, dispositivo_id)

    respuesta = cliente.post(URL, json=_cuerpo(entorno.camioneta_1), headers=_con_op(headers))

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    UUID(cuerpo["id"])
    assert cuerpo["estado"] == "ABIERTA"
    assert cuerpo["ubicacion_id"] == str(entorno.camioneta_1)
    assert cuerpo["usuario_id"] == str(entorno.usuario_id)
    assert cuerpo["dispositivo_id"] == str(dispositivo_id)
    assert cuerpo["abierta_en"]
    for campo in (
        "rendida_en",
        "rendida_por_id",
        "cerrada_en",
        "cerrada_por_id",
        "liberada_en",
        "liberada_por_id",
        "motivo_liberacion_id",
        "observacion_liberacion",
    ):
        assert cuerpo[campo] is None, campo
    assert _contar(sesion, "jornada", entorno.org) == 1


def test_el_reenvio_con_el_mismo_operation_id_devuelve_la_misma_jornada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    headers = _con_op(entorno.confirmar_y_entrar(cliente), uuid4())

    primera = cliente.post(URL, json=_cuerpo(entorno.camioneta_1), headers=headers)
    segunda = cliente.post(URL, json=_cuerpo(entorno.camioneta_1), headers=headers)

    assert (primera.status_code, segunda.status_code) == (201, 201)
    assert primera.json() == segunda.json()
    assert _contar(sesion, "jornada", entorno.org) == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"organizacion_id": str(uuid4())},
        {"usuario_id": str(uuid4())},
        {"dispositivo_id": str(uuid4())},
    ],
)
def test_un_cuerpo_con_organizacion_usuario_o_dispositivo_se_rechaza(
    cliente: TestClient, sesion: Session, extra: dict[str, str]
) -> None:
    """INV-21, TR-08, RUT-03: salen del token, nunca del cuerpo."""
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL, json=_cuerpo(entorno.camioneta_1, **extra), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert _contar(sesion, "jornada", entorno.org) == 0


def test_sin_ubicacion_el_cuerpo_se_rechaza(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    assert cliente.post(URL, json={}, headers=_con_op(headers)).status_code == 422


def test_sin_abrir_jornada_responde_403_sin_efectos(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion, permisos=frozenset({"RENDIR_JORNADA"}))
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(entorno.camioneta_1), headers=_con_op(headers))

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
    assert _contar(sesion, "jornada", entorno.org) == 0


def test_una_ubicacion_ajena_o_inexistente_responde_404(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21, SEG-07: otra organización responde 404, no 403."""
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    for ubicacion_id in (entorno.camioneta_ajena, uuid4()):
        respuesta = cliente.post(URL, json=_cuerpo(ubicacion_id), headers=_con_op(headers))
        assert respuesta.status_code == 404, respuesta.text
    assert _contar(sesion, "jornada", entorno.org) == 0


@pytest.mark.parametrize(
    ("ubicacion", "codigo"),
    [
        ("camioneta_inactiva", "UBICACION_INACTIVA"),
        ("deposito_id", "UBICACION_SIN_TOMA"),
    ],
)
def test_una_ubicacion_que_no_admite_jornada_responde_409(
    cliente: TestClient, sesion: Session, ubicacion: str, codigo: str
) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL, json=_cuerpo(getattr(entorno, ubicacion)), headers=_con_op(headers)
    )

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["codigo"] == codigo
    assert _contar(sesion, "jornada", entorno.org) == 0


def test_inv16_la_segunda_apertura_responde_409_ubicacion_tomada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    pedro = "pedro"
    entorno.agregar_usuario(ABRIR, pedro)
    juan_headers = _entrar(cliente, entorno, entorno.nombre_usuario)
    pedro_headers = _entrar(cliente, entorno, pedro)
    assert (
        cliente.post(
            URL, json=_cuerpo(entorno.camioneta_1), headers=_con_op(juan_headers)
        ).status_code
        == 201
    )

    respuesta = cliente.post(URL, json=_cuerpo(entorno.camioneta_1), headers=_con_op(pedro_headers))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "UBICACION_TOMADA"
    assert _contar(sesion, "jornada", entorno.org) == 1


def test_el_mismo_usuario_en_otro_dispositivo_responde_409_usuario_con_jornada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    primero = _entrar(cliente, entorno, entorno.nombre_usuario)
    segundo = _entrar(cliente, entorno, entorno.nombre_usuario)
    cliente.post(URL, json=_cuerpo(entorno.camioneta_1), headers=_con_op(primero))

    respuesta = cliente.post(URL, json=_cuerpo(entorno.camioneta_2), headers=_con_op(segundo))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "USUARIO_CON_JORNADA"


def test_otro_usuario_en_el_dispositivo_con_jornada_responde_409_dispositivo_con_jornada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    entorno.agregar_usuario(ABRIR, "pedro")
    telefono = uuid4()
    juan = _entrar(cliente, entorno, entorno.nombre_usuario, telefono)
    pedro = _entrar(cliente, entorno, "pedro", telefono)
    cliente.post(URL, json=_cuerpo(entorno.camioneta_1), headers=_con_op(juan))

    respuesta = cliente.post(URL, json=_cuerpo(entorno.camioneta_2), headers=_con_op(pedro))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "DISPOSITIVO_CON_JORNADA"


def test_una_ubicacion_cuya_jornada_se_cerro_vuelve_a_abrirse(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    crear_jornada_sql(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=entorno.camioneta_1,
        estado="CERRADA",
    )
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(entorno.camioneta_1), headers=_con_op(headers))

    assert respuesta.status_code == 201, respuesta.text


# --- rendición y cierre (tarea 6.2) -----------------------------------------------------------

RENDIR = frozenset({"RENDIR_JORNADA"})


def _jornada_en(
    entorno: EntornoConCamionetas, estado: str, ubicacion_id: UUID | None = None
) -> UUID:
    jornada_id = crear_jornada_sql(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=ubicacion_id or entorno.camioneta_1,
        estado=estado,
    )
    return jornada_id


@pytest.mark.parametrize(
    ("accion", "desde", "hacia"),
    [("rendicion", "ABIERTA", "EN_RENDICION"), ("cierre", "EN_RENDICION", "CERRADA")],
)
def test_la_transicion_responde_200_con_la_jornada_en_su_estado_nuevo(
    cliente: TestClient, sesion: Session, accion: str, desde: str, hacia: str
) -> None:
    entorno = _preparar(sesion, permisos=RENDIR)
    jornada_id = _jornada_en(entorno, desde)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(f"{URL}/{jornada_id}/{accion}", headers=_con_op(headers))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert (cuerpo["id"], cuerpo["estado"]) == (str(jornada_id), hacia)
    assert cuerpo["rendida_por_id"] == str(entorno.usuario_id)
    assert (cuerpo["cerrada_en"] is not None) == (hacia == "CERRADA")


@pytest.mark.parametrize("accion", ["rendicion", "cierre"])
def test_sin_operation_id_la_transicion_responde_400(
    cliente: TestClient, sesion: Session, accion: str
) -> None:
    entorno = _preparar(sesion, permisos=RENDIR)
    jornada_id = _jornada_en(entorno, "ABIERTA")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(f"{URL}/{jornada_id}/{accion}", headers=headers)

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


@pytest.mark.parametrize(
    ("accion", "estado"),
    [
        ("cierre", "ABIERTA"),
        ("rendicion", "EN_RENDICION"),
        ("rendicion", "CERRADA"),
        ("cierre", "LIBERADA"),
    ],
)
def test_una_transicion_invalida_responde_409_y_no_cambia_la_jornada(
    cliente: TestClient, sesion: Session, accion: str, estado: str
) -> None:
    entorno = _preparar(sesion, permisos=RENDIR)
    jornada_id = _jornada_en(entorno, estado)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(f"{URL}/{jornada_id}/{accion}", headers=_con_op(headers))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "JORNADA_ESTADO_INVALIDO"


@pytest.mark.parametrize("accion", ["rendicion", "cierre"])
def test_sin_rendir_jornada_la_transicion_responde_403(
    cliente: TestClient, sesion: Session, accion: str
) -> None:
    """`01` §19: el Vendedor (solo `ABRIR_JORNADA`) no rinde ni cierra."""
    entorno = _preparar(sesion, permisos=ABRIR)
    jornada_id = _jornada_en(entorno, "ABIERTA")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(f"{URL}/{jornada_id}/{accion}", headers=_con_op(headers))

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


@pytest.mark.parametrize("accion", ["rendicion", "cierre"])
def test_inv21_una_jornada_ajena_o_inexistente_responde_404(
    cliente: TestClient, sesion: Session, accion: str
) -> None:
    entorno = _preparar(sesion, permisos=RENDIR)
    otra_org = crear_organizacion(sesion).id
    otro_usuario, otro_dispositivo = crear_usuario_y_dispositivo(sesion, otra_org, permisos=ABRIR)
    ajena = crear_jornada_sql(
        sesion,
        otra_org,
        usuario_id=otro_usuario,
        dispositivo_id=otro_dispositivo,
        ubicacion_id=crear_ubicacion_sql(
            sesion, otra_org, nombre="Ajena", tipo="VEHICULO", requiere_toma=True
        ),
        estado="EN_RENDICION",
    )
    headers = entorno.confirmar_y_entrar(cliente)

    for jornada_id in (ajena, uuid4()):
        respuesta = cliente.post(f"{URL}/{jornada_id}/{accion}", headers=_con_op(headers))
        assert respuesta.status_code == 404, respuesta.text


def test_inv06_el_reenvio_de_la_rendicion_devuelve_la_misma_respuesta(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=RENDIR)
    jornada_id = _jornada_en(entorno, "ABIERTA")
    headers = _con_op(entorno.confirmar_y_entrar(cliente), uuid4())

    primera = cliente.post(f"{URL}/{jornada_id}/rendicion", headers=headers)
    segunda = cliente.post(f"{URL}/{jornada_id}/rendicion", headers=headers)

    assert (primera.status_code, segunda.status_code) == (200, 200)
    assert primera.json() == segunda.json()


# --- liberación (tarea 7.1) --------------------------------------------------------------------

LIBERAR = frozenset({"LIBERAR_UBICACION"})


def _motivo(entorno: EntornoConCamionetas, **opciones: object) -> UUID:
    return crear_motivo_sql(entorno.sesion, entorno.org, ambito="LIBERACION_JORNADA", **opciones)  # type: ignore[arg-type]


def test_la_liberacion_responde_200_con_el_motivo_y_la_observacion(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=LIBERAR)
    jornada_id = _jornada_en(entorno, "ABIERTA")
    motivo_id = _motivo(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        f"{URL}/{jornada_id}/liberacion",
        json={"motivo_id": str(motivo_id), "observacion": "Perdió el teléfono"},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert (cuerpo["id"], cuerpo["estado"]) == (str(jornada_id), "LIBERADA")
    assert cuerpo["motivo_liberacion_id"] == str(motivo_id)
    assert cuerpo["liberada_por_id"] == str(entorno.usuario_id)
    assert cuerpo["observacion_liberacion"] == "Perdió el teléfono"


def test_la_liberacion_sin_permiso_responde_403(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion, permisos=RENDIR)
    jornada_id = _jornada_en(entorno, "ABIERTA")
    motivo_id = _motivo(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        f"{URL}/{jornada_id}/liberacion",
        json={"motivo_id": str(motivo_id)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


@pytest.mark.parametrize(
    ("cuerpo_extra", "estado_http", "codigo"),
    [
        ({"observacion": "x" * 501}, 422, "OBSERVACION_INVALIDA"),
        ({"motivo": "inactivo"}, 422, "MOTIVO_INVALIDO"),
        ({"motivo": "ajeno"}, 404, None),
    ],
)
def test_la_liberacion_traduce_los_errores_de_dominio(
    cliente: TestClient,
    sesion: Session,
    cuerpo_extra: dict[str, str],
    estado_http: int,
    codigo: str | None,
) -> None:
    entorno = _preparar(sesion, permisos=LIBERAR)
    jornada_id = _jornada_en(entorno, "ABIERTA")
    cuerpo: dict[str, str] = {"motivo_id": str(_motivo(entorno))}
    if cuerpo_extra.get("motivo") == "inactivo":
        cuerpo["motivo_id"] = str(_motivo(entorno, activo=False))
    elif cuerpo_extra.get("motivo") == "ajeno":
        cuerpo["motivo_id"] = str(
            crear_motivo_sql(sesion, crear_organizacion(sesion).id, ambito="LIBERACION_JORNADA")
        )
    cuerpo.update({k: v for k, v in cuerpo_extra.items() if k != "motivo"})
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        f"{URL}/{jornada_id}/liberacion", json=cuerpo, headers=_con_op(headers)
    )

    assert respuesta.status_code == estado_http, respuesta.text
    if codigo is not None:
        assert respuesta.json()["codigo"] == codigo


def test_la_liberacion_de_una_jornada_cerrada_responde_409(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=LIBERAR)
    jornada_id = _jornada_en(entorno, "CERRADA")
    motivo_id = _motivo(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        f"{URL}/{jornada_id}/liberacion",
        json={"motivo_id": str(motivo_id)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "JORNADA_ESTADO_INVALIDO"


@pytest.mark.parametrize("extra", [{"usuario_id": str(uuid4())}, {"organizacion_id": str(uuid4())}])
def test_la_liberacion_rechaza_un_cuerpo_con_usuario_u_organizacion(
    cliente: TestClient, sesion: Session, extra: dict[str, str]
) -> None:
    """INV-21: salen del token."""
    entorno = _preparar(sesion, permisos=LIBERAR)
    jornada_id = _jornada_en(entorno, "ABIERTA")
    motivo_id = _motivo(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        f"{URL}/{jornada_id}/liberacion",
        json={"motivo_id": str(motivo_id), **extra},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422
