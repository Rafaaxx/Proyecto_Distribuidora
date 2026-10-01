"""Paquete de negocio `stock` (`docs/02-arquitectura.md` §5.3, §8).

Dueño de las ubicaciones, del libro de stock (`stock_movimiento`) y de su saldo
materializado (`stock_saldo`). Alcanza a `catalogo` y a `costeo` solo por su
`service.py`. El contenido son `models.py`, `repository.py`, `service.py` y
`domain/`.
"""
