"""Change 10, tarea 7.2: búsquedas por clave natural de `clientes/service.py` que usa la
importación de saldos (`design.md` D4: cliente por código o, si no, por documento).

Solo lectura, filtradas por la organización (INV-21), sin distinguir mayúsculas ni
espacios al borde en el código; el documento se compara en dígitos (CLI-05). Incluyen a
los clientes en cualquier estado.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.clientes import service as clientes_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

RELOJ = FixedClock(datetime(2026, 10, 1, 12, 0, tzinfo=UTC))


def _cliente(
    sesion: Session,
    org: UUID,
    *,
    codigo: str | None,
    documento: tuple[str, str] | None = None,
) -> UUID:
    cliente = clientes_service.crear_cliente(
        org,
        sesion,
        RELOJ,
        nombre="Cliente",
        codigo=codigo,
        razon_social=None,
        documento_tipo=None if documento is None else documento[0],
        documento_numero=None if documento is None else documento[1],
        direccion="San Martín 123",
        contacto="Pepe",
        telefono=None,
        email=None,
        estado_facturacion_default=None,
        actor_id=None,
    )
    return cliente.id


def test_busca_por_codigo_sin_distinguir_mayusculas_ni_espacios(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    c001 = _cliente(db_session, org, codigo="C001")
    _cliente(db_session, org, codigo="C002")

    encontrados = clientes_service.buscar_clientes_por_codigo(org, "  c001 ", db_session)

    assert [c.id for c in encontrados] == [c001]
    assert clientes_service.buscar_clientes_por_codigo(org, "C999", db_session) == []
    assert clientes_service.buscar_clientes_por_codigo(org, "  ", db_session) == []


def test_busca_por_documento_en_digitos(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    con_cuit = _cliente(db_session, org, codigo=None, documento=("CUIT", "20-12345678-9"))
    _cliente(db_session, org, codigo=None, documento=("DNI", "12345678"))

    encontrados = clientes_service.buscar_clientes_por_documento(org, "20123456789", db_session)

    assert [c.id for c in encontrados] == [con_cuit]
    assert clientes_service.buscar_clientes_por_documento(org, "", db_session) == []
    assert clientes_service.buscar_clientes_por_documento(org, "99999999", db_session) == []


def test_no_devuelve_los_de_otra_organizacion(db_session: Session) -> None:
    """INV-21: igual que si no existiera en ninguna."""
    propia = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    _cliente(db_session, ajena, codigo="C001", documento=("DNI", "12345678"))

    assert clientes_service.buscar_clientes_por_codigo(propia, "C001", db_session) == []
    assert clientes_service.buscar_clientes_por_documento(propia, "12345678", db_session) == []
