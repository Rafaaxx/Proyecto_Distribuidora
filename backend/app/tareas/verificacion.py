"""Verificación de consistencia (`02` §7.6, ADR-015, ADR-039; change 28, D4, D5).

Por cada organización compara, con SQL en la base, cada saldo materializado con su libro
(INV-12, INV-13, CST-13) y guarda el resultado. NUNCA corrige nada: una diferencia es un defecto
que se investiga. Las diferencias se guardan con identificadores e importes como texto, sin
nombres ni datos personales. Una falla en una organización se registra y no frena a las demás.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.modules.costeo import service as costeo_service
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.identidad import service as identidad_service
from app.modules.stock import service as stock_service

logger = logging.getLogger("app.tareas.verificacion")


@dataclass(frozen=True)
class ResultadoDeOrganizacion:
    """Lo que dejó la verificación de una organización: cuántas diferencias encontró, o el error
    que impidió verificarla (`error` es solo el tipo de la excepción, nunca datos de negocio)."""

    organizacion_id: UUID
    diferencias: int
    error: str | None = None


def verificar_organizacion(organizacion_id: UUID, sesion: Session) -> list[dict[str, object]]:
    """Las diferencias de la organización, listas para guardar como JSON (importes en texto)."""
    detalle = _diferencias_de_cuentas(organizacion_id, sesion)
    for diferencia in stock_service.verificar_consistencia(organizacion_id, sesion):
        detalle.append(
            {
                "tipo": "STOCK_TOTAL" if diferencia.ubicacion_id is None else "STOCK_SALDO",
                "producto_id": str(diferencia.producto_id),
                "ubicacion_id": (
                    None if diferencia.ubicacion_id is None else str(diferencia.ubicacion_id)
                ),
                "materializado": diferencia.valor_materializado,
                "esperado": diferencia.valor_esperado,
            }
        )
    for promedio in costeo_service.verificar_consistencia(organizacion_id, sesion):
        detalle.append(
            {
                "tipo": "PROMEDIO_COSTO",
                "producto_id": str(promedio.producto_id),
                "promedio_vigente": _texto(promedio.promedio_vigente),
                "promedio_historia": _texto(promedio.promedio_historia),
            }
        )
    return detalle


def _diferencias_de_cuentas(organizacion_id: UUID, sesion: Session) -> list[dict[str, object]]:
    return [
        {
            "tipo": "SALDO_CUENTA",
            "cuenta_tipo": diferencia.cuenta_tipo,
            "entidad_id": str(diferencia.entidad_id),
            "saldo_materializado": str(diferencia.saldo_materializado),
            "suma_del_libro": str(diferencia.suma_del_libro),
        }
        for diferencia in cuentas_service.verificar_consistencia(organizacion_id, sesion)
    ]


def _texto(valor: object) -> str | None:
    return None if valor is None else str(valor)


def ejecutar_verificacion(
    fabrica: sessionmaker[Session], reloj: Clock
) -> list[ResultadoDeOrganizacion]:
    """Verifica todas las organizaciones y guarda un resultado por cada una (una transacción por
    organización). Con diferencias escribe un registro CRÍTICO con la organización y la cantidad,
    sin nombres. La falla de una organización queda en el log y no frena a las otras; si ni
    siquiera se puede listar las organizaciones, el error sube."""
    with fabrica() as sesion:
        organizaciones = identidad_service.listar_organizaciones_ids(sesion)
    resultados: list[ResultadoDeOrganizacion] = []
    for organizacion_id in organizaciones:
        ejecutada_en = reloj.now()
        try:
            with fabrica() as sesion:
                diferencias = verificar_organizacion(organizacion_id, sesion)
                identidad_service.registrar_verificacion_de_consistencia(
                    organizacion_id,
                    sesion,
                    reloj,
                    ejecutada_en=ejecutada_en,
                    diferencias=diferencias,
                )
                sesion.commit()
        except Exception as error:
            logger.error(
                "Verificación de consistencia fallida: organizacion=%s error=%s",
                organizacion_id,
                type(error).__name__,
            )
            resultados.append(
                ResultadoDeOrganizacion(organizacion_id, 0, error=type(error).__name__)
            )
            continue
        if diferencias:
            logger.critical(
                "Verificación de consistencia: organizacion=%s diferencias=%d",
                organizacion_id,
                len(diferencias),
            )
        else:
            logger.info(
                "Verificación de consistencia: organizacion=%s sin diferencias", organizacion_id
            )
        resultados.append(ResultadoDeOrganizacion(organizacion_id, len(diferencias)))
    return resultados
