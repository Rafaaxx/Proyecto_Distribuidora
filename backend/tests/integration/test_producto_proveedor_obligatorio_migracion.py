"""Change 06, grupo 4 (`design.md` Migration Plan punto 2, D2; SQL exacto
aprobado en `tasks.md` 4.1): la migración `producto_proveedor_obligatorio`
completa `producto.proveedor_id` en las organizaciones con productos
huérfanos (creando un proveedor provisorio inactivo por organización y
asignándolo) y recién ahí agrega `NOT NULL` (CAT-01/CAT-06).

Corre alembic directo (subproceso) contra la base compartida de la sesión
de pytest, igual que `test_proveedores_migracion.py::test_downgrade_de_...`
y `test_alembic_integracion.py`: hace falta controlar el estado ANTES de
esta revisión (productos huérfanos sembrados a mano) y verificar el
resultado exacto de cada paso del ciclo, algo que `db_session` (que ya
corre en `head`) no permite. Usa ids de revisión explícitos, nunca
`downgrade -1` (lección de la tarea 3.6: `-1` es relativo al head y deja de
apuntar a esta migración en cuanto se agregue una revisión encima).

Cada prueba repone `head` en un `finally`, pase o falle: la base es
compartida con el resto de la sesión de pytest.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import _PASSWORD_ROL_MIGRACIONES, NOMBRE_ROL_MIGRACIONES, _url_con_credenciales
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

REVISION_ANTERIOR = "70dcb6dce507"
REVISION_MIGRACION = "8b9c0d1e2f3a"

MOMENTO = datetime(2026, 9, 24, tzinfo=UTC)

NOMBRE_PROVEEDOR_PROVISORIO = "Proveedor a asignar"


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    """Corre `alembic` en un subproceso, igual que
    `test_proveedores_migracion.py`/`test_alembic_integracion.py`: Alembic
    lee `DATABASE_URL_MIGRATIONS` (rol `app_migrations`), nunca
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


def _crear_producto(
    conexion,
    *,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID | None,
    nombre: str = "Cerveza B",
    codigo: str | None = None,
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
            "codigo": codigo or f"COD-{uuid.uuid4().hex[:8]}",
            "nombre": nombre,
            "categoria_id": categoria_id,
            "proveedor_id": proveedor_id,
            "alicuota_id": alicuota_id,
            "momento": MOMENTO,
        },
    )
    return producto_id


@pytest.fixture
def _en_revision_anterior(database_url: str):
    """Deja la base en `70dcb6dce507` (antes de esta migración) para que la
    prueba siembre datos previos, y repone `head` al terminar."""
    resultado_down = _alembic("downgrade", REVISION_ANTERIOR, database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr
    try:
        yield
    finally:
        resultado_up = _alembic("upgrade", "head", database_url=database_url)
        assert resultado_up.returncode == 0, resultado_up.stderr


# --- Tarea 4.2: RED/GREEN de la migración -----------------------------------


def test_producto_proveedor_obligatorio_asigna_provisorio_por_organizacion_huerfana(
    database_url: str, _en_revision_anterior: None
) -> None:
    """Con productos sin proveedor sembrados en dos organizaciones antes de
    la revisión, al subir cada producto queda con un proveedor de SU
    organización, inactivo, y ningún otro dato del producto cambia; una
    organización sin productos huérfanos no recibe provisorio."""
    engine = create_engine(database_url)
    try:
        with engine.begin() as conexion:
            org_a = _crear_organizacion(conexion, nombre="Org A huérfana")
            categoria_a = _crear_categoria(conexion, organizacion_id=org_a)
            alicuota_a = _crear_alicuota(conexion, organizacion_id=org_a)
            producto_a = _crear_producto(
                conexion,
                organizacion_id=org_a,
                categoria_id=categoria_a,
                alicuota_id=alicuota_a,
                proveedor_id=None,
                nombre="Cerveza A",
                codigo="COD-A",
            )

            org_b = _crear_organizacion(conexion, nombre="Org B huérfana")
            categoria_b = _crear_categoria(conexion, organizacion_id=org_b)
            alicuota_b = _crear_alicuota(conexion, organizacion_id=org_b)
            producto_b = _crear_producto(
                conexion,
                organizacion_id=org_b,
                categoria_id=categoria_b,
                alicuota_id=alicuota_b,
                proveedor_id=None,
                nombre="Vino B",
                codigo="COD-B",
            )

            # Organización sin productos huérfanos: no debe recibir provisorio.
            org_c = _crear_organizacion(conexion, nombre="Org C sin huérfanos")
            categoria_c = _crear_categoria(conexion, organizacion_id=org_c)
            alicuota_c = _crear_alicuota(conexion, organizacion_id=org_c)
            proveedor_real_c = _crear_proveedor(
                conexion, organizacion_id=org_c, nombre="Distribuidora Norte"
            )
            producto_c = _crear_producto(
                conexion,
                organizacion_id=org_c,
                categoria_id=categoria_c,
                alicuota_id=alicuota_c,
                proveedor_id=proveedor_real_c,
                nombre="Fernet C",
                codigo="COD-C",
            )
    finally:
        engine.dispose()

    resultado_up = _alembic("upgrade", REVISION_MIGRACION, database_url=database_url)
    assert resultado_up.returncode == 0, resultado_up.stderr

    engine_post = create_engine(database_url)
    try:
        with engine_post.connect() as conexion:
            fila_a = conexion.execute(
                text(
                    "SELECT p.proveedor_id, p.nombre, p.codigo, prov.nombre, prov.activo, "
                    "prov.organizacion_id FROM producto p JOIN proveedor prov "
                    "ON prov.id = p.proveedor_id WHERE p.id = :id"
                ),
                {"id": producto_a},
            ).one()
            assert fila_a[1] == "Cerveza A"
            assert fila_a[2] == "COD-A"
            assert fila_a[3] == NOMBRE_PROVEEDOR_PROVISORIO
            assert fila_a[4] is False
            assert fila_a[5] == org_a

            fila_b = conexion.execute(
                text(
                    "SELECT p.proveedor_id, p.nombre, p.codigo, prov.nombre, prov.activo, "
                    "prov.organizacion_id FROM producto p JOIN proveedor prov "
                    "ON prov.id = p.proveedor_id WHERE p.id = :id"
                ),
                {"id": producto_b},
            ).one()
            assert fila_b[1] == "Vino B"
            assert fila_b[2] == "COD-B"
            assert fila_b[3] == NOMBRE_PROVEEDOR_PROVISORIO
            assert fila_b[4] is False
            assert fila_b[5] == org_b

            # Cada organización recibe SU PROPIO provisorio (distinto id).
            assert fila_a[0] != fila_b[0]

            # Org C: sin huérfanos, no recibe provisorio; su producto y
            # proveedor real quedan intactos.
            cantidad_provisorios_c = conexion.execute(
                text(
                    "SELECT count(*) FROM proveedor WHERE organizacion_id = :org "
                    "AND nombre = :nombre"
                ),
                {"org": org_c, "nombre": NOMBRE_PROVEEDOR_PROVISORIO},
            ).scalar_one()
            assert cantidad_provisorios_c == 0

            fila_c = conexion.execute(
                text("SELECT proveedor_id FROM producto WHERE id = :id"), {"id": producto_c}
            ).scalar_one()
            assert fila_c == proveedor_real_c
    finally:
        engine_post.dispose()

    # Vuelve a `head` (queda hecho por el fixture, pero se re-sube acá para
    # dejar la revisión más allá de `REVISION_MIGRACION` antes de que el
    # fixture intente `upgrade head` sobre una base ya en esa revisión).
    resultado_up_head = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_head.returncode == 0, resultado_up_head.stderr


def test_producto_proveedor_obligatorio_es_idempotente(
    database_url: str, _en_revision_anterior: None
) -> None:
    """Reejecutar la migración (upgrade a la revisión anterior y volver a
    subir) no crea un segundo provisorio ni encuentra huérfanos: el primer
    `upgrade` ya los completó."""
    engine = create_engine(database_url)
    organizacion_id: uuid.UUID
    try:
        with engine.begin() as conexion:
            organizacion_id = _crear_organizacion(conexion, nombre="Org idempotente")
            categoria_id = _crear_categoria(conexion, organizacion_id=organizacion_id)
            alicuota_id = _crear_alicuota(conexion, organizacion_id=organizacion_id)
            _crear_producto(
                conexion,
                organizacion_id=organizacion_id,
                categoria_id=categoria_id,
                alicuota_id=alicuota_id,
                proveedor_id=None,
            )
    finally:
        engine.dispose()

    resultado_up = _alembic("upgrade", REVISION_MIGRACION, database_url=database_url)
    assert resultado_up.returncode == 0, resultado_up.stderr

    # Downgrade solo hace DROP NOT NULL (tarea 4.4): permite re-ejercer el
    # `upgrade` sin recrear la tabla. El provisorio ya asignado no vuelve a
    # ser huérfano, así que una segunda ejecución no debe insertar otro.
    resultado_down = _alembic("downgrade", REVISION_ANTERIOR, database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr
    resultado_up_2 = _alembic("upgrade", REVISION_MIGRACION, database_url=database_url)
    assert resultado_up_2.returncode == 0, resultado_up_2.stderr

    engine_post = create_engine(database_url)
    try:
        with engine_post.connect() as conexion:
            cantidad_provisorios = conexion.execute(
                text(
                    "SELECT count(*) FROM proveedor WHERE organizacion_id = :org "
                    "AND nombre = :nombre"
                ),
                {"org": organizacion_id, "nombre": NOMBRE_PROVEEDOR_PROVISORIO},
            ).scalar_one()
            assert cantidad_provisorios == 1
    finally:
        engine_post.dispose()

    resultado_up_head = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_head.returncode == 0, resultado_up_head.stderr


def test_producto_proveedor_obligatorio_falla_entera_si_ya_existe_el_nombre(
    database_url: str, _en_revision_anterior: None
) -> None:
    """Si la organización ya tiene un proveedor llamado exactamente
    "Proveedor a asignar", `ux_proveedor__nombre` rechaza la inserción y la
    migración falla entera, sin dejar estado parcial (D2: no se reutiliza el
    existente ni se deja `SET NOT NULL` aplicado a medias)."""
    engine = create_engine(database_url)
    organizacion_id: uuid.UUID
    try:
        with engine.begin() as conexion:
            organizacion_id = _crear_organizacion(conexion, nombre="Org con nombre chocado")
            categoria_id = _crear_categoria(conexion, organizacion_id=organizacion_id)
            alicuota_id = _crear_alicuota(conexion, organizacion_id=organizacion_id)
            _crear_proveedor(
                conexion,
                organizacion_id=organizacion_id,
                nombre=NOMBRE_PROVEEDOR_PROVISORIO,
                activo=True,
            )
            _crear_producto(
                conexion,
                organizacion_id=organizacion_id,
                categoria_id=categoria_id,
                alicuota_id=alicuota_id,
                proveedor_id=None,
            )
    finally:
        engine.dispose()

    try:
        resultado_up = _alembic("upgrade", REVISION_MIGRACION, database_url=database_url)
        assert resultado_up.returncode != 0
        assert "ux_proveedor__nombre" in resultado_up.stderr

        # Sin estado parcial: la revisión de alembic sigue en la anterior
        # (la migración corre en una única transacción, revertida entera al
        # fallar: el `INSERT` de proveedor NO quedó aplicado).
        engine_post = create_engine(database_url)
        try:
            with engine_post.connect() as conexion:
                es_nullable = conexion.execute(
                    text(
                        "SELECT is_nullable FROM information_schema.columns "
                        "WHERE table_name = 'producto' AND column_name = 'proveedor_id'"
                    )
                ).scalar_one()
                cantidad_proveedores_del_nombre = conexion.execute(
                    text(
                        "SELECT count(*) FROM proveedor WHERE organizacion_id = :org "
                        "AND nombre = :nombre"
                    ),
                    {"org": organizacion_id, "nombre": NOMBRE_PROVEEDOR_PROVISORIO},
                ).scalar_one()
        finally:
            engine_post.dispose()
        assert es_nullable == "YES"
        # Sigue habiendo exactamente UNO (el sembrado por la prueba): el
        # intento de INSERT de la migración no dejó una segunda fila.
        assert cantidad_proveedores_del_nombre == 1
    finally:
        # Limpieza defensiva ANTES de reponer `head`: el producto sembrado
        # sigue huérfano (la migración fallida no llegó a asignarlo), así
        # que un `upgrade head` posterior volvería a chocar con el mismo
        # nombre si no se borra el dato de la prueba primero -- igual que la
        # limpieza de `test_downgrade_de_70dcb6dce507_...` en
        # `test_proveedores_migracion.py`.
        engine_limpieza = create_engine(database_url)
        try:
            with engine_limpieza.begin() as conexion:
                conexion.execute(
                    text("DELETE FROM producto WHERE organizacion_id = :org"),
                    {"org": organizacion_id},
                )
                conexion.execute(
                    text("DELETE FROM proveedor WHERE organizacion_id = :org"),
                    {"org": organizacion_id},
                )
        except Exception:  # noqa: BLE001 (limpieza best-effort)
            pass
        finally:
            engine_limpieza.dispose()

        resultado_up_head = _alembic("upgrade", "head", database_url=database_url)
        assert resultado_up_head.returncode == 0, resultado_up_head.stderr


# --- Tarea 4.3: NOT NULL rechazado por la base ------------------------------


def test_cat06_producto_sin_proveedor_rechazado_por_la_base(
    db_session, organizacion_id_cat06, categoria_id_cat06, alicuota_id_cat06
) -> None:
    """CAT-06: en `head`, `producto.proveedor_id` es `NOT NULL`: un intento
    de insertar un producto sin proveedor es rechazado por la base."""
    savepoint = db_session.begin_nested()
    with pytest.raises(IntegrityError, match="null value in column .proveedor_id."):
        db_session.execute(
            text(
                "INSERT INTO producto (id, organizacion_id, codigo, nombre, "
                "categoria_id, marca_id, proveedor_id, unidad_base, alicuota_id, "
                "activo, creado_en, actualizado_en) VALUES (:id, :organizacion_id, "
                ":codigo, 'Sin proveedor', :categoria_id, NULL, NULL, 'botella', "
                ":alicuota_id, true, :momento, :momento)"
            ),
            {
                "id": uuid.uuid4(),
                "organizacion_id": organizacion_id_cat06,
                "codigo": f"COD-{uuid.uuid4().hex[:8]}",
                "categoria_id": categoria_id_cat06,
                "alicuota_id": alicuota_id_cat06,
                "momento": MOMENTO,
            },
        )
    savepoint.rollback()


@pytest.fixture
def organizacion_id_cat06(db_session) -> uuid.UUID:
    organizacion_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO organizacion (id, nombre, slug, cuit, moneda, zona_horaria, "
            "estado, creado_en, actualizado_en) VALUES (:id, 'Org CAT-06', :slug, "
            "NULL, 'ARS', 'America/Argentina/Buenos_Aires', 'ACTIVA', :momento, "
            ":momento)"
        ),
        {"id": organizacion_id, "slug": f"org-{uuid.uuid4().hex[:8]}", "momento": MOMENTO},
    )
    db_session.flush()
    return organizacion_id


@pytest.fixture
def categoria_id_cat06(db_session, organizacion_id_cat06: uuid.UUID) -> uuid.UUID:
    categoria_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO categoria (id, organizacion_id, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :organizacion_id, :nombre, true, :momento, "
            ":momento)"
        ),
        {
            "id": categoria_id,
            "organizacion_id": organizacion_id_cat06,
            "nombre": f"Categoria-{uuid.uuid4().hex[:8]}",
            "momento": MOMENTO,
        },
    )
    db_session.flush()
    return categoria_id


@pytest.fixture
def alicuota_id_cat06(db_session, organizacion_id_cat06: uuid.UUID) -> uuid.UUID:
    alicuota_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO alicuota_iva (id, organizacion_id, nombre, valor, activo, "
            "creado_en, actualizado_en) VALUES (:id, :organizacion_id, '21%', "
            "0.210000, true, :momento, :momento)"
        ),
        {"id": alicuota_id, "organizacion_id": organizacion_id_cat06, "momento": MOMENTO},
    )
    db_session.flush()
    return alicuota_id


# --- Tarea 4.4: downgrade solo DROP NOT NULL --------------------------------


def test_downgrade_conserva_proveedor_provisorio_asignado_solo_dropea_not_null(
    database_url: str, _en_revision_anterior: None
) -> None:
    """El `downgrade` de `producto_proveedor_obligatorio` hace ÚNICAMENTE
    `DROP NOT NULL`: los productos migrados CONSERVAN el proveedor
    provisorio asignado (no vuelven a `NULL`) y el provisorio NO se borra;
    productos con proveedor real lo conservan igual. Un `upgrade` posterior
    vuelve a ser idempotente en resultado (mismo estado que si nunca se
    hubiera bajado)."""
    engine = create_engine(database_url)
    org_huerfana: uuid.UUID
    org_con_real: uuid.UUID
    try:
        with engine.begin() as conexion:
            org_huerfana = _crear_organizacion(conexion, nombre="Org downgrade huérfana")
            categoria_h = _crear_categoria(conexion, organizacion_id=org_huerfana)
            alicuota_h = _crear_alicuota(conexion, organizacion_id=org_huerfana)
            producto_huerfano = _crear_producto(
                conexion,
                organizacion_id=org_huerfana,
                categoria_id=categoria_h,
                alicuota_id=alicuota_h,
                proveedor_id=None,
            )

            org_con_real = _crear_organizacion(conexion, nombre="Org downgrade con real")
            categoria_r = _crear_categoria(conexion, organizacion_id=org_con_real)
            alicuota_r = _crear_alicuota(conexion, organizacion_id=org_con_real)
            proveedor_real = _crear_proveedor(
                conexion, organizacion_id=org_con_real, nombre="Distribuidora Real"
            )
            producto_con_real = _crear_producto(
                conexion,
                organizacion_id=org_con_real,
                categoria_id=categoria_r,
                alicuota_id=alicuota_r,
                proveedor_id=proveedor_real,
            )
    finally:
        engine.dispose()

    resultado_up = _alembic("upgrade", REVISION_MIGRACION, database_url=database_url)
    assert resultado_up.returncode == 0, resultado_up.stderr

    engine_mid = create_engine(database_url)
    try:
        with engine_mid.connect() as conexion:
            proveedor_provisorio_id = conexion.execute(
                text("SELECT proveedor_id FROM producto WHERE id = :id"),
                {"id": producto_huerfano},
            ).scalar_one()
            assert proveedor_provisorio_id is not None
    finally:
        engine_mid.dispose()

    resultado_down = _alembic("downgrade", REVISION_ANTERIOR, database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr

    engine_post_down = create_engine(database_url)
    try:
        with engine_post_down.connect() as conexion:
            es_nullable = conexion.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'producto' AND column_name = 'proveedor_id'"
                )
            ).scalar_one()
            assert es_nullable == "YES"

            # El producto huérfano CONSERVA el proveedor provisorio (no
            # vuelve a NULL).
            proveedor_tras_downgrade = conexion.execute(
                text("SELECT proveedor_id FROM producto WHERE id = :id"),
                {"id": producto_huerfano},
            ).scalar_one()
            assert proveedor_tras_downgrade == proveedor_provisorio_id

            # El provisorio sigue existiendo (no se borra).
            provisorio_existe = conexion.execute(
                text("SELECT count(*) FROM proveedor WHERE id = :id"),
                {"id": proveedor_provisorio_id},
            ).scalar_one()
            assert provisorio_existe == 1

            # El producto con proveedor real lo conserva igual.
            proveedor_real_tras_downgrade = conexion.execute(
                text("SELECT proveedor_id FROM producto WHERE id = :id"),
                {"id": producto_con_real},
            ).scalar_one()
            assert proveedor_real_tras_downgrade == proveedor_real
    finally:
        engine_post_down.dispose()

    # Re-subir: idéntico resultado, ningún huérfano nuevo (el provisorio ya
    # asignado sigue cubriendo al producto huérfano).
    resultado_up_2 = _alembic("upgrade", REVISION_MIGRACION, database_url=database_url)
    assert resultado_up_2.returncode == 0, resultado_up_2.stderr

    engine_final = create_engine(database_url)
    try:
        with engine_final.connect() as conexion:
            cantidad_provisorios = conexion.execute(
                text(
                    "SELECT count(*) FROM proveedor WHERE organizacion_id = :org "
                    "AND nombre = :nombre"
                ),
                {"org": org_huerfana, "nombre": NOMBRE_PROVEEDOR_PROVISORIO},
            ).scalar_one()
            assert cantidad_provisorios == 1

            es_nullable_final = conexion.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'producto' AND column_name = 'proveedor_id'"
                )
            ).scalar_one()
            assert es_nullable_final == "NO"
    finally:
        engine_final.dispose()

    resultado_up_head = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_head.returncode == 0, resultado_up_head.stderr
