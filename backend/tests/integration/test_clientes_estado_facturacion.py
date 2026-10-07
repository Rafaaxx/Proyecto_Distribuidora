"""Change 10, tarea 12.2: `estado_facturacion_default` del cliente en el servicio
(`clientes/service.py`; `docs/03` §10, VTA-08).

`CLIENTE_CREAR` y `CLIENTE_MODIFICAR` aceptaban cualquier texto y la base lo rechazaba con
`ck_cliente__estado_facturacion`: un 500. La regla es del dominio de clientes
(`ESTADO_FACTURACION_INVALIDO`, 422), así que la pantalla, el bus y la importación de
clientes la comparten. Nada se escribe si falla.

Reglas citadas: CLI-01, INV-01, TR-10.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.clientes import service as clientes_service
from app.modules.clientes.domain.errores import EstadoFacturacionInvalidoError
from app.modules.clientes.models import Cliente

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

RELOJ = FixedClock(datetime(2026, 10, 1, 12, 0, tzinfo=UTC))


def _crear(sesion: Session, org: UUID, estado: str | None, codigo: str = "C001") -> Cliente:
    return clientes_service.crear_cliente(
        org,
        sesion,
        RELOJ,
        nombre="Almacén Don Pepe",
        codigo=codigo,
        razon_social=None,
        documento_tipo=None,
        documento_numero=None,
        direccion="San Martín 123",
        contacto="Pepe",
        telefono=None,
        email=None,
        estado_facturacion_default=estado,
        actor_id=None,
    )


def _cantidad(sesion: Session, org: UUID) -> int:
    return (
        sesion.scalar(
            select(func.count()).select_from(Cliente).where(Cliente.organizacion_id == org)
        )
        or 0
    )


@pytest.mark.parametrize("estado", ["FACTURADA", "PARCIAL", "pendiente", ""])
def test_crear_con_un_estado_de_facturacion_invalido_rechaza_sin_escribir(
    db_session: Session, estado: str
) -> None:
    org = crear_organizacion(db_session).id

    with pytest.raises(EstadoFacturacionInvalidoError):
        _crear(db_session, org, estado)

    assert _cantidad(db_session, org) == 0


@pytest.mark.parametrize("estado", ["NO_REQUIERE", "PENDIENTE", None])
def test_crear_con_un_estado_valido_o_nulo_lo_guarda_igual(
    db_session: Session, estado: str | None
) -> None:
    org = crear_organizacion(db_session).id

    cliente = _crear(db_session, org, estado)
    db_session.refresh(cliente)

    assert cliente.estado_facturacion_default == estado


def test_modificar_con_un_estado_invalido_rechaza_y_conserva_el_guardado(
    db_session: Session,
) -> None:
    org = crear_organizacion(db_session).id
    cliente = _crear(db_session, org, "PENDIENTE")
    ficha = {
        "nombre": "Almacén Don Pepe",
        "codigo": "C001",
        "razon_social": None,
        "documento_tipo": None,
        "documento_numero": None,
        "direccion": "San Martín 123",
        "contacto": "Pepe",
        "telefono": None,
        "email": None,
        "estado": "ACTIVO",
        "lista_precio_id": None,
        "actor_id": None,
    }

    with pytest.raises(EstadoFacturacionInvalidoError):
        clientes_service.modificar_cliente(
            org,
            db_session,
            RELOJ,
            cliente_id=cliente.id,
            estado_facturacion_default="FACTURADA",
            **ficha,
        )
    modificado = clientes_service.modificar_cliente(
        org,
        db_session,
        RELOJ,
        cliente_id=cliente.id,
        estado_facturacion_default="NO_REQUIERE",
        **ficha,
    )

    assert modificado.estado_facturacion_default == "NO_REQUIERE"
