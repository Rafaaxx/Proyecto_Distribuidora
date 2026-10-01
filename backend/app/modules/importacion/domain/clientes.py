"""Importación de clientes: de la fila de planilla a los datos del alta
(`specs/importacion/importacion-de-maestros`, `design.md` D6).

Puro. La fila trae solo texto; el servicio de `clientes` valida y normaliza (nombre,
dirección y contacto obligatorios, documento a dígitos con la longitud de su tipo, CLI-05),
así que acá no se repite ninguna de esas reglas: un vacío es `None` y el resto pasa tal
cual (mismo código de error que el alta individual, TR-10). Lo propio de la planilla:

- `codigo` es obligatorio (D6, restricción de negocio aprobada: CLI-01 lo deja opcional en
  la pantalla, pero sin él no se puede referenciar al cliente en los saldos ni evitar que
  una reimportación lo duplique).
- `estado_facturacion_default` se escribe sin distinguir mayúsculas ni espacios al borde
  (comodidad de la planilla); el catálogo cerrado (`NO_REQUIERE`, `PENDIENTE`) lo valida el
  servicio de `clientes` (`ESTADO_FACTURACION_INVALIDO`, tarea 12.2), igual que la pantalla.
"""

from __future__ import annotations

from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.referencias import obligatorio


def _o_none(texto: str) -> str | None:
    recortado = texto.strip()
    return recortado or None


def _estado_de_facturacion(texto: str) -> str | None:
    return texto.strip().upper() or None


def datos_de_cliente(fila: FilaPlanilla) -> dict[str, str | None]:
    """Argumentos de `clientes.service.crear_cliente` (menos el actor). `nombre`,
    `direccion` y `contacto` van siempre, aunque estén vacíos: el servicio los rechaza
    con `NOMBRE_INVALIDO` y `FICHA_INCOMPLETA`. `codigo` vacío es `VALOR_OBLIGATORIO`."""
    valores = fila.valores
    return {
        "nombre": valores["nombre"],
        "codigo": obligatorio(valores["codigo"], columna="codigo"),
        "razon_social": _o_none(valores["razon_social"]),
        "documento_tipo": _o_none(valores["documento_tipo"]),
        "documento_numero": _o_none(valores["documento_numero"]),
        "direccion": valores["direccion"],
        "contacto": valores["contacto"],
        "telefono": _o_none(valores["telefono"]),
        "email": _o_none(valores["email"]),
        "estado_facturacion_default": _estado_de_facturacion(valores["estado_facturacion_default"]),
    }


def claves_de_cliente(fila: FilaPlanilla) -> list[tuple[str, str]]:
    """Claves naturales de un cliente dentro del archivo: el código (tal como lo
    guarda el servicio, recortado) y, si hay tipo y número, el documento en dígitos
    (`CUIT:20123456789`). Un documento a medias no es clave: el servicio lo rechaza con
    su propio código."""
    valores = fila.valores
    claves: list[tuple[str, str]] = []
    codigo = valores["codigo"].strip()
    if codigo:
        claves.append(("codigo", codigo))
    tipo = valores["documento_tipo"].strip().upper()
    digitos = "".join(c for c in valores["documento_numero"] if c.isdigit())
    if tipo and digitos:
        claves.append(("documento_numero", f"{tipo}:{digitos}"))
    return claves


def columna_de_ficha_incompleta(fila: FilaPlanilla) -> str:
    """`FICHA_INCOMPLETA` lo da el servicio cuando falta la dirección o el contacto, en
    ese orden: la columna es la primera que está vacía."""
    return "direccion" if not fila.valores["direccion"].strip() else "contacto"
