"""Importación de costos informados: de la fila de planilla a los datos del costo
(`specs/importacion/importacion-de-maestros`, `design.md` D4, D8, D12).

Puro. El importe y la bonificación se escriben con coma decimal y se convierten sin punto
flotante (INV-03); la bonificación se escribe en porcentaje (`10`) y pasa a la fracción que
usa el sistema (`0.10`, TR-02). Las reglas (valor > 0 con hasta 2 decimales, bonificación en
[0, 1), presentación de compra activa) y el cálculo del costo base (CST-02) son del servicio
de `proveedores`: acá solo se leen las celdas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.modules.importacion.domain.errores import ErrorDeValor
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.referencias import (
    clave_de_texto,
    obligatorio,
    porcentaje_a_fraccion,
)
from app.modules.importacion.domain.valores import a_booleano, a_decimal, a_fecha


@dataclass(frozen=True)
class DatosDeCosto:
    """Una fila de costos ya leída. `producto_codigo` y `presentacion` siguen siendo
    texto: el importador los resuelve contra los datos de la organización (D4)."""

    producto_codigo: str
    presentacion: str
    valor: Decimal
    incluye_iva: bool
    bonificacion: Decimal
    vigencia_desde: date
    observacion: str | None


def datos_de_costo(fila: FilaPlanilla) -> DatosDeCosto:
    """Lee la fila o lanza el `ErrorDeValor` de la primera celda ilegible (con su
    columna). Sin bonificación es cero; sin observación, `None`."""
    valores = fila.valores
    texto_bonificacion = valores["bonificacion"].strip()
    return DatosDeCosto(
        producto_codigo=obligatorio(valores["producto_codigo"], columna="producto_codigo"),
        presentacion=obligatorio(valores["presentacion"], columna="presentacion"),
        valor=a_decimal(valores["valor"], columna="valor"),
        incluye_iva=a_booleano(valores["incluye_iva"], columna="incluye_iva"),
        bonificacion=(
            porcentaje_a_fraccion(texto_bonificacion, columna="bonificacion")
            if texto_bonificacion
            else Decimal(0)
        ),
        vigencia_desde=a_fecha(valores["vigencia_desde"], columna="vigencia_desde"),
        observacion=valores["observacion"].strip() or None,
    )


def claves_de_costo(fila: FilaPlanilla) -> list[tuple[str, str]]:
    """Clave natural de un costo dentro del archivo: producto, presentación y vigencia
    desde, la misma que rechaza el lote de `COSTO_INFORMAR` (sin distinguir mayúsculas ni
    espacios al borde). Sin una fecha legible no hay clave: su error lo informa la
    lectura de la fila."""
    valores = fila.valores
    try:
        vigencia = a_fecha(valores["vigencia_desde"], columna="vigencia_desde")
    except ErrorDeValor:
        return []
    producto = clave_de_texto(valores["producto_codigo"])
    presentacion = clave_de_texto(valores["presentacion"])
    if not producto or not presentacion:
        return []
    return [("producto_codigo", f"{producto}|{presentacion}|{vigencia.isoformat()}")]
