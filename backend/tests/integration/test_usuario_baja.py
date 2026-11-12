# ruff: noqa: F811
"""Change 20b, tarea 3.1: `USUARIO_BAJA` v1, `POST /api/v1/identidad/usuarios/{id}/baja`
(spec `identidad/administracion-de-usuarios` y `identidad/autenticacion-y-sesion`).

La baja pasa el usuario a `INACTIVO`, revoca sus familias de refresh salvo las de dispositivos con
una jornada no cerrada (`motivo_revocacion = 'USUARIO_INACTIVO'`), borra su PIN de autorización y
audita la baja y la revocación (`origen = 'COMANDO'`, mismo `operation_id`).

Reglas citadas: ADR-028 D9.1, D9.3-B y D9.5, ADR-011, ADR-053, AUD-01, AUD-02, INV-01, INV-06,
INV-21.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql
from usuarios_utiles import (
    URL_USUARIOS,
    EntornoUsuarios,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

from app.core.clock import SystemClock
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

SUPERVISOR = frozenset({"VENDER", "AUTORIZAR_DESCUENTO"})


def _baja(entorno: EntornoUsuarios, cliente: TestClient, quien, usuario_id: UUID, **extra: object):  # type: ignore[no-untyped-def]
    operation_id = extra.pop("operation_id", None)
    return entorno.enviar(
        cliente,
        "POST",
        f"{URL_USUARIOS}/{usuario_id}/baja",
        quien,
        {"observacion": None, **extra},
        operation_id=operation_id,  # type: ignore[arg-type]
    )


def test_la_baja_corta_las_sesiones_borra_el_pin_y_deja_su_auditoria(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-028 D9.1, D9.3-B, D9.5; ADR-011; AUD-01, AUD-02; INV-01."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    supervisor = entorno.crear_rol("Supervisor", SUPERVISOR)
    usuario_id, nombre = entorno.crear_usuario(supervisor, con_pin=True)
    en_la_pc = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    en_el_telefono = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    operation_id = uuid4()

    respuesta = _baja(
        entorno,
        cliente_http,
        administrador,
        usuario_id,
        observacion="Dejó la empresa",
        operation_id=operation_id,
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "INACTIVO"
    fila = entorno.usuario(usuario_id)
    assert fila["estado"] == "INACTIVO"
    assert fila["pin_autorizacion_hash"] is None
    revocadas = entorno.familias(usuario_id)
    assert len(revocadas) == 2
    assert {f["motivo_revocacion"] for f in revocadas} == {"USUARIO_INACTIVO"}
    assert all(f["revocado_en"] is not None for f in revocadas)
    # La petición siguiente se rechaza y la renovación también.
    for sesion_del_usuario in (en_la_pc, en_el_telefono):
        assert cliente_http.get("/api/v1/yo", headers=sesion_del_usuario.headers).status_code == 401
        renovada = entorno.renovar(cliente_http, sesion_del_usuario)
        assert renovada.status_code == 401
        assert renovada.json()["codigo"] == "IDENTIDAD_REFRESH_TOKEN_INVALIDO"
    # Auditoría: la baja con la observación y la revocación, del comando, con el mismo operation_id.
    (baja,) = entorno.auditorias("BAJA_USUARIO", entidad_id=usuario_id)
    assert baja["origen"] == "COMANDO"
    assert baja["operation_id"] == operation_id
    assert baja["antes"] == {"estado": "ACTIVO"}
    assert baja["despues"] == {"estado": "INACTIVO"}
    assert baja["observacion"] == "Dejó la empresa"
    assert baja["usuario_id"] == administrador.usuario_id
    (revocacion,) = entorno.auditorias("REVOCAR_SESIONES_REFRESH_USUARIO", entidad_id=usuario_id)
    assert revocacion["origen"] == "COMANDO"
    assert revocacion["operation_id"] == operation_id
    (pin,) = entorno.auditorias("INVALIDAR_PIN_AUTORIZACION", entidad_id=usuario_id)
    assert pin["operation_id"] == operation_id
    (del_bus,) = entorno.auditorias("USUARIO_BAJA")
    assert del_bus["entidad"] == "comando"
    assert del_bus["operation_id"] == operation_id


def test_una_baja_sin_sesiones_ni_pin_no_audita_la_revocacion_ni_el_pin(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """Triangulación: la auditoría de efecto solo existe si hubo efecto."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    vendedor = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    usuario_id, _ = entorno.crear_usuario(vendedor)

    respuesta = _baja(entorno, cliente_http, administrador, usuario_id)

    assert respuesta.status_code == 200, respuesta.text
    assert entorno.usuario(usuario_id)["estado"] == "INACTIVO"
    assert entorno.auditorias("REVOCAR_SESIONES_REFRESH_USUARIO") == []
    assert entorno.auditorias("INVALIDAR_PIN_AUTORIZACION") == []
    assert len(entorno.auditorias("BAJA_USUARIO", entidad_id=usuario_id)) == 1


def test_con_jornada_abierta_en_un_dispositivo_esa_familia_sigue_y_renueva(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-028 D9.3-B: la jornada no cerrada conserva la sesión de su dispositivo para que el
    teléfono entregue su cola; la otra familia se revoca."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    vendedor = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    usuario_id, nombre = entorno.crear_usuario(vendedor)
    en_la_pc = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    en_el_telefono = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    ubicacion = crear_ubicacion_sql(
        sesion_real, entorno.org, nombre="Camioneta", tipo="VEHICULO", requiere_toma=True
    )
    crear_jornada_sql(
        sesion_real,
        entorno.org,
        usuario_id=usuario_id,
        dispositivo_id=en_el_telefono.dispositivo_id,
        ubicacion_id=ubicacion,
    )
    sesion_real.commit()

    respuesta = _baja(entorno, cliente_http, administrador, usuario_id)

    assert respuesta.status_code == 200, respuesta.text
    assert entorno.familias_vigentes(usuario_id) == {en_el_telefono.dispositivo_id}
    assert entorno.renovar(cliente_http, en_la_pc).status_code == 401
    assert entorno.renovar(cliente_http, en_el_telefono).status_code == 200
    # El access token de la jornada tampoco abre una ruta de negocio: D9.1 sigue vigente.
    assert cliente_http.get("/api/v1/yo", headers=en_el_telefono.headers).status_code == 401
    (revocacion,) = entorno.auditorias("REVOCAR_SESIONES_REFRESH_USUARIO", entidad_id=usuario_id)
    assert revocacion["origen"] == "COMANDO"


def test_dar_de_baja_a_un_inactivo_responde_409_y_no_cambia_nada(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    vendedor = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    usuario_id, _ = entorno.crear_usuario(vendedor, estado="INACTIVO")
    auditoria_antes = entorno.total_auditoria()

    respuesta = _baja(entorno, cliente_http, administrador, usuario_id)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA"
    assert entorno.usuario(usuario_id)["estado"] == "INACTIVO"
    assert entorno.total_auditoria() == auditoria_antes


@pytest.mark.parametrize("hay_otro_administrador", [True, False])
def test_la_autobaja_responde_409_aunque_haya_otros_administradores_y_no_revoca(
    cliente_http: TestClient, sesion_real: Session, hay_otro_administrador: bool
) -> None:
    """D5-A: se rechaza siempre con `IDENTIDAD_AUTOBAJA` (no con `SIN_ADMINISTRADOR`)."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    if hay_otro_administrador:
        entorno.crear_usuario(entorno.administradores)

    respuesta = _baja(entorno, cliente_http, administrador, administrador.usuario_id)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "IDENTIDAD_AUTOBAJA"
    assert entorno.usuario(administrador.usuario_id)["estado"] == "ACTIVO"
    assert entorno.familias_vigentes(administrador.usuario_id) == {administrador.dispositivo_id}
    assert cliente_http.get("/api/v1/yo", headers=administrador.headers).status_code == 200
    assert entorno.auditorias("BAJA_USUARIO") == []


def test_un_usuario_de_otra_organizacion_responde_404_y_no_se_toca(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21, SEG-07."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    rol_ajeno = ajena.crear_rol("Vendedor", frozenset({"VENDER"}))
    ajeno_id, nombre = ajena.crear_usuario(rol_ajeno)
    ajena.abrir_sesion(cliente_http, ajeno_id, nombre)

    respuesta = _baja(propia, cliente_http, administrador, ajeno_id)

    assert respuesta.status_code == 404
    assert ajena.usuario(ajeno_id)["estado"] == "ACTIVO"
    assert len(ajena.familias_vigentes(ajeno_id)) == 1
    assert propia.auditorias("BAJA_USUARIO") == []


def test_un_usuario_inexistente_responde_404(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)

    assert _baja(entorno, cliente_http, administrador, uuid4()).status_code == 404


def test_el_doble_envio_no_repite_la_baja_ni_su_auditoria(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06: el mismo `Operation-Id` y el mismo contenido devuelven el resultado original."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    supervisor = entorno.crear_rol("Supervisor", SUPERVISOR)
    usuario_id, nombre = entorno.crear_usuario(supervisor, con_pin=True)
    entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    operation_id = uuid4()

    primera = _baja(entorno, cliente_http, administrador, usuario_id, operation_id=operation_id)
    segunda = _baja(entorno, cliente_http, administrador, usuario_id, operation_id=operation_id)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    assert len(entorno.auditorias("BAJA_USUARIO", entidad_id=usuario_id)) == 1
    assert len(entorno.auditorias("REVOCAR_SESIONES_REFRESH_USUARIO")) == 1
    assert entorno.comandos("USUARIO_BAJA") == 1


def test_sin_el_permiso_responde_403_por_rest_y_el_lote_lo_rechaza_sin_efectos(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """SEG-06, ADR-056: el permiso se exige en todo camino."""
    entorno = EntornoUsuarios(sesion_real)
    vendedor = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    quien_baja_id, quien_baja = entorno.crear_usuario(vendedor)
    objetivo_id, _ = entorno.crear_usuario(vendedor)
    sin_permiso = entorno.abrir_sesion(cliente_http, quien_baja_id, quien_baja)

    por_rest = _baja(entorno, cliente_http, sin_permiso, objetivo_id)

    assert por_rest.status_code == 403
    assert por_rest.json()["codigo"] == "PERMISO_REQUERIDO"

    item = ItemLote(
        operation_id=uuid4(),
        tipo="USUARIO_BAJA",
        version=1,
        modo="ONLINE",
        usuario_id=quien_baja_id,
        dispositivo_id=sin_permiso.dispositivo_id,
        occurred_at=SystemClock().now(),
        secuencia=1,
        app_version="1.0.0",
        contenido={"usuario_id": str(objetivo_id), "observacion": None},
        jornada_id=None,
    )
    (resultado,) = sync_service.procesar_lote(
        sesion_real,
        SystemClock(),
        organizacion_id=entorno.org,
        usuario_id=quien_baja_id,
        dispositivo_id=sin_permiso.dispositivo_id,
        items=[item],
    )
    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "PERMISO_REQUERIDO")
    assert entorno.usuario(objetivo_id)["estado"] == "ACTIVO"
    assert entorno.comandos("USUARIO_BAJA") == 0


def test_un_administrador_dado_de_baja_no_puede_dar_de_baja_a_otro(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D4: la baja del actor se ve en la petición siguiente (D9.1); el comando ya no se ejecuta."""
    entorno = EntornoUsuarios(sesion_real)
    primero = entorno.administrador(cliente_http)
    segundo = entorno.administrador(cliente_http)
    objetivo_id, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", frozenset({"VENDER"})))
    assert _baja(entorno, cliente_http, primero, segundo.usuario_id).status_code == 200

    respuesta = _baja(entorno, cliente_http, segundo, objetivo_id)

    assert respuesta.status_code == 401
    assert entorno.usuario(objetivo_id)["estado"] == "ACTIVO"
