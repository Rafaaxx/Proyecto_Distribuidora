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


# --- Compras (change 11, `design.md` D1, D2, D5, D6) -------------------------------


class CantidadInvalidaError(DomainError):
    """Cantidad de una línea de compra que no es positiva, tiene más de 3 decimales o
    no da unidades base enteras (INV-04, D5)."""

    codigo = "CANTIDAD_INVALIDA"
    status_http = 422


class CompraSinLineasError(DomainError):
    """INV-07: una compra necesita al menos una línea."""

    codigo = "COMPRA_SIN_LINEAS"
    status_http = 422


class LineasInvalidasError(DomainError):
    """Más de 200 líneas en una compra (D5)."""

    codigo = "LINEAS_INVALIDAS"
    status_http = 422


class IncluyeIvaNoAplicaError(DomainError):
    """11b, D4, CST-06: `incluye_iva = true` en una organización que no computa crédito
    fiscal. El valor que se carga es siempre el pagado; el IVA no se descuenta (TR-10)."""

    codigo = "INCLUYE_IVA_NO_APLICA"
    status_http = 422


class ImporteInvalidoError(DomainError):
    """Importe (total de factura, importe de un medio, total neto) no positivo, con más
    de 2 decimales o fuera de `numeric(14,2)` (TR-01, D1)."""

    codigo = "IMPORTE_INVALIDO"
    status_http = 422


class CondicionInvalidaError(DomainError):
    """Condición fuera de `CONTADO`/`CREDITO`, o medios de pago en una compra a crédito
    (CMP-01, D2)."""

    codigo = "CONDICION_INVALIDA"
    status_http = 422


class MediosNoSumanImporteError(DomainError):
    """INV-08: los medios de un pago no suman su importe."""

    codigo = "MEDIOS_NO_SUMAN_IMPORTE"
    status_http = 422


class MediosInvalidosError(DomainError):
    """Change 12, `design.md` D6: un pago a proveedor lleva de 1 a 20 medios; fuera de ese
    rango se rechaza antes de mirar importes (el pago de contado de una compra no tiene
    este límite, CMP-03)."""

    codigo = "MEDIOS_INVALIDOS"
    status_http = 422


class ReferenciaObligatoriaError(DomainError):
    """Un medio de pago que exige referencia llegó sin ella (`01` §4)."""

    codigo = "REFERENCIA_OBLIGATORIA"
    status_http = 422


class FechaInvalidaError(DomainError):
    """Fecha de la compra posterior a la fecha de negocio de hoy (TR-04, D6)."""

    codigo = "FECHA_INVALIDA"
    status_http = 422


class UbicacionInactivaError(DomainError):
    """Compra a una ubicación inactiva (D16; mismo código y estado que `stock`)."""

    codigo = "UBICACION_INACTIVA"
    status_http = 409


class MedioPagoInactivoError(DomainError):
    """Medio de pago inactivo usado en el pago de una compra de contado (D2: medios
    activos). Mismo criterio de estado que `ProductoInactivoError`."""

    codigo = "MEDIO_PAGO_INACTIVO"
    status_http = 422


class CompraYaAnuladaError(DomainError):
    """La compra ya está `ANULADA` (CMP-05, TR-06): no se anula dos veces."""

    codigo = "COMPRA_YA_ANULADA"
    status_http = 409


class MotivoInvalidoError(DomainError):
    """Motivo inactivo o de un ámbito distinto de `ANULACION_COMPRA` (CMP-05, `03` §4)."""

    codigo = "MOTIVO_INVALIDO"
    status_http = 422


# --- Pagos a proveedores (change 12, `design.md` D1, D2, D4, D6) -------------------------


class PagoYaAnuladoError(DomainError):
    """Change 12, PAG-03, TR-06: el pago ya está `ANULADA`, no se anula dos veces. Mismo
    estado y mismo criterio que `CompraYaAnuladaError`."""

    codigo = "PAGO_YA_ANULADO"
    status_http = 409


class PagoDeCompraVigienteError(DomainError):
    """Change 12, `design.md` D2 (opción A), CMP-03, CMP-05: el pago de una compra
    `CONFIRMADA` solo se anula junto con su compra. Una compra de contado vigente siempre
    tiene su pago vigente."""

    codigo = "PAGO_DE_COMPRA_VIGENTE"
    status_http = 409


class CursorInvalidoError(DomainError):
    """Cursor de paginación que no se puede leer (`02` §11)."""

    codigo = "CURSOR_INVALIDO"
    status_http = 422


class RangoDeFechasInvalidoError(DomainError):
    """`desde` posterior a `hasta` en un listado."""

    codigo = "RANGO_DE_FECHAS_INVALIDO"
    status_http = 422
