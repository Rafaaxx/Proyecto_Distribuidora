"""Grupo 8.5-8.8: rotación del refresh token, detección de reuso, rechazos
de renovación y cierre de sesión (`ADR-017`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.core.seguridad import derivar_hash_refresh_token, hashear_password
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import RefreshTokenInvalidoError
from app.modules.identidad.models import Auditoria, Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
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
    sesion: Session, organizacion_id, nombre_usuario: str = "vendedor1"
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
        estado="ACTIVO",
        momento=MOMENTO,
    )


def _login(sesion: Session, reloj, organizacion, usuario, dispositivo_id, ip: str = "127.0.0.1"):
    return identidad_service.iniciar_sesion(
        sesion,
        reloj,
        organizacion_slug=organizacion.slug,
        nombre_usuario=usuario.usuario,
        password=PASSWORD,
        dispositivo_id=dispositivo_id,
        nombre_dispositivo="Tablet",
        jwt_secreto=JWT_SECRETO,
        jwt_kid=JWT_KID,
        ip=ip,
    )


class TestRotacionDeRefresh:
    def test_renovar_la_sesion_rota_el_refresh_token(self, db_session: Session) -> None:
        """Escenario "Renovar la sesión rota el refresh token"."""
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_id = nuevo_id()
        primero = _login(db_session, FixedClock(MOMENTO), organizacion, usuario, dispositivo_id)

        # Reloj distinto para la rotación: un access token emitido en el
        # mismo instante, con los mismos claims, es determinísticamente
        # idéntico (JWT no lleva aleatoriedad propia) -- eso no es un bug,
        # así que la prueba avanza el reloj para reflejar una renovación
        # real, que nunca ocurre en el mismo instante que el login.
        reloj_rotacion = FixedClock(MOMENTO + timedelta(minutes=1))
        segundo = identidad_service.renovar_sesion(
            db_session,
            reloj_rotacion,
            refresh_token_claro=primero.refresh_token,
            dispositivo_id=dispositivo_id,
            jwt_secreto=JWT_SECRETO,
            jwt_kid=JWT_KID,
        )

        assert segundo.access_token != primero.access_token
        assert segundo.refresh_token != primero.refresh_token

        with pytest.raises(RefreshTokenInvalidoError):
            identidad_service.renovar_sesion(
                db_session,
                reloj_rotacion,
                refresh_token_claro=primero.refresh_token,
                dispositivo_id=dispositivo_id,
                jwt_secreto=JWT_SECRETO,
                jwt_kid=JWT_KID,
            )

    def test_el_vencimiento_se_renueva_en_cada_rotacion(self, db_session: Session) -> None:
        """Escenario "El vencimiento se renueva en cada rotación"."""
        momento_login = MOMENTO
        reloj_login = FixedClock(momento_login)
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_id = nuevo_id()
        primero = _login(db_session, reloj_login, organizacion, usuario, dispositivo_id)

        momento_rotacion = momento_login + timedelta(days=29)
        reloj_rotacion = FixedClock(momento_rotacion)
        segundo = identidad_service.renovar_sesion(
            db_session,
            reloj_rotacion,
            refresh_token_claro=primero.refresh_token,
            dispositivo_id=dispositivo_id,
            jwt_secreto=JWT_SECRETO,
            jwt_kid=JWT_KID,
        )

        fila_nueva = repository.obtener_sesion_refresh_por_token_hash_global(
            derivar_hash_refresh_token(segundo.refresh_token),
            db_session,
        )
        assert fila_nueva is not None
        assert fila_nueva.expira_en == momento_rotacion + timedelta(days=30)


class TestDeteccionDeReuso:
    def test_el_reuso_de_un_token_rotado_corta_toda_la_familia(self, db_session: Session) -> None:
        """Escenario "El reuso de un token rotado corta toda la familia"."""
        reloj = FixedClock(MOMENTO)
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_id = nuevo_id()
        t1 = _login(db_session, reloj, organizacion, usuario, dispositivo_id)
        t2 = identidad_service.renovar_sesion(
            db_session,
            reloj,
            refresh_token_claro=t1.refresh_token,
            dispositivo_id=dispositivo_id,
            jwt_secreto=JWT_SECRETO,
            jwt_kid=JWT_KID,
        )

        with pytest.raises(RefreshTokenInvalidoError):
            identidad_service.renovar_sesion(
                db_session,
                reloj,
                refresh_token_claro=t1.refresh_token,
                dispositivo_id=dispositivo_id,
                jwt_secreto=JWT_SECRETO,
                jwt_kid=JWT_KID,
            )

        with pytest.raises(RefreshTokenInvalidoError):
            identidad_service.renovar_sesion(
                db_session,
                reloj,
                refresh_token_claro=t2.refresh_token,
                dispositivo_id=dispositivo_id,
                jwt_secreto=JWT_SECRETO,
                jwt_kid=JWT_KID,
            )

    def test_la_revocacion_por_reuso_queda_auditada(self, db_session: Session) -> None:
        """Escenario "La revocación por reuso queda auditada"."""
        reloj = FixedClock(MOMENTO)
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_id = nuevo_id()
        t1 = _login(db_session, reloj, organizacion, usuario, dispositivo_id)
        identidad_service.renovar_sesion(
            db_session,
            reloj,
            refresh_token_claro=t1.refresh_token,
            dispositivo_id=dispositivo_id,
            jwt_secreto=JWT_SECRETO,
            jwt_kid=JWT_KID,
        )

        with pytest.raises(RefreshTokenInvalidoError):
            identidad_service.renovar_sesion(
                db_session,
                reloj,
                refresh_token_claro=t1.refresh_token,
                dispositivo_id=dispositivo_id,
                jwt_secreto=JWT_SECRETO,
                jwt_kid=JWT_KID,
            )

        auditoria = (
            db_session.query(Auditoria)
            .filter_by(organizacion_id=organizacion.id, accion="REVOCAR_FAMILIA_REFRESH")
            .one()
        )
        assert auditoria.usuario_id == usuario.id
        assert auditoria.dispositivo_id == dispositivo_id

    def test_la_revocacion_de_una_familia_no_afecta_a_otros_dispositivos(
        self, db_session: Session
    ) -> None:
        """Escenario "La revocación de una familia no afecta a otros
        dispositivos"."""
        reloj = FixedClock(MOMENTO)
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_1, dispositivo_2 = nuevo_id(), nuevo_id()
        t1_d1 = _login(db_session, reloj, organizacion, usuario, dispositivo_1)
        t1_d2 = _login(db_session, reloj, organizacion, usuario, dispositivo_2)
        identidad_service.renovar_sesion(
            db_session,
            reloj,
            refresh_token_claro=t1_d1.refresh_token,
            dispositivo_id=dispositivo_1,
            jwt_secreto=JWT_SECRETO,
            jwt_kid=JWT_KID,
        )

        with pytest.raises(RefreshTokenInvalidoError):
            identidad_service.renovar_sesion(
                db_session,
                reloj,
                refresh_token_claro=t1_d1.refresh_token,
                dispositivo_id=dispositivo_1,
                jwt_secreto=JWT_SECRETO,
                jwt_kid=JWT_KID,
            )

        # d2 sigue pudiendo renovarse.
        identidad_service.renovar_sesion(
            db_session,
            reloj,
            refresh_token_claro=t1_d2.refresh_token,
            dispositivo_id=dispositivo_2,
            jwt_secreto=JWT_SECRETO,
            jwt_kid=JWT_KID,
        )


class TestRechazosDeRenovacion:
    def test_un_token_vencido_obliga_a_iniciar_sesion(self, db_session: Session) -> None:
        """Escenario "Un refresh token vencido obliga a iniciar sesión"."""
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_id = nuevo_id()
        t1 = _login(db_session, FixedClock(MOMENTO), organizacion, usuario, dispositivo_id)

        reloj_futuro = FixedClock(MOMENTO + timedelta(days=31))
        with pytest.raises(RefreshTokenInvalidoError):
            identidad_service.renovar_sesion(
                db_session,
                reloj_futuro,
                refresh_token_claro=t1.refresh_token,
                dispositivo_id=dispositivo_id,
                jwt_secreto=JWT_SECRETO,
                jwt_kid=JWT_KID,
            )

    def test_un_token_de_otro_dispositivo_no_sirve(self, db_session: Session) -> None:
        """Escenario "Un refresh token de otro dispositivo no sirve"."""
        reloj = FixedClock(MOMENTO)
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_1, dispositivo_2 = nuevo_id(), nuevo_id()
        t1 = _login(db_session, reloj, organizacion, usuario, dispositivo_1)

        with pytest.raises(RefreshTokenInvalidoError):
            identidad_service.renovar_sesion(
                db_session,
                reloj,
                refresh_token_claro=t1.refresh_token,
                dispositivo_id=dispositivo_2,
                jwt_secreto=JWT_SECRETO,
                jwt_kid=JWT_KID,
            )

    def test_un_token_de_una_sesion_cerrada_no_sirve(self, db_session: Session) -> None:
        reloj = FixedClock(MOMENTO)
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_id = nuevo_id()
        t1 = _login(db_session, reloj, organizacion, usuario, dispositivo_id)
        identidad_service.cerrar_sesion(db_session, reloj, refresh_token_claro=t1.refresh_token)

        with pytest.raises(RefreshTokenInvalidoError):
            identidad_service.renovar_sesion(
                db_session,
                reloj,
                refresh_token_claro=t1.refresh_token,
                dispositivo_id=dispositivo_id,
                jwt_secreto=JWT_SECRETO,
                jwt_kid=JWT_KID,
            )


class TestCierreDeSesion:
    def test_despues_de_cerrar_sesion_no_se_puede_renovar(self, db_session: Session) -> None:
        """Escenario "Después de cerrar sesión no se puede renovar"."""
        reloj = FixedClock(MOMENTO)
        organizacion = _crear_organizacion(db_session)
        usuario = _crear_usuario_activo(db_session, organizacion.id)
        dispositivo_id = nuevo_id()
        t1 = _login(db_session, reloj, organizacion, usuario, dispositivo_id)

        identidad_service.cerrar_sesion(db_session, reloj, refresh_token_claro=t1.refresh_token)

        with pytest.raises(RefreshTokenInvalidoError):
            identidad_service.renovar_sesion(
                db_session,
                reloj,
                refresh_token_claro=t1.refresh_token,
                dispositivo_id=dispositivo_id,
                jwt_secreto=JWT_SECRETO,
                jwt_kid=JWT_KID,
            )

    def test_cerrar_sesion_sin_sesion_activa_no_falla(self, db_session: Session) -> None:
        """Escenario "Cerrar sesión sin sesión activa no falla"."""
        reloj = FixedClock(MOMENTO)
        identidad_service.cerrar_sesion(db_session, reloj, refresh_token_claro=None)
        identidad_service.cerrar_sesion(db_session, reloj, refresh_token_claro="token-inexistente")
