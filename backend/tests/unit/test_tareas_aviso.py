"""Change 28, tarea 8.5: el aviso externo de `tareas` a un servicio de «hombre muerto»
(`AVISO_TAREAS_URL`; `design.md` D5 d, ADR-073). HTTP y pausa inyectables: sin red real.

Reglas citadas: `02` §7.6 (verificación diaria), `02` §17.
"""

from __future__ import annotations

import logging

import pytest

from app.tareas import aviso

BASE = "https://hc-ping.com/secreto-abc123"


class _Registro:
    def __init__(self, fallos: int = 0) -> None:
        self.destinos: list[str] = []
        self.esperas: list[float] = []
        self._fallos = fallos

    def llamar(self, destino: str, espera_maxima: float) -> None:
        self.destinos.append(destino)
        assert espera_maxima <= 10  # espera corta
        if len(self.destinos) <= self._fallos:
            raise OSError(f"sin red hacia {destino}")

    def pausar(self, segundos: float) -> None:
        self.esperas.append(segundos)


def test_corrida_sana_llama_a_la_direccion_base() -> None:
    r = _Registro()
    aviso.avisar(BASE, sana=True, llamar=r.llamar, pausar=r.pausar)
    assert r.destinos == [BASE]


def test_corrida_con_diferencias_o_fallida_llama_a_fail_y_normaliza_la_barra_final() -> None:
    r = _Registro()
    aviso.avisar(BASE, sana=False, llamar=r.llamar, pausar=r.pausar)
    aviso.avisar(BASE + "/", sana=False, llamar=r.llamar, pausar=r.pausar)
    assert r.destinos == [BASE + "/fail", BASE + "/fail"]


@pytest.mark.parametrize("vacia", [None, ""])
def test_sin_direccion_no_llama_a_nadie(vacia: str | None) -> None:
    r = _Registro()
    aviso.avisar(vacia, sana=True, llamar=r.llamar, pausar=r.pausar)
    aviso.avisar(vacia, sana=False, llamar=r.llamar, pausar=r.pausar)
    assert r.destinos == []


def test_un_error_transitorio_se_reintenta_y_despues_llega() -> None:
    r = _Registro(fallos=2)
    aviso.avisar(BASE, sana=True, llamar=r.llamar, pausar=r.pausar)
    assert r.destinos == [BASE] * 3
    assert len(r.esperas) == 2


def test_un_error_permanente_no_rompe_reintenta_acotado_y_no_loguea_la_direccion(
    caplog: pytest.LogCaptureFixture,
) -> None:
    r = _Registro(fallos=99)
    with caplog.at_level(logging.DEBUG):
        aviso.avisar(BASE, sana=False, llamar=r.llamar, pausar=r.pausar)  # no lanza
    assert len(r.destinos) == aviso.INTENTOS
    assert "No se pudo llamar al aviso externo" in caplog.text
    assert "OSError" in caplog.text
    assert "secreto-abc123" not in caplog.text
    assert "hc-ping.com" not in caplog.text


def test_la_pausa_por_defecto_no_se_usa_si_el_primer_intento_sale_bien() -> None:
    r = _Registro()
    aviso.avisar(BASE, sana=True, llamar=r.llamar)  # pausar real, no debe invocarse
    assert r.destinos == [BASE]
