"""Unitarias del cargador de casos de cálculo compartidos.

Spec `calculo-compartido`, escenarios "Un caso con formato inválido se
rechaza", "El directorio de casos no existe" y "La suite de TypeScript deja
de cargar los casos" (versión Python de la misma garantía).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cargador import CasoInvalidoError, SinCasosError, descubrir_casos


def _escribir(directorio: Path, nombre: str, contenido: object) -> Path:
    archivo = directorio / nombre
    archivo.write_text(json.dumps(contenido), encoding="utf-8")
    return archivo


def test_descubre_un_caso_valido(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        "caso.json",
        {"id": "X-1", "reglas": ["INV-03"], "entrada": {"a": 1}, "salida_esperada": {"b": 2}},
    )

    casos = descubrir_casos(tmp_path)

    assert [c.id for c in casos] == ["X-1"]
    assert casos[0].reglas == ["INV-03"]


def test_descubre_varios_casos_dentro_de_un_archivo_lista(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        "casos.json",
        [
            {"id": "A", "reglas": [], "entrada": {}, "salida_esperada": {}},
            {"id": "B", "reglas": [], "entrada": {}, "salida_esperada": {}},
        ],
    )

    casos = descubrir_casos(tmp_path)

    assert sorted(c.id for c in casos) == ["A", "B"]


@pytest.mark.parametrize("campo_faltante", ["id", "reglas", "entrada", "salida_esperada"])
def test_falla_nombrando_archivo_y_campo_si_falta_uno_requerido(
    tmp_path: Path, campo_faltante: str
) -> None:
    caso = {"id": "X-1", "reglas": ["INV-03"], "entrada": {}, "salida_esperada": {}}
    del caso[campo_faltante]
    archivo = _escribir(tmp_path, "invalido.json", caso)

    with pytest.raises(CasoInvalidoError) as excinfo:
        descubrir_casos(tmp_path)

    assert str(archivo) in str(excinfo.value)
    assert campo_faltante in str(excinfo.value)


def test_falla_con_mensaje_que_nombra_la_ruta_si_el_directorio_no_existe(
    tmp_path: Path,
) -> None:
    inexistente = tmp_path / "no-existe"

    with pytest.raises(SinCasosError) as excinfo:
        descubrir_casos(inexistente)

    assert str(inexistente) in str(excinfo.value)


def test_falla_si_el_directorio_existe_pero_no_tiene_casos(tmp_path: Path) -> None:
    with pytest.raises(SinCasosError):
        descubrir_casos(tmp_path)


def test_el_directorio_canonico_del_repo_existe_y_tiene_casos() -> None:
    """Guardia de deriva: si esto falla, ninguna suite puede descubrir casos."""
    casos = descubrir_casos()

    assert len(casos) > 0
