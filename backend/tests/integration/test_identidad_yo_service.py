"""Grupo 3 del change 06b: `identidad_service.obtener_yo` (D1, `design.md`
"Contrato de `GET /api/v1/yo`").

`obtener_yo(organizacion_id, usuario_id, sesion) -> DatosYo` es la única
fuente de datos de la ruta `GET /api/v1/yo` (grupo 4, todavía sin escribir).
Antes de leer nada llama a `exigir_sesion_habilitada` (ADR-028, D9); los
permisos salen exclusivamente de `listar_permisos_del_usuario` más
`sorted()`, para que "lo que informa `/yo`" y "lo que autoriza el servidor"
sean, por construcción, la misma función (ADR-027).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.core.seguridad import AccessTokenInvalidoError, hashear_password
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.permisos import (
    ADMINISTRACION,
    ADMINISTRADOR,
    CONSULTA_DIRECCION,
    PLANTILLAS_DE_ROL,
    SUPERVISOR_COMERCIAL,
    VENDEDOR_REPARTIDOR,
)
from app.modules.identidad.models import Organizacion

PASSWORD = "una-contrasena-larga-de-prueba-yo-service-123"
MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


def _crear_organizacion(
    sesion: Session, slug: str, nombre: str = "Organización de prueba"
) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre=nombre,
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


def _crear_usuario_con_rol(
    sesion: Session,
    organizacion_id: UUID,
    *,
    nombre_rol: str = "Rol de prueba",
    permisos_rol: frozenset[str] = frozenset(),
    estado_usuario: str = "ACTIVO",
    rol_activo: bool = True,
    nombre_usuario: str = "Persona de prueba",
) -> tuple[UUID, UUID]:
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre=nombre_rol,
        tope_descuento=Decimal("0"),
        activo=rol_activo,
        momento=MOMENTO,
    )
    for codigo in permisos_rol:
        repository.asignar_permiso_a_rol(
            organizacion_id, sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    usuario = repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=f"usuario-{uuid4().hex[:8]}",
        nombre=nombre_usuario,
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado=estado_usuario,
        momento=MOMENTO,
    )
    return usuario.id, rol.id


class TestObtenerYo:
    """Escenarios de `identidad/autenticacion-y-sesion` para `obtener_yo`."""

    def test_usuario_de_administracion_obtiene_sus_permisos_ordenados(
        self, db_session: Session
    ) -> None:
        """ADR-027: usuario, organización y rol (id y nombre), y los
        permisos del rol en orden alfabético ascendente."""
        organizacion = _crear_organizacion(
            db_session, f"org-yo-{uuid4().hex[:8]}", nombre="Distribuidora de prueba"
        )
        permisos = PLANTILLAS_DE_ROL[ADMINISTRACION]
        usuario_id, rol_id = _crear_usuario_con_rol(
            db_session,
            organizacion.id,
            nombre_rol=ADMINISTRACION,
            permisos_rol=permisos,
            nombre_usuario="Administración de prueba",
        )

        datos = identidad_service.obtener_yo(organizacion.id, usuario_id, db_session)

        assert datos.usuario.id == usuario_id
        assert datos.usuario.nombre == "Administración de prueba"
        assert datos.organizacion.id == organizacion.id
        assert datos.organizacion.nombre == "Distribuidora de prueba"
        assert datos.rol.id == rol_id
        assert datos.rol.nombre == ADMINISTRACION
        assert datos.permisos == sorted(permisos)
        assert list(datos.permisos) == sorted(datos.permisos)

    def test_rol_con_la_composicion_vaciada_da_permisos_vacio(self, db_session: Session) -> None:
        """Un rol sin permisos asignados devuelve `permisos == []`, no un
        error: la composición vacía es un estado válido."""
        organizacion = _crear_organizacion(db_session, f"org-yo-vacio-{uuid4().hex[:8]}")
        usuario_id, _ = _crear_usuario_con_rol(
            db_session, organizacion.id, permisos_rol=frozenset()
        )

        datos = identidad_service.obtener_yo(organizacion.id, usuario_id, db_session)

        assert datos.permisos == []

    def test_usuario_de_otra_organizacion_da_401_generico(self, db_session: Session) -> None:
        """D1: el mismo 401 `IDENTIDAD_ACCESS_TOKEN_INVALIDO` que un usuario
        inexistente -- nunca datos parciales de otra organización (INV-21)."""
        organizacion_a = _crear_organizacion(db_session, f"org-yo-a-{uuid4().hex[:8]}")
        organizacion_b = _crear_organizacion(db_session, f"org-yo-b-{uuid4().hex[:8]}")
        usuario_id, _ = _crear_usuario_con_rol(db_session, organizacion_b.id)

        with pytest.raises(AccessTokenInvalidoError):
            identidad_service.obtener_yo(organizacion_a.id, usuario_id, db_session)

    def test_usuario_inexistente_da_401_generico(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, f"org-yo-inexistente-{uuid4().hex[:8]}")

        with pytest.raises(AccessTokenInvalidoError):
            identidad_service.obtener_yo(organizacion.id, uuid4(), db_session)

    def test_usuario_inactivo_da_el_mismo_401_nunca_200_con_lista_vacia(
        self, db_session: Session
    ) -> None:
        """(D9) ADR-028 D9.2-A: un usuario `INACTIVO` rechaza igual que uno
        inexistente -- nunca un 200 con `permisos == []`."""
        organizacion = _crear_organizacion(db_session, f"org-yo-inactivo-{uuid4().hex[:8]}")
        usuario_id, _ = _crear_usuario_con_rol(
            db_session, organizacion.id, estado_usuario="INACTIVO"
        )

        with pytest.raises(AccessTokenInvalidoError):
            identidad_service.obtener_yo(organizacion.id, usuario_id, db_session)

    def test_rol_inactivo_da_el_mismo_401_nunca_200_con_lista_vacia(
        self, db_session: Session
    ) -> None:
        """(D9) ADR-028 D9.4-A: mismo tratamiento que un usuario inactivo."""
        organizacion = _crear_organizacion(db_session, f"org-yo-rol-inactivo-{uuid4().hex[:8]}")
        usuario_id, _ = _crear_usuario_con_rol(db_session, organizacion.id, rol_activo=False)

        with pytest.raises(AccessTokenInvalidoError):
            identidad_service.obtener_yo(organizacion.id, usuario_id, db_session)

    @pytest.mark.parametrize(
        "nombre_plantilla",
        [
            ADMINISTRADOR,
            ADMINISTRACION,
            SUPERVISOR_COMERCIAL,
            VENDEDOR_REPARTIDOR,
            CONSULTA_DIRECCION,
        ],
    )
    def test_mismo_resultado_que_listar_permisos_del_usuario_por_plantilla(
        self, db_session: Session, nombre_plantilla: str
    ) -> None:
        """`01` §19: para cada plantilla de rol, los permisos que informa
        `obtener_yo` son exactamente los que autoriza el servidor
        (`listar_permisos_del_usuario`), sin divergencia."""
        organizacion = _crear_organizacion(db_session, f"org-yo-plantilla-{uuid4().hex[:8]}")
        permisos_de_la_plantilla = PLANTILLAS_DE_ROL[nombre_plantilla]
        usuario_id, _ = _crear_usuario_con_rol(
            db_session,
            organizacion.id,
            nombre_rol=nombre_plantilla,
            permisos_rol=permisos_de_la_plantilla,
        )

        datos = identidad_service.obtener_yo(organizacion.id, usuario_id, db_session)
        permisos_autorizados = identidad_service.listar_permisos_del_usuario(
            organizacion.id, usuario_id, db_session
        )

        assert datos.permisos == sorted(permisos_autorizados)
