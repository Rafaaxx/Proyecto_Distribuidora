"""Paquete de negocio `costeo` (`docs/02-arquitectura.md` §5.3, §8).

Dueño del costo promedio ponderado móvil de cada producto (`costo_producto`,
`costo_producto_mov`, CST-10 a CST-14, ADR-002). No depende de ningún módulo de
negocio: el módulo `stock` lo usa solo por su `service.py`. El contenido son
`models.py`, `repository.py`, `service.py` y `domain/`.
"""
