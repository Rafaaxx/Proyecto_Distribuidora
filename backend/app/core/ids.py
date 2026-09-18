"""Generación de identificadores UUIDv7 (`docs/02-arquitectura.md` §9).

UUIDv7 se usa como clave primaria en toda entidad de negocio: es ordenable
por tiempo, lo que mejora la localidad de los índices. El stdlib de Python
todavía no expone `uuid.uuid7()` (llega en 3.14), así que se implementa
según RFC 9562 §5.7 con el método "Monotonic Random" (§6.2, método 2):
48 bits de milisegundos Unix + un contador de 12 bits que se incrementa
dentro del mismo milisegundo, para garantizar orden creciente estricto
incluso entre ids generados en el mismo milisegundo (single-threaded, que
es el caso del servidor de aplicación por proceso).
"""

import os
import threading
import time
from uuid import UUID

_lock = threading.Lock()
_ultimo_timestamp_ms = -1
_contador = 0


def nuevo_id() -> UUID:
    """Genera un UUIDv7 nuevo, estrictamente creciente entre llamadas."""
    global _ultimo_timestamp_ms, _contador

    with _lock:
        timestamp_ms = time.time_ns() // 1_000_000

        if timestamp_ms > _ultimo_timestamp_ms:
            _ultimo_timestamp_ms = timestamp_ms
            _contador = int.from_bytes(os.urandom(2), "big") & 0x0FFF
        else:
            _contador += 1
            if _contador > 0x0FFF:
                # Se agotó el contador dentro del milisegundo: se avanza el
                # reloj lógico un milisegundo para preservar el orden.
                _ultimo_timestamp_ms += 1
                _contador = 0
            timestamp_ms = _ultimo_timestamp_ms

        timestamp_bytes = timestamp_ms.to_bytes(6, byteorder="big")

        # Byte 6-7: versión (4 bits altos) + los 12 bits del contador (rand_a).
        version_y_contador = (0x7000 | _contador).to_bytes(2, byteorder="big")

        # Byte 8-15: variante RFC 4122 (2 bits altos) + 62 bits aleatorios (rand_b).
        rand_b = bytearray(os.urandom(8))
        rand_b[0] = (rand_b[0] & 0x3F) | 0x80

        return UUID(bytes=timestamp_bytes + version_y_contador + bytes(rand_b))
