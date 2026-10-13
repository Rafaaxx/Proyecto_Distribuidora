"""Change 15, tarea 8.5 (D8): el texto de la constancia de STK-09 en la auditoría.

Reglas citadas: STK-09, AUD-02.
"""

from __future__ import annotations

from uuid import uuid4

from app.commands.auditoria import (
    DatosDeAuditoria,
    constancia_de_ubicacion_tomada,
    observacion_de_ubicacion_tomada,
)


def test_una_jornada_nombra_la_regla_y_la_jornada() -> None:
    jornada = uuid4()

    assert (
        observacion_de_ubicacion_tomada([jornada])
        == f"STK-09: ubicación tomada por la jornada {jornada}"
    )


def test_sin_ubicaciones_tomadas_no_hay_constancia() -> None:
    assert observacion_de_ubicacion_tomada([]) is None
    assert observacion_de_ubicacion_tomada([None, None]) is None


def test_varias_jornadas_se_nombran_sin_repetir_y_en_orden() -> None:
    a, b = sorted([uuid4(), uuid4()], key=str)

    texto = observacion_de_ubicacion_tomada([b, a, b, None])

    assert texto == f"STK-09: ubicación tomada por la jornada {a}, {b}"


def test_la_constancia_no_lleva_motivo() -> None:
    dato = constancia_de_ubicacion_tomada([uuid4()])

    assert isinstance(dato, DatosDeAuditoria)
    assert dato.motivo_id is None
    assert dato.observacion is not None
