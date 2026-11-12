"""INV-13 contra PostgreSQL real, con Hypothesis (change 08, tarea 8.2).

INV-13 (`docs/01` §20, CC-04): el saldo de cada cuenta corriente es igual a la
suma de sus movimientos. Acá se prueba con la base y el servicio reales: para
secuencias arbitrarias de movimientos sobre varias cuentas (clientes y
proveedores, con todos los tipos del catálogo), registradas por
`service.registrar_movimiento`, al final `saldo_cuenta` es igual a la suma SQL
del libro para cada cuenta y `verificar_consistencia` no devuelve diferencias.

INV-01: una falla inyectada a mitad de una operación deshace el movimiento y el
saldo juntos; lo confirmado antes queda intacto y la invariante se sostiene.

Cada ejemplo corre dentro de un `SAVEPOINT` que se revierte: es una prueba de la
invariante, no de concurrencia (esa confirma transacciones reales, tarea 8.5).
La contraparte de dominio puro es `test_inv13_saldo_cuenta_dominio.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.cuentas_corrientes import service
from app.modules.cuentas_corrientes.domain.catalogo import (
    CLIENTE,
    PROVEEDOR,
    SENTIDOS,
    TIPOS_POR_CUENTA,
    sentido_de_tipo,
)
from tests.integration.cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)

BASE = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(BASE)

type Movimiento = tuple[str, int, str, str, Decimal, datetime]

# Cuatro cuentas: dos de cliente y dos de proveedor.
_CUENTAS = [(CLIENTE, 0), (CLIENTE, 1), (PROVEEDOR, 0), (PROVEEDOR, 1)]


class _FallaInyectada(Exception):
    pass


@st.composite
def _movimientos(draw: st.DrawFn) -> Movimiento:
    cuenta_tipo, indice = draw(st.sampled_from(_CUENTAS))
    tipo = draw(st.sampled_from(sorted(TIPOS_POR_CUENTA[cuenta_tipo])))
    sentido = sentido_de_tipo(tipo) or draw(st.sampled_from(SENTIDOS))
    centavos = draw(st.integers(min_value=1, max_value=100_000_000))
    # Momentos dispersos y con empates: el saldo no depende del orden de registro.
    desplazamiento = draw(st.integers(min_value=-3, max_value=3))
    return (
        cuenta_tipo,
        indice,
        tipo,
        sentido,
        Decimal(centavos) / 100,
        BASE + timedelta(days=desplazamiento),
    )


_SECUENCIAS = st.lists(_movimientos(), min_size=1, max_size=25)

_PROPIEDAD = settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


class _Mundo:
    """Una organización con sus cuatro cuentas, creada dentro del `SAVEPOINT` del
    ejemplo."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        clientes = [crear_cliente(sesion, self.org, nombre=f"Cliente {i}") for i in range(2)]
        proveedores = [crear_proveedor(sesion, self.org) for _ in range(2)]
        self.entidades: dict[tuple[str, int], UUID] = {
            (CLIENTE, 0): clientes[0],
            (CLIENTE, 1): clientes[1],
            (PROVEEDOR, 0): proveedores[0],
            (PROVEEDOR, 1): proveedores[1],
        }

    def registrar(self, movimiento: Movimiento) -> None:
        cuenta_tipo, indice, tipo, sentido, importe, momento = movimiento
        operation_id = uuid4()
        service.registrar_movimiento(
            self.org,
            self.sesion,
            RELOJ,
            cuenta_tipo=cuenta_tipo,
            entidad_id=self.entidades[(cuenta_tipo, indice)],
            tipo=tipo,
            sentido=sentido,
            importe=importe,
            origen_tipo=tipo,
            origen_id=operation_id,
            occurred_at=momento,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=operation_id,
        )

    def suma_sql_del_libro(self, cuenta_tipo: str, entidad_id: UUID) -> Decimal:
        return self.sesion.execute(
            text(
                """
                SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), 0)
                FROM cuenta_movimiento
                WHERE organizacion_id = :o AND cuenta_tipo = :t AND entidad_id = :e
                """
            ),
            {"o": self.org, "t": cuenta_tipo, "e": entidad_id},
        ).scalar_one()

    def saldo_materializado_sql(self, cuenta_tipo: str, entidad_id: UUID) -> Decimal | None:
        return self.sesion.execute(
            text(
                "SELECT saldo FROM saldo_cuenta "
                "WHERE organizacion_id = :o AND cuenta_tipo = :t AND entidad_id = :e"
            ),
            {"o": self.org, "t": cuenta_tipo, "e": entidad_id},
        ).scalar_one_or_none()

    def sumas_del_libro(self) -> dict[tuple[str, int], Decimal]:
        return {
            clave: self.suma_sql_del_libro(clave[0], entidad_id)
            for clave, entidad_id in self.entidades.items()
        }

    def verificar_la_invariante(self) -> None:
        for (cuenta_tipo, _), entidad_id in self.entidades.items():
            suma = self.suma_sql_del_libro(cuenta_tipo, entidad_id)
            materializado = self.saldo_materializado_sql(cuenta_tipo, entidad_id)
            # Una cuenta sin movimientos no tiene fila de saldo (perezosa) y su saldo es 0.
            assert (materializado if materializado is not None else Decimal("0")) == suma
            saldo = service.obtener_saldo(
                self.org, self.sesion, cuenta_tipo=cuenta_tipo, entidad_id=entidad_id
            )
            assert saldo == suma
        assert service.verificar_consistencia(self.org, self.sesion) == []


@_PROPIEDAD
@given(_SECUENCIAS)
def test_inv13_el_saldo_materializado_es_la_suma_sql_del_libro_en_cada_cuenta(
    db_session: Session, secuencia: list[Movimiento]
) -> None:
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session)
        for movimiento in secuencia:
            mundo.registrar(movimiento)

        mundo.verificar_la_invariante()
    finally:
        savepoint.rollback()


@_PROPIEDAD
@given(_SECUENCIAS, _SECUENCIAS)
def test_inv13_inv01_una_falla_a_mitad_de_la_operacion_no_altera_lo_confirmado(
    db_session: Session, confirmadas: list[Movimiento], interrumpidas: list[Movimiento]
) -> None:
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session)
        for movimiento in confirmadas:
            mundo.registrar(movimiento)
        antes = mundo.sumas_del_libro()

        with pytest.raises(_FallaInyectada), db_session.begin_nested():
            for movimiento in interrumpidas:
                mundo.registrar(movimiento)
            raise _FallaInyectada

        assert mundo.sumas_del_libro() == antes
        mundo.verificar_la_invariante()
    finally:
        savepoint.rollback()
