"""Change 15, tarea 7.1: `JORNADA_LIBERAR` v1 por el bus contra PostgreSQL real (spec
`stock/jornadas`, requisito "Liberar una jornada con motivo" y los escenarios de atomicidad de
"Una jornada se registra completa y no se borra"; `design.md` D9, D13).

La fila de auditoría con el motivo es de la tarea 7.2 (gobernanza crítica, D8): acá no se la
prueba. La cobertura por HTTP está en `test_jornadas_api.py`.

Reglas citadas: RUT-09, TR-09, INV-01, INV-06, INV-16, INV-21, SEG-06, SYN-02, `01` §18, §19.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_jornada_sql,
    crear_motivo_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

from app.commands import catalogo as catalogo_bus
from app.commands import registro
from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad.models import Auditoria
from app.modules.stock import jornadas_commands
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    JornadaEstadoInvalidoError,
    MotivoInvalidoError,
    ObservacionInvalidaError,
    RecursoNoEncontradoError,
    UbicacionTomadaError,
)
from app.modules.stock.domain.movimientos import LineaDeStockInicial
from app.modules.stock.models import Jornada
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
EN_LA_TARDE = MOMENTO + timedelta(hours=6)
RELOJ = FixedClock(MOMENTO)
ABRIR = "JORNADA_ABRIR"
LIBERAR = "JORNADA_LIBERAR"

VENDEDOR = frozenset({"ABRIR_JORNADA"})
SUPERVISORA = frozenset({"RENDIR_JORNADA", "LIBERAR_UBICACION"})
ADMINISTRACION = frozenset({"RENDIR_JORNADA"})
VENDEDOR_QUE_LIBERA = frozenset({"ABRIR_JORNADA", "LIBERAR_UBICACION"})


class Actor:
    def __init__(self, usuario_id: UUID, dispositivo_id: UUID) -> None:
        self.usuario_id = usuario_id
        self.dispositivo_id = dispositivo_id


class Entorno:
    """ "Camioneta 1" con 48 unidades de Vino A; Juan y Pedro (vendedores), un vendedor que
    además puede liberar, una Supervisora (`LIBERAR_UBICACION`) y una Administración (sin
    `LIBERAR_UBICACION`); y los motivos: uno activo, uno inactivo y uno de otro ámbito."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.juan = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.pedro = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.vendedor_que_libera = Actor(
            *crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR_QUE_LIBERA)
        )
        self.supervisora = Actor(
            *crear_usuario_y_dispositivo(sesion, self.org, permisos=SUPERVISORA)
        )
        self.administracion = Actor(
            *crear_usuario_y_dispositivo(sesion, self.org, permisos=ADMINISTRACION)
        )
        self.camioneta_1 = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.vino_id = crear_producto_sql(sesion, self.org, nombre="Vino A")
        stock_service.registrar_stock_inicial(
            self.org,
            sesion,
            RELOJ,
            ubicacion_id=self.camioneta_1,
            lineas=[LineaDeStockInicial(self.vino_id, 48, "1050")],
            usuario_id=self.juan.usuario_id,
            dispositivo_id=self.juan.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
        )
        self.motivo = crear_motivo_sql(
            sesion, self.org, ambito="LIBERACION_JORNADA", nombre="Dispositivo perdido o averiado"
        )
        self.motivo_inactivo = crear_motivo_sql(
            sesion, self.org, ambito="LIBERACION_JORNADA", activo=False
        )
        self.motivo_de_ajuste = crear_motivo_sql(sesion, self.org, ambito="AJUSTE_STOCK")
        sesion.commit()

    def enviar(
        self,
        tipo: str,
        actor: Actor,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
    ) -> Comando:
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            occurred_at=EN_LA_TARDE,
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

    def abrir_juan(self) -> UUID:
        comando = self.enviar(ABRIR, self.juan, {"ubicacion_id": str(self.camioneta_1)})
        assert comando.resultado is not None
        return UUID(str(comando.resultado["jornada_id"]))

    def liberar(
        self,
        jornada_id: UUID,
        *,
        motivo_id: UUID | None = None,
        actor: Actor | None = None,
        operation_id: UUID | None = None,
        **extra: Any,
    ) -> Comando:
        return self.enviar(
            LIBERAR,
            actor or self.supervisora,
            {"jornada_id": str(jornada_id), "motivo_id": str(motivo_id or self.motivo), **extra},
            operation_id=operation_id,
        )

    def sembrada(self, estado: str) -> UUID:
        jornada_id = crear_jornada_sql(
            self.sesion,
            self.org,
            usuario_id=self.juan.usuario_id,
            dispositivo_id=self.juan.dispositivo_id,
            ubicacion_id=self.camioneta_1,
            estado=estado,
        )
        self.sesion.commit()
        return jornada_id

    def jornada(self, jornada_id: UUID) -> Jornada:
        self.sesion.rollback()
        return self.sesion.scalars(
            select(Jornada).where(Jornada.organizacion_id == self.org, Jornada.id == jornada_id)
        ).one()

    def saldo(self) -> int:
        self.sesion.rollback()
        return stock_service.obtener_saldo(
            self.org, self.sesion, producto_id=self.vino_id, ubicacion_id=self.camioneta_1
        )

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


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def test_el_tipo_esta_declarado_online_y_sin_offline_con_handler_v1() -> None:
    declarado = catalogo_bus.tipo_declarado(LIBERAR)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert registro.resolver_handler(LIBERAR, 1).tipo == LIBERAR


# --- escenarios felices --------------------------------------------------------------------


def test_liberar_una_jornada_abierta_deja_libre_la_ubicacion_con_su_stock(
    entorno: Entorno,
) -> None:
    """Escenario "Liberación de una jornada abierta" (RUT-09): momento, usuario y motivo
    guardados; la camioneta conserva sus 48 unidades y vuelve a poder abrirse."""
    jornada_id = entorno.abrir_juan()

    comando = entorno.liberar(jornada_id, observacion="  Lo dejó en un comercio  ")

    assert comando.estado == "ACEPTADO"
    jornada = entorno.jornada(jornada_id)
    assert jornada.estado == "LIBERADA"
    assert (jornada.liberada_en, jornada.liberada_por_id, jornada.motivo_liberacion_id) == (
        EN_LA_TARDE,
        entorno.supervisora.usuario_id,
        entorno.motivo,
    )
    assert jornada.observacion_liberacion == "Lo dejó en un comercio"
    assert entorno.saldo() == 48
    otra = entorno.enviar(ABRIR, entorno.pedro, {"ubicacion_id": str(entorno.camioneta_1)})
    assert otra.estado == "ACEPTADO"
    assert comando.resultado is not None
    assert comando.resultado["estado"] == "LIBERADA"
    assert comando.resultado["motivo_liberacion_id"] == str(entorno.motivo)


def test_liberar_una_jornada_en_rendicion(entorno: Entorno) -> None:
    """Escenario "Liberación de una jornada en rendición" (`01` §18)."""
    jornada_id = entorno.sembrada("EN_RENDICION")

    entorno.liberar(jornada_id)

    assert entorno.jornada(jornada_id).estado == "LIBERADA"


def test_una_observacion_vacia_se_guarda_como_nula(entorno: Entorno) -> None:
    jornada_id = entorno.abrir_juan()

    entorno.liberar(jornada_id, observacion="   ")

    assert entorno.jornada(jornada_id).observacion_liberacion is None


def test_quien_tiene_la_jornada_tambien_puede_liberar_la_suya(entorno: Entorno) -> None:
    """D13: vale sobre la jornada de cualquier usuario, incluida la propia."""
    comando = entorno.enviar(
        ABRIR, entorno.vendedor_que_libera, {"ubicacion_id": str(entorno.camioneta_1)}
    )
    assert comando.resultado is not None
    jornada_id = UUID(str(comando.resultado["jornada_id"]))

    liberada = entorno.liberar(jornada_id, actor=entorno.vendedor_que_libera)

    assert liberada.estado == "ACEPTADO"
    assert entorno.jornada(jornada_id).liberada_por_id == entorno.vendedor_que_libera.usuario_id


# --- permiso, motivo y organización ---------------------------------------------------------


def test_sin_liberar_ubicacion_responde_403_y_no_cambia_la_jornada(entorno: Entorno) -> None:
    """Escenario "Liberación sin permiso" (RUT-09, `01` §19): Administración tiene
    `RENDIR_JORNADA` pero no `LIBERAR_UBICACION`."""
    jornada_id = entorno.abrir_juan()
    operation_id = uuid4()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.liberar(jornada_id, actor=entorno.administracion, operation_id=operation_id)

    assert error.value.status_http == 403
    assert entorno.jornada(jornada_id).estado == "ABIERTA"
    assert entorno.cantidad_de_comandos(operation_id) == 0


@pytest.mark.parametrize("motivo", ["motivo_inactivo", "motivo_de_ajuste"])
def test_tr09_un_motivo_inactivo_o_de_otro_ambito_se_rechaza(entorno: Entorno, motivo: str) -> None:
    """Escenario "Motivo inactivo o de otro ámbito" (TR-09, RUT-09)."""
    jornada_id = entorno.abrir_juan()

    with pytest.raises(MotivoInvalidoError) as error:
        entorno.liberar(jornada_id, motivo_id=getattr(entorno, motivo))

    assert (error.value.codigo, error.value.status_http) == ("MOTIVO_INVALIDO", 422)
    assert entorno.jornada(jornada_id).estado == "ABIERTA"


def test_inv21_un_motivo_de_otra_organizacion_o_inexistente_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    jornada_id = entorno.abrir_juan()
    ajeno = crear_motivo_sql(
        db_session, crear_organizacion(db_session).id, ambito="LIBERACION_JORNADA"
    )
    db_session.commit()

    for motivo_id in (ajeno, uuid4()):
        with pytest.raises(RecursoNoEncontradoError) as error:
            entorno.liberar(jornada_id, motivo_id=motivo_id)
        assert error.value.status_http == 404
    assert entorno.jornada(jornada_id).estado == "ABIERTA"


def test_inv21_una_jornada_de_otra_organizacion_o_inexistente_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    otra_org = crear_organizacion(db_session).id
    usuario, dispositivo = crear_usuario_y_dispositivo(db_session, otra_org, permisos=VENDEDOR)
    ajena = crear_jornada_sql(
        db_session,
        otra_org,
        usuario_id=usuario,
        dispositivo_id=dispositivo,
        ubicacion_id=crear_ubicacion_sql(
            db_session, otra_org, nombre="Ajena", tipo="VEHICULO", requiere_toma=True
        ),
    )
    db_session.commit()

    for jornada_id in (ajena, uuid4()):
        with pytest.raises(RecursoNoEncontradoError):
            entorno.liberar(jornada_id)


# --- estado y observación ---------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["CERRADA", "LIBERADA"])
def test_liberar_una_jornada_terminada_se_rechaza(entorno: Entorno, estado: str) -> None:
    """Escenario "Liberar una jornada ya terminada" (`01` §18)."""
    jornada_id = entorno.sembrada(estado)

    with pytest.raises(JornadaEstadoInvalidoError):
        entorno.liberar(jornada_id)

    assert entorno.jornada(jornada_id).estado == estado


def test_una_observacion_de_501_caracteres_se_rechaza_y_una_de_500_se_acepta(
    entorno: Entorno,
) -> None:
    """Escenario "Observación demasiado larga" (D13)."""
    jornada_id = entorno.abrir_juan()

    with pytest.raises(ObservacionInvalidaError) as error:
        entorno.liberar(jornada_id, observacion="x" * 501)

    assert (error.value.codigo, error.value.status_http) == ("OBSERVACION_INVALIDA", 422)
    assert entorno.jornada(jornada_id).estado == "ABIERTA"
    entorno.liberar(jornada_id, observacion="x" * 500)
    assert entorno.jornada(jornada_id).estado == "LIBERADA"


def test_el_contenido_no_acepta_usuario_ni_organizacion(entorno: Entorno) -> None:
    jornada_id = entorno.abrir_juan()

    for extra in ({"usuario_id": str(uuid4())}, {"organizacion_id": str(uuid4())}):
        with pytest.raises(ContenidoDeComandoInvalidoError):
            entorno.liberar(jornada_id, **extra)


# --- modo, idempotencia y atomicidad ------------------------------------------------------------


def test_el_lote_rechaza_la_liberacion_enviada_sin_conexion(entorno: Entorno) -> None:
    jornada_id = entorno.abrir_juan()
    operation_id = uuid4()
    item = ItemLote(
        operation_id=operation_id,
        tipo=LIBERAR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.supervisora.usuario_id,
        dispositivo_id=entorno.supervisora.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={"jornada_id": str(jornada_id), "motivo_id": str(entorno.motivo)},
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


def test_inv06_el_reenvio_devuelve_el_resultado_original(entorno: Entorno) -> None:
    """Escenario "Doble envío de la liberación" (SYN-02, INV-06)."""
    jornada_id = entorno.abrir_juan()
    operation_id = uuid4()

    primero = entorno.liberar(jornada_id, operation_id=operation_id)
    segundo = entorno.liberar(jornada_id, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert entorno.jornada(jornada_id).estado == "LIBERADA"


def test_inv06_el_mismo_operation_id_con_otro_motivo_es_inconsistente(
    entorno: Entorno,
) -> None:
    jornada_id = entorno.abrir_juan()
    operation_id = uuid4()
    entorno.liberar(jornada_id, operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.liberar(jornada_id, motivo_id=entorno.motivo_inactivo, operation_id=operation_id)


def test_inv01_una_falla_antes_de_confirmar_deja_la_jornada_abierta(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Falla en medio de la liberación": la jornada sigue `ABIERTA`, la ubicación
    sigue tomada (INV-16) y el `operation_id` puede reintentarse."""
    jornada_id = entorno.abrir_juan()
    operation_id = uuid4()

    def fallar(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("falla inyectada después de liberar")

    monkeypatch.setattr(jornadas_commands, "resultado_de_jornada", fallar)
    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.liberar(jornada_id, operation_id=operation_id)

    assert entorno.jornada(jornada_id).estado == "ABIERTA"
    assert entorno.cantidad_de_comandos(operation_id) == 0
    with pytest.raises(UbicacionTomadaError):
        entorno.enviar(ABRIR, entorno.pedro, {"ubicacion_id": str(entorno.camioneta_1)})
    monkeypatch.undo()
    entorno.liberar(jornada_id, operation_id=operation_id)
    assert entorno.jornada(jornada_id).estado == "LIBERADA"


@pytest.mark.parametrize(
    "faltantes",
    [
        {"liberada_por_id", "motivo_liberacion_id"},
        {"motivo_liberacion_id"},
        {"liberada_por_id"},
        {"liberada_en"},
    ],
    ids=["sin_usuario_ni_motivo", "sin_motivo", "sin_usuario", "sin_momento"],
)
def test_la_base_rechaza_una_liberada_sin_motivo_usuario_o_momento(
    entorno: Entorno, faltantes: set[str]
) -> None:
    """Escenario "La base rechaza un estado incoherente" (RUT-09, D10)."""
    jornada_id = entorno.sembrada("ABIERTA")
    valores: dict[str, object] = {
        "liberada_en": EN_LA_TARDE,
        "liberada_por_id": entorno.supervisora.usuario_id,
        "motivo_liberacion_id": entorno.motivo,
    }
    asignaciones = ", ".join(f"{c} = :{c}" for c in valores if c not in faltantes)

    with pytest.raises(IntegrityError) as error:
        entorno.sesion.execute(
            text(f"UPDATE jornada SET estado = 'LIBERADA', {asignaciones} WHERE id = :id"),
            {**{c: v for c, v in valores.items() if c not in faltantes}, "id": jornada_id},
        )
    assert "ck_jornada__estado_coherente" in str(error.value)
    entorno.sesion.rollback()


# --- auditoría de las transiciones (tarea 7.2, D8; AUD-01, AUD-02) -----------------


def _auditorias_de(entorno: Entorno, operation_id: UUID) -> list[Auditoria]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Auditoria).where(
                Auditoria.organizacion_id == entorno.org, Auditoria.operation_id == operation_id
            )
        ).all()
    )


def test_aud01_aud02_la_liberacion_deja_una_fila_con_el_motivo(entorno: Entorno) -> None:
    jornada_id = entorno.abrir_juan()
    operation_id = uuid4()

    entorno.liberar(jornada_id, operation_id=operation_id)

    (auditoria,) = _auditorias_de(entorno, operation_id)
    assert (auditoria.accion, auditoria.motivo_id) == (LIBERAR, entorno.motivo)
    assert auditoria.usuario_id == entorno.supervisora.usuario_id


def test_aud02_apertura_rendicion_y_cierre_no_llevan_motivo(entorno: Entorno) -> None:
    op_abrir, op_rendir, op_cerrar = uuid4(), uuid4(), uuid4()
    comando = entorno.enviar(
        ABRIR, entorno.juan, {"ubicacion_id": str(entorno.camioneta_1)}, operation_id=op_abrir
    )
    assert comando.resultado is not None
    jornada_id = comando.resultado["jornada_id"]
    entorno.enviar(
        "JORNADA_RENDIR", entorno.supervisora, {"jornada_id": jornada_id}, operation_id=op_rendir
    )
    entorno.enviar(
        "JORNADA_CERRAR", entorno.supervisora, {"jornada_id": jornada_id}, operation_id=op_cerrar
    )

    for operation_id, accion in (
        (op_abrir, ABRIR),
        (op_rendir, "JORNADA_RENDIR"),
        (op_cerrar, "JORNADA_CERRAR"),
    ):
        (auditoria,) = _auditorias_de(entorno, operation_id)
        assert (auditoria.accion, auditoria.motivo_id) == (accion, None)


def test_aud02_una_liberacion_rechazada_no_deja_motivo(entorno: Entorno) -> None:
    jornada_id = entorno.sembrada("CERRADA")
    operation_id = uuid4()

    with pytest.raises(JornadaEstadoInvalidoError):
        entorno.liberar(jornada_id, operation_id=operation_id)

    assert _auditorias_de(entorno, operation_id) == []


def test_inv06_el_reenvio_de_la_liberacion_no_escribe_otra_fila(entorno: Entorno) -> None:
    jornada_id = entorno.abrir_juan()
    operation_id = uuid4()

    entorno.liberar(jornada_id, operation_id=operation_id)
    entorno.liberar(jornada_id, operation_id=operation_id)

    assert len(_auditorias_de(entorno, operation_id)) == 1
