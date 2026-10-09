"""Change 14, tarea 11.1: ratchets de los comandos de transferencias y ajustes.

- Los cuatro tipos nuevos (`STOCK_TRANSFERIR`, `STOCK_AJUSTAR`, `STOCK_TRANSFERENCIA_ANULAR`,
  `STOCK_AJUSTE_ANULAR`) están en el catálogo de comandos como solo `ONLINE` (`02` §6.5).
- D10 (`design.md`): EXACTAMENTE `STOCK_AJUSTAR`, `STOCK_TRANSFERENCIA_ANULAR` y
  `STOCK_AJUSTE_ANULAR` devuelven el motivo para la fila de auditoría del bus (AUD-02). Los
  demás handlers, incluidos `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` (deuda nominada, fuera
  del alcance aprobado), no lo devuelven. Un cuarto comando que empiece a devolverlo, o uno de
  los tres que deje de hacerlo, rompe esta prueba y obliga a revisar la enmienda de ADR-022.

CÓMO SE DETECTA "devuelve el motivo": se inspecciona el BYTECODE de la función del handler --
`co_names` de su `__code__` -- buscando el nombre `DatosDeAuditoria`, igual que
`test_bus_cobertura_rutas_de_escritura.py` busca `procesar_comando`: un comentario o un docstring
que lo mencionen no hacen pasar la prueba. El comportamiento real (una sola fila de auditoría con
el motivo) lo prueban `test_stock_ajustar.py`, `test_stock_transferencia_anular.py` y
`test_stock_ajuste_anular.py`.

Reglas citadas: AUD-02, SYN-02, ADR-022.
"""

from __future__ import annotations

import pytest

import app.main  # noqa: F401  (el arranque importa los módulos que registran los handlers)
from app.commands import registro
from app.commands.auditoria import DatosDeAuditoria
from app.commands.catalogo import tipo_declarado

TIPOS_NUEVOS = (
    "STOCK_TRANSFERIR",
    "STOCK_AJUSTAR",
    "STOCK_TRANSFERENCIA_ANULAR",
    "STOCK_AJUSTE_ANULAR",
)
TIPOS_CON_MOTIVO_DE_AUDITORIA = frozenset(
    {"STOCK_AJUSTAR", "STOCK_TRANSFERENCIA_ANULAR", "STOCK_AJUSTE_ANULAR"}
)
NOMBRE_DEL_DATO = "DatosDeAuditoria"


@pytest.mark.parametrize("tipo", TIPOS_NUEVOS)
def test_los_tipos_nuevos_estan_declarados_solo_online_y_con_handler_v1(tipo: str) -> None:
    declarado = tipo_declarado(tipo)

    assert declarado is not None, f"{tipo} no está en el catálogo de comandos"
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert registro.resolver_handler(tipo, 1).tipo == tipo


def _nombres(codigo: object) -> set[str]:
    """`co_names` del código y de los objetos de código anidados."""
    nombres: set[str] = set(codigo.co_names)  # type: ignore[attr-defined]
    for constante in codigo.co_consts:  # type: ignore[attr-defined]
        if hasattr(constante, "co_names"):
            nombres |= _nombres(constante)
    return nombres


def tipos_que_devuelven_motivo_de_auditoria() -> frozenset[str]:
    """Tipos de los handlers registrados cuyo código construye el dato de auditoría."""
    return frozenset(
        registrado.tipo
        for registrado in registro._REGISTRO.values()  # noqa: SLF001  (no hay listado público)
        if NOMBRE_DEL_DATO in _nombres(registrado.funcion.__code__)
    )


def test_exactamente_tres_comandos_devuelven_el_motivo_para_la_auditoria() -> None:
    assert tipos_que_devuelven_motivo_de_auditoria() == TIPOS_CON_MOTIVO_DE_AUDITORIA


@pytest.mark.parametrize(
    "tipo",
    ["STOCK_TRANSFERIR", "COMPRA_ANULAR", "PAGO_PROVEEDOR_ANULAR", "STOCK_INICIAL_REGISTRAR"],
)
def test_la_deuda_nominada_y_los_demas_comandos_siguen_sin_motivo(tipo: str) -> None:
    """D10: `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` quedan fuera del alcance aprobado."""
    assert tipo not in tipos_que_devuelven_motivo_de_auditoria()
    assert registro.resolver_handler(tipo, 1).tipo == tipo  # el tipo existe: la prueba mira algo


def test_la_deteccion_distingue_un_handler_que_devuelve_el_dato_de_uno_que_no() -> None:
    """Verificación en negativo: la misma inspección sobre dos funciones de prueba, una que
    construye el dato y otra que solo lo menciona en un comentario y en un docstring."""

    def con_dato() -> object:
        return DatosDeAuditoria(motivo_id=None)

    def sin_dato() -> object:
        """Devuelve DatosDeAuditoria (solo en este docstring)."""
        # DatosDeAuditoria
        return None

    assert NOMBRE_DEL_DATO in _nombres(con_dato.__code__)
    assert NOMBRE_DEL_DATO not in _nombres(sin_dato.__code__)
