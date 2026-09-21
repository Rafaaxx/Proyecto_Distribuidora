"""Tarea 11.4 (segunda mitad): desbloqueo manual de un usuario bloqueado
por intentos, por un actor con `ADMIN_USUARIOS`, auditado (`ADR-018`:
"registrando un intento de desbloqueo").

Ver la nota de alcance en `tasks.md` 11.4: `ADR-018` no fija el mecanismo
exacto; esta es una interpretación registrada para revisión humana, no una
decisión de negocio tomada en silencio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import (
    CredencialesInvalidasError,
    LoginBloqueadoPorIntentosError,
)
from app.modules.identidad.models import Auditoria, Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRETO = "secreto-de-prueba"
JWT_KID = "1"
RELOJ = FixedClock(MOMENTO)


def _crear_organizacion(sesion: Session, slug: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba",
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


def _crear_usuario(sesion: Session, organizacion_id, nombre_usuario: str) -> object:
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Vendedor",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    return repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=nombre_usuario,
        nombre="Persona de prueba",
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )


def _login(sesion: Session, *, organizacion_slug: str, nombre_usuario: str, password: str, ip: str):
    return identidad_service.iniciar_sesion(
        sesion,
        RELOJ,
        organizacion_slug=organizacion_slug,
        nombre_usuario=nombre_usuario,
        password=password,
        dispositivo_id=nuevo_id(),
        nombre_dispositivo="Tablet",
        jwt_secreto=JWT_SECRETO,
        jwt_kid=JWT_KID,
        ip=ip,
    )


def _bloquear_usuario(sesion: Session, organizacion, usuario, ip: str = "10.0.0.9") -> None:
    for _ in range(5):
        with pytest.raises(CredencialesInvalidasError):
            _login(
                sesion,
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password="mal",
                ip=ip,
            )


class TestDesbloqueoManual:
    def test_desbloquear_un_usuario_bloqueado_le_permite_iniciar_sesion_de_nuevo(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-desb-1")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")
        actor = _crear_usuario(db_session, organizacion.id, "admin1")
        _bloquear_usuario(db_session, organizacion, usuario)
        with pytest.raises(LoginBloqueadoPorIntentosError):
            _login(
                db_session,
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                ip="10.0.0.9",
            )

        resultado = identidad_service.desbloquear_usuario(
            organizacion.id, db_session, RELOJ, usuario_id=usuario.id, actor_id=actor.id
        )
        assert resultado is not None

        # Ahora sí puede iniciar sesión (incluso desde la misma IP bloqueada
        # para el usuario, porque el límite por usuario ya se reinició).
        logueado = _login(
            db_session,
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            ip="10.0.0.9",
        )
        assert logueado.usuario_id == usuario.id

    def test_desbloquear_no_reinicia_el_bloqueo_por_ip(self, db_session: Session) -> None:
        """Triangulación: desbloquear a UN usuario no limpia el límite por
        IP, que sigue contando los intentos fallidos de esa dirección --
        aquí, contra nombres de usuario inexistentes, para saturar el
        límite por IP (20) sin acercarse al límite por usuario (5) de
        ninguna cuenta real (el desbloqueo manual es por usuario, no por
        IP)."""
        organizacion = _crear_organizacion(db_session, "org-desb-2")
        usuario_real = _crear_usuario(db_session, organizacion.id, "vendedor1")
        actor = _crear_usuario(db_session, organizacion.id, "admin1")

        for i in range(20):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=f"no-existe-{i}",
                    password="mal",
                    ip="10.0.0.20",
                )

        identidad_service.desbloquear_usuario(
            organizacion.id,
            db_session,
            RELOJ,
            usuario_id=usuario_real.id,
            actor_id=actor.id,
        )

        # El límite por IP sigue activo: ni siquiera un usuario real que
        # nunca falló (y que además se acaba de "desbloquear") puede entrar
        # desde esa IP saturada -- el desbloqueo manual no la toca.
        with pytest.raises(LoginBloqueadoPorIntentosError):
            _login(
                db_session,
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario_real.usuario,
                password=PASSWORD,
                ip="10.0.0.20",
            )

    def test_desbloquear_un_usuario_de_otra_organizacion_no_lo_encuentra(
        self, db_session: Session
    ) -> None:
        org_a = _crear_organizacion(db_session, "org-desb-3a")
        org_b = _crear_organizacion(db_session, "org-desb-3b")
        usuario_a = _crear_usuario(db_session, org_a.id, "vendedor_a")
        actor_b = _crear_usuario(db_session, org_b.id, "admin_b")

        resultado = identidad_service.desbloquear_usuario(
            org_b.id, db_session, RELOJ, usuario_id=usuario_a.id, actor_id=actor_b.id
        )

        assert resultado is None

    def test_el_desbloqueo_manual_queda_auditado(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, "org-desb-4")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")
        actor = _crear_usuario(db_session, organizacion.id, "admin1")
        _bloquear_usuario(db_session, organizacion, usuario)

        identidad_service.desbloquear_usuario(
            organizacion.id, db_session, RELOJ, usuario_id=usuario.id, actor_id=actor.id
        )

        auditorias = (
            db_session.query(Auditoria)
            .filter_by(organizacion_id=organizacion.id, accion="DESBLOQUEO_MANUAL_LOGIN")
            .all()
        )
        assert len(auditorias) == 1
        assert auditorias[0].entidad_id == usuario.id
        assert auditorias[0].usuario_id == actor.id
