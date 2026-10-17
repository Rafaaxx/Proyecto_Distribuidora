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

No importa FastAPI ni módulos de negocio: Pydantic para el esquema de
contenido y SQLAlchemy solo para el tipo de la sesión (`design.md` D3, D9,
`import_linter`: `commands-no-modulos`).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.commands.errores import (
    ContenidoDeComandoInvalidoError,
    TipoDeComandoDesconocidoError,
    VersionDeComandoSinHandlerError,
)
from app.commands.sobre import SobreComando
from app.core.clock import Clock

SesionDeHandler = Session
"""Tipo de la sesión que el bus entrega a un handler (`design.md` D9).

En ejecución es la `SesionSinCommit` de `sync/service.py`: un envoltorio que
delega todo en la `Session` real salvo `commit`, `rollback` y `close`, que
rechaza (`CLAUDE.md` §4: los handlers no confirman). Se tipa como `Session`
porque los servicios de negocio, a los que el handler se la reenvía, piden
`Session`; el envoltorio no se puede nombrar acá sin importar un módulo de
negocio (contrato `commands-no-modulos`)."""


class HandlerFuncion[EsquemaContenido: BaseModel](Protocol):
    """Firma de un handler registrado (`design.md` D9): sobre y contenido ya
    validado por posición; `sesion` y `reloj` por nombre. El bus pasa los dos
    siempre, por REST y por el lote."""

    def __call__(
        self,
        sobre: SobreComando,
        contenido: EsquemaContenido,
        *,
        sesion: SesionDeHandler,
        reloj: Clock,
    ) -> object: ...


class FirmaDeHandlerInvalidaError(TypeError):
    """Un handler se intentó registrar sin `sesion` y `reloj` como parámetros
    de palabra clave (error de programación, detectado al importar)."""


@dataclass(frozen=True)
class HandlerRegistrado:
    """Un handler registrado, con el esquema que valida su contenido."""

    tipo: str
    version: int
    esquema: type[BaseModel]
    funcion: HandlerFuncion[BaseModel]


class TipoYVersionYaRegistradosError(ValueError):
    """Dos handlers intentaron registrarse para el mismo `(tipo, version)`
    (error de programación, detectado al importar los módulos de negocio)."""


# Puebla el arranque de la aplicación importando los módulos de negocio que
# llaman a `registrar_handler` (`design.md` D3). Las pruebas unitarias
# aíslan este diccionario con `monkeypatch` para no depender del orden de
# importación ni filtrar registros entre pruebas.
_REGISTRO: dict[tuple[str, int], HandlerRegistrado] = {}


def _exigir_firma_de_handler(tipo: str, funcion: Callable[..., object]) -> None:
    """Falla si `funcion` no recibe `sesion` y `reloj` por nombre: el bus los
    pasa siempre y una función de dos argumentos fallaría recién con un comando
    real (`design.md` D9)."""
    parametros = inspect.signature(funcion).parameters
    faltantes = [
        nombre
        for nombre in ("sesion", "reloj")
        if nombre not in parametros
        or parametros[nombre].kind not in (inspect.Parameter.KEYWORD_ONLY,)
    ]
    if faltantes:
        raise FirmaDeHandlerInvalidaError(
            f"El handler de {tipo!r} debe declarar {', '.join(faltantes)} como "
            "parámetros de palabra clave (`*, sesion, reloj`)."
        )


def registrar_handler[EsquemaContenido: BaseModel](
    tipo: str, version: int, esquema: type[EsquemaContenido]
) -> Callable[[HandlerFuncion[EsquemaContenido]], HandlerFuncion[EsquemaContenido]]:
    """Decorador que registra `funcion` como el handler de `(tipo,
    version)`, validado por `esquema`. Falla en el momento de la
    importación (arranque) si ya había un handler para esa combinación o si
    la función no tiene la firma de `HandlerFuncion`."""

    def decorador(
        funcion: HandlerFuncion[EsquemaContenido],
    ) -> HandlerFuncion[EsquemaContenido]:
        clave = (tipo, version)
        if clave in _REGISTRO:
            raise TipoYVersionYaRegistradosError(
                f"Ya hay un handler registrado para {tipo!r} versión {version}."
            )
        _exigir_firma_de_handler(tipo, funcion)
        # El registro es heterogéneo (cada entrada tiene su propio subtipo de
        # `BaseModel`); `validar_contenido` siempre pasa una instancia ya
        # validada de `esquema`, así que el tipo real coincide en ejecución.
        _REGISTRO[clave] = HandlerRegistrado(
            tipo=tipo,
            version=version,
            esquema=esquema,
            funcion=cast(HandlerFuncion[BaseModel], funcion),
        )
        return funcion

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
