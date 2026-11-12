"""Tarea 5.1: `SALDO_INICIAL_REGISTRAR` v1 por el bus, contra PostgreSQL real.

Se procesa por `sync_service.procesar_comando`, que maneja la transacción (mismo
criterio que `test_clientes_comandos.py`). La cobertura por escenario de la
spec (API, 403, 404, `Operation-Id`) es la tarea 8.1; acá se prueba el comando:
catálogo, esquema estricto, permiso, escritura, auditoría única del bus e
idempotencia.

Reglas citadas: CC-02, CC-03, CC-04, INV-01, INV-06, SYN-02, SYN-06, `01` §21,
ADR-022 y `design.md` D1, D3, D4, D5, D14.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands import catalogo as catalogo_bus
from app.commands import registro
from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import PermisoRequeridoError
from app.modules.cuentas_corrientes import commands as cc_commands
from app.modules.cuentas_corrientes import service as cc_service
from app.modules.cuentas_corrientes.domain.errores import (
    ConsumidorFinalSinCuentaError,
    CuentaConOperacionesError,
    ImporteInvalidoError,
    RecursoNoEncontradoError,
)
from app.modules.cuentas_corrientes.models import CuentaMovimiento
from app.modules.identidad import service as identidad_service
from app.modules.identidad.models import Auditoria
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
TIPO = "SALDO_INICIAL_REGISTRAR"


class Entorno:
    def __init__(self, sesion: Session, *, permisos: frozenset[str] | None = None) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        if permisos is None:
            self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        else:
            self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=permisos
            )
        self.cliente_id = crear_cliente(sesion, self.org)
        self.proveedor_id = crear_proveedor(sesion, self.org)
        sesion.commit()

    def contenido(self, **cambios: object) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "cuenta_tipo": "CLIENTE",
            "entidad_id": str(self.cliente_id),
            "importe": "150000.00",
            "sentido": "AUMENTA",
        }
        cuerpo.update(cambios)
        return cuerpo

    def sobre(
        self, contenido: dict[str, Any], *, operation_id: UUID | None = None, modo: str = "ONLINE"
    ) -> SobreComando:
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=TIPO,
            version=1,
            modo=modo,  # type: ignore[arg-type]
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )

    def enviar(self, contenido: dict[str, Any], *, operation_id: UUID | None = None) -> Comando:
        sobre = self.sobre(contenido, operation_id=operation_id)
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)
        assert isinstance(validado, cc_commands.SaldoInicialRegistrarContenidoV1)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return cc_commands.manejar_saldo_inicial_registrar(
                sobre, validado, sesion=sesion_protegida, reloj=RELOJ
            )

        return sync_service.procesar_comando(
            self.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    def movimientos(self, entidad_id: UUID) -> list[CuentaMovimiento]:
        return list(
            self.sesion.scalars(
                select(CuentaMovimiento).where(
                    CuentaMovimiento.organizacion_id == self.org,
                    CuentaMovimiento.entidad_id == entidad_id,
                )
            ).all()
        )

    def saldo(self, cuenta_tipo: str, entidad_id: UUID) -> Decimal:
        return cc_service.obtener_saldo(
            self.org, self.sesion, cuenta_tipo=cuenta_tipo, entidad_id=entidad_id
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- catálogo y esquema ------------------------------------------------------


def test_el_tipo_esta_declarado_online_y_sin_offline_con_handler_v1() -> None:
    """`02` §6.5: solo online (D1)."""
    declarado = catalogo_bus.tipo_declarado(TIPO)

    assert declarado is not None
    assert declarado.admite_online is True
    assert declarado.admite_offline is False
    handler = registro.resolver_handler(TIPO, 1)
    assert (handler.tipo, handler.version) == (TIPO, 1)


def test_el_esquema_acepta_el_contenido_valido_con_el_importe_como_string() -> None:
    contenido = cc_commands.SaldoInicialRegistrarContenidoV1.model_validate(
        {
            "cuenta_tipo": "PROVEEDOR",
            "entidad_id": str(uuid4()),
            "importe": "80000.00",
            "sentido": "REDUCE",
        }
    )

    assert contenido.importe == "80000.00"
    assert contenido.cuenta_tipo == "PROVEEDOR"
    assert contenido.sentido == "REDUCE"


@pytest.mark.parametrize(
    "cambios",
    [
        {"sentido": "SUMA"},
        {"cuenta_tipo": "EMPLEADO"},
        {"organizacion_id": str(uuid4())},
        {"saldo": "10.00"},
        {"entidad_id": "no-es-un-uuid"},
    ],
)
def test_un_contenido_malformado_se_rechaza_sin_efectos(
    entorno: Entorno, cambios: dict[str, object]
) -> None:
    """SYN-06: catálogos cerrados y `extra="forbid"` (la organización sale del
    token, CC-04: nadie manda un saldo)."""
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(entorno.contenido(**cambios))

    assert entorno.movimientos(entorno.cliente_id) == []


@pytest.mark.parametrize("faltante", ["cuenta_tipo", "entidad_id", "importe", "sentido"])
def test_un_campo_obligatorio_faltante_se_rechaza(entorno: Entorno, faltante: str) -> None:
    contenido = entorno.contenido()
    del contenido[faltante]

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(contenido)


# --- escritura -----------------------------------------------------------------


def test_saldo_inicial_deudor_de_un_cliente_audita_una_sola_vez(entorno: Entorno) -> None:
    operation_id = uuid4()

    comando = entorno.enviar(entorno.contenido(), operation_id=operation_id)

    assert comando.estado == "ACEPTADO"
    (movimiento,) = entorno.movimientos(entorno.cliente_id)
    assert movimiento.tipo == "SALDO_INICIAL"
    assert movimiento.sentido == "AUMENTA"
    assert movimiento.importe == Decimal("150000.00")
    assert movimiento.origen_tipo == "SALDO_INICIAL"
    assert movimiento.origen_id == operation_id
    assert movimiento.operation_id == operation_id
    assert movimiento.occurred_at == MOMENTO
    assert movimiento.usuario_id == entorno.usuario_id
    assert movimiento.dispositivo_id == entorno.dispositivo_id  # D14: del sobre
    assert entorno.saldo("CLIENTE", entorno.cliente_id) == Decimal("150000.00")
    auditorias = entorno.sesion.scalar(
        select(func.count())
        .select_from(Auditoria)
        .where(Auditoria.organizacion_id == entorno.org, Auditoria.operation_id == operation_id)
    )
    assert auditorias == 1  # ADR-022: la única es la del bus


def test_el_resultado_devuelve_el_movimiento_y_el_saldo_como_string(entorno: Entorno) -> None:
    comando = entorno.enviar(entorno.contenido())

    (movimiento,) = entorno.movimientos(entorno.cliente_id)
    assert comando.resultado == {
        "movimiento_id": str(movimiento.id),
        "saldo": "150000.00",
    }


def test_saldo_inicial_de_un_proveedor(entorno: Entorno) -> None:
    comando = entorno.enviar(
        entorno.contenido(
            cuenta_tipo="PROVEEDOR", entidad_id=str(entorno.proveedor_id), importe="80000.00"
        )
    )

    assert comando.estado == "ACEPTADO"
    assert entorno.saldo("PROVEEDOR", entorno.proveedor_id) == Decimal("80000.00")


def test_saldo_inicial_a_favor_del_cliente_es_negativo(entorno: Entorno) -> None:
    entorno.enviar(entorno.contenido(importe="20000.00", sentido="REDUCE"))

    assert entorno.saldo("CLIENTE", entorno.cliente_id) == Decimal("-20000.00")


def test_la_correccion_con_un_saldo_inverso_deja_los_dos_movimientos(entorno: Entorno) -> None:
    """D3."""
    entorno.enviar(entorno.contenido(importe="150000.00", sentido="AUMENTA"))
    entorno.enviar(entorno.contenido(importe="20000.00", sentido="REDUCE"))

    assert len(entorno.movimientos(entorno.cliente_id)) == 2
    assert entorno.saldo("CLIENTE", entorno.cliente_id) == Decimal("130000.00")


# --- idempotencia (INV-06, SYN-02) ----------------------------------------------


def test_el_reenvio_devuelve_el_resultado_original_sin_duplicar(entorno: Entorno) -> None:
    operation_id = uuid4()

    primero = entorno.enviar(entorno.contenido(), operation_id=operation_id)
    segundo = entorno.enviar(entorno.contenido(), operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.movimientos(entorno.cliente_id)) == 1
    assert entorno.saldo("CLIENTE", entorno.cliente_id) == Decimal("150000.00")
    assert (
        entorno.sesion.scalar(
            select(func.count())
            .select_from(Auditoria)
            .where(Auditoria.organizacion_id == entorno.org, Auditoria.operation_id == operation_id)
        )
        == 1
    )


def test_el_mismo_operation_id_con_otro_contenido_es_inconsistente(entorno: Entorno) -> None:
    operation_id = uuid4()
    entorno.enviar(entorno.contenido(importe="150000.00"), operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(entorno.contenido(importe="90000.00"), operation_id=operation_id)

    assert entorno.saldo("CLIENTE", entorno.cliente_id) == Decimal("150000.00")


# --- permiso (D1, SEG-06) ---------------------------------------------------------


def test_sin_importar_datos_se_rechaza_sin_efectos_ni_reserva(db_session: Session) -> None:
    entorno = Entorno(db_session, permisos=frozenset({"GESTIONAR_CLIENTES"}))
    operation_id = uuid4()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.enviar(entorno.contenido(), operation_id=operation_id)

    assert error.value.status_http == 403
    assert entorno.movimientos(entorno.cliente_id) == []
    assert (
        db_session.scalar(
            select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
        )
        == 0
    ), "El rechazo por permiso no deja reserva del operation_id."


# --- reglas de dominio a través del bus (INV-01) -----------------------------------


@pytest.mark.parametrize("importe", ["0.00", "-100.00", "100.005", 150000])
def test_un_importe_invalido_se_rechaza_como_error_de_dominio(
    entorno: Entorno, importe: object
) -> None:
    with pytest.raises(ImporteInvalidoError):
        entorno.enviar(entorno.contenido(importe=importe))

    assert entorno.movimientos(entorno.cliente_id) == []


def test_una_entidad_ajena_o_inexistente_es_404_y_el_operation_id_se_puede_reintentar(
    entorno: Entorno,
) -> None:
    otra = crear_organizacion(entorno.sesion)
    ajeno = crear_cliente(entorno.sesion, otra.id)
    entorno.sesion.commit()
    operation_id = uuid4()

    for entidad in (ajeno, uuid4()):
        with pytest.raises(RecursoNoEncontradoError):
            entorno.enviar(entorno.contenido(entidad_id=str(entidad)), operation_id=operation_id)

    assert entorno.movimientos(ajeno) == []
    # Reintento con contenido corregido con el MISMO operation_id.
    comando = entorno.enviar(entorno.contenido(), operation_id=operation_id)
    assert comando.estado == "ACEPTADO"


def test_una_cuenta_con_operaciones_no_admite_saldo_inicial(entorno: Entorno) -> None:
    cc_service.registrar_movimiento(
        entorno.org,
        entorno.sesion,
        RELOJ,
        cuenta_tipo="CLIENTE",
        entidad_id=entorno.cliente_id,
        tipo="VENTA",
        sentido="AUMENTA",
        importe="500.00",
        origen_tipo="VENTA",
        origen_id=uuid4(),
        occurred_at=MOMENTO,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        operation_id=uuid4(),
    )
    entorno.sesion.commit()

    with pytest.raises(CuentaConOperacionesError):
        entorno.enviar(entorno.contenido())

    assert entorno.saldo("CLIENTE", entorno.cliente_id) == Decimal("500.00")


def test_el_consumidor_final_no_tiene_saldo_inicial(entorno: Entorno) -> None:
    consumidor = crear_cliente(
        entorno.sesion, entorno.org, nombre="Consumidor final", es_consumidor_final=True
    )
    identidad_service.configurar_consumidor_final(
        entorno.org, entorno.sesion, RELOJ, cliente_consumidor_final_id=consumidor
    )
    entorno.sesion.commit()

    with pytest.raises(ConsumidorFinalSinCuentaError):
        entorno.enviar(entorno.contenido(entidad_id=str(consumidor)))

    assert entorno.movimientos(consumidor) == []


def test_una_falla_de_dominio_revierte_tambien_la_reserva_y_la_auditoria(
    entorno: Entorno,
) -> None:
    """INV-01: el handler no hace `commit`; la reversión del bus se lleva todo."""
    operation_id = uuid4()

    with pytest.raises(ImporteInvalidoError):
        entorno.enviar(entorno.contenido(importe="0.00"), operation_id=operation_id)

    assert (
        entorno.sesion.scalar(
            select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
        )
        == 0
    )
    assert (
        entorno.sesion.scalar(
            select(func.count())
            .select_from(Auditoria)
            .where(Auditoria.operation_id == operation_id)
        )
        == 0
    )


def test_el_modo_offline_no_se_admite(entorno: Entorno) -> None:
    """`02` §6.5: el saldo inicial es solo online. El catálogo del bus lo
    declara y el bus lo rechaza antes de llegar al handler (SYN-06); acá se
    comprueba la declaración que el bus consulta."""
    declarado = catalogo_bus.tipo_declarado(TIPO)

    assert declarado is not None
    assert not declarado.admite_offline


def test_el_lote_rechaza_el_saldo_inicial_enviado_sin_conexion(entorno: Entorno) -> None:
    """`02` §6.5, escenario "No se admite sin conexión": el bus real, no solo el
    catálogo, rechaza el comando en modo `OFFLINE` con un código estable y sin
    dejar reserva, movimiento ni saldo."""
    operation_id = uuid4()
    item = ItemLote(
        operation_id=operation_id,
        tipo=TIPO,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=entorno.contenido(),
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert entorno.movimientos(entorno.cliente_id) == []
    assert (
        entorno.sesion.scalar(
            select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
        )
        == 0
    )


@pytest.mark.parametrize("estado", ["ACTIVO", "SUSPENDIDO", "INACTIVO"])
def test_el_saldo_inicial_por_el_bus_se_admite_en_cualquier_estado_de_cliente(
    entorno: Entorno, estado: str
) -> None:
    """Escenario "Saldo inicial de un cliente suspendido" (D4), por el bus."""
    cliente = crear_cliente(entorno.sesion, entorno.org, estado=estado, nombre=f"Cliente {estado}")
    entorno.sesion.commit()

    comando = entorno.enviar(entorno.contenido(entidad_id=str(cliente), importe="700.00"))

    assert comando.estado == "ACEPTADO"
    assert entorno.saldo("CLIENTE", cliente) == Decimal("700.00")


@pytest.mark.parametrize("activo", [True, False])
def test_el_saldo_inicial_por_el_bus_se_admite_en_proveedor_activo_o_inactivo(
    entorno: Entorno, activo: bool
) -> None:
    """Escenario "Saldo inicial de un proveedor inactivo" (D4), por el bus."""
    proveedor = crear_proveedor(entorno.sesion, entorno.org, activo=activo)
    entorno.sesion.commit()

    comando = entorno.enviar(
        entorno.contenido(cuenta_tipo="PROVEEDOR", entidad_id=str(proveedor), importe="900.00")
    )

    assert comando.estado == "ACEPTADO"
    assert entorno.saldo("PROVEEDOR", proveedor) == Decimal("900.00")
