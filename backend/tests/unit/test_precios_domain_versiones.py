"""Change 13, tarea 8.1: la versión vigente, los estados derivados y las reglas de transición de
una versión de lista (`precios/domain/versiones.py`; spec `precios/versiones-de-lista`;
`design.md` D6; `01` §18).

Las fechas del ejemplo son las del spec: la versión n.º 2 desde el 01/09 sin vigencia hasta, la
n.º 3 desde el 01/10 hasta el 01/11. El reloj es un dato de entrada: nada de acá lee la hora.

Reglas citadas: PRC-02, PRC-03, PRC-04, PRC-05, INV-11, `design.md` D6.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.precios.domain.errores import (
    VersionNoEsBorradorError,
    VersionNoPublicadaError,
    VersionSinPreciosError,
    VersionYaVigenteError,
    VigenciaDuplicadaError,
    VigenciaInvalidaError,
)
from app.modules.precios.domain.versiones import (
    HISTORICA,
    PROGRAMADA,
    VIGENTE,
    VersionDeLista,
    estado_derivado,
    estados_derivados,
    validar_anulacion,
    validar_publicacion,
    version_vigente,
)


def _d(mes: int, dia: int, hora: int = 0) -> datetime:
    return datetime(2026, mes, dia, hora, 0, tzinfo=UTC)


def _version(
    numero: int,
    estado: str = "PUBLICADA",
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> VersionDeLista:
    return VersionDeLista(
        id=uuid4(), numero=numero, estado=estado, vigencia_desde=desde, vigencia_hasta=hasta
    )


# --- version_vigente (PRC-03, D6) -------------------------------------------------------------


def test_la_version_mas_nueva_reemplaza_a_la_anterior() -> None:
    """Escenario "La versión más nueva reemplaza a la anterior": al 15/09 es la n.º 2 y al
    02/10 la n.º 3; al 02/10 la n.º 2 es histórica."""
    segunda = _version(2, desde=_d(9, 1))
    tercera = _version(3, desde=_d(10, 1))
    versiones = [segunda, tercera]

    assert version_vigente(versiones, _d(9, 15)) == segunda
    assert version_vigente(versiones, _d(10, 2)) == tercera
    assert estado_derivado(segunda, version_vigente(versiones, _d(10, 2)), _d(10, 2)) == HISTORICA


def test_una_version_programada_no_es_vigente_y_la_vigente_es_la_anterior() -> None:
    """Escenario "Versión programada": el 30/09 la n.º 3 (desde el 01/10) es `PROGRAMADA`."""
    segunda = _version(2, desde=_d(9, 1))
    tercera = _version(3, desde=_d(10, 1))
    vigente = version_vigente([segunda, tercera], _d(9, 30))

    assert vigente == segunda
    assert estado_derivado(tercera, vigente, _d(9, 30)) == PROGRAMADA
    assert estado_derivado(segunda, vigente, _d(9, 30)) == VIGENTE


def test_una_version_que_vence_devuelve_la_vigencia_a_la_anterior() -> None:
    """Escenario "Una versión que vence devuelve la vigencia a la anterior": la n.º 3 va
    del 01/10 al 01/11; el 05/11 vuelve a regir la n.º 2."""
    segunda = _version(2, desde=_d(9, 1))
    tercera = _version(3, desde=_d(10, 1), hasta=_d(11, 1))
    vigente = version_vigente([segunda, tercera], _d(11, 5))

    assert vigente == segunda
    assert estado_derivado(tercera, vigente, _d(11, 5)) == HISTORICA


def test_el_limite_exacto_de_la_vigencia() -> None:
    """Escenario "Momento exacto del límite": en el instante del 01/10 00:00 es vigente y en el
    del 01/11 00:00 ya no (desde: no supera el momento; hasta: posterior)."""
    segunda = _version(2, desde=_d(9, 1))
    tercera = _version(3, desde=_d(10, 1), hasta=_d(11, 1))
    versiones = [segunda, tercera]

    assert version_vigente(versiones, _d(10, 1)) == tercera
    assert version_vigente(versiones, _d(10, 1) - timedelta(microseconds=1)) == segunda
    assert version_vigente(versiones, _d(11, 1)) == segunda
    assert version_vigente(versiones, _d(11, 1) - timedelta(microseconds=1)) == tercera


def test_un_borrador_y_una_anulada_nunca_son_vigentes() -> None:
    publicada = _version(1, desde=_d(8, 1))
    anulada = _version(2, "ANULADA", desde=_d(9, 1))
    borrador = _version(3, "BORRADOR")
    versiones = [publicada, anulada, borrador]

    assert version_vigente(versiones, _d(10, 1)) == publicada
    assert estado_derivado(anulada, publicada, _d(10, 1)) is None
    assert estado_derivado(borrador, publicada, _d(10, 1)) is None


def test_una_lista_sin_version_publicada_no_tiene_vigente() -> None:
    """Escenario "Lista sin versión vigente"."""
    assert version_vigente([_version(1, "BORRADOR")], _d(10, 1)) is None
    assert version_vigente([], _d(10, 1)) is None


def test_si_todas_estan_programadas_o_vencidas_no_hay_vigente() -> None:
    programada = _version(2, desde=_d(12, 1))
    vencida = _version(1, desde=_d(8, 1), hasta=_d(9, 1))

    assert version_vigente([vencida, programada], _d(10, 1)) is None
    assert estado_derivado(vencida, None, _d(10, 1)) == HISTORICA


def test_el_orden_de_las_versiones_recibidas_no_cambia_la_vigente() -> None:
    primera = _version(1, desde=_d(8, 1))
    segunda = _version(2, desde=_d(9, 1))
    tercera = _version(3, desde=_d(10, 1))

    assert version_vigente([tercera, primera, segunda], _d(10, 2)) == tercera
    assert version_vigente([primera, segunda, tercera], _d(10, 2)) == tercera


def test_estados_derivados_de_todas_las_versiones_de_una_lista() -> None:
    primera = _version(1, desde=_d(8, 1))
    segunda = _version(2, desde=_d(9, 1))
    tercera = _version(3, desde=_d(12, 1))
    anulada = _version(4, "ANULADA", desde=_d(9, 15))
    borrador = _version(5, "BORRADOR")

    estados = estados_derivados([primera, segunda, tercera, anulada, borrador], _d(10, 1))

    assert estados == {
        primera.id: HISTORICA,
        segunda.id: VIGENTE,
        tercera.id: PROGRAMADA,
        anulada.id: None,
        borrador.id: None,
    }


@given(
    desdes=st.lists(st.integers(min_value=0, max_value=60), min_size=0, max_size=8),
    duraciones=st.lists(
        st.one_of(st.none(), st.integers(min_value=1, max_value=40)), min_size=8, max_size=8
    ),
    estados=st.lists(st.sampled_from(["BORRADOR", "PUBLICADA", "ANULADA"]), min_size=8, max_size=8),
    momento_dia=st.integers(min_value=-5, max_value=120),
)
def test_propiedad_como_maximo_una_version_vigente_y_es_la_de_mayor_desde(
    desdes: list[int],
    duraciones: list[int | None],
    estados: list[str],
    momento_dia: int,
) -> None:
    """Para cualquier conjunto de versiones y cualquier momento hay como máximo una vigente, y
    es la publicada ya comenzada y no vencida de mayor vigencia desde (PRC-03)."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    versiones = []
    for numero, dia in enumerate(desdes, start=1):
        estado = estados[numero - 1]
        desde = None if estado == "BORRADOR" else base + timedelta(days=dia)
        duracion = duraciones[numero - 1]
        hasta = None if desde is None or duracion is None else desde + timedelta(days=duracion)
        versiones.append(_version(numero, estado, desde, hasta))
    momento = base + timedelta(days=momento_dia)

    estados_calculados = estados_derivados(versiones, momento)
    vigentes = [v for v in versiones if estados_calculados[v.id] == VIGENTE]
    candidatas = [
        v
        for v in versiones
        if v.estado == "PUBLICADA"
        and v.vigencia_desde is not None
        and v.vigencia_desde <= momento
        and (v.vigencia_hasta is None or v.vigencia_hasta > momento)
    ]

    assert len(vigentes) <= 1
    assert (len(vigentes) == 1) == (len(candidatas) > 0)
    if vigentes:
        maximo = max(v.vigencia_desde for v in candidatas if v.vigencia_desde is not None)
        assert vigentes[0].vigencia_desde == maximo
    for version in versiones:
        if version.estado != "PUBLICADA":
            assert estados_calculados[version.id] is None
        else:
            assert estados_calculados[version.id] in {PROGRAMADA, VIGENTE, HISTORICA}


# --- validar_publicacion (PRC-02, PRC-04, D6) -------------------------------------------------

AHORA = _d(9, 28, 12)


def _publicar(
    version: VersionDeLista | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    vigencias_publicadas: list[datetime] | None = None,
    cantidad_precios: int = 3,
):  # type: ignore[no-untyped-def]
    return validar_publicacion(
        version or _version(4, "BORRADOR"),
        momento=AHORA,
        vigencia_desde=desde,
        vigencia_hasta=hasta,
        vigencias_publicadas=vigencias_publicadas or [],
        cantidad_precios=cantidad_precios,
    )


def test_sin_vigencia_desde_se_usa_el_momento_de_la_publicacion() -> None:
    vigencia = _publicar()

    assert vigencia.desde == AHORA
    assert vigencia.hasta is None


def test_una_publicacion_programada_conserva_sus_vigencias() -> None:
    """Escenario "Publicación programada": desde el 01/10 hasta el 01/11, publicada el 28/09."""
    vigencia = _publicar(desde=_d(10, 1), hasta=_d(11, 1))

    assert (vigencia.desde, vigencia.hasta) == (_d(10, 1), _d(11, 1))


def test_la_vigencia_desde_igual_al_momento_es_valida_y_anterior_no() -> None:
    assert _publicar(desde=AHORA).desde == AHORA
    with pytest.raises(VigenciaInvalidaError) as error:
        _publicar(desde=AHORA - timedelta(microseconds=1))
    assert error.value.codigo == "VIGENCIA_INVALIDA"


def test_la_vigencia_hasta_debe_ser_posterior_a_la_desde() -> None:
    with pytest.raises(VigenciaInvalidaError):
        _publicar(desde=_d(10, 1), hasta=_d(10, 1))
    with pytest.raises(VigenciaInvalidaError):
        _publicar(desde=_d(10, 1), hasta=_d(9, 30))
    assert _publicar(desde=_d(10, 1), hasta=_d(10, 1) + timedelta(microseconds=1)).hasta is not None


def test_la_vigencia_hasta_sin_desde_se_compara_con_el_momento() -> None:
    """Sin vigencia desde rige la del momento: un hasta anterior o igual a él es inválido."""
    with pytest.raises(VigenciaInvalidaError):
        _publicar(hasta=AHORA)
    assert _publicar(hasta=AHORA + timedelta(days=1)).desde == AHORA


def test_la_vigencia_desde_igual_a_la_de_otra_publicada_se_rechaza() -> None:
    """Escenario "Misma vigencia desde que otra versión publicada"."""
    with pytest.raises(VigenciaDuplicadaError) as error:
        _publicar(desde=_d(10, 1), vigencias_publicadas=[_d(9, 1), _d(10, 1)])
    assert error.value.codigo == "VIGENCIA_DUPLICADA"
    assert _publicar(desde=_d(10, 2), vigencias_publicadas=[_d(9, 1), _d(10, 1)]).desde == _d(10, 2)


def test_sin_precios_se_rechaza() -> None:
    """Escenario "Borrador sin precios"."""
    with pytest.raises(VersionSinPreciosError) as error:
        _publicar(cantidad_precios=0)
    assert error.value.codigo == "VERSION_SIN_PRECIOS"


@pytest.mark.parametrize("estado", ["PUBLICADA", "ANULADA"])
def test_solo_un_borrador_se_publica(estado: str) -> None:
    """Escenario "Publicar dos veces" (PRC-04, INV-11): se rechaza antes que cualquier otra
    validación."""
    with pytest.raises(VersionNoEsBorradorError):
        _publicar(_version(3, estado, desde=_d(10, 1)), desde=_d(8, 1), cantidad_precios=0)


# --- validar_anulacion (PRC-05) ----------------------------------------------------------------


def test_se_anula_una_publicada_cuya_vigencia_aun_no_comenzo() -> None:
    """Escenario "Anular una versión programada": el 30/09, desde el 01/10."""
    validar_anulacion(_version(3, desde=_d(10, 1)), momento=_d(9, 30))


def test_una_version_que_ya_rige_no_se_anula() -> None:
    """Escenario "Anular una versión que ya rige": el 02/10, desde el 01/10; y en el instante
    exacto del desde ya rige."""
    tercera = _version(3, desde=_d(10, 1))
    with pytest.raises(VersionYaVigenteError) as error:
        validar_anulacion(tercera, momento=_d(10, 2))
    assert error.value.codigo == "VERSION_YA_VIGENTE"
    with pytest.raises(VersionYaVigenteError):
        validar_anulacion(tercera, momento=_d(10, 1))
    validar_anulacion(tercera, momento=_d(10, 1) - timedelta(microseconds=1))


@pytest.mark.parametrize("estado", ["BORRADOR", "ANULADA"])
def test_un_borrador_o_una_anulada_no_se_anulan(estado: str) -> None:
    """Escenario "Anular un borrador o una versión anulada"."""
    with pytest.raises(VersionNoPublicadaError) as error:
        validar_anulacion(
            _version(3, estado, desde=None if estado == "BORRADOR" else _d(10, 1)), momento=_d(9, 1)
        )
    assert error.value.codigo == "VERSION_NO_PUBLICADA"
