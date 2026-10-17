"""Firma tipada de los handlers (change 17, tarea 1.1; spec
`sistema/pipeline-de-comandos`, requisito "Un comando se ejecuta igual por REST
y por el lote"; `design.md` D9; deuda de ADR-048 punto 5 y ADR-049 punto 19).

`HandlerFuncion` es un `Protocol` con `(sobre, contenido, *, sesion, reloj)`.
Una función que no tiene esa forma se rechaza en dos lugares: al verificar tipos
(`mypy`) y al registrarla (arranque).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
from mypy import api as mypy_api
from pydantic import BaseModel

from app.commands.registro import (
    FirmaDeHandlerInvalidaError,
    HandlerRegistrado,
    registrar_handler,
)
from app.core.clock import Clock


class _Esquema(BaseModel):
    nombre: str


@pytest.fixture(autouse=True)
def _registro_aislado(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, int], Any]:
    registro_vacio: dict[tuple[str, int], HandlerRegistrado] = {}
    monkeypatch.setattr("app.commands.registro._REGISTRO", registro_vacio)
    return registro_vacio


def _verificar_tipos(codigo: str, tmp_path: Path) -> tuple[str, int]:
    archivo = tmp_path / "ejemplo_handler.py"
    archivo.write_text(textwrap.dedent(codigo), encoding="utf-8")
    salida, _errores, estado = mypy_api.run(
        [str(archivo), "--strict", "--python-version", "3.12", "--no-incremental"]
    )
    return salida, estado


_ENCABEZADO = """
from pydantic import BaseModel

from app.commands.registro import SesionDeHandler, registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock


class Esquema(BaseModel):
    nombre: str

"""


class TestRegistroEnTiempoDeEjecucion:
    def test_un_handler_con_sesion_y_reloj_por_nombre_se_registra(self) -> None:
        def handler(sobre: object, contenido: _Esquema, *, sesion: object, reloj: Clock) -> str:
            return "ok"

        registrar_handler("TIPO_OK_A", 1, _Esquema)(handler)  # type: ignore[arg-type]

    def test_un_handler_de_dos_argumentos_se_rechaza_al_registrarlo(self) -> None:
        def handler_viejo(sobre: object, contenido: _Esquema) -> str:
            return "ok"

        with pytest.raises(FirmaDeHandlerInvalidaError) as error:
            registrar_handler("TIPO_VIEJO", 1, _Esquema)(handler_viejo)  # type: ignore[arg-type]

        assert "sesion" in str(error.value)
        assert "reloj" in str(error.value)

    def test_un_handler_sin_reloj_se_rechaza_y_no_queda_registrado(
        self, _registro_aislado: dict[tuple[str, int], Any]
    ) -> None:
        def handler_sin_reloj(sobre: object, contenido: _Esquema, *, sesion: object) -> str:
            return "ok"

        with pytest.raises(FirmaDeHandlerInvalidaError):
            registrar_handler("TIPO_SIN_RELOJ", 1, _Esquema)(handler_sin_reloj)  # type: ignore[arg-type]

        assert ("TIPO_SIN_RELOJ", 1) not in _registro_aislado

    def test_sesion_y_reloj_como_posicionales_se_rechazan(self) -> None:
        def handler_posicional(
            sobre: object, contenido: _Esquema, sesion: object, reloj: Clock
        ) -> str:
            return "ok"

        with pytest.raises(FirmaDeHandlerInvalidaError):
            registrar_handler("TIPO_POSICIONAL", 1, _Esquema)(handler_posicional)  # type: ignore[arg-type]


class TestVerificacionDeTipos:
    def test_un_handler_con_la_firma_del_protocolo_pasa_mypy(self, tmp_path: Path) -> None:
        salida, estado = _verificar_tipos(
            _ENCABEZADO
            + """
@registrar_handler("TIPO_TIPADO", 1, Esquema)
def manejar(
    sobre: SobreComando, contenido: Esquema, *, sesion: SesionDeHandler, reloj: Clock
) -> str:
    return contenido.nombre
""",
            tmp_path,
        )

        assert estado == 0, salida

    def test_un_handler_de_dos_argumentos_falla_mypy(self, tmp_path: Path) -> None:
        salida, estado = _verificar_tipos(
            _ENCABEZADO
            + """
@registrar_handler("TIPO_VIEJO", 1, Esquema)
def manejar(sobre: SobreComando, contenido: Esquema) -> str:
    return contenido.nombre
""",
            tmp_path,
        )

        assert estado != 0
        assert "arg-type" in salida or "Argument 1" in salida

    def test_un_handler_con_otro_esquema_falla_mypy(self, tmp_path: Path) -> None:
        salida, estado = _verificar_tipos(
            _ENCABEZADO
            + """
class Otro(BaseModel):
    x: int


@registrar_handler("TIPO_ESQUEMA_AJENO", 1, Esquema)
def manejar(
    sobre: SobreComando, contenido: Otro, *, sesion: SesionDeHandler, reloj: Clock
) -> str:
    return "x"
""",
            tmp_path,
        )

        assert estado != 0, salida
