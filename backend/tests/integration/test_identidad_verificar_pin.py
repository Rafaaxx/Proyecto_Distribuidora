"""Tareas 6.2 y 6.8 (change 18b; `design.md` D2, D3 revisada; spec `identidad/pin-de-autorizacion`):
`identidad_service.verificar_pin_de_autorizacion` verifica el PIN de un autorizador contra su
derivación guardada. Con el PIN correcto no escribe nada; un fallo se escribe en una transacción
aparte (tarea 6.3, `test_identidad_pin_intentos.py`), por eso estas pruebas usan una sesión con
commits reales y limpian al terminar.

6.8 (precisiones del 2026-10-22): un autorizador inactivo, o con el rol inactivo, responde
`PIN_INCORRECTO` y cuenta como fallo; uno sin el permiso pedido responde `AUTORIZADOR_SIN_PERMISO`
sin verificar el PIN ni contar (el permiso va antes que el PIN).

Reglas citadas: SEG-05, ADR-011, ADR-019, ADR-028, INV-21.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_utiles import MOMENTO

from app.core import seguridad
from app.core.clock import FixedClock
from app.core.db import crear_engine, crear_session_factory
from app.core.errors import DomainError
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import (
    AutorizadorNoEncontradoError,
    AutorizadorSinPermisoError,
    PinIncorrectoError,
)

RELOJ = FixedClock(MOMENTO)
PIN = "482913"
PERMISO = "AUTORIZAR_DESCUENTO"
AUTORIZA = frozenset({PERMISO})


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    """Sesión con commits reales: el fallo de un PIN se escribe en una transacción aparte y
    necesita ver los datos confirmados (no sirve la sesión que se revierte al final)."""
    engine = crear_engine(database_url)
    try:
        with crear_session_factory(engine)() as sesion_real:
            yield sesion_real
    finally:
        with engine.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
        engine.dispose()


def _fallos(sesion: Session, autorizador_id: UUID) -> int:
    sesion.rollback()
    return int(
        sesion.execute(
            text(
                "SELECT count(*) FROM intento_pin_autorizacion "
                "WHERE autorizador_id = :a AND NOT exito"
            ),
            {"a": autorizador_id},
        ).scalar_one()
    )


def _autorizador(sesion: Session, organizacion_id: UUID, *, con_pin: str | None = PIN) -> UUID:
    usuario_id, _ = crear_usuario_y_dispositivo(sesion, organizacion_id, permisos=AUTORIZA)
    if con_pin is not None:
        identidad_service.establecer_pin_autorizacion(
            organizacion_id, sesion, RELOJ, usuario_id=usuario_id, pin=con_pin, actor_id=usuario_id
        )
    sesion.commit()
    return usuario_id


def _vendedor(sesion: Session, organizacion_id: UUID) -> UUID:
    usuario_id, _ = crear_usuario_y_dispositivo(
        sesion, organizacion_id, permisos=frozenset({"VENDER"})
    )
    sesion.commit()
    return usuario_id


def _verificar(
    sesion: Session,
    organizacion_id: UUID,
    autorizador_id: UUID,
    pin: str,
    *,
    permiso: str = PERMISO,
) -> Any:
    return identidad_service.verificar_pin_de_autorizacion(
        organizacion_id,
        sesion,
        RELOJ,
        autorizador_id=autorizador_id,
        intentante_id=_vendedor(sesion, organizacion_id),
        pin=pin,
        permiso=permiso,
    )


def test_seg05_el_pin_correcto_devuelve_al_autorizador(sesion: Session) -> None:
    organizacion = crear_organizacion(sesion)
    marta = _autorizador(sesion, organizacion.id)

    usuario = _verificar(sesion, organizacion.id, marta, PIN)

    assert usuario.id == marta
    assert _fallos(sesion, marta) == 0


def test_seg05_el_pin_correcto_de_otro_autorizador_no_sirve_para_marta(sesion: Session) -> None:
    """Cada derivación es del usuario: el PIN de Lucía no autoriza a nombre de Marta."""
    organizacion = crear_organizacion(sesion)
    marta = _autorizador(sesion, organizacion.id, con_pin="482913")
    lucia = _autorizador(sesion, organizacion.id, con_pin="735194")

    assert _verificar(sesion, organizacion.id, lucia, "735194")
    with pytest.raises(PinIncorrectoError):
        _verificar(sesion, organizacion.id, marta, "735194")


@pytest.mark.parametrize("pin", ["482914", "000000", "", "48291", "482913 "])
def test_seg05_un_pin_distinto_se_rechaza_con_pin_incorrecto_403(sesion: Session, pin: str) -> None:
    organizacion = crear_organizacion(sesion)
    marta = _autorizador(sesion, organizacion.id)

    with pytest.raises(PinIncorrectoError) as error:
        _verificar(sesion, organizacion.id, marta, pin)

    assert error.value.codigo == "PIN_INCORRECTO"
    assert error.value.status_http == 403


def _sin_pin(sesion: Session, organizacion_id: UUID) -> UUID:
    return _autorizador(sesion, organizacion_id, con_pin=None)


def _con_pin_invalidado(sesion: Session, organizacion_id: UUID) -> UUID:
    """El PIN se invalida cuando el rol pierde su último permiso de autorización (ADR-011)."""
    marta = _autorizador(sesion, organizacion_id)
    usuario = repository.obtener_usuario_por_id(organizacion_id, marta, sesion)
    assert usuario is not None and usuario.pin_autorizacion_hash is not None
    identidad_service.cambiar_composicion_rol(
        organizacion_id,
        sesion,
        RELOJ,
        rol_id=usuario.rol_id,
        permisos_nuevos=frozenset({"VENDER"}),
        actor_id=marta,
        auditar=False,
    )
    sesion.commit()
    sesion.refresh(usuario)
    assert usuario.pin_autorizacion_hash is None
    return marta


def _con_pin_definido(sesion: Session, organizacion_id: UUID) -> UUID:
    return _autorizador(sesion, organizacion_id)


def _con_pin_invalidado_y_permiso_devuelto(sesion: Session, organizacion_id: UUID) -> UUID:
    """El rol perdió su último permiso de autorización (el PIN se invalida) y después lo
    recuperó: tiene el permiso, pero no PIN."""
    marta = _con_pin_invalidado(sesion, organizacion_id)
    usuario = repository.obtener_usuario_por_id(organizacion_id, marta, sesion)
    assert usuario is not None
    identidad_service.cambiar_composicion_rol(
        organizacion_id,
        sesion,
        RELOJ,
        rol_id=usuario.rol_id,
        permisos_nuevos=frozenset({"VENDER", PERMISO}),
        actor_id=marta,
        auditar=False,
    )
    sesion.commit()
    return marta


@pytest.mark.parametrize(
    "armar",
    [_con_pin_definido, _sin_pin, _con_pin_invalidado_y_permiso_devuelto],
    ids=["erroneo", "sin_pin", "invalidado"],
)
def test_adr011_incorrecto_sin_pin_e_invalidado_responden_exactamente_igual(
    sesion: Session, armar: Callable[[Session, UUID], UUID]
) -> None:
    """No se revela cuál es el caso: mismo error, mismo código, mismo estado y mismo mensaje."""
    organizacion = crear_organizacion(sesion)
    autorizador = armar(sesion, organizacion.id)

    with pytest.raises(PinIncorrectoError) as error:
        _verificar(sesion, organizacion.id, autorizador, "999111")

    assert (error.value.codigo, error.value.status_http) == ("PIN_INCORRECTO", 403)
    assert str(error.value) == "El PIN de autorización es incorrecto."


def test_adr011_un_pin_invalidado_por_perder_el_permiso_responde_sin_permiso(
    sesion: Session,
) -> None:
    """Si el rol perdió el último permiso de autorización, el PIN se invalida (ADR-011) y el
    autorizador ya no tiene el permiso pedido: el permiso va antes que el PIN (6.8)."""
    organizacion = crear_organizacion(sesion)
    marta = _con_pin_invalidado(sesion, organizacion.id)

    with pytest.raises(AutorizadorSinPermisoError):
        _verificar(sesion, organizacion.id, marta, "999111")

    assert _fallos(sesion, marta) == 0


def test_inv21_un_autorizador_de_otra_organizacion_responde_404(sesion: Session) -> None:
    propia = crear_organizacion(sesion)
    ajena = crear_organizacion(sesion)
    marta_ajena = _autorizador(sesion, ajena.id)

    with pytest.raises(AutorizadorNoEncontradoError) as error:
        _verificar(sesion, propia.id, marta_ajena, PIN)

    assert (error.value.codigo, error.value.status_http) == ("RECURSO_NO_ENCONTRADO", 404)
    # El PIN correcto de la ajena NO se distingue de un autorizador inexistente.
    with pytest.raises(AutorizadorNoEncontradoError):
        _verificar(sesion, propia.id, uuid4(), PIN)
    assert _fallos(sesion, marta_ajena) == 0


def test_adr019_un_pin_trivial_ya_definido_sigue_validando(sesion: Session) -> None:
    """La trivialidad se controla solo al definir: una derivación vieja de `123456` valida."""
    organizacion = crear_organizacion(sesion)
    marta = _autorizador(sesion, organizacion.id, con_pin=None)
    hash_derivado, sal, iteraciones = seguridad.derivar_pin_autorizacion("123456")
    sesion.execute(
        text(
            "UPDATE usuario SET pin_autorizacion_hash = :h, pin_autorizacion_sal = :s, "
            "pin_autorizacion_iteraciones = :i WHERE id = :id"
        ),
        {"h": hash_derivado, "s": sal, "i": iteraciones, "id": marta},
    )
    sesion.commit()
    sesion.expire_all()

    assert _verificar(sesion, organizacion.id, marta, "123456")
    with pytest.raises(PinIncorrectoError):
        _verificar(sesion, organizacion.id, marta, "654321")


def test_seg05_la_comparacion_es_en_tiempo_constante(
    sesion: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La igualdad pasa por `secrets.compare_digest` sobre la derivación (nunca `==`)."""
    organizacion = crear_organizacion(sesion)
    marta = _autorizador(sesion, organizacion.id)
    llamadas: list[tuple[str, str]] = []
    original = seguridad.secrets.compare_digest

    def espia(a: Any, b: Any) -> bool:
        llamadas.append((a, b))
        return original(a, b)

    monkeypatch.setattr(seguridad.secrets, "compare_digest", espia)

    _verificar(sesion, organizacion.id, marta, PIN)
    with pytest.raises(PinIncorrectoError):
        _verificar(sesion, organizacion.id, marta, "482914")

    assert len(llamadas) == 2
    assert all(len(a) == len(b) == 64 for a, b in llamadas)  # hex de SHA-256, ambos lados


def test_seg05_sin_pin_se_deriva_igual_para_no_filtrar_por_tiempo(
    sesion: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un autorizador sin PIN cuesta lo mismo que uno con PIN equivocado: una derivación."""
    organizacion = crear_organizacion(sesion)
    con_pin = _autorizador(sesion, organizacion.id)
    sin_pin = _sin_pin(sesion, organizacion.id)
    derivaciones: list[int] = []
    original = hashlib.pbkdf2_hmac

    def espia(nombre: str, clave: bytes, sal: bytes, iteraciones: int, *args: Any) -> bytes:
        derivaciones.append(iteraciones)
        return original(nombre, clave, sal, iteraciones, *args)

    monkeypatch.setattr(seguridad.hashlib, "pbkdf2_hmac", espia)

    for autorizador in (con_pin, sin_pin):
        derivaciones.clear()
        with pytest.raises(DomainError):
            _verificar(sesion, organizacion.id, autorizador, "999111")
        assert len(derivaciones) == 1


# --- 6.8: estado del autorizador y permiso antes que el PIN (D3 revisada, punto 5) ------------


def _inactivar_usuario(sesion: Session, usuario_id: UUID) -> None:
    sesion.execute(text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :u"), {"u": usuario_id})
    sesion.commit()


def _inactivar_rol_de(sesion: Session, usuario_id: UUID) -> None:
    sesion.execute(
        text("UPDATE rol SET activo = false WHERE id = (SELECT rol_id FROM usuario WHERE id = :u)"),
        {"u": usuario_id},
    )
    sesion.commit()


@pytest.mark.parametrize(
    "inactivar", [_inactivar_usuario, _inactivar_rol_de], ids=["usuario", "rol"]
)
def test_adr028_un_autorizador_inactivo_con_su_pin_correcto_responde_pin_incorrecto_y_cuenta(
    sesion: Session, inactivar: Callable[[Session, UUID], None]
) -> None:
    organizacion = crear_organizacion(sesion)
    marta = _autorizador(sesion, organizacion.id)
    inactivar(sesion, marta)

    with pytest.raises(PinIncorrectoError) as error:
        _verificar(sesion, organizacion.id, marta, PIN)

    assert (error.value.codigo, error.value.status_http) == ("PIN_INCORRECTO", 403)
    assert str(error.value) == "El PIN de autorización es incorrecto."
    assert _fallos(sesion, marta) == 1


def test_adr028_el_mismo_autorizador_reactivado_vuelve_a_autorizar(sesion: Session) -> None:
    organizacion = crear_organizacion(sesion)
    marta = _autorizador(sesion, organizacion.id)
    _inactivar_usuario(sesion, marta)
    with pytest.raises(PinIncorrectoError):
        _verificar(sesion, organizacion.id, marta, PIN)

    sesion.execute(text("UPDATE usuario SET estado = 'ACTIVO' WHERE id = :u"), {"u": marta})
    sesion.commit()

    assert _verificar(sesion, organizacion.id, marta, PIN).id == marta
    assert _fallos(sesion, marta) == 1


def test_seg05_un_autorizador_sin_el_permiso_pedido_no_verifica_el_pin_ni_cuenta(
    sesion: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El permiso va antes que el PIN: ni con el PIN correcto ni con uno equivocado se deriva
    nada ni se escribe un fallo."""
    organizacion = crear_organizacion(sesion)
    marta = _autorizador(sesion, organizacion.id)  # solo AUTORIZAR_DESCUENTO
    derivaciones: list[int] = []
    original = hashlib.pbkdf2_hmac

    def espia(nombre: str, clave: bytes, sal: bytes, iteraciones: int, *args: Any) -> bytes:
        derivaciones.append(iteraciones)
        return original(nombre, clave, sal, iteraciones, *args)

    monkeypatch.setattr(seguridad.hashlib, "pbkdf2_hmac", espia)

    for pin in (PIN, "999111"):
        with pytest.raises(AutorizadorSinPermisoError) as error:
            _verificar(sesion, organizacion.id, marta, pin, permiso="SUPERAR_CREDITO")
        assert (error.value.codigo, error.value.status_http) == ("AUTORIZADOR_SIN_PERMISO", 403)

    assert derivaciones == []
    assert _fallos(sesion, marta) == 0


def test_seg05_el_permiso_pedido_distinto_se_evalua_por_autorizacion(sesion: Session) -> None:
    """Triangulación: la misma persona autoriza lo que su rol permite y no lo que no."""
    organizacion = crear_organizacion(sesion)
    marta = _autorizador(sesion, organizacion.id)

    assert _verificar(sesion, organizacion.id, marta, PIN, permiso="AUTORIZAR_DESCUENTO")
    with pytest.raises(AutorizadorSinPermisoError):
        _verificar(sesion, organizacion.id, marta, PIN, permiso="SUPERAR_CREDITO")
