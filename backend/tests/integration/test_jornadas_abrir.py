"""Change 15, tareas 4.1 y 4.2: `JORNADA_ABRIR` v1 por el bus contra PostgreSQL real (spec
`stock/jornadas`, requisitos "Abrir una jornada toma la ubicación", "Una ubicación que
requiere toma tiene como máximo una jornada no cerrada", "Un usuario y un dispositivo tienen a
lo sumo una jornada no cerrada" y "Una jornada se registra completa y no se borra";
`design.md` D3, D9, D10).

Se procesa por `sync_service.procesar_comando`, que maneja la transacción (mismo criterio que
`test_stock_transferir.py`). La cobertura por HTTP es de `test_jornadas_api.py`.

Reglas citadas: RUT-01, RUT-03, INV-01, INV-05, INV-06, INV-16, INV-21, SEG-06, AUD-02, SYN-02.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

from app.commands import catalogo as catalogo_bus
from app.commands import registro
from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad.models import Auditoria
from app.modules.stock import (
    jornadas_casos,
    jornadas_commands,  # noqa: F401  (registra los handlers)
)
from app.modules.stock.domain.errores import (
    DispositivoConJornadaError,
    RecursoNoEncontradoError,
    UbicacionInactivaError,
    UbicacionSinTomaError,
    UbicacionTomadaError,
    UsuarioConJornadaError,
)
from app.modules.stock.models import Jornada
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
ABRIR = "JORNADA_ABRIR"

VENDEDOR = frozenset({"ABRIR_JORNADA"})


class Actor:
    """Un usuario con un dispositivo, o un usuario en el dispositivo de otro."""

    def __init__(self, usuario_id: UUID, dispositivo_id: UUID) -> None:
        self.usuario_id = usuario_id
        self.dispositivo_id = dispositivo_id


class Entorno:
    """Una organización con "Camioneta 1" y "Camioneta 2" (vehículos que requieren toma),
    "Camioneta 3" inactiva y el "Depósito central" (sin toma); Juan (teléfono V03) y Pedro
    (teléfono V04), vendedores, y una Administración sin `ABRIR_JORNADA`."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.juan = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.pedro = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.administracion = Actor(
            *crear_usuario_y_dispositivo(sesion, self.org, permisos=frozenset({"RENDIR_JORNADA"}))
        )
        self.pedro_en_v03 = Actor(self.pedro.usuario_id, self.juan.dispositivo_id)
        self.camioneta_1 = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.camioneta_2 = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
        )
        self.camioneta_3 = crear_ubicacion_sql(
            sesion,
            self.org,
            nombre="Camioneta 3",
            tipo="VEHICULO",
            requiere_toma=True,
            activo=False,
        )
        self.deposito = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")
        sesion.commit()

    def sobre(
        self, actor: Actor, contenido: dict[str, Any], *, operation_id: UUID | None = None
    ) -> SobreComando:
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=ABRIR,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )

    def abrir(
        self, actor: Actor, ubicacion_id: UUID, *, operation_id: UUID | None = None, **extra: Any
    ) -> Comando:
        sobre = self.sobre(
            actor, {"ubicacion_id": str(ubicacion_id), **extra}, operation_id=operation_id
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

    def jornadas(self) -> list[Jornada]:
        self.sesion.rollback()
        return list(
            self.sesion.scalars(
                select(Jornada).where(Jornada.organizacion_id == self.org).order_by(Jornada.id)
            ).all()
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

    def auditorias(self, operation_id: UUID) -> list[Auditoria]:
        self.sesion.rollback()
        return list(
            self.sesion.scalars(
                select(Auditoria).where(
                    Auditoria.organizacion_id == self.org, Auditoria.operation_id == operation_id
                )
            ).all()
        )

    def terminada(self, actor: Actor, ubicacion_id: UUID, estado: str) -> UUID:
        jornada_id = crear_jornada_sql(
            self.sesion,
            self.org,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            ubicacion_id=ubicacion_id,
            estado=estado,
        )
        self.sesion.commit()
        return jornada_id


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- catálogo ----------------------------------------------------------------------------


def test_el_tipo_esta_declarado_online_y_sin_offline_con_handler_v1() -> None:
    """`02` §6.5: la apertura es solo `ONLINE` (RUT-03)."""
    declarado = catalogo_bus.tipo_declarado(ABRIR)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert registro.resolver_handler(ABRIR, 1).tipo == ABRIR


# --- escenarios felices ------------------------------------------------------------------


def test_apertura_de_una_jornada_sobre_un_vehiculo_libre(entorno: Entorno) -> None:
    """Escenario "Apertura de una jornada sobre un vehículo libre" (RUT-01, RUT-03)."""
    comando = entorno.abrir(entorno.juan, entorno.camioneta_1)

    assert comando.estado == "ACEPTADO"
    (jornada,) = entorno.jornadas()
    assert jornada.estado == "ABIERTA"
    assert (jornada.usuario_id, jornada.dispositivo_id, jornada.ubicacion_id) == (
        entorno.juan.usuario_id,
        entorno.juan.dispositivo_id,
        entorno.camioneta_1,
    )
    assert jornada.abierta_en == MOMENTO
    assert jornada.operation_id == comando.operation_id
    assert (jornada.rendida_en, jornada.cerrada_en, jornada.liberada_en) == (None, None, None)
    assert comando.resultado is not None
    assert comando.resultado["jornada_id"] == str(jornada.id)
    assert comando.resultado["estado"] == "ABIERTA"


def test_una_jornada_nueva_no_toma_otras_ubicaciones(entorno: Entorno) -> None:
    """La toma es de la ubicación indicada: la otra camioneta sigue libre (RUT-01)."""
    entorno.abrir(entorno.juan, entorno.camioneta_1)

    comando = entorno.abrir(entorno.pedro, entorno.camioneta_2)

    assert comando.estado == "ACEPTADO"
    assert {j.ubicacion_id for j in entorno.jornadas()} == {
        entorno.camioneta_1,
        entorno.camioneta_2,
    }


def test_el_contenido_no_acepta_usuario_ni_dispositivo(entorno: Entorno) -> None:
    """El usuario y el dispositivo salen de la sesión (RUT-03): un contenido que los traiga
    se rechaza."""
    for extra in ({"usuario_id": str(entorno.pedro.usuario_id)}, {"dispositivo_id": str(uuid4())}):
        with pytest.raises(ContenidoDeComandoInvalidoError):
            entorno.abrir(entorno.juan, entorno.camioneta_1, **extra)
    assert entorno.jornadas() == []


# --- permiso y ubicación -----------------------------------------------------------------


def test_sin_abrir_jornada_responde_403_sin_jornada_ni_reserva(entorno: Entorno) -> None:
    operation_id = uuid4()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.abrir(entorno.administracion, entorno.camioneta_1, operation_id=operation_id)

    assert error.value.status_http == 403
    assert entorno.jornadas() == []
    assert entorno.cantidad_de_comandos(operation_id) == 0


def test_inv21_una_ubicacion_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    ajena = crear_ubicacion_sql(
        db_session,
        crear_organizacion(db_session).id,
        nombre="Camioneta ajena",
        tipo="VEHICULO",
        requiere_toma=True,
    )
    db_session.commit()

    for ubicacion_id in (ajena, uuid4()):
        with pytest.raises(RecursoNoEncontradoError) as error:
            entorno.abrir(entorno.juan, ubicacion_id)
        assert error.value.status_http == 404
    assert entorno.jornadas() == []


def test_una_ubicacion_inactiva_se_rechaza(entorno: Entorno) -> None:
    with pytest.raises(UbicacionInactivaError):
        entorno.abrir(entorno.juan, entorno.camioneta_3)

    assert entorno.jornadas() == []


def test_una_ubicacion_que_no_requiere_toma_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Ubicación que no requiere toma" (RUT-01, D3): un depósito nunca queda
    tomado."""
    with pytest.raises(UbicacionSinTomaError) as error:
        entorno.abrir(entorno.juan, entorno.deposito)

    assert error.value.codigo == "UBICACION_SIN_TOMA"
    assert entorno.jornadas() == []


# --- unicidad (INV-16, D3) ----------------------------------------------------------------


def test_inv16_la_segunda_apertura_sobre_una_ubicacion_tomada_se_rechaza(
    entorno: Entorno,
) -> None:
    entorno.abrir(entorno.juan, entorno.camioneta_1)

    with pytest.raises(UbicacionTomadaError) as error:
        entorno.abrir(entorno.pedro, entorno.camioneta_1)

    assert (error.value.codigo, error.value.status_http) == ("UBICACION_TOMADA", 409)
    assert [j.usuario_id for j in entorno.jornadas()] == [entorno.juan.usuario_id]


@pytest.mark.parametrize("ocupa", ["ABIERTA", "EN_RENDICION"])
def test_inv16_una_jornada_en_rendicion_tambien_ocupa_la_ubicacion(
    entorno: Entorno, ocupa: str
) -> None:
    entorno.terminada(entorno.juan, entorno.camioneta_1, ocupa)

    with pytest.raises(UbicacionTomadaError):
        entorno.abrir(entorno.pedro, entorno.camioneta_1)


@pytest.mark.parametrize("terminada", ["CERRADA", "LIBERADA"])
def test_una_ubicacion_vuelve_a_abrirse_despues_del_cierre_o_la_liberacion(
    entorno: Entorno, terminada: str
) -> None:
    """Escenarios "después del cierre" y "después de la liberación" (RUT-08, RUT-09)."""
    entorno.terminada(entorno.juan, entorno.camioneta_1, terminada)

    comando = entorno.abrir(entorno.pedro, entorno.camioneta_1)

    assert comando.estado == "ACEPTADO"
    assert sorted(j.estado for j in entorno.jornadas()) == sorted(["ABIERTA", terminada])


def test_el_mismo_usuario_no_toma_un_segundo_vehiculo(entorno: Entorno) -> None:
    """Escenario "El mismo usuario intenta tomar un segundo vehículo" (RUT-04, D3)."""
    entorno.abrir(entorno.juan, entorno.camioneta_1)

    with pytest.raises(UsuarioConJornadaError) as error:
        entorno.abrir(entorno.juan, entorno.camioneta_2)

    assert error.value.codigo == "USUARIO_CON_JORNADA"
    assert [j.ubicacion_id for j in entorno.jornadas()] == [entorno.camioneta_1]


def test_otro_usuario_no_abre_desde_un_dispositivo_con_jornada(entorno: Entorno) -> None:
    """Escenario "Otro usuario intenta abrir desde un dispositivo con jornada" (ADR-005)."""
    entorno.abrir(entorno.juan, entorno.camioneta_1)

    with pytest.raises(DispositivoConJornadaError) as error:
        entorno.abrir(entorno.pedro_en_v03, entorno.camioneta_2)

    assert error.value.codigo == "DISPOSITIVO_CON_JORNADA"
    assert [j.ubicacion_id for j in entorno.jornadas()] == [entorno.camioneta_1]


def test_una_ubicacion_tomada_gana_sobre_el_usuario_y_el_dispositivo(entorno: Entorno) -> None:
    """Orden de las restricciones (D3): si además de tomada la ubicación el usuario y el
    dispositivo ya tienen jornada, se informa la ubicación."""
    entorno.abrir(entorno.juan, entorno.camioneta_1)

    with pytest.raises(UbicacionTomadaError):
        entorno.abrir(entorno.juan, entorno.camioneta_1)


def test_despues_de_cerrar_el_mismo_usuario_abre_otra(entorno: Entorno) -> None:
    """Escenario "Después de cerrar puede abrir otra" (RUT-08)."""
    entorno.terminada(entorno.juan, entorno.camioneta_1, "CERRADA")

    comando = entorno.abrir(entorno.juan, entorno.camioneta_2)

    assert comando.estado == "ACEPTADO"


# --- modo, idempotencia y auditoría --------------------------------------------------------


def test_el_lote_rechaza_una_apertura_enviada_sin_conexion(entorno: Entorno) -> None:
    operation_id = uuid4()
    item = ItemLote(
        operation_id=operation_id,
        tipo=ABRIR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.juan.usuario_id,
        dispositivo_id=entorno.juan.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={"ubicacion_id": str(entorno.camioneta_1)},
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.juan.usuario_id,
        dispositivo_id=entorno.juan.dispositivo_id,
        items=[item],
    )

    assert (resultado.estado, resultado.error_codigo) == (
        "RECHAZADO",
        "MODO_NO_ADMITIDO_PARA_TIPO",
    )
    assert entorno.jornadas() == []
    assert entorno.cantidad_de_comandos(operation_id) == 0


def test_inv06_el_reenvio_devuelve_el_resultado_original_con_una_sola_jornada(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()

    primero = entorno.abrir(entorno.juan, entorno.camioneta_1, operation_id=operation_id)
    segundo = entorno.abrir(entorno.juan, entorno.camioneta_1, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.jornadas()) == 1


def test_inv06_el_mismo_operation_id_con_otra_ubicacion_es_inconsistente(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()
    entorno.abrir(entorno.juan, entorno.camioneta_1, operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.abrir(entorno.juan, entorno.camioneta_2, operation_id=operation_id)

    (jornada,) = entorno.jornadas()
    assert jornada.ubicacion_id == entorno.camioneta_1


def test_aud02_una_sola_fila_de_auditoria_sin_motivo(entorno: Entorno) -> None:
    operation_id = uuid4()

    entorno.abrir(entorno.juan, entorno.camioneta_1, operation_id=operation_id)
    entorno.abrir(entorno.juan, entorno.camioneta_1, operation_id=operation_id)  # reenvío

    (auditoria,) = entorno.auditorias(operation_id)
    assert auditoria.accion == ABRIR
    assert auditoria.motivo_id is None
    assert (auditoria.usuario_id, auditoria.dispositivo_id) == (
        entorno.juan.usuario_id,
        entorno.juan.dispositivo_id,
    )


def test_una_apertura_rechazada_no_deja_auditoria(entorno: Entorno) -> None:
    entorno.abrir(entorno.juan, entorno.camioneta_1)
    operation_id = uuid4()

    with pytest.raises(UbicacionTomadaError):
        entorno.abrir(entorno.pedro, entorno.camioneta_1, operation_id=operation_id)

    assert entorno.auditorias(operation_id) == []


# --- atomicidad y privilegios (tarea 4.2, INV-01, INV-05) ------------------------------------


def test_inv01_una_falla_despues_de_escribir_la_jornada_no_deja_nada_y_se_reintenta(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Falla en medio de la apertura": ni jornada ni auditoría, la ubicación
    sigue libre y el mismo `operation_id` puede reintentarse."""
    original = jornadas_casos.repository.insertar_jornada

    def insertar_y_fallar(*args: Any, **kwargs: Any) -> Any:
        original(*args, **kwargs)
        raise RuntimeError("falla inyectada después de escribir la jornada")

    monkeypatch.setattr(jornadas_casos.repository, "insertar_jornada", insertar_y_fallar)
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.abrir(entorno.juan, entorno.camioneta_1, operation_id=operation_id)

    assert entorno.jornadas() == []
    assert entorno.auditorias(operation_id) == []
    assert entorno.cantidad_de_comandos(operation_id) == 0

    monkeypatch.undo()
    comando = entorno.abrir(entorno.juan, entorno.camioneta_1, operation_id=operation_id)
    assert comando.estado == "ACEPTADO"
    assert len(entorno.jornadas()) == 1


def test_inv05_app_runtime_no_reescribe_ni_borra_la_jornada_abierta(
    _engine_de_sesion: Engine, app_runtime_engine: Engine
) -> None:
    """INV-05, TR-06: después de abrir (con commit real), el usuario de aplicación no puede
    borrar la jornada ni cambiar su ubicación, su usuario o su momento de apertura."""
    with Session(_engine_de_sesion) as sesion:
        entorno = Entorno(sesion)
        entorno.abrir(entorno.juan, entorno.camioneta_1)
        jornada_id = entorno.jornadas()[0].id
        organizacion_id = entorno.org
    try:
        for sentencia in (
            "DELETE FROM jornada WHERE id = :id",
            "UPDATE jornada SET ubicacion_id = ubicacion_id WHERE id = :id",
            "UPDATE jornada SET usuario_id = usuario_id WHERE id = :id",
            "UPDATE jornada SET abierta_en = now() WHERE id = :id",
        ):
            with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
                conexion.execute(text(sentencia), {"id": jornada_id})
            assert "permission denied" in str(error.value), sentencia
        with _engine_de_sesion.connect() as conexion:
            assert (
                conexion.execute(
                    text("SELECT count(*) FROM jornada WHERE organizacion_id = :o"),
                    {"o": organizacion_id},
                ).scalar_one()
                == 1
            )
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
