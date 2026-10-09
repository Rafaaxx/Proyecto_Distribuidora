"""Handlers de comandos de `stock` (change 09, grupo 6, tarea 6.1; `design.md` D1,
D2, D4, D5, D6, D7, D8; plantilla D7 del change 04 y `cuentas_corrientes/commands.py`).

Tres tipos, todos `ONLINE` y `admite_offline=False` (`02` §6.5): exigen `sesion` y
`reloj` como parámetros de palabra clave y escriben en la base del servidor.

- `UBICACION_CREAR` y `UBICACION_MODIFICAR`: permiso `ADMIN_CONFIGURACION` (D2).
- `STOCK_INICIAL_REGISTRAR`: permiso `IMPORTAR_DATOS` (D1), igual que el saldo
  inicial (ADR-033).

El permiso se comprueba ACÁ y primero: el catálogo de tipos no modela permisos y
un lote de sincronización trae tipos distintos, así que el punto donde se puede
comprobar es el handler (mismo criterio que `cuentas_corrientes/commands.py`). Un
rechazo de permiso no deja movimiento, ni reserva del `operation_id`, ni auditoría:
el bus revierte la transacción entera.

Los handlers NO atrapan errores de dominio: los dejan subir, el bus revierte y el
comando puede reintentarse con contenido corregido. La única auditoría es la del
bus (ADR-022, `01` §21): el servicio no escribe una propia.

`dispositivo_id`, `usuario_id` y `occurred_at` salen del sobre (D12, TR-05); el
resultado de un stock inicial NO incluye costos: la ruta de escritura no está
condicionada por `VER_COSTOS` y el resultado se guarda y se reenvía tal cual
(INV-06).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictInt

from app.commands.auditoria import DatosDeAuditoria
from app.commands.catalogo import declarar_tipo
from app.commands.observaciones import ObservacionProducida
from app.commands.registro import registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad import service as identidad_service
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeStockInicial
from app.modules.stock.service import LineaDeAjuste, LineaDeTransferencia

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver
`catalogo/commands.py` para la justificación de no importarla de `sync`)."""

ResultadoHandlerConObservaciones = tuple[
    str, dict[str, object] | None, str | None, tuple[ObservacionProducida, ...]
]
"""Extensión con las observaciones del handler (`sync/service.py`, tarea 9.5)."""

ResultadoHandlerConAuditoria = tuple[
    str,
    dict[str, object] | None,
    str | None,
    tuple[ObservacionProducida, ...],
    DatosDeAuditoria,
]
"""Extensión con el dato opcional de auditoría (`sync/service.py`, change 14, tarea 7.1)."""

PERMISO_UBICACIONES = "ADMIN_CONFIGURACION"
PERMISO_STOCK_INICIAL = "IMPORTAR_DATOS"
PERMISO_TRANSFERIR = "TRANSFERIR_STOCK"
PERMISO_AJUSTAR = "AJUSTAR_STOCK"
PERMISO_PERMITIR_STOCK_NEGATIVO = "PERMITIR_STOCK_NEGATIVO"


def _exigir_permiso(sobre: SobreComando, sesion: object, codigo_permiso: str) -> None:
    """Falla con 403 `PERMISO_REQUERIDO` si el usuario del sobre no tiene el
    permiso (INV-01, SEG-06). Va PRIMERO: un rechazo no puede dejar nada
    escrito."""
    permitidos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id,
        sobre.usuario_id,
        sesion,  # type: ignore[arg-type]
    )
    if codigo_permiso not in permitidos:
        raise PermisoRequeridoError(f"Falta el permiso {codigo_permiso}.")


def _permisos_del_usuario(sobre: SobreComando, sesion: object) -> frozenset[str]:
    return frozenset(
        identidad_service.listar_permisos_del_usuario(
            sobre.organizacion_id,
            sobre.usuario_id,
            sesion,  # type: ignore[arg-type]
        )
    )


class UbicacionCrearContenidoV1(BaseModel):
    """`nombre`, `tipo` y `requiere_toma` (STK-02, D7). `extra="forbid"`:
    `organizacion_id` sale del token y una ubicación nace activa."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    tipo: Literal["DEPOSITO", "VEHICULO", "OTRO"]
    requiere_toma: bool = False


class UbicacionModificarContenidoV1(BaseModel):
    """Todos los campos editables de la ubicación (D7, D8): la modificación es un
    reemplazo completo, igual que los `PUT` de los demás maestros."""

    model_config = ConfigDict(extra="forbid")

    ubicacion_id: UUID
    nombre: str
    tipo: Literal["DEPOSITO", "VEHICULO", "OTRO"]
    requiere_toma: bool
    activo: bool


class LineaStockInicialContenidoV1(BaseModel):
    """Una línea del stock inicial (D5). `cantidad_base` es un entero estricto
    (INV-04): un número con decimales, un texto o un booleano son un contenido
    malformado. `costo_unitario` admite `int` y `float` A PROPÓSITO: con `Decimal`
    Pydantic convertiría en silencio un número JSON, y el escenario pide
    rechazarlo con `COSTO_INVALIDO` (INV-03); lo rechaza `costeo.validar_costo`,
    que solo admite `str` y `Decimal`."""

    model_config = ConfigDict(extra="forbid")

    producto_id: UUID
    cantidad_base: StrictInt
    costo_unitario: str | int | float | None = None


class StockInicialRegistrarContenidoV1(BaseModel):
    """`ubicacion_id` y `lineas` (1 a 200: lo valida el dominio con
    `LINEAS_INVALIDAS`, D5)."""

    model_config = ConfigDict(extra="forbid")

    ubicacion_id: UUID
    lineas: list[LineaStockInicialContenidoV1]


def manejar_ubicacion_crear(
    sobre: SobreComando,
    contenido: UbicacionCrearContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_UBICACIONES)
    ubicacion = stock_service.crear_ubicacion(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        nombre=contenido.nombre,
        tipo=contenido.tipo,
        requiere_toma=contenido.requiere_toma,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"ubicacion_id": str(ubicacion.id)}, None


def manejar_ubicacion_modificar(
    sobre: SobreComando,
    contenido: UbicacionModificarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_UBICACIONES)
    ubicacion = stock_service.modificar_ubicacion(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        ubicacion_id=contenido.ubicacion_id,
        nombre=contenido.nombre,
        tipo=contenido.tipo,
        requiere_toma=contenido.requiere_toma,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"ubicacion_id": str(ubicacion.id)}, None


def manejar_stock_inicial_registrar(
    sobre: SobreComando,
    contenido: StockInicialRegistrarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_STOCK_INICIAL)
    resultados = stock_service.registrar_stock_inicial(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        ubicacion_id=contenido.ubicacion_id,
        lineas=[
            LineaDeStockInicial(
                producto_id=linea.producto_id,
                cantidad_base=linea.cantidad_base,
                costo_unitario=linea.costo_unitario,  # type: ignore[arg-type]
            )
            for linea in contenido.lineas
        ],
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
        occurred_at=sobre.occurred_at,
    )
    return (
        "ACEPTADO",
        {
            "ubicacion_id": str(contenido.ubicacion_id),
            "lineas": [
                {
                    "producto_id": str(r.movimiento.producto_id),
                    "movimiento_id": str(r.movimiento.id),
                    "cantidad_base": r.movimiento.cantidad_base,
                    "saldo": r.saldo,
                }
                for r in resultados
            ],
        },
        None,
    )


registrar_handler("UBICACION_CREAR", 1, UbicacionCrearContenidoV1)(
    manejar_ubicacion_crear  # type: ignore[arg-type]
)
declarar_tipo("UBICACION_CREAR", admite_online=True, admite_offline=False)

registrar_handler("UBICACION_MODIFICAR", 1, UbicacionModificarContenidoV1)(
    manejar_ubicacion_modificar  # type: ignore[arg-type]
)
declarar_tipo("UBICACION_MODIFICAR", admite_online=True, admite_offline=False)

registrar_handler("STOCK_INICIAL_REGISTRAR", 1, StockInicialRegistrarContenidoV1)(
    manejar_stock_inicial_registrar  # type: ignore[arg-type]
)
declarar_tipo("STOCK_INICIAL_REGISTRAR", admite_online=True, admite_offline=False)


# --- STOCK_TRANSFERIR (change 14: STK-07, INV-15; `design.md` D1, D6, D9) -------------


class LineaTransferenciaContenidoV1(BaseModel):
    """Una línea de la transferencia: `cantidad_base` es un entero estricto (INV-04); que
    sea positiva lo valida el dominio con `CANTIDAD_INVALIDA`."""

    model_config = ConfigDict(extra="forbid")

    producto_id: UUID
    cantidad_base: StrictInt


class StockTransferirContenidoV1(BaseModel):
    """`extra="forbid"`: `organizacion_id` sale del token (INV-21, TR-08) y no hay campo de
    fecha: rige el `occurred_at` del sobre (TR-05). El largo de la observación y la
    cantidad de líneas los valida el dominio."""

    model_config = ConfigDict(extra="forbid")

    ubicacion_origen_id: UUID
    ubicacion_destino_id: UUID
    lineas: list[LineaTransferenciaContenidoV1]
    observacion: str | None = None


def manejar_stock_transferir(
    sobre: SobreComando,
    contenido: StockTransferirContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandlerConObservaciones:
    """Transfiere stock entre dos ubicaciones (permiso `TRANSFERIR_STOCK`). Con
    `PERMITIR_STOCK_NEGATIVO` una salida que no alcanza se aplica y el comando queda
    `ACEPTADO_CON_OBSERVACIONES` con un `STOCK_NEGATIVO` por cada producto y ubicación
    bajo cero (D1). El resultado se guarda y se reenvía tal cual ante un doble envío
    (INV-06); no incluye costos."""
    permisos = _permisos_del_usuario(sobre, sesion)
    if PERMISO_TRANSFERIR not in permisos:
        raise PermisoRequeridoError(f"Falta el permiso {PERMISO_TRANSFERIR}.")
    resultado = stock_service.transferir(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        ubicacion_origen_id=contenido.ubicacion_origen_id,
        ubicacion_destino_id=contenido.ubicacion_destino_id,
        lineas=[
            LineaDeTransferencia(producto_id=linea.producto_id, cantidad_base=linea.cantidad_base)
            for linea in contenido.lineas
        ],
        observacion=contenido.observacion,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
        occurred_at=sobre.occurred_at,
        permitir_negativo=PERMISO_PERMITIR_STOCK_NEGATIVO in permisos,
    )
    transferencia = resultado.transferencia
    observaciones = tuple(
        ObservacionProducida(
            codigo="STOCK_NEGATIVO",
            operacion_tipo="TRANSFERENCIA",
            operacion_id=transferencia.id,
            detalle={
                "producto_id": str(negativo.producto_id),
                "ubicacion_id": str(negativo.ubicacion_id),
                "saldo": negativo.saldo,
            },
        )
        for negativo in resultado.negativos
    )
    return (
        "ACEPTADO",
        {
            "transferencia_id": str(transferencia.id),
            "estado": transferencia.estado,
            "ubicacion_origen_id": str(transferencia.ubicacion_origen_id),
            "ubicacion_destino_id": str(transferencia.ubicacion_destino_id),
            "observacion": transferencia.observacion,
            "lineas": [
                {
                    "producto_id": str(saldo.producto_id),
                    "cantidad_base": saldo.cantidad_base,
                    "saldo_origen": saldo.saldo_origen,
                    "saldo_destino": saldo.saldo_destino,
                }
                for saldo in resultado.saldos
            ],
            "observaciones": ["STOCK_NEGATIVO"] if observaciones else [],
        },
        None,
        observaciones,
    )


registrar_handler("STOCK_TRANSFERIR", 1, StockTransferirContenidoV1)(
    manejar_stock_transferir  # type: ignore[arg-type]
)
declarar_tipo("STOCK_TRANSFERIR", admite_online=True, admite_offline=False)


# --- STOCK_AJUSTAR (change 14: STK-08; `design.md` D1, D3, D6, D9) ---------------------


class LineaAjusteContenidoV1(BaseModel):
    """Una línea del ajuste: `cantidad_base` es un entero estricto (INV-04) con signo; que sea
    distinta de cero lo valida el dominio con `CANTIDAD_INVALIDA`."""

    model_config = ConfigDict(extra="forbid")

    producto_id: UUID
    cantidad_base: StrictInt


class StockAjustarContenidoV1(BaseModel):
    """`extra="forbid"`: `organizacion_id` sale del token (INV-21, TR-08) y no hay campo de
    fecha (TR-05). El largo de la observación y la cantidad de líneas los valida el dominio."""

    model_config = ConfigDict(extra="forbid")

    ubicacion_id: UUID
    motivo_id: UUID
    lineas: list[LineaAjusteContenidoV1]
    observacion: str | None = None


def manejar_stock_ajustar(
    sobre: SobreComando,
    contenido: StockAjustarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandlerConAuditoria:
    """Ajusta el stock de una ubicación con un motivo (permiso `AJUSTAR_STOCK`). Un ajuste
    nunca deja stock negativo, tampoco con `PERMITIR_STOCK_NEGATIVO` (D1 = B), así que no
    produce observaciones. El resultado se guarda y se reenvía tal cual ante un doble envío
    (INV-06); no incluye costos (la ruta los agrega con `VER_COSTOS`).

    Devuelve además el dato de auditoría con el `motivo_id` del ajuste, que el bus copia a su
    única fila de auditoría (AUD-01, AUD-02, D10): es el único handler que lo hace."""
    _exigir_permiso(sobre, sesion, PERMISO_AJUSTAR)
    resultado = stock_service.ajustar(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        ubicacion_id=contenido.ubicacion_id,
        motivo_id=contenido.motivo_id,
        lineas=[
            LineaDeAjuste(producto_id=linea.producto_id, cantidad_base=linea.cantidad_base)
            for linea in contenido.lineas
        ],
        observacion=contenido.observacion,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
        occurred_at=sobre.occurred_at,
    )
    ajuste = resultado.ajuste
    return (
        "ACEPTADO",
        {
            "ajuste_id": str(ajuste.id),
            "estado": ajuste.estado,
            "ubicacion_id": str(ajuste.ubicacion_id),
            "motivo_id": str(ajuste.motivo_id),
            "observacion": ajuste.observacion,
            "lineas": [
                {
                    "producto_id": str(saldo.producto_id),
                    "cantidad_base": saldo.cantidad_base,
                    "saldo": saldo.saldo,
                }
                for saldo in resultado.saldos
            ],
        },
        None,
        (),
        DatosDeAuditoria(motivo_id=ajuste.motivo_id),
    )


registrar_handler("STOCK_AJUSTAR", 1, StockAjustarContenidoV1)(
    manejar_stock_ajustar  # type: ignore[arg-type]
)
declarar_tipo("STOCK_AJUSTAR", admite_online=True, admite_offline=False)


# --- STOCK_TRANSFERENCIA_ANULAR (change 14: TR-06; `design.md` D5, D5.4, D10) ----------------


class StockTransferenciaAnularContenidoV1(BaseModel):
    """Solo el id de la transferencia y el motivo de la anulación (D6): `organizacion_id`
    sale del token (INV-21) y la anulación es siempre total."""

    model_config = ConfigDict(extra="forbid")

    transferencia_id: UUID
    motivo_id: UUID


def manejar_stock_transferencia_anular(
    sobre: SobreComando,
    contenido: StockTransferenciaAnularContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandlerConAuditoria:
    """Anula una transferencia confirmada. `TRANSFERIR_STOCK` es siempre necesario (D5.4) y
    se comprueba primero; el servicio, con la cabecera ya bloqueada, exige además
    `ANULAR_TRANSFERENCIA` si la transferencia es de otro usuario. Con `PERMITIR_STOCK_NEGATIVO`
    una salida que no alcanza se aplica y el comando queda `ACEPTADO_CON_OBSERVACIONES`.

    Devuelve el motivo de la anulación como dato de auditoría, que el bus copia a su única
    fila (AUD-02, D10)."""
    permisos = _permisos_del_usuario(sobre, sesion)
    if PERMISO_TRANSFERIR not in permisos:
        raise PermisoRequeridoError(f"Falta el permiso {PERMISO_TRANSFERIR}.")
    resultado = stock_service.anular_transferencia(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        transferencia_id=contenido.transferencia_id,
        motivo_id=contenido.motivo_id,
        permisos=permisos,
        operation_id=sobre.operation_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        occurred_at=sobre.occurred_at,
    )
    transferencia = resultado.transferencia
    observaciones = tuple(
        ObservacionProducida(
            codigo="STOCK_NEGATIVO",
            operacion_tipo="TRANSFERENCIA",
            operacion_id=transferencia.id,
            detalle={
                "producto_id": str(negativo.producto_id),
                "ubicacion_id": str(negativo.ubicacion_id),
                "saldo": negativo.saldo,
            },
        )
        for negativo in resultado.negativos
    )
    assert transferencia.anulada_en is not None
    assert transferencia.anulacion_motivo_id is not None
    assert transferencia.anulada_por_id is not None
    return (
        "ACEPTADO",
        {
            "transferencia_id": str(transferencia.id),
            "estado": transferencia.estado,
            "ubicacion_origen_id": str(transferencia.ubicacion_origen_id),
            "ubicacion_destino_id": str(transferencia.ubicacion_destino_id),
            "observacion": transferencia.observacion,
            "anulacion": {
                "motivo_id": str(transferencia.anulacion_motivo_id),
                "anulada_en": transferencia.anulada_en.isoformat(),
                "anulada_por_id": str(transferencia.anulada_por_id),
            },
            "lineas": [
                {
                    "producto_id": str(saldo.producto_id),
                    "cantidad_base": saldo.cantidad_base,
                    "saldo_origen": saldo.saldo_origen,
                    "saldo_destino": saldo.saldo_destino,
                }
                for saldo in resultado.saldos
            ],
            "observaciones": ["STOCK_NEGATIVO"] if observaciones else [],
        },
        None,
        observaciones,
        DatosDeAuditoria(motivo_id=contenido.motivo_id),
    )


registrar_handler("STOCK_TRANSFERENCIA_ANULAR", 1, StockTransferenciaAnularContenidoV1)(
    manejar_stock_transferencia_anular  # type: ignore[arg-type]
)
declarar_tipo("STOCK_TRANSFERENCIA_ANULAR", admite_online=True, admite_offline=False)


# --- STOCK_AJUSTE_ANULAR (change 14: TR-06; `design.md` D5, D10) ----------------------------


class StockAjusteAnularContenidoV1(BaseModel):
    """Solo el id del ajuste y el motivo de la anulación (D6)."""

    model_config = ConfigDict(extra="forbid")

    ajuste_id: UUID
    motivo_id: UUID


def manejar_stock_ajuste_anular(
    sobre: SobreComando,
    contenido: StockAjusteAnularContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandlerConAuditoria:
    """Anula un ajuste confirmado, propio o de otro usuario (permiso `AJUSTAR_STOCK`). Con
    `PERMITIR_STOCK_NEGATIVO` el inverso de una línea positiva cuyo stock ya salió se aplica y
    el comando queda `ACEPTADO_CON_OBSERVACIONES` (D5 punto 6).

    Devuelve el motivo de la anulación como dato de auditoría (AUD-02, D10)."""
    permisos = _permisos_del_usuario(sobre, sesion)
    if PERMISO_AJUSTAR not in permisos:
        raise PermisoRequeridoError(f"Falta el permiso {PERMISO_AJUSTAR}.")
    resultado = stock_service.anular_ajuste(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        ajuste_id=contenido.ajuste_id,
        motivo_id=contenido.motivo_id,
        permitir_negativo=PERMISO_PERMITIR_STOCK_NEGATIVO in permisos,
        operation_id=sobre.operation_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        occurred_at=sobre.occurred_at,
    )
    ajuste = resultado.ajuste
    observaciones = tuple(
        ObservacionProducida(
            codigo="STOCK_NEGATIVO",
            operacion_tipo="AJUSTE_STOCK",
            operacion_id=ajuste.id,
            detalle={
                "producto_id": str(negativo.producto_id),
                "ubicacion_id": str(negativo.ubicacion_id),
                "saldo": negativo.saldo,
            },
        )
        for negativo in resultado.negativos
    )
    assert ajuste.anulado_en is not None
    assert ajuste.anulacion_motivo_id is not None
    assert ajuste.anulado_por_id is not None
    return (
        "ACEPTADO",
        {
            "ajuste_id": str(ajuste.id),
            "estado": ajuste.estado,
            "ubicacion_id": str(ajuste.ubicacion_id),
            "motivo_id": str(ajuste.motivo_id),
            "observacion": ajuste.observacion,
            "anulacion": {
                "motivo_id": str(ajuste.anulacion_motivo_id),
                "anulado_en": ajuste.anulado_en.isoformat(),
                "anulado_por_id": str(ajuste.anulado_por_id),
            },
            "lineas": [
                {
                    "producto_id": str(saldo.producto_id),
                    "cantidad_base": saldo.cantidad_base,
                    "saldo": saldo.saldo,
                }
                for saldo in resultado.saldos
            ],
            "observaciones": ["STOCK_NEGATIVO"] if observaciones else [],
        },
        None,
        observaciones,
        DatosDeAuditoria(motivo_id=contenido.motivo_id),
    )


registrar_handler("STOCK_AJUSTE_ANULAR", 1, StockAjusteAnularContenidoV1)(
    manejar_stock_ajuste_anular  # type: ignore[arg-type]
)
declarar_tipo("STOCK_AJUSTE_ANULAR", admite_online=True, admite_offline=False)
