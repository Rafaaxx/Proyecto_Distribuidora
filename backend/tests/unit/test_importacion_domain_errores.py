"""Tarea 3.5 (change 10): traducción de errores de dominio a errores de fila y error
agregado `IMPORTACION_CON_ERRORES` (`specs/importacion/registro-de-importaciones`,
`design.md` D1 y "Detalles derivados").

Cada `DomainError` de un servicio se traduce a `{fila, columna, codigo, mensaje}`
con una tabla código -> columna por tipo. El error de una celda ya trae su columna.
El error de `informar_costos` trae la `fila` (índice 0 dentro del lote) en
`extension`, y se traduce a la fila de la planilla.

Reglas citadas: INV-01 (un solo error agregado, con la lista completa), TR-10 (el
mismo código que devuelve el alta individual), `design.md` D1.
"""

from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.modules.importacion.domain.errores import (
    CantidadInvalidaError,
    ImportacionConErroresError,
    NumeroInvalidoError,
)
from app.modules.importacion.domain.informe import (
    ErrorDeFila,
    error_agregado,
    error_de_fila_duplicada,
    traducir_error,
)


class _CuitInvalido(DomainError):
    codigo = "CUIT_INVALIDO"
    status_http = 422


class _NombreDuplicado(DomainError):
    codigo = "NOMBRE_DUPLICADO"
    status_http = 409


class _ErrorSinTabla(DomainError):
    codigo = "ALGO_QUE_NO_ESTA_EN_LA_TABLA"


class _ErrorDeLote(DomainError):
    codigo = "COSTO_INVALIDO"


def test_el_cuit_invalido_de_un_proveedor_se_traduce_a_fila_columna_y_codigo() -> None:
    """Escenario "Mismo error que la pantalla" y "Error en la tercera fila de
    datos": fila 4, columna `cuit`, `CUIT_INVALIDO`."""
    error = traducir_error("PROVEEDORES", 4, _CuitInvalido("El CUIT debe tener 11 dígitos."))

    assert error == ErrorDeFila(
        fila=4, columna="cuit", codigo="CUIT_INVALIDO", mensaje="El CUIT debe tener 11 dígitos."
    )
    assert error.como_dict() == {
        "fila": 4,
        "columna": "cuit",
        "codigo": "CUIT_INVALIDO",
        "mensaje": "El CUIT debe tener 11 dígitos.",
    }


@pytest.mark.parametrize(
    ("tipo", "codigo", "columna"),
    [
        ("PROVEEDORES", "NOMBRE_DUPLICADO", "nombre"),
        ("PROVEEDORES", "NOMBRE_INVALIDO", "nombre"),
        ("PROVEEDORES", "CUIT_DUPLICADO", "cuit"),
        ("CLIENTES", "CODIGO_DUPLICADO", "codigo"),
        ("CLIENTES", "DOCUMENTO_DUPLICADO", "documento_numero"),
        ("CLIENTES", "DOCUMENTO_INVALIDO", "documento_numero"),
        ("CLIENTES", "ESTADO_FACTURACION_INVALIDO", "estado_facturacion_default"),
        ("PRODUCTOS", "CODIGO_DUPLICADO", "codigo"),
        ("PRODUCTOS", "UNIDADES_INVALIDAS", "unidades_base"),
        ("COSTOS", "PRESENTACION_INVALIDA", "presentacion"),
        ("STOCK_INICIAL", "COSTO_INVALIDO", "costo_unitario"),
        ("STOCK_INICIAL", "UBICACION_INACTIVA", "ubicacion"),
        ("STOCK_INICIAL", "PRODUCTO_INACTIVO", "producto_codigo"),
        ("STOCK_INICIAL", "PRODUCTO_CON_OPERACIONES", "producto_codigo"),
        ("STOCK_INICIAL", "STOCK_INSUFICIENTE", "cantidad_base"),
        ("STOCK_INICIAL", "CANTIDAD_INVALIDA", "cantidad_base"),
        ("STOCK_INICIAL", "CANTIDAD_FUERA_DE_RANGO", "cantidad_base"),
        ("SALDOS_INICIALES", "CUENTA_CON_OPERACIONES", "entidad"),
        ("SALDOS_INICIALES", "CONSUMIDOR_FINAL_SIN_CUENTA", "entidad"),
        ("SALDOS_INICIALES", "SALDO_FUERA_DE_RANGO", "importe"),
        ("SALDOS_INICIALES", "IMPORTE_INVALIDO", "importe"),
        ("SALDOS_INICIALES", "SENTIDO_INVALIDO", "sentido"),
    ],
)
def test_la_tabla_codigo_a_columna_depende_del_tipo(tipo: str, codigo: str, columna: str) -> None:
    class Error(DomainError):
        pass

    Error.codigo = codigo

    assert traducir_error(tipo, 2, Error("x")).columna == columna


def test_el_mismo_codigo_puede_ir_a_otra_columna_segun_el_tipo() -> None:
    class Duplicado(DomainError):
        codigo = "CODIGO_DUPLICADO"

    assert traducir_error("CLIENTES", 2, Duplicado("x")).columna == "codigo"
    assert traducir_error("PROVEEDORES", 2, Duplicado("x")).columna is None


def test_un_error_sin_entrada_en_la_tabla_queda_sin_columna_pero_conserva_su_codigo() -> None:
    error = traducir_error("PROVEEDORES", 7, _ErrorSinTabla("algo"))

    assert error.columna is None
    assert error.codigo == "ALGO_QUE_NO_ESTA_EN_LA_TABLA"
    assert error.fila == 7
    assert error.como_dict()["columna"] is None


def test_el_error_de_una_celda_ya_trae_su_columna_y_no_se_busca_en_la_tabla() -> None:
    numero = NumeroInvalidoError("1.500 no es un número.", columna="importe")
    cantidad = CantidadInvalidaError("10,5 no es entero.", columna="cantidad_base")

    assert traducir_error("SALDOS_INICIALES", 3, numero).columna == "importe"
    assert traducir_error("STOCK_INICIAL", 9, cantidad) == ErrorDeFila(
        fila=9, columna="cantidad_base", codigo="CANTIDAD_INVALIDA", mensaje="10,5 no es entero."
    )


def test_la_fila_del_lote_de_informar_costos_se_traduce_a_la_fila_de_la_planilla() -> None:
    """`informar_costos` informa `fila` (índice 0 dentro del lote) en `extension`:
    el lote armó las filas 2, 3 y 5 de la planilla, y el error de la tercera es la
    fila 5."""
    error = _ErrorDeLote("El valor debe ser mayor a cero.", extension={"fila": 2})

    traducido = traducir_error("COSTOS", 2, error, filas_de_lote=[2, 3, 5])

    assert traducido.fila == 5
    assert traducido.codigo == "COSTO_INVALIDO"


@pytest.mark.parametrize("extension", [{"fila": 9}, {"fila": -1}, {"fila": "x"}, {}, None])
def test_una_fila_de_lote_fuera_de_rango_o_ausente_conserva_la_fila_del_llamador(
    extension: dict[str, object] | None,
) -> None:
    error = _ErrorDeLote("x", extension=extension)

    assert traducir_error("COSTOS", 4, error, filas_de_lote=[2, 3, 5]).fila == 4


def test_sin_lote_la_fila_del_error_se_ignora() -> None:
    error = _ErrorDeLote("x", extension={"fila": 1})

    assert traducir_error("COSTOS", 4, error).fila == 4


def test_la_fila_duplicada_cita_la_primera_aparicion() -> None:
    """Escenario "Clave repetida dentro del archivo": "Bodega Sur" en las filas 2 y
    5; la fila 5 da `FILA_DUPLICADA` indicando la fila 2."""
    error = error_de_fila_duplicada(fila=5, columna="nombre", fila_original=2)

    assert error.codigo == "FILA_DUPLICADA"
    assert error.fila == 5
    assert error.columna == "nombre"
    assert "2" in error.mensaje


def test_el_error_agregado_lista_todos_los_errores_ordenados_por_fila() -> None:
    """INV-01: 422 `IMPORTACION_CON_ERRORES` con la lista completa, no solo el
    primero."""
    errores = [
        ErrorDeFila(210, "documento_numero", "DOCUMENTO_INVALIDO", "DNI inválido"),
        ErrorDeFila(45, "documento_numero", "DOCUMENTO_INVALIDO", "DNI inválido"),
    ]

    agregado = error_agregado(errores)

    assert isinstance(agregado, ImportacionConErroresError)
    assert agregado.codigo == "IMPORTACION_CON_ERRORES"
    assert agregado.status_http == 422
    assert agregado.extension is not None
    assert [e["fila"] for e in agregado.extension["errores"]] == [45, 210]
    assert "2" in agregado.mensaje


def test_el_orden_de_dos_errores_de_la_misma_fila_se_conserva() -> None:
    errores = [
        ErrorDeFila(3, "cuit", "CUIT_INVALIDO", "a"),
        ErrorDeFila(3, "nombre", "NOMBRE_INVALIDO", "b"),
        ErrorDeFila(2, None, "X", "c"),
    ]

    agregado = error_agregado(errores)

    assert agregado.extension is not None
    assert [(e["fila"], e["codigo"]) for e in agregado.extension["errores"]] == [
        (2, "X"),
        (3, "CUIT_INVALIDO"),
        (3, "NOMBRE_INVALIDO"),
    ]


def test_un_error_agregado_sin_errores_es_un_error_de_programacion() -> None:
    with pytest.raises(ValueError, match="al menos un error"):
        error_agregado([])
