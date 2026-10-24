"""Change 17, tareas 2.1 y 2.2: despacho por el lote de los handlers reales
(spec `sistema/pipeline-de-comandos`, requisito "Un comando se ejecuta igual por
REST y por el lote"; `design.md` D9, D10; ADR-048 punto 5, ADR-049 punto 19).

Hasta este change `_procesar_item_de_lote` llamaba `funcion(sobre, contenido)` sin
sesión ni reloj: ningún handler real funcionaba por el lote, ni siquiera en modo
`ONLINE`. Se despacha por `sync_service.procesar_lote` contra PostgreSQL real.

Reglas citadas: `02` §6.1, `02` §5.2 (los handlers no hacen commit), SYN-02, SYN-06,
INV-01, INV-21.
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
from stock_utiles import (
    crear_jornada_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

import app.main  # noqa: F401  (registra todos los handlers de producción)
from app.commands import catalogo, registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import Clock, FixedClock
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeStockInicial
from app.modules.stock.models import Jornada, StockMovimiento, Transferencia
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import HandlerNoPuedeConfirmarError, ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


class Entorno:
    """Una organización con Vino A (120 unidades en el depósito), dos camionetas con toma,
    un usuario con `TRANSFERIR_STOCK` y una supervisora con `RENDIR_JORNADA`."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=frozenset({"TRANSFERIR_STOCK"})
        )
        self.supervisora_id, self.dispositivo_supervisora_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=frozenset({"RENDIR_JORNADA"})
        )
        self.vino_id = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
        self.camioneta_id = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.camioneta_2_id = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
        )
        stock_service.registrar_stock_inicial(
            self.org,
            sesion,
            RELOJ,
            ubicacion_id=self.deposito_id,
            lineas=[LineaDeStockInicial(self.vino_id, 120, "1050")],
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
        )
        sesion.commit()

    def item(
        self,
        tipo: str,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
        usuario_id: UUID | None = None,
        dispositivo_id: UUID | None = None,
        version: int = 1,
    ) -> ItemLote:
        return ItemLote(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=version,
            modo="ONLINE",
            usuario_id=usuario_id or self.usuario_id,
            dispositivo_id=dispositivo_id or self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )

    def por_el_lote(self, item: ItemLote) -> sync_service.ResultadoItemLote:
        resultados = sync_service.procesar_lote(
            self.sesion,
            RELOJ,
            organizacion_id=self.org,
            usuario_id=item.usuario_id,
            dispositivo_id=item.dispositivo_id,
            items=[item],
        )
        assert len(resultados) == 1
        return resultados[0]

    def por_rest(self, item: ItemLote) -> Comando:
        """Lo que hace cada `api.py`: `procesar_comando` con un envoltorio que pasa la
        sesión protegida y el reloj al handler registrado."""
        sobre = SobreComando(
            operation_id=item.operation_id,
            tipo=item.tipo,
            version=item.version,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=item.usuario_id,
            dispositivo_id=item.dispositivo_id,
            occurred_at=item.occurred_at,
            secuencia=1,
            app_version="1.0.0",
            contenido=item.contenido,
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: registro.SesionDeHandler) -> sync_service.ResultadoHandler:
            return registrado.funcion(  # type: ignore[return-value]
                sobre, validado, sesion=sesion_protegida, reloj=RELOJ
            )

        return sync_service.procesar_comando(
            self.sesion,
            RELOJ,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def movimientos_de(self, operation_id: UUID) -> list[tuple[UUID, int]]:
        filas = self.sesion.execute(
            select(StockMovimiento.ubicacion_id, StockMovimiento.cantidad_base)
            .where(
                StockMovimiento.organizacion_id == self.org,
                StockMovimiento.operation_id == operation_id,
            )
            .order_by(StockMovimiento.cantidad_base)
        ).all()
        return [(fila[0], fila[1]) for fila in filas]


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _transferencia(entorno: Entorno, destino: UUID, cantidad: int) -> dict[str, Any]:
    return {
        "ubicacion_origen_id": str(entorno.deposito_id),
        "ubicacion_destino_id": str(destino),
        "lineas": [{"producto_id": str(entorno.vino_id), "cantidad_base": cantidad}],
    }


class TestTransferenciaPorElLoteEnModoOnline:
    """Escenario "Una transferencia por el lote en modo ONLINE" (`02` §6.1; ADR-048
    punto 5)."""

    def test_se_acepta_y_mueve_el_stock(self, entorno: Entorno) -> None:
        item = entorno.item("STOCK_TRANSFERIR", _transferencia(entorno, entorno.camioneta_id, 48))

        resultado = entorno.por_el_lote(item)

        assert resultado.estado == "ACEPTADO", resultado
        assert resultado.error_codigo is None
        assert sorted(entorno.movimientos_de(item.operation_id), key=lambda m: m[1]) == [
            (entorno.deposito_id, -48),
            (entorno.camioneta_id, 48),
        ]

    def test_deja_los_mismos_movimientos_que_por_rest(self, entorno: Entorno) -> None:
        por_lote = entorno.item(
            "STOCK_TRANSFERIR", _transferencia(entorno, entorno.camioneta_id, 30)
        )
        por_rest = entorno.item(
            "STOCK_TRANSFERIR", _transferencia(entorno, entorno.camioneta_2_id, 30)
        )

        resultado_lote = entorno.por_el_lote(por_lote)
        comando_rest = entorno.por_rest(por_rest)

        assert resultado_lote.estado == comando_rest.estado == "ACEPTADO"
        assert resultado_lote.resultado is not None and comando_rest.resultado is not None
        assert set(resultado_lote.resultado) == set(comando_rest.resultado)
        por_lote_mov = entorno.movimientos_de(por_lote.operation_id)
        por_rest_mov = entorno.movimientos_de(por_rest.operation_id)
        assert [cantidad for _, cantidad in por_lote_mov] == [
            cantidad for _, cantidad in por_rest_mov
        ]
        assert len(por_lote_mov) == 2
        cantidad_de_transferencias = entorno.sesion.scalar(
            select(func.count())
            .select_from(Transferencia)
            .where(Transferencia.organizacion_id == entorno.org)
        )
        assert cantidad_de_transferencias == 2

    def test_un_reenvio_idempotente_no_repite_el_movimiento(self, entorno: Entorno) -> None:
        item = entorno.item("STOCK_TRANSFERIR", _transferencia(entorno, entorno.camioneta_id, 10))

        primero = entorno.por_el_lote(item)
        segundo = entorno.por_el_lote(item)

        assert primero.estado == segundo.estado == "ACEPTADO"
        assert len(entorno.movimientos_de(item.operation_id)) == 2


class TestTransicionDeJornadaPorElLote:
    """Escenario "Una transición de jornada por el lote" (`02` §6.1; ADR-049
    punto 19)."""

    def test_rendir_pasa_la_jornada_a_en_rendicion(self, entorno: Entorno) -> None:
        jornada_id = crear_jornada_sql(
            entorno.sesion,
            entorno.org,
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
            ubicacion_id=entorno.camioneta_id,
        )
        entorno.sesion.commit()
        item = entorno.item(
            "JORNADA_RENDIR",
            {"jornada_id": str(jornada_id)},
            usuario_id=entorno.supervisora_id,
            dispositivo_id=entorno.dispositivo_supervisora_id,
        )

        resultado = entorno.por_el_lote(item)

        assert resultado.estado == "ACEPTADO", resultado
        estado = entorno.sesion.scalar(
            select(Jornada.estado).where(
                Jornada.organizacion_id == entorno.org, Jornada.id == jornada_id
            )
        )
        assert estado == "EN_RENDICION"

    def test_rendir_una_jornada_inexistente_se_rechaza_con_su_codigo(
        self, entorno: Entorno
    ) -> None:
        item = entorno.item(
            "JORNADA_RENDIR",
            {"jornada_id": str(uuid4())},
            usuario_id=entorno.supervisora_id,
            dispositivo_id=entorno.dispositivo_supervisora_id,
        )

        resultado = entorno.por_el_lote(item)

        assert resultado.estado == "RECHAZADO"
        assert resultado.error_codigo is not None


class _EsquemaVacio(BaseModel):
    pass


class TestUnHandlerNoConfirmaPorElLote:
    """Escenario "Un handler no confirma la transacción por el lote" (`02` §5.2)."""

    @pytest.fixture(autouse=True)
    def _handlers_que_confirman(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.commands.catalogo._CATALOGO", dict(catalogo._CATALOGO))
        monkeypatch.setattr("app.commands.registro._REGISTRO", dict(registro._REGISTRO))
        catalogo.declarar_tipo(
            "PRUEBA_CONFIRMA",
            admite_online=True,
            admite_offline=False,
            sin_permiso="tipo de prueba",
        )
        catalogo.declarar_tipo(
            "PRUEBA_REVIERTE",
            admite_online=True,
            admite_offline=False,
            sin_permiso="tipo de prueba",
        )

        @registro.registrar_handler("PRUEBA_CONFIRMA", 1, _EsquemaVacio)
        def _confirma(
            sobre: SobreComando,
            contenido: _EsquemaVacio,
            *,
            sesion: registro.SesionDeHandler,
            reloj: Clock,
        ) -> tuple[str, dict[str, object] | None, str | None]:
            sesion.commit()
            return "ACEPTADO", None, None

        @registro.registrar_handler("PRUEBA_REVIERTE", 1, _EsquemaVacio)
        def _revierte(
            sobre: SobreComando,
            contenido: _EsquemaVacio,
            *,
            sesion: registro.SesionDeHandler,
            reloj: Clock,
        ) -> tuple[str, dict[str, object] | None, str | None]:
            sesion.rollback()
            return "ACEPTADO", None, None

    @pytest.mark.parametrize("tipo", ["PRUEBA_CONFIRMA", "PRUEBA_REVIERTE"])
    def test_la_confirmacion_es_un_error_de_programacion_que_aborta_el_lote(
        self, entorno: Entorno, tipo: str
    ) -> None:
        """Un handler que intenta `commit`, `rollback` o `close` es un error de programación:
        `HandlerNoPuedeConfirmarError` aborta TODA la petición del lote (error interno) y NO se
        convierte en `RECHAZADO` (decisión del usuario, 2026-10-16; `02` §5.2). No queda el
        comando."""
        item = entorno.item(tipo, {})

        with pytest.raises(HandlerNoPuedeConfirmarError):
            entorno.por_el_lote(item)

        entorno.sesion.rollback()
        comandos = entorno.sesion.scalar(
            select(func.count())
            .select_from(Comando)
            .where(
                Comando.organizacion_id == entorno.org,
                Comando.operation_id == item.operation_id,
            )
        )
        assert comandos == 0


class TestContenidoInvalidoNuncaEsUnErrorInterno:
    """Escenario "Todos los tipos registrados se pueden despachar por el lote" (SYN-06;
    `02` §6.3)."""

    def test_el_registro_de_produccion_trae_los_handlers_reales(self) -> None:
        assert len(registro._REGISTRO) >= 54

    @pytest.mark.parametrize(
        "contenido_invalido",
        [{"__campo_que_ningun_esquema_acepta__": [1, 2, 3]}, {}],
        ids=["campo_desconocido", "vacio"],
    )
    def test_cada_tipo_con_contenido_invalido_responde_un_rechazo(
        self, entorno: Entorno, contenido_invalido: dict[str, Any]
    ) -> None:
        resultados: dict[tuple[str, int], tuple[str, str | None]] = {}

        for tipo, version in sorted(registro._REGISTRO):
            item = entorno.item(tipo, contenido_invalido, version=version)
            resultado = entorno.por_el_lote(item)
            resultados[(tipo, version)] = (resultado.estado, resultado.error_codigo)
            entorno.sesion.rollback()

        sin_rechazo = {c: v for c, v in resultados.items() if v[0] != "RECHAZADO"}
        assert sin_rechazo == {}
        sin_codigo = [clave for clave, (_, codigo) in resultados.items() if not codigo]
        assert sin_codigo == []
