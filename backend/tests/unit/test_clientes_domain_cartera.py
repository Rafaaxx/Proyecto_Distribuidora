"""Change 20b, tarea 9.1 (`design.md` D13, D14, D15; spec `clientes/cartera-de-clientes`): reglas
puras de la cartera. Reglas citadas: CLI-03, INV-01, ADR-052, `01` §19."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.errors import DomainError
from app.modules.clientes.domain.cartera import (
    ALCANCE_CARTERA,
    ALCANCE_TODOS,
    MAXIMO_CLIENTES_POR_ASIGNACION,
    ClienteAsignable,
    alcance_de_opciones,
    validar_asignacion,
)


def _cliente(*, consumidor_final: bool = False) -> ClienteAsignable:
    return ClienteAsignable(id=uuid4(), es_consumidor_final=consumidor_final)


def _codigo(error: pytest.ExceptionInfo[DomainError]) -> tuple[str, int]:
    return error.value.codigo, error.value.status_http


# --- validar_asignacion -------------------------------------------------------------------


def test_una_asignacion_valida_no_lanza_con_vendedor_ni_para_quitarlo() -> None:
    clientes = [_cliente(), _cliente()]

    validar_asignacion(clientes, vendedor_valido=True)
    validar_asignacion(clientes, vendedor_valido=None)  # quitar el vendedor


def test_el_consumidor_final_no_se_asigna_ni_siquiera_para_quitarle_el_vendedor() -> None:
    """CLI-03."""
    for vendedor_valido in (True, None):
        with pytest.raises(DomainError) as error:
            validar_asignacion([_cliente(), _cliente(consumidor_final=True)], vendedor_valido)
        assert _codigo(error) == ("CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR", 409)


def test_la_lista_vacia_es_422() -> None:
    with pytest.raises(DomainError) as error:
        validar_asignacion([], vendedor_valido=True)
    assert _codigo(error) == ("ASIGNACION_DE_CLIENTES_INVALIDA", 422)


def test_hasta_500_clientes_se_aceptan_y_501_es_422() -> None:
    assert MAXIMO_CLIENTES_POR_ASIGNACION == 500
    validar_asignacion([_cliente() for _ in range(500)], vendedor_valido=True)

    with pytest.raises(DomainError) as error:
        validar_asignacion([_cliente() for _ in range(501)], vendedor_valido=True)
    assert _codigo(error) == ("ASIGNACION_DE_CLIENTES_INVALIDA", 422)


def test_un_vendedor_invalido_es_409_y_para_quitar_no_se_evalua() -> None:
    """INV-01: el vendedor se valida antes de escribir."""
    with pytest.raises(DomainError) as error:
        validar_asignacion([_cliente()], vendedor_valido=False)
    assert _codigo(error) == ("VENDEDOR_INVALIDO", 409)


# --- alcance_de_opciones ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("gestiona", "asignados", "pide_todos", "esperado"),
    [
        (False, 2, False, ALCANCE_CARTERA),  # vendedor con cartera
        (False, 2, True, ALCANCE_TODOS),  # "Buscar en todos los clientes"
        (False, 0, False, ALCANCE_TODOS),  # sin cartera: todos (ADR-052)
        (True, 2, False, ALCANCE_TODOS),  # administración ve todos
        (True, 0, True, ALCANCE_TODOS),
    ],
)
def test_el_alcance_de_las_opciones(
    gestiona: bool, asignados: int, pide_todos: bool, esperado: str
) -> None:
    assert alcance_de_opciones(gestiona, asignados, pide_todos) == esperado
