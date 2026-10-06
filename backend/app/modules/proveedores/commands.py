"""Handlers de comandos de `proveedores` (change 06, grupo 9; `design.md`
D3, D4, D12, D14 -- plantilla D7 del change 04, aprobada tal cual el
2026-09-22: un tipo de comando por escritura ya existente en `service.py`,
un esquema de contenido versión 1, un handler de pocas líneas que llama al
método de servicio, sin `commit` propio (lo gestiona el bus).

Tres tipos, todos `ONLINE`, `admite_offline=False` (mismo motivo que
`catalogo/commands.py`: los tres exigen `sesion`/`reloj` como parámetros de
palabra clave obligatorios y sus endpoints, cuando lleguen en el grupo 10,
llaman al handler directamente con los cuatro argumentos):

- `PROVEEDOR_CREAR`, `PROVEEDOR_MODIFICAR` -- permiso `GESTIONAR_PROVEEDORES`
  (D8; el permiso se exige en la capa de API del grupo 10, no acá: el
  catálogo de tipos de comando no modela permisos, igual que en
  `catalogo/commands.py`).
- `COSTO_INFORMAR` -- permiso `EDITAR_COSTOS` (D12).

Mismo criterio que `catalogo/commands.py` (D6 del 05): los handlers NO
atrapan errores de dominio, los dejan subir; el bus (`sync/service.py::
procesar_comando`) revierte toda la transacción, incluida la reserva del
`operation_id`, y el comando puede reintentarse con contenido corregido.

Los ids de entidades nuevas (proveedor, costos informados) se generan en el
servidor (UUIDv7, `core/ids.py`, dentro de `proveedores/service.py`) y se
devuelven en el resultado del comando.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.commands.catalogo import declarar_tipo
from app.commands.observaciones import ObservacionProducida
from app.commands.registro import registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad import service as identidad_service
from app.modules.proveedores import service as proveedores_service
from app.modules.proveedores.domain.lote import CostoDelLote
from app.modules.proveedores.domain.pagos import MAXIMO_OBSERVACION
from app.modules.proveedores.service import LineaDeCompra, MedioAPagar

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver
`catalogo/commands.py` para la justificación de no importarla de `sync`)."""

ResultadoHandlerConObservaciones = tuple[
    str, dict[str, object] | None, str | None, tuple[ObservacionProducida, ...]
]
"""Extensión con las observaciones del handler (`sync/service.py`, tarea 9.5)."""


# --- PROVEEDOR_CREAR / PROVEEDOR_MODIFICAR (D7, D5/ADR-026) ----------------


class ProveedorCrearContenidoV1(BaseModel):
    nombre: str
    cuit: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None


def manejar_proveedor_crear(
    sobre: SobreComando, contenido: ProveedorCrearContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    proveedor = proveedores_service.crear_proveedor(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        nombre=contenido.nombre,
        cuit=contenido.cuit,
        contacto=contenido.contacto,
        telefono=contenido.telefono,
        email=contenido.email,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"proveedor_id": str(proveedor.id)}, None


registrar_handler("PROVEEDOR_CREAR", 1, ProveedorCrearContenidoV1)(
    manejar_proveedor_crear  # type: ignore[arg-type]
)
declarar_tipo("PROVEEDOR_CREAR", admite_online=True, admite_offline=False)


class ProveedorModificarContenidoV1(BaseModel):
    proveedor_id: UUID
    nombre: str
    cuit: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    activo: bool


def manejar_proveedor_modificar(
    sobre: SobreComando, contenido: ProveedorModificarContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    proveedor = proveedores_service.modificar_proveedor(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        proveedor_id=contenido.proveedor_id,
        nombre=contenido.nombre,
        cuit=contenido.cuit,
        contacto=contenido.contacto,
        telefono=contenido.telefono,
        email=contenido.email,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"proveedor_id": str(proveedor.id)}, None


registrar_handler("PROVEEDOR_MODIFICAR", 1, ProveedorModificarContenidoV1)(
    manejar_proveedor_modificar  # type: ignore[arg-type]
)
declarar_tipo("PROVEEDOR_MODIFICAR", admite_online=True, admite_offline=False)


# --- COSTO_INFORMAR (D3, D4, D12, D14; CST-01, CST-02, INV-01, INV-18) -----


class CostoDelLoteContenidoV1(BaseModel):
    """Un costo dentro del lote (D12): decimales como string, Pydantic los
    valida como `Decimal` sin pasar por `float` (`CLAUDE.md` §4)."""

    producto_id: UUID
    presentacion_id: UUID
    valor: Decimal
    incluye_iva: bool
    bonificacion: Decimal = Decimal("0")
    vigencia_desde: date
    observacion: str | None = None


class CostoInformarContenidoV1(BaseModel):
    proveedor_id: UUID
    costos: list[CostoDelLoteContenidoV1]


def manejar_costo_informar(
    sobre: SobreComando, contenido: CostoInformarContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    costos = [
        CostoDelLote(
            producto_id=costo.producto_id,
            presentacion_id=costo.presentacion_id,
            valor=costo.valor,
            incluye_iva=costo.incluye_iva,
            bonificacion=costo.bonificacion,
            vigencia_desde=costo.vigencia_desde,
            observacion=costo.observacion,
        )
        for costo in contenido.costos
    ]
    creados = proveedores_service.informar_costos(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        proveedor_id=contenido.proveedor_id,
        costos=costos,
        operation_id=sobre.operation_id,
        actor_id=sobre.usuario_id,
    )
    return (
        "ACEPTADO",
        {
            "costo_ids": [str(costo.id) for costo in creados],
            "costos_base": [str(costo.costo_base) for costo in creados],
        },
        None,
    )


registrar_handler("COSTO_INFORMAR", 1, CostoInformarContenidoV1)(
    manejar_costo_informar  # type: ignore[arg-type]
)
declarar_tipo("COSTO_INFORMAR", admite_online=True, admite_offline=False)


# --- COMPRA_CONFIRMAR (change 11: CMP-01 a CMP-04, CMP-08; `design.md` D1 a D7, D14) ------

PERMISO_REGISTRAR_COMPRA = "REGISTRAR_COMPRA"
_PATRON_DECIMAL = r"^-?\d+(\.\d+)?$"


def _exigir_permiso(sobre: SobreComando, sesion: object, codigo_permiso: str) -> None:
    """Falla con 403 `PERMISO_REQUERIDO` si el usuario del sobre no tiene el permiso
    (SEG-06). Va PRIMERO: un rechazo no puede dejar nada escrito (mismo criterio que
    `stock/commands.py`)."""
    permitidos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id,
        sobre.usuario_id,
        sesion,  # type: ignore[arg-type]
    )
    if codigo_permiso not in permitidos:
        raise PermisoRequeridoError(f"Falta el permiso {codigo_permiso}.")


class LineaDeCompraContenidoV1(BaseModel):
    """Una línea (D5). `cantidad`, `valor` y `bonificacion` viajan como string decimal:
    un número JSON ya degradado por `float` en el cliente se rechaza (INV-03); la
    cantidad de decimales la valida el dominio con su código estable."""

    model_config = ConfigDict(extra="forbid")

    producto_id: UUID
    presentacion_id: UUID
    cantidad: str = Field(pattern=_PATRON_DECIMAL)
    valor: str = Field(pattern=_PATRON_DECIMAL)
    incluye_iva: bool
    bonificacion: str = Field(default="0", pattern=_PATRON_DECIMAL)


class MedioDeCompraContenidoV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medio_pago_id: UUID
    importe: str = Field(pattern=_PATRON_DECIMAL)
    referencia: str | None = None


class CompraConfirmarContenidoV1(BaseModel):
    """`extra="forbid"`: `organizacion_id` sale del token (INV-21, TR-08) y la compra
    nace `CONFIRMADA`. `lineas` vacía la rechaza el dominio con `COMPRA_SIN_LINEAS`."""

    model_config = ConfigDict(extra="forbid")

    proveedor_id: UUID
    fecha: date
    ubicacion_id: UUID
    condicion: str
    total_factura: str = Field(pattern=_PATRON_DECIMAL)
    numero_comprobante: str | None = None
    observacion: str | None = None
    lineas: list[LineaDeCompraContenidoV1]
    medios: list[MedioDeCompraContenidoV1] = Field(default_factory=list)


def manejar_compra_confirmar(
    sobre: SobreComando, contenido: CompraConfirmarContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    """Confirma una compra (D14: `REGISTRAR_COMPRA`, también de contado). El resultado
    se guarda y se reenvía tal cual ante un doble envío (INV-06): los importes viajan
    como string y no incluye costos de valorización ajenos a la compra."""
    _exigir_permiso(sobre, sesion, PERMISO_REGISTRAR_COMPRA)
    resultado = proveedores_service.confirmar_compra(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        proveedor_id=contenido.proveedor_id,
        fecha=contenido.fecha,
        ubicacion_id=contenido.ubicacion_id,
        condicion=contenido.condicion,
        total_factura=Decimal(contenido.total_factura),
        numero_comprobante=contenido.numero_comprobante,
        observacion=contenido.observacion,
        lineas=[
            LineaDeCompra(
                producto_id=linea.producto_id,
                presentacion_id=linea.presentacion_id,
                cantidad=Decimal(linea.cantidad),
                valor=Decimal(linea.valor),
                incluye_iva=linea.incluye_iva,
                bonificacion=Decimal(linea.bonificacion),
            )
            for linea in contenido.lineas
        ],
        medios=[
            MedioAPagar(
                medio_pago_id=medio.medio_pago_id,
                importe=Decimal(medio.importe),
                referencia=medio.referencia,
            )
            for medio in contenido.medios
        ],
        operation_id=sobre.operation_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        occurred_at=sobre.occurred_at,
    )
    return (
        "ACEPTADO",
        {
            "compra_id": str(resultado.compra.id),
            "total_neto": str(resultado.compra.total_neto),
            "total_factura": str(resultado.compra.total_factura),
            "pago_id": None if resultado.pago is None else str(resultado.pago.id),
            "diferencias_de_costo": [
                {
                    "linea": diferencia.linea,
                    "producto_id": str(diferencia.producto_id),
                    "costo_base_compra": str(diferencia.costo_base_compra),
                    "costo_base_vigente": (
                        None
                        if diferencia.costo_base_vigente is None
                        else str(diferencia.costo_base_vigente)
                    ),
                }
                for diferencia in resultado.diferencias_de_costo
            ],
        },
        None,
    )


registrar_handler("COMPRA_CONFIRMAR", 1, CompraConfirmarContenidoV1)(
    manejar_compra_confirmar  # type: ignore[arg-type]
)
declarar_tipo("COMPRA_CONFIRMAR", admite_online=True, admite_offline=False)


# --- COMPRA_ANULAR (change 11: CMP-05 a CMP-07, CC-03; `design.md` D3, D9, D10, D14) ----

PERMISO_ANULAR_COMPRA = "ANULAR_COMPRA"
PERMISO_PERMITIR_STOCK_NEGATIVO = "PERMITIR_STOCK_NEGATIVO"


class CompraAnularContenidoV1(BaseModel):
    """`devuelve_pago` es obligatorio en una compra de contado y prohibido en una a
    crédito (D3): lo decide el servicio, que conoce la condición de la compra."""

    model_config = ConfigDict(extra="forbid")

    compra_id: UUID
    motivo_id: UUID
    devuelve_pago: bool | None = None


def manejar_compra_anular(
    sobre: SobreComando, contenido: CompraAnularContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandlerConObservaciones:
    """Anula una compra (D14: `ANULAR_COMPRA`; si deja stock negativo, además
    `PERMITIR_STOCK_NEGATIVO`, CMP-07). Devuelve `ANULACION_COMPRA_SIN_RECALCULO` y
    `STOCK_NEGATIVO` como observaciones (SYN-07)."""
    permisos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id,
        sobre.usuario_id,
        sesion,  # type: ignore[arg-type]
    )
    if PERMISO_ANULAR_COMPRA not in permisos:
        raise PermisoRequeridoError(f"Falta el permiso {PERMISO_ANULAR_COMPRA}.")
    resultado = proveedores_service.anular_compra(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        compra_id=contenido.compra_id,
        motivo_id=contenido.motivo_id,
        devuelve_pago=contenido.devuelve_pago,
        permitir_stock_negativo=PERMISO_PERMITIR_STOCK_NEGATIVO in permisos,
        operation_id=sobre.operation_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        occurred_at=sobre.occurred_at,
    )
    observaciones = tuple(
        ObservacionProducida(
            codigo=aviso.codigo,
            operacion_tipo="COMPRA",
            operacion_id=resultado.compra.id,
            detalle={"productos": aviso.productos},
        )
        for aviso in resultado.avisos
    )
    return (
        "ACEPTADO",
        {
            "compra_id": str(resultado.compra.id),
            "estado": resultado.compra.estado,
            "pago_anulado": resultado.pago_anulado,
            "observaciones": [aviso.codigo for aviso in resultado.avisos],
        },
        None,
        observaciones,
    )


registrar_handler("COMPRA_ANULAR", 1, CompraAnularContenidoV1)(
    manejar_compra_anular  # type: ignore[arg-type]
)
declarar_tipo("COMPRA_ANULAR", admite_online=True, admite_offline=False)


# --- PAGO_PROVEEDOR_REGISTRAR (change 12: PAG-01, PAG-02; D2 a D6, D10; CC-03, CC-04) ----

PERMISO_REGISTRAR_PAGO_PROVEEDOR = "REGISTRAR_PAGO_PROVEEDOR"


class MedioDePagoContenidoV1(BaseModel):
    """Un medio del pago (D6). `importe` viaja como string decimal: un número JSON ya
    degradado por `float` en el cliente se rechaza (INV-03)."""

    model_config = ConfigDict(extra="forbid")

    medio_pago_id: UUID
    importe: str = Field(pattern=_PATRON_DECIMAL)
    referencia: str | None = None


class PagoProveedorRegistrarContenidoV1(BaseModel):
    """`extra="forbid"`: `organizacion_id` sale del token (INV-21, TR-08) y el pago nace
    `CONFIRMADA` de origen `INDEPENDIENTE` (PAG-01, PAG-02). `medios` vacía la rechaza el
    dominio con `MEDIOS_INVALIDOS` (D6: de 1 a 20)."""

    model_config = ConfigDict(extra="forbid")

    proveedor_id: UUID
    fecha: date
    importe: str = Field(pattern=_PATRON_DECIMAL)
    medios: list[MedioDePagoContenidoV1]
    observacion: str | None = Field(default=None, max_length=MAXIMO_OBSERVACION)


def manejar_pago_proveedor_registrar(
    sobre: SobreComando,
    contenido: PagoProveedorRegistrarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    """Registra un pago a proveedor (D14: `REGISTRAR_PAGO_PROVEEDOR`). El resultado se
    guarda y se reenvía tal cual ante un doble envío (INV-06): devuelve el id del pago y
    el saldo resultante del proveedor, ambos como string (INV-03)."""
    _exigir_permiso(sobre, sesion, PERMISO_REGISTRAR_PAGO_PROVEEDOR)
    resultado = proveedores_service.registrar_pago(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        proveedor_id=contenido.proveedor_id,
        fecha=contenido.fecha,
        importe=Decimal(contenido.importe),
        medios=[
            MedioAPagar(
                medio_pago_id=medio.medio_pago_id,
                importe=Decimal(medio.importe),
                referencia=medio.referencia,
            )
            for medio in contenido.medios
        ],
        observacion=contenido.observacion,
        operation_id=sobre.operation_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        occurred_at=sobre.occurred_at,
    )
    return (
        "ACEPTADO",
        {
            "pago_id": str(resultado.pago.id),
            "estado": resultado.pago.estado,
            "importe": str(resultado.pago.importe),
            "saldo": str(resultado.saldo),
        },
        None,
    )


registrar_handler("PAGO_PROVEEDOR_REGISTRAR", 1, PagoProveedorRegistrarContenidoV1)(
    manejar_pago_proveedor_registrar  # type: ignore[arg-type]
)
declarar_tipo("PAGO_PROVEEDOR_REGISTRAR", admite_online=True, admite_offline=False)


# --- PAGO_PROVEEDOR_ANULAR (change 12: PAG-03; CC-03, CC-04; `design.md` D1, D2, D5, D10) --

PERMISO_ANULAR_PAGO_PROVEEDOR = "ANULAR_PAGO_PROVEEDOR"


class PagoProveedorAnularContenidoV1(BaseModel):
    """`extra="forbid"`: `organizacion_id` sale del token (INV-21, TR-08). El pago no se
    edita ni se borra: el comando solo lo deja `ANULADA` con su motivo (TR-06, PAG-03)."""

    model_config = ConfigDict(extra="forbid")

    pago_id: UUID
    motivo_id: UUID


def manejar_pago_proveedor_anular(
    sobre: SobreComando,
    contenido: PagoProveedorAnularContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    """Anula un pago a proveedor (D14: `ANULAR_PAGO_PROVEEDOR`). El resultado se guarda y
    se reenvía tal cual ante un doble envío (INV-06): devuelve el id del pago, su estado y
    el saldo resultante del proveedor, con el importe y el saldo como string (INV-03)."""
    _exigir_permiso(sobre, sesion, PERMISO_ANULAR_PAGO_PROVEEDOR)
    resultado = proveedores_service.anular_pago(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        pago_id=contenido.pago_id,
        motivo_id=contenido.motivo_id,
        operation_id=sobre.operation_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        occurred_at=sobre.occurred_at,
    )
    return (
        "ACEPTADO",
        {
            "pago_id": str(resultado.pago.id),
            "estado": resultado.pago.estado,
            "saldo": str(resultado.saldo),
        },
        None,
    )


registrar_handler("PAGO_PROVEEDOR_ANULAR", 1, PagoProveedorAnularContenidoV1)(
    manejar_pago_proveedor_anular  # type: ignore[arg-type]
)
declarar_tipo("PAGO_PROVEEDOR_ANULAR", admite_online=True, admite_offline=False)
