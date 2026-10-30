# ruff: noqa: F811
"""Change 20b, tarea 4.4: las reglas nuevas del alta de usuarios (`USUARIO_CREAR`,
`POST /api/v1/identidad/usuarios`), spec `identidad/administracion-de-usuarios` y
`design.md` D4, D9.

Un rol de baja no se asigna (409 `IDENTIDAD_ROL_INACTIVO`); un nombre de inicio de sesión repetido
en la organización responde 409 `IDENTIDAD_USUARIO_DUPLICADO` (no un error de infraestructura) y el
mismo nombre en otra organización se acepta; el alta toma la exclusión mutua de identidad.

Reglas citadas: ADR-028 D9.4, ADR-053, ADR-056, INV-01, INV-02, INV-21.
"""

from __future__ import annotations

import threading
import time
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from usuarios_utiles import (
    URL_USUARIOS,
    EntornoUsuarios,
    SesionAbierta,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

from app.core.db import crear_engine, crear_session_factory

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

CLAVE = "clave-del-alta-nueva-3391"


def _alta(
    entorno: EntornoUsuarios,
    cliente: TestClient,
    quien: SesionAbierta,
    rol_id: UUID,
    *,
    usuario: str = "nuevo1",
    password: str = CLAVE,
) -> Any:
    return entorno.enviar(
        cliente,
        "POST",
        URL_USUARIOS,
        quien,
        {
            "usuario": usuario,
            "nombre": "Persona Nueva",
            "email": None,
            "password": password,
            "rol_id": str(rol_id),
        },
    )


def _cantidad_de_usuarios(entorno: EntornoUsuarios, nombre: str) -> int:
    (fila,) = entorno.fila(
        "SELECT count(*) AS n FROM usuario WHERE organizacion_id = :o AND usuario = :u",
        o=entorno.org,
        u=nombre,
    )
    return int(fila["n"])


def test_un_rol_de_baja_responde_409_y_no_crea_al_usuario(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    de_baja = entorno.crear_rol("Viejo", frozenset({"VENDER"}), activo=False)

    respuesta = _alta(entorno, cliente_http, administrador, de_baja.id)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "IDENTIDAD_ROL_INACTIVO"
    assert _cantidad_de_usuarios(entorno, "nuevo1") == 0
    assert entorno.auditorias("ALTA_USUARIO") == []


def test_un_rol_activo_sigue_funcionando(cliente_http: TestClient, sesion_real: Session) -> None:
    """Triangulación: la validación nueva no rompe el alta normal."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    activo = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))

    respuesta = _alta(entorno, cliente_http, administrador, activo.id)

    assert respuesta.status_code == 201, respuesta.text
    assert _cantidad_de_usuarios(entorno, "nuevo1") == 1


def test_un_nombre_repetido_responde_409_de_dominio_y_no_un_error_de_infraestructura(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    assert _alta(entorno, cliente_http, administrador, rol.id).status_code == 201

    repetido = _alta(entorno, cliente_http, administrador, rol.id)

    assert repetido.status_code == 409
    assert repetido.json()["codigo"] == "IDENTIDAD_USUARIO_DUPLICADO"
    assert _cantidad_de_usuarios(entorno, "nuevo1") == 1


def test_el_mismo_nombre_en_otra_organizacion_se_acepta(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-02: la unicidad es por organización."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    admin_propio = propia.administrador(cliente_http)
    admin_ajeno = ajena.administrador(cliente_http)
    rol_propio = propia.crear_rol("Vendedor", frozenset({"VENDER"}))
    rol_ajeno = ajena.crear_rol("Vendedor", frozenset({"VENDER"}))

    assert _alta(propia, cliente_http, admin_propio, rol_propio.id).status_code == 201
    assert _alta(ajena, cliente_http, admin_ajeno, rol_ajeno.id).status_code == 201

    assert _cantidad_de_usuarios(propia, "nuevo1") == 1
    assert _cantidad_de_usuarios(ajena, "nuevo1") == 1


@pytest.mark.parametrize("contrasena", ["   ", "1234567", " " * 8])
def test_una_contrasena_en_blanco_o_de_menos_de_8_caracteres_responde_422(
    cliente_http: TestClient, sesion_real: Session, contrasena: str
) -> None:
    """D9/D20: el alta usa la misma regla de contraseña (mínimo 8, no en blanco) que el
    restablecimiento y el cambio propio."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))

    respuesta = _alta(entorno, cliente_http, administrador, rol.id, password=contrasena)

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "IDENTIDAD_CONTRASENA_INVALIDA"
    assert _cantidad_de_usuarios(entorno, "nuevo1") == 0


def test_una_contrasena_de_exactamente_8_caracteres_sin_composicion_se_acepta(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D9: sin reglas de mayúsculas, números ni símbolos; 8 caracteres bastan."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))

    respuesta = _alta(entorno, cliente_http, administrador, rol.id, password="abcdefgh")

    assert respuesta.status_code == 201
    assert _cantidad_de_usuarios(entorno, "nuevo1") == 1


def test_el_alta_espera_la_exclusion_mutua_de_identidad(
    cliente_http: TestClient, sesion_real: Session, database_url: str
) -> None:
    """D4: mientras otra operación de identidad tiene `configuracion_organizacion FOR UPDATE`, el
    alta espera; al liberarla, termina. Transacciones reales, sin rollback externo."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    engine = crear_engine(database_url)
    bloqueador = crear_session_factory(engine)()
    resultados: list[Any] = []
    try:
        bloqueador.execute(
            text("SELECT 1 FROM configuracion_organizacion WHERE organizacion_id = :o FOR UPDATE"),
            {"o": entorno.org},
        )
        hilo = threading.Thread(
            target=lambda: resultados.append(_alta(entorno, cliente_http, administrador, rol.id))
        )
        hilo.start()
        time.sleep(1.5)
        assert hilo.is_alive(), "el alta no esperó la exclusión mutua"
        assert _cantidad_de_usuarios(entorno, "nuevo1") == 0
    finally:
        bloqueador.rollback()
        bloqueador.close()
        engine.dispose()
    hilo.join(timeout=20)

    assert not hilo.is_alive()
    assert resultados[0].status_code == 201, resultados[0].text
    assert _cantidad_de_usuarios(entorno, "nuevo1") == 1
