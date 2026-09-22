"""Ejecuta contra `app.commands.huella.calcular_huella` los casos compartidos
de `shared/fixtures/calculo/huella-canonica.json` (`"motor": "huella"`).

Spec `sistema/pipeline-de-comandos`, escenarios "El mismo contenido en
distinto orden produce la misma huella" y "Un contenido distinto produce una
huella distinta"; ADR-012 (extensión 2026-09-21, `design.md` D1).

Los campos decimales del fixture viajan como `{"__decimal__": "<texto>",
"escala": 2|6}` porque JSON no tiene un tipo Decimal nativo: este cargador
los resuelve a un `str` ya cuantizado y formateado con `app.core.money` (la
única fuente de redondeo del sistema, `CLAUDE.md` §4) *antes* de llamar a
`calcular_huella`, tal como haría el código real que arma el contenido de un
comando. `calcular_huella` en sí no decide ninguna escala ni distingue un
`str` "decimal" de cualquier otro `str` (`design.md` D1: "decimales
normalizados a la escala de su columna antes de serializar" es
responsabilidad de quien arma el contenido, no de la función de huella --
ver el docstring de `app.commands.huella` para por qué no se usa `Decimal`
como tipo de entrada).
"""

from __future__ import annotations

from typing import Any

import pytest
from cargador import descubrir_casos

from app.commands.huella import calcular_huella
from app.core.money import redondear_costo, redondear_importe


def _resolver_decimales(nodo: Any) -> Any:
    if isinstance(nodo, dict):
        if "__decimal__" in nodo:
            escala = nodo["escala"]
            if escala == 2:
                return str(redondear_importe(nodo["__decimal__"]))
            if escala == 6:
                return str(redondear_costo(nodo["__decimal__"]))
            raise ValueError(f"escala de fixture no soportada: {escala}")
        return {clave: _resolver_decimales(valor) for clave, valor in nodo.items()}
    if isinstance(nodo, list):
        return [_resolver_decimales(elemento) for elemento in nodo]
    return nodo


_CASOS_HUELLA = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "huella"]

# Guardia de deriva: si el fixture semilla dejara de tener casos de
# "huella", esta suite no debe quedar en silencio con 0 pruebas.
if not _CASOS_HUELLA:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "huella" en '
        "shared/fixtures/calculo/ -- el arnés de huella.py quedaría mudo"
    )


@pytest.mark.parametrize(
    "caso",
    _CASOS_HUELLA,
    ids=[caso.id for caso in _CASOS_HUELLA],
)
def test_caso_compartido_de_huella(caso: object) -> None:
    entrada = caso.entrada  # type: ignore[attr-defined]
    contenido = _resolver_decimales(entrada["contenido"])

    resultado = calcular_huella(contenido)

    esperado = caso.salida_esperada["huella"]  # type: ignore[attr-defined]
    assert resultado == esperado


def test_claves_fuera_de_orden_dan_la_misma_huella() -> None:
    """Escenario "El mismo contenido en distinto orden produce la misma huella"."""
    original = next(
        c for c in _CASOS_HUELLA if c.id == "HUELLA-claves-fuera-de-orden-orden-original"
    )
    alterno = next(c for c in _CASOS_HUELLA if c.id == "HUELLA-claves-fuera-de-orden-orden-alterno")

    huella_original = calcular_huella(original.entrada["contenido"])
    huella_alterna = calcular_huella(alterno.entrada["contenido"])
    assert huella_original == huella_alterna


def test_nfc_y_nfd_dan_la_misma_huella() -> None:
    original = next(c for c in _CASOS_HUELLA if c.id == "HUELLA-texto-nfc")
    alterno = next(c for c in _CASOS_HUELLA if c.id == "HUELLA-texto-nfd")

    huella_original = calcular_huella(original.entrada["contenido"])
    huella_alterna = calcular_huella(alterno.entrada["contenido"])
    assert huella_original == huella_alterna


def test_nulo_y_clave_ausente_dan_huellas_distintas() -> None:
    con_nulo = next(c for c in _CASOS_HUELLA if c.id == "HUELLA-clave-con-valor-nulo")
    ausente = next(c for c in _CASOS_HUELLA if c.id == "HUELLA-clave-ausente")

    huella_con_nulo = calcular_huella(con_nulo.entrada["contenido"])
    huella_ausente = calcular_huella(ausente.entrada["contenido"])
    assert huella_con_nulo != huella_ausente


def test_orden_de_arreglo_cambia_la_huella() -> None:
    """Escenario "Un contenido distinto produce una huella distinta"

    (los arreglos no se reordenan, a diferencia de los objetos).
    """
    original = next(c for c in _CASOS_HUELLA if c.id == "HUELLA-arreglo-orden-importa-original")
    invertido = next(c for c in _CASOS_HUELLA if c.id == "HUELLA-arreglo-orden-importa-invertido")

    huella_original = calcular_huella(original.entrada["contenido"])
    huella_invertida = calcular_huella(invertido.entrada["contenido"])
    assert huella_original != huella_invertida


def test_decimal_normalizado_a_la_escala_de_su_columna_da_la_misma_huella() -> None:
    """`"31250.00"` y `"31250.0"` son el mismo importe (`design.md` D1): una
    vez normalizados a la escala de `NUMERIC(14,2)` con `redondear_importe`
    y formateados a texto, su huella es idéntica aunque el texto de origen
    difiera."""
    dos_decimales = str(redondear_importe("31250.00"))
    un_decimal = str(redondear_importe("31250.0"))

    assert dos_decimales == un_decimal == "31250.00"  # ambos normalizan al mismo texto
    assert calcular_huella({"importe_total": dos_decimales}) == calcular_huella(
        {"importe_total": un_decimal}
    )


def test_huella_no_confia_en_la_huella_informada_por_el_cliente() -> None:
    """Escenario "La huella informada por el cliente se ignora": la firma de
    `calcular_huella` no admite ningún parámetro de huella externa -- no hay
    forma de que el servidor use un valor que no calculó él mismo."""
    import inspect

    firma = inspect.signature(calcular_huella)
    assert list(firma.parameters) == ["contenido"]

    contenido = {"cliente_id": "c-1"}
    huella_correcta = calcular_huella(contenido)
    huella_informada_por_cliente = "0" * 64

    assert huella_correcta != huella_informada_por_cliente
    # Reenviar el mismo contenido siempre recalcula la misma huella real,
    # sin que exista ningún canal para inyectar la del cliente.
    assert calcular_huella(contenido) == huella_correcta


def test_calcular_huella_rechaza_un_tipo_no_admitido() -> None:
    """Segundo caso de borde de triangulación: un valor de tipo no admitido
    (p. ej. un `float`, prohibido en todo el sistema por INV-03) falla con
    un error explícito en vez de canonizarse en silencio."""
    from app.commands.huella import ContenidoNoSerializableError

    with pytest.raises(ContenidoNoSerializableError):
        calcular_huella({"importe": 3.14})  # type: ignore[dict-item]
