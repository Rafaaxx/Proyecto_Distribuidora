"""Change 17b, tarea 6.1: regla pura que protege a la organización de quedarse sin nadie con
`ADMIN_USUARIOS` (ADR-053, TR-10, INV-01). Recibe conteos ya hechos en SQL."""

from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.modules.identidad.domain.usuarios import (
    SinAdministradorError,
    validar_queda_administrador,
)


def test_el_error_es_de_dominio_con_codigo_estable_y_409() -> None:
    assert issubclass(SinAdministradorError, DomainError)
    assert SinAdministradorError.codigo == "IDENTIDAD_SIN_ADMINISTRADOR"
    assert SinAdministradorError.status_http == 409


def test_unico_rol_con_el_permiso_que_lo_pierde_falla() -> None:
    with pytest.raises(SinAdministradorError) as error:
        validar_queda_administrador(
            administradores_en_otros_roles=0,
            conserva_el_permiso=False,
            rol_activo=True,
            usuarios_activos_del_rol=1,
        )
    assert "nadie que administre usuarios y roles" in str(error.value)


def test_otro_rol_con_un_usuario_activo_lo_conserva() -> None:
    validar_queda_administrador(
        administradores_en_otros_roles=1,
        conserva_el_permiso=False,
        rol_activo=True,
        usuarios_activos_del_rol=1,
    )


def test_otro_rol_sin_usuarios_activos_no_cuenta() -> None:
    # En SQL un rol cuyos usuarios están inactivos (o el rol mismo inactivo) aporta 0.
    with pytest.raises(SinAdministradorError):
        validar_queda_administrador(
            administradores_en_otros_roles=0,
            conserva_el_permiso=False,
            rol_activo=True,
            usuarios_activos_del_rol=3,
        )


@pytest.mark.parametrize(
    ("rol_activo", "usuarios_activos", "debe_fallar"),
    [
        (True, 2, False),  # conserva el permiso, activo y con usuarios: queda administrador
        (False, 2, True),  # rol inactivo con el permiso: no cuenta
        (True, 0, True),  # rol activo con el permiso pero sin usuarios activos: no cuenta
    ],
)
def test_si_el_rol_editado_conserva_el_permiso_solo_cuenta_activo_y_con_usuarios(
    rol_activo: bool, usuarios_activos: int, debe_fallar: bool
) -> None:
    def validar() -> None:
        validar_queda_administrador(
            administradores_en_otros_roles=0,
            conserva_el_permiso=True,
            rol_activo=rol_activo,
            usuarios_activos_del_rol=usuarios_activos,
        )

    if debe_fallar:
        with pytest.raises(SinAdministradorError):
            validar()
    else:
        validar()
