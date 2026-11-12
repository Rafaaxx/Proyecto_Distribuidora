"""Tarea 8.1 (change 18b; spec `clientes/datos-de-credito`): `clientes/service.py` resuelve los
datos de crédito de un cliente con la herencia de la organización, contra PostgreSQL real.

Reglas citadas: CRE-01, CRE-03, CRE-06, CLI-03, INV-21.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from cuentas_corrientes_utiles import crear_cliente, crear_organizacion
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.clientes import service as clientes_service
from app.modules.clientes.domain.errores import RecursoNoEncontradoError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def _configurar_organizacion(sesion: Session, org: object, **columnas: object) -> None:
    asignaciones = ", ".join(f"{columna} = :{columna}" for columna in columnas)
    sesion.execute(
        text(f"UPDATE configuracion_organizacion SET {asignaciones} WHERE organizacion_id = :org"),
        {**columnas, "org": org},
    )


def _configurar_cliente(
    sesion: Session, org: object, cliente_id: object, **columnas: object
) -> None:
    asignaciones = ", ".join(f"{columna} = :{columna}" for columna in columnas)
    sesion.execute(
        text(f"UPDATE cliente SET {asignaciones} WHERE organizacion_id = :org AND id = :id"),
        {**columnas, "org": org, "id": cliente_id},
    )


def test_cre03_cre06_el_cliente_sin_datos_propios_hereda_politica_y_tolerancia(
    db_session: Session,
) -> None:
    org = crear_organizacion(db_session).id
    _configurar_organizacion(
        db_session,
        org,
        politica_credito_default="BLOQUEAR",
        tolerancia_offline_tipo="IMPORTE",
        tolerancia_offline_valor=Decimal("20000.00"),
    )
    cliente_id = crear_cliente(db_session, org)

    datos = clientes_service.resolver_datos_de_credito(org, cliente_id, db_session)

    assert datos.limite is None  # sin límite = sin control (CRE-01)
    assert datos.politica == "BLOQUEAR"
    assert (datos.tolerancia_tipo, datos.tolerancia_valor) == ("IMPORTE", Decimal("20000.00"))


def test_cre03_cre06_los_datos_propios_del_cliente_ganan(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    _configurar_organizacion(
        db_session,
        org,
        politica_credito_default="BLOQUEAR",
        tolerancia_offline_tipo="IMPORTE",
        tolerancia_offline_valor=Decimal("20000.00"),
    )
    cliente_id = crear_cliente(db_session, org)
    _configurar_cliente(
        db_session,
        org,
        cliente_id,
        limite_credito=Decimal("200000.00"),
        politica_credito="ADVERTIR",
        tolerancia_offline_tipo="PORCENTAJE",
        tolerancia_offline_valor=Decimal("5.00"),
    )

    datos = clientes_service.resolver_datos_de_credito(org, cliente_id, db_session)

    assert datos.limite == Decimal("200000.00")
    assert datos.politica == "ADVERTIR"
    assert (datos.tolerancia_tipo, datos.tolerancia_valor) == ("PORCENTAJE", Decimal("5.00"))


def test_cli03_el_consumidor_final_conserva_su_limite_cero(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    _configurar_organizacion(db_session, org, politica_credito_default="AUTORIZAR")
    cliente_id = crear_cliente(db_session, org, nombre="Consumidor final", es_consumidor_final=True)
    _configurar_cliente(db_session, org, cliente_id, limite_credito=Decimal("0.00"))

    datos = clientes_service.resolver_datos_de_credito(org, cliente_id, db_session)

    assert datos.limite == Decimal("0.00")
    assert datos.politica == "AUTORIZAR"  # la de la organización


def test_inv21_un_cliente_de_otra_organizacion_no_existe(db_session: Session) -> None:
    org_a = crear_organizacion(db_session).id
    org_b = crear_organizacion(db_session).id
    ajeno = crear_cliente(db_session, org_b)

    with pytest.raises(RecursoNoEncontradoError):
        clientes_service.resolver_datos_de_credito(org_a, ajeno, db_session)
    with pytest.raises(RecursoNoEncontradoError):
        clientes_service.resolver_datos_de_credito(org_a, uuid4(), db_session)
