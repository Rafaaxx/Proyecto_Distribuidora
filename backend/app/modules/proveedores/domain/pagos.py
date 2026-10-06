"""Dominio puro del pago a un proveedor (change 12, grupo 3, tareas 3.1 y 3.3;
`specs/proveedores/pagos-a-proveedores/spec.md`, `design.md` D6).

Sin dependencias de infraestructura (`AGENTS.md` §4: `domain/` no importa FastAPI,
SQLAlchemy ni nada más): recibe datos, devuelve resultados o lanza errores de dominio.
Los errores llevan un código estable de `errores.py`, no mensajes sueltos.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.core.money import redondear_importe
from app.modules.proveedores.domain.errores import (
    FechaInvalidaError,
    ImporteInvalidoError,
    MediosInvalidosError,
    MediosNoSumanImporteError,
    PagoDeCompraVigienteError,
    PagoYaAnuladoError,
    ReferenciaObligatoriaError,
)

DECIMALES_DE_IMPORTE = 2
"""`numeric(14,2)`: los importes viajan con 2 decimales (TR-01, INV-03)."""

IMPORTE_MAXIMO = Decimal("999999999999.99")
"""Techo de `numeric(14,2)`."""

MINIMO_MEDIOS = 1
MAXIMO_MEDIOS = 20
"""D6: de 1 a 20 medios por pago a proveedor."""

MAXIMO_OBSERVACION = 500
"""D6: largo máximo de la observación del pago, medido sobre el texto recibido (antes de
recortar los espacios), como el formulario (`max(500)` de Zod)."""

ORIGEN_COMPRA = "COMPRA"
ORIGEN_INDEPENDIENTE = "INDEPENDIENTE"
ESTADO_CONFIRMADA = "CONFIRMADA"
ESTADO_ANULADA = "ANULADA"


class MedioDePago(Protocol):
    """Un medio del pago ya resuelto por el servicio: su importe, la referencia
    informada y si el medio de la organización la exige.

    Es un `Protocol` y no el `MedioDeEntrada` de `compras.py` a propósito: este módulo es
    el que comparte `validar_medios` con el pago de contado (tarea 3.3), así que el
    dataclass de compras no puede depender de él en la otra dirección. Los dataclasses
    que llegan desde el servicio satisfacen este contrato por forma, sin conversión.

    Los tres miembros son de solo lectura (`@property`) porque los dataclasses que lo
    cumplen son `frozen`: un atributo escribible del `Protocol` no lo satisficiera.
    """

    @property
    def importe(self) -> Decimal: ...

    @property
    def referencia(self) -> str | None: ...

    @property
    def requiere_referencia(self) -> bool: ...


def _decimales(valor: Decimal) -> int:
    """Cantidad de decimales significativos (`2.500` tiene 1; `1E+1` tiene 0)."""
    exponente = valor.normalize().as_tuple().exponent
    assert isinstance(exponente, int)
    return max(0, -exponente)


def validar_importe(valor: Decimal, nombre: str) -> Decimal:
    """TR-01, D6: un importe es mayor que cero, con hasta 2 decimales y dentro de
    `numeric(14,2)`. Devuelve el importe redondeado con exactamente 2 decimales."""
    if (
        not valor.is_finite()
        or valor <= 0
        or _decimales(valor) > DECIMALES_DE_IMPORTE
        or valor > IMPORTE_MAXIMO
    ):
        raise ImporteInvalidoError(
            f"{nombre} debe ser mayor que cero, con hasta {DECIMALES_DE_IMPORTE} decimales "
            f"y no más de {IMPORTE_MAXIMO}."
        )
    return redondear_importe(valor)


def validar_medios(
    importe: Decimal,
    medios: Sequence[MedioDePago],
    *,
    minimo: int = MINIMO_MEDIOS,
    maximo: int | None = MAXIMO_MEDIOS,
) -> None:
    """D6, PAG-01, ADR-043 punto 2, INV-08: valida el importe del pago y sus medios.

    - de `minimo` a `maximo` medios (`MEDIOS_INVALIDOS`); el pago a proveedor va de 1 a
      20 (D6) y el contado de una compra no tiene tope (CMP-03), de ahí los dos
      parámetros en lugar de una regla fija;
    - cada medio con importe positivo de 2 decimales (`IMPORTE_INVALIDO`) y referencia
      no vacía donde el medio la exige (`REFERENCIA_OBLIGATORIA`);
    - la suma exacta de los medios igual al importe (`MEDIOS_NO_SUMAN_IMPORTE`).

    El estado del medio (activo) y su pertenencia a la organización no se validan acá:
    son consultas de la capa de servicio (`MEDIO_PAGO_INACTIVO`, INV-21), no reglas puras.
    """
    validar_importe(importe, "El importe del pago")

    cantidad = len(medios)
    if cantidad < minimo or (maximo is not None and cantidad > maximo):
        esperado = (
            f"de {minimo} a {maximo} medios" if maximo is not None else f"al menos {minimo} medios"
        )
        raise MediosInvalidosError(f"El pago lleva {cantidad} medios y se admiten {esperado}.")

    suma = Decimal("0.00")
    for indice, medio in enumerate(medios):
        try:
            suma += validar_importe(medio.importe, "El importe de cada medio")
            if medio.requiere_referencia and not (medio.referencia and medio.referencia.strip()):
                raise ReferenciaObligatoriaError("El medio de pago exige una referencia.")
        except (ImporteInvalidoError, ReferenciaObligatoriaError) as error:
            # PAG-01: el error de medio dice cuál lo causó. El índice 0-based viaja dos
            # veces: en el mensaje (que el usuario lee) y en `extension["medio"]` del
            # Problem Details (tarea 4.3), la misma clave que usa `_resolver_medios`.
            raise type(error)(
                f"Medio {indice}: {error.mensaje}", extension={"medio": indice}
            ) from error

    if suma != importe:
        raise MediosNoSumanImporteError(
            f"Los medios suman {redondear_importe(suma)} y el importe del pago es {importe}."
        )


# --- fecha, observacion y reglas de la anulacion (D2, D4, D6, PAG-03) -------------------


def validar_fecha(fecha: date, *, hoy: date) -> None:
    """D4, TR-04: la fecha es la del pago real (la del recibo o la transferencia) y no
    puede ser posterior a la fecha de negocio de hoy en la zona de la organización. Sin
    límite hacia atrás. El movimiento `PAGO` de la cuenta no usa esta fecha sino el
    `occurred_at` del comando (D4, opción A)."""
    if fecha > hoy:
        raise FechaInvalidaError(f"La fecha {fecha} es posterior a hoy ({hoy}).")


def recortar_observacion(observacion: str | None) -> str | None:
    """D6: la observación se guarda recortada y vacía equivale a `None`. La columna es
    `text` (D9), así que el largo (`MAXIMO_OBSERVACION`) lo aplican el esquema de la API
    y el contenido del comando, antes de llegar acá (INV-03, `03` §6)."""
    if observacion is None:
        return None
    recortada = observacion.strip()
    return recortada or None


def validar_pago_independiente(
    importe: Decimal, fecha: date, observacion: str | None, *, hoy: date
) -> str | None:
    """D4, D6, PAG-01: las reglas puras del pago independiente y la observación a guardar.

    Devuelve la observación recortada (o `None` si vino vacía) para que el servicio no
    tenga que repetir el recorte. Los medios los valida `validar_medios`, que el servicio
    invoca por separado igual que en el pago de contado; el resto de las reglas del pago
    -- que no se edita (TR-06), que el proveedor exista en la organización (INV-21), que
    el medio esté activo (TR-09) y que el pago reduzca el saldo (PAG-02) -- no son de esta
    capa.
    """
    validar_importe(importe, "El importe del pago")
    validar_fecha(fecha, hoy=hoy)
    return recortar_observacion(observacion)


def validar_pago_a_anular(estado: str, origen: str, estado_compra: str | None) -> None:
    """D2 (opción A), PAG-03, CMP-05, TR-06: las reglas puras de la anulación de un pago.

    - un pago `ANULADA` no se anula dos veces (`PAGO_YA_ANULADO`); la regla va primera
      porque es la que ve el cliente que reintenta una anulación ya aplicada;
    - el pago de una compra `CONFIRMADA` no se anula por separado
      (`PAGO_DE_COMPRA_VIGENTE`): una compra de contado vigente siempre tiene su pago
      vigente (CMP-03), se anula con la compra;
    - el pago de una compra `ANULADA` sí se anula por separado, cuando el proveedor
      devuelve el dinero después (D2).

    Que la compra exista, sea de esta organización y se haya anulado sin devolver el pago
    se resuelve en el servicio, con la fila bloqueada (D10, `02` §7.3).
    """
    if estado == ESTADO_ANULADA:
        raise PagoYaAnuladoError("El pago ya está anulado.")
    if origen == ORIGEN_COMPRA and estado_compra == ESTADO_CONFIRMADA:
        raise PagoDeCompraVigienteError(
            "El pago es de una compra confirmada: hay que anular la compra (CMP-05, D2)."
        )
