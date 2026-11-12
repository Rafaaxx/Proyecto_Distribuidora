# ruff: noqa: F811
"""Tarea 6.6 (change 18b; `design.md` D3 revisada punto 7 y D21 punto 7): definir el PIN reinicia
los dos contadores del autorizador con una fila marcador (`exito = true`) en la transacción del
comando. Solo cuentan los fallos posteriores al último marcador.

Estas pruebas definen el PIN por el servicio común (`establecer_pin_autorizacion`, que usan
`PIN_AUTORIZACION_ROTAR` y `PIN_AUTORIZACION_PROPIO_DEFINIR`) y por el handler de la rotación;
la definición por "Mi PIN" también se ejercita en `test_identidad_pin_propio_definir.py`.

Reglas citadas: ADR-011, SEG-04.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session
from test_identidad_pin_intentos import (
    PERMISO,
    PIN,
    PIN_MALO,
    Escenario,
    RelojAjustable,
    reloj,  # noqa: F401  (fixture)
    sesion,  # noqa: F401  (fixture)
)

from app.commands.sobre import SobreComando
from app.modules.identidad import commands as identidad_commands
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import (
    PinAutorizacionInvalidoError,
    PinBloqueadoError,
)

PIN_NUEVO = "735194"


def _definir_pin(e: Escenario, hora: str, pin: str = PIN_NUEVO) -> None:
    e.reloj.en(hora)
    identidad_service.establecer_pin_autorizacion(
        e.org, e.sesion, e.reloj, usuario_id=e.marta, pin=pin, actor_id=e.marta
    )
    e.sesion.commit()


def _marcadores(e: Escenario) -> list[dict[str, Any]]:
    return e.filas(exito=True)


def test_adr011_definir_el_pin_deja_una_fila_marcador_y_el_pin_nuevo_autoriza(
    sesion: Session,
    reloj: RelojAjustable,  # noqa: F811
) -> None:
    e = Escenario(sesion, reloj)
    pedro = e.vendedor()
    for hora in ("10:01", "10:02", "10:03", "10:04"):
        e.falla(pedro, hora)
    antes = len(_marcadores(e))

    _definir_pin(e, "10:05")

    nuevos = _marcadores(e)
    assert len(nuevos) == antes + 1
    assert nuevos[-1]["autorizador_id"] == e.marta
    assert nuevos[-1]["intentante_id"] is None
    assert e.verificar(pedro, PIN_NUEVO, hora="10:06").id == e.marta


def test_adr011_el_marcador_reinicia_los_dos_contadores_un_fallo_posterior_es_el_primero(
    sesion: Session,
    reloj: RelojAjustable,  # noqa: F811
) -> None:
    e = Escenario(sesion, reloj)
    pedro = e.vendedor()
    for hora in ("10:01", "10:02", "10:03", "10:04"):
        e.falla(pedro, hora)  # cuatro de cinco: un fallo más lo bloquearía

    _definir_pin(e, "10:05")
    e.falla(pedro, "10:06", pin=PIN_MALO)  # primero tras el marcador: no bloquea
    for hora in ("10:07", "10:08", "10:09"):
        e.falla(pedro, hora, pin=PIN_MALO)

    assert e.verificar(pedro, PIN_NUEVO, hora="10:10").id == e.marta  # cuatro: sigue libre
    e.falla(pedro, "10:11", pin=PIN_MALO)  # el quinto desde el marcador
    with pytest.raises(PinBloqueadoError):
        e.verificar(pedro, PIN_NUEVO, hora="10:12")


def test_adr011_con_marta_bloqueada_para_un_usuario_definir_el_pin_la_desbloquea(
    sesion: Session,
    reloj: RelojAjustable,  # noqa: F811
) -> None:
    e = Escenario(sesion, reloj)
    pedro = e.vendedor()
    for hora in ("10:02", "10:05", "10:07", "10:09", "10:10"):
        e.falla(pedro, hora)
    with pytest.raises(PinBloqueadoError):
        e.verificar(pedro, PIN, hora="10:11")

    _definir_pin(e, "10:12")

    assert e.verificar(pedro, PIN_NUEVO, hora="10:13").id == e.marta


def test_adr011_con_marta_bloqueada_para_todos_definir_el_pin_la_desbloquea_para_todos(
    sesion: Session,
    reloj: RelojAjustable,
    monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    monkeypatch.setattr(identidad_service, "LIMITE_FALLOS_PIN_POR_AUTORIZADOR", 3)
    e = Escenario(sesion, reloj, intentos_pin_max=10)
    a, b, c, otro = e.vendedor(), e.vendedor(), e.vendedor(), e.vendedor()
    e.falla(a, "10:01")
    e.falla(b, "10:02")
    e.falla(c, "10:03")
    for usuario in (a, b, c, otro):
        with pytest.raises(PinBloqueadoError):
            e.verificar(usuario, PIN, hora="10:04")

    _definir_pin(e, "10:05")

    for usuario in (a, b, c, otro):
        assert e.verificar(usuario, PIN_NUEVO, hora="10:06").id == e.marta


def test_adr011_un_comando_de_definicion_rechazado_no_deja_marcador(
    sesion: Session,
    reloj: RelojAjustable,  # noqa: F811
) -> None:
    e = Escenario(sesion, reloj)
    antes = len(_marcadores(e))
    e.reloj.en("10:05")

    with pytest.raises(PinAutorizacionInvalidoError):
        identidad_service.establecer_pin_autorizacion(
            e.org, e.sesion, e.reloj, usuario_id=e.marta, pin="123456", actor_id=e.marta
        )
    e.sesion.rollback()

    assert len(_marcadores(e)) == antes


def test_adr011_si_la_transaccion_del_comando_se_revierte_el_marcador_no_queda(
    sesion: Session,
    reloj: RelojAjustable,  # noqa: F811
) -> None:
    e = Escenario(sesion, reloj)
    antes = len(_marcadores(e))
    e.reloj.en("10:05")

    identidad_service.establecer_pin_autorizacion(
        e.org, e.sesion, e.reloj, usuario_id=e.marta, pin=PIN_NUEVO, actor_id=e.marta
    )
    e.sesion.rollback()

    assert len(_marcadores(e)) == antes
    assert e.verificar(e.vendedor(), PIN, hora="10:06").id == e.marta  # el PIN viejo sigue


def test_adr011_la_rotacion_por_el_handler_tambien_reinicia_el_contador(
    sesion: Session,
    reloj: RelojAjustable,  # noqa: F811
) -> None:
    e = Escenario(sesion, reloj)
    pedro = e.vendedor()
    administrador = e.usuario(frozenset({"ADMIN_USUARIOS"}))
    for hora in ("10:01", "10:02", "10:03", "10:04"):
        e.falla(pedro, hora)
    e.reloj.en("10:05")
    sobre = SobreComando(
        operation_id=uuid4(),
        tipo="PIN_AUTORIZACION_ROTAR",
        version=1,
        modo="ONLINE",
        organizacion_id=e.org,
        usuario_id=administrador,
        dispositivo_id=e.dispositivo,
        occurred_at=datetime(2026, 10, 22, 10, 5, tzinfo=UTC),
        secuencia=1,
        app_version="server",
        contenido={"usuario_id": str(e.marta)},
    )

    identidad_commands.manejar_pin_autorizacion_rotar(
        sobre,
        identidad_commands.PinAutorizacionRotarContenidoV1.model_validate(sobre.contenido),
        sesion=sesion,
        reloj=e.reloj,
        pin=SecretStr(PIN_NUEVO),
    )
    sesion.commit()

    assert len(_marcadores(e)) == 2  # el del alta de Marta y el de la rotación
    e.falla(pedro, "10:06", pin=PIN_MALO)
    assert e.verificar(pedro, PIN_NUEVO, hora="10:07").id == e.marta


def test_los_fallos_anteriores_a_otro_autorizador_no_se_reinician(
    sesion: Session,
    reloj: RelojAjustable,  # noqa: F811
) -> None:
    """El marcador es por autorizador: definir el PIN de Lucía no desbloquea a Marta."""
    e = Escenario(sesion, reloj)
    pedro = e.vendedor()
    lucia = e.usuario(frozenset({PERMISO}), con_pin="864209")
    for hora in ("10:02", "10:05", "10:07", "10:09", "10:10"):
        e.falla(pedro, hora)

    e.reloj.en("10:12")
    identidad_service.establecer_pin_autorizacion(
        e.org, e.sesion, e.reloj, usuario_id=lucia, pin=PIN_NUEVO, actor_id=lucia
    )
    e.sesion.commit()

    with pytest.raises(PinBloqueadoError):
        e.verificar(pedro, PIN, hora="10:13")
