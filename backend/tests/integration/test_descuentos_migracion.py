"""Tareas 5.1 a 5.3 (change 16): la revisión de Alembic de `regla_descuento` y
`regla_descuento_alcance` (`design.md` D17; `03` §11).

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_jornadas_migracion.py`); que el modelo no se desvíe de la migración lo cubre
`test_modelos_coinciden_con_migracion.py` (tarea 5.4).

Reglas citadas: DSC-01 a DSC-04, INV-02, INV-03, TR-06, `04` §2.1 punto 4, `design.md` D17.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from typing import NamedTuple
from uuid import UUID, uuid4

import pytest
from conftest import (
    _PASSWORD_ROL_MIGRACIONES,
    BACKEND_DIR,
    NOMBRE_ROL_MIGRACIONES,
    _url_con_credenciales,
)
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql

REVISION_ANTERIOR = "a4b5c6d7e8f9"  # `jornadas`, la previa a este change.
MOMENTO = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
OTRO_MOMENTO = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)

COLUMNAS_REGLA = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "nombre": ("text", False),
    "tipo": ("text", False),
    "medida": ("text", False),
    "operador": ("text", False),
    "umbral": ("numeric", False),
    "accion_tipo": ("text", False),
    "accion_porcentaje": ("numeric", True),
    "accion_importe": ("numeric", True),
    "prioridad": ("integer", False),
    "acumulable": ("boolean", False),
    "vigencia_desde": ("timestamp with time zone", True),
    "vigencia_hasta": ("timestamp with time zone", True),
    "estado": ("text", False),
    "creado_en": ("timestamp with time zone", False),
    "actualizado_en": ("timestamp with time zone", False),
    "actualizado_por_id": ("uuid", True),
}
COLUMNAS_ALCANCE = {
    "id": ("uuid", False),
    "organizacion_id": ("uuid", False),
    "regla_id": ("uuid", False),
    "alcance_tipo": ("text", False),
    "alcance_id": ("uuid", False),
    "producto_id": ("uuid", True),
    "categoria_id": ("uuid", True),
    "marca_id": ("uuid", True),
    "creado_en": ("timestamp with time zone", False),
}
FKS_ALCANCE = {
    "fk_regla_descuento_alcance__organizacion",
    "fk_regla_descuento_alcance__regla",
    "fk_regla_descuento_alcance__producto",
    "fk_regla_descuento_alcance__categoria",
    "fk_regla_descuento_alcance__marca",
}


class Entorno(NamedTuple):
    organizacion_id: UUID
    producto_id: UUID
    categoria_id: UUID
    marca_id: UUID


# --- consultas al esquema real -------------------------------------------------


def _columnas(motor: Engine, tabla: str) -> dict[str, tuple[str, bool]]:
    with motor.connect() as conexion:
        filas = conexion.execute(
            text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :tabla"
            ),
            {"tabla": tabla},
        )
        return {nombre: (tipo, nullable == "YES") for nombre, tipo, nullable in filas}


def _precision(motor: Engine, tabla: str, columna: str) -> tuple[int, int]:
    with motor.connect() as conexion:
        fila = conexion.execute(
            text(
                "SELECT numeric_precision, numeric_scale FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": tabla, "c": columna},
        ).one()
        return (fila[0], fila[1])


def _restricciones(motor: Engine, tabla: str, tipo: str) -> dict[str, str]:
    with motor.connect() as conexion:
        return dict(
            conexion.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = CAST(:tabla AS regclass) AND contype = :tipo"
                ),
                {"tabla": f"public.{tabla}", "tipo": tipo},
            ).all()
        )


def _indice(motor: Engine, nombre: str) -> str:
    with motor.connect() as conexion:
        return conexion.execute(
            text("SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"),
            {"n": nombre},
        ).scalar_one()


def _privilegios_de_tabla(motor: Engine, tabla: str) -> set[str]:
    with motor.connect() as conexion:
        return set(
            conexion.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_schema = 'public' AND table_name = :t AND grantee = 'app_runtime'"
                ),
                {"t": tabla},
            )
            .scalars()
            .all()
        )


def _tablas_existentes(motor: Engine) -> set[str]:
    with motor.connect() as conexion:
        return set(
            conexion.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )


# --- estructura (tarea 5.1) -----------------------------------------------------


def test_las_columnas_de_regla_descuento_son_las_del_design(_engine_de_sesion: Engine) -> None:
    """D17: dos columnas de acción en lugar de `accion_valor`, con el tipo de `CLAUDE.md` §4."""
    assert _columnas(_engine_de_sesion, "regla_descuento") == COLUMNAS_REGLA
    assert _precision(_engine_de_sesion, "regla_descuento", "accion_porcentaje") == (9, 6)
    assert _precision(_engine_de_sesion, "regla_descuento", "accion_importe") == (14, 2)
    assert _precision(_engine_de_sesion, "regla_descuento", "umbral") == (14, 4)


def test_las_columnas_de_regla_descuento_alcance_son_las_del_design(
    _engine_de_sesion: Engine,
) -> None:
    assert _columnas(_engine_de_sesion, "regla_descuento_alcance") == COLUMNAS_ALCANCE


@pytest.mark.parametrize("tabla", ["regla_descuento", "regla_descuento_alcance"])
def test_las_dos_tablas_tienen_unique_organizacion_id(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    unicas = _restricciones(_engine_de_sesion, tabla, "u")
    assert unicas[f"ux_{tabla}__org_id"] == "UNIQUE (organizacion_id, id)"


def test_inv02_las_claves_foraneas_del_alcance_son_compuestas(_engine_de_sesion: Engine) -> None:
    foraneas = _restricciones(_engine_de_sesion, "regla_descuento_alcance", "f")
    assert set(foraneas) == FKS_ALCANCE
    for nombre, definicion in foraneas.items():
        if nombre.endswith("__organizacion"):
            continue
        assert "FOREIGN KEY (organizacion_id," in definicion, nombre


def test_el_indice_de_listado_existe(_engine_de_sesion: Engine) -> None:
    definicion = _indice(_engine_de_sesion, "ix_regla_descuento__listado")
    assert "(organizacion_id, estado, id DESC)" in definicion


def test_el_alcance_es_unico_por_regla_tipo_y_entidad(_engine_de_sesion: Engine) -> None:
    unicas = _restricciones(_engine_de_sesion, "regla_descuento_alcance", "u")
    assert (
        unicas["ux_regla_descuento_alcance__regla_entidad"]
        == "UNIQUE (organizacion_id, regla_id, alcance_tipo, alcance_id)"
    )


@pytest.mark.parametrize(
    ("columna", "valor"),
    [
        ("tipo", "VOLUMEN_CLIENTE"),
        ("medida", "HISTORIAL_DE_COMPRAS"),
        ("operador", "LT"),
        ("accion_tipo", "BONIFICACION_EN_UNIDADES"),
        ("estado", "VENCIDA"),  # derivado: nunca se almacena (D16)
        ("estado", "borrador"),
    ],
)
def test_los_catalogos_cerrados_rechazan_un_valor_inventado(
    db_session: Session, columna: str, valor: str
) -> None:
    """DSC-02 a DSC-04 y D1: un valor fuera de las listas cerradas se rechaza en la base."""
    entorno = _armar(db_session)
    # Una acción inventada también rompe `ck_regla_descuento__accion` (la exacta): PostgreSQL
    # informa la primera por nombre, así que alcanza con el prefijo.
    restriccion = "accion" if columna == "accion_tipo" else columna
    _rechaza(db_session, {**_regla(entorno), columna: valor}, f'"ck_regla_descuento__{restriccion}')


@pytest.mark.parametrize(
    ("columna", "valor"),
    [
        ("tipo", "VOLUMEN_ALCANCE"),
        ("medida", "UNIDADES_BASE"),
        ("medida", "IMPORTE_BRUTO"),
        ("operador", "GT"),
        ("estado", "PAUSADA"),
    ],
)
def test_los_catalogos_cerrados_aceptan_cada_valor_de_las_specs(
    db_session: Session, columna: str, valor: str
) -> None:
    entorno = _armar(db_session)
    _insertar(db_session, "regla_descuento", {**_regla(entorno), columna: valor})


def test_inv03_la_accion_exige_exactamente_la_columna_que_corresponde(
    db_session: Session,
) -> None:
    """INV-03, D17: una regla de porcentaje sin porcentaje, con importe, o con ambos se
    rechaza; lo mismo la de importe fijo."""
    entorno = _armar(db_session)
    _insertar(db_session, "regla_descuento", _regla(entorno))
    _insertar(
        db_session,
        "regla_descuento",
        _regla(
            entorno,
            accion_tipo="IMPORTE_FIJO",
            accion_porcentaje=None,
            accion_importe=Decimal("1000.00"),
        ),
    )
    for cambios in (
        {"accion_porcentaje": None},
        {"accion_importe": Decimal("10.00")},
        {"accion_tipo": "IMPORTE_FIJO"},
        {"accion_tipo": "IMPORTE_FIJO", "accion_porcentaje": None},
        {"accion_tipo": "IMPORTE_FIJO", "accion_porcentaje": None, "accion_importe": Decimal("0")},
    ):
        with pytest.raises(IntegrityError) as error, db_session.begin_nested():
            _insertar(db_session, "regla_descuento", _regla(entorno, **cambios))
        assert "ck_regla_descuento__accion" in str(error.value), cambios


@pytest.mark.parametrize("porcentaje", ["0", "1.000001", "-0.05"])
def test_el_porcentaje_de_la_accion_es_mayor_que_0_y_hasta_1(
    db_session: Session, porcentaje: str
) -> None:
    entorno = _armar(db_session)
    _rechaza(
        db_session,
        _regla(entorno, accion_porcentaje=Decimal(porcentaje)),
        '"ck_regla_descuento__accion',
    )


@pytest.mark.parametrize("porcentaje", ["0.000001", "1", "0.125000"])
def test_el_porcentaje_de_la_accion_acepta_los_extremos(
    db_session: Session, porcentaje: str
) -> None:
    entorno = _armar(db_session)
    _insertar(db_session, "regla_descuento", _regla(entorno, accion_porcentaje=Decimal(porcentaje)))


@pytest.mark.parametrize("umbral", ["0", "-1"])
def test_el_umbral_es_mayor_que_0(db_session: Session, umbral: str) -> None:
    entorno = _armar(db_session)
    _rechaza(db_session, _regla(entorno, umbral=Decimal(umbral)), '"ck_regla_descuento__umbral"')


@pytest.mark.parametrize("prioridad", [0, -3])
def test_la_prioridad_es_mayor_o_igual_que_1(db_session: Session, prioridad: int) -> None:
    entorno = _armar(db_session)
    _rechaza(db_session, _regla(entorno, prioridad=prioridad), '"ck_regla_descuento__prioridad"')


@pytest.mark.parametrize("hasta", [MOMENTO, datetime(2026, 10, 1, tzinfo=UTC)])
def test_la_vigencia_hasta_es_posterior_a_la_desde(db_session: Session, hasta: datetime) -> None:
    entorno = _armar(db_session)
    _rechaza(
        db_session,
        _regla(entorno, vigencia_desde=MOMENTO, vigencia_hasta=hasta),
        '"ck_regla_descuento__vigencia"',
    )


def test_una_vigencia_valida_se_acepta(db_session: Session) -> None:
    entorno = _armar(db_session)
    _insertar(
        db_session,
        "regla_descuento",
        _regla(entorno, vigencia_desde=MOMENTO, vigencia_hasta=OTRO_MOMENTO),
    )


@pytest.mark.parametrize("estado", ["ACTIVA", "PAUSADA"])
def test_una_regla_no_borrador_sin_vigencia_desde_se_rechaza(
    db_session: Session, estado: str
) -> None:
    """D16: la vigencia desde es obligatoria desde la activación."""
    entorno = _armar(db_session)
    _rechaza(
        db_session,
        _regla(entorno, estado=estado, vigencia_desde=None),
        '"ck_regla_descuento__vigencia_desde"',
    )


def test_un_borrador_sin_vigencia_desde_se_acepta(db_session: Session) -> None:
    entorno = _armar(db_session)
    _insertar(db_session, "regla_descuento", _regla(entorno, estado="BORRADOR"))


@pytest.mark.parametrize(
    ("alcance_tipo", "columna_generada"),
    [("PRODUCTO", "producto_id"), ("CATEGORIA", "categoria_id"), ("MARCA", "marca_id")],
)
def test_el_alcance_deriva_la_columna_de_su_tipo(
    db_session: Session, alcance_tipo: str, columna_generada: str
) -> None:
    """ADR-035: las columnas generadas solo se llenan para el tipo que corresponde."""
    entorno = _armar(db_session)
    regla = _regla(entorno, tipo="VOLUMEN_ALCANCE")
    _insertar(db_session, "regla_descuento", regla)
    entidad = {
        "PRODUCTO": entorno.producto_id,
        "CATEGORIA": entorno.categoria_id,
        "MARCA": entorno.marca_id,
    }[alcance_tipo]
    _insertar(
        db_session, "regla_descuento_alcance", _alcance(entorno, regla, alcance_tipo, entidad)
    )
    fila = db_session.execute(
        text(
            "SELECT producto_id, categoria_id, marca_id FROM regla_descuento_alcance "
            "WHERE regla_id = :r"
        ),
        {"r": regla["id"]},
    ).one()
    columnas = ("producto_id", "categoria_id", "marca_id")
    llenas = {nombre for nombre, valor in zip(columnas, fila, strict=True) if valor}
    assert llenas == {columna_generada}


def test_inv02_un_alcance_hacia_una_entidad_de_otra_organizacion_se_rechaza(
    db_session: Session,
) -> None:
    """INV-02: producto, categoría y marca ajenos violan la clave foránea compuesta."""
    entorno = _armar(db_session)
    ajeno = _armar(db_session)
    regla = _regla(entorno, tipo="VOLUMEN_ALCANCE")
    _insertar(db_session, "regla_descuento", regla)
    for tipo, entidad, fk in (
        ("PRODUCTO", ajeno.producto_id, "fk_regla_descuento_alcance__producto"),
        ("CATEGORIA", ajeno.categoria_id, "fk_regla_descuento_alcance__categoria"),
        ("MARCA", ajeno.marca_id, "fk_regla_descuento_alcance__marca"),
    ):
        with pytest.raises(IntegrityError) as error, db_session.begin_nested():
            _insertar(
                db_session, "regla_descuento_alcance", _alcance(entorno, regla, tipo, entidad)
            )
        assert fk in str(error.value), tipo


def test_inv02_un_alcance_de_una_regla_de_otra_organizacion_se_rechaza(
    db_session: Session,
) -> None:
    entorno = _armar(db_session)
    ajeno = _armar(db_session)
    regla_ajena = _regla(ajeno, tipo="VOLUMEN_ALCANCE")
    _insertar(db_session, "regla_descuento", regla_ajena)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(
            db_session,
            "regla_descuento_alcance",
            {
                **_alcance(entorno, regla_ajena, "PRODUCTO", entorno.producto_id),
                "organizacion_id": entorno.organizacion_id,
            },
        )
    assert "fk_regla_descuento_alcance__regla" in str(error.value)


def test_un_alcance_repetido_en_una_regla_se_rechaza(db_session: Session) -> None:
    entorno = _armar(db_session)
    regla = _regla(entorno, tipo="VOLUMEN_ALCANCE")
    _insertar(db_session, "regla_descuento", regla)
    _insertar(
        db_session,
        "regla_descuento_alcance",
        _alcance(entorno, regla, "MARCA", entorno.marca_id),
    )
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(
            db_session,
            "regla_descuento_alcance",
            _alcance(entorno, regla, "MARCA", entorno.marca_id),
        )
    assert "ux_regla_descuento_alcance__regla_entidad" in str(error.value)


def test_el_mismo_alcance_en_otra_regla_se_acepta(db_session: Session) -> None:
    entorno = _armar(db_session)
    primera = _regla(entorno, tipo="VOLUMEN_ALCANCE")
    segunda = _regla(entorno, tipo="VOLUMEN_ALCANCE")
    for regla in (primera, segunda):
        _insertar(db_session, "regla_descuento", regla)
        _insertar(
            db_session,
            "regla_descuento_alcance",
            _alcance(entorno, regla, "MARCA", entorno.marca_id),
        )


def test_el_alcance_tipo_es_un_catalogo_cerrado(db_session: Session) -> None:
    entorno = _armar(db_session)
    regla = _regla(entorno, tipo="VOLUMEN_ALCANCE")
    _insertar(db_session, "regla_descuento", regla)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar(
            db_session,
            "regla_descuento_alcance",
            _alcance(entorno, regla, "PROVEEDOR", entorno.marca_id),
        )
    assert "ck_regla_descuento_alcance__alcance_tipo" in str(error.value)


# --- privilegios (tarea 5.2) ------------------------------------------------------


def test_tr06_app_runtime_no_borra_reglas_y_si_las_lee_inserta_y_actualiza(
    app_runtime_engine: Engine,
) -> None:
    assert _privilegios_de_tabla(app_runtime_engine, "regla_descuento") == {
        "SELECT",
        "INSERT",
        "UPDATE",
    }
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text("DELETE FROM regla_descuento"))
    assert "permission denied" in str(error.value)


def test_tr06_app_runtime_borra_alcances_pero_no_los_actualiza(
    app_runtime_engine: Engine,
) -> None:
    """Solo se borran al reemplazar los alcances de un borrador; sin `UPDATE` (D17)."""
    assert _privilegios_de_tabla(app_runtime_engine, "regla_descuento_alcance") == {
        "SELECT",
        "INSERT",
        "DELETE",
    }
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text("UPDATE regla_descuento_alcance SET creado_en = now()"))
    assert "permission denied" in str(error.value)


# --- ciclo (tarea 5.3) ------------------------------------------------------------


def test_el_ciclo_upgrade_downgrade_upgrade_con_datos(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`04` §2.1 punto 4: sube y baja limpio con catálogo, una lista de precios y reglas en
    los tres estados con alcances; no modifica ninguna fila de otras tablas. El `downgrade`
    pierde, por diseño, las reglas y sus alcances (ninguna venta las referencia todavía)."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        lista_id = uuid4()
        _insertar(
            sesion,
            "lista_precio",
            {
                "id": lista_id,
                "organizacion_id": entorno.organizacion_id,
                "nombre": "General",
                "redondeo_multiplo": Decimal("1.00"),
                "redondeo_direccion": "ARRIBA",
                "activo": True,
                "creado_en": MOMENTO,
                "actualizado_en": MOMENTO,
            },
        )
        for estado in ("BORRADOR", "ACTIVA", "PAUSADA"):
            regla = _regla(entorno, tipo="VOLUMEN_ALCANCE", estado=estado)
            _insertar(sesion, "regla_descuento", regla)
            _insertar(
                sesion,
                "regla_descuento_alcance",
                _alcance(entorno, regla, "MARCA", entorno.marca_id),
            )
        sesion.commit()

    def instantanea() -> dict[str, list[tuple[object, ...]]]:
        with _engine_de_sesion.connect() as conexion:
            return {
                tabla: [
                    tuple(f) for f in conexion.execute(text(f"SELECT * FROM {tabla} ORDER BY 1"))
                ]
                for tabla in ("organizacion", "producto", "categoria", "marca", "lista_precio")
            }

    antes = instantanea()
    assert antes["lista_precio"] and antes["marca"]

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        # Lo que el `downgrade` pierde, escrito explícito.
        tablas = _tablas_existentes(_engine_de_sesion)
        assert "regla_descuento" not in tablas
        assert "regla_descuento_alcance" not in tablas
        # Lo que NO toca.
        assert instantanea() == antes

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        tablas = _tablas_existentes(_engine_de_sesion)
        assert {"regla_descuento", "regla_descuento_alcance"} <= tablas
        with _engine_de_sesion.connect() as conexion:
            for tabla in ("regla_descuento", "regla_descuento_alcance"):
                assert conexion.execute(text(f"SELECT count(*) FROM {tabla}")).scalar_one() == 0
        assert instantanea() == antes
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


# --- armado de datos -----------------------------------------------------------


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    url_migraciones = _url_con_credenciales(
        database_url, NOMBRE_ROL_MIGRACIONES, _PASSWORD_ROL_MIGRACIONES
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL_MIGRATIONS": url_migraciones},
        capture_output=True,
        text=True,
    )


def _dejar_en_head(database_url: str, motor: Engine) -> None:
    """La base es compartida con el resto de la sesión: toda prueba que mueve Alembic
    DEBE terminar en `head` y sin filas propias."""
    subida = _alembic(database_url, "upgrade", "head")
    assert subida.returncode == 0, subida.stderr
    with motor.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))


def _insertar(sesion: Session, tabla: str, valores: dict[str, object]) -> None:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    sesion.execute(text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores})"), valores)


def _armar(sesion: Session) -> Entorno:
    """Una organización con un producto (y su categoría) y una marca."""
    organizacion = crear_organizacion(sesion)
    producto_id = crear_producto_sql(sesion, organizacion.id)
    categoria_id = sesion.execute(
        text("SELECT categoria_id FROM producto WHERE id = :p"), {"p": producto_id}
    ).scalar_one()
    marca_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO marca (id, organizacion_id, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :org, 'Bodega Norte', true, :m, :m)"
        ),
        {"id": marca_id, "org": organizacion.id, "m": MOMENTO},
    )
    return Entorno(organizacion.id, producto_id, categoria_id, marca_id)


def _regla(entorno: Entorno, **cambios: object) -> dict[str, object]:
    """Una regla coherente: "cajas equivalentes >= 20 -> 5%", activa y vigente."""
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "nombre": "Volumen 20 cajas",
        "tipo": "VOLUMEN_OPERACION",
        "medida": "CAJAS_EQUIVALENTES",
        "operador": "GTE",
        "umbral": Decimal("20"),
        "accion_tipo": "PORCENTAJE",
        "accion_porcentaje": Decimal("0.050000"),
        "accion_importe": None,
        "prioridad": 1,
        "acumulable": False,
        "vigencia_desde": MOMENTO,
        "vigencia_hasta": None,
        "estado": "ACTIVA",
        "creado_en": MOMENTO,
        "actualizado_en": MOMENTO,
    }
    valores.update(cambios)
    return valores


def _alcance(
    entorno: Entorno, regla: dict[str, object], tipo: str, entidad_id: UUID
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "regla_id": regla["id"],
        "alcance_tipo": tipo,
        "alcance_id": entidad_id,
        "creado_en": MOMENTO,
    }


def _rechaza(sesion: Session, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        _insertar(sesion, "regla_descuento", valores)
    assert restriccion in str(error.value)
