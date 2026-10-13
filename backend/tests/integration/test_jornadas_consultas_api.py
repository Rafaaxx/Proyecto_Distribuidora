"""Change 15, tarea 10.1: lecturas de jornadas por HTTP contra PostgreSQL real (spec
`stock/jornadas`, requisito "Las jornadas se consultan por organización"; `design.md` D15).

Permisos (aprobados por el usuario): el listado y el detalle los abre cualquiera de
`ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION`; `actual`, solo `ABRIR_JORNADA`.

Reglas citadas: RUT-01, RUT-09, ADR-005, TR-04, SEG-06, SEG-07, INV-21.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_motivo_sql, crear_ubicacion_sql
from test_jornadas_api import EntornoConCamionetas, _entrar, _preparar
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)

URL = "/api/v1/stock/jornadas"
LECTORES = [
    frozenset({"ABRIR_JORNADA"}),
    frozenset({"RENDIR_JORNADA"}),
    frozenset({"LIBERAR_UBICACION"}),
]


def _jornada(
    entorno: EntornoConCamionetas, ubicacion_id: UUID, estado: str, dia: int, **cambios: object
) -> UUID:
    return crear_jornada_sql(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=ubicacion_id,
        estado=estado,
        abierta_en=datetime(2026, 5, dia, 12, 0, tzinfo=UTC),
        **cambios,
    )


def _tres_jornadas(entorno: EntornoConCamionetas) -> tuple[UUID, UUID, UUID]:
    """Una `LIBERADA` el día 1, una `CERRADA` el día 2 y una `ABIERTA` el día 3."""
    return (
        _jornada(entorno, entorno.camioneta_1, "LIBERADA", 1),
        _jornada(entorno, entorno.camioneta_2, "CERRADA", 2),
        _jornada(entorno, entorno.camioneta_1, "ABIERTA", 3),
    )


def test_el_listado_trae_las_de_la_organizacion_de_la_mas_reciente_a_la_mas_antigua(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Listado de jornadas" (INV-21): la de otra organización no aparece."""
    entorno = _preparar(sesion, permisos=LECTORES[0])
    liberada, cerrada, abierta = _tres_jornadas(entorno)
    otra_org = crear_organizacion(sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(sesion, otra_org, permisos=LECTORES[0])
    ajena = crear_jornada_sql(
        sesion,
        otra_org,
        usuario_id=usuario,
        dispositivo_id=dispositivo,
        ubicacion_id=crear_ubicacion_sql(
            sesion, otra_org, nombre="Ajena", tipo="VEHICULO", requiere_toma=True
        ),
    )
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get(URL, headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert [fila["id"] for fila in cuerpo["items"]] == [str(abierta), str(cerrada), str(liberada)]
    assert str(ajena) not in {fila["id"] for fila in cuerpo["items"]}
    primera = cuerpo["items"][0]
    assert primera["ubicacion_id"] == str(entorno.camioneta_1)
    assert primera["ubicacion_nombre"] == "Camioneta 1"
    assert primera["usuario_id"] == str(entorno.usuario_id)
    assert primera["usuario_nombre"] == "Persona de prueba"
    assert primera["dispositivo_id"] == str(entorno.dispositivo_id)
    assert primera["estado"] == "ABIERTA"
    assert primera["abierta_en"]
    assert cuerpo["cursor_siguiente"] is None


@pytest.mark.parametrize("permisos", LECTORES, ids=["abrir", "rendir", "liberar"])
def test_cualquiera_de_los_tres_permisos_lee_el_listado_y_el_detalle(
    cliente: TestClient, sesion: Session, permisos: frozenset[str]
) -> None:
    entorno = _preparar(sesion, permisos=permisos)
    jornada_id = _jornada(entorno, entorno.camioneta_1, "ABIERTA", 3)
    headers = entorno.confirmar_y_entrar(cliente)

    assert cliente.get(URL, headers=headers).status_code == 200
    assert cliente.get(f"{URL}/{jornada_id}", headers=headers).status_code == 200


def test_sin_permisos_de_jornada_el_listado_el_detalle_y_actual_responden_403(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Usuario sin permisos de jornada" (SEG-06): el rol Consulta."""
    entorno = _preparar(sesion, permisos=frozenset({"TRANSFERIR_STOCK"}))
    jornada_id = _jornada(entorno, entorno.camioneta_1, "ABIERTA", 3)
    headers = entorno.confirmar_y_entrar(cliente)

    for url in (URL, f"{URL}/{jornada_id}", f"{URL}/actual"):
        respuesta = cliente.get(url, headers=headers)
        assert respuesta.status_code == 403, url
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def test_actual_exige_abrir_jornada_y_no_lo_abren_los_otros_dos_permisos(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=frozenset({"RENDIR_JORNADA", "LIBERAR_UBICACION"}))
    headers = entorno.confirmar_y_entrar(cliente)

    assert cliente.get(f"{URL}/actual", headers=headers).status_code == 403


def test_filtros_de_ubicacion_estado_y_usuario(cliente: TestClient, sesion: Session) -> None:
    """Escenario "Filtro por estado y ubicación"."""
    entorno = _preparar(sesion, permisos=LECTORES[0])
    liberada, _cerrada, abierta = _tres_jornadas(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    por_ubicacion_y_estado = cliente.get(
        URL,
        params={"ubicacion_id": str(entorno.camioneta_1), "estado": "ABIERTA"},
        headers=headers,
    ).json()
    por_ubicacion = cliente.get(
        URL, params={"ubicacion_id": str(entorno.camioneta_1)}, headers=headers
    ).json()
    por_otro_usuario = cliente.get(URL, params={"usuario_id": str(uuid4())}, headers=headers).json()
    por_usuario = cliente.get(
        URL, params={"usuario_id": str(entorno.usuario_id)}, headers=headers
    ).json()

    assert [f["id"] for f in por_ubicacion_y_estado["items"]] == [str(abierta)]
    assert [f["id"] for f in por_ubicacion["items"]] == [str(abierta), str(liberada)]
    assert por_otro_usuario["items"] == []
    assert len(por_usuario["items"]) == 3


def test_las_fechas_son_de_negocio(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion, permisos=LECTORES[0])
    liberada, cerrada, abierta = _tres_jornadas(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    desde = cliente.get(URL, params={"desde": "2026-05-02"}, headers=headers).json()
    entre = cliente.get(
        URL, params={"desde": "2026-05-02", "hasta": "2026-05-02"}, headers=headers
    ).json()

    assert [f["id"] for f in desde["items"]] == [str(abierta), str(cerrada)]
    assert [f["id"] for f in entre["items"]] == [str(cerrada)]
    assert liberada


def test_rango_invertido_cursor_ilegible_y_limite_fuera_de_rango(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=LECTORES[1])
    headers = entorno.confirmar_y_entrar(cliente)

    invertido = cliente.get(
        URL, params={"desde": "2026-05-10", "hasta": "2026-05-09"}, headers=headers
    )
    ilegible = cliente.get(URL, params={"cursor": "no-es-un-cursor"}, headers=headers)

    assert (invertido.status_code, invertido.json()["codigo"]) == (422, "RANGO_DE_FECHAS_INVALIDO")
    assert (ilegible.status_code, ilegible.json()["codigo"]) == (422, "CURSOR_INVALIDO")
    for limite in (0, 201):
        assert cliente.get(URL, params={"limite": limite}, headers=headers).status_code == 422


def test_paginacion_por_cursor(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion, permisos=LECTORES[0])
    liberada, cerrada, abierta = _tres_jornadas(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    primera = cliente.get(URL, params={"limite": 2}, headers=headers).json()
    segunda = cliente.get(
        URL, params={"limite": 2, "cursor": primera["cursor_siguiente"]}, headers=headers
    ).json()

    vistos = [f["id"] for f in primera["items"] + segunda["items"]]
    assert vistos == [str(abierta), str(cerrada), str(liberada)]
    assert primera["cursor_siguiente"] is not None and segunda["cursor_siguiente"] is None


def test_el_detalle_de_una_liberada_muestra_quien_cuando_motivo_y_observacion(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Detalle de una jornada liberada" (RUT-09)."""
    entorno = _preparar(sesion, permisos=LECTORES[2])
    motivo_id = crear_motivo_sql(
        sesion, entorno.org, ambito="LIBERACION_JORNADA", nombre="Vendedor ausente"
    )
    jornada_id = _jornada(
        entorno,
        entorno.camioneta_1,
        "LIBERADA",
        1,
        motivo_liberacion_id=motivo_id,
        observacion_liberacion="No se presentó",
    )
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get(f"{URL}/{jornada_id}", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert (cuerpo["id"], cuerpo["estado"]) == (str(jornada_id), "LIBERADA")
    assert cuerpo["liberada_por_id"] == str(entorno.usuario_id)
    assert cuerpo["liberada_por_nombre"] == "Persona de prueba"
    assert cuerpo["liberada_en"]
    assert cuerpo["motivo_liberacion_id"] == str(motivo_id)
    assert cuerpo["motivo_liberacion_nombre"] == "Vendedor ausente"
    assert cuerpo["observacion_liberacion"] == "No se presentó"
    assert cuerpo["ubicacion_nombre"] == "Camioneta 1"


def test_el_detalle_de_una_cerrada_muestra_la_rendicion_y_el_cierre(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=LECTORES[1])
    jornada_id = _jornada(entorno, entorno.camioneta_2, "CERRADA", 2)
    headers = entorno.confirmar_y_entrar(cliente)

    cuerpo = cliente.get(f"{URL}/{jornada_id}", headers=headers).json()

    assert cuerpo["rendida_en"] and cuerpo["cerrada_en"]
    assert cuerpo["rendida_por_nombre"] == cuerpo["cerrada_por_nombre"] == "Persona de prueba"
    assert cuerpo["liberada_en"] is None and cuerpo["motivo_liberacion_nombre"] is None


def test_inv21_el_detalle_de_una_jornada_ajena_o_inexistente_responde_404(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=LECTORES[0])
    otra_org = crear_organizacion(sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(sesion, otra_org, permisos=LECTORES[0])
    ajena = crear_jornada_sql(
        sesion,
        otra_org,
        usuario_id=usuario,
        dispositivo_id=dispositivo,
        ubicacion_id=crear_ubicacion_sql(
            sesion, otra_org, nombre="Ajena", tipo="VEHICULO", requiere_toma=True
        ),
    )
    headers = entorno.confirmar_y_entrar(cliente)

    for jornada_id in (ajena, uuid4()):
        assert cliente.get(f"{URL}/{jornada_id}", headers=headers).status_code == 404


@pytest.mark.parametrize("estado", ["ABIERTA", "EN_RENDICION"])
def test_actual_devuelve_la_jornada_del_usuario_y_del_dispositivo_del_token(
    cliente: TestClient, sesion: Session, estado: str
) -> None:
    """Escenario "Mi jornada actual" (RUT-01, ADR-005): desde V03 la devuelve; desde otro
    dispositivo, 404."""
    entorno = _preparar(sesion, permisos=LECTORES[0])
    telefono = uuid4()
    headers = _entrar(cliente, entorno, entorno.nombre_usuario, telefono)
    jornada_id = crear_jornada_sql(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=telefono,
        ubicacion_id=entorno.camioneta_1,
        estado=estado,
    )
    sesion.commit()
    otro_telefono = _entrar(cliente, entorno, entorno.nombre_usuario, uuid4())

    propia = cliente.get(f"{URL}/actual", headers=headers)
    ajena = cliente.get(f"{URL}/actual", headers=otro_telefono)

    assert propia.status_code == 200, propia.text
    assert (propia.json()["id"], propia.json()["estado"]) == (str(jornada_id), estado)
    assert ajena.status_code == 404


def test_actual_sin_jornada_no_cerrada_responde_404(cliente: TestClient, sesion: Session) -> None:
    """Una `CERRADA` o una `LIBERADA` no es "mi jornada actual"."""
    entorno = _preparar(sesion, permisos=LECTORES[0])
    telefono = uuid4()
    headers = _entrar(cliente, entorno, entorno.nombre_usuario, telefono)
    crear_jornada_sql(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=telefono,
        ubicacion_id=entorno.camioneta_1,
        estado="CERRADA",
    )
    sesion.commit()

    assert cliente.get(f"{URL}/actual", headers=headers).status_code == 404
