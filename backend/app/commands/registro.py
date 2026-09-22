"""Registro explícito de handlers por `(tipo, version)` (`design.md` D3,
`02` §6.3, §6.6).

Un handler se registra con un decorador que asocia `(tipo, version)` a una
función y a un esquema Pydantic que valida el contenido antes de ejecutarla.
El arranque puebla este registro importando los módulos de negocio que
declaran sus handlers (`identidad/commands.py`, etc.) -- un handler que
nadie importó simplemente no está acá, y `resolver_handler` lo trata igual
que un tipo que nunca existió: falla en el arranque de la aplicación
(porque el módulo dueño no se importó donde debía) y no en producción con
un comando real (`design.md` D3, alternativa descartada de descubrimiento
automático).

No importa FastAPI ni SQLAlchemy: solo Pydantic para el esquema de
contenido (`design.md` D3, `import_linter`: `commands-no-modulos`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from app.commands.errores import (
    ContenidoDeComandoInvalidoError,
    TipoDeComandoDesconocidoError,
    VersionDeComandoSinHandlerError,
)
from app.commands.sobre import SobreComando

HandlerFuncion = Callable[[SobreComando, BaseModel], object]


@dataclass(frozen=True)
class HandlerRegistrado:
    """Un handler registrado, con el esquema que valida su contenido."""

    tipo: str
    version: int
    esquema: type[BaseModel]
    funcion: HandlerFuncion


class TipoYVersionYaRegistradosError(ValueError):
    """Dos handlers intentaron registrarse para el mismo `(tipo, version)`
    (error de programación, detectado al importar los módulos de negocio)."""


# Puebla el arranque de la aplicación importando los módulos de negocio que
# llaman a `registrar_handler` (`design.md` D3). Las pruebas unitarias
# aíslan este diccionario con `monkeypatch` para no depender del orden de
# importación ni filtrar registros entre pruebas.
_REGISTRO: dict[tuple[str, int], HandlerRegistrado] = {}


def registrar_handler[EsquemaContenido: BaseModel](
    tipo: str, version: int, esquema: type[EsquemaContenido]
) -> Callable[[Callable[[SobreComando, EsquemaContenido], object]], HandlerFuncion]:
    """Decorador que registra `funcion` como el handler de `(tipo,
    version)`, validado por `esquema`. Falla en el momento de la
    importación (arranque) si ya había un handler para esa combinación."""

    def decorador(funcion: Callable[[SobreComando, EsquemaContenido], object]) -> HandlerFuncion:
        clave = (tipo, version)
        if clave in _REGISTRO:
            raise TipoYVersionYaRegistradosError(
                f"Ya hay un handler registrado para {tipo!r} versión {version}."
            )
        # El handler concreto valida un `EsquemaContenido` (subtipo de
        # `BaseModel`); `HandlerRegistrado.funcion` lo guarda como
        # `Callable[[SobreComando, BaseModel], object]` porque el registro
        # es heterogéneo (cada entrada tiene su propio subtipo). El
        # llamador siempre pasa una instancia ya validada de `esquema`
        # (`validar_contenido`), así que el tipo real coincide en runtime.
        _REGISTRO[clave] = HandlerRegistrado(
            tipo=tipo,
            version=version,
            esquema=esquema,
            funcion=funcion,  # type: ignore[arg-type]
        )
        return funcion  # type: ignore[return-value]

    return decorador


def _versiones_registradas(tipo: str) -> list[int]:
    return [version for (tipo_registrado, version) in _REGISTRO if tipo_registrado == tipo]


def resolver_handler(tipo: str, version: int) -> HandlerRegistrado:
    """Resuelve el handler de `(tipo, version)`.

    Un tipo sin ninguna versión registrada es "desconocido"
    (`TipoDeComandoDesconocidoError`); un tipo conocido sin handler para
    ESA versión puntual es distinto (`VersionDeComandoSinHandlerError`) --
    la spec exige distinguirlos porque el primero nunca fue implementado y
    el segundo fue retirado o todavía no llegó (`02` §6.6)."""
    if not _versiones_registradas(tipo):
        raise TipoDeComandoDesconocidoError(f"El tipo de comando {tipo!r} no está registrado.")
    clave = (tipo, version)
    if clave not in _REGISTRO:
        raise VersionDeComandoSinHandlerError(
            f"No hay handler registrado para {tipo!r} versión {version}."
        )
    return _REGISTRO[clave]


def validar_contenido(handler: HandlerRegistrado, contenido: Mapping[str, object]) -> BaseModel:
    """Valida `contenido` contra el esquema de `handler`. Un dato
    obligatorio faltante (o cualquier otra violación del esquema) se
    traduce a `ContenidoDeComandoInvalidoError` (SYN-06): el comando se
    rechaza como malformado, sin efectos.

    `Mapping`, no `dict` (change 04, grupo 8, descubrimiento de `mypy`):
    `dict` es invariante en su tipo de valor, así que un
    `dict[str, ContenidoComando]` (el tipo real de `SobreComando.contenido`)
    no encajaría como argumento de un parámetro `dict[str, object]` sin un
    `type: ignore`. `Mapping` es covariante y acepta ambos sin perder
    precisión de tipos en el llamador."""
    try:
        return handler.esquema.model_validate(contenido)
    except ValidationError as error:
        raise ContenidoDeComandoInvalidoError(
            f"El contenido no cumple el esquema de {handler.tipo!r} "
            f"versión {handler.version}: {error}"
        ) from error
