"""Tareas 3.1 y 3.2 (change 17b; `design.md` D2, D3, D4): reglas puras de los medios de pago
administrables. Citan CAT-05, TR-06 y TR-09.
"""

from __future__ import annotations

import pytest

from app.modules.configuracion.domain.valores import (
    NombreVacioError,
    UltimoMedioActivoError,
    validar_nombre_medio_pago,
    validar_quedan_medios_activos,
)


class TestNombreDelMedio:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [("  Mercado Pago ", "Mercado Pago"), ("Efectivo", "Efectivo"), ("\tCheque\n", "Cheque")],
    )
    def test_se_recorta_el_nombre(self, entrada: str, esperado: str) -> None:
        assert validar_nombre_medio_pago(entrada) == esperado

    @pytest.mark.parametrize("entrada", ["", "   ", "\t\n"])
    def test_vacio_o_solo_espacios_es_nombre_invalido_422(self, entrada: str) -> None:
        with pytest.raises(NombreVacioError) as error:
            validar_nombre_medio_pago(entrada)

        assert error.value.codigo == "NOMBRE_INVALIDO"
        assert error.value.status_http == 422


class TestQuedanMediosActivos:
    """CAT-05, TR-06, D4: no se puede dar de baja el único medio activo."""

    def test_dar_de_baja_el_unico_activo_lanza_ultimo_medio_activo_409(self) -> None:
        with pytest.raises(UltimoMedioActivoError) as error:
            validar_quedan_medios_activos(1, medio_activo=True, activo_nuevo=False)

        assert error.value.codigo == "ULTIMO_MEDIO_ACTIVO"
        assert error.value.status_http == 409

    def test_con_dos_activos_se_puede_dar_de_baja_uno(self) -> None:
        validar_quedan_medios_activos(2, medio_activo=True, activo_nuevo=False)

    def test_reactivar_nunca_se_rechaza_ni_con_cero_activos(self) -> None:
        validar_quedan_medios_activos(0, medio_activo=False, activo_nuevo=True)
        validar_quedan_medios_activos(3, medio_activo=False, activo_nuevo=True)

    def test_modificar_un_medio_de_baja_sin_reactivarlo_no_cambia_la_cuenta(self) -> None:
        # El único activo es otro: este medio ya estaba de baja y sigue de baja.
        validar_quedan_medios_activos(1, medio_activo=False, activo_nuevo=False)

    def test_modificar_el_unico_activo_sin_darlo_de_baja_se_acepta(self) -> None:
        validar_quedan_medios_activos(1, medio_activo=True, activo_nuevo=True)
