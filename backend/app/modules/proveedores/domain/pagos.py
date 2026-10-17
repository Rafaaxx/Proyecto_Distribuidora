"""Dominio puro del pago a un proveedor (change 12, grupo 3, tareas 3.1 y 3.3;
`specs/proveedores/pagos-a-proveedores/spec.md`, `design.md` D6).

Sin dependencias de infraestructura (`AGENTS.md` §4: `domain/` no importa FastAPI,
SQLAlchemy ni nada más): recibe datos, devuelve resultados o lanza errores de dominio.
Los errores llevan un código estable de `errores.py`, no mensajes sueltos.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

# Change 17 (`design.md` D17): la validación de medios vive en `configuracion/domain/medios.py`
# (la usan pagos, compras de contado y cobranzas). Se reexporta: es la misma función.
from app.modules.configuracion.domain.medios import (
    MedioDePago as MedioDePago,
)
from app.modules.configuracion.domain.medios import (
    validar_importe as validar_importe,
)
from app.modules.configuracion.domain.medios import (
    validar_medios as validar_medios,
)
from app.modules.proveedores.domain.errores import (
    FechaInvalidaError,
    PagoDeCompraVigienteError,
    PagoYaAnuladoError,
)

MAXIMO_OBSERVACION = 500
"""D6: largo máximo de la observación del pago, medido sobre el texto recibido (antes de
recortar los espacios), como el formulario (`max(500)` de Zod)."""

ORIGEN_COMPRA = "COMPRA"
ORIGEN_INDEPENDIENTE = "INDEPENDIENTE"
ESTADO_CONFIRMADA = "CONFIRMADA"
ESTADO_ANULADA = "ANULADA"


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
