"""Tareas 4.1 y 4.3 (change 10): piezas puras del importador de proveedores, la
detección de filas duplicadas dentro del archivo y el cursor del historial.

Funciones puras: la fila de planilla se traduce a los datos de `crear_proveedor`
sin conversiones de más, y las claves naturales de `design.md` D6 detectan una
repetición dentro del mismo archivo (`FILA_DUPLICADA`, citando la primera).

Reglas citadas: CAT-01 (nombre normalizado y único), `design.md` D4 (comparación sin
mayúsculas ni espacios al borde), D6 (altas, `FILA_DUPLICADA`), `02` §11 (cursor).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.importacion.domain.duplicados import marcar_duplicadas
from app.modules.importacion.domain.errores import CursorInvalidoError
from app.modules.importacion.domain.historial import (
    LIMITE_DEFAULT,
    LIMITE_MAXIMO,
    codificar_cursor,
    decodificar_cursor,
)
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.proveedores import (
    claves_de_proveedor,
    datos_de_proveedor,
)


def _proveedor(fila: int, nombre: str, cuit: str = "", **otros: str) -> FilaPlanilla:
    valores = {"nombre": nombre, "cuit": cuit, "contacto": "", "telefono": "", "email": ""}
    valores.update(otros)
    return FilaPlanilla(fila=fila, valores=valores)


# --- datos del proveedor -------------------------------------------------------


def test_los_datos_del_proveedor_salen_de_la_fila_con_vacios_como_none() -> None:
    fila = _proveedor(2, "Bodega Sur", "30-71234567-8", contacto="Ana", email="a@x.com")

    assert datos_de_proveedor(fila) == {
        "nombre": "Bodega Sur",
        "cuit": "30-71234567-8",  # lo normaliza el servicio, igual que en el alta individual
        "contacto": "Ana",
        "telefono": None,
        "email": "a@x.com",
    }


def test_un_proveedor_solo_con_nombre_deja_el_resto_en_none() -> None:
    assert datos_de_proveedor(_proveedor(2, "Cervecería Norte")) == {
        "nombre": "Cervecería Norte",
        "cuit": None,
        "contacto": None,
        "telefono": None,
        "email": None,
    }


# --- claves naturales ---------------------------------------------------------


def test_las_claves_son_el_nombre_sin_mayusculas_y_el_cuit_en_digitos() -> None:
    assert claves_de_proveedor(_proveedor(2, " Bodega  Sur ", "30-71234567-8")) == [
        ("nombre", "bodega  sur"),
        ("cuit", "30712345678"),
    ]


def test_sin_cuit_no_hay_clave_de_cuit() -> None:
    assert claves_de_proveedor(_proveedor(2, "Bodega Sur")) == [("nombre", "bodega sur")]


def test_un_cuit_que_no_tiene_once_digitos_no_es_clave() -> None:
    """Un CUIT inválido se informa como `CUIT_INVALIDO` en cada fila; no se lo trata
    como duplicado de otro."""
    assert claves_de_proveedor(_proveedor(2, "A", "20-1234")) == [("nombre", "a")]
    assert claves_de_proveedor(_proveedor(2, "A", "ABC")) == [("nombre", "a")]


# --- filas duplicadas (D6) ------------------------------------------------------


def test_la_segunda_aparicion_del_nombre_es_fila_duplicada_y_cita_la_primera() -> None:
    """Escenario "Clave repetida dentro del archivo": "Bodega Sur" en las filas 2 y 5."""
    filas = [_proveedor(2, "Bodega Sur"), _proveedor(3, "Norte"), _proveedor(5, "bodega sur ")]

    duplicadas = marcar_duplicadas(filas, claves_de_proveedor)

    assert set(duplicadas) == {5}
    assert duplicadas[5].codigo == "FILA_DUPLICADA"
    assert duplicadas[5].columna == "nombre"
    assert "2" in duplicadas[5].mensaje


def test_el_cuit_repetido_con_otro_formato_tambien_es_fila_duplicada() -> None:
    filas = [_proveedor(2, "A", "30712345678"), _proveedor(3, "B", "30-71234567-8")]

    duplicadas = marcar_duplicadas(filas, claves_de_proveedor)

    assert set(duplicadas) == {3}
    assert duplicadas[3].columna == "cuit"
    assert "2" in duplicadas[3].mensaje


def test_sin_repeticiones_no_hay_duplicadas() -> None:
    filas = [_proveedor(2, "A", "30712345678"), _proveedor(3, "B", "30712345679")]

    assert marcar_duplicadas(filas, claves_de_proveedor) == {}


def test_una_clave_vacia_no_cuenta_como_repeticion() -> None:
    filas = [_proveedor(2, "A"), _proveedor(3, "B")]  # los dos sin CUIT

    assert marcar_duplicadas(filas, claves_de_proveedor) == {}


def test_la_tercera_aparicion_cita_siempre_la_primera() -> None:
    filas = [_proveedor(2, "A"), _proveedor(3, "a"), _proveedor(4, "A")]

    duplicadas = marcar_duplicadas(filas, claves_de_proveedor)

    assert set(duplicadas) == {3, 4}
    assert "2" in duplicadas[4].mensaje


def test_una_fila_duplicada_no_registra_sus_otras_claves() -> None:
    """La fila 3 repite el nombre de la 2; su CUIT no pasa a ser "de la fila 3", así
    que la fila 4, con ese CUIT y otro nombre, NO es duplicada de la 3."""
    filas = [
        _proveedor(2, "A", "30712345678"),
        _proveedor(3, "a", "20123456786"),
        _proveedor(4, "C", "20123456786"),
    ]

    duplicadas = marcar_duplicadas(filas, claves_de_proveedor)

    assert set(duplicadas) == {3}


def test_se_informa_una_sola_vez_por_fila_aunque_repita_dos_claves() -> None:
    filas = [_proveedor(2, "A", "30712345678"), _proveedor(3, "a", "30712345678")]

    duplicadas = marcar_duplicadas(filas, claves_de_proveedor)

    assert set(duplicadas) == {3}
    assert duplicadas[3].columna == "nombre"


# --- cursor del historial ------------------------------------------------------


def test_el_cursor_vuelve_igual() -> None:
    momento = datetime(2026, 10, 1, 15, 30, 12, 123456, tzinfo=UTC)
    id_ = uuid4()

    assert decodificar_cursor(codificar_cursor(momento, id_)) == (momento, id_)


@pytest.mark.parametrize(
    "cursor",
    ["", "no-es-base64!!", "YWJj", "MjAyNi0xMC0wMVQxMjowMDowMHxub2VzdXVpZA=="],
)
def test_un_cursor_ilegible_es_cursor_invalido(cursor: str) -> None:
    with pytest.raises(CursorInvalidoError) as error:
        decodificar_cursor(cursor)

    assert error.value.codigo == "CURSOR_INVALIDO"


def test_un_cursor_sin_zona_horaria_es_invalido() -> None:
    import base64

    ingenuo = base64.urlsafe_b64encode(f"2026-10-01T12:00:00|{uuid4()}".encode()).decode()

    with pytest.raises(CursorInvalidoError):
        decodificar_cursor(ingenuo)


def test_los_limites_del_historial_son_50_y_200() -> None:
    assert (LIMITE_DEFAULT, LIMITE_MAXIMO) == (50, 200)
