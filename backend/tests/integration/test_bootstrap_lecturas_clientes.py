"""Change 21, tarea 1.1 (`design.md` D4; spec `sync/bootstrap`): las lecturas masivas que el
bootstrap necesita de `clientes` y `cuentas_corrientes`, por `service.py` y contra PostgreSQL real.

Reglas citadas: `01` §19, CRE-01, CRE-03, CRE-06, INV-13, INV-21.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.clientes import service as clientes_service
from app.modules.cuentas_corrientes import service as cuentas_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _configurar_organizacion(sesion: Session, org: UUID, **columnas: object) -> None:
    asignaciones = ", ".join(f"{columna} = :{columna}" for columna in columnas)
    sesion.execute(
        text(f"UPDATE configuracion_organizacion SET {asignaciones} WHERE organizacion_id = :org"),
        {**columnas, "org": org},
    )


def _configurar_cliente(sesion: Session, org: UUID, cliente_id: UUID, **columnas: object) -> None:
    asignaciones = ", ".join(f"{columna} = :{columna}" for columna in columnas)
    sesion.execute(
        text(f"UPDATE cliente SET {asignaciones} WHERE organizacion_id = :org AND id = :id"),
        {**columnas, "org": org, "id": cliente_id},
    )


def _mover(
    sesion: Session, org: UUID, cliente_id: UUID, importe: str, sentido: str = "AUMENTA"
) -> None:
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(sesion, org)
    tipo = "SALDO_INICIAL" if sentido == "AUMENTA" else "COBRANZA"
    cuentas_service.registrar_movimiento(
        org,
        sesion,
        FixedClock(MOMENTO),
        cuenta_tipo="CLIENTE",
        entidad_id=cliente_id,
        tipo=tipo,
        sentido=sentido,
        importe=importe,
        origen_tipo=tipo,
        origen_id=uuid4(),
        occurred_at=MOMENTO,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=uuid4(),
    )


# --- clientes ---------------------------------------------------------------------------------


def test_lista_los_clientes_activos_y_suspendidos_sin_los_inactivos(db_session: Session) -> None:
    """D4: `ACTIVO` y `SUSPENDIDO` de toda la organización; los `INACTIVO` no bajan (CLI-06)."""
    org = crear_organizacion(db_session).id
    activo = crear_cliente(db_session, org, nombre="Activo")
    suspendido = crear_cliente(db_session, org, nombre="Suspendido", estado="SUSPENDIDO")
    inactivo = crear_cliente(db_session, org, nombre="Inactivo", estado="INACTIVO")

    ids = {c.id for c in clientes_service.listar_clientes_para_dispositivo(org, db_session)}

    assert ids == {activo, suspendido}
    assert inactivo not in ids


def test_incluye_el_consumidor_final_habilitado(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    comun = crear_cliente(db_session, org, nombre="Almacén")
    final = crear_cliente(db_session, org, nombre="Consumidor final", es_consumidor_final=True)

    clientes = {c.id: c for c in clientes_service.listar_clientes_para_dispositivo(org, db_session)}

    assert set(clientes) == {comun, final}
    assert clientes[final].es_consumidor_final is True
    assert clientes[comun].es_consumidor_final is False


def test_sin_consumidor_final_habilitado_no_figura_ninguno(db_session: Session) -> None:
    org = crear_organizacion(db_session).id
    crear_cliente(db_session, org, nombre="Almacén")

    clientes = clientes_service.listar_clientes_para_dispositivo(org, db_session)

    assert [c.es_consumidor_final for c in clientes] == [False]


def test_cre03_cre06_el_credito_viene_resuelto_con_la_herencia_de_la_organizacion(
    db_session: Session,
) -> None:
    org = crear_organizacion(db_session).id
    _configurar_organizacion(
        db_session,
        org,
        politica_credito_default="AUTORIZAR",
        tolerancia_offline_tipo="PORCENTAJE",
        tolerancia_offline_valor=Decimal("5.00"),
    )
    heredero = crear_cliente(db_session, org, nombre="Hereda")
    propio = crear_cliente(db_session, org, nombre="Propio")
    _configurar_cliente(
        db_session,
        org,
        propio,
        limite_credito=Decimal("200000.00"),
        politica_credito="BLOQUEAR",
        tolerancia_offline_tipo="IMPORTE",
        tolerancia_offline_valor=Decimal("1000.00"),
    )

    clientes = {c.id: c for c in clientes_service.listar_clientes_para_dispositivo(org, db_session)}

    hereda = clientes[heredero].credito
    assert hereda.limite is None  # sin límite = sin control (CRE-01)
    assert hereda.politica == "AUTORIZAR"
    assert (hereda.tolerancia_tipo, hereda.tolerancia_valor) == ("PORCENTAJE", Decimal("5.00"))
    propia = clientes[propio].credito
    assert propia.limite == Decimal("200000.00")
    assert propia.politica == "BLOQUEAR"
    assert (propia.tolerancia_tipo, propia.tolerancia_valor) == ("IMPORTE", Decimal("1000.00"))


def test_trae_los_datos_de_contacto_y_la_lista_pero_no_correo_ni_vendedor(
    db_session: Session,
) -> None:
    """D4: sin correo ni vendedor asignado (el dato ni existe en la forma que se entrega)."""
    org = crear_organizacion(db_session).id
    cliente_id = crear_cliente(db_session, org, nombre="Don Pedro")
    _configurar_cliente(
        db_session,
        org,
        cliente_id,
        codigo="C-001",
        razon_social="Pedro SRL",
        documento_tipo="CUIT",
        documento_numero="30712345678",
        telefono="261 555 0101",
        email="pedro@example.com",
    )

    (cliente,) = clientes_service.listar_clientes_para_dispositivo(org, db_session)

    assert (cliente.codigo, cliente.nombre, cliente.razon_social) == (
        "C-001",
        "Don Pedro",
        "Pedro SRL",
    )
    assert (cliente.documento_tipo, cliente.documento_numero) == ("CUIT", "30712345678")
    assert cliente.telefono == "261 555 0101"
    assert cliente.direccion == "Av. San Martín 1420"
    assert cliente.estado == "ACTIVO"
    assert cliente.lista_precio_id is None
    assert not hasattr(cliente, "email")
    assert not hasattr(cliente, "vendedor_id")


def test_inv21_no_lista_clientes_de_otra_organizacion(db_session: Session) -> None:
    propia = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    mio = crear_cliente(db_session, propia, nombre="Mío")
    crear_cliente(db_session, ajena, nombre="Ajeno")

    clientes = clientes_service.listar_clientes_para_dispositivo(propia, db_session)

    assert [c.id for c in clientes] == [mio]


# --- saldos de todos los clientes ---------------------------------------------------------------


def test_inv13_los_saldos_de_todos_los_clientes_son_la_suma_de_sus_movimientos(
    db_session: Session,
) -> None:
    org = crear_organizacion(db_session).id
    debe = crear_cliente(db_session, org, nombre="Debe")
    parcial = crear_cliente(db_session, org, nombre="Parcial")
    limpio = crear_cliente(db_session, org, nombre="Sin movimientos")
    _mover(db_session, org, debe, "31250.00")
    _mover(db_session, org, parcial, "1000.00")
    _mover(db_session, org, parcial, "250.50", sentido="REDUCE")

    saldos = cuentas_service.saldos_de_clientes(org, db_session)

    assert saldos[debe] == Decimal("31250.00")
    assert saldos[parcial] == Decimal("749.50")
    assert limpio not in saldos  # sin movimientos: quien consume lo toma como 0.00 (CC-04)


def test_los_saldos_de_todos_se_leen_en_una_sola_consulta_sql(db_session: Session) -> None:
    """`CLAUDE.md` §4: los saldos se leen con SQL, una sola consulta, sin sumar filas en Python."""
    org = crear_organizacion(db_session).id
    for i in range(3):
        _mover(db_session, org, crear_cliente(db_session, org, nombre=f"C{i}"), "10.00")
    consultas: list[str] = []

    def _contar(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]
        consultas.append(statement)

    motor = db_session.get_bind()
    event.listen(motor, "before_cursor_execute", _contar)
    try:
        cuentas_service.saldos_de_clientes(org, db_session)
    finally:
        event.remove(motor, "before_cursor_execute", _contar)

    assert len(consultas) == 1


def test_inv21_los_saldos_no_incluyen_clientes_de_otra_organizacion(db_session: Session) -> None:
    propia = crear_organizacion(db_session).id
    ajena = crear_organizacion(db_session).id
    mio = crear_cliente(db_session, propia, nombre="Mío")
    ajeno = crear_cliente(db_session, ajena, nombre="Ajeno")
    _mover(db_session, propia, mio, "5.00")
    _mover(db_session, ajena, ajeno, "9.00")

    saldos = cuentas_service.saldos_de_clientes(propia, db_session)

    assert saldos == {mio: Decimal("5.00")}
