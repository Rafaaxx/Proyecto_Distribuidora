"""Transacción del bus de comandos con PostgreSQL real (change 04, grupo 6,
tareas 6.1, 6.2, 6.6, 6.8; `docs/02-arquitectura.md` §6.3, INV-01, INV-06).

`sync_service.procesar_comando` (grupo 6) envuelve `procesar_idempotente`
(grupo 5, ya probado en `test_inv06_reserva_idempotencia.py`) con permisos,
resultado y reintentos. Estas pruebas confirman los efectos REALES sobre la
base -- que un fallo del handler no deje ninguna fila, que la reserva se
libere para reintentar con contenido corregido, que agotar los reintentos
no deje un estado final, y los tres estados finales más el intermedio --
usando `db_session` (transacción revertida al final, no concurrencia)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Auditoria, Organizacion, Rol
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


def _crear_organizacion(sesion: Session, *, slug: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba bus",
        slug=slug,
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
        actualizado_por_id=None,
    )
    sesion.add(organizacion)
    sesion.flush()
    return organizacion


def _crear_usuario_y_dispositivo(sesion: Session, organizacion_id: UUID) -> tuple[UUID, UUID]:
    rol = identidad_repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Vendedor",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    usuario = identidad_repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=f"vendedor-{uuid4().hex[:8]}",
        nombre="Persona de prueba",
        email=None,
        password_hash="hash",
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    dispositivo = identidad_repository.crear_dispositivo(
        organizacion_id,
        sesion,
        dispositivo_id=nuevo_id(),
        nombre="Dispositivo de prueba",
        prefijo=f"B{uuid4().hex[:2]}",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario.id, dispositivo.id


def _sobre(
    *, organizacion_id: UUID, usuario_id: UUID, dispositivo_id: UUID, operation_id: UUID
) -> SobreComando:
    return SobreComando(
        operation_id=operation_id,
        tipo="USUARIO_CREAR",
        version=1,
        modo="ONLINE",
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={},
    )


def _contar_comandos(sesion: Session, operation_id: UUID) -> int:
    return sesion.scalar(
        select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
    )


def _contar_roles(sesion: Session, organizacion_id: UUID) -> int:
    return sesion.scalar(
        select(func.count()).select_from(Rol).where(Rol.organizacion_id == organizacion_id)
    )


class _ErrorDeBaseFalso(Exception):
    """Mismo doble que `tests/unit/test_sync_service_bus.py`: simula el
    `.orig.sqlstate` que expone un `DBAPIError` real, sin depender de que
    PostgreSQL produzca genuinamente el fallo (eso lo hace la prueba de
    concurrencia, `tests/concurrency/test_bus_reintentos_concurrencia.py`)."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"simulado sqlstate={sqlstate}")
        self.orig = SimpleNamespace(sqlstate=sqlstate)


class TestFalloDelHandlerNoDejaEfectosParciales:
    """Tarea 6.1, escenario "Un fallo del handler no deja efectos
    parciales" (INV-01)."""

    def test_un_fallo_del_handler_no_deja_efectos_parciales(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-bus-6.1-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()

        def _handler_que_escribe_y_despues_falla(sesion: object) -> sync_service.ResultadoHandler:
            # Parte de los "efectos": escribe un rol antes de fallar.
            identidad_repository.crear_rol(
                organizacion.id,
                sesion,  # type: ignore[arg-type]
                rol_id=nuevo_id(),
                nombre="Rol que no debería sobrevivir",
                tope_descuento=Decimal("0"),
                activo=True,
                momento=MOMENTO,
            )
            raise RuntimeError("una regla de negocio incumplida, simulada")

        with pytest.raises(RuntimeError, match="una regla de negocio incumplida"):
            sync_service.procesar_comando(
                db_session,
                FixedClock(MOMENTO),
                sobre=_sobre(
                    organizacion_id=organizacion.id,
                    usuario_id=usuario,
                    dispositivo_id=dispositivo,
                    operation_id=operation_id,
                ),
                huella="huella-1",
                ejecutar_handler=_handler_que_escribe_y_despues_falla,
            )

        # Ni la reserva del comando ni el rol escrito por el handler
        # sobreviven: la transacción entera se revirtió.
        assert _contar_comandos(db_session, operation_id) == 0
        # Un solo rol: el creado por `_crear_usuario_y_dispositivo`, no el
        # que el handler intentó agregar.
        assert _contar_roles(db_session, organizacion.id) == 1


class TestReintentarCorregidoTrasUnRechazoOnline:
    """Tarea 6.2, escenario "Un identificador de operación rechazado por
    regla de negocio puede reintentarse corregido"."""

    def test_el_mismo_operation_id_se_reintenta_con_contenido_corregido(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-bus-6.2-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()

        def _handler_que_falla(_sesion: object) -> sync_service.ResultadoHandler:
            raise RuntimeError("contenido incorrecto, simulado")

        with pytest.raises(RuntimeError, match="contenido incorrecto"):
            sync_service.procesar_comando(
                db_session,
                FixedClock(MOMENTO),
                sobre=_sobre(
                    organizacion_id=organizacion.id,
                    usuario_id=usuario,
                    dispositivo_id=dispositivo,
                    operation_id=operation_id,
                ),
                huella="huella-original-incorrecta",
                ejecutar_handler=_handler_que_falla,
            )
        assert _contar_comandos(db_session, operation_id) == 0

        # Reenvío del MISMO operation_id, con contenido (huella) corregido:
        # se procesa como comando nuevo, no como inconsistente, porque la
        # reserva original nunca sobrevivió al rollback.
        def _handler_corregido(_sesion: object) -> sync_service.ResultadoHandler:
            return "ACEPTADO", {"corregido": True}, None

        comando = sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-corregida",
            ejecutar_handler=_handler_corregido,
        )

        assert comando.estado == "ACEPTADO"
        assert comando.huella == "huella-corregida"
        assert _contar_comandos(db_session, operation_id) == 1


class TestReintentosTransitoriosConBaseReal:
    """Tarea 6.6, escenario "Agotados los reintentos, la respuesta es
    transitoria y no un rechazo", verificado contra la reserva REAL (no un
    doble de `procesar_idempotente` como en la prueba unitaria): cada
    intento inserta y revierte de verdad."""

    def test_agotados_los_reintentos_no_queda_estado_final(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-bus-6.6-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()
        intentos_del_handler = {"n": 0}

        def _handler_siempre_transitorio(_sesion: object) -> sync_service.ResultadoHandler:
            intentos_del_handler["n"] += 1
            raise _ErrorDeBaseFalso("40001")

        with pytest.raises(sync_service.ErrorTransitorioAgotadoError) as exc_info:
            sync_service.procesar_comando(
                db_session,
                FixedClock(MOMENTO),
                sobre=_sobre(
                    organizacion_id=organizacion.id,
                    usuario_id=usuario,
                    dispositivo_id=dispositivo,
                    operation_id=operation_id,
                ),
                huella="huella-1",
                ejecutar_handler=_handler_siempre_transitorio,
                config=sync_service.ConfiguracionReintentos(
                    intentos_maximos=3, espera_base_segundos=0.001, espera_techo_segundos=0.01
                ),
                dormir=lambda _segundos: None,
            )

        assert exc_info.value.intentos == 3
        assert intentos_del_handler["n"] == 3
        # Ninguno de los tres intentos dejó un `comando` con estado final --
        # ni siquiera la reserva intermedia sobrevive al rollback.
        assert _contar_comandos(db_session, operation_id) == 0


class TestTresEstadosFinalesYElIntermedio:
    """Tarea 6.8, escenarios "Un comando sin observaciones queda
    aceptado", "Un comando rechazado registra su código de error" y "El
    contenido del comando no se conserva cuando se acepta"."""

    def test_un_comando_sin_observaciones_queda_aceptado(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-bus-6.8a-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()

        comando = sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("ACEPTADO", {"usuario_id": "abc"}, None),
        )

        assert comando.estado == "ACEPTADO"
        assert comando.resultado == {"usuario_id": "abc"}
        assert comando.error_codigo is None

    def test_un_comando_rechazado_registra_su_codigo_de_error(self, db_session: Session) -> None:
        """El handler DEVUELVE (sin lanzar) un rechazo de negocio: se
        registra como estado final, con su código, distinto del camino de
        6.1/6.2 (el handler que LANZA)."""
        organizacion = _crear_organizacion(db_session, slug=f"org-bus-6.8b-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()

        comando = sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("RECHAZADO", None, "USUARIO_YA_EXISTE"),
        )

        assert comando.estado == "RECHAZADO"
        assert comando.error_codigo == "USUARIO_YA_EXISTE"
        assert _contar_comandos(db_session, operation_id) == 1

    def test_el_contenido_no_se_conserva_cuando_se_acepta(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-bus-6.8c-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()
        sobre = SobreComando(
            operation_id=operation_id,
            tipo="USUARIO_CREAR",
            version=1,
            modo="ONLINE",
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido={"usuario": "secreto-no-persistido", "email": "vendedor@example.com"},
        )

        comando = sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=sobre,
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("ACEPTADO", {"usuario_id": "abc"}, None),
        )

        assert comando.tipo == "USUARIO_CREAR"
        assert comando.version == 1
        assert comando.huella == "huella-1"
        assert comando.estado == "ACEPTADO"
        assert comando.resultado == {"usuario_id": "abc"}
        columnas = Comando.__table__.columns.keys()
        assert "contenido" not in columnas

    def test_el_comando_queda_en_estado_intermedio_mientras_se_procesa(
        self, db_session: Session
    ) -> None:
        """El estado intermedio (`PROCESANDO`) es visible DENTRO de la misma
        transacción, antes de que el handler termine -- una vez confirmado
        el comando pasa a uno de los tres finales."""
        organizacion = _crear_organizacion(db_session, slug=f"org-bus-6.8d-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()
        estados_vistos_durante_el_handler: list[str] = []

        def _handler_que_observa_su_propio_estado(sesion: object) -> sync_service.ResultadoHandler:
            id_comando = sesion.scalar(  # type: ignore[attr-defined]
                select(Comando.id).where(Comando.operation_id == operation_id)
            )
            fila = sesion.get(Comando, id_comando)  # type: ignore[attr-defined]
            estados_vistos_durante_el_handler.append(fila.estado)
            return "ACEPTADO", {}, None

        comando = sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-1",
            ejecutar_handler=_handler_que_observa_su_propio_estado,
        )

        assert estados_vistos_durante_el_handler == ["PROCESANDO"]
        assert comando.estado == "ACEPTADO"


class TestAuditoriaAutomaticaDelComando:
    """Grupo 10 (change 04, tarea 10.1), escenarios "La auditoría de un
    comando referencia su identificador de operación" y "La auditoría del
    comando se confirma junto con sus efectos": `procesar_comando` audita
    automáticamente TODO comando aceptado (decisión de diseño aprobada,
    no depende de que el handler lo declare), con `origen='COMANDO'` y el
    `operation_id` del sobre, dentro de la MISMA transacción que confirma
    los efectos del comando."""

    def _auditoria_del_operation_id(
        self, sesion: Session, operation_id: UUID
    ) -> list[Auditoria]:
        return list(
            sesion.execute(
                select(Auditoria).where(Auditoria.operation_id == operation_id)
            )
            .scalars()
            .all()
        )

    def test_la_auditoria_de_un_comando_referencia_su_operation_id(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-bus-10.1a-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()

        sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("ACEPTADO", {"usuario_id": "abc"}, None),
        )

        filas = self._auditoria_del_operation_id(db_session, operation_id)
        assert len(filas) == 1
        assert filas[0].origen == "COMANDO"
        assert filas[0].operation_id == operation_id

    def test_la_auditoria_del_comando_se_confirma_junto_con_sus_efectos(
        self, db_session: Session
    ) -> None:
        """Tras el `commit` real de `procesar_comando` (no una transacción
        de prueba revertida), la fila de auditoría y la de `comando`
        siguen ahí las dos -- se confirmaron juntas, en el mismo `commit`
        (INV-01, TR-06)."""
        organizacion = _crear_organizacion(db_session, slug=f"org-bus-10.1b-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()

        sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("ACEPTADO", {"usuario_id": "abc"}, None),
        )

        db_session.expire_all()
        assert _contar_comandos(db_session, operation_id) == 1
        assert len(self._auditoria_del_operation_id(db_session, operation_id)) == 1

    def test_un_comando_reenviado_idempotentemente_no_duplica_la_auditoria(
        self, db_session: Session
    ) -> None:
        """Triangulación: el reenvío del MISMO `operation_id` con la MISMA
        huella no vuelve a ejecutar el handler (SYN-02) -- tampoco debe
        volver a auditar, o un reenvío inocuo se vería como dos eventos."""
        organizacion = _crear_organizacion(db_session, slug=f"org-bus-10.1c-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()
        sobre = _sobre(
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            operation_id=operation_id,
        )

        sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=sobre,
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("ACEPTADO", {"usuario_id": "abc"}, None),
        )
        sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=sobre,
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("ACEPTADO", {"usuario_id": "otro"}, None),
        )

        assert len(self._auditoria_del_operation_id(db_session, operation_id)) == 1
