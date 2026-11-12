"""Handlers de `JORNADA_RENDIR` v2 y `JORNADA_CERRAR` v2 (change 24; `design.md` D2, D3, D5, D6;
RUT-05, RUT-06, RUT-08). `JORNADA_CERRAR` v1 (sin devolución) sigue en `jornadas_commands.py`.

La rendición con conteo reemplaza a la v1 (change 15), que deja de registrarse: un
`JORNADA_RENDIR` v1 responde `VERSION_DE_COMANDO_SIN_HANDLER` (D2). Es `ONLINE` y
`admite_offline=False` (`02` §6.5), permiso `RENDIR_JORNADA`, que se comprueba ACÁ y primero: un
rechazo no deja nada escrito (el bus revierte). El usuario y el dispositivo salen del sobre. Los
handlers no atrapan errores de dominio ni hacen `commit`.

El resultado que se guarda y se reenvía tal cual ante un doble envío (INV-06) es la jornada y la
rendición con sus líneas (cantidades, sin costos: el valor de las diferencias es de `VER_COSTOS`,
D4); la auditoría la escribe el bus (ADR-022).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictInt

from app.commands.catalogo import declarar_tipo
from app.commands.registro import SesionDeHandler, registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad import service as identidad_service
from app.modules.stock import service as stock_service
from app.modules.stock.jornadas_commands import resultado_de_jornada

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `stock/jornadas_commands.py`."""

PERMISO_RENDIR_JORNADA = "RENDIR_JORNADA"


class LineaDeConteoContenidoV2(BaseModel):
    """Una línea del conteo. Las cantidades son enteros estrictos (INV-04): un número con
    decimales, un texto, un booleano o un nulo son un contenido malformado (el número con
    decimales ni siquiera entra a la huella canónica del sobre); que no sea negativa lo valida el
    dominio con `CANTIDAD_INVALIDA`."""

    model_config = ConfigDict(extra="forbid")

    producto_id: UUID
    cantidad_contada: StrictInt
    cantidad_esperada: StrictInt


class JornadaRendirContenidoV2(BaseModel):
    """`jornada_id`, el conteo y una observación opcional (el largo lo valida el dominio:
    `OBSERVACION_INVALIDA`). `extra="forbid"`: la organización sale del token (INV-21) y el
    usuario y el dispositivo, de la sesión."""

    model_config = ConfigDict(extra="forbid")

    jornada_id: UUID
    lineas: list[LineaDeConteoContenidoV2]
    observacion: str | None = None


def resultado_de_rendicion(resultado: stock_service.ResultadoDeRendicion) -> dict[str, object]:
    """La jornada con su rendición: ids como texto y sin costos (se guarda en
    `comando.resultado`, JSON)."""
    rendicion = resultado.rendicion
    return {
        **resultado_de_jornada(resultado.jornada),
        "rendicion_id": str(rendicion.id),
        "observacion": rendicion.observacion,
        "lineas": [
            {
                "producto_id": str(linea.producto_id),
                "cantidad_esperada": linea.cantidad_esperada,
                "cantidad_contada": linea.cantidad_contada,
                "diferencia": linea.diferencia,
            }
            for linea in resultado.lineas
        ],
    }


def manejar_jornada_rendir(
    sobre: SobreComando,
    contenido: JornadaRendirContenidoV2,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    permisos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    if PERMISO_RENDIR_JORNADA not in permisos:
        raise PermisoRequeridoError(f"Falta el permiso {PERMISO_RENDIR_JORNADA}.")
    resultado = stock_service.rendir_jornada(
        sobre.organizacion_id,
        sesion,
        reloj,
        jornada_id=contenido.jornada_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
        occurred_at=sobre.occurred_at,
        lineas=[
            stock_service.LineaContada(
                producto=linea.producto_id,
                contada=linea.cantidad_contada,
                esperada=linea.cantidad_esperada,
            )
            for linea in contenido.lineas
        ],
        observacion=contenido.observacion,
    )
    return "ACEPTADO", resultado_de_rendicion(resultado), None


registrar_handler("JORNADA_RENDIR", 2, JornadaRendirContenidoV2)(manejar_jornada_rendir)
declarar_tipo(
    "JORNADA_RENDIR", admite_online=True, admite_offline=False, permisos=("RENDIR_JORNADA",)
)


# --- JORNADA_CERRAR v2: el cierre con el remanente (RUT-08, D6) -----------------------------

PERMISO_TRANSFERIR_STOCK = "TRANSFERIR_STOCK"


class LineaDeDevolucionContenidoV2(BaseModel):
    """Una línea de la devolución: `cantidad_base` es un entero estricto (INV-04); que sea
    positiva la valida el dominio con `CANTIDAD_INVALIDA`."""

    model_config = ConfigDict(extra="forbid")

    producto_id: UUID
    cantidad_base: StrictInt


class DevolucionContenidoV2(BaseModel):
    """El destino y de 1 a 200 líneas (el largo y los repetidos los valida el dominio)."""

    model_config = ConfigDict(extra="forbid")

    ubicacion_destino_id: UUID
    lineas: list[LineaDeDevolucionContenidoV2]


class JornadaCerrarContenidoV2(BaseModel):
    """`jornada_id` y una `devolucion` opcional. `extra="forbid"` (INV-21)."""

    model_config = ConfigDict(extra="forbid")

    jornada_id: UUID
    devolucion: DevolucionContenidoV2 | None = None


def manejar_jornada_cerrar_v2(
    sobre: SobreComando,
    contenido: JornadaCerrarContenidoV2,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Cierra la jornada `EN_RENDICION` (`RENDIR_JORNADA`) y, con devolución, además exige
    `TRANSFERIR_STOCK` y escribe la transferencia común del remanente (D6). Los permisos se
    comprueban ACÁ y primero: un rechazo no deja nada escrito."""
    permisos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    if PERMISO_RENDIR_JORNADA not in permisos:
        raise PermisoRequeridoError(f"Falta el permiso {PERMISO_RENDIR_JORNADA}.")
    devolucion = contenido.devolucion
    if devolucion is not None and PERMISO_TRANSFERIR_STOCK not in permisos:
        raise PermisoRequeridoError(f"Falta el permiso {PERMISO_TRANSFERIR_STOCK}.")
    resultado = stock_service.cerrar_jornada_con_devolucion(
        sobre.organizacion_id,
        sesion,
        reloj,
        jornada_id=contenido.jornada_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
        occurred_at=sobre.occurred_at,
        destino_id=None if devolucion is None else devolucion.ubicacion_destino_id,
        lineas=[]
        if devolucion is None
        else [
            stock_service.LineaDeTransferencia(
                producto_id=linea.producto_id, cantidad_base=linea.cantidad_base
            )
            for linea in devolucion.lineas
        ],
    )
    transferencia = resultado.devolucion
    return (
        "ACEPTADO",
        {
            **resultado_de_jornada(resultado.jornada),
            "transferencia_id": None
            if transferencia is None
            else str(transferencia.transferencia.id),
        },
        None,
    )


registrar_handler("JORNADA_CERRAR", 2, JornadaCerrarContenidoV2)(manejar_jornada_cerrar_v2)
