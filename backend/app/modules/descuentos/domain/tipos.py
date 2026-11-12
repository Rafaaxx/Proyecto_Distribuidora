"""Tipos de entrada y salida del motor de descuentos (`design.md` D4, D11).

Todo es inmutable y sin dependencias de infraestructura. Los importes y los porcentajes son
`Decimal`; un punto flotante se rechaza al calcular (INV-03). Los identificadores son cadenas: el
de una regla es un UUIDv7 en su forma canónica, cuyo orden lexicográfico es el de creación
(`design.md` D7)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

TipoRegla = Literal["VOLUMEN_OPERACION", "VOLUMEN_ALCANCE"]
Medida = Literal["CAJAS_EQUIVALENTES", "UNIDADES_BASE", "IMPORTE_BRUTO"]
Operador = Literal["GTE", "GT"]
AccionTipo = Literal["PORCENTAJE", "IMPORTE_FIJO"]
TipoAlcance = Literal["PRODUCTO", "CATEGORIA", "MARCA"]
Origen = Literal["AUTOMATICO", "MANUAL"]

TIPOS_REGLA: frozenset[str] = frozenset({"VOLUMEN_OPERACION", "VOLUMEN_ALCANCE"})
MEDIDAS: frozenset[str] = frozenset({"CAJAS_EQUIVALENTES", "UNIDADES_BASE", "IMPORTE_BRUTO"})
OPERADORES: frozenset[str] = frozenset({"GTE", "GT"})
ACCIONES: frozenset[str] = frozenset({"PORCENTAJE", "IMPORTE_FIJO"})
TIPOS_ALCANCE: frozenset[str] = frozenset({"PRODUCTO", "CATEGORIA", "MARCA"})


@dataclass(frozen=True)
class LineaVenta:
    """Una línea de la venta tal como la ve el motor: el bruto ya calculado por PRC-22, la
    cantidad base, las unidades de referencia con que se calculó el bruto (D5), su producto,
    categoría y marca, y el porcentaje manual propio opcional (D11)."""

    id: str
    bruto: Decimal
    cantidad_base: int
    unidades_referencia: int
    producto_id: str
    categoria_id: str
    marca_id: str
    descuento_manual: Decimal | None


@dataclass(frozen=True)
class AlcanceRegla:
    tipo: TipoAlcance
    entidad_id: str


@dataclass(frozen=True)
class ReglaDescuento:
    """Una regla aplicable (activa y vigente). `accion_porcentaje` es una fracción
    (`0.050000`); `accion_importe`, un importe. Exactamente uno de los dos según `accion_tipo`."""

    id: str
    tipo: TipoRegla
    medida: Medida
    operador: Operador
    umbral: Decimal
    accion_tipo: AccionTipo
    accion_porcentaje: Decimal | None
    accion_importe: Decimal | None
    acumulable: bool
    prioridad: int
    alcances: tuple[AlcanceRegla, ...]


@dataclass(frozen=True)
class DescuentoAplicado:
    """Un descuento de una línea (DSC-08). `regla_id` es nulo en el manual; `porcentaje` es nulo
    en una regla de importe fijo."""

    origen: Origen
    regla_id: str | None
    porcentaje: Decimal | None
    importe: Decimal


@dataclass(frozen=True)
class LineaResultado:
    id: str
    descuentos: tuple[DescuentoAplicado, ...]
    descuento_total: Decimal
    neto: Decimal


@dataclass(frozen=True)
class ResultadoDescuentos:
    """Resultado por línea, en el orden de la venta, y el mayor porcentaje manual que quedó
    aplicado en alguna línea (nulo si ninguna lleva manual): lo que se compara contra el tope
    (DSC-06; D11, D12)."""

    lineas: tuple[LineaResultado, ...]
    porcentaje_manual_maximo: Decimal | None
