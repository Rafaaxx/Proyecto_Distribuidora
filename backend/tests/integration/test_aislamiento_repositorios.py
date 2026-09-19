"""INV-21, TR-08 (`docs/01-dominio.md` §20, §3): ningún usuario obtiene ni
modifica datos de otra organización. Se prueba a nivel de repositorio con
dos organizaciones reales (`design.md` D1: sin JWT todavía, el aislamiento
se verifica en la capa de datos).

Escenarios: "Una consulta nunca ve filas de otra organización", "Buscar por
identificador con la organización equivocada no encuentra nada", "Modificar
con la organización equivocada no cambia nada", "Desactivar un elemento de
otra organización no hace nada", "Una referencia cruzada entre
organizaciones se rechaza en la base" (tareas 6.4, 6.5).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.modules.configuracion import repository as configuracion_repository
from app.modules.identidad.models import Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


def _crear_organizacion(sesion: Session, nombre: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre=nombre,
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
        actualizado_por_id=None,
    )
    sesion.add(organizacion)
    sesion.flush()
    return organizacion


@pytest.fixture
def dos_organizaciones(db_session: Session) -> tuple[Organizacion, Organizacion]:
    org_a = _crear_organizacion(db_session, "Organización A")
    org_b = _crear_organizacion(db_session, "Organización B")
    return org_a, org_b


def test_listar_activos_nunca_ve_filas_de_otra_organizacion(
    db_session: Session, dos_organizaciones: tuple[Organizacion, Organizacion]
) -> None:
    org_a, org_b = dos_organizaciones
    configuracion_repository.crear_medio_pago(
        org_a.id, db_session, nombre="Efectivo", requiere_referencia=False, momento=MOMENTO
    )
    configuracion_repository.crear_medio_pago(
        org_b.id, db_session, nombre="Efectivo", requiere_referencia=False, momento=MOMENTO
    )

    medios_de_a = configuracion_repository.listar_medios_pago_activos(org_a.id, db_session)

    assert len(medios_de_a) == 1
    assert all(medio.organizacion_id == org_a.id for medio in medios_de_a)


def test_buscar_por_id_con_la_organizacion_equivocada_no_encuentra_nada(
    db_session: Session, dos_organizaciones: tuple[Organizacion, Organizacion]
) -> None:
    org_a, org_b = dos_organizaciones
    medio_de_a = configuracion_repository.crear_medio_pago(
        org_a.id, db_session, nombre="Transferencia", requiere_referencia=True, momento=MOMENTO
    )

    encontrado = configuracion_repository.obtener_medio_pago_por_id(
        org_b.id, db_session, medio_de_a.id
    )

    assert encontrado is None


def test_desactivar_con_la_organizacion_equivocada_no_cambia_nada(
    db_session: Session, dos_organizaciones: tuple[Organizacion, Organizacion]
) -> None:
    org_a, org_b = dos_organizaciones
    alicuota_de_a = configuracion_repository.crear_alicuota(
        org_a.id, db_session, nombre="21%", valor=Decimal("0.210000"), momento=MOMENTO
    )

    resultado = configuracion_repository.desactivar_alicuota(
        org_b.id, db_session, alicuota_de_a.id, momento=MOMENTO
    )

    assert resultado is None
    db_session.refresh(alicuota_de_a)
    assert alicuota_de_a.activo is True


def test_desactivar_un_elemento_de_otra_organizacion_no_hace_nada(
    db_session: Session, dos_organizaciones: tuple[Organizacion, Organizacion]
) -> None:
    org_a, org_b = dos_organizaciones
    motivo_de_a = configuracion_repository.crear_motivo(
        org_a.id, db_session, ambito="AJUSTE_STOCK", nombre="Rotura", momento=MOMENTO
    )

    resultado = configuracion_repository.desactivar_motivo(
        org_b.id, db_session, motivo_de_a.id, momento=MOMENTO
    )

    assert resultado is None
    activos_de_a = configuracion_repository.listar_motivos_activos(org_a.id, db_session)
    assert motivo_de_a.id in {motivo.id for motivo in activos_de_a}


def test_una_referencia_cruzada_entre_organizaciones_se_rechaza_en_la_base(
    db_session: Session, dos_organizaciones: tuple[Organizacion, Organizacion]
) -> None:
    """La base rechaza una FK compuesta cruzada aunque el código no valide
    nada: se ejercita con SQL crudo contra una tabla temporal con FK
    compuesta hacia `alicuota_iva`, replicando el patrón de `docs/03` §2.4."""
    org_a, org_b = dos_organizaciones
    alicuota_de_a = configuracion_repository.crear_alicuota(
        org_a.id, db_session, nombre="10,5%", valor=Decimal("0.105000"), momento=MOMENTO
    )
    db_session.flush()

    db_session.execute(
        text(
            "CREATE TABLE inv02_negativo_referencia_cruzada ("
            "id uuid PRIMARY KEY, organizacion_id uuid NOT NULL, alicuota_id uuid NOT NULL, "
            "CONSTRAINT fk_negativo__alicuota FOREIGN KEY (organizacion_id, alicuota_id) "
            "REFERENCES alicuota_iva (organizacion_id, id))"
        )
    )

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO inv02_negativo_referencia_cruzada "
                "(id, organizacion_id, alicuota_id) VALUES (:id, :org_b, :alicuota)"
            ),
            {"id": nuevo_id(), "org_b": org_b.id, "alicuota": alicuota_de_a.id},
        )
        db_session.flush()
