"""Tareas 3.1 a 3.4 (change 18b; `design.md` D3, D9, D12, D13): la revisión `b6c7d8e9f0a1` suma a
`venta` las columnas `credito_*`, crea `venta_linea_descuento` e `intento_pin_autorizacion`, da
`SELECT, INSERT` a `app_runtime`, suma `AUTORIZACION_OFFLINE` a `ck_observacion__codigo` y siembra
los motivos de `DESCUENTO_MANUAL`.

Consulta el esquema REAL de PostgreSQL ya migrado; que los modelos no se desvíen de la migración
lo cubre `test_modelos_coinciden_con_migracion.py` (tarea 3.5).

Reglas citadas: INV-02, INV-03, INV-05, INV-10, INV-14, TR-06, SYN-07, DSC-08, CRE-10, SEG-04.
"""

from __future__ import annotations

import os
import subprocess
import sys
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
from stock_utiles import crear_motivo_sql
from ventas_utiles import MOMENTO, VentaSembrada, insertar_sql, sembrar_venta_sql

REVISION = "b6c7d8e9f0a1"
REVISION_ANTERIOR = "a2b3c4d5e6f7"  # `ventas`, la última del change 18a.
REVISION_HEAD = "d9e0f1a2b3c4"  # `venta_anulacion` (change 19), la cabeza actual.

AMBITO = "DESCUENTO_MANUAL"
MOTIVOS_SEMBRADOS = {
    "Cliente frecuente",
    "Negociación por volumen",
    "Producto próximo a vencer",
    "Compensación por reclamo",
    "Otro",
}

COLUMNAS_CREDITO_NUMERIC = (
    "credito_limite",
    "credito_saldo_considerado",
    "credito_disponible",
    "credito_exceso",
)
COLUMNAS_CREDITO_TEXT = ("credito_politica", "credito_resolucion")

CODIGO_NUEVO = "AUTORIZACION_OFFLINE"

TABLAS_NUEVAS = ("venta_linea_descuento", "intento_pin_autorizacion")


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


def _existe_columna(motor: Engine, tabla: str, columna: str) -> bool:
    return columna in _columnas(motor, tabla)


def _revision_actual(motor: Engine) -> str:
    with motor.connect() as conexion:
        return conexion.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _motivos_de_ambito(motor: Engine, organizacion_id: UUID, ambito: str) -> list[str]:
    with motor.connect() as conexion:
        return list(
            conexion.execute(
                text(
                    "SELECT nombre FROM motivo WHERE organizacion_id = :o "
                    "AND ambito = :a AND activo ORDER BY nombre"
                ),
                {"o": organizacion_id, "a": ambito},
            )
            .scalars()
            .all()
        )


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


# --- armado de datos -----------------------------------------------------------


class Entorno(NamedTuple):
    organizacion_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    cliente_id: UUID
    venta: VentaSembrada


def _armar(sesion: Session) -> Entorno:
    organizacion = crear_organizacion(sesion)
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(sesion, organizacion.id)
    cliente_id = crear_cliente(sesion, organizacion.id)
    venta = sembrar_venta_sql(
        sesion,
        organizacion.id,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
    )
    return Entorno(organizacion.id, usuario_id, dispositivo_id, cliente_id, venta)


def _regla_sql(sesion: Session, organizacion_id: UUID) -> UUID:
    regla_id = uuid4()
    insertar_sql(
        sesion,
        "regla_descuento",
        {
            "id": regla_id,
            "organizacion_id": organizacion_id,
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
        },
    )
    return regla_id


def _descuento(entorno: Entorno, **cambios: object) -> dict[str, object]:
    """Un descuento automático coherente sobre la línea de la venta sembrada."""
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "venta_linea_id": entorno.venta.linea_id,
        "orden": 0,
        "origen": "AUTOMATICO",
        "regla_id": None,
        "porcentaje": Decimal("0.050000"),
        "importe": Decimal("1562.50"),
        "motivo_id": None,
        "autorizador_id": None,
    }
    valores.update(cambios)
    return valores


def _rechaza(sesion: Session, tabla: str, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        insertar_sql(sesion, tabla, valores)
    assert restriccion in str(error.value)


def _actualiza_venta(sesion: Session, entorno: Entorno, **cambios: object) -> None:
    asignaciones = ", ".join(f"{columna} = :{columna}" for columna in cambios)
    sesion.execute(
        text(f"UPDATE venta SET {asignaciones} WHERE id = :venta_id"),
        {**cambios, "venta_id": entorno.venta.venta_id},
    )


def _rechaza_actualizacion(
    sesion: Session, entorno: Entorno, restriccion: str, **c: object
) -> None:
    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        _actualiza_venta(sesion, entorno, **c)
    assert restriccion in str(error.value)


def _insertar_observacion(sesion: Session, entorno: Entorno, *, codigo: str) -> None:
    comando_id = uuid4()
    insertar_sql(
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
            "huella": "h",
            "app_version": "1.0.0",
            "estado": "ACEPTADO_CON_OBSERVACIONES",
            "occurred_at": MOMENTO,
            "registered_at": MOMENTO,
        },
    )
    insertar_sql(
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


# --- columnas `credito_*` de `venta` (D12, CRE-10, INV-03) ---------------------------


@pytest.mark.parametrize("columna", COLUMNAS_CREDITO_NUMERIC)
def test_inv03_las_columnas_de_credito_son_numeric_14_2_y_nulables(
    _engine_de_sesion: Engine, columna: str
) -> None:
    """INV-03, CRE-10: importes de crédito `numeric(14,2)`, nulables (ventas del 18a)."""
    with _engine_de_sesion.connect() as conexion:
        fila = conexion.execute(
            text(
                "SELECT data_type, numeric_precision, numeric_scale, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'venta' AND column_name = :c"
            ),
            {"c": columna},
        ).one()

    assert tuple(fila) == ("numeric", 14, 2, "YES")


@pytest.mark.parametrize("columna", COLUMNAS_CREDITO_TEXT)
def test_las_columnas_de_politica_y_resolucion_son_text_nulables(
    _engine_de_sesion: Engine, columna: str
) -> None:
    assert _columnas(_engine_de_sesion, "venta")[columna] == ("text", True)


def test_el_autorizador_del_credito_es_uuid_nulable_con_fk_compuesta(
    _engine_de_sesion: Engine,
) -> None:
    """INV-02, D12: FK compuesta `(organizacion_id, credito_autorizador_id)` a `usuario`."""
    assert _columnas(_engine_de_sesion, "venta")["credito_autorizador_id"] == ("uuid", True)
    foraneas = _restricciones(_engine_de_sesion, "venta", "f")
    assert foraneas["fk_venta__credito_autorizador"] == (
        "FOREIGN KEY (organizacion_id, credito_autorizador_id) "
        "REFERENCES usuario(organizacion_id, id)"
    )


def test_inv02_un_autorizador_de_credito_de_otra_organizacion_se_rechaza(
    db_session: Session,
) -> None:
    propio = _armar(db_session)
    ajeno = _armar(db_session)

    _actualiza_venta(db_session, propio, credito_autorizador_id=propio.usuario_id)
    _rechaza_actualizacion(
        db_session,
        propio,
        "fk_venta__credito_autorizador",
        credito_autorizador_id=ajeno.usuario_id,
    )


@pytest.mark.parametrize(
    ("columna", "validos", "invalidos", "restriccion"),
    [
        (
            "credito_politica",
            ["ADVERTIR", "AUTORIZAR", "BLOQUEAR"],
            ["advertir", "PERMITIR", ""],
            "ck_venta__credito_politica",
        ),
        (
            "credito_resolucion",
            ["ADVERTENCIA_ACEPTADA", "PERMISO_PROPIO", "TOLERANCIA_OFFLINE"],
            ["PIN", "sin_exceso", ""],
            "ck_venta__credito_resolucion",
        ),
    ],
)
def test_los_catalogos_del_credito_se_validan_en_la_base(
    db_session: Session,
    columna: str,
    validos: list[str],
    invalidos: list[str],
    restriccion: str,
) -> None:
    """D12: política y resolución están en un catálogo cerrado (`03` §12)."""
    entorno = _armar(db_session)
    for valor in validos:
        _actualiza_venta(
            db_session,
            entorno,
            credito_limite=Decimal("100.00"),
            credito_saldo_considerado=Decimal("0.00"),
            credito_disponible=Decimal("100.00"),
            credito_exceso=Decimal("0.00"),
            **{columna: valor},
        )
    for valor in invalidos:
        _rechaza_actualizacion(db_session, entorno, restriccion, **{columna: valor})


def test_cre10_pin_supervisor_exige_autorizador(db_session: Session) -> None:
    """D12, CRE-05: `PIN_SUPERVISOR` sin autorizador se rechaza; con autorizador, se acepta."""
    entorno = _armar(db_session)
    snapshot = {
        "credito_limite": Decimal("100.00"),
        "credito_saldo_considerado": Decimal("0.00"),
        "credito_disponible": Decimal("100.00"),
        "credito_exceso": Decimal("10.00"),
    }

    _rechaza_actualizacion(
        db_session,
        entorno,
        "ck_venta__credito_autorizador",
        credito_resolucion="PIN_SUPERVISOR",
        **snapshot,
    )
    _actualiza_venta(
        db_session,
        entorno,
        credito_resolucion="PIN_SUPERVISOR",
        credito_autorizador_id=entorno.usuario_id,
        **snapshot,
    )


def test_cre10_el_exceso_no_es_negativo(db_session: Session) -> None:
    entorno = _armar(db_session)
    base = {
        "credito_limite": Decimal("100.00"),
        "credito_saldo_considerado": Decimal("0.00"),
        "credito_disponible": Decimal("100.00"),
    }

    _actualiza_venta(db_session, entorno, credito_exceso=Decimal("0.00"), **base)
    _rechaza_actualizacion(
        db_session, entorno, "ck_venta__credito_exceso", credito_exceso=Decimal("-0.01"), **base
    )


def test_cre10_sin_control_limite_disponible_y_exceso_son_nulos_juntos(
    db_session: Session,
) -> None:
    """D12: límite, disponible y exceso nulos juntos (sin control) solo con `SIN_EXCESO`."""
    entorno = _armar(db_session)

    _actualiza_venta(
        db_session,
        entorno,
        credito_limite=None,
        credito_saldo_considerado=Decimal("500.00"),
        credito_disponible=None,
        credito_exceso=None,
        credito_politica="AUTORIZAR",
        credito_resolucion="SIN_EXCESO",
    )
    # Mezcla de nulos: cada combinación incompleta se rechaza.
    for mezcla in (
        {"credito_limite": None, "credito_disponible": Decimal("1.00"), "credito_exceso": None},
        {"credito_limite": None, "credito_disponible": None, "credito_exceso": Decimal("0.00")},
        {
            "credito_limite": Decimal("1.00"),
            "credito_disponible": None,
            "credito_exceso": Decimal("0.00"),
        },
    ):
        _rechaza_actualizacion(
            db_session,
            entorno,
            "ck_venta__credito_sin_control",
            credito_resolucion="SIN_EXCESO",
            **mezcla,
        )
    # Sin control con otra resolución: se rechaza.
    _rechaza_actualizacion(
        db_session,
        entorno,
        "ck_venta__credito_sin_control",
        credito_limite=None,
        credito_disponible=None,
        credito_exceso=None,
        credito_resolucion="PERMISO_PROPIO",
    )


def test_una_venta_del_18a_sin_snapshot_sigue_siendo_valida(
    db_session: Session, _engine_de_sesion: Engine
) -> None:
    """Las siete columnas son nulables: la venta sembrada sin ellas existe."""
    entorno = _armar(db_session)
    fila = db_session.execute(
        text(
            "SELECT credito_limite, credito_saldo_considerado, credito_disponible, "
            "credito_exceso, credito_politica, credito_resolucion, credito_autorizador_id "
            "FROM venta WHERE id = :id"
        ),
        {"id": entorno.venta.venta_id},
    ).one()
    assert tuple(fila) == (None,) * 7


# --- venta_linea_descuento (D12, DSC-08, INV-02, INV-03) -----------------------------


def test_venta_linea_descuento_tiene_organizacion_y_unico_con_id(
    _engine_de_sesion: Engine,
) -> None:
    tabla = "venta_linea_descuento"
    assert _columnas(_engine_de_sesion, tabla)["organizacion_id"][1] is False
    unicos = _restricciones(_engine_de_sesion, tabla, "u")
    assert unicos["ux_venta_linea_descuento__org_id"] == "UNIQUE (organizacion_id, id)"
    assert unicos["ux_venta_linea_descuento__linea_orden"] == (
        "UNIQUE (organizacion_id, venta_linea_id, orden)"
    )


def test_inv02_las_claves_foraneas_de_venta_linea_descuento_son_compuestas(
    _engine_de_sesion: Engine,
) -> None:
    foraneas = _restricciones(_engine_de_sesion, "venta_linea_descuento", "f")
    esperadas = {
        "fk_venta_linea_descuento__venta_linea": ("venta_linea_id", "venta_linea"),
        "fk_venta_linea_descuento__regla": ("regla_id", "regla_descuento"),
        "fk_venta_linea_descuento__motivo": ("motivo_id", "motivo"),
        "fk_venta_linea_descuento__autorizador": ("autorizador_id", "usuario"),
    }

    assert set(foraneas) == {"fk_venta_linea_descuento__organizacion", *esperadas}
    for nombre, (columna, destino) in esperadas.items():
        assert foraneas[nombre] == (
            f"FOREIGN KEY (organizacion_id, {columna}) REFERENCES {destino}(organizacion_id, id)"
        )


def test_inv03_los_importes_del_descuento_son_numeric(_engine_de_sesion: Engine) -> None:
    with _engine_de_sesion.connect() as conexion:
        filas = conexion.execute(
            text(
                "SELECT column_name, data_type, numeric_precision, numeric_scale "
                "FROM information_schema.columns WHERE table_schema = 'public' "
                "AND table_name = 'venta_linea_descuento' "
                "AND column_name IN ('importe', 'porcentaje')"
            )
        ).all()

    assert {tuple(fila) for fila in filas} == {
        ("importe", "numeric", 14, 2),
        ("porcentaje", "numeric", 9, 6),
    }


def test_inv02_el_descuento_no_referencia_filas_de_otra_organizacion(db_session: Session) -> None:
    """INV-02: la FK compuesta rechaza línea, regla, motivo y autorizador ajenos."""
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    regla_propia = _regla_sql(db_session, propio.organizacion_id)
    regla_ajena = _regla_sql(db_session, ajeno.organizacion_id)
    motivo_ajeno = crear_motivo_sql(db_session, ajeno.organizacion_id, ambito=AMBITO)
    manual = {"origen": "MANUAL", "regla_id": None}

    insertar_sql(db_session, "venta_linea_descuento", _descuento(propio, regla_id=regla_propia))
    _rechaza(
        db_session,
        "venta_linea_descuento",
        _descuento(propio, orden=1, regla_id=regla_propia, venta_linea_id=ajeno.venta.linea_id),
        "fk_venta_linea_descuento__venta_linea",
    )
    _rechaza(
        db_session,
        "venta_linea_descuento",
        _descuento(propio, orden=2, regla_id=regla_ajena),
        "fk_venta_linea_descuento__regla",
    )
    _rechaza(
        db_session,
        "venta_linea_descuento",
        _descuento(propio, orden=3, motivo_id=motivo_ajeno, **manual),
        "fk_venta_linea_descuento__motivo",
    )
    _rechaza(
        db_session,
        "venta_linea_descuento",
        _descuento(propio, orden=4, autorizador_id=ajeno.usuario_id, **manual),
        "fk_venta_linea_descuento__autorizador",
    )


def test_el_origen_del_descuento_esta_en_el_catalogo(db_session: Session) -> None:
    entorno = _armar(db_session)
    regla_id = _regla_sql(db_session, entorno.organizacion_id)
    insertar_sql(
        db_session, "venta_linea_descuento", _descuento(entorno, orden=0, regla_id=regla_id)
    )
    insertar_sql(
        db_session,
        "venta_linea_descuento",
        _descuento(entorno, orden=1, origen="MANUAL", regla_id=None),
    )

    for orden, origen in enumerate(("AUTO", "manual", ""), start=2):
        _rechaza(
            db_session,
            "venta_linea_descuento",
            _descuento(entorno, orden=orden, origen=origen),
            "ck_venta_linea_descuento__origen",
        )


def test_dsc08_la_regla_es_nula_si_y_solo_si_el_descuento_es_manual(db_session: Session) -> None:
    entorno = _armar(db_session)
    regla_id = _regla_sql(db_session, entorno.organizacion_id)

    _rechaza(
        db_session,
        "venta_linea_descuento",
        _descuento(entorno, orden=0, origen="MANUAL", regla_id=regla_id),
        "ck_venta_linea_descuento__regla",
    )
    _rechaza(
        db_session,
        "venta_linea_descuento",
        _descuento(entorno, orden=1, origen="AUTOMATICO", regla_id=None),
        "ck_venta_linea_descuento__regla",
    )


@pytest.mark.parametrize("importe", [Decimal("0.00"), Decimal("-1.00")])
def test_el_importe_del_descuento_es_positivo(db_session: Session, importe: Decimal) -> None:
    entorno = _armar(db_session)
    regla_id = _regla_sql(db_session, entorno.organizacion_id)

    insertar_sql(
        db_session,
        "venta_linea_descuento",
        _descuento(entorno, orden=0, regla_id=regla_id, importe=Decimal("0.01")),
    )
    _rechaza(
        db_session,
        "venta_linea_descuento",
        _descuento(entorno, orden=1, regla_id=regla_id, importe=importe),
        "ck_venta_linea_descuento__importe",
    )


def test_el_porcentaje_del_descuento_esta_en_cero_uno_o_es_nulo(db_session: Session) -> None:
    """Porcentaje en (0, 1] o nulo (importe fijo)."""
    entorno = _armar(db_session)
    regla_id = _regla_sql(db_session, entorno.organizacion_id)
    for orden, porcentaje in enumerate((Decimal("1.000000"), Decimal("0.000001"), None)):
        insertar_sql(
            db_session,
            "venta_linea_descuento",
            _descuento(entorno, orden=orden, regla_id=regla_id, porcentaje=porcentaje),
        )

    for orden, porcentaje in enumerate((Decimal("0"), Decimal("1.000001"), Decimal("-0.1")), 10):
        _rechaza(
            db_session,
            "venta_linea_descuento",
            _descuento(entorno, orden=orden, regla_id=regla_id, porcentaje=porcentaje),
            "ck_venta_linea_descuento__porcentaje",
        )


def test_dsc08_a_lo_sumo_un_descuento_manual_por_linea(db_session: Session) -> None:
    """DSC-08: índice único parcial de `MANUAL` por línea; los automáticos no tienen tope."""
    entorno = _armar(db_session)
    regla_id = _regla_sql(db_session, entorno.organizacion_id)
    otra_linea = sembrar_venta_sql(
        db_session,
        entorno.organizacion_id,
        cliente_id=entorno.cliente_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
    )
    insertar_sql(
        db_session,
        "venta_linea_descuento",
        _descuento(entorno, orden=0, origen="MANUAL", regla_id=None),
    )
    for orden in (1, 2):
        insertar_sql(
            db_session,
            "venta_linea_descuento",
            _descuento(entorno, orden=orden, regla_id=regla_id),
        )
    # El manual de OTRA línea sí entra.
    insertar_sql(
        db_session,
        "venta_linea_descuento",
        _descuento(
            entorno, orden=0, origen="MANUAL", regla_id=None, venta_linea_id=otra_linea.linea_id
        ),
    )

    _rechaza(
        db_session,
        "venta_linea_descuento",
        _descuento(entorno, orden=3, origen="MANUAL", regla_id=None),
        "ux_venta_linea_descuento__manual",
    )


def test_el_orden_del_descuento_no_se_repite_en_la_linea(db_session: Session) -> None:
    entorno = _armar(db_session)
    regla_id = _regla_sql(db_session, entorno.organizacion_id)
    insertar_sql(
        db_session, "venta_linea_descuento", _descuento(entorno, orden=0, regla_id=regla_id)
    )

    _rechaza(
        db_session,
        "venta_linea_descuento",
        _descuento(entorno, orden=0, regla_id=regla_id),
        "ux_venta_linea_descuento__linea_orden",
    )
    _rechaza(
        db_session,
        "venta_linea_descuento",
        _descuento(entorno, orden=-1, regla_id=regla_id),
        "ck_venta_linea_descuento__orden",
    )


# --- intento_pin_autorizacion (D3, D12, D21 punto 7) --------------------------------


def test_intento_pin_autorizacion_tiene_organizacion_y_fks_compuestas_a_usuario(
    _engine_de_sesion: Engine,
) -> None:
    """D3 revisada, punto 8 (cita INV-02): `autorizador_id` (renombre de `usuario_id`) e
    `intentante_id`, ambos con FK compuesta a `usuario`."""
    tabla = "intento_pin_autorizacion"
    columnas = _columnas(_engine_de_sesion, tabla)
    assert columnas["organizacion_id"] == ("uuid", False)
    assert columnas["autorizador_id"] == ("uuid", False)
    assert columnas["intentante_id"] == ("uuid", True)
    assert "usuario_id" not in columnas
    assert columnas["exito"] == ("boolean", False)
    assert columnas["creado_en"] == ("timestamp with time zone", False)
    assert _restricciones(_engine_de_sesion, tabla, "u")["ux_intento_pin_autorizacion__org_id"] == (
        "UNIQUE (organizacion_id, id)"
    )
    fks = _restricciones(_engine_de_sesion, tabla, "f")
    assert fks["fk_intento_pin_autorizacion__autorizador"] == (
        "FOREIGN KEY (organizacion_id, autorizador_id) REFERENCES usuario(organizacion_id, id)"
    )
    assert fks["fk_intento_pin_autorizacion__intentante"] == (
        "FOREIGN KEY (organizacion_id, intentante_id) REFERENCES usuario(organizacion_id, id)"
    )


def test_intento_pin_autorizacion_tiene_los_indices_del_tope_general_y_del_par(
    _engine_de_sesion: Engine,
) -> None:
    general = _indice(_engine_de_sesion, "ix_intento_pin_autorizacion__autorizador_creado_en")
    assert "(organizacion_id, autorizador_id, creado_en)" in general
    par = _indice(_engine_de_sesion, "ix_intento_pin_autorizacion__par_creado_en")
    assert "(organizacion_id, autorizador_id, intentante_id, creado_en)" in par


def _intento(
    organizacion_id: UUID,
    autorizador_id: UUID,
    *,
    intentante_id: UUID | None,
    exito: bool,
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "organizacion_id": organizacion_id,
        "autorizador_id": autorizador_id,
        "intentante_id": intentante_id,
        "exito": exito,
        "creado_en": MOMENTO,
    }


def test_inv02_un_intento_no_referencia_un_autorizador_ni_un_intentante_de_otra_organizacion(
    db_session: Session,
) -> None:
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    org = propio.organizacion_id
    u = propio.usuario_id

    insertar_sql(
        db_session,
        "intento_pin_autorizacion",
        _intento(org, u, intentante_id=u, exito=False),
    )
    _rechaza(
        db_session,
        "intento_pin_autorizacion",
        _intento(org, ajeno.usuario_id, intentante_id=u, exito=False),
        "fk_intento_pin_autorizacion__autorizador",
    )
    _rechaza(
        db_session,
        "intento_pin_autorizacion",
        _intento(org, u, intentante_id=ajeno.usuario_id, exito=False),
        "fk_intento_pin_autorizacion__intentante",
    )


def test_un_fallo_sin_intentante_se_rechaza_y_el_marcador_lo_admite_nulo(
    db_session: Session,
) -> None:
    """`CHECK (exito OR intentante_id IS NOT NULL)` (D3 punto 8; cita ADR-011)."""
    entorno = _armar(db_session)
    org, u = entorno.organizacion_id, entorno.usuario_id

    _rechaza(
        db_session,
        "intento_pin_autorizacion",
        _intento(org, u, intentante_id=None, exito=False),
        "ck_intento_pin_autorizacion__fallo_con_intentante",
    )
    insertar_sql(
        db_session,
        "intento_pin_autorizacion",
        _intento(org, u, intentante_id=None, exito=True),
    )
    insertar_sql(
        db_session,
        "intento_pin_autorizacion",
        _intento(org, u, intentante_id=u, exito=True),
    )


# --- permisos (INV-05, INV-10, TR-06, SEG-04) ----------------------------------------


@pytest.mark.parametrize("tabla", TABLAS_NUEVAS)
def test_inv05_app_runtime_solo_lee_e_inserta_las_tablas_nuevas(
    app_runtime_engine: Engine, tabla: str
) -> None:
    """INV-05, INV-10, TR-06: `SELECT, INSERT` y ningún `UPDATE` ni `DELETE`."""
    assert _privilegios_de_tabla(app_runtime_engine, tabla) == {"SELECT", "INSERT"}
    assert _columnas_con_update(app_runtime_engine, tabla) == set()


@pytest.mark.parametrize("tabla", TABLAS_NUEVAS)
def test_inv05_app_runtime_no_puede_borrar_en_las_tablas_nuevas(
    app_runtime_engine: Engine, tabla: str
) -> None:
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"DELETE FROM {tabla}"))

    assert "permission denied" in str(error.value)


@pytest.mark.parametrize(
    ("tabla", "columna", "valor"),
    [
        ("venta_linea_descuento", "importe", "1"),
        ("intento_pin_autorizacion", "exito", "true"),
        ("venta", "credito_exceso", "1"),
        ("venta", "credito_resolucion", "'SIN_EXCESO'"),
    ],
)
def test_inv10_app_runtime_no_puede_actualizar_lo_nuevo(
    app_runtime_engine: Engine, tabla: str, columna: str, valor: str
) -> None:
    """INV-10, TR-06: sigue sin `UPDATE` en `venta` y no lo hay en las tablas nuevas."""
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"UPDATE {tabla} SET {columna} = {valor}"))

    assert "permission denied" in str(error.value)


# --- observación nueva (D9, SYN-07) -------------------------------------------------


def test_syn07_ck_observacion_codigo_admite_autorizacion_offline(db_session: Session) -> None:
    _insertar_observacion(db_session, _armar(db_session), codigo=CODIGO_NUEVO)


@pytest.mark.parametrize(
    "codigo", ["AUTORIZACION_OFFLINE_", "autorizacion_offline", "AUTORIZACION", ""]
)
def test_syn07_ck_observacion_codigo_sigue_rechazando_lo_que_no_es_del_catalogo(
    db_session: Session, codigo: str
) -> None:
    entorno = _armar(db_session)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_observacion(db_session, entorno, codigo=codigo)
    assert "ck_observacion__codigo" in str(error.value)


# --- ciclo de la migración (D13, tareas 3.3 y 3.4) -----------------------------------


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


def test_la_migracion_siembra_los_motivos_una_sola_vez_en_organizaciones_existentes(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D13: cinco motivos de `DESCUENTO_MANUAL` en cada organización sin ninguno de ese ámbito
    (aunque tenga de otros); una con motivos propios no se toca; `downgrade` y `upgrade` no
    duplican."""
    with Session(_engine_de_sesion) as sesion:
        vacia = crear_organizacion(sesion).id
        con_otros_ambitos = crear_organizacion(sesion).id
        con_propios = crear_organizacion(sesion).id
        for organizacion_id, ambito, nombre in (
            (con_otros_ambitos, "ANULACION_COMPRA", "Otro de compras"),
            (con_propios, AMBITO, "Motivo propio"),
        ):
            sesion.execute(
                text(
                    "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, "
                    "creado_en, actualizado_en) VALUES (:id, :o, :a, :n, true, :m, :m)"
                ),
                {"id": uuid4(), "o": organizacion_id, "a": ambito, "n": nombre, "m": MOMENTO},
            )
        sesion.commit()

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _motivos_de_ambito(_engine_de_sesion, vacia, AMBITO) == []

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr

        for organizacion_id in (vacia, con_otros_ambitos):
            sembrados = _motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO)
            assert set(sembrados) == MOTIVOS_SEMBRADOS
            assert len(sembrados) == 5
        assert _motivos_de_ambito(_engine_de_sesion, con_propios, AMBITO) == ["Motivo propio"]

        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        assert _alembic(database_url, "upgrade", "head").returncode == 0
        assert len(_motivos_de_ambito(_engine_de_sesion, vacia, AMBITO)) == 5
        assert _motivos_de_ambito(_engine_de_sesion, con_otros_ambitos, "ANULACION_COMPRA") == [
            "Otro de compras"
        ]
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_ciclo_upgrade_downgrade_upgrade_con_ventas_del_18a(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`04` §2.1 punto 4: sobre una base con ventas del 18a el ciclo sube y baja limpio. Lo que
    el `downgrade` quita queda como aserción explícita: las dos tablas, las siete columnas
    `credito_*` y los motivos de `DESCUENTO_MANUAL` sin uso. Lo que no pierde: la venta."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        sesion.commit()
        venta_id = entorno.venta.venta_id
        organizacion_id = entorno.organizacion_id

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr

        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
        for tabla in TABLAS_NUEVAS:
            assert not _existe_tabla(_engine_de_sesion, tabla)
        for columna in (*COLUMNAS_CREDITO_NUMERIC, *COLUMNAS_CREDITO_TEXT):
            assert not _existe_columna(_engine_de_sesion, "venta", columna)
        assert not _existe_columna(_engine_de_sesion, "venta", "credito_autorizador_id")
        assert _motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO) == []
        with _engine_de_sesion.connect() as conexion:
            assert (
                conexion.execute(
                    text("SELECT count(*) FROM venta WHERE id = :id"), {"id": venta_id}
                ).scalar_one()
                == 1
            )

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_HEAD
        for tabla in TABLAS_NUEVAS:
            assert _existe_tabla(_engine_de_sesion, tabla)
        assert _existe_columna(_engine_de_sesion, "venta", "credito_autorizador_id")
        assert len(_motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO)) == 5
        with _engine_de_sesion.connect() as conexion:
            assert (
                conexion.execute(
                    text("SELECT credito_resolucion FROM venta WHERE id = :id"), {"id": venta_id}
                ).scalar_one()
                is None
            )
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_aborta_si_hay_descuentos_de_venta(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """INV-10: borrar `venta_linea_descuento` perdería la historia; aborta y no toca nada."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        insertar_sql(
            sesion,
            "venta_linea_descuento",
            _descuento(entorno, origen="MANUAL", regla_id=None),
        )
        sesion.commit()

    try:
        abortada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert abortada.returncode != 0
        assert "venta_linea_descuento" in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_HEAD
        assert _existe_tabla(_engine_de_sesion, "venta_linea_descuento")

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("DELETE FROM venta_linea_descuento"))
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_aborta_si_hay_snapshots_de_credito(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """CRE-10: quitar las columnas `credito_*` perdería el snapshot congelado de una venta."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _actualiza_venta(
            sesion,
            entorno,
            credito_limite=Decimal("100.00"),
            credito_saldo_considerado=Decimal("0.00"),
            credito_disponible=Decimal("100.00"),
            credito_exceso=Decimal("0.00"),
            credito_politica="AUTORIZAR",
            credito_resolucion="SIN_EXCESO",
        )
        sesion.commit()
        venta_id = entorno.venta.venta_id

    try:
        abortada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert abortada.returncode != 0
        assert "credito" in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_HEAD
        assert _existe_columna(_engine_de_sesion, "venta", "credito_resolucion")

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(
                text(
                    "UPDATE venta SET credito_limite = NULL, credito_saldo_considerado = NULL, "
                    "credito_disponible = NULL, credito_exceso = NULL, credito_politica = NULL, "
                    "credito_resolucion = NULL WHERE id = :id"
                ),
                {"id": venta_id},
            )
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_aborta_si_hay_observaciones_autorizacion_offline(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """SYN-07, D9: volver el `CHECK` atrás dejaría inválidas las observaciones nuevas."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _insertar_observacion(sesion, entorno, codigo=CODIGO_NUEVO)
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
