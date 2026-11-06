"""Change 25, tarea 8.1: `RECHAZO_RESOLVER` por HTTP contra PostgreSQL real (spec
`sync/rechazos-sin-conexion`, requisito "Un rechazo se resuelve con comentario y, si ocurrió, con su
corrección", y spec `sync/cuarentena-de-comandos`; `design.md` D7).

Resolver NO reenvía ni crea nada: la corrección es una operación nueva, cargada con conexión, y se
vincula. La concurrencia (dos resoluciones a la vez) se prueba en el Lote 7 con commits reales.

Reglas citadas: SYN-06, SYN-08, INV-01, INV-05, INV-06, INV-21, SEG-06.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from fastapi.testclient import TestClient
from revision_utiles import sembrar_cuarentena, sembrar_rechazo
from sqlalchemy import Engine, text, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    Entorno,
    _con_op,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)
from ventas_utiles import insertar_sql, sembrar_venta_sql

from app.core.clock import FixedClock
from app.modules.identidad import service as identidad_service
from app.modules.sync import service as sync_service
from app.modules.sync.models import ComandoCuarentena
from app.modules.sync.service import ItemLote

REVISOR = frozenset({"REVISAR_OBSERVACIONES"})
COMENTARIO = "Se cargó con conexión"
MOMENTO = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def _url(rechazo_id: UUID) -> str:
    return f"/api/v1/observaciones/rechazos/{rechazo_id}/resolucion"


def _cuerpo(
    origen: str = "RECHAZO",
    comentario: str = COMENTARIO,
    vinculo: tuple[str, UUID] | None = None,
) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {"origen": origen, "comentario": comentario}
    if vinculo is not None:
        cuerpo["vinculo"] = {"tipo": vinculo[0], "id": str(vinculo[1])}
    return cuerpo


def _rechazo(entorno: Entorno, **cambios: Any) -> UUID:
    return sembrar_rechazo(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        **cambios,
    )


def _venta(entorno: Entorno, **cambios: object) -> UUID:
    cliente_id = crear_cliente(entorno.sesion, entorno.org, nombre="Kiosco La Esquina")
    return sembrar_venta_sql(
        entorno.sesion,
        entorno.org,
        cliente_id=cliente_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        **cambios,
    ).venta_id


def _cobranza(entorno: Entorno, organizacion_id: UUID | None = None) -> UUID:
    cobranza_id = uuid4()
    org = organizacion_id or entorno.org
    insertar_sql(
        entorno.sesion,
        "cobranza",
        {
            "id": cobranza_id,
            "organizacion_id": org,
            "cliente_id": crear_cliente(entorno.sesion, org, nombre="Almacén Don Pedro"),
            "origen": "INDEPENDIENTE",
            "importe": "50000.00",
            "estado": "CONFIRMADA",
            "operation_id": uuid4(),
            "usuario_id": entorno.usuario_id,
            "dispositivo_id": entorno.dispositivo_id,
            "occurred_at": MOMENTO,
            "registered_at": MOMENTO,
        },
    )
    return cobranza_id


def _fila(sesion: Session, tabla: str, id_: UUID) -> Any:
    sesion.rollback()
    return sesion.execute(text(f"SELECT * FROM {tabla} WHERE id = :i"), {"i": id_}).one()  # noqa: S608


def _foto_de_lo_que_no_se_toca(sesion: Session, organizacion_id: UUID) -> object:
    """Resolver no crea ni cambia ninguna operación, comando ni libro."""
    sesion.rollback()
    return [
        sesion.scalar(
            text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"),  # noqa: S608
            {"o": organizacion_id},
        )
        for tabla in (
            "venta",
            "cobranza",
            "stock_movimiento",
            "cuenta_movimiento",
            "costo_producto_mov",
        )
    ] + [
        sesion.execute(
            text(
                "SELECT id, estado FROM comando WHERE organizacion_id = :o "
                "AND tipo <> 'RECHAZO_RESOLVER' ORDER BY id"
            ),
            {"o": organizacion_id},
        ).all()
    ]


# --- rechazos -----------------------------------------------------------------------------


def test_syn08_una_venta_rechazada_se_resuelve_vinculandola_sin_crear_ni_cambiar_nada(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Venta rechazada corregida con conexión"."""
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(entorno)
    venta_id = _venta(entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    antes = _foto_de_lo_que_no_se_toca(sesion, entorno.org)

    respuesta = cliente.post(
        _url(rechazo_id), json=_cuerpo(vinculo=("VENTA", venta_id)), headers=_con_op(headers)
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert (cuerpo["id"], cuerpo["origen"], cuerpo["estado"]) == (
        str(rechazo_id),
        "RECHAZO",
        "RESUELTO",
    )
    assert (cuerpo["comentario"], cuerpo["vinculo_tipo"], cuerpo["vinculo_id"]) == (
        COMENTARIO,
        "VENTA",
        str(venta_id),
    )
    fila = _fila(sesion, "comando_rechazado", rechazo_id)
    assert fila.estado == "RESUELTO"
    assert fila.resuelto_por_id == entorno.usuario_id
    assert fila.resuelto_en is not None
    assert (fila.comentario, fila.vinculo_tipo, fila.vinculo_id) == (
        "Se cargó con conexión",
        "VENTA",
        venta_id,
    )
    assert fila.error_codigo == "TOTALES_INCONSISTENTES"
    assert _foto_de_lo_que_no_se_toca(sesion, entorno.org) == antes


def test_syn08_una_venta_que_no_ocurrio_se_resuelve_sin_vinculo(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "La venta no ocurrió"."""
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        _url(rechazo_id),
        json=_cuerpo(comentario="  El cliente devolvió la mercadería  "),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200, respuesta.text
    fila = _fila(sesion, "comando_rechazado", rechazo_id)
    assert (fila.estado, fila.vinculo_tipo, fila.vinculo_id) == ("RESUELTO", None, None)
    assert fila.comentario == "El cliente devolvió la mercadería"


def test_syn08_una_cobranza_rechazada_se_vincula_a_una_cobranza(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(
        entorno, tipo="COBRANZA_REGISTRAR", error_codigo="MEDIOS_NO_SUMAN_IMPORTE"
    )
    cobranza_id = _cobranza(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        _url(rechazo_id),
        json=_cuerpo(vinculo=("COBRANZA", cobranza_id)),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200, respuesta.text
    fila = _fila(sesion, "comando_rechazado", rechazo_id)
    assert (fila.vinculo_tipo, fila.vinculo_id) == ("COBRANZA", cobranza_id)


def test_syn08_una_anulacion_rechazada_se_resuelve_solo_con_comentario(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Anulación rechazada": sin vínculo (decisión del 2026-11-06)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(entorno, tipo="VENTA_ANULAR", error_codigo="VENTA_YA_ANULADA")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(_url(rechazo_id), json=_cuerpo(), headers=_con_op(headers))

    assert respuesta.status_code == 200, respuesta.text
    fila = _fila(sesion, "comando_rechazado", rechazo_id)
    assert (fila.estado, fila.vinculo_tipo, fila.vinculo_id) == ("RESUELTO", None, None)


@pytest.mark.parametrize(
    ("tipo_de_comando", "vinculo_tipo", "que_es"),
    [
        ("COBRANZA_REGISTRAR", "VENTA", "cobranza vinculada a una venta"),
        ("VENTA_CONFIRMAR", "COBRANZA", "venta vinculada a una cobranza"),
        ("VENTA_ANULAR", "VENTA", "la anulación rechazada no admite vínculo"),
        ("JORNADA_ENTREGAR", "VENTA", "entrega del día no admite vínculo"),
    ],
)
def test_syn08_un_vinculo_que_no_corresponde_es_vinculo_invalido_y_nada_cambia(
    cliente: TestClient, sesion: Session, tipo_de_comando: str, vinculo_tipo: str, que_es: str
) -> None:
    """Escenario "Vínculo de otro tipo" ({que_es})."""
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(entorno, tipo=tipo_de_comando, error_codigo="JORNADA_INEXISTENTE")
    vinculado = _cobranza(entorno) if vinculo_tipo == "COBRANZA" else _venta(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        _url(rechazo_id),
        json=_cuerpo(vinculo=(vinculo_tipo, vinculado)),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["codigo"] == "VINCULO_INVALIDO"
    assert _fila(sesion, "comando_rechazado", rechazo_id).estado == "PENDIENTE"


def test_inv21_un_vinculo_inexistente_o_de_otra_organizacion_responde_404(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Vínculo inexistente o ajeno"."""
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(entorno)
    otra = crear_organizacion(sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(sesion, otra)
    venta_ajena = sembrar_venta_sql(
        sesion,
        otra,
        cliente_id=crear_cliente(sesion, otra, nombre="Ajeno"),
        usuario_id=usuario,
        dispositivo_id=dispositivo,
    ).venta_id
    headers = entorno.confirmar_y_entrar(cliente)

    for id_ in (uuid4(), venta_ajena):
        respuesta = cliente.post(
            _url(rechazo_id), json=_cuerpo(vinculo=("VENTA", id_)), headers=_con_op(headers)
        )

        assert respuesta.status_code == 404, respuesta.text
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert _fila(sesion, "comando_rechazado", rechazo_id).estado == "PENDIENTE"


def test_01_18_un_rechazo_ya_resuelto_no_se_resuelve_otra_vez(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Ya resuelto": con otro `operation_id`, `RECHAZO_YA_RESUELTO` (409) y la primera
    resolución no cambia."""
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    primera = cliente.post(_url(rechazo_id), json=_cuerpo(), headers=_con_op(headers))
    assert primera.status_code == 200, primera.text

    segunda = cliente.post(
        _url(rechazo_id), json=_cuerpo(comentario="Otra vez"), headers=_con_op(headers)
    )

    assert segunda.status_code == 409
    assert segunda.json()["codigo"] == "RECHAZO_YA_RESUELTO"
    assert _fila(sesion, "comando_rechazado", rechazo_id).comentario == COMENTARIO


def test_inv21_un_rechazo_de_otra_organizacion_o_inexistente_responde_404(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    otra = crear_organizacion(sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(sesion, otra)
    ajeno = sembrar_rechazo(sesion, otra, usuario_id=usuario, dispositivo_id=dispositivo)
    headers = entorno.confirmar_y_entrar(cliente)

    for id_ in (ajeno, uuid4()):
        respuesta = cliente.post(_url(id_), json=_cuerpo(), headers=_con_op(headers))

        assert respuesta.status_code == 404, respuesta.text
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert _fila(sesion, "comando_rechazado", ajeno).estado == "PENDIENTE"


def test_seg06_sin_el_permiso_responde_403_y_nada_cambia(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Sin permiso": el Vendedor no tiene `REVISAR_OBSERVACIONES`."""
    entorno = Entorno(sesion, permisos=frozenset({"VENDER"}))
    rechazo_id = _rechazo(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(_url(rechazo_id), json=_cuerpo(), headers=_con_op(headers))

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
    assert _fila(sesion, "comando_rechazado", rechazo_id).estado == "PENDIENTE"


@pytest.mark.parametrize("comentario", ["", "    ", "x" * 501])
def test_syn08_un_comentario_vacio_o_demasiado_largo_se_rechaza(
    cliente: TestClient, sesion: Session, comentario: str
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        _url(rechazo_id), json=_cuerpo(comentario=comentario), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "COMENTARIO_INVALIDO"
    assert _fila(sesion, "comando_rechazado", rechazo_id).estado == "PENDIENTE"


def test_syn08_un_origen_desconocido_es_un_pedido_invalido(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        _url(rechazo_id), json=_cuerpo(origen="OTRO"), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert _fila(sesion, "comando_rechazado", rechazo_id).estado == "PENDIENTE"


def test_inv06_el_doble_envio_devuelve_el_resultado_original_y_audita_una_vez(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Doble envío de la resolución"."""
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(entorno)
    headers = _con_op(entorno.confirmar_y_entrar(cliente))

    primera = cliente.post(_url(rechazo_id), json=_cuerpo(), headers=headers)
    segunda = cliente.post(_url(rechazo_id), json=_cuerpo(), headers=headers)

    assert primera.status_code == segunda.status_code == 200
    assert segunda.json() == primera.json()
    sesion.rollback()
    assert (
        sesion.scalar(
            text(
                "SELECT count(*) FROM auditoria WHERE organizacion_id = :o AND operation_id = :op"
            ),
            {"o": entorno.org, "op": UUID(headers["Operation-Id"])},
        )
        == 1
    )


# --- cuarentena (spec `sync/cuarentena-de-comandos`) --------------------------------------


def test_syn06_una_cuarentena_se_resuelve_con_comentario_y_vinculo_sin_crear_nada(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Revisar la venta de un teléfono dado de baja"."""
    entorno = Entorno(sesion, permisos=REVISOR)
    cuarentena_id = sembrar_cuarentena(
        sesion, entorno.org, usuario_id=entorno.usuario_id, dispositivo_id=entorno.dispositivo_id
    )
    venta_id = _venta(entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    antes = _foto_de_lo_que_no_se_toca(sesion, entorno.org)

    respuesta = cliente.post(
        _url(cuarentena_id),
        json=_cuerpo(origen="CUARENTENA", vinculo=("VENTA", venta_id)),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["origen"] == "CUARENTENA"
    fila = _fila(sesion, "comando_cuarentena", cuarentena_id)
    assert fila.revisado_por_id == entorno.usuario_id
    assert fila.revisado_en is not None
    assert (fila.comentario, fila.vinculo_tipo, fila.vinculo_id) == (COMENTARIO, "VENTA", venta_id)
    assert fila.motivo == "DISPOSITIVO_REVOCADO"
    assert _foto_de_lo_que_no_se_toca(sesion, entorno.org) == antes


def test_syn06_una_cuarentena_ya_revisada_es_rechazo_ya_resuelto(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Ya revisada"."""
    entorno = Entorno(sesion, permisos=REVISOR)
    cuarentena_id = sembrar_cuarentena(
        sesion, entorno.org, usuario_id=entorno.usuario_id, dispositivo_id=entorno.dispositivo_id
    )
    headers = entorno.confirmar_y_entrar(cliente)
    primera = cliente.post(
        _url(cuarentena_id), json=_cuerpo(origen="CUARENTENA"), headers=_con_op(headers)
    )
    assert primera.status_code == 200, primera.text

    segunda = cliente.post(
        _url(cuarentena_id), json=_cuerpo(origen="CUARENTENA"), headers=_con_op(headers)
    )

    assert segunda.status_code == 409
    assert segunda.json()["codigo"] == "RECHAZO_YA_RESUELTO"


def test_inv21_una_cuarentena_de_otra_organizacion_responde_404(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Cuarentena de otra organización"."""
    entorno = Entorno(sesion, permisos=REVISOR)
    otra = crear_organizacion(sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(sesion, otra)
    ajena = sembrar_cuarentena(sesion, otra, usuario_id=usuario, dispositivo_id=dispositivo)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        _url(ajena), json=_cuerpo(origen="CUARENTENA"), headers=_con_op(headers)
    )

    assert respuesta.status_code == 404
    assert _fila(sesion, "comando_cuarentena", ajena).revisado_en is None


def test_el_origen_se_busca_en_su_tabla_un_rechazo_no_es_una_cuarentena(
    cliente: TestClient, sesion: Session
) -> None:
    """El `id` de un rechazo con `origen` `CUARENTENA` no existe en la cuarentena: 404."""
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        _url(rechazo_id), json=_cuerpo(origen="CUARENTENA"), headers=_con_op(headers)
    )

    assert respuesta.status_code == 404
    assert _fila(sesion, "comando_rechazado", rechazo_id).estado == "PENDIENTE"


def test_syn06_el_telefono_dado_de_baja_reenvia_y_sigue_en_dispositivo_revocado(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "El teléfono dado de baja reenvía": un solo registro y su resolución no cambia."""
    entorno = Entorno(sesion, permisos=REVISOR)
    identidad_service.revocar_dispositivo(
        entorno.org,
        sesion,
        FixedClock(MOMENTO),
        dispositivo_id=entorno.dispositivo_id,
        actor_id=entorno.usuario_id,
    )
    operation_id = uuid4()
    cuarentena_id = sembrar_cuarentena(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        operation_id=operation_id,
    )
    headers = entorno.confirmar_y_entrar(cliente)
    resuelta = cliente.post(
        _url(cuarentena_id), json=_cuerpo(origen="CUARENTENA"), headers=_con_op(headers)
    )
    assert resuelta.status_code == 200, resuelta.text
    reenvio = ItemLote(
        operation_id=operation_id,
        tipo="VENTA_CONFIRMAR",
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={},
        jornada_id=None,
    )

    (resultado,) = sync_service.procesar_lote(
        sesion,
        FixedClock(MOMENTO),
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[reenvio],
    )

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "DISPOSITIVO_REVOCADO")
    sesion.rollback()
    assert (
        sesion.scalar(
            text("SELECT count(*) FROM comando_cuarentena WHERE operation_id = :o"),
            {"o": operation_id},
        )
        == 1
    )
    fila = _fila(sesion, "comando_cuarentena", cuarentena_id)
    assert (fila.revisado_por_id, fila.comentario) == (entorno.usuario_id, COMENTARIO)


def test_inv05_la_base_impide_cambiar_el_contenido_de_una_cuarentena(
    app_runtime_engine: Engine,
) -> None:
    """Escenario "Solo cambian las columnas de la revisión"."""
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(update(ComandoCuarentena).values(contenido={}))
    assert "permission denied" in str(error.value)
