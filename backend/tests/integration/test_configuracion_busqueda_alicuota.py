"""Change 10, tarea 5.2: búsqueda de alícuotas por porcentaje de
`configuracion/service.py` (`design.md` D4: alícuota por porcentaje).

Compara el valor exacto (`Decimal`, INV-03: 21% es `0.210000`), filtra por la
organización (INV-21) e incluye las inactivas (el alta de producto rechaza después con
`ALICUOTA_INACTIVA`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.modules.configuracion import service as configuracion_service
from app.modules.configuracion.models import AlicuotaIva

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _alicuota(sesion: Session, org: UUID, valor: str, *, activo: bool = True) -> UUID:
    alicuota = AlicuotaIva(
        id=nuevo_id(),
        organizacion_id=org,
        nombre=valor,
        valor=Decimal(valor),
        activo=activo,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    sesion.add(alicuota)
    sesion.flush()
    return alicuota.id


def _ids(alicuotas: list[AlicuotaIva]) -> set[UUID]:
    return {a.id for a in alicuotas}


def test_busca_la_alicuota_por_valor_exacto(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    veintiuno = _alicuota(db_session, org, "0.210000")
    diez_y_medio = _alicuota(db_session, org, "0.105000")
    _alicuota(db_session, org, "0.000000")

    por_21 = configuracion_service.buscar_alicuotas_por_valor(org, Decimal("0.21"), db_session)
    por_105 = configuracion_service.buscar_alicuotas_por_valor(org, Decimal("0.105"), db_session)

    assert _ids(por_21) == {veintiuno}
    assert _ids(por_105) == {diez_y_medio}


def test_incluye_las_inactivas_y_nunca_hay_mas_de_una_coincidencia(db_session: Session) -> None:
    # Desde el change 20c el valor es único por organización (IMP-04): la importación por
    # porcentaje no es ambigua; una inactiva sigue encontrándose (el alta de producto la rechaza).
    org = crear_organizacion(db_session).id
    activa = _alicuota(db_session, org, "0.105000")
    inactiva = _alicuota(db_session, org, "0.210000", activo=False)

    por_inactiva = configuracion_service.buscar_alicuotas_por_valor(
        org, Decimal("0.210000"), db_session
    )
    por_activa = configuracion_service.buscar_alicuotas_por_valor(
        org, Decimal("0.105000"), db_session
    )

    assert _ids(por_inactiva) == {inactiva}
    assert _ids(por_activa) == {activa}


def test_no_devuelve_las_de_otra_organizacion_ni_valores_distintos(db_session: Session) -> None:
    """INV-21."""
    propia = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    _alicuota(db_session, ajena, "0.210000")
    _alicuota(db_session, propia, "0.105000")

    assert (
        configuracion_service.buscar_alicuotas_por_valor(propia, Decimal("0.21"), db_session) == []
    )
    assert (
        configuracion_service.buscar_alicuotas_por_valor(propia, Decimal("0.2100001"), db_session)
        == []
    )
