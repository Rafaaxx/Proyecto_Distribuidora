"""Change 25, tarea 9.1: la lectura de rechazos y cuarentenas (spec `sync/rechazos-sin-conexion`,
requisito "Los rechazos se leen por organización y no se borran"; `design.md` D4, D6).

`GET /api/v1/observaciones/rechazos` (lista con filtros y cursor) y `GET .../rechazos/{id}` (con lo
que envió el teléfono). Los resúmenes del contenido los dan los módulos dueños de cada comando por
`app.core.resumen` y no fallan con contenido mal formado ni con referencias inexistentes.

Reglas citadas: SYN-06, SYN-09, INV-05, INV-21, SEG-06.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import Entorno as EntornoDeCobranzas
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from fastapi.testclient import TestClient
from revision_utiles import sembrar_cuarentena, sembrar_rechazo
from sqlalchemy import Engine, delete, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    Entorno,
    _con_op,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)

from app.modules.sync import service as sync_service
from app.modules.sync.models import ComandoRechazado

URL = "/api/v1/observaciones/rechazos"
REVISOR = frozenset({"REVISAR_OBSERVACIONES"})
LLEGADA = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def _rechazo(entorno: Entorno, **cambios: Any) -> UUID:
    return sembrar_rechazo(
        entorno.sesion,
        entorno.org,
        usuario_id=cambios.pop("usuario_id", entorno.usuario_id),
        dispositivo_id=entorno.dispositivo_id,
        **cambios,
    )


def _cuarentena(entorno: Entorno, **cambios: Any) -> UUID:
    return sembrar_cuarentena(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        **cambios,
    )


def _leer(cliente_http: TestClient, headers: dict[str, str], **filtros: object) -> dict[str, Any]:
    respuesta = cliente_http.get(URL, params=filtros, headers=headers)  # type: ignore[arg-type]
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()  # type: ignore[no-any-return]


def _ids(pagina: dict[str, Any]) -> list[str]:
    return [item["id"] for item in pagina["items"]]


def _venta_enviada(entorno: Entorno, cliente_id: UUID, producto_id: UUID) -> dict[str, object]:
    """Lo que el teléfono envió en `VENTA_CONFIRMAR`: 15 botellas de Vino A por $31.250."""
    return {
        "venta_id": str(uuid4()),
        "numero": "V01-000123",
        "cliente_id": str(cliente_id),
        "total": "31250.00",
        "lineas": [
            {
                "linea_id": str(uuid4()),
                "producto_id": str(producto_id),
                "presentacion_id": str(uuid4()),
                "cantidad": 15,
                "importe_bruto": "31250.00",
            }
        ],
    }


# --- el resumen del contenido -----------------------------------------------------------------


def test_syn06_la_lista_muestra_cliente_numero_total_y_lineas_de_lo_que_envio_el_telefono(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Resumen del contenido"."""
    entorno = Entorno(sesion, permisos=REVISOR)
    cliente_id = crear_cliente(sesion, entorno.org, nombre="Kiosco La Esquina")
    jornada = crear_jornada_sql(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(sesion, entorno.org, nombre="Camioneta 1"),
    )
    rechazo_id = _rechazo(
        entorno,
        contenido=_venta_enviada(entorno, cliente_id, entorno.producto_id),
        jornada_id=jornada,
        recibido_en=LLEGADA,
    )
    headers = entorno.confirmar_y_entrar(cliente)

    (item,) = _leer(cliente, headers)["items"]

    assert item["id"] == str(rechazo_id)
    assert (item["origen"], item["estado"], item["tipo"]) == (
        "RECHAZO",
        "PENDIENTE",
        "VENTA_CONFIRMAR",
    )
    assert item["codigo"] == "TOTALES_INCONSISTENTES"
    assert (item["usuario_id"], item["usuario_nombre"]) == (
        str(entorno.usuario_id),
        "Persona de prueba",
    )
    assert item["jornada_id"] == str(jornada)
    assert item["aceptada_despues"] is False
    resumen = item["resumen"]
    assert resumen["titulo"] == "Venta V01-000123"
    assert (resumen["cliente"], resumen["numero"], resumen["total"]) == (
        "Kiosco La Esquina",
        "V01-000123",
        "31250.00",
    )
    assert resumen["lineas"] == [{"producto": "Vino A", "cantidad": 15, "importe": "31250.00"}]
    assert item["contenido"] is None  # lo crudo va solo en el detalle


def test_syn06_un_cliente_que_no_existe_o_es_de_otra_organizacion_se_indica_sin_fallar(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Contenido con un cliente que no existe" (y el de otra organización, INV-21)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    otra = crear_organizacion(sesion).id
    cliente_ajeno = crear_cliente(sesion, otra, nombre="Cliente de otra organización")
    inexistente = _rechazo(
        entorno,
        error_codigo="RECURSO_NO_ENCONTRADO",
        contenido=_venta_enviada(entorno, uuid4(), entorno.producto_id),
    )
    ajeno = _rechazo(
        entorno,
        contenido=_venta_enviada(entorno, cliente_ajeno, uuid4()),
        recibido_en=LLEGADA + timedelta(minutes=1),
    )
    headers = entorno.confirmar_y_entrar(cliente)

    items = {i["id"]: i for i in _leer(cliente, headers)["items"]}

    assert items[str(inexistente)]["resumen"]["cliente"] == "(no existe)"
    assert items[str(ajeno)]["resumen"]["cliente"] == "(no existe)"
    assert items[str(ajeno)]["resumen"]["lineas"][0]["producto"] == "(no existe)"
    assert "Cliente de otra organización" not in str(items)


@pytest.mark.parametrize(
    "contenido",
    [
        {},
        {"cliente_id": "esto no es un uuid", "lineas": "no es una lista", "total": 3},
        {"lineas": [None, 7, {"cantidad": "muchas"}], "numero": ["x"]},
        {"medios": {"a": 1}, "importe": {"x": 1}, "cliente_id": 5},
    ],
)
@pytest.mark.parametrize("tipo", ["VENTA_CONFIRMAR", "VENTA_ANULAR", "COBRANZA_REGISTRAR"])
def test_syn06_un_contenido_mal_formado_se_lee_sin_fallar(
    cliente: TestClient, sesion: Session, tipo: str, contenido: dict[str, object]
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo_id = _rechazo(entorno, tipo=tipo, contenido=contenido)
    headers = entorno.confirmar_y_entrar(cliente)

    (item,) = _leer(cliente, headers)["items"]

    assert item["id"] == str(rechazo_id)
    assert item["resumen"]["titulo"]


def test_syn06_la_anulacion_se_resume_con_la_venta_que_nombra(
    cliente: TestClient, sesion: Session
) -> None:
    """Una anulación rechazada muestra el número y el total de la venta (o que no existe)."""
    from ventas_utiles import sembrar_venta_sql

    entorno = Entorno(sesion, permisos=REVISOR)
    cliente_id = crear_cliente(sesion, entorno.org, nombre="Almacén Don Pedro")
    venta = sembrar_venta_sql(
        sesion,
        entorno.org,
        cliente_id=cliente_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        numero="V01-000456",
    )
    real = _rechazo(
        entorno,
        tipo="VENTA_ANULAR",
        error_codigo="JORNADA_AJENA",
        contenido={"venta_id": str(venta.venta_id)},
    )
    perdida = _rechazo(
        entorno,
        tipo="VENTA_ANULAR",
        error_codigo="VENTA_INEXISTENTE",
        contenido={"venta_id": str(uuid4())},
        recibido_en=LLEGADA + timedelta(minutes=1),
    )
    headers = entorno.confirmar_y_entrar(cliente)

    items = {i["id"]: i["resumen"] for i in _leer(cliente, headers)["items"]}

    assert items[str(real)]["titulo"] == "Anulación de venta"
    assert (items[str(real)]["numero"], items[str(real)]["cliente"]) == (
        "V01-000456",
        "Almacén Don Pedro",
    )
    assert items[str(perdida)]["numero"] == "(no existe)"


def test_syn06_una_cobranza_se_resume_con_el_cliente_el_importe_y_los_medios(
    db_session: Session,
) -> None:
    """Resumen de `COBRANZA_REGISTRAR`: cliente, importe y cada medio con su nombre."""
    entorno = EntornoDeCobranzas(db_session)
    contenido = entorno.contenido()

    (resumen,) = sync_service.resumir_contenidos(
        entorno.org, db_session, "COBRANZA_REGISTRAR", [contenido]
    )

    assert resumen is not None
    assert resumen.titulo == "Cobranza"
    assert resumen.total == "50000.00"
    assert resumen.cliente is not None
    assert [(m.medio, m.importe) for m in resumen.medios] == [
        ("Efectivo", "30000.00"),
        ("Transferencia", "20000.00"),
    ]


def test_syn06_un_tipo_sin_resumidor_no_tiene_resumen(db_session: Session) -> None:
    organizacion = crear_organizacion(db_session)

    resumenes = sync_service.resumir_contenidos(organizacion.id, db_session, "TIPO_RARO", [{}, {}])

    assert resumenes == [None, None]


def test_syn06_la_entrega_del_dia_se_resume_por_su_titulo(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    _rechazo(entorno, tipo="JORNADA_ENTREGAR", error_codigo="JORNADA_INEXISTENTE")
    headers = entorno.confirmar_y_entrar(cliente)

    (item,) = _leer(cliente, headers)["items"]

    assert item["resumen"]["titulo"] == "Entrega del día"


# --- cuarentenas, origen y estado ---------------------------------------------------------------


def test_syn06_la_lista_mezcla_rechazos_y_cuarentenas_con_su_origen(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    rechazo = _rechazo(entorno, recibido_en=LLEGADA)
    cuarentena = _cuarentena(entorno, recibido_en=LLEGADA + timedelta(minutes=5))
    headers = entorno.confirmar_y_entrar(cliente)

    pagina = _leer(cliente, headers)

    assert _ids(pagina) == [str(cuarentena), str(rechazo)]  # la más reciente primero
    por_id = {i["id"]: i for i in pagina["items"]}
    assert por_id[str(cuarentena)]["origen"] == "CUARENTENA"
    assert por_id[str(cuarentena)]["codigo"] == "DISPOSITIVO_REVOCADO"
    assert por_id[str(cuarentena)]["jornada_id"] is None
    assert por_id[str(rechazo)]["origen"] == "RECHAZO"
    assert _ids(_leer(cliente, headers, origen="CUARENTENA")) == [str(cuarentena)]
    assert _ids(_leer(cliente, headers, origen="RECHAZO")) == [str(rechazo)]


def test_syn08_el_estado_filtra_y_la_resolucion_se_muestra(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    pendiente = _rechazo(entorno, recibido_en=LLEGADA)
    resuelto = _rechazo(entorno, recibido_en=LLEGADA + timedelta(minutes=1))
    revisada = _cuarentena(entorno, recibido_en=LLEGADA + timedelta(minutes=2))
    headers = entorno.confirmar_y_entrar(cliente)
    for id_, origen in ((resuelto, "RECHAZO"), (revisada, "CUARENTENA")):
        respuesta = cliente.post(
            f"{URL}/{id_}/resolucion",
            json={"origen": origen, "comentario": "Revisado"},
            headers=_con_op(headers),
        )
        assert respuesta.status_code == 200, respuesta.text

    assert _ids(_leer(cliente, headers)) == [str(pendiente)]  # por defecto, las pendientes
    assert set(_ids(_leer(cliente, headers, estado="RESUELTO"))) == {str(resuelto), str(revisada)}
    assert len(_leer(cliente, headers, estado="TODOS")["items"]) == 3
    item = next(
        i for i in _leer(cliente, headers, estado="RESUELTO")["items"] if i["id"] == str(resuelto)
    )
    assert item["estado"] == "RESUELTO"
    assert item["resuelto_por_id"] == str(entorno.usuario_id)
    assert item["resuelto_por_nombre"] == "Persona de prueba"
    assert item["resuelto_en"] is not None
    assert item["comentario"] == "Revisado"
    assert (item["vinculo_tipo"], item["vinculo_id"]) == (None, None)


def test_syn09_los_filtros_de_tipo_usuario_y_jornada_restringen_la_lista(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    otro_usuario, _ = crear_usuario_y_dispositivo(sesion, entorno.org)
    jornada = crear_jornada_sql(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(sesion, entorno.org, nombre="Camioneta 1"),
    )
    venta = _rechazo(entorno, tipo="VENTA_CONFIRMAR", jornada_id=jornada, recibido_en=LLEGADA)
    cobranza = _rechazo(
        entorno,
        tipo="COBRANZA_REGISTRAR",
        usuario_id=otro_usuario,
        recibido_en=LLEGADA + timedelta(minutes=1),
    )
    cuarentena = _cuarentena(entorno, recibido_en=LLEGADA + timedelta(minutes=2))
    headers = entorno.confirmar_y_entrar(cliente)

    assert _ids(_leer(cliente, headers, tipo="COBRANZA_REGISTRAR")) == [str(cobranza)]
    # la cuarentena de la prueba es una venta: entra con el tipo `VENTA_CONFIRMAR`
    assert set(_ids(_leer(cliente, headers, tipo=["VENTA_CONFIRMAR", "COBRANZA_REGISTRAR"]))) == {
        str(venta),
        str(cobranza),
        str(cuarentena),
    }
    assert _ids(_leer(cliente, headers, usuario_id=str(otro_usuario))) == [str(cobranza)]
    assert _ids(_leer(cliente, headers, jornada_id=str(jornada))) == [str(venta)]


def test_syn09_aceptada_despues_cuando_el_mismo_operation_id_se_acepto(
    cliente: TestClient, sesion: Session
) -> None:
    """Un rechazo cuyo `operation_id` el servidor aceptó en un reenvío posterior lo indica."""
    from revision_utiles import sembrar_observaciones

    entorno = Entorno(sesion, permisos=REVISOR)
    operation_id = uuid4()
    rechazo = _rechazo(entorno, operation_id=operation_id)
    sin_aceptar = _rechazo(entorno, recibido_en=LLEGADA + timedelta(minutes=1))
    aceptado = sembrar_observaciones(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        codigos=("STOCK_NEGATIVO",),
    )
    sesion.execute(
        text("UPDATE comando SET operation_id = :o WHERE id = :c"),
        {"o": operation_id, "c": aceptado.comando_id},
    )
    headers = entorno.confirmar_y_entrar(cliente)

    items = {i["id"]: i["aceptada_despues"] for i in _leer(cliente, headers)["items"]}

    assert items == {str(rechazo): True, str(sin_aceptar): False}


def test_syn09_la_lista_se_pagina_con_cursor(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    ids = [
        _rechazo(entorno, recibido_en=LLEGADA + timedelta(minutes=minutos)) for minutos in range(5)
    ]
    headers = entorno.confirmar_y_entrar(cliente)

    primera = _leer(cliente, headers, limite=2)
    segunda = _leer(cliente, headers, limite=2, cursor=primera["cursor_siguiente"])
    tercera = _leer(cliente, headers, limite=2, cursor=segunda["cursor_siguiente"])

    assert _ids(primera) + _ids(segunda) + _ids(tercera) == [str(i) for i in reversed(ids)]
    assert tercera["cursor_siguiente"] is None


def test_syn09_un_cursor_ilegible_es_cursor_invalido(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get(URL, params={"cursor": "basura"}, headers=headers)

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "CURSOR_INVALIDO"


# --- detalle, organización y permiso ------------------------------------------------------------


def test_syn09_el_detalle_trae_lo_crudo_que_envio_el_telefono(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    contenido = {"venta_id": str(uuid4()), "numero": "V01-000999", "total": "10.00"}
    rechazo_id = _rechazo(entorno, contenido=contenido)
    cuarentena_id = _cuarentena(entorno, contenido={"cobranza_id": "x"}, tipo="COBRANZA_REGISTRAR")
    headers = entorno.confirmar_y_entrar(cliente)

    rechazo = cliente.get(f"{URL}/{rechazo_id}", headers=headers)
    cuarentena = cliente.get(f"{URL}/{cuarentena_id}", headers=headers)

    assert rechazo.status_code == 200, rechazo.text
    assert rechazo.json()["contenido"] == contenido
    assert rechazo.json()["origen"] == "RECHAZO"
    assert cuarentena.status_code == 200, cuarentena.text
    assert cuarentena.json()["origen"] == "CUARENTENA"
    assert cuarentena.json()["contenido"] == {"cobranza_id": "x"}


def test_inv21_otra_organizacion_no_ve_los_rechazos_y_su_pedido_responde_404(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Otra organización"."""
    entorno = Entorno(sesion, permisos=REVISOR)
    propio = _rechazo(entorno)
    otra = crear_organizacion(sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(sesion, otra)
    ajeno = sembrar_rechazo(sesion, otra, usuario_id=usuario, dispositivo_id=dispositivo)
    ajena_cuarentena = sembrar_cuarentena(
        sesion, otra, usuario_id=usuario, dispositivo_id=dispositivo
    )
    headers = entorno.confirmar_y_entrar(cliente)

    assert _ids(_leer(cliente, headers, estado="TODOS")) == [str(propio)]
    for id_ in (ajeno, ajena_cuarentena, uuid4()):
        respuesta = cliente.get(f"{URL}/{id_}", headers=headers)

        assert respuesta.status_code == 404, respuesta.text
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


def test_seg06_sin_el_permiso_la_lista_y_el_detalle_responden_403(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=frozenset({"VENDER"}))
    rechazo_id = _rechazo(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    for url in (URL, f"{URL}/{rechazo_id}"):
        respuesta = cliente.get(url, headers=headers)

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def test_inv05_la_aplicacion_no_puede_borrar_un_rechazo(app_runtime_engine: Engine) -> None:
    """Escenario "La aplicación no puede borrar un rechazo"."""
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(delete(ComandoRechazado))
    assert "permission denied" in str(error.value)
