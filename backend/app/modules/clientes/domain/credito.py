"""Los tres campos de crédito del cliente, guardados sin resolver (`design.md`
D6 y D8, CRE-01, CRE-03, CRE-06, CLI-03).

Nada en este módulo calcula disponible, exceso, política aplicada ni tolerancia
consumida: eso es del change 18b, en el módulo que confirma la venta (D8). Acá
solo se decide si lo que llega se puede guardar.

Tampoco se resuelve la herencia: un `None` se guarda como `None` y no se copia
el valor de la organización (CRE-03, CRE-06). La herencia se aplica en el
momento de evaluar, en el 18b.

Los importes llegan como `Decimal` exacto desde el esquema del comando (que es
donde la cadena `"150000.00"` del JSON se convierte); este módulo rechaza
`float` y `bool` explícitamente para que un punto flotante binario no pueda
colarse por un camino secundario (INV-03)."""

from __future__ import annotations

from decimal import Decimal

from app.core.money import redondear_importe
from app.modules.clientes.domain.errores import (
    ConsumidorFinalSinCreditoError,
    LimiteCreditoInvalidoError,
    PoliticaCreditoInvalidaError,
    ToleranciaOfflineInvalidaError,
)

# `03` §4. Catálogos cerrados, los mismos que los de la organización.
POLITICAS_CREDITO = frozenset({"ADVERTIR", "AUTORIZAR", "BLOQUEAR"})
TIPOS_TOLERANCIA = frozenset({"IMPORTE", "PORCENTAJE"})

# D6: `numeric(14,2)`, la misma precisión que
# `configuracion_organizacion.tolerancia_offline_valor`, para que heredar sea
# una lectura y no una conversión.
_DECIMALES = 2
_CERO = Decimal("0.00")


def _cantidad_de_decimales(valor: Decimal) -> int:
    _signo, _digitos, exponente = valor.as_tuple()
    assert isinstance(exponente, int)
    return max(0, -exponente)


def validar_limite_credito(limite: Decimal | None) -> Decimal | None:
    """Valida el límite de crédito (CRE-01, INV-03, D6).

    `None` significa SIN CONTROL DE CRÉDITO y es un valor legítimo, no un dato
    faltante: se guarda en nulo y así sigue siendo distinguible de un límite de
    cero (CRE-01). Un límite negativo se rechaza: el negativo no es "sin
    control", el nulo sí.

    Un límite con más de dos decimales se RECHAZA, no se redondea: la spec pide
    `LIMITE_CREDITO_INVALIDO` para `"100.005"`, y un redondeo en silencio
    convertiría un error del usuario en un dato distinto del que escribió
    (INV-03, `core/money.py`)."""
    if limite is None:
        return None

    if isinstance(limite, bool | float):
        raise LimiteCreditoInvalidoError(
            f"El límite de crédito no puede ser un punto flotante binario: {limite!r} "
            "(INV-03: se espera un Decimal exacto)."
        )

    if limite < 0:
        raise LimiteCreditoInvalidoError("El límite de crédito no puede ser negativo (CRE-01).")

    if _cantidad_de_decimales(limite) > _DECIMALES:
        raise LimiteCreditoInvalidoError(
            f"El límite de crédito no puede tener más de {_DECIMALES} decimales "
            f"(se reciba {limite}, no se redondea, se rechaza) (INV-03)."
        )

    return limite


def validar_politica_credito(politica: str | None) -> str | None:
    """Valida la política contra el catálogo `ADVERTIR`, `AUTORIZAR`, `BLOQUEAR`
    (CRE-03, `03` §4).

    `None` significa "hereda la de la organización", así que no se reemplaza por
    el valor por defecto acá: la herencia se resuelve cuando se evalúa el
    crédito (CRE-03)."""
    if politica is None:
        return None
    if politica not in POLITICAS_CREDITO:
        raise PoliticaCreditoInvalidaError(
            f"La política {politica!r} no está en el catálogo "
            f"({', '.join(sorted(POLITICAS_CREDITO))}) (CRE-03)."
        )
    return politica


def validar_tolerancia_offline(
    tipo: str | None, valor: Decimal | None
) -> tuple[str | None, Decimal | None]:
    """Valida el par de tolerancia offline y lo devuelve normalizado (CRE-06,
    D6).

    Tipo y valor van juntos: informar uno sin el otro se rechaza con
    `TOLERANCIA_OFFLINE_INVALIDA`, igual que en
    `configuracion_organizacion` y que en el `CHECK ck_cliente__tolerancia_
    pareja` de la base. Un tipo fuera del catálogo también se rechaza, y el
    valor además no puede ser negativo: una tolerancia negativa sería una
    exigencia de diferencia, no una tolerancia."""
    if tipo is None and valor is None:
        return None, None

    if tipo is None or valor is None:
        raise ToleranciaOfflineInvalidaError(
            "La tolerancia offline se informa en pareja: o van tipo y valor, o ninguno (CRE-06)."
        )

    assert tipo is not None
    assert valor is not None

    if tipo not in TIPOS_TOLERANCIA:
        raise ToleranciaOfflineInvalidaError(
            f"El tipo de tolerancia {tipo!r} no está en el catálogo "
            f"({', '.join(sorted(TIPOS_TOLERANCIA))}) (CRE-06)."
        )

    if isinstance(valor, bool | float):
        raise ToleranciaOfflineInvalidaError(
            f"El valor de la tolerancia no puede ser un punto flotante binario: {valor!r} "
            "(INV-03: se espera un Decimal exacto)."
        )

    if valor < 0:
        raise ToleranciaOfflineInvalidaError(
            "El valor de la tolerancia no puede ser negativo (CRE-06)."
        )

    if _cantidad_de_decimales(valor) > _DECIMALES:
        raise ToleranciaOfflineInvalidaError(
            f"El valor de la tolerancia no puede tener más de {_DECIMALES} decimales "
            f"(se recibe {valor}, no se redondea, se rechaza) (D6, INV-03)."
        )

    return tipo, valor


def validar_credito_de_consumidor_final(
    es_consumidor_final: bool,
    limite: Decimal | None,
    politica: str | None,
    tipo_tolerancia: str | None,
    valor_tolerancia: Decimal | None,
) -> None:
    """Rechaza darle crédito propio al consumidor final (CLI-03, CRE-01).

    Su límite es cero y fijo ("límite cero significa solo contado"), así que ni
    cambiarlo ni agregarle política o tolerancia propias tienen sentido: no
    crédito significa solo límite cero. La función no devuelve nada porque no
    hay ningún valor válido que normalizar: o no se manda nada, o se rechaza.

    Mandarlo todo en nulo NO es un error: es una escritura que no cambia nada y
    el límite del consumidor final ya es cero. Inventar un rechazo acá obligaría
    al handler a tratar distinto un reenvío del mismo crédito."""
    if not es_consumidor_final:
        return

    if (
        limite is not None
        or politica is not None
        or tipo_tolerancia is not None
        or valor_tolerancia is not None
    ):
        raise ConsumidorFinalSinCreditoError(
            "El cliente consumidor final solo puede tener límite cero, sin política ni "
            "tolerancia propias (CLI-03, CRE-01)."
        )


def limite_de_consumidor_final() -> Decimal:
    """El único límite que el consumidor final admite (CLI-03, CRE-01).

    Pasa por `redondear_importe` y no como literal suelto porque `CLAUDE.md` §4
    exige que todo importe cuantizado salga de `core/money.py`."""
    return redondear_importe(_CERO)
