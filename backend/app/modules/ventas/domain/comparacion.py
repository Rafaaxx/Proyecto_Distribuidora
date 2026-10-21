"""Comparación de lo esperado con lo resuelto (TR-10, PRC-20, PRC-23, VTA-10, SYN-06, SYN-07;
`design.md` D2, D7).

Con conexión el servidor resuelve todo de nuevo y rechaza con `PRECIO_DIFIERE` si cualquier valor
que vio el usuario difiere, devolviendo los suyos. Sin conexión congela lo enviado y solo
comprueba que los importes enviados sean los que da el motor sobre esos valores
(`TOTALES_INCONSISTENTES`). Funciones puras: sin infraestructura."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.ventas.domain.errores import (
    PrecioDifiereError,
    ProductoSinPrecioError,
    TotalesInconsistentesError,
    VersionNoPermitidaError,
)
from app.modules.ventas.domain.observaciones import ObservacionDeVenta

CODIGO_LISTA_NO_VIGENTE = "LISTA_NO_VIGENTE"


@dataclass(frozen=True)
class ValoresDeLinea:
    """Lo que una línea congela de su precio (PRC-23): versión, precio de referencia, unidades
    de referencia y bruto (PRC-22)."""

    linea_id: UUID
    lista_version_id: UUID
    precio_referencia: Decimal
    unidades_referencia: int
    importe_bruto: Decimal


@dataclass(frozen=True)
class ProductoSinPrecio:
    producto_id: UUID
    nombre: str


def _a_detalle(valores: ValoresDeLinea) -> dict[str, object]:
    return {
        "linea_id": str(valores.linea_id),
        "lista_version_id": str(valores.lista_version_id),
        "precio_referencia": str(valores.precio_referencia),
        "unidades_referencia": valores.unidades_referencia,
        "importe_bruto": str(valores.importe_bruto),
    }


def comparar_con_esperado(
    esperadas: Sequence[ValoresDeLinea],
    resueltas: Sequence[ValoresDeLinea],
    total_esperado: Decimal,
    total_resuelto: Decimal,
) -> None:
    """D2 con conexión: las líneas se comparan por identificador (no por posición) y el total
    también; cualquier diferencia, o una línea sin valores esperados, rechaza con
    `PRECIO_DIFIERE` y los valores del servidor en el detalle."""
    por_linea = {valores.linea_id: valores for valores in esperadas}
    iguales = (
        len(por_linea) == len(esperadas)
        and len(esperadas) == len(resueltas)
        and all(por_linea.get(resuelta.linea_id) == resuelta for resuelta in resueltas)
        and total_esperado == total_resuelto
    )
    if iguales:
        return
    raise PrecioDifiereError(
        "El precio o el total difieren de lo que vio el usuario: se confirma con los valores "
        "del servidor.",
        extension={
            "lineas": [_a_detalle(resuelta) for resuelta in resueltas],
            "total": str(total_resuelto),
        },
    )


def verificar_productos_con_precio(sin_precio: Sequence[ProductoSinPrecio]) -> None:
    """D7 con conexión: un producto sin precio en la versión rechaza la venta entera."""
    if not sin_precio:
        return
    raise ProductoSinPrecioError(
        "Algún producto no tiene precio en la versión de la lista.",
        extension={
            "productos": [
                {"producto_id": str(producto.producto_id), "nombre": producto.nombre}
                for producto in sin_precio
            ]
        },
    )


def verificar_totales_offline(
    enviadas: Sequence[ValoresDeLinea],
    brutos_del_motor: Mapping[UUID, Decimal],
    total_enviado: Decimal,
    total_calculado: Decimal,
) -> None:
    """D2 sin conexión: el bruto enviado de cada línea y el total deben ser los que da el motor
    compartido sobre los valores enviados; si no, el comando está malformado (SYN-06)."""
    for valores in enviadas:
        if brutos_del_motor.get(valores.linea_id) != valores.importe_bruto:
            raise TotalesInconsistentesError(
                "El bruto enviado de una línea no es el que da el cálculo sobre su precio.",
                extension={"linea_id": str(valores.linea_id)},
            )
    if total_enviado != total_calculado:
        raise TotalesInconsistentesError(
            "El total enviado no es el que da el cálculo.",
            extension={"total_calculado": str(total_calculado)},
        )


def verificar_version_uniforme(
    version_de_la_cabecera: UUID | None, versiones_de_las_lineas: Sequence[UUID]
) -> None:
    """D1 sin conexión (decisión del usuario, 2026-10-20): todas las líneas llevan la misma versión
    de lista y, si la cabecera la nombra, es esa. Con versiones mezcladas el comando es
    inconsistente (SYN-06, PRC-23) y se rechaza con `VERSION_NO_PERMITIDA`. Con conexión la
    comparación de D2 ya lo exige (`PRECIO_DIFIERE`)."""
    versiones = set(versiones_de_las_lineas)
    if version_de_la_cabecera is not None:
        versiones.add(version_de_la_cabecera)
    if len(versiones) > 1:
        raise VersionNoPermitidaError(
            "Todas las líneas deben llevar la misma versión de la lista, la de la cabecera "
            "(PRC-23)."
        )


def verificar_unidades_de_referencia(enviadas: Sequence[ValoresDeLinea]) -> None:
    """D2 sin conexión: las unidades de referencia que congela el dispositivo son de 1 en adelante
    (la base lo exige, `ck_venta_linea__unidades_referencia`); otra cosa es un comando malformado
    (SYN-06) y no se calcula nada con ella."""
    for valores in enviadas:
        if valores.unidades_referencia < 1:
            raise TotalesInconsistentesError(
                "Las unidades de referencia de una línea deben ser 1 o más.",
                extension={"linea_id": str(valores.linea_id)},
            )


def observacion_lista_no_vigente(
    version_enviada_id: UUID, version_vigente_id: UUID | None
) -> ObservacionDeVenta | None:
    """D7 sin conexión: una vez por venta, si la versión enviada no es la vigente al momento
    para la lista aplicable (SYN-07)."""
    if version_enviada_id == version_vigente_id:
        return None
    return ObservacionDeVenta(
        CODIGO_LISTA_NO_VIGENTE,
        {
            "version_enviada_id": str(version_enviada_id),
            "version_vigente_id": None if version_vigente_id is None else str(version_vigente_id),
        },
    )
