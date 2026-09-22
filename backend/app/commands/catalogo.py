"""Catálogo de tipos de comando declarados (`02` §6.5, `design.md` D3).

Un tipo se declara una vez, indicando si admite modo `ONLINE` y/o `OFFLINE`
(`02` §6.2, §6.5) -- dato que necesitan los grupos 7 y 8 para rechazar un
comando en el modo que no le corresponde. La declaración es independiente
del registro de handlers por versión (`registro.py`): son dos listas que
cada módulo de negocio puebla juntas al definir su tipo de comando, y
`verificacion.verificar_catalogo_y_registro` exige que coincidan
exactamente.

No importa FastAPI ni SQLAlchemy: mecanismo puro (`design.md` D3).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TipoDeComandoDeclarado:
    """Un tipo de comando declarado en el catálogo, con los modos que
    admite (`02` §6.5)."""

    tipo: str
    admite_online: bool
    admite_offline: bool


class TipoYaDeclaradoError(ValueError):
    """Dos declaraciones intentaron registrar el mismo tipo (error de
    programación, detectado al importar los módulos de negocio)."""


# Puebla el arranque de la aplicación importando los módulos de negocio que
# llaman a `declarar_tipo`. Las pruebas unitarias aíslan este diccionario
# con `monkeypatch` para no depender del orden de importación.
_CATALOGO: dict[str, TipoDeComandoDeclarado] = {}


def declarar_tipo(
    tipo: str, *, admite_online: bool, admite_offline: bool
) -> TipoDeComandoDeclarado:
    """Declara `tipo` en el catálogo. Falla en el momento de la
    importación si el tipo ya estaba declarado."""
    if tipo in _CATALOGO:
        raise TipoYaDeclaradoError(f"El tipo de comando {tipo!r} ya está declarado.")
    declarado = TipoDeComandoDeclarado(
        tipo=tipo, admite_online=admite_online, admite_offline=admite_offline
    )
    _CATALOGO[tipo] = declarado
    return declarado


def tipo_declarado(tipo: str) -> TipoDeComandoDeclarado | None:
    return _CATALOGO.get(tipo)


def tipos_declarados() -> frozenset[str]:
    return frozenset(_CATALOGO.keys())
