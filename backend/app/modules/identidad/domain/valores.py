"""Enumeraciones y validaciones puras de `organizacion` y
`configuracion_organizacion` (`docs/03-modelo-de-datos.md` §4).

Dominio puro: no importa SQLAlchemy ni FastAPI (`docs/02-arquitectura.md`
§5.2, `CLAUDE.md` §5). Cada `validar_*` recibe el string tal como llega
(por ejemplo, desde una fila de la base o un comando) y devuelve el mismo
valor si pertenece al dominio cerrado, o lanza un error de dominio propio
con código estable si no.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.core.errors import DomainError

_PATRON_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

ESTADOS_ORGANIZACION = ("ACTIVA", "SUSPENDIDA")
RESPONSABLE_INSCRIPTO = "RESPONSABLE_INSCRIPTO"
MONOTRIBUTO = "MONOTRIBUTO"
EXENTO = "EXENTO"
CONDICIONES_IVA = (RESPONSABLE_INSCRIPTO, MONOTRIBUTO, EXENTO)
MODOS_IMPOSITIVOS = ("A", "B", "C")
POLITICAS_CREDITO_DEFAULT = ("ADVERTIR", "AUTORIZAR", "BLOQUEAR")
TOLERANCIAS_OFFLINE_TIPO = ("IMPORTE", "PORCENTAJE")
REDONDEO_DIRECCIONES = ("ARRIBA", "CERCANO", "ABAJO")
ESTADOS_FACTURACION_DEFAULT = ("NO_REQUIERE", "PENDIENTE")
MODALIDADES_IVA_DEFAULT = ("CLIENTE", "ABSORBIDO")


class EstadoOrganizacionInvalidoError(DomainError):
    codigo = "IDENTIDAD_ESTADO_ORGANIZACION_INVALIDO"


class SlugOrganizacionInvalidoError(DomainError):
    codigo = "IDENTIDAD_SLUG_ORGANIZACION_INVALIDO"


class CondicionIvaInvalidaError(DomainError):
    codigo = "IDENTIDAD_CONDICION_IVA_INVALIDA"
    status_http = 422


class CondicionIvaSinCambioError(DomainError):
    """11b, D7, TR-10: se pidió cambiar la condición al mismo valor que ya tiene."""

    codigo = "CONDICION_IVA_SIN_CAMBIO"
    status_http = 409


class ModoImpositivoIncompatibleError(DomainError):
    """D2: una organización no inscripta es modo `A` y sin modalidad de IVA al facturar."""

    codigo = "MODO_IMPOSITIVO_INCOMPATIBLE"
    status_http = 409


class ModoImpositivoInvalidoError(DomainError):
    codigo = "IDENTIDAD_MODO_IMPOSITIVO_INVALIDO"


class PoliticaCreditoInvalidaError(DomainError):
    codigo = "IDENTIDAD_POLITICA_CREDITO_INVALIDA"


class ToleranciaOfflineTipoInvalidoError(DomainError):
    codigo = "IDENTIDAD_TOLERANCIA_OFFLINE_TIPO_INVALIDO"


class ToleranciaOfflineInvalidaError(DomainError):
    """Tolerancia sin conexión de la organización a medias (tipo sin valor o valor sin tipo), con
    tipo fuera del catálogo o con un valor que no es un importe exacto, negativo o con más de dos
    decimales (CRE-06, change 18b D14). Mismo código estable que el de la tolerancia del cliente
    (`clientes/domain/errores.py`): `identidad` es la raíz de dependencias y no puede importar de
    `clientes`."""

    codigo = "TOLERANCIA_OFFLINE_INVALIDA"
    status_http = 422


class RedondeoDireccionInvalidaError(DomainError):
    """Redondeo por defecto inválido (dirección desconocida, múltiplo no positivo o con más de
    dos decimales, o uno sin el otro). Mismo código que usa `precios` para el redondeo de una
    lista (PRC-01, PRC-14; change 20c, D10): 422 `REDONDEO_INVALIDO`."""

    codigo = "REDONDEO_INVALIDO"
    status_http = 422


class EstadoFacturacionInvalidoError(DomainError):
    codigo = "IDENTIDAD_ESTADO_FACTURACION_INVALIDO"


class ModalidadIvaInvalidaError(DomainError):
    codigo = "IDENTIDAD_MODALIDAD_IVA_INVALIDA"


def validar_estado_organizacion(valor: str) -> str:
    if valor not in ESTADOS_ORGANIZACION:
        raise EstadoOrganizacionInvalidoError(
            f"Estado de organización desconocido: {valor!r}. "
            f"Valores válidos: {ESTADOS_ORGANIZACION}."
        )
    return valor


def validar_slug_organizacion(valor: str) -> str:
    """Valida el formato del `slug` que resuelve la organización en el
    login antes de que exista un token (`ADR-021`): minúsculas, dígitos y
    guiones simples, sin empezar ni terminar en guion."""
    if not _PATRON_SLUG.match(valor):
        raise SlugOrganizacionInvalidoError(
            f"Slug de organización inválido: {valor!r}. Debe ser minúsculas, "
            "dígitos y guiones simples (ej. 'distribuidora-cuyo')."
        )
    return valor


def validar_modo_impositivo(valor: str) -> str:
    if valor not in MODOS_IMPOSITIVOS:
        raise ModoImpositivoInvalidoError(
            f"Modo impositivo desconocido: {valor!r}. Valores válidos: {MODOS_IMPOSITIVOS}."
        )
    return valor


def validar_politica_credito_default(valor: str) -> str:
    if valor not in POLITICAS_CREDITO_DEFAULT:
        raise PoliticaCreditoInvalidaError(
            f"Política de crédito desconocida: {valor!r}. "
            f"Valores válidos: {POLITICAS_CREDITO_DEFAULT}."
        )
    return valor


def validar_tolerancia_offline_tipo(valor: str) -> str:
    if valor not in TOLERANCIAS_OFFLINE_TIPO:
        raise ToleranciaOfflineTipoInvalidoError(
            f"Tipo de tolerancia offline desconocido: {valor!r}. "
            f"Valores válidos: {TOLERANCIAS_OFFLINE_TIPO}."
        )
    return valor


def validar_tolerancia_offline_de_organizacion(
    tipo: str | None, valor: str | None
) -> tuple[str | None, Decimal | None]:
    """Valida el par de tolerancia sin conexión de la organización y lo devuelve normalizado
    (CRE-06, ADR-032, change 18b D14): tipo y valor van JUNTOS o los dos vacíos; el tipo está en
    el catálogo; el valor es un importe exacto (texto, INV-03) no negativo y de a lo sumo dos
    decimales -- se rechaza, no se redondea. Nunca se acepta un valor sin tipo ni al revés."""
    if tipo is None and valor is None:
        return None, None
    if tipo is None or valor is None:
        raise ToleranciaOfflineInvalidaError(
            "La tolerancia sin conexión se informa en pareja: o van tipo y valor, o ninguno "
            "(CRE-06)."
        )
    if tipo not in TOLERANCIAS_OFFLINE_TIPO:
        raise ToleranciaOfflineInvalidaError(
            f"El tipo de tolerancia {tipo!r} no está en el catálogo {TOLERANCIAS_OFFLINE_TIPO} "
            "(CRE-06)."
        )
    try:
        importe = Decimal(valor)
    except InvalidOperation as error:
        raise ToleranciaOfflineInvalidaError(
            "El valor de la tolerancia no es un número exacto (CRE-06, INV-03)."
        ) from error
    if not importe.is_finite():
        raise ToleranciaOfflineInvalidaError(
            "El valor de la tolerancia no es un número finito (CRE-06)."
        )
    if importe < 0:
        raise ToleranciaOfflineInvalidaError("El valor de la tolerancia no puede ser negativo.")
    if importe != importe.quantize(Decimal("0.01")):
        raise ToleranciaOfflineInvalidaError(
            "El valor de la tolerancia no puede tener más de 2 decimales; no se redondea (INV-03)."
        )
    return tipo, importe.quantize(Decimal("0.01"))


def validar_redondeo_direccion(valor: str) -> str:
    if valor not in REDONDEO_DIRECCIONES:
        raise RedondeoDireccionInvalidaError(
            f"Dirección de redondeo desconocida: {valor!r}. "
            f"Valores válidos: {REDONDEO_DIRECCIONES}."
        )
    return valor


def validar_redondeo_por_defecto(
    multiplo: str | None, direccion: str | None
) -> tuple[Decimal, str] | None:
    """Redondeo por defecto de la organización (change 20c, D10; PRC-01, PRC-14): los dos nulos
    son "sin definir" (`None`); si no, múltiplo mayor que cero con hasta dos decimales (INV-03:
    texto decimal exacto, no se redondea) y dirección de `REDONDEO_DIRECCIONES`. Uno sin el
    otro, o cualquier valor fuera de dominio, es `REDONDEO_INVALIDO` (422)."""
    if multiplo is None and direccion is None:
        return None
    if multiplo is None or direccion is None:
        raise RedondeoDireccionInvalidaError(
            "El redondeo por defecto se define completo (múltiplo y dirección) o no se define."
        )
    validar_redondeo_direccion(direccion)
    try:
        valor = Decimal(multiplo.strip())
    except InvalidOperation as error:
        raise RedondeoDireccionInvalidaError(
            f"El múltiplo de redondeo no es un número decimal: {multiplo!r}."
        ) from error
    if not valor.is_finite() or valor <= 0:
        raise RedondeoDireccionInvalidaError(
            f"El múltiplo de redondeo tiene que ser mayor que cero: {multiplo!r}."
        )
    exponente = valor.as_tuple().exponent
    if isinstance(exponente, int) and exponente < -2:
        raise RedondeoDireccionInvalidaError(
            f"El múltiplo de redondeo admite hasta 2 decimales (no se redondea): {multiplo!r}."
        )
    return valor, direccion


def validar_estado_facturacion_default(valor: str) -> str:
    if valor not in ESTADOS_FACTURACION_DEFAULT:
        raise EstadoFacturacionInvalidoError(
            f"Estado de facturación desconocido: {valor!r}. "
            f"Valores válidos: {ESTADOS_FACTURACION_DEFAULT}."
        )
    return valor


def validar_modalidad_iva_default(valor: str) -> str:
    if valor not in MODALIDADES_IVA_DEFAULT:
        raise ModalidadIvaInvalidaError(
            f"Modalidad de IVA desconocida: {valor!r}. Valores válidos: {MODALIDADES_IVA_DEFAULT}."
        )
    return valor


def validar_condicion_iva(valor: str) -> str:
    if valor not in CONDICIONES_IVA:
        raise CondicionIvaInvalidaError(
            f"Condición frente al IVA desconocida: {valor!r}. Valores válidos: {CONDICIONES_IVA}."
        )
    return valor


def computa_credito_fiscal(condicion: str) -> bool:
    """CST-06: solo un responsable inscripto computa crédito fiscal de IVA en compras;
    para `MONOTRIBUTO` y `EXENTO` el IVA de una compra es costo. Toda parte del sistema que
    necesite saberlo usa esta regla y no la condición (`design.md` D1)."""
    return validar_condicion_iva(condicion) == RESPONSABLE_INSCRIPTO


def validar_compatibilidad_de_condicion(
    condicion: str, modo_impositivo: str, modalidad_iva_default: str | None
) -> None:
    """D2: una organización no inscripta exige modo `A` y modalidad de IVA sin definir
    (ADR-009 y FAC-02/03/04/08 solo se aplican a responsables inscriptos). La misma
    restricción la impone la base con `ck_configuracion_organizacion__no_inscripto_modo_a`."""
    if computa_credito_fiscal(condicion):
        return
    if modo_impositivo != "A" or modalidad_iva_default is not None:
        raise ModoImpositivoIncompatibleError(
            f"Una organización {condicion} es modo impositivo A y no tiene modalidad de IVA al "
            f"facturar (modo {modo_impositivo}, modalidad {modalidad_iva_default})."
        )
