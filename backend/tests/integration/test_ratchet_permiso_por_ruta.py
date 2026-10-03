"""Ratchet de la tarea 10.3: toda ruta de negocio declara el permiso que
exige (`design.md` D5; spec `autorizacion-por-permiso`, escenarios "Una ruta
de negocio sin permiso declarado no llega a existir" y "Las rutas de
autenticación y de sistema no exigen permiso").

Distinto del ratchet de aislamiento del grupo 12
(`test_inv21_ratchet_rutas.py`, que exige que cada ruta de negocio tenga
PRUEBA de aislamiento): este exige que cada ruta de negocio declare la
dependencia `requiere_permiso` en su firma, recorriendo el árbol de
`Dependant` de FastAPI (`app.routes`), no `app.openapi()["paths"]` (que no
expone las dependencias).

CÓMO DECLARAR UNA RUTA NUEVA: agregar `Depends(requiere_permiso("CODIGO"))`
a la firma de la función de la ruta (como en `identidad/api.py`). Una ruta
de negocio sin esa dependencia hace fallar este ratchet nombrando ruta y
método. Las rutas de sistema y de autenticación están exentas de forma
explícita y enumerable en `RUTAS_EXENTAS_DE_PERMISO`, no por patrón de nombre.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

# `app.main` primero: importa la cadena completa de routers (`identidad.api`
# -> `core.autenticacion`) antes de que este módulo pida `requiere_permiso`
# directamente -- en el orden inverso, `core.autenticacion` queda a medio
# inicializar cuando `identidad.api` intenta importar `ContextoAutenticado`
# de él (import circular real del árbol de routers, no de este archivo).
# fmt: off
# ruff: noqa: I001
from app.main import crear_app
from app.core.autenticacion import ContextoAutenticado, requiere_permiso
from app.core.config import Settings
# fmt: on

# Importados a nivel de módulo (no dentro de las funciones de prueba) a
# propósito: con `from __future__ import annotations`, FastAPI resuelve los
# `Annotated[...]` de las rutas ficticias de abajo contra los globals del
# módulo, no contra el scope local de la función de prueba -- un import
# local aquí haría que la resolución de `ContextoAutenticado`/`Depends`
# fallara en silencio y el `Dependant` de la ruta quedara incompleto.

# Lista explícita y enumerable (mismo criterio que `RUTAS_DE_SISTEMA` del
# ratchet de aislamiento): rutas de sistema (sin organización en contexto) y
# rutas de `/auth` (SEG-01: el login ocurre antes de que exista un usuario
# autenticado que pueda tener un permiso).
RUTAS_EXENTAS_DE_PERMISO = frozenset(
    {
        ("GET", "/api/v1/salud"),
        ("GET", "/api/v1/version"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
        # Change 04, grupo 8, tarea 8.6 (`sync/api.py`): un lote trae
        # comandos de tipos distintos, cada uno con su propio permiso de
        # negocio -- no hay UN permiso fijo que declarar en esta ruta.
        # `requiere_permiso` exige exactamente uno por ruta (`design.md`
        # D5); acá la validación de permiso corre por comando, dentro del
        # bus, a través del handler resuelto por `app.commands.registro`
        # (SEG-06, `02` §6.3 paso 4), no de esta ruta. Sí exige sesión
        # (`Depends(obtener_contexto_autenticado)`, ver docstring de
        # `sync/api.py`).
        ("POST", "/api/v1/sync/comandos"),
        # Change 06b, grupo 4 (`identidad/api.py::router_yo`, ADR-027): la
        # consulta de la propia sesión exige un access token válido
        # (`Depends(obtener_contexto_autenticado)`) pero ningún permiso en
        # particular -- su propósito es informar cuáles tiene el usuario,
        # así que no hay un permiso fijo que declarar sin volverse
        # circular (spec `autorizacion-por-permiso`, escenario "La consulta
        # de la propia sesión no exige permiso pero sí sesión").
        ("GET", "/api/v1/yo"),
        # Change 11, grupo 10 (`configuracion/api.py`, tarea 10.3, `design.md` D14): los
        # medios de pago y los motivos activos los lee cualquier usuario autenticado de la
        # organizacion, porque los consumen pantallas de compras, cobranzas y anulaciones,
        # cada una con su propio permiso de negocio. Exigen sesion valida y habilitada
        # (`Depends(requiere_sesion)`), no un
        # permiso (spec `catalogos-configurables`, `test_compras_api.py`:
        # `test_medios_y_motivos_sin_sesion_responden_401`).
        ("GET", "/api/v1/configuracion/medios-pago"),
        ("GET", "/api/v1/configuracion/motivos"),
    }
)


def _rutas_con_prefijo(routes: list[object], prefijo: str = "") -> list[tuple[str, APIRoute]]:
    """Aplana el árbol de routers de FastAPI, acumulando el prefijo de cada
    `include_router` anidado (`docker`/CLAUDE.md no aplica; nota técnica:
    en esta versión de FastAPI, `app.include_router` no copia las rutas al
    padre -- las envuelve en un `_IncludedRouter` perezoso con
    `original_router`/`include_context.prefix`, así que `route.path` de una
    `APIRoute` anidada NO incluye el prefijo con el que se incluyó; hay que
    acumularlo al recorrer, igual que hace `app.openapi()` internamente)."""
    encontradas: list[tuple[str, APIRoute]] = []
    for route in routes:
        if isinstance(route, APIRoute):
            encontradas.append((prefijo + route.path, route))
        elif hasattr(route, "original_router"):
            sub_prefijo = prefijo + route.include_context.prefix
            encontradas.extend(_rutas_con_prefijo(route.original_router.routes, sub_prefijo))
    return encontradas


def _dependencias_del_arbol(dependant: object) -> list[object]:
    """Recorre recursivamente el árbol de `Dependant` de una `APIRoute`
    (incluye las sub-dependencias declaradas como parámetros de la función,
    no solo las de `dependencies=[...]` a nivel de ruta)."""
    vistos: list[object] = []
    pendientes = [dependant]
    while pendientes:
        actual = pendientes.pop()
        vistos.append(actual)
        pendientes.extend(getattr(actual, "dependencies", []))
    return vistos


def ruta_declara_permiso(route: APIRoute) -> bool:
    """`True` si en algún punto del árbol de dependencias de `route` hay una
    dependencia marcada por `requiere_permiso` (`_dependencia.permiso_requerido`,
    `core/autenticacion.py`)."""
    for dependant in _dependencias_del_arbol(route.dependant):
        call = getattr(dependant, "call", None)
        if getattr(call, "permiso_requerido", None) is not None:
            return True
    return False


def rutas_de_negocio_sin_permiso(
    app: FastAPI, *, exentas: frozenset[tuple[str, str]]
) -> list[tuple[str, str]]:
    sin_permiso: list[tuple[str, str]] = []
    for path, route in _rutas_con_prefijo(app.routes):
        for metodo in route.methods or set():
            clave = (metodo, path)
            if clave in exentas:
                continue
            if not ruta_declara_permiso(route):
                sin_permiso.append(clave)
    return sin_permiso


def test_toda_ruta_de_negocio_declara_el_permiso_que_exige(database_url: str) -> None:
    """Escenario "Una ruta de negocio sin permiso declarado no llega a
    existir"."""
    app = crear_app(
        Settings(
            _env_file=None,
            database_url=database_url,
            jwt_secret="secreto-de-prueba",
            jwt_kid="1",
        )
    )

    sin_permiso = rutas_de_negocio_sin_permiso(app, exentas=RUTAS_EXENTAS_DE_PERMISO)

    assert sin_permiso == [], (
        f"{len(sin_permiso)} ruta(s) de negocio sin permiso declarado: {sin_permiso} "
        "(tarea 10.3: toda ruta de negocio debe usar Depends(requiere_permiso(...)))."
    )


def test_las_rutas_de_sistema_y_autenticacion_no_exigen_permiso(database_url: str) -> None:
    """Escenario "Las rutas de autenticación y de sistema no exigen
    permiso": están exentas por declaración explícita, no porque de hecho
    tengan la dependencia (de hecho no la tienen)."""
    app = crear_app(
        Settings(
            _env_file=None,
            database_url=database_url,
            jwt_secret="secreto-de-prueba",
            jwt_kid="1",
        )
    )
    rutas_presentes = {
        (metodo, path)
        for path, route in _rutas_con_prefijo(app.routes)
        for metodo in (route.methods or set())
    }
    for ruta_exenta in RUTAS_EXENTAS_DE_PERMISO:
        assert ruta_exenta in rutas_presentes, f"Ruta exenta {ruta_exenta} no está registrada."


def test_la_consulta_de_la_propia_sesion_no_exige_permiso_pero_si_sesion(
    database_url: str,
) -> None:
    """Escenario "La consulta de la propia sesión no exige permiso pero sí
    sesión" (spec `autorizacion-por-permiso`): `GET /api/v1/yo` no se marca
    como infractora del ratchet de permiso por ruta (está en
    `RUTAS_EXENTAS_DE_PERMISO`), pero una petición sin access token igual se
    rechaza como no autenticada -- la exención es de PERMISO, nunca de
    SESIÓN (ADR-027)."""
    app = crear_app(
        Settings(
            _env_file=None,
            database_url=database_url,
            jwt_secret="secreto-de-prueba",
            jwt_kid="1",
        )
    )

    sin_permiso = rutas_de_negocio_sin_permiso(app, exentas=RUTAS_EXENTAS_DE_PERMISO)
    assert ("GET", "/api/v1/yo") not in sin_permiso

    cliente = TestClient(app)
    respuesta = cliente.get("/api/v1/yo")

    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "IDENTIDAD_ACCESS_TOKEN_AUSENTE"


def test_el_ratchet_detecta_una_ruta_de_negocio_sin_permiso_declarado() -> None:
    """Verificación en negativo (tarea 10.3): se agrega a propósito una ruta
    de negocio sin `requiere_permiso` y el ratchet debe nombrarla."""
    app_de_prueba = FastAPI()

    @app_de_prueba.get("/api/v1/salud")
    def salud() -> dict[str, str]:  # pragma: no cover - solo para la prueba
        return {"estado": "ok"}

    @app_de_prueba.post("/api/v1/negocio/sin-permiso")
    def ruta_ficticia_sin_permiso() -> dict[str, str]:  # pragma: no cover
        return {}

    exentas = frozenset({("GET", "/api/v1/salud")})
    sin_permiso = rutas_de_negocio_sin_permiso(app_de_prueba, exentas=exentas)

    assert sin_permiso == [("POST", "/api/v1/negocio/sin-permiso")]


def test_el_ratchet_no_marca_una_ruta_que_si_declara_el_permiso() -> None:
    """Complementaria: una ruta que sí usa `Depends(requiere_permiso(...))`
    no debe marcarse como infractora."""
    app_de_prueba = FastAPI()

    @app_de_prueba.get("/api/v1/negocio/con-permiso")
    def ruta_con_permiso(
        contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso("ALGUN_PERMISO"))],
    ) -> dict[str, str]:  # pragma: no cover
        return {}

    sin_permiso = rutas_de_negocio_sin_permiso(app_de_prueba, exentas=frozenset())

    assert sin_permiso == []
