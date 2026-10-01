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

from app.commands.catalogo import declarar_tipo
from app.commands.registro import registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad import service as identidad_service
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeStockInicial

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver
`catalogo/commands.py` para la justificación de no importarla de `sync`)."""

PERMISO_UBICACIONES = "ADMIN_CONFIGURACION"
PERMISO_STOCK_INICIAL = "IMPORTAR_DATOS"


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
