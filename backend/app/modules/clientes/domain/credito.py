"""Los tres campos de crédito del cliente (`design.md` D6 y D8 del change 08, CRE-01,
CRE-03, CRE-06, CLI-03) y el motor de evaluación de crédito de la venta (change 18b,
D5, D6, D8; CRE-01 a CRE-07, ADR-016, ADR-032).

Validar: `validar_*` decide si lo que llega se puede guardar. No resuelve la herencia: un
`None` se guarda como `None` y no se copia el valor de la organización (CRE-03, CRE-06).

Evaluar: `evaluar_credito` es una función pura (disponible, saldo resultante, exceso,
tolerancia y resolución por política y modo). Recibe límite, política y tolerancia YA
resueltos con la herencia (cliente, si no organización); resolverla es de `clientes/service.py`.
Su gemela en TypeScript es `frontend/src/domain/credito/evaluacion.ts`: las dos corren
`shared/fixtures/calculo/cre-01-credito.json` (`"motor": "cre01"`).

Los importes llegan como `Decimal` exacto desde el esquema del comando (que es
donde la cadena `"150000.00"` del JSON se convierte); este módulo rechaza
`float` y `bool` explícitamente para que un punto flotante binario no pueda
colarse por un camino secundario (INV-03)."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from app.core.money import EntradaNoEsDineroExactoError, redondear_importe
from app.modules.clientes.domain.errores import (
    AutorizacionCreditoRequeridaError,
    AutorizadorSinPermisoError,
    ConsumidorFinalSinCreditoError,
    CreditoExcedidoError,
    CreditoInconsistenteError,
    ExcesoCreditoSinAceptarError,
    LimiteCreditoInvalidoError,
    ModoDeCreditoInvalidoError,
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


# --- Evaluación de crédito de la venta (change 18b, D5, D6, D8) ---------------------------------

PERMISO_SUPERAR_CREDITO = "SUPERAR_CREDITO"
MODOS_EVALUACION = frozenset({"CON_CONEXION", "SIN_CONEXION"})

Resolucion = Literal[
    "SIN_EXCESO",
    "ADVERTENCIA_ACEPTADA",
    "PERMISO_PROPIO",
    "PIN_SUPERVISOR",
    "TOLERANCIA_OFFLINE",
]


@dataclass(frozen=True)
class Autorizador:
    """Otro usuario de la organización que autoriza (con PIN), con los permisos que tiene hoy."""

    usuario_id: str
    permisos: frozenset[str]


@dataclass(frozen=True)
class ResultadoCredito:
    """Lo que la venta congela (CRE-01 a CRE-03, D5): `disponible` es nulo sin límite; `tolerancia`
    es el importe ya resuelto (cero si no hay tolerancia o no hay límite); `autorizador_id` es
    nulo salvo en `PERMISO_PROPIO` (quien vende) y `PIN_SUPERVISOR` (el supervisor)."""

    disponible: Decimal | None
    saldo_resultante: Decimal
    exceso: Decimal
    tolerancia: Decimal
    resolucion: Resolucion
    autorizador_id: str | None


@dataclass(frozen=True)
class DatosDeCredito:
    """Los datos de crédito de un cliente con la herencia de la organización ya resuelta
    (CRE-01, CRE-03, CRE-06): `limite` nulo es sin control; `politica` es siempre una del
    catálogo; la tolerancia es el par heredado entero o nula."""

    limite: Decimal | None
    politica: str
    tolerancia_tipo: str | None
    tolerancia_valor: Decimal | None


def resolver_datos_de_credito(
    *,
    limite_cliente: Decimal | None,
    politica_cliente: str | None,
    tolerancia_tipo_cliente: str | None,
    tolerancia_valor_cliente: Decimal | None,
    politica_organizacion: str,
    tolerancia_tipo_organizacion: str | None,
    tolerancia_valor_organizacion: Decimal | None,
) -> DatosDeCredito:
    """Herencia de la organización (CRE-03, CRE-06; `clientes/datos-de-credito`): la política es
    la del cliente o, si no tiene, la de la organización; la tolerancia es el par del cliente o,
    si no tiene, el de la organización (el par se hereda entero, nunca mezclado); el límite no se
    hereda: nulo es sin control (CRE-01). Función pura: no valida los valores guardados, que ya
    pasaron por `validar_*` al guardarse."""
    tipo: str | None
    valor: Decimal | None
    if tolerancia_tipo_cliente is not None:
        tipo, valor = tolerancia_tipo_cliente, tolerancia_valor_cliente
    else:
        tipo, valor = tolerancia_tipo_organizacion, tolerancia_valor_organizacion
    return DatosDeCredito(
        limite=limite_cliente,
        politica=politica_cliente if politica_cliente is not None else politica_organizacion,
        tolerancia_tipo=tipo,
        tolerancia_valor=valor,
    )


def _exigir_decimal_exacto(valor: object, nombre: str) -> None:
    # `bool` y `float` no son dinero exacto (INV-03); `Decimal` es lo único que se acepta.
    if not isinstance(valor, Decimal):
        raise EntradaNoEsDineroExactoError(
            f"{nombre} debe ser un Decimal exacto, no {type(valor).__name__}: {valor!r} "
            "(INV-03: nunca punto flotante)"
        )


def _tolerancia_en_importe(
    limite: Decimal | None, tipo: str | None, valor: Decimal | None
) -> Decimal:
    """D8: `IMPORTE` es el valor; `PORCENTAJE` es el valor (con dos decimales, `2.50` = 2,50 %)
    sobre el límite, redondeado una vez, mitad hacia arriba (ADR-032, TR-03). Sin tolerancia en
    el cliente ni en la organización, o sin límite, es cero."""
    if tipo is None or valor is None or limite is None:
        return _CERO
    if tipo == "IMPORTE":
        return redondear_importe(valor)
    return redondear_importe(limite * valor / 100)


@dataclass(frozen=True)
class CalculoDeExceso:
    """Lo que dan los números de una venta sobre el límite, sin política ni resolución:
    `disponible` es nulo sin límite (CRE-01)."""

    disponible: Decimal | None
    saldo_resultante: Decimal
    exceso: Decimal


def calcular_exceso(
    *,
    limite: Decimal | None,
    saldo_actual: Decimal,
    total_venta: Decimal,
    cobranza: Decimal,
) -> CalculoDeExceso:
    """CRE-01, CRE-02, D5: disponible = límite - saldo; resultante = saldo + total - cobranza;
    exceso = `mín(máx(0, total - cobranza), máx(0, resultante - límite))`. Sin límite no hay
    control ni exceso. Es lo que usa la evaluación con conexión y lo que el servidor repite, sin
    política, sobre los números del dispositivo y sobre los reales al sincronizar (D7)."""
    _exigir_decimal_exacto(saldo_actual, "El saldo actual")
    _exigir_decimal_exacto(total_venta, "El total de la venta")
    _exigir_decimal_exacto(cobranza, "La cobranza")
    if limite is not None:
        _exigir_decimal_exacto(limite, "El límite de crédito")
    saldo_resultante = redondear_importe(saldo_actual + total_venta - cobranza)
    disponible = None if limite is None else redondear_importe(limite - saldo_actual)
    if limite is None:
        return CalculoDeExceso(disponible, saldo_resultante, _CERO)
    no_cobrado = max(_CERO, total_venta - cobranza)
    sobre_el_limite = max(_CERO, saldo_resultante - limite)
    return CalculoDeExceso(
        disponible, saldo_resultante, redondear_importe(min(no_cobrado, sobre_el_limite))
    )


def evaluar_credito(
    *,
    limite: Decimal | None,
    saldo_actual: Decimal,
    total_venta: Decimal,
    cobranza: Decimal,
    politica: str | None,
    tolerancia_tipo: str | None,
    tolerancia_valor: Decimal | None,
    modo: str,
    acepta_exceso: bool,
    usuario_id: str,
    permisos_usuario: Collection[str],
    autorizador: Autorizador | None,
) -> ResultadoCredito:
    """Evalúa el crédito de una venta (CRE-01 a CRE-07, D5, D6, D8).

    - Disponible = límite - saldo (CRE-01); saldo resultante = saldo + total - cobranza (CRE-02).
    - Exceso (D5) = `mín(máx(0, total - cobranza), máx(0, resultante - límite))`: lo que la venta
      agrega por encima del límite. Una venta cobrada entera nunca tiene exceso, aunque el cliente
      ya esté excedido (CRE-07). Límite nulo: sin control, sin exceso.
    - Sin exceso -> `SIN_EXCESO`. Con exceso, por política (D6):
      * ADVERTIR: con `acepta_exceso` -> `ADVERTENCIA_ACEPTADA`; si no,
        `EXCESO_CREDITO_SIN_ACEPTAR`.
      * BLOQUEAR: `CREDITO_EXCEDIDO`, sin excepción de permiso.
      * AUTORIZAR: sin conexión y `exceso <= tolerancia` -> `TOLERANCIA_OFFLINE` (D8); si no,
        el propio usuario con `SUPERAR_CREDITO` -> `PERMISO_PROPIO` (se resuelve primero aunque se
        indique autorizador); si no, un autorizador con `SUPERAR_CREDITO` -> `PIN_SUPERVISOR`
        (`AUTORIZADOR_SIN_PERMISO` si no lo tiene); sin nada, con conexión
        `AUTORIZACION_CREDITO_REQUERIDA` y sin conexión `CREDITO_EXCEDIDO` (se comporta como
        BLOQUEAR). La tolerancia no rige con conexión.

    No verifica ningún PIN: que `autorizador` llegue acá significa que su PIN ya se verificó."""
    _exigir_decimal_exacto(saldo_actual, "El saldo actual")
    _exigir_decimal_exacto(total_venta, "El total de la venta")
    _exigir_decimal_exacto(cobranza, "La cobranza")
    if limite is not None:
        _exigir_decimal_exacto(limite, "El límite de crédito")
    if tolerancia_valor is not None:
        _exigir_decimal_exacto(tolerancia_valor, "El valor de la tolerancia")

    validar_limite_credito(limite)
    politica_valida = validar_politica_credito(politica)
    if politica_valida is None:
        raise PoliticaCreditoInvalidaError(
            "La evaluación necesita la política ya resuelta (cliente u organización) (CRE-03)."
        )
    tipo, valor = validar_tolerancia_offline(tolerancia_tipo, tolerancia_valor)
    if modo not in MODOS_EVALUACION:
        raise ModoDeCreditoInvalidoError(
            f"El modo {modo!r} no está en el catálogo ({', '.join(sorted(MODOS_EVALUACION))})."
        )

    calculo = calcular_exceso(
        limite=limite, saldo_actual=saldo_actual, total_venta=total_venta, cobranza=cobranza
    )
    disponible, saldo_resultante, exceso = (
        calculo.disponible,
        calculo.saldo_resultante,
        calculo.exceso,
    )
    tolerancia = _tolerancia_en_importe(limite, tipo, valor)

    def resultado(resolucion: Resolucion, autorizador_id: str | None = None) -> ResultadoCredito:
        return ResultadoCredito(
            disponible, saldo_resultante, exceso, tolerancia, resolucion, autorizador_id
        )

    if exceso == _CERO:
        return resultado("SIN_EXCESO")

    # Todo rechazo trae la evaluación para que la pantalla la muestre (D6). Aquí `limite` y
    # `disponible` no son nulos: sin límite no hay exceso.
    assert limite is not None
    evaluacion: dict[str, Any] = {
        "limite": str(redondear_importe(limite)),
        "saldo_considerado": str(redondear_importe(saldo_actual)),
        "disponible": str(disponible),
        "exceso": str(exceso),
        "politica": politica_valida,
    }

    if politica_valida == "ADVERTIR":
        if not acepta_exceso:
            raise ExcesoCreditoSinAceptarError(
                f"La venta deja un exceso de {exceso} sobre el límite y no se aceptó (CRE-04).",
                extension=evaluacion,
            )
        return resultado("ADVERTENCIA_ACEPTADA")

    if politica_valida == "BLOQUEAR":
        raise CreditoExcedidoError(
            f"La venta deja un exceso de {exceso} sobre el límite y la política bloquea (CRE-07).",
            extension=evaluacion,
        )

    # AUTORIZAR
    con_conexion = modo == "CON_CONEXION"
    if not con_conexion and exceso <= tolerancia:
        return resultado("TOLERANCIA_OFFLINE")
    if PERMISO_SUPERAR_CREDITO in permisos_usuario:
        return resultado("PERMISO_PROPIO", usuario_id)
    if autorizador is not None:
        if PERMISO_SUPERAR_CREDITO not in autorizador.permisos:
            raise AutorizadorSinPermisoError(
                f"El autorizador no tiene el permiso {PERMISO_SUPERAR_CREDITO} (CRE-05).",
                extension=evaluacion,
            )
        return resultado("PIN_SUPERVISOR", autorizador.usuario_id)
    if con_conexion:
        raise AutorizacionCreditoRequeridaError(
            f"El exceso de {exceso} necesita permiso propio o un supervisor con PIN (CRE-05).",
            extension=evaluacion,
        )
    raise CreditoExcedidoError(
        f"El exceso de {exceso} supera la tolerancia de {tolerancia} y no hay permiso propio "
        "ni PIN: se comporta como BLOQUEAR (CRE-06).",
        extension=evaluacion,
    )


# --- Evaluación del dispositivo en el servidor (change 18b, D7, tarea 10.1) ----------------------

RESOLUCIONES = frozenset(
    {"SIN_EXCESO", "ADVERTENCIA_ACEPTADA", "PERMISO_PROPIO", "PIN_SUPERVISOR", "TOLERANCIA_OFFLINE"}
)
_RESOLUCIONES_CON_AUTORIZADOR = frozenset({"PERMISO_PROPIO", "PIN_SUPERVISOR"})


def verificar_forma_del_credito_del_dispositivo(
    *,
    limite: Decimal | None,
    saldo_considerado: Decimal | None,
    politica: str | None,
    resolucion: str | None,
    autorizador_id: UUID | None,
) -> None:
    """D7 punto 1, paso 0 de D18: la forma de la evaluación que trae una venta sin conexión.
    Es obligatoria (decisión del usuario, 2026-10-23: la app no tiene versiones viejas): saldo
    considerado, política y resolución del catálogo; límite nulo (sin control) solo con
    `SIN_EXCESO` (`ck_venta__credito_sin_control`); `PIN_SUPERVISOR` y `PERMISO_PROPIO` con
    autorizador (`ck_venta__credito_autorizador`). Cualquier falla es `CREDITO_INCONSISTENTE`
    (SYN-06); no mira la política vigente ni el saldo real (SYN-05)."""
    if saldo_considerado is None:
        raise CreditoInconsistenteError("La evaluación de crédito no trae el saldo considerado.")
    if politica is None or politica not in POLITICAS_CREDITO:
        raise CreditoInconsistenteError("La evaluación de crédito no trae una política válida.")
    if resolucion is None or resolucion not in RESOLUCIONES:
        raise CreditoInconsistenteError("La evaluación de crédito no trae una resolución válida.")
    if limite is not None:
        _exigir_decimal_exacto(limite, "El límite de crédito")
        if limite < 0:
            raise CreditoInconsistenteError("El límite de crédito no puede ser negativo.")
    elif resolucion != "SIN_EXCESO":
        raise CreditoInconsistenteError(
            "Sin límite no hay control de crédito: la resolución solo puede ser SIN_EXCESO."
        )
    if resolucion in _RESOLUCIONES_CON_AUTORIZADOR and autorizador_id is None:
        raise CreditoInconsistenteError(
            f"La resolución {resolucion} necesita el autorizador que la dio."
        )


def evaluar_credito_del_dispositivo(
    *,
    limite: Decimal | None,
    saldo_considerado: Decimal | None,
    total_venta: Decimal,
    cobranza: Decimal,
    politica: str | None,
    resolucion: str | None,
    autorizador_id: UUID | None,
    coherencia_del_exceso: bool = True,
) -> ResultadoCredito:
    """D7 sin conexión, punto 2: congela la evaluación del dispositivo. El servidor calcula el
    disponible y el exceso con el mismo motor sobre los NÚMEROS DEL DISPOSITIVO (límite, saldo
    considerado, total y cobranza de la venta); la política y la resolución son las que él envió.
    No consulta la política vigente, el saldo real ni la tolerancia (el dispositivo no manda la que
    usó; decisión del usuario, 2026-10-23: no se valida su tamaño) y NUNCA rechaza por crédito
    (SYN-05, CRE-09).

    Lo único que rechaza (`CREDITO_INCONSISTENTE`) es lo incoherente consigo mismo: la forma (ver
    `verificar_forma_del_credito_del_dispositivo`) y un exceso propio mayor que cero con
    resolución `SIN_EXCESO`. Un exceso cero con otra resolución se acepta tal cual. Con
    `coherencia_del_exceso=False` (consumidor final, D17) no se compara la resolución con el
    exceso: su regla es `CONSUMIDOR_FINAL_CON_DEUDA`, no el crédito. `tolerancia` queda en cero
    (desconocida). El autorizador se conserva solo en `PIN_SUPERVISOR` y `PERMISO_PROPIO`."""
    verificar_forma_del_credito_del_dispositivo(
        limite=limite,
        saldo_considerado=saldo_considerado,
        politica=politica,
        resolucion=resolucion,
        autorizador_id=autorizador_id,
    )
    assert saldo_considerado is not None and resolucion is not None  # ya verificado
    calculo = calcular_exceso(
        limite=limite,
        saldo_actual=saldo_considerado,
        total_venta=total_venta,
        cobranza=cobranza,
    )
    if coherencia_del_exceso and calculo.exceso > _CERO and resolucion == "SIN_EXCESO":
        raise CreditoInconsistenteError(
            f"Los valores de la evaluación dan un exceso de {calculo.exceso} y la resolución "
            "es SIN_EXCESO."
        )
    return ResultadoCredito(
        calculo.disponible,
        calculo.saldo_resultante,
        calculo.exceso,
        _CERO,
        resolucion,  # type: ignore[arg-type]
        str(autorizador_id)
        if resolucion in _RESOLUCIONES_CON_AUTORIZADOR and autorizador_id is not None
        else None,
    )
