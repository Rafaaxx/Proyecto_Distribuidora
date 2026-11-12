"""Pruebas unitarias del sobre del comando (change 04, grupo 4, tarea 4.1).

Dominio puro: no importa FastAPI ni SQLAlchemy (`design.md` D3, verificado
además por `import_linter`, tarea 1.2/1.3).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.commands.sobre import ModoNoAdmitidoPorRestError, SobreComando, construir_sobre_online

_ORGANIZACION_A = UUID("00000000-0000-7000-8000-00000000000a")
_ORGANIZACION_B = UUID("00000000-0000-7000-8000-00000000000b")
_USUARIO = UUID("00000000-0000-7000-8000-000000000001")
_DISPOSITIVO = UUID("00000000-0000-7000-8000-000000000002")
_OPERATION_ID = UUID("00000000-0000-7000-8000-000000000003")
_MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


def _construir_sobre(*, organizacion_id: UUID, contenido: dict[str, object]) -> SobreComando:
    return SobreComando(
        operation_id=_OPERATION_ID,
        tipo="USUARIO_CREAR",
        version=1,
        modo="ONLINE",
        organizacion_id=organizacion_id,
        usuario_id=_USUARIO,
        dispositivo_id=_DISPOSITIVO,
        occurred_at=_MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=contenido,
    )


def test_el_contenido_no_puede_elegir_la_organizacion() -> None:
    """Escenario "El contenido no puede elegir la organización" (INV-21,
    TR-08): el sobre se arma con la organización del contexto de sesión
    (`_ORGANIZACION_A`), aunque el contenido informe otra (`_ORGANIZACION_B`).
    """
    sobre = _construir_sobre(
        organizacion_id=_ORGANIZACION_A,
        contenido={"organizacion_id": str(_ORGANIZACION_B), "usuario": "vendedor1"},
    )

    assert sobre.organizacion_id == _ORGANIZACION_A
    assert sobre.organizacion_id != _ORGANIZACION_B


def test_el_contenido_no_puede_elegir_usuario_ni_dispositivo() -> None:
    """Triangulación: el mismo principio aplica a usuario y dispositivo, no
    solo a organización -- ningún campo de contexto del sobre se deriva de
    `contenido`, aunque `contenido` traiga valores con esas mismas claves."""
    otro_usuario = UUID("00000000-0000-7000-8000-0000000000f1")
    otro_dispositivo = UUID("00000000-0000-7000-8000-0000000000f2")

    sobre = _construir_sobre(
        organizacion_id=_ORGANIZACION_A,
        contenido={
            "usuario_id": str(otro_usuario),
            "dispositivo_id": str(otro_dispositivo),
        },
    )

    assert sobre.usuario_id == _USUARIO
    assert sobre.dispositivo_id == _DISPOSITIVO
    assert sobre.usuario_id != otro_usuario
    assert sobre.dispositivo_id != otro_dispositivo


def test_el_sobre_es_inmutable() -> None:
    """El sobre es una estructura inmutable (`design.md` D3): reasignar un
    campo después de construido debe fallar, no aceptarse en silencio."""
    sobre = _construir_sobre(organizacion_id=_ORGANIZACION_A, contenido={})

    with pytest.raises(FrozenInstanceError):
        sobre.organizacion_id = _ORGANIZACION_B  # type: ignore[misc]


class TestConstruirSobreOnline:
    """Tarea 7.4, escenario "Un endpoint REST directo no acepta modo
    OFFLINE" (ADR-012, `design.md` D4): `construir_sobre_online` es lo que
    un endpoint de escritura usa para armar su sobre final."""

    def _kwargs(self, *, modo: str) -> dict[str, object]:
        return {
            "operation_id": _OPERATION_ID,
            "tipo": "USUARIO_CREAR",
            "version": 1,
            "modo": modo,
            "organizacion_id": _ORGANIZACION_A,
            "usuario_id": _USUARIO,
            "dispositivo_id": _DISPOSITIVO,
            "occurred_at": _MOMENTO,
            "secuencia": 1,
            "app_version": "1.0.0",
            "contenido": {},
        }

    def test_modo_online_se_acepta(self) -> None:
        sobre = construir_sobre_online(**self._kwargs(modo="ONLINE"))  # type: ignore[arg-type]

        assert sobre.modo == "ONLINE"
        assert sobre.operation_id == _OPERATION_ID

    def test_modo_offline_se_rechaza(self) -> None:
        with pytest.raises(ModoNoAdmitidoPorRestError) as exc_info:
            construir_sobre_online(**self._kwargs(modo="OFFLINE"))  # type: ignore[arg-type]

        assert exc_info.value.codigo == "MODO_NO_ADMITIDO_POR_REST"

    def test_cualquier_otro_modo_tambien_se_rechaza(self) -> None:
        """Triangulación: no es una lista blanca de un único valor prohibido
        (`OFFLINE`), es una lista blanca de un único valor permitido
        (`ONLINE`)."""
        with pytest.raises(ModoNoAdmitidoPorRestError):
            construir_sobre_online(**self._kwargs(modo="CUALQUIER_OTRA_COSA"))  # type: ignore[arg-type]
