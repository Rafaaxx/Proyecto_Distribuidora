"""Normalización de nombre y CUIT de proveedor (`design.md` D7, tarea 6.2).
Puro: sin acceso a datos, sin `organizacion_id` (la unicidad la valida el
servicio/repositorio, no esta capa)."""

from __future__ import annotations

from app.modules.proveedores.domain.errores import NombreInvalidoError

_DIGITOS = frozenset("0123456789")


def normalizar_nombre(nombre: str) -> str:
    """Recorta espacios al inicio y al final; rechaza vacío (`NOMBRE_INVALIDO`,
    D7: "nombre obligatorio, recortado")."""
    recortado = nombre.strip()
    if not recortado:
        raise NombreInvalidoError("El nombre no puede quedar vacío tras recortar espacios.")
    return recortado


def normalizar_cuit(cuit: str | None) -> str | None:
    """Descarta guiones y espacios; DEBE quedar en exactamente 11 dígitos
    (D7: "normalizado a 11 dígitos ... sin validar dígito verificador").

    `None` o una entrada que, tras descartar separadores, no son 11 dígitos
    (de más, de menos, o con caracteres no numéricos) devuelve `None`: el
    CUIT es opcional (no se levanta `CUIT_INVALIDO` acá; lo hace el
    servicio cuando el usuario lo envió y no normaliza, distinguiendo
    "no se cargó CUIT" de "se cargó uno inválido" a partir del valor
    original, no de este resultado)."""
    if cuit is None:
        return None

    solo_digitos = "".join(caracter for caracter in cuit if caracter in _DIGITOS)
    tiene_solo_digitos_y_separadores = all(
        caracter in _DIGITOS or caracter in {"-", " "} for caracter in cuit
    )
    if not tiene_solo_digitos_y_separadores or len(solo_digitos) != 11:
        return None

    return solo_digitos
