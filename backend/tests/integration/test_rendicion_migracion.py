"""Tarea 2.1 (change 24): la revisión `d2f4a6c8e0b1` crea `rendicion` y `rendicion_linea`, agrega a
`jornada` los datos de la entrega del día, rehace el `CHECK` de `observacion.codigo` con
`JORNADA_RENDIDA` y da sus privilegios a `app_runtime` (`design.md` D1, D4, D5, D7; `03` §9).

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_jornadas_migracion.py`, de donde toma los armados de datos); que el modelo no se desvíe de
la migración lo cubre `test_modelos_coinciden_con_migracion.py`.

Reglas citadas: INV-02, INV-03, INV-05, INV-21, RUT-05, RUT-06, SYN-07, `04` §2.1 punto 4.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from conftest import cabeza_de_alembic
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql
from test_jornadas_migracion import (
    Entorno,
    _alembic,
    _armar,
    _columnas,
    _columnas_con_update,
    _dejar_en_head,
    _insertar,
    _jornada,
    _privilegios_de_tabla,
    _restricciones,
    _revision_actual,
    _tablas_existentes,
)

REVISION = "d2f4a6c8e0b1"
REVISION_ANTERIOR = "b7d3f1a9c2e4"  # `descripcion_permitir_stock_negativo`, la previa al change 24.
REVISION_HEAD = (
    cabeza_de_alembic()
)  # la cabeza actual, leida de Alembic (un downgrade abortado la deja ahi).
MOMENTO = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
OTRO_MOMENTO = datetime(2026, 11, 4, 18, 0, tzinfo=UTC)
CODIGO_NUEVO = "JORNADA_RENDIDA"

COLUMNAS_RENDICION = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "jornada_id": ("uuid", False),
    "observacion": ("text", True),
    "operation_id": ("uuid", False),
    "usuario_id": ("uuid", False),
    "dispositivo_id": ("uuid", False),
    "occurred_at": ("timestamp with time zone", False),
    "registered_at": ("timestamp with time zone", False),
}
COLUMNAS_LINEA = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "rendicion_id": ("uuid", False),
    "producto_id": ("uuid", False),
    "stock_al_abrir": ("integer", False),
    "ingresos": ("integer", False),
    "ventas": ("integer", False),
    "anulaciones": ("integer", False),
    "otros": ("integer", False),
    "cantidad_esperada": ("integer", False),
    "cantidad_contada": ("integer", False),
    "diferencia": ("integer", False),
    "costo_unitario": ("numeric", True),
}
COLUMNAS_DE_ENTREGA = {
    "entregada_en": ("timestamp with time zone", True),
    "entrega_occurred_at": ("timestamp with time zone", True),
    "entrega_secuencia": ("integer", True),
}
FKS_RENDICION = {
    "fk_rendicion__organizacion",
    "fk_rendicion__jornada",
    "fk_rendicion__usuario",
    "fk_rendicion__dispositivo",
}
FKS_LINEA = {
    "fk_rendicion_linea__organizacion",
    "fk_rendicion_linea__rendicion",
    "fk_rendicion_linea__producto",
}


# --- armado de datos -------------------------------------------------------------------


def _rendicion(entorno: Entorno, jornada_id: UUID, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "jornada_id": jornada_id,
        "observacion": None,
        "operation_id": uuid4(),
        "usuario_id": entorno.usuario_2_id,
        "dispositivo_id": entorno.dispositivo_id,
        "occurred_at": OTRO_MOMENTO,
        "registered_at": OTRO_MOMENTO,
    }
    valores.update(cambios)
    return valores


def _linea(
    entorno: Entorno, rendicion_id: UUID, producto_id: UUID, **cambios: object
) -> dict[str, object]:
    """Vino A: 10 al abrir + 36 − 8 + 2 = 40 esperadas, 37 contadas, −3 (`design.md` D4)."""
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "rendicion_id": rendicion_id,
        "producto_id": producto_id,
        "stock_al_abrir": 10,
        "ingresos": 36,
        "ventas": 8,
        "anulaciones": 2,
        "otros": 0,
        "cantidad_esperada": 40,
        "cantidad_contada": 37,
        "diferencia": -3,
        "costo_unitario": Decimal("1050.000000"),
    }
    valores.update(cambios)
    return valores


def _armar_con_rendicion(sesion: Session) -> tuple[Entorno, UUID, UUID, UUID]:
    """Entorno con una jornada `EN_RENDICION`, su rendición y un producto; devuelve el entorno,
    el id de la jornada, el de la rendición y el del producto."""
    entorno = _armar(sesion)
    jornada = _jornada(entorno, "EN_RENDICION")
    _insertar(sesion, "jornada", jornada)
    rendicion = _rendicion(entorno, jornada["id"])  # type: ignore[arg-type]
    _insertar(sesion, "rendicion", rendicion)
    producto_id = crear_producto_sql(sesion, entorno.organizacion_id)
    return entorno, jornada["id"], rendicion["id"], producto_id  # type: ignore[return-value]


def _rechaza(sesion: Session, tabla: str, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        _insertar(sesion, tabla, valores)
    assert restriccion in str(error.value)


def _insertar_observacion(sesion: Session, entorno: Entorno, *, codigo: str) -> None:
    comando_id = uuid4()
    _insertar(
        sesion,
        "comando",
        {
            "id": comando_id,
            "organizacion_id": entorno.organizacion_id,
            "operation_id": uuid4(),
            "tipo": "VENTA_CONFIRMAR",
            "version": 1,
            "modo": "OFFLINE",
            "usuario_id": entorno.usuario_id,
            "dispositivo_id": entorno.dispositivo_id,
            "secuencia": 1,
            "huella": f"huella-{uuid4().hex}",
            "app_version": "1.0.0",
            "estado": "ACEPTADO_CON_OBSERVACIONES",
            "occurred_at": MOMENTO,
            "registered_at": MOMENTO,
        },
    )
    _insertar(
        sesion,
        "observacion",
        {
            "id": uuid4(),
            "organizacion_id": entorno.organizacion_id,
            "comando_id": comando_id,
            "operacion_tipo": "VENTA_CONFIRMAR",
            "operacion_id": uuid4(),
            "codigo": codigo,
            "estado": "PENDIENTE",
        },
    )


# --- estructura de las tablas nuevas (D1, D4, D5) --------------------------------------


def test_las_columnas_de_rendicion_y_de_su_linea_son_las_del_design(
    _engine_de_sesion: Engine,
) -> None:
    assert _columnas(_engine_de_sesion, "rendicion") == COLUMNAS_RENDICION
    assert _columnas(_engine_de_sesion, "rendicion_linea") == COLUMNAS_LINEA


def test_inv03_el_costo_unitario_es_numeric_18_6_y_nulable(_engine_de_sesion: Engine) -> None:
    """CLAUDE.md §4: costo por unidad base `NUMERIC(18,6)`; nulo si el producto no tenía
    promedio (D5)."""
    with _engine_de_sesion.connect() as conexion:
        precision, escala = conexion.execute(
            text(
                "SELECT numeric_precision, numeric_scale FROM information_schema.columns "
                "WHERE table_name = 'rendicion_linea' AND column_name = 'costo_unitario'"
            )
        ).one()
    assert (precision, escala) == (18, 6)
    assert COLUMNAS_LINEA["costo_unitario"] == ("numeric", True)


def test_inv02_las_claves_foraneas_son_compuestas_con_la_organizacion(
    _engine_de_sesion: Engine,
) -> None:
    for tabla, esperadas in (("rendicion", FKS_RENDICION), ("rendicion_linea", FKS_LINEA)):
        foraneas = _restricciones(_engine_de_sesion, tabla, "f")
        assert set(foraneas) == esperadas
        for nombre, definicion in foraneas.items():
            if nombre.endswith("__organizacion"):
                continue
            assert "FOREIGN KEY (organizacion_id," in definicion, nombre


def test_las_restricciones_de_unicidad_son_las_del_design(_engine_de_sesion: Engine) -> None:
    rendicion = _restricciones(_engine_de_sesion, "rendicion", "u")
    assert rendicion["ux_rendicion__org_id"] == "UNIQUE (organizacion_id, id)"
    assert rendicion["ux_rendicion__jornada"] == "UNIQUE (organizacion_id, jornada_id)"
    linea = _restricciones(_engine_de_sesion, "rendicion_linea", "u")
    assert linea["ux_rendicion_linea__org_id"] == "UNIQUE (organizacion_id, id)"
    assert (
        linea["ux_rendicion_linea__rendicion_producto"]
        == "UNIQUE (organizacion_id, rendicion_id, producto_id)"
    )


def test_una_jornada_tiene_a_lo_sumo_una_rendicion(db_session: Session) -> None:
    entorno, jornada_id, _, _ = _armar_con_rendicion(db_session)
    _rechaza(
        db_session,
        "rendicion",
        _rendicion(entorno, jornada_id),
        "ux_rendicion__jornada",
    )


def test_una_rendicion_tiene_a_lo_sumo_una_linea_por_producto(db_session: Session) -> None:
    entorno, _, rendicion_id, producto_id = _armar_con_rendicion(db_session)
    _insertar(db_session, "rendicion_linea", _linea(entorno, rendicion_id, producto_id))
    _rechaza(
        db_session,
        "rendicion_linea",
        _linea(entorno, rendicion_id, producto_id, cantidad_contada=40, diferencia=0),
        "ux_rendicion_linea__rendicion_producto",
    )


def test_inv02_una_referencia_de_otra_organizacion_se_rechaza(db_session: Session) -> None:
    entorno, _, rendicion_id, _ = _armar_con_rendicion(db_session)
    ajeno = _armar(db_session)
    producto_ajeno = crear_producto_sql(db_session, ajeno.organizacion_id)
    otra_jornada = _jornada(entorno, "EN_RENDICION", ubicacion_id=entorno.vehiculo_2_id)
    otra_jornada.update(usuario_id=entorno.usuario_2_id, dispositivo_id=entorno.dispositivo_2_id)
    _insertar(db_session, "jornada", otra_jornada)
    jornada_ajena = _jornada(ajeno, "EN_RENDICION")
    _insertar(db_session, "jornada", jornada_ajena)

    _rechaza(
        db_session,
        "rendicion",
        _rendicion(entorno, jornada_ajena["id"]),  # type: ignore[arg-type]
        "fk_rendicion__jornada",
    )
    _rechaza(
        db_session,
        "rendicion",
        _rendicion(entorno, otra_jornada["id"], usuario_id=ajeno.usuario_id),  # type: ignore[arg-type]
        "fk_rendicion__usuario",
    )
    _rechaza(
        db_session,
        "rendicion",
        _rendicion(entorno, otra_jornada["id"], dispositivo_id=ajeno.dispositivo_id),  # type: ignore[arg-type]
        "fk_rendicion__dispositivo",
    )
    _rechaza(
        db_session,
        "rendicion_linea",
        _linea(entorno, rendicion_id, producto_ajeno),
        "fk_rendicion_linea__producto",
    )


@pytest.mark.parametrize("largo", [0, 501])
def test_la_observacion_va_de_1_a_500_caracteres(db_session: Session, largo: int) -> None:
    entorno = _armar(db_session)
    jornada = _jornada(entorno, "EN_RENDICION")
    _insertar(db_session, "jornada", jornada)
    _rechaza(
        db_session,
        "rendicion",
        _rendicion(entorno, jornada["id"], observacion="x" * largo),  # type: ignore[arg-type]
        "ck_rendicion__observacion",
    )
    _insertar(
        db_session,
        "rendicion",
        _rendicion(entorno, jornada["id"], observacion="x" * 500),  # type: ignore[arg-type]
    )


# --- los CHECK de la línea (D4, D5) ------------------------------------------------------


@pytest.mark.parametrize(
    ("cambios", "restriccion"),
    [
        # diferencia = contada − esperada
        ({"diferencia": -2}, "ck_rendicion_linea__diferencia"),
        ({"cantidad_contada": 38}, "ck_rendicion_linea__diferencia"),
        # esperada = al abrir + ingresos − ventas + anulaciones + otros
        ({"cantidad_esperada": 41, "diferencia": -4}, "ck_rendicion_linea__esperada"),
        ({"otros": 1}, "ck_rendicion_linea__esperada"),
        # contada >= 0
        (
            {"cantidad_contada": -1, "diferencia": -41},
            "ck_rendicion_linea__contada",
        ),
    ],
)
def test_los_check_de_la_linea_rechazan_lo_incoherente(
    db_session: Session, cambios: dict[str, object], restriccion: str
) -> None:
    entorno, _, rendicion_id, producto_id = _armar_con_rendicion(db_session)
    _rechaza(
        db_session,
        "rendicion_linea",
        _linea(entorno, rendicion_id, producto_id, **cambios),
        restriccion,
    )


def test_la_linea_coherente_se_acepta_con_o_sin_costo_y_con_diferencia_cero(
    db_session: Session,
) -> None:
    entorno, _, rendicion_id, producto_id = _armar_con_rendicion(db_session)
    segundo = crear_producto_sql(db_session, entorno.organizacion_id, nombre="Agua 500")
    tercero = crear_producto_sql(db_session, entorno.organizacion_id, nombre="Agua 1500")
    _insertar(db_session, "rendicion_linea", _linea(entorno, rendicion_id, producto_id))
    # Sobrante de un producto sin promedio: esperado 0, contado 2, costo nulo (D5).
    _insertar(
        db_session,
        "rendicion_linea",
        _linea(
            entorno,
            rendicion_id,
            segundo,
            stock_al_abrir=0,
            ingresos=0,
            ventas=0,
            anulaciones=0,
            cantidad_esperada=0,
            cantidad_contada=2,
            diferencia=2,
            costo_unitario=None,
        ),
    )
    # Sin diferencia: 12 esperadas y 12 contadas.
    _insertar(
        db_session,
        "rendicion_linea",
        _linea(
            entorno,
            rendicion_id,
            tercero,
            stock_al_abrir=12,
            ingresos=0,
            ventas=0,
            anulaciones=0,
            cantidad_esperada=12,
            cantidad_contada=12,
            diferencia=0,
        ),
    )


# --- los datos de la entrega en `jornada` (D1) --------------------------------------------


def test_las_columnas_de_jornada_suman_los_datos_de_la_entrega(_engine_de_sesion: Engine) -> None:
    columnas = _columnas(_engine_de_sesion, "jornada")
    for nombre, definicion in COLUMNAS_DE_ENTREGA.items():
        assert columnas[nombre] == definicion


@pytest.mark.parametrize("estado", ["ABIERTA", "EN_RENDICION", "CERRADA", "LIBERADA"])
def test_la_entrega_completa_se_acepta_en_cualquier_estado(
    db_session: Session, estado: str
) -> None:
    """RUT-05, RUT-09: se entrega una `ABIERTA`; después puede rendirse, cerrarse o liberarse
    sin perder el dato de la entrega."""
    entorno = _armar(db_session)
    _insertar(
        db_session,
        "jornada",
        _jornada(
            entorno,
            estado,
            entregada_en=OTRO_MOMENTO,
            entrega_occurred_at=MOMENTO,
            entrega_secuencia=12,
        ),
    )


@pytest.mark.parametrize(
    "cambios",
    [
        {"entregada_en": OTRO_MOMENTO},
        {"entrega_occurred_at": MOMENTO},
        {"entrega_secuencia": 12},
        {"entregada_en": OTRO_MOMENTO, "entrega_occurred_at": MOMENTO},
        {"entregada_en": OTRO_MOMENTO, "entrega_secuencia": 12},
        {"entrega_occurred_at": MOMENTO, "entrega_secuencia": 12},
    ],
)
def test_la_entrega_parcial_se_rechaza_en_la_base(
    db_session: Session, cambios: dict[str, object]
) -> None:
    """Los tres datos de la entrega son nulos juntos o presentes juntos."""
    entorno = _armar(db_session)
    _rechaza(
        db_session,
        "jornada",
        _jornada(entorno, "ABIERTA", **cambios),
        "ck_jornada__entrega_coherente",
    )


def test_la_jornada_sin_entrega_sigue_siendo_valida_en_todos_los_estados(
    db_session: Session,
) -> None:
    """D1 y D8: las jornadas anteriores al change no tienen entrega."""
    entorno = _armar(db_session)
    _insertar(db_session, "jornada", _jornada(entorno, "CERRADA"))


# --- observación nueva (D7, SYN-07) --------------------------------------------------------


def test_syn07_ck_observacion_codigo_admite_jornada_rendida(db_session: Session) -> None:
    _insertar_observacion(db_session, _armar(db_session), codigo=CODIGO_NUEVO)


@pytest.mark.parametrize("codigo", ["JORNADA_RENDIDA_", "jornada_rendida", "JORNADA", ""])
def test_syn07_ck_observacion_codigo_sigue_rechazando_lo_que_no_es_del_catalogo(
    db_session: Session, codigo: str
) -> None:
    entorno = _armar(db_session)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_observacion(db_session, entorno, codigo=codigo)
    assert "ck_observacion__codigo" in str(error.value)


def test_syn07_los_codigos_anteriores_siguen_admitidos(db_session: Session) -> None:
    entorno = _armar(db_session)
    for codigo in ("JORNADA_LIBERADA", "AUTORIZACION_OFFLINE", "UBICACION_TOMADA_AL_SINCRONIZAR"):
        _insertar_observacion(db_session, entorno, codigo=codigo)


# --- privilegios (INV-05) ------------------------------------------------------------------


@pytest.mark.parametrize("tabla", ["rendicion", "rendicion_linea"])
def test_inv05_app_runtime_solo_tiene_select_e_insert_en_las_tablas_de_la_rendicion(
    app_runtime_engine: Engine, tabla: str
) -> None:
    assert _privilegios_de_tabla(app_runtime_engine, tabla) == {"SELECT", "INSERT"}
    assert _columnas_con_update(app_runtime_engine, tabla) == set()


def test_inv05_app_runtime_solo_agrega_el_update_de_las_tres_columnas_de_la_entrega(
    app_runtime_engine: Engine,
) -> None:
    columnas = _columnas_con_update(app_runtime_engine, "jornada")
    assert set(COLUMNAS_DE_ENTREGA) <= columnas
    # Lo que no se actualiza ni antes ni ahora: los datos de la apertura.
    assert not columnas & {
        "ubicacion_id",
        "usuario_id",
        "dispositivo_id",
        "abierta_en",
        "operation_id",
        "organizacion_id",
    }


@pytest.mark.parametrize(
    "sentencia",
    [
        "DELETE FROM rendicion",
        "DELETE FROM rendicion_linea",
        "UPDATE rendicion SET observacion = 'x'",
        "UPDATE rendicion_linea SET cantidad_contada = 0",
    ],
)
def test_inv05_app_runtime_no_modifica_ni_borra_una_rendicion(
    app_runtime_engine: Engine, sentencia: str
) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(sentencia))
    assert "permission denied" in str(error.value)


def test_app_runtime_registra_la_entrega_de_una_jornada(
    _engine_de_sesion: Engine, app_runtime_engine: Engine
) -> None:
    """Control positivo: lo que sí puede escribir el runtime (la entrega) funciona."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        jornada = _jornada(entorno, "ABIERTA")
        _insertar(sesion, "jornada", jornada)
        sesion.commit()
    try:
        with app_runtime_engine.begin() as conexion:
            actualizadas = conexion.execute(
                text(
                    "UPDATE jornada SET entregada_en = :e, entrega_occurred_at = :o, "
                    "entrega_secuencia = 12 WHERE organizacion_id = :org AND id = :id"
                ),
                {
                    "e": OTRO_MOMENTO,
                    "o": MOMENTO,
                    "org": entorno.organizacion_id,
                    "id": jornada["id"],
                },
            ).rowcount
        assert actualizadas == 1
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))


# --- ciclo (`04` §2.1 punto 4) ---------------------------------------------------------------


def test_el_ciclo_upgrade_downgrade_upgrade_con_datos(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """Sube y baja limpio sobre una base con datos (jornadas abierta, en rendición y cerrada,
    sin rendiciones ni entregas): el `downgrade` quita las dos tablas y las tres columnas y
    vuelve el `CHECK` de observaciones; ninguna jornada cambia (TR-06)."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _insertar(sesion, "jornada", _jornada(entorno, "ABIERTA"))
        _insertar(
            sesion,
            "jornada",
            _jornada(
                entorno,
                "EN_RENDICION",
                ubicacion_id=entorno.vehiculo_2_id,
                usuario_id=entorno.usuario_2_id,
                dispositivo_id=entorno.dispositivo_2_id,
            ),
        )
        _insertar(sesion, "jornada", _jornada(entorno, "CERRADA"))
        _insertar_observacion(sesion, entorno, codigo="JORNADA_LIBERADA")
        sesion.commit()

    def instantanea() -> list[tuple[object, ...]]:
        with _engine_de_sesion.connect() as conexion:
            return [
                tuple(f)
                for f in conexion.execute(
                    text(
                        "SELECT id, estado, usuario_id, ubicacion_id, rendida_en, cerrada_en "
                        "FROM jornada ORDER BY id"
                    )
                )
            ]

    antes = instantanea()
    assert len(antes) == 3
    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
        assert not {"rendicion", "rendicion_linea"} & _tablas_existentes(_engine_de_sesion)
        assert not set(COLUMNAS_DE_ENTREGA) & set(_columnas(_engine_de_sesion, "jornada"))
        assert instantanea() == antes

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert {"rendicion", "rendicion_linea"} <= _tablas_existentes(_engine_de_sesion)
        assert set(COLUMNAS_DE_ENTREGA) <= set(_columnas(_engine_de_sesion, "jornada"))
        assert instantanea() == antes
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_aborta_con_mensaje_claro_si_hay_rendiciones(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """El libro de la rendición es de solo inserción (INV-05): no se borra al bajar."""
    with Session(_engine_de_sesion) as sesion:
        _armar_con_rendicion(sesion)
        sesion.commit()
    try:
        abortada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert abortada.returncode != 0
        assert "rendicion" in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_HEAD
        assert "rendicion" in _tablas_existentes(_engine_de_sesion)
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_aborta_con_mensaje_claro_si_hay_entregas(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _insertar(
            sesion,
            "jornada",
            _jornada(
                entorno,
                "ABIERTA",
                entregada_en=OTRO_MOMENTO,
                entrega_occurred_at=MOMENTO,
                entrega_secuencia=3,
            ),
        )
        sesion.commit()
    try:
        abortada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert abortada.returncode != 0
        assert "entrega" in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_HEAD
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_aborta_si_hay_observaciones_jornada_rendida(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """SYN-07: volver el `CHECK` atrás dejaría inválidas las observaciones nuevas."""
    with Session(_engine_de_sesion) as sesion:
        _insertar_observacion(sesion, _armar(sesion), codigo=CODIGO_NUEVO)
        sesion.commit()
    try:
        abortada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert abortada.returncode != 0
        assert CODIGO_NUEVO in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_HEAD

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("DELETE FROM observacion WHERE codigo = :c"), {"c": CODIGO_NUEVO})
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)
