"""Pruebas unitarias del registro de handlers por `(tipo, version)`
(change 04, grupo 4, tareas 4.3-4.6, `design.md` D3).

Dominio puro: no importa FastAPI ni SQLAlchemy.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from app.commands.errores import (
    ContenidoDeComandoInvalidoError,
    TipoDeComandoDesconocidoError,
    VersionDeComandoSinHandlerError,
)
from app.commands.registro import (
    HandlerRegistrado,
    registrar_handler,
    resolver_handler,
    validar_contenido,
)


class _EsquemaV1(BaseModel):
    nombre: str


class _EsquemaV2(BaseModel):
    nombre: str
    email: str


@pytest.fixture(autouse=True)
def _registro_aislado(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, int], Any]:
    """Cada prueba parte de un registro vacío: el registro real de
    producción (poblado por los módulos de negocio al importarse) no debe
    filtrarse entre pruebas ni depender del orden de importación."""
    registro_vacio: dict[tuple[str, int], HandlerRegistrado] = {}
    monkeypatch.setattr("app.commands.registro._REGISTRO", registro_vacio)
    return registro_vacio


def _handler_de_prueba(sobre: object, contenido: BaseModel) -> str:
    return "ejecutado"


class TestResolverHandler:
    def test_un_tipo_de_comando_desconocido_se_rechaza(self) -> None:
        """Escenario "Un tipo de comando desconocido se rechaza" (SYN-06)."""
        with pytest.raises(TipoDeComandoDesconocidoError) as exc_info:
            resolver_handler("TIPO_QUE_NO_EXISTE", 1)

        assert exc_info.value.codigo == "TIPO_DE_COMANDO_DESCONOCIDO"

    def test_una_version_sin_handler_registrado_se_rechaza(self) -> None:
        """Escenario "Una versión sin handler registrado se rechaza sin
        efectos" (`02` §6.6, SYN-06): el tipo existe (tiene la versión 1
        registrada) pero no la versión 2."""
        registrar_handler("USUARIO_CREAR", 1, _EsquemaV1)(_handler_de_prueba)

        with pytest.raises(VersionDeComandoSinHandlerError) as exc_info:
            resolver_handler("USUARIO_CREAR", 2)

        assert exc_info.value.codigo == "VERSION_DE_COMANDO_SIN_HANDLER"

    def test_una_version_anterior_del_mismo_tipo_sigue_atendiendose(self) -> None:
        """Escenario "Una versión anterior del mismo tipo sigue
        atendiéndose" (`02` §6.6): dos versiones registradas del mismo tipo
        resuelven cada una a SU handler, no al de la última."""
        registrar_handler("USUARIO_CREAR", 1, _EsquemaV1)(_handler_de_prueba)
        registrar_handler("USUARIO_CREAR", 2, _EsquemaV2)(_handler_de_prueba)

        resuelto_v1 = resolver_handler("USUARIO_CREAR", 1)
        resuelto_v2 = resolver_handler("USUARIO_CREAR", 2)

        assert resuelto_v1.version == 1
        assert resuelto_v1.esquema is _EsquemaV1
        assert resuelto_v2.version == 2
        assert resuelto_v2.esquema is _EsquemaV2


class TestValidarContenido:
    def test_un_contenido_que_no_cumple_el_esquema_de_su_tipo_se_rechaza(self) -> None:
        """Escenario "Un contenido que no cumple el esquema de su tipo se
        rechaza" (SYN-06, `02` §6.3): omite el dato obligatorio `nombre`."""
        registrar_handler("USUARIO_CREAR", 1, _EsquemaV1)(_handler_de_prueba)
        handler = resolver_handler("USUARIO_CREAR", 1)

        with pytest.raises(ContenidoDeComandoInvalidoError) as exc_info:
            validar_contenido(handler, {})

        assert exc_info.value.codigo == "CONTENIDO_DE_COMANDO_INVALIDO"

    def test_un_contenido_que_cumple_el_esquema_se_valida_correctamente(self) -> None:
        """Triangulación: un contenido completo pasa la validación y
        devuelve una instancia tipada del esquema, no un `dict` crudo."""
        registrar_handler("USUARIO_CREAR", 1, _EsquemaV1)(_handler_de_prueba)
        handler = resolver_handler("USUARIO_CREAR", 1)

        validado = validar_contenido(handler, {"nombre": "Vendedor Uno"})

        assert isinstance(validado, _EsquemaV1)
        assert validado.nombre == "Vendedor Uno"
