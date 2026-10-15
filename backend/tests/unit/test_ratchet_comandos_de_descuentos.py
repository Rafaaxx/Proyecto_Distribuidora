"""Change 16, tarea 11.1: ratchet de los comandos de reglas de descuento.

- Los cuatro tipos (`REGLA_DESCUENTO_CREAR`, `REGLA_DESCUENTO_MODIFICAR`,
  `REGLA_DESCUENTO_ACTIVAR`, `REGLA_DESCUENTO_PAUSAR`) están en el catálogo de comandos y en el
  registro de handlers, como solo `ONLINE` con `admite_offline = False` (`02` §6.5, `design.md`
  D18).
- Ningún handler de `descuentos` devuelve `DatosDeAuditoria`: el bus deja UNA fila de auditoría
  por comando aceptado (AUD-01, ADR-022) y estos comandos no llevan motivo ni constancia de
  ubicación tomada. Los ratchets de motivo y de constancia del change 15 (en
  `test_ratchet_comandos_de_stock.py`) no cambian: este archivo no los toca.

CÓMO SE DETECTA "devuelve el dato de auditoría": se inspecciona el BYTECODE del handler
(`co_names` de su `__code__`, recursivo en los objetos de código anidados) buscando
`DatosDeAuditoria`, igual que `test_ratchet_comandos_de_stock.py`: un comentario o un docstring
que lo mencionen no hacen pasar ni fallar la prueba.

Reglas citadas: AUD-01, SYN-02, ADR-022, `02` §6.5.
"""

from __future__ import annotations

import pytest

import app.main  # noqa: F401  (el arranque importa los módulos que registran los handlers)
from app.commands import registro
from app.commands.auditoria import DatosDeAuditoria
from app.commands.catalogo import tipo_declarado, tipos_declarados

TIPOS_DE_DESCUENTOS = (
    "REGLA_DESCUENTO_CREAR",
    "REGLA_DESCUENTO_MODIFICAR",
    "REGLA_DESCUENTO_ACTIVAR",
    "REGLA_DESCUENTO_PAUSAR",
)
NOMBRE_DEL_DATO = "DatosDeAuditoria"


def _nombres(codigo: object) -> set[str]:
    """`co_names` del código y de los objetos de código anidados."""
    nombres: set[str] = set(codigo.co_names)  # type: ignore[attr-defined]
    for constante in codigo.co_consts:  # type: ignore[attr-defined]
        if hasattr(constante, "co_names"):
            nombres |= _nombres(constante)
    return nombres


def _tipos_registrados() -> frozenset[str]:
    return frozenset(
        registrado.tipo
        for registrado in registro._REGISTRO.values()  # noqa: SLF001  (no hay listado público)
    )


@pytest.mark.parametrize("tipo", TIPOS_DE_DESCUENTOS)
def test_los_cuatro_tipos_estan_en_el_catalogo_y_en_el_registro_solo_online(tipo: str) -> None:
    declarado = tipo_declarado(tipo)

    assert declarado is not None, f"{tipo} no está en el catálogo de comandos"
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert tipo in _tipos_registrados()
    assert registro.resolver_handler(tipo, 1).tipo == tipo


def test_el_catalogo_y_el_registro_coinciden_en_los_tipos_de_descuentos() -> None:
    del_catalogo = {t for t in tipos_declarados() if t.startswith("REGLA_DESCUENTO_")}
    del_registro = {t for t in _tipos_registrados() if t.startswith("REGLA_DESCUENTO_")}

    assert del_catalogo == del_registro == set(TIPOS_DE_DESCUENTOS)


def test_ningun_handler_de_descuentos_devuelve_datos_de_auditoria() -> None:
    de_descuentos = [
        registrado
        for registrado in registro._REGISTRO.values()  # noqa: SLF001
        if registrado.tipo.startswith("REGLA_DESCUENTO_")
    ]

    assert len(de_descuentos) == len(TIPOS_DE_DESCUENTOS)
    devuelven = [r.tipo for r in de_descuentos if NOMBRE_DEL_DATO in _nombres(r.funcion.__code__)]
    assert devuelven == []


def test_la_deteccion_distingue_un_handler_que_devuelve_el_dato_de_uno_que_no() -> None:
    """Verificación en negativo: la misma inspección sobre dos funciones de prueba."""

    def devuelve() -> object:
        return DatosDeAuditoria(motivo_id=None)

    def no_devuelve() -> object:
        """Menciona DatosDeAuditoria solo en este docstring."""
        # DatosDeAuditoria
        return None

    assert NOMBRE_DEL_DATO in _nombres(devuelve.__code__)
    assert NOMBRE_DEL_DATO not in _nombres(no_devuelve.__code__)
