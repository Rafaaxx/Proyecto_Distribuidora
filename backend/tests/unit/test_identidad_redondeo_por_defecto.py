"""Tarea 5.1 (change 20c; `design.md` D10): regla pura del redondeo por defecto de la
organización. Cita PRC-01, PRC-14 e INV-03.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.identidad.domain.valores import (
    RedondeoDireccionInvalidaError,
    validar_redondeo_direccion,
    validar_redondeo_por_defecto,
)


class TestRedondeoPorDefecto:
    def test_los_dos_nulos_son_sin_definir(self) -> None:
        assert validar_redondeo_por_defecto(None, None) is None

    @pytest.mark.parametrize(
        ("multiplo", "direccion", "esperado"),
        [
            ("100.00", "ARRIBA", (Decimal("100.00"), "ARRIBA")),
            ("500", "ABAJO", (Decimal("500"), "ABAJO")),
            (" 0.50 ", "CERCANO", (Decimal("0.50"), "CERCANO")),
            ("0.01", "ARRIBA", (Decimal("0.01"), "ARRIBA")),
        ],
    )
    def test_prc01_un_multiplo_positivo_con_hasta_dos_decimales_y_su_direccion_es_valido(
        self, multiplo: str, direccion: str, esperado: tuple[Decimal, str]
    ) -> None:
        assert validar_redondeo_por_defecto(multiplo, direccion) == esperado

    @pytest.mark.parametrize("multiplo", ["0.00", "0", "10.005", "-1", "-0.01", "abc", "", "NaN"])
    def test_prc14_un_multiplo_cero_negativo_con_mas_de_dos_decimales_o_no_numerico_es_invalido(
        self, multiplo: str
    ) -> None:
        with pytest.raises(RedondeoDireccionInvalidaError) as error:
            validar_redondeo_por_defecto(multiplo, "ARRIBA")
        assert error.value.codigo == "REDONDEO_INVALIDO"
        assert error.value.status_http == 422

    @pytest.mark.parametrize("direccion", ["MEDIO", "arriba", "", "ARRIBA "])
    def test_prc01_una_direccion_desconocida_es_invalida(self, direccion: str) -> None:
        with pytest.raises(RedondeoDireccionInvalidaError) as error:
            validar_redondeo_por_defecto("100.00", direccion)
        assert error.value.codigo == "REDONDEO_INVALIDO"

    @pytest.mark.parametrize(("multiplo", "direccion"), [("100.00", None), (None, "ARRIBA")])
    def test_se_define_completo_o_no_se_define_uno_sin_el_otro_es_invalido(
        self, multiplo: str | None, direccion: str | None
    ) -> None:
        with pytest.raises(RedondeoDireccionInvalidaError) as error:
            validar_redondeo_por_defecto(multiplo, direccion)
        assert error.value.codigo == "REDONDEO_INVALIDO"
        assert error.value.status_http == 422


class TestElValidadorDeDireccionExistenteSeAlinea:
    def test_una_direccion_desconocida_responde_el_codigo_de_precios(self) -> None:
        with pytest.raises(RedondeoDireccionInvalidaError) as error:
            validar_redondeo_direccion("MEDIO")
        assert error.value.codigo == "REDONDEO_INVALIDO"
        assert error.value.status_http == 422

    @pytest.mark.parametrize("direccion", ["ARRIBA", "CERCANO", "ABAJO"])
    def test_las_validas_pasan_sin_cambios(self, direccion: str) -> None:
        assert validar_redondeo_direccion(direccion) == direccion
