"""Tarea 4.1 (change 20c; `design.md` D6, D7, D8): reglas puras de las alícuotas
administrables. Citan TR-02, INV-03, CAT-01, CAT-05 y TR-06.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.configuracion.domain.valores import (
    AlicuotaEnUsoError,
    UltimaAlicuotaActivaError,
    ValorAlicuotaInvalidoError,
    ValorNoModificableError,
    parsear_valor_alicuota,
    validar_baja_de_alicuota,
    validar_nombre_alicuota,
    validar_valor_alicuota,
    validar_valor_no_cambia,
)


class TestValorDeLaAlicuota:
    @pytest.mark.parametrize("valor", ["1.000000", "1", "1.5", "27"])
    def test_tr02_una_fraccion_de_uno_o_mas_es_invalida(self, valor: str) -> None:
        with pytest.raises(ValorAlicuotaInvalidoError):
            validar_valor_alicuota(Decimal(valor))

    @pytest.mark.parametrize("valor", ["0.999999", "0.270000", "0"])
    def test_tr02_una_fraccion_menor_que_uno_es_valida(self, valor: str) -> None:
        assert validar_valor_alicuota(Decimal(valor)) == Decimal(valor)

    @pytest.mark.parametrize("valor", ["-0.010000", "0.2100001"])
    def test_inv03_negativos_y_mas_de_seis_decimales_siguen_rechazados(self, valor: str) -> None:
        with pytest.raises(ValorAlicuotaInvalidoError):
            validar_valor_alicuota(Decimal(valor))


class TestParseoDelValor:
    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [("0.270000", "0.270000"), (" 0.105 ", "0.105"), ("0", "0"), ("0.000001", "0.000001")],
    )
    def test_inv03_un_texto_decimal_valido_se_parsea_exacto(
        self, texto: str, esperado: str
    ) -> None:
        assert parsear_valor_alicuota(texto) == Decimal(esperado)

    @pytest.mark.parametrize(
        "texto", ["abc", "", "NaN", "Infinity", "-0.5", "1.0", "0,21", "0.2100001"]
    )
    def test_un_texto_no_decimal_o_fuera_de_dominio_es_valor_invalido(self, texto: str) -> None:
        with pytest.raises(ValorAlicuotaInvalidoError):
            parsear_valor_alicuota(texto)


class TestNombreDeLaAlicuota:
    def test_se_recorta_el_nombre(self) -> None:
        assert validar_nombre_alicuota("  27% ") == "27%"

    @pytest.mark.parametrize("entrada", ["", "   ", "\t"])
    def test_vacio_es_nombre_invalido_422(self, entrada: str) -> None:
        with pytest.raises(Exception) as error:  # noqa: PT011 - se comprueba el código abajo
            validar_nombre_alicuota(entrada)
        assert getattr(error.value, "codigo", None) == "NOMBRE_INVALIDO"
        assert getattr(error.value, "status_http", None) == 422


class TestElValorNoCambia:
    def test_d6_el_mismo_valor_con_otra_escala_es_el_mismo_valor(self) -> None:
        validar_valor_no_cambia(Decimal("0.210000"), Decimal("0.21"))

    @pytest.mark.parametrize(
        ("guardado", "recibido"),
        [("0.210000", "0.270000"), ("0.105000", "0.105001"), ("0.000000", "0.010000")],
    )
    def test_d6_un_valor_distinto_es_valor_no_modificable_422(
        self, guardado: str, recibido: str
    ) -> None:
        with pytest.raises(ValorNoModificableError) as error:
            validar_valor_no_cambia(Decimal(guardado), Decimal(recibido))
        assert error.value.codigo == "VALOR_NO_MODIFICABLE"
        assert error.value.status_http == 422


class TestBajaDeUnaAlicuota:
    def test_cat01_con_productos_activos_es_alicuota_en_uso_con_la_cantidad(self) -> None:
        with pytest.raises(AlicuotaEnUsoError) as error:
            validar_baja_de_alicuota(productos_activos=12, activas=3, activo_nuevo=False)
        assert error.value.codigo == "ALICUOTA_EN_USO"
        assert error.value.status_http == 409
        assert error.value.extension == {"productos": 12}

    def test_cat01_un_solo_producto_tambien_impide_la_baja(self) -> None:
        with pytest.raises(AlicuotaEnUsoError) as error:
            validar_baja_de_alicuota(productos_activos=1, activas=2, activo_nuevo=False)
        assert error.value.extension == {"productos": 1}

    def test_d8_la_ultima_activa_sin_uso_es_ultima_alicuota_activa(self) -> None:
        with pytest.raises(UltimaAlicuotaActivaError) as error:
            validar_baja_de_alicuota(productos_activos=0, activas=1, activo_nuevo=False)
        assert error.value.codigo == "ULTIMA_ALICUOTA_ACTIVA"
        assert error.value.status_http == 409

    @pytest.mark.parametrize(("activas", "productos"), [(2, 0), (5, 0)])
    def test_cat05_sin_uso_y_con_otras_activas_la_baja_se_acepta(
        self, activas: int, productos: int
    ) -> None:
        validar_baja_de_alicuota(productos_activos=productos, activas=activas, activo_nuevo=False)

    @pytest.mark.parametrize(("activas", "productos"), [(1, 4), (0, 0), (2, 7)])
    def test_la_reactivacion_y_el_renombrado_no_validan_uso(
        self, activas: int, productos: int
    ) -> None:
        validar_baja_de_alicuota(productos_activos=productos, activas=activas, activo_nuevo=True)
