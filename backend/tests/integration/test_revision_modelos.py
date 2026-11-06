"""Tarea 3.1 (change 25): el modelo `ComandoRechazado`, las columnas nuevas de `ComandoCuarentena`
y `CODIGOS_OBSERVACION` con `PRODUCTO_DESACTIVADO` mapean lo que crea la revisión
`e3a5c7d9f1b2`; no declaran carga diferida implícita (`CLAUDE.md` §4) y la base rechaza con
`app_runtime` el `UPDATE` del código o del detalle de una observación y el `DELETE` de las tres
tablas (INV-05). Que el modelo no se desvíe de la migración lo cubre además
`test_modelos_coinciden_con_migracion.py`.

Reglas citadas: INV-05, SYN-06, SYN-07, SYN-08, `design.md` D2, D6, D7, D10.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Engine, delete, select, text, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker as crear_sessionmaker
from test_jornadas_migracion import _armar, _jornada
from test_revision_migracion import (
    COLUMNAS_NUEVAS_CUARENTENA,
    COLUMNAS_RECHAZO,
    _comando_con_observacion,
    _cuarentena,
    _rechazo,
    _resuelto,
)

from app.modules.sync.models import (
    CODIGOS_OBSERVACION,
    ComandoCuarentena,
    ComandoRechazado,
    Observacion,
)

MOMENTO = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
OTRO_MOMENTO = datetime(2026, 11, 5, 18, 0, tzinfo=UTC)


def test_syn07_el_catalogo_de_observaciones_suma_producto_desactivado() -> None:
    assert "PRODUCTO_DESACTIVADO" in CODIGOS_OBSERVACION
    assert len(CODIGOS_OBSERVACION) == len(set(CODIGOS_OBSERVACION)) == 18


def test_los_modelos_mapean_las_columnas_de_la_migracion() -> None:
    assert ComandoRechazado.__tablename__ == "comando_rechazado"
    assert {c.name for c in ComandoRechazado.__table__.columns} == set(COLUMNAS_RECHAZO)
    assert set(COLUMNAS_NUEVAS_CUARENTENA) <= {c.name for c in ComandoCuarentena.__table__.columns}


def test_los_modelos_no_declaran_relaciones() -> None:
    """`CLAUDE.md` §4: la carga de relaciones es siempre explícita; no hay carga diferida
    implícita."""
    for modelo in (ComandoRechazado, ComandoCuarentena, Observacion):
        assert list(modelo.__mapper__.relationships) == []


def test_el_rechazo_se_guarda_y_se_lee_con_su_contenido_y_su_jornada(
    db_session: Session,
) -> None:
    entorno = _armar(db_session)
    jornada = _jornada(entorno, "ABIERTA")
    db_session.execute(
        text(
            "INSERT INTO jornada ("
            + ", ".join(jornada)
            + ") VALUES ("
            + ", ".join(f":{c}" for c in jornada)
            + ")"
        ),
        jornada,
    )
    contenido = {"cliente_id": str(uuid4()), "lineas": [{"cantidad": 3}]}
    rechazo = ComandoRechazado(
        **{**_rechazo(entorno, jornada_id=jornada["id"]), "contenido": contenido}  # type: ignore[arg-type]
    )
    db_session.add(rechazo)
    db_session.flush()
    db_session.expire_all()

    leido = db_session.scalars(
        select(ComandoRechazado).where(
            ComandoRechazado.organizacion_id == entorno.organizacion_id,
            ComandoRechazado.operation_id == rechazo.operation_id,
        )
    ).one()

    assert leido.contenido == contenido
    assert (leido.estado, leido.jornada_id, leido.secuencia) == ("PENDIENTE", jornada["id"], 7)
    assert (leido.resuelto_por_id, leido.resuelto_en, leido.vinculo_tipo) == (None, None, None)


def test_el_rechazo_resuelto_conserva_comentario_y_vinculo(db_session: Session) -> None:
    entorno = _armar(db_session)
    vinculo_id = uuid4()
    db_session.add(
        ComandoRechazado(
            **{**_resuelto(entorno, vinculo_tipo="VENTA", vinculo_id=vinculo_id), "contenido": {}}  # type: ignore[arg-type]
        )
    )
    db_session.flush()
    db_session.expire_all()

    leido = db_session.scalars(
        select(ComandoRechazado).where(ComandoRechazado.organizacion_id == entorno.organizacion_id)
    ).one()

    assert leido.estado == "RESUELTO"
    assert (leido.resuelto_por_id, leido.resuelto_en) == (entorno.usuario_2_id, OTRO_MOMENTO)
    assert (leido.comentario, leido.vinculo_tipo, leido.vinculo_id) == (
        "El cliente devolvió la mercadería",
        "VENTA",
        vinculo_id,
    )


def test_la_cuarentena_revisada_se_lee_con_comentario_y_vinculo(db_session: Session) -> None:
    entorno = _armar(db_session)
    vinculo_id = uuid4()
    datos = _cuarentena(
        entorno,
        revisado_en=OTRO_MOMENTO,
        revisado_por_id=entorno.usuario_2_id,
        comentario="Cargada con conexión",
        vinculo_tipo="COBRANZA",
        vinculo_id=vinculo_id,
    )
    db_session.add(ComandoCuarentena(**{**datos, "contenido": {}}))  # type: ignore[arg-type]
    db_session.flush()
    db_session.expire_all()

    leida = db_session.scalars(
        select(ComandoCuarentena).where(
            ComandoCuarentena.organizacion_id == entorno.organizacion_id
        )
    ).one()

    assert (leida.comentario, leida.vinculo_tipo, leida.vinculo_id) == (
        "Cargada con conexión",
        "COBRANZA",
        vinculo_id,
    )
    assert leida.revisado_por_id == entorno.usuario_2_id


def test_la_observacion_producto_desactivado_se_guarda_por_el_orm(db_session: Session) -> None:
    entorno = _armar(db_session)
    observacion_id = _comando_con_observacion(db_session, entorno, codigo="PRODUCTO_DESACTIVADO")
    db_session.expire_all()

    leida = db_session.scalars(select(Observacion).where(Observacion.id == observacion_id)).one()

    assert (leida.codigo, leida.estado, leida.comentario) == (
        "PRODUCTO_DESACTIVADO",
        "PENDIENTE",
        None,
    )


@pytest.mark.parametrize(
    "sentencia",
    [
        update(Observacion).values(codigo="STOCK_NEGATIVO"),
        update(Observacion).values(detalle={"x": 1}),
        delete(Observacion),
        delete(ComandoRechazado),
        delete(ComandoCuarentena),
        update(ComandoRechazado).values(contenido={}),
    ],
    ids=[
        "update-codigo-observacion",
        "update-detalle-observacion",
        "delete-observacion",
        "delete-rechazo",
        "delete-cuarentena",
        "update-contenido-rechazo",
    ],
)
def test_inv05_la_base_rechaza_con_app_runtime_lo_que_los_modelos_no_deben_hacer(
    app_runtime_engine: Engine, sentencia: object
) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(sentencia)  # type: ignore[call-overload]
    assert "permission denied" in str(error.value)


def test_el_runtime_resuelve_por_el_orm_las_columnas_de_la_resolucion(
    _engine_de_sesion: Engine, app_runtime_engine: Engine
) -> None:
    """Control positivo: el `UPDATE` ORM de las columnas de la resolución sí pasa."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        observacion_id = _comando_con_observacion(sesion, entorno)
        sesion.commit()
    try:
        with crear_sessionmaker(app_runtime_engine).begin() as sesion:
            sesion.execute(
                update(Observacion)
                .where(Observacion.id == observacion_id)
                .values(
                    estado="RESUELTA",
                    resuelto_por_id=entorno.usuario_2_id,
                    resuelto_en=OTRO_MOMENTO,
                    comentario="ok",
                )
            )
        with Session(_engine_de_sesion) as sesion:
            leida = sesion.scalars(
                select(Observacion).where(Observacion.id == observacion_id)
            ).one()
            assert (leida.estado, leida.comentario) == ("RESUELTA", "ok")
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
