"""Verifica que las migraciones aplican y revierten limpio contra
PostgreSQL real (`docs/04-roadmap-changes.md` §2.1, criterio 4).

Este test corre alembic directamente contra la base compartida de la
sesión de pytest (la misma que usan `_engine_de_sesion`/`db_session` en
`conftest.py`), no contra una base propia. Por eso DEBE terminar con la
base en `head`: si terminara en `downgrade base`, cualquier test de
integración que corra después perdería todas las tablas (fallaría con
`relation "organizacion" does not exist` o similar) según el orden de
recolección de pytest.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import (
    _PASSWORD_ROL_MIGRACIONES,
    NOMBRE_ROL_MIGRACIONES,
    _crear_roles_de_base,
    _url_con_credenciales,
)
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    # Alembic lee `DATABASE_URL_MIGRATIONS` (rol `app_migrations`, dueño del
    # esquema), nunca `DATABASE_URL` (tarea 1.5, `app/core/alembic_url.py`).
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


@pytest.mark.usefixtures("database_url")
def test_upgrade_head_y_downgrade_base_corren_limpios(database_url: str) -> None:
    # Esta prueba corre alembic directo (sin pasar por `aplicar_migraciones`),
    # así que crea los dos roles de base (tarea 1.4, INV-05) a mano: las
    # migraciones de este change otorgan permisos a `app_runtime` y fallarían
    # con "el rol no existe" si nadie los creó todavía en esta sesión.
    _crear_roles_de_base(database_url)

    resultado_up = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up.returncode == 0, resultado_up.stderr

    resultado_down = _alembic("downgrade", "base", database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr

    # Repetido: debe seguir corriendo limpio sobre una base ya usada.
    resultado_up_2 = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_2.returncode == 0, resultado_up_2.stderr

    resultado_down_2 = _alembic("downgrade", "base", database_url=database_url)
    assert resultado_down_2.returncode == 0, resultado_down_2.stderr

    # Deja la base en `head`: es compartida con el resto de la sesión de
    # pytest (ver docstring del módulo). Terminar en `base` rompería todos
    # los tests de integración que corran después de este.
    resultado_up_final = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_final.returncode == 0, resultado_up_final.stderr


def _sembrar_datos_representativos(database_url: str) -> None:
    """Una fila por cada una de las siete tablas nuevas de este change (más
    `intento_login`, grupo 11), con relaciones reales entre sí, para que la
    tarea 14.4 ejerza el downgrade/upgrade contra una base CON datos, no
    vacía: un `DROP TABLE` con el orden de FK equivocado en un `downgrade`
    solo se manifiesta si hay filas y restricciones que atravesar, nunca
    contra un esquema vacío."""
    from datetime import UTC, datetime
    from uuid import uuid4

    engine = create_engine(database_url)
    momento = datetime(2026, 1, 1, tzinfo=UTC)
    organizacion_id = uuid4()
    rol_id = uuid4()
    usuario_id = uuid4()
    dispositivo_id = uuid4()
    try:
        with engine.begin() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO organizacion "
                    "(id, nombre, slug, cuit, moneda, zona_horaria, estado, "
                    "creado_en, actualizado_en, actualizado_por_id) "
                    "VALUES (:id, 'Org 14.4', :slug, NULL, 'ARS', "
                    "'America/Argentina/Mendoza', 'ACTIVA', :momento, :momento, NULL)"
                ),
                {"id": organizacion_id, "slug": f"org-144-{organizacion_id}", "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO rol "
                    "(id, organizacion_id, nombre, tope_descuento, activo, creado_en, "
                    "actualizado_en, actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, 'Rol 14.4', 0.100000, true, :momento, "
                    ":momento, NULL)"
                ),
                {"id": rol_id, "organizacion_id": organizacion_id, "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO rol_permiso (organizacion_id, rol_id, permiso_codigo) "
                    "VALUES (:organizacion_id, :rol_id, 'VENDER')"
                ),
                {"organizacion_id": organizacion_id, "rol_id": rol_id},
            )
            conexion.execute(
                text(
                    "INSERT INTO usuario "
                    "(id, organizacion_id, usuario, nombre, email, password_hash, rol_id, "
                    "tope_descuento_override, estado, creado_en, actualizado_en, "
                    "actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, 'usuario144', 'Usuario 14.4', NULL, "
                    "'hash-de-prueba', :rol_id, NULL, 'ACTIVO', :momento, :momento, NULL)"
                ),
                {
                    "id": usuario_id,
                    "organizacion_id": organizacion_id,
                    "rol_id": rol_id,
                    "momento": momento,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO dispositivo "
                    "(id, organizacion_id, nombre, prefijo, ultimo_correlativo, estado, "
                    "revocado_en, revocado_por_id, creado_en, actualizado_en, "
                    "actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, 'Dispositivo 14.4', 'V01', 0, 'ACTIVO', "
                    "NULL, NULL, :momento, :momento, NULL)"
                ),
                {"id": dispositivo_id, "organizacion_id": organizacion_id, "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO sesion_refresh "
                    "(id, organizacion_id, usuario_id, dispositivo_id, token_hash, familia_id, "
                    "emitido_en, expira_en, usado_en, revocado_en, motivo_revocacion) "
                    "VALUES (:id, :organizacion_id, :usuario_id, :dispositivo_id, "
                    "'hash-de-refresh-de-prueba', :familia_id, :momento, :momento, NULL, "
                    "NULL, NULL)"
                ),
                {
                    "id": uuid4(),
                    "organizacion_id": organizacion_id,
                    "usuario_id": usuario_id,
                    "dispositivo_id": dispositivo_id,
                    "familia_id": uuid4(),
                    "momento": momento,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO auditoria "
                    "(id, organizacion_id, usuario_id, dispositivo_id, accion, entidad, "
                    "entidad_id, antes, despues, motivo_id, observacion, autorizador_id, "
                    "operation_id, occurred_at, registered_at, origen) "
                    "VALUES (:id, :organizacion_id, :usuario_id, :dispositivo_id, "
                    "'INICIO_SESION', 'usuario', NULL, NULL, NULL, NULL, NULL, NULL, NULL, "
                    ":momento, :momento, 'SISTEMA')"
                ),
                {
                    "id": uuid4(),
                    "organizacion_id": organizacion_id,
                    "usuario_id": usuario_id,
                    "dispositivo_id": dispositivo_id,
                    "momento": momento,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO intento_login (id, usuario_id, ip, exito, creado_en) "
                    "VALUES (:id, :usuario_id, '127.0.0.1', true, :momento)"
                ),
                {"id": uuid4(), "usuario_id": usuario_id, "momento": momento},
            )

            # --- change 04 (grupo 2): comando, comando_cuarentena,
            # observacion, y un segundo registro de auditoria de origen
            # COMANDO -- la migracion queda ejercitada con datos de AMBOS
            # origenes (tarea 2.7, `04` §2.1 punto 4), no solo el SISTEMA
            # del login de arriba.
            comando_id = uuid4()
            comando_operation_id = uuid4()
            conexion.execute(
                text(
                    "INSERT INTO comando "
                    "(id, organizacion_id, operation_id, tipo, version, modo, usuario_id, "
                    "dispositivo_id, jornada_id, secuencia, huella, app_version, estado, "
                    "resultado, error_codigo, occurred_at, registered_at) "
                    "VALUES (:id, :organizacion_id, :operation_id, 'PRUEBA_14_4', 1, 'ONLINE', "
                    ":usuario_id, :dispositivo_id, NULL, 1, 'huella-de-prueba-14-4', '1.0.0', "
                    "'ACEPTADO', NULL, NULL, :momento, :momento)"
                ),
                {
                    "id": comando_id,
                    "organizacion_id": organizacion_id,
                    "operation_id": comando_operation_id,
                    "usuario_id": usuario_id,
                    "dispositivo_id": dispositivo_id,
                    "momento": momento,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO comando_cuarentena "
                    "(id, organizacion_id, dispositivo_id, usuario_id, operation_id, tipo, "
                    "contenido, motivo, recibido_en, revisado_en, revisado_por_id) "
                    "VALUES (:id, :organizacion_id, :dispositivo_id, :usuario_id, "
                    ":operation_id, 'PRUEBA_CUARENTENA_14_4', '{}'::jsonb, "
                    "'dispositivo revocado (prueba 14.4)', :momento, NULL, NULL)"
                ),
                {
                    "id": uuid4(),
                    "organizacion_id": organizacion_id,
                    "dispositivo_id": dispositivo_id,
                    "usuario_id": usuario_id,
                    "operation_id": uuid4(),
                    "momento": momento,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO observacion "
                    "(id, organizacion_id, comando_id, operacion_tipo, operacion_id, codigo, "
                    "detalle, estado, resuelto_por_id, resuelto_en, comentario) "
                    "VALUES (:id, :organizacion_id, :comando_id, 'VENTA', :operacion_id, "
                    "'STOCK_NEGATIVO', NULL, 'PENDIENTE', NULL, NULL, NULL)"
                ),
                {
                    "id": uuid4(),
                    "organizacion_id": organizacion_id,
                    "comando_id": comando_id,
                    "operacion_id": uuid4(),
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO auditoria "
                    "(id, organizacion_id, usuario_id, dispositivo_id, accion, entidad, "
                    "entidad_id, antes, despues, motivo_id, observacion, autorizador_id, "
                    "operation_id, occurred_at, registered_at, origen) "
                    "VALUES (:id, :organizacion_id, :usuario_id, :dispositivo_id, "
                    "'PRUEBA_COMANDO_14_4', 'comando', NULL, NULL, NULL, NULL, NULL, NULL, "
                    ":operation_id, :momento, :momento, 'COMANDO')"
                ),
                {
                    "id": uuid4(),
                    "organizacion_id": organizacion_id,
                    "usuario_id": usuario_id,
                    "dispositivo_id": dispositivo_id,
                    "operation_id": comando_operation_id,
                    "momento": momento,
                },
            )
    finally:
        engine.dispose()


def test_downgrade_y_upgrade_corren_limpios_con_datos_representativos(
    database_url: str,
) -> None:
    """Tarea 14.4 (`04` §2.1, criterio 4): `upgrade head` -> `downgrade
    base` -> `upgrade head` sobre una base CON datos, no vacía, sembrando
    una fila real en cada una de las siete tablas nuevas de este change
    (más `intento_login`) con sus relaciones entre sí, para que un `DROP
    TABLE`/`DROP CONSTRAINT` en el orden equivocado del `downgrade` no
    pueda esconderse detrás de un esquema sin filas ni FKs que atravesar.
    """
    _crear_roles_de_base(database_url)

    resultado_up = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up.returncode == 0, resultado_up.stderr

    _sembrar_datos_representativos(database_url)

    resultado_down = _alembic("downgrade", "base", database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr

    resultado_up_2 = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_2.returncode == 0, resultado_up_2.stderr

    # El catálogo de permisos (sincronizado por migración, tarea 4.2) volvió
    # a poblarse desde cero tras el downgrade -- la migración de catálogo no
    # depende de un estado previo, corre limpia sobre la base recién creada.
    engine = create_engine(database_url)
    try:
        with engine.connect() as conexion:
            cantidad_permisos = conexion.execute(text("SELECT count(*) FROM permiso")).scalar_one()
            # La organización sembrada antes del downgrade no sobrevive: un
            # downgrade a `base` borra las tablas, y con ellas sus filas.
            # Esto es la pérdida de datos ESPERADA de un downgrade completo,
            # no la "inesperada" que pide descartar la tarea 14.4 (que se
            # refiere a errores o corrupción durante el propio ciclo, no a
            # que un downgrade total dilapide lo que había).
            cantidad_organizaciones = conexion.execute(
                text("SELECT count(*) FROM organizacion")
            ).scalar_one()
    finally:
        engine.dispose()

    assert cantidad_permisos == 39
    assert cantidad_organizaciones == 0

    # Deja la base en `head`, compartida con el resto de la sesión de pytest.
    resultado_up_final = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_final.returncode == 0, resultado_up_final.stderr


def test_downgrade_y_upgrade_de_origen_no_pierde_ni_altera_auditoria_previa_al_bus(
    database_url: str,
) -> None:
    """Tarea 10.4 (change 04, grupo 10), escenario "Los registros de
    auditoría anteriores al bus no se pierden": la migración
    `f6a7b8c9d0e1` agrega `auditoria.origen` (`server_default` `'SISTEMA'`,
    con relleno explícito de las filas existentes) y sus dos restricciones
    de verificación. Se siembra una fila de auditoría con el esquema DE
    ANTES de esta migración (revisión `e5f6a7b8c9d0`, change 03 -- sin
    `origen`, como cualquier `INICIO_SESION` histórico) y se ejerce el
    ciclo `upgrade head` -> `downgrade` a esa revisión anterior (no a
    `base`: acá interesa exclusivamente esta migración, no las de las
    tablas del bus) -> `upgrade head` de nuevo. La fila original sigue
    intacta después de cada paso, y termina con `origen='SISTEMA'` y
    `operation_id=NULL` -- nunca `'COMANDO'`, que exigiría un
    `operation_id` que este registro histórico nunca tuvo."""
    _crear_roles_de_base(database_url)

    resultado_up_previo = _alembic("upgrade", "e5f6a7b8c9d0", database_url=database_url)
    assert resultado_up_previo.returncode == 0, resultado_up_previo.stderr

    from datetime import UTC, datetime
    from uuid import uuid4

    momento = datetime(2026, 1, 1, tzinfo=UTC)
    organizacion_id = uuid4()
    auditoria_id = uuid4()

    engine = create_engine(database_url)
    try:
        with engine.begin() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO organizacion "
                    "(id, nombre, slug, cuit, moneda, zona_horaria, estado, "
                    "creado_en, actualizado_en, actualizado_por_id) "
                    "VALUES (:id, 'Org 10.4', :slug, NULL, 'ARS', "
                    "'America/Argentina/Mendoza', 'ACTIVA', :momento, :momento, NULL)"
                ),
                {"id": organizacion_id, "slug": f"org-104-{organizacion_id}", "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO auditoria "
                    "(id, organizacion_id, usuario_id, dispositivo_id, accion, entidad, "
                    "entidad_id, antes, despues, motivo_id, observacion, autorizador_id, "
                    "operation_id, occurred_at, registered_at) "
                    "VALUES (:id, :organizacion_id, NULL, NULL, 'INICIO_SESION', 'usuario', "
                    "NULL, NULL, NULL, NULL, NULL, NULL, NULL, :momento, :momento)"
                ),
                {"id": auditoria_id, "organizacion_id": organizacion_id, "momento": momento},
            )
    finally:
        engine.dispose()

    def _leer_fila() -> object:
        engine_local = create_engine(database_url)
        try:
            with engine_local.connect() as conexion:
                return conexion.execute(
                    text("SELECT accion, origen, operation_id FROM auditoria WHERE id = :id"),
                    {"id": auditoria_id},
                ).one()
        finally:
            engine_local.dispose()

    resultado_up = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up.returncode == 0, resultado_up.stderr

    fila = _leer_fila()
    assert fila.accion == "INICIO_SESION"
    assert fila.origen == "SISTEMA"
    assert fila.operation_id is None

    resultado_down = _alembic("downgrade", "e5f6a7b8c9d0", database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr

    # Sin la columna `origen` (recién eliminada por el downgrade), la fila
    # sigue existiendo con sus columnas originales intactas.
    engine = create_engine(database_url)
    try:
        with engine.connect() as conexion:
            fila_sin_origen = conexion.execute(
                text("SELECT accion, operation_id FROM auditoria WHERE id = :id"),
                {"id": auditoria_id},
            ).one()
    finally:
        engine.dispose()
    assert fila_sin_origen.accion == "INICIO_SESION"
    assert fila_sin_origen.operation_id is None

    resultado_up_2 = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_2.returncode == 0, resultado_up_2.stderr

    fila_final = _leer_fila()
    assert fila_final.accion == "INICIO_SESION"
    assert fila_final.origen == "SISTEMA"
    assert fila_final.operation_id is None

    # Deja la base en `head` (docstring del módulo: es compartida con el
    # resto de la sesión de pytest).


def test_alembic_corre_como_app_migrations_no_como_app_runtime(database_url: str) -> None:
    """Tarea 1.5: confirma que Alembic efectivamente usó `DATABASE_URL_MIGRATIONS`
    (rol `app_migrations`) para correr, no una URL con otro rol: las tablas
    que crea quedan de su propiedad."""
    _crear_roles_de_base(database_url)
    resultado = _alembic("upgrade", "head", database_url=database_url)
    assert resultado.returncode == 0, resultado.stderr

    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    try:
        with engine.connect() as conexion:
            dueno = conexion.execute(
                text("SELECT tableowner FROM pg_tables WHERE tablename = 'auditoria'")
            ).scalar_one()
    finally:
        engine.dispose()

    assert dueno == NOMBRE_ROL_MIGRACIONES


def _sembrar_datos_de_catalogo(database_url: str) -> None:
    """Change 05, tarea 11.4: una fila por cada una de las cuatro tablas
    nuevas de `c1d2e3f4a5b6` (`categoria`, `marca`, `producto`,
    `presentacion`), con sus relaciones reales entre sí (`producto` FK a
    `categoria`, `marca` y `alicuota_iva`; `presentacion` FK a `producto`),
    para que el `downgrade -1` de esta migración específica (no un
    `downgrade base`) tenga datos y restricciones reales que atravesar al
    hacer `DROP TABLE`/`DROP CONSTRAINT` en el orden correcto."""
    from datetime import UTC, datetime
    from uuid import uuid4

    engine = create_engine(database_url)
    momento = datetime(2026, 1, 1, tzinfo=UTC)
    organizacion_id = uuid4()
    categoria_id = uuid4()
    marca_id = uuid4()
    alicuota_id = uuid4()
    producto_id = uuid4()
    try:
        with engine.begin() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO organizacion "
                    "(id, nombre, slug, cuit, moneda, zona_horaria, estado, "
                    "creado_en, actualizado_en, actualizado_por_id) "
                    "VALUES (:id, 'Org 11.4', :slug, NULL, 'ARS', "
                    "'America/Argentina/Mendoza', 'ACTIVA', :momento, :momento, NULL)"
                ),
                {"id": organizacion_id, "slug": f"org-114-{organizacion_id}", "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO categoria "
                    "(id, organizacion_id, nombre, activo, creado_en, actualizado_en, "
                    "actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, 'Categoria 11.4', true, :momento, :momento, "
                    "NULL)"
                ),
                {"id": categoria_id, "organizacion_id": organizacion_id, "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO marca "
                    "(id, organizacion_id, nombre, activo, creado_en, actualizado_en, "
                    "actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, 'Marca 11.4', true, :momento, :momento, NULL)"
                ),
                {"id": marca_id, "organizacion_id": organizacion_id, "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO alicuota_iva "
                    "(id, organizacion_id, nombre, valor, activo, creado_en, actualizado_en) "
                    "VALUES (:id, :organizacion_id, 'Alicuota 11.4', 0.210000, true, :momento, "
                    ":momento)"
                ),
                {"id": alicuota_id, "organizacion_id": organizacion_id, "momento": momento},
            )
            conexion.execute(
                text(
                    "INSERT INTO producto "
                    "(id, organizacion_id, codigo, nombre, categoria_id, marca_id, "
                    "proveedor_id, unidad_base, alicuota_id, activo, creado_en, "
                    "actualizado_en, actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, 'VA-114', 'Vino 11.4', :categoria_id, "
                    ":marca_id, NULL, 'botella', :alicuota_id, true, :momento, :momento, NULL)"
                ),
                {
                    "id": producto_id,
                    "organizacion_id": organizacion_id,
                    "categoria_id": categoria_id,
                    "marca_id": marca_id,
                    "alicuota_id": alicuota_id,
                    "momento": momento,
                },
            )
            conexion.execute(
                text(
                    "INSERT INTO presentacion "
                    "(id, organizacion_id, producto_id, nombre, unidades_base, "
                    "usar_en_venta, usar_en_compra, es_referencia, activo, creado_en, "
                    "actualizado_en, actualizado_por_id) "
                    "VALUES (:id, :organizacion_id, :producto_id, 'Botella', 1, true, true, "
                    "true, true, :momento, :momento, NULL)"
                ),
                {
                    "id": uuid4(),
                    "organizacion_id": organizacion_id,
                    "producto_id": producto_id,
                    "momento": momento,
                },
            )
    finally:
        engine.dispose()


def test_downgrade_menos_uno_y_upgrade_corren_limpios_con_datos_de_catalogo_sembrados(
    database_url: str,
) -> None:
    """Tarea 11.4 (`04` §2.1, criterio 4, change 05): `upgrade head` ->
    `downgrade -1` -> `upgrade head` sobre la migración de catálogo
    (`c1d2e3f4a5b6`) CON datos sembrados en sus cuatro tablas nuevas
    (`categoria`, `marca`, `producto`, `presentacion`), no vacías -- a
    diferencia de `test_downgrade_y_upgrade_corren_limpios_con_datos_
    representativos` (tarea 14.4 del change 04, `downgrade base` completo),
    acá el `downgrade -1` revierte EXCLUSIVAMENTE esta migración: las
    tablas de `organizacion`/`identidad`/`sync` de los changes anteriores
    quedan intactas, así que la prueba también confirma que no se
    perdieron ni se alteraron (`organizacion` sigue existiendo con su
    fila)."""
    _crear_roles_de_base(database_url)

    resultado_up = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up.returncode == 0, resultado_up.stderr

    _sembrar_datos_de_catalogo(database_url)

    engine_previo = create_engine(database_url)
    try:
        with engine_previo.connect() as conexion:
            organizacion_id_previa = conexion.execute(
                text("SELECT id FROM organizacion WHERE nombre = 'Org 11.4'")
            ).scalar_one()
    finally:
        engine_previo.dispose()

    resultado_down = _alembic("downgrade", "-1", database_url=database_url)
    assert resultado_down.returncode == 0, resultado_down.stderr

    # Las cuatro tablas de catálogo ya no existen tras el downgrade de ESTA
    # migración -- confirma que el `downgrade -1` efectivamente revirtió
    # `c1d2e3f4a5b6`, no otra cosa.
    engine_sin_catalogo = create_engine(database_url)
    try:
        with engine_sin_catalogo.connect() as conexion:
            tablas_de_catalogo = (
                conexion.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE tablename IN "
                        "('categoria', 'marca', 'producto', 'presentacion')"
                    )
                )
                .scalars()
                .all()
            )
    finally:
        engine_sin_catalogo.dispose()
    assert tablas_de_catalogo == []

    # La organización sembrada ANTES del downgrade sigue existiendo: el
    # `downgrade -1` de catálogo no tocó tablas de changes anteriores.
    engine_intacto = create_engine(database_url)
    try:
        with engine_intacto.connect() as conexion:
            organizacion_sigue_existiendo = conexion.execute(
                text("SELECT count(*) FROM organizacion WHERE id = :id"),
                {"id": organizacion_id_previa},
            ).scalar_one()
    finally:
        engine_intacto.dispose()
    assert organizacion_sigue_existiendo == 1

    resultado_up_2 = _alembic("upgrade", "head", database_url=database_url)
    assert resultado_up_2.returncode == 0, resultado_up_2.stderr

    # Tras el segundo `upgrade head`, las cuatro tablas de catálogo vuelven
    # a existir, vacías (la migración no reinserta datos de un downgrade
    # parcial -- eso es la pérdida ESPERADA de las filas de catálogo que
    # dependían de las tablas borradas, no la "inesperada" que la tarea
    # 11.4 pide descartar).
    engine_final = create_engine(database_url)
    try:
        with engine_final.connect() as conexion:
            cantidad_categorias = conexion.execute(
                text("SELECT count(*) FROM categoria")
            ).scalar_one()
            cantidad_productos = conexion.execute(
                text("SELECT count(*) FROM producto")
            ).scalar_one()
    finally:
        engine_final.dispose()
    assert cantidad_categorias == 0
    assert cantidad_productos == 0

    # Deja la base en `head`, compartida con el resto de la sesión de
    # pytest (docstring del módulo).
