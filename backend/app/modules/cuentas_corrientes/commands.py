"""Handlers de comandos de `cuentas_corrientes` (change 08, grupo 5, tarea 5.1;
`design.md` D1, D3, D4, D5, D14 -- plantilla D7 del change 04: un tipo de comando
por escritura ya existente en `service.py`, un esquema de contenido versión 1, un
handler de pocas líneas que llama al servicio, sin `commit` propio, que lo
gestiona el bus).

Un solo tipo, `SALDO_INICIAL_REGISTRAR`, `ONLINE` y `admite_offline=False`
(`02` §6.5): exige `sesion` y `reloj` como parámetros de palabra clave y escribe
en la base del servidor. Permiso `IMPORTAR_DATOS` (D1), comprobado ACÁ y primero:
el catálogo de tipos no modela permisos y un lote de sincronización trae tipos
distintos, así que el punto donde se puede comprobar es el handler (mismo criterio
que `clientes/commands.py`). Un rechazo de permiso no deja movimiento, ni reserva
del `operation_id`, ni auditoría: el bus revierte la transacción entera.

Los handlers NO atrapan errores de dominio: los dejan subir, el bus revierte y el
comando puede reintentarse con contenido corregido. La única auditoría es la del
bus (ADR-022, `01` §21): el servicio no escribe una propia.

`dispositivo_id` sale del sobre (D14) y `occurred_at` también (TR-05).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.commands.catalogo import declarar_tipo
from app.commands.registro import registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.cuentas_corrientes import service as cuentas_corrientes_service
from app.modules.identidad import service as identidad_service

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver
`catalogo/commands.py` para la justificación de no importarla de `sync`)."""

PERMISO_SALDO_INICIAL = "IMPORTAR_DATOS"


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


class SaldoInicialRegistrarContenidoV1(BaseModel):
    """`cuenta_tipo`, `entidad_id`, `importe` y `sentido`, igual que las columnas
    (D5). `extra="forbid"`: `organizacion_id` sale del token y el saldo se deriva
    del libro (CC-04), así que mandarlos es un contenido malformado y no un dato
    que se descarte en silencio.

    `importe` viaja como string (`"150000.00"`, `CLAUDE.md` §4). El tipo admite
    también `int` y `float` A PROPÓSITO: con `Decimal`, Pydantic aceptaría un
    número JSON (`150000.0`) y lo convertiría en silencio, y el escenario de la spec
    pide que un número en lugar de un string se rechace con `IMPORTE_INVALIDO`
    (INV-03). Lo rechaza `domain/importe.py`, que solo admite `str` y `Decimal`."""

    model_config = ConfigDict(extra="forbid")

    cuenta_tipo: Literal["CLIENTE", "PROVEEDOR"]
    entidad_id: UUID
    importe: str | int | float
    sentido: Literal["AUMENTA", "REDUCE"]


def manejar_saldo_inicial_registrar(
    sobre: SobreComando,
    contenido: SaldoInicialRegistrarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_SALDO_INICIAL)
    resultado = cuentas_corrientes_service.registrar_saldo_inicial(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        cuenta_tipo=contenido.cuenta_tipo,
        entidad_id=contenido.entidad_id,
        importe=contenido.importe,
        sentido=contenido.sentido,
        occurred_at=sobre.occurred_at,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    return (
        "ACEPTADO",
        {"movimiento_id": str(resultado.movimiento.id), "saldo": str(resultado.saldo)},
        None,
    )


registrar_handler("SALDO_INICIAL_REGISTRAR", 1, SaldoInicialRegistrarContenidoV1)(
    manejar_saldo_inicial_registrar  # type: ignore[arg-type]
)
declarar_tipo("SALDO_INICIAL_REGISTRAR", admite_online=True, admite_offline=False)
