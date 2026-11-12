"""Tarea 2.2 (change 26, spec `reportes/area-de-reportes`, «Los reportes se leen con
`VER_REPORTES`…»; `design.md` D6 y D8): cada ruta de `/api/v1/reportes` declara `VER_REPORTES`; la
de saldos de proveedores declara, además, la regla compuesta (D8 = B).

El ratchet central (`test_ratchet_permiso_por_ruta.py`) une los códigos y no distingue «y» de «o»:
acá se comprueba que toda ruta del área exija `VER_REPORTES` y, para la de proveedores, los
cuatro códigos esperados. La regla de «y»/«o» la prueban las pruebas de saldos (tarea 7.1).

Reglas citadas: REP-01, SEG-06, INV-21.
"""

from __future__ import annotations

from fastapi.routing import APIRoute
from test_ratchet_permiso_por_ruta import _rutas_con_prefijo, permisos_declarados_de

from app.core.config import Settings
from app.main import crear_app

PREFIJO = "/api/v1/reportes"
# Las rutas del área, completas desde el Lote 3 (tareas 7.1 y 8.1).
RUTAS_DEL_AREA = frozenset(
    {
        ("GET", "/api/v1/reportes/ventas"),
        ("GET", "/api/v1/reportes/rendiciones"),
        ("GET", "/api/v1/reportes/rendiciones/{jornada_id}"),
        ("GET", "/api/v1/reportes/observaciones"),
        ("GET", "/api/v1/reportes/ajustes"),
        ("GET", "/api/v1/reportes/saldos/clientes"),
        ("GET", "/api/v1/reportes/saldos/proveedores"),
    }
)
PERMISOS_DE_SALDOS_DE_PROVEEDORES = frozenset(
    {"VER_REPORTES", "GESTIONAR_PROVEEDORES", "REGISTRAR_PAGO_PROVEEDOR", "VER_UTILIDAD"}
)


def _rutas_de_reportes(database_url: str) -> dict[tuple[str, str], APIRoute]:
    app = crear_app(
        Settings(
            _env_file=None, database_url=database_url, jwt_secret="secreto-de-prueba", jwt_kid="1"
        )
    )
    return {
        (metodo, path): route
        for path, route in _rutas_con_prefijo(app.routes)
        if path.startswith(PREFIJO)
        for metodo in (route.methods or set())
    }


def test_el_area_de_reportes_registra_sus_rutas(database_url: str) -> None:
    rutas = _rutas_de_reportes(database_url)

    assert ("GET", "/api/v1/reportes/ventas") in rutas
    assert set(rutas) <= RUTAS_DEL_AREA, f"rutas no previstas: {set(rutas) - RUTAS_DEL_AREA}"


def test_toda_ruta_de_reportes_exige_ver_reportes(database_url: str) -> None:
    rutas = _rutas_de_reportes(database_url)

    assert rutas, "el área de reportes no registra ninguna ruta"
    sin_permiso = sorted(
        clave
        for clave, route in rutas.items()
        if "VER_REPORTES" not in permisos_declarados_de(route)
    )
    assert sin_permiso == []


def test_toda_ruta_de_reportes_es_de_lectura(database_url: str) -> None:
    """REP-01: los reportes no escriben nada; todas son `GET`."""
    rutas = _rutas_de_reportes(database_url)

    assert {metodo for metodo, _ in rutas} == {"GET"}


def test_las_rutas_comunes_no_piden_permisos_de_mas(database_url: str) -> None:
    """Solo la de saldos de proveedores suma la regla compuesta (D8 = B)."""
    rutas = _rutas_de_reportes(database_url)

    de_mas = {
        clave: sorted(permisos_declarados_de(route))
        for clave, route in rutas.items()
        if clave != ("GET", "/api/v1/reportes/saldos/proveedores")
        and permisos_declarados_de(route) != frozenset({"VER_REPORTES"})
    }
    assert de_mas == {}


def test_la_de_saldos_de_proveedores_declara_la_regla_compuesta(database_url: str) -> None:
    rutas = _rutas_de_reportes(database_url)
    clave = ("GET", "/api/v1/reportes/saldos/proveedores")

    assert clave in rutas
    assert permisos_declarados_de(rutas[clave]) == PERMISOS_DE_SALDOS_DE_PROVEEDORES


def test_el_area_registra_exactamente_las_rutas_previstas(database_url: str) -> None:
    """Cerrada la tarea 2.2: ni una ruta menos (se olvidó registrar) ni una más (sin revisar)."""
    assert set(_rutas_de_reportes(database_url)) == RUTAS_DEL_AREA
