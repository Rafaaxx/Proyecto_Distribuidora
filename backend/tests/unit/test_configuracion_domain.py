"""Pruebas unitarias del dominio puro de `configuracion` (tarea 5.2, 5.3, 5.4).

Cubren la enumeración cerrada de `ambito` de `motivo` y la validación de
`valor` de `alicuota_iva` (`docs/03-modelo-de-datos.md` §4; INV-03, TR-02).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.modules.configuracion.domain.valores import (
    AMBITOS_MOTIVO,
    AmbitoMotivoInvalidoError,
    NombreVacioError,
    ValorAlicuotaInvalidoError,
    validar_ambito_motivo,
    validar_nombre_medio_pago,
    validar_valor_alicuota,
)


class TestAmbitoMotivo:
    @pytest.mark.parametrize("valor", list(AMBITOS_MOTIVO))
    def test_acepta_los_diez_ambitos_de_la_lista_cerrada(self, valor: str) -> None:
        assert validar_ambito_motivo(valor) == valor

    def test_hay_exactamente_diez_ambitos(self) -> None:
        """Ratchet: la lista cerrada de `motivo.ambito` (`03` §4) no crece sin que la
        lista cerrada y su `CHECK` en la base cambien los dos (TR-09). El octavo es
        `ANULACION_PAGO` (PAG-03, change 12); el noveno y el décimo son
        `ANULACION_TRANSFERENCIA` y `ANULACION_AJUSTE` (`design.md` D5 del change 14)."""
        assert len(AMBITOS_MOTIVO) == 10

    def test_el_ambito_de_la_anulacion_de_pago_esta_en_la_lista(self) -> None:
        """D1: sin esto, `PAGO_PROVEEDOR_ANULAR` no podría exigir un motivo válido."""
        assert validar_ambito_motivo("ANULACION_PAGO") == "ANULACION_PAGO"

    @pytest.mark.parametrize("ambito", ["ANULACION_TRANSFERENCIA", "ANULACION_AJUSTE"])
    def test_los_ambitos_de_anulacion_de_stock_estan_en_la_lista(self, ambito: str) -> None:
        """Change 14, D5: sin esto, las anulaciones de transferencias y ajustes no podrían
        exigir un motivo válido; "AJUSTE_STOCK" no sirve para un error de carga."""
        assert validar_ambito_motivo(ambito) == ambito

    def test_rechaza_un_ambito_fuera_de_la_lista_cerrada(self) -> None:
        with pytest.raises(AmbitoMotivoInvalidoError) as exc_info:
            validar_ambito_motivo("DEVOLUCION")

        assert issubclass(AmbitoMotivoInvalidoError, DomainError)
        assert exc_info.value.codigo == "CONFIGURACION_AMBITO_MOTIVO_INVALIDO"


class TestValorAlicuota:
    def test_acepta_veintiuno_por_ciento_como_fraccion_de_seis_decimales(self) -> None:
        assert validar_valor_alicuota(Decimal("0.210000")) == Decimal("0.210000")

    def test_acepta_cero_como_alicuota_valida(self) -> None:
        assert validar_valor_alicuota(Decimal("0.000000")) == Decimal("0.000000")

    def test_rechaza_un_valor_recibido_como_float(self) -> None:
        with pytest.raises(ValorAlicuotaInvalidoError):
            validar_valor_alicuota(0.21)  # type: ignore[arg-type]

    def test_rechaza_un_valor_con_mas_de_seis_decimales(self) -> None:
        with pytest.raises(ValorAlicuotaInvalidoError):
            validar_valor_alicuota(Decimal("0.2100001"))

    def test_rechaza_un_valor_negativo(self) -> None:
        with pytest.raises(ValorAlicuotaInvalidoError):
            validar_valor_alicuota(Decimal("-0.050000"))


class TestNombreMedioPago:
    def test_acepta_un_nombre_no_vacio(self) -> None:
        assert validar_nombre_medio_pago("Efectivo") == "Efectivo"

    def test_rechaza_un_nombre_vacio(self) -> None:
        with pytest.raises(NombreVacioError):
            validar_nombre_medio_pago("")

    def test_rechaza_un_nombre_de_solo_espacios(self) -> None:
        with pytest.raises(NombreVacioError):
            validar_nombre_medio_pago("   ")
