"""Columnas por tipo, encabezado y filas de una planilla de importación
(`specs/importacion/planillas`, `design.md` D5, D6, D9, D11, D13).

Puro: recibe filas ya leídas por un lector (`FilaCruda`: número de fila en la
planilla más sus celdas como texto) y devuelve filas con un valor de texto por
columna del tipo, o rechaza el archivo completo (`COLUMNAS_INVALIDAS`,
`ARCHIVO_SIN_FILAS`, `ARCHIVO_DEMASIADO_GRANDE`, `ARCHIVO_INVALIDO`) sin procesar
ninguna fila. La conversión de cada valor a decimal, entero, booleano o fecha es
de `valores.py` y la hace el importador de cada tipo.

Numeración: el encabezado es la fila 1 y la primera fila de datos la 2, tal como
las ve el usuario en su planilla, aunque haya filas vacías en el medio.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.modules.importacion.domain.errores import (
    ArchivoDemasiadoGrandeError,
    ArchivoInvalidoError,
    ArchivoSinFilasError,
    ColumnasInvalidasError,
    TipoImportacionInvalidoError,
)

TIPOS_DE_IMPORTACION: tuple[str, ...] = (
    "PRODUCTOS",
    "CLIENTES",
    "PROVEEDORES",
    "PRECIOS",
    "COSTOS",
    "STOCK_INICIAL",
    "SALDOS_INICIALES",
)
"""Catálogo completo de `03` §13 más `COSTOS` (`design.md` D9). `PRECIOS` no tiene
importador hasta el change 13."""

LIMITE_DE_FILAS = 2000
"""Filas de datos por archivo (`design.md` D11)."""

LIMITE_DE_BYTES = 5 * 1024 * 1024
"""Tamaño máximo del archivo (`design.md` D11)."""

FilaCruda = tuple[int, list[str]]
"""`(número de fila en la planilla, celdas como texto)`."""


@dataclass(frozen=True)
class Columna:
    """Una columna de la plantilla de un tipo. `obligatoria` dice si DEBE estar en
    el encabezado; su valor puede ser vacío si la regla del tipo lo admite."""

    nombre: str
    obligatoria: bool


def _con_orden(*grupos: tuple[str, bool]) -> tuple[Columna, ...]:
    return tuple(Columna(nombre, obligatoria) for nombre, obligatoria in grupos)


_COLUMNAS_POR_TIPO: dict[str, tuple[Columna, ...]] = {
    "PROVEEDORES": _con_orden(
        ("nombre", True),
        ("cuit", False),
        ("contacto", False),
        ("telefono", False),
        ("email", False),
    ),
    # D5-A: una fila por presentación, agrupadas por `codigo`, con los datos del
    # producto repetidos.
    "PRODUCTOS": _con_orden(
        ("codigo", True),
        ("nombre", True),
        ("categoria", True),
        ("marca", False),
        ("proveedor", True),
        ("unidad_base", True),
        ("alicuota", True),
        ("presentacion", True),
        ("unidades_base", True),
        ("usar_en_venta", True),
        ("usar_en_compra", True),
        ("es_referencia", True),
    ),
    # D6-A: `codigo` es obligatorio en la planilla (CLI-01 lo deja opcional en la
    # pantalla) para poder referenciar al cliente en los saldos y para que una
    # reimportación no duplique clientes.
    "CLIENTES": _con_orden(
        ("nombre", True),
        ("codigo", True),
        ("razon_social", False),
        ("documento_tipo", False),
        ("documento_numero", False),
        ("direccion", True),
        ("contacto", True),
        ("telefono", False),
        ("email", False),
        ("estado_facturacion_default", False),
    ),
    "COSTOS": _con_orden(
        ("producto_codigo", True),
        ("presentacion", True),
        ("valor", True),
        ("incluye_iva", True),
        ("bonificacion", False),
        ("vigencia_desde", True),
        ("observacion", False),
    ),
    # D13-A: `cantidad_base` entera y `costo_unitario` por unidad base, el mismo
    # contrato que `STOCK_INICIAL_REGISTRAR`.
    "STOCK_INICIAL": _con_orden(
        ("ubicacion", True),
        ("producto_codigo", True),
        ("cantidad_base", True),
        ("costo_unitario", True),
    ),
    "SALDOS_INICIALES": _con_orden(
        ("cuenta_tipo", True),
        ("entidad", True),
        ("importe", True),
        ("sentido", True),
    ),
}


def columnas_de(tipo: str) -> tuple[Columna, ...]:
    """Columnas de la plantilla de `tipo`, en el orden de la plantilla.
    `TIPO_IMPORTACION_INVALIDO` si el tipo es desconocido o todavía no tiene
    importador (`PRECIOS`, `design.md` D9)."""
    try:
        return _COLUMNAS_POR_TIPO[tipo]
    except KeyError:
        raise TipoImportacionInvalidoError(
            f"El tipo de importación {tipo!r} no es válido o todavía no está disponible."
        ) from None


def encabezado_de_plantilla(tipo: str) -> list[str]:
    """Nombres de las columnas en el orden de la plantilla descargable."""
    return [columna.nombre for columna in columnas_de(tipo)]


@dataclass(frozen=True)
class FilaPlanilla:
    """Una fila de datos: su número en la planilla y un texto por columna del tipo
    (vacío si la celda está vacía o la columna opcional no está en el archivo)."""

    fila: int
    valores: dict[str, str]


def _es_vacia(celdas: Sequence[str]) -> bool:
    return all(celda.strip() == "" for celda in celdas)


def _nombres_del_encabezado(celdas: Sequence[str]) -> list[str]:
    """Recorta las celdas vacías del final (Excel guarda `nombre;cuit;;;`) y
    normaliza: sin espacios al borde y sin distinguir mayúsculas."""
    nombres = [celda.strip().lower() for celda in celdas]
    while nombres and nombres[-1] == "":
        nombres.pop()
    return nombres


def _validar_columnas(tipo: str, nombres: list[str]) -> None:
    definidas = columnas_de(tipo)
    conocidas = {columna.nombre for columna in definidas}

    repetidas: list[str] = []
    for nombre in nombres:
        if nombres.count(nombre) > 1 and nombre not in repetidas:
            repetidas.append(nombre)
    desconocidas = [nombre for nombre in dict.fromkeys(nombres) if nombre not in conocidas]
    faltantes = [c.nombre for c in definidas if c.obligatoria and c.nombre not in nombres]

    if not (faltantes or desconocidas or repetidas):
        return
    partes: list[str] = []
    if faltantes:
        partes.append("falta " + ", ".join(faltantes))
    if desconocidas:
        partes.append("desconocida " + ", ".join(repr(n) if n == "" else n for n in desconocidas))
    if repetidas:
        partes.append("repetida " + ", ".join(repetidas))
    raise ColumnasInvalidasError(
        "El encabezado no coincide con la plantilla: " + "; ".join(partes) + ".",
        faltantes=faltantes,
        desconocidas=desconocidas,
        repetidas=repetidas,
    )


def armar_planilla(tipo: str, filas: Sequence[FilaCruda]) -> list[FilaPlanilla]:
    """Valida el encabezado y arma las filas de datos de `tipo` (`design.md` D11).

    La fila 1 es el encabezado. Una columna obligatoria faltante, desconocida o
    repetida rechaza el archivo (`COLUMNAS_INVALIDAS`, con los nombres); el orden
    no importa. Las filas totalmente vacías se ignoran (y no cuentan para el
    límite). Una fila con celdas con datos más allá del encabezado rechaza el
    archivo (`ARCHIVO_INVALIDO`: no se pierden datos en silencio).
    """
    columnas_definidas = columnas_de(tipo)  # valida el tipo antes de mirar el archivo
    if not filas:
        raise ArchivoInvalidoError("El archivo está vacío.")
    numero_encabezado, celdas_encabezado = filas[0]
    if numero_encabezado != 1 or _es_vacia(celdas_encabezado):
        raise ArchivoInvalidoError("La primera fila del archivo debe ser el encabezado.")

    nombres = _nombres_del_encabezado(celdas_encabezado)
    _validar_columnas(tipo, nombres)

    resultado: list[FilaPlanilla] = []
    for numero, celdas in filas[1:]:
        if _es_vacia(celdas):
            continue
        if len(resultado) >= LIMITE_DE_FILAS:
            raise ArchivoDemasiadoGrandeError(
                f"El archivo tiene más de {LIMITE_DE_FILAS} filas de datos."
            )
        if not _es_vacia(celdas[len(nombres) :]):
            raise ArchivoInvalidoError(
                f"La fila {numero} tiene más celdas con datos que columnas el encabezado."
            )
        valores = dict.fromkeys((c.nombre for c in columnas_definidas), "")
        for nombre, celda in zip(nombres, celdas, strict=False):
            valores[nombre] = celda.strip()
        resultado.append(FilaPlanilla(fila=numero, valores=valores))

    if not resultado:
        raise ArchivoSinFilasError("El archivo no tiene filas de datos, solo el encabezado.")
    return resultado


def verificar_columnas_de_filas(tipo: str, filas: Sequence[FilaPlanilla]) -> None:
    """Las filas que llegan en el contenido de un comando DEBEN traer exactamente las
    columnas del tipo (`COLUMNAS_INVALIDAS` si sobra o falta alguna, con los
    nombres). `armar_planilla` ya lo garantiza al leer el archivo; el handler lo
    vuelve a verificar porque el contenido puede armarlo otro ensamblador."""
    esperadas = [columna.nombre for columna in columnas_de(tipo)]
    conocidas = set(esperadas)
    desconocidas: set[str] = set()
    faltantes: set[str] = set()
    for fila in filas:
        presentes = set(fila.valores)
        desconocidas |= presentes - conocidas
        faltantes |= conocidas - presentes
    if desconocidas or faltantes:
        raise ColumnasInvalidasError(
            "Las filas no traen las columnas de la plantilla del tipo.",
            faltantes=[nombre for nombre in esperadas if nombre in faltantes],
            desconocidas=sorted(desconocidas),
        )


def plantilla_csv(tipo: str) -> str:
    """Contenido de la plantilla descargable: solo el encabezado exacto, con `;`
    (Excel en español abre un CSV con `;` en columnas separadas; el lector detecta
    ambos separadores) y salto de línea de Windows."""
    return ";".join(encabezado_de_plantilla(tipo)) + "\r\n"


LARGO_MAXIMO_DE_NOMBRE = 255


def nombre_de_archivo(crudo: str | None) -> str:
    """Nombre del archivo tal como se guarda en el historial: sin la ruta que algunos
    navegadores antiguos envían, sin caracteres de control y de a lo sumo 255
    caracteres. Sin nombre, `archivo`."""
    ultimo = (crudo or "").replace("\\", "/").rsplit("/", 1)[-1]
    limpio = "".join(caracter for caracter in ultimo if caracter.isprintable()).strip()
    return limpio[:LARGO_MAXIMO_DE_NOMBRE] or "archivo"
