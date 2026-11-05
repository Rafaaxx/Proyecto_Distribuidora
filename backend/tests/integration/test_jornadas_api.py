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

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_jornada_sql,
    crear_motivo_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)
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

MOMENTO = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def _jornada_en(
    entorno: EntornoConCamionetas,
    estado: str,
    ubicacion_id: UUID | None = None,
    *,
    entregada: bool = True,
) -> UUID:
    """La jornada entregada por defecto: desde el change 24 la rendición exige la entrega."""
    entrega: dict[str, object] = (
        {"entregada_en": MOMENTO, "entrega_occurred_at": MOMENTO, "entrega_secuencia": 1}
        if entregada
        else {}
    )
    jornada_id = crear_jornada_sql(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=ubicacion_id or entorno.camioneta_1,
        estado=estado,
        **entrega,
    )
    return jornada_id


def _transicion(
    cliente: TestClient, jornada_id: UUID, accion: str, headers: dict[str, str]
) -> Response:
    """La rendición (v2) lleva el conteo; el cierre no lleva cuerpo."""
    if accion == "rendicion":
        return cliente.post(f"{URL}/{jornada_id}/rendicion", json={"lineas": []}, headers=headers)
    return cliente.post(f"{URL}/{jornada_id}/{accion}", headers=headers)


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

    respuesta = _transicion(cliente, jornada_id, accion, _con_op(headers))

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

    respuesta = _transicion(cliente, jornada_id, accion, headers)

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

    respuesta = _transicion(cliente, jornada_id, accion, _con_op(headers))

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

    respuesta = _transicion(cliente, jornada_id, accion, _con_op(headers))

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
        respuesta = _transicion(cliente, jornada_id, accion, _con_op(headers))
        assert respuesta.status_code == 404, respuesta.text


def test_inv06_el_reenvio_de_la_rendicion_devuelve_la_misma_respuesta(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=RENDIR)
    jornada_id = _jornada_en(entorno, "ABIERTA")
    headers = _con_op(entorno.confirmar_y_entrar(cliente), uuid4())

    primera = _transicion(cliente, jornada_id, "rendicion", headers)
    segunda = _transicion(cliente, jornada_id, "rendicion", headers)

    assert (primera.status_code, segunda.status_code) == (200, 200)
    assert primera.json() == segunda.json()


def test_la_rendicion_responde_con_la_rendicion_y_sus_lineas(
    cliente: TestClient, sesion: Session
) -> None:
    """Change 24, D2: 200 con la jornada `EN_RENDICION`, el id de la rendición y las líneas del
    conteo (sin costos)."""
    entorno = _preparar(sesion, permisos=RENDIR)
    jornada_id = _jornada_en(entorno, "ABIERTA")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        f"{URL}/{jornada_id}/rendicion",
        json={"lineas": [], "observacion": "Sin novedades"},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert (cuerpo["id"], cuerpo["estado"]) == (str(jornada_id), "EN_RENDICION")
    assert (cuerpo["observacion"], cuerpo["lineas"]) == ("Sin novedades", [])
    assert UUID(cuerpo["rendicion_id"])


def test_la_rendicion_sin_la_entrega_responde_409(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion, permisos=RENDIR)
    jornada_id = _jornada_en(entorno, "ABIERTA", entregada=False)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = _transicion(cliente, jornada_id, "rendicion", _con_op(headers))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "JORNADA_SIN_ENTREGA"


def test_la_rendicion_sin_conteo_en_el_cuerpo_responde_422(
    cliente: TestClient, sesion: Session
) -> None:
    """Nadie rinde sin contar: el cuerpo vacío ya no es una rendición."""
    entorno = _preparar(sesion, permisos=RENDIR)
    jornada_id = _jornada_en(entorno, "ABIERTA")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(f"{URL}/{jornada_id}/rendicion", headers=_con_op(headers))

    assert respuesta.status_code == 422


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


# --- cierre con el remanente (change 24, tarea 9.1; RUT-08, D6) --------------------------------

RENDIR_Y_TRANSFERIR = frozenset({"RENDIR_JORNADA", "TRANSFERIR_STOCK"})


def _cuerpo_de_devolucion(destino: UUID, producto: UUID, cantidad: int) -> dict[str, object]:
    return {
        "devolucion": {
            "ubicacion_destino_id": str(destino),
            "lineas": [{"producto_id": str(producto), "cantidad_base": cantidad}],
        }
    }


def test_el_cierre_sin_cuerpo_responde_200_sin_transferencia(
    cliente: TestClient, sesion: Session
) -> None:
    """Spec "Cerrar sin devolver": el cuerpo es opcional y `transferencia_id` es nulo."""
    entorno = _preparar(sesion, permisos=RENDIR)
    jornada_id = _jornada_en(entorno, "EN_RENDICION")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(f"{URL}/{jornada_id}/cierre", headers=_con_op(headers))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "CERRADA"
    assert respuesta.json()["transferencia_id"] is None


def test_la_devolucion_sin_transferir_stock_responde_403(
    cliente: TestClient, sesion: Session
) -> None:
    """Spec "Devolución sin permiso de transferir" (`01` §19)."""
    entorno = _preparar(sesion, permisos=RENDIR)
    deposito = crear_ubicacion_sql(sesion, entorno.org, nombre="Depósito de devolución")
    producto = crear_producto_sql(sesion, entorno.org, nombre="Vino A")
    jornada_id = _jornada_en(entorno, "EN_RENDICION")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        f"{URL}/{jornada_id}/cierre",
        json=_cuerpo_de_devolucion(deposito, producto, 1),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


@pytest.mark.parametrize(
    ("destino", "codigo", "estado_http"),
    [
        ("camioneta_2", "UBICACION_CON_TOMA", 409),
        ("camioneta_1", "UBICACIONES_IGUALES", 422),
        ("deposito", "STOCK_INSUFICIENTE", 409),
    ],
)
def test_la_devolucion_rechazada_responde_con_su_codigo_y_no_cierra(
    cliente: TestClient, sesion: Session, destino: str, codigo: str, estado_http: int
) -> None:
    entorno = _preparar(sesion, permisos=RENDIR_Y_TRANSFERIR)
    entorno.deposito = crear_ubicacion_sql(sesion, entorno.org, nombre="Depósito de devolución")  # type: ignore[attr-defined]
    producto = crear_producto_sql(sesion, entorno.org, nombre="Vino A")
    jornada_id = _jornada_en(entorno, "EN_RENDICION")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        f"{URL}/{jornada_id}/cierre",
        json=_cuerpo_de_devolucion(getattr(entorno, destino), producto, 5),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == estado_http, respuesta.text
    assert respuesta.json()["codigo"] == codigo
    detalle = cliente.get(f"{URL}/{jornada_id}", headers=headers)
    assert detalle.json()["estado"] == "EN_RENDICION"


# --- el detalle informa la entrega (change 24, tarea 13.1; RUT-05, D9) --------------------------


@pytest.mark.parametrize("entregada", [True, False])
def test_el_detalle_informa_el_momento_de_la_entrega_o_su_falta(
    cliente: TestClient, sesion: Session, entregada: bool
) -> None:
    """RUT-05: el detalle de `/admin` muestra «Entregada ... a las {hora}» o que el vendedor
    todavía no terminó el día; el momento es el del servidor (`entregada_en`)."""
    entorno = _preparar(sesion, permisos=RENDIR)
    jornada_id = _jornada_en(entorno, "ABIERTA", entregada=entregada)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get(f"{URL}/{jornada_id}", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    esperado = MOMENTO.isoformat().replace("+00:00", "Z") if entregada else None
    assert respuesta.json()["entregada_en"] == esperado


# --- el resumen de la jornada (change 24, tarea 10.1; RUT-07, D4) ------------------------------


@pytest.mark.parametrize("permiso", ["ABRIR_JORNADA", "RENDIR_JORNADA", "LIBERAR_UBICACION"])
def test_el_resumen_responde_200_con_cualquiera_de_los_tres_permisos(
    cliente: TestClient, sesion: Session, permiso: str
) -> None:
    entorno = _preparar(sesion, permisos=frozenset({permiso}))
    jornada_id = _jornada_en(entorno, "ABIERTA")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get(f"{URL}/{jornada_id}/resumen", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["jornada_id"] == str(jornada_id)
    assert cuerpo["con_conteo"] is False
    assert cuerpo["dinero"]["ventas"] == {"cantidad": 0, "total": "0.00"}
    assert cuerpo["despues_de_la_rendicion"] is None
    assert "valor_de_diferencias" not in cuerpo


def test_el_resumen_sin_permisos_de_jornada_responde_403(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=frozenset({"VER_COSTOS"}))
    jornada_id = _jornada_en(entorno, "ABIERTA")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get(f"{URL}/{jornada_id}/resumen", headers=headers)

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def _rendicion_con_faltante(entorno: EntornoConCamionetas, jornada_id: UUID) -> UUID:
    """Una rendición por SQL con 40 esperadas de Vino A, 37 contadas (-3) a $1.050."""
    producto = crear_producto_sql(entorno.sesion, entorno.org, nombre="Vino A")
    rendicion_id = uuid4()
    entorno.sesion.execute(
        text(
            "INSERT INTO rendicion (id, organizacion_id, jornada_id, operation_id, usuario_id, "
            "dispositivo_id, occurred_at, registered_at) VALUES (:id, :org, :j, :op, :u, :d, "
            ":m, :m)"
        ),
        {
            "id": rendicion_id,
            "org": entorno.org,
            "j": jornada_id,
            "op": uuid4(),
            "u": entorno.usuario_id,
            "d": entorno.dispositivo_id,
            "m": MOMENTO,
        },
    )
    entorno.sesion.execute(
        text(
            "INSERT INTO rendicion_linea (id, organizacion_id, rendicion_id, producto_id, "
            "stock_al_abrir, ingresos, ventas, anulaciones, otros, cantidad_esperada, "
            "cantidad_contada, diferencia, costo_unitario) VALUES (:id, :org, :r, :p, 10, 36, "
            "8, 2, 0, 40, 37, -3, 1050.000000)"
        ),
        {"id": uuid4(), "org": entorno.org, "r": rendicion_id, "p": producto},
    )
    return producto


def test_el_valor_de_las_diferencias_viaja_como_string_solo_con_ver_costos(
    cliente: TestClient, sesion: Session
) -> None:
    """`01` §19: con `VER_COSTOS` la clave existe (string, INV-03); sin él desaparece."""
    con = _preparar(sesion, permisos=frozenset({"RENDIR_JORNADA", "VER_COSTOS"}))
    jornada_con = _jornada_en(con, "EN_RENDICION")
    _rendicion_con_faltante(con, jornada_con)
    headers_con = con.confirmar_y_entrar(cliente)
    sin = _preparar(sesion, permisos=RENDIR)
    jornada_sin = _jornada_en(sin, "EN_RENDICION")
    _rendicion_con_faltante(sin, jornada_sin)
    headers_sin = sin.confirmar_y_entrar(cliente)

    cuerpo_con = cliente.get(f"{URL}/{jornada_con}/resumen", headers=headers_con).json()
    cuerpo_sin = cliente.get(f"{URL}/{jornada_sin}/resumen", headers=headers_sin).json()

    assert cuerpo_con["con_conteo"] is True
    assert cuerpo_con["valor_de_diferencias"] == "-3150.00"
    (linea,) = cuerpo_con["lineas"]
    assert (linea["esperado"], linea["contado"], linea["diferencia"]) == (40, 37, -3)
    assert linea["valor_diferencia"] == "-3150.00"
    assert "valor_de_diferencias" not in cuerpo_sin
    assert "valor_diferencia" not in cuerpo_sin["lineas"][0]
    assert cuerpo_sin["lineas"][0]["diferencia"] == -3


def test_inv21_el_resumen_de_una_jornada_ajena_o_inexistente_responde_404(
    cliente: TestClient, sesion: Session
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
    )
    headers = entorno.confirmar_y_entrar(cliente)

    for jornada_id in (ajena, uuid4()):
        respuesta = cliente.get(f"{URL}/{jornada_id}/resumen", headers=headers)
        assert respuesta.status_code == 404, respuesta.text
