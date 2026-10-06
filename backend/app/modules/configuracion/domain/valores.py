"""Enumeraciones y validaciones puras de los catálogos configurables
(`docs/03-modelo-de-datos.md` §4; TR-09).

Dominio puro: no importa SQLAlchemy ni FastAPI (`docs/02-arquitectura.md`
§5.2).
"""

from __future__ import annotations

from decimal import Decimal

from app.core.errors import DomainError

AMBITOS_MOTIVO = (
    "AJUSTE_STOCK",
    "ANULACION_VENTA",
    "ANULACION_COMPRA",
    "ANULACION_COBRANZA",
    "ANULACION_PAGO",
    "DESCUENTO_MANUAL",
    "LISTA_ANTERIOR",
    "LIBERACION_JORNADA",
)
"""Lista cerrada de `motivo.ambito` (`03` §4, TR-09). `ANULACION_PAGO` es el de la
anulación de pagos a proveedores (PAG-03, `design.md` D1 del change 12)."""

_EXPONENTE_MAXIMO_ALICUOTA = Decimal("0.000001")


class AmbitoMotivoInvalidoError(DomainError):
    codigo = "CONFIGURACION_AMBITO_MOTIVO_INVALIDO"


class AmbitoInvalidoError(DomainError):
    """Ámbito fuera de la lista cerrada al consultar motivos por API (change 11): 422
    con el código estable `AMBITO_INVALIDO`. Distinto de `AmbitoMotivoInvalidoError`,
    que protege el alta de un motivo."""

    codigo = "AMBITO_INVALIDO"
    status_http = 422


class ValorAlicuotaInvalidoError(DomainError):
    codigo = "CONFIGURACION_VALOR_ALICUOTA_INVALIDO"


class NombreVacioError(DomainError):
    codigo = "CONFIGURACION_NOMBRE_VACIO"


def validar_ambito_motivo(valor: str) -> str:
    if valor not in AMBITOS_MOTIVO:
        raise AmbitoMotivoInvalidoError(
            f"Ámbito de motivo desconocido: {valor!r}. Valores válidos: {AMBITOS_MOTIVO}."
        )
    return valor


def validar_valor_alicuota(valor: Decimal) -> Decimal:
    """Valida el `valor` de una alícuota de IVA: `Decimal` exacto de hasta
    6 decimales, no negativo (INV-03, TR-02: 21% = `0.210000`)."""
    if not isinstance(valor, Decimal):
        raise ValorAlicuotaInvalidoError(
            f"El valor de la alícuota debe ser Decimal, no {type(valor).__name__} "
            "(INV-03: nunca punto flotante binario)."
        )
    if valor < 0:
        raise ValorAlicuotaInvalidoError(f"El valor de la alícuota no puede ser negativo: {valor}.")

    exponente = valor.as_tuple().exponent
    if isinstance(exponente, int) and exponente < -6:
        raise ValorAlicuotaInvalidoError(
            f"El valor de la alícuota admite hasta 6 decimales (TR-02): {valor}."
        )
    return valor


def validar_nombre_medio_pago(valor: str) -> str:
    if not valor.strip():
        raise NombreVacioError("El nombre del medio de pago no puede estar vacío.")
    return valor
