"""Change 18b, lote 3 (aprobado por el usuario el 2026-10-23; `design.md` D23, ADR-056; spec
`sync/lote-de-comandos`): en el lote, el permiso del tipo se evalúa ANTES de validar el contenido.

- `ONLINE` sin permiso con contenido inválido: el ítem se rechaza por `PERMISO_REQUERIDO`; nunca
  se revela el detalle de la validación del contenido a quien no puede ejecutar el tipo.
- `ONLINE` con permiso y contenido inválido: sigue el rechazo por contenido inválido.
- `OFFLINE` con el permiso revocado y contenido válido: NO se rechaza, entra con la observación
  `PERMISO_REVOCADO` (SYN-05, SYN-10); solo cambia el orden.
- `OFFLINE` con el permiso revocado y contenido inválido: se rechaza por contenido (es malformado).

El permiso lo sigue exigiendo un solo lugar, el bus (`procesar_comando`); el lote no lo evalúa dos
veces. Tipo de prueba aislado por `monkeypatch`.

Reglas citadas: SEG-06, SYN-05, SYN-06, SYN-10, INV-01, INV-06.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

from app.commands import catalogo, registro
from app.commands.catalogo import OperacionObservable
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

MOMENTO = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
TIPO = "PRUEBA_PERMISO_ANTES_QUE_CONTENIDO"
PERMISO = "REGISTRAR_COBRANZA"

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


class _Esquema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monto: int


def _handler(
    sobre: SobreComando, contenido: _Esquema, *, sesion: object, reloj: object
) -> tuple[str, dict[str, object] | None, str | None]:
    return "ACEPTADO", {"operacion_id": str(sobre.operation_id)}, None


@pytest.fixture(autouse=True)
def _catalogo_y_registro_aislados(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})
    monkeypatch.setattr("app.commands.registro._REGISTRO", {})
    catalogo.declarar_tipo(
        TIPO,
        admite_online=True,
        admite_offline=True,
        permisos=(PERMISO,),
        operacion_offline=OperacionObservable("OPERACION_DE_PRUEBA", "operacion_id"),
    )
    registro.registrar_handler(TIPO, 1, _Esquema)(_handler)


class Entorno:
    def __init__(self, sesion: Session, *, con_permiso: bool) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=frozenset({PERMISO}) if con_permiso else frozenset()
        )
        self.jornada_id = crear_jornada_sql(
            sesion,
            self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            ubicacion_id=crear_ubicacion_sql(sesion, self.org, requiere_toma=True),
        )
        sesion.commit()

    def lote(
        self, contenido: dict[str, object], *, modo: str
    ) -> tuple[sync_service.ResultadoItemLote, UUID]:
        item = ItemLote(
            operation_id=uuid4(),
            tipo=TIPO,
            version=1,
            modo=modo,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,  # type: ignore[arg-type]
            jornada_id=self.jornada_id if modo == "OFFLINE" else None,
        )
        (resultado,) = sync_service.procesar_lote(
            self.sesion,
            RELOJ,
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            items=[item],
        )
        return resultado, item.operation_id

    def comandos(self) -> int:
        self.sesion.rollback()
        return int(
            self.sesion.scalar(
                select(func.count()).select_from(Comando).where(Comando.organizacion_id == self.org)
            )
            or 0
        )

    def codigos_de_observacion(self) -> list[str]:
        self.sesion.rollback()
        return list(
            self.sesion.scalars(
                select(Observacion.codigo).where(Observacion.organizacion_id == self.org)
            ).all()
        )


INVALIDO: dict[str, object] = {"monto": "no-es-un-entero", "sobra": 1}
VALIDO: dict[str, object] = {"monto": 10}


def test_seg06_online_sin_permiso_y_contenido_invalido_responde_permiso_requerido(
    db_session: Session,
) -> None:
    entorno = Entorno(db_session, con_permiso=False)

    resultado, _ = entorno.lote(INVALIDO, modo="ONLINE")

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "PERMISO_REQUERIDO"
    assert entorno.comandos() == 0


def test_seg06_online_sin_permiso_y_contenido_valido_tambien_responde_permiso_requerido(
    db_session: Session,
) -> None:
    """Triangula: el resultado no depende de si el contenido era válido."""
    entorno = Entorno(db_session, con_permiso=False)

    resultado, _ = entorno.lote(VALIDO, modo="ONLINE")

    assert resultado.error_codigo == "PERMISO_REQUERIDO"
    assert entorno.comandos() == 0


def test_syn06_online_con_permiso_y_contenido_invalido_sigue_rechazando_por_contenido(
    db_session: Session,
) -> None:
    entorno = Entorno(db_session, con_permiso=True)

    resultado, _ = entorno.lote(INVALIDO, modo="ONLINE")

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "CONTENIDO_DE_COMANDO_INVALIDO"
    assert entorno.comandos() == 0


def test_syn10_offline_con_permiso_revocado_y_contenido_valido_entra_con_observacion(
    db_session: Session,
) -> None:
    entorno = Entorno(db_session, con_permiso=False)

    resultado, _ = entorno.lote(VALIDO, modo="OFFLINE")

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert entorno.codigos_de_observacion() == ["PERMISO_REVOCADO"]
    assert entorno.comandos() == 1


def test_syn06_offline_con_permiso_revocado_y_contenido_invalido_se_rechaza_por_contenido(
    db_session: Session,
) -> None:
    """El permiso revocado sin conexión no rechaza ni oculta lo malformado: el comando es
    inválido y no deja fila ni observación."""
    entorno = Entorno(db_session, con_permiso=False)

    resultado, _ = entorno.lote(INVALIDO, modo="OFFLINE")

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "CONTENIDO_DE_COMANDO_INVALIDO"
    assert entorno.comandos() == 0
    assert entorno.codigos_de_observacion() == []
