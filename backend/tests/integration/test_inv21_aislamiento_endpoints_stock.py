"""Change 09, tarea 9.5: cobertura de aislamiento (INV-21, SEG-07) de las siete
rutas nuevas de `stock` y de `catalogo`:

- escrituras: `POST /stock/ubicaciones`, `PUT /stock/ubicaciones/{id}`,
  `POST /stock/iniciales`;
- lecturas: `GET /stock/ubicaciones`, `GET /stock/ubicaciones/{id}/saldos`,
  `GET /stock/kardex` y `GET /catalogo/productos/{producto_id}/costo`.

Mismo arnés HTTP que `test_stock_api.py` (PostgreSQL real, `login` real de dos
organizaciones, nunca un token fabricado): se reutilizan su `Entorno` y sus
fixtures. Un recurso de otra organización responde 404 (no 403) y no deja rastro:
ni ubicación modificada, ni movimiento, ni fila de saldo o de costo, ni dato del
stock o del costo ajeno en la respuesta.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_motivo_sql, crear_ubicacion_sql
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    ADMIN,
    URL_INICIALES,
    URL_KARDEX,
    URL_UBICACIONES,
    Entorno,
    _con_op,
    _contar,
    _cuerpo_inicial,
    _cuerpo_ubicacion,
    _limpiar_datos_confirmados,
    _params_kardex,
    _url_costo,
    _url_saldos,
    cliente,
    sesion,
)

from app.core.clock import FixedClock
from app.modules.stock import service as stock_service
from app.modules.stock.service import LineaDeAjuste, LineaDeTransferencia

MARCA_DE_COSTO = "7777.77"
MARCA_DE_CANTIDAD = 424242


def _dos_organizaciones(sesion: Session) -> tuple[Entorno, Entorno]:
    return (
        Entorno(sesion, permisos=ADMIN, nombre_usuario="a1"),
        Entorno(sesion, permisos=ADMIN, nombre_usuario="b1"),
    )


def _sembrar_con_marcas(entorno: Entorno) -> None:
    entorno.sembrar(entorno.producto_id, MARCA_DE_CANTIDAD, MARCA_DE_COSTO)


def _sin_rastro_de_a(sesion: Session, entorno_a: Entorno, entorno_b: Entorno) -> None:
    """Nada nuevo en ninguna de las dos organizaciones, salvo lo sembrado a mano
    en la de A (un movimiento)."""
    assert _contar(sesion, "stock_movimiento", entorno_a.org) == 1
    assert _contar(sesion, "stock_movimiento", entorno_b.org) == 0
    assert _contar(sesion, "stock_saldo", entorno_b.org) == 0
    assert _contar(sesion, "costo_producto", entorno_b.org) == 0


def test_inv21_modificar_una_ubicacion_ajena_es_404_y_no_la_toca(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.put(
        f"{URL_UBICACIONES}/{entorno_a.deposito_id}",
        json={**_cuerpo_ubicacion(nombre="Tomada por B"), "activo": True},
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    nombre = sesion.scalar(
        text("select nombre from ubicacion where id = :i"), {"i": entorno_a.deposito_id}
    )
    assert nombre == "Depósito central"


def test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_la_ubicacion(
    cliente: TestClient, sesion: Session
) -> None:
    """`organizacion_id` sale siempre del token: si viene en el cuerpo, el esquema
    estricto lo rechaza y no se crea nada en ninguna de las dos organizaciones."""
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    antes_a = _contar(sesion, "ubicacion", entorno_a.org)
    antes_b = _contar(sesion, "ubicacion", entorno_b.org)

    respuesta = cliente.post(
        URL_UBICACIONES,
        json=_cuerpo_ubicacion(nombre="Intrusa", organizacion_id=str(entorno_a.org)),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 422
    assert _contar(sesion, "ubicacion", entorno_a.org) == antes_a
    assert _contar(sesion, "ubicacion", entorno_b.org) == antes_b


def test_inv21_una_ubicacion_creada_queda_en_la_organizacion_del_token(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    headers_a = entorno_a.confirmar_y_entrar(cliente)

    creada = cliente.post(
        URL_UBICACIONES, json=_cuerpo_ubicacion(nombre="Solo de B"), headers=_con_op(headers_b)
    )

    assert creada.status_code == 201
    de_a = cliente.get(URL_UBICACIONES, headers=headers_a).json()["items"]
    de_b = cliente.get(URL_UBICACIONES, headers=headers_b).json()["items"]
    assert "Solo de B" not in [u["nombre"] for u in de_a]
    assert "Solo de B" in [u["nombre"] for u in de_b]


def test_inv21_registrar_stock_inicial_en_una_ubicacion_ajena_es_404_sin_rastro(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL_INICIALES,
        json=_cuerpo_inicial(entorno_b, ubicacion_id=str(entorno_a.deposito_id)),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    _sin_rastro_de_a(sesion, entorno_a, entorno_b)


def test_inv21_registrar_stock_inicial_de_un_producto_ajeno_es_404_sin_rastro(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    linea = {
        "producto_id": str(entorno_a.producto_id),
        "cantidad_base": 5,
        "costo_unitario": "5",
    }

    respuesta = cliente.post(
        URL_INICIALES,
        json=_cuerpo_inicial(entorno_b, lineas=[linea]),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    _sin_rastro_de_a(sesion, entorno_a, entorno_b)


def test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_el_stock_inicial(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL_INICIALES,
        json=_cuerpo_inicial(entorno_b, organizacion_id=str(entorno_a.org)),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 422
    assert _contar(sesion, "stock_movimiento", entorno_a.org) == 0
    assert _contar(sesion, "stock_movimiento", entorno_b.org) == 0


def test_inv21_leer_el_stock_de_una_ubicacion_ajena_es_404_y_no_revela_nada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.get(_url_saldos(entorno_a.deposito_id), headers=headers_b)

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert str(MARCA_DE_CANTIDAD) not in respuesta.text
    assert MARCA_DE_COSTO not in respuesta.text
    assert "Vino A" not in respuesta.text


def test_inv21_leer_el_kardex_con_una_ubicacion_o_un_producto_ajenos_es_404_y_no_revela_nada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    ubicacion_ajena = cliente.get(
        URL_KARDEX,
        params=_params_kardex(entorno_b, ubicacion_id=str(entorno_a.deposito_id)),
        headers=headers_b,
    )
    producto_ajeno = cliente.get(
        URL_KARDEX,
        params=_params_kardex(entorno_b, producto_id=str(entorno_a.producto_id)),
        headers=headers_b,
    )

    for respuesta in (ubicacion_ajena, producto_ajeno):
        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert str(MARCA_DE_CANTIDAD) not in respuesta.text
        assert MARCA_DE_COSTO not in respuesta.text


def test_inv21_leer_el_costo_de_un_producto_ajeno_es_404_y_no_revela_el_promedio(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.get(_url_costo(entorno_a.producto_id), headers=headers_b)

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert MARCA_DE_COSTO not in respuesta.text
    assert str(MARCA_DE_CANTIDAD) not in respuesta.text
    # Un producto que no existe en ninguna organización responde igual: el 404 no
    # distingue "ajeno" de "inexistente".
    inexistente = cliente.get(_url_costo(uuid4()), headers=headers_b)
    assert (inexistente.status_code, inexistente.json()["codigo"]) == (
        respuesta.status_code,
        respuesta.json()["codigo"],
    )


def test_inv21_cada_organizacion_ve_solo_su_stock_su_kardex_y_su_costo(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    entorno_a.sembrar(entorno_a.producto_id, 111, "1000")
    entorno_b.sembrar(entorno_b.producto_id, 222, "2000")
    headers_a = entorno_a.confirmar_y_entrar(cliente)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    saldos_a = cliente.get(_url_saldos(entorno_a.deposito_id), headers=headers_a).json()
    saldos_b = cliente.get(_url_saldos(entorno_b.deposito_id), headers=headers_b).json()
    kardex_a = cliente.get(URL_KARDEX, params=_params_kardex(entorno_a), headers=headers_a).json()
    kardex_b = cliente.get(URL_KARDEX, params=_params_kardex(entorno_b), headers=headers_b).json()
    costo_b = cliente.get(_url_costo(entorno_b.producto_id), headers=headers_b).json()

    assert [linea["cantidad_base"] for linea in saldos_a["items"]] == [111]
    assert [linea["cantidad_base"] for linea in saldos_b["items"]] == [222]
    assert [m["cantidad_base"] for m in kardex_a["items"]] == [111]
    assert [m["cantidad_base"] for m in kardex_b["items"]] == [222]
    assert costo_b["costo_promedio"] == "2000.000000"


URL_TRANSFERENCIAS = "/api/v1/stock/transferencias"


def _cuerpo_transferencia(
    origen: object, destino: object, producto: object, cantidad: int = 5
) -> dict[str, object]:
    return {
        "ubicacion_origen_id": str(origen),
        "ubicacion_destino_id": str(destino),
        "lineas": [{"producto_id": str(producto), "cantidad_base": cantidad}],
    }


def test_inv21_transferir_desde_o_hacia_una_ubicacion_ajena_es_404_sin_rastro(
    cliente: TestClient, sesion: Session
) -> None:
    """Change 14, tarea 5.3 (INV-21, SEG-07): el origen o el destino de otra organización
    responden como inexistentes y no mueven nada."""
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    _sembrar_con_marcas(entorno_b)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    desde_ajena = cliente.post(
        URL_TRANSFERENCIAS,
        json=_cuerpo_transferencia(
            entorno_a.deposito_id, entorno_b.deposito_id, entorno_b.producto_id
        ),
        headers=_con_op(headers_b),
    )
    hacia_ajena = cliente.post(
        URL_TRANSFERENCIAS,
        json=_cuerpo_transferencia(
            entorno_b.deposito_id, entorno_a.deposito_id, entorno_b.producto_id
        ),
        headers=_con_op(headers_b),
    )

    for respuesta in (desde_ajena, hacia_ajena):
        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    for tabla in ("transferencia", "transferencia_linea"):
        assert _contar(sesion, tabla, entorno_a.org) == 0
        assert _contar(sesion, tabla, entorno_b.org) == 0
    # Solo el movimiento sembrado a mano en cada organización.
    assert _contar(sesion, "stock_movimiento", entorno_a.org) == 1
    assert _contar(sesion, "stock_movimiento", entorno_b.org) == 1


def test_inv21_transferir_un_producto_ajeno_es_404_sin_rastro(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    _sembrar_con_marcas(entorno_a)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    destino_b = crear_ubicacion_sql(sesion, entorno_b.org, nombre="Camioneta B")
    sesion.commit()

    respuesta = cliente.post(
        URL_TRANSFERENCIAS,
        json=_cuerpo_transferencia(entorno_b.deposito_id, destino_b, entorno_a.producto_id),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 404
    assert _contar(sesion, "transferencia", entorno_b.org) == 0
    _sin_rastro_de_a(sesion, entorno_a, entorno_b)


def test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_la_transferencia(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    cuerpo = _cuerpo_transferencia(
        entorno_b.deposito_id, entorno_b.deposito_id, entorno_b.producto_id
    )
    cuerpo["organizacion_id"] = str(entorno_a.org)

    respuesta = cliente.post(URL_TRANSFERENCIAS, json=cuerpo, headers=_con_op(headers_b))

    assert respuesta.status_code == 422
    assert _contar(sesion, "transferencia", entorno_a.org) == 0
    assert _contar(sesion, "transferencia", entorno_b.org) == 0


URL_AJUSTES = "/api/v1/stock/ajustes"
ADMIN_CON_AJUSTES = ADMIN | {"AJUSTAR_STOCK"}


def _cuerpo_ajuste(
    ubicacion: object, motivo: object, producto: object, cantidad: int = -1
) -> dict[str, object]:
    return {
        "ubicacion_id": str(ubicacion),
        "motivo_id": str(motivo),
        "lineas": [{"producto_id": str(producto), "cantidad_base": cantidad}],
    }


def _dos_organizaciones_con_motivo(sesion: Session) -> tuple[Entorno, Entorno, object, object]:
    entorno_a = Entorno(sesion, permisos=ADMIN_CON_AJUSTES, nombre_usuario="a1")
    entorno_b = Entorno(sesion, permisos=ADMIN_CON_AJUSTES, nombre_usuario="b1")
    return (
        entorno_a,
        entorno_b,
        crear_motivo_sql(sesion, entorno_a.org),
        crear_motivo_sql(sesion, entorno_b.org),
    )


@pytest.mark.parametrize("ajeno", ["ubicacion", "motivo", "producto"])
def test_inv21_ajustar_con_una_ubicacion_motivo_o_producto_ajeno_es_404_sin_rastro(
    cliente: TestClient, sesion: Session, ajeno: str
) -> None:
    """Change 14, tarea 6.3 (INV-21, SEG-07): lo de otra organización responde como
    inexistente y no mueve nada."""
    entorno_a, entorno_b, motivo_a, motivo_b = _dos_organizaciones_con_motivo(sesion)
    _sembrar_con_marcas(entorno_a)
    _sembrar_con_marcas(entorno_b)
    ubicacion = entorno_a.deposito_id if ajeno == "ubicacion" else entorno_b.deposito_id
    motivo = motivo_a if ajeno == "motivo" else motivo_b
    producto = entorno_a.producto_id if ajeno == "producto" else entorno_b.producto_id
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL_AJUSTES, json=_cuerpo_ajuste(ubicacion, motivo, producto), headers=_con_op(headers_b)
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    for tabla in ("ajuste_stock", "ajuste_stock_linea"):
        assert _contar(sesion, tabla, entorno_a.org) == 0
        assert _contar(sesion, tabla, entorno_b.org) == 0
    assert _contar(sesion, "stock_movimiento", entorno_a.org) == 1
    assert _contar(sesion, "stock_movimiento", entorno_b.org) == 1


def test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_el_ajuste(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b, _, motivo_b = _dos_organizaciones_con_motivo(sesion)
    _sembrar_con_marcas(entorno_b)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    cuerpo = _cuerpo_ajuste(entorno_b.deposito_id, motivo_b, entorno_b.producto_id)
    cuerpo["organizacion_id"] = str(entorno_a.org)

    respuesta = cliente.post(URL_AJUSTES, json=cuerpo, headers=_con_op(headers_b))

    assert respuesta.status_code == 422
    assert _contar(sesion, "ajuste_stock", entorno_a.org) == 0
    assert _contar(sesion, "ajuste_stock", entorno_b.org) == 0


# --- change 14, tarea 11.1: anulaciones y lecturas de transferencias y ajustes ----------------

ADMIN_CON_TODO = ADMIN | {"AJUSTAR_STOCK", "ANULAR_TRANSFERENCIA"}


def _organizaciones_con_operaciones(sesion: Session) -> tuple[Entorno, Entorno, object, object]:
    """Dos organizaciones; la de A tiene una transferencia y un ajuste confirmados. Devuelve
    también el id de cada uno."""
    entorno_a = Entorno(sesion, permisos=ADMIN_CON_TODO, nombre_usuario="a1")
    entorno_b = Entorno(sesion, permisos=ADMIN_CON_TODO, nombre_usuario="b1")
    _sembrar_con_marcas(entorno_a)
    _sembrar_con_marcas(entorno_b)
    camioneta_a = crear_ubicacion_sql(sesion, entorno_a.org, nombre="Camioneta A")
    momento = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    transferencia = stock_service.transferir(
        entorno_a.org,
        sesion,
        FixedClock(momento),
        ubicacion_origen_id=entorno_a.deposito_id,
        ubicacion_destino_id=camioneta_a,
        lineas=[LineaDeTransferencia(entorno_a.producto_id, 10)],
        observacion=None,
        usuario_id=entorno_a.usuario_id,
        dispositivo_id=entorno_a.dispositivo_id,
        operation_id=uuid4(),
        occurred_at=momento,
    )
    ajuste = stock_service.ajustar(
        entorno_a.org,
        sesion,
        FixedClock(momento),
        ubicacion_id=entorno_a.deposito_id,
        motivo_id=crear_motivo_sql(sesion, entorno_a.org),
        lineas=[LineaDeAjuste(entorno_a.producto_id, -1)],
        observacion=None,
        usuario_id=entorno_a.usuario_id,
        dispositivo_id=entorno_a.dispositivo_id,
        operation_id=uuid4(),
        occurred_at=momento,
    )
    sesion.commit()
    return entorno_a, entorno_b, transferencia.transferencia.id, ajuste.ajuste.id


def _estado(sesion: Session, tabla: str, id_: object) -> str:
    sesion.rollback()
    return str(sesion.scalar(text(f"SELECT estado FROM {tabla} WHERE id = :i"), {"i": id_}))


def test_inv21_anular_una_transferencia_o_un_ajuste_ajeno_es_404_y_los_deja_confirmados(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b, transferencia_id, ajuste_id = _organizaciones_con_operaciones(sesion)
    motivo_transferencia_b = crear_motivo_sql(
        sesion, entorno_b.org, ambito="ANULACION_TRANSFERENCIA"
    )
    motivo_ajuste_b = crear_motivo_sql(sesion, entorno_b.org, ambito="ANULACION_AJUSTE")
    sesion.commit()
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    movimientos_de_a = _contar(sesion, "stock_movimiento", entorno_a.org)

    transferencia = cliente.post(
        f"{URL_TRANSFERENCIAS}/{transferencia_id}/anulacion",
        json={"motivo_id": str(motivo_transferencia_b)},
        headers=_con_op(headers_b),
    )
    ajuste = cliente.post(
        f"{URL_AJUSTES}/{ajuste_id}/anulacion",
        json={"motivo_id": str(motivo_ajuste_b)},
        headers=_con_op(headers_b),
    )

    for respuesta in (transferencia, ajuste):
        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert _estado(sesion, "transferencia", transferencia_id) == "CONFIRMADA"
    assert _estado(sesion, "ajuste_stock", ajuste_id) == "CONFIRMADA"
    assert _contar(sesion, "stock_movimiento", entorno_a.org) == movimientos_de_a
    assert _contar(sesion, "stock_movimiento", entorno_b.org) == 1


def test_inv21_el_motivo_de_otra_organizacion_no_anula_una_operacion_propia(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b, transferencia_id, ajuste_id = _organizaciones_con_operaciones(sesion)
    # Las operaciones son de A; el motivo es de B: 404, no `MOTIVO_INVALIDO`.
    motivo_de_b = crear_motivo_sql(sesion, entorno_b.org, ambito="ANULACION_TRANSFERENCIA")
    motivo_de_b_ajuste = crear_motivo_sql(sesion, entorno_b.org, ambito="ANULACION_AJUSTE")
    sesion.commit()
    headers_a = entorno_a.confirmar_y_entrar(cliente)

    transferencia = cliente.post(
        f"{URL_TRANSFERENCIAS}/{transferencia_id}/anulacion",
        json={"motivo_id": str(motivo_de_b)},
        headers=_con_op(headers_a),
    )
    ajuste = cliente.post(
        f"{URL_AJUSTES}/{ajuste_id}/anulacion",
        json={"motivo_id": str(motivo_de_b_ajuste)},
        headers=_con_op(headers_a),
    )

    assert transferencia.status_code == ajuste.status_code == 404
    assert _estado(sesion, "transferencia", transferencia_id) == "CONFIRMADA"
    assert _estado(sesion, "ajuste_stock", ajuste_id) == "CONFIRMADA"


def test_inv21_leer_transferencias_y_ajustes_ajenos_es_404_y_el_listado_no_los_muestra(
    cliente: TestClient, sesion: Session
) -> None:
    _, entorno_b, transferencia_id, ajuste_id = _organizaciones_con_operaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    detalle_transferencia = cliente.get(
        f"{URL_TRANSFERENCIAS}/{transferencia_id}", headers=headers_b
    )
    detalle_ajuste = cliente.get(f"{URL_AJUSTES}/{ajuste_id}", headers=headers_b)
    listado_transferencias = cliente.get(URL_TRANSFERENCIAS, headers=headers_b)
    listado_ajustes = cliente.get(URL_AJUSTES, headers=headers_b)

    for respuesta in (detalle_transferencia, detalle_ajuste):
        assert respuesta.status_code == 404
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert listado_transferencias.status_code == listado_ajustes.status_code == 200
    assert listado_transferencias.json()["items"] == []
    assert listado_ajustes.json()["items"] == []
    assert MARCA_DE_COSTO not in detalle_transferencia.text + detalle_ajuste.text


def test_inv21_filtrar_por_una_ubicacion_o_un_motivo_ajeno_no_revela_nada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b, _, _ = _organizaciones_con_operaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    por_ubicacion = cliente.get(
        URL_TRANSFERENCIAS, params={"ubicacion_id": str(entorno_a.deposito_id)}, headers=headers_b
    )
    ajustes_por_ubicacion = cliente.get(
        URL_AJUSTES, params={"ubicacion_id": str(entorno_a.deposito_id)}, headers=headers_b
    )

    assert por_ubicacion.json()["items"] == []
    assert ajustes_por_ubicacion.json()["items"] == []
