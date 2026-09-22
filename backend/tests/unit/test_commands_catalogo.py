"""Prueba unitaria del cruce catálogo <-> registro de handlers (change 04,
grupo 4, tarea 4.5, `design.md` D3).

Decisión de diseño tomada dentro del alcance delegado a este grupo (mismo
criterio que la tarea 3.3 del change 04 con la huella): `design.md` D3 exige
"una prueba que exige que todo tipo declarado en el catálogo tenga handler
registrado y viceversa" pero no especifica el mecanismo concreto. Se
implementa como dos registros independientes que deben declararse juntos
por cada módulo de negocio: `catalogo.declarar_tipo` (si el tipo admite
ONLINE/OFFLINE, dato que necesitan los grupos 7 y 8) y
`registro.registrar_handler` (el handler de una versión concreta). La
función `verificar_catalogo_y_registro` cruza ambos y falla si un tipo
está en uno sin estar en el otro -- se llama en el arranque de la
aplicación, no en cada comando, para que un handler no importado (o un
tipo declarado sin ningún handler) se vea en el arranque y no en
producción, tal como pide D3. Esta decisión se reporta en el resumen final
para confirmación humana: es una elección de implementación, no de
negocio, pero fija un patrón que los 23 changes siguientes van a repetir.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.commands import catalogo
from app.commands.registro import registrar_handler
from app.commands.verificacion import CatalogoDesincronizadoError, verificar_catalogo_y_registro


class _Esquema(BaseModel):
    nombre: str


def _handler_de_prueba(sobre: object, contenido: BaseModel) -> str:
    return "ejecutado"


@pytest.fixture(autouse=True)
def _estado_aislado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Catálogo y registro parten vacíos en cada prueba: el estado real de
    producción no debe filtrarse ni depender del orden de importación."""
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})
    monkeypatch.setattr("app.commands.registro._REGISTRO", {})


def test_un_tipo_declarado_sin_handler_falla_la_verificacion() -> None:
    """Un tipo declarado en el catálogo que nadie implementó (ningún
    handler registrado para ninguna versión) se detecta en el arranque."""
    catalogo.declarar_tipo("VENTA_CONFIRMAR", admite_online=True, admite_offline=True)

    with pytest.raises(CatalogoDesincronizadoError):
        verificar_catalogo_y_registro()


def test_un_handler_registrado_sin_declarar_en_el_catalogo_falla_la_verificacion() -> None:
    """Triangulación: el caso inverso -- un handler registrado para un tipo
    que nadie declaró en el catálogo (typo, o módulo que se saltó
    `declarar_tipo`) también se detecta en el arranque."""
    registrar_handler("USUARIO_CREAR", 1, _Esquema)(_handler_de_prueba)

    with pytest.raises(CatalogoDesincronizadoError):
        verificar_catalogo_y_registro()


def test_un_tipo_declarado_con_su_handler_registrado_verifica_sin_error() -> None:
    """Cuando catálogo y registro coinciden, la verificación no levanta
    nada."""
    catalogo.declarar_tipo("USUARIO_CREAR", admite_online=True, admite_offline=False)
    registrar_handler("USUARIO_CREAR", 1, _Esquema)(_handler_de_prueba)

    verificar_catalogo_y_registro()  # no debe lanzar
