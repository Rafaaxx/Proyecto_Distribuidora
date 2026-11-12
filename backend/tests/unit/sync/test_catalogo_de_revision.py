"""Tarea 12.1 (change 25; SYN-08, SEG-06, `02` §6.5): el catálogo de tipos de la revisión.

`OBSERVACION_RESOLVER` y `RECHAZO_RESOLVER` son solo `ONLINE` (administración revisa con conexión;
el teléfono nunca las encola) y exigen exactamente `REVISAR_OBSERVACIONES`.
"""

from __future__ import annotations

import pytest

from app.commands import catalogo
from app.modules.sync import revision_commands  # noqa: F401  (declara los tipos)

TIPOS = ("OBSERVACION_RESOLVER", "RECHAZO_RESOLVER")


@pytest.mark.parametrize("tipo", TIPOS)
def test_syn08_el_tipo_es_solo_online(tipo: str) -> None:
    declarado = catalogo._CATALOGO[tipo]
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)


@pytest.mark.parametrize("tipo", TIPOS)
def test_seg06_el_tipo_exige_revisar_observaciones(tipo: str) -> None:
    declarado = catalogo._CATALOGO[tipo]
    assert declarado.permisos == ("REVISAR_OBSERVACIONES",)
    assert declarado.sin_permiso is None
