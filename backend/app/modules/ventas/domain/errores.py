"""Errores de dominio de `ventas` (`CLAUDE.md` §5): código estable, heredan de `DomainError`.
422 para las validaciones de contenido y 409 para los conflictos con el estado de la
organización (`design.md` D8 y D13)."""

from __future__ import annotations

from app.core.errors import DomainError


class ModoImpositivoNoSoportadoError(DomainError):
    """El modo impositivo de la organización no es `A`: los modos `B` y `C` son de la etapa 4
    (VTA-04; `design.md` D13)."""

    codigo = "MODO_IMPOSITIVO_NO_SOPORTADO"
    status_http = 409


class VentaSinLineasError(DomainError):
    """Una venta necesita al menos una línea (VTA-02, INV-07; `design.md` D8)."""

    codigo = "VENTA_SIN_LINEAS"
    status_http = 422


class LineasInvalidasError(DomainError):
    """Una venta admite hasta 200 líneas (VTA-02, `design.md` D8)."""

    codigo = "LINEAS_INVALIDAS"
    status_http = 422


class CantidadInvalidaError(DomainError):
    """La cantidad de una línea es un entero mayor que cero (INV-04)."""

    codigo = "CANTIDAD_INVALIDA"
    status_http = 422


class LineaDuplicadaError(DomainError):
    """El mismo producto en la misma presentación dos veces (VTA-02, `design.md` D8)."""

    codigo = "LINEA_DUPLICADA"
    status_http = 422


class ProductoInactivoError(DomainError):
    """Un producto inactivo no se vende (CAT-05)."""

    codigo = "PRODUCTO_INACTIVO"
    status_http = 409


class PresentacionNoVendibleError(DomainError):
    """La presentación está inactiva o no tiene uso en venta (CAT-02, CAT-05)."""

    codigo = "PRESENTACION_NO_VENDIBLE"
    status_http = 409


class ClienteSuspendidoError(DomainError):
    """Vender a un cliente suspendido requiere `VENDER_CLIENTE_SUSPENDIDO` (CLI-02)."""

    codigo = "CLIENTE_SUSPENDIDO"
    status_http = 409


class ClienteInactivoError(DomainError):
    """A un cliente inactivo no se le vende con conexión (CLI-02)."""

    codigo = "CLIENTE_INACTIVO"
    status_http = 409


class ConsumidorFinalContadoError(DomainError):
    """Al consumidor final se le vende solo de contado: la cobranza en el acto debe ser igual
    al total (CLI-03, `design.md` D5)."""

    codigo = "CONSUMIDOR_FINAL_CONTADO"
    status_http = 422


class NumeroInvalidoError(DomainError):
    """El número no tiene el formato `PPP-NNNNNN` o su prefijo no es el del dispositivo de la
    sesión (VTA-06, `design.md` D4)."""

    codigo = "NUMERO_INVALIDO"
    status_http = 422


class NumeroDuplicadoError(DomainError):
    """El número ya lo usa otra venta de la organización (VTA-06, `design.md` D4); la pantalla
    relee la numeración y propone el siguiente."""

    codigo = "NUMERO_DUPLICADO"
    status_http = 409


class MomentoFueraDeRangoError(DomainError):
    """El `occurred_at` de una venta con conexión difiere del reloj del servidor en más que el
    margen (PRC-20, TR-05, `design.md` D9)."""

    codigo = "MOMENTO_FUERA_DE_RANGO"
    status_http = 422


class PrecioDifiereError(DomainError):
    """Lo que el servidor resuelve difiere de lo que vio el usuario: precio, versión, unidades
    de referencia, bruto o total (TR-10, `design.md` D2). El detalle trae los valores del
    servidor para que la pantalla los muestre y el usuario reconfirme."""

    codigo = "PRECIO_DIFIERE"
    status_http = 409


class ProductoSinPrecioError(DomainError):
    """Algún producto de la venta no tiene precio en la versión (VTA-10, PRC-10,
    `design.md` D7). El detalle lista los productos."""

    codigo = "PRODUCTO_SIN_PRECIO"
    status_http = 409


class TotalesInconsistentesError(DomainError):
    """Sin conexión, los importes enviados no coinciden con el cálculo del motor sobre los
    valores enviados: el comando está malformado (SYN-06, ADR-016, `design.md` D2)."""

    codigo = "TOTALES_INCONSISTENTES"
    status_http = 422


class VentaDuplicadaError(DomainError):
    """El identificador de la venta ya fue usado por otra venta (`02` §9, SYN-06;
    `design.md` D17 paso 0)."""

    codigo = "VENTA_DUPLICADA"
    status_http = 409


class RecursoNoEncontradoError(DomainError):
    """Un cliente, producto, presentación o motivo que no existe en la organización del token (o
    que pertenece a otra) responde como inexistente (INV-21, SEG-07)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class VersionNoPermitidaError(DomainError):
    """La versión elegida no se puede usar en una venta: es programada, está anulada o es de
    otra lista (PRC-21, PRC-05; `design.md` D6)."""

    codigo = "VERSION_NO_PERMITIDA"
    status_http = 409


class MotivoInvalidoError(DomainError):
    """Falta el motivo de `LISTA_ANTERIOR` que la organización exige, o el motivo no es uno
    activo de ese ámbito (PRC-21, `01` §4; `design.md` D6)."""

    codigo = "MOTIVO_INVALIDO"
    status_http = 422


class ProductoSinCostoError(DomainError):
    """Con conexión, un producto sin costo promedio no se vende, aun con el permiso de stock
    negativo: primero se carga una compra o el stock inicial (ADR-039, STK-08; `design.md`
    D10). El detalle lista los productos."""

    codigo = "PRODUCTO_SIN_COSTO"
    status_http = 409


class JornadaAjenaError(DomainError):
    """La ubicación o la jornada del comando no es la jornada abierta del usuario y el
    dispositivo de la sesión (RUT-04; `design.md` D3)."""

    codigo = "JORNADA_AJENA"
    status_http = 409


class UbicacionRequeridaError(DomainError):
    """Sin una jornada abierta, la venta tiene que decir de qué ubicación sale el stock
    (VTA-01, `design.md` D3)."""

    codigo = "UBICACION_REQUERIDA"
    status_http = 422


class CursorInvalidoError(DomainError):
    """El cursor de paginación del listado de ventas no se puede leer (TR-04)."""

    codigo = "CURSOR_INVALIDO"
    status_http = 422


class RangoDeFechasInvalidoError(DomainError):
    """`desde` es posterior a `hasta` en el listado de ventas (TR-04)."""

    codigo = "RANGO_DE_FECHAS_INVALIDO"
    status_http = 422


class DescuentoDifiereError(DomainError):
    """Con conexión, los descuentos que vio el usuario no son los que calcula el servidor con las
    reglas vigentes al `occurred_at` (DSC-09, change 18b, D11). La respuesta trae los del
    servidor, igual que `PRECIO_DIFIERE`."""

    codigo = "DESCUENTO_DIFIERE"
    status_http = 409


class AutorizacionRequeridaError(DomainError):
    """Un descuento sobre el tope nombra a un autorizador, pero la venta no trae su credencial
    (el PIN viaja fuera del contenido, `design.md` D2): equivale a no tener autorización
    (DSC-06). Mismo código que el de `descuentos`."""

    codigo = "AUTORIZACION_REQUERIDA"
    status_http = 403


class AutorizacionCreditoRequeridaError(DomainError):
    """Un exceso de crédito nombra a un autorizador, pero la venta no trae su credencial
    (`design.md` D2): equivale a no tener autorización (CRE-05). Mismo código que el de
    `clientes`."""

    codigo = "AUTORIZACION_CREDITO_REQUERIDA"
    status_http = 403
