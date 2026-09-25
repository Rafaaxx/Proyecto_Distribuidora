"""Errores de dominio de `proveedores` (`design.md`, tasks.md 6.1): código
estable, heredan de `DomainError` (`CLAUDE.md` §5), mismo criterio de
`status_http` que `catalogo/domain/errores.py` (409 duplicados/estado en
conflicto, 422 validaciones de contenido, 404 no encontrado). Referencias
inexistentes o de otra organización usan `RecursoNoEncontradoError` (INV-21,
SEG-07: "Un recurso de otra organización responde 404, no 403")."""

from __future__ import annotations

from app.core.errors import DomainError


class RecursoNoEncontradoError(DomainError):
    """Un proveedor, producto o presentación que no existe en la
    organización del token (o que pertenece a otra) responde como
    inexistente (INV-21, SEG-07)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class NombreInvalidoError(DomainError):
    """Nombre de proveedor vacío o solo espacios tras recortar (D7)."""

    codigo = "NOMBRE_INVALIDO"
    status_http = 422


class NombreDuplicadoError(DomainError):
    """Nombre de proveedor ya usado en la organización (D7,
    `ux_proveedor__nombre`)."""

    codigo = "NOMBRE_DUPLICADO"
    status_http = 409


class CuitInvalidoError(DomainError):
    """CUIT que, tras normalizar, no son 11 dígitos (D7)."""

    codigo = "CUIT_INVALIDO"
    status_http = 422


class CuitDuplicadoError(DomainError):
    """CUIT ya usado en la organización (D7, `ux_proveedor__cuit`)."""

    codigo = "CUIT_DUPLICADO"
    status_http = 409


class ProveedorInactivoError(DomainError):
    """Proveedor inactivo asignado a un producto nuevo o modificado (D9),
    o usado para informar un costo (D5: "un proveedor inactivo no recibe
    costos")."""

    codigo = "PROVEEDOR_INACTIVO"
    status_http = 422


class ProveedorConProductosActivosError(DomainError):
    """D5 (ADR-026): un proveedor no se desactiva mientras tenga productos
    activos, simétrico con `CategoriaConProductosActivosError` del 05."""

    codigo = "PROVEEDOR_CON_PRODUCTOS_ACTIVOS"
    status_http = 409


class ProveedorNoCorrespondeError(DomainError):
    """D3: el proveedor de un costo informado debe ser el proveedor actual
    del producto."""

    codigo = "PROVEEDOR_NO_CORRESPONDE"
    status_http = 422


class ProductoInactivoError(DomainError):
    """Producto inactivo usado para informar un costo (CAT-05)."""

    codigo = "PRODUCTO_INACTIVO"
    status_http = 422


class PresentacionInvalidaError(DomainError):
    """Presentación que no es del producto, no está activa o no se usa en
    compra (ADR-010, CAT-05)."""

    codigo = "PRESENTACION_INVALIDA"
    status_http = 422


class ValorInvalidoError(DomainError):
    """Valor informado `<= 0` o con más de 2 decimales (TR-01)."""

    codigo = "VALOR_INVALIDO"
    status_http = 422


class BonificacionInvalidaError(DomainError):
    """Bonificación fuera de `[0, 1)` o con más de 6 decimales (TR-02)."""

    codigo = "BONIFICACION_INVALIDA"
    status_http = 422


class CostosInvalidosError(DomainError):
    """Lote de `COSTO_INFORMAR` vacío, con más de 200 costos, o con dos
    costos del mismo producto, presentación y vigencia (D12, CST-05)."""

    codigo = "COSTOS_INVALIDOS"
    status_http = 422
