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
    "ANULACION_TRANSFERENCIA",
    "ANULACION_AJUSTE",
    "DESCUENTO_MANUAL",
    "LISTA_ANTERIOR",
    "LIBERACION_JORNADA",
)
"""Lista cerrada de `motivo.ambito` (`03` §4, TR-09). `ANULACION_PAGO` es el de la
anulación de pagos a proveedores (PAG-03, `design.md` D1 del change 12);
`ANULACION_TRANSFERENCIA` y `ANULACION_AJUSTE` son los de la anulación de transferencias y
ajustes de stock (TR-06, `design.md` D5 del change 14)."""

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
    """Nombre de un medio de pago vacío o de solo espacios: 422 `NOMBRE_INVALIDO`, el mismo
    código que categorías, ubicaciones y listas (change 17b, D2; CAT-01)."""

    codigo = "NOMBRE_INVALIDO"
    status_http = 422


class NombreDuplicadoError(DomainError):
    """Nombre de medio de pago ya usado en la organización, activo o no y sin distinguir
    mayúsculas (`ux_medio_pago__nombre`, change 17b, D3): 409 `NOMBRE_DUPLICADO`."""

    codigo = "NOMBRE_DUPLICADO"
    status_http = 409


class MedioPagoNoEncontradoError(DomainError):
    """El medio de pago no existe en la organización del token (o es de otra): 404, nunca 403
    (INV-21, SEG-07)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class UltimoMedioActivoError(DomainError):
    """Dar de baja el único medio de pago activo dejaría la organización sin poder cobrar ni
    pagar: 409 `ULTIMO_MEDIO_ACTIVO` (change 17b, D4; CAT-05, TR-06)."""

    codigo = "ULTIMO_MEDIO_ACTIVO"
    status_http = 409


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
    """Recorta el nombre y rechaza el vacío (`NOMBRE_INVALIDO`, D2). Devuelve el recortado."""
    recortado = valor.strip()
    if not recortado:
        raise NombreVacioError("El nombre del medio de pago no puede estar vacío.")
    return recortado


def validar_quedan_medios_activos(
    activos_antes: int, *, medio_activo: bool, activo_nuevo: bool
) -> None:
    """D4: tras el cambio tiene que quedar al menos un medio activo. `activos_antes` es la
    cantidad de medios activos de la organización antes de aplicar el cambio; `medio_activo` y
    `activo_nuevo`, el estado del medio que se modifica antes y después. Solo una baja
    (activo -> inactivo) puede dejar la cuenta en cero (`ULTIMO_MEDIO_ACTIVO`)."""
    es_baja = medio_activo and not activo_nuevo
    if es_baja and activos_antes - 1 < 1:
        raise UltimoMedioActivoError(
            "Tiene que quedar al menos un medio de pago activo: este es el último."
        )
