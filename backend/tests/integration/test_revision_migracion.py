"""Tarea 2.1 (change 25): la revisión `e3a5c7d9f1b2` crea `comando_rechazado`, acota la resolución
de `observacion` y de `comando_cuarentena` (columnas, `CHECK` y `UPDATE` por columna) y suma
`PRODUCTO_DESACTIVADO` al catálogo de observaciones (`design.md` D2, D6, D7, D10; `03` §13).

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_rendicion_migracion.py`, de donde toma los armados de datos); que el modelo no se desvíe de
la migración lo cubre `test_modelos_coinciden_con_migracion.py`.

Reglas citadas: INV-02, INV-05, INV-21, SYN-06, SYN-07, SYN-08, `04` §2.1 punto 4.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from test_jornadas_migracion import (
    Entorno,
    _alembic,
    _armar,
    _columnas,
    _columnas_con_update,
    _dejar_en_head,
    _indice,
    _insertar,
    _jornada,
    _privilegios_de_tabla,
    _restricciones,
    _revision_actual,
    _tablas_existentes,
)

REVISION = "e3a5c7d9f1b2"
REVISION_ANTERIOR = "d2f4a6c8e0b1"  # `rendicion_de_jornada`, la previa al change 25.
MOMENTO = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
OTRO_MOMENTO = datetime(2026, 11, 5, 18, 0, tzinfo=UTC)
CODIGO_NUEVO = "PRODUCTO_DESACTIVADO"

COLUMNAS_RECHAZO = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "operation_id": ("uuid", False),
    "tipo": ("text", False),
    "version": ("integer", False),
    "modo": ("text", False),
    "usuario_id": ("uuid", False),
    "dispositivo_id": ("uuid", False),
    "jornada_id": ("uuid", True),
    "secuencia": ("integer", False),
    "occurred_at": ("timestamp with time zone", False),
    "app_version": ("text", False),
    "contenido": ("jsonb", False),
    "error_codigo": ("text", False),
    "recibido_en": ("timestamp with time zone", False),
    "estado": ("text", False),
    "resuelto_por_id": ("uuid", True),
    "resuelto_en": ("timestamp with time zone", True),
    "comentario": ("text", True),
    "vinculo_tipo": ("text", True),
    "vinculo_id": ("uuid", True),
}
COLUMNAS_NUEVAS_CUARENTENA = {
    "comentario": ("text", True),
    "vinculo_tipo": ("text", True),
    "vinculo_id": ("uuid", True),
}
FKS_RECHAZO = {
    "fk_comando_rechazado__organizacion",
    "fk_comando_rechazado__usuario",
    "fk_comando_rechazado__dispositivo",
    "fk_comando_rechazado__jornada",
    "fk_comando_rechazado__resuelto_por",
}
UPDATE_DE_RECHAZO = {
    "estado",
    "resuelto_por_id",
    "resuelto_en",
    "comentario",
    "vinculo_tipo",
    "vinculo_id",
}
UPDATE_DE_OBSERVACION = {"estado", "resuelto_por_id", "resuelto_en", "comentario"}
UPDATE_DE_CUARENTENA = {
    "revisado_en",
    "revisado_por_id",
    "comentario",
    "vinculo_tipo",
    "vinculo_id",
}


# --- armado de datos -------------------------------------------------------------------


def _rechazo(entorno: Entorno, **cambios: object) -> dict[str, object]:
    """Un rechazo `PENDIENTE` de una venta sin conexión, sin jornada."""
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "operation_id": uuid4(),
        "tipo": "VENTA_CONFIRMAR",
        "version": 1,
        "modo": "OFFLINE",
        "usuario_id": entorno.usuario_id,
        "dispositivo_id": entorno.dispositivo_id,
        "jornada_id": None,
        "secuencia": 7,
        "occurred_at": MOMENTO,
        "app_version": "1.0.0",
        "contenido": "{}",
        "error_codigo": "CLIENTE_INEXISTENTE",
        "recibido_en": OTRO_MOMENTO,
        "estado": "PENDIENTE",
        "resuelto_por_id": None,
        "resuelto_en": None,
        "comentario": None,
        "vinculo_tipo": None,
        "vinculo_id": None,
    }
    valores.update(cambios)
    return valores


def _resuelto(entorno: Entorno, **cambios: object) -> dict[str, object]:
    """Un rechazo `RESUELTO` por el segundo usuario, con comentario y sin vínculo."""
    valores: dict[str, object] = {
        "estado": "RESUELTO",
        "resuelto_por_id": entorno.usuario_2_id,
        "resuelto_en": OTRO_MOMENTO,
        "comentario": "El cliente devolvió la mercadería",
    }
    valores.update(cambios)
    return _rechazo(entorno, **valores)


def _insertar_rechazo(sesion: Session, valores: dict[str, object]) -> None:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f"CAST(:{c} AS jsonb)" if c == "contenido" else f":{c}" for c in valores)
    sesion.execute(
        text(f"INSERT INTO comando_rechazado ({columnas}) VALUES ({marcadores})"), valores
    )


def _rechaza(sesion: Session, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        _insertar_rechazo(sesion, valores)
    assert restriccion in str(error.value)


def _comando_con_observacion(
    sesion: Session, entorno: Entorno, *, codigo: str = "STOCK_NEGATIVO", **cambios: object
) -> UUID:
    """Un comando aceptado con una observación; devuelve el id de la observación."""
    comando_id, observacion_id = uuid4(), uuid4()
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
    valores: dict[str, object] = {
        "id": observacion_id,
        "organizacion_id": entorno.organizacion_id,
        "comando_id": comando_id,
        "operacion_tipo": "VENTA",
        "operacion_id": uuid4(),
        "codigo": codigo,
        "estado": "PENDIENTE",
    }
    valores.update(cambios)
    _insertar(sesion, "observacion", valores)
    return observacion_id


def _cuarentena(entorno: Entorno, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "dispositivo_id": entorno.dispositivo_id,
        "usuario_id": entorno.usuario_id,
        "operation_id": uuid4(),
        "tipo": "VENTA_CONFIRMAR",
        "contenido": "{}",
        "motivo": "DISPOSITIVO_REVOCADO",
        "recibido_en": MOMENTO,
    }
    valores.update(cambios)
    return valores


def _insertar_cuarentena(sesion: Session, valores: dict[str, object]) -> None:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f"CAST(:{c} AS jsonb)" if c == "contenido" else f":{c}" for c in valores)
    sesion.execute(
        text(f"INSERT INTO comando_cuarentena ({columnas}) VALUES ({marcadores})"), valores
    )


# --- estructura de `comando_rechazado` (D6) ---------------------------------------------------


def test_las_columnas_de_comando_rechazado_son_las_del_design(_engine_de_sesion: Engine) -> None:
    assert _columnas(_engine_de_sesion, "comando_rechazado") == COLUMNAS_RECHAZO


def test_inv02_las_claves_foraneas_son_compuestas_con_la_organizacion(
    _engine_de_sesion: Engine,
) -> None:
    foraneas = _restricciones(_engine_de_sesion, "comando_rechazado", "f")

    assert set(foraneas) == FKS_RECHAZO
    for nombre, definicion in foraneas.items():
        if nombre.endswith("__organizacion"):
            continue
        assert "FOREIGN KEY (organizacion_id," in definicion, nombre


def test_las_restricciones_de_unicidad_son_las_del_design(_engine_de_sesion: Engine) -> None:
    unicas = _restricciones(_engine_de_sesion, "comando_rechazado", "u")

    assert unicas["ux_comando_rechazado__org_id"] == "UNIQUE (organizacion_id, id)"
    assert (
        unicas["ux_comando_rechazado__org_operation_id"] == "UNIQUE (organizacion_id, operation_id)"
    )


def test_el_indice_de_pendientes_por_jornada_es_parcial(_engine_de_sesion: Engine) -> None:
    definicion = _indice(_engine_de_sesion, "ix_comando_rechazado__org_jornada_pendiente")

    assert "(organizacion_id, jornada_id)" in definicion
    assert "WHERE (estado = 'PENDIENTE'::text)" in definicion


def test_syn06_el_reenvio_del_mismo_operation_id_no_se_duplica(db_session: Session) -> None:
    entorno = _armar(db_session)
    primero = _rechazo(entorno)
    _insertar_rechazo(db_session, primero)

    _rechaza(
        db_session,
        _rechazo(entorno, operation_id=primero["operation_id"]),
        "ux_comando_rechazado__org_operation_id",
    )


def test_el_mismo_operation_id_en_otra_organizacion_es_otro_rechazo(db_session: Session) -> None:
    entorno, ajeno = _armar(db_session), _armar(db_session)
    operation_id = uuid4()

    _insertar_rechazo(db_session, _rechazo(entorno, operation_id=operation_id))
    _insertar_rechazo(db_session, _rechazo(ajeno, operation_id=operation_id))


def test_inv02_una_referencia_de_otra_organizacion_se_rechaza(db_session: Session) -> None:
    entorno, ajeno = _armar(db_session), _armar(db_session)
    jornada_ajena = _jornada(ajeno, "ABIERTA")
    _insertar(db_session, "jornada", jornada_ajena)

    _rechaza(
        db_session,
        _rechazo(entorno, usuario_id=ajeno.usuario_id),
        "fk_comando_rechazado__usuario",
    )
    _rechaza(
        db_session,
        _rechazo(entorno, dispositivo_id=ajeno.dispositivo_id),
        "fk_comando_rechazado__dispositivo",
    )
    _rechaza(
        db_session,
        _rechazo(entorno, jornada_id=jornada_ajena["id"]),
        "fk_comando_rechazado__jornada",
    )
    _rechaza(
        db_session,
        _resuelto(entorno, resuelto_por_id=ajeno.usuario_id),
        "fk_comando_rechazado__resuelto_por",
    )


def test_la_jornada_es_opcional_y_si_existe_se_acepta(db_session: Session) -> None:
    """D6: la jornada del sobre puede no existir en la organización; entonces queda nula."""
    entorno = _armar(db_session)
    jornada = _jornada(entorno, "ABIERTA")
    _insertar(db_session, "jornada", jornada)

    _insertar_rechazo(db_session, _rechazo(entorno, jornada_id=None))
    _insertar_rechazo(db_session, _rechazo(entorno, jornada_id=jornada["id"]))


# --- los CHECK de `comando_rechazado` (D6, D7) -----------------------------------------------


@pytest.mark.parametrize("modo", ["ONLINE", "OFFLINE"])
def test_el_modo_admite_online_y_offline(db_session: Session, modo: str) -> None:
    _insertar_rechazo(db_session, _rechazo(_armar(db_session), modo=modo))


def test_el_modo_inventado_se_rechaza(db_session: Session) -> None:
    _rechaza(db_session, _rechazo(_armar(db_session), modo="MIXTO"), "ck_comando_rechazado__modo")


def test_el_estado_inventado_se_rechaza(db_session: Session) -> None:
    _rechaza(
        db_session,
        _rechazo(_armar(db_session), estado="ARCHIVADO"),
        "ck_comando_rechazado__estado",
    )


def test_inv05_un_pendiente_y_un_resuelto_coherentes_se_aceptan(db_session: Session) -> None:
    entorno = _armar(db_session)

    _insertar_rechazo(db_session, _rechazo(entorno))
    _insertar_rechazo(db_session, _resuelto(entorno))
    _insertar_rechazo(db_session, _resuelto(entorno, vinculo_tipo="VENTA", vinculo_id=uuid4()))


@pytest.mark.parametrize(
    "cambios",
    [
        # PENDIENTE con algún dato de resolución
        {"resuelto_por_id": "usuario_2_id"},
        {"resuelto_en": OTRO_MOMENTO},
        {"comentario": "x"},
        {"vinculo_tipo": "VENTA", "vinculo_id": "nuevo"},
    ],
)
def test_un_pendiente_con_datos_de_resolucion_se_rechaza(
    db_session: Session, cambios: dict[str, object]
) -> None:
    entorno = _armar(db_session)
    valores = {
        clave: (
            entorno.usuario_2_id
            if valor == "usuario_2_id"
            else uuid4()
            if valor == "nuevo"
            else valor
        )
        for clave, valor in cambios.items()
    }

    _rechaza(
        db_session,
        _rechazo(entorno, **valores),
        "ck_comando_rechazado__resolucion_coherente",
    )


@pytest.mark.parametrize("faltante", ["resuelto_por_id", "resuelto_en", "comentario"])
def test_un_resuelto_sin_usuario_momento_o_comentario_se_rechaza(
    db_session: Session, faltante: str
) -> None:
    entorno = _armar(db_session)

    _rechaza(
        db_session,
        _resuelto(entorno, **{faltante: None}),
        "ck_comando_rechazado__resolucion_coherente",
    )


@pytest.mark.parametrize("largo", [0, 501])
def test_el_comentario_del_rechazo_va_de_1_a_500_caracteres(
    db_session: Session, largo: int
) -> None:
    entorno = _armar(db_session)

    _rechaza(
        db_session,
        _resuelto(entorno, comentario="x" * largo),
        "ck_comando_rechazado__comentario",
    )
    _insertar_rechazo(db_session, _resuelto(entorno, comentario="x" * 500))


@pytest.mark.parametrize(
    "cambios",
    [
        {"vinculo_tipo": "VENTA"},
        {"vinculo_id": "nuevo"},
        {"vinculo_tipo": "TRANSFERENCIA", "vinculo_id": "nuevo"},
    ],
)
def test_el_vinculo_va_completo_y_es_de_venta_o_cobranza(
    db_session: Session, cambios: dict[str, object]
) -> None:
    entorno = _armar(db_session)
    valores = {c: (uuid4() if v == "nuevo" else v) for c, v in cambios.items()}

    _rechaza(db_session, _resuelto(entorno, **valores), "ck_comando_rechazado__vinculo")


@pytest.mark.parametrize("tipo", ["VENTA", "COBRANZA"])
def test_el_vinculo_de_venta_o_de_cobranza_se_acepta(db_session: Session, tipo: str) -> None:
    _insertar_rechazo(
        db_session,
        _resuelto(_armar(db_session), vinculo_tipo=tipo, vinculo_id=uuid4()),
    )


# --- `observacion` (D2, D10) ----------------------------------------------------------------


def test_syn07_ck_observacion_codigo_admite_producto_desactivado(db_session: Session) -> None:
    _comando_con_observacion(db_session, _armar(db_session), codigo=CODIGO_NUEVO)


@pytest.mark.parametrize("codigo", ["PRODUCTO_DESACTIVADO_", "producto_desactivado", "PRODUCTO"])
def test_syn07_ck_observacion_codigo_sigue_rechazando_lo_que_no_es_del_catalogo(
    db_session: Session, codigo: str
) -> None:
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _comando_con_observacion(db_session, entorno, codigo=codigo)
    assert "ck_observacion__codigo" in str(error.value)


def test_syn07_los_codigos_anteriores_siguen_admitidos(db_session: Session) -> None:
    entorno = _armar(db_session)

    for codigo in ("JORNADA_RENDIDA", "AUTORIZACION_OFFLINE", "STOCK_NEGATIVO"):
        _comando_con_observacion(db_session, entorno, codigo=codigo)


def test_syn08_una_observacion_resuelta_coherente_se_acepta(db_session: Session) -> None:
    entorno = _armar(db_session)

    _comando_con_observacion(
        db_session,
        entorno,
        estado="RESUELTA",
        resuelto_por_id=entorno.usuario_2_id,
        resuelto_en=OTRO_MOMENTO,
        comentario="Se habló con el cliente",
    )


@pytest.mark.parametrize(
    "cambios",
    [
        {"estado": "PENDIENTE", "comentario": "x"},
        {"estado": "PENDIENTE", "resuelto_en": OTRO_MOMENTO},
        {"estado": "PENDIENTE", "resuelto_por_id": "usuario"},
        {"estado": "RESUELTA"},
        {"estado": "RESUELTA", "resuelto_en": OTRO_MOMENTO, "comentario": "x"},
        {"estado": "RESUELTA", "resuelto_por_id": "usuario", "comentario": "x"},
        {"estado": "RESUELTA", "resuelto_por_id": "usuario", "resuelto_en": OTRO_MOMENTO},
    ],
)
def test_syn08_una_resolucion_incoherente_se_rechaza_en_la_base(
    db_session: Session, cambios: dict[str, object]
) -> None:
    entorno = _armar(db_session)
    valores = {c: (entorno.usuario_2_id if v == "usuario" else v) for c, v in cambios.items()}

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _comando_con_observacion(db_session, entorno, **valores)
    assert "ck_observacion__resolucion_coherente" in str(error.value)


@pytest.mark.parametrize("largo", [0, 501])
def test_syn08_el_comentario_de_la_observacion_va_de_1_a_500_caracteres(
    db_session: Session, largo: int
) -> None:
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _comando_con_observacion(
            db_session,
            entorno,
            estado="RESUELTA",
            resuelto_por_id=entorno.usuario_2_id,
            resuelto_en=OTRO_MOMENTO,
            comentario="x" * largo,
        )
    assert "ck_observacion__comentario" in str(error.value)


# --- `comando_cuarentena` (D2, D7) -----------------------------------------------------------


def test_comando_cuarentena_suma_comentario_y_vinculo(_engine_de_sesion: Engine) -> None:
    columnas = _columnas(_engine_de_sesion, "comando_cuarentena")

    for nombre, definicion in COLUMNAS_NUEVAS_CUARENTENA.items():
        assert columnas[nombre] == definicion


def test_syn06_una_cuarentena_pendiente_y_una_revisada_coherentes_se_aceptan(
    db_session: Session,
) -> None:
    entorno = _armar(db_session)

    _insertar_cuarentena(db_session, _cuarentena(entorno))
    _insertar_cuarentena(
        db_session,
        _cuarentena(
            entorno,
            revisado_en=OTRO_MOMENTO,
            revisado_por_id=entorno.usuario_2_id,
            comentario="Se dio de baja el teléfono por robo",
        ),
    )
    _insertar_cuarentena(
        db_session,
        _cuarentena(
            entorno,
            revisado_en=OTRO_MOMENTO,
            revisado_por_id=entorno.usuario_2_id,
            comentario="Cargada con conexión",
            vinculo_tipo="VENTA",
            vinculo_id=uuid4(),
        ),
    )


@pytest.mark.parametrize(
    "cambios",
    [
        {"comentario": "x"},
        {"vinculo_tipo": "VENTA", "vinculo_id": "nuevo"},
        {"revisado_en": OTRO_MOMENTO},
        {"revisado_por_id": "usuario"},
        {"revisado_en": OTRO_MOMENTO, "revisado_por_id": "usuario"},
        {"revisado_en": OTRO_MOMENTO, "comentario": "x"},
    ],
)
def test_syn06_una_revision_incoherente_de_la_cuarentena_se_rechaza(
    db_session: Session, cambios: dict[str, object]
) -> None:
    entorno = _armar(db_session)
    valores = {
        c: (entorno.usuario_2_id if v == "usuario" else uuid4() if v == "nuevo" else v)
        for c, v in cambios.items()
    }

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_cuarentena(db_session, _cuarentena(entorno, **valores))
    assert "ck_comando_cuarentena__revision_coherente" in str(error.value)


@pytest.mark.parametrize("largo", [0, 501])
def test_el_comentario_de_la_cuarentena_va_de_1_a_500_caracteres(
    db_session: Session, largo: int
) -> None:
    entorno = _armar(db_session)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_cuarentena(
            db_session,
            _cuarentena(
                entorno,
                revisado_en=OTRO_MOMENTO,
                revisado_por_id=entorno.usuario_2_id,
                comentario="x" * largo,
            ),
        )
    assert "ck_comando_cuarentena__comentario" in str(error.value)


@pytest.mark.parametrize(
    "cambios",
    [{"vinculo_tipo": "VENTA"}, {"vinculo_id": "nuevo"}, {"vinculo_tipo": "COMPRA"}],
)
def test_el_vinculo_de_la_cuarentena_va_completo_y_es_de_venta_o_cobranza(
    db_session: Session, cambios: dict[str, object]
) -> None:
    entorno = _armar(db_session)
    valores = {c: (uuid4() if v == "nuevo" else v) for c, v in cambios.items()}
    if "vinculo_id" not in valores and valores["vinculo_tipo"] == "COMPRA":
        valores["vinculo_id"] = uuid4()

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_cuarentena(
            db_session,
            _cuarentena(
                entorno,
                revisado_en=OTRO_MOMENTO,
                revisado_por_id=entorno.usuario_2_id,
                comentario="x",
                **valores,
            ),
        )
    assert "ck_comando_cuarentena__vinculo" in str(error.value)


# --- privilegios (INV-05, D2) -----------------------------------------------------------------


def test_inv05_app_runtime_solo_inserta_y_lee_comando_rechazado(app_runtime_engine: Engine) -> None:
    assert _privilegios_de_tabla(app_runtime_engine, "comando_rechazado") == {"SELECT", "INSERT"}
    assert _columnas_con_update(app_runtime_engine, "comando_rechazado") == UPDATE_DE_RECHAZO


def test_inv05_app_runtime_solo_actualiza_la_resolucion_de_la_observacion(
    app_runtime_engine: Engine,
) -> None:
    assert _privilegios_de_tabla(app_runtime_engine, "observacion") == {"SELECT", "INSERT"}
    assert _columnas_con_update(app_runtime_engine, "observacion") == UPDATE_DE_OBSERVACION


def test_inv05_app_runtime_solo_actualiza_la_revision_de_la_cuarentena(
    app_runtime_engine: Engine,
) -> None:
    assert _privilegios_de_tabla(app_runtime_engine, "comando_cuarentena") == {
        "SELECT",
        "INSERT",
    }
    assert _columnas_con_update(app_runtime_engine, "comando_cuarentena") == UPDATE_DE_CUARENTENA


def test_comando_sigue_con_su_update_de_tabla(app_runtime_engine: Engine) -> None:
    """Lo que no cambia: `comando` pasa de estado intermedio a final (INV-06)."""
    assert _privilegios_de_tabla(app_runtime_engine, "comando") == {"SELECT", "INSERT", "UPDATE"}


@pytest.mark.parametrize(
    "sentencia",
    [
        "DELETE FROM comando_rechazado",
        "DELETE FROM observacion",
        "DELETE FROM comando_cuarentena",
        "UPDATE comando_rechazado SET contenido = '{}'",
        "UPDATE comando_rechazado SET error_codigo = 'OTRO'",
        "UPDATE observacion SET codigo = 'STOCK_NEGATIVO'",
        "UPDATE observacion SET detalle = '{}'",
        "UPDATE comando_cuarentena SET contenido = '{}'",
        "UPDATE comando_cuarentena SET motivo = 'OTRO'",
    ],
)
def test_inv05_app_runtime_no_borra_ni_reescribe_lo_registrado(
    app_runtime_engine: Engine, sentencia: str
) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(sentencia))
    assert "permission denied" in str(error.value)


def test_app_runtime_resuelve_una_observacion_y_un_rechazo(
    _engine_de_sesion: Engine, app_runtime_engine: Engine
) -> None:
    """Control positivo: lo que sí puede escribir el runtime (la resolución) funciona."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        observacion_id = _comando_con_observacion(sesion, entorno)
        rechazo = _rechazo(entorno)
        _insertar_rechazo(sesion, rechazo)
        sesion.commit()
    try:
        with app_runtime_engine.begin() as conexion:
            observaciones = conexion.execute(
                text(
                    "UPDATE observacion SET estado = 'RESUELTA', resuelto_por_id = :u, "
                    "resuelto_en = :e, comentario = 'ok' WHERE id = :id"
                ),
                {"u": entorno.usuario_2_id, "e": OTRO_MOMENTO, "id": observacion_id},
            ).rowcount
            rechazos = conexion.execute(
                text(
                    "UPDATE comando_rechazado SET estado = 'RESUELTO', resuelto_por_id = :u, "
                    "resuelto_en = :e, comentario = 'ok', vinculo_tipo = 'VENTA', "
                    "vinculo_id = :v WHERE id = :id"
                ),
                {"u": entorno.usuario_2_id, "e": OTRO_MOMENTO, "v": uuid4(), "id": rechazo["id"]},
            ).rowcount
        assert (observaciones, rechazos) == (1, 1)
    finally:
        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))


# --- ciclo y aborto del downgrade (`04` §2.1 punto 4) -------------------------------------------


def test_el_ciclo_upgrade_downgrade_upgrade_con_datos(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """Sube y baja limpio sobre una base con observaciones y cuarentenas pendientes previas:
    siguen siendo válidas y ninguna fila cambia."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _comando_con_observacion(sesion, entorno, codigo="JORNADA_RENDIDA")
        _comando_con_observacion(sesion, entorno, codigo="STOCK_NEGATIVO")
        _insertar_cuarentena(sesion, _cuarentena(entorno))
        sesion.commit()

    def instantanea() -> list[tuple[object, ...]]:
        with _engine_de_sesion.connect() as conexion:
            observaciones = conexion.execute(
                text("SELECT id, codigo, estado, comentario FROM observacion ORDER BY id")
            ).all()
            cuarentenas = conexion.execute(
                text("SELECT id, motivo, revisado_en FROM comando_cuarentena ORDER BY id")
            ).all()
        return [tuple(f) for f in (*observaciones, *cuarentenas)]

    antes = instantanea()
    assert len(antes) == 3
    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
        assert "comando_rechazado" not in _tablas_existentes(_engine_de_sesion)
        assert not set(COLUMNAS_NUEVAS_CUARENTENA) & set(
            _columnas(_engine_de_sesion, "comando_cuarentena")
        )
        assert instantanea()[:2] == antes[:2]

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert "comando_rechazado" in _tablas_existentes(_engine_de_sesion)
        assert instantanea() == antes
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def _abortado_con(database_url: str, motor: Engine, fragmento: str) -> None:
    abortada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)

    assert abortada.returncode != 0
    assert fragmento in abortada.stderr
    assert _revision_actual(motor) == REVISION
    assert "comando_rechazado" in _tablas_existentes(motor)


def test_el_downgrade_aborta_con_mensaje_claro_si_hay_rechazos(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """El rechazo registrado es el único rastro de lo que envió el teléfono (SYN-06)."""
    with Session(_engine_de_sesion) as sesion:
        _insertar_rechazo(sesion, _rechazo(_armar(sesion)))
        sesion.commit()
    try:
        _abortado_con(database_url, _engine_de_sesion, "rechazo")
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_aborta_si_hay_observaciones_resueltas(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _comando_con_observacion(
            sesion,
            entorno,
            estado="RESUELTA",
            resuelto_por_id=entorno.usuario_2_id,
            resuelto_en=OTRO_MOMENTO,
            comentario="ok",
        )
        sesion.commit()
    try:
        _abortado_con(database_url, _engine_de_sesion, "observación(es) resuelta(s)")
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_aborta_si_hay_cuarentenas_revisadas(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _insertar_cuarentena(
            sesion,
            _cuarentena(
                entorno,
                revisado_en=OTRO_MOMENTO,
                revisado_por_id=entorno.usuario_2_id,
                comentario="ok",
            ),
        )
        sesion.commit()
    try:
        _abortado_con(database_url, _engine_de_sesion, "cuarentena(s) revisada(s)")
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_aborta_si_hay_observaciones_producto_desactivado(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """SYN-07: volver el `CHECK` atrás dejaría inválidas las observaciones nuevas."""
    with Session(_engine_de_sesion) as sesion:
        _comando_con_observacion(sesion, _armar(sesion), codigo=CODIGO_NUEVO)
        sesion.commit()
    try:
        _abortado_con(database_url, _engine_de_sesion, CODIGO_NUEVO)

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("DELETE FROM observacion WHERE codigo = :c"), {"c": CODIGO_NUEVO})
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)
