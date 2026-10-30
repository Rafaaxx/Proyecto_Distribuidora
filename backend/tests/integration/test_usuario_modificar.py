# ruff: noqa: F811
"""Change 20b, tarea 4.1: `USUARIO_MODIFICAR` v1, `PUT /api/v1/identidad/usuarios/{id}`
(spec `identidad/administracion-de-usuarios`).

Edita el nombre (obligatorio, recortado, hasta 200) y el email (opcional; vacío es nulo) con
reemplazo completo. El nombre de inicio de sesión (`usuario`) no se edita (D9).

Reglas citadas: AUD-01, INV-01, INV-06, INV-21, SEG-06.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from usuarios_utiles import (
    URL_USUARIOS,
    EntornoUsuarios,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")


def _modificar(entorno, cliente, quien, usuario_id, cuerpo, operation_id=None):  # type: ignore[no-untyped-def]
    return entorno.enviar(
        cliente, "PUT", f"{URL_USUARIOS}/{usuario_id}", quien, cuerpo, operation_id=operation_id
    )


def test_modificar_nombre_y_email_deja_la_auditoria_con_antes_y_despues(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", frozenset({"VENDER"})))
    operation_id = uuid4()

    respuesta = _modificar(
        entorno,
        cliente_http,
        administrador,
        usuario_id,
        {"nombre": "  Laura Pérez  ", "email": " laura@ejemplo.com "},
        operation_id,
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["nombre"] == "Laura Pérez"
    assert respuesta.json()["email"] == "laura@ejemplo.com"
    fila = entorno.usuario(usuario_id)
    assert (fila["nombre"], fila["email"]) == ("Laura Pérez", "laura@ejemplo.com")
    (auditoria,) = entorno.auditorias("MODIFICAR_USUARIO", entidad_id=usuario_id)
    assert auditoria["origen"] == "COMANDO"
    assert auditoria["operation_id"] == operation_id
    assert auditoria["antes"] == {"nombre": "Persona de prueba", "email": None}
    assert auditoria["despues"] == {"nombre": "Laura Pérez", "email": "laura@ejemplo.com"}
    assert auditoria["usuario_id"] == administrador.usuario_id


def test_un_email_vacio_se_guarda_como_nulo_y_la_auditoria_lo_refleja(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", frozenset({"VENDER"})))
    _modificar(
        entorno, cliente_http, administrador, usuario_id, {"nombre": "Juan", "email": "j@e.com"}
    )

    respuesta = _modificar(
        entorno, cliente_http, administrador, usuario_id, {"nombre": "Juan", "email": "   "}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["email"] is None
    assert entorno.usuario(usuario_id)["email"] is None
    ultima = entorno.auditorias("MODIFICAR_USUARIO", entidad_id=usuario_id)[-1]
    assert ultima["antes"] == {"nombre": "Juan", "email": "j@e.com"}
    assert ultima["despues"] == {"nombre": "Juan", "email": None}


@pytest.mark.parametrize("nombre", ["", "    ", "a" * 201])
def test_un_nombre_invalido_responde_422_y_no_cambia_nada(
    cliente_http: TestClient, sesion_real: Session, nombre: str
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", frozenset({"VENDER"})))

    respuesta = _modificar(
        entorno, cliente_http, administrador, usuario_id, {"nombre": nombre, "email": None}
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "IDENTIDAD_NOMBRE_DE_USUARIO_INVALIDO"
    assert entorno.usuario(usuario_id)["nombre"] == "Persona de prueba"
    assert entorno.auditorias("MODIFICAR_USUARIO") == []


def test_el_mismo_valor_se_acepta_sin_auditoria_de_entidad(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", frozenset({"VENDER"})))

    respuesta = _modificar(
        entorno,
        cliente_http,
        administrador,
        usuario_id,
        {"nombre": "Persona de prueba", "email": None},
    )

    assert respuesta.status_code == 200, respuesta.text
    assert entorno.auditorias("MODIFICAR_USUARIO") == []
    assert len(entorno.auditorias("USUARIO_MODIFICAR")) == 1  # la fila genérica del bus


def test_el_nombre_de_inicio_de_sesion_no_se_edita(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D9: `usuario` es la clave del bloqueo por nombre escrito (ADR-057); un cuerpo que lo trae se
    rechaza por campo no admitido y el login no cambia."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, nombre_login = entorno.crear_usuario(
        entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    )

    respuesta = _modificar(
        entorno,
        cliente_http,
        administrador,
        usuario_id,
        {"nombre": "Otro nombre", "email": None, "usuario": "otro-login"},
    )

    assert respuesta.status_code == 422
    assert entorno.usuario(usuario_id)["usuario"] == nombre_login
    assert entorno.usuario(usuario_id)["nombre"] == "Persona de prueba"


def test_modificar_no_toca_el_estado_ni_el_rol_ni_las_sesiones(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    usuario_id, nombre_login = entorno.crear_usuario(rol)
    entorno.abrir_sesion(cliente_http, usuario_id, nombre_login)

    _modificar(entorno, cliente_http, administrador, usuario_id, {"nombre": "Nuevo", "email": None})

    fila = entorno.usuario(usuario_id)
    assert (fila["estado"], fila["rol_id"]) == ("ACTIVO", rol.id)
    assert len(entorno.familias_vigentes(usuario_id)) == 1


def test_un_usuario_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21, SEG-07."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    ajeno_id, _ = ajena.crear_usuario(ajena.crear_rol("Vendedor", frozenset({"VENDER"})))

    respuesta = _modificar(
        propia, cliente_http, administrador, ajeno_id, {"nombre": "Intruso", "email": None}
    )

    assert respuesta.status_code == 404
    assert ajena.usuario(ajeno_id)["nombre"] == "Persona de prueba"


def test_el_doble_envio_no_repite_la_auditoria(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", frozenset({"VENDER"})))
    operation_id = uuid4()
    cuerpo = {"nombre": "Laura", "email": None}

    primera = _modificar(entorno, cliente_http, administrador, usuario_id, cuerpo, operation_id)
    segunda = _modificar(entorno, cliente_http, administrador, usuario_id, cuerpo, operation_id)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    assert len(entorno.auditorias("MODIFICAR_USUARIO")) == 1


def test_sin_el_permiso_responde_403(cliente_http: TestClient, sesion_real: Session) -> None:
    """SEG-06."""
    entorno = EntornoUsuarios(sesion_real)
    vendedor = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    quien_id, quien = entorno.crear_usuario(vendedor)
    sin_permiso = entorno.abrir_sesion(cliente_http, quien_id, quien)

    respuesta = _modificar(
        entorno, cliente_http, sin_permiso, quien_id, {"nombre": "Yo mismo", "email": None}
    )

    assert respuesta.status_code == 403
    assert entorno.usuario(quien_id)["nombre"] == "Persona de prueba"
