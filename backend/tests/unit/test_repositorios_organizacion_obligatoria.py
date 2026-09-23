"""Tarea 6.3: ningún método público de los repositorios de `identidad` ni
`configuracion` existe sin `organizacion_id` como primer parámetro
obligatorio (`docs/02-arquitectura.md` §8).

Escenario "Una operación de acceso a datos sin organización no llega a
existir": se inspeccionan por introspección las firmas de todos los métodos
públicos (no privados, no importados) de ambos módulos de repositorio.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pytest

from app.modules.catalogo import repository as catalogo_repository
from app.modules.configuracion import repository as configuracion_repository
from app.modules.identidad import repository as identidad_repository


def _funciones_publicas_del_modulo(modulo: Any) -> list[tuple[str, Callable[..., Any]]]:
    return [
        (nombre, objeto)
        for nombre, objeto in vars(modulo).items()
        if inspect.isfunction(objeto)
        and not nombre.startswith("_")
        and objeto.__module__ == modulo.__name__
    ]


def _verificar_organizacion_id_primer_parametro(
    modulo: Any, *, exentas: frozenset[str] = frozenset()
) -> None:
    funciones = _funciones_publicas_del_modulo(modulo)
    assert funciones, f"{modulo.__name__} no expone ninguna función pública para verificar."

    infractoras = []
    for nombre, funcion in funciones:
        if nombre in exentas:
            continue
        parametros = list(inspect.signature(funcion).parameters)
        if not parametros or parametros[0] != "organizacion_id":
            infractoras.append(nombre)

    assert infractoras == [], (
        f"Métodos de {modulo.__name__} sin `organizacion_id` como primer parámetro: {infractoras}"
    )


def test_identidad_repository_exige_organizacion_id_primero_en_todo_metodo() -> None:
    """Tarea 6.4: la excepción del catálogo global `permiso` es la lista
    explícita y enumerable `FUNCIONES_SIN_ORGANIZACION_ID` (mismo criterio
    que `TABLAS_GLOBALES_EXENTAS` de la tarea 3.1), no una regla de nombre."""
    _verificar_organizacion_id_primer_parametro(
        identidad_repository,
        exentas=identidad_repository.FUNCIONES_SIN_ORGANIZACION_ID,
    )


def test_la_excepcion_del_catalogo_global_es_explicita_y_enumerable() -> None:
    assert isinstance(identidad_repository.FUNCIONES_SIN_ORGANIZACION_ID, frozenset)
    assert {
        "obtener_permiso_por_codigo",
        "listar_permisos",
        "obtener_organizacion_por_slug",
        "obtener_sesion_refresh_por_token_hash_global",
        "registrar_intento_login",
        "contar_intentos_fallidos_por_usuario",
        "contar_intentos_fallidos_por_ip",
        "obtener_intento_fallido_mas_antiguo_en_ventana_por_usuario",
        "obtener_intento_fallido_mas_antiguo_en_ventana_por_ip",
    } == identidad_repository.FUNCIONES_SIN_ORGANIZACION_ID


def test_sin_la_exencion_las_funciones_de_permiso_si_serian_detectadas() -> None:
    """Verificación en negativo (mismo espíritu que la tarea 3.1): sin pasar
    `exentas`, las funciones del catálogo global aparecen como infractoras
    -- confirma que la exención hace lo que dice, no que la prueba esté
    vacía por otra razón."""
    with pytest.raises(AssertionError):
        _verificar_organizacion_id_primer_parametro(identidad_repository)


def test_configuracion_repository_exige_organizacion_id_primero_en_todo_metodo() -> None:
    _verificar_organizacion_id_primer_parametro(configuracion_repository)


def test_catalogo_repository_exige_organizacion_id_primero_en_todo_metodo() -> None:
    """Change 05, tarea 6.1: `catalogo` no declara ninguna excepción
    (`FUNCIONES_SIN_ORGANIZACION_ID` vacío, `design.md` D7) -- toda función
    pública recibe `organizacion_id` primero, sin catálogo global propio."""
    _verificar_organizacion_id_primer_parametro(
        catalogo_repository,
        exentas=catalogo_repository.FUNCIONES_SIN_ORGANIZACION_ID,
    )


def test_una_funcion_sin_organizacion_id_primero_es_detectada() -> None:
    """Verificación en negativo: un módulo con un método mal formado debe
    ser detectado por la misma comprobación (no una lista fija de nombres)."""

    class _ModuloFalso:
        __name__ = "modulo_falso_de_prueba"

    def metodo_malo(sesion: object, alicuota_id: object) -> None:  # sin organizacion_id primero
        return None

    metodo_malo.__module__ = "modulo_falso_de_prueba"
    modulo_falso = _ModuloFalso()
    modulo_falso.metodo_malo = metodo_malo  # type: ignore[attr-defined]

    infractoras = [
        nombre
        for nombre, funcion in _funciones_publicas_del_modulo(modulo_falso)
        if not list(inspect.signature(funcion).parameters)
        or list(inspect.signature(funcion).parameters)[0] != "organizacion_id"
    ]

    assert infractoras == ["metodo_malo"]
