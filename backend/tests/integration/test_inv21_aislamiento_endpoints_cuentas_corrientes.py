"""Change 08, tarea 8.4: cobertura de aislamiento (INV-21, SEG-07) de las tres
rutas nuevas de `cuentas_corrientes` -- `POST /cuentas-corrientes/saldos-iniciales`,
`GET /clientes/{id}/cuenta-corriente` y `GET /proveedores/{id}/cuenta-corriente`--,
con cliente y proveedor ajenos en lectura y en escritura.

Mismo arnés HTTP que `test_cuentas_corrientes_api.py` (PostgreSQL real, `login`
real de dos organizaciones, nunca un token fabricado): se reutilizan su `Entorno`
y sus fixtures. Un recurso de otra organización responde 404 (no 403) y no deja
rastro: ni movimiento, ni fila de saldo, ni dato del saldo ajeno en la respuesta.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_cuentas_corrientes_api import (  # noqa: F401  (fixtures reutilizadas)
    URL_SALDOS,
    Entorno,
    _cuerpo_saldo,
    _limpiar_datos_confirmados,
    _movimientos_de,
    _url_cliente,
    _url_proveedor,
    cliente,
    sesion,
)

MOMENTO = datetime(2026, 3, 10, 15, 0, tzinfo=UTC)


def _saldos_de(sesion: Session, organizacion_id: object) -> int:
    sesion.rollback()
    return int(
        sesion.scalar(
            text("select count(*) from saldo_cuenta where organizacion_id = :o"),
            {"o": organizacion_id},
        )
        or 0
    )


def _dos_organizaciones(sesion: Session) -> tuple[Entorno, Entorno]:
    permisos = frozenset({"IMPORTAR_DATOS", "GESTIONAR_CLIENTES", "GESTIONAR_PROVEEDORES"})
    return (
        Entorno(sesion, permisos=permisos, nombre_usuario="a1"),
        Entorno(sesion, permisos=permisos, nombre_usuario="b1"),
    )


def test_inv21_escribir_el_saldo_inicial_de_un_cliente_ajeno_es_404_sin_rastro(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL_SALDOS,
        json=_cuerpo_saldo(entorno_a.cliente_id),
        headers={**headers_b, "Operation-Id": str(uuid4())},
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert _movimientos_de(sesion, entorno_a.org) == 0
    assert _movimientos_de(sesion, entorno_b.org) == 0
    assert _saldos_de(sesion, entorno_a.org) == 0


def test_inv21_escribir_el_saldo_inicial_de_un_proveedor_ajeno_es_404_sin_rastro(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL_SALDOS,
        json=_cuerpo_saldo(entorno_a.proveedor_id, cuenta_tipo="PROVEEDOR"),
        headers={**headers_b, "Operation-Id": str(uuid4())},
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert _movimientos_de(sesion, entorno_a.org) == 0
    assert _movimientos_de(sesion, entorno_b.org) == 0
    assert _saldos_de(sesion, entorno_a.org) == 0


def test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_la_cuenta(
    cliente: TestClient, sesion: Session
) -> None:
    """`organizacion_id` sale siempre del token: si viene en el cuerpo, el esquema
    estricto lo rechaza y nada se escribe en ninguna de las dos organizaciones."""
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL_SALDOS,
        json=_cuerpo_saldo(entorno_a.cliente_id, organizacion_id=str(entorno_a.org)),
        headers={**headers_b, "Operation-Id": str(uuid4())},
    )

    assert respuesta.status_code == 422
    assert _movimientos_de(sesion, entorno_a.org) == 0
    assert _movimientos_de(sesion, entorno_b.org) == 0


def test_inv21_leer_la_cuenta_de_un_cliente_ajeno_es_404_y_no_revela_el_saldo(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    entorno_a.mover(importe="777123.00", occurred_at=MOMENTO)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.get(_url_cliente(entorno_a.cliente_id), headers=headers_b)

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert "777123" not in respuesta.text


def test_inv21_leer_la_cuenta_de_un_proveedor_ajeno_es_404_y_no_revela_el_saldo(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    entorno_a.mover(cuenta_tipo="PROVEEDOR", importe="888456.00", occurred_at=MOMENTO)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.get(_url_proveedor(entorno_a.proveedor_id), headers=headers_b)

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert "888456" not in respuesta.text


def test_inv21_cada_organizacion_ve_solo_sus_movimientos(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    entorno_a.mover(importe="111.00", occurred_at=MOMENTO)
    entorno_b.mover(importe="222.00", occurred_at=MOMENTO)
    headers_a = entorno_a.confirmar_y_entrar(cliente)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    de_a = cliente.get(_url_cliente(entorno_a.cliente_id), headers=headers_a).json()
    de_b = cliente.get(_url_cliente(entorno_b.cliente_id), headers=headers_b).json()

    assert [m["importe"] for m in de_a["items"]] == ["111.00"]
    assert [m["importe"] for m in de_b["items"]] == ["222.00"]
