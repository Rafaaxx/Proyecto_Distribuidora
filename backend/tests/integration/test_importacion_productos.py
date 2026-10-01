"""Tarea 5.2 (change 10): importación de productos con presentaciones por
`IMPORTACION_REGISTRAR`, contra PostgreSQL real
(`specs/importacion/importacion-de-maestros`, `design.md` D4, D5, D6).

Cada escenario de la spec se prueba por el bus real: el producto nace igual que por
`PRODUCTO_CREAR` (TR-10), las referencias se resuelven por nombre, porcentaje o código
dentro de la organización del token (INV-21), un producto mal armado no se crea y, como
siempre, una fila mala impide toda la importación (INV-01).

Reglas citadas: CAT-01, CAT-02, CAT-03, CAT-05, CAT-07, INV-01, INV-04, INV-21, TR-08, TR-10.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from importacion_utiles import (
    EntornoDeImportacion,
    contenido,
    errores_de,
    fila_de,
)
from sqlalchemy.orm import Session

from app.modules.configuracion import service as configuracion_service
from app.modules.importacion.domain.errores import ImportacionConErroresError
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

TIPO = "PRODUCTOS"


def fila(numero: int, **cambios: str) -> dict[str, object]:
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
    return fila_de(numero, valores)


def botella(numero: int, **cambios: str) -> dict[str, object]:
    base = {
        "presentacion": "Botella",
        "unidades_base": "1",
        "usar_en_compra": "N",
        "es_referencia": "N",
    }
    base.update(cambios)
    return fila(numero, **base)


@pytest.fixture
def entorno(db_session: Session) -> EntornoDeImportacion:
    entorno = EntornoDeImportacion(db_session)
    entorno.catalogo_base()
    return entorno


def importar(entorno: EntornoDeImportacion, *filas: dict[str, object]) -> Comando:
    return entorno.enviar(contenido(TIPO, list(filas), "productos.csv"))


def fallar(
    entorno: EntornoDeImportacion, *filas: dict[str, object]
) -> list[tuple[int, str | None, str]]:
    with pytest.raises(ImportacionConErroresError) as excinfo:
        importar(entorno, *filas)
    return errores_de(excinfo.value)


# --- escenario "Vino con caja y botella" -----------------------------------------


def test_vino_a_con_caja_y_botella_queda_con_dos_presentaciones_y_la_caja_de_referencia(
    entorno: EntornoDeImportacion,
) -> None:
    """CAT-02, CAT-03, CAT-07."""
    comando = importar(entorno, fila(2), botella(3, usar_en_venta="S"))

    assert comando.resultado is not None
    assert (comando.resultado["filas_total"], comando.resultado["filas_ok"]) == (2, 2)
    [producto] = entorno.productos()
    assert (producto.codigo, producto.nombre, producto.unidad_base, producto.activo) == (
        "VA-750",
        "Vino A",
        "botella",
        True,
    )
    assert producto.marca_id is None
    presentaciones = {p.nombre: p for p in entorno.presentaciones_de(producto.id)}
    assert set(presentaciones) == {"Caja x6", "Botella"}
    caja, unidad = presentaciones["Caja x6"], presentaciones["Botella"]
    assert (caja.unidades_base, caja.usar_en_venta, caja.usar_en_compra, caja.es_referencia) == (
        6,
        True,
        True,
        True,
    )
    assert (
        unidad.unidades_base,
        unidad.usar_en_venta,
        unidad.usar_en_compra,
        unidad.es_referencia,
    ) == (
        1,
        True,
        False,
        False,
    )
    [importacion] = entorno.importaciones()
    assert (importacion.tipo, importacion.filas_total, importacion.filas_ok) == (TIPO, 2, 2)


def test_dos_productos_en_el_mismo_archivo_se_crean_con_sus_propias_presentaciones(
    entorno: EntornoDeImportacion,
) -> None:
    comando = importar(
        entorno,
        fila(2),
        fila(
            3,
            codigo="CB-473",
            nombre="Cerveza B",
            categoria="cervezas",
            presentacion="Lata",
            unidades_base="1",
        ),
        botella(4),
    )

    assert comando.resultado is not None
    assert comando.resultado["filas_total"] == 3
    productos = {p.codigo: p for p in entorno.productos()}
    assert set(productos) == {"CB-473", "VA-750"}
    assert [p.nombre for p in entorno.presentaciones_de(productos["VA-750"].id)] == [
        "Botella",
        "Caja x6",
    ]
    assert [p.nombre for p in entorno.presentaciones_de(productos["CB-473"].id)] == ["Lata"]


def test_la_marca_se_resuelve_por_nombre(entorno: EntornoDeImportacion) -> None:
    marca_id = entorno.marca("Casa Vieja")

    importar(entorno, fila(2, marca=" casa vieja "))

    [producto] = entorno.productos()
    assert producto.marca_id == marca_id


def test_no_se_crean_categorias_ni_marcas_al_vuelo(entorno: EntornoDeImportacion) -> None:
    """D4-A: las referencias deben existir."""
    categorias_antes = len(entorno.categorias())

    errores = fallar(entorno, fila(2, categoria="Vinoss"), fila(3, codigo="X-1", marca="Nueva"))

    assert errores == [
        (2, "categoria", "REFERENCIA_NO_ENCONTRADA"),
        (3, "marca", "REFERENCIA_NO_ENCONTRADA"),
    ]
    assert len(entorno.categorias()) == categorias_antes
    assert entorno.marcas() == []
    assert entorno.productos() == []


# --- escenarios de referencias por clave natural (D4) -----------------------------


def test_la_alicuota_se_resuelve_por_porcentaje(entorno: EntornoDeImportacion) -> None:
    """Escenario "Alícuota por porcentaje" (`01` §4)."""
    entorno.alicuota("10.5")  # 10,5% -> 0.105
    entorno.alicuota("0")

    importar(
        entorno,
        fila(2, alicuota="10,5"),
        fila(3, codigo="AG-1", alicuota="0", presentacion="Pack", es_referencia="S"),
    )

    por_codigo = {p.codigo: p for p in entorno.productos()}
    alicuota_105 = configuracion_service.obtener_alicuota_por_id(
        entorno.org, por_codigo["VA-750"].alicuota_id, entorno.sesion
    )
    alicuota_0 = configuracion_service.obtener_alicuota_por_id(
        entorno.org, por_codigo["AG-1"].alicuota_id, entorno.sesion
    )
    assert alicuota_105 is not None and str(alicuota_105.valor) == "0.105000"
    assert alicuota_0 is not None and str(alicuota_0.valor) == "0.000000"


def test_alicuota_inexistente_es_referencia_no_encontrada(entorno: EntornoDeImportacion) -> None:
    errores = fallar(entorno, fila(2, alicuota="27"))

    assert errores == [(2, "alicuota", "REFERENCIA_NO_ENCONTRADA")]


def test_proveedor_de_otra_organizacion_es_no_encontrado_como_si_no_existiera(
    entorno: EntornoDeImportacion, db_session: Session
) -> None:
    """Escenario "Proveedor de otra organización" (INV-21, TR-08)."""
    ajena = EntornoDeImportacion(db_session)
    ajena.proveedor("Bodega Del Oeste")

    errores = fallar(entorno, fila(2, proveedor="Bodega Del Oeste"))

    assert errores == [(2, "proveedor", "REFERENCIA_NO_ENCONTRADA")]
    assert entorno.productos() == []


def test_categoria_de_otra_organizacion_tampoco_se_ve(
    entorno: EntornoDeImportacion, db_session: Session
) -> None:
    ajena = EntornoDeImportacion(db_session)
    ajena.categoria("Licores")

    errores = fallar(entorno, fila(2, categoria="Licores"))

    assert errores == [(2, "categoria", "REFERENCIA_NO_ENCONTRADA")]


def test_nombre_que_coincide_con_dos_registros_es_referencia_ambigua(
    entorno: EntornoDeImportacion,
) -> None:
    entorno.proveedor("BODEGA SUR")  # junto al "Bodega Sur" del catálogo base
    entorno.categoria("VINOS")

    errores = fallar(entorno, fila(2))

    assert errores == [
        (2, "categoria", "REFERENCIA_AMBIGUA"),
        (2, "proveedor", "REFERENCIA_AMBIGUA"),
    ]


@pytest.mark.parametrize(
    ("preparar", "cambios", "esperado"),
    [
        ("categoria", {"categoria": "Retirada"}, (2, "categoria", "CATEGORIA_INACTIVA")),
        ("marca", {"marca": "Vieja"}, (2, "marca", "MARCA_INACTIVA")),
        ("alicuota", {"alicuota": "5"}, (2, "alicuota", "ALICUOTA_INACTIVA")),
        ("proveedor", {"proveedor": "Cerrado"}, (2, "proveedor", "PROVEEDOR_INACTIVO")),
    ],
)
def test_una_referencia_inactiva_da_el_codigo_de_inactivo_de_la_regla_de_destino(
    entorno: EntornoDeImportacion,
    preparar: str,
    cambios: dict[str, str],
    esperado: tuple[int, str, str],
) -> None:
    """CAT-05: las referencias se encuentran aunque estén inactivas; el servicio las
    rechaza con su código."""
    if preparar == "categoria":
        entorno.categoria("Retirada", activa=False)
    elif preparar == "marca":
        entorno.marca("Vieja", activa=False)
    elif preparar == "alicuota":
        entorno.alicuota("5", activa=False)
    else:
        entorno.proveedor("Cerrado", activo=False)

    errores = fallar(entorno, fila(2, **cambios))

    assert errores == [esperado]
    assert entorno.productos() == []


# --- escenarios de presentaciones (CAT-02, CAT-03) ---------------------------------


def test_producto_sin_referencia_da_referencia_invalida_en_su_primera_fila(
    entorno: EntornoDeImportacion,
) -> None:
    """Escenario "Producto sin referencia" (CAT-03): la primera fila del producto."""
    errores = fallar(
        entorno,
        fila(2),  # otro producto, válido, en el mismo archivo
        fila(3, codigo="CB-473", es_referencia="N", presentacion="Caja"),
        fila(4, codigo="CB-473", es_referencia="N", presentacion="Lata", unidades_base="1"),
    )

    assert errores == [(3, "es_referencia", "REFERENCIA_INVALIDA")]
    assert entorno.productos() == []  # todo o nada, incluso el producto válido


def test_referencia_que_no_es_de_venta_da_referencia_invalida_en_su_fila(
    entorno: EntornoDeImportacion,
) -> None:
    """Escenario "Referencia que no es de venta" (CAT-03)."""
    errores = fallar(entorno, botella(2, es_referencia="S", usar_en_venta="N"))

    assert errores == [(2, "es_referencia", "REFERENCIA_INVALIDA")]


def test_dos_referencias_dan_referencia_invalida_en_la_segunda(
    entorno: EntornoDeImportacion,
) -> None:
    errores = fallar(entorno, fila(2), botella(3, es_referencia="S", usar_en_venta="S"))

    assert errores == [(3, "es_referencia", "REFERENCIA_INVALIDA")]


def test_unidades_cero_dan_unidades_invalidas_en_la_fila_de_la_presentacion(
    entorno: EntornoDeImportacion,
) -> None:
    """Escenario "Unidades inválidas" (CAT-02, INV-04)."""
    errores = fallar(entorno, fila(2), botella(3, unidades_base="0"))

    assert errores == [(3, "unidades_base", "UNIDADES_INVALIDAS")]
    assert entorno.productos() == []


@pytest.mark.parametrize(
    ("cambios", "esperado"),
    [
        ({"unidades_base": "1,5"}, (2, "unidades_base", "CANTIDAD_INVALIDA")),
        ({"es_referencia": "quizás"}, (2, "es_referencia", "VALOR_INVALIDO")),
        ({"nombre": ""}, (2, "nombre", "NOMBRE_INVALIDO")),
        ({"nombre": "   "}, (2, "nombre", "NOMBRE_INVALIDO")),
        ({"unidad_base": ""}, (2, "unidad_base", "VALOR_OBLIGATORIO")),
        ({"unidad_base": "  "}, (2, "unidad_base", "VALOR_OBLIGATORIO")),
        ({"presentacion": ""}, (2, "presentacion", "NOMBRE_INVALIDO")),
        ({"alicuota": "21.5"}, (2, "alicuota", "NUMERO_INVALIDO")),
        ({"codigo": ""}, (2, "codigo", "CODIGO_INVALIDO")),
    ],
)
def test_una_celda_ilegible_o_vacia_da_su_error_de_fila_y_columna(
    entorno: EntornoDeImportacion, cambios: dict[str, str], esperado: tuple[int, str, str]
) -> None:
    assert fallar(entorno, fila(2, **cambios)) == [esperado]


def test_nombre_de_presentacion_vacio_cae_en_la_fila_de_esa_presentacion(
    entorno: EntornoDeImportacion,
) -> None:
    """Tarea 12.1: la regla es del catálogo (la misma que la pantalla)."""
    errores = fallar(entorno, fila(2), botella(3, presentacion=" "))

    assert errores == [(3, "presentacion", "NOMBRE_INVALIDO")]
    assert entorno.productos() == []


def test_un_error_en_cualquier_presentacion_impide_el_alta_del_producto_entero(
    entorno: EntornoDeImportacion,
) -> None:
    errores = fallar(entorno, fila(2), botella(3, es_referencia="tal vez"))

    assert errores == [(3, "es_referencia", "VALOR_INVALIDO")]
    assert entorno.productos() == []


# --- escenarios de solo altas y duplicados (D6) ------------------------------------


def test_producto_ya_existente_da_codigo_duplicado_y_no_cambia(
    entorno: EntornoDeImportacion,
) -> None:
    """Escenario "Producto ya existente" (CAT-01, D6)."""
    importar(entorno, fila(2), botella(3, usar_en_venta="S"))
    [existente] = entorno.productos()

    errores = fallar(entorno, fila(2, nombre="Otro nombre", presentacion="Pack"))

    assert errores == [(2, "codigo", "CODIGO_DUPLICADO")]
    [igual] = entorno.productos()
    assert (igual.id, igual.nombre) == (existente.id, "Vino A")
    assert len(entorno.presentaciones_de(existente.id)) == 2


def test_el_mismo_codigo_en_otra_organizacion_no_es_duplicado(
    entorno: EntornoDeImportacion, db_session: Session
) -> None:
    ajena = EntornoDeImportacion(db_session)
    ajena.catalogo_base()
    importar(ajena, fila(2))

    importar(entorno, fila(2))

    assert [p.codigo for p in entorno.productos()] == ["VA-750"]
    assert [p.codigo for p in ajena.productos()] == ["VA-750"]


def test_datos_de_producto_contradictorios_dan_producto_inconsistente_en_la_segunda_fila(
    entorno: EntornoDeImportacion,
) -> None:
    """Escenario "Datos de producto contradictorios entre filas" (CAT-01, D5)."""
    entorno.categoria("Espumantes")

    errores = fallar(entorno, fila(2), botella(3, categoria="Espumantes"))

    assert errores == [(3, "categoria", "PRODUCTO_INCONSISTENTE")]
    assert entorno.productos() == []


def test_una_presentacion_repetida_dentro_del_producto_da_fila_duplicada(
    entorno: EntornoDeImportacion,
) -> None:
    errores = fallar(entorno, fila(2), fila(3, es_referencia="N"))

    assert errores == [(3, "presentacion", "FILA_DUPLICADA")]


# --- todo o nada y registro --------------------------------------------------------


def test_los_errores_de_varios_productos_se_informan_todos_y_ninguno_se_crea(
    entorno: EntornoDeImportacion,
) -> None:
    """INV-01: el informe completo, un solo rechazo."""
    errores = fallar(
        entorno,
        fila(2, categoria="Vinoss"),
        fila(3, codigo="OK-1"),
        fila(4, codigo="CB-473", unidades_base="0"),
    )

    assert errores == [
        (2, "categoria", "REFERENCIA_NO_ENCONTRADA"),
        (4, "unidades_base", "UNIDADES_INVALIDAS"),
    ]
    assert entorno.productos() == []
    assert entorno.importaciones() == []


def test_doble_envio_con_el_mismo_operation_id_no_duplica_productos(
    entorno: EntornoDeImportacion,
) -> None:
    """INV-06."""
    operation_id = uuid4()
    cuerpo = contenido(TIPO, [fila(2), botella(3, usar_en_venta="S")], "productos.csv")

    primero = entorno.enviar(cuerpo, operation_id=operation_id)
    segundo = entorno.enviar(cuerpo, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(entorno.productos()) == 1
    assert len(entorno.importaciones()) == 1
    assert entorno.auditorias(operation_id) == 1
