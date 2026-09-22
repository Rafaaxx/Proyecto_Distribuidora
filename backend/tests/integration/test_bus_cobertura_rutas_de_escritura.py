"""Tareas 14.2 y 14.7 (change 04, grupo 14): ratchet de cobertura del bus de
comandos. `CLAUDE.md` §4 ("Arquitectura"): "Toda escritura de negocio pasa
por el bus de comandos. No existen endpoints de escritura que lo esquiven."
Este archivo convierte esa regla en una prueba ejecutable: recorre TODAS
las rutas de escritura (POST/PUT/PATCH/DELETE) registradas en la app real
y exige que la función de cada una, en algún punto de su código (incluidas
las funciones anidadas que declara, como el `_ejecutar_handler` que le pasa
a `sync_service.procesar_comando`), referencie `procesar_comando` -- salvo
las exentas de forma explícita y enumerable en
`EXENCIONES_PERMANENTES_DE_AUTH` (change 03, D6, ver más abajo).

Esta es la señal temprana que pide `04` §14 y el portón para los changes 05
a 27 (tal como lo describe `tasks.md` línea 360): cualquier endpoint de
escritura futuro que no pase por el bus hace fallar este archivo, nombrando
la ruta.

La tarea 14.2 encontró dos rutas que esquivaban el bus sin estar nominadas
como deuda (`PUT /identidad/roles/{rol_id}/permisos`, `POST
/identidad/usuarios/{usuario_id}/desbloqueo`) y las dejó en una lista aparte,
explícitamente no permanente (`DEUDA_CONOCIDA_PENDIENTE_DE_DECISION`), para
no romper la suite mientras se decidía qué hacer. La tarea 14.7 cierra esa
decisión (usuario, 2026-09-22, `tasks.md` 14.3-14.6): ambas rutas ahora
delegan en el bus (`ROL_PERMISOS_CAMBIAR`, `USUARIO_DESBLOQUEAR`), así que
la lista de deuda queda vacía y se elimina -- junto con el código que la
usaba -- en vez de dejarla como una lista vacía sin sentido. La prueba
central vuelve a exigir el conjunto vacío como meta final, sin ninguna
excepción salvo `/auth`.

CÓMO SE DETECTA "pasa por el bus" (decisión de diseño de esta tarea,
reportada para confirmación humana en vez de resuelta en silencio): se
inspecciona el BYTECODE de la función del endpoint -- `co_names` de su
`__code__`, recorrido recursivamente en los objetos de código anidados que
aparecen en `co_consts` (las funciones que la función del endpoint declara
adentro, como el `_ejecutar_handler` de `identidad/api.py`) -- buscando el
nombre `procesar_comando`. Se prefirió esto sobre:
- **Buscar la cadena en el código fuente** (`inspect.getsource`): además de
  necesitar el mismo recorrido recursivo para las funciones anidadas, un
  comentario o docstring que mencione "procesar_comando" sin llamarlo haría
  pasar la prueba en falso -- justo la falsa sensación de cobertura que
  este ratchet existe para evitar (mismo criterio que el docstring de
  `test_inv21_ratchet_rutas.py`).
- **Inspeccionar el AST**: correcto en espíritu, pero mucho más código para
  el mismo resultado que ya da `co_names` (que ya es la forma en la que
  Python resuelve nombres globales/atributos en tiempo de ejecución).
`co_names` es inmune a reordenar imports, renombrar variables locales,
reformatear o mover comentarios -- solo cambia si la función deja de
referenciar ese nombre.
"""

from __future__ import annotations

from collections.abc import Callable
from types import CodeType

from fastapi import FastAPI

from app.core.config import Settings
from app.main import crear_app

# `test_ratchet_permiso_por_ruta.py` ya resuelve el mismo problema (aplanar
# el árbol de `app.include_router` anidados, acumulando el prefijo) --
# reutilizado en vez de duplicado, mismo criterio de DRY que ese archivo
# aplica sobre `app.routes`.
from tests.integration.test_ratchet_permiso_por_ruta import _rutas_con_prefijo

METODOS_DE_ESCRITURA = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Lista explícita y enumerable (change 03, D6, archivada en
# `openspec/changes/archive/2026-09-20-03-identidad-usuarios-permisos/design.md`):
# "Los endpoints de `/auth` quedan permanentemente fuera del bus, y eso no
# es deuda: no son operaciones de negocio, no tienen `operation_id` ni
# pueden tenerlo (el de login ocurre antes de que exista un usuario
# autenticado que pueda tener uno) y `02` §6.5 no los lista." Estas tres
# son las únicas rutas de `/auth` registradas hoy (`api_v1/auth.py`,
# confirmadas también en `test_inv21_ratchet_rutas.py::RUTAS_DE_AUTENTICACION`);
# una ruta nueva bajo `/auth` no declarada acá sigue exigiendo el bus (mismo
# criterio de "lista enumerable, no patrón de prefijo" que ese archivo).
EXENCIONES_PERMANENTES_DE_AUTH: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
    }
)


def _nombres_referenciados(code: CodeType) -> set[str]:
    """`co_names` de `code`, más los de cada objeto de código anidado en
    `co_consts` (una función declarada dentro de otra, como
    `_ejecutar_handler` en `identidad/api.py`), recorrido recursivamente."""
    nombres = set(code.co_names)
    for constante in code.co_consts:
        if isinstance(constante, CodeType):
            nombres |= _nombres_referenciados(constante)
    return nombres


# Las dos puertas de entrada reales al bus (`sync/service.py`):
# `procesar_comando` (un comando) y `procesar_lote` (`POST /sync/comandos`,
# tarea 8.6 -- recibe el lote de la cola local y llama a `procesar_comando`
# por cada ítem, adentro de `sync/service.py`, no en la función de la ruta;
# la ruta de `sync/api.py` solo referencia `procesar_lote`, nunca
# `procesar_comando` directamente). Ambos nombres cuentan como "pasa por el
# bus" -- lo que este ratchet exige es que ninguna ruta de escritura
# construya su propio camino a la base esquivando estas dos funciones.
NOMBRES_DE_ENTRADA_AL_BUS = frozenset({"procesar_comando", "procesar_lote"})


def endpoint_pasa_por_el_bus(funcion: Callable[..., object]) -> bool:
    """`True` si `funcion` (o alguna función que declara adentro)
    referencia `procesar_comando` o `procesar_lote` en su bytecode -- los
    nombres con los que `sync_service` se invoca en cada endpoint
    (`identidad/api.py` llama a `procesar_comando` directamente; `sync/api.py`
    llama a `procesar_lote`, que a su vez llama a `procesar_comando` por
    ítem dentro de `sync/service.py`, no en la función de la ruta)."""
    return bool(_nombres_referenciados(funcion.__code__) & NOMBRES_DE_ENTRADA_AL_BUS)


def rutas_de_escritura_sin_bus(
    app: FastAPI, *, exentas: frozenset[tuple[str, str]]
) -> list[tuple[str, str]]:
    sin_bus: list[tuple[str, str]] = []
    for path, route in _rutas_con_prefijo(app.routes):
        for metodo in route.methods or set():
            if metodo not in METODOS_DE_ESCRITURA:
                continue
            clave = (metodo, path)
            if clave in exentas:
                continue
            if not endpoint_pasa_por_el_bus(route.endpoint):
                sin_bus.append(clave)
    return sin_bus


def _app_real(database_url: str) -> FastAPI:
    return crear_app(
        Settings(
            _env_file=None,
            database_url=database_url,
            jwt_secret="secreto-de-prueba-cobertura-bus",
            jwt_kid="1",
        )
    )


def test_toda_ruta_de_escritura_pasa_por_el_bus_de_comandos(database_url: str) -> None:
    """Escenario central de las tareas 14.2/14.7: ninguna ruta de escritura
    de negocio esquiva el bus, salvo las exentas permanentes de `/auth`.
    Desde la tarea 14.7 (decisión del usuario, 2026-09-22) ya no existe
    ninguna deuda conocida: las dos rutas que la tarea 14.2 había encontrado
    sin bus (`PUT /identidad/roles/{rol_id}/permisos`, `POST
    /identidad/usuarios/{usuario_id}/desbloqueo`) ahora delegan en
    `ROL_PERMISOS_CAMBIAR`/`USUARIO_DESBLOQUEAR`.

    Esta prueba compara contra el conjunto vacío, sin ninguna excepción
    nombrada aparte de `/auth`: si aparece una ruta de escritura nueva que
    esquiva el bus (el escenario que este ratchet existe para vetar en los
    changes 05-27), la prueba falla, nombrando la ruta exacta.
    """
    app = _app_real(database_url)

    sin_bus = set(rutas_de_escritura_sin_bus(app, exentas=EXENCIONES_PERMANENTES_DE_AUTH))

    assert sin_bus == set(), (
        f"{len(sin_bus)} ruta(s) de escritura no pasan por el bus de comandos: "
        f"{sin_bus}. Toda escritura de negocio debe pasar por "
        "sync_service.procesar_comando/procesar_lote (CLAUDE.md §4), salvo las "
        "tres exentas permanentemente por ser de /auth (change 03, D6)."
    )


def test_las_rutas_exentas_de_auth_estan_registradas(database_url: str) -> None:
    """Verificación complementaria (mismo criterio que
    `test_inv21_ratchet_rutas.py::test_inv21_las_rutas_de_autenticacion...`):
    las tres rutas de `EXENCIONES_PERMANENTES_DE_AUTH` existen de verdad en
    la app -- si `/auth` cambiara de forma y alguna dejara de estar
    registrada, esta prueba lo nota en vez de dejar una exención fantasma."""
    app = _app_real(database_url)

    rutas_presentes = {
        (metodo, path)
        for path, route in _rutas_con_prefijo(app.routes)
        for metodo in (route.methods or set())
    }
    for ruta_exenta in EXENCIONES_PERMANENTES_DE_AUTH:
        assert ruta_exenta in rutas_presentes, f"Ruta exenta {ruta_exenta} no está registrada."


def test_el_ratchet_detecta_una_ruta_de_escritura_que_no_pasa_por_el_bus() -> None:
    """Verificación en negativo (mismo patrón que los otros dos ratchets de
    rutas): una app de prueba con una ruta de escritura ficticia que NO
    llama a `procesar_comando` debe ser detectada y nombrada."""
    app_de_prueba = FastAPI()

    @app_de_prueba.post("/api/v1/negocio/sin-bus")
    def ruta_ficticia_sin_bus() -> dict[str, str]:  # pragma: no cover
        return {"ok": "true"}

    sin_bus = rutas_de_escritura_sin_bus(app_de_prueba, exentas=frozenset())

    assert sin_bus == [("POST", "/api/v1/negocio/sin-bus")]


def test_el_ratchet_no_marca_una_ruta_que_si_pasa_por_el_bus() -> None:
    """Complementaria: una ruta que sí referencia `procesar_comando` -- acá,
    desde una función anidada, mismo patrón que `identidad/api.py` -- no se
    marca como infractora. Triangula el mecanismo de detección contra el
    caso "referencia en una función anidada", no solo "referencia directa"."""
    app_de_prueba = FastAPI()

    @app_de_prueba.post("/api/v1/negocio/con-bus")
    def ruta_con_bus() -> dict[str, str]:  # pragma: no cover
        def _ejecutar_handler() -> None:
            # Referencia intencional, nunca resuelta en tiempo de ejecución
            # (`_ejecutar_handler` no se llega a invocar de verdad, ver
            # `# pragma: no cover` de `ruta_con_bus`): lo único que importa
            # es que el nombre `procesar_comando` quede en el bytecode de
            # esta función anidada, para triangular la detección contra el
            # caso "referencia en una función anidada".
            procesar_comando()  # type: ignore[name-defined]  # noqa: F821

        _ejecutar_handler()
        return {"ok": "true"}

    sin_bus = rutas_de_escritura_sin_bus(app_de_prueba, exentas=frozenset())

    assert sin_bus == []


def test_una_ruta_de_auth_no_declarada_no_queda_exenta_por_prefijo() -> None:
    """Verificación en negativo (mismo criterio que el ratchet de
    aislamiento, tarea 12.6): la exención de `/auth` es una lista
    enumerable, no un patrón de prefijo -- una ruta de escritura ficticia
    bajo `/auth` que no esté declarada en `EXENCIONES_PERMANENTES_DE_AUTH`
    sigue exigiendo el bus."""
    app_de_prueba = FastAPI()

    @app_de_prueba.post("/api/v1/auth/impersonar")
    def ruta_ficticia_bajo_auth() -> dict[str, str]:  # pragma: no cover
        return {"ok": "true"}

    sin_bus = rutas_de_escritura_sin_bus(app_de_prueba, exentas=EXENCIONES_PERMANENTES_DE_AUTH)

    assert sin_bus == [("POST", "/api/v1/auth/impersonar")]
