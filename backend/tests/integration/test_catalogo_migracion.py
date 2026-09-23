"""Change 05, grupo 2 (`design.md` Migration Plan, `03` §5): la migración
de catálogo crea `categoria`, `marca`, `producto`, `presentacion` con las
garantías de base que el servicio no puede reemplazar.

Cubre las tareas 2.1 a 2.6 del `tasks.md`: existencia y columnas de las
cuatro tablas, unicidades (CAT-01), la referencia única de presentación
(CAT-03), las restricciones de `presentacion` (CAT-02, CAT-03) y los
`GRANT` sin `DELETE` (ADR-020, CAT-05). INV-02/INV-03/INV-04 ya están
cubiertos por `test_inv02_aislamiento_esquema.py`/`test_inv03_sin_punto_
flotante.py`, que recorren el esquema completo sin lista fija de tablas
(tarea 2.6): no se duplican acá, solo se confirma que pasan con las tablas
nuevas en `test_ratchets_estructurales_incluyen_catalogo`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.catalogo.models import Categoria, Marca, Presentacion, Producto
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad.models import Organizacion

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def organizacion_id(db_session: Session) -> uuid.UUID:
    momento = datetime.now(UTC)
    organizacion = Organizacion(
        id=uuid.uuid4(),
        nombre="Distribuidora de prueba",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Buenos_Aires",
        estado="ACTIVA",
        creado_en=momento,
        actualizado_en=momento,
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion.id


@pytest.fixture
def alicuota_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    momento = datetime.now(UTC)
    alicuota = AlicuotaIva(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        nombre="21%",
        valor="0.210000",
        activo=True,
        creado_en=momento,
        actualizado_en=momento,
    )
    db_session.add(alicuota)
    db_session.flush()
    return alicuota.id


@pytest.fixture
def categoria_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    momento = datetime.now(UTC)
    categoria = Categoria(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        nombre=f"Vinos-{uuid.uuid4().hex[:8]}",
        activo=True,
        creado_en=momento,
        actualizado_en=momento,
    )
    db_session.add(categoria)
    db_session.flush()
    return categoria.id


def _crear_producto(
    db_session: Session,
    *,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    codigo: str,
) -> Producto:
    momento = datetime.now(UTC)
    producto = Producto(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        codigo=codigo,
        nombre="Vino A",
        categoria_id=categoria_id,
        marca_id=None,
        proveedor_id=None,
        unidad_base="botella",
        alicuota_id=alicuota_id,
        activo=True,
        creado_en=momento,
        actualizado_en=momento,
    )
    db_session.add(producto)
    db_session.flush()
    return producto


def _presentacion_obj(
    *,
    organizacion_id: uuid.UUID,
    producto_id: uuid.UUID,
    nombre: str,
    unidades_base: int,
    usar_en_venta: bool = True,
    usar_en_compra: bool = True,
    es_referencia: bool = False,
) -> Presentacion:
    momento = datetime.now(UTC)
    return Presentacion(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        producto_id=producto_id,
        nombre=nombre,
        unidades_base=unidades_base,
        usar_en_venta=usar_en_venta,
        usar_en_compra=usar_en_compra,
        es_referencia=es_referencia,
        activo=True,
        creado_en=momento,
        actualizado_en=momento,
    )


def _crear_presentacion(
    db_session: Session,
    *,
    organizacion_id: uuid.UUID,
    producto_id: uuid.UUID,
    nombre: str,
    unidades_base: int,
    usar_en_venta: bool = True,
    usar_en_compra: bool = True,
    es_referencia: bool = False,
) -> Presentacion:
    """Crea y confirma (`flush`) una presentación válida. Las pruebas que
    esperan que la BASE rechace la fila construyen el objeto con
    `_presentacion_obj` y hacen `add`/`flush` ellas mismas, dentro de su
    propio `pytest.raises` -- esta función no sirve para esos casos porque
    ya haría `flush` (y por lo tanto levantaría la excepción) antes de que
    el bloque `with pytest.raises(...)` del llamador llegue a ejecutarse."""
    presentacion = _presentacion_obj(
        organizacion_id=organizacion_id,
        producto_id=producto_id,
        nombre=nombre,
        unidades_base=unidades_base,
        usar_en_venta=usar_en_venta,
        usar_en_compra=usar_en_compra,
        es_referencia=es_referencia,
    )
    db_session.add(presentacion)
    db_session.flush()
    return presentacion


# --- Tarea 2.1: existencia y columnas -------------------------------------


def test_cat01_las_cuatro_tablas_existen_con_columnas_de_maestro(
    db_session: Session,
) -> None:
    columnas_por_tabla = {
        fila[0]: fila[1]
        for fila in db_session.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name IN "
                "('categoria', 'marca', 'producto', 'presentacion')"
            )
        )
    }
    for tabla in ("categoria", "marca", "producto", "presentacion"):
        columnas = {
            fila[0]
            for fila in db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :tabla"
                ),
                {"tabla": tabla},
            )
        }
        assert {"id", "organizacion_id", "creado_en", "actualizado_en", "actualizado_por_id"} <= (
            columnas
        ), f"{tabla} no tiene las columnas comunes de maestro (03 §2.3): {columnas}"
    del columnas_por_tabla


def test_cat01_producto_organizacion_id_not_null(db_session: Session) -> None:
    resultado = db_session.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'producto' "
            "AND column_name = 'organizacion_id'"
        )
    ).scalar_one()
    assert resultado == "NO"


# --- Tarea 2.2: unicidades (CAT-01) ---------------------------------------


def test_cat01_ux_categoria_nombre_rechaza_duplicado_en_la_misma_organizacion(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    momento = datetime.now(UTC)
    nombre = f"Vinos-{uuid.uuid4().hex[:8]}"
    db_session.add(
        Categoria(
            id=uuid.uuid4(),
            organizacion_id=organizacion_id,
            nombre=nombre,
            activo=True,
            creado_en=momento,
            actualizado_en=momento,
        )
    )
    db_session.flush()

    with db_session.begin_nested():
        db_session.add(
            Categoria(
                id=uuid.uuid4(),
                organizacion_id=organizacion_id,
                nombre=nombre,
                activo=True,
                creado_en=momento,
                actualizado_en=momento,
            )
        )
        with pytest.raises(IntegrityError, match="ux_categoria__nombre"):
            db_session.flush()


def test_cat01_ux_marca_nombre_rechaza_duplicado_en_la_misma_organizacion(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    momento = datetime.now(UTC)
    nombre = f"Bodega-{uuid.uuid4().hex[:8]}"
    db_session.add(
        Marca(
            id=uuid.uuid4(),
            organizacion_id=organizacion_id,
            nombre=nombre,
            activo=True,
            creado_en=momento,
            actualizado_en=momento,
        )
    )
    db_session.flush()

    with db_session.begin_nested():
        db_session.add(
            Marca(
                id=uuid.uuid4(),
                organizacion_id=organizacion_id,
                nombre=nombre,
                activo=True,
                creado_en=momento,
                actualizado_en=momento,
            )
        )
        with pytest.raises(IntegrityError, match="ux_marca__nombre"):
            db_session.flush()


def test_cat01_ux_producto_codigo_rechaza_duplicado(
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    codigo = f"VA-{uuid.uuid4().hex[:8]}"
    _crear_producto(
        db_session,
        organizacion_id=organizacion_id,
        categoria_id=categoria_id,
        alicuota_id=alicuota_id,
        codigo=codigo,
    )
    with db_session.begin_nested():
        momento = datetime.now(UTC)
        db_session.add(
            Producto(
                id=uuid.uuid4(),
                organizacion_id=organizacion_id,
                codigo=codigo,
                nombre="Otro producto",
                categoria_id=categoria_id,
                marca_id=None,
                proveedor_id=None,
                unidad_base="botella",
                alicuota_id=alicuota_id,
                activo=True,
                creado_en=momento,
                actualizado_en=momento,
            )
        )
        with pytest.raises(IntegrityError, match="ux_producto__codigo"):
            db_session.flush()


# --- Tarea 2.3: presentacion (CAT-02, CAT-03) -----------------------------


def test_cat03_ux_presentacion_referencia_rechaza_segunda_referencia_directa(
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    producto = _crear_producto(
        db_session,
        organizacion_id=organizacion_id,
        categoria_id=categoria_id,
        alicuota_id=alicuota_id,
        codigo=f"VA-{uuid.uuid4().hex[:8]}",
    )
    _crear_presentacion(
        db_session,
        organizacion_id=organizacion_id,
        producto_id=producto.id,
        nombre="Botella",
        unidades_base=1,
        es_referencia=True,
    )
    with db_session.begin_nested():
        db_session.add(
            _presentacion_obj(
                organizacion_id=organizacion_id,
                producto_id=producto.id,
                nombre="Caja x6",
                unidades_base=6,
                es_referencia=True,
            )
        )
        with pytest.raises(IntegrityError, match="ux_presentacion__referencia"):
            db_session.flush()


def test_cat03_ck_referencia_venta_rechaza_referencia_sin_venta(
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    producto = _crear_producto(
        db_session,
        organizacion_id=organizacion_id,
        categoria_id=categoria_id,
        alicuota_id=alicuota_id,
        codigo=f"VA-{uuid.uuid4().hex[:8]}",
    )
    with db_session.begin_nested():
        db_session.add(
            _presentacion_obj(
                organizacion_id=organizacion_id,
                producto_id=producto.id,
                nombre="Pack x24",
                unidades_base=24,
                usar_en_venta=False,
                es_referencia=True,
            )
        )
        with pytest.raises(IntegrityError, match="ck_presentacion__referencia_venta"):
            db_session.flush()


def test_cat02_ck_unidades_base_rechaza_cero(
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    producto = _crear_producto(
        db_session,
        organizacion_id=organizacion_id,
        categoria_id=categoria_id,
        alicuota_id=alicuota_id,
        codigo=f"VA-{uuid.uuid4().hex[:8]}",
    )
    with db_session.begin_nested():
        db_session.add(
            _presentacion_obj(
                organizacion_id=organizacion_id,
                producto_id=producto.id,
                nombre="Suelta",
                unidades_base=0,
            )
        )
        with pytest.raises(IntegrityError, match="ck_presentacion__unidades_base"):
            db_session.flush()


# --- Tarea 2.5: GRANT sin DELETE (ADR-020, CAT-05) ------------------------


@pytest.fixture
def _conexion_runtime(app_runtime_engine: Engine) -> Iterator[sa.Connection]:
    conexion = app_runtime_engine.connect()
    try:
        yield conexion
    finally:
        conexion.close()


@pytest.mark.parametrize("tabla", ["categoria", "marca", "producto", "presentacion"])
def test_cat05_app_runtime_no_puede_borrar_de_ninguna_tabla_de_catalogo(
    _conexion_runtime: sa.Connection, tabla: str
) -> None:
    with pytest.raises(Exception, match="permission denied"):
        _conexion_runtime.execute(text(f"DELETE FROM {tabla}"))  # noqa: S608 (tabla de un set fijo)


def test_cat05_app_runtime_puede_select_insert_update_producto(
    app_runtime_engine: Engine,
) -> None:
    """Verificación en positivo (complementa la prueba anterior): el rol de
    aplicación SÍ tiene los tres permisos que necesita para operar, no solo
    le falta `DELETE` por un error de otorgamiento más amplio."""
    consulta = text(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE table_name = 'producto' AND grantee = 'app_runtime'"
    )
    with app_runtime_engine.connect() as conexion:
        privilegios = {fila[0] for fila in conexion.execute(consulta)}
    assert privilegios == {"SELECT", "INSERT", "UPDATE"}
