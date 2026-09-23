"""Errores de dominio de `catalogo` (`design.md` D6): código estable,
heredan de `DomainError` (`CLAUDE.md` §4), `status_http` 409 para
duplicados y congelados (conflicto con el estado actual) y 422 para
validaciones de contenido. Referencias inexistentes o de otra organización
usan `RecursoNoEncontradoError` (404, INV-21, SEG-07) -- `design.md` D6:
"esto difiere de identidad, que devuelve `RECHAZADO` persistido para 'no
encontrado'; aquí se sigue `02` §6.3 al pie de la letra" (el handler lanza,
el bus revierte toda la transacción, incluida la reserva del comando).
"""

from __future__ import annotations

from app.core.errors import DomainError


class RecursoNoEncontradoError(DomainError):
    """SEG-07/INV-21: una categoría, marca, alícuota, producto o
    presentación que no existe en la organización del token (o que
    pertenece a otra) responde como inexistente, nunca como un error
    distinto (`CLAUDE.md` §4: "Un recurso de otra organización responde
    404, no 403")."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class NombreInvalidoError(DomainError):
    """Nombre de categoría/marca vacío o solo espacios tras recortar
    (`spec` categorias-y-marcas, TR-10)."""

    codigo = "NOMBRE_INVALIDO"
    status_http = 422


class NombreDuplicadoError(DomainError):
    """Nombre de categoría/marca ya usado en la organización (CAT-01,
    `03` §5: `UNIQUE (organizacion_id, nombre)`)."""

    codigo = "NOMBRE_DUPLICADO"
    status_http = 409


class CodigoInvalidoError(DomainError):
    """Código de producto vacío o solo espacios tras recortar (CAT-01)."""

    codigo = "CODIGO_INVALIDO"
    status_http = 422


class CodigoDuplicadoError(DomainError):
    """Código de producto ya usado en la organización (CAT-01, `03` §5:
    `UNIQUE (organizacion_id, codigo)`)."""

    codigo = "CODIGO_DUPLICADO"
    status_http = 409


class ProductoSinPresentacionesError(DomainError):
    """Un alta de producto sin ninguna presentación (CAT-02: "una o más
    presentaciones")."""

    codigo = "PRODUCTO_SIN_PRESENTACIONES"
    status_http = 422


class ReferenciaInvalidaError(DomainError):
    """Ninguna, o más de una, presentación de referencia (CAT-03); una
    referencia que no se usa en venta o está inactiva; o un intento de
    desactivar/dejar de usar en venta la presentación de referencia
    vigente."""

    codigo = "REFERENCIA_INVALIDA"
    status_http = 422


class UnidadesInvalidasError(DomainError):
    """Unidades base que no son un entero `>= 1` (CAT-02, INV-04)."""

    codigo = "UNIDADES_INVALIDAS"
    status_http = 422


class UnidadesCongeladasError(DomainError):
    """Cambio de unidades de una presentación ya usada en alguna operación
    (CAT-04, INV-18): se crea una presentación nueva y se desactiva la
    anterior en su lugar."""

    codigo = "UNIDADES_CONGELADAS"
    status_http = 409


class CategoriaInactivaError(DomainError):
    """Categoría inactiva asignada a un producto nuevo o modificado
    (CAT-05: "los inactivos no se ofrecen en nuevas operaciones")."""

    codigo = "CATEGORIA_INACTIVA"
    status_http = 422


class MarcaInactivaError(DomainError):
    """Marca inactiva asignada a un producto nuevo o modificado (CAT-05)."""

    codigo = "MARCA_INACTIVA"
    status_http = 422


class AlicuotaInactivaError(DomainError):
    """Alícuota inactiva asignada a un producto nuevo o modificado
    (CAT-01, CAT-05)."""

    codigo = "ALICUOTA_INACTIVA"
    status_http = 422


class CategoriaConProductosActivosError(DomainError):
    """D11 (aprobado 2026-09-22): una categoría no se desactiva mientras
    tenga productos activos (CAT-01: todo producto tiene categoría; CAT-05:
    un inactivo no se ofrece)."""

    codigo = "CATEGORIA_CON_PRODUCTOS_ACTIVOS"
    status_http = 409
