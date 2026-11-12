"""Enumeraciones y validaciones puras de los catálogos configurables
(`docs/03-modelo-de-datos.md` §4; TR-09).

Dominio puro: no importa SQLAlchemy ni FastAPI (`docs/02-arquitectura.md`
§5.2).
"""

from __future__ import annotations

from collections.abc import Collection
from decimal import Decimal, InvalidOperation
from uuid import UUID

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
    status_http = 422


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


class UltimoMotivoActivoError(DomainError):
    """Dar de baja el único motivo activo de un ámbito lo dejaría sin motivos y las operaciones
    de ese ámbito quedarían imposibles: 409 `ULTIMO_MOTIVO_ACTIVO` (change 20c, D4)."""

    codigo = "ULTIMO_MOTIVO_ACTIVO"
    status_http = 409


class ValorNoModificableError(DomainError):
    """`ALICUOTA_MODIFICAR` trae un valor distinto del guardado: el porcentaje de una alícuota
    no cambia, se crea otra (change 20c, D6): 422 `VALOR_NO_MODIFICABLE`."""

    codigo = "VALOR_NO_MODIFICABLE"
    status_http = 422


class ValorDuplicadoError(DomainError):
    """Ya hay una alícuota con ese valor en la organización, activa o no
    (`ux_alicuota_iva__valor`, change 20c, D7; IMP-04): 409 `VALOR_DUPLICADO`."""

    codigo = "VALOR_DUPLICADO"
    status_http = 409


class AlicuotaEnUsoError(DomainError):
    """Algún producto activo usa la alícuota: 409 `ALICUOTA_EN_USO` con la cantidad
    (change 20c, D8; CAT-01)."""

    codigo = "ALICUOTA_EN_USO"
    status_http = 409


class UltimaAlicuotaActivaError(DomainError):
    """Dar de baja la única alícuota activa dejaría la organización sin poder dar de alta
    productos: 409 `ULTIMA_ALICUOTA_ACTIVA` (change 20c, D8)."""

    codigo = "ULTIMA_ALICUOTA_ACTIVA"
    status_http = 409


def validar_ambito_motivo(valor: str) -> str:
    if valor not in AMBITOS_MOTIVO:
        raise AmbitoMotivoInvalidoError(
            f"Ámbito de motivo desconocido: {valor!r}. Valores válidos: {AMBITOS_MOTIVO}."
        )
    return valor


def validar_valor_alicuota(valor: Decimal) -> Decimal:
    """Valida el `valor` de una alícuota de IVA: `Decimal` exacto de hasta
    6 decimales, `0 <= valor < 1` (INV-03, TR-02: 21% = `0.210000`; change 20c, D7)."""
    if not isinstance(valor, Decimal):
        raise ValorAlicuotaInvalidoError(
            f"El valor de la alícuota debe ser Decimal, no {type(valor).__name__} "
            "(INV-03: nunca punto flotante binario)."
        )
    if valor < 0:
        raise ValorAlicuotaInvalidoError(f"El valor de la alícuota no puede ser negativo: {valor}.")
    if valor >= 1:
        raise ValorAlicuotaInvalidoError(
            f"El valor de la alícuota es una fracción menor que 1 (21% = 0.21): {valor}."
        )

    exponente = valor.as_tuple().exponent
    if isinstance(exponente, int) and exponente < -6:
        raise ValorAlicuotaInvalidoError(
            f"El valor de la alícuota admite hasta 6 decimales (TR-02): {valor}."
        )
    return valor


def parsear_valor_alicuota(texto: str) -> Decimal:
    """Convierte el texto decimal que viaja en el comando (`"0.270000"`, INV-03: nunca un
    número JSON) en `Decimal` y lo valida con `validar_valor_alicuota`."""
    try:
        valor = Decimal(texto.strip())
    except InvalidOperation as error:
        raise ValorAlicuotaInvalidoError(
            f"El valor de la alícuota no es un número decimal: {texto!r}."
        ) from error
    if not valor.is_finite():
        raise ValorAlicuotaInvalidoError(f"El valor de la alícuota no es finito: {texto!r}.")
    return validar_valor_alicuota(valor)


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


def validar_nombre_motivo(valor: str) -> str:
    """Recorta el nombre del motivo y rechaza el vacío (`NOMBRE_INVALIDO`, change 20c, D2)."""
    recortado = valor.strip()
    if not recortado:
        raise NombreVacioError("El nombre del motivo no puede estar vacío.")
    return recortado


def validar_quedan_motivos_activos(
    activos_del_ambito: Collection[UUID], motivo_id: UUID, activo_nuevo: bool
) -> None:
    """D4: tras el cambio tiene que quedar al menos un motivo activo en el ámbito.
    `activos_del_ambito` son los ids de los motivos activos del ámbito antes del cambio. Solo
    una baja (el motivo estaba activo y pasa a inactivo) puede dejar la cuenta en cero
    (`ULTIMO_MOTIVO_ACTIVO`)."""
    es_baja = motivo_id in activos_del_ambito and not activo_nuevo
    if es_baja and len(activos_del_ambito) - 1 < 1:
        raise UltimoMotivoActivoError(
            "Tiene que quedar al menos un motivo activo en este ámbito: este es el último."
        )


def validar_nombre_alicuota(valor: str) -> str:
    """Recorta el nombre de la alícuota y rechaza el vacío (`NOMBRE_INVALIDO`, change 20c, D6)."""
    recortado = valor.strip()
    if not recortado:
        raise NombreVacioError("El nombre de la alícuota no puede estar vacío.")
    return recortado


def validar_valor_no_cambia(guardado: Decimal, recibido: Decimal) -> None:
    """D6: el valor de una alícuota existente no cambia (`VALOR_NO_MODIFICABLE`). Compara por
    valor, no por escala: `0.21` es `0.210000`."""
    if guardado != recibido:
        raise ValorNoModificableError(
            "El porcentaje de una alícuota no se puede cambiar: creá otra alícuota."
        )


def validar_baja_de_alicuota(*, productos_activos: int, activas: int, activo_nuevo: bool) -> None:
    """D8: la baja de una alícuota se rechaza si algún producto activo la usa (`ALICUOTA_EN_USO`,
    con la cantidad) o si es la última activa (`ULTIMA_ALICUOTA_ACTIVA`). `activas` cuenta las
    alícuotas activas de la organización antes del cambio, incluida esta. Solo se llama (y solo
    valida) para una baja; la reactivación no valida uso. Los productos inactivos no cuentan."""
    if activo_nuevo:
        return
    if productos_activos > 0:
        raise AlicuotaEnUsoError(
            f"{productos_activos} producto(s) activo(s) usan esta alícuota.",
            extension={"productos": productos_activos},
        )
    if activas - 1 < 1:
        raise UltimaAlicuotaActivaError(
            "Tiene que quedar al menos una alícuota activa: esta es la última."
        )
