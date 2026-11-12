"""Una corrida completa del servicio de tareas (change 28, D2, D5, D6, D7).

Primero la verificación de consistencia de todas las organizaciones, después la limpieza de
`intento_login`; guarda el estado para la salud y, si hay `AVISO_TAREAS_URL`, avisa. Una falla en
una parte no impide la otra: queda en el log, la corrida se marca `FALLIDA` y la siguiente
reintenta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.tareas import aviso, estado, limpieza, verificacion

logger = logging.getLogger("app.tareas.corrida")

SIN_DIFERENCIAS = "SIN_DIFERENCIAS"
CON_DIFERENCIAS = "CON_DIFERENCIAS"
FALLIDA = "FALLIDA"


@dataclass(frozen=True)
class ResultadoDeCorrida:
    resultado: str
    diferencias: int
    organizaciones: int
    intentos_borrados: int | None


def correr(
    fabrica: sessionmaker[Session],
    reloj: Clock,
    *,
    estado_dir: Path,
    aviso_url: str | None,
) -> ResultadoDeCorrida:
    momento = reloj.now()
    fallo = False

    resultados: list[verificacion.ResultadoDeOrganizacion] = []
    try:
        resultados = verificacion.ejecutar_verificacion(fabrica, reloj)
    except Exception as error:
        fallo = True
        logger.error("La verificación de consistencia no pudo correr: %s", type(error).__name__)
    fallo = fallo or any(r.error is not None for r in resultados)

    borrados: int | None = None
    try:
        borrados = limpieza.limpiar_intentos_de_login(fabrica, reloj)
    except Exception as error:
        fallo = True
        logger.error("La limpieza de intentos de inicio de sesión falló: %s", type(error).__name__)

    diferencias = sum(r.diferencias for r in resultados)
    resultado = FALLIDA if fallo else CON_DIFERENCIAS if diferencias else SIN_DIFERENCIAS
    try:
        estado.guardar_estado(
            estado_dir,
            {
                "ultima_corrida": momento.isoformat(),
                "resultado": resultado,
                "diferencias": diferencias,
            },
        )
    except OSError as error:
        logger.error("No se pudo guardar el estado de la corrida: %s", type(error).__name__)
    aviso.avisar(aviso_url, sana=resultado == SIN_DIFERENCIAS)
    return ResultadoDeCorrida(resultado, diferencias, len(resultados), borrados)
