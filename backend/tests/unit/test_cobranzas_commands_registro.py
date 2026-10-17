"""Change 17, tareas 8.1 y 12.3: `verificar_catalogo_y_registro` sigue en verde con
`COBRANZA_REGISTRAR`, declarado `ONLINE` y `OFFLINE` (con el permiso que exige, `design.md` D10),
con su handler registrado en la versión 1. `COBRANZA_ANULAR` sigue solo `ONLINE`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.commands import catalogo as catalogo_bus
from app.commands import registro as registro_bus
from app.commands.verificacion import verificar_catalogo_y_registro
from app.modules.catalogo import commands as catalogo_commands  # noqa: F401
from app.modules.cobranzas import commands as cobranzas_commands
from app.modules.identidad import commands as identidad_commands  # noqa: F401


def test_verificar_catalogo_y_registro_en_verde_con_el_tipo_de_cobranzas() -> None:
    verificar_catalogo_y_registro()  # No debe lanzar.


def test_cobranza_registrar_admite_offline_y_declara_su_permiso() -> None:
    """SYN-10, SEG-06, `design.md` D10: el bus compara `REGISTRAR_COBRANZA` al sincronizar y
    anota `PERMISO_REVOCADO` sobre la cobranza que el handler creó."""
    declarado = catalogo_bus.tipo_declarado("COBRANZA_REGISTRAR")

    assert declarado is not None, "COBRANZA_REGISTRAR no está declarado en el catálogo."
    assert declarado.admite_online is True
    assert declarado.admite_offline is True
    assert declarado.permiso_offline == "REGISTRAR_COBRANZA"
    assert declarado.operacion_offline == catalogo_bus.OperacionObservable(
        "COBRANZA", "cobranza_id"
    )


def test_cobranza_anular_sigue_solo_online_y_sin_permiso_offline() -> None:
    """Triangulación: los tipos solo `ONLINE` no se tocan (D10)."""
    declarado = catalogo_bus.tipo_declarado("COBRANZA_ANULAR")

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert declarado.permiso_offline is None


def test_cobranza_registrar_tiene_handler_registrado_en_version_1() -> None:
    handler = registro_bus.resolver_handler("COBRANZA_REGISTRAR", 1)

    assert handler.tipo == "COBRANZA_REGISTRAR"
    assert handler.version == 1
    assert handler.esquema is cobranzas_commands.CobranzaRegistrarContenidoV1


@pytest.mark.parametrize("campo_extra", ["organizacion_id", "estado", "origen", "venta_id"])
def test_el_contenido_no_acepta_campos_que_la_cobranza_no_elige(campo_extra: str) -> None:
    """INV-21, TR-08, COB-01: la organización sale del token y la cobranza nace `CONFIRMADA` de
    origen `INDEPENDIENTE`."""
    contenido = {
        "cobranza_id": "0198f3a0-0000-7000-8000-000000000001",
        "cliente_id": "0198f3a0-0000-7000-8000-000000000002",
        "importe": "10.00",
        "medios": [],
        campo_extra: "x",
    }

    with pytest.raises(ValidationError):
        cobranzas_commands.CobranzaRegistrarContenidoV1.model_validate(contenido)
