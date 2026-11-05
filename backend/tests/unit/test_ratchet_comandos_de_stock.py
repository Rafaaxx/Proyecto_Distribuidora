"""Change 14, tarea 11.1: ratchets de los comandos de transferencias y ajustes.

- Los cuatro tipos nuevos (`STOCK_TRANSFERIR`, `STOCK_AJUSTAR`, `STOCK_TRANSFERENCIA_ANULAR`,
  `STOCK_AJUSTE_ANULAR`) están en el catálogo de comandos como solo `ONLINE` (`02` §6.5).
- D10 (`design.md`): EXACTAMENTE `STOCK_AJUSTAR`, `STOCK_TRANSFERENCIA_ANULAR` y
  `STOCK_AJUSTE_ANULAR` devuelven el motivo para la fila de auditoría del bus (AUD-02). Los
  demás handlers, incluidos `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` (deuda nominada, fuera
  del alcance aprobado), no lo devuelven. Un cuarto comando que empiece a devolverlo, o uno de
  los cuatro que deje de hacerlo, rompe esta prueba y obliga a revisar la enmienda de ADR-022.

CÓMO SE DETECTA "devuelve el motivo": se inspecciona el BYTECODE de la función del handler --
`co_names` de su `__code__` -- buscando el nombre `DatosDeAuditoria`, igual que
`test_bus_cobertura_rutas_de_escritura.py` busca `procesar_comando`: un comentario o un docstring
que lo mencionen no hacen pasar la prueba. El comportamiento real (una sola fila de auditoría con
el motivo) lo prueban `test_stock_ajustar.py`, `test_stock_transferencia_anular.py` y
`test_stock_ajuste_anular.py`.

Reglas citadas: AUD-02, SYN-02, ADR-022.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import app.main  # noqa: F401  (el arranque importa los módulos que registran los handlers)
import app.modules.stock
from app.commands import registro
from app.commands.auditoria import DatosDeAuditoria
from app.commands.catalogo import tipo_declarado
from app.commands.errores import VersionDeComandoSinHandlerError

TIPOS_NUEVOS = (
    "STOCK_TRANSFERIR",
    "STOCK_AJUSTAR",
    "STOCK_TRANSFERENCIA_ANULAR",
    "STOCK_AJUSTE_ANULAR",
)
TIPOS_CON_MOTIVO_DE_AUDITORIA = frozenset(
    {
        "STOCK_AJUSTAR",
        "STOCK_TRANSFERENCIA_ANULAR",
        "STOCK_AJUSTE_ANULAR",
        "JORNADA_LIBERAR",
        "COBRANZA_ANULAR",
        "VENTA_CONFIRMAR",
        "VENTA_ANULAR",
    }
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


def test_exactamente_siete_comandos_devuelven_el_motivo_para_la_auditoria() -> None:
    """Change 17, tarea 10.2 (D15, AUD-02): el ratchet pasó de cuatro a cinco con
    `COBRANZA_ANULAR`; `COBRANZA_REGISTRAR` queda auditado solo por la fila del bus. Change 18a,
    tarea 10.1 (D20, AUD-01): pasa a seis con `VENTA_CONFIRMAR` (otra lista o versión no vigente;
    la fila lleva el motivo y la observación con lista y versión). Change 19, tarea 7.6 (D15,
    AUD-01, AUD-02): pasa a siete con `VENTA_ANULAR` (motivo de la anulación y, en la observación,
    la cobranza anulada)."""
    assert tipos_que_devuelven_motivo_de_auditoria() == TIPOS_CON_MOTIVO_DE_AUDITORIA


NOMBRES_DE_LA_CONSTANCIA = frozenset(
    {"observacion_de_ubicacion_tomada", "constancia_de_ubicacion_tomada"}
)
TIPOS_CON_CONSTANCIA_DE_UBICACION_TOMADA = frozenset(
    {
        "STOCK_INICIAL_REGISTRAR",
        "STOCK_TRANSFERIR",
        "STOCK_AJUSTAR",
        "STOCK_TRANSFERENCIA_ANULAR",
        "STOCK_AJUSTE_ANULAR",
        "COMPRA_CONFIRMAR",
        "COMPRA_ANULAR",
        "IMPORTACION_REGISTRAR",
        "VENTA_CONFIRMAR",
        "VENTA_ANULAR",
    }
)


def test_exactamente_diez_comandos_pueden_devolver_la_constancia_de_ubicacion_tomada() -> None:
    """Change 15, tarea 8.5 (D8): los cinco de stock que mueven mercadería, `COMPRA_CONFIRMAR`,
    `COMPRA_ANULAR` e `IMPORTACION_REGISTRAR`; change 18a, tarea 10.1 (STK-09, decisión del
    2026-10-20): también `VENTA_CONFIRMAR`; change 19, tarea 7.6 (D6, D15): también `VENTA_ANULAR`
    (la excepción de `LIBERAR_UBICACION` al reingresar). Un handler nuevo que la devuelva (o uno que
    deje de hacerlo) rompe esta prueba y obliga a revisar ADR-022 y ADR-049."""
    devuelven = frozenset(
        registrado.tipo
        for registrado in registro._REGISTRO.values()  # noqa: SLF001
        if NOMBRES_DE_LA_CONSTANCIA & _nombres(registrado.funcion.__code__)
    )

    assert devuelven == TIPOS_CON_CONSTANCIA_DE_UBICACION_TOMADA


@pytest.mark.parametrize(
    "tipo",
    [
        "STOCK_TRANSFERIR",
        "COMPRA_ANULAR",
        "PAGO_PROVEEDOR_ANULAR",
        "STOCK_INICIAL_REGISTRAR",
        "COBRANZA_REGISTRAR",
    ],
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


# --- jornadas (change 15, tarea 4.5) ---------------------------------------------------------

TIPOS_DE_JORNADA = ("JORNADA_ABRIR", "JORNADA_RENDIR", "JORNADA_CERRAR", "JORNADA_LIBERAR")


@pytest.mark.parametrize("tipo", TIPOS_DE_JORNADA)
def test_los_tipos_de_jornada_estan_declarados_solo_online_y_con_su_handler(tipo: str) -> None:
    """Con `app.main` importado, el tipo está en el catálogo y en el registro de handlers
    (`02` §6.5): sin el import de `jornadas_commands` (y, desde el change 24, de
    `rendicion_commands`, que registra `JORNADA_RENDIR` v2) en `app/main.py` no estaría."""
    declarado = tipo_declarado(tipo)

    assert declarado is not None, f"{tipo} no está en el catálogo de comandos"
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    version = 2 if tipo == "JORNADA_RENDIR" else 1
    assert registro.resolver_handler(tipo, version).tipo == tipo


def _importa_service(codigo_fuente: str) -> bool:
    """Si el código importa `app.modules.stock.service` (con `import x.service`, `from x
    import service` o `from x.service import y`)."""
    arbol = ast.parse(codigo_fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            if any(alias.name == "app.modules.stock.service" for alias in nodo.names):
                return True
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module == "app.modules.stock.service":
                return True
            if nodo.module == "app.modules.stock" and any(
                alias.name == "service" for alias in nodo.names
            ):
                return True
    return False


def test_jornadas_casos_no_importa_service_para_evitar_el_ciclo() -> None:
    """D1: `service.py` delega en `jornadas_casos.py`; si este importara `service.py` habría
    un ciclo. Arquitectura: ninguno de los archivos de jornadas por debajo de `service` lo
    importa."""
    base = Path(app.modules.stock.__file__).parent
    for nombre in ("jornadas_casos.py", "jornadas_repository.py", "domain/jornadas.py"):
        assert not _importa_service((base / nombre).read_text(encoding="utf-8")), nombre


def test_los_archivos_de_la_rendicion_no_importan_el_service_propio() -> None:
    """Change 24, tarea 11.1 (D3): `service.py` delega en `rendicion_casos.py` (que recibe la puerta
    del libro y la transferencia como parámetro); ningún archivo de la rendición por debajo de
    `service` lo importa, así que no hay ciclo. Los comandos (`rendicion_commands.py`) sí usan
    `service.py`, como los demás handlers."""
    base = Path(app.modules.stock.__file__).parent
    for nombre in (
        "rendicion_casos.py",
        "rendicion_repository.py",
        "domain/rendicion.py",
        "domain/resumen.py",
    ):
        assert not _importa_service((base / nombre).read_text(encoding="utf-8")), nombre
    assert _importa_service((base / "rendicion_commands.py").read_text(encoding="utf-8"))


# --- la rendición (change 24, tarea 11.1) ----------------------------------------------------


def test_la_entrega_del_dia_es_solo_offline_y_tiene_handler_v1() -> None:
    """`JORNADA_ENTREGAR` solo viaja por el lote del teléfono (RUT-05, `02` §6.5)."""
    declarado = tipo_declarado("JORNADA_ENTREGAR")

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (False, True)
    assert declarado.permisos == ("ABRIR_JORNADA",)
    assert registro.resolver_handler("JORNADA_ENTREGAR", 1).tipo == "JORNADA_ENTREGAR"


def test_la_rendicion_no_tiene_version_1_y_el_cierre_conserva_las_dos() -> None:
    """D2, D6: `JORNADA_RENDIR` v1 se retira (responde `VERSION_DE_COMANDO_SIN_HANDLER`);
    `JORNADA_CERRAR` v1 (sin devolución) sigue registrada junto a la v2."""
    with pytest.raises(VersionDeComandoSinHandlerError):
        registro.resolver_handler("JORNADA_RENDIR", 1)
    assert registro.resolver_handler("JORNADA_RENDIR", 2).tipo == "JORNADA_RENDIR"
    assert registro.resolver_handler("JORNADA_CERRAR", 1).tipo == "JORNADA_CERRAR"
    assert registro.resolver_handler("JORNADA_CERRAR", 2).tipo == "JORNADA_CERRAR"


@pytest.mark.parametrize("tipo", ["JORNADA_ENTREGAR", "JORNADA_RENDIR", "JORNADA_CERRAR"])
def test_la_entrega_la_rendicion_y_el_cierre_no_llevan_motivo_ni_constancia(tipo: str) -> None:
    """D5, D6: las diferencias no llevan motivo (la fila de auditoría del bus alcanza) y la
    devolución del remanente pasa STK-09 por la rendición, no por la excepción de
    `LIBERAR_UBICACION`: ninguno devuelve motivo ni constancia de ubicación tomada."""
    handlers = [h for h in registro._REGISTRO.values() if h.tipo == tipo]  # noqa: SLF001

    assert handlers
    for handler in handlers:
        nombres = _nombres(handler.funcion.__code__)
        assert NOMBRE_DEL_DATO not in nombres
        assert not (NOMBRES_DE_LA_CONSTANCIA & nombres)


@pytest.mark.parametrize(
    "linea",
    [
        "from app.modules.stock import service",
        "from app.modules.stock import service as stock_service",
        "from app.modules.stock.service import abrir_jornada",
        "import app.modules.stock.service",
    ],
)
def test_la_deteccion_del_ciclo_encuentra_cada_forma_de_importar_service(linea: str) -> None:
    """Verificación en negativo de la prueba de arriba."""
    assert _importa_service(f"from __future__ import annotations\n{linea}\n")


@pytest.mark.parametrize(
    "linea",
    [
        "from app.modules.stock import jornadas_repository",
        "from app.modules.stock import models",
        "from app.modules.identidad import service",
    ],
)
def test_la_deteccion_del_ciclo_no_marca_otros_imports(linea: str) -> None:
    assert not _importa_service(f"{linea}\n")
