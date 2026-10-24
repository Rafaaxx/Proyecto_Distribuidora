"""Change 15, tarea 5.1 (`design.md` D12): el bus ante una `jornada_id` inexistente.

Antes de reservar el `operation_id`, `procesar_comando` pregunta a `stock` si la jornada del
sobre existe en la organización. Si no, `JORNADA_INEXISTENTE`: en el lote el ítem queda
`RECHAZADO` sin fila de `comando` y el lote sigue; por REST responde 404. El bus NO evalúa el
dueño ni el estado de la jornada (eso es regla de cada comando de ruta). La FK
`fk_comando__jornada` queda como red de seguridad.

Un tipo de prueba aislado por `monkeypatch` (mismo patrón que `test_bus_lote_sincronizacion.py`)
permite correr el lote completo con handlers que no dependen de stock.

Reglas citadas: SYN-04, SYN-06, INV-06, INV-21.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

from app.commands import catalogo, registro
from app.commands.errores import JornadaInexistenteError
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote

MOMENTO = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
TIPO = "PRUEBA_JORNADA_DEL_SOBRE"


class _Esquema(BaseModel):
    etiqueta: str | None = None


def _handler(
    sobre: SobreComando, contenido: _Esquema, *, sesion: object, reloj: object
) -> tuple[str, dict[str, object], None]:
    return "ACEPTADO", {"etiqueta": contenido.etiqueta}, None


@pytest.fixture(autouse=True)
def _catalogo_y_registro_aislados(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})
    monkeypatch.setattr("app.commands.registro._REGISTRO", {})
    catalogo.declarar_tipo(
        TIPO, admite_online=True, admite_offline=True, permisos=("REGISTRAR_COBRANZA",)
    )
    registro.registrar_handler(TIPO, 1, _Esquema)(_handler)


class Entorno:
    """Dos organizaciones; en la A, un vendedor (Juan) con una jornada propia y una jornada
    `CERRADA` de otro usuario; en la B, una jornada `ABIERTA`."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=frozenset({"REGISTRAR_COBRANZA"})
        )
        pedro, dispositivo_pedro = crear_usuario_y_dispositivo(sesion, self.org)
        vehiculo = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.jornada_propia = crear_jornada_sql(
            sesion,
            self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            ubicacion_id=vehiculo,
        )
        self.jornada_cerrada_de_otro = crear_jornada_sql(
            sesion,
            self.org,
            usuario_id=pedro,
            dispositivo_id=dispositivo_pedro,
            ubicacion_id=vehiculo,
            estado="CERRADA",
        )
        org_ajena = crear_organizacion(sesion).id
        usuario_ajeno, dispositivo_ajeno = crear_usuario_y_dispositivo(sesion, org_ajena)
        self.jornada_ajena = crear_jornada_sql(
            sesion,
            org_ajena,
            usuario_id=usuario_ajeno,
            dispositivo_id=dispositivo_ajeno,
            ubicacion_id=crear_ubicacion_sql(
                sesion, org_ajena, nombre="Camioneta B", tipo="VEHICULO", requiere_toma=True
            ),
        )
        sesion.commit()

    def item(
        self, secuencia: int, jornada_id: UUID | None = None, operation_id: UUID | None = None
    ) -> ItemLote:
        return ItemLote(
            operation_id=operation_id or uuid4(),
            tipo=TIPO,
            version=1,
            modo="ONLINE",
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=secuencia,
            app_version="1.0.0",
            contenido={"etiqueta": f"seq-{secuencia}"},
            jornada_id=jornada_id,
        )

    def lote(self, *items: ItemLote) -> list[sync_service.ResultadoItemLote]:
        return sync_service.procesar_lote(
            self.sesion,
            RELOJ,
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            items=list(items),
        )

    def comandos(self, operation_id: UUID) -> list[Comando]:
        self.sesion.rollback()
        return list(
            self.sesion.scalars(select(Comando).where(Comando.operation_id == operation_id)).all()
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


@pytest.mark.parametrize("origen", ["inexistente", "de_otra_organizacion"])
def test_syn06_un_item_con_una_jornada_que_no_existe_se_rechaza_y_el_lote_sigue(
    entorno: Entorno, origen: str
) -> None:
    """SYN-06, SYN-04, INV-21: `RECHAZADO` con `JORNADA_INEXISTENTE`, sin fila de `comando`
    (reintentable), y el ítem siguiente del lote se procesa. Una jornada de otra organización
    responde igual que una que no existe."""
    jornada = uuid4() if origen == "inexistente" else entorno.jornada_ajena
    malo = entorno.item(1, jornada)
    bueno = entorno.item(2)

    resultados = entorno.lote(malo, bueno)

    por_id = {r.operation_id: r for r in resultados}
    assert (por_id[malo.operation_id].estado, por_id[malo.operation_id].error_codigo) == (
        "RECHAZADO",
        "JORNADA_INEXISTENTE",
    )
    assert por_id[bueno.operation_id].estado == "ACEPTADO"
    assert entorno.comandos(malo.operation_id) == []
    assert len(entorno.comandos(bueno.operation_id)) == 1


def test_un_comando_con_una_jornada_existente_queda_registrado_con_ella(
    entorno: Entorno,
) -> None:
    item = entorno.item(1, entorno.jornada_propia)

    (resultado,) = entorno.lote(item)

    assert resultado.estado == "ACEPTADO"
    (comando,) = entorno.comandos(item.operation_id)
    assert comando.jornada_id == entorno.jornada_propia


def test_el_bus_no_evalua_el_dueno_ni_el_estado_de_la_jornada(entorno: Entorno) -> None:
    """D12: una jornada `CERRADA` de otro usuario de la organización existe, y alcanza."""
    item = entorno.item(1, entorno.jornada_cerrada_de_otro)

    (resultado,) = entorno.lote(item)

    assert resultado.estado == "ACEPTADO"
    (comando,) = entorno.comandos(item.operation_id)
    assert comando.jornada_id == entorno.jornada_cerrada_de_otro


def test_un_comando_sin_jornada_no_cambia_y_no_consulta(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas: list[Any] = []

    def espiar(*args: Any, **kwargs: Any) -> bool:
        llamadas.append(args)
        return True

    monkeypatch.setattr(sync_service.stock_service, "existe_jornada", espiar)
    item = entorno.item(1)

    (resultado,) = entorno.lote(item)

    assert resultado.estado == "ACEPTADO"
    assert llamadas == []
    (comando,) = entorno.comandos(item.operation_id)
    assert comando.jornada_id is None


def test_inv06_el_doble_envio_con_jornada_devuelve_el_resultado_original(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()

    item = entorno.item(1, entorno.jornada_propia, operation_id)
    (primero,) = entorno.lote(item)
    (segundo,) = entorno.lote(item)

    assert (primero.estado, segundo.estado) == ("ACEPTADO", "ACEPTADO")
    assert primero.resultado == segundo.resultado
    assert len(entorno.comandos(operation_id)) == 1


def test_por_rest_una_jornada_inexistente_es_404_sin_reserva(entorno: Entorno) -> None:
    """El camino REST (`procesar_comando`) propaga el error de dominio: 404."""
    operation_id = uuid4()
    sobre = SobreComando(
        operation_id=operation_id,
        tipo=TIPO,
        version=1,
        modo="ONLINE",
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="server",
        contenido={"etiqueta": "x"},
        jornada_id=entorno.jornada_ajena,
    )

    with pytest.raises(JornadaInexistenteError) as error:
        sync_service.procesar_comando(
            entorno.sesion,
            RELOJ,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=lambda _s: ("ACEPTADO", {}, None),
        )

    assert (error.value.codigo, error.value.status_http) == ("JORNADA_INEXISTENTE", 404)
    assert entorno.comandos(operation_id) == []
    assert (
        entorno.sesion.scalar(
            select(func.count()).select_from(Comando).where(Comando.organizacion_id == entorno.org)
        )
        == 0
    )
