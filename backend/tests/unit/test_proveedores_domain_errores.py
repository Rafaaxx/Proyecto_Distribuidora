"""Change 06, tarea 6.1: los errores de dominio de `proveedores` heredan de
`DomainError`, tienen `codigo` estable y el `status_http` que `design.md`
fija (409 duplicados/estado en conflicto, 422 validaciones, 404 no
encontrado), mismo criterio que `catalogo` (D6 del 05)."""

from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.modules.proveedores.domain import errores

_ERRORES_409 = (
    errores.NombreDuplicadoError,
    errores.CuitDuplicadoError,
    errores.ProveedorConProductosActivosError,
)
_ERRORES_422 = (
    errores.NombreInvalidoError,
    errores.CuitInvalidoError,
    errores.ProveedorInactivoError,
    errores.ProveedorNoCorrespondeError,
    errores.ProductoInactivoError,
    errores.PresentacionInvalidaError,
    errores.ValorInvalidoError,
    errores.BonificacionInvalidaError,
    errores.CostosInvalidosError,
)


@pytest.mark.parametrize("clase_error", _ERRORES_409)
def test_errores_de_conflicto_son_409(clase_error: type[DomainError]) -> None:
    error = clase_error("mensaje")
    assert isinstance(error, DomainError)
    assert error.status_http == 409
    assert error.codigo and error.codigo != "ERROR_DE_DOMINIO"


@pytest.mark.parametrize("clase_error", _ERRORES_422)
def test_errores_de_validacion_son_422(clase_error: type[DomainError]) -> None:
    error = clase_error("mensaje")
    assert isinstance(error, DomainError)
    assert error.status_http == 422
    assert error.codigo and error.codigo != "ERROR_DE_DOMINIO"


def test_recurso_no_encontrado_es_404() -> None:
    error = errores.RecursoNoEncontradoError("no existe")
    assert error.status_http == 404
    assert error.codigo == "RECURSO_NO_ENCONTRADO"


def test_todos_los_codigos_de_design_son_distintos() -> None:
    todos = _ERRORES_409 + _ERRORES_422 + (errores.RecursoNoEncontradoError,)
    codigos = [clase.codigo for clase in todos]
    assert len(codigos) == len(set(codigos)), f"Códigos repetidos: {codigos}"


def test_mensaje_se_conserva_en_la_excepcion() -> None:
    error = errores.ValorInvalidoError("el valor debe ser positivo")
    assert error.mensaje == "el valor debe ser positivo"
    assert str(error) == "el valor debe ser positivo"
