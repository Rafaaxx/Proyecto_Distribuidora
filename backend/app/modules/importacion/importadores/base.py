"""Mecanismo común de los importadores (`design.md` D1, "Detalles derivados").

Cada fila se escribe llamando al servicio del módulo dueño dentro de un SAVEPOINT
(`begin_nested`): si la fila falla, se revierte solo ese savepoint, se anota su error
de fila y se sigue con la siguiente. Al terminar, el handler decide: con algún error
lanza `IMPORTACION_CON_ERRORES` y el bus revierte TODA la transacción (INV-01).

Un savepoint no es un `commit` (`CLAUDE.md` §4): el handler recibe una sesión que
prohíbe `commit`/`rollback`/`close` pero deja pasar `begin_nested`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.core.clock import Clock
from app.core.errors import DomainError
from app.modules.importacion.domain.informe import ErrorDeFila, traducir_error
from app.modules.importacion.domain.planilla import FilaPlanilla


class SesionConSavepoint(Protocol):
    """Lo único que el mecanismo común le pide a la sesión del bus."""

    def begin_nested(self) -> AbstractContextManager[object]: ...


@dataclass(frozen=True)
class ContextoDeImportacion:
    """Lo que un importador necesita del sobre del comando: la organización, el
    actor y el origen de la operación salen del sobre, nunca del archivo."""

    organizacion_id: UUID
    sesion: SesionConSavepoint
    reloj: Clock
    usuario_id: UUID
    dispositivo_id: UUID
    operation_id: UUID
    occurred_at: datetime


Importador = Callable[[ContextoDeImportacion, Sequence[FilaPlanilla]], list[ErrorDeFila]]
"""Escribe las filas por los servicios y devuelve los errores por fila (vacío si
todas entraron)."""


def ejecutar_en_savepoint(
    tipo: str,
    sesion: SesionConSavepoint,
    accion: Callable[[], None],
    *,
    fila: int | Callable[[DomainError], int],
    columna: Callable[[DomainError], str | None] | None = None,
    filas_de_lote: Sequence[int] | None = None,
) -> ErrorDeFila | None:
    """Ejecuta `accion` dentro de un savepoint. Un `DomainError` revierte solo ese
    savepoint y se traduce a error de fila (`None` si no falló); cualquier otra
    excepción (una falla de infraestructura) sube y el bus revierte todo.

    `fila` es la fila del informe o, si el error decide en cuál cae (un producto con
    varias presentaciones), una función del error. `columna` fuerza la columna cuando la
    tabla código -> columna no alcanza."""
    try:
        with sesion.begin_nested():
            accion()
    except DomainError as error:
        return traducir_error(
            tipo,
            fila(error) if callable(fila) else fila,
            error,
            filas_de_lote=filas_de_lote,
            columna=columna(error) if columna is not None else None,
        )
    return None


def procesar_filas(
    tipo: str,
    sesion: SesionConSavepoint,
    filas: Sequence[FilaPlanilla],
    accion: Callable[[FilaPlanilla], None],
    *,
    omitidas: dict[int, ErrorDeFila] | None = None,
    columna: Callable[[FilaPlanilla, DomainError], str | None] | None = None,
) -> list[ErrorDeFila]:
    """Ejecuta `accion` por fila dentro de un savepoint. Un `DomainError` revierte
    solo esa fila y se traduce a error de fila. Las filas de `omitidas` (p. ej.
    `FILA_DUPLICADA`) no se ejecutan y aportan su error en su lugar."""
    errores: list[ErrorDeFila] = []
    for fila in filas:
        if omitidas is not None and fila.fila in omitidas:
            errores.append(omitidas[fila.fila])
            continue
        error = ejecutar_en_savepoint(
            tipo,
            sesion,
            lambda fila=fila: accion(fila),  # type: ignore[misc]
            fila=fila.fila,
            columna=(lambda e, fila=fila: columna(fila, e)) if columna is not None else None,  # type: ignore[misc]
        )
        if error is not None:
            errores.append(error)
    return errores
