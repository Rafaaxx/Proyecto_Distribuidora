"""Change 06, grupo 3 (`design.md` Migration Plan punto 1, D10): la
migración `proveedores_y_costos` crea `proveedor` y `costo_informado` con
las garantías de base que el servicio no puede reemplazar, y agrega
`fk_producto__proveedor` a `producto` (todavía nulable en esta revisión).

Cubre las tareas 3.1 a 3.5 del `tasks.md`. La tarea 3.6 (INV-02/INV-03
sobre el esquema completo) se confirma corriendo
`test_inv02_aislamiento_esquema.py`/`test_inv03_sin_punto_flotante.py`
sin modificarlos: recorren `information_schema` sin lista fija de tablas.

`proveedor`/`costo_informado` todavía no tienen modelos SQLAlchemy (grupo
5, tarea 5.1): se insertan con SQL crudo (`text`), igual que las tablas
temporales de `test_inv02_aislamiento_esquema.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from conftest import _PASSWORD_ROL_MIGRACIONES, NOMBRE_ROL_MIGRACIONES, _url_con_credenciales
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.catalogo.models import Presentacion, Producto
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad.models import Organizacion, Rol, Usuario

# Grupo 5 (tarea 5.1) agregó `fk_producto__proveedor` al modelo ORM de
# `Producto`: sin importar `proveedores/models.py`, SQLAlchemy no puede
# resolver la tabla `proveedor` al configurar el mapper de `Producto`
# (`NoReferencedTableError`), aunque este archivo siga insertando
# `proveedor`/`costo_informado` con SQL crudo (docstring arriba).
from app.modules.proveedores.models import CostoInformado, Proveedor  # noqa: F401

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 9, 23, tzinfo=UTC)


# --- Fixtures de apoyo (organización, alícuota, categoría, usuario) --------


@pytest.fixture
def organizacion_id(db_session: Session) -> uuid.UUID:
    organizacion = Organizacion(
        id=uuid.uuid4(),
        nombre="Distribuidora de prueba",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Buenos_Aires",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion.id


@pytest.fixture
def alicuota_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    alicuota = AlicuotaIva(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        nombre="21%",
        valor=Decimal("0.210000"),
        activo=True,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    db_session.add(alicuota)
    db_session.flush()
    return alicuota.id


@pytest.fixture
def usuario_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    rol = Rol(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        nombre="Rol de prueba",
        tope_descuento=Decimal("0"),
        activo=True,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    db_session.add(rol)
    db_session.flush()

    usuario = Usuario(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        usuario=f"usuario-{uuid.uuid4().hex[:8]}",
        nombre="Usuario de prueba",
        email=None,
        password_hash="hash-de-prueba",
        rol_id=rol.id,
        estado="ACTIVO",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    db_session.add(usuario)
    db_session.flush()
    return usuario.id


def _crear_categoria_y_producto(
    db_session: Session,
    *,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID | None,
) -> Producto:
    categoria_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO categoria (id, organizacion_id, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :organizacion_id, :nombre, true, :momento, :momento)"
        ),
        {
            "id": categoria_id,
            "organizacion_id": organizacion_id,
            "nombre": f"Categoria-{uuid.uuid4().hex[:8]}",
            "momento": MOMENTO,
        },
    )
    producto = Producto(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        codigo=f"COD-{uuid.uuid4().hex[:8]}",
        nombre="Cerveza B",
        categoria_id=categoria_id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="botella",
        alicuota_id=alicuota_id,
        activo=True,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    db_session.add(producto)
    db_session.flush()
    return producto


def _crear_presentacion(
    db_session: Session, *, organizacion_id: uuid.UUID, producto_id: uuid.UUID
) -> Presentacion:
    presentacion = Presentacion(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        producto_id=producto_id,
        nombre="Caja x12",
        unidades_base=12,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=True,
        activo=True,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    db_session.add(presentacion)
    db_session.flush()
    return presentacion


def _insertar_proveedor(
    db_session: Session,
    *,
    organizacion_id: uuid.UUID,
    nombre: str,
    cuit: str | None = None,
    activo: bool = True,
) -> uuid.UUID:
    proveedor_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO proveedor "
            "(id, organizacion_id, nombre, cuit, activo, actualizado_en) "
            "VALUES (:id, :organizacion_id, :nombre, :cuit, :activo, :momento)"
        ),
        {
            "id": proveedor_id,
            "organizacion_id": organizacion_id,
            "nombre": nombre,
            "cuit": cuit,
            "activo": activo,
            "momento": MOMENTO,
        },
    )
    return proveedor_id


def _costo_informado_kwargs(
    *,
    organizacion_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    producto_id: uuid.UUID,
    presentacion_id: uuid.UUID,
    usuario_id: uuid.UUID,
    valor: str = "18000.00",
    bonificacion: str = "0",
    alicuota_aplicada: str = "0.210000",
    costo_base: str = "1500.000000",
    vigencia_desde: date = date(2026, 9, 1),
) -> dict[str, object]:
    return {
        "id": uuid.uuid4(),
        "organizacion_id": organizacion_id,
        "proveedor_id": proveedor_id,
        "producto_id": producto_id,
        "presentacion_id": presentacion_id,
        "valor": Decimal(valor),
        "incluye_iva": False,
        "bonificacion": Decimal(bonificacion),
        "alicuota_aplicada": Decimal(alicuota_aplicada),
        "costo_base": Decimal(costo_base),
        "vigencia_desde": vigencia_desde,
        "operation_id": uuid.uuid4(),
        "usuario_id": usuario_id,
        "momento": MOMENTO,
    }


_INSERT_COSTO_INFORMADO = text(
    "INSERT INTO costo_informado "
    "(id, organizacion_id, proveedor_id, producto_id, presentacion_id, valor, "
    "incluye_iva, bonificacion, alicuota_aplicada, costo_base, vigencia_desde, "
    "operation_id, usuario_id, creado_en) "
    "VALUES (:id, :organizacion_id, :proveedor_id, :producto_id, :presentacion_id, "
    ":valor, :incluye_iva, :bonificacion, :alicuota_aplicada, :costo_base, "
    ":vigencia_desde, :operation_id, :usuario_id, :momento)"
)


# --- Tarea 3.1: existencia, columnas, organizacion_id NOT NULL, UNIQUE -----


def test_cst01_proveedor_y_costo_informado_existen_con_columnas_de_03_6(
    db_session: Session,
) -> None:
    columnas_proveedor = {
        fila[0]
        for fila in db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'proveedor'"
            )
        )
    }
    assert {
        "id",
        "organizacion_id",
        "nombre",
        "cuit",
        "contacto",
        "telefono",
        "email",
        "activo",
        "creado_en",
        "actualizado_en",
        "actualizado_por_id",
    } <= columnas_proveedor

    columnas_costo = {
        fila[0]
        for fila in db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'costo_informado'"
            )
        )
    }
    assert {
        "id",
        "organizacion_id",
        "proveedor_id",
        "producto_id",
        "presentacion_id",
        "valor",
        "incluye_iva",
        "bonificacion",
        "alicuota_aplicada",
        "costo_base",
        "vigencia_desde",
        "observacion",
        "operation_id",
        "usuario_id",
        "creado_en",
    } <= columnas_costo


@pytest.mark.parametrize("tabla", ["proveedor", "costo_informado"])
def test_cst01_organizacion_id_not_null(db_session: Session, tabla: str) -> None:
    resultado = db_session.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :tabla "
            "AND column_name = 'organizacion_id'"
        ),
        {"tabla": tabla},
    ).scalar_one()
    assert resultado == "NO"


@pytest.mark.parametrize(
    ("tabla", "restriccion"),
    [("proveedor", "ux_proveedor__org_id"), ("costo_informado", "ux_costo_informado__org_id")],
)
def test_cst01_unique_organizacion_id_id(db_session: Session, tabla: str, restriccion: str) -> None:
    columnas = {
        fila[0]
        for fila in db_session.execute(
            text(
                "SELECT kcu.column_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "ON tc.constraint_name = kcu.constraint_name "
                "WHERE tc.table_name = :tabla AND tc.constraint_name = :restriccion "
                "AND tc.constraint_type = 'UNIQUE'"
            ),
            {"tabla": tabla, "restriccion": restriccion},
        )
    }
    assert columnas == {"organizacion_id", "id"}


# --- Tarea 3.2: ux_proveedor__nombre y ux_proveedor__cuit ------------------


def test_d7_ux_proveedor_nombre_rechaza_duplicado_en_la_misma_organizacion(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    nombre = f"Distribuidora Norte-{uuid.uuid4().hex[:8]}"
    _insertar_proveedor(db_session, organizacion_id=organizacion_id, nombre=nombre)

    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError, match="ux_proveedor__nombre"):
        db_session.execute(
            text(
                "INSERT INTO proveedor (id, organizacion_id, nombre, activo, actualizado_en) "
                "VALUES (:id, :organizacion_id, :nombre, true, :momento)"
            ),
            {
                "id": uuid.uuid4(),
                "organizacion_id": organizacion_id,
                "nombre": nombre,
                "momento": MOMENTO,
            },
        )
    savepoint.rollback()


def test_d7_ux_proveedor_nombre_acepta_el_mismo_nombre_en_otra_organizacion(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    nombre = f"Distribuidora Norte-{uuid.uuid4().hex[:8]}"
    _insertar_proveedor(db_session, organizacion_id=organizacion_id, nombre=nombre)

    otra_organizacion = Organizacion(
        id=uuid.uuid4(),
        nombre="Otra organización",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Buenos_Aires",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    db_session.add(otra_organizacion)
    db_session.flush()

    # No debe lanzar: mismo nombre, distinta organización.
    _insertar_proveedor(db_session, organizacion_id=otra_organizacion.id, nombre=nombre)
    db_session.flush()


def test_d7_ux_proveedor_cuit_rechaza_duplicado_en_la_misma_organizacion(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    cuit = "30712345671"
    _insertar_proveedor(
        db_session, organizacion_id=organizacion_id, nombre="Bodega Andina", cuit=cuit
    )

    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError, match="ux_proveedor__cuit"):
        db_session.execute(
            text(
                "INSERT INTO proveedor (id, organizacion_id, nombre, cuit, activo, "
                "actualizado_en) VALUES (:id, :organizacion_id, :nombre, :cuit, true, "
                ":momento)"
            ),
            {
                "id": uuid.uuid4(),
                "organizacion_id": organizacion_id,
                "nombre": "Otro proveedor",
                "cuit": cuit,
                "momento": MOMENTO,
            },
        )
    savepoint.rollback()


def test_d7_ux_proveedor_cuit_acepta_el_mismo_cuit_en_otra_organizacion(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    cuit = "30712345671"
    _insertar_proveedor(
        db_session, organizacion_id=organizacion_id, nombre="Bodega Andina", cuit=cuit
    )

    otra_organizacion = Organizacion(
        id=uuid.uuid4(),
        nombre="Otra organización",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Buenos_Aires",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    db_session.add(otra_organizacion)
    db_session.flush()

    _insertar_proveedor(
        db_session, organizacion_id=otra_organizacion.id, nombre="Bodega Andina (B)", cuit=cuit
    )
    db_session.flush()


def test_d7_ux_proveedor_cuit_parcial_permite_varios_proveedores_sin_cuit(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    """El índice único es parcial (`WHERE cuit IS NOT NULL`, D7): dos
    proveedores de la misma organización sin CUIT no chocan entre sí."""
    _insertar_proveedor(db_session, organizacion_id=organizacion_id, nombre="Proveedor 1")
    _insertar_proveedor(db_session, organizacion_id=organizacion_id, nombre="Proveedor 2")
    db_session.flush()


# --- Tarea 3.3: FK compuestas y CHECK de costo_informado -------------------


def test_cst01_costo_informado_fk_compuesta_a_proveedor_producto_presentacion_usuario(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor_id = _insertar_proveedor(
        db_session, organizacion_id=organizacion_id, nombre="Distribuidora Norte"
    )
    producto = _crear_categoria_y_producto(
        db_session,
        organizacion_id=organizacion_id,
        alicuota_id=alicuota_id,
        proveedor_id=proveedor_id,
    )
    presentacion = _crear_presentacion(
        db_session, organizacion_id=organizacion_id, producto_id=producto.id
    )

    db_session.execute(
        _INSERT_COSTO_INFORMADO,
        _costo_informado_kwargs(
            organizacion_id=organizacion_id,
            proveedor_id=proveedor_id,
            producto_id=producto.id,
            presentacion_id=presentacion.id,
            usuario_id=usuario_id,
        ),
    )
    db_session.flush()


def test_cst01_costo_informado_rechaza_proveedor_de_otra_organizacion(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """INV-21: la FK compuesta impide referenciar un proveedor de otra
    organización, aunque el `id` exista."""
    otra_organizacion = Organizacion(
        id=uuid.uuid4(),
        nombre="Otra organización",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Buenos_Aires",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    db_session.add(otra_organizacion)
    db_session.flush()
    proveedor_ajeno_id = _insertar_proveedor(
        db_session, organizacion_id=otra_organizacion.id, nombre="Proveedor ajeno"
    )
    proveedor_propio_id = _insertar_proveedor(
        db_session, organizacion_id=organizacion_id, nombre="Distribuidora Norte"
    )

    producto = _crear_categoria_y_producto(
        db_session,
        organizacion_id=organizacion_id,
        alicuota_id=alicuota_id,
        proveedor_id=proveedor_propio_id,
    )
    presentacion = _crear_presentacion(
        db_session, organizacion_id=organizacion_id, producto_id=producto.id
    )

    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError, match="fk_costo_informado__proveedor"):
        db_session.execute(
            _INSERT_COSTO_INFORMADO,
            _costo_informado_kwargs(
                organizacion_id=organizacion_id,
                proveedor_id=proveedor_ajeno_id,
                producto_id=producto.id,
                presentacion_id=presentacion.id,
                usuario_id=usuario_id,
            ),
        )
    savepoint.rollback()


@pytest.mark.parametrize(
    ("valor", "restriccion"),
    [("0.00", "ck_costo_informado__valor"), ("-5.00", "ck_costo_informado__valor")],
)
def test_cst02_ck_valor_rechaza_cero_y_negativo(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
    valor: str,
    restriccion: str,
) -> None:
    proveedor_id = _insertar_proveedor(
        db_session, organizacion_id=organizacion_id, nombre="Distribuidora Norte"
    )
    producto = _crear_categoria_y_producto(
        db_session,
        organizacion_id=organizacion_id,
        alicuota_id=alicuota_id,
        proveedor_id=proveedor_id,
    )
    presentacion = _crear_presentacion(
        db_session, organizacion_id=organizacion_id, producto_id=producto.id
    )

    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError, match=restriccion):
        db_session.execute(
            _INSERT_COSTO_INFORMADO,
            _costo_informado_kwargs(
                organizacion_id=organizacion_id,
                proveedor_id=proveedor_id,
                producto_id=producto.id,
                presentacion_id=presentacion.id,
                usuario_id=usuario_id,
                valor=valor,
            ),
        )
    savepoint.rollback()


@pytest.mark.parametrize("bonificacion", ["1.000000", "-0.000001"])
def test_tr02_ck_bonificacion_rechaza_uno_y_negativa(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
    bonificacion: str,
) -> None:
    proveedor_id = _insertar_proveedor(
        db_session, organizacion_id=organizacion_id, nombre="Distribuidora Norte"
    )
    producto = _crear_categoria_y_producto(
        db_session,
        organizacion_id=organizacion_id,
        alicuota_id=alicuota_id,
        proveedor_id=proveedor_id,
    )
    presentacion = _crear_presentacion(
        db_session, organizacion_id=organizacion_id, producto_id=producto.id
    )

    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError, match="ck_costo_informado__bonificacion"):
        db_session.execute(
            _INSERT_COSTO_INFORMADO,
            _costo_informado_kwargs(
                organizacion_id=organizacion_id,
                proveedor_id=proveedor_id,
                producto_id=producto.id,
                presentacion_id=presentacion.id,
                usuario_id=usuario_id,
                bonificacion=bonificacion,
            ),
        )
    savepoint.rollback()


def test_tr01_ck_alicuota_aplicada_rechaza_negativa(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor_id = _insertar_proveedor(
        db_session, organizacion_id=organizacion_id, nombre="Distribuidora Norte"
    )
    producto = _crear_categoria_y_producto(
        db_session,
        organizacion_id=organizacion_id,
        alicuota_id=alicuota_id,
        proveedor_id=proveedor_id,
    )
    presentacion = _crear_presentacion(
        db_session, organizacion_id=organizacion_id, producto_id=producto.id
    )

    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError, match="ck_costo_informado__alicuota"):
        db_session.execute(
            _INSERT_COSTO_INFORMADO,
            _costo_informado_kwargs(
                organizacion_id=organizacion_id,
                proveedor_id=proveedor_id,
                producto_id=producto.id,
                presentacion_id=presentacion.id,
                usuario_id=usuario_id,
                alicuota_aplicada="-0.01",
            ),
        )
    savepoint.rollback()


def test_cst02_ck_costo_base_rechaza_negativo(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor_id = _insertar_proveedor(
        db_session, organizacion_id=organizacion_id, nombre="Distribuidora Norte"
    )
    producto = _crear_categoria_y_producto(
        db_session,
        organizacion_id=organizacion_id,
        alicuota_id=alicuota_id,
        proveedor_id=proveedor_id,
    )
    presentacion = _crear_presentacion(
        db_session, organizacion_id=organizacion_id, producto_id=producto.id
    )

    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError, match="ck_costo_informado__costo_base"):
        db_session.execute(
            _INSERT_COSTO_INFORMADO,
            _costo_informado_kwargs(
                organizacion_id=organizacion_id,
                proveedor_id=proveedor_id,
                producto_id=producto.id,
                presentacion_id=presentacion.id,
                usuario_id=usuario_id,
                costo_base="-1.000000",
            ),
        )
    savepoint.rollback()


def test_design_d4_indice_de_vigencia_existe_con_las_columnas_de_desempate(
    db_session: Session,
) -> None:
    """`ix_costo_informado__producto_vigencia`
    (`organizacion_id, producto_id, vigencia_desde DESC, creado_en DESC, id
    DESC`, D4) resuelve CST-03 en SQL sin traer filas a Python."""
    definicion = db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'ix_costo_informado__producto_vigencia'"
        )
    ).scalar_one()
    assert "organizacion_id" in definicion
    assert "producto_id" in definicion
    assert "vigencia_desde DESC" in definicion
    assert "creado_en DESC" in definicion
    assert "id DESC" in definicion


# --- Tarea 3.4: fk_producto__proveedor NOT VALID + VALIDATE ----------------


def test_d9_fk_producto_proveedor_rechaza_proveedor_de_otra_organizacion(
    db_session: Session, organizacion_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    """INV-02/INV-21: un producto de A no puede apuntar a un proveedor de
    B, aunque el `id` del proveedor exista."""
    otra_organizacion = Organizacion(
        id=uuid.uuid4(),
        nombre="Otra organización",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Buenos_Aires",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    db_session.add(otra_organizacion)
    db_session.flush()
    proveedor_ajeno_id = _insertar_proveedor(
        db_session, organizacion_id=otra_organizacion.id, nombre="Proveedor ajeno"
    )

    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError, match="fk_producto__proveedor"):
        _crear_categoria_y_producto(
            db_session,
            organizacion_id=organizacion_id,
            alicuota_id=alicuota_id,
            proveedor_id=proveedor_ajeno_id,
        )
    savepoint.rollback()


def test_d2_producto_con_proveedor_nulo_se_acepta_en_70dcb6dce507(database_url: str) -> None:
    """`producto.proveedor_id` sigue nulable en ESTA revisión (`70dcb6dce507`,
    D2): el `NOT NULL` llega recién con `producto_proveedor_obligatorio`
    (grupo 4). Con esa migración ya aplicada en `head` (change 06 completo),
    `db_session` (que corre sobre la sesión de pytest ya migrada a `head`)
    ya no sirve para probar este estado intermedio -- se aísla con alembic
    en subproceso apuntado a la revisión exacta, igual que
    `test_downgrade_de_70dcb6dce507_deja_producto_proveedor_id_en_null`, y
    se repone `head` al final (la base es compartida con el resto de la
    sesión de pytest)."""
    resultado_down = _alembic("downgrade", "70dcb6dce507", database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr

    engine = create_engine(database_url)
    organizacion_id = uuid.uuid4()
    categoria_id = uuid.uuid4()
    alicuota_id = uuid.uuid4()
    producto_id = uuid.uuid4()
    try:
        with engine.begin() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO organizacion (id, nombre, slug, cuit, moneda, "
                    "zona_horaria, estado, creado_en, actualizado_en) VALUES "
                    "(:id, 'Org D2', :slug, NULL, 'ARS', "
                    "'America/Argentina/Buenos_Aires', 'ACTIVA', :momento, :momento)"
                ),
                {
                    "id": organizacion_id,
                    "slug": f"org-{uuid.uuid4().hex[:8]}",
                    "momento": MOMENTO,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO categoria (id, organizacion_id, nombre, activo, "
                    "creado_en, actualizado_en) VALUES (:id, :organizacion_id, "
                    ":nombre, true, :momento, :momento)"
                ),
                {
                    "id": categoria_id,
                    "organizacion_id": organizacion_id,
                    "nombre": f"Categoria-{uuid.uuid4().hex[:8]}",
                    "momento": MOMENTO,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO alicuota_iva (id, organizacion_id, nombre, valor, "
                    "activo, creado_en, actualizado_en) VALUES (:id, :organizacion_id, "
                    "'21%', 0.210000, true, :momento, :momento)"
                ),
                {"id": alicuota_id, "organizacion_id": organizacion_id, "momento": MOMENTO},
            )
            conexion.execute(
                text(
                    "INSERT INTO producto (id, organizacion_id, codigo, nombre, "
                    "categoria_id, marca_id, proveedor_id, unidad_base, alicuota_id, "
                    "activo, creado_en, actualizado_en) VALUES (:id, :organizacion_id, "
                    ":codigo, 'Cerveza D2', :categoria_id, NULL, NULL, 'botella', "
                    ":alicuota_id, true, :momento, :momento)"
                ),
                {
                    "id": producto_id,
                    "organizacion_id": organizacion_id,
                    "codigo": f"COD-{uuid.uuid4().hex[:8]}",
                    "categoria_id": categoria_id,
                    "alicuota_id": alicuota_id,
                    "momento": MOMENTO,
                },
            )

            proveedor_id_en_producto = conexion.execute(
                text("SELECT proveedor_id FROM producto WHERE id = :id"),
                {"id": producto_id},
            ).scalar_one()
            assert proveedor_id_en_producto is None
    finally:
        engine.dispose()
        resultado_up = _alembic("upgrade", "head", database_url=database_url)
        assert resultado_up.returncode == 0, resultado_up.stderr


def test_d9_fk_producto_proveedor_acepta_proveedor_propio(
    db_session: Session, organizacion_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    proveedor_id = _insertar_proveedor(
        db_session, organizacion_id=organizacion_id, nombre="Distribuidora Norte"
    )
    producto = _crear_categoria_y_producto(
        db_session,
        organizacion_id=organizacion_id,
        alicuota_id=alicuota_id,
        proveedor_id=proveedor_id,
    )
    assert producto.proveedor_id == proveedor_id


# --- Tarea 3.5: GRANT sin DELETE (D10) -------------------------------------


@pytest.fixture
def _conexion_runtime(app_runtime_engine: Engine) -> Iterator[sa.Connection]:
    conexion = app_runtime_engine.connect()
    try:
        yield conexion
    finally:
        conexion.close()


def test_app_runtime_no_puede_borrar_proveedor(_conexion_runtime: sa.Connection) -> None:
    with pytest.raises(Exception, match="permission denied"):
        _conexion_runtime.execute(text("DELETE FROM proveedor"))


def test_app_runtime_puede_select_insert_update_proveedor(app_runtime_engine: Engine) -> None:
    consulta = text(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE table_name = 'proveedor' AND grantee = 'app_runtime'"
    )
    with app_runtime_engine.connect() as conexion:
        privilegios = {fila[0] for fila in conexion.execute(consulta)}
    assert privilegios == {"SELECT", "INSERT", "UPDATE"}


def test_cst03_app_runtime_no_puede_borrar_costo_informado(
    _conexion_runtime: sa.Connection,
) -> None:
    """CST-03: los costos informados no se borran; el usuario de aplicación
    no tiene `DELETE`."""
    with pytest.raises(Exception, match="permission denied"):
        _conexion_runtime.execute(text("DELETE FROM costo_informado"))


def test_cst03_app_runtime_no_puede_modificar_costo_informado(
    app_runtime_engine: Engine,
) -> None:
    """CST-03: los costos informados no se sobrescriben; el usuario de
    aplicación no tiene `UPDATE`. Conexión propia (distinta de la prueba de
    `DELETE`): un `UPDATE` denegado deja la transacción de Postgres abortada,
    así que no puede compartir conexión con otra aserción posterior."""
    with (
        app_runtime_engine.connect() as conexion,
        pytest.raises(Exception, match="permission denied"),
    ):
        conexion.execute(text("UPDATE costo_informado SET valor = 1"))


def test_cst03_app_runtime_puede_select_insert_costo_informado_sin_update(
    app_runtime_engine: Engine,
) -> None:
    consulta = text(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE table_name = 'costo_informado' AND grantee = 'app_runtime'"
    )
    with app_runtime_engine.connect() as conexion:
        privilegios = {fila[0] for fila in conexion.execute(consulta)}
    assert privilegios == {"SELECT", "INSERT"}


# --- Downgrade de 70dcb6dce507: producto.proveedor_id no debe quedar ------
# --- colgante hacia una tabla borrada (fix pedido por el coordinador) ------


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    """Corre `alembic` en un subproceso, igual que
    `test_alembic_integracion.py::_alembic`: Alembic lee
    `DATABASE_URL_MIGRATIONS` (rol `app_migrations`, dueño del esquema),
    nunca `DATABASE_URL`."""
    url_migraciones = _url_con_credenciales(
        database_url, NOMBRE_ROL_MIGRACIONES, _PASSWORD_ROL_MIGRACIONES
    )
    entorno = {**os.environ, "DATABASE_URL_MIGRATIONS": url_migraciones}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=entorno,
        capture_output=True,
        text=True,
    )


def test_downgrade_de_70dcb6dce507_deja_producto_proveedor_id_en_null(
    database_url: str,
) -> None:
    """El `downgrade` de `70dcb6dce507` (variante aprobada, D2) hace
    `UPDATE producto SET proveedor_id = NULL` ANTES de borrar
    `fk_producto__proveedor`/`proveedor`/`costo_informado`: un producto que
    apuntaba a un proveedor real (change 05 + change 06 con un proveedor ya
    asignado) no debe quedar con un `proveedor_id` colgando hacia una tabla
    que ya no existe -- si no, la base NO vuelve al estado del change 05
    tras el `downgrade` (`04` §2.1 punto 4).

    Corre alembic directo contra la base compartida de la sesión (igual que
    `test_alembic_integracion.py`), así que termina reponiendo `head` en un
    `finally`, pase o falle la aserción."""
    resultado_up = _alembic("upgrade", "70dcb6dce507", database_url=database_url)
    assert resultado_up.returncode == 0, resultado_up.stderr

    engine = create_engine(database_url)
    organizacion_id = uuid.uuid4()
    categoria_id = uuid.uuid4()
    alicuota_id = uuid.uuid4()
    proveedor_id = uuid.uuid4()
    producto_id = uuid.uuid4()
    try:
        with engine.begin() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO organizacion (id, nombre, slug, cuit, moneda, "
                    "zona_horaria, estado, creado_en, actualizado_en) VALUES "
                    "(:id, 'Org downgrade 06', :slug, NULL, 'ARS', "
                    "'America/Argentina/Buenos_Aires', 'ACTIVA', :momento, :momento)"
                ),
                {
                    "id": organizacion_id,
                    "slug": f"org-{uuid.uuid4().hex[:8]}",
                    "momento": MOMENTO,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO categoria (id, organizacion_id, nombre, activo, "
                    "creado_en, actualizado_en) VALUES (:id, :organizacion_id, "
                    ":nombre, true, :momento, :momento)"
                ),
                {
                    "id": categoria_id,
                    "organizacion_id": organizacion_id,
                    "nombre": f"Categoria-{uuid.uuid4().hex[:8]}",
                    "momento": MOMENTO,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO alicuota_iva (id, organizacion_id, nombre, valor, "
                    "activo, creado_en, actualizado_en) VALUES (:id, :organizacion_id, "
                    "'21%', 0.210000, true, :momento, :momento)"
                ),
                {"id": alicuota_id, "organizacion_id": organizacion_id, "momento": MOMENTO},
            )
            conexion.execute(
                text(
                    "INSERT INTO proveedor (id, organizacion_id, nombre, activo, "
                    "actualizado_en) VALUES (:id, :organizacion_id, 'Distribuidora "
                    "Norte', true, :momento)"
                ),
                {"id": proveedor_id, "organizacion_id": organizacion_id, "momento": MOMENTO},
            )
            conexion.execute(
                text(
                    "INSERT INTO producto (id, organizacion_id, codigo, nombre, "
                    "categoria_id, marca_id, proveedor_id, unidad_base, alicuota_id, "
                    "activo, creado_en, actualizado_en) VALUES (:id, :organizacion_id, "
                    ":codigo, 'Cerveza B', :categoria_id, NULL, :proveedor_id, "
                    "'botella', :alicuota_id, true, :momento, :momento)"
                ),
                {
                    "id": producto_id,
                    "organizacion_id": organizacion_id,
                    "codigo": f"COD-{uuid.uuid4().hex[:8]}",
                    "categoria_id": categoria_id,
                    "proveedor_id": proveedor_id,
                    "alicuota_id": alicuota_id,
                    "momento": MOMENTO,
                },
            )
    finally:
        engine.dispose()

    try:
        resultado_down = _alembic("downgrade", "c1d2e3f4a5b6", database_url=database_url)
        assert resultado_down.returncode == 0, resultado_down.stderr

        engine_post = create_engine(database_url)
        try:
            with engine_post.connect() as conexion:
                proveedor_id_en_producto = conexion.execute(
                    text("SELECT proveedor_id FROM producto WHERE id = :id"),
                    {"id": producto_id},
                ).scalar_one()
                assert proveedor_id_en_producto is None, (
                    "producto.proveedor_id quedó colgando hacia un proveedor "
                    "de una tabla borrada por el downgrade"
                )

                tablas_borradas = (
                    conexion.execute(
                        text(
                            "SELECT tablename FROM pg_tables WHERE tablename IN "
                            "('proveedor', 'costo_informado')"
                        )
                    )
                    .scalars()
                    .all()
                )
                assert tablas_borradas == []
        finally:
            engine_post.dispose()
    finally:
        # Limpieza defensiva ANTES de reponer `head`: si el downgrade no dejó
        # `proveedor_id` en NULL (el bug que esta prueba cubre), el producto
        # de prueba queda con una referencia colgante que haría fallar el
        # `VALIDATE CONSTRAINT` del `upgrade head` de más abajo -- y esa base
        # es COMPARTIDA con el resto de la sesión de pytest, así que no puede
        # quedar por debajo de `head`. Se borra el producto de prueba por
        # `id` (dato de la prueba, no del bug) para que reponer `head` nunca
        # dependa de que el fix ya esté aplicado.
        engine_limpieza = create_engine(database_url)
        try:
            with engine_limpieza.begin() as conexion:
                conexion.execute(text("DELETE FROM producto WHERE id = :id"), {"id": producto_id})
        except Exception:  # noqa: BLE001 (limpieza best-effort, no debe ocultar el assert de arriba)
            pass
        finally:
            engine_limpieza.dispose()

        # Repone `head` pase lo que pase (la base es compartida con el resto
        # de la sesión de pytest, igual que `test_alembic_integracion.py`).
        resultado_up_final = _alembic("upgrade", "head", database_url=database_url)
        assert resultado_up_final.returncode == 0, resultado_up_final.stderr
