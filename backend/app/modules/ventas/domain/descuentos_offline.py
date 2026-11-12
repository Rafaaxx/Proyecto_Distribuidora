"""Descuentos y autorizaciones de una venta sin conexión (change 18b, tarea 10.1; `design.md` D9 y
D10; DSC-08, DSC-09, SYN-05, SYN-06, INV-14, INV-17). Funciones puras: sin infraestructura.

Principio (SYN-05, INV-17): una venta sin conexión no se rechaza por lo que el dispositivo no pudo
saber. Solo se rechaza lo malformado (`TOTALES_INCONSISTENTES`); los descuentos del dispositivo se
congelan y lo que el servidor ve distinto se observa: una sola `DESCUENTO_DIFIERE` por venta con
las causas, y una `AUTORIZACION_OFFLINE` por autorización resuelta con PIN o permiso propio."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.ventas.domain.descuentos import DescuentoDeLinea, _a_detalle, _clave
from app.modules.ventas.domain.errores import TotalesInconsistentesError
from app.modules.ventas.domain.observaciones import ObservacionDeVenta

CODIGO_DESCUENTO_DIFIERE = "DESCUENTO_DIFIERE"
CODIGO_AUTORIZACION_OFFLINE = "AUTORIZACION_OFFLINE"

_CERO = Decimal("0.00")
_UNO = Decimal("1")

_CAUSA_POR_CODIGO_DE_ERROR = {
    "AUTORIZACION_REQUERIDA": "TOPE",
    "PERMISO_REQUERIDO": "PERMISO",
    "DESCUENTO_MANUAL_DESHABILITADO": "DESHABILITADO",
    "MOTIVO_REQUERIDO": "MOTIVO",
    "AUTORIZADOR_SIN_PERMISO": "AUTORIZADOR_SIN_PERMISO",
}
"""Cada rechazo que el descuento manual tendría con conexión (DSC-06) es, sin conexión, una causa
de `DESCUENTO_DIFIERE` (D10 punto 4)."""


@dataclass(frozen=True)
class LineaEnviada:
    """Una línea tal como la registró el dispositivo: su bruto y sus descuentos."""

    linea_id: UUID
    importe_bruto: Decimal
    descuentos: Sequence[DescuentoDeLinea]


def neto_de_linea(linea: LineaEnviada) -> Decimal:
    """INV-14: neto = bruto - suma de los descuentos de la línea (modo `A`: sin IVA aparte)."""
    return linea.importe_bruto - sum((d.importe for d in linea.descuentos), _CERO)


def verificar_descuentos_offline(lineas: Sequence[LineaEnviada], total_enviado: Decimal) -> None:
    """D10 punto 1, paso 0 de D18: lo malformado se rechaza con `TOTALES_INCONSISTENTES` (el
    código del 18a). Un descuento con importe no positivo (DSC-07: los de cero no se informan) o
    con más de dos decimales, o con un porcentaje fuera de (0, 1] (lo exige la base);
    más de un `MANUAL` por línea (DSC-08); un `AUTOMATICO` sin regla o un `MANUAL` con regla;
    una línea cuyos descuentos superan su bruto (neto negativo); un total distinto de la suma de
    los netos (INV-14). El contenido no trae el neto de cada línea: el neto es bruto - descuentos,
    así que no puede discrepar de ellos."""
    for linea in lineas:
        manuales = 0
        for descuento in linea.descuentos:
            if descuento.importe <= _CERO:
                raise TotalesInconsistentesError(
                    "El importe de un descuento debe ser mayor que cero.",
                    extension={"linea_id": str(linea.linea_id)},
                )
            if descuento.importe != descuento.importe.quantize(_CERO):
                raise TotalesInconsistentesError(
                    "El importe de un descuento no puede tener más de dos decimales.",
                    extension={"linea_id": str(linea.linea_id)},
                )
            if descuento.porcentaje is not None and not _CERO < descuento.porcentaje <= _UNO:
                raise TotalesInconsistentesError(
                    "El porcentaje de un descuento debe ser mayor que cero y a lo sumo uno.",
                    extension={"linea_id": str(linea.linea_id)},
                )
            if descuento.origen == "MANUAL":
                manuales += 1
                if descuento.regla_id is not None:
                    raise TotalesInconsistentesError(
                        "Un descuento manual no lleva regla.",
                        extension={"linea_id": str(linea.linea_id)},
                    )
            elif descuento.regla_id is None:
                raise TotalesInconsistentesError(
                    "Un descuento automático lleva la regla que lo originó.",
                    extension={"linea_id": str(linea.linea_id)},
                )
        if manuales > 1:
            raise TotalesInconsistentesError(
                "Una línea lleva a lo sumo un descuento manual.",
                extension={"linea_id": str(linea.linea_id)},
            )
        if neto_de_linea(linea) < _CERO:
            raise TotalesInconsistentesError(
                "Los descuentos de una línea superan su importe bruto.",
                extension={"linea_id": str(linea.linea_id)},
            )
    total_calculado = sum((neto_de_linea(linea) for linea in lineas), _CERO)
    if total_enviado != total_calculado:
        raise TotalesInconsistentesError(
            "El total enviado no es la suma de los netos de las líneas.",
            extension={"total_calculado": str(total_calculado)},
        )


def diferencias_de_calculo(
    enviados: Mapping[UUID, Sequence[DescuentoDeLinea]],
    calculados: Mapping[UUID, Sequence[DescuentoDeLinea]],
) -> list[dict[str, object]]:
    """Causa `CALCULO` (D10): una entrada por línea cuyos descuentos del dispositivo difieren de
    los que calcula el servidor con las reglas vigentes al `occurred_at` y los porcentajes
    manuales enviados (origen, regla, porcentaje o importe; el orden no cuenta). `esperado` es lo
    que registró el dispositivo y `calculado` lo del servidor."""
    diferencias: list[dict[str, object]] = []
    for linea_id in dict.fromkeys([*enviados, *calculados]):
        del_dispositivo = list(enviados.get(linea_id, ()))
        del_servidor = list(calculados.get(linea_id, ()))
        if sorted(map(_clave, del_dispositivo)) != sorted(map(_clave, del_servidor)):
            diferencias.append(
                {
                    "causa": "CALCULO",
                    "linea_id": str(linea_id),
                    "esperado": [_a_detalle(d) for d in del_dispositivo],
                    "calculado": [_a_detalle(d) for d in del_servidor],
                }
            )
    return diferencias


def causa_de_rechazo_del_manual(codigo_de_error: str) -> str | None:
    """La causa de `DESCUENTO_DIFIERE` que corresponde al rechazo que el descuento manual tendría
    con conexión (`TOPE`, `PERMISO`, `DESHABILITADO`, `MOTIVO`, `AUTORIZADOR_SIN_PERMISO`); `None`
    si el código no es del descuento manual (un error ajeno sube tal cual)."""
    return _CAUSA_POR_CODIGO_DE_ERROR.get(codigo_de_error)


_CAUSAS_CON_DATOS_DE_TOPE = frozenset({"TOPE", "AUTORIZADOR_SIN_PERMISO"})


def detalle_de_causa_del_manual(
    causa: str, *, porcentaje: Decimal, tope: Decimal
) -> dict[str, object]:
    """El detalle de una causa del descuento manual: `TOPE` y `AUTORIZADOR_SIN_PERMISO` (que solo
    se da sobre el tope) llevan el porcentaje evaluado y el tope de hoy; `PERMISO`,
    `DESHABILITADO` y `MOTIVO` no tienen datos de tope que informar."""
    if causa in _CAUSAS_CON_DATOS_DE_TOPE:
        return {"causa": causa, "porcentaje_maximo": f"{porcentaje:.6f}", "tope": f"{tope:.6f}"}
    return {"causa": causa}


def observacion_descuento_difiere(
    causas: Sequence[dict[str, object]],
) -> ObservacionDeVenta | None:
    """D10 punto 4: una sola `DESCUENTO_DIFIERE` por venta, con todas las causas en el detalle;
    sin causas no hay observación."""
    if not causas:
        return None
    return ObservacionDeVenta(CODIGO_DESCUENTO_DIFIERE, {"causas": list(causas)})


def autorizacion_declarada_de_descuento(
    *,
    usuario_id: UUID,
    autorizador_enviado: UUID | None,
    usuario_puede_autorizar: bool,
    porcentaje_maximo: Decimal,
    tope: Decimal,
) -> tuple[str | None, UUID | None]:
    """Cómo se autorizó el descuento manual del dispositivo (decisiones del usuario, 2026-10-23,
    puntos 3 y 4). Otra persona como autorizador: `PIN_SUPERVISOR`. El mismo usuario, o ninguno y
    el usuario con `AUTORIZAR_DESCUENTO` y un porcentaje sobre el tope de hoy: `PERMISO_PROPIO`.
    Un autorizador enviado se observa aunque hoy el porcentaje esté dentro del tope. Si no, no
    hubo autorización (`None`). Devuelve `(resolución, autorizador)`."""
    if autorizador_enviado is not None:
        if autorizador_enviado == usuario_id:
            return "PERMISO_PROPIO", usuario_id
        return "PIN_SUPERVISOR", autorizador_enviado
    if usuario_puede_autorizar and porcentaje_maximo > tope:
        return "PERMISO_PROPIO", usuario_id
    return None, None


def observacion_autorizacion_offline(
    *,
    tipo: str,
    resolucion: str,
    autorizador_id: UUID | None,
    autorizador_con_permiso: bool,
) -> ObservacionDeVenta:
    """D9 (SYN-07): `AUTORIZACION_OFFLINE`, una por autorización sin conexión resuelta con PIN o
    permiso propio. `tipo` es `DESCUENTO` o `CREDITO`; `autorizador_con_permiso` es el permiso
    que el autorizador tiene HOY (si lo perdió la venta se acepta igual, SYN-05)."""
    return ObservacionDeVenta(
        CODIGO_AUTORIZACION_OFFLINE,
        {
            "tipo": tipo,
            "resolucion": resolucion,
            "autorizador_id": None if autorizador_id is None else str(autorizador_id),
            "autorizador_con_permiso": autorizador_con_permiso,
        },
    )
