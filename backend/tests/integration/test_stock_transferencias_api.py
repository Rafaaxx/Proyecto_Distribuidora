"""Change 14, tarea 5.3: `POST /api/v1/stock/transferencias` por HTTP contra PostgreSQL real
(spec `stock/transferencias`, `design.md` D1, D6, D9).

Mismo arnés que `test_stock_api.py` (login real, motor propio de la aplicación). La
cobertura por escenario del comando está en `test_stock_transferir.py`; acá se prueba el
contrato de la ruta: `Operation-Id` obligatorio, esquema estricto, Problem Details con el
índice de la línea, 201 con la transferencia y sus saldos, permisos y aislamiento.

Reglas citadas: STK-05, STK-07, INV-03, INV-04, INV-06, INV-15, INV-21, SEG-06, TR-07.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_motivo_sql, crear_ubicacion_sql, desactivar_producto_sql
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    Entorno,
    _con_op,
    _contar,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)

from app.core.clock import FixedClock
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeMovimiento

URL = "/api/v1/stock/transferencias"

TRANSFERIR = frozenset({"TRANSFERIR_STOCK"})
ADMINISTRADOR = frozenset({"TRANSFERIR_STOCK", "PERMITIR_STOCK_NEGATIVO", "VER_COSTOS"})


class EntornoConCamioneta(Entorno):
    """El `Entorno` de `test_stock_api.py` más una camioneta vacía."""

    camioneta_id: UUID


def _preparar(sesion: Session, permisos: frozenset[str] = TRANSFERIR) -> EntornoConCamioneta:
    """Vino A (120 a 1050) y Cerveza B (40 a 400) en el depósito y una camioneta vacía."""
    entorno = EntornoConCamioneta(sesion, permisos=permisos)
    entorno.sembrar(entorno.producto_id, 120, "1050")
    entorno.sembrar(entorno.otro_producto_id, 40, "400")
    entorno.camioneta_id = crear_ubicacion_sql(
        sesion, entorno.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
    )
    return entorno


def _cuerpo(
    entorno: EntornoConCamioneta, lineas: list[tuple[UUID, object]] | None = None, **cambios: object
) -> dict[str, object]:
    cuerpo: dict[str, object] = {
        "ubicacion_origen_id": str(entorno.deposito_id),
        "ubicacion_destino_id": str(entorno.camioneta_id),
        "lineas": [
            {"producto_id": str(producto_id), "cantidad_base": cantidad}
            for producto_id, cantidad in (
                lineas if lineas is not None else [(entorno.producto_id, 48)]
            )
        ],
    }
    cuerpo.update(cambios)
    return cuerpo


def _saldo(sesion: Session, entorno: Entorno, producto_id: UUID, ubicacion_id: UUID) -> int:
    sesion.rollback()
    return int(
        sesion.scalar(
            text(
                "select coalesce(sum(cantidad_base), 0) from stock_saldo where "
                "organizacion_id = :o and producto_id = :p and ubicacion_id = :u"
            ),
            {"o": entorno.org, "p": producto_id, "u": ubicacion_id},
        )
        or 0
    )


def test_sin_operation_id_se_rechaza_con_400(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(entorno), headers=headers)

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


def test_la_carga_de_la_camioneta_responde_201_con_la_transferencia_y_los_saldos(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(entorno), headers=_con_op(headers))

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    UUID(cuerpo["id"])
    assert cuerpo["estado"] == "CONFIRMADA"
    assert cuerpo["ubicacion_origen_id"] == str(entorno.deposito_id)
    assert cuerpo["ubicacion_destino_id"] == str(entorno.camioneta_id)
    assert cuerpo["observacion"] is None
    assert cuerpo["lineas"] == [
        {
            "producto_id": str(entorno.producto_id),
            "cantidad_base": 48,
            "saldo_origen": 72,
            "saldo_destino": 48,
        }
    ]
    assert cuerpo["observaciones"] == []
    assert "organizacion_id" not in cuerpo
    assert "costo" not in str(cuerpo)
    assert _contar(sesion, "transferencia", entorno.org) == 1
    assert _contar(sesion, "transferencia_linea", entorno.org) == 1


def test_el_reenvio_con_el_mismo_operation_id_devuelve_lo_mismo_sin_duplicar(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-06."""
    entorno = _preparar(sesion)
    headers = _con_op(entorno.confirmar_y_entrar(cliente))

    primera = cliente.post(URL, json=_cuerpo(entorno), headers=headers)
    segunda = cliente.post(URL, json=_cuerpo(entorno), headers=headers)

    assert primera.status_code == segunda.status_code == 201
    assert primera.json() == segunda.json()
    assert _contar(sesion, "transferencia", entorno.org) == 1
    assert _saldo(sesion, entorno, entorno.producto_id, entorno.deposito_id) == 72


def test_el_mismo_operation_id_con_otro_contenido_es_comando_inconsistente(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    headers = _con_op(entorno.confirmar_y_entrar(cliente))
    cliente.post(URL, json=_cuerpo(entorno), headers=headers)

    segunda = cliente.post(URL, json=_cuerpo(entorno, [(entorno.producto_id, 5)]), headers=headers)

    assert segunda.status_code == 409
    assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"


def test_una_cantidad_fraccionaria_es_422_de_validacion_sin_efectos(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-04: `1.5` no es una cantidad."""
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL, json=_cuerpo(entorno, [(entorno.producto_id, 1.5)]), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert _contar(sesion, "transferencia", entorno.org) == 0


def test_una_cantidad_cero_es_cantidad_invalida_con_el_indice_de_su_linea(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL,
        json=_cuerpo(entorno, [(entorno.producto_id, 10), (entorno.otro_producto_id, 0)]),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422
    problema = respuesta.json()
    assert problema["codigo"] == "CANTIDAD_INVALIDA"
    assert problema["linea"] == 1
    assert _contar(sesion, "transferencia", entorno.org) == 0


def test_origen_y_destino_iguales_es_ubicaciones_iguales(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL,
        json=_cuerpo(entorno, ubicacion_destino_id=str(entorno.deposito_id)),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "UBICACIONES_IGUALES"


def test_lineas_vacias_y_producto_repetido(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    vacias = cliente.post(URL, json=_cuerpo(entorno, lineas=[]), headers=_con_op(headers))
    repetido = cliente.post(
        URL,
        json=_cuerpo(entorno, [(entorno.producto_id, 1), (entorno.producto_id, 2)]),
        headers=_con_op(headers),
    )

    assert (vacias.status_code, vacias.json()["codigo"]) == (422, "LINEAS_INVALIDAS")
    assert (repetido.status_code, repetido.json()["codigo"]) == (422, "PRODUCTO_REPETIDO")
    assert repetido.json()["linea"] == 1


def test_el_cuerpo_no_admite_la_organizacion(cliente: TestClient, sesion: Session) -> None:
    """INV-21, TR-08: `organizacion_id` sale del token."""
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL, json=_cuerpo(entorno, organizacion_id=str(uuid4())), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422


def test_sin_transferir_stock_responde_403_sin_efectos(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=frozenset({"AJUSTAR_STOCK"}))
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(entorno), headers=_con_op(headers))

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
    assert _contar(sesion, "transferencia", entorno.org) == 0


def test_saldo_insuficiente_sin_permiso_es_409_con_la_linea_que_no_alcanza(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL,
        json=_cuerpo(entorno, [(entorno.producto_id, 10), (entorno.otro_producto_id, 41)]),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 409
    problema = respuesta.json()
    assert problema["codigo"] == "STOCK_INSUFICIENTE"
    assert problema["linea"] == 1
    # Todo o nada: la primera línea tampoco se aplicó.
    assert _saldo(sesion, entorno, entorno.producto_id, entorno.deposito_id) == 120
    assert _contar(sesion, "transferencia", entorno.org) == 0


def test_saldo_insuficiente_con_permiso_deja_negativo_y_lo_informa(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=ADMINISTRADOR)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL, json=_cuerpo(entorno, [(entorno.otro_producto_id, 52)]), headers=_con_op(headers)
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["lineas"][0]["saldo_origen"] == -12
    assert cuerpo["lineas"][0]["saldo_destino"] == 52
    assert cuerpo["observaciones"] == ["STOCK_NEGATIVO"]


def test_un_producto_inactivo_es_409_con_la_linea(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion)
    desactivar_producto_sql(sesion, entorno.org, entorno.otro_producto_id)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL,
        json=_cuerpo(entorno, [(entorno.producto_id, 1), (entorno.otro_producto_id, 1)]),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "PRODUCTO_INACTIVO"
    assert respuesta.json()["linea"] == 1


def test_ubicacion_o_producto_de_otra_organizacion_es_404(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21, SEG-07."""
    entorno = _preparar(sesion)
    ajena = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    destino_ajeno = cliente.post(
        URL,
        json=_cuerpo(entorno, ubicacion_destino_id=str(ajena.camioneta_id)),
        headers=_con_op(headers),
    )
    producto_ajeno = cliente.post(
        URL, json=_cuerpo(entorno, [(ajena.producto_id, 1)]), headers=_con_op(headers)
    )

    assert destino_ajeno.status_code == 404
    assert producto_ajeno.status_code == 404
    assert _saldo(sesion, ajena, ajena.producto_id, ajena.deposito_id) == 120


# --- anulación (change 14, tarea 9.6: TR-06; `design.md` D5, D5.4) --------------------------

ANULADORA = frozenset({"TRANSFERIR_STOCK", "ANULAR_TRANSFERENCIA"})
ADMINISTRADOR_CON_ANULACION = frozenset(
    {"TRANSFERIR_STOCK", "ANULAR_TRANSFERENCIA", "PERMITIR_STOCK_NEGATIVO"}
)
AHORA = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def _url_anulacion(transferencia_id: object) -> str:
    return f"{URL}/{transferencia_id}/anulacion"


def _transferir(
    cliente: TestClient,
    headers: dict[str, str],
    entorno: EntornoConCamioneta,
    cantidad: int = 60,
) -> str:
    respuesta = cliente.post(
        URL, json=_cuerpo(entorno, [(entorno.producto_id, cantidad)]), headers=_con_op(headers)
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["id"])


def _motivo_de_anulacion(sesion: Session, entorno: Entorno, *, activo: bool = True) -> UUID:
    motivo_id = crear_motivo_sql(
        sesion, entorno.org, ambito="ANULACION_TRANSFERENCIA", activo=activo
    )
    sesion.commit()
    return motivo_id


def _vender_en_la_camioneta(sesion: Session, entorno: EntornoConCamioneta, cantidad: int) -> None:
    stock_service.registrar_movimientos(
        entorno.org,
        sesion,
        FixedClock(AHORA),
        lineas=[
            LineaDeMovimiento(
                entorno.producto_id,
                entorno.camioneta_id,
                -cantidad,
                "VENTA",
                None,
                "VENTA",
                uuid4(),
            )
        ],
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        operation_id=uuid4(),
        occurred_at=AHORA,
    )
    sesion.commit()


def test_anular_sin_operation_id_se_rechaza_con_400(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    transferencia_id = _transferir(cliente, headers, entorno)

    respuesta = cliente.post(
        _url_anulacion(transferencia_id), json={"motivo_id": str(motivo)}, headers=headers
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


def test_anular_responde_200_con_la_transferencia_anulada_y_los_saldos(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    transferencia_id = _transferir(cliente, headers, entorno)

    respuesta = cliente.post(
        _url_anulacion(transferencia_id),
        json={"motivo_id": str(motivo)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id"] == transferencia_id
    assert cuerpo["estado"] == "ANULADA"
    assert cuerpo["ubicacion_origen_id"] == str(entorno.deposito_id)
    assert cuerpo["ubicacion_destino_id"] == str(entorno.camioneta_id)
    assert cuerpo["anulacion"]["motivo_id"] == str(motivo)
    assert cuerpo["anulacion"]["anulada_por_id"] == str(entorno.usuario_id)
    assert datetime.fromisoformat(cuerpo["anulacion"]["anulada_en"]).tzinfo is not None
    assert cuerpo["lineas"] == [
        {
            "producto_id": str(entorno.producto_id),
            "cantidad_base": 60,
            "saldo_origen": 120,
            "saldo_destino": 0,
        }
    ]
    assert cuerpo["observaciones"] == []
    assert "organizacion_id" not in cuerpo
    assert "costo" not in str(cuerpo)
    assert _saldo(sesion, entorno, entorno.producto_id, entorno.camioneta_id) == 0
    assert _saldo(sesion, entorno, entorno.producto_id, entorno.deposito_id) == 120


def test_el_reenvio_de_la_anulacion_devuelve_lo_mismo_sin_nuevos_movimientos(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-06."""
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    transferencia_id = _transferir(cliente, headers, entorno)
    con_operacion = _con_op(headers)
    cuerpo = {"motivo_id": str(motivo)}

    primera = cliente.post(_url_anulacion(transferencia_id), json=cuerpo, headers=con_operacion)
    segunda = cliente.post(_url_anulacion(transferencia_id), json=cuerpo, headers=con_operacion)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    # dos de stock inicial, dos de la ida y dos de la vuelta
    assert _contar(sesion, "stock_movimiento", entorno.org) == 2 + 2 + 2


def test_la_segunda_anulacion_es_409_transferencia_ya_anulada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    transferencia_id = _transferir(cliente, headers, entorno)
    cuerpo = {"motivo_id": str(motivo)}
    cliente.post(_url_anulacion(transferencia_id), json=cuerpo, headers=_con_op(headers))

    segunda = cliente.post(_url_anulacion(transferencia_id), json=cuerpo, headers=_con_op(headers))

    assert segunda.status_code == 409
    assert segunda.json()["codigo"] == "TRANSFERENCIA_YA_ANULADA"


def test_motivo_de_otro_ambito_o_inactivo_es_422_y_ajeno_o_inexistente_es_404(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    ajena = _preparar(sesion)
    de_ajuste = crear_motivo_sql(sesion, entorno.org)
    inactivo = _motivo_de_anulacion(sesion, entorno, activo=False)
    de_la_otra = _motivo_de_anulacion(sesion, ajena)
    headers = entorno.confirmar_y_entrar(cliente)
    transferencia_id = _transferir(cliente, headers, entorno)

    def anular(motivo_id: UUID) -> tuple[int, str]:
        respuesta = cliente.post(
            _url_anulacion(transferencia_id),
            json={"motivo_id": str(motivo_id)},
            headers=_con_op(headers),
        )
        return respuesta.status_code, respuesta.json()["codigo"]

    assert anular(de_ajuste) == (422, "MOTIVO_INVALIDO")
    assert anular(inactivo) == (422, "MOTIVO_INVALIDO")
    assert anular(de_la_otra)[0] == 404
    assert anular(uuid4())[0] == 404
    assert _saldo(sesion, entorno, entorno.producto_id, entorno.camioneta_id) == 60


def test_anular_una_transferencia_de_otra_organizacion_o_inexistente_es_404(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21, SEG-07."""
    entorno = _preparar(sesion)
    ajena = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers_ajena = ajena.confirmar_y_entrar(cliente)
    de_la_otra = _transferir(cliente, headers_ajena, ajena)
    headers = entorno.confirmar_y_entrar(cliente)

    for transferencia_id in (de_la_otra, str(uuid4())):
        respuesta = cliente.post(
            _url_anulacion(transferencia_id),
            json={"motivo_id": str(motivo)},
            headers=_con_op(headers),
        )
        assert respuesta.status_code == 404

    assert _saldo(sesion, ajena, ajena.producto_id, ajena.camioneta_id) == 60


def test_el_cuerpo_exige_el_motivo_y_no_admite_la_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    transferencia_id = _transferir(cliente, headers, entorno)

    sin_motivo = cliente.post(_url_anulacion(transferencia_id), json={}, headers=_con_op(headers))
    con_organizacion = cliente.post(
        _url_anulacion(transferencia_id),
        json={"motivo_id": str(motivo), "organizacion_id": str(uuid4())},
        headers=_con_op(headers),
    )

    assert sin_motivo.status_code == con_organizacion.status_code == 422
    assert _saldo(sesion, entorno, entorno.producto_id, entorno.camioneta_id) == 60


def test_la_transferencia_de_otro_usuario_es_403_sin_anular_ajenas_y_200_con_el_permiso(
    cliente: TestClient, sesion: Session
) -> None:
    """D5 punto 5: 403 `PERMISO_REQUERIDO` (el recurso existe y se puede leer; 404 es para lo
    de otra organización)."""
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    entorno.agregar_usuario(TRANSFERIR, "pedro")
    administracion_id = entorno.agregar_usuario(ANULADORA, "administracion")
    headers = entorno.confirmar_y_entrar(cliente)
    transferencia_id = _transferir(cliente, headers, entorno)
    cuerpo = {"motivo_id": str(motivo)}

    de_pedro = entorno.entrar_como(cliente, "pedro")
    rechazada = cliente.post(
        _url_anulacion(transferencia_id), json=cuerpo, headers=_con_op(de_pedro)
    )
    de_administracion = entorno.entrar_como(cliente, "administracion")
    aceptada = cliente.post(
        _url_anulacion(transferencia_id), json=cuerpo, headers=_con_op(de_administracion)
    )

    assert rechazada.status_code == 403
    assert rechazada.json()["codigo"] == "PERMISO_REQUERIDO"
    assert aceptada.status_code == 200, aceptada.text
    assert aceptada.json()["anulacion"]["anulada_por_id"] == str(administracion_id)


def test_anular_sin_transferir_stock_es_403(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    entorno.agregar_usuario(frozenset({"ANULAR_TRANSFERENCIA"}), "auditor")
    headers = entorno.confirmar_y_entrar(cliente)
    transferencia_id = _transferir(cliente, headers, entorno)

    respuesta = cliente.post(
        _url_anulacion(transferencia_id),
        json={"motivo_id": str(motivo)},
        headers=_con_op(entorno.entrar_como(cliente, "auditor")),
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
    assert _saldo(sesion, entorno, entorno.producto_id, entorno.camioneta_id) == 60


def test_stock_insuficiente_en_el_destino_es_409_con_la_linea(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    transferencia_id = _transferir(cliente, headers, entorno)
    _vender_en_la_camioneta(sesion, entorno, 10)

    respuesta = cliente.post(
        _url_anulacion(transferencia_id),
        json={"motivo_id": str(motivo)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "STOCK_INSUFICIENTE"
    assert respuesta.json()["linea"] == 0
    assert _saldo(sesion, entorno, entorno.producto_id, entorno.camioneta_id) == 50


def test_con_stock_negativo_permitido_responde_200_y_lo_informa(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=ADMINISTRADOR_CON_ANULACION)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    transferencia_id = _transferir(cliente, headers, entorno)
    _vender_en_la_camioneta(sesion, entorno, 10)

    respuesta = cliente.post(
        _url_anulacion(transferencia_id),
        json={"motivo_id": str(motivo)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["lineas"][0]["saldo_destino"] == -10
    assert respuesta.json()["observaciones"] == ["STOCK_NEGATIVO"]


def test_un_producto_o_una_ubicacion_inactivos_son_409_sin_efectos(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    transferencia_id = _transferir(cliente, headers, entorno)
    cuerpo = {"motivo_id": str(motivo)}

    desactivar_producto_sql(sesion, entorno.org, entorno.producto_id)
    sesion.commit()
    por_producto = cliente.post(
        _url_anulacion(transferencia_id), json=cuerpo, headers=_con_op(headers)
    )
    sesion.execute(
        text("UPDATE producto SET activo = true WHERE id = :p"), {"p": entorno.producto_id}
    )
    sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE id = :u"), {"u": entorno.deposito_id}
    )
    sesion.commit()
    por_ubicacion = cliente.post(
        _url_anulacion(transferencia_id), json=cuerpo, headers=_con_op(headers)
    )

    assert (por_producto.status_code, por_producto.json()["codigo"]) == (409, "PRODUCTO_INACTIVO")
    assert por_producto.json()["linea"] == 0
    assert (por_ubicacion.status_code, por_ubicacion.json()["codigo"]) == (
        409,
        "UBICACION_INACTIVA",
    )
    assert _saldo(sesion, entorno, entorno.producto_id, entorno.camioneta_id) == 60
