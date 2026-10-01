"""Tarea 3.2 (change 10): encabezados y filas de la planilla, límites del archivo y
definición de columnas por tipo (`specs/importacion/planillas`, `design.md` D5,
D6, D9, D11, D13).

Funciones puras sobre filas ya leídas (`FilaCruda` = número de fila en la planilla
más sus celdas): el lector de CSV o de `.xlsx` queda afuera (tareas 3.3 y 3.4).

Reglas citadas: CAT-01, INV-01, INV-21 (una columna `organizacion_id` se rechaza),
TR-08, `design.md` D5 (productos), D6 (código de cliente obligatorio), D9 (tipos),
D11 (límites y columnas), D13 (stock inicial).
"""

from __future__ import annotations

import pytest

from app.modules.importacion.domain.errores import (
    ArchivoDemasiadoGrandeError,
    ArchivoInvalidoError,
    ArchivoSinFilasError,
    ColumnasInvalidasError,
    TipoImportacionInvalidoError,
)
from app.modules.importacion.domain.planilla import (
    LIMITE_DE_FILAS,
    TIPOS_DE_IMPORTACION,
    FilaCruda,
    FilaPlanilla,
    armar_planilla,
    columnas_de,
    encabezado_de_plantilla,
    nombre_de_archivo,
    plantilla_csv,
    verificar_columnas_de_filas,
)

ENCABEZADO_PROVEEDORES = ["nombre", "cuit", "contacto", "telefono", "email"]


def _filas(*filas: list[str], desde: int = 1) -> list[FilaCruda]:
    return [(desde + indice, celdas) for indice, celdas in enumerate(filas)]


# --- columnas por tipo (D5, D6, D9, D13) --------------------------------------


def test_los_tipos_son_los_de_03_mas_costos_y_precios_no_tiene_columnas() -> None:
    """D9: el catálogo declara los siete tipos; `PRECIOS` no tiene importador hasta
    el change 13 y pedir sus columnas es `TIPO_IMPORTACION_INVALIDO`."""
    assert set(TIPOS_DE_IMPORTACION) == {
        "PROVEEDORES",
        "PRODUCTOS",
        "CLIENTES",
        "PRECIOS",
        "COSTOS",
        "STOCK_INICIAL",
        "SALDOS_INICIALES",
    }
    with pytest.raises(TipoImportacionInvalidoError) as error:
        columnas_de("PRECIOS")
    assert error.value.codigo == "TIPO_IMPORTACION_INVALIDO"


@pytest.mark.parametrize("tipo", ["VENTAS", "proveedores", "", "PRECIOS"])
def test_un_tipo_desconocido_o_sin_importador_es_tipo_importacion_invalido(tipo: str) -> None:
    with pytest.raises(TipoImportacionInvalidoError):
        columnas_de(tipo)


def test_proveedores_solo_exige_el_nombre() -> None:
    columnas = columnas_de("PROVEEDORES")

    assert [c.nombre for c in columnas] == ENCABEZADO_PROVEEDORES
    assert {c.nombre for c in columnas if c.obligatoria} == {"nombre"}


def test_productos_tiene_una_fila_por_presentacion_con_los_datos_del_producto_repetidos() -> None:
    """D5-A: `codigo, nombre, categoria, marca, proveedor, unidad_base, alicuota,
    presentacion, unidades_base, usar_en_venta, usar_en_compra, es_referencia`."""
    assert encabezado_de_plantilla("PRODUCTOS") == [
        "codigo",
        "nombre",
        "categoria",
        "marca",
        "proveedor",
        "unidad_base",
        "alicuota",
        "presentacion",
        "unidades_base",
        "usar_en_venta",
        "usar_en_compra",
        "es_referencia",
    ]


def test_clientes_exige_el_codigo_en_la_planilla() -> None:
    """D6-A: `codigo` obligatorio aunque la pantalla lo deje opcional (CLI-01)."""
    columnas = {c.nombre: c.obligatoria for c in columnas_de("CLIENTES")}

    assert columnas["codigo"] is True
    assert columnas["nombre"] is True
    assert columnas["documento_numero"] is False


def test_stock_inicial_usa_cantidad_base_y_costo_por_unidad_base() -> None:
    """D13-A: el mismo contrato que `STOCK_INICIAL_REGISTRAR`."""
    assert encabezado_de_plantilla("STOCK_INICIAL") == [
        "ubicacion",
        "producto_codigo",
        "cantidad_base",
        "costo_unitario",
    ]


@pytest.mark.parametrize(
    ("tipo", "esperado"),
    [
        ("COSTOS", ["producto_codigo", "presentacion", "valor", "incluye_iva", "bonificacion"]),
        ("SALDOS_INICIALES", ["cuenta_tipo", "entidad", "importe", "sentido"]),
    ],
)
def test_las_columnas_de_costos_y_saldos_siguen_a_la_spec(tipo: str, esperado: list[str]) -> None:
    assert set(esperado) <= set(encabezado_de_plantilla(tipo))


@pytest.mark.parametrize("tipo", [t for t in TIPOS_DE_IMPORTACION if t != "PRECIOS"])
def test_la_plantilla_de_cada_tipo_se_importa_sin_errores_de_columnas(tipo: str) -> None:
    """Escenario "Descargar la plantilla": el encabezado exacto, sin filas de datos,
    pasa la validación de columnas y se rechaza solo por no tener filas."""
    encabezado = encabezado_de_plantilla(tipo)

    with pytest.raises(ArchivoSinFilasError):
        armar_planilla(tipo, _filas(encabezado))


# --- encabezado --------------------------------------------------------------


def test_el_orden_de_las_columnas_no_importa_y_las_filas_vacias_se_ignoran() -> None:
    """Escenario "Columnas en otro orden y filas vacías"."""
    crudas = _filas(
        ["email", "nombre", "cuit", "telefono", "contacto"],
        ["a@x.com", "Bodega Sur", "30712345678", "", ""],
        ["", "", "", "", ""],
        [],
        ["", "Cervecería Norte", "", "", ""],
    )

    planilla = armar_planilla("PROVEEDORES", crudas)

    assert [f.fila for f in planilla] == [2, 5]
    assert planilla[0].valores == {
        "nombre": "Bodega Sur",
        "cuit": "30712345678",
        "contacto": "",
        "telefono": "",
        "email": "a@x.com",
    }
    assert planilla[1].valores["nombre"] == "Cervecería Norte"


def test_el_encabezado_no_distingue_mayusculas_ni_espacios_al_borde() -> None:
    crudas = _filas([" Nombre ", "CUIT", "Contacto", "Telefono", "Email"], ["X"])

    planilla = armar_planilla("PROVEEDORES", crudas)

    assert planilla[0].valores["nombre"] == "X"


def test_una_columna_faltante_nombra_cual_es() -> None:
    """Escenario "Falta una columna obligatoria" (CAT-01, INV-01)."""
    encabezado = [c for c in encabezado_de_plantilla("PRODUCTOS") if c != "codigo"]

    with pytest.raises(ColumnasInvalidasError) as error:
        armar_planilla("PRODUCTOS", _filas(encabezado, ["x"] * len(encabezado)))

    assert error.value.codigo == "COLUMNAS_INVALIDAS"
    assert error.value.faltantes == ["codigo"]
    assert "codigo" in error.value.mensaje
    assert error.value.extension is not None
    assert error.value.extension["columnas_faltantes"] == ["codigo"]


def test_una_columna_opcional_ausente_no_rechaza_el_archivo_y_se_lee_vacia() -> None:
    planilla = armar_planilla("PROVEEDORES", _filas(["nombre"], ["Bodega Sur"]))

    assert planilla[0].valores == {
        "nombre": "Bodega Sur",
        "cuit": "",
        "contacto": "",
        "telefono": "",
        "email": "",
    }


def test_una_columna_desconocida_nombra_cual_es() -> None:
    """Escenario "Columna desconocida" (D11)."""
    encabezado = [*encabezado_de_plantilla("CLIENTES"), "observaciones"]

    with pytest.raises(ColumnasInvalidasError) as error:
        armar_planilla("CLIENTES", _filas(encabezado, ["x"] * len(encabezado)))

    assert error.value.desconocidas == ["observaciones"]
    assert "observaciones" in error.value.mensaje


def test_una_columna_de_organizacion_se_rechaza() -> None:
    """INV-21, TR-08: la organización sale del token, no del archivo."""
    with pytest.raises(ColumnasInvalidasError) as error:
        armar_planilla("PROVEEDORES", _filas(["nombre", "organizacion_id"], ["X", "abc"]))

    assert error.value.desconocidas == ["organizacion_id"]


def test_una_columna_repetida_nombra_cual_es_aunque_difiera_en_mayusculas() -> None:
    with pytest.raises(ColumnasInvalidasError) as error:
        armar_planilla("PROVEEDORES", _filas(["nombre", "cuit", "NOMBRE"], ["X", "", "Y"]))

    assert error.value.repetidas == ["nombre"]


def test_varios_problemas_de_columnas_se_informan_juntos() -> None:
    with pytest.raises(ColumnasInvalidasError) as error:
        armar_planilla("PROVEEDORES", _filas(["cuit", "cuit", "extra"], ["1", "2", "3"]))

    assert error.value.faltantes == ["nombre"]
    assert error.value.desconocidas == ["extra"]
    assert error.value.repetidas == ["cuit"]


def test_las_celdas_vacias_al_final_del_encabezado_se_ignoran() -> None:
    """Excel suele guardar `nombre;cuit;;;` cuando hubo columnas usadas y vaciadas."""
    planilla = armar_planilla("PROVEEDORES", _filas(["nombre", "cuit", "", ""], ["X", "1"]))

    assert planilla[0].valores["nombre"] == "X"


def test_una_celda_vacia_en_medio_del_encabezado_es_una_columna_desconocida() -> None:
    with pytest.raises(ColumnasInvalidasError) as error:
        armar_planilla("PROVEEDORES", _filas(["nombre", "", "cuit"], ["X", "", "1"]))

    assert error.value.desconocidas == [""]


# --- filas ---------------------------------------------------------------------


def test_el_numero_de_fila_es_el_de_la_planilla_aunque_haya_filas_vacias() -> None:
    """Escenario "Error en la tercera fila de datos": encabezado = fila 1; la
    tercera fila de datos es la 4. Con una fila vacía en el medio, la siguiente
    sigue contando."""
    crudas = _filas(
        ENCABEZADO_PROVEEDORES,
        ["A", "", "", "", ""],
        ["B", "", "", "", ""],
        ["C", "20-1234", "", "", ""],
    )
    assert [f.fila for f in armar_planilla("PROVEEDORES", crudas)] == [2, 3, 4]

    con_vacia = _filas(ENCABEZADO_PROVEEDORES, ["A"], [], ["B"])
    assert [f.fila for f in armar_planilla("PROVEEDORES", con_vacia)] == [2, 4]


def test_una_fila_mas_corta_que_el_encabezado_se_completa_con_vacios() -> None:
    planilla = armar_planilla("PROVEEDORES", _filas(ENCABEZADO_PROVEEDORES, ["A", "30712345678"]))

    assert planilla[0].valores["contacto"] == ""


def test_los_valores_se_recortan() -> None:
    planilla = armar_planilla("PROVEEDORES", _filas(ENCABEZADO_PROVEEDORES, ["  Bodega Sur  "]))

    assert planilla[0].valores["nombre"] == "Bodega Sur"


def test_una_fila_con_mas_celdas_que_el_encabezado_rechaza_el_archivo() -> None:
    """Datos fuera de columna no se pierden en silencio (D11)."""
    with pytest.raises(ArchivoInvalidoError) as error:
        armar_planilla(
            "PROVEEDORES", _filas(ENCABEZADO_PROVEEDORES, ["A", "", "", "", "", "sobrante"])
        )

    assert "2" in error.value.mensaje


def test_las_celdas_vacias_de_mas_al_final_de_una_fila_no_molestan() -> None:
    planilla = armar_planilla(
        "PROVEEDORES", _filas(ENCABEZADO_PROVEEDORES, ["A", "", "", "", "", "", ""])
    )

    assert len(planilla) == 1


# --- límites ---------------------------------------------------------------------


def test_un_archivo_sin_celdas_es_archivo_invalido() -> None:
    with pytest.raises(ArchivoInvalidoError):
        armar_planilla("PROVEEDORES", [])


def test_un_archivo_cuya_primera_fila_esta_vacia_es_archivo_invalido() -> None:
    with pytest.raises(ArchivoInvalidoError):
        armar_planilla("PROVEEDORES", [(2, ENCABEZADO_PROVEEDORES), (3, ["A"])])
    with pytest.raises(ArchivoInvalidoError):
        armar_planilla("PROVEEDORES", [(1, ["", ""]), (2, ["A"])])


def test_solo_el_encabezado_es_archivo_sin_filas() -> None:
    """Escenario "Archivo sin filas de datos"."""
    with pytest.raises(ArchivoSinFilasError) as error:
        armar_planilla("PROVEEDORES", _filas(ENCABEZADO_PROVEEDORES, [], ["", "", "", "", ""]))

    assert error.value.codigo == "ARCHIVO_SIN_FILAS"


def test_el_limite_de_filas_se_acepta_y_una_mas_se_rechaza() -> None:
    """Escenario "Archivo con demasiadas filas" (D11: 2.000 filas de datos)."""
    assert LIMITE_DE_FILAS == 2000
    filas = [[f"Proveedor {n}"] for n in range(LIMITE_DE_FILAS + 1)]

    en_el_limite = armar_planilla("PROVEEDORES", _filas(["nombre"], *filas[:LIMITE_DE_FILAS]))
    assert len(en_el_limite) == LIMITE_DE_FILAS

    with pytest.raises(ArchivoDemasiadoGrandeError) as error:
        armar_planilla("PROVEEDORES", _filas(["nombre"], *filas))
    assert error.value.codigo == "ARCHIVO_DEMASIADO_GRANDE"


def test_las_filas_vacias_no_cuentan_para_el_limite() -> None:
    filas = [["Proveedor"]] * LIMITE_DE_FILAS + [[""]] * 50

    planilla = armar_planilla("PROVEEDORES", _filas(["nombre"], *filas))

    assert len(planilla) == LIMITE_DE_FILAS


def test_la_fila_de_planilla_es_inmutable() -> None:
    fila = FilaPlanilla(fila=2, valores={"nombre": "A"})

    with pytest.raises(AttributeError):
        fila.fila = 3  # type: ignore[misc]


# --- filas que llegan en el contenido del comando ------------------------------------


def test_las_filas_del_comando_con_las_columnas_del_tipo_se_aceptan() -> None:
    """El handler vuelve a verificar las columnas del contenido: no confía en que el
    ensamblador del contenido (la API) lo haya hecho."""
    filas = [FilaPlanilla(2, dict.fromkeys(ENCABEZADO_PROVEEDORES, ""))]

    verificar_columnas_de_filas("PROVEEDORES", filas)  # no lanza


def test_las_filas_del_comando_con_una_columna_de_mas_o_de_menos_se_rechazan() -> None:
    sucia = FilaPlanilla(2, {**dict.fromkeys(ENCABEZADO_PROVEEDORES, ""), "organizacion_id": "x"})
    incompleta = FilaPlanilla(3, {"nombre": "A"})

    with pytest.raises(ColumnasInvalidasError) as error:
        verificar_columnas_de_filas("PROVEEDORES", [sucia, incompleta])

    assert error.value.desconocidas == ["organizacion_id"]
    assert error.value.faltantes == ["cuit", "contacto", "telefono", "email"]


def test_las_filas_del_comando_de_un_tipo_desconocido_se_rechazan() -> None:
    with pytest.raises(TipoImportacionInvalidoError):
        verificar_columnas_de_filas("PRECIOS", [FilaPlanilla(2, {})])


# --- plantilla descargable y nombre de archivo ---------------------------------------


@pytest.mark.parametrize("tipo", [t for t in TIPOS_DE_IMPORTACION if t != "PRECIOS"])
def test_la_plantilla_csv_es_el_encabezado_exacto_con_punto_y_coma_y_sin_filas(tipo: str) -> None:
    """Excel en español abre un CSV con `;` en columnas separadas (`design.md` D2)."""
    plantilla = plantilla_csv(tipo)

    assert plantilla == ";".join(encabezado_de_plantilla(tipo)) + "\r\n"
    assert plantilla.count("\n") == 1


def test_la_plantilla_de_precios_no_existe() -> None:
    with pytest.raises(TipoImportacionInvalidoError):
        plantilla_csv("PRECIOS")


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("proveedores.csv", "proveedores.csv"),
        (r"C:\fakepath\mis proveedores.csv", "mis proveedores.csv"),
        ("/tmp/../etc/pase.csv", "pase.csv"),
        ("  datos.xlsx  ", "datos.xlsx"),
        ("raro\x00\x1fnombre.csv", "raronombre.csv"),
        (None, "archivo"),
        ("", "archivo"),
        ("C:\\carpeta\\", "archivo"),
        ("a" * 400 + ".csv", ("a" * 400 + ".csv")[:255]),
    ],
)
def test_el_nombre_de_archivo_se_guarda_sin_ruta_ni_caracteres_de_control(
    crudo: str | None, esperado: str
) -> None:
    assert nombre_de_archivo(crudo) == esperado
