"""Change 15, tarea 11.1: ratchet de las rutas de jornadas. Ninguna ruta edita ni borra una
jornada: las únicas escrituras sobre `/stock/jornadas` son los cuatro comandos (abrir, rendir,
cerrar y liberar), y las cuatro van por el bus (el ratchet general de escritura por el bus está
en `tests/integration/test_bus_cobertura_rutas_de_escritura.py`).

Reglas citadas: INV-05, TR-06 (una jornada no se borra ni se reescribe), INV-21, `02` §6.5.

Va en `tests/integration` porque reutiliza el aplanado de routers del ratchet de permisos.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import Settings
from app.main import crear_app
from tests.integration.test_ratchet_permiso_por_ruta import _rutas_con_prefijo

PREFIJO = "/api/v1/stock/jornadas"

ESCRITURAS_ESPERADAS = {
    ("POST", PREFIJO),  # JORNADA_ABRIR
    ("POST", PREFIJO + "/{jornada_id}/rendicion"),  # JORNADA_RENDIR
    ("POST", PREFIJO + "/{jornada_id}/cierre"),  # JORNADA_CERRAR
    ("POST", PREFIJO + "/{jornada_id}/liberacion"),  # JORNADA_LIBERAR
}


def _app_real(database_url: str) -> FastAPI:
    return crear_app(
        Settings(
            _env_file=None,
            database_url=database_url,
            jwt_secret="secreto-de-prueba-ratchet-jornadas",
            jwt_kid="1",
        )
    )


def _rutas_de_jornadas(database_url: str) -> set[tuple[str, str]]:
    return {
        (metodo, ruta)
        for ruta, route in _rutas_con_prefijo(_app_real(database_url).routes)
        if ruta.startswith(PREFIJO)
        for metodo in route.methods or set()
    }


def test_las_unicas_escrituras_sobre_jornadas_son_los_cuatro_comandos(database_url: str) -> None:
    escrituras = {
        (metodo, ruta) for metodo, ruta in _rutas_de_jornadas(database_url) if metodo != "GET"
    }

    assert escrituras == ESCRITURAS_ESPERADAS


def test_ninguna_ruta_edita_ni_borra_una_jornada(database_url: str) -> None:
    metodos = {metodo for metodo, _ruta in _rutas_de_jornadas(database_url)}

    assert not metodos & {"PUT", "PATCH", "DELETE"}


def test_el_ratchet_ve_las_rutas_de_jornadas(database_url) -> None:
    """Triangulación: si el prefijo cambiara, las dos pruebas anteriores pasarían en vacío."""
    assert ("POST", PREFIJO) in _rutas_de_jornadas(database_url)
