"""Change 09, tarea 9.4, escenario "No existe ruta que edite o borre movimientos"
de `specs/stock/libro-de-stock` (STK-04, TR-06, INV-05) y "La historia no se
edita" de `specs/costeo/costo-promedio` (CST-13).

Los libros de stock y de costo son de solo inserción: la base lo impone con los
permisos (INV-05) y la API no ofrece ninguna forma de pedirlo. Se revisan todas
las rutas registradas de la aplicación real: ninguna `PUT`, `PATCH` ni `DELETE`
cuelga del kardex, del stock inicial, de los saldos, de un `movimiento` ni del
costo de un producto. Sí hay un `PUT` sobre `/stock/ubicaciones/{id}`: la
ubicación es un maestro (se modifica por reemplazo completo), no un libro, y no
coincide con ningún fragmento del libro. Un recurso nuevo con esos verbos sobre
los libros rompe esta prueba y obliga a leer TR-06 antes de agregarlo.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import crear_app

VERBOS_DE_EDICION = {"PUT", "PATCH", "DELETE"}
FRAGMENTOS_DEL_LIBRO = (
    "/stock/kardex",
    "/stock/iniciales",
    "/stock/transferencias",
    "/stock/ajustes",
    "/saldos",
    "movimiento",
    "/productos/{producto_id}/costo",
)


def _rutas_del_libro(app: FastAPI) -> dict[str, set[str]]:
    """`{ruta: {verbos}}` de cada ruta que cuelga de los libros. Se lee de
    `app.openapi()["paths"]`, que trae el camino completo con prefijo (el mismo
    criterio que `test_inv21_ratchet_rutas.py`)."""
    paths: dict[str, dict[str, object]] = app.openapi()["paths"]
    return {
        ruta: {verbo.upper() for verbo in operaciones}
        for ruta, operaciones in paths.items()
        if any(fragmento in ruta for fragmento in FRAGMENTOS_DEL_LIBRO)
    }


def rutas_de_edicion_sobre_el_libro(app: FastAPI) -> list[tuple[str, str]]:
    """`(verbo, ruta)` de cada ruta de edición o borrado que cuelga de los libros."""
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


def test_ninguna_ruta_edita_ni_borra_el_libro_de_stock_ni_el_de_costo(app_real: FastAPI) -> None:
    """STK-04, TR-06, INV-05, CST-13."""
    # La revisión mira algo: las rutas de este change existen y se examinaron.
    assert {
        "/api/v1/stock/iniciales",
        "/api/v1/stock/kardex",
        "/api/v1/stock/ubicaciones/{ubicacion_id}/saldos",
        "/api/v1/catalogo/productos/{producto_id}/costo",
    } <= set(_rutas_del_libro(app_real))

    assert rutas_de_edicion_sobre_el_libro(app_real) == []


def test_la_ubicacion_es_un_maestro_y_se_modifica_por_put(app_real: FastAPI) -> None:
    """Aclaración de la regla: el `PUT` de la ubicación no es una ruta del libro."""
    paths = app_real.openapi()["paths"]

    assert "put" in paths["/api/v1/stock/ubicaciones/{ubicacion_id}"]
    assert "/api/v1/stock/ubicaciones/{ubicacion_id}" not in _rutas_del_libro(app_real)


def test_la_revision_detecta_una_ruta_de_borrado_sobre_los_libros() -> None:
    """Verificación en negativo: la misma revisión marca una ruta que sí edita."""
    app = FastAPI()

    @app.delete("/api/v1/stock/movimientos/{movimiento_id}")
    def borrar(movimiento_id: str) -> None: ...

    @app.patch("/api/v1/stock/kardex")
    def editar() -> None: ...

    @app.put("/api/v1/catalogo/productos/{producto_id}/costo")
    def reemplazar(producto_id: str) -> None: ...

    @app.get("/api/v1/stock/kardex/leer")
    def leer() -> None: ...

    assert rutas_de_edicion_sobre_el_libro(app) == [
        ("DELETE", "/api/v1/stock/movimientos/{movimiento_id}"),
        ("PATCH", "/api/v1/stock/kardex"),
        ("PUT", "/api/v1/catalogo/productos/{producto_id}/costo"),
    ]


OPERACIONES_NUEVAS = ("/api/v1/stock/transferencias", "/api/v1/stock/ajustes")


def test_la_anulacion_es_la_unica_escritura_sobre_una_transferencia_o_un_ajuste_existente(
    app_real: FastAPI,
) -> None:
    """Change 14, tarea 11.1 (TR-06, INV-05): las transferencias y los ajustes solo se crean
    (`POST` a la colección) o se anulan (`POST .../anulacion`); ninguna ruta los edita ni los
    borra, y una lectura es siempre `GET`."""
    paths = app_real.openapi()["paths"]
    rutas = {
        ruta: {verbo.upper() for verbo in operaciones}
        for ruta, operaciones in paths.items()
        if ruta.startswith(OPERACIONES_NUEVAS)
    }

    assert rutas == {
        "/api/v1/stock/transferencias": {"GET", "POST"},
        "/api/v1/stock/transferencias/{transferencia_id}": {"GET"},
        "/api/v1/stock/transferencias/{transferencia_id}/anulacion": {"POST"},
        "/api/v1/stock/ajustes": {"GET", "POST"},
        "/api/v1/stock/ajustes/{ajuste_id}": {"GET"},
        "/api/v1/stock/ajustes/{ajuste_id}/anulacion": {"POST"},
    }
    assert rutas_de_edicion_sobre_el_libro(app_real) == []


def test_la_revision_detecta_una_ruta_que_edita_una_transferencia_o_un_ajuste() -> None:
    """Verificación en negativo: el mismo recorrido marca una ruta de edición sobre ellos."""
    app = FastAPI()

    @app.put("/api/v1/stock/transferencias/{transferencia_id}")
    def editar_transferencia(transferencia_id: str) -> None: ...

    @app.delete("/api/v1/stock/ajustes/{ajuste_id}")
    def borrar_ajuste(ajuste_id: str) -> None: ...

    @app.post("/api/v1/stock/ajustes/{ajuste_id}/anulacion")
    def anular(ajuste_id: str) -> None: ...

    assert rutas_de_edicion_sobre_el_libro(app) == [
        ("DELETE", "/api/v1/stock/ajustes/{ajuste_id}"),
        ("PUT", "/api/v1/stock/transferencias/{transferencia_id}"),
    ]
