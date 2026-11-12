"""Tarea 8.9 (alta de usuarios y composición de roles) y 8.9.a (invalidación
automática del PIN al perder el permiso que lo habilita, extensión de
`ADR-011` confirmada el 2026-09-19).

Estas tres escrituras (alta de usuario, composición de rol, invalidación de
PIN) quedan, a propósito, fuera del bus de comandos (`design.md` D6): el
change 04 las envuelve en comandos. `identidad/service.py` no hace
`commit`: la transacción la gestiona quien llama.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import (
    RolConPermisoInexistenteError,
    UsuarioSinRolError,
)
from app.modules.identidad.models import Auditoria, Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


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


def _crear_rol(sesion: Session, organizacion_id, nombre: str = "Supervisor") -> object:
    return repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre=nombre,
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )


def _crear_actor(sesion: Session, organizacion_id) -> object:
    """Un usuario cualquiera de `organizacion_id` para usar como `actor_id`
    en las pruebas: `auditoria.usuario_id` tiene FK compuesta a `usuario`
    (no acepta un UUID que no exista)."""
    rol_actor = _crear_rol(sesion, organizacion_id, nombre="Actor de prueba")
    usuario_actor = repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=f"actor-{nuevo_id().hex[:8]}",
        nombre="Actor de prueba",
        email=None,
        password_hash="hash-de-prueba",
        rol_id=rol_actor.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario_actor.id


class TestCrearUsuario:
    def test_un_alta_de_usuario_queda_auditada(self, db_session: Session) -> None:
        """Escenario "Un alta de usuario queda auditada"."""
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id)
        actor_id = _crear_actor(db_session, organizacion.id)

        usuario = identidad_service.crear_usuario(
            organizacion.id,
            db_session,
            RELOJ,
            usuario="vendedor1",
            nombre="Vendedor Uno",
            email=None,
            password="una-contrasena-larga-123",
            rol_id=rol.id,
            actor_id=actor_id,
        )

        assert usuario.usuario == "vendedor1"
        assert usuario.password_hash != "una-contrasena-larga-123"
        assert usuario.estado == "ACTIVO"

        auditorias = (
            db_session.query(Auditoria)
            .filter_by(organizacion_id=organizacion.id, entidad="usuario")
            .all()
        )
        assert len(auditorias) == 1
        assert auditorias[0].accion == "ALTA_USUARIO"
        assert auditorias[0].entidad_id == usuario.id
        assert auditorias[0].usuario_id == actor_id

    def test_un_usuario_no_puede_quedar_sin_rol(self, db_session: Session) -> None:
        """Escenario "Un usuario no puede quedar sin rol"."""
        organizacion = _crear_organizacion(db_session)
        actor_id = _crear_actor(db_session, organizacion.id)

        with pytest.raises(UsuarioSinRolError):
            identidad_service.crear_usuario(
                organizacion.id,
                db_session,
                RELOJ,
                usuario="sin-rol",
                nombre="Sin Rol",
                email=None,
                password="una-contrasena-larga-123",
                rol_id=None,  # type: ignore[arg-type]
                actor_id=actor_id,
            )

    def test_la_contrasena_nunca_se_guarda_en_claro(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id)
        actor_id = _crear_actor(db_session, organizacion.id)

        usuario = identidad_service.crear_usuario(
            organizacion.id,
            db_session,
            RELOJ,
            usuario="vendedor2",
            nombre="Vendedor Dos",
            email=None,
            password="otra-contrasena-larga-456",
            rol_id=rol.id,
            actor_id=actor_id,
        )

        assert "otra-contrasena-larga-456" not in usuario.password_hash


class TestCambiarComposicionDeRol:
    def test_una_organizacion_cambia_la_composicion_de_un_rol(self, db_session: Session) -> None:
        """Escenario "Una organización cambia la composición de un rol"."""
        org_a = _crear_organizacion(db_session)
        org_b = _crear_organizacion(db_session)
        rol_a = _crear_rol(db_session, org_a.id)
        rol_b = _crear_rol(db_session, org_b.id)
        actor_a = _crear_actor(db_session, org_a.id)
        actor_b = _crear_actor(db_session, org_b.id)
        for rol, actor_id in ((rol_a, actor_a), (rol_b, actor_b)):
            identidad_service.cambiar_composicion_rol(
                rol.organizacion_id,
                db_session,
                RELOJ,
                rol_id=rol.id,
                permisos_nuevos=frozenset({"LIBERAR_UBICACION", "GESTIONAR_CLIENTES"}),
                actor_id=actor_id,
            )

        identidad_service.cambiar_composicion_rol(
            org_a.id,
            db_session,
            RELOJ,
            rol_id=rol_a.id,
            permisos_nuevos=frozenset({"GESTIONAR_CLIENTES"}),
            actor_id=actor_a,
        )

        assert set(repository.listar_permisos_de_rol(org_a.id, rol_a.id, db_session)) == {
            "GESTIONAR_CLIENTES"
        }
        # El mismo rol de la otra organización no cambia.
        assert set(repository.listar_permisos_de_rol(org_b.id, rol_b.id, db_session)) == {
            "LIBERAR_UBICACION",
            "GESTIONAR_CLIENTES",
        }

    def test_un_rol_no_puede_referirse_a_un_permiso_inexistente(self, db_session: Session) -> None:
        """Escenario "Un rol no puede referirse a un permiso inexistente"."""
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id)
        actor_id = _crear_actor(db_session, organizacion.id)

        with pytest.raises(RolConPermisoInexistenteError):
            identidad_service.cambiar_composicion_rol(
                organizacion.id,
                db_session,
                RELOJ,
                rol_id=rol.id,
                permisos_nuevos=frozenset({"PERMISO_QUE_NO_EXISTE"}),
                actor_id=actor_id,
            )

        assert repository.listar_permisos_de_rol(organizacion.id, rol.id, db_session) == []

    def test_un_cambio_de_composicion_de_rol_queda_auditado(self, db_session: Session) -> None:
        """Escenario "Un cambio de composición de rol queda auditado"."""
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id)
        actor_id = _crear_actor(db_session, organizacion.id)

        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            db_session,
            RELOJ,
            rol_id=rol.id,
            permisos_nuevos=frozenset({"GESTIONAR_CLIENTES"}),
            actor_id=actor_id,
        )

        auditorias = (
            db_session.query(Auditoria)
            .filter_by(organizacion_id=organizacion.id, entidad="rol")
            .all()
        )
        assert len(auditorias) == 1
        assert auditorias[0].accion == "CAMBIAR_COMPOSICION_ROL"
        assert auditorias[0].usuario_id == actor_id
        assert auditorias[0].despues == {"permisos": ["GESTIONAR_CLIENTES"]}


class TestInvalidacionAutomaticaDelPin:
    """Tarea 8.9.a: extensión de `ADR-011` confirmada -- al perder el
    permiso que habilita el PIN de autorización, el servidor lo invalida en
    la misma transacción que el cambio de rol, auditado."""

    def _crear_usuario_con_pin(self, sesion: Session, organizacion_id, rol_id, actor_id) -> object:
        usuario = identidad_service.crear_usuario(
            organizacion_id,
            sesion,
            RELOJ,
            usuario="supervisor1",
            nombre="Supervisor Uno",
            email=None,
            password="una-contrasena-larga-123",
            rol_id=rol_id,
            actor_id=actor_id,
        )
        usuario.pin_autorizacion_hash = "hash-de-prueba"
        usuario.pin_autorizacion_sal = "sal-de-prueba"
        usuario.pin_autorizacion_iteraciones = 100_000
        sesion.flush()
        return usuario

    def test_quitarle_al_rol_su_ultimo_permiso_de_autorizacion_invalida_el_pin(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id)
        actor_id = _crear_actor(db_session, organizacion.id)
        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            db_session,
            RELOJ,
            rol_id=rol.id,
            permisos_nuevos=frozenset({"AUTORIZAR_DESCUENTO", "LIBERAR_UBICACION"}),
            actor_id=actor_id,
        )
        usuario = self._crear_usuario_con_pin(db_session, organizacion.id, rol.id, actor_id)

        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            db_session,
            RELOJ,
            rol_id=rol.id,
            permisos_nuevos=frozenset({"LIBERAR_UBICACION"}),
            actor_id=actor_id,
        )

        actualizado = repository.obtener_usuario_por_id(organizacion.id, usuario.id, db_session)
        assert actualizado is not None
        assert actualizado.pin_autorizacion_hash is None
        assert actualizado.pin_autorizacion_sal is None
        assert actualizado.pin_autorizacion_iteraciones is None

    def test_conservar_un_permiso_de_autorizacion_no_invalida_el_pin(
        self, db_session: Session
    ) -> None:
        """Triangulación: si el rol conserva al menos un permiso de
        autorización, el PIN no se toca."""
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id)
        actor_id = _crear_actor(db_session, organizacion.id)
        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            db_session,
            RELOJ,
            rol_id=rol.id,
            permisos_nuevos=frozenset({"AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO"}),
            actor_id=actor_id,
        )
        usuario = self._crear_usuario_con_pin(db_session, organizacion.id, rol.id, actor_id)

        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            db_session,
            RELOJ,
            rol_id=rol.id,
            permisos_nuevos=frozenset({"AUTORIZAR_DESCUENTO"}),
            actor_id=actor_id,
        )

        actualizado = repository.obtener_usuario_por_id(organizacion.id, usuario.id, db_session)
        assert actualizado is not None
        assert actualizado.pin_autorizacion_hash == "hash-de-prueba"

    def test_la_invalidacion_del_pin_queda_auditada_junto_con_el_cambio_de_rol(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id)
        actor_id = _crear_actor(db_session, organizacion.id)
        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            db_session,
            RELOJ,
            rol_id=rol.id,
            permisos_nuevos=frozenset({"AUTORIZAR_DESCUENTO"}),
            actor_id=actor_id,
        )
        usuario = self._crear_usuario_con_pin(db_session, organizacion.id, rol.id, actor_id)

        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            db_session,
            RELOJ,
            rol_id=rol.id,
            permisos_nuevos=frozenset(),
            actor_id=actor_id,
        )

        auditorias_pin = (
            db_session.query(Auditoria)
            .filter_by(
                organizacion_id=organizacion.id,
                entidad="usuario",
                accion="INVALIDAR_PIN_AUTORIZACION",
            )
            .all()
        )
        assert len(auditorias_pin) == 1
        assert auditorias_pin[0].entidad_id == usuario.id
        assert auditorias_pin[0].usuario_id == actor_id
        # Nunca se audita el valor del PIN (ni antes ni después).
        assert auditorias_pin[0].antes is None
        assert auditorias_pin[0].despues is None

    def test_recuperar_el_permiso_no_restaura_el_pin_anterior(self, db_session: Session) -> None:
        """Recuperar el permiso más adelante NO restaura el PIN viejo: el
        usuario queda sin PIN hasta que un admin le asigne uno nuevo."""
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol(db_session, organizacion.id)
        actor_id = _crear_actor(db_session, organizacion.id)
        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            db_session,
            RELOJ,
            rol_id=rol.id,
            permisos_nuevos=frozenset({"AUTORIZAR_DESCUENTO"}),
            actor_id=actor_id,
        )
        usuario = self._crear_usuario_con_pin(db_session, organizacion.id, rol.id, actor_id)

        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            db_session,
            RELOJ,
            rol_id=rol.id,
            permisos_nuevos=frozenset(),
            actor_id=actor_id,
        )
        identidad_service.cambiar_composicion_rol(
            organizacion.id,
            db_session,
            RELOJ,
            rol_id=rol.id,
            permisos_nuevos=frozenset({"AUTORIZAR_DESCUENTO"}),
            actor_id=actor_id,
        )

        actualizado = repository.obtener_usuario_por_id(organizacion.id, usuario.id, db_session)
        assert actualizado is not None
        assert actualizado.pin_autorizacion_hash is None
