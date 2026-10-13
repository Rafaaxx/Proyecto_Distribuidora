"""Tarea 3.1 (change 15, `design.md` D2, D3, D13; `01` §18): la máquina de estados de la
jornada, la decisión de qué ubicaciones admiten abrir y la validación de la liberación, todo
puro (`stock/domain/jornadas.py`).

Reglas citadas: INV-16, RUT-01, RUT-08, RUT-09, TR-09, `01` §18.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import DomainError
from app.modules.stock.domain import jornadas
from app.modules.stock.domain.errores import (
    JornadaEstadoInvalidoError,
    MotivoInvalidoError,
    ObservacionInvalidaError,
    UbicacionInactivaError,
    UbicacionSinTomaError,
)

ABIERTA = "ABIERTA"
EN_RENDICION = "EN_RENDICION"
CERRADA = "CERRADA"
LIBERADA = "LIBERADA"
ESTADOS = (ABIERTA, EN_RENDICION, CERRADA, LIBERADA)


# --- máquina de estados (`01` §18) --------------------------------------------------


@pytest.mark.parametrize(
    ("transicion", "desde", "hacia"),
    [
        (jornadas.rendir, ABIERTA, EN_RENDICION),
        (jornadas.cerrar, EN_RENDICION, CERRADA),
        (jornadas.liberar, ABIERTA, LIBERADA),
        (jornadas.liberar, EN_RENDICION, LIBERADA),
    ],
)
def test_las_transiciones_de_la_maquina_son_las_de_01_18(
    transicion: object, desde: str, hacia: str
) -> None:
    assert transicion(desde) == hacia  # type: ignore[operator]


@pytest.mark.parametrize(
    ("transicion", "desde"),
    [
        # Cerrar desde ABIERTA: no se cierra lo que no se rindió (D2).
        (jornadas.cerrar, ABIERTA),
        # Rendir dos veces.
        (jornadas.rendir, EN_RENDICION),
        # Cualquiera sobre una jornada terminada.
        (jornadas.rendir, CERRADA),
        (jornadas.rendir, LIBERADA),
        (jornadas.cerrar, CERRADA),
        (jornadas.cerrar, LIBERADA),
        (jornadas.liberar, CERRADA),
        (jornadas.liberar, LIBERADA),
    ],
)
def test_toda_otra_transicion_es_jornada_estado_invalido(transicion: object, desde: str) -> None:
    with pytest.raises(JornadaEstadoInvalidoError) as error:
        transicion(desde)  # type: ignore[operator]
    assert error.value.codigo == "JORNADA_ESTADO_INVALIDO"
    assert error.value.status_http == 409


@pytest.mark.parametrize(
    ("estado", "no_cerrada"),
    [(ABIERTA, True), (EN_RENDICION, True), (CERRADA, False), (LIBERADA, False)],
)
def test_inv16_solo_abierta_y_en_rendicion_ocupan_la_ubicacion(
    estado: str, no_cerrada: bool
) -> None:
    """INV-16: una jornada `CERRADA` o `LIBERADA` no ocupa la ubicación."""
    assert jornadas.esta_no_cerrada(estado) is no_cerrada


_TRANSICIONES = {"rendir": jornadas.rendir, "cerrar": jornadas.cerrar, "liberar": jornadas.liberar}


@given(st.lists(st.sampled_from(sorted(_TRANSICIONES)), max_size=12))
def test_inv16_una_jornada_terminada_nunca_vuelve_a_estar_no_cerrada(
    secuencia: list[str],
) -> None:
    """Propiedad: desde cualquier secuencia de transiciones, las aceptadas se encadenan según
    la máquina y, una vez `CERRADA` o `LIBERADA`, el estado ya no cambia ni vuelve a ocupar la
    ubicación."""
    estado = ABIERTA
    terminada = False
    for nombre in secuencia:
        try:
            estado = _TRANSICIONES[nombre](estado)
        except JornadaEstadoInvalidoError:
            continue
        assert not terminada, "se aceptó una transición sobre una jornada terminada"
        terminada = not jornadas.esta_no_cerrada(estado)
    if terminada:
        assert estado in {CERRADA, LIBERADA}
        assert not jornadas.esta_no_cerrada(estado)


# --- dónde se abre (D3) -----------------------------------------------------------


def test_se_abre_sobre_una_ubicacion_activa_que_requiere_toma() -> None:
    jornadas.validar_ubicacion_para_abrir(activa=True, requiere_toma=True)


def test_una_ubicacion_inactiva_no_admite_jornada() -> None:
    with pytest.raises(UbicacionInactivaError) as error:
        jornadas.validar_ubicacion_para_abrir(activa=False, requiere_toma=True)
    assert error.value.codigo == "UBICACION_INACTIVA"


def test_una_ubicacion_sin_toma_no_admite_jornada() -> None:
    with pytest.raises(UbicacionSinTomaError) as error:
        jornadas.validar_ubicacion_para_abrir(activa=True, requiere_toma=False)
    assert error.value.codigo == "UBICACION_SIN_TOMA"
    assert error.value.status_http == 409


def test_una_ubicacion_inactiva_y_sin_toma_se_informa_como_inactiva() -> None:
    """Orden de las reglas: primero que esté activa (ADR-038), después que requiera toma."""
    with pytest.raises(UbicacionInactivaError):
        jornadas.validar_ubicacion_para_abrir(activa=False, requiere_toma=False)


# --- observación de la liberación (D13) --------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("  Lo dejó en un comercio de Godoy Cruz  ", "Lo dejó en un comercio de Godoy Cruz"),
        ("x" * 500, "x" * 500),
    ],
)
def test_la_observacion_se_recorta_y_vacia_es_nula(
    entrada: str | None, esperada: str | None
) -> None:
    assert jornadas.normalizar_observacion_de_liberacion(entrada) == esperada


@pytest.mark.parametrize("entrada", ["x" * 501, " " + "x" * 501 + " "])
def test_una_observacion_de_mas_de_500_caracteres_se_rechaza(entrada: str) -> None:
    with pytest.raises(ObservacionInvalidaError) as error:
        jornadas.normalizar_observacion_de_liberacion(entrada)
    assert error.value.codigo == "OBSERVACION_INVALIDA"


# --- motivo de la liberación (D13, TR-09) -------------------------------------------


def test_el_motivo_activo_del_ambito_de_liberacion_es_valido() -> None:
    jornadas.validar_motivo_de_liberacion(activo=True, ambito="LIBERACION_JORNADA")


@pytest.mark.parametrize(
    ("activo", "ambito"),
    [(False, "LIBERACION_JORNADA"), (True, "AJUSTE_STOCK"), (False, "AJUSTE_STOCK")],
)
def test_el_motivo_inactivo_o_de_otro_ambito_es_invalido(activo: bool, ambito: str) -> None:
    with pytest.raises(MotivoInvalidoError) as error:
        jornadas.validar_motivo_de_liberacion(activo=activo, ambito=ambito)
    assert error.value.codigo == "MOTIVO_INVALIDO"


def test_los_errores_nuevos_son_errores_de_dominio_con_codigo_estable() -> None:
    from app.modules.stock.domain import errores

    esperados = {
        "JornadaEstadoInvalidoError": ("JORNADA_ESTADO_INVALIDO", 409),
        "UbicacionSinTomaError": ("UBICACION_SIN_TOMA", 409),
        "UbicacionTomadaError": ("UBICACION_TOMADA", 409),
        "UsuarioConJornadaError": ("USUARIO_CON_JORNADA", 409),
        "DispositivoConJornadaError": ("DISPOSITIVO_CON_JORNADA", 409),
    }
    for nombre, (codigo, status) in esperados.items():
        clase = getattr(errores, nombre)
        assert issubclass(clase, DomainError)
        assert (clase.codigo, clase.status_http) == (codigo, status)
