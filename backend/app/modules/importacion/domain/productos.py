"""Importación de productos con presentaciones: de las filas de la planilla a un producto
con sus presentaciones (`specs/importacion/importacion-de-maestros`, `design.md` D4, D5).

Puro. D5-A: una fila por presentación, agrupadas por `codigo`, con los datos del producto
repetidos en cada fila. Acá se agrupa, se detectan las contradicciones entre filas
(`PRODUCTO_INCONSISTENTE`), se convierte cada celda con exactitud (INV-03, INV-04) y se
arma el producto. Las reglas de negocio (CAT-01 a CAT-03: unidades >= 1, una única
referencia de venta, código único) las aplica el servicio de `catalogo`; acá solo se
decide en qué fila del informe aparece cada error.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.modules.importacion.domain.errores import ErrorDeValor
from app.modules.importacion.domain.informe import (
    ErrorDeFila,
    error_de_fila_duplicada,
    traducir_error,
)
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.referencias import clave_de_texto, porcentaje_a_fraccion
from app.modules.importacion.domain.valores import a_booleano, a_entero

TIPO = "PRODUCTOS"


@dataclass(frozen=True)
class PresentacionDeFila:
    """Una presentación tal como la describe su fila de la planilla."""

    fila: int
    nombre: str
    unidades_base: int
    usar_en_venta: bool
    usar_en_compra: bool
    es_referencia: bool


@dataclass(frozen=True)
class ProductoDeGrupo:
    """Un producto armado desde su grupo de filas. Las referencias (`categoria`,
    `marca`, `proveedor`) siguen siendo el texto de la planilla: las resuelve el
    importador contra los datos de la organización; `alicuota` es la fracción (0.21) y
    `alicuota_texto` el porcentaje tal como se escribió. `fila` es la primera del grupo."""

    fila: int
    codigo: str
    nombre: str
    categoria: str
    marca: str | None
    proveedor: str
    unidad_base: str
    alicuota: Decimal
    alicuota_texto: str
    presentaciones: tuple[PresentacionDeFila, ...]


def agrupar_por_codigo(filas: Sequence[FilaPlanilla]) -> list[list[FilaPlanilla]]:
    """Agrupa las filas de un mismo producto, en orden de primera aparición. El código
    se compara sin espacios al borde ni mayúsculas (un `va-750` en otra fila es el mismo
    producto, y `PRODUCTO_INCONSISTENTE` avisa que está escrito distinto). Una fila sin
    código no se agrupa con ninguna: el servicio la rechaza con `CODIGO_INVALIDO`."""
    grupos: dict[str, list[FilaPlanilla]] = {}
    for fila in filas:
        clave = clave_de_texto(fila.valores["codigo"]) or f"\0fila-{fila.fila}"
        grupos.setdefault(clave, []).append(fila)
    return list(grupos.values())


def _alicuota_comparable(texto: str) -> str:
    """`21` y `21,0` son la misma alícuota; un texto ilegible se compara tal cual (su
    error de número lo informa la lectura de la primera fila)."""
    try:
        return str(porcentaje_a_fraccion(texto, columna="alicuota").normalize())
    except ErrorDeValor:
        return clave_de_texto(texto)


# Columna -> forma comparable de su valor, en el orden en que se informa la primera
# diferencia.
_COMPARABLES = (
    ("codigo", lambda texto: texto.strip()),
    ("nombre", lambda texto: texto.strip()),
    ("categoria", clave_de_texto),
    ("marca", clave_de_texto),
    ("proveedor", clave_de_texto),
    ("unidad_base", clave_de_texto),
    ("alicuota", _alicuota_comparable),
)


def _inconsistencias(grupo: Sequence[FilaPlanilla]) -> list[ErrorDeFila]:
    primera = grupo[0]
    errores: list[ErrorDeFila] = []
    for fila in grupo[1:]:
        for columna, comparable in _COMPARABLES:
            if comparable(fila.valores[columna]) != comparable(primera.valores[columna]):
                errores.append(
                    ErrorDeFila(
                        fila=fila.fila,
                        columna=columna,
                        codigo="PRODUCTO_INCONSISTENTE",
                        mensaje=(
                            f"El dato {columna} difiere del de la fila {primera.fila}, "
                            "que ya describe este producto."
                        ),
                    )
                )
                break
    return errores


def _presentaciones_repetidas(grupo: Sequence[FilaPlanilla]) -> list[ErrorDeFila]:
    vistas: dict[str, int] = {}
    errores: list[ErrorDeFila] = []
    for fila in grupo:
        clave = clave_de_texto(fila.valores["presentacion"])
        if not clave:
            continue
        if clave in vistas:
            errores.append(
                error_de_fila_duplicada(
                    fila=fila.fila, columna="presentacion", fila_original=vistas[clave]
                )
            )
        else:
            vistas[clave] = fila.fila
    return errores


def _leer_presentacion(fila: FilaPlanilla) -> PresentacionDeFila:
    valores = fila.valores
    return PresentacionDeFila(
        fila=fila.fila,
        nombre=valores["presentacion"].strip(),
        unidades_base=a_entero(valores["unidades_base"], columna="unidades_base"),
        usar_en_venta=a_booleano(valores["usar_en_venta"], columna="usar_en_venta"),
        usar_en_compra=a_booleano(valores["usar_en_compra"], columna="usar_en_compra"),
        es_referencia=a_booleano(valores["es_referencia"], columna="es_referencia"),
    )


def analizar_grupo(
    grupo: Sequence[FilaPlanilla],
) -> tuple[ProductoDeGrupo | None, list[ErrorDeFila]]:
    """Arma el producto de un grupo de filas, o devuelve TODOS los errores de lectura
    del grupo (un error en cualquier presentación impide el alta del producto entero,
    y cada uno se informa en su fila). Nunca devuelve las dos cosas."""
    primera = grupo[0]
    errores: list[ErrorDeFila] = [*_inconsistencias(grupo), *_presentaciones_repetidas(grupo)]

    valores = primera.valores
    campos: dict[str, str] = {}
    alicuota: Decimal | None = None
    # Código, nombre y unidad base pasan tal cual al servicio de catálogo: sus reglas
    # (`CODIGO_INVALIDO`, `NOMBRE_INVALIDO`, `VALOR_OBLIGATORIO`) son las de la pantalla.
    campos["codigo"] = valores["codigo"].strip()
    campos["nombre"] = valores["nombre"].strip()
    campos["unidad_base"] = valores["unidad_base"].strip()
    try:
        alicuota = porcentaje_a_fraccion(valores["alicuota"], columna="alicuota")
    except ErrorDeValor as error:
        errores.append(traducir_error(TIPO, primera.fila, error))

    presentaciones: list[PresentacionDeFila] = []
    for fila in grupo:
        try:
            presentaciones.append(_leer_presentacion(fila))
        except ErrorDeValor as error:
            errores.append(traducir_error(TIPO, fila.fila, error))

    if errores or alicuota is None:
        return None, sorted(errores, key=lambda e: e.fila)
    return (
        ProductoDeGrupo(
            fila=primera.fila,
            codigo=campos["codigo"],
            nombre=campos["nombre"],
            categoria=valores["categoria"].strip(),
            marca=valores["marca"].strip() or None,
            proveedor=valores["proveedor"].strip(),
            unidad_base=campos["unidad_base"],
            alicuota=alicuota,
            alicuota_texto=valores["alicuota"].strip(),
            presentaciones=tuple(presentaciones),
        ),
        [],
    )


def columna_del_error(codigo: str, *, nombre_vacio: bool) -> str | None:
    """La columna de un error de texto vacío del servicio de catálogo que la tabla
    código -> columna no puede decidir: `NOMBRE_INVALIDO` es del nombre del producto o del
    de una presentación (`nombre_vacio` dice cuál); `VALOR_OBLIGATORIO` es de la unidad
    base. Cualquier otro código: `None` (lo decide la tabla)."""
    if codigo == "NOMBRE_INVALIDO":
        return "nombre" if nombre_vacio else "presentacion"
    if codigo == "VALOR_OBLIGATORIO":
        return "unidad_base"
    return None


def fila_del_error(
    codigo: str,
    presentaciones: Sequence[PresentacionDeFila],
    primera_fila: int,
    *,
    nombre_vacio: bool = False,
) -> int:
    """La fila del informe para un error que lanzó el servicio al crear el producto.

    El servicio valida el producto completo y no dice qué presentación falló; acá se
    ubica la culpable: `UNIDADES_INVALIDAS` en la primera con unidades menores a 1;
    `REFERENCIA_INVALIDA` en la referencia que no es de venta, o en la segunda
    referencia si hay dos, o en la primera fila del producto si no hay ninguna; todo lo
    demás en la primera fila del producto. `NOMBRE_INVALIDO` cae en la primera fila si el
    nombre del producto está vacío (`nombre_vacio`) y si no, en la primera presentación con
    el nombre vacío (el servicio valida el nombre del producto primero)."""
    if codigo == "NOMBRE_INVALIDO" and not nombre_vacio:
        for presentacion in presentaciones:
            if not presentacion.nombre.strip():
                return presentacion.fila
    elif codigo == "UNIDADES_INVALIDAS":
        for presentacion in presentaciones:
            if presentacion.unidades_base < 1:
                return presentacion.fila
    elif codigo == "REFERENCIA_INVALIDA":
        referencias = [p for p in presentaciones if p.es_referencia]
        if len(referencias) == 1:
            return referencias[0].fila
        if len(referencias) > 1:
            return referencias[1].fila
    return primera_fila
