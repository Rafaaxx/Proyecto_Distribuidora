"""Change 23, tarea 2.1 (`design.md` D2; spec `sync/lote-de-comandos`, requisito "La cobranza del
teléfono se acepta por el lote con el contrato fijado"), contra PostgreSQL real y por
`procesar_lote`. Es una prueba de CARACTERIZACIÓN: el servidor no cambia (ADR-052); si una de
estas pruebas exigiera código de producción, se detiene el apply y se consulta.

- Los sobres del fixture `shared/fixtures/sync/cobranza-registrar-offline.json`, con los
  identificadores reales de la base de prueba, los acepta el lote con la jornada del sobre.
- Una venta y una cobranza al mismo cliente en el mismo lote se procesan en orden (SYN-03).
- Un cliente inexistente se rechaza sin efectos y el lote sigue; medios que no suman el importe,
  `MEDIOS_NO_SUMAN_IMPORTE` (INV-08); un doble envío devuelve lo mismo y baja el saldo una vez
  (INV-06).

Reglas citadas: COB-01, COB-02, COB-03, SYN-01, SYN-02, SYN-03, SYN-05, SYN-06, INV-06, INV-08,
INV-17, INV-21.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_ventas_offline import Ruta, lote
from ventas_confirmar_utiles import PERMISOS_DE_VENTA, EntornoVenta

from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

RUTA_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "fixtures"
    / "sync"
    / "cobranza-registrar-offline.json"
)
PERMISOS_DEL_VENDEDOR = PERMISOS_DE_VENTA | {"REGISTRAR_COBRANZA"}


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session, permisos=PERMISOS_DEL_VENDEDOR)


def _item_del_fixture(
    nombre: str,
    entorno: EntornoVenta,
    jornada_id: UUID,
    *,
    operation_id: UUID | None = None,
    cliente_id: UUID | None = None,
    secuencia: int | None = None,
) -> ItemLote:
    crudo = json.loads(RUTA_FIXTURE.read_text(encoding="utf-8"))
    reales = {
        "{{operation_id}}": str(operation_id or uuid4()),
        "{{usuario_id}}": str(entorno.usuario_id),
        "{{dispositivo_id}}": str(entorno.dispositivo_id),
        "{{jornada_id}}": str(jornada_id),
        "{{cobranza_id}}": str(uuid4()),
        "{{cliente_id}}": str(cliente_id or entorno.cliente_id),
        "{{medio_efectivo_id}}": str(entorno.efectivo_id),
        "{{medio_transferencia_id}}": str(entorno.transferencia_id),
    }
    assert set(reales) == set(crudo["simbolos"]), "el fixture declara símbolos desconocidos"
    texto = json.dumps(crudo["sobres"][nombre])
    for simbolo, valor in reales.items():
        texto = texto.replace(simbolo, valor)
    sobre: dict[str, Any] = json.loads(texto)
    return ItemLote(
        operation_id=UUID(sobre["operation_id"]),
        tipo=sobre["tipo"],
        version=sobre["version"],
        modo=sobre["modo"],
        usuario_id=UUID(sobre["usuario_id"]),
        dispositivo_id=UUID(sobre["dispositivo_id"]),
        occurred_at=datetime.fromisoformat(sobre["occurred_at"]),
        secuencia=secuencia if secuencia is not None else sobre["secuencia"],
        app_version=sobre["app_version"],
        contenido=sobre["contenido"],
        jornada_id=UUID(sobre["jornada_id"]),
    )


def _observaciones(entorno: EntornoVenta) -> list[Observacion]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Observacion).where(Observacion.organizacion_id == entorno.org)
        ).all()
    )


def _comandos(entorno: EntornoVenta, operation_id: UUID) -> list[Comando]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Comando).where(
                Comando.organizacion_id == entorno.org, Comando.operation_id == operation_id
            )
        ).all()
    )


# --- Escenario: "Sobre del teléfono aceptado" ---------------------------------------------------


def test_cob01_el_sobre_del_fixture_se_acepta_con_la_jornada_del_sobre(
    entorno: EntornoVenta,
) -> None:
    """$150.000 de saldo y una cobranza de $50.000 con $30.000 en efectivo y $20.000 por
    transferencia n.º 0042: ACEPTADO, saldo $100.000, la cobranza lleva la jornada del sobre."""
    jornada = entorno.crear_jornada()
    item = _item_del_fixture("dos_medios_con_referencia", entorno, jornada)

    resultado = lote(entorno, item)[item.operation_id]

    assert resultado.estado == "ACEPTADO", resultado
    assert resultado.resultado is not None
    assert resultado.resultado["saldo"] == "100000.00"
    assert _observaciones(entorno) == []
    assert entorno.saldo() == Decimal("100000.00")
    (cobranza,) = entorno.cobranzas()
    assert cobranza.jornada_id == jornada
    assert cobranza.origen == "INDEPENDIENTE"
    assert [(m.importe, m.referencia) for m in entorno.medios_de_cobranza()] == [
        (Decimal("30000.00"), None),
        (Decimal("20000.00"), "0042"),
    ]


@pytest.mark.parametrize(
    ("nombre", "saldo_final", "observacion"),
    [
        ("un_medio", "100000.00", None),
        ("con_observacion", "137499.50", "Pago de la cuota de octubre"),
    ],
)
def test_cob02_cada_sobre_del_fixture_se_acepta_sin_observaciones_del_servidor(
    entorno: EntornoVenta, nombre: str, saldo_final: str, observacion: str | None
) -> None:
    item = _item_del_fixture(nombre, entorno, entorno.crear_jornada())

    resultado = lote(entorno, item)[item.operation_id]

    assert resultado.estado == "ACEPTADO", resultado
    assert _observaciones(entorno) == []
    assert entorno.saldo() == Decimal(saldo_final)
    (cobranza,) = entorno.cobranzas()
    assert cobranza.observacion == observacion


# --- Escenario: "Venta y cobranza en el mismo lote" ---------------------------------------------


def test_syn03_venta_y_cobranza_del_mismo_cliente_se_procesan_en_orden(
    entorno: EntornoVenta,
) -> None:
    """Venta de $31.250 (secuencia 7) y cobranza de $50.000 (secuencia 8) al mismo cliente:
    el saldo refleja las dos ($150.000 + $31.250 - $50.000)."""
    ruta = Ruta(entorno)
    venta = ruta.item(ruta.contenido(), secuencia=7)
    cobranza = _item_del_fixture("dos_medios_con_referencia", entorno, ruta.jornada_id, secuencia=8)

    resultados = lote(entorno, venta, cobranza)

    assert resultados[venta.operation_id].estado in {"ACEPTADO", "ACEPTADO_CON_OBSERVACIONES"}
    assert resultados[cobranza.operation_id].estado == "ACEPTADO"
    assert entorno.saldo() == Decimal("131250.00")
    (cobranza_guardada,) = entorno.cobranzas()
    assert cobranza_guardada.jornada_id == ruta.jornada_id
    # El servidor guarda la secuencia de cada comando: la venta (7) antes que la cobranza (8).
    (comando_venta,) = _comandos(entorno, venta.operation_id)
    (comando_cobranza,) = _comandos(entorno, cobranza.operation_id)
    assert (comando_venta.secuencia, comando_cobranza.secuencia) == (7, 8)


# --- Escenario: "Cliente inexistente" -----------------------------------------------------------


def test_inv21_un_cliente_inexistente_se_rechaza_sin_efectos_y_el_lote_sigue(
    entorno: EntornoVenta,
) -> None:
    jornada = entorno.crear_jornada()
    inexistente = _item_del_fixture("un_medio", entorno, jornada, cliente_id=uuid4(), secuencia=8)
    siguiente = _item_del_fixture("un_medio", entorno, jornada, secuencia=9)

    resultados = lote(entorno, inexistente, siguiente)

    rechazado = resultados[inexistente.operation_id]
    assert (rechazado.estado, rechazado.error_codigo) == ("RECHAZADO", "RECURSO_NO_ENCONTRADO")
    assert _comandos(entorno, inexistente.operation_id) == []
    assert resultados[siguiente.operation_id].estado == "ACEPTADO"
    assert len(entorno.cobranzas()) == 1
    assert entorno.saldo() == Decimal("100000.00")


def test_inv21_un_medio_inexistente_se_rechaza_como_recurso_no_encontrado(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: la dependencia inexistente puede ser el medio y no el cliente."""
    item = _item_del_fixture("un_medio", entorno, entorno.crear_jornada())
    item.contenido["medios"][0]["medio_pago_id"] = str(uuid4())

    resultado = lote(entorno, item)[item.operation_id]

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "RECURSO_NO_ENCONTRADO")
    assert entorno.cobranzas() == []
    assert entorno.saldo() == Decimal("150000.00")


# --- Escenario: "Medios que no suman el importe" ------------------------------------------------


def test_inv08_medios_que_no_suman_el_importe_se_rechazan_sin_efectos(
    entorno: EntornoVenta,
) -> None:
    item = _item_del_fixture("dos_medios_con_referencia", entorno, entorno.crear_jornada())
    item.contenido["medios"][0]["importe"] = "29000.00"  # suman 49.000 y el importe es 50.000

    resultado = lote(entorno, item)[item.operation_id]

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "MEDIOS_NO_SUMAN_IMPORTE")
    assert _comandos(entorno, item.operation_id) == []
    assert entorno.cobranzas() == []
    assert entorno.saldo() == Decimal("150000.00")
    assert _observaciones(entorno) == []


def test_inv08_medios_que_suman_de_mas_tambien_se_rechazan(entorno: EntornoVenta) -> None:
    """Triangulación: la suma por encima del importe es igual de inválida."""
    item = _item_del_fixture("dos_medios_con_referencia", entorno, entorno.crear_jornada())
    item.contenido["medios"][1]["importe"] = "21000.00"

    resultado = lote(entorno, item)[item.operation_id]

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "MEDIOS_NO_SUMAN_IMPORTE")
    assert entorno.saldo() == Decimal("150000.00")


# --- Escenario: "Doble envío" -------------------------------------------------------------------


def test_inv06_el_doble_envio_devuelve_lo_mismo_y_el_saldo_baja_una_sola_vez(
    entorno: EntornoVenta,
) -> None:
    item = _item_del_fixture("dos_medios_con_referencia", entorno, entorno.crear_jornada())

    primero = lote(entorno, item)[item.operation_id]
    segundo = lote(entorno, item)[item.operation_id]

    assert primero.estado == "ACEPTADO"
    assert (segundo.estado, segundo.resultado, segundo.observaciones) == (
        primero.estado,
        primero.resultado,
        primero.observaciones,
    )
    assert len(entorno.cobranzas()) == 1
    assert entorno.saldo() == Decimal("100000.00")


def test_inv06_el_doble_envio_con_observaciones_devuelve_las_mismas_sin_duplicarlas(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: un medio dado de baja después del bootstrap deja `MEDIO_INACTIVO`; el
    reenvío devuelve la misma observación y no crea otra (INV-17, SYN-07)."""
    item = _item_del_fixture("un_medio", entorno, entorno.crear_jornada())
    entorno.desactivar_medio(entorno.efectivo_id)

    primero = lote(entorno, item)[item.operation_id]
    segundo = lote(entorno, item)[item.operation_id]

    assert primero.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert [o.codigo for o in primero.observaciones] == ["MEDIO_INACTIVO"]
    assert [o.codigo for o in segundo.observaciones] == ["MEDIO_INACTIVO"]
    assert [o.codigo for o in _observaciones(entorno)] == ["MEDIO_INACTIVO"]
    assert entorno.saldo() == Decimal("100000.00")
