# ruff: noqa: F811
"""Change 20b, tarea 4.2: `USUARIO_ROL_CAMBIAR` v1, `PUT /api/v1/identidad/usuarios/{id}/rol`
(spec `identidad/administracion-de-usuarios`).

El cambio rige en la petición siguiente (los permisos se leen en cada petición, ADR-017), no
revoca sesiones, borra el PIN si el rol nuevo no autoriza excepciones (ADR-011) y nunca deja a la
organización sin un administrador (ADR-053).

Reglas citadas: ADR-053, ADR-017, ADR-011, ADR-028 D9.4, INV-01, INV-06, INV-21.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from usuarios_utiles import (
    ADMIN,
    URL_USUARIOS,
    EntornoUsuarios,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

VENDEDOR = frozenset({"VENDER"})
SUPERVISOR = frozenset({"VENDER", "AUTORIZAR_DESCUENTO", "GESTIONAR_DISPOSITIVOS"})


def _cambiar(entorno, cliente, quien, usuario_id, rol_id, operation_id=None):  # type: ignore[no-untyped-def]
    return entorno.enviar(
        cliente,
        "PUT",
        f"{URL_USUARIOS}/{usuario_id}/rol",
        quien,
        {"rol_id": str(rol_id)},
        operation_id=operation_id,
    )


def test_el_cambio_a_un_rol_con_menos_permisos_rige_en_la_peticion_siguiente(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-017: rige sin cerrar la sesión; ADR-011: el PIN se borra si el rol nuevo no autoriza;
    ADR-028 D9.4."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    supervisor = entorno.crear_rol("Supervisor", SUPERVISOR)
    vendedor = entorno.crear_rol("Vendedor", VENDEDOR)
    usuario_id, nombre = entorno.crear_usuario(supervisor, con_pin=True)
    sesion_del_usuario = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    assert (
        cliente_http.get("/api/v1/identidad/dispositivos", headers=sesion_del_usuario.headers)
    ).status_code == 200
    operation_id = uuid4()

    respuesta = _cambiar(
        entorno, cliente_http, administrador, usuario_id, vendedor.id, operation_id
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["rol_id"] == str(vendedor.id)
    assert entorno.usuario(usuario_id)["rol_id"] == vendedor.id
    # La siguiente petición ya tiene los permisos nuevos; la sesión sigue viva.
    sin_permiso = cliente_http.get(
        "/api/v1/identidad/dispositivos", headers=sesion_del_usuario.headers
    )
    assert sin_permiso.status_code == 403
    assert cliente_http.get("/api/v1/yo", headers=sesion_del_usuario.headers).status_code == 200
    assert entorno.familias_vigentes(usuario_id) == {sesion_del_usuario.dispositivo_id}
    assert entorno.renovar(cliente_http, sesion_del_usuario).status_code == 200
    assert entorno.usuario(usuario_id)["pin_autorizacion_hash"] is None
    (auditoria,) = entorno.auditorias("CAMBIO_ROL_USUARIO", entidad_id=usuario_id)
    assert auditoria["origen"] == "COMANDO"
    assert auditoria["operation_id"] == operation_id
    assert auditoria["antes"] == {"rol_id": str(supervisor.id), "rol_nombre": "Supervisor"}
    assert auditoria["despues"] == {"rol_id": str(vendedor.id), "rol_nombre": "Vendedor"}
    (pin,) = entorno.auditorias("INVALIDAR_PIN_AUTORIZACION", entidad_id=usuario_id)
    assert pin["operation_id"] == operation_id


def test_si_el_rol_nuevo_conserva_la_autorizacion_el_pin_sigue(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """Triangulación de ADR-011: un solo permiso de autorización alcanza para conservar el PIN."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    supervisor = entorno.crear_rol("Supervisor", SUPERVISOR)
    otro_supervisor = entorno.crear_rol("Supervisor de crédito", frozenset({"SUPERAR_CREDITO"}))
    usuario_id, _ = entorno.crear_usuario(supervisor, con_pin=True)

    respuesta = _cambiar(entorno, cliente_http, administrador, usuario_id, otro_supervisor.id)

    assert respuesta.status_code == 200, respuesta.text
    assert entorno.usuario(usuario_id)["pin_autorizacion_hash"] is not None
    assert entorno.auditorias("INVALIDAR_PIN_AUTORIZACION") == []


def test_un_rol_de_baja_responde_409_y_no_cambia_nada(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    vendedor = entorno.crear_rol("Vendedor", VENDEDOR)
    de_baja = entorno.crear_rol("Viejo", VENDEDOR, activo=False)
    usuario_id, _ = entorno.crear_usuario(vendedor)

    respuesta = _cambiar(entorno, cliente_http, administrador, usuario_id, de_baja.id)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "IDENTIDAD_ROL_INACTIVO"
    assert entorno.usuario(usuario_id)["rol_id"] == vendedor.id
    assert entorno.auditorias("CAMBIO_ROL_USUARIO") == []


def test_un_rol_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21: la clave foránea compuesta no truena como error de infraestructura."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    vendedor = propia.crear_rol("Vendedor", VENDEDOR)
    usuario_id, _ = propia.crear_usuario(vendedor)
    rol_ajeno = ajena.crear_rol("Vendedor ajeno", VENDEDOR)

    respuesta = _cambiar(propia, cliente_http, administrador, usuario_id, rol_ajeno.id)

    assert respuesta.status_code == 404
    assert propia.usuario(usuario_id)["rol_id"] == vendedor.id


def test_un_usuario_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    ajeno_id, _ = ajena.crear_usuario(ajena.crear_rol("Vendedor", VENDEDOR))
    mi_rol = propia.crear_rol("Gerencia", VENDEDOR)

    respuesta = _cambiar(propia, cliente_http, administrador, ajeno_id, mi_rol.id)

    assert respuesta.status_code == 404


def test_el_unico_administrador_que_se_cambia_a_si_mismo_responde_409_sin_tocar_el_pin(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-053 punto 11, INV-01: la validación va antes de escribir y de borrar el PIN."""
    entorno = EntornoUsuarios(sesion_real)
    administrador_con_pin = entorno.crear_rol(
        "Administrador con PIN", frozenset({ADMIN, "AUTORIZAR_DESCUENTO"})
    )
    vendedor = entorno.crear_rol("Vendedor", VENDEDOR)
    yo, nombre = entorno.crear_usuario(administrador_con_pin, con_pin=True)
    mi_sesion = entorno.abrir_sesion(cliente_http, yo, nombre)

    respuesta = _cambiar(entorno, cliente_http, mi_sesion, yo, vendedor.id)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "IDENTIDAD_SIN_ADMINISTRADOR"
    assert entorno.usuario(yo)["rol_id"] == administrador_con_pin.id
    assert entorno.usuario(yo)["pin_autorizacion_hash"] is not None
    assert entorno.auditorias("CAMBIO_ROL_USUARIO") == []
    assert entorno.auditorias("INVALIDAR_PIN_AUTORIZACION") == []


def test_con_otro_administrador_el_cambio_del_propio_rol_se_acepta(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D5-A: el cambio del propio rol está permitido si queda otro administrador."""
    entorno = EntornoUsuarios(sesion_real)
    yo = entorno.administrador(cliente_http)
    entorno.crear_usuario(entorno.administradores)
    vendedor = entorno.crear_rol("Vendedor", VENDEDOR)

    respuesta = _cambiar(entorno, cliente_http, yo, yo.usuario_id, vendedor.id)

    assert respuesta.status_code == 200, respuesta.text
    assert entorno.usuario(yo.usuario_id)["rol_id"] == vendedor.id


def test_cambiar_a_otro_rol_administrador_no_deja_a_la_organizacion_sin_nadie(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """El conteo posterior cuenta al usuario con el rol nuevo: pasar a otro rol con
    `ADMIN_USUARIOS` es válido aunque sea el único administrador."""
    entorno = EntornoUsuarios(sesion_real)
    yo = entorno.administrador(cliente_http)
    gerencia = entorno.crear_rol("Gerencia", frozenset({ADMIN, "VER_REPORTES"}))

    respuesta = _cambiar(entorno, cliente_http, yo, yo.usuario_id, gerencia.id)

    assert respuesta.status_code == 200, respuesta.text


def test_el_mismo_rol_se_acepta_sin_auditoria_de_entidad(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    vendedor = entorno.crear_rol("Vendedor", VENDEDOR)
    usuario_id, _ = entorno.crear_usuario(vendedor)

    respuesta = _cambiar(entorno, cliente_http, administrador, usuario_id, vendedor.id)

    assert respuesta.status_code == 200, respuesta.text
    assert entorno.auditorias("CAMBIO_ROL_USUARIO") == []
    assert len(entorno.auditorias("USUARIO_ROL_CAMBIAR")) == 1


def test_el_doble_envio_no_repite_la_auditoria(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    vendedor = entorno.crear_rol("Vendedor", VENDEDOR)
    gerencia = entorno.crear_rol("Gerencia", VENDEDOR | {"VER_REPORTES"})
    usuario_id, _ = entorno.crear_usuario(vendedor)
    operation_id = uuid4()

    primera = _cambiar(entorno, cliente_http, administrador, usuario_id, gerencia.id, operation_id)
    segunda = _cambiar(entorno, cliente_http, administrador, usuario_id, gerencia.id, operation_id)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    assert len(entorno.auditorias("CAMBIO_ROL_USUARIO")) == 1


def test_sin_el_permiso_responde_403(cliente_http: TestClient, sesion_real: Session) -> None:
    """SEG-06: nadie se da permisos a sí mismo sin `ADMIN_USUARIOS`."""
    entorno = EntornoUsuarios(sesion_real)
    vendedor = entorno.crear_rol("Vendedor", VENDEDOR)
    yo, nombre = entorno.crear_usuario(vendedor)
    mi_sesion = entorno.abrir_sesion(cliente_http, yo, nombre)

    respuesta = _cambiar(entorno, cliente_http, mi_sesion, yo, entorno.administradores.id)

    assert respuesta.status_code == 403
    assert entorno.usuario(yo)["rol_id"] == vendedor.id
