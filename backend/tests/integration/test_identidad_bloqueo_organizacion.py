"""Change 20b, tarea 2.2: `bloquear_organizacion_para_identidad` (`design.md` D4, ADR-053).

Toma `configuracion_organizacion FOR UPDATE` (la exclusión mutua de identidad de la organización,
`02` §7.3) y, ya con el bloqueo, revalida que quien ejecuta sigue ACTIVO, con rol activo y con
`ADMIN_USUARIOS`. Si no, `PERMISO_REQUERIDO` (403) sin cambios.

Reglas citadas: ADR-053, ADR-056, SEG-06, INV-01, INV-21.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from roles_utiles import ADMIN, Entorno
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.db import crear_engine, crear_session_factory
from app.core.errors import PermisoRequeridoError
from app.modules.identidad import service as identidad_service


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = crear_engine(database_url)
    try:
        with crear_session_factory(engine)() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


def test_un_administrador_activo_toma_el_bloqueo_y_sigue(sesion: Session) -> None:
    entorno = Entorno(sesion)
    administrador, _ = entorno.crear_usuario(entorno.crear_rol("Administrador", frozenset({ADMIN})))

    identidad_service.bloquear_organizacion_para_identidad(
        entorno.org, sesion, actor_id=administrador
    )


def test_el_bloqueo_impide_que_otra_transaccion_tome_la_configuracion(
    sesion: Session, database_url: str
) -> None:
    """Exclusión mutua real: mientras la transacción A lo tiene, la B no puede bloquear la fila."""
    entorno = Entorno(sesion)
    administrador, _ = entorno.crear_usuario(entorno.crear_rol("Administrador", frozenset({ADMIN})))
    identidad_service.bloquear_organizacion_para_identidad(
        entorno.org, sesion, actor_id=administrador
    )

    engine = crear_engine(database_url)
    try:
        with crear_session_factory(engine)() as otra, pytest.raises(OperationalError):
            otra.execute(
                text(
                    "SELECT 1 FROM configuracion_organizacion "
                    "WHERE organizacion_id = :o FOR UPDATE NOWAIT"
                ),
                {"o": entorno.org},
            )
    finally:
        engine.dispose()
        sesion.rollback()


@pytest.mark.parametrize(
    "caso", ["inactivo", "rol_inactivo", "sin_permiso", "inexistente", "de_otra_organizacion"]
)
def test_quien_ya_no_administra_se_rechaza_con_permiso_requerido(
    sesion: Session, caso: str
) -> None:
    entorno = Entorno(sesion)
    ajena = Entorno(sesion)
    administrador, _ = entorno.crear_usuario(entorno.crear_rol("Administrador", frozenset({ADMIN})))
    if caso == "inactivo":
        actor, _ = entorno.crear_usuario(
            entorno.crear_rol("Gerencia", frozenset({ADMIN})), estado="INACTIVO"
        )
    elif caso == "rol_inactivo":
        actor, _ = entorno.crear_usuario(
            entorno.crear_rol("Vieja", frozenset({ADMIN}), activo=False)
        )
    elif caso == "sin_permiso":
        actor, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", frozenset({"VENDER"})))
    elif caso == "de_otra_organizacion":
        actor, _ = ajena.crear_usuario(ajena.crear_rol("Administrador", frozenset({ADMIN})))
    else:
        actor = administrador.__class__(int=0)

    with pytest.raises(PermisoRequeridoError) as error:
        identidad_service.bloquear_organizacion_para_identidad(entorno.org, sesion, actor_id=actor)

    assert error.value.codigo == "PERMISO_REQUERIDO"
    assert error.value.status_http == 403


def test_la_revalidacion_ve_el_estado_confirmado_aunque_el_usuario_estuviera_en_la_sesion(
    sesion: Session, database_url: str
) -> None:
    """Un administrador dado de baja por otra transacción mientras su objeto seguía cargado en
    esta sesión no pasa la revalidación: lee la base, no la caché de la sesión."""
    entorno = Entorno(sesion)
    entorno.crear_usuario(entorno.crear_rol("Administrador", frozenset({ADMIN})))
    segundo, _ = entorno.crear_usuario(entorno.crear_rol("Gerencia", frozenset({ADMIN})))
    # Carga al usuario en la identidad de la sesión, como hace la dependencia de permisos.
    identidad_service.exigir_sesion_habilitada(entorno.org, segundo, sesion)
    sesion.commit()

    engine = crear_engine(database_url)
    try:
        with engine.begin() as conexion:
            conexion.execute(
                text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :u"), {"u": segundo}
            )
    finally:
        engine.dispose()

    with pytest.raises(PermisoRequeridoError):
        identidad_service.bloquear_organizacion_para_identidad(
            entorno.org, sesion, actor_id=segundo
        )
