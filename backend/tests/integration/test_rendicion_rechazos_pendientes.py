"""Change 25, tarea 9b.2 (spec `stock/rendicion-de-jornada`, requisito "La rendición espera a que se
resuelvan las operaciones rechazadas de la jornada", y spec `sync/rechazos-sin-conexion`, escenarios
"Resolver el último rechazo de la jornada habilita la rendición" y "Cantidad pendiente por
jornada"; `design.md` D9 = B), contra PostgreSQL real y por el bus.

`JORNADA_RENDIR` se rechaza con `RECHAZOS_PENDIENTES` mientras la jornada tenga rechazos
`PENDIENTE`, sin escribir nada. Rechazos de otra jornada, sin jornada, de otra organización y
cuarentenas no bloquean; tampoco bloquean la entrega, el cierre ni la liberación. El puerto lo
declara `stock/service.py` y lo registra `sync/service.py`; sin puerto la rendición falla.

La concurrencia (resolución y rendición a la vez) es del Lote 7.

Reglas citadas: RUT-05, RUT-06, SYN-06, SYN-08, INV-01, INV-06, INV-21.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from fastapi.testclient import TestClient
from revision_utiles import sembrar_cuarentena, sembrar_rechazo
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql
from test_jornada_cerrar_v2 import Entorno as EntornoDeCierre
from test_jornada_entregar import Entorno as EntornoDeEntrega
from test_jornada_rendir_v2 import Entorno as EntornoDeRendicion
from test_jornadas_liberar import Entorno as EntornoDeLiberacion
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    Entorno,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)
from ventas_utiles import sembrar_venta_sql

from app.core.clock import FixedClock
from app.modules.cobranzas import service as _cobranzas  # noqa: F401  (registra el lector)
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import RechazosPendientesError
from app.modules.sync import revision_casos
from app.modules.ventas import service as _ventas  # noqa: F401  (registra el lector)

MOMENTO = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def entorno(db_session: Session) -> EntornoDeRendicion:
    return EntornoDeRendicion(db_session)


def _rechazar(
    entorno: EntornoDeRendicion,
    *,
    jornada_id: UUID | None = ...,  # type: ignore[assignment]
    tipo: str = "VENTA_CONFIRMAR",
    org: UUID | None = None,
) -> UUID:
    """Un rechazo `PENDIENTE` de Juan (por defecto, de la jornada del entorno)."""
    rechazo_id = sembrar_rechazo(
        entorno.sesion,
        org or entorno.org,
        usuario_id=entorno.juan.usuario_id,
        dispositivo_id=entorno.juan.dispositivo_id,
        jornada_id=entorno.jornada_id if jornada_id is ... else jornada_id,
        tipo=tipo,
    )
    entorno.sesion.commit()  # las lecturas del entorno hacen `rollback`
    return rechazo_id


def _resolver(
    entorno: EntornoDeRendicion,
    rechazo_id: UUID,
    *,
    vinculo: tuple[str, UUID] | None = None,
) -> None:
    revision_casos.resolver_rechazo(
        entorno.org,
        entorno.sesion,
        FixedClock(MOMENTO),
        usuario_id=entorno.supervisora.usuario_id,
        origen="RECHAZO",
        rechazo_id=rechazo_id,
        comentario="Revisado",
        vinculo_tipo=None if vinculo is None else vinculo[0],
        vinculo_id=None if vinculo is None else vinculo[1],
    )
    entorno.sesion.commit()


def _preparado(entorno: EntornoDeRendicion) -> UUID:
    """La jornada entregada de Juan con 40 de Vino A y un conteo completo posible."""
    entorno.cargar(entorno.vino, 40)
    return entorno.abrir()


def _rendir(entorno: EntornoDeRendicion, **opciones: object):  # type: ignore[no-untyped-def]
    return entorno.enviar(entorno.contenido([(entorno.vino, 40, 40)]), **opciones)  # type: ignore[arg-type]


# --- el bloqueo -------------------------------------------------------------------------------


def test_rut05_la_rendicion_con_un_rechazo_pendiente_se_rechaza_sin_escribir_nada(
    entorno: EntornoDeRendicion,
) -> None:
    """Escenario "Rendición con una venta rechazada sin resolver"."""
    _preparado(entorno)
    _rechazar(entorno)
    movimientos = entorno.cantidad_de_movimientos()

    with pytest.raises(RechazosPendientesError) as error:
        _rendir(entorno)

    assert (error.value.codigo, error.value.status_http) == ("RECHAZOS_PENDIENTES", 409)
    assert error.value.extension == {"rechazos_pendientes": 1}
    assert entorno.jornada().estado == "ABIERTA"
    assert entorno.rendiciones() == []
    assert entorno.lineas() == {}
    assert entorno.diferencias() == []
    assert entorno.cantidad_de_movimientos() == movimientos
    assert entorno.saldo(entorno.vino) == 40


def test_rut05_la_cantidad_cuenta_los_rechazos_de_cualquier_tipo_de_la_jornada(
    entorno: EntornoDeRendicion,
) -> None:
    """Triangulación: una venta, una cobranza y una entrega rechazadas son 3."""
    _preparado(entorno)
    for tipo in ("VENTA_CONFIRMAR", "COBRANZA_REGISTRAR", "JORNADA_ENTREGAR"):
        _rechazar(entorno, tipo=tipo)

    with pytest.raises(RechazosPendientesError) as error:
        _rendir(entorno)

    assert error.value.extension == {"rechazos_pendientes": 3}


def test_syn08_resuelto_sin_vinculo_la_rendicion_se_acepta(entorno: EntornoDeRendicion) -> None:
    """Escenarios "Resuelto sin vínculo" y "Resolver el último rechazo de la jornada habilita la
    rendición"."""
    _preparado(entorno)
    rechazo = _rechazar(entorno)
    with pytest.raises(RechazosPendientesError):
        _rendir(entorno)
    _resolver(entorno, rechazo)

    comando = _rendir(entorno)

    assert comando.estado == "ACEPTADO"
    assert entorno.jornada().estado == "EN_RENDICION"


def test_syn08_resuelto_con_vinculo_a_la_venta_cargada_la_rendicion_se_acepta(
    entorno: EntornoDeRendicion,
) -> None:
    """Escenario "Rendición permitida cuando todo está resuelto"."""
    _preparado(entorno)
    rechazo = _rechazar(entorno)
    venta = sembrar_venta_sql(
        entorno.sesion,
        entorno.org,
        cliente_id=crear_cliente(entorno.sesion, entorno.org, nombre="Kiosco La Esquina"),
        usuario_id=entorno.juan.usuario_id,
        dispositivo_id=entorno.juan.dispositivo_id,
    ).venta_id
    _resolver(entorno, rechazo, vinculo=("VENTA", venta))

    comando = _rendir(entorno)

    assert comando.estado == "ACEPTADO"


def test_syn08_con_dos_rechazos_alcanza_con_resolver_uno_para_pasar_de_dos_a_uno(
    entorno: EntornoDeRendicion,
) -> None:
    _preparado(entorno)
    primero = _rechazar(entorno)
    _rechazar(entorno)
    _resolver(entorno, primero)

    with pytest.raises(RechazosPendientesError) as error:
        _rendir(entorno)

    assert error.value.extension == {"rechazos_pendientes": 1}


def test_inv06_el_mismo_operation_id_se_procesa_de_nuevo_despues_de_resolver(
    entorno: EntornoDeRendicion,
) -> None:
    """Escenario "Doble envío de una rendición rechazada": el rechazo revirtió la reserva."""
    _preparado(entorno)
    rechazo = _rechazar(entorno)
    operation_id = uuid4()
    with pytest.raises(RechazosPendientesError):
        _rendir(entorno, operation_id=operation_id)
    _resolver(entorno, rechazo)

    comando = _rendir(entorno, operation_id=operation_id)

    assert comando.estado == "ACEPTADO"
    assert comando.operation_id == operation_id


# --- lo que no bloquea ------------------------------------------------------------------------


def test_inv21_rechazos_de_otra_jornada_sin_jornada_otra_organizacion_y_cuarentenas_no_bloquean(
    entorno: EntornoDeRendicion,
) -> None:
    """Escenario "Rechazos de otra jornada o en cuarentena"."""
    _preparado(entorno)
    otra_jornada = crear_jornada_sql(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.juan.usuario_id,
        dispositivo_id=entorno.juan.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(entorno.sesion, entorno.org, nombre="Camioneta 2"),
        estado="CERRADA",
    )
    _rechazar(entorno, jornada_id=otra_jornada)
    _rechazar(entorno, jornada_id=None)
    sembrar_cuarentena(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.juan.usuario_id,
        dispositivo_id=entorno.juan.dispositivo_id,
    )
    ajena = crear_organizacion(entorno.sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(entorno.sesion, ajena)
    jornada_ajena = crear_jornada_sql(
        entorno.sesion,
        ajena,
        usuario_id=usuario,
        dispositivo_id=dispositivo,
        ubicacion_id=crear_ubicacion_sql(entorno.sesion, ajena, nombre="Camioneta ajena"),
    )
    sembrar_rechazo(
        entorno.sesion,
        ajena,
        usuario_id=usuario,
        dispositivo_id=dispositivo,
        jornada_id=jornada_ajena,
    )
    entorno.sesion.commit()

    comando = _rendir(entorno)

    assert comando.estado == "ACEPTADO"


def test_rut05_la_entrega_del_dia_no_se_bloquea_con_rechazos_pendientes(
    db_session: Session,
) -> None:
    """Escenario "La entrega del día no se bloquea"."""
    entorno = EntornoDeEntrega(db_session)
    jornada = entorno.jornada()
    sembrar_rechazo(
        db_session,
        entorno.org,
        usuario_id=entorno.juan,
        dispositivo_id=entorno.dispositivo_juan,
        jornada_id=jornada,
    )
    db_session.commit()

    _, resultado = entorno.entregar(jornada)

    assert resultado.estado == "ACEPTADO"
    assert entorno.leer(jornada).entregada_en is not None


def test_rut08_el_cierre_no_se_bloquea_con_rechazos_pendientes(db_session: Session) -> None:
    entorno = EntornoDeCierre(db_session)
    sembrar_rechazo(
        db_session,
        entorno.org,
        usuario_id=entorno.juan.usuario_id,
        dispositivo_id=entorno.juan.dispositivo_id,
        jornada_id=entorno.jornada_id,
    )
    db_session.commit()

    comando = entorno.enviar(entorno.contenido())

    assert comando.estado == "ACEPTADO"
    assert entorno.jornada().estado == "CERRADA"


def test_rut09_la_liberacion_no_se_bloquea_con_rechazos_pendientes(db_session: Session) -> None:
    """La salida si el teléfono se perdió (RUT-09) sigue disponible."""
    entorno = EntornoDeLiberacion(db_session)
    jornada = entorno.abrir_juan()
    sembrar_rechazo(
        db_session,
        entorno.org,
        usuario_id=entorno.juan.usuario_id,
        dispositivo_id=entorno.juan.dispositivo_id,
        jornada_id=jornada,
    )
    db_session.commit()

    comando = entorno.enviar(
        "JORNADA_LIBERAR",
        entorno.supervisora,
        {"jornada_id": str(jornada), "motivo_id": str(entorno.motivo)},
    )

    assert comando.estado == "ACEPTADO"


# --- el puerto --------------------------------------------------------------------------------


def test_syn06_el_puerto_cuenta_solo_los_pendientes_de_la_jornada_y_la_organizacion(
    entorno: EntornoDeRendicion,
) -> None:
    """Escenario "Cantidad pendiente por jornada": 2 pendientes y 1 resuelto de la jornada, uno
    de otra jornada, uno sin jornada y uno de otra organización: es 2."""
    jornada = _preparado(entorno)
    _rechazar(entorno)
    _rechazar(entorno)
    resuelto = _rechazar(entorno)
    otra_jornada = crear_jornada_sql(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.juan.usuario_id,
        dispositivo_id=entorno.juan.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(entorno.sesion, entorno.org, nombre="Camioneta 2"),
        estado="CERRADA",
    )
    _rechazar(entorno, jornada_id=otra_jornada)
    _rechazar(entorno, jornada_id=None)
    ajena = crear_organizacion(entorno.sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(entorno.sesion, ajena)
    sembrar_rechazo(entorno.sesion, ajena, usuario_id=usuario, dispositivo_id=dispositivo)
    entorno.sesion.commit()
    _resolver(entorno, resuelto)

    cantidad = stock_service.rechazos_pendientes_de_jornada(
        entorno.org, entorno.sesion, jornada_id=jornada
    )

    assert cantidad == 2
    assert (
        stock_service.rechazos_pendientes_de_jornada(ajena, entorno.sesion, jornada_id=jornada) == 0
    )


def test_la_aplicacion_tiene_registrado_el_puerto_de_rechazos_pendientes() -> None:
    """`sync/service.py` lo registra al importarse y la aplicación importa `sync`."""
    import app.main  # noqa: F401

    assert stock_service.hay_contador_de_rechazos_pendientes()


def test_sin_puerto_registrado_la_rendicion_falla_y_no_escribe_nada(
    entorno: EntornoDeRendicion, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No se rinde sin comprobar: sin puerto es un error de configuración, no «no hay»."""
    _preparado(entorno)
    movimientos = entorno.cantidad_de_movimientos()
    monkeypatch.setattr(stock_service, "_CONTADOR_DE_RECHAZOS", None)

    with pytest.raises(RuntimeError, match="rechazos pendientes"):
        _rendir(entorno)

    assert entorno.jornada().estado == "ABIERTA"
    assert entorno.rendiciones() == []
    assert entorno.cantidad_de_movimientos() == movimientos


# --- la lectura de la jornada ------------------------------------------------------------------


def test_rut05_el_detalle_de_la_jornada_trae_la_cantidad_de_rechazos_pendientes(
    cliente: TestClient, sesion: Session
) -> None:
    """`GET /stock/jornadas/{id}` devuelve `rechazos_pendientes` a quien puede leer la jornada,
    aunque no tenga `REVISAR_OBSERVACIONES`."""
    entorno = Entorno(sesion, permisos=frozenset({"RENDIR_JORNADA"}))
    jornada = crear_jornada_sql(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(sesion, entorno.org, nombre="Camioneta 1"),
    )
    for _ in range(2):
        sembrar_rechazo(
            sesion,
            entorno.org,
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
            jornada_id=jornada,
        )
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get(f"/api/v1/stock/jornadas/{jornada}", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["rechazos_pendientes"] == 2


def test_rut05_sin_rechazos_el_detalle_dice_cero(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=frozenset({"RENDIR_JORNADA"}))
    jornada = crear_jornada_sql(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(sesion, entorno.org, nombre="Camioneta 1"),
    )
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get(f"/api/v1/stock/jornadas/{jornada}", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["rechazos_pendientes"] == 0
