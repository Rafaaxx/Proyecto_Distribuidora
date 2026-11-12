"""Tareas 6.5 y 6.6: unicidad de `usuario.usuario` y `dispositivo.prefijo`
dentro de la organización (no entre organizaciones), y que un usuario no
pueda tomar un rol de otra organización (rechazado por la FK compuesta, no
por código de aplicación).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


def _crear_organizacion(sesion: Session, nombre: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre=nombre,
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


def _crear_rol(sesion: Session, organizacion_id: UUID, nombre: str = "Vendedor") -> UUID:
    rol = identidad_repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre=nombre,
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    return rol.id


def _crear_usuario(
    sesion: Session, organizacion_id: UUID, rol_id: UUID, nombre_usuario: str
) -> UUID:
    usuario = identidad_repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=nombre_usuario,
        nombre="Persona de prueba",
        email=None,
        password_hash="hash-de-prueba",
        rol_id=rol_id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario.id


@pytest.fixture
def dos_organizaciones_con_rol(
    db_session: Session,
) -> tuple[Organizacion, UUID, Organizacion, UUID]:
    org_a = _crear_organizacion(db_session, "Organización A")
    rol_a = _crear_rol(db_session, org_a.id)
    org_b = _crear_organizacion(db_session, "Organización B")
    rol_b = _crear_rol(db_session, org_b.id)
    return org_a, rol_a, org_b, rol_b


class TestUnicidadDeNombreDeUsuario:
    def test_dos_organizaciones_pueden_tener_el_mismo_nombre_de_usuario(
        self,
        db_session: Session,
        dos_organizaciones_con_rol: tuple[Organizacion, UUID, Organizacion, UUID],
    ) -> None:
        org_a, rol_a, org_b, rol_b = dos_organizaciones_con_rol

        _crear_usuario(db_session, org_a.id, rol_a, "admin")
        _crear_usuario(db_session, org_b.id, rol_b, "admin")  # no debe fallar

        assert (
            identidad_repository.obtener_usuario_por_nombre_usuario(org_a.id, "admin", db_session)
            is not None
        )
        assert (
            identidad_repository.obtener_usuario_por_nombre_usuario(org_b.id, "admin", db_session)
            is not None
        )

    def test_un_nombre_de_usuario_repetido_dentro_de_la_organizacion_se_rechaza(
        self,
        db_session: Session,
        dos_organizaciones_con_rol: tuple[Organizacion, UUID, Organizacion, UUID],
    ) -> None:
        org_a, rol_a, _org_b, _rol_b = dos_organizaciones_con_rol
        _crear_usuario(db_session, org_a.id, rol_a, "vendedor1")

        with pytest.raises(IntegrityError):
            _crear_usuario(db_session, org_a.id, rol_a, "vendedor1")


class TestUnicidadDePrefijoDeDispositivo:
    def test_dos_dispositivos_de_la_misma_organizacion_no_comparten_prefijo(
        self, db_session: Session, dos_organizaciones_con_rol: tuple
    ) -> None:
        org_a, *_ = dos_organizaciones_con_rol
        identidad_repository.crear_dispositivo(
            org_a.id,
            db_session,
            dispositivo_id=nuevo_id(),
            nombre="Tablet 1",
            prefijo="V01",
            ultimo_correlativo=0,
            estado="ACTIVO",
            momento=MOMENTO,
        )

        with pytest.raises(IntegrityError):
            identidad_repository.crear_dispositivo(
                org_a.id,
                db_session,
                dispositivo_id=nuevo_id(),
                nombre="Tablet 2",
                prefijo="V01",
                ultimo_correlativo=0,
                estado="ACTIVO",
                momento=MOMENTO,
            )

    def test_dos_organizaciones_pueden_usar_el_mismo_prefijo(
        self, db_session: Session, dos_organizaciones_con_rol: tuple
    ) -> None:
        org_a, _rol_a, org_b, _rol_b = dos_organizaciones_con_rol

        identidad_repository.crear_dispositivo(
            org_a.id,
            db_session,
            dispositivo_id=nuevo_id(),
            nombre="Tablet A",
            prefijo="V01",
            ultimo_correlativo=0,
            estado="ACTIVO",
            momento=MOMENTO,
        )
        # No debe fallar: el prefijo se repite pero en otra organización.
        identidad_repository.crear_dispositivo(
            org_b.id,
            db_session,
            dispositivo_id=nuevo_id(),
            nombre="Tablet B",
            prefijo="V01",
            ultimo_correlativo=0,
            estado="ACTIVO",
            momento=MOMENTO,
        )

        assert (
            identidad_repository.obtener_dispositivo_por_prefijo(org_a.id, "V01", db_session)
            is not None
        )
        assert (
            identidad_repository.obtener_dispositivo_por_prefijo(org_b.id, "V01", db_session)
            is not None
        )


def test_un_usuario_no_puede_tomar_un_rol_de_otra_organizacion(
    db_session: Session,
    dos_organizaciones_con_rol: tuple[Organizacion, UUID, Organizacion, UUID],
) -> None:
    """Escenario "Un usuario no puede tomar un rol de otra organización":
    rechazado por la FK compuesta `fk_usuario__rol` (INV-21, `03` §2.4), no
    por una validación de aplicación."""
    org_a, _rol_a, _org_b, rol_b = dos_organizaciones_con_rol

    with pytest.raises(IntegrityError):
        _crear_usuario(db_session, org_a.id, rol_b, "vendedor_con_rol_ajeno")
