"""Change 05, grupo 9, tarea 9.6 (D12): paginación por cursor de
`configuracion/repository.py::listar_alicuotas_paginado`, mismo patrón que
`catalogo_repository.listar_categorias_paginado` (cursor por `nombre`,
codificado en base64, límite máximo 100)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.modules.configuracion import repository as configuracion_repository
from app.modules.identidad.models import Organizacion

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

_MOMENTO = datetime.now(UTC)


@pytest.fixture
def organizacion_id(db_session: Session) -> uuid.UUID:
    organizacion = Organizacion(
        id=uuid.uuid4(),
        nombre="Distribuidora de prueba",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Buenos_Aires",
        estado="ACTIVA",
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion.id


@pytest.fixture
def otra_organizacion_id(db_session: Session) -> uuid.UUID:
    organizacion = Organizacion(
        id=uuid.uuid4(),
        nombre="Otra distribuidora",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Buenos_Aires",
        estado="ACTIVA",
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion.id


def _crear_alicuota(
    db_session: Session, organizacion_id: uuid.UUID, *, nombre: str, activo: bool = True
) -> uuid.UUID:
    alicuota = configuracion_repository.crear_alicuota(
        organizacion_id,
        db_session,
        nombre=nombre,
        valor="0.210000",  # type: ignore[arg-type]
        momento=_MOMENTO,
        activo=activo,
    )
    return alicuota.id


def test_recorrido_completo_por_cursor_sin_repetir_incluye_inactivas(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    """D12: el listado devuelve activas e inactivas -- el cliente filtra."""
    _crear_alicuota(db_session, organizacion_id, nombre="10,5%")
    _crear_alicuota(db_session, organizacion_id, nombre="21%")
    _crear_alicuota(db_session, organizacion_id, nombre="27%", activo=False)

    vistos: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        pagina, cursor_siguiente = configuracion_repository.listar_alicuotas_paginado(
            organizacion_id, db_session, cursor=cursor, limite=1
        )
        vistos.extend(alicuota.nombre for alicuota in pagina)
        if cursor_siguiente is None:
            break
        cursor = cursor_siguiente

    assert vistos == ["10,5%", "21%", "27%"]
    assert len(set(vistos)) == len(vistos)


def test_nunca_devuelve_alicuotas_de_otra_organizacion(
    db_session: Session, organizacion_id: uuid.UUID, otra_organizacion_id: uuid.UUID
) -> None:
    _crear_alicuota(db_session, organizacion_id, nombre="21%")
    _crear_alicuota(db_session, otra_organizacion_id, nombre="27%")

    pagina, cursor_siguiente = configuracion_repository.listar_alicuotas_paginado(
        organizacion_id, db_session, cursor=None, limite=100
    )

    assert [alicuota.nombre for alicuota in pagina] == ["21%"]
    assert cursor_siguiente is None
