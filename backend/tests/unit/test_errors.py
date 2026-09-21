"""`DomainError.status_http` (tarea 10.2): cada error de dominio declara el
código HTTP con el que se traduce a Problem Details (RFC 9457, `02` §11).
Por defecto 400; los que ya existen en el código y necesitan otro lo
sobreescriben explícitamente (401 para credenciales/token, 403 para
permiso faltante).
"""

from __future__ import annotations

from app.core.errors import DomainError


def test_el_default_es_400() -> None:
    class ErrorDeEjemplo(DomainError):
        codigo = "EJEMPLO"

    error = ErrorDeEjemplo("mensaje")
    assert error.status_http == 400


def test_una_subclase_puede_sobreescribir_el_status_http() -> None:
    class ErrorDeEjemplo401(DomainError):
        codigo = "EJEMPLO_401"
        status_http = 401

    assert ErrorDeEjemplo401("mensaje").status_http == 401
