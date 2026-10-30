# ruff: noqa: F811
"""Change 20b, tarea 8.4 (`design.md` D16): las lecturas de usuarios y roles que necesitan las
pantallas.

- `GET /identidad/roles` suma la cantidad de usuarios con tope propio.
- `GET /identidad/usuarios` suma `rol_nombre`, `rol_activo`, `tope_descuento_override` (string) y
  el filtro por estado.
- `GET /identidad/usuarios/{id}` (404 entre organizaciones).

Nunca `password_hash` ni el PIN. Reglas citadas: ADR-011, INV-03, INV-21, SEG-06, SEG-07.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from usuarios_utiles import (
    URL_USUARIOS,
    EntornoUsuarios,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

URL_ROLES = "/api/v1/identidad/roles"
VENDER = frozenset({"VENDER"})
CAMPOS_PROHIBIDOS = {
    "password_hash",
    "pin_autorizacion_hash",
    "pin_autorizacion_sal",
    "pin_autorizacion_iteraciones",
}


def _definir_tope_propio(entorno: EntornoUsuarios, usuario_id: UUID, valor: str) -> None:
    entorno.sesion.execute(
        text("UPDATE usuario SET tope_descuento_override = :t WHERE id = :u"),
        {"t": valor, "u": usuario_id},
    )
    entorno.sesion.commit()


def _get(entorno: EntornoUsuarios, cliente: TestClient, quien, ruta: str):  # type: ignore[no-untyped-def]
    return entorno.enviar(cliente, "GET", ruta, quien)


# --- GET /identidad/roles ----------------------------------------------------------------------


def test_los_roles_informan_cuantos_usuarios_tienen_tope_propio(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", VENDER)
    sin_rol_con_tope = entorno.crear_rol("Supervisor", VENDER)
    uno, _ = entorno.crear_usuario(rol)
    dos, _ = entorno.crear_usuario(rol)
    entorno.crear_usuario(rol)
    _definir_tope_propio(entorno, uno, "0.100000")
    _definir_tope_propio(entorno, dos, "0.000000")

    respuesta = _get(entorno, cliente_http, administrador, URL_ROLES)

    assert respuesta.status_code == 200, respuesta.text
    por_id = {fila["id"]: fila for fila in respuesta.json()}
    assert por_id[str(rol.id)]["usuarios_con_tope_propio"] == 2
    assert por_id[str(sin_rol_con_tope.id)]["usuarios_con_tope_propio"] == 0
    assert por_id[str(entorno.administradores.id)]["usuarios_con_tope_propio"] == 0


def test_los_roles_no_cuentan_topes_propios_de_otra_organizacion(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    rol = propia.crear_rol("Vendedor", VENDER)
    rol_ajeno = ajena.crear_rol("Vendedor", VENDER)
    ajeno_id, _ = ajena.crear_usuario(rol_ajeno)
    _definir_tope_propio(ajena, ajeno_id, "0.200000")

    respuesta = _get(propia, cliente_http, administrador, URL_ROLES)

    ids = {fila["id"] for fila in respuesta.json()}
    assert str(rol_ajeno.id) not in ids
    assert {fila["id"]: fila for fila in respuesta.json()}[str(rol.id)][
        "usuarios_con_tope_propio"
    ] == 0


def test_los_roles_separan_los_topes_propios_de_usuarios_activos_e_inactivos(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """Tarea 8.6: el tope se conserva en la baja (D2), asi que el rol informa cuantos topes
    propios estan en usuarios activos y cuantos en inactivos; el total sigue en
    `usuarios_con_tope_propio`."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", VENDER)
    otro = entorno.crear_rol("Supervisor", VENDER)
    activo_a, _ = entorno.crear_usuario(rol)
    activo_b, _ = entorno.crear_usuario(rol)
    inactivo, _ = entorno.crear_usuario(rol, estado="INACTIVO")
    solo_inactivo, _ = entorno.crear_usuario(otro, estado="INACTIVO")
    entorno.crear_usuario(rol)
    for usuario_id in (activo_a, activo_b, inactivo, solo_inactivo):
        _definir_tope_propio(entorno, usuario_id, "0.100000")

    respuesta = _get(entorno, cliente_http, administrador, URL_ROLES)

    assert respuesta.status_code == 200, respuesta.text
    por_id = {fila["id"]: fila for fila in respuesta.json()}
    vendedor = por_id[str(rol.id)]
    assert vendedor["usuarios_con_tope_propio"] == 3
    assert vendedor["usuarios_con_tope_propio_activos"] == 2
    assert vendedor["usuarios_con_tope_propio_inactivos"] == 1
    supervisor = por_id[str(otro.id)]
    assert supervisor["usuarios_con_tope_propio"] == 1
    assert supervisor["usuarios_con_tope_propio_activos"] == 0
    assert supervisor["usuarios_con_tope_propio_inactivos"] == 1
    base = por_id[str(entorno.administradores.id)]
    assert base["usuarios_con_tope_propio_activos"] == 0
    assert base["usuarios_con_tope_propio_inactivos"] == 0


# --- GET /identidad/usuarios -------------------------------------------------------------------


def test_el_listado_de_usuarios_suma_rol_y_tope_propio_y_nunca_los_secretos(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-011, INV-03: el tope propio viaja como string con seis decimales."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol_de_baja = entorno.crear_rol("Viejo", VENDER, activo=False)
    con_tope, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDER), con_pin=True)
    sin_tope, _ = entorno.crear_usuario(rol_de_baja, estado="INACTIVO")
    _definir_tope_propio(entorno, con_tope, "0.100000")

    respuesta = _get(entorno, cliente_http, administrador, URL_USUARIOS)

    assert respuesta.status_code == 200, respuesta.text
    por_id = {fila["id"]: fila for fila in respuesta.json()}
    uno = por_id[str(con_tope)]
    assert uno["rol_nombre"] == "Vendedor"
    assert uno["rol_activo"] is True
    assert uno["tope_descuento_override"] == "0.100000"
    assert uno["tiene_pin_autorizacion"] is True
    otro = por_id[str(sin_tope)]
    assert otro["rol_nombre"] == "Viejo"
    assert otro["rol_activo"] is False
    assert otro["tope_descuento_override"] is None
    for fila in respuesta.json():
        assert CAMPOS_PROHIBIDOS.isdisjoint(fila)


@pytest.mark.parametrize(("estado", "esperados"), [("ACTIVO", 3), ("INACTIVO", 1)])
def test_el_listado_filtra_por_estado(
    cliente_http: TestClient, sesion_real: Session, estado: str, esperados: int
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", VENDER)
    # Activos: el usuario base del entorno, el administrador y este; inactivo: uno.
    entorno.crear_usuario(rol)
    entorno.crear_usuario(rol, estado="INACTIVO")

    respuesta = _get(entorno, cliente_http, administrador, f"{URL_USUARIOS}?estado={estado}")

    assert respuesta.status_code == 200, respuesta.text
    filas = respuesta.json()
    assert len(filas) == esperados
    assert {fila["estado"] for fila in filas} == {estado}


def test_un_estado_desconocido_responde_422(cliente_http: TestClient, sesion_real: Session) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)

    respuesta = _get(entorno, cliente_http, administrador, f"{URL_USUARIOS}?estado=BORRADO")

    assert respuesta.status_code == 422


def test_el_listado_no_incluye_usuarios_de_otra_organizacion(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    ajeno_id, _ = ajena.crear_usuario(ajena.crear_rol("Vendedor", VENDER))

    respuesta = _get(propia, cliente_http, administrador, URL_USUARIOS)

    assert str(ajeno_id) not in {fila["id"] for fila in respuesta.json()}


# --- GET /identidad/usuarios/{id} --------------------------------------------------------------


def test_el_detalle_de_un_usuario_trae_rol_y_tope_propio_sin_secretos(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, nombre = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDER), con_pin=True)
    _definir_tope_propio(entorno, usuario_id, "0.050000")

    respuesta = _get(entorno, cliente_http, administrador, f"{URL_USUARIOS}/{usuario_id}")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id"] == str(usuario_id)
    assert cuerpo["usuario"] == nombre
    assert cuerpo["estado"] == "ACTIVO"
    assert cuerpo["rol_nombre"] == "Vendedor"
    assert cuerpo["rol_activo"] is True
    assert cuerpo["tope_descuento_override"] == "0.050000"
    assert cuerpo["tiene_pin_autorizacion"] is True
    assert CAMPOS_PROHIBIDOS.isdisjoint(cuerpo)


def test_el_detalle_de_un_usuario_de_otra_organizacion_o_inexistente_responde_404(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21, SEG-07."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    ajeno_id, _ = ajena.crear_usuario(ajena.crear_rol("Vendedor", VENDER))

    de_otra = _get(propia, cliente_http, administrador, f"{URL_USUARIOS}/{ajeno_id}")
    inexistente = _get(propia, cliente_http, administrador, f"{URL_USUARIOS}/{uuid4()}")

    assert de_otra.status_code == inexistente.status_code == 404


def test_las_lecturas_sin_el_permiso_responden_403(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """SEG-06."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDER))
    sin_permiso = entorno.abrir_sesion(cliente_http, usuario_id, nombre)

    listado = _get(entorno, cliente_http, sin_permiso, URL_USUARIOS)
    detalle = _get(entorno, cliente_http, sin_permiso, f"{URL_USUARIOS}/{usuario_id}")

    assert listado.status_code == detalle.status_code == 403


# --- filtros rol_id y con_tope_propio (tarea 8.6) ----------------------------------------------


def _ids(respuesta) -> set[str]:  # type: ignore[no-untyped-def]
    assert respuesta.status_code == 200, respuesta.text
    return {fila["id"] for fila in respuesta.json()}


def test_el_listado_filtra_por_rol_y_por_tope_propio_combinables_con_estado(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", VENDER)
    otro = entorno.crear_rol("Supervisor", VENDER)
    activo_con, _ = entorno.crear_usuario(rol)
    activo_sin, _ = entorno.crear_usuario(rol)
    inactivo_con, _ = entorno.crear_usuario(rol, estado="INACTIVO")
    de_otro_rol_con, _ = entorno.crear_usuario(otro)
    _definir_tope_propio(entorno, activo_con, "0.100000")
    _definir_tope_propio(entorno, inactivo_con, "0.000000")
    _definir_tope_propio(entorno, de_otro_rol_con, "0.200000")
    url = URL_USUARIOS

    por_rol = _ids(_get(entorno, cliente_http, administrador, f"{url}?rol_id={rol.id}"))
    assert por_rol == {str(activo_con), str(activo_sin), str(inactivo_con)}

    con_tope = _ids(_get(entorno, cliente_http, administrador, f"{url}?con_tope_propio=true"))
    assert con_tope == {str(activo_con), str(inactivo_con), str(de_otro_rol_con)}

    sin_tope = _ids(
        _get(entorno, cliente_http, administrador, f"{url}?rol_id={rol.id}&con_tope_propio=false")
    )
    assert sin_tope == {str(activo_sin)}

    rol_y_tope = _ids(
        _get(entorno, cliente_http, administrador, f"{url}?rol_id={rol.id}&con_tope_propio=true")
    )
    assert rol_y_tope == {str(activo_con), str(inactivo_con)}

    solo_inactivos = _ids(
        _get(
            entorno,
            cliente_http,
            administrador,
            f"{url}?rol_id={rol.id}&con_tope_propio=true&estado=INACTIVO",
        )
    )
    assert solo_inactivos == {str(inactivo_con)}

    solo_activos = _ids(
        _get(
            entorno,
            cliente_http,
            administrador,
            f"{url}?rol_id={rol.id}&con_tope_propio=true&estado=ACTIVO",
        )
    )
    assert solo_activos == {str(activo_con)}


def test_el_filtro_por_rol_ajeno_o_inexistente_no_filtra_nada_ni_filtra_datos(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21: un `rol_id` de otra organizacion devuelve lista vacia, igual que uno inexistente,
    y nunca usuarios de la otra organizacion."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    rol_ajeno = ajena.crear_rol("Vendedor", VENDER)
    ajeno_id, _ = ajena.crear_usuario(rol_ajeno)
    _definir_tope_propio(ajena, ajeno_id, "0.300000")

    de_otra = _get(propia, cliente_http, administrador, f"{URL_USUARIOS}?rol_id={rol_ajeno.id}")
    inexistente = _get(propia, cliente_http, administrador, f"{URL_USUARIOS}?rol_id={uuid4()}")
    con_tope = _get(propia, cliente_http, administrador, f"{URL_USUARIOS}?con_tope_propio=true")

    assert de_otra.status_code == inexistente.status_code == 200
    assert de_otra.json() == inexistente.json() == []
    assert str(ajeno_id) not in {fila["id"] for fila in con_tope.json()}


def test_los_filtros_nuevos_con_valor_invalido_responden_422(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)

    mal_rol = _get(entorno, cliente_http, administrador, f"{URL_USUARIOS}?rol_id=no-es-uuid")
    mal_tope = _get(entorno, cliente_http, administrador, f"{URL_USUARIOS}?con_tope_propio=quizas")

    assert mal_rol.status_code == mal_tope.status_code == 422
