"""INV-21 (`docs/01-dominio.md` §20; `design.md` D1): ratchet de rutas.

Sin JWT todavía (llega en el change 03), el aislamiento de rutas de negocio
no se puede probar end-to-end. Esta prueba recorre dinámicamente las rutas
registradas de FastAPI (`app.openapi()["paths"]`, que refleja el path
completo con prefijo, a diferencia de `app.routes` cuyas rutas anidadas no
exponen el path resuelto en esta versión de FastAPI) y falla nombrando ruta
y método si aparece una ruta de negocio que no está en `COBERTURA_DE_AISLAMIENTO`.

Hoy `COBERTURA_DE_AISLAMIENTO` está vacía (no hay ninguna ruta de negocio) y
el mensaje de la prueba lo dice explícitamente (tarea 9.2), para que la
cobertura nula no se confunda con cobertura completa (`design.md`, Risks).

CÓMO DECLARAR UNA RUTA NUEVA (tarea 9.4, para el change 03 y siguientes):
cuando un módulo agrega su primer `api.py` con una ruta de negocio, agregar
la tupla `(metodo, "/api/v1/<ruta>")` a `COBERTURA_DE_AISLAMIENTO` en este
archivo, junto con la prueba de integración (con dos organizaciones y un
token/dependencia real) que demuestra que esa ruta aísla por organización.
Sin esa prueba, no agregar la tupla: agregarla sin probar el aislamiento real
es exactamente la falsa sensación de cobertura que este ratchet existe para
evitar.
"""

from __future__ import annotations

import os

from app.core.config import Settings
from app.main import crear_app

# Lista enumerable y explícita (`design.md` D1): nunca un patrón de nombre.
RUTAS_DE_SISTEMA = frozenset(
    {
        ("get", "/api/v1/salud"),
        ("get", "/api/v1/version"),
    }
)

# Ver "CÓMO DECLARAR UNA RUTA NUEVA" arriba. Vacío a propósito en este change.
COBERTURA_DE_AISLAMIENTO: frozenset[tuple[str, str]] = frozenset()


def rutas_de_negocio_sin_cobertura(
    rutas_del_esquema: dict[str, dict[str, object]],
    *,
    rutas_de_sistema: frozenset[tuple[str, str]],
    cobertura: frozenset[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Devuelve las rutas `(metodo, path)` que son de negocio (no están en
    `rutas_de_sistema`) y no están cubiertas por `cobertura`."""
    todas = [(metodo, path) for path, metodos in rutas_del_esquema.items() for metodo in metodos]
    de_negocio = [ruta for ruta in todas if ruta not in rutas_de_sistema]
    return [ruta for ruta in de_negocio if ruta not in cobertura]


def _rutas_reales_del_esquema() -> dict[str, dict[str, object]]:
    app = crear_app(Settings())  # type: ignore[call-arg]
    schema = app.openapi()
    paths: dict[str, dict[str, object]] = schema["paths"]
    return paths


def test_inv21_toda_ruta_de_negocio_esta_cubierta_por_el_aislamiento(
    database_url: str,
) -> None:
    """Escenario 'Una ruta de negocio sin cobertura de aislamiento hace
    fallar la verificación'."""
    os.environ.setdefault("DATABASE_URL", database_url)
    rutas = _rutas_reales_del_esquema()

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        rutas, rutas_de_sistema=RUTAS_DE_SISTEMA, cobertura=COBERTURA_DE_AISLAMIENTO
    )

    total_de_negocio = len(
        [
            (metodo, path)
            for path, metodos in rutas.items()
            for metodo in metodos
            if (metodo, path) not in RUTAS_DE_SISTEMA
        ]
    )
    mensaje = (
        f"INV-21: {len(sin_cobertura)} ruta(s) de negocio sin cobertura de "
        f"aislamiento: {sin_cobertura}. Rutas de negocio cubiertas hoy: "
        f"{total_de_negocio - len(sin_cobertura)} de {total_de_negocio} "
        "(tarea 9.2: la cobertura nula debe ser visible, no confundirse con completa)."
    )
    assert sin_cobertura == [], mensaje
    assert total_de_negocio == 0, (
        "Este change no debe registrar ninguna ruta de negocio (design.md D1); "
        f"se encontraron {total_de_negocio}. Si esto cambió, el change 03 debe "
        "agregar su cobertura en COBERTURA_DE_AISLAMIENTO antes de continuar."
    )


def test_inv21_las_rutas_de_sistema_no_requieren_organizacion(database_url: str) -> None:
    """Escenario 'Las rutas de sistema no requieren organización': las
    rutas de sistema están explícitamente exentas, no por patrón de nombre."""
    os.environ.setdefault("DATABASE_URL", database_url)
    rutas = _rutas_reales_del_esquema()

    rutas_presentes = {(metodo, path) for path, metodos in rutas.items() for metodo in metodos}
    for ruta_sistema in RUTAS_DE_SISTEMA:
        assert ruta_sistema in rutas_presentes, (
            f"Ruta de sistema {ruta_sistema} esperada pero no está registrada."
        )


def test_inv21_detecta_una_ruta_de_negocio_ficticia_sin_cobertura() -> None:
    """Verificación en negativo (tarea 9.3): una ruta de negocio no
    registrada en `COBERTURA_DE_AISLAMIENTO` debe ser detectada y nombrada."""
    esquema_con_ruta_ficticia = {
        "/api/v1/salud": {"get": {}},
        "/api/v1/version": {"get": {}},
        "/api/v1/venta": {"post": {}},  # ruta de negocio ficticia, sin cobertura
    }

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        esquema_con_ruta_ficticia,
        rutas_de_sistema=RUTAS_DE_SISTEMA,
        cobertura=COBERTURA_DE_AISLAMIENTO,
    )

    assert sin_cobertura == [("post", "/api/v1/venta")]


def test_inv21_no_marca_una_ruta_de_negocio_que_si_tiene_cobertura_declarada() -> None:
    """Verificación complementaria: si una ruta de negocio SÍ está en
    `cobertura`, no se marca como infractora."""
    esquema = {
        "/api/v1/salud": {"get": {}},
        "/api/v1/venta": {"post": {}},
    }
    cobertura_de_prueba = frozenset({("post", "/api/v1/venta")})

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        esquema, rutas_de_sistema=RUTAS_DE_SISTEMA, cobertura=cobertura_de_prueba
    )

    assert sin_cobertura == []
