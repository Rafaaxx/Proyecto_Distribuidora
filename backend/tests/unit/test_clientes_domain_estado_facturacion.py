"""Change 10, tarea 12.2: catálogo cerrado de `estado_facturacion_default` del cliente
(`docs/03` §10: `NO_REQUIERE` o `PENDIENTE`; nulo = el de la organización, VTA-08).

Regla pura del dominio de clientes: un valor fuera del catálogo es
`ESTADO_FACTURACION_INVALIDO` (422), nunca un fallo interno de la base. No normaliza
mayúsculas ni recorta (como `validar_estado`): es un valor de catálogo, no texto libre.
"""

from __future__ import annotations

import pytest

from app.modules.clientes.domain.errores import EstadoFacturacionInvalidoError
from app.modules.clientes.domain.estado import validar_estado_facturacion_default


@pytest.mark.parametrize("valor", ["NO_REQUIERE", "PENDIENTE"])
def test_los_valores_del_catalogo_pasan_sin_cambios(valor: str) -> None:
    assert validar_estado_facturacion_default(valor) == valor


def test_nulo_significa_el_de_la_organizacion_y_no_se_reemplaza() -> None:
    assert validar_estado_facturacion_default(None) is None


@pytest.mark.parametrize(
    "valor", ["FACTURADA", "PARCIAL", "pendiente", " PENDIENTE", "", "SI", "NO_REQUIERE,PENDIENTE"]
)
def test_un_valor_fuera_del_catalogo_es_estado_facturacion_invalido(valor: str) -> None:
    with pytest.raises(EstadoFacturacionInvalidoError) as excinfo:
        validar_estado_facturacion_default(valor)

    assert excinfo.value.codigo == "ESTADO_FACTURACION_INVALIDO"
    assert excinfo.value.status_http == 422
    assert "NO_REQUIERE" in excinfo.value.mensaje
    assert "PENDIENTE" in excinfo.value.mensaje
