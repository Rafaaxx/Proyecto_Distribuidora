"""Change 21, tarea 1.4 (`design.md` D8; spec `sync/bootstrap`, requisito "trae los autorizadores
con la derivación de su PIN"): `identidad/service.py` entrega los autorizadores con la derivación
PBKDF2 de su PIN para que el dispositivo los verifique sin conexión.

Reglas citadas: `02` §12.4, ADR-011, SEG-05, INV-21.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from roles_utiles import AUTORIZACION, Entorno

from app.core.seguridad import derivar_pin_autorizacion, verificar_pin_autorizacion
from app.modules.identidad import service as identidad_service
from app.modules.identidad.models import Usuario

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session):  # type: ignore[no-untyped-def]
    return Entorno(db_session)


def _usuario_con_pin(
    entorno: Entorno,
    permisos: frozenset[str],
    pin: str = "482915",
    *,
    estado: str = "ACTIVO",
    rol_activo: bool = True,
) -> UUID:
    """Un usuario con una derivación REAL de `pin` (no un texto de relleno)."""
    rol = entorno.crear_rol(f"Rol {len(permisos)}-{pin}", permisos, activo=rol_activo)
    usuario_id, _ = entorno.crear_usuario(rol, estado=estado)
    hash_hex, sal_hex, iteraciones = derivar_pin_autorizacion(pin, iteraciones=1_000)
    usuario = entorno.sesion.get_one(Usuario, usuario_id)
    usuario.pin_autorizacion_hash = hash_hex
    usuario.pin_autorizacion_sal = sal_hex
    usuario.pin_autorizacion_iteraciones = iteraciones
    entorno.sesion.commit()
    return usuario_id


def _quien_pide(entorno: Entorno) -> UUID:
    rol = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    usuario_id, _ = entorno.crear_usuario(rol)
    return usuario_id


def _listar(entorno: Entorno, pide: UUID, *, org: UUID | None = None):  # type: ignore[no-untyped-def]
    return identidad_service.listar_autorizadores_con_derivacion(
        org or entorno.org, entorno.sesion, excluir_usuario_id=pide
    )


def test_sec05_trae_hash_sal_e_iteraciones_que_verifican_el_pin(entorno: Entorno) -> None:
    """Escenario "La derivación es verificable en el dispositivo" del lado del servidor: lo que baja
    verifica el PIN con `verificar_pin_autorizacion` (el mismo criterio de `02` §12.4)."""
    pide = _quien_pide(entorno)
    sup = _usuario_con_pin(entorno, frozenset({"AUTORIZAR_DESCUENTO"}), "482915")

    (autorizador,) = _listar(entorno, pide)

    assert autorizador.usuario_id == sup
    assert autorizador.iteraciones == 1_000
    assert verificar_pin_autorizacion(
        "482915",
        hash_almacenado=autorizador.pin_hash,
        sal=autorizador.pin_sal,
        iteraciones=autorizador.iteraciones,
    )
    assert not verificar_pin_autorizacion(
        "000000",
        hash_almacenado=autorizador.pin_hash,
        sal=autorizador.pin_sal,
        iteraciones=autorizador.iteraciones,
    )


def test_trae_los_permisos_de_autorizacion_que_tiene_cada_uno(entorno: Entorno) -> None:
    pide = _quien_pide(entorno)
    _usuario_con_pin(entorno, frozenset({"AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO", "VENDER"}))
    _usuario_con_pin(entorno, AUTORIZACION, "135790")

    solo_dos, todos = sorted(_listar(entorno, pide), key=lambda a: len(a.permisos))

    assert solo_dos.permisos == frozenset({"AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO"})
    assert todos.permisos == AUTORIZACION


def test_sin_pin_no_figura(entorno: Entorno) -> None:
    """Escenario "Supervisor con PIN": `admin` sin PIN definido no figura."""
    pide = _quien_pide(entorno)
    rol = entorno.crear_rol("Sin PIN", frozenset({"AUTORIZAR_DESCUENTO"}))
    entorno.crear_usuario(rol, con_pin=False)

    assert _listar(entorno, pide) == []


def test_usuario_inactivo_o_rol_inactivo_no_figura(entorno: Entorno) -> None:
    pide = _quien_pide(entorno)
    _usuario_con_pin(entorno, frozenset({"AUTORIZAR_DESCUENTO"}), estado="INACTIVO")
    _usuario_con_pin(entorno, frozenset({"SUPERAR_CREDITO"}), "246802", rol_activo=False)

    assert _listar(entorno, pide) == []


def test_sin_permiso_de_autorizacion_no_figura(entorno: Entorno) -> None:
    pide = _quien_pide(entorno)
    _usuario_con_pin(entorno, frozenset({"VENDER", "VER_REPORTES"}))

    assert _listar(entorno, pide) == []


def test_no_incluye_a_quien_pide(entorno: Entorno) -> None:
    sup = _usuario_con_pin(entorno, frozenset({"AUTORIZAR_DESCUENTO"}))
    otro = _usuario_con_pin(entorno, frozenset({"SUPERAR_CREDITO"}), "246802")

    assert [a.usuario_id for a in _listar(entorno, sup)] == [otro]


def test_nunca_devuelve_contrasenas(entorno: Entorno) -> None:
    pide = _quien_pide(entorno)
    _usuario_con_pin(entorno, frozenset({"AUTORIZAR_DESCUENTO"}))

    (autorizador,) = _listar(entorno, pide)

    campos = set(vars(autorizador)) | set(autorizador.__dataclass_fields__)
    assert not {c for c in campos if "password" in c or "contrasena" in c}
    assert not hasattr(autorizador, "password_hash")


def test_inv21_no_trae_autorizadores_de_otra_organizacion(entorno: Entorno, db_session) -> None:  # type: ignore[no-untyped-def]
    pide = _quien_pide(entorno)
    propio = _usuario_con_pin(entorno, frozenset({"AUTORIZAR_DESCUENTO"}))
    ajeno = Entorno(db_session)
    _usuario_con_pin(ajeno, frozenset({"AUTORIZAR_DESCUENTO"}))

    assert [a.usuario_id for a in _listar(entorno, pide)] == [propio]
