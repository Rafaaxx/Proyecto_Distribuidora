"""Tarea 3.1 (change 11b): la condición frente al IVA de la organización y la regla
derivada *computa crédito fiscal* (CST-06), funciones puras de `identidad/domain/valores.py`
(`design.md` D1, D2)."""

from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.modules.identidad.domain.valores import (
    CONDICIONES_IVA,
    CondicionIvaInvalidaError,
    ModoImpositivoIncompatibleError,
    computa_credito_fiscal,
    validar_compatibilidad_de_condicion,
    validar_condicion_iva,
)


class TestValidarCondicionIva:
    @pytest.mark.parametrize("valor", ["RESPONSABLE_INSCRIPTO", "MONOTRIBUTO", "EXENTO"])
    def test_acepta_los_valores_del_dominio_cerrado(self, valor: str) -> None:
        assert validar_condicion_iva(valor) == valor

    @pytest.mark.parametrize("valor", ["CONSUMIDOR_FINAL", "monotributo", "", "INSCRIPTO"])
    def test_rechaza_un_valor_fuera_del_dominio(self, valor: str) -> None:
        with pytest.raises(CondicionIvaInvalidaError) as error:
            validar_condicion_iva(valor)

        assert error.value.codigo == "IDENTIDAD_CONDICION_IVA_INVALIDA"
        assert isinstance(error.value, DomainError)

    def test_el_dominio_tiene_exactamente_las_tres_condiciones(self) -> None:
        assert set(CONDICIONES_IVA) == {"RESPONSABLE_INSCRIPTO", "MONOTRIBUTO", "EXENTO"}


class TestComputaCreditoFiscal:
    """CST-06: solo un responsable inscripto computa crédito fiscal de IVA en compras."""

    def test_el_responsable_inscripto_computa(self) -> None:
        assert computa_credito_fiscal("RESPONSABLE_INSCRIPTO") is True

    @pytest.mark.parametrize("condicion", ["MONOTRIBUTO", "EXENTO"])
    def test_monotributo_y_exento_no_computan(self, condicion: str) -> None:
        assert computa_credito_fiscal(condicion) is False

    def test_una_condicion_desconocida_no_se_interpreta_como_falsa(self) -> None:
        with pytest.raises(CondicionIvaInvalidaError):
            computa_credito_fiscal("OTRA")


class TestCompatibilidadDeCondicion:
    """D2: una organización no inscripta es modo A y sin modalidad de IVA al facturar."""

    @pytest.mark.parametrize(
        ("modo", "modalidad"), [("A", None), ("B", "CLIENTE"), ("C", "ABSORBIDO"), ("B", None)]
    )
    def test_el_responsable_inscripto_acepta_cualquier_modo_y_modalidad(
        self, modo: str, modalidad: str | None
    ) -> None:
        validar_compatibilidad_de_condicion("RESPONSABLE_INSCRIPTO", modo, modalidad)

    @pytest.mark.parametrize("condicion", ["MONOTRIBUTO", "EXENTO"])
    def test_una_organizacion_no_inscripta_acepta_modo_a_sin_modalidad(
        self, condicion: str
    ) -> None:
        validar_compatibilidad_de_condicion(condicion, "A", None)

    @pytest.mark.parametrize("condicion", ["MONOTRIBUTO", "EXENTO"])
    @pytest.mark.parametrize(
        ("modo", "modalidad"), [("B", None), ("C", None), ("A", "CLIENTE"), ("A", "ABSORBIDO")]
    )
    def test_una_organizacion_no_inscripta_rechaza_otro_modo_o_una_modalidad(
        self, condicion: str, modo: str, modalidad: str | None
    ) -> None:
        with pytest.raises(ModoImpositivoIncompatibleError) as error:
            validar_compatibilidad_de_condicion(condicion, modo, modalidad)

        assert error.value.codigo == "MODO_IMPOSITIVO_INCOMPATIBLE"
