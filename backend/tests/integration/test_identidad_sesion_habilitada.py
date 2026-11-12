"""ADR-028 / D9 (grupo 2 del change 06b): la sesión exige usuario y rol
activos. `identidad_service.exigir_sesion_habilitada(organizacion_id,
usuario_id, sesion)` es el punto único que lo verifica (`design.md` D9,
"Punto técnico de implementación"): la usan `requiere_permiso` (`core/
autenticacion.py`), `obtener_yo` (grupo 3) y `renovar_sesion` (más abajo en
este mismo grupo).

D9.2-A (aprobada por el usuario el 2026-09-25): el rechazo reusa el mismo
401 `IDENTIDAD_ACCESS_TOKEN_INVALIDO` que ya existe para un access token con
firma alterada o para el usuario del token inexistente (D1) -- nunca revela
si la causa fue el usuario, el rol, o que no existe (SEG-06, falla cerrada).

Hasta que exista el comando de baja de usuarios o de roles (D9.5, nota para
el change que lo agregue), estas pruebas siembran `usuario.estado =
'INACTIVO'` y `rol.activo = false` directamente en la base de prueba
(Testcontainers), documentado acá como el auxiliar `_desactivar_usuario`/
`_desactivar_rol` (`tasks.md` 2.x, nota del grupo 2).
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
from app.modules.identidad.models import Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-de-prueba-sesion-123"


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


def _crear_usuario_con_rol(
    sesion: Session,
    organizacion_id: UUID,
    *,
    estado_usuario: str = "ACTIVO",
    rol_activo: bool = True,
    nombre_usuario: str | None = None,
) -> tuple[UUID, UUID]:
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre=f"Rol de prueba {uuid4().hex[:6]}",
        tope_descuento=Decimal("0"),
        activo=rol_activo,
        momento=MOMENTO,
    )
    usuario = repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=nombre_usuario or f"usuario-{uuid4().hex[:8]}",
        nombre="Persona de prueba",
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado=estado_usuario,
        momento=MOMENTO,
    )
    return usuario.id, rol.id


class TestExigirSesionHabilitada:
    """Escenarios de `identidad/autenticacion-y-sesion` marcados **(D9)**."""

    def test_usuario_activo_con_rol_activo_pasa(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, f"org-sesion-ok-{uuid4().hex[:8]}")
        usuario_id, _ = _crear_usuario_con_rol(db_session, organizacion.id)

        # No debe lanzar nada.
        identidad_service.exigir_sesion_habilitada(organizacion.id, usuario_id, db_session)

    def test_usuario_inactivo_se_rechaza_con_401_generico(self, db_session: Session) -> None:
        """ADR-028 D9.1/D9.2-A."""
        organizacion = _crear_organizacion(db_session, f"org-sesion-inactivo-{uuid4().hex[:8]}")
        usuario_id, _ = _crear_usuario_con_rol(
            db_session, organizacion.id, estado_usuario="INACTIVO"
        )

        with pytest.raises(AccessTokenInvalidoError):
            identidad_service.exigir_sesion_habilitada(organizacion.id, usuario_id, db_session)

    def test_rol_inactivo_se_rechaza_con_el_mismo_error(self, db_session: Session) -> None:
        """ADR-028 D9.4-A: un rol con `activo = false` se trata igual que un
        usuario inactivo, sin un código distinto."""
        organizacion = _crear_organizacion(db_session, f"org-sesion-rol-{uuid4().hex[:8]}")
        usuario_id, _ = _crear_usuario_con_rol(db_session, organizacion.id, rol_activo=False)

        with pytest.raises(AccessTokenInvalidoError):
            identidad_service.exigir_sesion_habilitada(organizacion.id, usuario_id, db_session)

    def test_usuario_inexistente_se_rechaza_con_el_mismo_error(self, db_session: Session) -> None:
        """Coherente con D1 (usuario del token inexistente -> mismo 401)."""
        organizacion = _crear_organizacion(db_session, f"org-sesion-inexistente-{uuid4().hex[:8]}")

        with pytest.raises(AccessTokenInvalidoError):
            identidad_service.exigir_sesion_habilitada(organizacion.id, uuid4(), db_session)

    def test_usuario_de_otra_organizacion_se_rechaza_con_el_mismo_error(
        self, db_session: Session
    ) -> None:
        """INV-21: el usuario existe, pero no en la organización consultada."""
        organizacion_a = _crear_organizacion(db_session, f"org-sesion-a-{uuid4().hex[:8]}")
        organizacion_b = _crear_organizacion(db_session, f"org-sesion-b-{uuid4().hex[:8]}")
        usuario_id, _ = _crear_usuario_con_rol(db_session, organizacion_a.id)

        with pytest.raises(AccessTokenInvalidoError):
            identidad_service.exigir_sesion_habilitada(organizacion_b.id, usuario_id, db_session)

    def test_usuario_inactivo_de_una_organizacion_no_afecta_a_otra(
        self, db_session: Session
    ) -> None:
        """Triangulación (tarea 2.9, INV-21): la inactividad de un usuario
        de la organización A no tiene ningún efecto sobre un usuario
        distinto de la organización B."""
        organizacion_a = _crear_organizacion(db_session, f"org-sesion-inv21-a-{uuid4().hex[:8]}")
        organizacion_b = _crear_organizacion(db_session, f"org-sesion-inv21-b-{uuid4().hex[:8]}")
        _crear_usuario_con_rol(db_session, organizacion_a.id, estado_usuario="INACTIVO")
        usuario_b_id, _ = _crear_usuario_con_rol(db_session, organizacion_b.id)

        # No debe lanzar nada: el usuario de B sigue activo.
        identidad_service.exigir_sesion_habilitada(organizacion_b.id, usuario_b_id, db_session)


class TestListarPermisosDelUsuarioFallaCerrada:
    """`listar_permisos_del_usuario` devuelve vacío para un usuario o rol
    inactivo (ADR-028, defensa en profundidad, D9.1 último punto): ningún
    consumidor futuro puede leer permisos de una sesión deshabilitada aunque
    se olvide de llamar a `exigir_sesion_habilitada`."""

    def test_usuario_inactivo_no_tiene_permisos(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, f"org-permisos-inactivo-{uuid4().hex[:8]}")
        usuario_id, rol_id = _crear_usuario_con_rol(
            db_session, organizacion.id, estado_usuario="INACTIVO"
        )
        repository.asignar_permiso_a_rol(
            organizacion.id, db_session, rol_id=rol_id, permiso_codigo="GESTIONAR_CATALOGO"
        )

        assert (
            identidad_service.listar_permisos_del_usuario(organizacion.id, usuario_id, db_session)
            == frozenset()
        )

    def test_rol_inactivo_no_tiene_permisos(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, f"org-permisos-rol-{uuid4().hex[:8]}")
        usuario_id, rol_id = _crear_usuario_con_rol(db_session, organizacion.id, rol_activo=False)
        repository.asignar_permiso_a_rol(
            organizacion.id, db_session, rol_id=rol_id, permiso_codigo="GESTIONAR_CATALOGO"
        )

        assert (
            identidad_service.listar_permisos_del_usuario(organizacion.id, usuario_id, db_session)
            == frozenset()
        )

    def test_usuario_activo_con_rol_activo_conserva_sus_permisos(self, db_session: Session) -> None:
        """Triangulación: la falla cerrada no rompe el camino feliz."""
        organizacion = _crear_organizacion(db_session, f"org-permisos-ok-{uuid4().hex[:8]}")
        usuario_id, rol_id = _crear_usuario_con_rol(db_session, organizacion.id)
        repository.asignar_permiso_a_rol(
            organizacion.id, db_session, rol_id=rol_id, permiso_codigo="GESTIONAR_CATALOGO"
        )

        assert identidad_service.listar_permisos_del_usuario(
            organizacion.id, usuario_id, db_session
        ) == frozenset({"GESTIONAR_CATALOGO"})
