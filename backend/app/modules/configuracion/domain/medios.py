"""Validación pura de los medios de pago de un pago, una compra de contado o una cobranza
(change 17, tareas 5.1 y 5.2; `design.md` D13 y D17; PAG-01, CMP-03, COB-02, INV-08, TR-01).

Vivía en `proveedores/domain/pagos.py` (change 12); se movió acá para que `proveedores` y
`cobranzas` usen la MISMA función sin que una importe a la otra (`02` §5.3). Sin dependencias
de infraestructura (`CLAUDE.md` §4: `domain/` no importa FastAPI ni SQLAlchemy): recibe datos,
devuelve resultados o lanza errores de dominio de código estable. El estado del medio (activo)
y su pertenencia a la organización no se validan acá: son consultas de la capa de servicio
(`MEDIO_PAGO_INACTIVO`, INV-21).

Los cuatro errores se definen acá y `proveedores/domain/errores.py` los reexporta: la clase es
una sola, así que las pruebas y los manejadores que ya los nombran siguen valiendo.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from app.core.errors import DomainError
from app.core.money import redondear_importe

DECIMALES_DE_IMPORTE = 2
"""`numeric(14,2)`: los importes viajan con 2 decimales (TR-01, INV-03)."""

IMPORTE_MAXIMO = Decimal("999999999999.99")
"""Techo de `numeric(14,2)`."""

MINIMO_MEDIOS = 1
MAXIMO_MEDIOS = 20
"""D6 (change 12), D2 (change 17): de 1 a 20 medios por pago a proveedor o por cobranza."""


class ImporteInvalidoError(DomainError):
    """Importe (total de factura, importe de un medio, total neto) no positivo, con más
    de 2 decimales o fuera de `numeric(14,2)` (TR-01, D1)."""

    codigo = "IMPORTE_INVALIDO"
    status_http = 422


class MediosNoSumanImporteError(DomainError):
    """INV-08: los medios de un pago o una cobranza no suman su importe."""

    codigo = "MEDIOS_NO_SUMAN_IMPORTE"
    status_http = 422


class MediosInvalidosError(DomainError):
    """Change 12, `design.md` D6: un pago a proveedor (o una cobranza, change 17 D2) lleva de
    1 a 20 medios; fuera de ese rango se rechaza antes de mirar importes (el pago de contado
    de una compra no tiene este límite, CMP-03)."""

    codigo = "MEDIOS_INVALIDOS"
    status_http = 422


class ReferenciaObligatoriaError(DomainError):
    """Un medio de pago que exige referencia llegó sin ella (`01` §4)."""

    codigo = "REFERENCIA_OBLIGATORIA"
    status_http = 422


class MedioDePago(Protocol):
    """Un medio ya resuelto por el servicio: su importe, la referencia informada y si el medio
    de la organización la exige.

    Es un `Protocol`: los dataclasses `frozen` de cada módulo (`MedioDeEntrada` de compras, el
    de cobranzas) lo satisfacen por forma, sin conversión. Los tres miembros son de solo
    lectura (`@property`) porque esos dataclasses son `frozen`: un atributo escribible del
    `Protocol` no lo satisficiera.
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
    """TR-01: un importe es mayor que cero, con hasta 2 decimales y dentro de `numeric(14,2)`.
    Devuelve el importe redondeado con exactamente 2 decimales."""
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


def _falta_la_referencia(medio: MedioDePago) -> bool:
    """El medio la exige y llegó sin ella o con solo espacios (`01` §4)."""
    return medio.requiere_referencia and not (medio.referencia and medio.referencia.strip())


def posiciones_sin_referencia(medios: Sequence[MedioDePago]) -> tuple[int, ...]:
    """D13-C (change 17): las posiciones (desde 0, en orden) de los medios cuya referencia es
    obligatoria y falta; una referencia de solo espacios cuenta como faltante. Es lo que la
    cobranza sin conexión observa como `REFERENCIA_FALTANTE` en lugar de rechazar."""
    return tuple(indice for indice, medio in enumerate(medios) if _falta_la_referencia(medio))


def validar_medios(
    importe: Decimal,
    medios: Sequence[MedioDePago],
    *,
    minimo: int = MINIMO_MEDIOS,
    maximo: int | None = MAXIMO_MEDIOS,
    exigir_referencia: bool = True,
) -> None:
    """PAG-01, COB-02, ADR-043 punto 2, INV-08: valida el importe y sus medios.

    - de `minimo` a `maximo` medios (`MEDIOS_INVALIDOS`); el pago a proveedor y la cobranza van
      de 1 a 20 y el contado de una compra no tiene tope (CMP-03), de ahí los dos parámetros;
    - cada medio con importe positivo de 2 decimales (`IMPORTE_INVALIDO`) y, con
      `exigir_referencia`, referencia no vacía donde el medio la exige
      (`REFERENCIA_OBLIGATORIA`);
    - la suma exacta de los medios igual al importe (`MEDIOS_NO_SUMAN_IMPORTE`).

    `exigir_referencia=False` es el modo sin conexión de la cobranza (D13-C, SYN-05): la
    referencia faltante no rechaza (se observa, ver `posiciones_sin_referencia`) pero todo lo
    demás sigue rechazando, porque es contenido malformado (SYN-06, INV-08).

    Un error de medio indica cuál lo causó: el índice desde 0 viaja en el mensaje (que el
    usuario lee) y en `extension["medio"]` del Problem Details.
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
            if exigir_referencia and _falta_la_referencia(medio):
                raise ReferenciaObligatoriaError("El medio de pago exige una referencia.")
        except (ImporteInvalidoError, ReferenciaObligatoriaError) as error:
            raise type(error)(
                f"Medio {indice}: {error.mensaje}", extension={"medio": indice}
            ) from error

    if suma != importe:
        raise MediosNoSumanImporteError(
            f"Los medios suman {redondear_importe(suma)} y el importe del pago es {importe}."
        )
