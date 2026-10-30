# ruff: noqa: F811
"""Change 20b, tarea 8.1: `ROL_CREAR` v1 (`POST /api/v1/identidad/roles`) y `ROL_RENOMBRAR` v1
(`PUT /api/v1/identidad/roles/{id}/nombre`) (spec `identidad/administracion-de-roles`).

El nombre se recorta, tiene de 1 a 100 caracteres y es único por organización sin distinguir
mayúsculas, incluidos los roles de baja. Reglas citadas: `01` §19, AUD-01, INV-01, INV-02, INV-06,
INV-21, SEG-06.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from usuarios_utiles import (
    EntornoUsuarios,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

URL_ROLES = "/api/v1/identidad/roles"
VENDER = frozenset({"VENDER"})


def _crear(
    entorno, cliente, quien, nombre="Repartidor", permisos=None, tope=None, operation_id=None
):  # type: ignore[no-untyped-def]
    cuerpo: dict[str, object] = {
        "nombre": nombre,
        "permisos": ["VENDER", "REGISTRAR_COBRANZA"] if permisos is None else permisos,
    }
    if tope is not None:
        cuerpo["tope_descuento"] = tope
    return entorno.enviar(cliente, "POST", URL_ROLES, quien, cuerpo, operation_id=operation_id)


def _renombrar(entorno, cliente, quien, rol_id: UUID, nombre: str, operation_id=None):  # type: ignore[no-untyped-def]
    return entorno.enviar(
        cliente,
        "PUT",
        f"{URL_ROLES}/{rol_id}/nombre",
        quien,
        {"nombre": nombre},
        operation_id=operation_id,
    )


def _roles(entorno: EntornoUsuarios, nombre: str) -> list[dict]:  # type: ignore[type-arg]
    return entorno.fila(
        "SELECT id, nombre, activo, tope_descuento FROM rol "
        "WHERE organizacion_id = :o AND lower(nombre) = lower(:n)",
        o=entorno.org,
        n=nombre,
    )


def _permisos(entorno: EntornoUsuarios, rol_id: UUID) -> set[str]:
    return {
        f["permiso_codigo"]
        for f in entorno.fila("SELECT permiso_codigo FROM rol_permiso WHERE rol_id = :r", r=rol_id)
    }


# --- ROL_CREAR ---------------------------------------------------------------------------------


def test_crear_un_rol_lo_deja_activo_asignable_y_auditado(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """`01` §19, AUD-01, INV-06."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    operation_id = uuid4()

    respuesta = _crear(
        entorno, cliente_http, administrador, tope="0.100000", operation_id=operation_id
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Repartidor"
    assert cuerpo["activo"] is True
    assert cuerpo["tope_descuento"] == "0.100000"
    assert cuerpo["permisos"] == ["REGISTRAR_COBRANZA", "VENDER"]
    rol_id = UUID(cuerpo["id"])
    (fila,) = _roles(entorno, "Repartidor")
    assert fila["id"] == rol_id and fila["activo"] is True
    assert _permisos(entorno, rol_id) == {"VENDER", "REGISTRAR_COBRANZA"}
    (auditoria,) = entorno.auditorias("ALTA_ROL", entidad_id=rol_id)
    assert auditoria["origen"] == "COMANDO"
    assert auditoria["operation_id"] == operation_id
    assert auditoria["antes"] is None
    assert auditoria["despues"] == {
        "nombre": "Repartidor",
        "activo": True,
        "tope_descuento": "0.100000",
        "permisos": ["REGISTRAR_COBRANZA", "VENDER"],
    }
    # Se puede asignar a un usuario nuevo.
    alta = entorno.enviar(
        cliente_http,
        "POST",
        "/api/v1/identidad/usuarios",
        administrador,
        {
            "usuario": f"u-{uuid4().hex[:6]}",
            "nombre": "Nuevo",
            "email": None,
            "password": "una-contrasena-larga-123",
            "rol_id": str(rol_id),
        },
    )
    assert alta.status_code == 201, alta.text


def test_sin_tope_el_rol_nace_con_cero_y_el_nombre_se_recorta(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)

    respuesta = _crear(entorno, cliente_http, administrador, nombre="  Chofer  ", permisos=[])

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["nombre"] == "Chofer"
    assert respuesta.json()["tope_descuento"] == "0.000000"
    assert respuesta.json()["permisos"] == []


@pytest.mark.parametrize("repetido", ["vendedor", "VENDEDOR", "  Vendedor "])
def test_un_nombre_repetido_sin_distinguir_mayusculas_responde_409(
    cliente_http: TestClient, sesion_real: Session, repetido: str
) -> None:
    """INV-01, INV-02."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    entorno.crear_rol("Vendedor", VENDER)

    respuesta = _crear(entorno, cliente_http, administrador, nombre=repetido)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO"
    assert len(_roles(entorno, "Vendedor")) == 1
    assert entorno.auditorias("ALTA_ROL") == []


def test_el_nombre_de_un_rol_de_baja_tambien_cuenta_como_repetido(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    entorno.crear_rol("Viejo", VENDER, activo=False)

    respuesta = _crear(entorno, cliente_http, administrador, nombre="viejo")

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO"


@pytest.mark.parametrize("nombre", ["", "     ", "x" * 101])
def test_un_nombre_invalido_responde_422(
    cliente_http: TestClient, sesion_real: Session, nombre: str
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)

    respuesta = _crear(entorno, cliente_http, administrador, nombre=nombre)

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "IDENTIDAD_NOMBRE_DE_ROL_INVALIDO"
    assert entorno.auditorias("ALTA_ROL") == []


def test_un_nombre_de_exactamente_100_caracteres_se_acepta(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)

    respuesta = _crear(entorno, cliente_http, administrador, nombre="x" * 100)

    assert respuesta.status_code == 201, respuesta.text


def test_un_permiso_fuera_del_catalogo_no_crea_nada(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """`03` §4, INV-01: como en el cambio de permisos."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)

    respuesta = _crear(entorno, cliente_http, administrador, permisos=["VENDER", "NO_EXISTE"])

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "IDENTIDAD_ROL_CON_PERMISO_INEXISTENTE"
    assert _roles(entorno, "Repartidor") == []
    assert entorno.auditorias("ALTA_ROL") == []


@pytest.mark.parametrize("tope", ["1.5", "-0.1"])
def test_un_tope_fuera_de_rango_responde_422_y_no_crea_nada(
    cliente_http: TestClient, sesion_real: Session, tope: str
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)

    respuesta = _crear(entorno, cliente_http, administrador, tope=tope)

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO"
    assert _roles(entorno, "Repartidor") == []


def test_el_mismo_nombre_en_otra_organizacion_se_acepta(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-02."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    admin_propio = propia.administrador(cliente_http)
    ajena.crear_rol("Repartidor", VENDER)

    respuesta = _crear(propia, cliente_http, admin_propio)

    assert respuesta.status_code == 201, respuesta.text


def test_crear_el_doble_envio_no_crea_otro_rol(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    operation_id = uuid4()

    primera = _crear(entorno, cliente_http, administrador, operation_id=operation_id)
    segunda = _crear(entorno, cliente_http, administrador, operation_id=operation_id)

    assert primera.status_code == 201 and segunda.status_code == 201
    assert primera.json() == segunda.json()
    assert len(_roles(entorno, "Repartidor")) == 1
    assert len(entorno.auditorias("ALTA_ROL")) == 1
    assert entorno.comandos("ROL_CREAR") == 1


def test_crear_sin_el_permiso_responde_403(cliente_http: TestClient, sesion_real: Session) -> None:
    """SEG-06."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDER))
    sin_permiso = entorno.abrir_sesion(cliente_http, usuario_id, nombre)

    respuesta = _crear(entorno, cliente_http, sin_permiso)

    assert respuesta.status_code == 403
    assert _roles(entorno, "Repartidor") == []


# --- ROL_RENOMBRAR -----------------------------------------------------------------------------


def test_renombrar_audita_los_dos_nombres_y_no_toca_nada_mas(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """`01` §19, AUD-01: una plantilla se renombra como cualquier rol."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    plantilla = entorno.crear_rol(
        "Vendedor/Repartidor", frozenset({"VENDER", "REGISTRAR_COBRANZA"})
    )
    usuario_id, _ = entorno.crear_usuario(plantilla)
    operation_id = uuid4()

    respuesta = _renombrar(
        entorno, cliente_http, administrador, plantilla.id, "  Vendedor  ", operation_id
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["nombre"] == "Vendedor"
    assert respuesta.json()["id"] == str(plantilla.id)
    assert _permisos(entorno, plantilla.id) == {"VENDER", "REGISTRAR_COBRANZA"}
    assert entorno.usuario(usuario_id)["rol_id"] == plantilla.id
    (auditoria,) = entorno.auditorias("RENOMBRAR_ROL", entidad_id=plantilla.id)
    assert auditoria["origen"] == "COMANDO"
    assert auditoria["operation_id"] == operation_id
    assert auditoria["antes"] == {"nombre": "Vendedor/Repartidor"}
    assert auditoria["despues"] == {"nombre": "Vendedor"}


def test_renombrar_solo_en_mayusculas_se_acepta_sobre_el_mismo_rol(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """El índice único ignora mayúsculas, pero no choca con el propio rol."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("vendedor", VENDER)

    respuesta = _renombrar(entorno, cliente_http, administrador, rol.id, "Vendedor")

    assert respuesta.status_code == 200, respuesta.text
    assert len(entorno.auditorias("RENOMBRAR_ROL")) == 1


def test_renombrar_al_mismo_nombre_no_deja_auditoria_de_entidad(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", VENDER)

    respuesta = _renombrar(entorno, cliente_http, administrador, rol.id, "Vendedor")

    assert respuesta.status_code == 200
    assert entorno.auditorias("RENOMBRAR_ROL") == []


def test_renombrar_a_un_nombre_de_otro_rol_responde_409(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    entorno.crear_rol("Supervisor", VENDER)
    rol = entorno.crear_rol("Vendedor", VENDER)

    respuesta = _renombrar(entorno, cliente_http, administrador, rol.id, "SUPERVISOR")

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO"
    assert entorno.auditorias("RENOMBRAR_ROL") == []


@pytest.mark.parametrize("nombre", ["", "   ", "y" * 101])
def test_renombrar_con_nombre_invalido_responde_422(
    cliente_http: TestClient, sesion_real: Session, nombre: str
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", VENDER)

    respuesta = _renombrar(entorno, cliente_http, administrador, rol.id, nombre)

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "IDENTIDAD_NOMBRE_DE_ROL_INVALIDO"


def test_renombrar_un_rol_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21, SEG-07."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    rol_ajeno = ajena.crear_rol("Vendedor", VENDER)

    respuesta = _renombrar(propia, cliente_http, administrador, rol_ajeno.id, "Otro")

    assert respuesta.status_code == 404
    assert _roles(ajena, "Vendedor")[0]["id"] == rol_ajeno.id


def test_renombrar_el_doble_envio_no_repite_la_auditoria(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", VENDER)
    operation_id = uuid4()

    primera = _renombrar(entorno, cliente_http, administrador, rol.id, "Nuevo", operation_id)
    segunda = _renombrar(entorno, cliente_http, administrador, rol.id, "Nuevo", operation_id)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    assert len(entorno.auditorias("RENOMBRAR_ROL")) == 1
    assert entorno.comandos("ROL_RENOMBRAR") == 1


def test_renombrar_sin_el_permiso_responde_403(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """SEG-06."""
    entorno = EntornoUsuarios(sesion_real)
    rol = entorno.crear_rol("Vendedor", VENDER)
    usuario_id, nombre = entorno.crear_usuario(rol)
    sin_permiso = entorno.abrir_sesion(cliente_http, usuario_id, nombre)

    respuesta = _renombrar(entorno, cliente_http, sin_permiso, rol.id, "Otro")

    assert respuesta.status_code == 403
    assert _roles(entorno, "Vendedor")[0]["nombre"] == "Vendedor"
