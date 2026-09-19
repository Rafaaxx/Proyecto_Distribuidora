"""Cargador de casos de cálculo compartidos entre pytest y Vitest.

Lee `shared/fixtures/calculo/*.json`, valida el formato de caso de
`docs/02-arquitectura.md` §10.4 (`id`, `reglas`, `entrada`, `salida_esperada`)
y falla nombrando el archivo y el campo faltante si un caso está incompleto
(spec `calculo-compartido`, escenario "Un caso con formato inválido se
rechaza").

La ruta al directorio de casos se resuelve desde este archivo hacia la raíz
del repo, nunca desde el directorio de trabajo, para que `pytest` funcione
invocado desde cualquier lugar (`design.md` D1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# backend/tests/fixtures_compartidos/cargador.py -> sube 3 niveles hasta la
# raíz del repo (fixtures_compartidos -> tests -> backend -> raíz).
_REPO_ROOT = Path(__file__).resolve().parents[3]
DIRECTORIO_CASOS = _REPO_ROOT / "shared" / "fixtures" / "calculo"

CAMPOS_REQUERIDOS: tuple[str, ...] = ("id", "reglas", "entrada", "salida_esperada")


class CasoInvalidoError(Exception):
    """Un archivo de `shared/fixtures/calculo/` no respeta el formato de caso."""


class SinCasosError(Exception):
    """El directorio de casos no existe o no contiene ningún caso descubrible."""


@dataclass(frozen=True)
class CasoCalculo:
    """Un caso de cálculo compartido, ya validado."""

    id: str
    reglas: list[str]
    entrada: dict[str, Any]
    salida_esperada: dict[str, Any]
    archivo: Path


def _validar_caso(bruto: dict[str, Any], archivo: Path) -> CasoCalculo:
    if not isinstance(bruto, dict):
        raise CasoInvalidoError(f"{archivo}: cada caso debe ser un objeto JSON")

    for campo in CAMPOS_REQUERIDOS:
        if campo not in bruto:
            raise CasoInvalidoError(
                f"{archivo}: falta el campo requerido '{campo}' en un caso de cálculo"
            )

    return CasoCalculo(
        id=bruto["id"],
        reglas=bruto["reglas"],
        entrada=bruto["entrada"],
        salida_esperada=bruto["salida_esperada"],
        archivo=archivo,
    )


def descubrir_casos(directorio: Path | None = None) -> list[CasoCalculo]:
    """Descubre y valida todos los casos de `directorio` (o del canónico).

    Un archivo puede contener un único objeto de caso o una lista de casos.
    Levanta `SinCasosError` si el directorio no existe o no aporta ningún
    caso, y `CasoInvalidoError` si algún caso no tiene los campos requeridos.
    """
    directorio_efectivo = directorio if directorio is not None else DIRECTORIO_CASOS

    if not directorio_efectivo.is_dir():
        raise SinCasosError(
            f"No existe el directorio de casos de cálculo compartidos: {directorio_efectivo}"
        )

    casos: list[CasoCalculo] = []
    for archivo in sorted(directorio_efectivo.glob("*.json")):
        contenido = json.loads(archivo.read_text(encoding="utf-8"))
        elementos = contenido if isinstance(contenido, list) else [contenido]
        for elemento in elementos:
            casos.append(_validar_caso(elemento, archivo))

    if not casos:
        raise SinCasosError(
            f"No se descubrió ningún caso de cálculo compartido en {directorio_efectivo}"
        )

    return casos
