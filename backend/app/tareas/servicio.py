"""El bucle del servicio `tareas` (change 28, D2, D6; modelo: `infra/backup/programar.sh`).

Duerme hasta la próxima `TAREAS_HORA` en la zona `TZ`, corre y vuelve a esperar. Una corrida que
falla no detiene el servicio: queda en el log y la salud avisa. `esperar` devuelve `True` si
pidieron parar (señal de parada), así el servicio atiende `docker compose stop` enseguida.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.core.clock import Clock
from app.tareas.configuracion import ConfiguracionDeTareas
from app.tareas.estado import guardar_estado
from app.tareas.programador import proxima_corrida

logger = logging.getLogger("app.tareas.servicio")
_TRAMO_MAXIMO_SEGUNDOS = 3600.0


def servir(
    config: ConfiguracionDeTareas,
    reloj: Clock,
    correr_una_vez: Callable[[], object],
    esperar: Callable[[float], bool],
) -> None:
    guardar_estado(config.estado_dir, {"arranque": reloj.now().isoformat()})
    logger.info(
        "Servicio de tareas en marcha: todos los días a las %s (%s)",
        config.hora.strftime("%H:%M"),
        config.zona.key,
    )
    while True:
        objetivo = proxima_corrida(reloj.now(), config.hora, config.zona)
        logger.info("Próxima corrida: %s", objetivo.isoformat())
        # Se espera por tramos y se vuelve a mirar el reloj: un salto de hora no la adelanta ni
        # la atrasa.
        while (faltan := (objetivo - reloj.now()).total_seconds()) > 0:
            if esperar(min(faltan, _TRAMO_MAXIMO_SEGUNDOS)):
                return
        correr_una_vez()
        if esperar(1.0):
            return
