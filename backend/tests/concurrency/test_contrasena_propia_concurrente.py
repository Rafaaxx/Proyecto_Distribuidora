"""Change 20b, tarea 4.6: concurrencia real de "Mi contraseña" (`CONTRASENA_PROPIA_CAMBIAR`), contra
PostgreSQL real (Testcontainers, `READ COMMITTED`), con commits reales y sin rollback externo.

- (a) varios cambios en paralelo con la contraseña actual incorrecta suman TODOS sus intentos
  fallidos aunque cada comando se rechace (el intento se confirma en una transacción aparte, nada
  se pierde por el rollback del comando) y el bloqueo se alcanza exactamente en el límite: como el
  usuario se toma `FOR NO KEY UPDATE`, el siguiente cambio ya ve los fallos confirmados del
  anterior (ADR-057).
- (b) un cambio de contraseña propio frente a un restablecimiento del administrador sobre el mismo
  usuario nunca deja dos hashes mezclados ni sesiones vigentes anteriores a ambos cambios.

Reglas citadas: ADR-018, ADR-057, INV-01.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app.core.db import crear_engine
from app.core.seguridad import verificar_password
from app.modules.identidad.domain.usuarios import (
    ContrasenaIncorrectaError,
    LoginBloqueadoPorIntentosError,
)
from tests.concurrency.identidad_escenario import CLAVE_ORIGINAL, Actor, EscenarioDeIdentidad
from tests.concurrency.test_compras_concurrencia import _en_paralelo

LIMITE = 5
EQUIVOCADA = "clave-equivocada-de-la-prueba-1127"
NUEVA_PROPIA = "clave-nueva-propia-de-la-prueba-8841"
NUEVA_DEL_ADMIN = "clave-del-administrador-de-la-prueba-3306"
RONDAS = 4


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _cambiar(
    escenario: EscenarioDeIdentidad,
    sesion,
    actor: Actor,
    actual: str,
    nueva: str,
    ip: str,  # type: ignore[no-untyped-def]
):
    return escenario.enviar(
        sesion,
        actor,
        "CONTRASENA_PROPIA_CAMBIAR",
        {},
        password_actual=SecretStr(actual),
        password_nueva=SecretStr(nueva),
        ip=ip,
    )


def _fallos_registrados(escenario: EscenarioDeIdentidad, usuario_id: UUID) -> int:
    (fila,) = escenario.leer(
        "SELECT count(*) FROM intento_login WHERE usuario_id = :u AND exito = false",
        u=usuario_id,
    )
    return int(fila[0])


@pytest.mark.parametrize("ronda", range(RONDAS))
def test_a_los_fallos_en_paralelo_se_suman_todos_y_el_bloqueo_llega_en_el_limite(
    database_url: str, _engine_de_sesion, ronda: int
) -> None:
    """ADR-018, ADR-057, SEG-04: ocho cambios simultáneos con la actual incorrecta. Cada comando
    se rechaza, pero sus intentos fallidos se confirman: quedan exactamente `LIMITE` fallos y los
    otros tres reciben el bloqueo (429), sin perder ni pasarse de un intento."""
    escenario = EscenarioDeIdentidad(database_url)
    usuario, _ = escenario.crear_usuario(frozenset({"VENDER"}), con_clave=True)
    trabajos = [
        lambda sesion: _cambiar(escenario, sesion, usuario, EQUIVOCADA, NUEVA_PROPIA, "10.20.30.40")
        for _ in range(LIMITE + 3)
    ]

    resultados, errores = _en_paralelo(database_url, trabajos)

    assert resultados == {}
    incorrectas = [e for e in errores.values() if isinstance(e, ContrasenaIncorrectaError)]
    bloqueadas = [e for e in errores.values() if isinstance(e, LoginBloqueadoPorIntentosError)]
    assert len(incorrectas) == LIMITE, errores
    assert len(bloqueadas) == 3, errores
    assert _fallos_registrados(escenario, usuario[0]) == LIMITE
    (hash_actual,) = escenario.leer(
        "SELECT password_hash FROM usuario WHERE id = :u", u=usuario[0]
    )[0]
    assert verificar_password(CLAVE_ORIGINAL, hash_actual)


def test_a_por_debajo_del_limite_ningun_intento_se_pierde_por_el_rollback(
    database_url: str, _engine_de_sesion
) -> None:
    """Triangulación: tres fallos simultáneos (menos que el límite) dejan tres filas confirmadas
    aunque los tres comandos se hayan revertido."""
    escenario = EscenarioDeIdentidad(database_url)
    usuario, _ = escenario.crear_usuario(frozenset({"VENDER"}), con_clave=True)

    resultados, errores = _en_paralelo(
        database_url,
        [
            lambda sesion: _cambiar(
                escenario, sesion, usuario, EQUIVOCADA, NUEVA_PROPIA, "10.20.30.41"
            )
            for _ in range(3)
        ],
    )

    assert resultados == {}
    assert all(isinstance(e, ContrasenaIncorrectaError) for e in errores.values()), errores
    assert _fallos_registrados(escenario, usuario[0]) == 3
    assert escenario.leer("SELECT count(*) FROM comando WHERE organizacion_id = :o")[0][0] == 0


@pytest.mark.parametrize("ronda", range(RONDAS))
def test_b_cambio_propio_y_restablecimiento_del_administrador_no_mezclan_hashes_ni_sesiones(
    database_url: str, _engine_de_sesion, ronda: int
) -> None:
    """INV-01: el usuario se toma `FOR NO KEY UPDATE`. Si el restablecimiento corre después, queda
    su contraseña y ninguna sesión; si corre antes, el cambio propio ya no valida la actual
    (cambió) y se rechaza. En ningún orden queda una contraseña distinta de la última escrita ni
    una sesión anterior a ambos cambios."""
    escenario = EscenarioDeIdentidad(database_url)
    administrador, _ = escenario.administrador()
    usuario, _ = escenario.crear_usuario(frozenset({"VENDER"}), con_clave=True)
    otro_dispositivo = escenario.dispositivo()
    escenario.abrir_familia(usuario[0], usuario[1])
    escenario.abrir_familia(usuario[0], otro_dispositivo)

    resultados, errores = _en_paralelo(
        database_url,
        [
            lambda sesion: _cambiar(
                escenario, sesion, usuario, CLAVE_ORIGINAL, NUEVA_PROPIA, "10.20.30.42"
            ),
            lambda sesion: escenario.enviar(
                sesion,
                administrador,
                "USUARIO_CONTRASENA_RESTABLECER",
                {"usuario_id": str(usuario[0])},
                password_nueva=SecretStr(NUEVA_DEL_ADMIN),
            ),
        ],
    )

    # El restablecimiento siempre se aplica; el cambio propio se aplica solo si corrió antes.
    assert 1 in resultados, (resultados, errores)
    if 0 in errores:
        assert isinstance(errores[0], ContrasenaIncorrectaError), errores
    (hash_actual,) = escenario.leer(
        "SELECT password_hash FROM usuario WHERE id = :u", u=usuario[0]
    )[0]
    assert verificar_password(NUEVA_DEL_ADMIN, hash_actual)
    assert not verificar_password(NUEVA_PROPIA, hash_actual)
    assert not verificar_password(CLAVE_ORIGINAL, hash_actual)
    assert escenario.familias_vigentes(usuario[0]) == 0
