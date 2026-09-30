"""Change 08, escenario "No existe ruta que edite o borre movimientos" de
`specs/cuentas-corrientes/libro-de-cuenta-corriente` (CC-06, TR-06, INV-05).

El libro es de solo inserción: la base lo impone con los permisos (INV-05), y la
API no ofrece ninguna forma de pedirlo. Se revisan todas las rutas registradas de
la aplicación real: ninguna `PUT`, `PATCH` ni `DELETE` cuelga de la cuenta
corriente (`/cuentas-corrientes/...` o `.../cuenta-corriente`) ni de un
`movimiento`. Un recurso nuevo con esos verbos sobre el libro rompe esta prueba
y obliga a leer CC-06 antes de agregarlo.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import crear_app

VERBOS_DE_EDICION = {"PUT", "PATCH", "DELETE"}
FRAGMENTOS_DEL_LIBRO = ("cuentas-corrientes", "cuenta-corriente", "movimiento")


def _rutas_del_libro(app: FastAPI) -> dict[str, set[str]]:
    """`{ruta: {verbos}}` de cada ruta que cuelga del libro. Se lee de
    `app.openapi()["paths"]`, que trae el camino completo con prefijo (el mismo
    criterio que `test_inv21_ratchet_rutas.py`)."""
    paths: dict[str, dict[str, object]] = app.openapi()["paths"]
    return {
        ruta: {verbo.upper() for verbo in operaciones}
        for ruta, operaciones in paths.items()
        if any(fragmento in ruta for fragmento in FRAGMENTOS_DEL_LIBRO)
    }


def rutas_de_edicion_sobre_el_libro(app: FastAPI) -> list[tuple[str, str]]:
    """`(verbo, ruta)` de cada ruta de edición o borrado que cuelga del libro."""
    return sorted(
        (verbo, ruta)
        for ruta, verbos in _rutas_del_libro(app).items()
        for verbo in verbos & VERBOS_DE_EDICION
    )


@pytest.fixture
def app_real(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.setenv("JWT_SECRET", "un-secreto-de-prueba-suficientemente-largo")
    return crear_app(Settings(_env_file=None))


def test_ninguna_ruta_edita_ni_borra_movimientos_de_cuenta_corriente(app_real: FastAPI) -> None:
    """CC-06, TR-06, INV-05."""
    # La revisión mira algo: las tres rutas de este change existen y se examinaron.
    assert {
        "/api/v1/cuentas-corrientes/saldos-iniciales",
        "/api/v1/clientes/{cliente_id}/cuenta-corriente",
        "/api/v1/proveedores/{proveedor_id}/cuenta-corriente",
    } <= set(_rutas_del_libro(app_real))

    assert rutas_de_edicion_sobre_el_libro(app_real) == []


def test_la_revision_detecta_una_ruta_de_borrado_sobre_el_libro() -> None:
    """Verificación en negativo: la misma revisión marca una ruta que sí edita."""
    app = FastAPI()

    @app.delete("/api/v1/cuentas-corrientes/movimientos/{movimiento_id}")
    def borrar(movimiento_id: str) -> None: ...

    @app.patch("/api/v1/clientes/{cliente_id}/cuenta-corriente")
    def editar(cliente_id: str) -> None: ...

    @app.get("/api/v1/clientes/{cliente_id}/cuenta-corriente")
    def leer(cliente_id: str) -> None: ...

    assert rutas_de_edicion_sobre_el_libro(app) == [
        ("DELETE", "/api/v1/cuentas-corrientes/movimientos/{movimiento_id}"),
        ("PATCH", "/api/v1/clientes/{cliente_id}/cuenta-corriente"),
    ]
