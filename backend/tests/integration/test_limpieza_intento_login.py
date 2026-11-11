"""Change 28, tarea 2.2: la limpieza borra los `intento_login` de más de 24 horas con el rol
`app_mantenimiento`, sin levantar un bloqueo vigente ni tocar la auditoría (`design.md` D3, D7).

Los datos se confirman de verdad (la conexión de mantenimiento es otra) y se vacían al terminar.

Reglas citadas: INV-05, ADR-018, ADR-057, AUD-01, AUD-03.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from test_identidad_rate_limit_login_service import (
    PASSWORD,
    _crear_organizacion,
    _crear_usuario,
    _login,
)

from app.core.clock import FixedClock
from app.core.db import crear_session_factory
from app.modules.identidad.domain.usuarios import (
    CredencialesInvalidasError,
    LoginBloqueadoPorIntentosError,
)
from app.tareas import limpieza

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

AHORA = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)


@pytest.fixture
def sesion_real(_engine_de_sesion: Engine) -> Iterator[Session]:
    with crear_session_factory(_engine_de_sesion)() as sesion:
        yield sesion
        sesion.rollback()


@pytest.fixture(autouse=True)
def _vaciar_al_terminar(_engine_de_sesion: Engine) -> Iterator[None]:
    yield
    with _engine_de_sesion.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE intento_login, organizacion CASCADE"))


def _insertar(motor: Engine, *, hace: timedelta, exito: bool = False, ip: str = "10.9.9.9") -> None:
    with motor.begin() as conexion:
        conexion.execute(
            text(
                "INSERT INTO intento_login (id, usuario_id, clave_intento, ip, exito, creado_en) "
                "VALUES (:id, NULL, :clave, :ip, :exito, :creado)"
            ),
            {
                "id": uuid4(),
                "clave": "a" * 64,
                "ip": ip,
                "exito": exito,
                "creado": AHORA - hace,
            },
        )


def _cantidad(motor: Engine) -> int:
    with motor.connect() as conexion:
        return int(conexion.execute(text("SELECT count(*) FROM intento_login")).scalar_one())


def _limpiar(app_mantenimiento_engine: Engine, ahora: datetime = AHORA) -> int:
    return limpieza.limpiar_intentos_de_login(
        crear_session_factory(app_mantenimiento_engine), FixedClock(ahora)
    )


def test_adr018_se_borran_las_filas_de_25_horas_y_quedan_las_de_10_minutos(
    sesion_real: Session, _engine_de_sesion: Engine, app_mantenimiento_engine: Engine
) -> None:
    _insertar(_engine_de_sesion, hace=timedelta(hours=25))
    _insertar(_engine_de_sesion, hace=timedelta(hours=25), exito=True)
    _insertar(_engine_de_sesion, hace=timedelta(minutes=10))

    borradas = _limpiar(app_mantenimiento_engine)

    assert borradas == 2
    with _engine_de_sesion.connect() as conexion:
        (restante,) = conexion.execute(text("SELECT creado_en FROM intento_login")).one()
    assert restante == AHORA - timedelta(minutes=10)


def test_adr018_el_limite_es_de_24_horas_justas(
    _engine_de_sesion: Engine, app_mantenimiento_engine: Engine
) -> None:
    """Triangulación del borde: 23 h 59 min queda; 24 h 1 min se borra; sin nada que borrar, 0."""
    _insertar(_engine_de_sesion, hace=timedelta(hours=23, minutes=59))
    _insertar(_engine_de_sesion, hace=timedelta(hours=24, minutes=1))

    assert _limpiar(app_mantenimiento_engine) == 1
    assert _cantidad(_engine_de_sesion) == 1
    assert _limpiar(app_mantenimiento_engine) == 0
    assert _cantidad(_engine_de_sesion) == 1


def test_adr057_la_limpieza_no_levanta_un_bloqueo_vigente_y_no_toca_la_auditoria(
    sesion_real: Session, _engine_de_sesion: Engine, app_mantenimiento_engine: Engine
) -> None:
    organizacion = _crear_organizacion(sesion_real, f"org-limpieza-{uuid4().hex[:6]}")
    usuario = _crear_usuario(sesion_real, organizacion.id, "vendedor1")
    sesion_real.commit()
    for minuto in (1, 3, 5, 7, 9):
        with pytest.raises(CredencialesInvalidasError):
            _login(
                sesion_real,
                reloj=FixedClock(AHORA.replace(minute=minuto)),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password="mal",
                ip="10.1.1.1",
            )
        sesion_real.commit()
    _insertar(_engine_de_sesion, hace=timedelta(hours=30))
    reloj_del_intento = FixedClock(AHORA.replace(minute=12))
    with pytest.raises(LoginBloqueadoPorIntentosError) as antes:
        _login(
            sesion_real,
            reloj=reloj_del_intento,
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            ip="10.1.1.1",
        )
    sesion_real.commit()
    auditorias_antes = sesion_real.execute(
        text("SELECT count(*) FROM auditoria WHERE organizacion_id = :o"), {"o": organizacion.id}
    ).scalar_one()
    assert auditorias_antes >= 1

    borradas = _limpiar(app_mantenimiento_engine, AHORA.replace(minute=12))

    assert borradas == 1  # solo la de 30 horas
    with pytest.raises(LoginBloqueadoPorIntentosError) as despues:
        _login(
            sesion_real,
            reloj=reloj_del_intento,
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            ip="10.1.1.1",
        )
    assert str(despues.value) == str(antes.value)
    assert despues.value.status_http == 429
    sesion_real.rollback()
    auditorias_despues = sesion_real.execute(
        text("SELECT count(*) FROM auditoria WHERE organizacion_id = :o"), {"o": organizacion.id}
    ).scalar_one()
    assert auditorias_despues >= auditorias_antes


def test_inv05_la_aplicacion_no_puede_borrar_intentos(
    _engine_de_sesion: Engine, app_runtime_engine: Engine
) -> None:
    _insertar(_engine_de_sesion, hace=timedelta(hours=48))

    with pytest.raises(ProgrammingError, match="permission denied"):  # noqa: SIM117
        with app_runtime_engine.begin() as conexion:
            conexion.execute(text("DELETE FROM intento_login"))

    assert _cantidad(_engine_de_sesion) == 1
