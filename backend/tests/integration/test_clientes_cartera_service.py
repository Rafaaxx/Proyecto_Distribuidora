# ruff: noqa: F811
"""Change 20b, tarea 9.4 (`design.md` D19): lo que el change 21 necesita de la cartera, por
`clientes/service.py` y sin rutas nuevas.

- `listar_cartera(organizacion_id, usuario_id)`: los clientes asignados al usuario (vacío si no
  tiene; el 21 aplica la regla "vacía = todos" de D14).
- `contar_clientes_asignados(organizacion_id, usuario_id)`: cuántos son.

Aislamiento por organización (INV-21): ninguno cuenta ni lista clientes de otra.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_cliente
from sqlalchemy import text
from sqlalchemy.orm import Session
from usuarios_utiles import (
    EntornoUsuarios,
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

from app.modules.clientes import service as clientes_service

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")


def _asignar(entorno: EntornoUsuarios, vendedor_id: UUID | None, *clientes: UUID) -> None:
    entorno.sesion.execute(
        text("UPDATE cliente SET vendedor_id = :v WHERE id = ANY(:c)"),
        {"v": vendedor_id, "c": list(clientes)},
    )
    entorno.sesion.commit()


def _vendedor(entorno: EntornoUsuarios) -> UUID:
    usuario_id, _ = entorno.crear_usuario(
        entorno.crear_rol(f"Vendedor {uuid4().hex[:6]}", frozenset({"VENDER"}))
    )
    return usuario_id


def test_la_cartera_lista_y_cuenta_los_clientes_asignados(sesion_real: Session) -> None:
    entorno = EntornoUsuarios(sesion_real)
    juan = _vendedor(entorno)
    pedro = _vendedor(entorno)
    a, b, c, d = (crear_cliente(sesion_real, entorno.org, nombre=f"Cliente {i}") for i in range(4))
    sesion_real.commit()
    _asignar(entorno, juan, a, b)
    _asignar(entorno, pedro, c)

    assert sorted(clientes_service.listar_cartera(entorno.org, juan, sesion_real)) == sorted([a, b])
    assert clientes_service.contar_clientes_asignados(entorno.org, juan, sesion_real) == 2
    assert clientes_service.listar_cartera(entorno.org, pedro, sesion_real) == [c]
    assert clientes_service.contar_clientes_asignados(entorno.org, pedro, sesion_real) == 1
    assert d not in clientes_service.listar_cartera(entorno.org, juan, sesion_real)


def test_sin_clientes_asignados_la_cartera_esta_vacia(sesion_real: Session) -> None:
    entorno = EntornoUsuarios(sesion_real)
    sin_cartera = _vendedor(entorno)
    crear_cliente(sesion_real, entorno.org)
    sesion_real.commit()

    assert clientes_service.listar_cartera(entorno.org, sin_cartera, sesion_real) == []
    assert clientes_service.contar_clientes_asignados(entorno.org, sin_cartera, sesion_real) == 0


def test_la_cartera_cuenta_clientes_de_cualquier_estado(sesion_real: Session) -> None:
    """D6: quien se da de baja o tiene clientes inactivos conserva su cartera hasta reasignarla."""
    entorno = EntornoUsuarios(sesion_real)
    juan = _vendedor(entorno)
    activo = crear_cliente(sesion_real, entorno.org, nombre="Activo")
    inactivo = crear_cliente(sesion_real, entorno.org, nombre="Inactivo", estado="INACTIVO")
    sesion_real.commit()
    _asignar(entorno, juan, activo, inactivo)

    assert clientes_service.contar_clientes_asignados(entorno.org, juan, sesion_real) == 2
    assert set(clientes_service.listar_cartera(entorno.org, juan, sesion_real)) == {
        activo,
        inactivo,
    }


def test_la_cartera_no_cruza_organizaciones(sesion_real: Session) -> None:
    """INV-21: pedir la cartera de un usuario ajeno con la organización propia, o la de un usuario
    propio con la organización ajena, no devuelve nada."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    mio = _vendedor(propia)
    ajeno = _vendedor(ajena)
    cliente_propio = crear_cliente(sesion_real, propia.org, nombre="Propio")
    cliente_ajeno = crear_cliente(sesion_real, ajena.org, nombre="Ajeno")
    sesion_real.commit()
    _asignar(propia, mio, cliente_propio)
    _asignar(ajena, ajeno, cliente_ajeno)

    assert clientes_service.listar_cartera(propia.org, ajeno, sesion_real) == []
    assert clientes_service.contar_clientes_asignados(propia.org, ajeno, sesion_real) == 0
    assert clientes_service.listar_cartera(ajena.org, mio, sesion_real) == []
    assert clientes_service.contar_clientes_asignados(ajena.org, mio, sesion_real) == 0
    assert clientes_service.listar_cartera(propia.org, mio, sesion_real) == [cliente_propio]
