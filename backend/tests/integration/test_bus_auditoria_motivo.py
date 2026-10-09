"""Change 14, tarea 7.1: el motivo en la fila de auditoría del bus (`design.md` D10, D10.1;
spec `stock/ajustes-de-stock`, requisito "Un ajuste se audita con su motivo").

Un handler puede devolver un dato opcional de auditoría (`DatosDeAuditoria`, declarado en
`app/commands`) y `sync/service.py` lo pasa a `registrar_auditoria(motivo_id=...)`. Es la
**única** fila de auditoría del comando (ADR-022). Un handler que no lo devuelve deja
`motivo_id` nulo, y `auditoria.observacion` sigue sin llenarse.

Reglas citadas: AUD-01, AUD-02, INV-01, INV-06, SYN-02, SYN-04.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.commands.auditoria import DatosDeAuditoria
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from stock_utiles import crear_motivo_sql

from app.commands import catalogo, registro
from app.commands.huella import calcular_huella
from app.commands.observaciones import ObservacionProducida
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.modules.identidad.models import Auditoria
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
TIPO = "USUARIO_CREAR"


class Entorno:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.motivo_id = crear_motivo_sql(sesion, self.org)
        self.otro_motivo_id = crear_motivo_sql(sesion, self.org)
        sesion.commit()

    def enviar(self, resultado_del_handler: object, *, operation_id: UUID | None = None):  # type: ignore[no-untyped-def]
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=TIPO,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido={},
        )

        def _ejecutar(_sesion_protegida: object) -> sync_service.ResultadoHandler:
            if isinstance(resultado_del_handler, Exception):
                raise resultado_del_handler
            return resultado_del_handler  # type: ignore[return-value]

        return sync_service.procesar_comando(
            self.sesion,
            RELOJ,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def auditorias(self, operation_id: UUID) -> list[Auditoria]:
        return list(
            self.sesion.scalars(
                select(Auditoria).where(
                    Auditoria.organizacion_id == self.org, Auditoria.operation_id == operation_id
                )
            ).all()
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def test_aud02_el_dato_de_auditoria_deja_el_motivo_en_la_unica_fila(entorno: Entorno) -> None:
    operation_id = uuid4()

    entorno.enviar(
        ("ACEPTADO", {"ok": True}, None, (), DatosDeAuditoria(motivo_id=entorno.motivo_id)),
        operation_id=operation_id,
    )

    (auditoria,) = entorno.auditorias(operation_id)
    assert auditoria.motivo_id == entorno.motivo_id
    assert auditoria.accion == TIPO
    assert auditoria.origen == "COMANDO"
    assert auditoria.observacion is None


def test_aud02_cada_comando_deja_su_propio_motivo(entorno: Entorno) -> None:
    primero, segundo = uuid4(), uuid4()

    entorno.enviar(
        ("ACEPTADO", None, None, (), DatosDeAuditoria(motivo_id=entorno.motivo_id)),
        operation_id=primero,
    )
    entorno.enviar(
        ("ACEPTADO", None, None, (), DatosDeAuditoria(motivo_id=entorno.otro_motivo_id)),
        operation_id=segundo,
    )

    assert [a.motivo_id for a in entorno.auditorias(primero)] == [entorno.motivo_id]
    assert [a.motivo_id for a in entorno.auditorias(segundo)] == [entorno.otro_motivo_id]


def test_un_handler_de_tres_elementos_deja_motivo_nulo(entorno: Entorno) -> None:
    operation_id = uuid4()

    entorno.enviar(("ACEPTADO", {"ok": True}, None), operation_id=operation_id)

    (auditoria,) = entorno.auditorias(operation_id)
    assert auditoria.motivo_id is None
    assert auditoria.observacion is None


def test_un_handler_con_observaciones_y_sin_dato_deja_motivo_nulo(entorno: Entorno) -> None:
    operation_id = uuid4()
    observacion = ObservacionProducida(
        codigo="STOCK_NEGATIVO", operacion_tipo="TRANSFERENCIA", operacion_id=uuid4()
    )

    comando = entorno.enviar(("ACEPTADO", None, None, (observacion,)), operation_id=operation_id)

    assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
    (auditoria,) = entorno.auditorias(operation_id)
    assert auditoria.motivo_id is None


def test_el_dato_de_auditoria_sin_motivo_deja_motivo_nulo(entorno: Entorno) -> None:
    operation_id = uuid4()

    entorno.enviar(
        ("ACEPTADO", None, None, (), DatosDeAuditoria(motivo_id=None)), operation_id=operation_id
    )

    (auditoria,) = entorno.auditorias(operation_id)
    assert auditoria.motivo_id is None


def test_el_dato_de_auditoria_convive_con_observaciones(entorno: Entorno) -> None:
    operation_id = uuid4()
    observacion = ObservacionProducida(
        codigo="STOCK_NEGATIVO", operacion_tipo="TRANSFERENCIA", operacion_id=uuid4()
    )

    comando = entorno.enviar(
        ("ACEPTADO", None, None, (observacion,), DatosDeAuditoria(motivo_id=entorno.motivo_id)),
        operation_id=operation_id,
    )

    assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
    (auditoria,) = entorno.auditorias(operation_id)
    assert auditoria.motivo_id == entorno.motivo_id


def test_syn04_un_resultado_rechazado_no_deja_fila_con_motivo(entorno: Entorno) -> None:
    operation_id = uuid4()

    comando = entorno.enviar(
        (
            "RECHAZADO",
            None,
            "STOCK_INSUFICIENTE",
            (),
            DatosDeAuditoria(motivo_id=entorno.motivo_id),
        ),
        operation_id=operation_id,
    )

    assert comando.estado == "RECHAZADO"
    assert [a.motivo_id for a in entorno.auditorias(operation_id)] == [None]


def test_inv01_un_handler_que_falla_no_deja_fila_de_auditoria(entorno: Entorno) -> None:
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="falla"):
        entorno.enviar(RuntimeError("falla del handler"), operation_id=operation_id)

    assert entorno.auditorias(operation_id) == []


def test_syn02_el_reenvio_idempotente_no_escribe_otra_fila(entorno: Entorno) -> None:
    operation_id = uuid4()
    resultado = ("ACEPTADO", {"ok": True}, None, (), DatosDeAuditoria(motivo_id=entorno.motivo_id))

    entorno.enviar(resultado, operation_id=operation_id)
    entorno.enviar(resultado, operation_id=operation_id)

    (auditoria,) = entorno.auditorias(operation_id)
    assert auditoria.motivo_id == entorno.motivo_id


class _EsquemaVacio(BaseModel):
    con_motivo: bool = True


def test_aud02_el_lote_tambien_copia_el_motivo_del_handler(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El camino del lote resuelve el handler antes que `procesar_comando`: el dato de
    auditoría no se puede perder en ese paso."""
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})
    monkeypatch.setattr("app.commands.registro._REGISTRO", {})
    catalogo.declarar_tipo("PRUEBA_MOTIVO", admite_online=True, admite_offline=True)

    def _handler(sobre: SobreComando, contenido: _EsquemaVacio) -> object:
        if contenido.con_motivo:
            return ("ACEPTADO", None, None, (), DatosDeAuditoria(motivo_id=entorno.motivo_id))
        return ("ACEPTADO", None, None)

    registro.registrar_handler("PRUEBA_MOTIVO", 1, _EsquemaVacio)(_handler)
    con_motivo, sin_motivo = uuid4(), uuid4()

    resultados = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[
            ItemLote(
                operation_id=operation_id,
                tipo="PRUEBA_MOTIVO",
                version=1,
                modo="ONLINE",
                usuario_id=entorno.usuario_id,
                dispositivo_id=entorno.dispositivo_id,
                occurred_at=MOMENTO,
                secuencia=secuencia,
                app_version="1.0.0",
                contenido={"con_motivo": hay_motivo},
            )
            for secuencia, (operation_id, hay_motivo) in enumerate(
                ((con_motivo, True), (sin_motivo, False)), start=1
            )
        ],
    )

    assert [r.estado for r in resultados] == ["ACEPTADO", "ACEPTADO"]
    assert [a.motivo_id for a in entorno.auditorias(con_motivo)] == [entorno.motivo_id]
    assert [a.motivo_id for a in entorno.auditorias(sin_motivo)] == [None]
