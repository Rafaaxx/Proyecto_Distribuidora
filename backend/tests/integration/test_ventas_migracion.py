"""Tareas 3.1 a 3.4 (change 18a; `design.md` D1, D10, D12, D16): la revisión `a2b3c4d5e6f7`
crea `venta` y `venta_linea`, da `SELECT, INSERT` a `app_runtime`, agrega la clave foránea
compuesta de `cobranza.venta_id`, suma `VENTA_SIN_COSTO` a `ck_observacion__codigo` y siembra los
motivos de `LISTA_ANTERIOR`.

Consulta el esquema REAL de PostgreSQL ya migrado; que los modelos no se desvíen de la migración
lo cubre `test_modelos_coinciden_con_migracion.py` (tarea 3.5).

Reglas citadas: INV-02, INV-03, INV-05, INV-10, INV-14, TR-06, SYN-07, VTA-03, VTA-06, VTA-11,
PRC-21, PRC-23.
"""

from __future__ import annotations

import os
import subprocess
import sys
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
from stock_utiles import (
    crear_jornada_sql,
    crear_motivo_sql,
    crear_presentacion_referencia_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
    insertar_stock_movimiento_sql,
)
from ventas_utiles import (
    MOMENTO,
    ListaSembrada,
    insertar_sql,
    sembrar_lista_sql,
    sembrar_venta_sql,
    valores_de_linea,
    valores_de_venta,
)

REVISION = "a2b3c4d5e6f7"
# La del change 18b: el `head`. Un `downgrade` que aborta en la revisión de este change revierte
# toda la corrida (Alembic corre en una sola transacción), así que la base queda en `head`.
REVISION_HEAD = "f1a2b3c4d5e6"  # `usuarios_roles_y_cartera` (change 20b), la cabeza actual.
REVISION_ANTERIOR = "f8a9b0c1d2e3"  # `medios_de_pago_administrables`, la previa a este change.

AMBITO = "LISTA_ANTERIOR"
MOTIVOS_SEMBRADOS = {
    "Precio acordado con el cliente",
    "Error en la lista vigente",
    "Otro",
}

TABLAS = ("venta", "venta_linea")

CODIGOS_PREVIOS = (
    "STOCK_NEGATIVO",
    "EXCESO_CREDITO_ADVERTIDO",
    "EXCESO_CREDITO_AUTORIZADO_OFFLINE",
    "EXCESO_CREDITO_DETECTADO_SYNC",
    "LISTA_NO_VIGENTE",
    "DESCUENTO_DIFIERE",
    "CLIENTE_NO_HABILITADO",
    "PERMISO_REVOCADO",
    "JORNADA_LIBERADA",
    "ANULACION_COMPRA_SIN_RECALCULO",
    "MEDIO_INACTIVO",
    "REFERENCIA_FALTANTE",
)
CODIGO_NUEVO = "VENTA_SIN_COSTO"
# Decisión del usuario del 2026-10-19 (D5).
CODIGO_CONSUMIDOR_FINAL = "CONSUMIDOR_FINAL_CON_DEUDA"
# Decisión del usuario del 2026-10-20 (D1, D3, STK-09).
CODIGO_UBICACION_TOMADA = "UBICACION_TOMADA_AL_SINCRONIZAR"

FKS_ESPERADAS = {
    "venta": {
        "fk_venta__cliente": ("cliente_id", "cliente"),
        "fk_venta__usuario": ("usuario_id", "usuario"),
        "fk_venta__dispositivo": ("dispositivo_id", "dispositivo"),
        "fk_venta__ubicacion": ("ubicacion_id", "ubicacion"),
        "fk_venta__jornada": ("jornada_id", "jornada"),
        "fk_venta__lista": ("lista_id", "lista_precio"),
        "fk_venta__lista_version": ("lista_version_id", "lista_version"),
        "fk_venta__motivo_lista": ("motivo_lista_id", "motivo"),
        # Change 18b (D12): el autorizador del snapshot de crédito.
        "fk_venta__credito_autorizador": ("credito_autorizador_id", "usuario"),
    },
    "venta_linea": {
        "fk_venta_linea__venta": ("venta_id", "venta"),
        "fk_venta_linea__producto": ("producto_id", "producto"),
        "fk_venta_linea__presentacion": ("presentacion_id", "presentacion"),
        "fk_venta_linea__lista_version": ("lista_version_id", "lista_version"),
    },
}

INDICES = {
    "ix_venta__occurred_at": "(organizacion_id, occurred_at DESC, id DESC)",
    "ix_venta__cliente": "(organizacion_id, cliente_id, occurred_at DESC, id DESC)",
    "ix_venta__usuario": "(organizacion_id, usuario_id, occurred_at DESC, id DESC)",
    "ix_venta__jornada": "(organizacion_id, jornada_id)",
    "ix_venta__facturacion_pendiente": (
        "WHERE (estado_facturacion = ANY (ARRAY['PENDIENTE'::text, 'PARCIAL'::text]))"
    ),
    "ix_venta_linea__producto": "(organizacion_id, producto_id)",
    "ix_venta_linea__presentacion": "(organizacion_id, presentacion_id)",
}

# (tabla, columna, precisión, escala): INV-03.
COLUMNAS_NUMERIC = {
    ("venta", "total_neto", 14, 2),
    ("venta", "total_iva", 14, 2),
    ("venta", "total", 14, 2),
    ("venta", "importe_facturado", 14, 2),
    ("venta_linea", "precio_referencia", 14, 2),
    ("venta_linea", "importe_bruto", 14, 2),
    ("venta_linea", "importe_descuento", 14, 2),
    ("venta_linea", "importe_neto", 14, 2),
    ("venta_linea", "importe_iva", 14, 2),
    ("venta_linea", "costo_total", 14, 2),
    ("venta_linea", "costo_unitario", 18, 6),
    ("venta_linea", "alicuota", 9, 6),
}
COLUMNAS_INTEGER = {
    ("venta_linea", "orden"),
    ("venta_linea", "unidades_presentacion"),
    ("venta_linea", "cantidad"),
    ("venta_linea", "cantidad_base"),
    ("venta_linea", "unidades_referencia"),
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


# --- armado de datos -----------------------------------------------------------


class Entorno(NamedTuple):
    organizacion_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    cliente_id: UUID
    ubicacion_id: UUID
    lista: ListaSembrada
    producto_id: UUID
    presentacion_id: UUID


def _armar(sesion: Session) -> Entorno:
    organizacion = crear_organizacion(sesion)
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(sesion, organizacion.id)
    producto_id = crear_producto_sql(sesion, organizacion.id)
    return Entorno(
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        cliente_id=crear_cliente(sesion, organizacion.id),
        ubicacion_id=crear_ubicacion_sql(sesion, organizacion.id),
        lista=sembrar_lista_sql(sesion, organizacion.id, usuario_id),
        producto_id=producto_id,
        presentacion_id=crear_presentacion_referencia_sql(
            sesion, organizacion.id, producto_id, unidades_base=6
        ),
    )


def _venta(entorno: Entorno, **cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "cliente_id": entorno.cliente_id,
        "usuario_id": entorno.usuario_id,
        "dispositivo_id": entorno.dispositivo_id,
        "ubicacion_id": entorno.ubicacion_id,
        "lista_id": entorno.lista.lista_id,
        "version_id": entorno.lista.version_id,
    }
    valores = valores_de_venta(entorno.organizacion_id, **base)  # type: ignore[arg-type]
    valores.update(cambios)
    return valores


def _linea(entorno: Entorno, venta_id: object, **cambios: object) -> dict[str, object]:
    valores = valores_de_linea(
        entorno.organizacion_id,
        venta_id,  # type: ignore[arg-type]
        producto_id=entorno.producto_id,
        presentacion_id=entorno.presentacion_id,
        version_id=entorno.lista.version_id,
    )
    valores.update(cambios)
    return valores


def _rechaza(sesion: Session, tabla: str, valores: dict[str, object], restriccion: str) -> None:
    with pytest.raises(IntegrityError) as error, sesion.begin_nested():
        insertar_sql(sesion, tabla, valores)
    assert restriccion in str(error.value)


def _venta_insertada(sesion: Session, entorno: Entorno, **cambios: object) -> dict[str, object]:
    venta = _venta(entorno, **cambios)
    insertar_sql(sesion, "venta", venta)
    return venta


def _insertar_observacion(sesion: Session, entorno: Entorno, *, codigo: str) -> None:
    """Una observación con su comando mínimo (lo que se prueba es el `CHECK` del código)."""
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


# --- las dos tablas (INV-02, INV-03, D16) ---------------------------------------


@pytest.mark.parametrize("tabla", TABLAS)
def test_inv02_cada_tabla_tiene_organizacion_y_unico_con_id(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    """INV-02: `organizacion_id NOT NULL` y `UNIQUE (organizacion_id, id)` en cada tabla."""
    assert _columnas(_engine_de_sesion, tabla)["organizacion_id"][1] is False
    unicos = _restricciones(_engine_de_sesion, tabla, "u")
    assert unicos[f"ux_{tabla}__org_id"] == "UNIQUE (organizacion_id, id)"


@pytest.mark.parametrize("tabla", TABLAS)
def test_inv02_las_claves_foraneas_son_compuestas_con_la_organizacion(
    _engine_de_sesion: Engine, tabla: str
) -> None:
    """INV-02, D16: cada FK a otra entidad de negocio incluye `organizacion_id`."""
    foraneas = _restricciones(_engine_de_sesion, tabla, "f")
    esperadas = FKS_ESPERADAS[tabla]

    assert set(foraneas) == {f"fk_{tabla}__organizacion", *esperadas}
    for nombre, (columna, destino) in esperadas.items():
        assert foraneas[nombre] == (
            f"FOREIGN KEY (organizacion_id, {columna}) REFERENCES {destino}(organizacion_id, id)"
        )


@pytest.mark.parametrize(
    ("campo", "tabla_ajena"),
    [
        ("cliente_id", "cliente"),
        ("ubicacion_id", "ubicacion"),
        ("lista_id", "lista"),
        ("lista_version_id", "lista"),
    ],
)
def test_inv02_una_venta_no_referencia_filas_de_otra_organizacion(
    db_session: Session, campo: str, tabla_ajena: str
) -> None:
    """INV-02, INV-21: la FK compuesta rechaza una referencia de otra organización."""
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    ajena = {
        "cliente_id": ajeno.cliente_id,
        "ubicacion_id": ajeno.ubicacion_id,
        "lista_id": ajeno.lista.lista_id,
        "lista_version_id": ajeno.lista.version_id,
    }[campo]
    nombre_fk = {
        "cliente_id": "fk_venta__cliente",
        "ubicacion_id": "fk_venta__ubicacion",
        "lista_id": "fk_venta__lista",
        "lista_version_id": "fk_venta__lista_version",
    }[campo]

    _rechaza(db_session, "venta", _venta(propio, **{campo: ajena}), nombre_fk)


def test_inv02_el_usuario_el_dispositivo_y_el_motivo_ajenos_se_rechazan(
    db_session: Session,
) -> None:
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    motivo_ajeno = crear_motivo_sql(db_session, ajeno.organizacion_id, ambito=AMBITO)

    _rechaza(db_session, "venta", _venta(propio, usuario_id=ajeno.usuario_id), "fk_venta__usuario")
    _rechaza(
        db_session,
        "venta",
        _venta(propio, dispositivo_id=ajeno.dispositivo_id),
        "fk_venta__dispositivo",
    )
    _rechaza(
        db_session,
        "venta",
        _venta(propio, motivo_lista_id=motivo_ajeno),
        "fk_venta__motivo_lista",
    )


def test_inv02_la_jornada_de_otra_organizacion_se_rechaza(db_session: Session) -> None:
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    jornada_ajena = crear_jornada_sql(
        db_session,
        ajeno.organizacion_id,
        usuario_id=ajeno.usuario_id,
        dispositivo_id=ajeno.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(db_session, ajeno.organizacion_id, requiere_toma=True),
    )

    _rechaza(db_session, "venta", _venta(propio, jornada_id=jornada_ajena), "fk_venta__jornada")


def test_inv02_una_linea_no_referencia_producto_ni_presentacion_ajenos(
    db_session: Session,
) -> None:
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    venta = _venta_insertada(db_session, propio)

    _rechaza(
        db_session,
        "venta_linea",
        _linea(propio, venta["id"], producto_id=ajeno.producto_id),
        "fk_venta_linea__producto",
    )
    _rechaza(
        db_session,
        "venta_linea",
        _linea(propio, venta["id"], presentacion_id=ajeno.presentacion_id),
        "fk_venta_linea__presentacion",
    )
    _rechaza(
        db_session,
        "venta_linea",
        _linea(propio, venta["id"], lista_version_id=ajeno.lista.version_id),
        "fk_venta_linea__lista_version",
    )


def test_inv02_una_linea_no_cuelga_de_una_venta_ajena(db_session: Session) -> None:
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    venta_ajena = _venta_insertada(db_session, ajeno)

    _rechaza(
        db_session,
        "venta_linea",
        _linea(propio, venta_ajena["id"]),
        "fk_venta_linea__venta",
    )


@pytest.mark.parametrize(("tabla", "columna", "precision", "escala"), sorted(COLUMNAS_NUMERIC))
def test_inv03_importes_costos_y_alicuotas_son_numeric(
    _engine_de_sesion: Engine, tabla: str, columna: str, precision: int, escala: int
) -> None:
    """INV-03: importe `numeric(14,2)`, costo unitario `numeric(18,6)`, alícuota
    `numeric(9,6)`; nunca punto flotante."""
    with _engine_de_sesion.connect() as conexion:
        fila = conexion.execute(
            text(
                "SELECT data_type, numeric_precision, numeric_scale "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
            ),
            {"t": tabla, "c": columna},
        ).one()

    assert tuple(fila) == ("numeric", precision, escala)


@pytest.mark.parametrize(("tabla", "columna"), sorted(COLUMNAS_INTEGER))
def test_inv03_las_cantidades_son_integer(
    _engine_de_sesion: Engine, tabla: str, columna: str
) -> None:
    """`03` §2.2: cantidades en unidad base y en presentación son `integer` en ventas."""
    assert _columnas(_engine_de_sesion, tabla)[columna] == ("integer", False)


def test_el_numero_es_unico_por_organizacion(db_session: Session) -> None:
    """VTA-06: `ux_venta__numero` sobre `(organizacion_id, numero)`; otra organización puede
    repetir el número."""
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    _venta_insertada(db_session, propio, numero="V01-000042")
    _venta_insertada(db_session, ajeno, numero="V01-000042")

    _rechaza(db_session, "venta", _venta(propio, numero="V01-000042"), "ux_venta__numero")


@pytest.mark.parametrize(
    ("columna", "validos", "invalidos", "restriccion"),
    [
        ("estado", ["CONFIRMADA", "ANULADA"], ["PENDIENTE", "confirmada", ""], "ck_venta__estado"),
        (
            "estado_facturacion",
            ["NO_REQUIERE", "PENDIENTE", "PARCIAL", "FACTURADA"],
            ["FACTURADO", ""],
            "ck_venta__estado_facturacion",
        ),
        ("modo_impositivo", ["A", "B", "C"], ["D", "a", ""], "ck_venta__modo_impositivo"),
        (
            "modo_confirmacion",
            ["ONLINE"],
            ["ONLINE ", "online", ""],
            "ck_venta__modo_confirmacion",
        ),
    ],
)
def test_los_catalogos_de_la_venta_se_validan_en_la_base(
    db_session: Session,
    columna: str,
    validos: list[str],
    invalidos: list[str],
    restriccion: str,
) -> None:
    entorno = _armar(db_session)
    jornada_id = crear_jornada_sql(
        db_session,
        entorno.organizacion_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=entorno.ubicacion_id,
    )  # con jornada, para que solo falle el catálogo que se prueba
    for valor in validos:
        _venta_insertada(db_session, entorno, jornada_id=jornada_id, **{columna: valor})
    for valor in invalidos:
        _rechaza(
            db_session,
            "venta",
            _venta(entorno, jornada_id=jornada_id, **{columna: valor}),
            restriccion,
        )


def test_inv14_el_total_es_neto_mas_iva(db_session: Session) -> None:
    # Escenario: "La base impide un total incoherente"
    """INV-14, VTA-04: `total = total_neto + total_iva` en la cabecera."""
    entorno = _armar(db_session)
    _venta_insertada(db_session, entorno, total_neto="1000.00", total_iva="210.00", total="1210.00")
    _venta_insertada(db_session, entorno, total_neto="0.00", total_iva="0.00", total="0.00")

    for total in ("1210.01", "1000.00", "0.00"):
        _rechaza(
            db_session,
            "venta",
            _venta(entorno, total_neto="1000.00", total_iva="210.00", total=total),
            "ck_venta__total",
        )


def test_inv09_lo_facturado_no_supera_el_neto_ni_es_negativo(db_session: Session) -> None:
    entorno = _armar(db_session)
    _venta_insertada(db_session, entorno, importe_facturado="31250.00")

    _rechaza(
        db_session, "venta", _venta(entorno, importe_facturado="31250.01"), "ck_venta__facturado"
    )
    _rechaza(db_session, "venta", _venta(entorno, importe_facturado="-1.00"), "ck_venta__facturado")


def test_la_venta_online_admite_jornada_nula_y_la_offline_no(db_session: Session) -> None:
    """`03` §12: `ck_venta__jornada`: solo `ONLINE` puede no tener jornada. El catálogo de
    `modo_confirmacion` admite `OFFLINE` (D1), aunque este chequeo es el de la jornada."""
    entorno = _armar(db_session)
    jornada_id = crear_jornada_sql(
        db_session,
        entorno.organizacion_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=entorno.ubicacion_id,
    )
    _venta_insertada(db_session, entorno, modo_confirmacion="ONLINE", jornada_id=None)
    _venta_insertada(db_session, entorno, modo_confirmacion="ONLINE", jornada_id=jornada_id)
    _venta_insertada(db_session, entorno, modo_confirmacion="OFFLINE", jornada_id=jornada_id)

    _rechaza(
        db_session,
        "venta",
        _venta(entorno, modo_confirmacion="OFFLINE", jornada_id=None),
        "ck_venta__jornada",
    )


def test_la_cantidad_de_una_linea_es_positiva_y_coherente_con_la_presentacion(
    db_session: Session,
) -> None:
    """INV-04, INV-18: `cantidad > 0` y `cantidad_base = cantidad * unidades_presentacion`."""
    entorno = _armar(db_session)
    venta = _venta_insertada(db_session, entorno)
    for orden, cambios in enumerate(
        (
            {"cantidad": 2, "unidades_presentacion": 12, "cantidad_base": 24},
            {"cantidad": 3, "unidades_presentacion": 1, "cantidad_base": 3},
        )
    ):
        insertar_sql(
            db_session, "venta_linea", _linea(entorno, venta["id"], orden=orden, **cambios)
        )

    for orden, cambios in enumerate(
        (
            {"cantidad": 0, "cantidad_base": 0},
            {"cantidad": -1, "cantidad_base": -6},
        ),
        start=10,
    ):
        _rechaza(
            db_session,
            "venta_linea",
            _linea(entorno, venta["id"], orden=orden, **cambios),
            "ck_venta_linea__cantidad",
        )
    _rechaza(
        db_session,
        "venta_linea",
        _linea(
            entorno, venta["id"], orden=20, cantidad=2, unidades_presentacion=6, cantidad_base=13
        ),
        "ck_venta_linea__cantidad_base",
    )


def test_el_neto_de_una_linea_es_bruto_menos_descuento(db_session: Session) -> None:
    """VTA-03, DSC-05: `importe_neto = importe_bruto - importe_descuento`."""
    entorno = _armar(db_session)
    venta = _venta_insertada(db_session, entorno)
    insertar_sql(
        db_session,
        "venta_linea",
        _linea(
            entorno,
            venta["id"],
            orden=0,
            importe_bruto="1000.00",
            importe_descuento="50.00",
            importe_neto="950.00",
        ),
    )

    _rechaza(
        db_session,
        "venta_linea",
        _linea(
            entorno,
            venta["id"],
            orden=1,
            importe_bruto="1000.00",
            importe_descuento="50.00",
            importe_neto="1000.00",
        ),
        "ck_venta_linea__neto",
    )


def test_el_costo_unitario_y_el_total_son_nulos_juntos(db_session: Session) -> None:
    """D10: una línea vendida sin costo (offline) guarda ambos nulos; uno solo no vale."""
    entorno = _armar(db_session)
    venta = _venta_insertada(db_session, entorno)
    insertar_sql(
        db_session,
        "venta_linea",
        _linea(entorno, venta["id"], orden=0, costo_unitario=None, costo_total=None),
    )

    _rechaza(
        db_session,
        "venta_linea",
        _linea(entorno, venta["id"], orden=1, costo_unitario=None, costo_total="10.00"),
        "ck_venta_linea__costo",
    )
    _rechaza(
        db_session,
        "venta_linea",
        _linea(entorno, venta["id"], orden=2, costo_unitario="10.000000", costo_total=None),
        "ck_venta_linea__costo",
    )


def test_las_posiciones_de_las_lineas_no_se_repiten_en_una_venta(db_session: Session) -> None:
    entorno = _armar(db_session)
    venta = _venta_insertada(db_session, entorno)
    insertar_sql(db_session, "venta_linea", _linea(entorno, venta["id"], orden=0))

    _rechaza(
        db_session,
        "venta_linea",
        _linea(entorno, venta["id"], orden=0),
        "ux_venta_linea__venta_orden",
    )
    _rechaza(
        db_session,
        "venta_linea",
        _linea(entorno, venta["id"], orden=-1),
        "ck_venta_linea__orden",
    )


@pytest.mark.parametrize(("nombre", "fragmento"), list(INDICES.items()))
def test_los_indices_de_listado_jornada_y_facturacion_existen(
    _engine_de_sesion: Engine, nombre: str, fragmento: str
) -> None:
    """`03` §12: índices por período, cliente, vendedor, jornada y facturación pendiente."""
    assert fragmento in _indice(_engine_de_sesion, nombre)


# --- permisos (INV-05, INV-10, TR-06) ---------------------------------------------


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


@pytest.mark.parametrize("tabla", TABLAS)
def test_inv05_app_runtime_solo_lee_e_inserta(app_runtime_engine: Engine, tabla: str) -> None:
    """INV-05, INV-10, TR-06, D16: sin `DELETE`; el único `UPDATE` es el de `venta.estado`
    (change 19, D11: la anulación de la venta)."""
    assert _privilegios_de_tabla(app_runtime_engine, tabla) == {"SELECT", "INSERT"}
    assert _columnas_con_update(app_runtime_engine, tabla) == (
        {"estado"} if tabla == "venta" else set()
    )


@pytest.mark.parametrize("tabla", TABLAS)
def test_inv05_app_runtime_no_puede_borrar(app_runtime_engine: Engine, tabla: str) -> None:
    # Escenario: "La base impide editar"
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"DELETE FROM {tabla}"))

    assert "permission denied" in str(error.value)


@pytest.mark.parametrize(
    ("tabla", "columna", "valor"),
    [
        ("venta", "total", "1"),
        ("venta", "importe_facturado", "1"),
        ("venta_linea", "importe_neto", "1"),
        ("venta_linea", "costo_total", "1"),
    ],
)
def test_inv10_app_runtime_no_puede_actualizar_nada(
    app_runtime_engine: Engine, tabla: str, columna: str, valor: str
) -> None:
    # Escenario: "La base impide editar"
    with pytest.raises(ProgrammingError) as error, app_runtime_engine.begin() as conexion:
        conexion.execute(text(f"UPDATE {tabla} SET {columna} = {valor}"))

    assert "permission denied" in str(error.value)


# --- clave foránea de la cobranza (D12, tarea 3.3) ---------------------------------


def _cobranza(entorno: Entorno, **cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": entorno.organizacion_id,
        "cliente_id": entorno.cliente_id,
        "origen": "INDEPENDIENTE",
        "importe": 5000,
        "estado": "CONFIRMADA",
        "operation_id": uuid4(),
        "usuario_id": entorno.usuario_id,
        "dispositivo_id": entorno.dispositivo_id,
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
    }
    valores.update(cambios)
    return valores


def test_la_cobranza_de_venta_exige_una_venta_de_la_misma_organizacion(
    db_session: Session, _engine_de_sesion: Engine
) -> None:
    """VTA-11, INV-02, D12: `fk_cobranza__venta` compuesta; una venta inexistente o ajena se
    rechaza; una propia se acepta."""
    propio = _armar(db_session)
    ajeno = _armar(db_session)
    venta_propia = _venta_insertada(db_session, propio)
    venta_ajena = _venta_insertada(db_session, ajeno)

    foraneas = _restricciones(_engine_de_sesion, "cobranza", "f")
    assert foraneas["fk_cobranza__venta"] == (
        "FOREIGN KEY (organizacion_id, venta_id) REFERENCES venta(organizacion_id, id)"
    )
    insertar_sql(
        db_session,
        "cobranza",
        _cobranza(propio, origen="VENTA", venta_id=venta_propia["id"]),
    )
    for venta_id in (uuid4(), venta_ajena["id"]):
        _rechaza(
            db_session,
            "cobranza",
            _cobranza(propio, origen="VENTA", venta_id=venta_id),
            "fk_cobranza__venta",
        )


# --- observación nueva (D10, SYN-07) --------------------------------------------------


@pytest.mark.parametrize(
    "codigo",
    [*CODIGOS_PREVIOS, CODIGO_NUEVO, CODIGO_CONSUMIDOR_FINAL, CODIGO_UBICACION_TOMADA],
)
def test_syn07_ck_observacion_codigo_admite_el_catalogo(db_session: Session, codigo: str) -> None:
    """SYN-07, D10, D5, STK-09: el `CHECK` admite los doce códigos previos, `VENTA_SIN_COSTO`,
    `CONSUMIDOR_FINAL_CON_DEUDA` y `UBICACION_TOMADA_AL_SINCRONIZAR`."""
    _insertar_observacion(db_session, _armar(db_session), codigo=codigo)


@pytest.mark.parametrize(
    "codigo",
    [
        "VENTA_SIN_COSTOS",
        "venta_sin_costo",
        "CONSUMIDOR_FINAL_CON_DEUDAS",
        "UBICACION_TOMADA",
        "UBICACION_TOMADA_AL_SINCRONIZAR_",
        "",
    ],
)
def test_syn07_ck_observacion_codigo_rechaza_un_codigo_fuera_del_catalogo(
    db_session: Session, codigo: str
) -> None:
    entorno = _armar(db_session)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        _insertar_observacion(db_session, entorno, codigo=codigo)
    assert "ck_observacion__codigo" in str(error.value)


# --- siembra y ciclo de la migración (D6, D16, tareas 3.3 y 3.4) -----------------------


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
    """D6: "Precio acordado con el cliente", "Error en la lista vigente" y "Otro" en cada
    organización sin motivos de `LISTA_ANTERIOR` (aunque tenga de otros ámbitos); una
    organización con motivos propios no se toca; `downgrade` y `upgrade` no duplican."""
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
            assert len(sembrados) == 3
        assert _motivos_de_ambito(_engine_de_sesion, con_propios, AMBITO) == ["Motivo propio"]

        # Una segunda vuelta no duplica nada.
        assert _alembic(database_url, "downgrade", REVISION_ANTERIOR).returncode == 0
        assert _alembic(database_url, "upgrade", "head").returncode == 0
        assert len(_motivos_de_ambito(_engine_de_sesion, vacia, AMBITO)) == 3
        assert _motivos_de_ambito(_engine_de_sesion, con_otros_ambitos, "ANULACION_COMPRA") == [
            "Otro de compras"
        ]
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_la_migracion_aborta_si_hay_cobranzas_con_venta(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """D12: `cobranza.venta_id` no tenía clave foránea; si hay filas con venta (no existía
    donde crearlas), la migración aborta con un mensaje claro y no cambia nada."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        sesion.commit()

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        with _engine_de_sesion.begin() as conexion:
            valores = _cobranza(entorno, origen="VENTA", venta_id=uuid4())
            columnas = ", ".join(valores)
            marcadores = ", ".join(f":{c}" for c in valores)
            conexion.execute(
                text(f"INSERT INTO cobranza ({columnas}) VALUES ({marcadores})"), valores
            )

        abortada = _alembic(database_url, "upgrade", "head")
        assert abortada.returncode != 0
        assert "cobranza" in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
        assert not _existe_tabla(_engine_de_sesion, "venta")

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("DELETE FROM cobranza"))
        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        assert _existe_tabla(_engine_de_sesion, "venta")
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_ciclo_upgrade_downgrade_upgrade_con_datos(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """`04` §2.1 punto 4: el ciclo sube y baja limpio sobre una base con clientes, stock y
    cobranzas independientes. Lo que el `downgrade` quita queda como aserción explícita: las
    dos tablas, la clave foránea de `cobranza.venta_id` y los motivos de `LISTA_ANTERIOR` sin
    uso. Lo que no pierde: clientes, stock y las cobranzas existentes."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        insertar_stock_movimiento_sql(
            sesion,
            organizacion_id=entorno.organizacion_id,
            producto_id=entorno.producto_id,
            ubicacion_id=entorno.ubicacion_id,
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
        )
        insertar_sql(sesion, "cobranza", _cobranza(entorno))
        sesion.commit()
        organizacion_id = entorno.organizacion_id

    try:
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr

        # Lo que el `downgrade` quita, escrito explícito.
        for tabla in TABLAS:
            assert not _existe_tabla(_engine_de_sesion, tabla)
        foraneas = _restricciones(_engine_de_sesion, "cobranza", "f")
        assert "fk_cobranza__venta" not in foraneas
        # Lo que no pierde.
        with _engine_de_sesion.connect() as conexion:
            assert conexion.execute(text("SELECT count(*) FROM cliente")).scalar_one() == 1
            assert conexion.execute(text("SELECT count(*) FROM cobranza")).scalar_one() == 1
            assert conexion.execute(text("SELECT count(*) FROM stock_movimiento")).scalar_one() == 1

        subida = _alembic(database_url, "upgrade", "head")
        assert subida.returncode == 0, subida.stderr
        for tabla in TABLAS:
            assert _existe_tabla(_engine_de_sesion, tabla)
        assert "fk_cobranza__venta" in _restricciones(_engine_de_sesion, "cobranza", "f")
        assert set(_motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO)) == (
            MOTIVOS_SEMBRADOS
        )
        assert len(_motivos_de_ambito(_engine_de_sesion, organizacion_id, AMBITO)) == 3
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


def test_el_downgrade_aborta_si_hay_ventas(database_url: str, _engine_de_sesion: Engine) -> None:
    """`04` §2.1 punto 4, INV-10: borrar las tablas perdería la historia de ventas; el
    `downgrade` aborta con un mensaje claro y no toca nada. Sin ventas, baja."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        sembrar_venta_sql(
            sesion,
            entorno.organizacion_id,
            cliente_id=entorno.cliente_id,
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
        )
        sesion.commit()

    try:
        abortada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert abortada.returncode != 0
        assert "venta" in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_HEAD
        for tabla in TABLAS:
            assert _existe_tabla(_engine_de_sesion, tabla)
        with _engine_de_sesion.connect() as conexion:
            assert conexion.execute(text("SELECT count(*) FROM venta")).scalar_one() == 1

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)


@pytest.mark.parametrize("codigo", [CODIGO_NUEVO, CODIGO_CONSUMIDOR_FINAL, CODIGO_UBICACION_TOMADA])
def test_el_downgrade_aborta_si_hay_observaciones_de_codigos_nuevos(
    database_url: str, _engine_de_sesion: Engine, codigo: str
) -> None:
    """D10, D5, SYN-07: volver el `CHECK` atrás con observaciones de un código nuevo las dejaría
    inválidas; el `downgrade` aborta con un mensaje claro y no toca nada."""
    with Session(_engine_de_sesion) as sesion:
        entorno = _armar(sesion)
        _insertar_observacion(sesion, entorno, codigo=codigo)
        sesion.commit()

    try:
        abortada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert abortada.returncode != 0
        assert codigo in abortada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_HEAD
        for tabla in TABLAS:
            assert _existe_tabla(_engine_de_sesion, tabla)

        with _engine_de_sesion.begin() as conexion:
            conexion.execute(text("DELETE FROM observacion WHERE codigo = :c"), {"c": codigo})
        bajada = _alembic(database_url, "downgrade", REVISION_ANTERIOR)
        assert bajada.returncode == 0, bajada.stderr
        assert _revision_actual(_engine_de_sesion) == REVISION_ANTERIOR
    finally:
        _dejar_en_head(database_url, _engine_de_sesion)
