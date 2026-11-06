"""Tarea 1.2 (change 25, `design.md` D1, D7; specs `sync/revision-de-observaciones` y
`sync/rechazos-sin-conexion`): reglas puras de la revisión de observaciones y de rechazos.

Reglas citadas: SYN-08, INV-01.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.sync.domain import revision
from app.modules.sync.domain.errores import (
    ComentarioInvalidoError,
    ObservacionesInvalidasError,
    ObservacionYaResueltaError,
    RechazoYaResueltoError,
    VinculoInvalidoError,
)

# --- la lista de observaciones (D1: de 1 a 100, sin repetidas) --------------------------------


def test_inv01_una_lista_valida_se_devuelve_ordenada_para_bloquear_en_orden_de_id() -> None:
    ids = [UUID(int=3), UUID(int=1), UUID(int=2)]

    assert revision.validar_observaciones(ids) == (UUID(int=1), UUID(int=2), UUID(int=3))


@pytest.mark.parametrize("cantidad", [1, 100])
def test_inv01_los_limites_de_la_lista_se_aceptan(cantidad: int) -> None:
    ids = [uuid4() for _ in range(cantidad)]

    assert len(revision.validar_observaciones(ids)) == cantidad


def test_inv01_una_lista_vacia_se_rechaza() -> None:
    with pytest.raises(ObservacionesInvalidasError) as error:
        revision.validar_observaciones([])

    assert (error.value.codigo, error.value.status_http) == ("OBSERVACIONES_INVALIDAS", 422)


def test_inv01_mas_de_100_se_rechaza() -> None:
    with pytest.raises(ObservacionesInvalidasError):
        revision.validar_observaciones([uuid4() for _ in range(101)])


def test_inv01_una_observacion_repetida_se_rechaza() -> None:
    repetida = uuid4()

    with pytest.raises(ObservacionesInvalidasError):
        revision.validar_observaciones([repetida, uuid4(), repetida])


# --- el comentario (SYN-08: de 1 a 500 caracteres tras recortar) ------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("Se habló con el cliente", "Se habló con el cliente"), ("  recortado \n", "recortado")],
)
def test_syn08_el_comentario_se_recorta_en_los_extremos(entrada: str, esperado: str) -> None:
    assert revision.validar_comentario(entrada) == esperado


@pytest.mark.parametrize("largo", [1, 500])
def test_syn08_los_limites_del_comentario_se_aceptan(largo: int) -> None:
    assert len(revision.validar_comentario("x" * largo)) == largo


def test_syn08_los_500_se_cuentan_despues_de_recortar() -> None:
    assert len(revision.validar_comentario("  " + "x" * 500 + "  ")) == 500


@pytest.mark.parametrize("comentario", ["", "   ", "\n\t ", "x" * 501, " " + "x" * 501])
def test_syn08_un_comentario_vacio_o_demasiado_largo_se_rechaza(comentario: str) -> None:
    with pytest.raises(ComentarioInvalidoError) as error:
        revision.validar_comentario(comentario)

    assert (error.value.codigo, error.value.status_http) == ("COMENTARIO_INVALIDO", 422)


# --- las ya resueltas (INV-01: ninguna se resuelve si alguna ya lo estaba) ---------------------


def test_inv01_si_todas_estan_pendientes_no_pasa_nada() -> None:
    a, b = uuid4(), uuid4()

    revision.validar_pendientes({a: "PENDIENTE", b: "PENDIENTE"})


def test_inv01_una_resuelta_levanta_observacion_ya_resuelta_con_su_id() -> None:
    pendiente, resuelta = uuid4(), uuid4()

    with pytest.raises(ObservacionYaResueltaError) as error:
        revision.validar_pendientes({pendiente: "PENDIENTE", resuelta: "RESUELTA"})

    assert (error.value.codigo, error.value.status_http) == ("OBSERVACION_YA_RESUELTA", 409)
    assert error.value.extension == {"observaciones": [str(resuelta)]}


def test_inv01_con_varias_resueltas_las_nombra_a_todas_en_orden() -> None:
    a, b, c = UUID(int=2), UUID(int=1), UUID(int=3)

    with pytest.raises(ObservacionYaResueltaError) as error:
        revision.validar_pendientes({a: "RESUELTA", b: "RESUELTA", c: "PENDIENTE"})

    assert error.value.extension == {"observaciones": [str(b), str(a)]}


# --- el vínculo admitido por tipo de comando (D7) ----------------------------------------------


@pytest.mark.parametrize(
    ("comando", "vinculo"),
    [
        ("VENTA_CONFIRMAR", "VENTA"),
        ("COBRANZA_REGISTRAR", "COBRANZA"),
    ],
)
def test_syn08_cada_comando_admite_su_tipo_de_vinculo(comando: str, vinculo: str) -> None:
    assert revision.vinculo_admitido(comando) == vinculo
    revision.validar_tipo_de_vinculo(comando, vinculo)


@pytest.mark.parametrize(
    ("comando", "vinculo"),
    [
        ("COBRANZA_REGISTRAR", "VENTA"),
        ("VENTA_CONFIRMAR", "COBRANZA"),
        ("VENTA_ANULAR", "COBRANZA"),
        ("VENTA_ANULAR", "VENTA"),
        ("JORNADA_ENTREGAR", "VENTA"),
        ("TRANSFERENCIA_REGISTRAR", "COBRANZA"),
    ],
)
def test_syn08_un_vinculo_de_otro_tipo_o_a_un_comando_sin_vinculo_se_rechaza(
    comando: str, vinculo: str
) -> None:
    with pytest.raises(VinculoInvalidoError) as error:
        revision.validar_tipo_de_vinculo(comando, vinculo)

    assert (error.value.codigo, error.value.status_http) == ("VINCULO_INVALIDO", 422)


@pytest.mark.parametrize(
    "comando", ["JORNADA_ENTREGAR", "COMPRA_REGISTRAR", "VENTA_CONFIRMAR", "VENTA_ANULAR"]
)
def test_syn08_sin_vinculo_siempre_es_valido(comando: str) -> None:
    revision.validar_tipo_de_vinculo(comando, None)


def test_syn08_la_anulacion_rechazada_no_admite_vinculo() -> None:
    assert revision.vinculo_admitido("VENTA_ANULAR") is None


# --- rechazo pendiente y tipo de vínculo (RECHAZO_RESOLVER, D7) --------------------------------


def test_syn08_un_rechazo_pendiente_se_puede_resolver() -> None:
    revision.validar_rechazo_pendiente(True)


def test_syn08_un_rechazo_ya_resuelto_no_se_resuelve_otra_vez() -> None:
    with pytest.raises(RechazoYaResueltoError) as error:
        revision.validar_rechazo_pendiente(False)

    assert (error.value.codigo, error.value.status_http) == ("RECHAZO_YA_RESUELTO", 409)


@pytest.mark.parametrize(
    ("comando", "vinculo"),
    [
        ("VENTA_CONFIRMAR", "VENTA"),
        ("COBRANZA_REGISTRAR", "COBRANZA"),
    ],
)
def test_syn08_el_tipo_de_vinculo_admitido_pasa_sin_leer_la_operacion(
    comando: str, vinculo: str
) -> None:
    """El tipo de vínculo se valida antes de leer la operación vinculada."""
    revision.validar_tipo_de_vinculo(comando, vinculo)


@pytest.mark.parametrize(
    ("comando", "vinculo"),
    [
        ("VENTA_CONFIRMAR", "COBRANZA"),
        ("COBRANZA_REGISTRAR", "VENTA"),
        ("JORNADA_ENTREGAR", "VENTA"),
        ("VENTA_ANULAR", "VENTA"),
    ],
)
def test_syn08_un_tipo_de_vinculo_que_el_comando_no_admite_se_rechaza(
    comando: str, vinculo: str
) -> None:
    with pytest.raises(VinculoInvalidoError):
        revision.validar_tipo_de_vinculo(comando, vinculo)


def test_syn08_sin_vinculo_el_tipo_siempre_es_valido() -> None:
    revision.validar_tipo_de_vinculo("JORNADA_ENTREGAR", None)
