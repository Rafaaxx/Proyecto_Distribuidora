"""Dominio puro de la cobranza (change 17, grupo 6; `specs/cobranzas/registro-de-cobranzas` y
`anulacion-de-cobranzas`; `design.md` D2, D4, D7, D13).

Sin dependencias de infraestructura (`CLAUDE.md` §4: `domain/` no importa FastAPI, SQLAlchemy
ni el bus): recibe datos, devuelve resultados o lanza errores de dominio de código estable.

La validación de los medios es la función compartida de `configuracion/domain/medios.py`
(D17); acá se arma lo propio de la cobranza. Hay dos formas de evaluarla:

- `validar_cobranza` (con conexión, `ONLINE`): rechaza todo lo que no cumple, incluido el
  consumidor final y la referencia faltante (la de un medio inactivo la rechaza el servicio al
  resolver los medios, `MEDIO_PAGO_INACTIVO`).
- `evaluar_cobranza_offline` (sin conexión, `OFFLINE`, SYN-05, D13-C): rechaza solo lo
  malformado (esquema, importe, cantidad de medios, medios que no suman el importe: INV-08) y
  convierte lo demás en observaciones SYN-07: `MEDIO_INACTIVO`, `REFERENCIA_FALTANTE` y
  `CLIENTE_NO_HABILITADO`. El permiso (`PERMISO_REVOCADO`) y la jornada (`JORNADA_LIBERADA`) los
  decide el bus.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.cobranzas.domain.errores import (
    CobranzaDeVentaError,
    CobranzaYaAnuladaError,
    ConsumidorFinalSinCuentaError,
    ObservacionInvalidaError,
)
from app.modules.configuracion.domain.medios import posiciones_sin_referencia, validar_medios

ORIGEN_VENTA = "VENTA"
ORIGEN_INDEPENDIENTE = "INDEPENDIENTE"
ESTADO_CONFIRMADA = "CONFIRMADA"
ESTADO_ANULADA = "ANULADA"

MAXIMO_OBSERVACION = 500
"""D2, D7: largo máximo de la observación de la cobranza y de la anulación, medido sobre el texto
recibido (antes de recortar los espacios), como el formulario (`max(500)` de Zod)."""

CODIGO_MEDIO_INACTIVO = "MEDIO_INACTIVO"
CODIGO_REFERENCIA_FALTANTE = "REFERENCIA_FALTANTE"
CODIGO_CLIENTE_NO_HABILITADO = "CLIENTE_NO_HABILITADO"
CODIGO_JORNADA_LIBERADA = "JORNADA_LIBERADA"
"""Códigos de observación SYN-07 que produce una cobranza sin conexión (D13)."""


@dataclass(frozen=True)
class MedioResuelto:
    """Un medio de la cobranza ya resuelto por el servicio contra la configuración de la
    organización: lo informado (importe y referencia) y lo que dice el medio (nombre, si exige
    referencia y si está activo). Cumple `MedioDePago` por forma, así que la validación
    compartida lo acepta sin convertirlo."""

    medio_pago_id: UUID
    nombre: str
    importe: Decimal
    referencia: str | None
    requiere_referencia: bool
    activo: bool


@dataclass(frozen=True)
class ObservacionDeCobranza:
    """Una observación SYN-07 de la cobranza; el handler la completa con la operación."""

    codigo: str
    detalle: dict[str, object] | None


@dataclass(frozen=True)
class EvaluacionOffline:
    """Resultado de aceptar una cobranza sin conexión: la observación a guardar, las
    observaciones SYN-07 y la referencia a guardar de cada línea (nula si faltó)."""

    observacion: str | None
    observaciones: tuple[ObservacionDeCobranza, ...]
    referencias: tuple[str | None, ...]


def recortar_observacion(observacion: str | None) -> str | None:
    """D2: la observación se guarda recortada y vacía equivale a `None`."""
    if observacion is None:
        return None
    recortada = observacion.strip()
    return recortada or None


def validar_observacion(observacion: str | None) -> str | None:
    """D2, D7: hasta 500 caracteres (medidos antes de recortar); devuelve la observación a
    guardar, recortada (o `None` si vino vacía)."""
    if observacion is not None and len(observacion) > MAXIMO_OBSERVACION:
        raise ObservacionInvalidaError(
            f"La observación admite hasta {MAXIMO_OBSERVACION} caracteres "
            f"y tiene {len(observacion)}."
        )
    return recortar_observacion(observacion)


def referencias_a_guardar(medios: Sequence[MedioResuelto]) -> tuple[str | None, ...]:
    """La referencia de cada línea, recortada; vacía o de solo espacios se guarda nula (D13)."""
    return tuple(recortar_observacion(medio.referencia) for medio in medios)


def validar_cobranza(
    importe: Decimal,
    medios: Sequence[MedioResuelto],
    observacion: str | None,
    *,
    es_consumidor_final: bool,
) -> str | None:
    """COB-01, COB-02, INV-08, D2, D4: las reglas de una cobranza con conexión. Devuelve la
    observación a guardar.

    Lo malformado (importe, cantidad de medios, suma exacta, referencia obligatoria, largo de la
    observación) se rechaza primero; después el consumidor final (`CONSUMIDOR_FINAL_SIN_CUENTA`,
    D4). Que el cliente exista, el estado de los medios y el resto de las referencias son
    consultas del servicio (INV-21, TR-09)."""
    texto = validar_observacion(observacion)
    validar_medios(importe, medios)
    if es_consumidor_final:
        raise ConsumidorFinalSinCuentaError(
            "El cliente consumidor final no tiene cuenta corriente: no admite una cobranza."
        )
    return texto


def _detalle_de_linea(indice: int, medio: MedioResuelto) -> dict[str, object]:
    return {
        "medio": indice,
        "medio_pago_id": str(medio.medio_pago_id),
        "nombre": medio.nombre,
        "importe": str(medio.importe),
    }


def evaluar_cobranza_offline(
    importe: Decimal,
    medios: Sequence[MedioResuelto],
    observacion: str | None,
    *,
    cliente_id: UUID,
    es_consumidor_final: bool,
) -> EvaluacionOffline:
    """SYN-05, SYN-07, INV-17, D13-C: una cobranza sin conexión nunca se rechaza por reglas de
    negocio. Se rechaza solo lo malformado (esquema, importe, cantidad de medios, medios que no
    suman el importe: INV-08, observación demasiado larga); el resto se acepta con observaciones:

    - `MEDIO_INACTIVO` por cada línea cuyo medio está inactivo;
    - `REFERENCIA_FALTANTE` por cada línea cuyo medio exige referencia y llegó sin ella o con
      solo espacios (se guarda nula);
    - `CLIENTE_NO_HABILITADO` si es el consumidor final.

    Una misma línea puede llevar las dos primeras; van por línea, en orden, y la del cliente al
    final. El estado del cliente (activo, suspendido, inactivo) no se evalúa: no observa (D4).
    """
    texto = validar_observacion(observacion)
    validar_medios(importe, medios, exigir_referencia=False)

    sin_referencia = set(posiciones_sin_referencia(medios))
    observaciones: list[ObservacionDeCobranza] = []
    for indice, medio in enumerate(medios):
        if not medio.activo:
            observaciones.append(
                ObservacionDeCobranza(CODIGO_MEDIO_INACTIVO, _detalle_de_linea(indice, medio))
            )
        if indice in sin_referencia:
            observaciones.append(
                ObservacionDeCobranza(CODIGO_REFERENCIA_FALTANTE, _detalle_de_linea(indice, medio))
            )
    if es_consumidor_final:
        observaciones.append(
            ObservacionDeCobranza(CODIGO_CLIENTE_NO_HABILITADO, {"cliente_id": str(cliente_id)})
        )
    return EvaluacionOffline(
        observacion=texto,
        observaciones=tuple(observaciones),
        referencias=referencias_a_guardar(medios),
    )


def validar_cobranza_a_anular(estado: str, origen: str) -> None:
    """COB-05, D7: solo se anula una cobranza `CONFIRMADA` (una sola vez) y una de origen
    `VENTA` se rechaza (se anula con la venta, VTA-22). La regla de estado va primera porque es
    la que ve quien reintenta una anulación ya aplicada. Que la cobranza exista en la
    organización, el motivo y la revalidación con la fila bloqueada son del servicio."""
    if estado == ESTADO_ANULADA:
        raise CobranzaYaAnuladaError("La cobranza ya está anulada.")
    if origen == ORIGEN_VENTA:
        raise CobranzaDeVentaError(
            "La cobranza es de una venta: hay que anular la venta (VTA-22, D7)."
        )
