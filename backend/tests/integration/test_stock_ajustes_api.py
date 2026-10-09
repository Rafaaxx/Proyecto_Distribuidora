"""Change 14, tarea 6.3: `POST /api/v1/stock/ajustes` por HTTP contra PostgreSQL real (spec
`stock/ajustes-de-stock`, `design.md` D1, D3, D6, D9).

Mismo arnés que `test_stock_transferencias_api.py`. La cobertura por escenario del comando
está en `test_stock_ajustar.py`; acá se prueba el contrato de la ruta: `Operation-Id`
obligatorio, esquema estricto, Problem Details con el índice de la línea, 201 con el ajuste,
su estado y los saldos resultantes, `costo_unitario` como string solo con `VER_COSTOS`,
permisos y aislamiento.

Reglas citadas: STK-05, STK-08, CST-12, INV-03, INV-04, INV-06, INV-21, SEG-06, ADR-036, TR-07.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_motivo_sql, crear_producto_sql, desactivar_producto_sql
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

URL = "/api/v1/stock/ajustes"

AJUSTAR = frozenset({"AJUSTAR_STOCK"})
ADMINISTRADOR = frozenset({"AJUSTAR_STOCK", "PERMITIR_STOCK_NEGATIVO", "VER_COSTOS"})


class EntornoConMotivo(Entorno):
    """El `Entorno` de `test_stock_api.py` más un motivo de ajuste."""

    motivo_id: UUID


def _preparar(sesion: Session, permisos: frozenset[str] = AJUSTAR) -> EntornoConMotivo:
    """Vino A (120 a 1050) y Cerveza B (40 a 400) en el depósito y un motivo de ajuste."""
    entorno = EntornoConMotivo(sesion, permisos=permisos)
    entorno.sembrar(entorno.producto_id, 120, "1050")
    entorno.sembrar(entorno.otro_producto_id, 40, "400")
    entorno.motivo_id = crear_motivo_sql(sesion, entorno.org)
    return entorno


def _cuerpo(
    entorno: EntornoConMotivo,
    lineas: list[tuple[UUID, object]] | None = None,
    **cambios: object,
) -> dict[str, object]:
    cuerpo: dict[str, object] = {
        "ubicacion_id": str(entorno.deposito_id),
        "motivo_id": str(entorno.motivo_id),
        "lineas": [
            {"producto_id": str(producto_id), "cantidad_base": cantidad}
            for producto_id, cantidad in (
                lineas if lineas is not None else [(entorno.producto_id, -6)]
            )
        ],
    }
    cuerpo.update(cambios)
    return cuerpo


def _saldo(sesion: Session, entorno: Entorno, producto_id: UUID) -> int:
    sesion.rollback()
    return int(
        sesion.scalar(
            text(
                "select coalesce(sum(cantidad_base), 0) from stock_saldo where "
                "organizacion_id = :o and producto_id = :p and ubicacion_id = :u"
            ),
            {"o": entorno.org, "p": producto_id, "u": entorno.deposito_id},
        )
        or 0
    )


def test_sin_operation_id_se_rechaza_con_400(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(entorno), headers=headers)

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


def test_la_rotura_responde_201_con_el_ajuste_los_saldos_y_el_costo_con_ver_costos(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-03: el costo viaja como string con 6 decimales."""
    entorno = _preparar(sesion, permisos=ADMINISTRADOR)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL, json=_cuerpo(entorno, observacion="rota"), headers=_con_op(headers)
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    UUID(cuerpo["id"])
    assert cuerpo["estado"] == "CONFIRMADA"
    assert cuerpo["ubicacion_id"] == str(entorno.deposito_id)
    assert cuerpo["motivo_id"] == str(entorno.motivo_id)
    assert cuerpo["observacion"] == "rota"
    assert cuerpo["lineas"] == [
        {
            "producto_id": str(entorno.producto_id),
            "cantidad_base": -6,
            "saldo": 114,
            "costo_unitario": "1050.000000",
        }
    ]
    assert "organizacion_id" not in cuerpo
    assert _contar(sesion, "ajuste_stock", entorno.org) == 1
    assert _contar(sesion, "ajuste_stock_linea", entorno.org) == 1


def test_sin_ver_costos_la_respuesta_no_trae_ningun_campo_de_costo(
    cliente: TestClient, sesion: Session
) -> None:
    """ADR-036: la clave desaparece, no viaja ni como `null`."""
    entorno = _preparar(sesion, permisos=AJUSTAR)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(entorno), headers=_con_op(headers))

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["lineas"] == [
        {"producto_id": str(entorno.producto_id), "cantidad_base": -6, "saldo": 114}
    ]
    assert "costo" not in respuesta.text


def test_el_reenvio_con_el_mismo_operation_id_devuelve_lo_mismo_sin_duplicar(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-06."""
    entorno = _preparar(sesion, permisos=ADMINISTRADOR)
    headers = _con_op(entorno.confirmar_y_entrar(cliente))

    primera = cliente.post(URL, json=_cuerpo(entorno), headers=headers)
    segunda = cliente.post(URL, json=_cuerpo(entorno), headers=headers)

    assert primera.status_code == segunda.status_code == 201
    assert primera.json() == segunda.json()
    assert _contar(sesion, "ajuste_stock", entorno.org) == 1
    assert _saldo(sesion, entorno, entorno.producto_id) == 114


def test_el_mismo_operation_id_con_otro_contenido_es_comando_inconsistente(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    headers = _con_op(entorno.confirmar_y_entrar(cliente))
    cliente.post(URL, json=_cuerpo(entorno), headers=headers)

    segunda = cliente.post(URL, json=_cuerpo(entorno, [(entorno.producto_id, -5)]), headers=headers)

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
    assert _contar(sesion, "ajuste_stock", entorno.org) == 0


def test_una_cantidad_cero_es_cantidad_invalida_con_el_indice_de_su_linea(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL,
        json=_cuerpo(entorno, [(entorno.producto_id, 3), (entorno.otro_producto_id, 0)]),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "CANTIDAD_INVALIDA"
    assert respuesta.json()["linea"] == 1
    assert _contar(sesion, "ajuste_stock", entorno.org) == 0


def test_lineas_vacias_y_producto_repetido(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    vacias = cliente.post(URL, json=_cuerpo(entorno, lineas=[]), headers=_con_op(headers))
    repetido = cliente.post(
        URL,
        json=_cuerpo(entorno, [(entorno.producto_id, 1), (entorno.producto_id, -2)]),
        headers=_con_op(headers),
    )

    assert (vacias.status_code, vacias.json()["codigo"]) == (422, "LINEAS_INVALIDAS")
    assert (repetido.status_code, repetido.json()["codigo"]) == (422, "PRODUCTO_REPETIDO")
    assert repetido.json()["linea"] == 1


def test_observacion_de_501_caracteres_es_422(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL, json=_cuerpo(entorno, observacion="x" * 501), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "OBSERVACION_INVALIDA"


def test_el_cuerpo_no_admite_la_organizacion(cliente: TestClient, sesion: Session) -> None:
    """INV-21, TR-08: `organizacion_id` sale del token."""
    entorno = _preparar(sesion)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL, json=_cuerpo(entorno, organizacion_id=str(uuid4())), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422


def test_sin_ajustar_stock_responde_403_sin_efectos(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion, permisos=frozenset({"TRANSFERIR_STOCK"}))
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(entorno), headers=_con_op(headers))

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
    assert _contar(sesion, "ajuste_stock", entorno.org) == 0


def test_saldo_insuficiente_es_409_con_la_linea_incluso_con_permiso_de_negativo(
    cliente: TestClient, sesion: Session
) -> None:
    """D1 = B: `PERMITIR_STOCK_NEGATIVO` no alcanza al ajuste."""
    entorno = _preparar(sesion, permisos=ADMINISTRADOR)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL,
        json=_cuerpo(entorno, [(entorno.producto_id, -10), (entorno.otro_producto_id, -41)]),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 409
    problema = respuesta.json()
    assert problema["codigo"] == "STOCK_INSUFICIENTE"
    assert problema["linea"] == 1
    assert _saldo(sesion, entorno, entorno.producto_id) == 120  # todo o nada
    assert _contar(sesion, "ajuste_stock", entorno.org) == 0


def test_motivo_invalido_es_422_y_motivo_ajeno_es_404(cliente: TestClient, sesion: Session) -> None:
    entorno = _preparar(sesion)
    ajena = _preparar(sesion)
    sesion.execute(
        text("UPDATE motivo SET ambito = 'ANULACION_COMPRA' WHERE id = :m"),
        {"m": entorno.motivo_id},
    )
    headers = entorno.confirmar_y_entrar(cliente)

    de_otro_ambito = cliente.post(URL, json=_cuerpo(entorno), headers=_con_op(headers))
    ajeno = cliente.post(
        URL, json=_cuerpo(entorno, motivo_id=str(ajena.motivo_id)), headers=_con_op(headers)
    )

    assert (de_otro_ambito.status_code, de_otro_ambito.json()["codigo"]) == (422, "MOTIVO_INVALIDO")
    assert ajeno.status_code == 404


def test_un_ajuste_positivo_de_un_producto_sin_costo_es_409(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    nuevo = crear_producto_sql(sesion, entorno.org, nombre="Sin costo")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(entorno, [(nuevo, 24)]), headers=_con_op(headers))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "PRODUCTO_SIN_COSTO"
    assert respuesta.json()["linea"] == 0


# --- anulación (change 14, tarea 9.6: TR-06; `design.md` D5) ---------------------------------

AHORA = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def _url_anulacion(ajuste_id: object) -> str:
    return f"{URL}/{ajuste_id}/anulacion"


def _ajustar(
    cliente: TestClient,
    headers: dict[str, str],
    entorno: EntornoConMotivo,
    lineas: list[tuple[UUID, object]] | None = None,
) -> str:
    respuesta = cliente.post(URL, json=_cuerpo(entorno, lineas), headers=_con_op(headers))
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["id"])


def _motivo_de_anulacion(sesion: Session, entorno: Entorno, *, activo: bool = True) -> UUID:
    motivo_id = crear_motivo_sql(sesion, entorno.org, ambito="ANULACION_AJUSTE", activo=activo)
    sesion.commit()
    return motivo_id


def _sacar_del_deposito(sesion: Session, entorno: EntornoConMotivo, cantidad: int) -> None:
    stock_service.registrar_movimientos(
        entorno.org,
        sesion,
        FixedClock(AHORA),
        lineas=[
            LineaDeMovimiento(
                entorno.producto_id,
                entorno.deposito_id,
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
    ajuste_id = _ajustar(cliente, headers, entorno)

    respuesta = cliente.post(
        _url_anulacion(ajuste_id), json={"motivo_id": str(motivo)}, headers=headers
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


def test_anular_responde_200_con_el_ajuste_anulado_el_saldo_y_el_costo_con_ver_costos(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-03: el costo de cada línea viaja como string con 6 decimales."""
    entorno = _preparar(sesion, permisos=ADMINISTRADOR)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    ajuste_id = _ajustar(cliente, headers, entorno)

    respuesta = cliente.post(
        _url_anulacion(ajuste_id), json={"motivo_id": str(motivo)}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id"] == ajuste_id
    assert cuerpo["estado"] == "ANULADA"
    assert cuerpo["ubicacion_id"] == str(entorno.deposito_id)
    assert cuerpo["motivo_id"] == str(entorno.motivo_id)  # el motivo del ajuste no cambia
    assert cuerpo["anulacion"]["motivo_id"] == str(motivo)
    assert cuerpo["anulacion"]["anulado_por_id"] == str(entorno.usuario_id)
    assert datetime.fromisoformat(cuerpo["anulacion"]["anulado_en"]).tzinfo is not None
    assert cuerpo["lineas"] == [
        {
            "producto_id": str(entorno.producto_id),
            "cantidad_base": -6,
            "saldo": 120,
            "costo_unitario": "1050.000000",
        }
    ]
    assert cuerpo["observaciones"] == []
    assert "organizacion_id" not in cuerpo
    assert _saldo(sesion, entorno, entorno.producto_id) == 120


def test_sin_ver_costos_la_respuesta_de_la_anulacion_no_trae_costos(
    cliente: TestClient, sesion: Session
) -> None:
    """ADR-036: la clave desaparece, no viaja ni como `null`."""
    entorno = _preparar(sesion, permisos=AJUSTAR)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    ajuste_id = _ajustar(cliente, headers, entorno)

    respuesta = cliente.post(
        _url_anulacion(ajuste_id), json={"motivo_id": str(motivo)}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["lineas"] == [
        {"producto_id": str(entorno.producto_id), "cantidad_base": -6, "saldo": 120}
    ]
    assert "costo" not in respuesta.text


def test_el_reenvio_de_la_anulacion_devuelve_lo_mismo_sin_nuevos_movimientos(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-06."""
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    ajuste_id = _ajustar(cliente, headers, entorno)
    con_operacion = _con_op(headers)
    cuerpo = {"motivo_id": str(motivo)}

    primera = cliente.post(_url_anulacion(ajuste_id), json=cuerpo, headers=con_operacion)
    segunda = cliente.post(_url_anulacion(ajuste_id), json=cuerpo, headers=con_operacion)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    # dos de stock inicial, uno del ajuste y uno de su anulación
    assert _contar(sesion, "stock_movimiento", entorno.org) == 2 + 1 + 1


def test_la_segunda_anulacion_es_409_ajuste_ya_anulado(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    ajuste_id = _ajustar(cliente, headers, entorno)
    cuerpo = {"motivo_id": str(motivo)}
    cliente.post(_url_anulacion(ajuste_id), json=cuerpo, headers=_con_op(headers))

    segunda = cliente.post(_url_anulacion(ajuste_id), json=cuerpo, headers=_con_op(headers))

    assert segunda.status_code == 409
    assert segunda.json()["codigo"] == "AJUSTE_YA_ANULADO"


def test_motivo_de_otro_ambito_o_inactivo_es_422_y_ajeno_o_inexistente_es_404(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    ajena = _preparar(sesion)
    inactivo = _motivo_de_anulacion(sesion, entorno, activo=False)
    de_la_otra = _motivo_de_anulacion(sesion, ajena)
    headers = entorno.confirmar_y_entrar(cliente)
    ajuste_id = _ajustar(cliente, headers, entorno)

    def anular(motivo_id: UUID) -> tuple[int, str]:
        respuesta = cliente.post(
            _url_anulacion(ajuste_id), json={"motivo_id": str(motivo_id)}, headers=_con_op(headers)
        )
        return respuesta.status_code, respuesta.json()["codigo"]

    assert anular(entorno.motivo_id) == (422, "MOTIVO_INVALIDO")  # es de AJUSTE_STOCK
    assert anular(inactivo) == (422, "MOTIVO_INVALIDO")
    assert anular(de_la_otra)[0] == 404
    assert anular(uuid4())[0] == 404
    assert _saldo(sesion, entorno, entorno.producto_id) == 114


def test_anular_un_ajuste_de_otra_organizacion_o_inexistente_es_404(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21, SEG-07."""
    entorno = _preparar(sesion)
    ajena = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    de_la_otra = _ajustar(cliente, ajena.confirmar_y_entrar(cliente), ajena)
    headers = entorno.confirmar_y_entrar(cliente)

    for ajuste_id in (de_la_otra, str(uuid4())):
        respuesta = cliente.post(
            _url_anulacion(ajuste_id), json={"motivo_id": str(motivo)}, headers=_con_op(headers)
        )
        assert respuesta.status_code == 404

    assert _saldo(sesion, ajena, ajena.producto_id) == 114


def test_el_cuerpo_exige_el_motivo_y_no_admite_la_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    ajuste_id = _ajustar(cliente, headers, entorno)

    sin_motivo = cliente.post(_url_anulacion(ajuste_id), json={}, headers=_con_op(headers))
    con_organizacion = cliente.post(
        _url_anulacion(ajuste_id),
        json={"motivo_id": str(motivo), "organizacion_id": str(uuid4())},
        headers=_con_op(headers),
    )

    assert sin_motivo.status_code == con_organizacion.status_code == 422
    assert _saldo(sesion, entorno, entorno.producto_id) == 114


def test_sin_ajustar_stock_es_403_aunque_pueda_transferir_y_el_ajuste_de_otro_se_anula(
    cliente: TestClient, sesion: Session
) -> None:
    """SEG-06; un ajuste lo anula cualquiera con `AJUSTAR_STOCK`, propio o ajeno (D5)."""
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    entorno.agregar_usuario(frozenset({"TRANSFERIR_STOCK"}), "vendedor")
    otra_id = entorno.agregar_usuario(AJUSTAR, "otra-administracion")
    headers = entorno.confirmar_y_entrar(cliente)
    ajuste_id = _ajustar(cliente, headers, entorno)
    cuerpo = {"motivo_id": str(motivo)}

    del_vendedor = cliente.post(
        _url_anulacion(ajuste_id),
        json=cuerpo,
        headers=_con_op(entorno.entrar_como(cliente, "vendedor")),
    )
    de_otra = cliente.post(
        _url_anulacion(ajuste_id),
        json=cuerpo,
        headers=_con_op(entorno.entrar_como(cliente, "otra-administracion")),
    )

    assert del_vendedor.status_code == 403
    assert del_vendedor.json()["codigo"] == "PERMISO_REQUERIDO"
    assert de_otra.status_code == 200, de_otra.text
    assert de_otra.json()["anulacion"]["anulado_por_id"] == str(otra_id)


def test_el_stock_ya_salio_sin_permiso_es_409_stock_insuficiente_con_la_linea(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    ajuste_id = _ajustar(cliente, headers, entorno, [(entorno.producto_id, 12)])  # 132
    _sacar_del_deposito(sesion, entorno, 127)  # quedan 5

    respuesta = cliente.post(
        _url_anulacion(ajuste_id), json={"motivo_id": str(motivo)}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "STOCK_INSUFICIENTE"
    assert respuesta.json()["linea"] == 0
    assert _saldo(sesion, entorno, entorno.producto_id) == 5


def test_el_stock_ya_salio_con_permiso_responde_200_y_lo_informa(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion, permisos=ADMINISTRADOR)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    ajuste_id = _ajustar(cliente, headers, entorno, [(entorno.producto_id, 12)])
    _sacar_del_deposito(sesion, entorno, 127)

    respuesta = cliente.post(
        _url_anulacion(ajuste_id), json={"motivo_id": str(motivo)}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["lineas"][0]["saldo"] == -7
    assert respuesta.json()["observaciones"] == ["STOCK_NEGATIVO"]


def test_un_producto_o_una_ubicacion_inactivos_son_409_sin_efectos(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    motivo = _motivo_de_anulacion(sesion, entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    ajuste_id = _ajustar(cliente, headers, entorno)
    cuerpo = {"motivo_id": str(motivo)}

    desactivar_producto_sql(sesion, entorno.org, entorno.producto_id)
    sesion.commit()
    por_producto = cliente.post(_url_anulacion(ajuste_id), json=cuerpo, headers=_con_op(headers))
    sesion.execute(
        text("UPDATE producto SET activo = true WHERE id = :p"), {"p": entorno.producto_id}
    )
    sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE id = :u"), {"u": entorno.deposito_id}
    )
    sesion.commit()
    por_ubicacion = cliente.post(_url_anulacion(ajuste_id), json=cuerpo, headers=_con_op(headers))

    assert (por_producto.status_code, por_producto.json()["codigo"]) == (409, "PRODUCTO_INACTIVO")
    assert por_producto.json()["linea"] == 0
    assert (por_ubicacion.status_code, por_ubicacion.json()["codigo"]) == (
        409,
        "UBICACION_INACTIVA",
    )
    assert _saldo(sesion, entorno, entorno.producto_id) == 114
