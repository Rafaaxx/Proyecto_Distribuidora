"""CST-02: costo base por unidad base a partir de lo informado por el
proveedor (`design.md` D11, tarea 6.3, **[ALTA: cálculo de costos]**).

Función pura compartida (mismo cálculo que
`frontend/src/domain/proveedores/costoBase.ts`, tarea 11.1, con los casos
comunes de `shared/fixtures/calculo/cst-02-costo-base.json`).

Fórmula (TR-03: sin redondeos intermedios, un único redondeo al final):

    costo_por_presentacion = valor * (1 - bonificacion) / (1 + alicuota si incluye_iva sino 1)
    costo_base = costo_por_presentacion / unidades

El cociente se calcula con `Decimal` de precisión ampliada (50 dígitos
significativos, misma verificación que la tarea 2.1) para que la única
cuantización sea la de `redondear_costo` (`ROUND_HALF_UP`, 6 decimales) al
final -- nunca antes.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from app.core.money import redondear_costo
from app.modules.proveedores.domain.errores import (
    BonificacionInvalidaError,
    ValorInvalidoError,
)

_PRECISION_INTERMEDIA = 50


def calcular_costo_base(
    *,
    valor: Decimal,
    incluye_iva: bool,
    alicuota: Decimal,
    bonificacion: Decimal,
    unidades: int,
) -> Decimal:
    """Calcula el costo base por unidad base de una presentación informada
    (CST-02).

    - `valor`: lo pagado por la presentación completa, `> 0` (`VALOR_INVALIDO`
      si no; TR-01).
    - `incluye_iva`: si `valor` ya incluye el IVA de `alicuota`.
    - `alicuota`: la alícuota de IVA del producto (fracción, `>= 0`).
    - `bonificacion`: fracción en `[0, 1)` (`BONIFICACION_INVALIDA` si no;
      TR-02).
    - `unidades`: unidades base de la presentación informada, entero `>= 1`
      (una presentación ya validada por `catalogo`, CAT-02/INV-04 -- acá es
      un invariante del llamador, no una entrada de usuario, así que se
      afirma con `ValueError` en vez de un `DomainError` con código propio).
    """
    if valor <= 0:
        raise ValorInvalidoError("El valor informado debe ser mayor a cero.")
    if bonificacion < 0 or bonificacion >= 1:
        raise BonificacionInvalidaError(
            "La bonificación debe estar entre 0 (inclusive) y 1 (exclusive)."
        )
    if unidades < 1:
        raise ValueError("Las unidades de la presentación deben ser un entero mayor o igual a 1.")

    with localcontext() as contexto:
        contexto.prec = _PRECISION_INTERMEDIA

        costo_por_presentacion = valor * (Decimal(1) - bonificacion)
        if incluye_iva:
            costo_por_presentacion = costo_por_presentacion / (Decimal(1) + alicuota)

        costo_sin_redondear = costo_por_presentacion / Decimal(unidades)

    return redondear_costo(costo_sin_redondear)
