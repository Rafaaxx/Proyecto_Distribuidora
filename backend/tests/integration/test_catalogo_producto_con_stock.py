"""Change 14, tarea 8.3: un producto con stock no se desactiva, de punta a punta por
`PUT /api/v1/catalogo/productos/{id}` contra PostgreSQL real (spec delta
`catalogo/productos-y-presentaciones`, `design.md` D4, D4.1, D4.2).

El verificador es el real: `stock` lo registra al importarse (`app.main`), así que el catálogo
consulta los saldos de verdad. La carrera con un movimiento simultáneo es del grupo 14.

Reglas citadas: CAT-05, ADR-038 punto 5, STK-04, STK-05, INV-21, SEG-07.
Nota (tarea 8.3): la importación de maestros solo CREA productos (no tiene columna `activo` ni
llama a `PRODUCTO_MODIFICAR`), así que no hay una fila de importación que desactive un
producto: ese caso no existe por construcción.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_motivo_sql, crear_ubicacion_sql
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    Entorno,
    _con_op,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)

PERMISOS = frozenset(
    {
        "GESTIONAR_CATALOGO",
        "TRANSFERIR_STOCK",
        "AJUSTAR_STOCK",
        "IMPORTAR_DATOS",
        "PERMITIR_STOCK_NEGATIVO",
    }
)


class EntornoConCamioneta(Entorno):
    camioneta_id: UUID
    motivo_id: UUID


def _preparar(sesion: Session) -> EntornoConCamioneta:
    entorno = EntornoConCamioneta(sesion, permisos=PERMISOS)
    entorno.camioneta_id = crear_ubicacion_sql(
        sesion, entorno.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
    )
    entorno.motivo_id = crear_motivo_sql(sesion, entorno.org)
    return entorno


def _url(producto_id: UUID) -> str:
    return f"/api/v1/catalogo/productos/{producto_id}"


def _cuerpo(sesion: Session, entorno: Entorno, producto_id: UUID, **cambios: object) -> dict:
    fila = (
        sesion.execute(
            text(
                "SELECT codigo, nombre, categoria_id, proveedor_id, unidad_base, alicuota_id "
                "FROM producto WHERE organizacion_id = :o AND id = :p"
            ),
            {"o": entorno.org, "p": producto_id},
        )
        .mappings()
        .one()
    )
    cuerpo: dict[str, object] = {
        "codigo": fila["codigo"],
        "nombre": fila["nombre"],
        "categoria_id": str(fila["categoria_id"]),
        "marca_id": None,
        "proveedor_id": str(fila["proveedor_id"]),
        "unidad_base": fila["unidad_base"],
        "alicuota_id": str(fila["alicuota_id"]),
        "activo": False,
    }
    cuerpo.update(cambios)
    return cuerpo


def _activo(sesion: Session, entorno: Entorno, producto_id: UUID) -> bool:
    sesion.rollback()
    return bool(
        sesion.execute(
            text("SELECT activo FROM producto WHERE organizacion_id = :o AND id = :p"),
            {"o": entorno.org, "p": producto_id},
        ).scalar_one()
    )


def _saldo(sesion: Session, entorno: Entorno, producto_id: UUID, ubicacion_id: UUID) -> int:
    sesion.rollback()
    return int(
        sesion.scalar(
            text(
                "SELECT coalesce(sum(cantidad_base), 0) FROM stock_saldo WHERE "
                "organizacion_id = :o AND producto_id = :p AND ubicacion_id = :u"
            ),
            {"o": entorno.org, "p": producto_id, "u": ubicacion_id},
        )
        or 0
    )


def _desactivar(
    cliente: TestClient, headers: dict[str, str], sesion: Session, entorno: Entorno, producto: UUID
):
    return cliente.put(
        _url(producto), json=_cuerpo(sesion, entorno, producto), headers=_con_op(headers)
    )


def test_desactivar_un_producto_con_stock_es_409_y_sigue_activo(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Desactivar un producto con stock": 18 en la camioneta y 0 en el depósito."""
    entorno = _preparar(sesion)
    entorno.sembrar(entorno.producto_id, 18, "1050", ubicacion_id=entorno.camioneta_id)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = _desactivar(cliente, headers, sesion, entorno, entorno.producto_id)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "PRODUCTO_CON_STOCK"
    assert _activo(sesion, entorno, entorno.producto_id) is True


def test_desactivar_un_producto_sin_stock_pero_con_movimientos_se_acepta(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Desactivar un producto sin stock": movimientos en el libro, saldo 0."""
    entorno = _preparar(sesion)
    entorno.sembrar(entorno.producto_id, 18, "1050")
    entorno.sembrar(entorno.producto_id, -18, None)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = _desactivar(cliente, headers, sesion, entorno, entorno.producto_id)

    assert respuesta.status_code == 200, respuesta.text
    assert _activo(sesion, entorno, entorno.producto_id) is False


def test_saldos_que_se_compensan_o_negativos_tambien_bloquean(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenarios "Saldos que se compensan" y "Saldo negativo": transferir 5 de un depósito
    vacío (con permiso) deja −5 y +5, que suman cero; y 52 de 40 deja −12."""
    entorno = _preparar(sesion)
    otro = entorno.otro_producto_id
    entorno.sembrar(otro, 40, "400")
    headers = entorno.confirmar_y_entrar(cliente)
    for producto, cantidad in ((entorno.producto_id, 5), (otro, 52)):
        transferencia = cliente.post(
            "/api/v1/stock/transferencias",
            json={
                "ubicacion_origen_id": str(entorno.deposito_id),
                "ubicacion_destino_id": str(entorno.camioneta_id),
                "lineas": [{"producto_id": str(producto), "cantidad_base": cantidad}],
            },
            headers=_con_op(headers),
        )
        assert transferencia.status_code == 201, transferencia.text

    compensados = _desactivar(cliente, headers, sesion, entorno, entorno.producto_id)
    negativo = _desactivar(cliente, headers, sesion, entorno, otro)

    assert _saldo(sesion, entorno, entorno.producto_id, entorno.deposito_id) == -5
    assert _saldo(sesion, entorno, otro, entorno.deposito_id) == -12
    for respuesta in (compensados, negativo):
        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "PRODUCTO_CON_STOCK"
    assert _activo(sesion, entorno, entorno.producto_id) is True
    assert _activo(sesion, entorno, otro) is True


def test_modificar_otros_datos_de_un_producto_con_stock_se_acepta(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = _preparar(sesion)
    entorno.sembrar(entorno.producto_id, 18, "1050")
    headers = entorno.confirmar_y_entrar(cliente)
    cuerpo = _cuerpo(sesion, entorno, entorno.producto_id, nombre="Vino Rosado", activo=True)

    respuesta = cliente.put(_url(entorno.producto_id), json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["nombre"] == "Vino Rosado"


def test_un_producto_ya_inactivo_con_stock_se_guarda_y_se_reactiva_pero_no_se_vuelve_a_desactivar(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Producto ya inactivo con stock" (heredado de antes de la regla)."""
    entorno = _preparar(sesion)
    entorno.sembrar(entorno.producto_id, 6, "1050")
    sesion.execute(
        text("UPDATE producto SET activo = false WHERE organizacion_id = :o AND id = :p"),
        {"o": entorno.org, "p": entorno.producto_id},
    )
    headers = entorno.confirmar_y_entrar(cliente)

    guardado = _desactivar(cliente, headers, sesion, entorno, entorno.producto_id)
    reactivado = cliente.put(
        _url(entorno.producto_id),
        json=_cuerpo(sesion, entorno, entorno.producto_id, activo=True),
        headers=_con_op(headers),
    )
    otra_vez = _desactivar(cliente, headers, sesion, entorno, entorno.producto_id)

    assert guardado.status_code == 200, guardado.text
    assert reactivado.status_code == 200, reactivado.text
    assert otra_vez.status_code == 409
    assert otra_vez.json()["codigo"] == "PRODUCTO_CON_STOCK"
    assert _activo(sesion, entorno, entorno.producto_id) is True


def test_solo_cuenta_el_stock_de_la_propia_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21, SEG-07: A desactiva el suyo, sin stock, aunque B tenga stock."""
    entorno_a = _preparar(sesion)
    entorno_b = _preparar(sesion)
    entorno_b.sembrar(entorno_b.producto_id, 99, "1050")
    headers = entorno_a.confirmar_y_entrar(cliente)

    respuesta = _desactivar(cliente, headers, sesion, entorno_a, entorno_a.producto_id)

    assert respuesta.status_code == 200, respuesta.text
    assert _activo(sesion, entorno_a, entorno_a.producto_id) is False
    assert _activo(sesion, entorno_b, entorno_b.producto_id) is True


def test_flujo_completo_reactivar_transferir_ajustar_a_cero_y_desactivar(
    cliente: TestClient, sesion: Session
) -> None:
    """Un inactivo con 18 en la camioneta: se reactiva, se transfiere al depósito, se da de
    baja con un ajuste a cero y recién entonces se desactiva (D4)."""
    entorno = _preparar(sesion)
    entorno.sembrar(entorno.producto_id, 18, "1050", ubicacion_id=entorno.camioneta_id)
    sesion.execute(
        text("UPDATE producto SET activo = false WHERE organizacion_id = :o AND id = :p"),
        {"o": entorno.org, "p": entorno.producto_id},
    )
    headers = entorno.confirmar_y_entrar(cliente)

    reactivado = cliente.put(
        _url(entorno.producto_id),
        json=_cuerpo(sesion, entorno, entorno.producto_id, activo=True),
        headers=_con_op(headers),
    )
    transferido = cliente.post(
        "/api/v1/stock/transferencias",
        json={
            "ubicacion_origen_id": str(entorno.camioneta_id),
            "ubicacion_destino_id": str(entorno.deposito_id),
            "lineas": [{"producto_id": str(entorno.producto_id), "cantidad_base": 18}],
        },
        headers=_con_op(headers),
    )
    antes_del_ajuste = _desactivar(cliente, headers, sesion, entorno, entorno.producto_id)
    ajustado = cliente.post(
        "/api/v1/stock/ajustes",
        json={
            "ubicacion_id": str(entorno.deposito_id),
            "motivo_id": str(entorno.motivo_id),
            "lineas": [{"producto_id": str(entorno.producto_id), "cantidad_base": -18}],
        },
        headers=_con_op(headers),
    )
    desactivado = _desactivar(cliente, headers, sesion, entorno, entorno.producto_id)

    assert reactivado.status_code == 200, reactivado.text
    assert transferido.status_code == 201, transferido.text
    assert antes_del_ajuste.status_code == 409
    assert ajustado.status_code == 201, ajustado.text
    assert desactivado.status_code == 200, desactivado.text
    assert _activo(sesion, entorno, entorno.producto_id) is False
