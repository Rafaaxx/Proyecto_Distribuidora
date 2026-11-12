"""Paquete de negocio `importacion` (`docs/02-arquitectura.md` §5, `design.md` D10).

Orquesta la puesta en marcha desde planillas: lee el archivo, valida cada fila y
llama SOLO a los `service.py` de los demás módulos. Nadie depende de él. El
contenido del módulo son `models.py`, `repository.py`, `commands.py`,
`queries.py`, `api.py`, `schemas.py`, `domain/`, `lectores/` e `importadores/`.
"""
