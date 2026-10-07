"""Change 13, tarea 4.1: validación de una regla de margen y resolución por precedencia
(`precios/domain/reglas.py`; spec `precios/reglas-de-margen`; PRC-12, PRC-13, D8).

Reglas citadas: PRC-12 (margen bruto `< 1`), PRC-13 (producto, marca, categoría,
proveedor, lista), TR-02 (seis decimales), INV-03 (sin punto flotante).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.core.errors import DomainError
from app.core.money import EntradaNoEsDineroExactoError
from app.modules.precios.domain.errores import AlcanceInvalidoError, MargenInvalidoError
from app.modules.precios.domain.reglas import (
    ProductoDeRegla,
    Regla,
    resolver_regla,
    validar_regla,
)

PRODUCTO_ID, MARCA_ID, CATEGORIA_ID, PROVEEDOR_ID = uuid4(), uuid4(), uuid4(), uuid4()
VINO_A = ProductoDeRegla(
    producto_id=PRODUCTO_ID,
    marca_id=MARCA_ID,
    categoria_id=CATEGORIA_ID,
    proveedor_id=PROVEEDOR_ID,
)

# --- validar_regla: el valor (PRC-12, TR-02) --------------------------------------


@pytest.mark.parametrize(
    ("tipo", "valor", "esperado"),
    [
        ("MARKUP", "0.300000", Decimal("0.300000")),
        ("MARGEN_BRUTO", "0.300000", Decimal("0.300000")),
        ("MARKUP", "1.5", Decimal("1.500000")),  # el markup puede superar el 100%
        ("MARKUP", "0", Decimal("0.000000")),
        ("MARGEN_BRUTO", "0", Decimal("0.000000")),
        ("MARGEN_BRUTO", "0.999999", Decimal("0.999999")),
        ("MARKUP", Decimal("0.25"), Decimal("0.250000")),
    ],
)
def test_una_regla_con_valor_valido_se_acepta_con_seis_decimales(
    tipo: str, valor: str | Decimal, esperado: Decimal
) -> None:
    validada = validar_regla(tipo, valor, "LISTA", None)

    assert validada.valor == esperado
    assert str(validada.valor) == str(esperado)
    assert validada.tipo == tipo


@pytest.mark.parametrize(
    ("tipo", "valor"),
    [
        ("MARGEN_BRUTO", "1"),
        ("MARGEN_BRUTO", "1.000000"),
        ("MARGEN_BRUTO", "1.200000"),
        ("MARKUP", "-0.100000"),
        ("MARGEN_BRUTO", "-0.000001"),
        ("MARKUP", "0.3000001"),  # siete decimales
        ("MARGEN_BRUTO", "0.1234567"),
        ("MARKUP", "NaN"),
        ("MARKUP", "Infinity"),
        ("MARKUP", "treinta por ciento"),
        ("MARKUP", ""),
    ],
)
def test_una_regla_con_valor_invalido_se_rechaza_con_margen_invalido(tipo: str, valor: str) -> None:
    with pytest.raises(MargenInvalidoError) as error:
        validar_regla(tipo, valor, "LISTA", None)

    assert error.value.codigo == "MARGEN_INVALIDO"
    assert isinstance(error.value, DomainError)


def test_el_valor_cabe_en_numeric_9_6() -> None:
    """`numeric(9,6)`: el mayor markup posible es `999.999999`."""
    assert validar_regla("MARKUP", "999.999999", "LISTA", None).valor == Decimal("999.999999")
    with pytest.raises(MargenInvalidoError):
        validar_regla("MARKUP", "1000", "LISTA", None)


def test_un_tipo_de_margen_desconocido_se_rechaza_con_margen_invalido() -> None:
    with pytest.raises(MargenInvalidoError):
        validar_regla("DESCUENTO", "0.1", "LISTA", None)


@pytest.mark.parametrize("valor", [0.3, True])
def test_inv03_un_valor_de_punto_flotante_se_rechaza(valor: object) -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        validar_regla("MARKUP", valor, "LISTA", None)  # type: ignore[arg-type]


# --- validar_regla: el alcance (PRC-13) --------------------------------------------


@pytest.mark.parametrize("alcance", ["PRODUCTO", "MARCA", "CATEGORIA", "PROVEEDOR"])
def test_un_alcance_con_entidad_es_valido(alcance: str) -> None:
    entidad = uuid4()

    validada = validar_regla("MARKUP", "0.3", alcance, entidad)

    assert (validada.alcance_tipo, validada.alcance_id) == (alcance, entidad)


def test_el_alcance_lista_no_lleva_entidad() -> None:
    validada = validar_regla("MARKUP", "0.3", "LISTA", None)

    assert (validada.alcance_tipo, validada.alcance_id) == ("LISTA", None)


@pytest.mark.parametrize(
    ("alcance", "entidad"),
    [
        ("LISTA", uuid4()),  # lista con entidad
        ("MARCA", None),  # marca sin entidad
        ("PRODUCTO", None),
        ("CATEGORIA", None),
        ("PROVEEDOR", None),
        ("CLIENTE", uuid4()),  # alcance que no existe
        ("producto", uuid4()),
    ],
)
def test_un_alcance_incoherente_se_rechaza_con_alcance_invalido(
    alcance: str, entidad: UUID | None
) -> None:
    with pytest.raises(AlcanceInvalidoError) as error:
        validar_regla("MARKUP", "0.3", alcance, entidad)

    assert error.value.codigo == "ALCANCE_INVALIDO"


# --- resolver_regla: precedencia (PRC-13) -------------------------------------------

ORDEN = ["PRODUCTO", "MARCA", "CATEGORIA", "PROVEEDOR", "LISTA"]


def _regla(alcance_tipo: str, alcance_id: UUID | None, *, activo: bool = True) -> Regla:
    return Regla(
        id=uuid4(),
        alcance_tipo=alcance_tipo,
        alcance_id=alcance_id,
        tipo="MARKUP",
        valor=Decimal("0.3"),
        activo=activo,
    )


def _todas() -> dict[str, Regla]:
    return {
        "PRODUCTO": _regla("PRODUCTO", PRODUCTO_ID),
        "MARCA": _regla("MARCA", MARCA_ID),
        "CATEGORIA": _regla("CATEGORIA", CATEGORIA_ID),
        "PROVEEDOR": _regla("PROVEEDOR", PROVEEDOR_ID),
        "LISTA": _regla("LISTA", None),
    }


def test_la_regla_de_producto_gana_a_todas() -> None:
    reglas = _todas()

    assert resolver_regla(reglas.values(), VINO_A) is reglas["PRODUCTO"]


@pytest.mark.parametrize("quitar_hasta", ORDEN[:4])
def test_sin_la_mas_especifica_gana_la_siguiente_de_la_cadena(quitar_hasta: str) -> None:
    """Cada paso de la cadena se prueba quitando de a una las reglas más específicas."""
    reglas = _todas()
    for alcance in ORDEN[: ORDEN.index(quitar_hasta) + 1]:
        del reglas[alcance]
    gana = ORDEN[ORDEN.index(quitar_hasta) + 1]

    assert resolver_regla(reglas.values(), VINO_A) is reglas[gana]


def test_el_orden_de_las_reglas_en_la_entrada_no_importa() -> None:
    reglas = _todas()
    al_reves = list(reversed(list(reglas.values())))

    assert resolver_regla(al_reves, VINO_A) is reglas["PRODUCTO"]


def test_solo_la_regla_de_la_lista_alcanza_a_cualquier_producto() -> None:
    lista = _regla("LISTA", None)
    otro = ProductoDeRegla(uuid4(), uuid4(), uuid4(), uuid4())

    assert resolver_regla([lista], VINO_A) is lista
    assert resolver_regla([lista], otro) is lista


def test_una_regla_inactiva_no_participa() -> None:
    reglas = _todas()
    inactiva = _regla("PRODUCTO", PRODUCTO_ID, activo=False)

    assert (
        resolver_regla([inactiva, reglas["CATEGORIA"], reglas["LISTA"]], VINO_A)
        is (reglas["CATEGORIA"])
    )
    assert resolver_regla([inactiva], VINO_A) is None


def test_una_regla_de_otra_entidad_no_alcanza_al_producto() -> None:
    de_otra_marca = _regla("MARCA", uuid4())
    de_otra_categoria = _regla("CATEGORIA", uuid4())
    lista = _regla("LISTA", None)

    assert resolver_regla([de_otra_marca, de_otra_categoria, lista], VINO_A) is lista
    assert resolver_regla([de_otra_marca, de_otra_categoria], VINO_A) is None


def test_un_producto_sin_marca_no_tiene_regla_de_marca() -> None:
    sin_marca = ProductoDeRegla(PRODUCTO_ID, None, CATEGORIA_ID, PROVEEDOR_ID)
    regla_de_marca = _regla("MARCA", MARCA_ID)
    categoria = _regla("CATEGORIA", CATEGORIA_ID)

    assert resolver_regla([regla_de_marca, categoria], sin_marca) is categoria
    assert resolver_regla([regla_de_marca], sin_marca) is None


def test_un_producto_sin_regla_aplicable_no_tiene_regla() -> None:
    """Cerveza B (categoría distinta de `Vinos`) con una sola regla, la de `Vinos`."""
    cerveza_b = ProductoDeRegla(uuid4(), None, uuid4(), uuid4())

    assert resolver_regla([_regla("CATEGORIA", CATEGORIA_ID)], cerveza_b) is None
    assert resolver_regla([], cerveza_b) is None
