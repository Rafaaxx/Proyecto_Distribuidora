"""Grupo 11 (`ADR-018`): rate limit de login por usuario y por IP.

Tareas 11.2 (conteo con los umbrales del ADR), 11.3 (propiedades que no
dependen de los valores concretos: aislamiento entre usuarios, no revela
existencia, queda auditado) y 11.4 (desbloqueo automático al vencer la
ventana; el desbloqueo manual está en `test_identidad_desbloqueo_manual_service.py`).

La prueba de "uniforme entre procesos" (11.2) que ejercita conexiones
realmente independientes vive en `tests/concurrency/
test_rate_limit_login_concurrencia.py` (Testcontainers, sin mocks); acá se
prueba la lógica de conteo/umbral con `db_session` (una sola transacción,
suficiente para la lógica de negocio en sí).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


def _login(
    sesion: Session,
    *,
    reloj,
    organizacion_slug: str,
    nombre_usuario: str,
    password: str = PASSWORD,
    ip: str = "10.0.0.1",
):
    return identidad_service.iniciar_sesion(
        sesion,
        reloj,
        organizacion_slug=organizacion_slug,
        nombre_usuario=nombre_usuario,
        password=password,
        dispositivo_id=nuevo_id(),
        nombre_dispositivo="Tablet de reparto",
        jwt_secreto=JWT_SECRETO,
        jwt_kid=JWT_KID,
        ip=ip,
    )


class TestLimitePorUsuario:
    def test_5_intentos_fallidos_bloquean_al_usuario(self, db_session: Session) -> None:
        """Escenario homónimo de `ADR-018`: 5 intentos fallidos en la
        ventana bloquean, incluso con la contraseña correcta en el sexto."""
        organizacion = _crear_organizacion(db_session, "org-rl-1")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")

        for _ in range(5):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario.usuario,
                    password="mal",
                )

        with pytest.raises(LoginBloqueadoPorIntentosError):
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,  # correcta: el bloqueo igual rechaza.
            )

    def test_4_intentos_fallidos_todavia_no_bloquean(self, db_session: Session) -> None:
        """Triangulación: un intento menos que el umbral no bloquea."""
        organizacion = _crear_organizacion(db_session, "org-rl-2")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")

        for _ in range(4):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario.usuario,
                    password="mal",
                )

        resultado = _login(
            db_session,
            reloj=FixedClock(MOMENTO),
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
        )
        assert resultado.usuario_id == usuario.id


class TestLimitePorIp:
    def test_20_intentos_fallidos_por_ip_bloquean_aunque_sean_de_usuarios_distintos(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-rl-3")
        usuarios = [_crear_usuario(db_session, organizacion.id, f"vendedor{i}") for i in range(4)]

        for i in range(20):
            usuario = usuarios[i % len(usuarios)]
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario.usuario,
                    password="mal",
                    ip="10.0.0.99",
                )

        with pytest.raises(LoginBloqueadoPorIntentosError):
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuarios[0].usuario,
                password=PASSWORD,
                ip="10.0.0.99",
            )


class TestPropiedadesIndependientesDelValor:
    def test_un_usuario_bloqueado_no_penaliza_a_otro(self, db_session: Session) -> None:
        """Escenario "Un inicio de sesión exitoso no queda penalizado por
        intentos de otro usuario"."""
        organizacion = _crear_organizacion(db_session, "org-rl-4")
        usuario_a = _crear_usuario(db_session, organizacion.id, "usuario_a")
        usuario_b = _crear_usuario(db_session, organizacion.id, "usuario_b")

        for _ in range(5):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario_a.usuario,
                    password="mal",
                    ip="10.0.0.1",
                )

        # Usuario B, desde OTRA dirección de origen: no está bloqueado.
        resultado = _login(
            db_session,
            reloj=FixedClock(MOMENTO),
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario_b.usuario,
            password=PASSWORD,
            ip="10.0.0.2",
        )
        assert resultado.usuario_id == usuario_b.id

    def test_el_bloqueo_no_revela_si_el_usuario_existe(self, db_session: Session) -> None:
        """Escenario "El bloqueo por intentos no revela si el usuario
        existe": agotar el límite por IP con un usuario inexistente produce
        el mismo error, con el mismo código, que agotarlo contra uno real."""
        organizacion = _crear_organizacion(db_session, "org-rl-5")
        _crear_usuario(db_session, organizacion.id, "usuario_real")

        for _ in range(20):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario="no-existe-ningun-usuario-asi",
                    password="mal",
                    ip="10.0.0.50",
                )

        with pytest.raises(LoginBloqueadoPorIntentosError) as excinfo_inexistente:
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario="no-existe-ningun-usuario-asi",
                password="mal",
                ip="10.0.0.50",
            )

        with pytest.raises(LoginBloqueadoPorIntentosError) as excinfo_real:
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario="usuario_real",
                password=PASSWORD,
                ip="10.0.0.50",
            )

        assert excinfo_inexistente.value.codigo == excinfo_real.value.codigo
        assert str(excinfo_inexistente.value) == str(excinfo_real.value)

    def test_un_bloqueo_por_intentos_queda_auditado(self, db_session: Session) -> None:
        """Escenario "Un bloqueo por intentos queda auditado"."""
        organizacion = _crear_organizacion(db_session, "org-rl-6")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")

        for _ in range(5):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario.usuario,
                    password="mal",
                    ip="10.0.0.7",
                )
        with pytest.raises(LoginBloqueadoPorIntentosError):
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                ip="10.0.0.7",
            )

        auditorias = (
            db_session.query(Auditoria)
            .filter_by(
                organizacion_id=organizacion.id,
                accion="LOGIN_BLOQUEADO_POR_INTENTOS",
            )
            .all()
        )
        assert len(auditorias) == 1
        assert auditorias[0].usuario_id == usuario.id


class TestDesbloqueoAutomatico:
    def test_desbloqueo_automatico_al_vencer_la_ventana(self, db_session: Session) -> None:
        """Escenario homónimo (tarea 11.4): pasados los 15 minutos, los
        intentos fallidos anteriores dejan de contar."""
        organizacion = _crear_organizacion(db_session, "org-rl-7")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")

        for _ in range(5):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario.usuario,
                    password="mal",
                    ip="10.0.0.8",
                )
        with pytest.raises(LoginBloqueadoPorIntentosError):
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                ip="10.0.0.8",
            )

        momento_futuro = MOMENTO + timedelta(minutes=16)
        resultado = _login(
            db_session,
            reloj=FixedClock(momento_futuro),
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            ip="10.0.0.8",
        )
        assert resultado.usuario_id == usuario.id
