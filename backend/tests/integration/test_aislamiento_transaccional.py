"""Spec `integracion-continua`, escenario "Cada prueba de integración queda
aislada" (`docs/02-arquitectura.md` §15: aislamiento por transacción
revertida al final de cada prueba).

Dos pruebas escriben en la misma tabla usando `db_session`; ninguna ve lo
que escribió la otra, y al terminar la corrida la tabla queda vacía (la
transacción de cada prueba se revirtió, nunca se confirmó).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session


@pytest.fixture(scope="module", autouse=True)
def _tabla_de_prueba(_engine_de_sesion: Engine) -> Iterator[None]:
    with _engine_de_sesion.connect() as conexion:
        conexion.execute(
            text("CREATE TABLE aislamiento_prueba (id integer PRIMARY KEY, origen text)")
        )
        conexion.commit()

    try:
        yield
    finally:
        with _engine_de_sesion.connect() as conexion:
            conexion.execute(text("DROP TABLE IF EXISTS aislamiento_prueba"))
            conexion.commit()


def test_la_primera_prueba_no_ve_filas_de_otra_prueba(db_session: Session) -> None:
    filas_antes = db_session.execute(text("SELECT count(*) FROM aislamiento_prueba")).scalar_one()
    assert filas_antes == 0

    db_session.execute(text("INSERT INTO aislamiento_prueba (id, origen) VALUES (1, 'primera')"))
    db_session.flush()

    filas_propias = (
        db_session.execute(text("SELECT origen FROM aislamiento_prueba")).scalars().all()
    )
    assert filas_propias == ["primera"]


def test_la_segunda_prueba_tampoco_ve_la_fila_de_la_primera(db_session: Session) -> None:
    filas_antes = db_session.execute(text("SELECT count(*) FROM aislamiento_prueba")).scalar_one()
    # Si la transacción de la prueba anterior no se hubiera revertido, esta
    # cuenta ya sería 1 y la aserción siguiente fallaría.
    assert filas_antes == 0

    db_session.execute(text("INSERT INTO aislamiento_prueba (id, origen) VALUES (2, 'segunda')"))
    db_session.flush()

    filas_propias = (
        db_session.execute(text("SELECT origen FROM aislamiento_prueba")).scalars().all()
    )
    assert filas_propias == ["segunda"]


def test_ninguna_fila_de_las_dos_pruebas_anteriores_quedo_confirmada(
    _engine_de_sesion: Engine,
) -> None:
    # Fuera de cualquier `db_session` de prueba: si `db_session` confirmara
    # en vez de revertir, esta consulta encontraría las filas de los dos
    # tests anteriores.
    with _engine_de_sesion.connect() as conexion:
        total = conexion.execute(text("SELECT count(*) FROM aislamiento_prueba")).scalar_one()

    assert total == 0
