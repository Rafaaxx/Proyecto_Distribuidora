"""Tarea 4.2: `cuentas_corrientes/service.py` contra PostgreSQL real.

Reglas citadas: CC-01, CC-02, CC-03, CC-04, CC-06, CC-07, CLI-03, INV-01, INV-02,
INV-13, INV-21 y `design.md` D3, D4, D5, D6, D9, D10, D14.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.cuentas_corrientes import service
from app.modules.cuentas_corrientes.domain.errores import (
    ConsumidorFinalSinCuentaError,
    CuentaConOperacionesError,
    ImporteInvalidoError,
    RecursoNoEncontradoError,
    SentidoInvalidoError,
    TipoMovimientoInvalidoError,
)
from app.modules.cuentas_corrientes.models import CuentaMovimiento, SaldoCuenta
from app.modules.identidad import service as identidad_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


class Entorno:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.cliente_id = crear_cliente(sesion, self.org)
        self.proveedor_id = crear_proveedor(sesion, self.org)

    def mover(
        self,
        *,
        cuenta_tipo: str = "CLIENTE",
        entidad_id: UUID | None = None,
        tipo: str = "SALDO_INICIAL",
        sentido: str = "AUMENTA",
        importe: str | Decimal = "150000.00",
        occurred_at: datetime = MOMENTO,
    ) -> service.ResultadoDeMovimiento:
        if entidad_id is None:
            entidad_id = self.cliente_id if cuenta_tipo == "CLIENTE" else self.proveedor_id
        return service.registrar_movimiento(
            self.org,
            self.sesion,
            RELOJ,
            cuenta_tipo=cuenta_tipo,
            entidad_id=entidad_id,
            tipo=tipo,
            sentido=sentido,
            importe=importe,
            origen_tipo=tipo,
            origen_id=uuid4(),
            occurred_at=occurred_at,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
        )

    def saldo_inicial(self, **cambios: object) -> service.ResultadoDeMovimiento:
        argumentos: dict[str, object] = {
            "cuenta_tipo": "CLIENTE",
            "entidad_id": self.cliente_id,
            "importe": "150000.00",
            "sentido": "AUMENTA",
            "occurred_at": MOMENTO,
            "usuario_id": self.usuario_id,
            "dispositivo_id": self.dispositivo_id,
            "operation_id": uuid4(),
            **cambios,
        }
        return service.registrar_saldo_inicial(self.org, self.sesion, RELOJ, **argumentos)  # type: ignore[arg-type]

    def movimientos(self, entidad_id: UUID) -> list[CuentaMovimiento]:
        return list(
            self.sesion.scalars(
                select(CuentaMovimiento)
                .where(
                    CuentaMovimiento.organizacion_id == self.org,
                    CuentaMovimiento.entidad_id == entidad_id,
                )
                .order_by(CuentaMovimiento.occurred_at, CuentaMovimiento.id)
            ).all()
        )

    def suma_sql(self, entidad_id: UUID) -> Decimal:
        return self.sesion.execute(
            text(
                """
                SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), 0)
                FROM cuenta_movimiento WHERE organizacion_id = :o AND entidad_id = :e
                """
            ),
            {"o": self.org, "e": entidad_id},
        ).scalar_one()


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- registrar_movimiento (CC-01, CC-04, D10) -------------------------------


def test_un_movimiento_guarda_todos_sus_datos(entorno: Entorno) -> None:
    operation_id = uuid4()
    origen_id = uuid4()
    ocurrido = MOMENTO - timedelta(hours=2)

    resultado = service.registrar_movimiento(
        entorno.org,
        entorno.sesion,
        RELOJ,
        cuenta_tipo="CLIENTE",
        entidad_id=entorno.cliente_id,
        tipo="SALDO_INICIAL",
        sentido="AUMENTA",
        importe="150000.00",
        origen_tipo="SALDO_INICIAL",
        origen_id=origen_id,
        occurred_at=ocurrido,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        operation_id=operation_id,
    )

    (movimiento,) = entorno.movimientos(entorno.cliente_id)
    assert movimiento.id == resultado.movimiento.id
    assert movimiento.cuenta_tipo == "CLIENTE"
    assert movimiento.importe == Decimal("150000.00")
    assert movimiento.sentido == "AUMENTA"
    assert movimiento.origen_tipo == "SALDO_INICIAL"
    assert movimiento.origen_id == origen_id
    assert movimiento.occurred_at == ocurrido
    assert movimiento.registered_at == MOMENTO  # del reloj inyectable
    assert movimiento.usuario_id == entorno.usuario_id
    assert movimiento.dispositivo_id == entorno.dispositivo_id  # D14
    assert movimiento.operation_id == operation_id


def test_el_saldo_es_la_suma_de_los_movimientos(entorno: Entorno) -> None:
    """CC-04, INV-13."""
    entorno.mover(sentido="AUMENTA", importe="150000.00")
    resultado = entorno.mover(sentido="REDUCE", importe="20000.00")

    assert resultado.saldo == Decimal("130000.00")
    assert service.obtener_saldo(
        entorno.org, entorno.sesion, cuenta_tipo="CLIENTE", entidad_id=entorno.cliente_id
    ) == Decimal("130000.00")
    assert entorno.suma_sql(entorno.cliente_id) == Decimal("130000.00")


def test_un_saldo_negativo_es_saldo_a_favor(entorno: Entorno) -> None:
    resultado = entorno.mover(sentido="REDUCE", importe="20000.00")

    assert resultado.saldo == Decimal("-20000.00")


def test_las_cuentas_de_cliente_y_proveedor_no_se_mezclan(entorno: Entorno) -> None:
    entorno.mover(cuenta_tipo="CLIENTE", importe="100.00")
    entorno.mover(cuenta_tipo="PROVEEDOR", tipo="COMPRA", importe="80000.00")

    assert service.obtener_saldo(
        entorno.org, entorno.sesion, cuenta_tipo="CLIENTE", entidad_id=entorno.cliente_id
    ) == Decimal("100.00")
    assert service.obtener_saldo(
        entorno.org, entorno.sesion, cuenta_tipo="PROVEEDOR", entidad_id=entorno.proveedor_id
    ) == Decimal("80000.00")


def test_un_tipo_de_proveedor_en_una_cuenta_de_cliente_se_rechaza_sin_rastro(
    entorno: Entorno,
) -> None:
    with pytest.raises(TipoMovimientoInvalidoError):
        entorno.mover(tipo="COMPRA")

    assert entorno.movimientos(entorno.cliente_id) == []
    assert entorno.sesion.scalar(
        select(func.count()).select_from(SaldoCuenta)
    ) == 0 or service.obtener_saldo(
        entorno.org, entorno.sesion, cuenta_tipo="CLIENTE", entidad_id=entorno.cliente_id
    ) == Decimal("0.00")


def test_un_sentido_que_contradice_el_del_tipo_se_rechaza(entorno: Entorno) -> None:
    """CC-05: la venta aumenta; una `VENTA` que reduce es un dato incoherente."""
    with pytest.raises(SentidoInvalidoError):
        entorno.mover(tipo="VENTA", sentido="REDUCE")
    entorno.mover(tipo="VENTA", sentido="AUMENTA", importe="10.00")


@pytest.mark.parametrize("importe", ["0.00", "-1.00", "100.005", "abc"])
def test_un_importe_invalido_se_rechaza(entorno: Entorno, importe: str) -> None:
    with pytest.raises(ImporteInvalidoError):
        entorno.mover(importe=importe)

    assert entorno.movimientos(entorno.cliente_id) == []


def test_una_entidad_inexistente_o_ajena_es_404_y_no_deja_rastro(entorno: Entorno) -> None:
    """D6, D7, INV-21."""
    otra = crear_organizacion(entorno.sesion)
    ajeno = crear_cliente(entorno.sesion, otra.id)

    for entidad in (uuid4(), ajeno):
        with pytest.raises(RecursoNoEncontradoError):
            entorno.mover(entidad_id=entidad)

    assert entorno.movimientos(ajeno) == []
    assert service.obtener_saldo(
        otra.id, entorno.sesion, cuenta_tipo="CLIENTE", entidad_id=ajeno
    ) == Decimal("0.00")


def test_el_id_de_un_proveedor_no_sirve_como_cuenta_de_cliente(entorno: Entorno) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        entorno.mover(cuenta_tipo="CLIENTE", entidad_id=entorno.proveedor_id)


def test_una_falla_a_mitad_de_la_operacion_no_deja_movimiento_ni_saldo(
    entorno: Entorno,
) -> None:
    """INV-01, INV-13: si la transaccion se revierte, se van juntos."""

    class _Falla(Exception):
        pass

    with pytest.raises(_Falla), entorno.sesion.begin_nested():
        entorno.mover(importe="500.00")
        raise _Falla

    assert entorno.movimientos(entorno.cliente_id) == []
    assert service.obtener_saldo(
        entorno.org, entorno.sesion, cuenta_tipo="CLIENTE", entidad_id=entorno.cliente_id
    ) == Decimal("0.00")
    assert not service.cuenta_tiene_movimientos(
        entorno.org, entorno.sesion, cuenta_tipo="CLIENTE", entidad_id=entorno.cliente_id
    )


# --- bloquear_saldo, obtener_saldo, cuenta_tiene_movimientos ------------------


def test_bloquear_saldo_crea_la_fila_en_cero_y_es_idempotente(entorno: Entorno) -> None:
    primero = service.bloquear_saldo(
        entorno.org, entorno.sesion, RELOJ, cuenta_tipo="CLIENTE", entidad_id=entorno.cliente_id
    )
    segundo = service.bloquear_saldo(
        entorno.org, entorno.sesion, RELOJ, cuenta_tipo="CLIENTE", entidad_id=entorno.cliente_id
    )

    assert primero == segundo == Decimal("0.00")
    assert (
        entorno.sesion.scalar(
            select(func.count())
            .select_from(SaldoCuenta)
            .where(SaldoCuenta.entidad_id == entorno.cliente_id)
        )
        == 1
    )


def test_bloquear_saldo_de_una_entidad_ajena_es_404(entorno: Entorno) -> None:
    otra = crear_organizacion(entorno.sesion)
    ajeno = crear_cliente(entorno.sesion, otra.id)

    with pytest.raises(RecursoNoEncontradoError):
        service.bloquear_saldo(
            entorno.org, entorno.sesion, RELOJ, cuenta_tipo="CLIENTE", entidad_id=ajeno
        )


def test_el_saldo_de_una_cuenta_sin_movimientos_es_cero(entorno: Entorno) -> None:
    assert service.obtener_saldo(
        entorno.org, entorno.sesion, cuenta_tipo="PROVEEDOR", entidad_id=entorno.proveedor_id
    ) == Decimal("0.00")


def test_cuenta_tiene_movimientos_pasa_de_falso_a_verdadero(entorno: Entorno) -> None:
    def tiene() -> bool:
        return service.cuenta_tiene_movimientos(
            entorno.org, entorno.sesion, cuenta_tipo="CLIENTE", entidad_id=entorno.cliente_id
        )

    assert not tiene()
    entorno.mover()
    assert tiene()


def test_cuenta_tiene_movimientos_solo_mira_la_cuenta_pedida(entorno: Entorno) -> None:
    entorno.mover(cuenta_tipo="PROVEEDOR", tipo="COMPRA")

    assert not service.cuenta_tiene_movimientos(
        entorno.org, entorno.sesion, cuenta_tipo="CLIENTE", entidad_id=entorno.cliente_id
    )
    assert service.cuenta_tiene_movimientos(
        entorno.org, entorno.sesion, cuenta_tipo="PROVEEDOR", entidad_id=entorno.proveedor_id
    )


# --- registrar_saldo_inicial (D3, D4, D5) --------------------------------------


def test_saldo_inicial_deudor_de_un_cliente(entorno: Entorno) -> None:
    operation_id = uuid4()

    resultado = entorno.saldo_inicial(operation_id=operation_id)

    assert resultado.saldo == Decimal("150000.00")
    (movimiento,) = entorno.movimientos(entorno.cliente_id)
    assert movimiento.tipo == "SALDO_INICIAL"
    assert movimiento.origen_tipo == "SALDO_INICIAL"
    assert movimiento.origen_id == operation_id  # D5
    assert movimiento.operation_id == operation_id
    assert movimiento.dispositivo_id == entorno.dispositivo_id  # D14


def test_saldo_inicial_de_un_proveedor(entorno: Entorno) -> None:
    resultado = entorno.saldo_inicial(
        cuenta_tipo="PROVEEDOR", entidad_id=entorno.proveedor_id, importe="80000.00"
    )

    assert resultado.saldo == Decimal("80000.00")


def test_saldo_inicial_a_favor_del_cliente(entorno: Entorno) -> None:
    resultado = entorno.saldo_inicial(sentido="REDUCE", importe="20000.00")

    assert resultado.saldo == Decimal("-20000.00")


def test_un_saldo_inicial_equivocado_se_corrige_con_otro_inverso(entorno: Entorno) -> None:
    """D3, TR-06, CC-06: los dos quedan, ninguno se modifica."""
    entorno.saldo_inicial(importe="150000.00", sentido="AUMENTA")
    antes = [(m.id, m.importe, m.sentido) for m in entorno.movimientos(entorno.cliente_id)]

    resultado = entorno.saldo_inicial(importe="20000.00", sentido="REDUCE")

    assert resultado.saldo == Decimal("130000.00")
    despues = entorno.movimientos(entorno.cliente_id)
    assert len(despues) == 2
    assert antes[0] in [(m.id, m.importe, m.sentido) for m in despues]


def test_una_cuenta_con_otras_operaciones_no_admite_saldo_inicial(entorno: Entorno) -> None:
    """D3: `CUENTA_CON_OPERACIONES`, el saldo no cambia."""
    entorno.mover(tipo="VENTA", sentido="AUMENTA", importe="500.00")

    with pytest.raises(CuentaConOperacionesError):
        entorno.saldo_inicial()

    assert service.obtener_saldo(
        entorno.org, entorno.sesion, cuenta_tipo="CLIENTE", entidad_id=entorno.cliente_id
    ) == Decimal("500.00")
    assert len(entorno.movimientos(entorno.cliente_id)) == 1


def test_otra_operacion_bloquea_el_saldo_inicial_en_la_cuenta_de_proveedor(
    entorno: Entorno,
) -> None:
    entorno.mover(cuenta_tipo="PROVEEDOR", tipo="PAGO", sentido="REDUCE", importe="10.00")

    with pytest.raises(CuentaConOperacionesError):
        entorno.saldo_inicial(cuenta_tipo="PROVEEDOR", entidad_id=entorno.proveedor_id)


@pytest.mark.parametrize("estado", ["ACTIVO", "SUSPENDIDO", "INACTIVO"])
def test_el_saldo_inicial_se_admite_en_cualquier_estado_de_cliente(
    db_session: Session, estado: str
) -> None:
    """D4."""
    entorno = Entorno(db_session)
    cliente = crear_cliente(db_session, entorno.org, estado=estado, nombre=f"Cliente {estado}")

    resultado = entorno.saldo_inicial(entidad_id=cliente)

    assert resultado.saldo == Decimal("150000.00")


@pytest.mark.parametrize("activo", [True, False])
def test_el_saldo_inicial_se_admite_en_proveedor_activo_o_inactivo(
    db_session: Session, activo: bool
) -> None:
    entorno = Entorno(db_session)
    proveedor = crear_proveedor(db_session, entorno.org, activo=activo)

    resultado = entorno.saldo_inicial(cuenta_tipo="PROVEEDOR", entidad_id=proveedor)

    assert resultado.saldo == Decimal("150000.00")


def test_el_consumidor_final_no_tiene_saldo_inicial(entorno: Entorno) -> None:
    """CLI-03, D4: se reconoce por la configuración de la organización."""
    consumidor = crear_cliente(
        entorno.sesion, entorno.org, nombre="Consumidor final", es_consumidor_final=True
    )
    identidad_service.configurar_consumidor_final(
        entorno.org, entorno.sesion, RELOJ, cliente_consumidor_final_id=consumidor
    )

    with pytest.raises(ConsumidorFinalSinCuentaError):
        entorno.saldo_inicial(entidad_id=consumidor)

    assert entorno.movimientos(consumidor) == []
    # Un cliente común de la misma organización sí acepta.
    assert entorno.saldo_inicial().saldo == Decimal("150000.00")


def test_un_saldo_inicial_de_entidad_ajena_es_404(entorno: Entorno) -> None:
    otra = crear_organizacion(entorno.sesion)
    ajeno = crear_cliente(entorno.sesion, otra.id)

    with pytest.raises(RecursoNoEncontradoError):
        entorno.saldo_inicial(entidad_id=ajeno)


@pytest.mark.parametrize("importe", ["0.00", "-100.00", "100.005"])
def test_un_saldo_inicial_con_importe_invalido_se_rechaza(entorno: Entorno, importe: str) -> None:
    with pytest.raises(ImporteInvalidoError):
        entorno.saldo_inicial(importe=importe)

    assert entorno.movimientos(entorno.cliente_id) == []


# --- estado de cuenta (CC-07, D9) ------------------------------------------------


def _estado(entorno: Entorno, **cambios: object) -> service.EstadoDeCuenta:
    argumentos: dict[str, object] = {
        "cuenta_tipo": "CLIENTE",
        "entidad_id": entorno.cliente_id,
        "desde": None,
        "hasta": None,
        "cursor": None,
        "limite": None,
    }
    argumentos.update(cambios)
    return service.estado_de_cuenta(entorno.org, entorno.sesion, **argumentos)  # type: ignore[arg-type]


def test_el_estado_de_cuenta_acumula_en_orden(entorno: Entorno) -> None:
    entorno.mover(sentido="AUMENTA", importe="150000.00", occurred_at=MOMENTO)
    entorno.mover(sentido="REDUCE", importe="20000.00", occurred_at=MOMENTO + timedelta(days=1))

    estado = _estado(entorno)

    assert [m.saldo_acumulado for m in estado.movimientos] == [
        Decimal("150000.00"),
        Decimal("130000.00"),
    ]
    assert estado.saldo_actual == Decimal("130000.00")
    assert estado.saldo_anterior == Decimal("0.00")
    assert estado.cursor_siguiente is None


def test_un_movimiento_con_momento_anterior_se_ordena_por_su_momento(entorno: Entorno) -> None:
    entorno.mover(sentido="AUMENTA", importe="150000.00", occurred_at=MOMENTO)
    entorno.mover(sentido="REDUCE", importe="20000.00", occurred_at=MOMENTO - timedelta(days=1))

    estado = _estado(entorno)

    assert [m.importe for m in estado.movimientos] == [Decimal("20000.00"), Decimal("150000.00")]
    assert [m.saldo_acumulado for m in estado.movimientos] == [
        Decimal("-20000.00"),
        Decimal("130000.00"),
    ]


def test_dos_movimientos_del_mismo_momento_se_ordenan_igual_siempre_por_id(
    entorno: Entorno,
) -> None:
    entorno.mover(importe="1.00")
    entorno.mover(importe="2.00")

    primera = [m.id for m in _estado(entorno).movimientos]
    segunda = [m.id for m in _estado(entorno).movimientos]

    assert primera == segunda == sorted(primera)


def test_una_cuenta_sin_movimientos_tiene_estado_vacio_y_saldo_cero(entorno: Entorno) -> None:
    estado = _estado(entorno, cuenta_tipo="PROVEEDOR", entidad_id=entorno.proveedor_id)

    assert estado.movimientos == []
    assert estado.saldo_actual == Decimal("0.00")
    assert estado.saldo_anterior == Decimal("0.00")


def test_el_periodo_trae_el_saldo_anterior_y_arranca_de_el(entorno: Entorno) -> None:
    """D9, TR-04: marzo 150.000 aumenta, abril 20.000 reduce, desde el 1 de abril."""
    entorno.mover(
        sentido="AUMENTA", importe="150000.00", occurred_at=datetime(2026, 3, 15, 15, tzinfo=UTC)
    )
    entorno.mover(
        sentido="REDUCE", importe="20000.00", occurred_at=datetime(2026, 4, 10, 15, tzinfo=UTC)
    )

    estado = _estado(entorno, desde=date(2026, 4, 1))

    assert estado.saldo_anterior == Decimal("150000.00")
    assert [m.importe for m in estado.movimientos] == [Decimal("20000.00")]
    assert estado.movimientos[0].saldo_acumulado == Decimal("130000.00")


def test_hasta_incluye_todo_el_dia_en_la_zona_de_la_organizacion(entorno: Entorno) -> None:
    """Mendoza es UTC-3: las 01:00 UTC del 1 de abril son las 22:00 del 31 de marzo."""
    entorno.mover(importe="1.00", occurred_at=datetime(2026, 4, 1, 1, 0, tzinfo=UTC))
    entorno.mover(importe="2.00", occurred_at=datetime(2026, 4, 1, 4, 0, tzinfo=UTC))

    estado = _estado(entorno, hasta=date(2026, 3, 31))

    assert [m.importe for m in estado.movimientos] == [Decimal("1.00")]


def test_la_segunda_pagina_continua_el_acumulado_sin_repetir_ni_omitir(entorno: Entorno) -> None:
    for indice in range(5):
        entorno.mover(
            importe=f"{indice + 1}.00",
            sentido="AUMENTA",
            occurred_at=MOMENTO + timedelta(minutes=indice),
        )
    entorno.mover(importe="1.00", sentido="AUMENTA", occurred_at=MOMENTO)  # empate de momento

    paginas: list[service.EstadoDeCuenta] = []
    cursor: str | None = None
    while True:
        pagina = _estado(entorno, cursor=cursor, limite=2)
        paginas.append(pagina)
        cursor = pagina.cursor_siguiente
        if cursor is None:
            break

    ids = [m.id for pagina in paginas for m in pagina.movimientos]
    assert len(ids) == 6
    assert len(set(ids)) == 6
    completo = [m.saldo_acumulado for m in _estado(entorno, limite=200).movimientos]
    assert [m.saldo_acumulado for p in paginas for m in p.movimientos] == completo
    assert completo[-1] == Decimal("16.00")


def test_un_rango_de_fechas_invertido_se_rechaza(entorno: Entorno) -> None:
    from app.modules.cuentas_corrientes.domain.errores import RangoDeFechasInvalidoError

    with pytest.raises(RangoDeFechasInvalidoError):
        _estado(entorno, desde=date(2026, 4, 2), hasta=date(2026, 4, 1))


def test_el_estado_de_cuenta_de_otra_organizacion_no_ve_movimientos(entorno: Entorno) -> None:
    entorno.mover()
    otra = crear_organizacion(entorno.sesion)

    estado = service.estado_de_cuenta(
        otra.id,
        entorno.sesion,
        cuenta_tipo="CLIENTE",
        entidad_id=entorno.cliente_id,
        desde=None,
        hasta=None,
        cursor=None,
        limite=None,
    )

    assert estado.movimientos == []
    assert estado.saldo_actual == Decimal("0.00")


# --- consistencia (INV-13, 02 §7.6) -----------------------------------------------


def test_sin_diferencias_despues_de_operar(entorno: Entorno) -> None:
    entorno.mover(importe="150000.00")
    entorno.mover(sentido="REDUCE", importe="20000.00")
    entorno.mover(cuenta_tipo="PROVEEDOR", tipo="COMPRA", importe="80000.00")

    assert service.verificar_consistencia(entorno.org, entorno.sesion) == []


def test_una_diferencia_se_informa_y_no_se_corrige(entorno: Entorno) -> None:
    entorno.mover(importe="150000.00")
    entorno.mover(sentido="REDUCE", importe="20000.00")
    entorno.sesion.execute(
        text("UPDATE saldo_cuenta SET saldo = 999.00 WHERE organizacion_id = :o"),
        {"o": entorno.org},
    )

    (diferencia,) = service.verificar_consistencia(entorno.org, entorno.sesion)

    assert diferencia.cuenta_tipo == "CLIENTE"
    assert diferencia.entidad_id == entorno.cliente_id
    assert diferencia.saldo_materializado == Decimal("999.00")
    assert diferencia.suma_del_libro == Decimal("130000.00")
    assert service.obtener_saldo(
        entorno.org, entorno.sesion, cuenta_tipo="CLIENTE", entidad_id=entorno.cliente_id
    ) == Decimal("999.00")


def test_la_verificacion_ignora_las_cuentas_de_otra_organizacion(entorno: Entorno) -> None:
    entorno.mover()
    entorno.sesion.execute(
        text("UPDATE saldo_cuenta SET saldo = 1.00 WHERE organizacion_id = :o"),
        {"o": entorno.org},
    )
    otra = crear_organizacion(entorno.sesion)

    assert service.verificar_consistencia(otra.id, entorno.sesion) == []
    assert len(service.verificar_consistencia(entorno.org, entorno.sesion)) == 1
