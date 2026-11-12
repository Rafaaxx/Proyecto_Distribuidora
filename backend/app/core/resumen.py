"""El resumen de una operación observada o rechazada que muestra la bandeja de revisión
(change 25, `design.md` D4). Lo declaran sin ciclos los módulos dueños de cada operación
(`ventas`, `cobranzas`, `proveedores`, `stock`) y lo consume `sync`: es un tipo neutro, sin
dependencias de ningún módulo.

También vive acá el registro de los resumidores por tipo de operación. Un módulo de negocio no
puede importar `sync` (contratos de import-linter, y `sync` no puede importar `ventas`,
`cobranzas`, `proveedores` ni `stock` sin abrir una cadena indirecta desde las `api.py`), así que
el punto de encuentro es `core`: cada módulo dueño registra su resumidor al importar su
`service.py` y `sync.service.resumir_operaciones` solo lo consulta."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ResumenDeOperacion:
    """`titulo` identifica la operación («Venta V01-000123»); `tercero` es el cliente o el
    proveedor; `total` es un importe como texto (`"31250.00"`, nunca un float); `momento` es
    cuándo ocurrió."""

    titulo: str
    tercero: str | None
    total: str | None
    momento: datetime


# La sesión de SQLAlchemy se tipa `Any` a propósito: `core.resumen` no puede importar SQLAlchemy
# (contrato "domain no importa infraestructura", que alcanza a los módulos que lo importan). Cada
# resumidor real recibe una `Session` tipada; `sync.service.resumir_operaciones` es la fachada
# tipada que usa el resto del módulo.
ResumidorDeOperacion = Callable[[UUID, Any, Sequence[UUID]], Mapping[UUID, ResumenDeOperacion]]
"""`funcion(organizacion_id, sesion, ids) -> {id: resumen}`: resume varias operaciones de un mismo
tipo con una cantidad de consultas que no crece con `ids`. Las que no existen o son de otra
organización no aparecen (INV-21)."""

_RESUMIDORES_DE_OPERACION: dict[str, ResumidorDeOperacion] = {}


def registrar_resumidor_de_operacion(operacion_tipo: str, funcion: ResumidorDeOperacion) -> None:
    """Registra el resumidor de un tipo de operación (`VENTA`, `COBRANZA`, ...); lo hace el
    `service.py` del módulo dueño al importarse."""
    _RESUMIDORES_DE_OPERACION[operacion_tipo] = funcion


def resumir_operaciones(
    organizacion_id: UUID, sesion: Any, operacion_tipo: str, ids: Sequence[UUID]
) -> dict[UUID, ResumenDeOperacion]:
    """Resumen de varias operaciones del mismo tipo, o `{}` si el tipo no tiene resumidor, no hay
    ids o ninguna existe en la organización (la bandeja muestra «Operación {tipo}»)."""
    resumidor = _RESUMIDORES_DE_OPERACION.get(operacion_tipo)
    if resumidor is None or not ids:
        return {}
    return dict(resumidor(organizacion_id, sesion, ids))


NumeradoraDeLineas = Callable[[UUID, Any, Sequence[UUID]], Mapping[UUID, int]]
"""`funcion(organizacion_id, sesion, linea_ids) -> {linea_id: número}` (desde 1): el número de
línea que la bandeja muestra («Línea 2») sin que `sync` importe al módulo dueño."""

_NUMERADORAS_DE_LINEAS: dict[str, NumeradoraDeLineas] = {}


def registrar_numeradora_de_lineas(operacion_tipo: str, funcion: NumeradoraDeLineas) -> None:
    """Registra quién numera las líneas de un tipo de operación; lo hace el `service.py` dueño."""
    _NUMERADORAS_DE_LINEAS[operacion_tipo] = funcion


def numerar_lineas(
    organizacion_id: UUID, sesion: Any, operacion_tipo: str, linea_ids: Sequence[UUID]
) -> dict[UUID, int]:
    """Número de cada línea (desde 1) del tipo de operación, o `{}` si el tipo no tiene numeradora,
    no hay ids o ninguna existe en la organización (INV-21)."""
    numeradora = _NUMERADORAS_DE_LINEAS.get(operacion_tipo)
    if numeradora is None or not linea_ids:
        return {}
    return dict(numeradora(organizacion_id, sesion, linea_ids))


# --- Resumen de lo que envió el teléfono en un comando rechazado (change 25, D4, D6) --------------

SIN_REFERENCIA = "(no existe)"
"""Lo que se muestra de un cliente, una venta o un producto que el contenido nombra y ya no existe
en la organización (o es de otra: INV-21)."""


@dataclass(frozen=True)
class LineaResumida:
    """Una línea de lo que envió el teléfono: producto (por nombre), cantidad e importe bruto."""

    producto: str | None
    cantidad: int | None
    importe: str | None


@dataclass(frozen=True)
class MedioResumido:
    """Un medio de la cobranza que envió el teléfono: nombre del medio e importe."""

    medio: str | None
    importe: str | None


@dataclass(frozen=True)
class ResumenDeContenido:
    """Lo que dice un comando rechazado, legible: sin fallar si el contenido está mal formado
    (los campos que no se pueden leer quedan nulos). Los importes viajan como texto."""

    titulo: str
    cliente: str | None = None
    numero: str | None = None
    total: str | None = None
    lineas: tuple[LineaResumida, ...] = ()
    medios: tuple[MedioResumido, ...] = ()


ResumidorDeContenido = Callable[[UUID, Any, Sequence[Mapping[str, Any]]], list[ResumenDeContenido]]
"""`funcion(organizacion_id, sesion, contenidos) -> [resumen]`, uno por contenido y en el mismo
orden, con una cantidad de consultas que no crece con la lista. No lanza por un contenido mal
formado ni por una referencia inexistente."""

_RESUMIDORES_DE_CONTENIDO: dict[str, ResumidorDeContenido] = {}


def registrar_resumidor_de_contenido(tipo_comando: str, funcion: ResumidorDeContenido) -> None:
    """Registra el resumidor del contenido de un tipo de comando (`VENTA_CONFIRMAR`, ...); lo hace
    el `service.py` del módulo dueño del comando al importarse."""
    _RESUMIDORES_DE_CONTENIDO[tipo_comando] = funcion


def resumir_contenidos(
    organizacion_id: UUID, sesion: Any, tipo_comando: str, contenidos: Sequence[Mapping[str, Any]]
) -> list[ResumenDeContenido | None]:
    """Un resumen por contenido, o `None` en cada uno si el tipo no tiene resumidor."""
    resumidor = _RESUMIDORES_DE_CONTENIDO.get(tipo_comando)
    if resumidor is None:
        return [None] * len(contenidos)
    return list(resumidor(organizacion_id, sesion, contenidos))


# --- Vínculo de una resolución con la operación que la corrige (change 25, D7) ----------------


LectorDeVinculo = Callable[[UUID, Any, UUID], bool]
"""`funcion(organizacion_id, sesion, id) -> bool` (`False` si no existe en la
organización: INV-21)."""

_LECTORES_DE_VINCULO: dict[str, LectorDeVinculo] = {}


def registrar_lector_de_vinculo(vinculo_tipo: str, funcion: LectorDeVinculo) -> None:
    """Registra el lector de un tipo de vínculo (`VENTA`, `COBRANZA`); lo hace el `service.py` del
    módulo dueño al importarse."""
    _LECTORES_DE_VINCULO[vinculo_tipo] = funcion


def leer_vinculo(organizacion_id: UUID, sesion: Any, vinculo_tipo: str, vinculo_id: UUID) -> bool:
    """Dice si la operación vinculada existe en la organización, según el lector de su módulo.
    Falla cerrado: sin lector registrado es un error de programación, no un vínculo que
    se acepta sin comprobar."""
    lector = _LECTORES_DE_VINCULO.get(vinculo_tipo)
    if lector is None:
        raise RuntimeError(f"Ningún módulo registró el lector del vínculo {vinculo_tipo!r}.")
    return lector(organizacion_id, sesion, vinculo_id)


# --- Lectura defensiva del contenido de un comando rechazado ----------------------------------
# Lo que envió un teléfono puede venir mal formado: estas funciones devuelven `None` (o vacío) en
# vez de lanzar, y los resumidores de los módulos dueños las usan para no fallar nunca.

_PATRON_IMPORTE = re.compile(r"^-?\d+(\.\d+)?$")


def como_mapa(valor: object) -> Mapping[str, Any]:
    return valor if isinstance(valor, Mapping) else {}


def como_lista(valor: object) -> list[Any]:
    return valor if isinstance(valor, list) else []


def como_uuid(valor: object) -> UUID | None:
    if not isinstance(valor, str):
        return None
    try:
        return UUID(valor)
    except ValueError:
        return None


def como_texto(valor: object) -> str | None:
    return valor if isinstance(valor, str) and valor.strip() else None


def como_entero(valor: object) -> int | None:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


def como_importe(valor: object) -> str | None:
    """Un importe viaja como texto decimal (`"31250.00"`); cualquier otra cosa es `None`."""
    return valor if isinstance(valor, str) and _PATRON_IMPORTE.match(valor) else None


def nombre_o_sin_referencia(nombres: Mapping[UUID, str], referencia: object) -> str | None:
    """El nombre de lo que el contenido nombra: `None` si no nombra nada legible y
    `SIN_REFERENCIA` si lo nombra pero no existe en la organización."""
    id_ = como_uuid(referencia)
    if id_ is None:
        return None
    return nombres.get(id_, SIN_REFERENCIA)
