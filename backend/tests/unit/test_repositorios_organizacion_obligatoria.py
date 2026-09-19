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


def _verificar_organizacion_id_primer_parametro(modulo: Any) -> None:
    funciones = _funciones_publicas_del_modulo(modulo)
    assert funciones, f"{modulo.__name__} no expone ninguna función pública para verificar."

    infractoras = []
    for nombre, funcion in funciones:
        parametros = list(inspect.signature(funcion).parameters)
        if not parametros or parametros[0] != "organizacion_id":
            infractoras.append(nombre)

    assert infractoras == [], (
        f"Métodos de {modulo.__name__} sin `organizacion_id` como primer parámetro: {infractoras}"
    )


def test_identidad_repository_exige_organizacion_id_primero_en_todo_metodo() -> None:
    _verificar_organizacion_id_primer_parametro(identidad_repository)


def test_configuracion_repository_exige_organizacion_id_primero_en_todo_metodo() -> None:
    _verificar_organizacion_id_primer_parametro(configuracion_repository)


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
