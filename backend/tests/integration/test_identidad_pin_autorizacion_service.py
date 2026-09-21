"""Grupo 9: PIN de autorización (`ADR-019`, extensión de `ADR-011`).

**Nota de alcance:** la tarea 9.3 pide, entre sus rechazos, "rotar sin
`ADMIN_USUARIOS`". Ese chequeo de permiso es responsabilidad de la
dependencia de permisos del grupo 10 (`design.md`: "único camino" por el
que se aplica un permiso), todavía no implementada; igual que
`cambiar_composicion_rol` y `crear_usuario` del grupo 8.9, este servicio
recibe `actor_id` para auditar pero no valida el permiso del actor -- lo
hará el endpoint del grupo 10 antes de llamarlo. Las pruebas de esta sesión
cubren lo que el servicio SÍ decide: formato del PIN, que el rol confiera
autorización, y el aislamiento por organización (INV-21).
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
    PinAutorizacionInvalidoError,
    RolSinAutorizacionParaPinError,
)
from app.modules.identidad.models import Auditoria, Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


def _crear_organizacion(sesion: Session, nombre: str = "Organización de prueba") -> Organizacion:
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


def _crear_rol_con_permisos(sesion: Session, organizacion_id, permisos: frozenset[str]) -> object:
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


def _crear_usuario(sesion: Session, organizacion_id, rol_id, nombre_usuario: str) -> object:
    return repository.crear_usuario(
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


class TestEstablecerPinAutorizacion:
    def test_el_pin_nunca_queda_almacenado_en_claro(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol_con_permisos(
            db_session, organizacion.id, frozenset({"AUTORIZAR_DESCUENTO"})
        )
        supervisor = _crear_usuario(db_session, organizacion.id, rol.id, "supervisor1")

        actualizado = identidad_service.establecer_pin_autorizacion(
            organizacion.id,
            db_session,
            RELOJ,
            usuario_id=supervisor.id,
            pin="482913",
            actor_id=supervisor.id,
        )

        assert actualizado is not None
        assert actualizado.pin_autorizacion_hash is not None
        assert "482913" not in actualizado.pin_autorizacion_hash
        assert actualizado.pin_autorizacion_sal is not None
        assert actualizado.pin_autorizacion_iteraciones is not None

    def test_un_pin_de_menos_de_seis_digitos_se_rechaza_y_no_toca_el_anterior(
        self, db_session: Session
    ) -> None:
        """Escenario "Un PIN de menos de seis dígitos se rechaza"."""
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol_con_permisos(
            db_session, organizacion.id, frozenset({"AUTORIZAR_DESCUENTO"})
        )
        supervisor = _crear_usuario(db_session, organizacion.id, rol.id, "supervisor1")
        identidad_service.establecer_pin_autorizacion(
            organizacion.id,
            db_session,
            RELOJ,
            usuario_id=supervisor.id,
            pin="482913",
            actor_id=supervisor.id,
        )
        hash_anterior = repository.obtener_usuario_por_id(
            organizacion.id, supervisor.id, db_session
        ).pin_autorizacion_hash  # type: ignore[union-attr]

        with pytest.raises(PinAutorizacionInvalidoError):
            identidad_service.establecer_pin_autorizacion(
                organizacion.id,
                db_session,
                RELOJ,
                usuario_id=supervisor.id,
                pin="12345",
                actor_id=supervisor.id,
            )

        actualizado = repository.obtener_usuario_por_id(organizacion.id, supervisor.id, db_session)
        assert actualizado is not None
        assert actualizado.pin_autorizacion_hash == hash_anterior

    def test_un_pin_con_caracteres_que_no_son_digitos_se_rechaza(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol_con_permisos(
            db_session, organizacion.id, frozenset({"AUTORIZAR_DESCUENTO"})
        )
        supervisor = _crear_usuario(db_session, organizacion.id, rol.id, "supervisor1")

        with pytest.raises(PinAutorizacionInvalidoError):
            identidad_service.establecer_pin_autorizacion(
                organizacion.id,
                db_session,
                RELOJ,
                usuario_id=supervisor.id,
                pin="12a456",
                actor_id=supervisor.id,
            )

    def test_un_vendedor_no_puede_definir_pin_de_autorizacion(self, db_session: Session) -> None:
        """Escenario "Un vendedor no puede definir PIN de autorización"."""
        organizacion = _crear_organizacion(db_session)
        rol_vendedor = _crear_rol_con_permisos(
            db_session, organizacion.id, frozenset({"VENDER", "REGISTRAR_COBRANZA"})
        )
        vendedor = _crear_usuario(db_session, organizacion.id, rol_vendedor.id, "vendedor1")

        with pytest.raises(RolSinAutorizacionParaPinError):
            identidad_service.establecer_pin_autorizacion(
                organizacion.id,
                db_session,
                RELOJ,
                usuario_id=vendedor.id,
                pin="482913",
                actor_id=vendedor.id,
            )

    def test_dos_supervisores_con_el_mismo_pin_tienen_derivaciones_distintas(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol_con_permisos(
            db_session, organizacion.id, frozenset({"AUTORIZAR_DESCUENTO"})
        )
        supervisor_1 = _crear_usuario(db_session, organizacion.id, rol.id, "supervisor1")
        supervisor_2 = _crear_usuario(db_session, organizacion.id, rol.id, "supervisor2")

        identidad_service.establecer_pin_autorizacion(
            organizacion.id,
            db_session,
            RELOJ,
            usuario_id=supervisor_1.id,
            pin="482913",
            actor_id=supervisor_1.id,
        )
        identidad_service.establecer_pin_autorizacion(
            organizacion.id,
            db_session,
            RELOJ,
            usuario_id=supervisor_2.id,
            pin="482913",
            actor_id=supervisor_2.id,
        )

        u1 = repository.obtener_usuario_por_id(organizacion.id, supervisor_1.id, db_session)
        u2 = repository.obtener_usuario_por_id(organizacion.id, supervisor_2.id, db_session)
        assert u1.pin_autorizacion_hash != u2.pin_autorizacion_hash  # type: ignore[union-attr]
        assert u1.pin_autorizacion_sal != u2.pin_autorizacion_sal  # type: ignore[union-attr]


class TestRotarPinAutorizacion:
    def test_rotar_el_pin_invalida_el_anterior(self, db_session: Session) -> None:
        """Escenario "Rotar el PIN invalida el anterior"."""
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol_con_permisos(
            db_session, organizacion.id, frozenset({"AUTORIZAR_DESCUENTO"})
        )
        supervisor = _crear_usuario(db_session, organizacion.id, rol.id, "supervisor1")
        identidad_service.establecer_pin_autorizacion(
            organizacion.id,
            db_session,
            RELOJ,
            usuario_id=supervisor.id,
            pin="111111",
            actor_id=supervisor.id,
        )
        hash_anterior = repository.obtener_usuario_por_id(
            organizacion.id, supervisor.id, db_session
        ).pin_autorizacion_hash  # type: ignore[union-attr]
        admin = _crear_usuario(db_session, organizacion.id, rol.id, "admin1")

        identidad_service.establecer_pin_autorizacion(
            organizacion.id,
            db_session,
            RELOJ,
            usuario_id=supervisor.id,
            pin="222222",
            actor_id=admin.id,
        )

        actualizado = repository.obtener_usuario_por_id(organizacion.id, supervisor.id, db_session)
        assert actualizado is not None
        assert actualizado.pin_autorizacion_hash != hash_anterior

    def test_rotar_el_pin_de_un_usuario_de_otra_organizacion_no_lo_encuentra(
        self, db_session: Session
    ) -> None:
        """Escenario "Rotar el PIN de un usuario de otra organización no lo
        encuentra"."""
        org_a = _crear_organizacion(db_session, "Organización A")
        org_b = _crear_organizacion(db_session, "Organización B")
        rol_a = _crear_rol_con_permisos(db_session, org_a.id, frozenset({"AUTORIZAR_DESCUENTO"}))
        supervisor_a = _crear_usuario(db_session, org_a.id, rol_a.id, "supervisor1")
        rol_b = _crear_rol_con_permisos(db_session, org_b.id, frozenset({"AUTORIZAR_DESCUENTO"}))
        admin_b = _crear_usuario(db_session, org_b.id, rol_b.id, "admin1")

        resultado = identidad_service.establecer_pin_autorizacion(
            org_b.id,
            db_session,
            RELOJ,
            usuario_id=supervisor_a.id,
            pin="999999",
            actor_id=admin_b.id,
        )

        assert resultado is None
        assert (
            repository.obtener_usuario_por_id(
                org_a.id, supervisor_a.id, db_session
            ).pin_autorizacion_hash  # type: ignore[union-attr]
            is None
        )

    def test_la_rotacion_queda_auditada_sin_exponer_el_pin(self, db_session: Session) -> None:
        """Escenario "La rotación queda auditada sin exponer el PIN"."""
        organizacion = _crear_organizacion(db_session)
        rol = _crear_rol_con_permisos(
            db_session, organizacion.id, frozenset({"AUTORIZAR_DESCUENTO"})
        )
        supervisor = _crear_usuario(db_session, organizacion.id, rol.id, "supervisor1")
        admin = _crear_usuario(db_session, organizacion.id, rol.id, "admin1")

        identidad_service.establecer_pin_autorizacion(
            organizacion.id,
            db_session,
            RELOJ,
            usuario_id=supervisor.id,
            pin="482913",
            actor_id=admin.id,
        )

        auditoria = (
            db_session.query(Auditoria)
            .filter_by(organizacion_id=organizacion.id, entidad="usuario", entidad_id=supervisor.id)
            .one()
        )
        assert auditoria.usuario_id == admin.id
        assert auditoria.antes is None
        assert auditoria.despues is None
        assert "482913" not in (auditoria.observacion or "")
