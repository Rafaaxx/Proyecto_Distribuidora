"""Lector de `.xlsx` con la biblioteca estándar: `zipfile` + `xml.etree`
(`design.md` D2, D3). Sin dependencia nueva.

Lee la PRIMERA hoja del libro y devuelve filas de texto con su número de fila
(`FilaCruda`). La conversión de cada celda a decimal, entero, booleano o fecha NO
ocurre acá: el texto llega a `domain/valores.py`.

Exactitud (INV-03, D3): una celda numérica se lee como el TEXTO LITERAL guardado
en el XML (`<v>1239.669421</v>`), nunca como `float`. Excel guarda el número con
punto decimal y, a veces, en notación científica; el lector lo expande con
`Decimal` (exacto) y lo entrega con coma decimal, el mismo formato de un texto
escrito en español (D12), para que el dominio tenga un único formato de entrada.
Un resultado de fórmula con decimales espurios (`1239.6694214876034`) se conserva
literal: lo rechaza la regla de decimales del destino, no se redondea acá.

- Texto: cadenas compartidas (`t="s"`), en línea (`t="inlineStr"`) y resultados de
  fórmula de texto (`t="str"`).
- Booleanos de Excel (`t="b"`): `S` / `N`.
- Fechas: solo si la celda numérica tiene formato de fecha (integrado o
  personalizado) y es un día entero; salen como `AAAA-MM-DD`. Un número sin ese
  formato sigue siendo un número.
- Defensas: tamaño descomprimido de cada parte, columnas máximas de Excel y sin
  entidades ni DTD en el XML.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET  # noqa: S405 (se rechazan DTD y entidades antes)

from app.modules.importacion.domain.errores import ArchivoInvalidoError
from app.modules.importacion.domain.planilla import FilaCruda

_NS_RELACIONES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Una hoja de 5 MB comprimidos no descomprime legítimamente a más de esto: es la
# defensa contra una bomba de compresión.
TAMANO_MAXIMO_DE_PARTE = 50 * 1024 * 1024
COLUMNAS_MAXIMAS = 16384  # XFD

_EPOCA_EXCEL = date(1899, 12, 30)
_SERIAL_MINIMO_DE_FECHA = 61  # antes de esto Excel arrastra el error del 29/02/1900
_SERIAL_MAXIMO_DE_FECHA = 2_958_465  # 31/12/9999
_EXPONENTE_MAXIMO = 40  # un número con más magnitud no es un importe

_FORMATOS_DE_FECHA_INTEGRADOS = frozenset(
    {*range(14, 23), *range(27, 37), *range(45, 48), *range(50, 59)}
)
_QUITAR_DE_FORMATO = re.compile(r'"[^"]*"|\[[^\]]*\]|\\.|_.|\*.')
_LETRAS_DE_FECHA = frozenset("dmyhs")
_REFERENCIA = re.compile(r"([A-Za-z]+)(\d+)")


def _local(etiqueta: str) -> str:
    return etiqueta.rsplit("}", 1)[-1]


def _no_es_un_libro(motivo: str) -> ArchivoInvalidoError:
    return ArchivoInvalidoError(f"El archivo no es un libro de Excel (.xlsx) válido: {motivo}.")


def _parsear(datos: bytes, parte: str) -> ET.Element:
    """XML de una parte del libro. Un DTD o una entidad no existen en un `.xlsx`
    legítimo y habilitarían una expansión de entidades: se rechazan."""
    cabecera = datos[:4096].lower()
    if b"<!doctype" in cabecera or b"<!entity" in datos.lower():
        raise _no_es_un_libro(f"{parte} declara entidades")
    try:
        return ET.fromstring(datos)  # noqa: S314 (sin DTD ni entidades, ver arriba)
    except ET.ParseError as error:
        raise _no_es_un_libro(f"{parte} está dañada") from error


def _leer_parte(zf: zipfile.ZipFile, parte: str) -> bytes | None:
    try:
        return zf.read(parte)
    except KeyError:
        return None


def _texto_de(elemento: ET.Element) -> str:
    """Texto de un `<si>` o `<is>`: concatena los `<t>` (también los de runs con
    formato `<r>`) y descarta la fonética `<rPh>`."""
    partes: list[str] = []
    for hijo in elemento:
        etiqueta = _local(hijo.tag)
        if etiqueta == "t":
            partes.append(hijo.text or "")
        elif etiqueta == "r":
            partes.extend((t.text or "") for t in hijo if _local(t.tag) == "t")
    return "".join(partes)


def _cadenas_compartidas(zf: zipfile.ZipFile) -> list[str]:
    datos = _leer_parte(zf, "xl/sharedStrings.xml")
    if datos is None:
        return []
    raiz = _parsear(datos, "xl/sharedStrings.xml")
    return [_texto_de(si) for si in raiz if _local(si.tag) == "si"]


def _es_formato_de_fecha_personalizado(codigo: str) -> bool:
    sin_literales = _QUITAR_DE_FORMATO.sub("", codigo).lower()
    return any(letra in _LETRAS_DE_FECHA for letra in sin_literales)


def _estilos_de_fecha(zf: zipfile.ZipFile) -> list[bool]:
    """Para cada `xf` de `cellXfs` (por índice de estilo), si su formato es de fecha."""
    datos = _leer_parte(zf, "xl/styles.xml")
    if datos is None:
        return []
    raiz = _parsear(datos, "xl/styles.xml")
    personalizados: dict[int, str] = {}
    xfs: list[int] = []
    for hijo in raiz:
        etiqueta = _local(hijo.tag)
        if etiqueta == "numFmts":
            for formato in hijo:
                identificador = formato.get("numFmtId")
                if identificador is not None and identificador.isdigit():
                    personalizados[int(identificador)] = formato.get("formatCode", "")
        elif etiqueta == "cellXfs":
            for xf in hijo:
                identificador = xf.get("numFmtId", "0")
                xfs.append(int(identificador) if identificador.isdigit() else 0)
    return [
        formato in _FORMATOS_DE_FECHA_INTEGRADOS
        or (
            formato in personalizados
            and _es_formato_de_fecha_personalizado(personalizados[formato])
        )
        for formato in xfs
    ]


def _ruta_de_la_primera_hoja(zf: zipfile.ZipFile) -> str:
    libro = _leer_parte(zf, "xl/workbook.xml")
    relaciones = _leer_parte(zf, "xl/_rels/workbook.xml.rels")
    if libro is None or relaciones is None:
        raise _no_es_un_libro("faltan xl/workbook.xml o sus relaciones")
    identificador: str | None = None
    for hoja in _parsear(libro, "xl/workbook.xml").iter():
        if _local(hoja.tag) == "sheet":
            identificador = hoja.get(f"{{{_NS_RELACIONES}}}id")
            break
    if identificador is None:
        raise _no_es_un_libro("el libro no tiene hojas")
    for relacion in _parsear(relaciones, "xl/_rels/workbook.xml.rels"):
        if relacion.get("Id") == identificador:
            destino = relacion.get("Target", "")
            return destino.lstrip("/") if destino.startswith("/") else posixpath.join("xl", destino)
    raise _no_es_un_libro("no se encuentra la primera hoja")


def _indice_de_columna(letras: str) -> int:
    indice = 0
    for letra in letras.upper():
        indice = indice * 26 + (ord(letra) - 64)
    return indice - 1


def _numero_a_texto(literal: str, *, es_fecha: bool) -> str:
    """Literal numérico del XML a texto de planilla, sin pasar por `float`."""
    recortado = literal.strip()
    try:
        valor = Decimal(recortado)
    except InvalidOperation:
        return recortado
    if not valor.is_finite() or abs(valor.adjusted()) > _EXPONENTE_MAXIMO:
        return recortado
    if (
        es_fecha
        and valor == valor.to_integral_value()
        and _SERIAL_MINIMO_DE_FECHA <= valor <= _SERIAL_MAXIMO_DE_FECHA
    ):
        return (_EPOCA_EXCEL + timedelta(days=int(valor))).isoformat()
    return format(valor, "f").replace(".", ",")


def _valor_de_celda(celda: ET.Element, compartidas: list[str], estilos_de_fecha: list[bool]) -> str:
    tipo = celda.get("t", "n")
    valor = next((hijo for hijo in celda if _local(hijo.tag) == "v"), None)
    texto_v = (valor.text or "") if valor is not None else ""
    if tipo == "inlineStr":
        en_linea = next((hijo for hijo in celda if _local(hijo.tag) == "is"), None)
        return _texto_de(en_linea) if en_linea is not None else ""
    if tipo == "s":
        try:
            return compartidas[int(texto_v)]
        except (ValueError, IndexError) as error:
            raise _no_es_un_libro("una celda referencia una cadena inexistente") from error
    if tipo == "b":
        return "S" if texto_v.strip() == "1" else "N"
    if tipo == "d":
        return texto_v.strip()[:10]
    if tipo in ("str", "e"):
        return texto_v
    if texto_v.strip() == "":
        return ""
    estilo = celda.get("s")
    es_fecha = (
        estilo is not None
        and estilo.isdigit()
        and int(estilo) < len(estilos_de_fecha)
        and estilos_de_fecha[int(estilo)]
    )
    return _numero_a_texto(texto_v, es_fecha=es_fecha)


def _filas_de_la_hoja(
    raiz: ET.Element, compartidas: list[str], estilos_de_fecha: list[bool]
) -> list[FilaCruda]:
    resultado: list[FilaCruda] = []
    numero_anterior = 0
    for fila in raiz.iter():
        if _local(fila.tag) != "row":
            continue
        atributo = fila.get("r")
        numero = (
            int(atributo) if atributo is not None and atributo.isdigit() else numero_anterior + 1
        )
        numero_anterior = numero
        celdas: list[str] = []
        siguiente = 0
        for celda in fila:
            if _local(celda.tag) != "c":
                continue
            referencia = _REFERENCIA.fullmatch(celda.get("r", ""))
            columna = _indice_de_columna(referencia[1]) if referencia is not None else siguiente
            if not 0 <= columna < COLUMNAS_MAXIMAS:
                raise _no_es_un_libro("una celda está fuera de las columnas de Excel")
            celdas.extend([""] * (columna + 1 - len(celdas)))
            celdas[columna] = _valor_de_celda(celda, compartidas, estilos_de_fecha)
            siguiente = columna + 1
        if celdas:
            resultado.append((numero, celdas))
    return resultado


def leer_xlsx(contenido: bytes) -> list[FilaCruda]:
    """Filas de la primera hoja como `(número de fila, celdas)`. `ARCHIVO_INVALIDO`
    si el archivo no es un `.xlsx` legible."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile as error:
        raise _no_es_un_libro("no es un archivo zip") from error
    with zf:
        for parte in zf.infolist():
            if parte.file_size > TAMANO_MAXIMO_DE_PARTE:
                raise ArchivoInvalidoError(
                    "El archivo descomprime a un tamaño demasiado grande para ser una planilla."
                )
        try:
            ruta = _ruta_de_la_primera_hoja(zf)
            datos_hoja = _leer_parte(zf, ruta)
            if datos_hoja is None:
                raise _no_es_un_libro("falta la primera hoja")
            compartidas = _cadenas_compartidas(zf)
            estilos_de_fecha = _estilos_de_fecha(zf)
            hoja = _parsear(datos_hoja, ruta)
        except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as error:
            raise _no_es_un_libro("el contenido está dañado") from error
        return _filas_de_la_hoja(hoja, compartidas, estilos_de_fecha)
