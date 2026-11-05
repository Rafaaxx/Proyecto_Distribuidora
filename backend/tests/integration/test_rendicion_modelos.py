"""Tarea 3.1 (change 24): los modelos `Rendicion` y `RendicionLinea` de `stock/models.py` y las
columnas de la entrega de `Jornada` mapean lo que crea la revisión `d2f4a6c8e0b1`; no declaran
carga diferida implícita (`CLAUDE.md` §4) y la base rechaza el `UPDATE` y el `DELETE` de
`app_runtime` sobre la rendición (INV-05). Que el modelo no se desvíe de la migración lo cubre
además `test_modelos_coinciden_con_migracion.py`.

Reglas citadas: INV-03, INV-05, RUT-05, RUT-06, `design.md` D1, D4, D5.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, delete, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql
from test_jornadas_migracion import _armar, _jornada
from test_rendicion_migracion import (
    COLUMNAS_DE_ENTREGA,
    COLUMNAS_LINEA,
    COLUMNAS_RENDICION,
    _linea,
    _rendicion,
)

from app.modules.stock.models import Jornada, Rendicion, RendicionLinea

MOMENTO = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
OTRO_MOMENTO = datetime(2026, 11, 4, 18, 0, tzinfo=UTC)


def _persistir_rendicion(sesion: Session) -> tuple[Jornada, Rendicion, RendicionLinea, UUID]:
    """Una jornada `EN_RENDICION` con entrega, su rendición y una línea, por el ORM."""
    entorno = _armar(sesion)
    jornada = Jornada(
        **_jornada(
            entorno,
            "EN_RENDICION",
            entregada_en=OTRO_MOMENTO,
            entrega_occurred_at=MOMENTO,
            entrega_secuencia=12,
        )  # type: ignore[arg-type]
    )
    sesion.add(jornada)
    sesion.flush()
    rendicion = Rendicion(**_rendicion(entorno, jornada.id, observacion="Contó el supervisor"))  # type: ignore[arg-type]
    sesion.add(rendicion)
    sesion.flush()
    producto_id = crear_producto_sql(sesion, entorno.organizacion_id)
    linea = RendicionLinea(**_linea(entorno, rendicion.id, producto_id))  # type: ignore[arg-type]
    sesion.add(linea)
    sesion.flush()
    return jornada, rendicion, linea, producto_id


def test_los_modelos_mapean_las_columnas_de_la_migracion() -> None:
    assert Rendicion.__tablename__ == "rendicion"
    assert RendicionLinea.__tablename__ == "rendicion_linea"
    assert {c.name for c in Rendicion.__table__.columns} == set(COLUMNAS_RENDICION)
    assert {c.name for c in RendicionLinea.__table__.columns} == set(COLUMNAS_LINEA)
    assert set(COLUMNAS_DE_ENTREGA) <= {c.name for c in Jornada.__table__.columns}


def test_los_modelos_de_la_rendicion_no_declaran_relaciones() -> None:
    """`CLAUDE.md` §4: la carga de relaciones es siempre explícita; no hay carga diferida
    implícita."""
    for modelo in (Rendicion, RendicionLinea, Jornada):
        assert list(modelo.__mapper__.relationships) == []


def test_la_rendicion_y_su_linea_se_guardan_y_se_leen_con_consultas_explicitas(
    db_session: Session,
) -> None:
    jornada, rendicion, linea, producto_id = _persistir_rendicion(db_session)
    db_session.expire_all()

    leida = db_session.scalars(
        select(Rendicion).where(
            Rendicion.organizacion_id == rendicion.organizacion_id,
            Rendicion.jornada_id == jornada.id,
        )
    ).one()
    lineas = db_session.scalars(
        select(RendicionLinea).where(
            RendicionLinea.organizacion_id == leida.organizacion_id,
            RendicionLinea.rendicion_id == leida.id,
        )
    ).all()

    assert leida.observacion == "Contó el supervisor"
    assert [
        (x.producto_id, x.cantidad_esperada, x.cantidad_contada, x.diferencia) for x in lineas
    ] == [(producto_id, 40, 37, -3)]
    assert (lineas[0].stock_al_abrir, lineas[0].ingresos, lineas[0].ventas) == (10, 36, 8)
    assert (lineas[0].anulaciones, lineas[0].otros) == (2, 0)


def test_inv03_el_costo_de_la_linea_vuelve_como_decimal_exacto_o_nulo(
    db_session: Session,
) -> None:
    """CLAUDE.md §4: costo por unidad base `NUMERIC(18,6)`, nunca punto flotante; nulo si el
    producto no tenía promedio (D5)."""
    _, rendicion, linea, _ = _persistir_rendicion(db_session)
    sin_promedio = crear_producto_sql(db_session, rendicion.organizacion_id, nombre="Agua 500")
    sobrante = RendicionLinea(
        id=uuid4(),
        organizacion_id=rendicion.organizacion_id,
        rendicion_id=rendicion.id,
        producto_id=sin_promedio,
        stock_al_abrir=0,
        ingresos=0,
        ventas=0,
        anulaciones=0,
        otros=0,
        cantidad_esperada=0,
        cantidad_contada=2,
        diferencia=2,
        costo_unitario=None,
    )
    db_session.add(sobrante)
    db_session.flush()
    db_session.expire_all()

    assert linea.costo_unitario == Decimal("1050.000000")
    assert isinstance(linea.costo_unitario, Decimal)
    assert sobrante.costo_unitario is None


def test_la_entrega_de_la_jornada_se_lee_con_sus_tres_datos(db_session: Session) -> None:
    jornada, _, _, _ = _persistir_rendicion(db_session)
    db_session.expire_all()

    assert jornada.entregada_en == OTRO_MOMENTO
    assert jornada.entrega_occurred_at == MOMENTO
    assert jornada.entrega_secuencia == 12


def test_una_jornada_sin_entrega_tiene_los_tres_datos_nulos(db_session: Session) -> None:
    entorno = _armar(db_session)
    jornada = Jornada(**_jornada(entorno, "ABIERTA"))  # type: ignore[arg-type]
    db_session.add(jornada)
    db_session.flush()
    db_session.expire_all()

    assert (jornada.entregada_en, jornada.entrega_occurred_at, jornada.entrega_secuencia) == (
        None,
        None,
        None,
    )


def test_la_base_rechaza_la_entrega_parcial_guardada_por_el_modelo(db_session: Session) -> None:
    entorno = _armar(db_session)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.add(Jornada(**_jornada(entorno, "ABIERTA", entrega_secuencia=1)))  # type: ignore[arg-type]
        db_session.flush()
    assert "ck_jornada__entrega_coherente" in str(error.value)


def test_inv05_app_runtime_no_actualiza_ni_borra_la_rendicion_por_el_orm(
    _engine_de_sesion: Engine, app_runtime_engine: Engine
) -> None:
    """INV-05: con datos reales confirmados, el `UPDATE` y el `DELETE` que arma el ORM los
    rechaza la base por falta de privilegios; la entrega de la jornada sí se puede escribir."""
    with Session(_engine_de_sesion) as sesion:
        jornada, rendicion, linea, _ = _persistir_rendicion(sesion)
        sesion.commit()
        ids = (jornada.id, jornada.organizacion_id, jornada.usuario_id, rendicion.id, linea.id)
    jornada_id, organizacion_id, usuario_id, rendicion_id, linea_id = ids

    try:
        with Session(app_runtime_engine) as sesion:
            for sentencia in (
                update(Rendicion).where(Rendicion.id == rendicion_id).values(observacion="otra"),
                update(RendicionLinea).where(RendicionLinea.id == linea_id).values(diferencia=0),
                delete(Rendicion).where(Rendicion.id == rendicion_id),
                delete(RendicionLinea).where(RendicionLinea.id == linea_id),
            ):
                with pytest.raises(ProgrammingError) as error:
                    sesion.execute(sentencia)
                assert "permission denied" in str(error.value)
                sesion.rollback()

            with pytest.raises(ProgrammingError) as error:
                sesion.execute(
                    update(Jornada).where(Jornada.id == jornada_id).values(usuario_id=uuid4())
                )
            assert "permission denied" in str(error.value)
            sesion.rollback()

            actualizadas = sesion.execute(
                update(Jornada)
                .where(Jornada.organizacion_id == organizacion_id, Jornada.id == jornada_id)
                .values(entrega_secuencia=13)
            ).rowcount
            sesion.commit()
            assert actualizadas == 1
        _ = usuario_id
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
