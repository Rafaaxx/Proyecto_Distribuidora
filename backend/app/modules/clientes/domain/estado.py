"""Máquina de estados del cliente (`docs/01-dominio.md` §18, CLI-02, CLI-04,
CLI-06, `design.md` D7).

`ACTIVO <-> SUSPENDIDO`, `ACTIVO -> INACTIVO`, `SUSPENDIDO -> INACTIVO`, y
desde `INACTIVO` la única salida es volver a `ACTIVO` y solo si el cliente no
tiene operaciones (CLI-06, ADR-030). El cliente nace `ACTIVO` (`CLIENTE_CREAR`
no acepta el estado inicial) y nunca se borra (CLI-04, INV-05): inactivar es la
forma de retirarlo.

`tiene_operaciones` es un dato, no una consulta: la función no sabe si el
cliente tuvo ventas, cobranzas o compras, y este change no tiene forma de
averiguarlo porque ninguno de esos módulos existe todavía (changes 08, 10, 17 y
18a). Por eso la comprobación vive acá como parámetro y no como
`SELECT EXISTS`: el change que registre la primera operación pasa el dato desde
su verificador (ADR-023) sin tocar esta máquina."""

from __future__ import annotations

from app.modules.clientes.domain.errores import (
    ClienteConOperacionesError,
    ConsumidorFinalNoInactivableError,
    EstadoInvalidoError,
    TransicionEstadoInvalidaError,
)

# `03` §10, `01` §18. Catálogo cerrado: un estado fuera de acá no entra ni por un
# camino que se salte el dominio (el `CHECK` de la base lo repite).
ESTADOS = frozenset({"ACTIVO", "SUSPENDIDO", "INACTIVO"})

_TRANSICIONES: dict[str, frozenset[str]] = {
    "ACTIVO": frozenset({"SUSPENDIDO", "INACTIVO"}),
    "SUSPENDIDO": frozenset({"ACTIVO", "INACTIVO"}),
    # La salida de `INACTIVO` depende de si el cliente tiene operaciones, así que
    # no está en la tabla y se resuelve en `validar_transicion`.
    "INACTIVO": frozenset(),
}

# Estados en los que puede estar el consumidor final (CLI-03, ADR-029): no se
# inactiva, para que la venta "de paso" no se apague por un cambio de estado.
_ESTADOS_INACTIVABLES = frozenset({"ACTIVO", "SUSPENDIDO"})


def validar_estado(estado: str) -> str:
    """Verifica que el estado esté en el catálogo (`ESTADO_INVALIDO`, `01` §18).

    No normaliza: el estado es un valor de catálogo cerrado, no texto libre, y
    aceptarlo "arreglado" ocultaría un cliente que nunca would've coincidido con
    el `CHECK` de la base."""
    if estado not in ESTADOS:
        raise EstadoInvalidoError(
            f"El estado {estado!r} no está en el catálogo ({', '.join(sorted(ESTADOS))})."
        )
    return estado


def validar_transicion(
    estado_actual: str,
    estado_nuevo: str,
    *,
    tiene_operaciones: bool = False,
    es_consumidor_final: bool = False,
) -> str:
    """Valida el paso de un estado a otro contra `01` §18 y devuelve el estado
    nuevo.

    Las cuatro razones por las que un cambio se rechaza, en el orden en que se
    evalúan:

    1. `ESTADO_INVALIDO`: el estado pedido no existe. Se valida el nuevo y el
       actual, porque una fila con un estado que ya no está en el catálogo es
       una inconsistencia que hay que ver, no asumir.
    2. `CONSUMIDOR_FINAL_NO_INACTIVABLE`: el consumidor final no pasa a
       `INACTIVO` (CLI-03, ADR-029). Se chequea antes que la transición
       genérica para que el mensaje sea el de esta regla y no el de la máquina.
    3. `CLIENTE_CON_OPERACIONES`: `INACTIVO -> ACTIVO` con operaciones (CLI-06,
       ADR-030).
    4. `TRANSICION_ESTADO_INVALIDA`: cualquier otro salto no permitido.

    Volver al mismo estado NO es un error: `CLIENTE_MODIFICAR` manda la ficha
    entera, así que reenviar la misma ficha deja el estado como estaba y eso no
    puede ser un rechazo."""
    validar_estado(estado_actual)
    validar_estado(estado_nuevo)

    if estado_nuevo == estado_actual:
        return estado_nuevo

    if estado_nuevo == "INACTIVO" and es_consumidor_final:
        raise ConsumidorFinalNoInactivableError(
            "El cliente consumidor final no se inactiva: solo puede estar ACTIVO o "
            "SUSPENDIDO (CLI-03, ADR-029)."
        )

    if estado_actual == "INACTIVO" and estado_nuevo == "ACTIVO":
        if tiene_operaciones:
            raise ClienteConOperacionesError(
                "Un cliente inactivo con operaciones no vuelve a ACTIVO: la inactivación es "
                "terminal (CLI-06, ADR-030)."
            )
        return estado_nuevo

    if estado_nuevo not in _TRANSICIONES[estado_actual]:
        raise TransicionEstadoInvalidaError(
            f"No se permite pasar de {estado_actual} a {estado_nuevo} (01 §18)."
        )

    return estado_nuevo


def puede_inactivar(estado_actual: str, *, es_consumidor_final: bool = False) -> bool:
    """Si el cliente puede pasar a `INACTIVO` desde su estado actual.

    Responde lo mismo que `validar_transicion` para esa transición y nada más:
    la usa la interfaz de confirmación tipeada del frontend (D7), que tiene que
    saber si va a pedir el nombre completo antes de enviar."""

    if es_consumidor_final:
        return False
    if estado_actual not in ESTADOS:
        return False
    return "INACTIVO" in _TRANSICIONES[estado_actual]
