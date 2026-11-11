"""Orden del servicio de tareas (change 28, D2).

    python -m app.tareas          queda en marcha (verificación y limpieza todos los días)
    python -m app.tareas ahora    corre todo en el momento (`docker compose run --rm tareas ahora`);
                                  sale con 0 si no hay diferencias y con 1 si las hay o falló
    python -m app.tareas salud    sale con 0 si el servicio está sano (la salud de Docker)

Variables: DATABASE_URL (conexión de `app_mantenimiento`), TAREAS_HORA (HH:MM, 05:00), TZ,
ESTADO_DIR y AVISO_TAREAS_URL (opcional).
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from collections.abc import Mapping, Sequence

from app import modelos  # noqa: F401  (registra todos los modelos: claves foráneas entre módulos)
from app.core.clock import Clock, SystemClock
from app.core.db import crear_engine, crear_session_factory
from app.tareas import corrida, servicio
from app.tareas.configuracion import ConfiguracionDeTareas, ConfiguracionInvalidaError
from app.tareas.estado import evaluar_salud, leer_estado


def main(
    argv: Sequence[str] | None = None,
    *,
    entorno: Mapping[str, str] | None = None,
    reloj: Clock | None = None,
) -> int:
    argumentos = list(sys.argv[1:] if argv is None else argv)
    variables = os.environ if entorno is None else entorno
    reloj = reloj or SystemClock()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if len(argumentos) > 1 or (argumentos and argumentos[0] not in ("ahora", "salud")):
        print("Uso: python -m app.tareas [ahora|salud]", file=sys.stderr)
        return 2
    try:
        config = ConfiguracionDeTareas.desde_entorno(variables)
    except ConfiguracionInvalidaError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if argumentos == ["salud"]:
        sana, motivo = evaluar_salud(leer_estado(config.estado_dir), reloj.now())
        print(motivo)
        return 0 if sana else 1

    motor = crear_engine(config.database_url)
    fabrica = crear_session_factory(motor)

    def correr_una_vez() -> corrida.ResultadoDeCorrida:
        return corrida.correr(
            fabrica, reloj, estado_dir=config.estado_dir, aviso_url=config.aviso_url
        )

    try:
        if argumentos == ["ahora"]:
            resultado = correr_una_vez()
            _informar(resultado)
            return 0 if resultado.resultado == corrida.SIN_DIFERENCIAS else 1
        parar = threading.Event()
        for senal in (signal.SIGINT, signal.SIGTERM):
            signal.signal(senal, lambda *_: parar.set())
        servicio.servir(config, reloj, correr_una_vez, parar.wait)
        return 0
    finally:
        motor.dispose()


def _informar(resultado: corrida.ResultadoDeCorrida) -> None:
    if resultado.resultado == corrida.SIN_DIFERENCIAS:
        print("Verificación de consistencia: sin diferencias")
    elif resultado.resultado == corrida.CON_DIFERENCIAS:
        if resultado.diferencias == 1:
            detalle = "1 diferencia (no se corrige sola: avisar a soporte)"
        else:
            detalle = (
                f"{resultado.diferencias} diferencias (no se corrigen solas: avisar a soporte)"
            )
        print(f"Verificación de consistencia: {detalle}")
    else:
        print("Verificación de consistencia: la corrida falló (ver el registro)")
    if resultado.intentos_borrados is not None:
        if resultado.intentos_borrados == 1:
            intentos = "1 intento de inicio de sesión de más de 24 horas borrado"
        else:
            intentos = (
                f"{resultado.intentos_borrados} intentos de inicio de sesión "
                "de más de 24 horas borrados"
            )
        print(f"Limpieza: {intentos}")


if __name__ == "__main__":
    raise SystemExit(main())
