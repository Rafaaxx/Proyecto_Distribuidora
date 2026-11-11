"""Aviso externo opcional (`AVISO_TAREAS_URL`; change 28, D5 d, ADR-073; criterio de la copia).

Sin `AVISO_TAREAS_URL` no hace nada. Con ella, una corrida sana llama a la dirección y una con
diferencias o fallida llama a `<dirección>/fail` (protocolo de healthchecks.io). NUNCA envía datos
del negocio (ni cuerpo ni parámetros). Un aviso que no llega NO rompe la corrida ni cambia su
resultado: se reintenta unas pocas veces con espera corta y, si sigue sin llegar, solo queda en el
log. La dirección lleva un secreto: no se escribe en el log (tampoco dentro del mensaje del error).
"""

from __future__ import annotations

import logging
import time
import urllib.request
from collections.abc import Callable

logger = logging.getLogger("app.tareas.aviso")
ESPERA_MAXIMA_SEGUNDOS = 10.0
INTENTOS = 3
PAUSA_ENTRE_INTENTOS_SEGUNDOS = 2.0


def _llamar_http(destino: str, espera_maxima: float) -> None:
    pedido = urllib.request.Request(destino, method="GET")  # noqa: S310 (la fija el operador)
    with urllib.request.urlopen(pedido, timeout=espera_maxima):  # noqa: S310
        pass


def avisar(
    aviso_url: str | None,
    *,
    sana: bool,
    llamar: Callable[[str, float], None] = _llamar_http,
    pausar: Callable[[float], None] = time.sleep,
) -> None:
    if not aviso_url:
        return
    destino = aviso_url if sana else f"{aviso_url.rstrip('/')}/fail"
    for intento in range(1, INTENTOS + 1):
        try:
            llamar(destino, ESPERA_MAXIMA_SEGUNDOS)
            return
        except Exception as error:
            if intento == INTENTOS:
                logger.warning(
                    "No se pudo llamar al aviso externo (%d intentos): %s",
                    INTENTOS,
                    type(error).__name__,
                )
                return
            pausar(PAUSA_ENTRE_INTENTOS_SEGUNDOS)
