# ruff: noqa: F811
"""Change 20b, tarea 9.2: `CLIENTE_VENDEDOR_ASIGNAR` v1, `POST /api/v1/clientes/vendedor` (spec
`clientes/cartera-de-clientes`).

Asigna un vendedor (o lo quita con `null`) a uno o varios clientes (hasta 500), todo o nada, con
una fila de auditoría por cliente cambiado.

Reglas citadas: `01` §19, CLI-03, AUD-01, SEG-06, ADR-056, INV-01, INV-02, INV-06, INV-21.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_cliente
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from usuarios_utiles import (
    EntornoUsuarios,
    SesionAbierta,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

URL = "/api/v1/clientes/vendedor"
URL_LOTE = "/api/v1/sync/comandos"
GESTIONAR = frozenset({"GESTIONAR_CLIENTES"})
VENDER = frozenset({"VENDER"})
COBRAR = frozenset({"REGISTRAR_COBRANZA"})


def _gestor(entorno: EntornoUsuarios, cliente: TestClient) -> SesionAbierta:
    usuario_id, nombre = entorno.crear_usuario(entorno.crear_rol("Gestor", GESTIONAR))
    return entorno.abrir_sesion(cliente, usuario_id, nombre)


def _clientes(entorno: EntornoUsuarios, cantidad: int, **cambios: Any) -> list[UUID]:
    ids = [
        crear_cliente(entorno.sesion, entorno.org, nombre=f"Kiosco {i}", **cambios)
        for i in range(cantidad)
    ]
    entorno.sesion.commit()
    return ids


def _vendedor_de(entorno: EntornoUsuarios, cliente_id: UUID) -> UUID | None:
    (fila,) = entorno.fila("SELECT vendedor_id FROM cliente WHERE id = :c", c=cliente_id)
    return fila["vendedor_id"]


def _asignar(
    entorno: EntornoUsuarios,
    cliente_http: TestClient,
    quien: SesionAbierta,
    cliente_ids: list[UUID],
    vendedor_id: UUID | None,
    operation_id: UUID | None = None,
) -> Any:
    return entorno.enviar(
        cliente_http,
        "POST",
        URL,
        quien,
        {
            "cliente_ids": [str(c) for c in cliente_ids],
            "vendedor_id": None if vendedor_id is None else str(vendedor_id),
        },
        operation_id=operation_id,
    )


def _vendedor(
    entorno: EntornoUsuarios,
    permisos: frozenset[str] = VENDER,
    *,
    rol_activo: bool = True,
    estado: str = "ACTIVO",
) -> UUID:
    usuario_id, _ = entorno.crear_usuario(
        entorno.crear_rol(f"Rol {uuid4().hex[:6]}", permisos, activo=rol_activo), estado=estado
    )
    return usuario_id


def _sin_cambios(entorno: EntornoUsuarios, clientes: list[UUID]) -> None:
    for cliente_id in clientes:
        assert _vendedor_de(entorno, cliente_id) is None
    assert entorno.auditorias("ASIGNAR_VENDEDOR_CLIENTE") == []


def test_asignar_tres_clientes_deja_una_auditoria_por_cliente(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """`01` §19, AUD-01."""
    entorno = EntornoUsuarios(sesion_real)
    gestor = _gestor(entorno, cliente_http)
    juan = _vendedor(entorno)
    clientes = _clientes(entorno, 3)

    respuesta = _asignar(entorno, cliente_http, gestor, clientes, juan)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "vendedor_id": str(juan),
        "cliente_ids": [str(c) for c in clientes],
        "cambiados": 3,
    }
    for cliente_id in clientes:
        assert _vendedor_de(entorno, cliente_id) == juan
        (auditoria,) = entorno.auditorias("ASIGNAR_VENDEDOR_CLIENTE", entidad_id=cliente_id)
        assert auditoria["entidad"] == "cliente"
        assert auditoria["antes"] == {"vendedor_id": None}
        assert auditoria["despues"] == {"vendedor_id": str(juan)}
        assert auditoria["origen"] == "COMANDO"
        assert auditoria["usuario_id"] == gestor.usuario_id
    assert len(entorno.auditorias("ASIGNAR_VENDEDOR_CLIENTE")) == 3


def test_reasignar_registra_el_vendedor_anterior_y_el_mismo_vendedor_no_audita(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    gestor = _gestor(entorno, cliente_http)
    juan = _vendedor(entorno)
    pedro = _vendedor(entorno, COBRAR)
    uno, dos = _clientes(entorno, 2)
    _asignar(entorno, cliente_http, gestor, [uno], juan)

    reasignado = _asignar(entorno, cliente_http, gestor, [uno, dos], pedro)

    assert reasignado.json()["cambiados"] == 2
    (_, segunda) = entorno.auditorias("ASIGNAR_VENDEDOR_CLIENTE", entidad_id=uno)
    assert segunda["antes"] == {"vendedor_id": str(juan)}
    assert segunda["despues"] == {"vendedor_id": str(pedro)}

    igual = _asignar(entorno, cliente_http, gestor, [uno, dos], pedro)

    assert igual.status_code == 200
    assert igual.json()["cambiados"] == 0
    assert len(entorno.auditorias("ASIGNAR_VENDEDOR_CLIENTE")) == 3


def test_quitar_el_vendedor_con_null(cliente_http: TestClient, sesion_real: Session) -> None:
    entorno = EntornoUsuarios(sesion_real)
    gestor = _gestor(entorno, cliente_http)
    juan = _vendedor(entorno)
    uno, dos = _clientes(entorno, 2)
    _asignar(entorno, cliente_http, gestor, [uno, dos], juan)

    respuesta = _asignar(entorno, cliente_http, gestor, [uno], None)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["vendedor_id"] is None
    assert _vendedor_de(entorno, uno) is None
    assert _vendedor_de(entorno, dos) == juan
    ultima = entorno.auditorias("ASIGNAR_VENDEDOR_CLIENTE", entidad_id=uno)[-1]
    assert ultima["antes"] == {"vendedor_id": str(juan)}
    assert ultima["despues"] == {"vendedor_id": None}


def test_un_cliente_inexistente_o_ajeno_es_404_y_ninguno_cambia(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-01, INV-21."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    gestor = _gestor(propia, cliente_http)
    juan = _vendedor(propia)
    (mio,) = _clientes(propia, 1)
    (ajeno,) = _clientes(ajena, 1)

    de_otra = _asignar(propia, cliente_http, gestor, [mio, ajeno], juan)
    inexistente = _asignar(propia, cliente_http, gestor, [mio, uuid4()], juan)

    assert de_otra.status_code == inexistente.status_code == 404
    _sin_cambios(propia, [mio])
    _sin_cambios(ajena, [ajeno])


@pytest.mark.parametrize(
    "preparar",
    [
        pytest.param(lambda e: _vendedor(e, VENDER, rol_activo=False), id="rol-de-baja"),
        pytest.param(lambda e: _vendedor(e, frozenset({"VER_REPORTES"})), id="sin-permiso"),
        pytest.param(lambda e: _vendedor(e, VENDER, estado="INACTIVO"), id="usuario-inactivo"),
    ],
)
def test_un_vendedor_invalido_es_409_y_ninguno_cambia(
    cliente_http: TestClient,
    sesion_real: Session,
    preparar: Callable[[EntornoUsuarios], UUID],
) -> None:
    """INV-01: inactivo, sin `VENDER` ni `REGISTRAR_COBRANZA`, o de rol de baja."""
    entorno = EntornoUsuarios(sesion_real)
    gestor = _gestor(entorno, cliente_http)
    invalido = preparar(entorno)
    clientes = _clientes(entorno, 2)

    respuesta = _asignar(entorno, cliente_http, gestor, clientes, invalido)

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["codigo"] == "VENDEDOR_INVALIDO"
    _sin_cambios(entorno, clientes)


def test_un_vendedor_con_solo_registrar_cobranza_es_valido(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    gestor = _gestor(entorno, cliente_http)
    cobrador = _vendedor(entorno, COBRAR)
    (uno,) = _clientes(entorno, 1)

    respuesta = _asignar(entorno, cliente_http, gestor, [uno], cobrador)

    assert respuesta.status_code == 200, respuesta.text


def test_un_vendedor_de_otra_organizacion_es_404(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21, INV-02: se responde como usuario inexistente."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    gestor = _gestor(propia, cliente_http)
    ajeno = _vendedor(ajena)
    (uno,) = _clientes(propia, 1)

    respuesta = _asignar(propia, cliente_http, gestor, [uno], ajeno)

    assert respuesta.status_code == 404
    _sin_cambios(propia, [uno])


def test_el_consumidor_final_es_409_y_ninguno_cambia(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """CLI-03."""
    entorno = EntornoUsuarios(sesion_real)
    gestor = _gestor(entorno, cliente_http)
    juan = _vendedor(entorno)
    (comun,) = _clientes(entorno, 1)
    (final,) = _clientes(entorno, 1, es_consumidor_final=True)

    respuesta = _asignar(entorno, cliente_http, gestor, [comun, final], juan)
    quitando = _asignar(entorno, cliente_http, gestor, [final], None)

    assert respuesta.status_code == quitando.status_code == 409
    assert respuesta.json()["codigo"] == "CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR"
    _sin_cambios(entorno, [comun, final])


def test_la_lista_vacia_y_mas_de_500_son_422(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    gestor = _gestor(entorno, cliente_http)
    juan = _vendedor(entorno)

    vacia = _asignar(entorno, cliente_http, gestor, [], juan)
    demasiados = _asignar(entorno, cliente_http, gestor, [uuid4() for _ in range(501)], juan)

    assert vacia.status_code == demasiados.status_code == 422
    codigos = {vacia.json()["codigo"], demasiados.json()["codigo"]}
    assert codigos == {"ASIGNACION_DE_CLIENTES_INVALIDA"}


def test_sin_gestionar_clientes_es_403_por_rest_y_por_lote(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """SEG-06, ADR-056."""
    entorno = EntornoUsuarios(sesion_real)
    juan = _vendedor(entorno)
    usuario_id, nombre = entorno.crear_usuario(entorno.crear_rol("Cobrador", VENDER | COBRAR))
    sin_permiso = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    (uno,) = _clientes(entorno, 1)

    por_rest = _asignar(entorno, cliente_http, sin_permiso, [uno], juan)
    por_lote = cliente_http.post(
        URL_LOTE,
        json={
            "items": [
                {
                    "operation_id": str(uuid4()),
                    "tipo": "CLIENTE_VENDEDOR_ASIGNAR",
                    "version": 1,
                    "modo": "ONLINE",
                    "usuario_id": str(usuario_id),
                    "dispositivo_id": str(sin_permiso.dispositivo_id),
                    "occurred_at": "2026-10-28T12:00:00Z",
                    "secuencia": 1,
                    "app_version": "1.0.0",
                    "contenido": {"cliente_ids": [str(uno)], "vendedor_id": str(juan)},
                }
            ]
        },
        headers=sin_permiso.headers,
    )

    assert por_rest.status_code == 403
    assert por_rest.json()["codigo"] == "PERMISO_REQUERIDO"
    (resultado,) = por_lote.json()["resultados"]
    assert resultado["error_codigo"] == "PERMISO_REQUERIDO"
    _sin_cambios(entorno, [uno])


def test_el_doble_envio_devuelve_el_resultado_original_sin_auditorias_nuevas(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06."""
    entorno = EntornoUsuarios(sesion_real)
    gestor = _gestor(entorno, cliente_http)
    juan = _vendedor(entorno)
    clientes = _clientes(entorno, 2)
    operation_id = uuid4()

    primera = _asignar(entorno, cliente_http, gestor, clientes, juan, operation_id)
    segunda = _asignar(entorno, cliente_http, gestor, clientes, juan, operation_id)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    assert len(entorno.auditorias("ASIGNAR_VENDEDOR_CLIENTE")) == 2


def test_el_mismo_operation_id_con_otro_vendedor_es_comando_inconsistente(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06."""
    entorno = EntornoUsuarios(sesion_real)
    gestor = _gestor(entorno, cliente_http)
    juan = _vendedor(entorno)
    pedro = _vendedor(entorno)
    (uno,) = _clientes(entorno, 1)
    operation_id = uuid4()
    _asignar(entorno, cliente_http, gestor, [uno], juan, operation_id)

    respuesta = _asignar(entorno, cliente_http, gestor, [uno], pedro, operation_id)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "COMANDO_INCONSISTENTE"
    assert _vendedor_de(entorno, uno) == juan


def test_una_falla_en_la_auditoria_no_deja_clientes_asignados(
    cliente_http: TestClient, sesion_real: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-01: todo o nada."""
    from app.modules.identidad import service as identidad_service

    entorno = EntornoUsuarios(sesion_real)
    gestor = _gestor(entorno, cliente_http)
    juan = _vendedor(entorno)
    clientes = _clientes(entorno, 2)
    original = identidad_service.registrar_auditoria
    llamadas: list[str] = []

    def _falla_en_la_segunda(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("accion") == "ASIGNAR_VENDEDOR_CLIENTE":
            llamadas.append("x")
            if len(llamadas) == 2:
                raise RuntimeError("falla inyectada")
        return original(*args, **kwargs)

    monkeypatch.setattr(identidad_service, "registrar_auditoria", _falla_en_la_segunda)
    sin_propagar = TestClient(cliente_http.app, raise_server_exceptions=False)

    respuesta = sin_propagar.post(
        URL,
        json={"cliente_ids": [str(c) for c in clientes], "vendedor_id": str(juan)},
        headers={**gestor.headers, "Operation-Id": str(uuid4())},
    )
    monkeypatch.undo()

    assert respuesta.status_code == 500
    _sin_cambios(entorno, clientes)
