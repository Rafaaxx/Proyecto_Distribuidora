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
        # Change 06b, grupo 9, tarea 9.2 (`identidad/api.py::router_yo`,
        # ADR-027, D1-A): la consulta de la propia sesión no declara NINGÚN
        # parámetro -- ni `organizacion_id` ni `usuario_id`, que salen del
        # token. Es la ruta donde el criterio de esta prueba se cumple de la
        # forma más fuerte: no hay forma de informar la organización, porque
        # la operación no tiene dónde declararla. Su comportamiento real
        # (informar identificadores ajenos no cambia la respuesta) lo
        # comprueba `test_inv21_aislamiento_endpoints_identidad.py::
        # TestAislamientoDeLaSesion`.
        ("get", "/api/v1/yo"),
        # Change 12, grupo 7 (tarea 7.1): las cuatro rutas nuevas -- la anulación dedicada
        # de `PAGO_PROVEEDOR_ANULAR` y las tres lecturas (saldo del proveedor, listado y
        # detalle de pagos). Su comportamiento real (informar el `organizacion_id` de otra
        # organización no cambia la respuesta ni toca datos ajenos) lo comprueba
        # `test_inv21_aislamiento_endpoints_proveedores.py::
        # TestAislamientoDePagosAProveedores`. Acá se agrega la afirmación estructural:
        # ninguna declara `organizacion_id` ni como parámetro ni como campo de cuerpo, así
        # que no hay forma de informarlo por el contrato (TR-08, INV-21).
        ("post", "/api/v1/pagos-proveedores/{pago_id}/anulacion"),
        ("get", "/api/v1/pagos-proveedores"),
        ("get", "/api/v1/pagos-proveedores/{pago_id}"),
        ("get", "/api/v1/proveedores/{proveedor_id}/saldo"),
        # Change 13, tarea 11.1: las diecinueve rutas de `precios/api.py`. Su comportamiento
        # real lo comprueba `test_inv21_aislamiento_endpoints_precios.py`; acá la afirmacion
        # estructural (TR-08, INV-21): ninguna declara `organizacion_id`.
        ("post", "/api/v1/precios/listas"),
        ("get", "/api/v1/precios/listas"),
        ("get", "/api/v1/precios/listas/opciones"),
        ("get", "/api/v1/precios/listas/{lista_id}"),
        ("put", "/api/v1/precios/listas/{lista_id}"),
        ("get", "/api/v1/precios/listas/{lista_id}/reglas"),
        ("post", "/api/v1/precios/listas/{lista_id}/reglas"),
        ("put", "/api/v1/precios/listas/{lista_id}/reglas/{regla_id}"),
        ("put", "/api/v1/precios/listas/{lista_id}/redondeos-categoria/{categoria_id}"),
        ("post", "/api/v1/precios/listas/{lista_id}/borrador"),
        ("get", "/api/v1/precios/listas/{lista_id}/borrador"),
        ("put", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/precios/{producto_id}"),
        ("post", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/publicar"),
        ("post", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/anular"),
        ("get", "/api/v1/precios/listas/{lista_id}/versiones"),
        ("get", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/precios"),
        ("get", "/api/v1/precios/listas/{lista_id}/vigente"),
        ("put", "/api/v1/precios/lista-predeterminada"),
        ("get", "/api/v1/precios/lista-predeterminada"),
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


def test_la_recorrida_de_aislamiento_alcanza_la_consulta_de_la_sesion(
    database_url: str,
) -> None:
    """Tarea 9.2: esta verificación RECORRE la ruta nueva, no la omite.

    `test_ninguna_ruta_de_negocio_declara_organizacion_id_como_parametro_o_campo`
    itera `COBERTURA_DE_AISLAMIENTO` e indexa el esquema real, así que si
    `("get", "/api/v1/yo")` no estuviera en esa lista, su inclusión sería
    silenciosa: la prueba seguiría en verde sin haber mirado la ruta nueva.
    Por eso se afirma acá, contra el esquema REAL, que la operación existe y
    que además no declara `organizacion_id` (ni como parámetro ni en el
    cuerpo) -- de modo que una tupla agregada a una ruta que no exista, o a
    una que sí la declare, falle en vez de pasar por vacuidad.

    Regla: `02` §8, INV-21, SEG-07, ADR-027."""
    os.environ.setdefault("DATABASE_URL", database_url)
    esquema = _esquema_real()
    rutas = esquema["paths"]  # type: ignore[index]
    componentes = esquema.get("components", {})  # type: ignore[assignment]

    ruta = ("get", "/api/v1/yo")
    assert ruta in COBERTURA_DE_AISLAMIENTO, (
        "La consulta de la sesión tiene que estar en COBERTURA_DE_AISLAMIENTO "
        "para que esta verificación la recorra (tarea 9.2)."
    )
    metodo, path = ruta
    assert path in rutas and metodo in rutas[path], (  # type: ignore[operator]
        f"La ruta {ruta} está declarada como cubierta pero no está registrada "
        "en el esquema OpenAPI."
    )

    operacion = rutas[path][metodo]  # type: ignore[index]
    parametros = _nombres_de_parametros(operacion)
    assert _NOMBRE_PROHIBIDO not in parametros
    assert _NOMBRE_PROHIBIDO not in _propiedades_del_cuerpo(operacion, componentes)
    # `/yo` no declara ningún parámetro propio (D1-A, "Parámetros: Ninguno"):
    # lo único que OpenAPI muestra es el esquema de seguridad
    # `HTTPBearer`, que FastAPI agrega a toda operación autenticada. Ni
    # `organizacion_id` ni `usuario_id` -- si alguna vez aparecieran, esta
    # aserción los delata en el mismo lugar.
    assert parametros == {"authorization"}
    assert "usuario_id" not in parametros
    # Y tampoco declara cuerpo: no hay nada que informar.
    assert _propiedades_del_cuerpo(operacion, componentes) == set()


def test_la_recorrida_de_aislamiento_alcanza_las_rutas_nuevas_de_pagos(
    database_url: str,
) -> None:
    """Change 12, tarea 7.1: la recorrido anterior itera `COBERTURA_DE_AISLAMIENTO` e
    indexa el esquema real, así que una tupla agregada a una ruta que no exista -- o a una
    que sí declare `organizacion_id` -- tiene que fallar, no pasar por vacuidad.

    Se afirma contra el esquema REAL, para las cuatro rutas nuevas del change: que están
    en la lista (si no, la recorrido las omitiría en silencio), que están registradas, y
    que ni sus parámetros ni su cuerpo declaran `organizacion_id`. En las tres lecturas no
    hay ningún campo de cuerpo; en la anulación, el cuerpo es solo `motivo_id`.

    Regla: `02` §8, INV-21, TR-08."""
    os.environ.setdefault("DATABASE_URL", database_url)
    esquema = _esquema_real()
    rutas = esquema["paths"]  # type: ignore[index]
    componentes = esquema.get("components", {})  # type: ignore[assignment]

    nuevas = [
        ("get", "/api/v1/proveedores/{proveedor_id}/saldo"),
        ("get", "/api/v1/pagos-proveedores"),
        ("get", "/api/v1/pagos-proveedores/{pago_id}"),
        ("post", "/api/v1/pagos-proveedores/{pago_id}/anulacion"),
    ]
    for ruta in nuevas:
        assert ruta in COBERTURA_DE_AISLAMIENTO, (
            f"La ruta {ruta} tiene que estar en COBERTURA_DE_AISLAMIENTO para que la "
            "recorrida de esta prueba la recorra (tarea 7.1)."
        )
        metodo, path = ruta
        assert path in rutas and metodo in rutas[path], (  # type: ignore[operator]
            f"La ruta {ruta} está declarada como cubierta pero no está registrada "
            "en el esquema OpenAPI."
        )
        operacion = rutas[path][metodo]  # type: ignore[index]
        assert _NOMBRE_PROHIBIDO not in _nombres_de_parametros(operacion)
        assert _NOMBRE_PROHIBIDO not in _propiedades_del_cuerpo(operacion, componentes)

    # La anulación no admite nada más que el motivo: ni la organización ni el estado
    # (INV-05/TR-06, la anulación no edita el pago más allá de su estado).
    anulacion = rutas["/api/v1/pagos-proveedores/{pago_id}/anulacion"]["post"]  # type: ignore[index]
    assert _propiedades_del_cuerpo(anulacion, componentes) == {"motivo_id"}


def test_toda_ruta_de_precios_esta_recorrida_y_no_declara_organizacion_id(
    database_url: str,
) -> None:
    """Change 13, tarea 11.1: cada ruta registrada bajo `/api/v1/precios` esta en
    `COBERTURA_DE_AISLAMIENTO` (la recorrida las alcanza) y ninguna declara `organizacion_id`
    ni como parametro ni como campo del cuerpo: la organizacion sale siempre del token."""
    os.environ.setdefault("DATABASE_URL", database_url)
    esquema = _esquema_real()
    rutas = esquema["paths"]  # type: ignore[index]
    componentes = esquema.get("components", {})  # type: ignore[assignment]

    registradas = {
        (metodo, path)
        for path, operaciones in rutas.items()  # type: ignore[union-attr]
        if path.startswith("/api/v1/precios")
        for metodo in operaciones  # type: ignore[union-attr]
    }
    for ruta in registradas:
        assert ruta in COBERTURA_DE_AISLAMIENTO, (
            f"La ruta {ruta} de `precios` tiene que estar en COBERTURA_DE_AISLAMIENTO."
        )
        metodo, path = ruta
        operacion = rutas[path][metodo]  # type: ignore[index]
        assert _NOMBRE_PROHIBIDO not in _nombres_de_parametros(operacion), ruta
        assert _NOMBRE_PROHIBIDO not in _propiedades_del_cuerpo(operacion, componentes), ruta
    assert len(registradas) == 19, "las diecinueve rutas de `precios` (change 13)"


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
