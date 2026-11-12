"""Reglas puras de la rendición de una jornada (RUT-06, RUT-07, STK-04, INV-04; `design.md` D2
y D4; change 24): el conjunto a contar, el esperado, la diferencia y la validación del conteo.

No importa infraestructura (`02` §5.2): el caso de uso lee los saldos y los movimientos de la
ventana por SQL y le pasa a estas funciones solo los datos. Los productos son cualquier valor
comparable por igualdad y por `str` (en producción, `UUID`; los casos compartidos usan texto).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from app.modules.stock.domain.errores import (
    CantidadInvalidaError,
    ConteoIncompletoError,
    EsperadoDifiereError,
    ObservacionInvalidaError,
    ProductoRepetidoError,
    RechazosPendientesError,
)

MAXIMO_OBSERVACION = 500


def validar_sin_rechazos_pendientes(cantidad: int) -> None:
    """RUT-05, SYN-06 (change 25, D9 = B): con operaciones rechazadas sin resolver en la jornada
    no se rinde, porque el esperado no incluiría lo que el vendedor sí entregó y el faltante
    saldría sin explicación (o se descontaría dos veces al cargar la corrección). El detalle lleva
    la cantidad. Una cantidad negativa es un error de quien la calcula."""
    if cantidad < 0:
        raise ValueError("La cantidad de rechazos pendientes no puede ser negativa.")
    if cantidad > 0:
        raise RechazosPendientesError(
            f"La jornada tiene {cantidad} "
            f"{'operación rechazada' if cantidad == 1 else 'operaciones rechazadas'} "
            "sin resolver: hay que resolverlas antes de rendir.",
            extension={"rechazos_pendientes": cantidad},
        )


@dataclass(frozen=True)
class LineaContada[P]:
    """Una línea del conteo tal como llega: lo contado y el esperado que vio quien contó."""

    producto: P
    contada: int
    esperada: int


@dataclass(frozen=True)
class LineaRendida[P]:
    """Una línea validada: el esperado es el del servidor y la diferencia es contado menos
    esperado, con signo."""

    producto: P
    esperado: int
    contado: int
    diferencia: int


def conjunto_a_contar[P](saldos: Mapping[P, int], *, con_movimiento: Collection[P]) -> frozenset[P]:
    """RUT-06 (D2): los productos con saldo distinto de cero en la ubicación (también
    negativo) o con algún movimiento en ella durante la jornada, aunque hoy su saldo sea
    cero."""
    return frozenset(p for p, saldo in saldos.items() if saldo != 0) | frozenset(con_movimiento)


def esperado(*, al_abrir: int, ingresos: int, ventas: int, anulaciones: int, otros: int) -> int:
    """RUT-07 (D4): al abrir + ingresos − ventas + anulaciones + otros."""
    return al_abrir + ingresos - ventas + anulaciones + otros


def diferencia(*, contada: int, esperada: int) -> int:
    """INV-04, RUT-06 (D5): contado menos esperado, con signo."""
    return contada - esperada


def productos_faltantes[P](conjunto: Iterable[P], *, contados: Iterable[P]) -> list[P]:
    """Los productos del conjunto que el conteo no trae, en el orden del conjunto (los
    productos contados de más son sobrantes y no cuentan)."""
    presentes = set(contados)
    return [p for p in conjunto if p not in presentes]


def _es_entero(valor: object) -> bool:
    return type(valor) is int


def validar_conteo[P](
    *,
    conjunto: Collection[P],
    esperados: Mapping[P, int],
    lineas: Sequence[LineaContada[P]],
) -> list[LineaRendida[P]]:
    """RUT-06 (D2). Valida el conteo contra el conjunto a contar y los esperados del servidor
    (`esperados`; un producto ausente espera cero) y devuelve una línea por producto, en el
    orden recibido. Orden de los rechazos: `CANTIDAD_INVALIDA` y `PRODUCTO_REPETIDO` (forma),
    `CONTEO_INCOMPLETO` y al final `ESPERADO_DIFIERE`."""
    vistos: set[P] = set()
    for linea in lineas:
        if not _es_entero(linea.contada) or linea.contada < 0 or not _es_entero(linea.esperada):
            raise CantidadInvalidaError(
                "La cantidad contada debe ser un entero mayor o igual que cero."
            )
        if linea.producto in vistos:
            raise ProductoRepetidoError("Un producto no puede repetirse en el conteo.")
        vistos.add(linea.producto)

    faltan = sorted(productos_faltantes(conjunto, contados=vistos), key=str)
    if faltan:
        raise ConteoIncompletoError(
            "Falta contar algún producto de la ubicación.", extension={"productos": faltan}
        )

    actuales = {p: esperados.get(p, 0) for p in (*conjunto, *vistos)}
    distintos = sorted((x.producto for x in lineas if x.esperada != actuales[x.producto]), key=str)
    if distintos:
        raise EsperadoDifiereError(
            "El stock cambió mientras se contaba.",
            extension={"distintos": distintos, "esperados": actuales},
        )

    return [
        LineaRendida(
            producto=x.producto,
            esperado=actuales[x.producto],
            contado=x.contada,
            diferencia=diferencia(contada=x.contada, esperada=actuales[x.producto]),
        )
        for x in lineas
    ]


def normalizar_observacion(observacion: str | None) -> str | None:
    """D2: recortada, vacía equivale a `None`, hasta 500 caracteres (`OBSERVACION_INVALIDA`)."""
    if observacion is None:
        return None
    recortada = observacion.strip()
    if len(recortada) > MAXIMO_OBSERVACION:
        raise ObservacionInvalidaError(
            f"La observación admite hasta {MAXIMO_OBSERVACION} caracteres."
        )
    return recortada or None
