"""Change 15, tarea 6.1: `JORNADA_RENDIR` v1 y `JORNADA_CERRAR` v1 por el bus contra PostgreSQL
real (spec `stock/jornadas`, requisito "La jornada se rinde y se cierra siguiendo su máquina de
estados"; `design.md` D2, D9; `01` §18, §19).

Se procesa por `sync_service.procesar_comando` (mismo criterio que `test_jornadas_abrir.py`). La
cobertura por HTTP es de `test_jornadas_api.py`.

Reglas citadas: RUT-05, RUT-08, INV-01, INV-06, INV-16, INV-21, SEG-06, AUD-02, SYN-02, TR-06.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

from app.commands import catalogo as catalogo_bus
from app.commands import registro
from app.commands.errores import ContenidoDeComandoInvalidoError
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad.models import Auditoria
from app.modules.stock import jornadas_commands  # noqa: F401  (registra los handlers)
from app.modules.stock.domain.errores import (
    JornadaEstadoInvalidoError,
    RecursoNoEncontradoError,
    UbicacionTomadaError,
)
from app.modules.stock.models import Jornada
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
EN_LA_TARDE = MOMENTO + timedelta(hours=6)
RELOJ = FixedClock(MOMENTO)
ABRIR = "JORNADA_ABRIR"
RENDIR = "JORNADA_RENDIR"
CERRAR = "JORNADA_CERRAR"

VENDEDOR = frozenset({"ABRIR_JORNADA"})
SUPERVISORA = frozenset({"RENDIR_JORNADA", "LIBERAR_UBICACION"})


class Actor:
    def __init__(self, usuario_id: UUID, dispositivo_id: UUID) -> None:
        self.usuario_id = usuario_id
        self.dispositivo_id = dispositivo_id


class Entorno:
    """Una organización con "Camioneta 1" y "Camioneta 2" (con toma), Juan y Pedro (vendedores,
    solo `ABRIR_JORNADA`) y una Supervisora con `RENDIR_JORNADA`."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.juan = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.pedro = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.supervisora = Actor(
            *crear_usuario_y_dispositivo(sesion, self.org, permisos=SUPERVISORA)
        )
        self.camioneta_1 = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.camioneta_2 = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
        )
        sesion.commit()

    def enviar(
        self,
        tipo: str,
        actor: Actor,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
        ocurrio_en: datetime = MOMENTO,
    ) -> Comando:
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            occurred_at=ocurrio_en,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return registrado.funcion(  # type: ignore[call-arg, return-value]
                sobre,
                validado,
                sesion=sesion_protegida,
                reloj=RELOJ,
            )

        return sync_service.procesar_comando(
            self.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    def abrir(self, actor: Actor, ubicacion_id: UUID) -> UUID:
        comando = self.enviar(ABRIR, actor, {"ubicacion_id": str(ubicacion_id)})
        assert comando.resultado is not None
        return UUID(str(comando.resultado["jornada_id"]))

    def rendir(self, jornada_id: UUID, **opciones: Any) -> Comando:
        return self.enviar(
            RENDIR,
            self.supervisora,
            {"jornada_id": str(jornada_id)},
            ocurrio_en=EN_LA_TARDE,
            **opciones,
        )

    def cerrar(self, jornada_id: UUID, **opciones: Any) -> Comando:
        return self.enviar(
            CERRAR,
            self.supervisora,
            {"jornada_id": str(jornada_id)},
            ocurrio_en=EN_LA_TARDE,
            **opciones,
        )

    def terminada(self, estado: str, ubicacion_id: UUID | None = None) -> UUID:
        jornada_id = crear_jornada_sql(
            self.sesion,
            self.org,
            usuario_id=self.juan.usuario_id,
            dispositivo_id=self.juan.dispositivo_id,
            ubicacion_id=ubicacion_id or self.camioneta_1,
            estado=estado,
        )
        self.sesion.commit()
        return jornada_id

    def jornada(self, jornada_id: UUID) -> Jornada:
        self.sesion.rollback()
        return self.sesion.scalars(
            select(Jornada).where(Jornada.organizacion_id == self.org, Jornada.id == jornada_id)
        ).one()

    def cantidad_de_comandos(self, operation_id: UUID) -> int:
        self.sesion.rollback()
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(Comando)
                .where(Comando.operation_id == operation_id)
            )
            or 0
        )

    def auditorias(self, operation_id: UUID) -> list[Auditoria]:
        self.sesion.rollback()
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


# --- catálogo ----------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", [RENDIR, CERRAR])
def test_los_tipos_estan_declarados_online_y_sin_offline_con_handler_v1(tipo: str) -> None:
    """`02` §6.5: rendir y cerrar son solo `ONLINE`."""
    declarado = catalogo_bus.tipo_declarado(tipo)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert registro.resolver_handler(tipo, 1).tipo == tipo


# --- rendir ------------------------------------------------------------------------------


def test_rendir_deja_la_jornada_en_rendicion_con_momento_y_usuario(entorno: Entorno) -> None:
    """Escenario "Rendir una jornada abierta" (`01` §18, RUT-05): la Supervisora rinde la
    jornada de Juan; guarda cuándo y quién."""
    jornada_id = entorno.abrir(entorno.juan, entorno.camioneta_1)

    comando = entorno.rendir(jornada_id)

    assert comando.estado == "ACEPTADO"
    jornada = entorno.jornada(jornada_id)
    assert jornada.estado == "EN_RENDICION"
    assert (jornada.rendida_en, jornada.rendida_por_id) == (
        EN_LA_TARDE,
        entorno.supervisora.usuario_id,
    )
    assert (jornada.cerrada_en, jornada.liberada_en) == (None, None)
    assert comando.resultado is not None
    assert comando.resultado["estado"] == "EN_RENDICION"
    assert comando.resultado["jornada_id"] == str(jornada_id)


def test_inv16_rendir_no_libera_la_ubicacion(entorno: Entorno) -> None:
    """La ubicación sigue tomada durante la rendición (INV-16)."""
    jornada_id = entorno.abrir(entorno.juan, entorno.camioneta_1)
    entorno.rendir(jornada_id)

    with pytest.raises(UbicacionTomadaError):
        entorno.enviar(ABRIR, entorno.pedro, {"ubicacion_id": str(entorno.camioneta_1)})


def test_rendir_dos_veces_se_rechaza_y_no_cambia_la_jornada(entorno: Entorno) -> None:
    """Escenario "Rendir dos veces" (`01` §18)."""
    jornada_id = entorno.abrir(entorno.juan, entorno.camioneta_1)
    entorno.rendir(jornada_id)

    with pytest.raises(JornadaEstadoInvalidoError) as error:
        entorno.rendir(jornada_id)

    assert (error.value.codigo, error.value.status_http) == ("JORNADA_ESTADO_INVALIDO", 409)
    jornada = entorno.jornada(jornada_id)
    assert (jornada.estado, jornada.rendida_en) == ("EN_RENDICION", EN_LA_TARDE)


# --- cerrar ------------------------------------------------------------------------------


def test_cerrar_deja_la_jornada_cerrada_y_libera_la_ubicacion(entorno: Entorno) -> None:
    """Escenario "Cerrar una jornada en rendición libera la ubicación" (RUT-08, INV-16): otro
    usuario puede abrir la misma camioneta."""
    jornada_id = entorno.abrir(entorno.juan, entorno.camioneta_1)
    entorno.rendir(jornada_id)

    comando = entorno.cerrar(jornada_id)

    assert comando.estado == "ACEPTADO"
    jornada = entorno.jornada(jornada_id)
    assert jornada.estado == "CERRADA"
    assert (jornada.cerrada_en, jornada.cerrada_por_id) == (
        EN_LA_TARDE,
        entorno.supervisora.usuario_id,
    )
    otra = entorno.enviar(ABRIR, entorno.pedro, {"ubicacion_id": str(entorno.camioneta_1)})
    assert otra.estado == "ACEPTADO"


def test_cerrar_una_jornada_que_no_se_rindio_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Cerrar una jornada que no se rindió" (`01` §18, D2)."""
    jornada_id = entorno.abrir(entorno.juan, entorno.camioneta_1)

    with pytest.raises(JornadaEstadoInvalidoError):
        entorno.cerrar(jornada_id)

    assert entorno.jornada(jornada_id).estado == "ABIERTA"


@pytest.mark.parametrize("estado", ["CERRADA", "LIBERADA"])
@pytest.mark.parametrize("transicion", ["rendir", "cerrar"])
def test_una_jornada_terminada_no_admite_transiciones(
    entorno: Entorno, estado: str, transicion: str
) -> None:
    """Escenario "Transición sobre una jornada terminada" (`01` §18, TR-06)."""
    jornada_id = entorno.terminada(estado)

    with pytest.raises(JornadaEstadoInvalidoError):
        getattr(entorno, transicion)(jornada_id)

    assert entorno.jornada(jornada_id).estado == estado


# --- permiso y organización ---------------------------------------------------------------


@pytest.mark.parametrize("tipo", [RENDIR, CERRAR])
def test_el_vendedor_no_rinde_ni_cierra_su_propia_jornada(entorno: Entorno, tipo: str) -> None:
    """Escenario "El vendedor no rinde su propia jornada" (RUT-05, SEG-06, `01` §19)."""
    jornada_id = entorno.abrir(entorno.juan, entorno.camioneta_1)
    operation_id = uuid4()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.enviar(
            tipo, entorno.juan, {"jornada_id": str(jornada_id)}, operation_id=operation_id
        )

    assert error.value.status_http == 403
    assert entorno.jornada(jornada_id).estado == "ABIERTA"
    assert entorno.cantidad_de_comandos(operation_id) == 0


@pytest.mark.parametrize("transicion", ["rendir", "cerrar"])
def test_inv21_una_jornada_de_otra_organizacion_o_inexistente_responde_404(
    entorno: Entorno, db_session: Session, transicion: str
) -> None:
    otra_org = crear_organizacion(db_session).id
    otro_usuario, otro_dispositivo = crear_usuario_y_dispositivo(
        db_session, otra_org, permisos=VENDEDOR
    )
    ubicacion_ajena = crear_ubicacion_sql(
        db_session, otra_org, nombre="Ajena", tipo="VEHICULO", requiere_toma=True
    )
    ajena = crear_jornada_sql(
        db_session,
        otra_org,
        usuario_id=otro_usuario,
        dispositivo_id=otro_dispositivo,
        ubicacion_id=ubicacion_ajena,
        estado="EN_RENDICION",
    )
    db_session.commit()

    for jornada_id in (ajena, uuid4()):
        with pytest.raises(RecursoNoEncontradoError) as error:
            getattr(entorno, transicion)(jornada_id)
        assert error.value.status_http == 404


@pytest.mark.parametrize("tipo", [RENDIR, CERRAR])
def test_el_contenido_solo_acepta_la_jornada(entorno: Entorno, tipo: str) -> None:
    """El usuario sale de la sesión; un contenido con otros campos se rechaza (INV-21)."""
    jornada_id = entorno.abrir(entorno.juan, entorno.camioneta_1)

    for extra in ({"usuario_id": str(uuid4())}, {"organizacion_id": str(uuid4())}):
        with pytest.raises(ContenidoDeComandoInvalidoError):
            entorno.enviar(tipo, entorno.supervisora, {"jornada_id": str(jornada_id), **extra})
    assert entorno.jornada(jornada_id).estado == "ABIERTA"


# --- modo, idempotencia y auditoría --------------------------------------------------------


@pytest.mark.parametrize("tipo", [RENDIR, CERRAR])
def test_el_lote_rechaza_la_transicion_enviada_sin_conexion(entorno: Entorno, tipo: str) -> None:
    jornada_id = entorno.abrir(entorno.juan, entorno.camioneta_1)
    operation_id = uuid4()
    item = ItemLote(
        operation_id=operation_id,
        tipo=tipo,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.supervisora.usuario_id,
        dispositivo_id=entorno.supervisora.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={"jornada_id": str(jornada_id)},
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.supervisora.usuario_id,
        dispositivo_id=entorno.supervisora.dispositivo_id,
        items=[item],
    )

    assert (resultado.estado, resultado.error_codigo) == (
        "RECHAZADO",
        "MODO_NO_ADMITIDO_PARA_TIPO",
    )
    assert entorno.jornada(jornada_id).estado == "ABIERTA"
    assert entorno.cantidad_de_comandos(operation_id) == 0


def test_inv06_el_reenvio_del_cierre_devuelve_el_resultado_original(entorno: Entorno) -> None:
    """Escenario "Doble envío del cierre" (SYN-02, INV-06): la jornada sigue `CERRADA` con los
    datos del primer cierre y no se escribe otra auditoría."""
    jornada_id = entorno.abrir(entorno.juan, entorno.camioneta_1)
    entorno.rendir(jornada_id)
    operation_id = uuid4()

    primero = entorno.cerrar(jornada_id, operation_id=operation_id)
    segundo = entorno.enviar(
        CERRAR,
        entorno.supervisora,
        {"jornada_id": str(jornada_id)},
        operation_id=operation_id,
        ocurrio_en=EN_LA_TARDE + timedelta(hours=1),
    )

    assert primero.resultado == segundo.resultado
    jornada = entorno.jornada(jornada_id)
    assert (jornada.estado, jornada.cerrada_en) == ("CERRADA", EN_LA_TARDE)
    assert len(entorno.auditorias(operation_id)) == 1


def test_aud02_cada_comando_deja_una_fila_de_auditoria_sin_motivo(entorno: Entorno) -> None:
    jornada_id = entorno.abrir(entorno.juan, entorno.camioneta_1)
    op_rendir, op_cerrar = uuid4(), uuid4()

    entorno.rendir(jornada_id, operation_id=op_rendir)
    entorno.cerrar(jornada_id, operation_id=op_cerrar)

    for operation_id, accion in ((op_rendir, RENDIR), (op_cerrar, CERRAR)):
        (auditoria,) = entorno.auditorias(operation_id)
        assert auditoria.accion == accion
        assert auditoria.motivo_id is None
        assert auditoria.usuario_id == entorno.supervisora.usuario_id


def test_una_transicion_rechazada_no_deja_auditoria(entorno: Entorno) -> None:
    jornada_id = entorno.abrir(entorno.juan, entorno.camioneta_1)
    operation_id = uuid4()

    with pytest.raises(JornadaEstadoInvalidoError):
        entorno.cerrar(jornada_id, operation_id=operation_id)

    assert entorno.auditorias(operation_id) == []
    assert entorno.cantidad_de_comandos(operation_id) == 0
