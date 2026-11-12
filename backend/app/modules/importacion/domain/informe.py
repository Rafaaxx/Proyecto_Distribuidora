"""Informe de errores por fila de una importación (`design.md` D1 y "Detalles
derivados"; `specs/importacion/registro-de-importaciones`).

Puro. Cada `DomainError` que lanza un servicio al escribir una fila se traduce a un
`ErrorDeFila` `{fila, columna, codigo, mensaje}`: el código y el mensaje son los del
servicio (el mismo error que devuelve el alta individual, TR-10) y la columna sale
de una tabla código -> columna por tipo. Los errores de una celda (`NUMERO_INVALIDO`
y compañía) ya traen su columna. El error de `informar_costos` trae la `fila` como
índice dentro del lote en `extension`, y se traduce a la fila de la planilla.

Si al terminar hubo algún error, la importación entera se rechaza con
`IMPORTACION_CON_ERRORES` (422) y la lista completa en `extension.errores`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.core.errors import DomainError
from app.modules.importacion.domain.errores import ErrorDeValor, ImportacionConErroresError

# Código de dominio -> columna de la planilla, por tipo. Un código que no figura
# queda sin columna (error de toda la fila). Los códigos son los de los servicios
# de los demás módulos; la tabla crece con cada importador.
_COLUMNA_POR_CODIGO: dict[str, dict[str, str]] = {
    "PROVEEDORES": {
        "NOMBRE_INVALIDO": "nombre",
        "NOMBRE_DUPLICADO": "nombre",
        "CUIT_INVALIDO": "cuit",
        "CUIT_DUPLICADO": "cuit",
    },
    "CLIENTES": {
        "NOMBRE_INVALIDO": "nombre",
        "CODIGO_DUPLICADO": "codigo",
        "DOCUMENTO_INCOMPLETO": "documento_numero",
        "DOCUMENTO_DUPLICADO": "documento_numero",
        "DOCUMENTO_INVALIDO": "documento_numero",
        "ESTADO_FACTURACION_INVALIDO": "estado_facturacion_default",
    },
    "PRODUCTOS": {
        "CODIGO_DUPLICADO": "codigo",
        "CODIGO_INVALIDO": "codigo",
        "UNIDADES_INVALIDAS": "unidades_base",
        "REFERENCIA_INVALIDA": "es_referencia",
        "CATEGORIA_INACTIVA": "categoria",
        "MARCA_INACTIVA": "marca",
        "ALICUOTA_INACTIVA": "alicuota",
        "PROVEEDOR_INACTIVO": "proveedor",
    },
    "COSTOS": {
        "PRESENTACION_INVALIDA": "presentacion",
        "VALOR_INVALIDO": "valor",
        "BONIFICACION_INVALIDA": "bonificacion",
        "PRODUCTO_INACTIVO": "producto_codigo",
        "PROVEEDOR_INACTIVO": "producto_codigo",
    },
    "STOCK_INICIAL": {
        "COSTO_INVALIDO": "costo_unitario",
        "UBICACION_INACTIVA": "ubicacion",
        "PRODUCTO_INACTIVO": "producto_codigo",
        "PRODUCTO_CON_OPERACIONES": "producto_codigo",
        "CANTIDAD_INVALIDA": "cantidad_base",
        "CANTIDAD_FUERA_DE_RANGO": "cantidad_base",
        "STOCK_INSUFICIENTE": "cantidad_base",
    },
    "SALDOS_INICIALES": {
        "IMPORTE_INVALIDO": "importe",
        "SALDO_FUERA_DE_RANGO": "importe",
        "SENTIDO_INVALIDO": "sentido",
        "CUENTA_CON_OPERACIONES": "entidad",
        "CONSUMIDOR_FINAL_SIN_CUENTA": "entidad",
    },
}


@dataclass(frozen=True)
class ErrorDeFila:
    """Un error del informe: la fila de la planilla (el encabezado es la 1), la
    columna si aplica, el código de dominio estable y el mensaje."""

    fila: int
    columna: str | None
    codigo: str
    mensaje: str

    def como_dict(self) -> dict[str, object]:
        return {
            "fila": self.fila,
            "columna": self.columna,
            "codigo": self.codigo,
            "mensaje": self.mensaje,
        }


def _fila_del_lote(error: DomainError, fila: int, filas_de_lote: Sequence[int] | None) -> int:
    """La fila de planilla que corresponde al índice `fila` de `extension`, si el
    error vino de un lote y el índice es válido; si no, la del llamador."""
    if filas_de_lote is None or error.extension is None:
        return fila
    indice = error.extension.get("fila")
    if (
        isinstance(indice, int)
        and not isinstance(indice, bool)
        and 0 <= indice < len(filas_de_lote)
    ):
        return filas_de_lote[indice]
    return fila


def traducir_error(
    tipo: str,
    fila: int,
    error: DomainError,
    *,
    filas_de_lote: Sequence[int] | None = None,
    columna: str | None = None,
) -> ErrorDeFila:
    """Error de dominio de un servicio a error de fila. `filas_de_lote` mapea el
    índice de lote de `informar_costos` a la fila de la planilla. `columna` fuerza la
    columna cuando la tabla código -> columna no alcanza (un mismo código que según el
    dato cae en columnas distintas, como `FICHA_INCOMPLETA`)."""
    if isinstance(error, ErrorDeValor):
        columna = error.columna
    elif columna is None:
        columna = _COLUMNA_POR_CODIGO.get(tipo, {}).get(error.codigo)
    return ErrorDeFila(
        fila=_fila_del_lote(error, fila, filas_de_lote),
        columna=columna,
        codigo=error.codigo,
        mensaje=error.mensaje,
    )


def error_de_fila_duplicada(*, fila: int, columna: str, fila_original: int) -> ErrorDeFila:
    """La clave natural ya apareció antes en el mismo archivo (`FILA_DUPLICADA`,
    `design.md` D6): cita la primera aparición."""
    return ErrorDeFila(
        fila=fila,
        columna=columna,
        codigo="FILA_DUPLICADA",
        mensaje=f"Esta fila repite la clave de la fila {fila_original} del mismo archivo.",
    )


def error_agregado(errores: Sequence[ErrorDeFila]) -> ImportacionConErroresError:
    """`IMPORTACION_CON_ERRORES` con la lista completa, ordenada por fila (el orden
    entre errores de una misma fila se conserva)."""
    if not errores:
        raise ValueError("El error agregado necesita al menos un error de fila.")
    ordenados = sorted(errores, key=lambda e: e.fila)
    return ImportacionConErroresError([e.como_dict() for e in ordenados])
