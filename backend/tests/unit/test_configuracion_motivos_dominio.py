"""Tarea 2.1 (change 20c; `design.md` D2, D4): reglas puras de los motivos administrables.
Citan CAT-05, TR-06 y TR-09.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.configuracion.domain.valores import (
    NombreVacioError,
    UltimoMotivoActivoError,
    validar_nombre_motivo,
    validar_quedan_motivos_activos,
)


class TestNombreDelMotivo:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [("  Robo ", "Robo"), ("Rotura", "Rotura"), ("\tMerma\n", "Merma")],
    )
    def test_se_recorta_el_nombre(self, entrada: str, esperado: str) -> None:
        assert validar_nombre_motivo(entrada) == esperado

    @pytest.mark.parametrize("entrada", ["", "   ", "\t\n"])
    def test_vacio_o_solo_espacios_es_nombre_invalido_422(self, entrada: str) -> None:
        with pytest.raises(NombreVacioError) as error:
            validar_nombre_motivo(entrada)

        assert error.value.codigo == "NOMBRE_INVALIDO"
        assert error.value.status_http == 422


class TestQuedanMotivosActivos:
    """CAT-05, TR-06, D4: un ámbito no puede quedarse sin ningún motivo activo."""

    def test_dar_de_baja_el_unico_activo_lanza_ultimo_motivo_activo_409(self) -> None:
        unico = uuid4()

        with pytest.raises(UltimoMotivoActivoError) as error:
            validar_quedan_motivos_activos({unico}, unico, False)

        assert error.value.codigo == "ULTIMO_MOTIVO_ACTIVO"
        assert error.value.status_http == 409

    def test_dar_de_baja_uno_de_dos_activos_se_acepta(self) -> None:
        uno, otro = uuid4(), uuid4()

        validar_quedan_motivos_activos({uno, otro}, uno, False)

    def test_dar_de_baja_un_motivo_ya_inactivo_no_cuenta_como_baja(self) -> None:
        activo, inactivo = uuid4(), uuid4()

        validar_quedan_motivos_activos({activo}, inactivo, False)

    def test_reactivar_o_dejar_activo_siempre_se_acepta(self) -> None:
        inactivo, activo = uuid4(), uuid4()

        validar_quedan_motivos_activos(set(), inactivo, True)
        validar_quedan_motivos_activos({activo}, activo, True)
