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

from app.core.errors import DomainError

_PATRON_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

ESTADOS_ORGANIZACION = ("ACTIVA", "SUSPENDIDA")
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


class ModoImpositivoInvalidoError(DomainError):
    codigo = "IDENTIDAD_MODO_IMPOSITIVO_INVALIDO"


class PoliticaCreditoInvalidaError(DomainError):
    codigo = "IDENTIDAD_POLITICA_CREDITO_INVALIDA"


class ToleranciaOfflineTipoInvalidoError(DomainError):
    codigo = "IDENTIDAD_TOLERANCIA_OFFLINE_TIPO_INVALIDO"


class RedondeoDireccionInvalidaError(DomainError):
    codigo = "IDENTIDAD_REDONDEO_DIRECCION_INVALIDA"


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


def validar_redondeo_direccion(valor: str) -> str:
    if valor not in REDONDEO_DIRECCIONES:
        raise RedondeoDireccionInvalidaError(
            f"Dirección de redondeo desconocida: {valor!r}. "
            f"Valores válidos: {REDONDEO_DIRECCIONES}."
        )
    return valor


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
