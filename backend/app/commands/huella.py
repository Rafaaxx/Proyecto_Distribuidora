"""Huella canónica del contenido de un comando (ADR-012, extensión
2026-09-21; `design.md` D1; `02` §6.2).

Implementa JCS (RFC 8785, JSON Canonicalization Scheme) acotado a las formas
de dato que el contenido de un comando puede tener: objetos, arreglos,
cadenas, enteros JSON, booleanos y `None`. El dominio prohíbe números de
punto flotante en todo el sistema (`CLAUDE.md` §4, INV-03), así que esta
función deliberadamente no implementa el algoritmo de serialización de
`double` de ECMA-262 que exige JCS para números fraccionarios -- ese caso
no puede ocurrir en contenido válido y, si ocurriera, es un error de
programación que se prefiere ver como `TypeError` en vez de canonizar en
silencio.

Los importes, costos y porcentajes **no** tienen un tipo dedicado en esta
función: viajan como `str`, ya formateados a la escala de su columna por
quien arma el contenido (`redondear_importe`/`redondear_costo` de
`app.core.money`, la única fuente de redondeo del sistema, `CLAUDE.md`
§4), exactamente como dice la spec: "los importes y porcentajes DEBEN
participar de la huella como texto". No se usa `Decimal` como tipo de
entrada acá a propósito: `Decimal.__str__` de Python preserva la escala de
construcción, pero el `Decimal` equivalente de TypeScript (`decimal.js`)
normaliza y **no** preserva los ceros a la derecha (`31250.00` pierde su
escala y queda `31250`) -- dejar que cada lenguaje formatee con su propia
librería antes de entrar a esta función es la única manera de que Python y
TypeScript produzcan el mismo texto y, por lo tanto, la misma huella.

Reglas de canonización:

- Los objetos ordenan sus miembros por la secuencia de unidades de código
  UTF-16 del nombre de la propiedad (RFC 8785 §3.2.3), no por comparación
  de cadena por defecto de Python -- para coincidir exactamente con el
  orden de comparación nativo de cadenas de TypeScript/JavaScript incluso
  fuera del plano básico multilingüe.
- Los arreglos conservan su orden original: solo los objetos se reordenan.
- Las cadenas se normalizan a NFC antes de serializar (`design.md` D1) y
  se escapan solo lo estrictamente necesario (comilla, backslash,
  caracteres de control); el resto, incluido el texto no-ASCII y los
  emoji, se emite tal cual, sin `\\uXXXX` (igual que `JSON.stringify` de
  ECMAScript, que es la base de JCS).
- Los importes y costos/porcentajes viajan como cadena, ya formateados a
  la escala de su columna por `app.core.money` antes de llegar acá (ver
  más arriba). Esta función no distingue un `str` "decimal" de cualquier
  otro `str`: los serializa igual, con NFC y el mismo escape.
- Una clave con valor `None` y una clave ausente producen huellas
  **distintas**: la ausencia simplemente no aparece en el objeto
  serializado, mientras que `None` se emite como el literal `null`.
- Ausencia de espacios: separadores `,` y `:` sin espacio adicional.

`calcular_huella` es la única función pública de este módulo y su firma
tiene un único parámetro (`contenido`): no existe ningún canal para pasarle
una huella informada por el cliente, así que el servidor no puede
confiar en ella aunque quisiera (escenario "La huella informada por el
cliente se ignora", spec `sistema/pipeline-de-comandos`).
"""

from __future__ import annotations

import hashlib
import unicodedata

# Tipos de dato admitidos en el contenido de un comando. Sin `Any`
# (`CLAUDE.md` §5): un valor que no encaje acá es un error de programación,
# no un caso a tolerar en silencio.
ContenidoComando = (
    None | bool | int | str | list["ContenidoComando"] | dict[str, "ContenidoComando"]
)

_ESCAPES_CORTOS: dict[str, str] = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


class ContenidoNoSerializableError(TypeError):
    """Un valor del contenido no tiene un tipo admitido por la huella canónica."""


def _escapar_string(valor: str) -> str:
    normalizado = unicodedata.normalize("NFC", valor)
    partes: list[str] = []
    for caracter in normalizado:
        if caracter in _ESCAPES_CORTOS:
            partes.append(_ESCAPES_CORTOS[caracter])
        elif ord(caracter) < 0x20:
            partes.append(f"\\u{ord(caracter):04x}")
        else:
            partes.append(caracter)
    return '"' + "".join(partes) + '"'


def _clave_de_ordenamiento(clave: str) -> bytes:
    # Unidades de código UTF-16, no codepoints (RFC 8785 §3.2.3): coincide
    # con el orden de comparación nativo de cadenas en TypeScript.
    return clave.encode("utf-16-be", "surrogatepass")


def _serializar(valor: ContenidoComando) -> str:
    if valor is None:
        return "null"
    # `bool` es subclase de `int` en Python: se comprueba primero para no
    # serializar `True`/`False` como `1`/`0`.
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, str):
        return _escapar_string(valor)
    if isinstance(valor, list):
        return "[" + ",".join(_serializar(elemento) for elemento in valor) + "]"
    if isinstance(valor, dict):
        claves_ordenadas = sorted(valor.keys(), key=_clave_de_ordenamiento)
        miembros = (
            f"{_escapar_string(clave)}:{_serializar(valor[clave])}" for clave in claves_ordenadas
        )
        return "{" + ",".join(miembros) + "}"

    raise ContenidoNoSerializableError(
        f"Tipo no admitido en el contenido de un comando: {type(valor).__name__} "
        "(la huella canónica solo admite dict, list, str, int, bool y None; los "
        "decimales viajan como str ya formateado por app.core.money)"
    )


def calcular_huella(contenido: dict[str, ContenidoComando]) -> str:
    """Calcula la huella SHA-256 canónica del contenido de un comando.

    El resultado es determinista: el mismo contenido lógico produce siempre
    la misma huella hexadecimal, sin importar el orden de las claves con el
    que llegó ni el proceso (Python o TypeScript) que lo calculó, siempre
    que los importes y costos/porcentajes ya vengan formateados como texto
    a la escala de su columna por el llamador (`app.core.money`).
    """
    canonico = _serializar(contenido)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()
