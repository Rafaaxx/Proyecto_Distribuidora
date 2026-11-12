"""Change 06, tarea 12.5 (`tasks.md` grupo 12, `04` §2.1 punto 4): ronda
completa de las DOS migraciones del change (`70dcb6dce507` +
`8b9c0d1e2f3a`) -- `upgrade head -> downgrade c1d2e3f4a5b6 -> upgrade
head` -- con datos sembrados antes de la revisión de catálogo (change 05)
y proveedores/costos reales asignados después de subir a `head` (change
06), para verificar que el ciclo completo "sube y baja limpia" (`04` §2.1
punto 4) contra las DOS migraciones juntas, no solo cada una por
separado (ver `test_proveedores_migracion.py` y
`test_producto_proveedor_obligatorio_migracion.py`, que ya cubren cada
downgrade individual).

**DECISIÓN APROBADA POR EL USUARIO (2026-09-24), afirmada a propósito en
este test:** "sube y baja limpia" (`04` §2.1 punto 4) significa que el
ciclo corre SIN ERRORES y preservando la integridad referencial en cada
paso -- no que los datos de negocio sobrevivan un rollback de dos
migraciones. El downgrade de `70dcb6dce507` borra `proveedor` y
`costo_informado` enteras y pone `producto.proveedor_id = NULL` para
TODOS los productos (no solo los provisorios), así que un
`downgrade c1d2e3f4a5b6` seguido de `upgrade head` pierde a propósito el
historial de `costo_informado` y las asignaciones de proveedor real
(`design.md` D2, sección "Risks/Trade-offs": "el provisorio queda
olvidado en datos reales"; mismo riesgo ya nominado, ahora afirmado
explícitamente como aserción de prueba en vez de quedar implícito, tal
como lo dejó planteado la tarea 12.5 en la sesión 2026-09-25). Esta
pérdida es la aceptada por diseño, distinta de una pérdida "inesperada"
por un `DROP` en el orden equivocado o una FK colgante -- eso sigue
siendo lo que este test (y los de aislamiento/integridad de cada
migración individual) descartarían si apareciera.

Sigue el mismo patrón de `test_producto_proveedor_obligatorio_migracion.py`
(alembic en subproceso, revisiones EXPLÍCITAS, nunca `downgrade -2`
relativo -- lección de la tarea 3.6: un target relativo deja de apuntar a
lo mismo en cuanto se agrega una revisión encima) y de
`test_alembic_integracion.py::_sembrar_datos_de_catalogo` (siembra con SQL
crudo, sin ORM). Corre contra la base compartida de la sesión de pytest y
repone `head` en un `finally` incondicional.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from conftest import _PASSWORD_ROL_MIGRACIONES, NOMBRE_ROL_MIGRACIONES, _url_con_credenciales
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

# Revisión de catálogo (change 05): `producto.proveedor_id` ya existe acá,
# nulable y SIN FK (D1 opción A) -- `proveedor` todavía no existe.
REVISION_CATALOGO = "c1d2e3f4a5b6"

MOMENTO = datetime(2026, 9, 24, tzinfo=UTC)

NOMBRE_PROVEEDOR_PROVISORIO = "Proveedor a asignar"


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    """Corre `alembic` en un subproceso, igual que
    `test_proveedores_migracion.py`/`test_producto_proveedor_obligatorio_migracion.py`:
    Alembic lee `DATABASE_URL_MIGRATIONS` (rol `app_migrations`), nunca
    `DATABASE_URL`."""
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


def _crear_organizacion(conexion, *, nombre: str) -> uuid.UUID:
    organizacion_id = uuid.uuid4()
    conexion.execute(
        text(
            "INSERT INTO organizacion (id, nombre, slug, cuit, moneda, zona_horaria, "
            "estado, creado_en, actualizado_en) VALUES (:id, :nombre, :slug, NULL, "
            "'ARS', 'America/Argentina/Buenos_Aires', 'ACTIVA', :momento, :momento)"
        ),
        {
            "id": organizacion_id,
            "nombre": nombre,
            "slug": f"org-{uuid.uuid4().hex[:8]}",
            "momento": MOMENTO,
        },
    )
    return organizacion_id


def _crear_categoria(conexion, *, organizacion_id: uuid.UUID) -> uuid.UUID:
    categoria_id = uuid.uuid4()
    conexion.execute(
        text(
            "INSERT INTO categoria (id, organizacion_id, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :organizacion_id, :nombre, true, :momento, "
            ":momento)"
        ),
        {
            "id": categoria_id,
            "organizacion_id": organizacion_id,
            "nombre": f"Categoria-{uuid.uuid4().hex[:8]}",
            "momento": MOMENTO,
        },
    )
    return categoria_id


def _crear_alicuota(conexion, *, organizacion_id: uuid.UUID) -> uuid.UUID:
    alicuota_id = uuid.uuid4()
    conexion.execute(
        text(
            "INSERT INTO alicuota_iva (id, organizacion_id, nombre, valor, activo, "
            "creado_en, actualizado_en) VALUES (:id, :organizacion_id, '21%', "
            "0.210000, true, :momento, :momento)"
        ),
        {"id": alicuota_id, "organizacion_id": organizacion_id, "momento": MOMENTO},
    )
    return alicuota_id


def _crear_producto(
    conexion,
    *,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID | None,
    nombre: str,
    codigo: str,
) -> uuid.UUID:
    producto_id = uuid.uuid4()
    conexion.execute(
        text(
            "INSERT INTO producto (id, organizacion_id, codigo, nombre, categoria_id, "
            "marca_id, proveedor_id, unidad_base, alicuota_id, activo, creado_en, "
            "actualizado_en) VALUES (:id, :organizacion_id, :codigo, :nombre, "
            ":categoria_id, NULL, :proveedor_id, 'botella', :alicuota_id, true, "
            ":momento, :momento)"
        ),
        {
            "id": producto_id,
            "organizacion_id": organizacion_id,
            "codigo": codigo,
            "nombre": nombre,
            "categoria_id": categoria_id,
            "proveedor_id": proveedor_id,
            "alicuota_id": alicuota_id,
            "momento": MOMENTO,
        },
    )
    return producto_id


def _crear_presentacion(
    conexion, *, organizacion_id: uuid.UUID, producto_id: uuid.UUID, nombre: str = "Botella"
) -> uuid.UUID:
    presentacion_id = uuid.uuid4()
    conexion.execute(
        text(
            "INSERT INTO presentacion (id, organizacion_id, producto_id, nombre, "
            "unidades_base, usar_en_venta, usar_en_compra, es_referencia, activo, "
            "creado_en, actualizado_en, actualizado_por_id) VALUES (:id, "
            ":organizacion_id, :producto_id, :nombre, 1, true, true, true, true, "
            ":momento, :momento, NULL)"
        ),
        {
            "id": presentacion_id,
            "organizacion_id": organizacion_id,
            "producto_id": producto_id,
            "nombre": nombre,
            "momento": MOMENTO,
        },
    )
    return presentacion_id


def _crear_proveedor(
    conexion, *, organizacion_id: uuid.UUID, nombre: str, activo: bool = True
) -> uuid.UUID:
    proveedor_id = uuid.uuid4()
    conexion.execute(
        text(
            "INSERT INTO proveedor (id, organizacion_id, nombre, activo, "
            "actualizado_en) VALUES (:id, :organizacion_id, :nombre, :activo, "
            ":momento)"
        ),
        {
            "id": proveedor_id,
            "organizacion_id": organizacion_id,
            "nombre": nombre,
            "activo": activo,
            "momento": MOMENTO,
        },
    )
    return proveedor_id


def _crear_rol_y_usuario(conexion, *, organizacion_id: uuid.UUID) -> uuid.UUID:
    """`costo_informado.usuario_id` tiene FK compuesta a `usuario`: no puede
    ser un UUID inventado (mismo criterio que `test_proveedores_concurrencia.py`)."""
    rol_id = uuid.uuid4()
    usuario_id = uuid.uuid4()
    conexion.execute(
        text(
            "INSERT INTO rol (id, organizacion_id, nombre, tope_descuento, activo, "
            "creado_en, actualizado_en, actualizado_por_id) VALUES (:id, "
            ":organizacion_id, :nombre, 0.100000, true, :momento, :momento, NULL)"
        ),
        {
            "id": rol_id,
            "organizacion_id": organizacion_id,
            "nombre": f"Rol-{uuid.uuid4().hex[:8]}",
            "momento": MOMENTO,
        },
    )
    conexion.execute(
        text(
            "INSERT INTO usuario (id, organizacion_id, usuario, nombre, email, "
            "password_hash, rol_id, tope_descuento_override, estado, creado_en, "
            "actualizado_en, actualizado_por_id) VALUES (:id, :organizacion_id, "
            ":usuario, 'Usuario 12.5', NULL, 'hash-de-prueba', :rol_id, NULL, "
            "'ACTIVO', :momento, :momento, NULL)"
        ),
        {
            "id": usuario_id,
            "organizacion_id": organizacion_id,
            "usuario": f"usuario-{uuid.uuid4().hex[:8]}",
            "rol_id": rol_id,
            "momento": MOMENTO,
        },
    )
    return usuario_id


def _crear_costo_informado(
    conexion,
    *,
    organizacion_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    producto_id: uuid.UUID,
    presentacion_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> uuid.UUID:
    costo_id = uuid.uuid4()
    conexion.execute(
        text(
            "INSERT INTO costo_informado (id, organizacion_id, proveedor_id, "
            "producto_id, presentacion_id, valor, incluye_iva, computa_credito_fiscal, "
            "bonificacion, alicuota_aplicada, costo_base, vigencia_desde, observacion, "
            "operation_id, usuario_id, creado_en) VALUES (:id, :organizacion_id, "
            ":proveedor_id, :producto_id, :presentacion_id, 1500.00, false, true, 0, "
            "0.210000, 1500.000000, :vigencia_desde, NULL, :operation_id, "
            ":usuario_id, :momento)"
        ),
        {
            "id": costo_id,
            "organizacion_id": organizacion_id,
            "proveedor_id": proveedor_id,
            "producto_id": producto_id,
            "presentacion_id": presentacion_id,
            "vigencia_desde": date(2026, 9, 1),
            "operation_id": uuid.uuid4(),
            "usuario_id": usuario_id,
            "momento": MOMENTO,
        },
    )
    return costo_id


@pytest.fixture
def _en_revision_catalogo(database_url: str):
    """Deja la base en `c1d2e3f4a5b6` (antes de las dos migraciones de este
    change) para sembrar datos previos, y repone `head` al terminar."""
    resultado_down = _alembic("downgrade", REVISION_CATALOGO, database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr
    try:
        yield
    finally:
        resultado_up = _alembic("upgrade", "head", database_url=database_url)
        assert resultado_up.returncode == 0, resultado_up.stderr


def test_ronda_de_las_dos_migraciones_sube_y_baja_limpia(
    database_url: str, _en_revision_catalogo: None
) -> None:
    """`upgrade head -> downgrade c1d2e3f4a5b6 -> upgrade head` con
    productos del change 05 sin proveedor, y proveedores/costos reales del
    change 06 sembrados después de la primera subida (`04` §2.1 punto 4)."""
    # --- Paso 1: sembrar en c1d2e3f4a5b6 (antes de las dos migraciones) ---
    engine = create_engine(database_url)
    try:
        with engine.begin() as conexion:
            org_b = _crear_organizacion(conexion, nombre="Org B huérfana 12.5")
            categoria_b = _crear_categoria(conexion, organizacion_id=org_b)
            alicuota_b = _crear_alicuota(conexion, organizacion_id=org_b)
            producto_b = _crear_producto(
                conexion,
                organizacion_id=org_b,
                categoria_id=categoria_b,
                alicuota_id=alicuota_b,
                proveedor_id=None,
                nombre="Vino B 12.5",
                codigo="COD-125-B",
            )
            _crear_presentacion(conexion, organizacion_id=org_b, producto_id=producto_b)

            org_a = _crear_organizacion(conexion, nombre="Org A con proveedor real 12.5")
            categoria_a = _crear_categoria(conexion, organizacion_id=org_a)
            alicuota_a = _crear_alicuota(conexion, organizacion_id=org_a)
            producto_a = _crear_producto(
                conexion,
                organizacion_id=org_a,
                categoria_id=categoria_a,
                alicuota_id=alicuota_a,
                proveedor_id=None,
                nombre="Cerveza A 12.5",
                codigo="COD-125-A",
            )
            presentacion_a = _crear_presentacion(
                conexion, organizacion_id=org_a, producto_id=producto_a
            )
    finally:
        engine.dispose()

    # --- Paso 2: upgrade head. Org B recibe el provisorio de la migración;
    # se siembra en org A un proveedor real y un costo_informado ---------
    resultado_up_1 = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_1.returncode == 0, resultado_up_1.stderr

    engine = create_engine(database_url)
    try:
        with engine.begin() as conexion:
            usuario_a = _crear_rol_y_usuario(conexion, organizacion_id=org_a)
            proveedor_real_a = _crear_proveedor(
                conexion, organizacion_id=org_a, nombre="Distribuidora Norte 12.5"
            )
            conexion.execute(
                text("UPDATE producto SET proveedor_id = :proveedor WHERE id = :id"),
                {"proveedor": proveedor_real_a, "id": producto_a},
            )
            costo_informado_a = _crear_costo_informado(
                conexion,
                organizacion_id=org_a,
                proveedor_id=proveedor_real_a,
                producto_id=producto_a,
                presentacion_id=presentacion_a,
                usuario_id=usuario_a,
            )
    finally:
        engine.dispose()

    engine = create_engine(database_url)
    try:
        with engine.connect() as conexion:
            proveedor_provisorio_b = conexion.execute(
                text(
                    "SELECT prov.id FROM producto p JOIN proveedor prov "
                    "ON prov.id = p.proveedor_id WHERE p.id = :id"
                ),
                {"id": producto_b},
            ).scalar_one()
            nombre_provisorio_b, activo_provisorio_b = conexion.execute(
                text("SELECT nombre, activo FROM proveedor WHERE id = :id"),
                {"id": proveedor_provisorio_b},
            ).one()
            assert nombre_provisorio_b == NOMBRE_PROVEEDOR_PROVISORIO
            assert activo_provisorio_b is False
    finally:
        engine.dispose()

    # --- Paso 3: downgrade a c1d2e3f4a5b6 (las DOS migraciones juntas) ----
    resultado_down = _alembic("downgrade", REVISION_CATALOGO, database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr

    engine = create_engine(database_url)
    try:
        with engine.connect() as conexion:
            tablas_de_proveedores = (
                conexion.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE tablename IN "
                        "('proveedor', 'costo_informado')"
                    )
                )
                .scalars()
                .all()
            )
            assert tablas_de_proveedores == []

            es_nullable = conexion.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'producto' AND column_name = 'proveedor_id'"
                )
            ).scalar_one()
            assert es_nullable == "YES"

            proveedor_id_a_tras_downgrade = conexion.execute(
                text("SELECT proveedor_id FROM producto WHERE id = :id"), {"id": producto_a}
            ).scalar_one()
            proveedor_id_b_tras_downgrade = conexion.execute(
                text("SELECT proveedor_id FROM producto WHERE id = :id"), {"id": producto_b}
            ).scalar_one()
            assert proveedor_id_a_tras_downgrade is None
            assert proveedor_id_b_tras_downgrade is None

            # organizacion, categoria, alicuota_iva y presentacion siguen
            # existiendo con sus filas intactas (el downgrade de las dos
            # migraciones de este change no las toca).
            organizaciones_intactas = conexion.execute(
                text("SELECT count(*) FROM organizacion WHERE id IN (:a, :b)"),
                {"a": org_a, "b": org_b},
            ).scalar_one()
            assert organizaciones_intactas == 2

            categorias_intactas = conexion.execute(
                text("SELECT count(*) FROM categoria WHERE id IN (:a, :b)"),
                {"a": categoria_a, "b": categoria_b},
            ).scalar_one()
            assert categorias_intactas == 2

            alicuotas_intactas = conexion.execute(
                text("SELECT count(*) FROM alicuota_iva WHERE id IN (:a, :b)"),
                {"a": alicuota_a, "b": alicuota_b},
            ).scalar_one()
            assert alicuotas_intactas == 2

            presentacion_a_intacta = conexion.execute(
                text("SELECT count(*) FROM presentacion WHERE id = :id"),
                {"id": presentacion_a},
            ).scalar_one()
            assert presentacion_a_intacta == 1
    finally:
        engine.dispose()

    # --- Paso 4: upgrade head de nuevo -------------------------------------
    resultado_up_2 = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_2.returncode == 0, resultado_up_2.stderr

    engine = create_engine(database_url)
    try:
        with engine.connect() as conexion:
            tablas_de_proveedores_final = (
                conexion.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE tablename IN "
                        "('proveedor', 'costo_informado')"
                    )
                )
                .scalars()
                .all()
            )
            assert sorted(tablas_de_proveedores_final) == ["costo_informado", "proveedor"]

            # El costo_informado de A NO vuelve: la tabla se recreó vacía.
            costo_viejo_existe = conexion.execute(
                text("SELECT count(*) FROM costo_informado WHERE id = :id"),
                {"id": costo_informado_a},
            ).scalar_one()
            assert costo_viejo_existe == 0

            es_nullable_final = conexion.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'producto' AND column_name = 'proveedor_id'"
                )
            ).scalar_one()
            assert es_nullable_final == "NO"

            proveedor_id_a_final, nombre_a_final, activo_a_final = conexion.execute(
                text(
                    "SELECT prov.id, prov.nombre, prov.activo FROM producto p "
                    "JOIN proveedor prov ON prov.id = p.proveedor_id WHERE p.id = :id"
                ),
                {"id": producto_a},
            ).one()
            # A's producto ya NO tiene su proveedor real viejo: recibió un
            # provisorio NUEVO (distinto id, inactivo, mismo nombre).
            assert proveedor_id_a_final != proveedor_real_a
            assert nombre_a_final == NOMBRE_PROVEEDOR_PROVISORIO
            assert activo_a_final is False

            proveedor_id_b_final, nombre_b_final, activo_b_final = conexion.execute(
                text(
                    "SELECT prov.id, prov.nombre, prov.activo FROM producto p "
                    "JOIN proveedor prov ON prov.id = p.proveedor_id WHERE p.id = :id"
                ),
                {"id": producto_b},
            ).one()
            # B también recibe un provisorio NUEVO, distinto del capturado
            # en el paso 2 (aquella fila de `proveedor` fue borrada por el
            # DROP TABLE del downgrade).
            assert proveedor_id_b_final != proveedor_provisorio_b
            assert nombre_b_final == NOMBRE_PROVEEDOR_PROVISORIO
            assert activo_b_final is False

            # El proveedor real viejo de A tampoco existe más (se borró con
            # el DROP TABLE proveedor del downgrade).
            proveedor_real_a_existe = conexion.execute(
                text("SELECT count(*) FROM proveedor WHERE id = :id"),
                {"id": proveedor_real_a},
            ).scalar_one()
            assert proveedor_real_a_existe == 0
    finally:
        engine.dispose()

    resultado_up_head = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_head.returncode == 0, resultado_up_head.stderr
