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
    permiso_offline: str | None = None
    """El permiso que el bus compara al sincronizar un comando `OFFLINE` de este tipo (paso 4 de
    `02` §6.3, change 17, `design.md` D10). Obligatorio si y solo si el tipo admite `OFFLINE`."""
    operacion_offline: OperacionObservable | None = None
    """La operación de negocio sobre la que el bus anota sus observaciones (`PERMISO_REVOCADO`).
    Sin declarar, la observación queda anotada sobre el comando mismo."""


@dataclass(frozen=True)
class OperacionObservable:
    """Dónde encuentra el bus el identificador de la operación de negocio que creó el handler:
    `tipo` (por ejemplo `"COBRANZA"`) y la clave del resultado del handler que lo trae (por
    ejemplo `"cobranza_id"`). Es lo que une una observación del bus con la operación que el
    usuario revisa (SYN-08)."""

    tipo: str
    clave_en_resultado: str


class TipoOfflineSinPermisoError(ValueError):
    """Un tipo que admite `OFFLINE` no declaró el permiso que exige, o un tipo solo `ONLINE`
    declaró uno (error de programación, detectado al importar los módulos de negocio: la
    aplicación no arranca, `design.md` D10, SEG-06)."""


class TipoYaDeclaradoError(ValueError):
    """Dos declaraciones intentaron registrar el mismo tipo (error de
    programación, detectado al importar los módulos de negocio)."""


# Puebla el arranque de la aplicación importando los módulos de negocio que
# llaman a `declarar_tipo`. Las pruebas unitarias aíslan este diccionario
# con `monkeypatch` para no depender del orden de importación.
_CATALOGO: dict[str, TipoDeComandoDeclarado] = {}


def declarar_tipo(
    tipo: str,
    *,
    admite_online: bool,
    admite_offline: bool,
    permiso_offline: str | None = None,
    operacion_offline: OperacionObservable | None = None,
) -> TipoDeComandoDeclarado:
    """Declara `tipo` en el catálogo. Falla en el momento de la importación si el tipo ya estaba
    declarado, si admite `OFFLINE` sin declarar `permiso_offline` (o con uno en blanco) o si
    declara `permiso_offline` sin admitir `OFFLINE` (change 17, `design.md` D10)."""
    if tipo in _CATALOGO:
        raise TipoYaDeclaradoError(f"El tipo de comando {tipo!r} ya está declarado.")
    permiso = None if permiso_offline is None else permiso_offline.strip() or None
    if admite_offline and permiso is None:
        raise TipoOfflineSinPermisoError(
            f"El tipo {tipo!r} admite OFFLINE pero no declara `permiso_offline` (SEG-06)."
        )
    if not admite_offline and permiso_offline is not None:
        raise TipoOfflineSinPermisoError(
            f"El tipo {tipo!r} no admite OFFLINE pero declara `permiso_offline`."
        )
    declarado = TipoDeComandoDeclarado(
        tipo=tipo,
        admite_online=admite_online,
        admite_offline=admite_offline,
        permiso_offline=permiso,
        operacion_offline=operacion_offline,
    )
    _CATALOGO[tipo] = declarado
    return declarado


def tipo_declarado(tipo: str) -> TipoDeComandoDeclarado | None:
    return _CATALOGO.get(tipo)


def tipos_declarados() -> frozenset[str]:
    return frozenset(_CATALOGO.keys())
