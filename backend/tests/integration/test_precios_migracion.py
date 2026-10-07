"""Tareas 1.1 a 1.4 (change 13): la revisión `e2f3a4b5c6d7` crea las cinco tablas de
precios de `docs/03-modelo-de-datos.md` §8 con los agregados de `design.md` D13, las
claves foráneas compuestas de `cliente.lista_precio_id` y de
`configuracion_organizacion.lista_precio_default_id`, y los privilegios de `app_runtime`.

Consulta el esquema REAL de PostgreSQL ya migrado (mismo criterio que
`test_pagos_proveedor_migracion.py`); que el modelo no se desvíe de la migración lo cubre
`test_modelos_coinciden_con_migracion.py` y el catálogo de tipos de INV-03 está en
`test_inv03_sin_punto_flotante.py` (tarea 1.5).

Reglas citadas: INV-02, INV-03, INV-05, PRC-01, PRC-02, PRC-10, PRC-12, PRC-14, PRC-16,
`design.md` D1, D5, D6, D7, D8, D9, D13.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
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
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from stock_utiles import crear_presentacion_referencia_sql, crear_producto_sql

REVISION = "e2f3a4b5c6d7"
REVISION_ANTERIOR = "d1e2f3a4b5c6"  # `pagos_a_proveedores`, la previa a este change.
MOMENTO = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

TABLAS = ("lista_precio", "regla_margen", "redondeo_categoria", "lista_version", "precio_item")

# --- catálogo de columnas y claves foráneas compuestas (INV-02, D13) ---------------

COLUMNAS: dict[str, dict[str, tuple[str, bool]]] = {
    "lista_precio": {
        "id": ("uuid", False),
        "organizacion_id": ("uuid", False),
        "nombre": ("text", False),
        "redondeo_multiplo": ("numeric", False),
        "redondeo_direccion": ("text", False),
        "activo": ("boolean", False),
        "creado_en": ("timestamp with time zone", False),
        "actualizado_en": ("timestamp with time zone", False),
        "actualizado_por_id": ("uuid", True),
    },
    "regla_margen": {
        "id": ("uuid", False),
        "organizacion_id": ("uuid", False),
        "lista_id": ("uuid", False),
        "alcance_tipo": ("text", False),
        "alcance_id": ("uuid", True),
        "producto_id": ("uuid", True),
        "marca_id": ("uuid", True),
        "categoria_id": ("uuid", True),
        "proveedor_id": ("uuid", True),
        "tipo": ("text", False),
        "valor": ("numeric", False),
        "activo": ("boolean", False),
        "creado_en": ("timestamp with time zone", False),
        "actualizado_en": ("timestamp with time zone", False),
        "actualizado_por_id": ("uuid", True),
    },
    "redondeo_categoria": {
        "id": ("uuid", False),
        "organizacion_id": ("uuid", False),
        "lista_id": ("uuid", False),
        "categoria_id": ("uuid", False),
        "multiplo": ("numeric", False),
        "direccion": ("text", False),
        "activo": ("boolean", False),
        "creado_en": ("timestamp with time zone", False),
        "actualizado_en": ("timestamp with time zone", False),
        "actualizado_por_id": ("uuid", True),
    },
    "lista_version": {
        "id": ("uuid", False),
        "organizacion_id": ("uuid", False),
        "lista_id": ("uuid", False),
        "numero": ("integer", False),
        "estado": ("text", False),
        "vigencia_desde": ("timestamp with time zone", True),
        "vigencia_hasta": ("timestamp with time zone", True),
        "version_base_id": ("uuid", True),
        "generado_en": ("timestamp with time zone", True),
        "creado_por_id": ("uuid", False),
        "creado_en": ("timestamp with time zone", False),
        "publicado_por_id": ("uuid", True),
        "publicado_en": ("timestamp with time zone", True),
        "anulado_por_id": ("uuid", True),
        "anulado_en": ("timestamp with time zone", True),
        "operation_id": ("uuid", False),
    },
    "precio_item": {
        "id": ("uuid", False),
        "organizacion_id": ("uuid", False),
        "version_id": ("uuid", False),
        "producto_id": ("uuid", False),
        "unidades_referencia": ("integer", False),
        "costo_informado_id": ("uuid", True),
        "costo_referencia": ("numeric", True),
        "regla_margen_id": ("uuid", True),
        "tipo_margen": ("text", True),
        "valor_margen": ("numeric", True),
        "precio_calculado": ("numeric", True),
        "precio_final": ("numeric", False),
        "manual": ("boolean", False),
    },
}

PRECISIONES = {
    ("lista_precio", "redondeo_multiplo"): (14, 2),
    ("regla_margen", "valor"): (9, 6),
    ("redondeo_categoria", "multiplo"): (14, 2),
    ("precio_item", "costo_referencia"): (18, 6),
    ("precio_item", "valor_margen"): (9, 6),
    ("precio_item", "precio_calculado"): (18, 6),
    ("precio_item", "precio_final"): (14, 2),
}

# Cada FK saliente hacia una entidad de negocio es compuesta e incluye `organizacion_id`
# (INV-02): nombre -> (columna de la entidad referenciada, tabla destino).
FKS_COMPUESTAS = {
    "lista_precio": {
        "fk_lista_precio__actualizado_por": ("actualizado_por_id", "usuario"),
    },
    "regla_margen": {
        "fk_regla_margen__lista": ("lista_id", "lista_precio"),
        "fk_regla_margen__producto": ("producto_id", "producto"),
        "fk_regla_margen__marca": ("marca_id", "marca"),
        "fk_regla_margen__categoria": ("categoria_id", "categoria"),
        "fk_regla_margen__proveedor": ("proveedor_id", "proveedor"),
        "fk_regla_margen__actualizado_por": ("actualizado_por_id", "usuario"),
    },
    "redondeo_categoria": {
        "fk_redondeo_categoria__lista": ("lista_id", "lista_precio"),
        "fk_redondeo_categoria__categoria": ("categoria_id", "categoria"),
        "fk_redondeo_categoria__actualizado_por": ("actualizado_por_id", "usuario"),
    },
    "lista_version": {
        "fk_lista_version__lista": ("lista_id", "lista_precio"),
        "fk_lista_version__version_base": ("version_base_id", "lista_version"),
        "fk_lista_version__creado_por": ("creado_por_id", "usuario"),
        "fk_lista_version__publicado_por": ("publicado_por_id", "usuario"),
        "fk_lista_version__anulado_por": ("anulado_por_id", "usuario"),
    },
    "precio_item": {
        "fk_precio_item__version": ("version_id", "lista_version"),
        "fk_precio_item__producto": ("producto_id", "producto"),
        "fk_precio_item__costo_informado": ("costo_informado_id", "costo_informado"),
        "fk_precio_item__regla_margen": ("regla_margen_id", "regla_margen"),
    },
}

CHECKS = {
    "lista_precio": {
        "ck_lista_precio__redondeo_multiplo",
        "ck_lista_precio__redondeo_direccion",
    },
    "regla_margen": {
        "ck_regla_margen__valor",
        "ck_regla_margen__alcance_tipo",
        "ck_regla_margen__tipo",
        "ck_regla_margen__alcance",
    },
    "redondeo_categoria": {
        "ck_redondeo_categoria__multiplo",
        "ck_redondeo_categoria__direccion",
    },
    "lista_version": {
        "ck_lista_version__estado",
        "ck_lista_version__numero",
        "ck_lista_version__publicacion_coherente",
        "ck_lista_version__anulacion_coherente",
        "ck_lista_version__vigencia",
    },
    "precio_item": {
        "ck_precio_item__unidades_referencia",
        "ck_precio_item__precio_final",
        "ck_precio_item__tipo_margen",
        "ck_precio_item__calculo_coherente",
    },
}

INDICES = {
    "ux_lista_precio__nombre",
    "ux_regla_margen__alcance_activa",
    "ux_regla_margen__lista_activa",
    "ux_redondeo_categoria__lista_categoria",
    "ux_lista_version__numero",
    "ux_lista_version__borrador",
    "ux_lista_version__vigencia_desde",
    "ix_lista_version__resolucion",
    "ux_precio_item__version_producto",
}


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


def _existe_tabla(motor: Engine, tabla: str) -> bool:
    with motor.connect() as conexion:
        return bool(
            conexion.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :t"
                ),
                {"t": tabla},
            ).scalar_one()
        )


def _revision_actual(motor: Engine) -> str:
    with motor.connect() as conexion:
        return conexion.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _cantidad_de_filas(motor: Engine, tabla: str) -> int:
    with motor.connect() as conexion:
        return conexion.execute(text(f"SELECT count(*) FROM {tabla}")).scalar_one()


# --- tablas, columnas y tipos (D13) ---------------------------------------------


@pytest.mark.parametrize("tabla", TABLAS)
def test_las_tablas_de_precios_tienen_las_columnas_y_los_tipos_de_d13(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    assert _columnas(_engine_de_sesion, tabla) == COLUMNAS[tabla]


@pytest.mark.parametrize(("clave", "precision"), list(PRECISIONES.items()))
def test_los_importes_costos_y_porcentajes_tienen_la_precision_de_claude_md(
    _engine_de_sesion: Engine, clave: tuple[str, str], precision: tuple[int, int]
) -> None:
    """INV-03: `NUMERIC(14,2)` importes, `(18,6)` costos y `(9,6)` porcentajes."""
    with _engine_de_sesion.connect() as conexion:
        fila = conexion.execute(
            text(
                "SELECT numeric_precision, numeric_scale FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
            ),
            {"t": clave[0], "c": clave[1]},
        ).one()
    assert (fila[0], fila[1]) == precision


@pytest.mark.parametrize("tabla", TABLAS)
def test_inv02_cada_tabla_tiene_unique_organizacion_id_y_sus_fks_son_compuestas(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    """INV-02: `UNIQUE (organizacion_id, id)` y toda clave foránea hacia una entidad de
    negocio lleva `organizacion_id` primero."""
    unicos = _restricciones(_engine_de_sesion, tabla, "u")
    assert unicos[f"ux_{tabla}__org_id"] == "UNIQUE (organizacion_id, id)"

    fks = _restricciones(_engine_de_sesion, tabla, "f")
    assert fks[f"fk_{tabla}__organizacion"].startswith("FOREIGN KEY (organizacion_id) REFERENCES")
    for nombre, (columna, destino) in FKS_COMPUESTAS[tabla].items():
        assert fks[nombre].startswith(
            f"FOREIGN KEY (organizacion_id, {columna}) REFERENCES {destino}(organizacion_id, id)"
        ), nombre
    assert set(fks) == {f"fk_{tabla}__organizacion", *FKS_COMPUESTAS[tabla]}


@pytest.mark.parametrize("tabla", TABLAS)
def test_las_restricciones_check_de_d13_existen(_engine_de_sesion: Engine, tabla: str) -> None:
    assert set(_restricciones(_engine_de_sesion, tabla, "c")) == CHECKS[tabla]


def test_los_indices_de_d13_existen(_engine_de_sesion: Engine) -> None:
    for nombre in INDICES:
        assert _indice(_engine_de_sesion, nombre)
    assert "lower(nombre)" in _indice(_engine_de_sesion, "ux_lista_precio__nombre")
    assert "WHERE (estado = 'BORRADOR'::text)" in _indice(
        _engine_de_sesion, "ux_lista_version__borrador"
    )
    assert "WHERE (estado = 'PUBLICADA'::text)" in _indice(
        _engine_de_sesion, "ux_lista_version__vigencia_desde"
    )
    assert "vigencia_desde DESC" in _indice(_engine_de_sesion, "ix_lista_version__resolucion")


# --- armado de datos -----------------------------------------------------------


class Entorno(NamedTuple):
    organizacion_id: UUID
    usuario_id: UUID
    producto_id: UUID
    presentacion_id: UUID
    categoria_id: UUID
    marca_id: UUID
    proveedor_id: UUID
    costo_id: UUID


def _insertar(sesion: Session, tabla: str, valores: dict[str, object]) -> None:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    sesion.execute(text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores})"), valores)


def _armar(sesion: Session) -> Entorno:
    """Organización con usuario, un producto con su presentación de referencia, categoría,
    marca, proveedor y un costo informado."""
    organizacion = crear_organizacion(sesion)
    usuario_id, _ = crear_usuario_y_dispositivo(sesion, organizacion.id)
    producto_id = crear_producto_sql(sesion, organizacion.id, nombre="Vino A")
    presentacion_id = crear_presentacion_referencia_sql(sesion, organizacion.id, producto_id)
    marca_id, costo_id = uuid4(), uuid4()
    _insertar(
        sesion,
        "marca",
        {
            "id": marca_id,
            "organizacion_id": organizacion.id,
            "nombre": f"Marca-{uuid4().hex[:6]}",
            "activo": True,
            "creado_en": MOMENTO,
            "actualizado_en": MOMENTO,
        },
    )
    fila = sesion.execute(
        text("SELECT categoria_id, proveedor_id FROM producto WHERE id = :p"), {"p": producto_id}
    ).one()
    _insertar(
        sesion,
        "costo_informado",
        {
            "id": costo_id,
            "organizacion_id": organizacion.id,
            "proveedor_id": fila.proveedor_id,
            "producto_id": producto_id,
            "presentacion_id": presentacion_id,
            "valor": 36000,
            "incluye_iva": False,
            "computa_credito_fiscal": True,
            "bonificacion": 0,
            "alicuota_aplicada": Decimal("0.21"),
            "costo_base": 6000,
            "vigencia_desde": MOMENTO.date(),
            "operation_id": uuid4(),
            "usuario_id": usuario_id,
            "creado_en": MOMENTO,
        },
    )
    return Entorno(
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        producto_id=producto_id,
        presentacion_id=presentacion_id,
        categoria_id=fila.categoria_id,
        marca_id=marca_id,
        proveedor_id=fila.proveedor_id,
        costo_id=costo_id,
    )


def _lista(entorno: Entorno, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "nombre": f"Lista-{uuid4().hex[:8]}",
        "redondeo_multiplo": Decimal("100.00"),
        "redondeo_direccion": "ARRIBA",
        "activo": True,
        "creado_en": MOMENTO,
        "actualizado_en": MOMENTO,
        "actualizado_por_id": None,
    }
    valores.update(cambios)
    return valores


def _regla(entorno: Entorno, lista_id: object, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "lista_id": lista_id,
        "alcance_tipo": "LISTA",
        "alcance_id": None,
        "tipo": "MARGEN_BRUTO",
        "valor": Decimal("0.300000"),
        "activo": True,
        "creado_en": MOMENTO,
        "actualizado_en": MOMENTO,
    }
    valores.update(cambios)
    return valores


def _redondeo(entorno: Entorno, lista_id: object, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "lista_id": lista_id,
        "categoria_id": entorno.categoria_id,
        "multiplo": Decimal("500.00"),
        "direccion": "ARRIBA",
        "activo": True,
        "creado_en": MOMENTO,
        "actualizado_en": MOMENTO,
    }
    valores.update(cambios)
    return valores


def _borrador(entorno: Entorno, lista_id: object, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "lista_id": lista_id,
        "numero": 1,
        "estado": "BORRADOR",
        "creado_por_id": entorno.usuario_id,
        "creado_en": MOMENTO,
        "operation_id": uuid4(),
    }
    valores.update(cambios)
    return valores


def _publicada(
    entorno: Entorno, lista_id: object, *, numero: int = 1, **cambios: object
) -> dict[str, object]:
    valores = _borrador(
        entorno,
        lista_id,
        numero=numero,
        estado="PUBLICADA",
        vigencia_desde=datetime(2026, 9, 1, tzinfo=UTC) + timedelta(days=numero),
        publicado_por_id=entorno.usuario_id,
        publicado_en=MOMENTO,
    )
    valores.update(cambios)
    return valores


def _precio(entorno: Entorno, version_id: object, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "version_id": version_id,
        "producto_id": entorno.producto_id,
        "unidades_referencia": 6,
        "costo_informado_id": entorno.costo_id,
        "costo_referencia": Decimal("6000.000000"),
        "regla_margen_id": None,
        "tipo_margen": "MARGEN_BRUTO",
        "valor_margen": Decimal("0.300000"),
        "precio_calculado": Decimal("8571.428571"),
        "precio_final": Decimal("8600.00"),
        "manual": True,
    }
    valores.update(cambios)
    return valores


def _rechaza(sesion: Session, tabla: str, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        _insertar(sesion, tabla, valores)
    assert restriccion in str(error.value)


def _lista_con_borrador(sesion: Session, entorno: Entorno) -> tuple[UUID, UUID]:
    lista = _lista(entorno)
    _insertar(sesion, "lista_precio", lista)
    borrador = _borrador(entorno, lista["id"])
    _insertar(sesion, "lista_version", borrador)
    return lista["id"], borrador["id"]  # type: ignore[return-value]


# --- lista_precio (PRC-01, PRC-14) ----------------------------------------------


def test_la_lista_exige_un_multiplo_positivo_y_una_direccion_del_catalogo(
    db_session: Session,
) -> None:
    """PRC-01, PRC-14, D13 punto 1: el múltiplo es mayor que cero y la dirección es una
    de las tres."""
    entorno = _armar(db_session)
    for direccion in ("ARRIBA", "CERCANO", "ABAJO"):
        _insertar(db_session, "lista_precio", _lista(entorno, redondeo_direccion=direccion))
    _insertar(db_session, "lista_precio", _lista(entorno, redondeo_multiplo=Decimal("0.01")))

    for multiplo in (Decimal("0"), Decimal("-100")):
        _rechaza(
            db_session,
            "lista_precio",
            _lista(entorno, redondeo_multiplo=multiplo),
            "ck_lista_precio__redondeo_multiplo",
        )
    for direccion in ("arriba", "ARRIBAA", ""):
        _rechaza(
            db_session,
            "lista_precio",
            _lista(entorno, redondeo_direccion=direccion),
            "ck_lista_precio__redondeo_direccion",
        )


def test_el_nombre_de_la_lista_es_unico_por_organizacion_sin_distinguir_mayusculas(
    db_session: Session,
) -> None:
    """D13 punto 1: único `(organizacion_id, lower(nombre))`; otra organización puede
    repetirlo."""
    entorno = _armar(db_session)
    otra = _armar(db_session)
    _insertar(db_session, "lista_precio", _lista(entorno, nombre="General"))

    _rechaza(
        db_session, "lista_precio", _lista(entorno, nombre="GENERAL"), "ux_lista_precio__nombre"
    )
    _insertar(db_session, "lista_precio", _lista(otra, nombre="General"))


def test_una_lista_con_actualizado_por_de_otra_organizacion_se_rechaza(
    db_session: Session,
) -> None:
    """INV-02: la clave foránea compuesta hacia `usuario` rechaza al usuario ajeno."""
    entorno = _armar(db_session)
    otra = _armar(db_session)
    _rechaza(
        db_session,
        "lista_precio",
        _lista(entorno, actualizado_por_id=otra.usuario_id),
        "fk_lista_precio__actualizado_por",
    )
    _insertar(db_session, "lista_precio", _lista(entorno, actualizado_por_id=entorno.usuario_id))


# --- regla_margen (PRC-12, PRC-13, D8, D13 punto 2) ------------------------------


def test_ck_regla_margen_valor_rechaza_un_margen_bruto_de_uno_y_acepta_el_markup(
    db_session: Session,
) -> None:
    """PRC-12: margen bruto `< 1`; el markup puede superar 1 (`1.5` = 150%); nunca negativo."""
    entorno = _armar(db_session)
    lista_id, _ = _lista_con_borrador(db_session, entorno)

    _insertar(
        db_session,
        "regla_margen",
        _regla(entorno, lista_id, tipo="MARGEN_BRUTO", valor=Decimal("0.999999")),
    )
    _rechaza(
        db_session,
        "regla_margen",
        _regla(entorno, lista_id, tipo="MARGEN_BRUTO", valor=Decimal("1")),
        "ck_regla_margen__valor",
    )
    _rechaza(
        db_session,
        "regla_margen",
        _regla(entorno, lista_id, tipo="MARGEN_BRUTO", valor=Decimal("1.5")),
        "ck_regla_margen__valor",
    )
    _rechaza(
        db_session,
        "regla_margen",
        _regla(entorno, lista_id, tipo="MARKUP", valor=Decimal("-0.01")),
        "ck_regla_margen__valor",
    )
    _insertar(
        db_session,
        "regla_margen",
        _regla(
            entorno,
            lista_id,
            tipo="MARKUP",
            valor=Decimal("1.5"),
            alcance_tipo="PRODUCTO",
            alcance_id=entorno.producto_id,
        ),
    )
    _insertar(
        db_session,
        "regla_margen",
        _regla(
            entorno,
            lista_id,
            tipo="MARKUP",
            valor=Decimal("0"),
            alcance_tipo="MARCA",
            alcance_id=entorno.marca_id,
        ),
    )


def test_el_check_de_alcance_exige_alcance_id_salvo_en_el_alcance_lista(
    db_session: Session,
) -> None:
    """D13 punto 2: "sin `alcance_id` ⇔ alcance `LISTA`"; el tipo es del catálogo."""
    entorno = _armar(db_session)
    lista_id, _ = _lista_con_borrador(db_session, entorno)

    _rechaza(
        db_session,
        "regla_margen",
        _regla(entorno, lista_id, alcance_tipo="LISTA", alcance_id=entorno.producto_id),
        "ck_regla_margen__alcance",
    )
    _rechaza(
        db_session,
        "regla_margen",
        _regla(entorno, lista_id, alcance_tipo="PRODUCTO", alcance_id=None),
        "ck_regla_margen__alcance",
    )
    _rechaza(
        db_session,
        "regla_margen",
        _regla(entorno, lista_id, alcance_tipo="CLIENTE", alcance_id=entorno.producto_id),
        "ck_regla_margen__alcance_tipo",
    )
    _rechaza(
        db_session,
        "regla_margen",
        _regla(entorno, lista_id, tipo="DESCUENTO"),
        "ck_regla_margen__tipo",
    )


@pytest.mark.parametrize(
    ("alcance_tipo", "columna", "atributo"),
    [
        ("PRODUCTO", "producto_id", "producto_id"),
        ("MARCA", "marca_id", "marca_id"),
        ("CATEGORIA", "categoria_id", "categoria_id"),
        ("PROVEEDOR", "proveedor_id", "proveedor_id"),
    ],
)
def test_las_columnas_generadas_de_alcance_se_llenan_y_su_clave_foranea_rechaza_lo_ajeno(
    db_session: Session, alcance_tipo: str, columna: str, atributo: str
) -> None:
    """D13 punto 2 (ADR-035): `producto_id`, `marca_id`, `categoria_id` y `proveedor_id` son
    generadas a partir de `alcance_id` y su clave foránea compuesta rechaza una entidad de
    otra organización o inexistente (INV-02)."""
    entorno = _armar(db_session)
    otra = _armar(db_session)
    lista_id, _ = _lista_con_borrador(db_session, entorno)
    propio = getattr(entorno, atributo)
    ajeno = getattr(otra, atributo)

    regla = _regla(entorno, lista_id, alcance_tipo=alcance_tipo, alcance_id=propio)
    _insertar(db_session, "regla_margen", regla)
    fila = db_session.execute(
        text(
            "SELECT producto_id, marca_id, categoria_id, proveedor_id FROM regla_margen "
            "WHERE id = :id"
        ),
        {"id": regla["id"]},
    ).one()
    esperadas = {"producto_id": None, "marca_id": None, "categoria_id": None, "proveedor_id": None}
    esperadas[columna] = propio
    assert dict(fila._mapping) == esperadas

    for entidad_ajena in (ajeno, uuid4()):
        _rechaza(
            db_session,
            "regla_margen",
            _regla(entorno, lista_id, alcance_tipo=alcance_tipo, alcance_id=entidad_ajena),
            f"fk_regla_margen__{columna.removesuffix('_id')}",
        )


def test_una_regla_con_una_lista_de_otra_organizacion_se_rechaza(db_session: Session) -> None:
    entorno = _armar(db_session)
    otra = _armar(db_session)
    lista_ajena, _ = _lista_con_borrador(db_session, otra)
    _rechaza(db_session, "regla_margen", _regla(entorno, lista_ajena), "fk_regla_margen__lista")


def test_hay_una_sola_regla_activa_por_lista_y_alcance(db_session: Session) -> None:
    """D8, D13 punto 2: único parcial por lista y alcance entre las activas, incluido el
    alcance `LISTA` (sin `alcance_id`); una inactiva o la de otra lista no estorban."""
    entorno = _armar(db_session)
    lista_id, _ = _lista_con_borrador(db_session, entorno)
    otra_lista = _lista(entorno)
    _insertar(db_session, "lista_precio", otra_lista)

    por_producto = {"alcance_tipo": "PRODUCTO", "alcance_id": entorno.producto_id}
    _insertar(db_session, "regla_margen", _regla(entorno, lista_id, **por_producto))
    _insertar(db_session, "regla_margen", _regla(entorno, lista_id))

    _rechaza(
        db_session,
        "regla_margen",
        _regla(entorno, lista_id, tipo="MARKUP", **por_producto),
        "ux_regla_margen__alcance_activa",
    )
    _rechaza(
        db_session,
        "regla_margen",
        _regla(entorno, lista_id, tipo="MARKUP"),
        "ux_regla_margen__lista_activa",
    )
    # Se acepta: la anterior está inactiva, o es de otra lista, o es de otro alcance.
    _insertar(db_session, "regla_margen", _regla(entorno, lista_id, activo=False, **por_producto))
    _insertar(db_session, "regla_margen", _regla(entorno, lista_id, activo=False))
    _insertar(db_session, "regla_margen", _regla(entorno, otra_lista["id"], **por_producto))
    _insertar(db_session, "regla_margen", _regla(entorno, otra_lista["id"]))
    _insertar(
        db_session,
        "regla_margen",
        _regla(entorno, lista_id, alcance_tipo="MARCA", alcance_id=entorno.marca_id),
    )


# --- redondeo_categoria (PRC-14) ------------------------------------------------


def test_el_redondeo_por_categoria_es_unico_por_lista_y_categoria_y_valida_sus_datos(
    db_session: Session,
) -> None:
    entorno = _armar(db_session)
    otra = _armar(db_session)
    lista_id, _ = _lista_con_borrador(db_session, entorno)

    _insertar(db_session, "redondeo_categoria", _redondeo(entorno, lista_id))
    _rechaza(
        db_session,
        "redondeo_categoria",
        _redondeo(entorno, lista_id, multiplo=Decimal("50.00")),
        "ux_redondeo_categoria__lista_categoria",
    )
    _rechaza(
        db_session,
        "redondeo_categoria",
        _redondeo(entorno, lista_id, categoria_id=otra.categoria_id),
        "fk_redondeo_categoria__categoria",
    )
    for multiplo in (Decimal("0"), Decimal("-1")):
        _rechaza(
            db_session,
            "redondeo_categoria",
            _redondeo(entorno, lista_id, multiplo=multiplo),
            "ck_redondeo_categoria__multiplo",
        )
    _rechaza(
        db_session,
        "redondeo_categoria",
        _redondeo(entorno, lista_id, direccion="REDONDO"),
        "ck_redondeo_categoria__direccion",
    )


# --- lista_version (PRC-02, D5, D6, D13 punto 4) --------------------------------


def test_el_numero_de_version_es_unico_por_lista_y_positivo(db_session: Session) -> None:
    entorno = _armar(db_session)
    lista_id, _ = _lista_con_borrador(db_session, entorno)  # el n.º 1 es el borrador
    otra_lista = _lista(entorno)
    _insertar(db_session, "lista_precio", otra_lista)

    _rechaza(
        db_session,
        "lista_version",
        _publicada(entorno, lista_id, numero=1),
        "ux_lista_version__numero",
    )
    _insertar(db_session, "lista_version", _publicada(entorno, lista_id, numero=2))
    _insertar(db_session, "lista_version", _publicada(entorno, otra_lista["id"], numero=1))
    _rechaza(
        db_session,
        "lista_version",
        _publicada(entorno, otra_lista["id"], numero=0),
        "ck_lista_version__numero",
    )


def test_solo_hay_un_borrador_por_lista(db_session: Session) -> None:
    """D5, D13 punto 4: único parcial "un borrador por lista"."""
    entorno = _armar(db_session)
    lista_id, _ = _lista_con_borrador(db_session, entorno)

    _rechaza(
        db_session,
        "lista_version",
        _borrador(entorno, lista_id, numero=2),
        "ux_lista_version__borrador",
    )
    # Con el borrador publicado ya puede haber otro.
    db_session.execute(
        text(
            "UPDATE lista_version SET estado = 'PUBLICADA', vigencia_desde = :v, "
            "publicado_por_id = :u, publicado_en = :m WHERE lista_id = :l"
        ),
        {"v": MOMENTO, "u": entorno.usuario_id, "m": MOMENTO, "l": lista_id},
    )
    _insertar(db_session, "lista_version", _borrador(entorno, lista_id, numero=2))


def test_dos_versiones_publicadas_no_comparten_vigencia_desde_pero_una_anulada_si(
    db_session: Session,
) -> None:
    """D6, D13 punto 4: único parcial `(lista, vigencia_desde)` entre las `PUBLICADA`."""
    entorno = _armar(db_session)
    lista = _lista(entorno)
    _insertar(db_session, "lista_precio", lista)
    desde = datetime(2026, 10, 1, tzinfo=UTC)
    _insertar(
        db_session,
        "lista_version",
        _publicada(entorno, lista["id"], numero=1, vigencia_desde=desde),
    )

    _rechaza(
        db_session,
        "lista_version",
        _publicada(entorno, lista["id"], numero=2, vigencia_desde=desde),
        "ux_lista_version__vigencia_desde",
    )
    anulada = _publicada(
        entorno,
        lista["id"],
        numero=3,
        estado="ANULADA",
        vigencia_desde=desde,
        anulado_por_id=entorno.usuario_id,
        anulado_en=MOMENTO,
    )
    _insertar(db_session, "lista_version", anulada)


def test_el_estado_de_la_version_es_del_catalogo(db_session: Session) -> None:
    """01 §18: solo `BORRADOR`, `PUBLICADA` y `ANULADA` se almacenan; `PROGRAMADA`, `VIGENTE`
    e `HISTORICA` se derivan (PRC-03)."""
    entorno = _armar(db_session)
    lista = _lista(entorno)
    _insertar(db_session, "lista_precio", lista)
    for estado in ("PROGRAMADA", "VIGENTE", "HISTORICA", "borrador"):
        _rechaza(
            db_session,
            "lista_version",
            _publicada(entorno, lista["id"], estado=estado),
            "ck_lista_version__estado",
        )


def test_la_coherencia_de_la_publicacion_exige_usuario_momento_y_vigencia(
    db_session: Session,
) -> None:
    """D13 punto 4: el borrador no tiene vigencia ni publicación; la versión publicada o
    anulada tiene usuario, momento y vigencia desde."""
    entorno = _armar(db_session)
    lista = _lista(entorno)
    _insertar(db_session, "lista_precio", lista)
    desde = datetime(2026, 10, 1, tzinfo=UTC)

    incoherentes = [
        _borrador(entorno, lista["id"], vigencia_desde=desde),
        _borrador(entorno, lista["id"], publicado_en=MOMENTO),
        _borrador(entorno, lista["id"], publicado_por_id=entorno.usuario_id),
        _borrador(entorno, lista["id"], vigencia_hasta=desde),
        _publicada(entorno, lista["id"], vigencia_desde=None),
        _publicada(entorno, lista["id"], publicado_en=None),
        _publicada(entorno, lista["id"], publicado_por_id=None),
    ]
    for valores in incoherentes:
        _rechaza(db_session, "lista_version", valores, "ck_lista_version__publicacion_coherente")


def test_la_vigencia_hasta_es_posterior_a_la_vigencia_desde(db_session: Session) -> None:
    entorno = _armar(db_session)
    lista = _lista(entorno)
    _insertar(db_session, "lista_precio", lista)
    desde = datetime(2026, 10, 1, tzinfo=UTC)

    _insertar(
        db_session,
        "lista_version",
        _publicada(
            entorno,
            lista["id"],
            numero=1,
            vigencia_desde=desde,
            vigencia_hasta=datetime(2026, 11, 1, tzinfo=UTC),
        ),
    )
    for hasta in (desde, datetime(2026, 9, 1, tzinfo=UTC)):
        _rechaza(
            db_session,
            "lista_version",
            _publicada(
                entorno,
                lista["id"],
                numero=2,
                vigencia_desde=datetime(2026, 10, 2, tzinfo=UTC),
                vigencia_hasta=hasta,
            ),
            "ck_lista_version__vigencia",
        )


def test_la_coherencia_de_la_anulacion_exige_usuario_y_momento(db_session: Session) -> None:
    """PRC-05: anulada ⇔ momento y usuario de la anulación."""
    entorno = _armar(db_session)
    lista = _lista(entorno)
    _insertar(db_session, "lista_precio", lista)

    incoherentes = [
        _publicada(entorno, lista["id"], estado="ANULADA"),
        _publicada(entorno, lista["id"], estado="ANULADA", anulado_en=MOMENTO),
        _publicada(entorno, lista["id"], estado="ANULADA", anulado_por_id=entorno.usuario_id),
        _publicada(entorno, lista["id"], anulado_en=MOMENTO, anulado_por_id=entorno.usuario_id),
        _publicada(entorno, lista["id"], anulado_en=MOMENTO),
    ]
    for valores in incoherentes:
        _rechaza(db_session, "lista_version", valores, "ck_lista_version__anulacion_coherente")


def test_la_version_base_es_de_la_misma_organizacion_y_las_claves_son_compuestas(
    db_session: Session,
) -> None:
    entorno = _armar(db_session)
    otra = _armar(db_session)
    lista_ajena, version_ajena = _lista_con_borrador(db_session, otra)
    lista = _lista(entorno)
    _insertar(db_session, "lista_precio", lista)
    base = _publicada(entorno, lista["id"], numero=1)
    _insertar(db_session, "lista_version", base)

    _insertar(
        db_session,
        "lista_version",
        _borrador(entorno, lista["id"], numero=2, version_base_id=base["id"], generado_en=MOMENTO),
    )
    _rechaza(
        db_session,
        "lista_version",
        _publicada(entorno, lista["id"], numero=3, version_base_id=version_ajena),
        "fk_lista_version__version_base",
    )
    _rechaza(
        db_session,
        "lista_version",
        _publicada(entorno, lista_ajena, numero=3),
        "fk_lista_version__lista",
    )


# --- precio_item (PRC-10, PRC-16, D1, D7, D13 punto 5) --------------------------


def test_un_producto_tiene_un_solo_precio_por_version(db_session: Session) -> None:
    """PRC-10: `ux_precio_item__version_producto`."""
    entorno = _armar(db_session)
    _, version_id = _lista_con_borrador(db_session, entorno)
    _insertar(db_session, "precio_item", _precio(entorno, version_id))

    _rechaza(
        db_session,
        "precio_item",
        _precio(entorno, version_id, precio_final=Decimal("9000.00")),
        "ux_precio_item__version_producto",
    )
    otra_version = _publicada(entorno, _lista_id_de(db_session, version_id), numero=2)
    _insertar(db_session, "lista_version", otra_version)
    _insertar(db_session, "precio_item", _precio(entorno, otra_version["id"]))


def _lista_id_de(sesion: Session, version_id: object) -> UUID:
    return sesion.execute(
        text("SELECT lista_id FROM lista_version WHERE id = :v"), {"v": version_id}
    ).scalar_one()


def test_el_precio_final_es_positivo_y_las_unidades_de_referencia_al_menos_uno(
    db_session: Session,
) -> None:
    """D1, D13 punto 5: `precio_final > 0` y `unidades_referencia >= 1`."""
    entorno = _armar(db_session)
    _, version_id = _lista_con_borrador(db_session, entorno)

    for precio in (Decimal("0"), Decimal("-1.00")):
        _rechaza(
            db_session,
            "precio_item",
            _precio(entorno, version_id, precio_final=precio),
            "ck_precio_item__precio_final",
        )
    for unidades in (0, -6):
        _rechaza(
            db_session,
            "precio_item",
            _precio(entorno, version_id, unidades_referencia=unidades),
            "ck_precio_item__unidades_referencia",
        )
    _insertar(
        db_session,
        "precio_item",
        _precio(entorno, version_id, unidades_referencia=1, precio_final=Decimal("0.01")),
    )


def test_un_precio_calculado_guarda_todo_el_calculo_y_uno_manual_admite_nulos(
    db_session: Session,
) -> None:
    """PRC-16, D7: un precio calculado guarda costo, regla y calculado; uno manual puede
    carecer de costo o de regla ("se admite un precio manual sin costo")."""
    entorno = _armar(db_session)
    lista_id, version_id = _lista_con_borrador(db_session, entorno)
    regla = _regla(entorno, lista_id)
    _insertar(db_session, "regla_margen", regla)

    _insertar(
        db_session,
        "precio_item",
        _precio(entorno, version_id, regla_margen_id=regla["id"], manual=False),
    )
    for faltante in (
        "costo_informado_id",
        "costo_referencia",
        "regla_margen_id",
        "tipo_margen",
        "valor_margen",
        "precio_calculado",
    ):
        calculado = _precio(entorno, version_id, regla_margen_id=regla["id"], manual=False)
        calculado[faltante] = None
        db_session.execute(text("DELETE FROM precio_item WHERE version_id = :v"), {"v": version_id})
        _rechaza(db_session, "precio_item", calculado, "ck_precio_item__calculo_coherente")

    sin_costo = {
        "manual": True,
        "costo_informado_id": None,
        "costo_referencia": None,
        "regla_margen_id": None,
        "tipo_margen": None,
        "valor_margen": None,
        "precio_calculado": None,
        "precio_final": Decimal("8990.00"),
    }
    db_session.execute(text("DELETE FROM precio_item WHERE version_id = :v"), {"v": version_id})
    _insertar(db_session, "precio_item", _precio(entorno, version_id, **sin_costo))


def test_el_tipo_de_margen_del_precio_es_del_catalogo(db_session: Session) -> None:
    entorno = _armar(db_session)
    _, version_id = _lista_con_borrador(db_session, entorno)
    _rechaza(
        db_session,
        "precio_item",
        _precio(entorno, version_id, tipo_margen="DESCUENTO"),
        "ck_precio_item__tipo_margen",
    )


def test_un_precio_no_referencia_costos_reglas_ni_productos_de_otra_organizacion(
    db_session: Session,
) -> None:
    """INV-02: las claves foráneas compuestas de `precio_item`."""
    entorno = _armar(db_session)
    otra = _armar(db_session)
    lista_ajena, version_ajena = _lista_con_borrador(db_session, otra)
    regla_ajena = _regla(otra, lista_ajena)
    _insertar(db_session, "regla_margen", regla_ajena)
    _, version_id = _lista_con_borrador(db_session, entorno)

    _rechaza(
        db_session,
        "precio_item",
        _precio(entorno, version_ajena),
        "fk_precio_item__version",
    )
    _rechaza(
        db_session,
        "precio_item",
        _precio(entorno, version_id, producto_id=otra.producto_id),
        "fk_precio_item__producto",
    )
    _rechaza(
        db_session,
        "precio_item",
        _precio(entorno, version_id, costo_informado_id=otra.costo_id),
        "fk_precio_item__costo_informado",
    )
    _rechaza(
        db_session,
        "precio_item",
        _precio(entorno, version_id, regla_margen_id=regla_ajena["id"]),
        "fk_precio_item__regla_margen",
    )


# --- claves foráneas de cliente y configuración (tarea 1.2, D11, D13 punto 6) ----


def test_el_cliente_solo_admite_una_lista_de_su_organizacion(db_session: Session) -> None:
    """D13 punto 6: `cliente (organizacion_id, lista_precio_id) → lista_precio`; una lista
    inexistente o de otra organización se rechaza (INV-02)."""
    entorno = _armar(db_session)
    otra = _armar(db_session)
    lista_propia, _ = _lista_con_borrador(db_session, entorno)
    lista_ajena, _ = _lista_con_borrador(db_session, otra)
    cliente_id = crear_cliente(db_session, entorno.organizacion_id)

    db_session.execute(
        text("UPDATE cliente SET lista_precio_id = :l WHERE id = :c"),
        {"l": lista_propia, "c": cliente_id},
    )
    for lista_invalida in (lista_ajena, uuid4()):
        with pytest.raises(IntegrityError) as error, db_session.begin_nested():
            db_session.execute(
                text("UPDATE cliente SET lista_precio_id = :l WHERE id = :c"),
                {"l": lista_invalida, "c": cliente_id},
            )
        assert "fk_cliente__lista_precio" in str(error.value)


def test_la_configuracion_solo_admite_una_lista_predeterminada_de_su_organizacion(
    db_session: Session,
) -> None:
    """D13 punto 6: `configuracion_organizacion (organizacion_id, lista_precio_default_id)
    → lista_precio`."""
    entorno = _armar(db_session)
    otra = _armar(db_session)
    lista_propia, _ = _lista_con_borrador(db_session, entorno)
    lista_ajena, _ = _lista_con_borrador(db_session, otra)

    db_session.execute(
        text(
            "UPDATE configuracion_organizacion SET lista_precio_default_id = :l "
            "WHERE organizacion_id = :o"
        ),
        {"l": lista_propia, "o": entorno.organizacion_id},
    )
    for lista_invalida in (lista_ajena, uuid4()):
        with pytest.raises(IntegrityError) as error, db_session.begin_nested():
            db_session.execute(
                text(
                    "UPDATE configuracion_organizacion SET lista_precio_default_id = :l "
                    "WHERE organizacion_id = :o"
                ),
                {"l": lista_invalida, "o": entorno.organizacion_id},
            )
        assert "fk_configuracion_organizacion__lista_precio_default" in str(error.value)


# --- permisos (tarea 1.3, D13 punto 7, INV-05) -----------------------------------


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


def _columnas_con_update(motor: Engine, tabla: str) -> set[str]:
    with motor.connect() as conexion:
        return set(
            conexion.execute(
                text(
                    "SELECT column_name FROM information_schema.column_privileges "
                    "WHERE table_schema = 'public' AND table_name = :t "
                    "AND grantee = 'app_runtime' AND privilege_type = 'UPDATE'"
                ),
                {"t": tabla},
            )
            .scalars()
            .all()
        )


@pytest.mark.parametrize("tabla", ["lista_precio", "regla_margen", "redondeo_categoria"])
def test_app_runtime_lee_inserta_y_actualiza_los_maestros_pero_no_borra(
    app_runtime_engine: Engine, tabla: str
) -> None:
    """D13 punto 7: `SELECT, INSERT, UPDATE` en los tres maestros y sin `DELETE`
    (nada confirmado se borra: se desactiva)."""
    assert _privilegios_de_tabla(app_runtime_engine, tabla) == {"SELECT", "INSERT", "UPDATE"}

    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"DELETE FROM {tabla}"))
    assert "permission denied" in str(error.value)


COLUMNAS_MUTABLES_DE_VERSION = {
    "estado",
    "vigencia_desde",
    "vigencia_hasta",
    "publicado_por_id",
    "publicado_en",
    "anulado_por_id",
    "anulado_en",
    "generado_en",
    "version_base_id",
}


def test_app_runtime_no_borra_versiones_y_solo_actualiza_su_ciclo_de_vida(
    app_runtime_engine: Engine,
) -> None:
    """D13 punto 7: en `lista_version`, `SELECT, INSERT` y `UPDATE` solo de estado,
    vigencias, publicación, anulación y generación."""
    assert _privilegios_de_tabla(app_runtime_engine, "lista_version") == {"SELECT", "INSERT"}
    assert _columnas_con_update(app_runtime_engine, "lista_version") == COLUMNAS_MUTABLES_DE_VERSION

    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text("DELETE FROM lista_version"))
    assert "permission denied" in str(error.value)


@pytest.mark.parametrize(
    ("columna", "valor"),
    [
        ("numero", "1"),
        ("lista_id", "NULL"),
        ("creado_por_id", "NULL"),
        ("operation_id", "NULL"),
        ("organizacion_id", "NULL"),
    ],
)
def test_app_runtime_no_puede_cambiar_el_numero_ni_la_lista_de_una_version(
    app_runtime_engine: Engine, columna: str, valor: str
) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"UPDATE lista_version SET {columna} = {valor}"))
    assert "permission denied" in str(error.value)


def test_app_runtime_puede_leer_insertar_actualizar_y_borrar_precios_del_borrador(
    app_runtime_engine: Engine,
) -> None:
    """D13 punto 7: `precio_item` con los cuatro privilegios (el borrador se regenera);
    INV-11 se garantiza en el servicio, no en la base."""
    assert _privilegios_de_tabla(app_runtime_engine, "precio_item") == {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    }


# --- ciclo de la migración (tareas 1.2 y 1.4) -------------------------------------


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


def test_el_upgrade_aborta_con_un_mensaje_claro_si_un_cliente_apunta_a_una_lista_inexistente(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """Tarea 1.2: antes de crear las claves foráneas, la revisión verifica que ningún
    `cliente.lista_precio_id` ni `lista_precio_default_id` apunte a una lista inexistente
    y aborta diciendo cuál; el error de PostgreSQL al agregar la clave sería opaco."""
    bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
    assert bajada.returncode == 0, bajada.stderr

    with Session(_engine_de_sesion) as sesion:
        organizacion_id = crear_organizacion(sesion).id
        cliente_id = crear_cliente(sesion, organizacion_id)
        sesion.execute(
            text("UPDATE cliente SET lista_precio_id = :l WHERE id = :c"),
            {"l": uuid4(), "c": cliente_id},
        )
        sesion.commit()

    try:
        abortada = _alembic(database_url, "upgrade", "head")
        assert abortada.returncode != 0
        assert "lista_precio_id" in abortada.stderr
        assert "cliente" in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
        assert not _existe_tabla(_engine_de_sesion, "lista_precio")

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(
                text("UPDATE cliente SET lista_precio_id = NULL WHERE id = :c"), {"c": cliente_id}
            )
            conexion.execute(
                text(
                    "UPDATE configuracion_organizacion SET lista_precio_default_id = :l "
                    "WHERE organizacion_id = :o"
                ),
                {"l": uuid4(), "o": organizacion_id},
            )
        abortada_por_la_predeterminada = _alembic(database_url, "upgrade", "head")
        assert abortada_por_la_predeterminada.returncode != 0
        assert "lista_precio_default_id" in abortada_por_la_predeterminada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(
                text(
                    "UPDATE configuracion_organizacion SET lista_precio_default_id = NULL "
                    "WHERE organizacion_id = :o"
                ),
                {"o": organizacion_id},
            )
        reparada = _alembic(database_url, "upgrade", "head")
        assert reparada.returncode == 0, reparada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_ciclo_upgrade_downgrade_upgrade_con_datos_sembrados(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`04` §2.1 punto 4 y D13: el ciclo sube y baja limpio sobre una base con datos; la
    aserción explícita es lo que el `downgrade` pierde: las listas, las reglas, los
    redondeos, las versiones y los precios, y la lista asignada al cliente y la
    predeterminada, que vuelven a nulo."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        lista = _lista(entorno, nombre="General")
        _insertar(sesion, "lista_precio", lista)
        regla = _regla(entorno, lista["id"])
        _insertar(sesion, "regla_margen", regla)
        _insertar(
            sesion,
            "regla_margen",
            _regla(
                entorno,
                lista["id"],
                alcance_tipo="CATEGORIA",
                alcance_id=entorno.categoria_id,
                tipo="MARKUP",
            ),
        )
        _insertar(sesion, "redondeo_categoria", _redondeo(entorno, lista["id"]))
        publicada = _publicada(entorno, lista["id"], numero=1)
        _insertar(sesion, "lista_version", publicada)
        _insertar(
            sesion, "precio_item", _precio(entorno, publicada["id"], regla_margen_id=regla["id"])
        )
        _insertar(
            sesion,
            "lista_version",
            _borrador(
                entorno, lista["id"], numero=2, version_base_id=publicada["id"], generado_en=MOMENTO
            ),
        )
        cliente_id = crear_cliente(sesion, entorno.organizacion_id)
        sesion.execute(
            text("UPDATE cliente SET lista_precio_id = :l WHERE id = :c"),
            {"l": lista["id"], "c": cliente_id},
        )
        sesion.execute(
            text(
                "UPDATE configuracion_organizacion SET lista_precio_default_id = :l "
                "WHERE organizacion_id = :o"
            ),
            {"l": lista["id"], "o": entorno.organizacion_id},
        )
        sesion.commit()
        organizacion_id = entorno.organizacion_id

    assert [_cantidad_de_filas(_engine_de_sesion, t) for t in TABLAS] == [1, 2, 1, 2, 1]

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr

        # Lo que el `downgrade` pierde, escrito explícito (D13).
        assert [_existe_tabla(_engine_de_sesion, t) for t in TABLAS] == [False] * 5
        with _engine_de_sesion.connect() as conexion:
            asignada = conexion.execute(
                text("SELECT lista_precio_id FROM cliente WHERE id = :c"), {"c": cliente_id}
            ).scalar_one()
            predeterminada = conexion.execute(
                text(
                    "SELECT lista_precio_default_id FROM configuracion_organizacion "
                    "WHERE organizacion_id = :o"
                ),
                {"o": organizacion_id},
            ).scalar_one()
        assert asignada is None
        assert predeterminada is None
        # Lo que no pierde: el cliente, el producto y el costo informado.
        assert _cantidad_de_filas(_engine_de_sesion, "cliente") == 1
        assert _cantidad_de_filas(_engine_de_sesion, "costo_informado") == 1

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION
        assert [_cantidad_de_filas(_engine_de_sesion, t) for t in TABLAS] == [0] * 5
        assert _columnas(_engine_de_sesion, "lista_version") == COLUMNAS["lista_version"]
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)
