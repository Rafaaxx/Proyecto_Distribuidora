"""Tarea 12.2 (change 20b, spec `sistema/pipeline-de-comandos`; ADR-056, SEG-06, SYN-06; cita `02`
§6.3 paso 4 y §6.5): el catálogo declara los comandos de usuarios, roles y cartera, y el cambio
de la propia contraseña, con su modo, su permiso y su marca de credenciales efímeras, y cada uno
tiene su handler registrado en la versión 1.

Son los doce tipos nuevos del change (seis de usuarios, cuatro de roles, uno de cartera y "Mi
contraseña") más `USUARIO_CREAR`, que el change endurece (rol activo, contraseña y nombre de usuario
libre) y es el decimotercer tipo que toca. `tasks.md` 12.2 habla de "trece comandos": son estos.
"""

from __future__ import annotations

import pytest

import app.main  # noqa: F401  (importar `app.main` puebla catálogo y registro reales)
from app.commands import catalogo, registro
from app.commands.verificacion import verificar_catalogo_y_registro

_CATALOGO_REAL = dict(catalogo._CATALOGO)
_REGISTRO_REAL = dict(registro._REGISTRO)

ADMIN = ("ADMIN_USUARIOS",)

# tipo -> (permisos, exige_credenciales_efimeras)
COMANDOS_DE_USUARIOS = {
    "USUARIO_CREAR": (ADMIN, True),
    "USUARIO_MODIFICAR": (ADMIN, False),
    "USUARIO_BAJA": (ADMIN, False),
    "USUARIO_REACTIVAR": (ADMIN, False),
    "USUARIO_ROL_CAMBIAR": (ADMIN, False),
    "USUARIO_CONTRASENA_RESTABLECER": (ADMIN, True),
    "USUARIO_TOPE_DESCUENTO_DEFINIR": (ADMIN, False),
}
COMANDOS_DE_ROLES = {
    "ROL_CREAR": (ADMIN, False),
    "ROL_RENOMBRAR": (ADMIN, False),
    "ROL_BAJA": (ADMIN, False),
    "ROL_REACTIVAR": (ADMIN, False),
}
COMANDO_DE_CARTERA = {"CLIENTE_VENDEDOR_ASIGNAR": (("GESTIONAR_CLIENTES",), False)}
COMANDO_DE_CONTRASENA_PROPIA = {"CONTRASENA_PROPIA_CAMBIAR": ((), True)}

TODOS = {
    **COMANDOS_DE_USUARIOS,
    **COMANDOS_DE_ROLES,
    **COMANDO_DE_CARTERA,
    **COMANDO_DE_CONTRASENA_PROPIA,
}


def test_son_trece_los_comandos_que_toca_el_change() -> None:
    assert len(TODOS) == 13
    assert len(COMANDOS_DE_USUARIOS) + len(COMANDOS_DE_ROLES) + len(COMANDO_DE_CARTERA) == 12


@pytest.mark.parametrize("tipo", sorted(TODOS))
def test_cada_comando_esta_declarado_y_es_solo_online(tipo: str) -> None:
    declarado = _CATALOGO_REAL.get(tipo)

    assert declarado is not None, f"{tipo} no está declarado en el catálogo"
    assert declarado.admite_online is True
    assert declarado.admite_offline is False, f"{tipo} no puede admitir OFFLINE (SYN-06)"


@pytest.mark.parametrize(("tipo", "esperado"), sorted(TODOS.items()))
def test_cada_comando_declara_su_permiso_y_sus_credenciales_efimeras(
    tipo: str, esperado: tuple[tuple[str, ...], bool]
) -> None:
    permisos, efimeras = esperado
    declarado = _CATALOGO_REAL[tipo]

    assert declarado.permisos == permisos
    assert declarado.exige_credenciales_efimeras is efimeras


def test_solo_cambiar_la_propia_contrasena_se_declara_sin_permiso_y_lo_justifica() -> None:
    sin_permiso = {tipo for tipo in TODOS if _CATALOGO_REAL[tipo].sin_permiso is not None}

    assert sin_permiso == {"CONTRASENA_PROPIA_CAMBIAR"}
    justificacion = _CATALOGO_REAL["CONTRASENA_PROPIA_CAMBIAR"].sin_permiso
    assert justificacion is not None and len(justificacion) > 20


def test_los_comandos_con_una_contrasena_son_exactamente_los_marcados_como_efimeros() -> None:
    efimeros = {tipo for tipo in TODOS if _CATALOGO_REAL[tipo].exige_credenciales_efimeras}

    assert efimeros == {
        "USUARIO_CREAR",
        "USUARIO_CONTRASENA_RESTABLECER",
        "CONTRASENA_PROPIA_CAMBIAR",
    }


@pytest.mark.parametrize("tipo", sorted(TODOS))
def test_cada_comando_tiene_su_handler_en_la_version_1(tipo: str) -> None:
    assert (tipo, 1) in _REGISTRO_REAL, f"{tipo} v1 no tiene handler registrado"


def test_el_catalogo_y_el_registro_reales_coinciden_exactamente() -> None:
    verificar_catalogo_y_registro()
