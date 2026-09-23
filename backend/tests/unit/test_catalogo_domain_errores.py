"""Change 05, tarea 4.1: los errores de dominio de `catalogo` heredan de
`DomainError`, tienen `codigo` estable y el `status_http` que `design.md`
D6 fija (409 duplicados/congelados, 422 validaciones, 404 no encontrado)."""

from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.modules.catalogo.domain import errores

_ERRORES_409 = (
    errores.NombreDuplicadoError,
    errores.CodigoDuplicadoError,
    errores.UnidadesCongeladasError,
    errores.CategoriaConProductosActivosError,
)
_ERRORES_422 = (
    errores.NombreInvalidoError,
    errores.CodigoInvalidoError,
    errores.ProductoSinPresentacionesError,
    errores.ReferenciaInvalidaError,
    errores.UnidadesInvalidasError,
    errores.CategoriaInactivaError,
    errores.MarcaInactivaError,
    errores.AlicuotaInactivaError,
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


def test_todos_los_codigos_de_design_d6_son_distintos() -> None:
    todos = _ERRORES_409 + _ERRORES_422 + (errores.RecursoNoEncontradoError,)
    codigos = [clase.codigo for clase in todos]
    assert len(codigos) == len(set(codigos)), f"Códigos repetidos: {codigos}"
