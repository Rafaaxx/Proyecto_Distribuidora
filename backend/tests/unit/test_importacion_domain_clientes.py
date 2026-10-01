"""Tarea 6.1 (change 10): dominio puro de la importación de clientes
(`specs/importacion/importacion-de-maestros`, `design.md` D6).

De la fila de planilla a los datos del alta (`clientes.service.crear_cliente`): `codigo`
obligatorio en la planilla (D6, restricción de negocio aprobada), vacíos como `None`, estado
de facturación del catálogo cerrado, claves naturales para detectar repeticiones dentro del
archivo y la columna que informa `FICHA_INCOMPLETA`.

Reglas citadas: CLI-01, CLI-05, TR-10.
"""

from __future__ import annotations

import pytest

from app.modules.importacion.domain.clientes import (
    claves_de_cliente,
    columna_de_ficha_incompleta,
    datos_de_cliente,
)
from app.modules.importacion.domain.errores import ValorObligatorioError
from app.modules.importacion.domain.planilla import FilaPlanilla


def fila(numero: int = 2, **cambios: str) -> FilaPlanilla:
    valores = {
        "nombre": "Almacén Don Pepe",
        "codigo": "C001",
        "razon_social": "",
        "documento_tipo": "",
        "documento_numero": "",
        "direccion": "San Martín 123",
        "contacto": "Pepe",
        "telefono": "",
        "email": "",
        "estado_facturacion_default": "",
    }
    valores.update(cambios)
    return FilaPlanilla(fila=numero, valores=valores)


def test_los_datos_del_alta_salen_de_la_fila_con_los_vacios_como_none() -> None:
    datos = datos_de_cliente(
        fila(
            razon_social="Don Pepe SRL",
            documento_tipo="CUIT",
            documento_numero="20-12345678-9",
            telefono="261 555",
        )
    )

    assert datos == {
        "nombre": "Almacén Don Pepe",
        "codigo": "C001",
        "razon_social": "Don Pepe SRL",
        "documento_tipo": "CUIT",
        "documento_numero": "20-12345678-9",
        "direccion": "San Martín 123",
        "contacto": "Pepe",
        "telefono": "261 555",
        "email": None,
        "estado_facturacion_default": None,
    }


def test_el_documento_pasa_tal_cual_para_que_lo_normalice_el_servicio() -> None:
    """CLI-05: la normalización a dígitos es del servicio, no se repite acá."""
    datos = datos_de_cliente(fila(documento_tipo="dni", documento_numero="30.111.222"))

    assert (datos["documento_tipo"], datos["documento_numero"]) == ("dni", "30.111.222")


@pytest.mark.parametrize("codigo", ["", "   "])
def test_el_codigo_es_obligatorio_en_la_planilla(codigo: str) -> None:
    """D6: CLI-01 lo deja opcional en la pantalla; la planilla lo exige."""
    with pytest.raises(ValorObligatorioError) as excinfo:
        datos_de_cliente(fila(codigo=codigo))

    assert (excinfo.value.codigo, excinfo.value.columna) == ("VALOR_OBLIGATORIO", "codigo")


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("pendiente", "PENDIENTE"),
        (" NO_REQUIERE ", "NO_REQUIERE"),
        ("", None),
    ],
)
def test_el_estado_de_facturacion_se_escribe_sin_distinguir_mayusculas_ni_espacios(
    texto: str, esperado: str | None
) -> None:
    assert datos_de_cliente(fila(estado_facturacion_default=texto))[
        "estado_facturacion_default"
    ] == (esperado)


def test_el_catalogo_de_estados_de_facturacion_es_del_dominio_de_clientes_no_de_la_planilla() -> (
    None
):
    """Tarea 12.2: la planilla no repite la regla; pasa el texto (en mayúsculas) y el
    servicio de clientes lo rechaza con `ESTADO_FACTURACION_INVALIDO`."""
    datos = datos_de_cliente(fila(estado_facturacion_default="facturado"))

    assert datos["estado_facturacion_default"] == "FACTURADO"


def test_las_claves_son_el_codigo_y_el_documento_normalizado() -> None:
    claves = claves_de_cliente(fila(documento_tipo="cuit", documento_numero="20-12345678-9"))

    assert claves == [("codigo", "C001"), ("documento_numero", "CUIT:20123456789")]


def test_sin_documento_completo_la_unica_clave_es_el_codigo() -> None:
    assert claves_de_cliente(fila()) == [("codigo", "C001")]
    assert claves_de_cliente(fila(documento_tipo="CUIT")) == [("codigo", "C001")]
    assert claves_de_cliente(fila(codigo="", documento_numero="123")) == []


def test_el_mismo_documento_escrito_distinto_es_la_misma_clave() -> None:
    con_guiones = claves_de_cliente(fila(documento_tipo="CUIT", documento_numero="20-12345678-9"))
    con_espacios = claves_de_cliente(fila(documento_tipo="CUIT", documento_numero="20 12345678 9"))

    assert con_guiones[1] == con_espacios[1]


def test_ficha_incompleta_se_informa_en_la_columna_que_falta() -> None:
    """Escenario "Ficha incompleta" (CLI-01): `direccion` primero, como el servicio."""
    assert columna_de_ficha_incompleta(fila(direccion="")) == "direccion"
    assert columna_de_ficha_incompleta(fila(contacto="")) == "contacto"
    assert columna_de_ficha_incompleta(fila(direccion="", contacto="")) == "direccion"
