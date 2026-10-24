# ruff: noqa: F811
"""Tarea 22.5 (change 18b; `design.md` D2 y D23, ADR-056; spec `identidad/usuarios-y-roles`): la
contraseña de `USUARIO_CREAR` sale del contenido del comando y viaja como dato efímero.

`POST /api/v1/identidad/usuarios` separa la contraseña del cuerpo antes de armar el contenido y la
huella y se la entrega al handler por clausura (`SecretStr`). El contenido queda con los datos del
alta, sin `password` (`extra="forbid"`). La contraseña no llega a la huella, a `comando`, a la
auditoría, al resultado ni a los registros; el usuario creado inicia sesión con ella.

Reglas citadas: SEG-05, ADR-019, ADR-022, ADR-056, INV-06, `02` §17.
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_identidad_commands_maestros import (
    _crear_organizacion,
    _crear_usuario,
    _limpiar_datos_confirmados,  # noqa: F401  (fixture autouse)
    _login,
    cliente,  # noqa: F401  (fixture)
    sesion,  # noqa: F401  (fixture)
)

from app.commands import registro
from app.commands.errores import ContenidoDeComandoInvalidoError
from app.commands.huella import calcular_huella

CLAVE = "clave-secreta-del-alta-48213"
CLAVE_2 = "otra-clave-secreta-del-alta-77310"
URL = "/api/v1/identidad/usuarios"


class Entorno:
    """Un administrador (`ADMIN_USUARIOS`) y un rol sin permisos para el alta."""

    def __init__(self, cliente: TestClient, sesion: Session) -> None:
        self.cliente = cliente
        self.sesion = sesion
        self.organizacion = _crear_organizacion(sesion, f"org-alta-ef-{uuid4().hex[:8]}")
        admin, rol = _crear_usuario(
            sesion,
            self.organizacion.id,
            permisos=frozenset({"ADMIN_USUARIOS"}),
            nombre_usuario="admin1",
        )
        sesion.commit()
        self.rol_id = rol.id
        self.token = _login(cliente, self.organizacion.slug, "admin1")

    def alta(
        self,
        password: object,
        *,
        nombre: str = "nueva1",
        operation_id: UUID | None = None,
        rol_id: UUID | None = None,
    ):  # type: ignore[no-untyped-def]
        return self.cliente.post(
            URL,
            json={
                "usuario": nombre,
                "nombre": "Nueva Persona",
                "email": None,
                "password": password,
                "rol_id": str(rol_id or self.rol_id),
            },
            headers={
                "Authorization": f"Bearer {self.token}",
                "Operation-Id": str(operation_id or uuid4()),
            },
        )

    def volcado(self, tabla: str) -> str:
        self.sesion.rollback()
        return str(
            self.sesion.execute(
                text(f"SELECT coalesce(string_agg(to_json(t)::text, ' '), '') FROM {tabla} t")
            ).scalar_one()
        )

    def sin_rastro(self, secreto: str) -> None:
        for tabla in ("comando", "comando_cuarentena", "auditoria", "observacion"):
            assert secreto not in self.volcado(tabla), tabla


def test_sec17_la_contrasena_no_queda_en_ningun_registro_ni_en_la_respuesta(
    cliente: TestClient,  # noqa: F811
    sesion: Session,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    e = Entorno(cliente, sesion)

    with caplog.at_level(logging.DEBUG):
        respuesta = e.alta(CLAVE)

    assert respuesta.status_code == 201
    assert CLAVE not in respuesta.text
    assert CLAVE not in caplog.text
    e.sin_rastro(CLAVE)


def test_sec17_tampoco_con_un_alta_rechazada_ni_con_un_cuerpo_invalido(
    cliente: TestClient,  # noqa: F811
    sesion: Session,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Triangulación con entradas inválidas: un rol inexistente (404) y una contraseña que no es
    un texto (422) no dejan la contraseña en la respuesta, los registros ni la base."""
    e = Entorno(cliente, sesion)

    with caplog.at_level(logging.DEBUG):
        sin_rol = e.alta(CLAVE_2, nombre="nueva2", rol_id=uuid4())
        mal_tipo = e.alta(917253, nombre="nueva3")

    assert sin_rol.status_code == 404
    assert CLAVE_2 not in sin_rol.text
    assert mal_tipo.status_code == 422
    assert "917253" not in mal_tipo.text
    assert all("input" not in error for error in mal_tipo.json()["detail"])
    assert CLAVE_2 not in caplog.text
    e.sin_rastro(CLAVE_2)


def test_inv06_dos_contrasenas_distintas_con_el_mismo_operation_id_dan_la_misma_huella(
    cliente: TestClient,  # noqa: F811
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    operacion = uuid4()

    primera = e.alta(CLAVE, operation_id=operacion)
    segunda = e.alta(CLAVE_2, operation_id=operacion)

    assert (primera.status_code, segunda.status_code) == (201, 201)
    assert segunda.json() == primera.json()  # el resultado original, sin crear otro usuario
    cantidad = sesion.execute(
        text("SELECT count(*) FROM usuario WHERE usuario = 'nueva1'")
    ).scalar_one()
    huella = sesion.execute(
        text("SELECT huella FROM comando WHERE operation_id = :o"), {"o": operacion}
    ).scalar_one()
    sesion.rollback()
    assert cantidad == 1
    assert huella == calcular_huella(
        {
            "usuario": "nueva1",
            "nombre": "Nueva Persona",
            "email": None,
            "rol_id": str(e.rol_id),
        }
    )


def test_un_contenido_antiguo_con_password_adentro_es_malformado() -> None:
    handler = registro.resolver_handler("USUARIO_CREAR", 1)
    base = {"usuario": "x", "nombre": "X", "email": None, "rol_id": str(uuid4())}

    with pytest.raises(ContenidoDeComandoInvalidoError) as error:
        registro.validar_contenido(handler, {**base, "password": CLAVE})

    assert CLAVE not in error.value.mensaje
    registro.validar_contenido(handler, base)  # sin la contraseña, es válido


def test_seg05_el_usuario_creado_inicia_sesion_con_esa_contrasena(
    cliente: TestClient,  # noqa: F811
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    assert e.alta(CLAVE).status_code == 201

    correcto = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": e.organizacion.slug,
            "usuario": "nueva1",
            "contrasena": CLAVE,
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "PC",
        },
    )

    assert correcto.status_code == 200
