"""Importación de proveedores: de la fila de planilla a los datos del alta
(`specs/importacion/importacion-de-maestros`, `design.md` D4, D6).

Puro. La fila trae solo texto; el servicio de `proveedores` valida y normaliza
(nombre recortado y obligatorio, CUIT de 11 dígitos), así que acá no se repite
ninguna regla: un vacío es `None` y el resto pasa tal cual (mismo código de error
que el alta individual, TR-10).
"""

from __future__ import annotations

from app.modules.importacion.domain.planilla import FilaPlanilla

_LARGO_DE_CUIT = 11


def _o_none(texto: str) -> str | None:
    return texto or None


def datos_de_proveedor(fila: FilaPlanilla) -> dict[str, str | None]:
    """Argumentos de `proveedores.service.crear_proveedor` (menos la organización y
    el actor). `nombre` va siempre, aunque esté vacío: el servicio lo rechaza con
    `NOMBRE_INVALIDO`."""
    valores = fila.valores
    return {
        "nombre": valores["nombre"],
        "cuit": _o_none(valores["cuit"]),
        "contacto": _o_none(valores["contacto"]),
        "telefono": _o_none(valores["telefono"]),
        "email": _o_none(valores["email"]),
    }


def claves_de_proveedor(fila: FilaPlanilla) -> list[tuple[str, str]]:
    """Claves naturales de un proveedor dentro del archivo: el nombre sin
    mayúsculas ni espacios al borde (D4) y el CUIT en dígitos, solo si tiene 11
    (uno inválido no es clave: cada fila lo informa como `CUIT_INVALIDO`)."""
    claves = [("nombre", fila.valores["nombre"].strip().casefold())]
    digitos = fila.valores["cuit"].replace("-", "").replace(" ", "")
    if len(digitos) == _LARGO_DE_CUIT and digitos.isdigit():
        claves.append(("cuit", digitos))
    return claves
