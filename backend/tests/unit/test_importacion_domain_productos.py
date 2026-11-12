"""Tarea 5.1 (change 10): dominio puro de la importación de productos con presentaciones
(`specs/importacion/importacion-de-maestros`, `design.md` D4, D5).

Agrupación por `codigo` (una fila por presentación, D5), `PRODUCTO_INCONSISTENTE`, armado
de presentaciones con conversión exacta (INV-03, INV-04) y resolución de referencias por
clave natural (D4: `REFERENCIA_NO_ENCONTRADA`, `REFERENCIA_AMBIGUA`).

Reglas citadas: CAT-01, CAT-02, CAT-03, INV-04, TR-02, INV-21.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.modules.importacion.domain.errores import (
    ReferenciaAmbiguaError,
    ReferenciaNoEncontradaError,
    ValorObligatorioError,
)
from app.modules.importacion.domain.informe import traducir_error
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.productos import (
    PresentacionDeFila,
    agrupar_por_codigo,
    analizar_grupo,
    columna_del_error,
    fila_del_error,
)
from app.modules.importacion.domain.referencias import (
    porcentaje_a_fraccion,
    resolver_unica,
)


def fila(numero: int, **cambios: str) -> FilaPlanilla:
    valores = {
        "codigo": "VA-750",
        "nombre": "Vino A",
        "categoria": "Vinos",
        "marca": "",
        "proveedor": "Bodega Sur",
        "unidad_base": "botella",
        "alicuota": "21",
        "presentacion": "Caja x6",
        "unidades_base": "6",
        "usar_en_venta": "S",
        "usar_en_compra": "S",
        "es_referencia": "S",
    }
    valores.update(cambios)
    return FilaPlanilla(fila=numero, valores=valores)


def botella(numero: int, **cambios: str) -> FilaPlanilla:
    base = {
        "presentacion": "Botella",
        "unidades_base": "1",
        "usar_en_compra": "N",
        "es_referencia": "N",
    }
    base.update(cambios)
    return fila(numero, **base)


# --- agrupación por código (D5) ----------------------------------------------------


def test_agrupa_las_filas_de_un_mismo_codigo_en_orden_de_aparicion() -> None:
    filas = [fila(2), fila(3, codigo="CB-473"), botella(4)]

    grupos = agrupar_por_codigo(filas)

    assert [[f.fila for f in grupo] for grupo in grupos] == [[2, 4], [3]]


def test_agrupa_sin_distinguir_mayusculas_ni_espacios_al_borde() -> None:
    filas = [fila(2), botella(3, codigo=" va-750 ")]

    grupos = agrupar_por_codigo(filas)

    assert [[f.fila for f in grupo] for grupo in grupos] == [[2, 3]]


def test_las_filas_sin_codigo_no_se_agrupan_entre_si() -> None:
    filas = [fila(2, codigo=""), fila(3, codigo="")]

    grupos = agrupar_por_codigo(filas)

    assert [[f.fila for f in grupo] for grupo in grupos] == [[2], [3]]


# --- armado de un producto con sus presentaciones ----------------------------------


def test_vino_a_con_caja_y_botella_arma_el_producto_con_dos_presentaciones() -> None:
    """Escenario "Vino con caja y botella" (CAT-02, CAT-03)."""
    producto, errores = analizar_grupo([fila(2), botella(3, usar_en_venta="S")])

    assert errores == []
    assert producto is not None
    assert (producto.codigo, producto.nombre, producto.unidad_base) == (
        "VA-750",
        "Vino A",
        "botella",
    )
    assert (producto.categoria, producto.marca, producto.proveedor) == (
        "Vinos",
        None,
        "Bodega Sur",
    )
    assert producto.fila == 2
    assert producto.presentaciones == (
        PresentacionDeFila(2, "Caja x6", 6, True, True, True),
        PresentacionDeFila(3, "Botella", 1, True, False, False),
    )


def test_la_alicuota_en_porcentaje_pasa_a_fraccion_exacta() -> None:
    """TR-02: `21` es `0.21` y `10,5` es `0.105`, sin punto flotante."""
    veintiuno, _ = analizar_grupo([fila(2)])
    diez_y_medio, _ = analizar_grupo([fila(2, alicuota="10,5")])

    assert veintiuno is not None and diez_y_medio is not None
    assert veintiuno.alicuota == Decimal("0.21")
    assert diez_y_medio.alicuota == Decimal("0.105")
    assert isinstance(diez_y_medio.alicuota, Decimal)


def test_la_marca_con_texto_se_conserva() -> None:
    producto, _ = analizar_grupo([fila(2, marca="Casa Vieja")])

    assert producto is not None
    assert producto.marca == "Casa Vieja"


def test_unidades_cero_pasan_al_servicio_que_da_unidades_invalidas() -> None:
    """La regla CAT-02 es del servicio: acá solo se convierte el entero (INV-04)."""
    producto, errores = analizar_grupo([fila(2, unidades_base="0")])

    assert errores == []
    assert producto is not None
    assert producto.presentaciones[0].unidades_base == 0


@pytest.mark.parametrize(
    ("cambios", "columna", "codigo"),
    [
        ({"unidades_base": "1,5"}, "unidades_base", "CANTIDAD_INVALIDA"),
        ({"unidades_base": "seis"}, "unidades_base", "CANTIDAD_INVALIDA"),
        ({"es_referencia": "quizás"}, "es_referencia", "VALOR_INVALIDO"),
        ({"usar_en_venta": ""}, "usar_en_venta", "VALOR_INVALIDO"),
        ({"alicuota": "21.5"}, "alicuota", "NUMERO_INVALIDO"),
    ],
)
def test_una_celda_ilegible_da_error_de_fila_y_columna_y_no_arma_el_producto(
    cambios: dict[str, str], columna: str, codigo: str
) -> None:
    producto, errores = analizar_grupo([fila(2, **cambios)])

    assert producto is None
    assert [(e.fila, e.columna, e.codigo) for e in errores] == [(2, columna, codigo)]


@pytest.mark.parametrize("columna", ["nombre", "unidad_base", "presentacion"])
def test_los_textos_vacios_pasan_al_servicio_que_los_rechaza_con_la_regla_de_catalogo(
    columna: str,
) -> None:
    """Tarea 12.1: nombre, unidad base y nombre de presentación son reglas del catálogo
    (`NOMBRE_INVALIDO`, `VALOR_OBLIGATORIO`), iguales para la pantalla y la importación: la
    planilla no las repite."""
    producto, errores = analizar_grupo([fila(2, **{columna: "  "})])

    assert errores == []
    assert producto is not None
    assert {
        "nombre": producto.nombre,
        "unidad_base": producto.unidad_base,
        "presentacion": producto.presentaciones[0].nombre,
    }[columna] == ""


def test_los_errores_de_varias_filas_del_mismo_producto_se_acumulan() -> None:
    producto, errores = analizar_grupo(
        [fila(2, unidades_base="x"), botella(3, es_referencia="tal vez")]
    )

    assert producto is None
    assert [(e.fila, e.columna, e.codigo) for e in errores] == [
        (2, "unidades_base", "CANTIDAD_INVALIDA"),
        (3, "es_referencia", "VALOR_INVALIDO"),
    ]


# --- PRODUCTO_INCONSISTENTE (D5) ---------------------------------------------------


def test_categoria_distinta_en_la_segunda_fila_da_producto_inconsistente_en_esa_fila() -> None:
    """Escenario "Datos de producto contradictorios entre filas"."""
    producto, errores = analizar_grupo([fila(2), botella(3, categoria="Espumantes")])

    assert producto is None
    assert [(e.fila, e.columna, e.codigo) for e in errores] == [
        (3, "categoria", "PRODUCTO_INCONSISTENTE")
    ]
    assert "fila 2" in errores[0].mensaje


@pytest.mark.parametrize(
    ("cambios", "columna"),
    [
        ({"nombre": "Vino B"}, "nombre"),
        ({"proveedor": "Otra Bodega"}, "proveedor"),
        ({"unidad_base": "litro"}, "unidad_base"),
        ({"alicuota": "10,5"}, "alicuota"),
        ({"marca": "Casa Vieja"}, "marca"),
        ({"codigo": "va-750"}, "codigo"),
    ],
)
def test_cualquier_dato_de_producto_distinto_es_inconsistente(
    cambios: dict[str, str], columna: str
) -> None:
    _, errores = analizar_grupo([fila(2), botella(3, **cambios)])

    assert [(e.fila, e.columna, e.codigo) for e in errores] == [
        (3, columna, "PRODUCTO_INCONSISTENTE")
    ]


def test_el_mismo_dato_escrito_distinto_no_es_inconsistente() -> None:
    """Categoría sin distinguir mayúsculas, alícuota `21` y `21,0` son lo mismo."""
    producto, errores = analizar_grupo(
        [fila(2), botella(3, categoria=" vinos ", alicuota="21,0", proveedor="BODEGA SUR")]
    )

    assert errores == []
    assert producto is not None


def test_una_presentacion_repetida_dentro_del_producto_da_fila_duplicada() -> None:
    _, errores = analizar_grupo([fila(2), fila(3, presentacion=" caja X6 ", es_referencia="N")])

    assert [(e.fila, e.columna, e.codigo) for e in errores] == [
        (3, "presentacion", "FILA_DUPLICADA")
    ]
    assert "fila 2" in errores[0].mensaje


# --- fila que informa un error del servicio ----------------------------------------


def _presentaciones() -> list[PresentacionDeFila]:
    return [
        PresentacionDeFila(2, "Caja x6", 6, True, True, True),
        PresentacionDeFila(3, "Botella", 1, True, False, False),
    ]


def test_unidades_invalidas_se_informan_en_la_fila_de_la_presentacion_culpable() -> None:
    presentaciones = [
        PresentacionDeFila(2, "Caja x6", 6, True, True, True),
        PresentacionDeFila(3, "Botella", 0, True, False, False),
    ]

    assert fila_del_error("UNIDADES_INVALIDAS", presentaciones, 2) == 3
    assert fila_del_error("UNIDADES_INVALIDAS", _presentaciones()[:1], 2) == 2


def test_sin_referencia_se_informa_en_la_primera_fila_del_producto() -> None:
    """Escenario "Producto sin referencia" (CAT-03)."""
    sin_referencia = [
        PresentacionDeFila(5, "Caja", 12, True, True, False),
        PresentacionDeFila(6, "Lata", 1, True, False, False),
    ]

    assert fila_del_error("REFERENCIA_INVALIDA", sin_referencia, 5) == 5


def test_referencia_que_no_es_de_venta_se_informa_en_su_propia_fila() -> None:
    """Escenario "Referencia que no es de venta" (CAT-03)."""
    presentaciones = [
        PresentacionDeFila(2, "Caja x6", 6, True, True, False),
        PresentacionDeFila(3, "Botella", 1, False, False, True),
    ]

    assert fila_del_error("REFERENCIA_INVALIDA", presentaciones, 2) == 3


def test_dos_referencias_se_informan_en_la_segunda() -> None:
    presentaciones = [
        PresentacionDeFila(2, "Caja x6", 6, True, True, True),
        PresentacionDeFila(3, "Botella", 1, True, False, True),
    ]

    assert fila_del_error("REFERENCIA_INVALIDA", presentaciones, 2) == 3


def test_otro_error_del_servicio_se_informa_en_la_primera_fila() -> None:
    assert fila_del_error("CODIGO_DUPLICADO", _presentaciones(), 2) == 2


def test_nombre_invalido_cae_en_el_producto_o_en_la_presentacion_segun_cual_este_vacio() -> None:
    """Tarea 12.1: el servicio no dice cuál de los dos nombres falló."""
    presentaciones = [
        PresentacionDeFila(2, "Caja x6", 6, True, True, True),
        PresentacionDeFila(3, "", 1, True, False, False),
        PresentacionDeFila(4, " ", 1, True, False, False),
    ]

    assert fila_del_error("NOMBRE_INVALIDO", presentaciones, 2, nombre_vacio=True) == 2
    assert fila_del_error("NOMBRE_INVALIDO", presentaciones, 2, nombre_vacio=False) == 3
    assert fila_del_error("VALOR_OBLIGATORIO", presentaciones, 2) == 2


def test_columna_del_error_de_texto_vacio() -> None:
    assert columna_del_error("NOMBRE_INVALIDO", nombre_vacio=True) == "nombre"
    assert columna_del_error("NOMBRE_INVALIDO", nombre_vacio=False) == "presentacion"
    assert columna_del_error("VALOR_OBLIGATORIO", nombre_vacio=False) == "unidad_base"
    assert columna_del_error("CODIGO_DUPLICADO", nombre_vacio=False) is None
    assert fila_del_error("CATEGORIA_INACTIVA", _presentaciones(), 2) == 2


# --- resolución de referencias por clave natural (D4) ------------------------------


def test_una_unica_coincidencia_se_devuelve() -> None:
    elegido = resolver_unica(["Vinos"], columna="categoria", valor=" vinos ", que="categoría")

    assert elegido == "Vinos"


def test_ninguna_coincidencia_es_referencia_no_encontrada_en_la_columna() -> None:
    """Escenarios "Categoría inexistente" y "Proveedor de otra organización" (INV-21):
    el mensaje no revela si existe en otra organización."""
    with pytest.raises(ReferenciaNoEncontradaError) as excinfo:
        resolver_unica([], columna="categoria", valor="Vinoss", que="categoría")

    assert excinfo.value.codigo == "REFERENCIA_NO_ENCONTRADA"
    assert excinfo.value.columna == "categoria"
    assert "Vinoss" in excinfo.value.mensaje
    assert "otra organización" not in excinfo.value.mensaje


def test_valor_vacio_es_referencia_no_encontrada() -> None:
    with pytest.raises(ReferenciaNoEncontradaError):
        resolver_unica(["Vinos"], columna="categoria", valor="  ", que="categoría")


def test_mas_de_una_coincidencia_es_referencia_ambigua() -> None:
    with pytest.raises(ReferenciaAmbiguaError) as excinfo:
        resolver_unica(["Vinos", "vinos"], columna="proveedor", valor="vinos", que="proveedor")

    assert excinfo.value.codigo == "REFERENCIA_AMBIGUA"
    assert excinfo.value.columna == "proveedor"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("21", Decimal("0.21")),
        ("10,5", Decimal("0.105")),
        ("0", Decimal("0")),
        ("2,5", Decimal("0.025")),
    ],
)
def test_porcentaje_a_fraccion_es_exacto(texto: str, esperado: Decimal) -> None:
    """Escenario "Alícuota por porcentaje" (`01` §4)."""
    assert porcentaje_a_fraccion(texto, columna="alicuota") == esperado


def test_porcentaje_con_punto_se_rechaza() -> None:
    with pytest.raises(DomainError) as excinfo:
        porcentaje_a_fraccion("10.5", columna="alicuota")

    assert excinfo.value.codigo == "NUMERO_INVALIDO"


def test_valor_obligatorio_lleva_su_columna() -> None:
    error = ValorObligatorioError("falta", columna="nombre")

    assert (error.codigo, error.columna) == ("VALOR_OBLIGATORIO", "nombre")


# --- traducción de errores del servicio de catálogo --------------------------------


@pytest.mark.parametrize(
    ("codigo_error", "columna"),
    [
        ("CODIGO_DUPLICADO", "codigo"),
        ("CODIGO_INVALIDO", "codigo"),
        ("UNIDADES_INVALIDAS", "unidades_base"),
        ("CATEGORIA_INACTIVA", "categoria"),
        ("MARCA_INACTIVA", "marca"),
        ("ALICUOTA_INACTIVA", "alicuota"),
        ("PROVEEDOR_INACTIVO", "proveedor"),
        ("REFERENCIA_INVALIDA", "es_referencia"),
    ],
)
def test_los_errores_del_catalogo_se_asocian_a_su_columna(codigo_error: str, columna: str) -> None:
    class ErrorDelServicio(DomainError):
        status_http = 422

    ErrorDelServicio.codigo = codigo_error

    error = traducir_error("PRODUCTOS", 4, ErrorDelServicio("mensaje"))

    assert (error.fila, error.columna, error.codigo) == (4, columna, codigo_error)
