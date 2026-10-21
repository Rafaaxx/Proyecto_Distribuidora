"""Motor de cálculo de la venta (VTA-04, INV-14; `design.md` D13 y D14, ADR-016, ADR-050).

Función pura que orquesta, por línea, el bruto de PRC-22 (`precios.domain.bruto_de_linea`) y
los descuentos de DSC-05 (`descuentos.domain.motor`), y aplica VTA-04 en modo impositivo `A`:
el IVA de cada línea es cero y

    neto de línea = bruto - descuentos
    total_neto    = suma de netos
    total_iva     = suma de IVA (cero en modo A)
    total         = total_neto + total_iva                                     (INV-14)

Los modos `B` y `C` son de la etapa 4 y se rechazan con `ModoImpositivoNoSoportadoError`. Cada
línea conserva la alícuota del producto con que se calculó (se congela para la facturación,
FAC-08). Un solo redondeo por línea, el del bruto (TR-03); ningún otro paso redondea.

Las dos únicas dependencias de otros módulos son las funciones puras de `precios.domain` y
`descuentos.domain`, declaradas como `ignore_imports` de import-linter (ADR-054, D14).

Gemela en TypeScript: `frontend/src/domain/calculo.ts` (mismos casos de
`shared/fixtures/calculo/vta-04-totales.json`, `"motor": "vta04"`)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.core.money import EntradaNoEsDineroExactoError
from app.modules.descuentos.domain.motor import calcular_descuentos
from app.modules.descuentos.domain.tipos import (
    DescuentoAplicado,
    LineaVenta,
    ReglaDescuento,
)
from app.modules.precios.domain.bruto_de_linea import calcular_bruto_de_linea
from app.modules.ventas.domain.errores import (
    ModoImpositivoNoSoportadoError,
    VentaSinLineasError,
)

MODO_IMPOSITIVO_A = "A"
_CERO = Decimal("0.00")


@dataclass(frozen=True)
class LineaCalculo:
    """Una línea de la venta tal como entra al motor: el precio y las unidades de referencia
    con que se calcula el bruto (PRC-22), la cantidad base, la alícuota del producto
    (fracción, `0.210000`) y los datos que el motor de descuentos usa para los alcances."""

    id: str
    precio_referencia: Decimal
    unidades_referencia: int
    cantidad_base: int
    alicuota: Decimal
    producto_id: str
    categoria_id: str
    marca_id: str
    descuento_manual: Decimal | None


@dataclass(frozen=True)
class ResultadoLineaVenta:
    id: str
    bruto: Decimal
    descuentos: tuple[DescuentoAplicado, ...]
    descuento_total: Decimal
    neto: Decimal
    alicuota: Decimal
    importe_iva: Decimal


@dataclass(frozen=True)
class ResultadoVenta:
    modo_impositivo: str
    lineas: tuple[ResultadoLineaVenta, ...]
    total_neto: Decimal
    total_iva: Decimal
    total: Decimal


def _exigir_alicuota(linea: LineaCalculo) -> None:
    # `bool` y `float` no son `Decimal`: el rechazo cubre el punto flotante (INV-03).
    if not isinstance(linea.alicuota, Decimal):
        raise EntradaNoEsDineroExactoError(
            f"La alícuota de la línea {linea.id!r} debe ser un Decimal exacto, no "
            f"{type(linea.alicuota).__name__}: {linea.alicuota!r} "
            "(INV-03: nunca punto flotante)"
        )


def calcular_venta(
    modo_impositivo: str,
    lineas: Sequence[LineaCalculo],
    reglas: Sequence[ReglaDescuento],
    descuento_manual_general: Decimal | None = None,
) -> ResultadoVenta:
    """Calcula bruto, descuentos, neto, IVA y total de la venta (VTA-04, INV-14).

    Rechaza un modo distinto de `A` (D13) y una venta sin líneas antes de calcular nada; cualquier
    otra entrada inválida levanta el error de dominio de `precios` o `descuentos` que
    corresponde, sin devolver un resultado parcial."""
    if modo_impositivo != MODO_IMPOSITIVO_A:
        raise ModoImpositivoNoSoportadoError(
            f"El modo impositivo {modo_impositivo!r} no está soportado: solo se vende en modo "
            f"{MODO_IMPOSITIVO_A!r} (los modos B y C son de la etapa 4)."
        )
    if len(lineas) == 0:
        raise VentaSinLineasError("Una venta necesita al menos una línea.")

    for linea in lineas:
        _exigir_alicuota(linea)

    para_descuentos = [
        LineaVenta(
            id=linea.id,
            bruto=calcular_bruto_de_linea(
                linea.precio_referencia, linea.unidades_referencia, linea.cantidad_base
            ),
            cantidad_base=linea.cantidad_base,
            unidades_referencia=linea.unidades_referencia,
            producto_id=linea.producto_id,
            categoria_id=linea.categoria_id,
            marca_id=linea.marca_id,
            descuento_manual=linea.descuento_manual,
        )
        for linea in lineas
    ]
    descuentos = calcular_descuentos(para_descuentos, reglas, descuento_manual_general)

    resultado = tuple(
        ResultadoLineaVenta(
            id=entrada.id,
            bruto=entrada.bruto,
            descuentos=calculada.descuentos,
            descuento_total=calculada.descuento_total,
            neto=calculada.neto,
            alicuota=original.alicuota,
            importe_iva=_CERO,
        )
        for original, entrada, calculada in zip(
            lineas, para_descuentos, descuentos.lineas, strict=True
        )
    )
    total_neto = sum((linea.neto for linea in resultado), _CERO)
    total_iva = sum((linea.importe_iva for linea in resultado), _CERO)
    return ResultadoVenta(
        modo_impositivo=modo_impositivo,
        lineas=resultado,
        total_neto=total_neto,
        total_iva=total_iva,
        total=total_neto + total_iva,
    )
