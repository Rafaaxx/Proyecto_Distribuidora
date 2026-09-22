"""ADR-022: los tres métodos de `identidad/service.py` que el change 04
(grupo 11) envuelve como handlers del bus (`crear_usuario`,
`revocar_dispositivo`, `establecer_pin_autorizacion`) ganan un parámetro
`auditar: bool = True`. Llamados directo (fuera del bus, default `True`)
siguen auditando como hoy; llamados desde un handler del bus (`auditar=False`
explícito) omiten su inserción interna porque el bus ya audita
automáticamente (`sync/service.py::procesar_comando`, grupo 10, origen
`COMANDO`) -- dejar las dos activas duplicaría la fila por comando.

Este archivo prueba SOLO el parámetro en sí (triangulación `auditar=True`
audita / `auditar=False` no audita), aislado del bus real -- la prueba de
que el bus + `auditar=False` deja EXACTAMENTE una fila por comando vive en
`test_identidad_commands_maestros.py` (grupo 11, tarea 11.3+), que ejercita
el camino completo end-to-end."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.identidad import repository, service
from app.modules.identidad.models import Auditoria, Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


def _crear_organizacion(sesion: Session) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba",
        slug=f"org-{nuevo_id().hex[:12]}",
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


def _crear_rol(sesion: Session, organizacion_id, *, permisos: frozenset[str] = frozenset()):
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Rol de prueba",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    for codigo in permisos:
        repository.asignar_permiso_a_rol(
            organizacion_id, sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    return rol


def _contar_auditoria(sesion: Session, organizacion_id) -> int:
    return sesion.execute(
        select(func.count())
        .select_from(Auditoria)
        .where(Auditoria.organizacion_id == organizacion_id)
    ).scalar_one()


class TestAuditarParamCrearUsuario:
    def test_crear_usuario_con_auditar_true_por_defecto_audita(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id)
        actor = repository.crear_usuario(
            organizacion.id,
            db_session,
            usuario_id=nuevo_id(),
            usuario="actor",
            nombre="Actor",
            email=None,
            password_hash="hash",
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )

        service.crear_usuario(
            organizacion.id,
            db_session,
            FixedClock(MOMENTO),
            usuario="nuevo1",
            nombre="Nuevo Uno",
            email=None,
            password="contrasena-de-prueba-larga-1",
            rol_id=rol.id,
            actor_id=actor.id,
        )

        assert _contar_auditoria(db_session, organizacion.id) == 1

    def test_crear_usuario_con_auditar_false_no_audita(self, db_session: Session) -> None:
        """Triangulación: mismo caso, `auditar=False` explícito -- ninguna
        fila (la deja para el bus, ADR-022)."""
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id)
        actor = repository.crear_usuario(
            organizacion.id,
            db_session,
            usuario_id=nuevo_id(),
            usuario="actor2",
            nombre="Actor",
            email=None,
            password_hash="hash",
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )

        service.crear_usuario(
            organizacion.id,
            db_session,
            FixedClock(MOMENTO),
            usuario="nuevo2",
            nombre="Nuevo Dos",
            email=None,
            password="contrasena-de-prueba-larga-2",
            rol_id=rol.id,
            actor_id=actor.id,
            auditar=False,
        )

        assert _contar_auditoria(db_session, organizacion.id) == 0


class TestAuditarParamRevocarDispositivo:
    def test_revocar_dispositivo_con_auditar_true_por_defecto_audita(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        dispositivo = service.registrar_dispositivo(
            organizacion.id, db_session, FixedClock(MOMENTO), dispositivo_id=nuevo_id(), nombre="T"
        )
        rol = _crear_rol(db_session, organizacion.id)
        actor = repository.crear_usuario(
            organizacion.id,
            db_session,
            usuario_id=nuevo_id(),
            usuario="actor3",
            nombre="Actor",
            email=None,
            password_hash="hash",
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )

        service.revocar_dispositivo(
            organizacion.id,
            db_session,
            FixedClock(MOMENTO),
            dispositivo_id=dispositivo.id,
            actor_id=actor.id,
        )

        assert _contar_auditoria(db_session, organizacion.id) == 1

    def test_revocar_dispositivo_con_auditar_false_no_audita(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        dispositivo = service.registrar_dispositivo(
            organizacion.id, db_session, FixedClock(MOMENTO), dispositivo_id=nuevo_id(), nombre="T"
        )
        rol = _crear_rol(db_session, organizacion.id)
        actor = repository.crear_usuario(
            organizacion.id,
            db_session,
            usuario_id=nuevo_id(),
            usuario="actor4",
            nombre="Actor",
            email=None,
            password_hash="hash",
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )

        service.revocar_dispositivo(
            organizacion.id,
            db_session,
            FixedClock(MOMENTO),
            dispositivo_id=dispositivo.id,
            actor_id=actor.id,
            auditar=False,
        )

        assert _contar_auditoria(db_session, organizacion.id) == 0


class TestAuditarParamEstablecerPinAutorizacion:
    def test_establecer_pin_con_auditar_true_por_defecto_audita(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id, permisos=frozenset({"AUTORIZAR_DESCUENTO"}))
        usuario = repository.crear_usuario(
            organizacion.id,
            db_session,
            usuario_id=nuevo_id(),
            usuario="supervisor1",
            nombre="Supervisor",
            email=None,
            password_hash="hash",
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )

        service.establecer_pin_autorizacion(
            organizacion.id,
            db_session,
            FixedClock(MOMENTO),
            usuario_id=usuario.id,
            pin="654321",
            actor_id=usuario.id,
        )

        assert _contar_auditoria(db_session, organizacion.id) == 1

    def test_establecer_pin_con_auditar_false_no_audita(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id, permisos=frozenset({"AUTORIZAR_DESCUENTO"}))
        usuario = repository.crear_usuario(
            organizacion.id,
            db_session,
            usuario_id=nuevo_id(),
            usuario="supervisor2",
            nombre="Supervisor",
            email=None,
            password_hash="hash",
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )

        service.establecer_pin_autorizacion(
            organizacion.id,
            db_session,
            FixedClock(MOMENTO),
            usuario_id=usuario.id,
            pin="654321",
            actor_id=usuario.id,
            auditar=False,
        )

        assert _contar_auditoria(db_session, organizacion.id) == 0
