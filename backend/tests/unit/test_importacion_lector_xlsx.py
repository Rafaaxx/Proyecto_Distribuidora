"""Tarea 3.4 (change 10): lector de `.xlsx` con la biblioteca estándar
(`design.md` D2 y D3).

Las planillas mínimas se generan en la prueba con `zipfile`: la primera hoja,
cadenas compartidas y en línea, celdas numéricas leídas como TEXTO LITERAL del XML
(nunca `float`) y fechas solo cuando la celda tiene formato de fecha.

Una celda numérica sale con coma decimal, igual que el texto que escribe Excel en
español, para que `domain/valores.py` tenga un único formato de entrada (D12).

Reglas citadas: INV-03 (ninguna ruta del lector produce `float`), TR-01, TR-02,
`design.md` D2, D3 y el escenario "Excel aceptado" y "Celda numérica de Excel sin
error binario" de `specs/importacion/planillas`.
"""

from __future__ import annotations

import ast
import io
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.importacion.domain.errores import ArchivoInvalidoError
from app.modules.importacion.domain.valores import a_decimal
from app.modules.importacion.lectores.xlsx_lector import leer_xlsx

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
BACKEND = Path(__file__).resolve().parent.parent.parent


@dataclass
class N:
    """Celda numérica: el literal tal cual lo guarda Excel en `<v>`."""

    literal: str
    estilo: int | None = None


@dataclass
class T:
    """Celda de texto en línea (`t="inlineStr"`)."""

    texto: str


@dataclass
class S:
    """Celda de cadena compartida (`t="s"`)."""

    texto: str


@dataclass
class B:
    valor: bool


@dataclass
class F:
    """Resultado de fórmula de texto (`t="str"`)."""

    texto: str


def _letra(indice: int) -> str:
    letras = ""
    indice += 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def construir_xlsx(
    filas: dict[int, dict[int, object]],
    *,
    segunda_hoja: bool = False,
    estilos: str | None = None,
    compartidas_xml: str | None = None,
    con_referencia_de_celda: bool = True,
) -> bytes:
    """`filas`: `{numero_de_fila: {indice_de_columna: celda}}` (filas y columnas
    pueden saltearse, como en una planilla real)."""
    compartidas: list[str] = []
    xml_filas: list[str] = []
    for numero in sorted(filas):
        celdas_xml: list[str] = []
        for columna in sorted(filas[numero]):
            celda = filas[numero][columna]
            ref = f' r="{_letra(columna)}{numero}"' if con_referencia_de_celda else ""
            if isinstance(celda, N):
                s = f' s="{celda.estilo}"' if celda.estilo is not None else ""
                celdas_xml.append(f"<c{ref}{s}><v>{celda.literal}</v></c>")
            elif isinstance(celda, T):
                celdas_xml.append(
                    f'<c{ref} t="inlineStr"><is><t xml:space="preserve">'
                    f"{escape(celda.texto)}</t></is></c>"
                )
            elif isinstance(celda, S):
                compartidas.append(celda.texto)
                celdas_xml.append(f'<c{ref} t="s"><v>{len(compartidas) - 1}</v></c>')
            elif isinstance(celda, B):
                celdas_xml.append(f'<c{ref} t="b"><v>{int(celda.valor)}</v></c>')
            elif isinstance(celda, F):
                celdas_xml.append(f'<c{ref} t="str"><f>A1</f><v>{escape(celda.texto)}</v></c>')
            else:  # pragma: no cover - error de la prueba
                raise AssertionError(celda)
        xml_filas.append(f'<row r="{numero}">{"".join(celdas_xml)}</row>')
    hoja = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{NS}"><sheetData>{"".join(xml_filas)}</sheetData></worksheet>'
    )
    if compartidas_xml is None:
        compartidas_xml = (
            f'<?xml version="1.0" encoding="UTF-8"?><sst xmlns="{NS}">'
            + "".join(f"<si><t xml:space='preserve'>{escape(c)}</t></si>" for c in compartidas)
            + "</sst>"
        )
    hojas = '<sheet name="Datos" sheetId="1" r:id="rId1"/>'
    relaciones = '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>'
    if segunda_hoja:
        hojas += '<sheet name="Otra" sheetId="2" r:id="rId2"/>'
        relaciones += '<Relationship Id="rId2" Type="worksheet" Target="worksheets/sheet2.xml"/>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        zf.writestr(
            "xl/workbook.xml",
            f'<?xml version="1.0"?><workbook xmlns="{NS}" xmlns:r="{NS_REL}">'
            f"<sheets>{hojas}</sheets></workbook>",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            f'package/2006/relationships">{relaciones}</Relationships>',
        )
        zf.writestr("xl/worksheets/sheet1.xml", hoja)
        if segunda_hoja:
            zf.writestr(
                "xl/worksheets/sheet2.xml",
                f'<worksheet xmlns="{NS}"><sheetData><row r="1"><c r="A1" t="inlineStr">'
                "<is><t>OTRA HOJA</t></is></c></row></sheetData></worksheet>",
            )
        zf.writestr("xl/sharedStrings.xml", compartidas_xml)
        if estilos is not None:
            zf.writestr("xl/styles.xml", estilos)
    return buffer.getvalue()


ESTILOS = (
    f'<?xml version="1.0"?><styleSheet xmlns="{NS}">'
    '<numFmts count="2"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/>'
    '<numFmt numFmtId="165" formatCode="0.00&quot;d&quot;"/></numFmts>'
    "<cellXfs>"
    '<xf numFmtId="0"/>'  # 0: General
    '<xf numFmtId="14"/>'  # 1: fecha integrada
    '<xf numFmtId="164"/>'  # 2: fecha personalizada
    '<xf numFmtId="2"/>'  # 3: 0.00
    '<xf numFmtId="165"/>'  # 4: personalizado que NO es fecha (la "d" está entre comillas)
    "</cellXfs></styleSheet>"
)


def _serial(fecha: date) -> str:
    return str((fecha - date(1899, 12, 30)).days)


# --- primera hoja, textos y números ---------------------------------------------


def test_se_lee_la_primera_hoja_con_cadenas_compartidas_y_en_linea() -> None:
    """Escenario "Excel aceptado"."""
    datos = construir_xlsx(
        {
            1: {0: S("nombre"), 1: S("cuit")},
            2: {0: S("Bodega Sur"), 1: N("30712345678")},
            3: {0: T("Cervecería Ñandú"), 1: F("")},
        },
        segunda_hoja=True,
    )

    filas = leer_xlsx(datos)

    assert filas == [
        (1, ["nombre", "cuit"]),
        (2, ["Bodega Sur", "30712345678"]),
        (3, ["Cervecería Ñandú", ""]),
    ]  # y nada de "OTRA HOJA"


def test_las_celdas_vacias_intermedias_y_las_filas_salteadas_conservan_su_posicion() -> None:
    datos = construir_xlsx({1: {0: S("a"), 2: S("c")}, 4: {1: S("x")}})

    filas = leer_xlsx(datos)

    assert filas == [(1, ["a", "", "c"]), (4, ["", "x"])]


def test_una_cadena_compartida_con_formato_se_lee_completa_y_sin_la_fonetica() -> None:
    compartidas = (
        f'<sst xmlns="{NS}"><si><r><t>Bod</t></r><r><t>ega</t></r><rPh sb="0" eb="1">'
        "<t>ボ</t></rPh></si></sst>"
    )
    datos = construir_xlsx({1: {0: S("ignorado")}}, compartidas_xml=compartidas)

    assert leer_xlsx(datos) == [(1, ["Bodega"])]


def test_un_numero_se_lee_como_el_texto_literal_del_xml_con_coma_decimal() -> None:
    """Escenario "Celda numérica de Excel sin error binario" (D3): `1239.669421` es
    `"1239.669421"` en el valor, sin dígitos espurios."""
    datos = construir_xlsx({1: {0: N("1239.669421"), 1: N("18000"), 2: N("-12"), 3: N("0.5")}})

    ((_, celdas),) = leer_xlsx(datos)

    assert celdas == ["1239,669421", "18000", "-12", "0,5"]
    assert a_decimal(celdas[0], columna="costo") == Decimal("1239.669421")


def test_un_resultado_de_formula_con_decimales_espurios_se_conserva_literal() -> None:
    """D3: `=18000/1,21/12` guardado como `1239.6694214876034` NO se redondea acá;
    lo rechaza la regla de decimales del destino (`COSTO_INVALIDO`)."""
    datos = construir_xlsx({1: {0: N("1239.6694214876034")}})

    ((_, celdas),) = leer_xlsx(datos)

    assert celdas == ["1239,6694214876034"]
    assert a_decimal(celdas[0], columna="costo") == Decimal("1239.6694214876034")


@pytest.mark.parametrize(
    ("literal", "esperado"),
    [
        ("1.5E-3", "0,0015"),
        ("1E+2", "100"),
        ("1.23456789012345E+20", "123456789012345000000"),
        ("1E-10", "0,0000000001"),
        ("0.1", "0,1"),
        ("12", "12"),
    ],
)
def test_la_notacion_cientifica_de_excel_se_expande_sin_pasar_por_float(
    literal: str, esperado: str
) -> None:
    ((_, celdas),) = leer_xlsx(construir_xlsx({1: {0: N(literal)}}))

    assert celdas == [esperado]


@settings(deadline=None)
@given(
    entero=st.integers(min_value=0, max_value=10**20),
    decimales=st.text(alphabet="0123456789", min_size=1, max_size=17),
    negativo=st.booleans(),
)
def test_inv03_cualquier_literal_numerico_sobrevive_exacto_sin_pasar_por_float(
    entero: int, decimales: str, negativo: bool
) -> None:
    """INV-03: con hasta 20 dígitos enteros y 17 decimales (más de los que alcanza
    un `float`), el valor leído es exactamente el literal del XML."""
    literal = f"{'-' if negativo else ''}{entero}.{decimales}"

    ((_, celdas),) = leer_xlsx(construir_xlsx({1: {0: N(literal)}}))

    assert a_decimal(celdas[0], columna="costo") == Decimal(literal)
    assert str(a_decimal(celdas[0], columna="costo")) == str(Decimal(literal))


def test_inv03_ningun_valor_devuelto_es_float_y_el_codigo_de_lectura_no_usa_float() -> None:
    """INV-03: los valores devueltos son todos `str` y ni los lectores ni el dominio
    de `importacion` nombran `float` en su código."""
    datos = construir_xlsx(
        {1: {0: N("1239.669421"), 1: B(True), 2: N("1E-3"), 3: N("5", estilo=1)}},
        estilos=ESTILOS,
    )

    ((_, celdas),) = leer_xlsx(datos)

    assert all(type(celda) is str for celda in celdas)

    infractores: list[str] = []
    raiz = BACKEND / "app" / "modules" / "importacion"
    for carpeta in ("lectores", "domain"):
        for archivo in (raiz / carpeta).glob("*.py"):
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Name) and nodo.id == "float":
                    infractores.append(f"{archivo.name}:{nodo.lineno}")
                if isinstance(nodo, ast.Constant) and isinstance(nodo.value, float):
                    infractores.append(f"{archivo.name}:{nodo.lineno} (literal)")
    assert infractores == []


# --- fechas, booleanos y errores --------------------------------------------------


@pytest.mark.parametrize("estilo", [1, 2])
def test_una_celda_numerica_con_formato_de_fecha_se_lee_como_fecha_iso(estilo: int) -> None:
    """Fechas de Excel: número de serie SOLO si la celda tiene formato de fecha
    (integrado o personalizado)."""
    serial = _serial(date(2026, 10, 1))

    ((_, celdas),) = leer_xlsx(construir_xlsx({1: {0: N(serial, estilo)}}, estilos=ESTILOS))

    assert celdas == ["2026-10-01"]


@pytest.mark.parametrize("estilo", [None, 0, 3, 4])
def test_un_numero_sin_formato_de_fecha_no_se_convierte_en_fecha(estilo: int | None) -> None:
    serial = _serial(date(2026, 10, 1))

    ((_, celdas),) = leer_xlsx(construir_xlsx({1: {0: N(serial, estilo)}}, estilos=ESTILOS))

    assert celdas == [serial]


def test_un_serial_de_fecha_con_hora_no_se_convierte_y_queda_para_fecha_invalida() -> None:
    ((_, celdas),) = leer_xlsx(construir_xlsx({1: {0: N("46296.5", 1)}}, estilos=ESTILOS))

    assert celdas == ["46296,5"]


def test_un_libro_sin_estilos_lee_los_numeros_como_numeros() -> None:
    ((_, celdas),) = leer_xlsx(construir_xlsx({1: {0: N("45000", 1)}}, estilos=None))

    assert celdas == ["45000"]


def test_un_booleano_de_excel_se_lee_como_s_o_n() -> None:
    ((_, celdas),) = leer_xlsx(construir_xlsx({1: {0: B(True), 1: B(False)}}))

    assert celdas == ["S", "N"]


def test_las_celdas_sin_referencia_se_leen_en_orden() -> None:
    """Hay escritores que omiten `r=` en las celdas: se asume la columna siguiente."""
    datos = construir_xlsx({1: {0: S("a"), 1: S("b")}}, con_referencia_de_celda=False)

    assert leer_xlsx(datos) == [(1, ["a", "b"])]


@pytest.mark.parametrize(
    "datos",
    [
        b"",
        b"%PDF-1.7 no es un xlsx",
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 .xls antiguo (OLE2)",
        b"PK\x03\x04 zip roto",
    ],
)
def test_un_archivo_que_no_es_xlsx_es_archivo_invalido(datos: bytes) -> None:
    with pytest.raises(ArchivoInvalidoError) as error:
        leer_xlsx(datos)

    assert error.value.codigo == "ARCHIVO_INVALIDO"


def test_un_zip_que_no_es_un_libro_de_excel_es_archivo_invalido() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("hola.txt", "no soy un libro")

    with pytest.raises(ArchivoInvalidoError):
        leer_xlsx(buffer.getvalue())


def test_una_hoja_con_xml_roto_es_archivo_invalido() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{NS}" xmlns:r="{NS_REL}"><sheets>'
            '<sheet name="A" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        zf.writestr("xl/worksheets/sheet1.xml", "<worksheet><sheetData><row")

    with pytest.raises(ArchivoInvalidoError):
        leer_xlsx(buffer.getvalue())


def test_una_hoja_que_descomprime_a_un_tamano_absurdo_se_rechaza_sin_leerla() -> None:
    """Defensa contra bombas de compresión: el tamaño descomprimido declarado por el
    zip se verifica antes de parsear."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", b"<a>" + b"x" * (60 * 1024 * 1024) + b"</a>")

    with pytest.raises(ArchivoInvalidoError) as error:
        leer_xlsx(buffer.getvalue())

    assert "demasiado" in error.value.mensaje.lower()
