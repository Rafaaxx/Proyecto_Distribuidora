"""Change 17, tarea 13.2 (`design.md` D13 = C; spec `cobranzas/registro-de-cobranzas`, requisito
"Una cobranza sin conexión nunca se rechaza por reglas de negocio"): `COBRANZA_REGISTRAR` en modo
`OFFLINE` por `procesar_lote`, contra PostgreSQL real.

- Se rechaza solo lo malformado o inconsistente: medios que no suman el importe (INV-08), cliente o
  medio inexistente o de otra organización, y los casos de la jornada (`test_lote_jornada_offline`).
  Sin registro del comando ni observación.
- Se acepta con observación: `MEDIO_INACTIVO` por cada línea con el medio desactivado,
  `REFERENCIA_FALTANTE` por cada línea sin la referencia que su medio exige (o con solo espacios;
  se guarda nula), `CLIENTE_NO_HABILITADO` para el consumidor final. Conviven con `PERMISO_REVOCADO`
  y `JORNADA_LIBERADA`; un doble envío devuelve las mismas sin duplicarlas.
- Con conexión no cambia nada (TR-09): `MEDIO_PAGO_INACTIVO` y `REFERENCIA_OBLIGATORIA`, sin
  observaciones.

Reglas citadas: SYN-05, SYN-06, SYN-07, SYN-10, INV-06, INV-08, INV-17, TR-09, CLI-03.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import MOMENTO, RELOJ, Entorno
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.cobranzas.domain.errores import MedioPagoInactivoError
from app.modules.configuracion.domain.medios import ReferenciaObligatoriaError
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _enviar(
    entorno: Entorno,
    contenido: dict[str, Any],
    *,
    jornada_id: UUID | None,
    modo: str = "OFFLINE",
    operation_id: UUID | None = None,
) -> sync_service.ResultadoItemLote:
    item = ItemLote(
        operation_id=operation_id or uuid4(),
        tipo="COBRANZA_REGISTRAR",
        version=1,
        modo=modo,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=contenido,
        jornada_id=jornada_id,
    )
    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )
    return resultado


def _observaciones(entorno: Entorno) -> list[Observacion]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Observacion)
            .where(Observacion.organizacion_id == entorno.org)
            .order_by(Observacion.codigo, Observacion.detalle["medio"].astext)
        ).all()
    )


def _codigos(entorno: Entorno) -> list[str]:
    return [o.codigo for o in _observaciones(entorno)]


def _comandos(entorno: Entorno, operation_id: UUID) -> list[Comando]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Comando).where(
                Comando.organizacion_id == entorno.org, Comando.operation_id == operation_id
            )
        ).all()
    )


# --- sin observaciones (SYN-05) ---------------------------------------------------------------


def test_medios_activos_con_referencia_se_aceptan_sin_observaciones(entorno: Entorno) -> None:
    """Escenario base (D13 punto 3): medios activos y con la referencia que exigen."""
    jornada = entorno.crear_jornada()

    resultado = _enviar(entorno, entorno.contenido(), jornada_id=jornada)

    assert resultado.estado == "ACEPTADO"
    assert _observaciones(entorno) == []
    assert entorno.saldo() == Decimal("100000.00")
    (cobranza,) = entorno.cobranzas()
    assert [m.referencia for m in entorno.medios_de_cobranza()] == [None, "0042"]
    assert cobranza.jornada_id == jornada


# Escenario: "Cliente inactivo sin conexión"
def test_un_cliente_inactivo_se_acepta_sin_observacion(entorno: Entorno) -> None:
    """D4, D13 punto 3, INV-17: el estado del cliente no se evalúa sin conexión."""
    inactivo = entorno.crear_cliente(estado="INACTIVO", nombre="Almacén Don Pedro")
    entorno.cargar_saldo_inicial(inactivo, "12000.00")
    entorno.sesion.commit()
    contenido = entorno.contenido(
        cliente_id=str(inactivo),
        importe="12000.00",
        medios=entorno.medios((entorno.efectivo_id, "12000.00", None)),
    )

    resultado = _enviar(entorno, contenido, jornada_id=entorno.crear_jornada())

    assert resultado.estado == "ACEPTADO"
    assert _observaciones(entorno) == []
    assert entorno.saldo(inactivo) == Decimal("0.00")


# --- MEDIO_INACTIVO (SYN-07, D13 punto 2) -------------------------------------------------------


def test_syn07_un_medio_desactivado_despues_de_abrir_la_jornada_se_acepta_con_medio_inactivo(
    entorno: Entorno,
) -> None:
    """La vendedora cobra $10.000,00 con "Billetera"; la administración la desactiva; al
    sincronizar la cobranza se acepta, el saldo baja y queda `MEDIO_INACTIVO` con la línea."""
    billetera = entorno.crear_medio("Billetera", requiere_referencia=False)
    jornada = entorno.crear_jornada()
    entorno.sesion.commit()
    entorno.desactivar_medio(billetera)
    cobranza_id = uuid4()
    contenido = entorno.contenido(
        cobranza_id=str(cobranza_id),
        importe="10000.00",
        medios=entorno.medios((billetera, "10000.00", None)),
    )

    resultado = _enviar(entorno, contenido, jornada_id=jornada)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert entorno.saldo() == Decimal("140000.00")
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "MEDIO_INACTIVO"
    assert observacion.detalle == {
        "medio": 0,
        "medio_pago_id": str(billetera),
        "nombre": "Billetera",
        "importe": "10000.00",
    }
    assert (observacion.operacion_tipo, observacion.operacion_id) == ("COBRANZA", cobranza_id)


def test_syn07_un_medio_inactivo_en_una_de_varias_lineas_observa_solo_esa_linea(
    entorno: Entorno,
) -> None:
    billetera = entorno.crear_medio("Billetera", requiere_referencia=False)
    jornada = entorno.crear_jornada()
    entorno.sesion.commit()
    entorno.desactivar_medio(billetera)
    contenido = entorno.contenido(
        medios=entorno.medios(
            (entorno.efectivo_id, "30000.00", None),
            (billetera, "5000.00", None),
            (entorno.transferencia_id, "15000.00", "0042"),
        )
    )

    resultado = _enviar(entorno, contenido, jornada_id=jornada)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "MEDIO_INACTIVO"
    assert observacion.detalle is not None
    assert observacion.detalle["medio"] == 1
    assert observacion.detalle["importe"] == "5000.00"
    assert entorno.saldo() == Decimal("100000.00")


def test_syn07_dos_lineas_con_el_mismo_medio_inactivo_dan_dos_observaciones(
    entorno: Entorno,
) -> None:
    """D13: dos líneas con el mismo medio inactivo, cada una con su línea."""
    entorno.desactivar_medio(entorno.efectivo_id)
    contenido = entorno.contenido(
        medios=entorno.medios(
            (entorno.efectivo_id, "20000.00", None), (entorno.efectivo_id, "30000.00", None)
        )
    )

    _enviar(entorno, contenido, jornada_id=entorno.crear_jornada())

    detalles = [o.detalle for o in _observaciones(entorno) if o.codigo == "MEDIO_INACTIVO"]
    assert [(d or {}).get("medio") for d in detalles] == [0, 1]


# --- REFERENCIA_FALTANTE (SYN-07, D13 punto 2) --------------------------------------------------


@pytest.mark.parametrize("referencia", [None, "", "   "])
def test_syn07_una_referencia_faltante_o_de_solo_espacios_se_acepta_con_referencia_faltante(
    entorno: Entorno, referencia: str | None
) -> None:
    """Una transferencia sin número de operación: se acepta, la referencia se guarda nula y la
    observación indica la línea."""
    contenido = entorno.contenido(
        medios=entorno.medios(
            (entorno.efectivo_id, "30000.00", None),
            (entorno.transferencia_id, "20000.00", referencia),
        )
    )

    resultado = _enviar(entorno, contenido, jornada_id=entorno.crear_jornada())

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "REFERENCIA_FALTANTE"
    assert observacion.detalle == {
        "medio": 1,
        "medio_pago_id": str(entorno.transferencia_id),
        "nombre": "Transferencia",
        "importe": "20000.00",
    }
    assert [m.referencia for m in entorno.medios_de_cobranza()] == [None, None]
    assert entorno.saldo() == Decimal("100000.00")


def test_syn07_la_misma_linea_puede_llevar_medio_inactivo_y_referencia_faltante(
    entorno: Entorno,
) -> None:
    entorno.desactivar_medio(entorno.transferencia_id)
    contenido = entorno.contenido(
        medios=entorno.medios(
            (entorno.efectivo_id, "30000.00", None),
            (entorno.transferencia_id, "20000.00", None),
        )
    )

    _enviar(entorno, contenido, jornada_id=entorno.crear_jornada())

    assert _codigos(entorno) == ["MEDIO_INACTIVO", "REFERENCIA_FALTANTE"]
    assert {(o.detalle or {}).get("medio") for o in _observaciones(entorno)} == {1}


# --- consumidor final (SYN-07, D13 punto 1) -----------------------------------------------------


def test_syn07_el_consumidor_final_se_acepta_con_cliente_no_habilitado(entorno: Entorno) -> None:
    consumidor = entorno.crear_cliente(es_consumidor_final=True, nombre="Consumidor final")
    entorno.sesion.commit()
    contenido = entorno.contenido(cliente_id=str(consumidor))

    resultado = _enviar(entorno, contenido, jornada_id=entorno.crear_jornada())

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (observacion,) = _observaciones(entorno)
    assert observacion.codigo == "CLIENTE_NO_HABILITADO"
    assert observacion.detalle == {"cliente_id": str(consumidor)}
    assert entorno.saldo(consumidor) == Decimal("-50000.00")


# --- conviven con PERMISO_REVOCADO y JORNADA_LIBERADA; doble envío (INV-06) ---------------------


# Escenario: "Observaciones de medio junto con otras"
def test_inv06_todas_las_observaciones_conviven_y_un_doble_envio_no_las_duplica(
    entorno: Entorno,
) -> None:
    """D13 punto 2: `PERMISO_REVOCADO`, `JORNADA_LIBERADA`, `MEDIO_INACTIVO` y
    `REFERENCIA_FALTANTE` en el mismo comando; el reenvío devuelve el mismo resultado."""
    entorno.desactivar_medio(entorno.efectivo_id)
    entorno.sesion.execute(
        text("DELETE FROM rol_permiso WHERE organizacion_id = :o"), {"o": entorno.org}
    )
    entorno.sesion.commit()
    jornada = entorno.crear_jornada(estado="LIBERADA")
    contenido = entorno.contenido(
        medios=entorno.medios(
            (entorno.efectivo_id, "30000.00", None), (entorno.transferencia_id, "20000.00", None)
        )
    )
    operation_id = uuid4()

    primero = _enviar(entorno, contenido, jornada_id=jornada, operation_id=operation_id)
    codigos = sorted(_codigos(entorno))
    segundo = _enviar(entorno, contenido, jornada_id=jornada, operation_id=operation_id)

    assert primero.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert codigos == [
        "JORNADA_LIBERADA",
        "MEDIO_INACTIVO",
        "PERMISO_REVOCADO",
        "REFERENCIA_FALTANTE",
    ]
    assert (segundo.estado, segundo.resultado) == (primero.estado, primero.resultado)
    assert sorted(_codigos(entorno)) == codigos
    assert len(entorno.cobranzas()) == 1
    assert len(entorno.movimientos("COBRANZA")) == 1
    assert entorno.saldo() == Decimal("100000.00")


# --- lo que sí se rechaza (SYN-06, INV-08) -------------------------------------------------------


def test_inv08_medios_que_no_suman_el_importe_se_rechazan_sin_observaciones(
    entorno: Entorno,
) -> None:
    """INV-08 es un invariante: el dispositivo lo calcula, no es regla de negocio."""
    contenido = entorno.contenido(
        importe="50000.00", medios=entorno.medios((entorno.efectivo_id, "49999.00", None))
    )
    operation_id = uuid4()

    resultado = _enviar(
        entorno, contenido, jornada_id=entorno.crear_jornada(), operation_id=operation_id
    )

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "MEDIOS_NO_SUMAN_IMPORTE")
    assert _comandos(entorno, operation_id) == []
    entorno.sin_efectos()
    assert _observaciones(entorno) == []
    assert entorno.saldo() == Decimal("150000.00")


def test_inv08_medios_que_no_suman_se_rechazan_aunque_el_medio_este_inactivo(
    entorno: Entorno,
) -> None:
    """Triangulación: un medio inactivo no tapa un descuadre."""
    entorno.desactivar_medio(entorno.efectivo_id)
    contenido = entorno.contenido(
        importe="50000.00", medios=entorno.medios((entorno.efectivo_id, "100.00", None))
    )

    resultado = _enviar(entorno, contenido, jornada_id=entorno.crear_jornada())

    assert resultado.error_codigo == "MEDIOS_NO_SUMAN_IMPORTE"
    assert _observaciones(entorno) == []


# Escenario: "Cliente inexistente sin conexión"
# Escenario: "Medio inexistente o de otra organización sin conexión"
@pytest.mark.parametrize("que", ["cliente", "medio"])
def test_syn06_un_cliente_o_medio_inexistente_se_rechaza_sin_observacion(
    entorno: Entorno, que: str
) -> None:
    """Dependencia inexistente (SYN-06, INV-21): rechazada, sin registro del comando."""
    if que == "cliente":
        contenido = entorno.contenido(cliente_id=str(uuid4()))
    else:
        contenido = entorno.contenido(
            medios=entorno.medios((uuid4(), "50000.00", None)),
        )
    operation_id = uuid4()

    resultado = _enviar(
        entorno, contenido, jornada_id=entorno.crear_jornada(), operation_id=operation_id
    )

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "RECURSO_NO_ENCONTRADO")
    assert _comandos(entorno, operation_id) == []
    entorno.sin_efectos()
    assert _observaciones(entorno) == []


def test_syn06_un_medio_de_otra_organizacion_se_rechaza_como_inexistente(
    entorno: Entorno, db_session: Session
) -> None:
    ajeno = Entorno(db_session)
    contenido = entorno.contenido(medios=entorno.medios((ajeno.efectivo_id, "50000.00", None)))

    resultado = _enviar(entorno, contenido, jornada_id=entorno.crear_jornada())

    assert resultado.error_codigo == "RECURSO_NO_ENCONTRADO"


# --- con conexión no cambia nada (TR-09) ---------------------------------------------------------


def test_tr09_un_medio_inactivo_con_conexion_se_rechaza_por_el_lote_y_por_el_bus(
    entorno: Entorno,
) -> None:
    """D13 punto 4: el mismo medio inactivo, en `ONLINE`, es `MEDIO_PAGO_INACTIVO` y sin
    observaciones: por el lote y por el camino de REST."""
    entorno.desactivar_medio(entorno.efectivo_id)

    por_lote = _enviar(entorno, entorno.contenido(), jornada_id=None, modo="ONLINE")
    with pytest.raises(MedioPagoInactivoError):
        entorno.registrar()

    assert (por_lote.estado, por_lote.error_codigo) == ("RECHAZADO", "MEDIO_PAGO_INACTIVO")
    assert _observaciones(entorno) == []
    entorno.sin_efectos()


def test_tr09_una_referencia_faltante_con_conexion_se_rechaza_con_referencia_obligatoria(
    entorno: Entorno,
) -> None:
    contenido = entorno.contenido(
        medios=entorno.medios(
            (entorno.efectivo_id, "30000.00", None), (entorno.transferencia_id, "20000.00", None)
        )
    )

    por_lote = _enviar(entorno, contenido, jornada_id=None, modo="ONLINE")
    with pytest.raises(ReferenciaObligatoriaError):
        entorno.enviar(contenido)

    assert (por_lote.estado, por_lote.error_codigo) == ("RECHAZADO", "REFERENCIA_OBLIGATORIA")
    assert _observaciones(entorno) == []
    entorno.sin_efectos()
