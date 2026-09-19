"""Tarea 3.4: la base rechaza datos que violarían INV-02 y el parámetro
"1 fila por organización" de `configuracion_organizacion` (`docs/03` §4),
aunque el código de la aplicación no valide nada.

Escenarios homónimos de las specs `aislamiento-multiorganizacion` y
`parametros-de-organizacion`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.modules.identidad.models import ConfiguracionOrganizacion, Organizacion


def _crear_organizacion(sesion: Session) -> Organizacion:
    momento = datetime.now(UTC)
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Distribuidora de prueba",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=None,
    )
    sesion.add(organizacion)
    sesion.flush()
    return organizacion


def _configuracion_valida(organizacion_id: object) -> ConfiguracionOrganizacion:
    momento = datetime.now(UTC)
    return ConfiguracionOrganizacion(
        organizacion_id=organizacion_id,
        modo_impositivo="A",
        politica_credito_default="AUTORIZAR",
        descuento_manual_habilitado=True,
        motivo_obligatorio_lista=True,
        estado_facturacion_default="NO_REQUIERE",
        intentos_pin_max=5,
        creado_en=momento,
        actualizado_en=momento,
    )


def test_insertar_configuracion_con_organizacion_id_nulo_es_rechazado(
    db_session: Session,
) -> None:
    """Escenario 'Una tabla de negocio sin organización no llega a la base'."""
    configuracion = _configuracion_valida(None)
    db_session.add(configuracion)

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_insertar_configuracion_con_organizacion_inexistente_es_rechazado(
    db_session: Session,
) -> None:
    configuracion = _configuracion_valida(uuid4())
    db_session.add(configuracion)

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_una_segunda_fila_de_configuracion_para_la_misma_organizacion_es_rechazada(
    db_session: Session,
) -> None:
    """Escenario 'Una organización tiene a lo sumo una fila de configuración'
    (spec `parametros-de-organizacion`)."""
    organizacion = _crear_organizacion(db_session)
    db_session.add(_configuracion_valida(organizacion.id))
    db_session.flush()

    db_session.add(_configuracion_valida(organizacion.id))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    db_session.rollback()
