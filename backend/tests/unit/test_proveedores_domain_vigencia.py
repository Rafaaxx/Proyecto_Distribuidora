"""Change 06, tarea 6.5: `elegir_vigente` es la referencia pura del orden
de D4 (`vigencia_desde DESC, creado_en DESC, id DESC`, entre los costos con
`vigencia_desde <= fecha`), usada para una propiedad Hypothesis que la
compara contra la consulta SQL en el grupo 7 (`ix_costo_informado__producto_vigencia`).
Acá solo se prueba la función pura en sí."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from app.modules.proveedores.domain.vigencia import CandidatoVigencia, elegir_vigente


def _candidato(
    *,
    id_: object = None,
    vigencia_desde: date,
    creado_en: datetime,
) -> CandidatoVigencia:
    return CandidatoVigencia(
        id=id_ if id_ is not None else uuid4(),  # type: ignore[arg-type]
        vigencia_desde=vigencia_desde,
        creado_en=creado_en,
        costo_base=Decimal("1500.000000"),
    )


def test_ninguno_alcanza_la_fecha_devuelve_none() -> None:
    candidatos = [
        _candidato(vigencia_desde=date(2026, 9, 1), creado_en=datetime(2026, 9, 1, tzinfo=UTC))
    ]
    assert elegir_vigente(candidatos, fecha=date(2026, 8, 31)) is None


def test_lista_vacia_devuelve_none() -> None:
    assert elegir_vigente([], fecha=date(2026, 9, 1)) is None


def test_elige_el_de_mayor_vigencia_desde_que_no_supera_la_fecha() -> None:
    anterior = _candidato(
        vigencia_desde=date(2026, 9, 1), creado_en=datetime(2026, 9, 1, tzinfo=UTC)
    )
    futuro = _candidato(
        vigencia_desde=date(2026, 10, 1), creado_en=datetime(2026, 9, 1, tzinfo=UTC)
    )

    assert elegir_vigente([anterior, futuro], fecha=date(2026, 9, 15)) is anterior
    assert elegir_vigente([anterior, futuro], fecha=date(2026, 10, 1)) is futuro


def test_misma_vigencia_desde_prevalece_el_mayor_creado_en() -> None:
    primero = _candidato(
        vigencia_desde=date(2026, 9, 1), creado_en=datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    )
    segundo = _candidato(
        vigencia_desde=date(2026, 9, 1), creado_en=datetime(2026, 9, 1, 11, 0, tzinfo=UTC)
    )

    assert elegir_vigente([primero, segundo], fecha=date(2026, 9, 1)) is segundo
    assert elegir_vigente([segundo, primero], fecha=date(2026, 9, 1)) is segundo


def test_misma_vigencia_desde_y_creado_en_desempata_por_id_mayor() -> None:
    id_menor = uuid4()
    id_mayor = uuid4()
    if id_menor > id_mayor:
        id_menor, id_mayor = id_mayor, id_menor

    misma_fecha = date(2026, 9, 1)
    mismo_creado_en = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    candidato_menor = _candidato(
        id_=id_menor, vigencia_desde=misma_fecha, creado_en=mismo_creado_en
    )
    candidato_mayor = _candidato(
        id_=id_mayor, vigencia_desde=misma_fecha, creado_en=mismo_creado_en
    )

    assert elegir_vigente([candidato_menor, candidato_mayor], fecha=misma_fecha) is candidato_mayor


def test_candidatos_futuros_se_ignoran_aunque_su_id_sea_mayor() -> None:
    vigente = _candidato(
        vigencia_desde=date(2026, 9, 1), creado_en=datetime(2026, 9, 1, tzinfo=UTC)
    )
    programado = _candidato(
        vigencia_desde=date(2026, 12, 1), creado_en=datetime(2026, 9, 1, tzinfo=UTC)
    )

    assert elegir_vigente([vigente, programado], fecha=date(2026, 9, 15)) is vigente
