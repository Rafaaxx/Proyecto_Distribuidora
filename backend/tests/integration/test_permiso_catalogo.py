"""Catálogo global de permisos (`01` §19, `03` §4, `03` §17). Tareas 4.1-4.3.

El catálogo se sincroniza por migración, idempotente (`ON CONFLICT DO
NOTHING`): es dato atado al código, no a una organización (D7).
"""

from __future__ import annotations

from conftest import aplicar_migraciones
from sqlalchemy import Engine, text

from app.modules.identidad.domain.permisos import PERMISOS_DEL_CATALOGO


def _contar_permisos(engine: Engine) -> int:
    with engine.connect() as conexion:
        return conexion.execute(text("SELECT count(*) FROM permiso")).scalar_one()


def _codigos_en_catalogo(engine: Engine) -> set[str]:
    with engine.connect() as conexion:
        return {fila[0] for fila in conexion.execute(text("SELECT codigo FROM permiso")).all()}


def _insertar_catalogo(engine: Engine) -> None:
    """Misma sentencia que la migración `b2c3d4e5f6a7`: se re-ejecuta acá
    para probar su idempotencia sin depender de que Alembic vuelva a
    aplicar una revisión ya migrada (`alembic upgrade head` repetido es un
    no-op de Alembic, no ejercita el SQL de nuevo)."""
    with engine.begin() as conexion:
        for permiso in PERMISOS_DEL_CATALOGO:
            conexion.execute(
                text(
                    "INSERT INTO permiso (codigo, descripcion, modulo) "
                    "VALUES (:codigo, :descripcion, :modulo) "
                    "ON CONFLICT (codigo) DO NOTHING"
                ),
                {
                    "codigo": permiso.codigo,
                    "descripcion": permiso.descripcion,
                    "modulo": permiso.modulo,
                },
            )


def test_el_catalogo_contiene_los_40_permisos_de_la_documentacion(
    database_url: str, _engine_de_sesion: Engine
) -> None:
    """Escenario "El catálogo contiene los permisos de la documentación"."""
    aplicar_migraciones(database_url)
    codigos = _codigos_en_catalogo(_engine_de_sesion)

    assert len(PERMISOS_DEL_CATALOGO) == 40
    assert codigos == {permiso.codigo for permiso in PERMISOS_DEL_CATALOGO}
    for codigo in (
        "ADMIN_USUARIOS",
        "GESTIONAR_DISPOSITIVOS",
        "VENDER",
        "VER_COSTOS",
        "AUTORIZAR_DESCUENTO",
        "VER_AUDITORIA",
        "ANULAR_TRANSFERENCIA",
    ):
        assert codigo in codigos


def test_ningun_permiso_del_catalogo_tiene_organizacion(_engine_de_sesion: Engine) -> None:
    with _engine_de_sesion.connect() as conexion:
        columnas = {
            fila[0]
            for fila in conexion.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'permiso'"
                )
            ).all()
        }
    assert "organizacion_id" not in columnas


def test_sincronizar_el_catalogo_dos_veces_no_lo_duplica(_engine_de_sesion: Engine) -> None:
    """Escenario "Sincronizar el catálogo dos veces no lo duplica"."""
    antes = _contar_permisos(_engine_de_sesion)
    assert antes == 40

    _insertar_catalogo(_engine_de_sesion)
    _insertar_catalogo(_engine_de_sesion)

    assert _contar_permisos(_engine_de_sesion) == 40
    assert _codigos_en_catalogo(_engine_de_sesion) == {p.codigo for p in PERMISOS_DEL_CATALOGO}


def test_una_organizacion_no_puede_crear_ni_borrar_permisos_del_catalogo(
    database_url: str,
) -> None:
    """Escenario "Una organización no puede crear ni borrar permisos": el
    catálogo global de `permiso` se sincroniza únicamente por migración
    (`03` §17, D7) -- la aplicación no expone, para ningún rol, una ruta
    que agregue o quite un código del catálogo. Se verifica recorriendo
    dinámicamente las rutas registradas (mismo mecanismo que el ratchet de
    permiso por ruta de la tarea 10.3), no confiando en que "no vimos
    ninguna" al leer el código a mano."""
    from app.core.config import Settings
    from app.main import crear_app

    app = crear_app(
        Settings(
            _env_file=None,
            database_url=database_url,
            jwt_secret="secreto-de-prueba",
            jwt_kid="1",
        )
    )

    metodos_de_escritura = {"POST", "PUT", "PATCH", "DELETE"}
    rutas_de_escritura_sobre_el_catalogo = [
        (ruta.path, metodo)
        for ruta in app.routes
        if hasattr(ruta, "path") and "permiso" in ruta.path.lower()
        for metodo in getattr(ruta, "methods", set()) or set()
        if metodo in metodos_de_escritura
    ]

    assert rutas_de_escritura_sobre_el_catalogo == []
