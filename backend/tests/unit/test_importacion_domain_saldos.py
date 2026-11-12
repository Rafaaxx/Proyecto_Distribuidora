"""Tarea 7.2 (change 10): dominio puro de la importación de saldos iniciales
(`specs/importacion/puesta-en-marcha`, `design.md` D4, D12).

De la fila de planilla a los argumentos de `registrar_saldo_inicial`: tipo de cuenta en
mayúsculas, importe con coma decimal convertido sin punto flotante (INV-03; los dos
decimales los exige el servicio), sentido con los rótulos de ADR-034 punto 8 según el
tipo de cuenta, y la forma de buscar la entidad (código o documento del cliente, nombre
del proveedor, D4).

Reglas citadas: CC-08, INV-03, TR-01, ADR-034.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.importacion.domain.errores import (
    CuentaTipoInvalidoError,
    NumeroInvalidoError,
    ValorObligatorioError,
)
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.saldos import (
    DatosDeSaldo,
    datos_de_saldo,
    documento_de_entidad,
)


def fila(numero: int = 2, **cambios: str) -> FilaPlanilla:
    valores = {
        "cuenta_tipo": "CLIENTE",
        "entidad": "C001",
        "importe": "150000",
        "sentido": "Nos debe",
    }
    valores.update(cambios)
    return FilaPlanilla(fila=numero, valores=valores)


@pytest.mark.parametrize(
    ("cuenta_tipo", "sentido", "esperado"),
    [
        ("CLIENTE", "Nos debe", "AUMENTA"),
        ("CLIENTE", "  SALDO A FAVOR ", "REDUCE"),
        ("PROVEEDOR", "Le debemos", "AUMENTA"),
        ("PROVEEDOR", "saldo a nuestro favor", "REDUCE"),
        ("CLIENTE", "aumenta", "AUMENTA"),
        ("PROVEEDOR", "Reduce", "REDUCE"),
    ],
)
def test_los_rotulos_de_adr_034_se_traducen_al_sentido(
    cuenta_tipo: str, sentido: str, esperado: str
) -> None:
    assert datos_de_saldo(fila(cuenta_tipo=cuenta_tipo, sentido=sentido)).sentido == esperado


@pytest.mark.parametrize(
    ("cuenta_tipo", "sentido"),
    [("CLIENTE", "debe"), ("CLIENTE", "Le debemos"), ("PROVEEDOR", "Nos debe"), ("CLIENTE", "")],
)
def test_un_rotulo_desconocido_o_de_la_otra_cuenta_pasa_en_mayusculas(
    cuenta_tipo: str, sentido: str
) -> None:
    """El servicio es quien lanza `SENTIDO_INVALIDO` (misma regla que la pantalla)."""
    datos = datos_de_saldo(fila(cuenta_tipo=cuenta_tipo, sentido=sentido))

    assert datos.sentido == sentido.strip().upper()
    assert datos.sentido not in ("AUMENTA", "REDUCE")


def test_lee_importe_exacto_con_coma_sin_redondear() -> None:
    assert datos_de_saldo(fila(importe="100,005")) == DatosDeSaldo(
        cuenta_tipo="CLIENTE",
        entidad="C001",
        importe=Decimal("100.005"),
        sentido="AUMENTA",
    )


def test_el_tipo_de_cuenta_se_normaliza_a_mayusculas() -> None:
    datos = datos_de_saldo(fila(cuenta_tipo=" proveedor ", entidad="Bodega Sur"))

    assert datos.cuenta_tipo == "PROVEEDOR"


def test_tipo_de_cuenta_desconocido_es_cuenta_tipo_invalido_en_su_columna() -> None:
    with pytest.raises(CuentaTipoInvalidoError) as excinfo:
        datos_de_saldo(fila(cuenta_tipo="EMPLEADO"))

    assert (excinfo.value.codigo, excinfo.value.columna) == ("CUENTA_TIPO_INVALIDO", "cuenta_tipo")


@pytest.mark.parametrize("texto", ["1.500", "mucho", ""])
def test_importe_mal_escrito_es_numero_invalido_en_su_columna(texto: str) -> None:
    with pytest.raises(NumeroInvalidoError) as excinfo:
        datos_de_saldo(fila(importe=texto))

    assert excinfo.value.columna == "importe"


def test_entidad_vacia_es_obligatoria() -> None:
    with pytest.raises(ValorObligatorioError) as excinfo:
        datos_de_saldo(fila(entidad=" "))

    assert excinfo.value.columna == "entidad"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("20-12345678-9", "20123456789"),
        ("12.345.678", "12345678"),
        (" 20 12345678 9 ", "20123456789"),
        ("C001", None),
        ("C-20123456789", None),
        ("Bodega Sur", None),
    ],
)
def test_solo_un_texto_de_digitos_y_separadores_se_busca_como_documento(
    texto: str, esperado: str | None
) -> None:
    assert documento_de_entidad(texto) == esperado
