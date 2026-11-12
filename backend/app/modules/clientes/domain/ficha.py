"""Nombre, código y documento del cliente (`design.md` D1, tareas 1.3 y 6.1).

Puro: sin acceso a datos y sin `organizacion_id` (la unicidad la garantizan
los índices `ux_cliente__codigo` y `ux_cliente__documento` de la base, no esta
capa: son los que separan dos altas concurrentes con el mismo dato, INV-01).

El número de documento admite guiones y espacios porque quien lo carga lo
teclea con separadores (`30-111 222`), igual que el CUIT del proveedor
(`proveedores/domain/normalizacion.py`); lo que se guarda y lo que se compara
son solo dígitos (CLI-05)."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.clientes.domain.errores import (
    DocumentoIncompletoError,
    DocumentoInvalidoError,
    FichaIncompletaError,
    NombreInvalidoError,
)

_DIGITOS = frozenset("0123456789")
# Separadores que se descartan al normalizar. Los puntos NO se aceptan: en el
# CUIT del proveedor tampoco, y `30.111.222` es una ambigüedad que conviene
# obligar a resolver en el formulario.
_SEPARADORES = frozenset("- ")

# CLI-05, decided 2026-09-28: el catálogo es cerrado y la longitud se valida por
# tipo. `DNI` admite 7 u 8 dígitos porque el documento Argentino tiene ambas
# longitudes históricas (`03` §10 no lo restringe más).
_TIPOS_DE_DOCUMENTO = {"CUIT": (11,), "DNI": (7, 8)}


@dataclass(frozen=True, slots=True)
class Documento:
    """Pareja de documento ya normalizada a dígitos."""

    tipo: str
    numero: str

    def __str__(self) -> str:
        """Representación para auditoría y mensajes: `DNI 30111222`."""
        return f"{self.tipo} {self.numero}"


def normalizar_nombre(nombre: str) -> str:
    """Recorta espacios al inicio y al final; rechaza vacío (`NOMBRE_INVALIDO`,
    TR-10, D1)."""
    recortado = nombre.strip()
    if not recortado:
        raise NombreInvalidoError("El nombre no puede quedar vacío tras recortar espacios.")
    return recortado


def normalizar_codigo(codigo: str | None) -> str | None:
    """Recorta el código; vacío se guarda como nulo, no como cadena vacía (D1).

    Una cadena vacía en la columna haría que dos clientes sin código se
    chocaran en `ux_cliente__codigo`, que es único por organización. `None` y
    `""` significan lo mismo y se normalizan al mismo valor."""
    if codigo is None:
        return None
    recortado = codigo.strip()
    if not recortado:
        return None
    return recortado


def normalizar_direccion(direccion: str | None) -> str:
    """La dirección es obligatoria (CLI-01) y se guarda recortada.

    A diferencia de `nombre`, acá un vacío SÍ es un error y no un valor neutro:
    `direccion` es `NOT NULL` en la base y la ficha incompleta se rechaza
    (`FICHA_INCOMPLETA`)."""
    if direccion is None or not direccion.strip():
        raise FichaIncompletaError("La dirección es obligatoria (CLI-01).")
    return direccion.strip()


def normalizar_contacto(contacto: str | None) -> str:
    """El contacto es obligatorio (CLI-01) y se guarda recortado. Mismo criterio
    que la dirección."""
    if contacto is None or not contacto.strip():
        raise FichaIncompletaError("El contacto es obligatorio (CLI-01).")
    return contacto.strip()


def normalizar_documento(tipo: str | None, numero: str | None) -> Documento | None:
    """Normaliza la pareja tipo/número a dígitos, o devuelve `None` si no se
    informó ninguno (CLI-01, CLI-05, D1).

    Los tres casos se distinguen por el código que levantan, porque la spec los
    separa:

    - Los dos ausentes (o los dos vacíos) NO es un error: el documento es
      opcional como pareja y el cliente se identifica por su `id`.
    - Uno de los dos informado, o un número con letras, levanta
      `DOCUMENTO_INCOMPLETO`: la pareja no está completa o no es un número.
    - Tipo fuera del catálogo, o longitud que no corresponde al tipo, levanta
      `DOCUMENTO_INVALIDO` (CLI-05).

    Los separadores `-` y espacio se descartan; cualquier otro carácter
    (`letras`, `.`, `/`) deja el número incompleto. El tipo se compara en
    mayúsculas para no depender de cómo lo tecleó el usuario, pero se guarda en
    mayúsculas para que el índice único compare igual que el catálogo.
    """
    tipo_normalizado = None if tipo is None else tipo.strip().upper()
    numero_recortado = None if numero is None else numero.strip()

    if not tipo_normalizado and not numero_recortado:
        return None

    if not tipo_normalizado or not numero_recortado:
        raise DocumentoIncompletoError(
            "El documento se informa en pareja: o van tipo y número, o ninguno (CLI-01)."
        )

    assert tipo_normalizado is not None
    assert numero_recortado is not None

    longitudes = _TIPOS_DE_DOCUMENTO.get(tipo_normalizado)
    if longitudes is None:
        raise DocumentoInvalidoError(
            f"El tipo de documento {tipo_normalizado!r} no está en el catálogo "
            f"({', '.join(sorted(_TIPOS_DE_DOCUMENTO))}) (CLI-05)."
        )

    solo_digitos = "".join(caracter for caracter in numero_recortado if caracter in _DIGITOS)
    tiene_solo_digitos_y_separadores = all(
        caracter in _DIGITOS or caracter in _SEPARADORES for caracter in numero_recortado
    )
    if not tiene_solo_digitos_y_separadores:
        raise DocumentoIncompletoError(
            "El número de documento solo admite dígitos, guiones y espacios (CLI-05)."
        )

    if len(solo_digitos) not in longitudes:
        esperadas = " o ".join(str(cantidad) for cantidad in longitudes)
        raise DocumentoInvalidoError(
            f"El {tipo_normalizado} debe tener {esperadas} dígitos y tiene {len(solo_digitos)} "
            "(CLI-05)."
        )

    return Documento(tipo=tipo_normalizado, numero=solo_digitos)
