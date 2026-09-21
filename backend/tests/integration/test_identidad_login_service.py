"""Grupo 8.3/8.4: servicio de autenticación (login), sobre `ADR-021`
(resolución de organización por `organizacion_slug`) y `ADR-017`
(access/refresh tokens).
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
from app.modules.identidad.domain.usuarios import CredencialesInvalidasError
from app.modules.identidad.models import Auditoria, Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
JWT_SECRETO = "secreto-de-prueba"
JWT_KID = "1"
PASSWORD = "una-contrasena-larga-123"


def _crear_organizacion(sesion: Session, slug: str = "org-de-prueba") -> Organizacion:
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


def _crear_usuario_activo(
    sesion: Session, organizacion_id, *, nombre_usuario: str = "vendedor1", estado: str = "ACTIVO"
) -> object:
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
        estado=estado,
        momento=MOMENTO,
    )


def _iniciar_sesion(
    sesion: Session,
    *,
    organizacion_slug: str,
    nombre_usuario: str,
    password: str,
    dispositivo_id,
    reloj=None,
    ip: str = "127.0.0.1",
):
    return identidad_service.iniciar_sesion(
        sesion,
        reloj if reloj is not None else RELOJ,
        organizacion_slug=organizacion_slug,
        nombre_usuario=nombre_usuario,
        password=password,
        dispositivo_id=dispositivo_id,
        nombre_dispositivo="Tablet de reparto",
        jwt_secreto=JWT_SECRETO,
        jwt_kid=JWT_KID,
        ip=ip,
    )


class TestInicioDeSesionExitoso:
    def test_inicio_de_sesion_con_credenciales_correctas(self, db_session: Session) -> None:
        """Escenario "Inicio de sesión con credenciales correctas"."""
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)

        resultado = _iniciar_sesion(
            db_session,
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            dispositivo_id=nuevo_id(),
        )

        assert resultado.access_token
        assert resultado.refresh_token
        assert resultado.usuario_id == usuario.id
        assert resultado.organizacion_id == organizacion.id

    def test_el_primer_inicio_de_sesion_registra_el_dispositivo(self, db_session: Session) -> None:
        """Escenario "El primer inicio de sesión registra el dispositivo"."""
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_id = nuevo_id()

        resultado = _iniciar_sesion(
            db_session,
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            dispositivo_id=dispositivo_id,
        )

        dispositivo = repository.obtener_dispositivo_por_id(
            organizacion.id, dispositivo_id, db_session
        )
        assert dispositivo is not None
        assert dispositivo.estado == "ACTIVO"
        assert resultado.dispositivo_id == dispositivo.id

    def test_el_segundo_inicio_de_sesion_reutiliza_el_dispositivo(
        self, db_session: Session
    ) -> None:
        """Escenario "El segundo inicio de sesión reutiliza el dispositivo"."""
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_id = nuevo_id()
        _iniciar_sesion(
            db_session,
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            dispositivo_id=dispositivo_id,
        )
        prefijo_original = repository.obtener_dispositivo_por_id(
            organizacion.id, dispositivo_id, db_session
        ).prefijo  # type: ignore[union-attr]

        _iniciar_sesion(
            db_session,
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            dispositivo_id=dispositivo_id,
        )

        cantidad = (
            db_session.query(repository.Dispositivo)
            .filter_by(organizacion_id=organizacion.id, id=dispositivo_id)
            .count()
        )
        assert cantidad == 1
        dispositivo = repository.obtener_dispositivo_por_id(
            organizacion.id, dispositivo_id, db_session
        )
        assert dispositivo.prefijo == prefijo_original  # type: ignore[union-attr]

    def test_dos_usuarios_de_la_misma_organizacion_comparten_un_dispositivo(
        self, db_session: Session
    ) -> None:
        """Escenario "Dos usuarios de la misma organización comparten un
        dispositivo"."""
        organizacion = _crear_organizacion(db_session)
        usuario_a = _crear_usuario_activo(db_session, organizacion.id, nombre_usuario="a")
        usuario_b = _crear_usuario_activo(db_session, organizacion.id, nombre_usuario="b")
        dispositivo_id = nuevo_id()

        _iniciar_sesion(
            db_session,
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario_a.usuario,
            password=PASSWORD,
            dispositivo_id=dispositivo_id,
        )
        resultado_b = _iniciar_sesion(
            db_session,
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario_b.usuario,
            password=PASSWORD,
            dispositivo_id=dispositivo_id,
        )

        assert resultado_b.dispositivo_id == dispositivo_id

    def test_el_inicio_de_sesion_queda_auditado(self, db_session: Session) -> None:
        """Escenario "El inicio de sesión queda auditado"."""
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)

        _iniciar_sesion(
            db_session,
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            dispositivo_id=nuevo_id(),
        )

        auditoria = (
            db_session.query(Auditoria)
            .filter_by(organizacion_id=organizacion.id, accion="INICIO_SESION")
            .one()
        )
        assert auditoria.usuario_id == usuario.id


class TestRechazoDeInicioDeSesion:
    def test_contrasena_incorrecta_y_usuario_inexistente_son_indistinguibles(
        self, db_session: Session
    ) -> None:
        """Escenario "Contraseña incorrecta no distingue de usuario
        inexistente"."""
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)

        with pytest.raises(CredencialesInvalidasError) as exc_contrasena:
            _iniciar_sesion(
                db_session,
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password="contrasena-incorrecta",
                dispositivo_id=nuevo_id(),
            )
        with pytest.raises(CredencialesInvalidasError) as exc_inexistente:
            _iniciar_sesion(
                db_session,
                organizacion_slug=organizacion.slug,
                nombre_usuario="no-existe",
                password="cualquier-cosa",
                dispositivo_id=nuevo_id(),
            )

        assert exc_contrasena.value.codigo == exc_inexistente.value.codigo
        assert str(exc_contrasena.value) == str(exc_inexistente.value)

    def test_un_slug_inexistente_da_el_mismo_rechazo(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)

        with pytest.raises(CredencialesInvalidasError) as exc_slug_malo:
            _iniciar_sesion(
                db_session,
                organizacion_slug="slug-que-no-existe",
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                dispositivo_id=nuevo_id(),
            )
        with pytest.raises(CredencialesInvalidasError) as exc_credenciales:
            _iniciar_sesion(
                db_session,
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password="mal",
                dispositivo_id=nuevo_id(),
            )

        assert str(exc_slug_malo.value) == str(exc_credenciales.value)

    def test_un_usuario_inactivo_no_obtiene_sesion(self, db_session: Session) -> None:
        """Escenario "Un usuario inactivo no obtiene sesión"."""
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id, estado="INACTIVO")

        with pytest.raises(CredencialesInvalidasError):
            _iniciar_sesion(
                db_session,
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                dispositivo_id=nuevo_id(),
            )

    def test_un_inicio_de_sesion_sin_dispositivo_se_rechaza(self, db_session: Session) -> None:
        """Escenario "Un inicio de sesión sin dispositivo se rechaza"."""
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)

        with pytest.raises(CredencialesInvalidasError):
            _iniciar_sesion(
                db_session,
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                dispositivo_id=None,
            )

    def test_un_dispositivo_revocado_se_rechaza(self, db_session: Session) -> None:
        """Escenario "Un inicio de sesión desde un dispositivo revocado se
        rechaza"."""
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_id = nuevo_id()
        _iniciar_sesion(
            db_session,
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            dispositivo_id=dispositivo_id,
        )
        identidad_service.revocar_dispositivo(
            organizacion.id,
            db_session,
            RELOJ,
            dispositivo_id=dispositivo_id,
            actor_id=usuario.id,
        )

        with pytest.raises(CredencialesInvalidasError):
            _iniciar_sesion(
                db_session,
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                dispositivo_id=dispositivo_id,
            )

    def test_un_inicio_de_sesion_fallido_tambien_queda_auditado(self, db_session: Session) -> None:
        """Escenario "Un inicio de sesión fallido también queda auditado"."""
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)

        with pytest.raises(CredencialesInvalidasError):
            _iniciar_sesion(
                db_session,
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password="mal",
                dispositivo_id=nuevo_id(),
            )

        auditoria = (
            db_session.query(Auditoria)
            .filter_by(organizacion_id=organizacion.id, accion="INICIO_SESION_FALLIDO")
            .one()
        )
        assert auditoria.usuario_id == usuario.id
