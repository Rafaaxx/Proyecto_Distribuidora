"""Tarea 12.4 (cierre de INV-21): "La organización usada es siempre la del
token" (spec `aislamiento-multiorganizacion`) -- generaliza a TODAS las
rutas de negocio registradas lo que `test_auth_api.py::
test_ninguna_organizacion_informada_en_la_peticion_se_usa` y
`test_el_dispositivo_del_contexto_es_el_del_token` ya probaban puntualmente
sobre `/identidad/dispositivos` (tarea 10.4).

En vez de repetir, ruta por ruta, "informar `organizacion_id` no tiene
efecto" contra Postgres real, esta prueba recorre estructuralmente el
esquema OpenAPI (mismo mecanismo que el ratchet de aislamiento y el de
permiso por ruta) y confirma algo más fuerte: ninguna ruta de negocio
siquiera DECLARA un parámetro o un campo de cuerpo llamado `organizacion_id`
-- no hay forma de "informarlo" porque el endpoint no lo acepta en absoluto
(`CLAUDE.md` §4: "`organizacion_id` se toma siempre del token JWT, nunca
del cuerpo de la petición"). Complementa, no reemplaza, las pruebas HTTP
puntuales que confirman el comportamiento real."""

from __future__ import annotations

import os

from app.core.config import Settings
from app.main import crear_app

# Mismas listas que `test_inv21_ratchet_rutas.py` (tarea 12.1) -- duplicadas
# a propósito, no importadas: cada archivo de `tests/integration/` es
# autónomo en este proyecto (sin `__init__.py`, ver convención documentada
# en `conftest.py`), y esta prueba es sobre la FORMA del esquema OpenAPI, no
# sobre el registro de cobertura del ratchet en sí -- una divergencia entre
# ambas listas sería en sí misma una señal de alerta detectable por
# inspección, no un acoplamiento que valga la pena introducir.
COBERTURA_DE_AISLAMIENTO: frozenset[tuple[str, str]] = frozenset(
    {
        ("get", "/api/v1/identidad/dispositivos"),
        ("delete", "/api/v1/identidad/dispositivos/{dispositivo_id}"),
        ("get", "/api/v1/identidad/usuarios"),
        ("post", "/api/v1/identidad/usuarios"),
        ("put", "/api/v1/identidad/roles/{rol_id}/permisos"),
        ("post", "/api/v1/identidad/usuarios/{usuario_id}/pin"),
        ("post", "/api/v1/identidad/usuarios/{usuario_id}/desbloqueo"),
    }
)
RUTAS_DE_AUTENTICACION = frozenset(
    {
        ("post", "/api/v1/auth/login"),
        ("post", "/api/v1/auth/refresh"),
        ("post", "/api/v1/auth/logout"),
    }
)

_NOMBRE_PROHIBIDO = "organizacion_id"


def _esquema_real() -> dict[str, object]:
    app = crear_app(Settings())  # type: ignore[call-arg]
    return app.openapi()


def _nombres_de_parametros(operacion: dict[str, object]) -> set[str]:
    return {p.get("name") for p in operacion.get("parameters", [])}  # type: ignore[union-attr]


def _propiedades_del_cuerpo(
    operacion: dict[str, object], componentes: dict[str, object]
) -> set[str]:
    cuerpo = operacion.get("requestBody")
    if not cuerpo:
        return set()
    esquema_cuerpo = cuerpo.get("content", {}).get("application/json", {}).get("schema", {})  # type: ignore[union-attr]
    ref = esquema_cuerpo.get("$ref")
    if ref is None:
        return set(esquema_cuerpo.get("properties", {}).keys())
    nombre_schema = ref.rsplit("/", 1)[-1]
    definicion = componentes.get("schemas", {}).get(nombre_schema, {})  # type: ignore[union-attr]
    return set(definicion.get("properties", {}).keys())


def test_ninguna_ruta_de_negocio_declara_organizacion_id_como_parametro_o_campo(
    database_url: str,
) -> None:
    """Escenario "La organización usada es siempre la del token": recorre
    cada ruta de `COBERTURA_DE_AISLAMIENTO` (tarea 12.1) y confirma que
    ninguna declara `organizacion_id` como parámetro de ruta, de consulta,
    de encabezado, ni como campo del cuerpo. Regla: `02` §8, INV-21."""
    os.environ.setdefault("DATABASE_URL", database_url)
    esquema = _esquema_real()
    rutas = esquema["paths"]  # type: ignore[index]
    componentes = esquema.get("components", {})  # type: ignore[assignment]

    infractoras: list[tuple[str, str, str]] = []
    for metodo, path in COBERTURA_DE_AISLAMIENTO:
        operacion = rutas[path][metodo]  # type: ignore[index]
        if _NOMBRE_PROHIBIDO in _nombres_de_parametros(operacion):
            infractoras.append((metodo, path, "parametro"))
        if _NOMBRE_PROHIBIDO in _propiedades_del_cuerpo(operacion, componentes):
            infractoras.append((metodo, path, "cuerpo"))

    assert infractoras == [], (
        f"Rutas que declaran '{_NOMBRE_PROHIBIDO}' en vez de tomarlo del token: {infractoras}."
    )


def test_las_rutas_de_autenticacion_tampoco_declaran_organizacion_id(
    database_url: str,
) -> None:
    """Triangulación: el mismo criterio vale para las rutas de `/auth`
    (que reciben `organizacion_slug`, no `organizacion_id` -- la
    organización todavía no está resuelta antes del login)."""
    os.environ.setdefault("DATABASE_URL", database_url)
    esquema = _esquema_real()
    rutas = esquema["paths"]  # type: ignore[index]
    componentes = esquema.get("components", {})  # type: ignore[assignment]

    infractoras: list[tuple[str, str, str]] = []
    for metodo, path in RUTAS_DE_AUTENTICACION:
        operacion = rutas[path][metodo]  # type: ignore[index]
        if _NOMBRE_PROHIBIDO in _nombres_de_parametros(operacion):
            infractoras.append((metodo, path, "parametro"))
        if _NOMBRE_PROHIBIDO in _propiedades_del_cuerpo(operacion, componentes):
            infractoras.append((metodo, path, "cuerpo"))

    assert infractoras == []


def test_deteccion_en_negativo_una_ruta_con_organizacion_id_en_el_cuerpo_se_marca() -> None:
    """Verificación en negativo (mismo criterio que los ratchets de rutas y
    de permiso): un esquema fabricado con `organizacion_id` en el cuerpo de
    una ruta debe ser detectado, para confiar en que la prueba real no pasa
    por vacuidad."""
    operacion_infractora = {
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"properties": {"organizacion_id": {"type": "string"}, "nombre": {}}}
                }
            }
        }
    }
    assert _NOMBRE_PROHIBIDO in _propiedades_del_cuerpo(operacion_infractora, {})
