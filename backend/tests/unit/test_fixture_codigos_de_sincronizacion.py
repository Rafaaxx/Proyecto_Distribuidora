"""Change 22c, tarea 3.2 (`design.md` D5; reglas SYN-06, SYN-07, INV-17): el fixture compartido
`shared/fixtures/sync/codigos-de-sincronizacion.json` lista los códigos que el teléfono traduce.

- `observaciones`: exactamente el catálogo de observaciones del servidor (SYN-07).
- `rechazos`: los códigos con que puede volver rechazada una venta sin conexión (SYN-06). Cada uno
  es el `codigo` de un error del bus (`app.commands.errores`), de `ventas` o de la evaluación de
  crédito, o el rechazo por dispositivo dado de baja. Ningún código de observación y ningún
  código que solo rige con conexión (INV-17: sin conexión no se rechaza por reglas de negocio).
- La prueba del teléfono (Vitest) exige un texto aprobado por cada código del fixture.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from app.commands import errores as errores_del_bus
from app.core.errors import DomainError
from app.modules.clientes.domain import errores as errores_de_credito
from app.modules.stock.domain import errores as errores_de_stock
from app.modules.sync.models import CODIGOS_OBSERVACION
from app.modules.sync.service import CODIGO_DISPOSITIVO_REVOCADO
from app.modules.ventas import service as servicio_de_ventas
from app.modules.ventas.domain import anulacion as dominio_de_anulacion
from app.modules.ventas.domain import errores as errores_de_ventas

RUTA = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "fixtures"
    / "sync"
    / "codigos-de-sincronizacion.json"
)

# Reglas que rigen solo con conexión: sin conexión se aceptan con una observación (SYN-05).
SOLO_CON_CONEXION = frozenset(
    {
        "STOCK_INSUFICIENTE",
        "PRECIO_DIFIERE",
        "MOMENTO_FUERA_DE_RANGO",
        "UBICACION_TOMADA",
        "CLIENTE_SUSPENDIDO",
        "CLIENTE_INACTIVO",
        "CONSUMIDOR_FINAL_CONTADO",
        "AUTORIZACION_REQUERIDA",
        "AUTORIZACION_CREDITO_REQUERIDA",
        "PERMISO_REQUERIDO",
        "PRODUCTO_INACTIVO",
        "PRESENTACION_NO_VENDIBLE",
    }
)


def _cargar() -> dict[str, list[str]]:
    return json.loads(RUTA.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _codigos_de_errores(*modulos: object) -> set[str]:
    codigos: set[str] = set()
    for modulo in modulos:
        for _, clase in inspect.getmembers(modulo, inspect.isclass):
            if issubclass(clase, DomainError) and "codigo" in vars(clase):
                codigos.add(str(vars(clase)["codigo"]))
    return codigos


def test_syn07_las_observaciones_son_exactamente_el_catalogo_del_servidor() -> None:
    observaciones = _cargar()["observaciones"]

    assert len(observaciones) == len(set(observaciones))
    assert set(observaciones) == set(CODIGOS_OBSERVACION)
    assert len(observaciones) == 16


def test_syn06_cada_rechazo_es_el_codigo_de_un_error_del_bus_o_de_ventas() -> None:
    existentes = _codigos_de_errores(errores_del_bus, errores_de_ventas, errores_de_credito) | {
        CODIGO_DISPOSITIVO_REVOCADO
    }

    rechazos = _cargar()["rechazos"]

    assert rechazos
    assert len(rechazos) == len(set(rechazos))
    assert set(rechazos) <= existentes, sorted(set(rechazos) - existentes)


def test_syn06_los_rechazos_cubren_el_bus_y_la_validacion_de_la_venta() -> None:
    """Triangulación: la lista incluye los rechazos del bus que alcanzan a toda venta sin conexión
    y los de la validación de la propia venta (la lista que fija esta tarea)."""
    rechazos = set(_cargar()["rechazos"])

    assert {
        "JORNADA_INEXISTENTE",
        "JORNADA_REQUERIDA",
        "JORNADA_AJENA",
        "DISPOSITIVO_REVOCADO",
        "COMANDO_INCONSISTENTE",
        "MODO_NO_ADMITIDO_PARA_TIPO",
        "TIPO_DE_COMANDO_DESCONOCIDO",
        "VERSION_DE_COMANDO_SIN_HANDLER",
        "CONTENIDO_DE_COMANDO_INVALIDO",
    } <= rechazos
    assert {
        "TOTALES_INCONSISTENTES",
        "CREDITO_INCONSISTENTE",
        "VENTA_DUPLICADA",
        "NUMERO_DUPLICADO",
        "NUMERO_INVALIDO",
        "VENTA_SIN_LINEAS",
        "LINEAS_INVALIDAS",
        "CANTIDAD_INVALIDA",
        "LINEA_DUPLICADA",
        "RECURSO_NO_ENCONTRADO",
        "VERSION_NO_PERMITIDA",
        "MOTIVO_INVALIDO",
    } <= rechazos


@pytest.mark.parametrize("codigo", sorted(SOLO_CON_CONEXION))
def test_inv17_un_codigo_que_solo_rige_con_conexion_no_es_un_rechazo_sin_conexion(
    codigo: str,
) -> None:
    assert codigo not in _cargar()["rechazos"]


def test_syn07_ningun_codigo_de_observacion_figura_como_rechazo() -> None:
    """Un código es una observación (aceptada) o un rechazo, nunca las dos (por ejemplo
    `DESCUENTO_DIFIERE`: observación sin conexión, error solo con conexión)."""
    datos = _cargar()

    assert not set(datos["observaciones"]) & set(datos["rechazos"])


# --- Change 22d, tarea 4.2 (D11; SYN-06, SYN-07): los códigos de la anulación sin conexión --------

# Los rechazos del bus que alcanzan a todo comando `OFFLINE` (jornada del sobre, dispositivo dado de
# baja, sobre mal armado), antes del handler.
RECHAZOS_DEL_BUS_PARA_TODO_COMANDO = frozenset(
    {
        "JORNADA_INEXISTENTE",
        "JORNADA_REQUERIDA",
        "JORNADA_AJENA",
        "DISPOSITIVO_REVOCADO",
        "COMANDO_INCONSISTENTE",
        "MODO_NO_ADMITIDO_PARA_TIPO",
        "TIPO_DE_COMANDO_DESCONOCIDO",
        "VERSION_DE_COMANDO_SIN_HANDLER",
        "CONTENIDO_DE_COMANDO_INVALIDO",
    }
)
# `anular_venta` también levanta `RecursoNoEncontradoError`, pero solo con conexión (el 404 del
# REST): sin conexión la venta o el motivo inexistentes son `VENTA_INEXISTENTE` y `MOTIVO_INVALIDO`.
SOLO_CON_CONEXION_DE_LA_ANULACION = frozenset({"RECURSO_NO_ENCONTRADO"})
# Lo que levanta `stock` al reingresar y no se ve leyendo el servicio de `ventas`.
RECHAZOS_DEL_REINGRESO = frozenset({"UBICACION_INACTIVA"})
OBSERVACIONES_DE_LA_ANULACION = frozenset(
    {"PERMISO_REVOCADO", "JORNADA_LIBERADA", "UBICACION_TOMADA_AL_SINCRONIZAR"}
)


def _levantados_leyendo_la_anulacion() -> set[str]:
    """Los códigos de los errores que nombran `anular_venta`, su validación del motivo y el
    dominio de la anulación (leyendo el código fuente, así un rechazo nuevo rompe la prueba)."""
    fuentes = [
        inspect.getsource(servicio_de_ventas.anular_venta),
        inspect.getsource(servicio_de_ventas._validar_motivo_de_anulacion_de_venta),
        inspect.getsource(dominio_de_anulacion),
    ]
    clases = {
        nombre: clase
        for modulo in (errores_de_ventas, dominio_de_anulacion)
        for nombre, clase in inspect.getmembers(modulo, inspect.isclass)
        if issubclass(clase, DomainError) and "codigo" in vars(clase)
    }
    nombres = {
        nombre
        for fuente in fuentes
        for nombre in re.findall(r"raise (\w+Error)\(", fuente)
        if nombre in clases
    }
    return {str(vars(clases[nombre])["codigo"]) for nombre in nombres}


def test_syn06_el_fixture_separa_los_rechazos_por_tipo_de_operacion() -> None:
    datos = _cargar()

    assert "VENTA_INEXISTENTE" in datos["rechazos_de_anulacion"]
    assert "VENTA_INEXISTENTE" not in datos["rechazos"]
    assert "TOTALES_INCONSISTENTES" in datos["rechazos"]
    assert "TOTALES_INCONSISTENTES" not in datos["rechazos_de_anulacion"]


def test_syn06_cada_rechazo_de_la_anulacion_existe_en_el_bus_en_ventas_o_en_stock() -> None:
    existentes = _codigos_de_errores(errores_del_bus, errores_de_ventas, errores_de_stock) | {
        CODIGO_DISPOSITIVO_REVOCADO
    }

    rechazos = _cargar()["rechazos_de_anulacion"]

    assert len(rechazos) == len(set(rechazos))
    assert set(rechazos) <= existentes, sorted(set(rechazos) - existentes)


def test_syn06_los_rechazos_de_la_anulacion_son_el_bus_mas_lo_que_levanta_anular_venta() -> None:
    """La lista se fija recorriendo el bus (los rechazos que alcanzan a todo comando sin conexión)
    y `anular_venta`; ni más ni menos, y con `VENTA_INEXISTENTE` incluido."""
    levantados = _levantados_leyendo_la_anulacion()
    esperados = (
        RECHAZOS_DEL_BUS_PARA_TODO_COMANDO
        | (levantados - SOLO_CON_CONEXION_DE_LA_ANULACION)
        | RECHAZOS_DEL_REINGRESO
    )

    assert {
        "VENTA_INEXISTENTE",
        "VENTA_YA_ANULADA",
        "DEVOLUCION_INVALIDA",
        "CONSUMIDOR_FINAL_SIN_DEVOLUCION",
        "OBSERVACION_INVALIDA",
        "MOTIVO_INVALIDO",
        "JORNADA_AJENA",
    } <= levantados
    assert set(_cargar()["rechazos_de_anulacion"]) == esperados


@pytest.mark.parametrize("codigo", sorted(SOLO_CON_CONEXION | {"UBICACION_TOMADA"}))
def test_inv17_un_codigo_que_solo_rige_con_conexion_no_es_un_rechazo_de_la_anulacion(
    codigo: str,
) -> None:
    """La ubicación tomada se acepta con observación sin conexión (D2), igual que la venta."""
    assert codigo not in _cargar()["rechazos_de_anulacion"]


def test_syn07_las_observaciones_de_la_anulacion_son_las_tres_de_la_spec_y_del_catalogo() -> None:
    observaciones = _cargar()["observaciones_de_anulacion"]

    assert len(observaciones) == len(set(observaciones))
    assert set(observaciones) == OBSERVACIONES_DE_LA_ANULACION
    assert set(observaciones) <= set(CODIGOS_OBSERVACION)
    assert not set(observaciones) & set(_cargar()["rechazos_de_anulacion"])
