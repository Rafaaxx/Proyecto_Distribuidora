"""Ratchet de la tarea 22.2 (change 18b, `design.md` D23, ADR-056; cita SEG-06, `02` §6.3 paso 4):
el catálogo y las rutas dicen lo mismo.

1. Todo tipo declarado tiene `permisos`, o está en `EXCEPCIONES_SIN_PERMISO` con su justificación
   (la lista está vacía: ningún tipo se exime).
2. Para cada ruta de escritura, los permisos de su dependencia (`requiere_comando_online...`) son
   exactamente los `permisos` del catálogo del tipo que envía. Sin esto, el bus (que exige el
   catálogo en todo camino) y la ruta (que exige su dependencia) podrían decir cosas distintas y
   el lote sería más laxo o más estricto que REST.

El tipo que envía cada ruta se lee del código de su endpoint: las constantes de texto que son un
tipo del catálogo, directas o a través de una constante del módulo. Un tipo sin ruta tiene que
estar en `TIPOS_SIN_RUTA`.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from fastapi.routing import APIRoute

# fmt: off
# ruff: noqa: I001
from app.main import crear_app
from app.commands import catalogo
from app.core.config import Settings
from tests.integration.test_ratchet_permiso_por_ruta import (
    _rutas_con_prefijo,
    permisos_declarados_de,
)
# fmt: on

EXCEPCIONES_SIN_PERMISO: frozenset[str] = frozenset()
"""Tipos que declaran `sin_permiso` con su justificación. Vacía (ADR-056)."""

TIPOS_SIN_RUTA: frozenset[str] = frozenset()
"""Tipos que no tienen una ruta REST de escritura (solo el lote). Vacía hoy."""


def _tipos_que_envia(route: APIRoute, tipos: frozenset[str]) -> set[str]:
    """Las constantes de texto del endpoint que son un tipo del catálogo."""
    endpoint = route.endpoint
    modulo = inspect.getmodule(endpoint)
    arbol = ast.parse(textwrap.dedent(inspect.getsource(endpoint)))
    encontrados: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and nodo.value in tipos:
            encontrados.add(nodo.value)
        elif isinstance(nodo, ast.Name) and modulo is not None:
            valor = getattr(modulo, nodo.id, None)
            if isinstance(valor, str) and valor in tipos:
                encontrados.add(valor)
    return encontrados


def test_todo_tipo_declarado_tiene_permisos_o_una_excepcion_justificada() -> None:
    sin_permiso = sorted(
        t.tipo
        for t in catalogo._CATALOGO.values()
        if not t.permisos and t.tipo not in EXCEPCIONES_SIN_PERMISO
    )
    assert not sin_permiso, f"Tipos sin `permisos` ni excepción justificada: {sin_permiso}"
    # Y la lista de excepciones no puede quedar desactualizada.
    assert {t for t in EXCEPCIONES_SIN_PERMISO} <= {
        t.tipo for t in catalogo._CATALOGO.values() if t.sin_permiso
    }


def test_el_permiso_de_la_ruta_de_cada_tipo_coincide_con_el_del_catalogo(
    database_url: str,
) -> None:
    app = crear_app(
        Settings(
            _env_file=None, database_url=database_url, jwt_secret="secreto-de-prueba", jwt_kid="1"
        )
    )
    tipos = frozenset(catalogo._CATALOGO)
    tipos_con_ruta: set[str] = set()
    distintos: list[tuple[str, str, str, list[str], list[str]]] = []
    for path, route in _rutas_con_prefijo(app.routes):
        if not (route.methods or set()) & {"POST", "PUT", "PATCH", "DELETE"}:
            continue
        enviados = _tipos_que_envia(route, tipos)
        for tipo in enviados:
            tipos_con_ruta.add(tipo)
            esperado = frozenset(catalogo._CATALOGO[tipo].permisos)
            real = permisos_declarados_de(route)
            if real != esperado:
                metodo = sorted(route.methods or set())[0]
                distintos.append((tipo, metodo, path, sorted(real), sorted(esperado)))
    assert not distintos, (
        f"Permiso de la ruta distinto del catálogo (tipo, método, ruta, ruta, catálogo): "
        f"{distintos}"
    )
    sin_ruta = sorted(tipos - tipos_con_ruta - TIPOS_SIN_RUTA)
    assert not sin_ruta, f"Tipos sin ruta REST que los envíe (ni en TIPOS_SIN_RUTA): {sin_ruta}"
