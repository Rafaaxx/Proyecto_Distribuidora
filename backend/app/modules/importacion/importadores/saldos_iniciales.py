"""Importador de saldos iniciales (`specs/importacion/puesta-en-marcha`, `design.md` D4,
D7, D12): una fila por saldo, sobre `cuentas_corrientes.service.registrar_saldo_inicial`.

Cada fila se registra por el mismo servicio que `SALDO_INICIAL_REGISTRAR` (TR-10, ADR-034):
varios saldos por cuenta mientras no tenga movimientos de otro tipo, cualquier estado de la
entidad salvo el consumidor final, importe positivo con hasta dos decimales y sentido
`AUMENTA`/`REDUCE` (o sus rótulos de negocio, ADR-034 punto 8). El momento es el
`occurred_at` del sobre (D7-A: sin fecha de corte).

La entidad se resuelve por clave natural (D4): el cliente por código y, si no hay, por
documento (solo si el texto es un documento); el proveedor por nombre. Orden de bloqueo
(`02` §7.3): las filas resueltas se escriben por (`cuenta_tipo`, entidad) ascendentes con un
orden estable, así una corrección sigue a su saldo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.modules.clientes import service as clientes_service
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.importacion.domain.errores import ErrorDeValor
from app.modules.importacion.domain.informe import ErrorDeFila, traducir_error
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.referencias import clave_de_texto, resolver_unica
from app.modules.importacion.domain.saldos import (
    CLIENTE,
    DatosDeSaldo,
    datos_de_saldo,
    documento_de_entidad,
)
from app.modules.importacion.domain.stock_inicial import ordenar_para_bloqueo
from app.modules.importacion.importadores.base import (
    ContextoDeImportacion,
    ejecutar_en_savepoint,
)
from app.modules.proveedores import service as proveedores_service

TIPO = "SALDOS_INICIALES"


@dataclass(frozen=True)
class _FilaResuelta:
    fila: int
    datos: DatosDeSaldo
    entidad_id: UUID


def importar_saldos_iniciales(
    contexto: ContextoDeImportacion, filas: Sequence[FilaPlanilla]
) -> list[ErrorDeFila]:
    org, sesion = contexto.organizacion_id, contexto.sesion
    entidades: dict[tuple[str, str], list[Any]] = {}

    def candidatos(datos: DatosDeSaldo) -> list[Any]:
        clave = (datos.cuenta_tipo, clave_de_texto(datos.entidad))
        if clave not in entidades:
            encontrados: list[Any]
            if datos.cuenta_tipo == CLIENTE:
                encontrados = clientes_service.buscar_clientes_por_codigo(
                    org,
                    datos.entidad,
                    sesion,  # type: ignore[arg-type]
                )
                documento = documento_de_entidad(datos.entidad)
                if not encontrados and documento is not None:
                    encontrados = clientes_service.buscar_clientes_por_documento(
                        org,
                        documento,
                        sesion,  # type: ignore[arg-type]
                    )
            else:
                encontrados = proveedores_service.buscar_proveedores_por_nombre(
                    org,
                    datos.entidad,
                    sesion,  # type: ignore[arg-type]
                )
            entidades[clave] = encontrados
        return entidades[clave]

    errores: list[ErrorDeFila] = []
    resueltas: list[_FilaResuelta] = []
    for fila in filas:
        try:
            datos = datos_de_saldo(fila)
            entidad = resolver_unica(
                candidatos(datos),
                columna="entidad",
                valor=datos.entidad,
                que="un cliente" if datos.cuenta_tipo == CLIENTE else "un proveedor",
            )
        except ErrorDeValor as error:
            errores.append(traducir_error(TIPO, fila.fila, error))
            continue
        resueltas.append(_FilaResuelta(fila.fila, datos, entidad.id))

    for resuelta in ordenar_para_bloqueo(
        resueltas, clave=lambda r: (r.datos.cuenta_tipo, r.entidad_id)
    ):

        def registrar(r: _FilaResuelta = resuelta) -> None:
            cuentas_service.registrar_saldo_inicial(
                org,
                sesion,  # type: ignore[arg-type]
                contexto.reloj,
                cuenta_tipo=r.datos.cuenta_tipo,
                entidad_id=r.entidad_id,
                importe=r.datos.importe,
                sentido=r.datos.sentido,
                occurred_at=contexto.occurred_at,
                usuario_id=contexto.usuario_id,
                dispositivo_id=contexto.dispositivo_id,
                operation_id=contexto.operation_id,
            )

        fallo = ejecutar_en_savepoint(TIPO, sesion, registrar, fila=resuelta.fila)
        if fallo is not None:
            errores.append(fallo)
    return errores
