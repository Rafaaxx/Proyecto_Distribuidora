"""INV-21 (`docs/01-dominio.md` §20; `design.md` D1 del change 02): ratchet
de rutas.

Recorre dinámicamente las rutas registradas de FastAPI (`app.openapi()["paths"]`,
que refleja el path completo con prefijo, a diferencia de `app.routes` cuyas
rutas anidadas no exponen el path resuelto en esta versión de FastAPI) y
falla nombrando ruta y método si aparece una ruta de negocio que no está en
`COBERTURA_DE_AISLAMIENTO`.

Tarea 12.1 (change 03) cierra lo que el change 02 dejó parcial (`design.md`
D1 de ese change: "hoy la prueba de rutas pasa sin ejercitar nada de
negocio... el change 03 no puede agregar su primer endpoint sin que la
suite se ponga roja hasta cubrirlo"): las rutas de negocio del grupo 10.7
(usuarios, roles, PIN, dispositivos, desbloqueo) ya están declaradas en
`COBERTURA_DE_AISLAMIENTO`, cada una con su prueba real en
`test_identidad_api_usuarios.py` / `test_inv21_aislamiento_endpoints_identidad.py`
(HTTP, con `login` real de un usuario de otra organización, nunca un JWT
fabricado a mano con `emitir_access_token`). Las rutas de `/auth` quedan
exentas en `RUTAS_DE_AUTENTICACION`, separadas de `RUTAS_DE_SISTEMA`,
porque operan sin organización en contexto (spec `aislamiento-multiorganizacion`,
escenario "Las rutas de autenticación quedan exentas por operar sin
organización en contexto").

CÓMO DECLARAR UNA RUTA NUEVA (tarea 9.2/12.1, para los changes siguientes):
cuando un módulo agrega una ruta de negocio, agregar la tupla
`(metodo, "/api/v1/<ruta>")` a `COBERTURA_DE_AISLAMIENTO` en este archivo,
junto con la prueba de integración que demuestra su aislamiento real:
- dos organizaciones, cada una con su propio usuario autenticado por
  `POST /api/v1/auth/login` (login real, NUNCA un access token fabricado a
  mano con `emitir_access_token`, porque eso no prueba que el flujo de
  autenticación real produzca un contexto correcto);
- el usuario de la organización B ejerce la ruta sobre un recurso de la
  organización A (o, para una ruta de alta, con una referencia -- p. ej.
  `rol_id` -- que pertenece a la organización A);
- la respuesta indica "no encontrado", nunca un error de infraestructura ni
  un 200/201/204 que hubiera modificado o expuesto el recurso ajeno.
Sin esa prueba, no agregar la tupla: agregarla sin probar el aislamiento
real es exactamente la falsa sensación de cobertura que este ratchet existe
para evitar.
"""

from __future__ import annotations

import os

from app.core.config import Settings
from app.main import crear_app

# Listas enumerables y explícitas (`design.md` D1 del change 02): nunca un
# patrón de nombre. Separadas porque representan dos motivos de exención
# distintos: sistema (sin negocio en absoluto) vs. autenticación (negocio de
# identidad, pero sin organización todavía en contexto -- tarea 12.1).
RUTAS_DE_SISTEMA = frozenset(
    {
        ("get", "/api/v1/salud"),
        ("get", "/api/v1/version"),
    }
)

RUTAS_DE_AUTENTICACION = frozenset(
    {
        ("post", "/api/v1/auth/login"),
        ("post", "/api/v1/auth/refresh"),
        ("post", "/api/v1/auth/logout"),
    }
)

# Ver "CÓMO DECLARAR UNA RUTA NUEVA" arriba. Las siete rutas de negocio del
# grupo 10.7, cada una con su prueba de aislamiento real (login real, dos
# organizaciones, "no encontrado" sobre el recurso ajeno):
# - `test_identidad_api_usuarios.py`: composición de rol, rotación de PIN,
#   desbloqueo manual.
# - `test_inv21_aislamiento_endpoints_identidad.py`: listado y revocación de
#   dispositivos, listado y alta de usuarios (incluida el alta con un
#   `rol_id` de otra organización).
COBERTURA_DE_AISLAMIENTO: frozenset[tuple[str, str]] = frozenset(
    {
        ("get", "/api/v1/identidad/dispositivos"),
        ("delete", "/api/v1/identidad/dispositivos/{dispositivo_id}"),
        ("get", "/api/v1/identidad/usuarios"),
        ("post", "/api/v1/identidad/usuarios"),
        ("put", "/api/v1/identidad/roles/{rol_id}/permisos"),
        ("post", "/api/v1/identidad/usuarios/{usuario_id}/pin"),
        ("post", "/api/v1/identidad/usuarios/{usuario_id}/desbloqueo"),
        # Change 04, grupo 8 (`sync/api.py`, tarea 8.6): a diferencia de las
        # rutas de arriba, `POST /sync/comandos` no tiene un "recurso ajeno"
        # por id -- `organizacion_id`/`usuario_id`/`dispositivo_id` salen
        # siempre del token (nunca del cuerpo, `sobre.py`), así que no hay
        # forma de pedir la cola de otra organización con esta ruta: el
        # aislamiento es estructural, no una verificación en tiempo de
        # ejecución sobre un id ajeno. Su prueba real de aislamiento no
        # sigue el patrón de "recurso de otra organización -> 404" de las
        # rutas de arriba, sino el de "cola ajena -> rechazada" (mismo
        # principio, SEG-02/SEG-07): `test_bus_lote_sincronizacion.py::
        # TestPropiedadDeLaCola` (otro usuario, otro dispositivo, sin
        # sesión) y `test_cuarentena_comandos.py::
        # test_la_cuarentena_de_otra_organizacion_no_es_alcanzable`
        # (tarea 8.9, aislamiento de `comando_cuarentena` entre
        # organizaciones).
        ("post", "/api/v1/sync/comandos"),
        # Change 05, grupo 9 (`catalogo/api.py`, tarea 9.1/9.2), cobertura
        # de tarea 11.1: las trece rutas nuevas, cada una con su prueba de
        # aislamiento real -- incluida la referencia ajena EN EL CONTENIDO
        # (categoría/marca/alícuota de otra organización), no solo el id
        # de la ruta -- en `test_inv21_aislamiento_endpoints_catalogo.py`.
        ("post", "/api/v1/catalogo/categorias"),
        ("get", "/api/v1/catalogo/categorias"),
        ("put", "/api/v1/catalogo/categorias/{categoria_id}"),
        ("post", "/api/v1/catalogo/marcas"),
        ("get", "/api/v1/catalogo/marcas"),
        ("put", "/api/v1/catalogo/marcas/{marca_id}"),
        ("post", "/api/v1/catalogo/productos"),
        ("get", "/api/v1/catalogo/productos"),
        ("put", "/api/v1/catalogo/productos/{producto_id}"),
        ("get", "/api/v1/catalogo/productos/{producto_id}"),
        ("post", "/api/v1/catalogo/productos/{producto_id}/presentaciones"),
        ("put", "/api/v1/catalogo/presentaciones/{presentacion_id}"),
        ("put", "/api/v1/catalogo/productos/{producto_id}/referencia"),
        # Change 05, grupo 9/11 (tarea 9.6/11.5, D12): la ruta de solo
        # lectura de `configuracion/api.py` -- cada organización lista solo
        # sus propias alícuotas, `test_configuracion_api.py::
        # TestAislamientoInv21`.
        ("get", "/api/v1/configuracion/alicuotas"),
        # Change 06, grupo 10/12 (`proveedores/api.py`, tarea 10.2),
        # cobertura de tarea 12.1: las ocho rutas nuevas, cada una con su
        # prueba de aislamiento real -- incluida la referencia ajena EN EL
        # CONTENIDO de `COSTO_INFORMAR` (`proveedor_id`, `producto_id`,
        # `presentacion_id` de otra organización) -- en
        # `test_inv21_aislamiento_endpoints_proveedores.py`. La misma
        # prueba cubre además `proveedor_id` ajeno en `PRODUCTO_CREAR`/
        # `PRODUCTO_MODIFICAR` v2 (`catalogo/api.py`, ya cubiertas arriba,
        # caso que las pruebas de la tarea 11.1 del change 05 no llegaban a
        # ejercitar porque `proveedor_id` no existía en el contrato).
        ("post", "/api/v1/proveedores"),
        ("get", "/api/v1/proveedores"),
        ("get", "/api/v1/proveedores/opciones"),
        ("get", "/api/v1/proveedores/{proveedor_id}"),
        ("put", "/api/v1/proveedores/{proveedor_id}"),
        ("post", "/api/v1/costos"),
        ("get", "/api/v1/costos/productos/{producto_id}/vigente"),
        ("get", "/api/v1/costos/productos/{producto_id}/historial"),
        # Change 06b, grupo 9, tarea 9.1 (`identidad/api.py::router_yo`,
        # ADR-027), con la prueba real en
        # `test_inv21_aislamiento_endpoints_identidad.py::TestAislamientoDeLaSesion`.
        # La 4.6 dejó esta ruta sin cobertura A PROPÓSITO (mismo precedente
        # que la 12.1 del change 02): el ratchet quedó en rojo nombrando
        # `[('get', '/api/v1/yo')]` desde que la ruta se registró hasta que
        # sus dos pruebas de aislamiento existen. Como `/yo` no recibe ningún
        # identificador (todo sale del token, D1-A), su aislamiento no sigue
        # el patrón "recurso de otra organización -> 404" de las rutas de
        # arriba, sino el inverso: dos organizaciones con login real, y el
        # usuario de B obtiene solo su usuario, su organización y su rol
        # (ningún id, nombre ni permiso de A), tanto si informa los
        # identificadores de A en la consulta y en encabezados como si no.
        ("get", "/api/v1/yo"),
    }
)


def rutas_de_negocio_sin_cobertura(
    rutas_del_esquema: dict[str, dict[str, object]],
    *,
    rutas_exentas: frozenset[tuple[str, str]],
    cobertura: frozenset[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Devuelve las rutas `(metodo, path)` que son de negocio (no están en
    `rutas_exentas`) y no están cubiertas por `cobertura`."""
    todas = [(metodo, path) for path, metodos in rutas_del_esquema.items() for metodo in metodos]
    de_negocio = [ruta for ruta in todas if ruta not in rutas_exentas]
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
    rutas_exentas = RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        rutas, rutas_exentas=rutas_exentas, cobertura=COBERTURA_DE_AISLAMIENTO
    )

    total_de_negocio = len(
        [
            (metodo, path)
            for path, metodos in rutas.items()
            for metodo in metodos
            if (metodo, path) not in rutas_exentas
        ]
    )
    mensaje = (
        f"INV-21: {len(sin_cobertura)} ruta(s) de negocio sin cobertura de "
        f"aislamiento: {sin_cobertura}. Rutas de negocio cubiertas hoy: "
        f"{total_de_negocio - len(sin_cobertura)} de {total_de_negocio}."
    )
    assert sin_cobertura == [], mensaje


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


def test_inv21_las_rutas_de_autenticacion_quedan_exentas_por_operar_sin_organizacion(
    database_url: str,
) -> None:
    """Escenario 'Las rutas de autenticación quedan exentas por operar sin
    organización en contexto' (tarea 12.1, spec `aislamiento-multiorganizacion`):
    `/auth/login`, `/auth/refresh` y `/auth/logout` están registradas, y
    quedan fuera de la exigencia de `COBERTURA_DE_AISLAMIENTO` por estar
    declaradas explícitamente en `RUTAS_DE_AUTENTICACION` -- una lista
    separada de `RUTAS_DE_SISTEMA`, porque el motivo de la exención es
    distinto (sin organización en contexto todavía, no "sin negocio")."""
    os.environ.setdefault("DATABASE_URL", database_url)
    rutas = _rutas_reales_del_esquema()

    rutas_presentes = {(metodo, path) for path, metodos in rutas.items() for metodo in metodos}
    for ruta_auth in RUTAS_DE_AUTENTICACION:
        assert ruta_auth in rutas_presentes, (
            f"Ruta de autenticación {ruta_auth} esperada pero no está registrada."
        )

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        rutas,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
        cobertura=COBERTURA_DE_AISLAMIENTO,
    )
    for ruta_auth in RUTAS_DE_AUTENTICACION:
        assert ruta_auth not in sin_cobertura, (
            f"{ruta_auth} no debería exigir cobertura de aislamiento: opera "
            "sin organización en contexto (tarea 12.1)."
        )


def test_inv21_una_ruta_de_autenticacion_no_declarada_no_queda_exenta_por_prefijo(
    database_url: str,
) -> None:
    """Verificación en negativo (tarea 12.1, mismo criterio que la de
    sistema/tarea 9.3): la exención de `/auth` es una lista enumerable, no
    un patrón de prefijo -- una ruta de negocio nueva bajo `/auth` que no
    esté declarada en `RUTAS_DE_AUTENTICACION` sigue exigiendo cobertura."""
    esquema_con_ruta_ficticia = {
        "/api/v1/salud": {"get": {}},
        "/api/v1/auth/login": {"post": {}},
        "/api/v1/auth/impersonar": {"post": {}},  # ruta de negocio ficticia bajo /auth
    }

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        esquema_con_ruta_ficticia,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
        cobertura=COBERTURA_DE_AISLAMIENTO,
    )

    assert sin_cobertura == [("post", "/api/v1/auth/impersonar")]


def test_inv21_detecta_una_ruta_de_negocio_ficticia_sin_cobertura() -> None:
    """Verificación en negativo (tarea 9.3, extendida en 12.6): una ruta de
    negocio no registrada en `COBERTURA_DE_AISLAMIENTO` debe ser detectada y
    nombrada -- el ratchet falla si se agrega a propósito una ruta de
    negocio sin declarar su cobertura de aislamiento."""
    esquema_con_ruta_ficticia = {
        "/api/v1/salud": {"get": {}},
        "/api/v1/version": {"get": {}},
        "/api/v1/venta": {"post": {}},  # ruta de negocio ficticia, sin cobertura
    }

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        esquema_con_ruta_ficticia,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
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
        esquema,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
        cobertura=cobertura_de_prueba,
    )

    assert sin_cobertura == []
