"""Errores de dominio de `stock` (`CLAUDE.md` §5): código estable, heredan de
`DomainError`.

Los códigos que las specs nombran textualmente son `VEHICULO_REQUIERE_TOMA`,
`NOMBRE_DUPLICADO`, `UBICACION_CON_STOCK`, `UBICACION_INACTIVA`,
`PRODUCTO_INACTIVO`, `PRODUCTO_REPETIDO`, `COSTO_INVALIDO`, `STOCK_INSUFICIENTE`,
`PRODUCTO_CON_OPERACIONES`, `CURSOR_INVALIDO` y `RANGO_DE_FECHAS_INVALIDO`. El
resto (`NOMBRE_INVALIDO`, `TIPO_UBICACION_INVALIDO`, `TIPO_MOVIMIENTO_INVALIDO`,
`LINEAS_INVALIDAS`, `CANTIDAD_INVALIDA`, `CANTIDAD_FUERA_DE_RANGO`) son defensas del
servicio para quien lo llame con datos que el esquema de un comando ya habría
rechazado.

Una ubicación o un producto que no existe en la organización del token, o que
pertenece a otra, es `RecursoNoEncontradoError` (INV-21, SEG-07): 404, no 403.
"""

from __future__ import annotations

from app.core.errors import DomainError


class RecursoNoEncontradoError(DomainError):
    """La ubicación o el producto no existe en la organización del token (o
    pertenece a otra) (INV-21, SEG-07)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class NombreInvalidoError(DomainError):
    """Nombre de ubicación vacío o solo espacios tras recortar (`design.md` D7)."""

    codigo = "NOMBRE_INVALIDO"
    status_http = 422


class NombreDuplicadoError(DomainError):
    """Nombre de ubicación ya usado en la organización, activa o no (D7,
    `ux_ubicacion__nombre`)."""

    codigo = "NOMBRE_DUPLICADO"
    status_http = 409


class TipoDeUbicacionInvalidoError(DomainError):
    """`tipo` distinto de `DEPOSITO`, `VEHICULO` y `OTRO` (STK-02)."""

    codigo = "TIPO_UBICACION_INVALIDO"
    status_http = 422


class VehiculoRequiereTomaError(DomainError):
    """Una ubicación `VEHICULO` con `requiere_toma = false` (STK-02, D7)."""

    codigo = "VEHICULO_REQUIERE_TOMA"
    status_http = 422


class UbicacionConStockError(DomainError):
    """Ubicación con algún saldo distinto de cero: no se desactiva (D8)."""

    codigo = "UBICACION_CON_STOCK"
    status_http = 409


class UbicacionInactivaError(DomainError):
    """No se registran movimientos nuevos sobre una ubicación inactiva (D8)."""

    codigo = "UBICACION_INACTIVA"
    status_http = 409


class ProductoInactivoError(DomainError):
    """No se registran movimientos nuevos sobre un producto inactivo (CAT-05,
    D8)."""

    codigo = "PRODUCTO_INACTIVO"
    status_http = 409


class TipoDeMovimientoInvalidoError(DomainError):
    """`tipo` fuera de los nueve de la etapa 1 (STK-03, D13)."""

    codigo = "TIPO_MOVIMIENTO_INVALIDO"
    status_http = 422


class LineasInvalidasError(DomainError):
    """El comando trae menos de 1 o más de 200 líneas (D5)."""

    codigo = "LINEAS_INVALIDAS"
    status_http = 422


class ProductoRepetidoError(DomainError):
    """Un mismo producto en dos líneas del comando (D5)."""

    codigo = "PRODUCTO_REPETIDO"
    status_http = 422


class CantidadInvalidaError(DomainError):
    """Cantidad base que no es un entero distinto de cero (INV-04, D5)."""

    codigo = "CANTIDAD_INVALIDA"
    status_http = 422


class CantidadFueraDeRangoError(DomainError):
    """La cantidad, o el saldo que resultaría, no entra en `integer` (INV-04)."""

    codigo = "CANTIDAD_FUERA_DE_RANGO"
    status_http = 422


class CostoInvalidoError(DomainError):
    """El costo no corresponde al signo de la línea: obligatorio si la cantidad
    es positiva y prohibido si es negativa (D5). El formato y el rango del costo
    (`design.md` D6) los valida `costeo` con el mismo código."""

    codigo = "COSTO_INVALIDO"
    status_http = 422


class StockInsuficienteError(DomainError):
    """Un egreso mayor que el saldo de la ubicación (STK-05, `02` §7.4, D4)."""

    codigo = "STOCK_INSUFICIENTE"
    status_http = 409


class ProductoConOperacionesError(DomainError):
    """El producto ya tiene movimientos de otro tipo en la organización: no
    admite más stock inicial (D4, análogo a CC-08)."""

    codigo = "PRODUCTO_CON_OPERACIONES"
    status_http = 409


class CursorInvalidoError(DomainError):
    """El cursor de paginación del kardex está malformado (D11)."""

    codigo = "CURSOR_INVALIDO"
    status_http = 422


class RangoDeFechasInvalidoError(DomainError):
    """`desde` es posterior a `hasta` en el kardex (D11)."""

    codigo = "RANGO_DE_FECHAS_INVALIDO"
    status_http = 422


# --- Transferencias y ajustes (change 14, `design.md` D3, D6) ----------------------


class UbicacionesIgualesError(DomainError):
    """El origen y el destino de una transferencia son la misma ubicación (STK-07, `03`
    §9: `CHECK (origen <> destino)`)."""

    codigo = "UBICACIONES_IGUALES"
    status_http = 422


class ObservacionInvalidaError(DomainError):
    """La observación supera los 500 caracteres (D6)."""

    codigo = "OBSERVACION_INVALIDA"
    status_http = 422


class MotivoInvalidoError(DomainError):
    """El motivo del ajuste está inactivo o no es del ámbito `AJUSTE_STOCK` (STK-08,
    TR-09, D6)."""

    codigo = "MOTIVO_INVALIDO"
    status_http = 422


class ProductoSinCostoError(DomainError):
    """Un ajuste positivo de un producto sin costo promedio (D3): ese stock se carga con
    stock inicial o con una compra, que sí fijan costo."""

    codigo = "PRODUCTO_SIN_COSTO"
    status_http = 409


# --- Anulación de transferencias y ajustes (change 14, `design.md` D5) --------------------


class TransferenciaYaAnuladaError(DomainError):
    """La transferencia ya está anulada: se anula una sola vez, como `COMPRA_YA_ANULADA`
    (D5 punto 1)."""

    codigo = "TRANSFERENCIA_YA_ANULADA"
    status_http = 409


class AjusteYaAnuladoError(DomainError):
    """El ajuste ya está anulado: se anula una sola vez (D5 punto 1)."""

    codigo = "AJUSTE_YA_ANULADO"
    status_http = 409
