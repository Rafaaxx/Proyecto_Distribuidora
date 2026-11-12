"""Change 17, grupo 7, tareas 7.1 y 7.2: `COBRANZA_REGISTRAR` v1 por el bus en modo `ONLINE`,
contra PostgreSQL real.

Se procesa por `sync_service.procesar_comando`, que maneja la transacción (mismo criterio que
`test_pagos_proveedor_registrar.py`). La cobertura HTTP es de `test_cobranzas_api.py` (tarea
7.3); la anulación, de `test_cobranzas_anular.py` (grupo 9); el camino `OFFLINE`, de
`test_cobranzas_offline.py` (grupo 13).

Reglas citadas: COB-01, COB-02, COB-03, CC-05, CC-08, INV-01, INV-03, INV-06, INV-08, INV-13,
INV-21, RUT-07, SEG-06, SEG-07, TR-09, CLI-02, CLI-03 y `design.md` D2, D3, D4, D5, D8, D13, D18.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import (
    MOMENTO,
    PERMISOS_DE_COBRANZA,
    Entorno,
)
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.core.errors import PermisoRequeridoError
from app.modules.cobranzas.domain.errores import (
    CobranzaDuplicadaError,
    ConsumidorFinalSinCuentaError,
    JornadaAjenaError,
    MedioPagoInactivoError,
    RecursoNoEncontradoError,
)
from app.modules.configuracion.domain.medios import (
    ImporteInvalidoError,
    MediosInvalidosError,
    MediosNoSumanImporteError,
    ReferenciaObligatoriaError,
)
from app.modules.cuentas_corrientes.domain.errores import CuentaConOperacionesError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- una cobranza con uno o más medios (COB-01, COB-02, COB-03, CC-05, INV-08) ------------


def test_cobranza_con_efectivo_y_transferencia_queda_confirmada_y_reduce_el_saldo(
    entorno: Entorno,
) -> None:
    """Escenario "Cobranza con efectivo y transferencia" (COB-01, COB-02, COB-03, INV-08)."""
    assert entorno.saldo() == Decimal("150000.00")
    operation_id = uuid4()
    cobranza_id = uuid4()

    comando = entorno.enviar(
        entorno.contenido(cobranza_id=str(cobranza_id)), operation_id=operation_id
    )

    assert comando.estado == "ACEPTADO"
    (cobranza,) = entorno.cobranzas()
    assert cobranza.id == cobranza_id
    assert cobranza.estado == "CONFIRMADA"
    assert cobranza.origen == "INDEPENDIENTE"
    assert cobranza.venta_id is None
    assert cobranza.cliente_id == entorno.cliente_id
    assert cobranza.importe == Decimal("50000.00")
    assert cobranza.observacion is None
    assert cobranza.occurred_at == MOMENTO
    assert cobranza.operation_id == operation_id
    assert cobranza.usuario_id == entorno.usuario_id
    assert cobranza.dispositivo_id == entorno.dispositivo_id
    medios = entorno.medios_de_cobranza()
    assert [(m.orden, m.medio_pago_id, m.importe, m.referencia) for m in medios] == [
        (0, entorno.efectivo_id, Decimal("30000.00"), None),
        (1, entorno.transferencia_id, Decimal("20000.00"), "0042"),
    ]
    assert entorno.saldo() == Decimal("100000.00")
    assert comando.resultado == {
        "cobranza_id": str(cobranza_id),
        "estado": "CONFIRMADA",
        "importe": "50000.00",
        "saldo": "100000.00",
        "jornada_id": None,
    }
    assert entorno.auditorias(operation_id) == 1
    assert entorno.observaciones() == []


def test_otra_cobranza_distinta_tambien_reduce_el_saldo(entorno: Entorno) -> None:
    """Triangulación: dos cobranzas seguidas, cada una con su efecto."""
    entorno.registrar()
    entorno.registrar(
        importe="20000.00", medios=entorno.medios((entorno.efectivo_id, "20000.00", None))
    )

    assert len(entorno.cobranzas()) == 2
    assert entorno.saldo() == Decimal("80000.00")


def test_el_credito_lleva_la_cobranza_como_origen_en_la_cuenta(entorno: Entorno) -> None:
    """Escenario "El crédito lleva la cobranza como origen" (CC-01, CC-05, COB-03)."""
    cobranza_id = uuid4()

    entorno.registrar(cobranza_id=str(cobranza_id))

    (movimiento,) = entorno.movimientos("COBRANZA")
    assert movimiento.sentido == "REDUCE"
    assert movimiento.importe == Decimal("50000.00")
    assert movimiento.origen_tipo == "COBRANZA"
    assert movimiento.origen_id == cobranza_id
    assert movimiento.occurred_at == MOMENTO
    assert movimiento.entidad_id == entorno.cliente_id


def test_la_cobranza_no_se_imputa_a_ninguna_venta(entorno: Entorno) -> None:
    """COB-03: reduce el saldo general; ni venta ni imputación."""
    entorno.registrar()

    (cobranza,) = entorno.cobranzas()
    assert cobranza.venta_id is None


def test_saldo_inicial_despues_de_una_cobranza_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Saldo inicial después de una cobranza" (CC-08)."""
    entorno.registrar()

    with pytest.raises(CuentaConOperacionesError):
        entorno.cargar_saldo_inicial(entorno.cliente_id, "10.00")


# --- observación ----------------------------------------------------------------------


def test_la_observacion_se_guarda_recortada(entorno: Entorno) -> None:
    """Escenario "Observación recortada" (COB-01, D2)."""
    entorno.registrar(
        importe="20000.00",
        medios=entorno.medios((entorno.efectivo_id, "20000.00", None)),
        observacion="  paga facturas de septiembre  ",
    )

    (cobranza,) = entorno.cobranzas()
    assert cobranza.observacion == "paga facturas de septiembre"


def test_la_observacion_vacia_se_guarda_como_nula(entorno: Entorno) -> None:
    entorno.registrar(observacion="   ")

    (cobranza,) = entorno.cobranzas()
    assert cobranza.observacion is None


def test_la_observacion_de_500_se_guarda_completa_y_la_de_501_se_rechaza_sin_efectos(
    entorno: Entorno,
) -> None:
    """Escenario "Observación demasiado larga" (D2): ninguna vía esquiva el límite."""
    entorno.registrar(observacion="b" * 500)
    (cobranza,) = entorno.cobranzas()
    assert cobranza.observacion == "b" * 500

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.registrar(observacion="a" * 501)

    entorno.sesion.rollback()
    assert len(entorno.cobranzas()) == 1


# --- importe y cantidad de medios (TR-01, INV-03) --------------------------------------


@pytest.mark.parametrize("importe", ["0.00", "-1.00", "50000.001"])
def test_importe_invalido_se_rechaza_sin_efectos(entorno: Entorno, importe: str) -> None:
    """Escenario "Importe inválido" (TR-01, INV-03)."""
    with pytest.raises(ImporteInvalidoError):
        entorno.registrar(importe=importe)

    entorno.sin_efectos()


def test_un_importe_como_numero_json_se_rechaza_como_contenido_invalido(entorno: Entorno) -> None:
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.registrar(importe=50000)

    entorno.sin_efectos()


@pytest.mark.parametrize("cantidad", [0, 21])
def test_sin_medios_o_con_demasiados_se_rechaza(entorno: Entorno, cantidad: int) -> None:
    """Escenario "Sin medios o con demasiados"."""
    medios = entorno.medios(*[(entorno.efectivo_id, "1.00", None)] * cantidad)

    with pytest.raises(MediosInvalidosError):
        entorno.registrar(importe="21.00", medios=medios)

    entorno.sin_efectos()


# --- INV-08, referencia, medio inactivo y medio ajeno ----------------------------------


def test_inv08_medios_que_no_suman_el_importe_se_rechazan_sin_efectos(entorno: Entorno) -> None:
    """Escenario "INV-08 — medios que no suman el importe"."""
    with pytest.raises(MediosNoSumanImporteError):
        entorno.registrar(
            medios=entorno.medios(
                (entorno.efectivo_id, "30000.00", None),
                (entorno.transferencia_id, "19000.00", "0042"),
            )
        )

    entorno.sin_efectos()


@pytest.mark.parametrize("referencia", [None, "", "   "])
def test_medio_que_exige_referencia_sin_referencia_se_rechaza_indicando_el_medio(
    entorno: Entorno, referencia: str | None
) -> None:
    """Escenario "Medio que exige referencia sin referencia" (COB-02, `01` §4)."""
    with pytest.raises(ReferenciaObligatoriaError) as error:
        entorno.registrar(
            medios=entorno.medios(
                (entorno.efectivo_id, "30000.00", None),
                (entorno.transferencia_id, "20000.00", referencia),
            )
        )

    assert error.value.extension == {"medio": 1}
    entorno.sin_efectos()


def test_medio_inactivo_con_conexion_se_rechaza_indicando_el_medio_y_sin_observacion(
    entorno: Entorno,
) -> None:
    """Escenario "Medio inactivo con conexión" (TR-09, D13 punto 4)."""
    entorno.desactivar_medio(entorno.efectivo_id)

    with pytest.raises(MedioPagoInactivoError) as error:
        entorno.registrar()

    assert error.value.extension == {"medio": 0}
    entorno.sin_efectos()
    assert entorno.observaciones() == []


def test_el_mismo_medio_puede_repetirse(entorno: Entorno) -> None:
    """Escenario "Mismo medio repetido"."""
    entorno.registrar(
        medios=entorno.medios(
            (entorno.efectivo_id, "25000.00", None), (entorno.efectivo_id, "25000.00", None)
        )
    )

    assert len(entorno.medios_de_cobranza()) == 2


def test_un_medio_de_otra_organizacion_responde_404_sin_efectos(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Medio de otra organización" (INV-21, SEG-07)."""
    ajeno = Entorno(db_session)

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.registrar(
            medios=entorno.medios(
                (entorno.efectivo_id, "30000.00", None), (ajeno.efectivo_id, "20000.00", None)
            )
        )

    assert error.value.status_http == 404
    assert error.value.extension == {"medio": 1}
    entorno.sin_efectos()


# --- saldo a favor (COB-03, D5) --------------------------------------------------------


def test_una_cobranza_mayor_que_la_deuda_deja_saldo_a_favor_sin_observaciones(
    entorno: Entorno,
) -> None:
    """Escenario "Pago de más" (COB-03, CC-04, D5)."""
    comando = entorno.registrar(
        importe="160000.00", medios=entorno.medios((entorno.efectivo_id, "160000.00", None))
    )

    assert comando.estado == "ACEPTADO"
    assert entorno.saldo() == Decimal("-10000.00")
    assert entorno.observaciones() == []


def test_un_cliente_sin_deuda_queda_con_saldo_a_favor(db_session: Session) -> None:
    """Escenario "Cliente sin deuda" (D5)."""
    entorno = Entorno(db_session, saldo_inicial=None)

    entorno.registrar(
        importe="20000.00", medios=entorno.medios((entorno.efectivo_id, "20000.00", None))
    )

    assert entorno.saldo() == Decimal("-20000.00")


# --- cliente de cualquier estado, salvo el consumidor final (D4) ------------------------


def test_se_cobra_a_un_cliente_inactivo_con_deuda(entorno: Entorno) -> None:
    """Escenario "Cliente inactivo con deuda" (CLI-02, D4)."""
    inactivo = entorno.crear_cliente(estado="INACTIVO", nombre="Almacén Don Pedro")
    entorno.cargar_saldo_inicial(inactivo, "12000.00")

    entorno.registrar(
        cliente_id=str(inactivo),
        importe="12000.00",
        medios=entorno.medios((entorno.efectivo_id, "12000.00", None)),
    )

    assert entorno.saldo(inactivo) == Decimal("0.00")


def test_se_cobra_a_un_cliente_suspendido(entorno: Entorno) -> None:
    """Escenario "Cliente suspendido"."""
    suspendido = entorno.crear_cliente(estado="SUSPENDIDO", nombre="Almacén Suspendido")
    entorno.cargar_saldo_inicial(suspendido, "5000.00")

    comando = entorno.registrar(
        cliente_id=str(suspendido),
        importe="5000.00",
        medios=entorno.medios((entorno.efectivo_id, "5000.00", None)),
    )

    assert comando.estado == "ACEPTADO"
    assert entorno.saldo(suspendido) == Decimal("0.00")


def test_la_cobranza_al_consumidor_final_se_rechaza_sin_efectos(entorno: Entorno) -> None:
    """Escenario "Consumidor final" (CLI-03, CC-08, D4)."""
    consumidor = entorno.crear_cliente(es_consumidor_final=True, nombre="Consumidor final")

    with pytest.raises(ConsumidorFinalSinCuentaError) as error:
        entorno.registrar(cliente_id=str(consumidor))

    assert error.value.codigo == "CONSUMIDOR_FINAL_SIN_CUENTA"
    entorno.sin_efectos()


def test_un_cliente_de_otra_organizacion_responde_404_sin_efectos(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Cliente de otra organización" (INV-21, SEG-07)."""
    ajeno = Entorno(db_session)

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.registrar(cliente_id=str(ajeno.cliente_id))

    assert error.value.status_http == 404
    entorno.sin_efectos()


def test_un_cliente_inexistente_responde_404(entorno: Entorno) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        entorno.registrar(cliente_id=str(uuid4()))

    entorno.sin_efectos()


# --- identificador, doble envío, permiso y atomicidad ----------------------------------


def test_un_identificador_de_cobranza_repetido_se_rechaza_y_la_original_no_cambia(
    entorno: Entorno,
) -> None:
    """Escenario "Identificador de cobranza repetido" (`02` §9, SYN-06)."""
    cobranza_id = str(uuid4())
    entorno.registrar(cobranza_id=cobranza_id)
    saldo = entorno.saldo()

    with pytest.raises(CobranzaDuplicadaError) as error:
        entorno.registrar(
            cobranza_id=cobranza_id,
            importe="1000.00",
            medios=entorno.medios((entorno.efectivo_id, "1000.00", None)),
        )

    assert error.value.status_http == 409
    entorno.sesion.rollback()
    (cobranza,) = entorno.cobranzas()
    assert cobranza.importe == Decimal("50000.00")
    assert entorno.saldo() == saldo


def test_el_doble_envio_devuelve_el_resultado_original_sin_duplicar(entorno: Entorno) -> None:
    """Escenario "Doble envío" (INV-06, SYN-02)."""
    operation_id = uuid4()
    contenido = entorno.contenido()
    primero = entorno.enviar(contenido, operation_id=operation_id)

    segundo = entorno.enviar(contenido, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(entorno.cobranzas()) == 1
    assert len(entorno.movimientos("COBRANZA")) == 1
    assert entorno.saldo() == Decimal("100000.00")


def test_el_mismo_operation_id_con_otro_importe_se_rechaza_como_inconsistente(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()
    entorno.enviar(entorno.contenido(), operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(
            entorno.contenido(
                importe="1000.00", medios=entorno.medios((entorno.efectivo_id, "1000.00", None))
            ),
            operation_id=operation_id,
        )

    entorno.sesion.rollback()
    assert len(entorno.cobranzas()) == 1


def test_sin_el_permiso_con_conexion_responde_403_sin_efectos(db_session: Session) -> None:
    """Escenario "Permiso faltante con conexión" (SEG-06, `01` §19)."""
    entorno = Entorno(db_session, permisos=frozenset({"GESTIONAR_CLIENTES"}))

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.registrar()

    assert error.value.status_http == 403
    entorno.sin_efectos()


def test_el_permiso_de_otro_comando_no_alcanza(db_session: Session) -> None:
    entorno = Entorno(db_session, permisos=frozenset({"ANULAR_COBRANZA"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.registrar()

    entorno.sin_efectos()


def test_una_falla_despues_de_los_medios_y_antes_del_movimiento_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Una falla a mitad no deja nada" (INV-01)."""
    from app.modules.cuentas_corrientes import service as cuentas_service

    def _falla(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("falla inyectada antes del movimiento")

    monkeypatch.setattr(cuentas_service, "registrar_movimiento", _falla)

    with pytest.raises(RuntimeError):
        entorno.registrar()

    entorno.sin_efectos()
    assert entorno.saldo() == Decimal("150000.00")


# --- 7.2: la jornada de una cobranza con conexión (D8, RUT-07) -------------------------


def test_la_cobranza_de_un_vendedor_con_jornada_abierta_queda_en_su_jornada(
    db_session: Session,
) -> None:
    """Escenario "Vendedor con jornada abierta" (RUT-07, D8)."""
    entorno = Entorno(db_session, permisos=PERMISOS_DE_COBRANZA)
    jornada_id = entorno.crear_jornada()

    comando = entorno.registrar()

    (cobranza,) = entorno.cobranzas()
    assert cobranza.jornada_id == jornada_id
    assert comando.resultado is not None
    assert comando.resultado["jornada_id"] == str(jornada_id)


def test_la_cobranza_de_administracion_sin_jornada_queda_sin_jornada(entorno: Entorno) -> None:
    """Escenario "Administración sin jornada" (D8)."""
    entorno.registrar()

    (cobranza,) = entorno.cobranzas()
    assert cobranza.jornada_id is None


@pytest.mark.parametrize("estado", ["EN_RENDICION", "CERRADA", "LIBERADA"])
def test_una_jornada_que_no_esta_abierta_no_la_recibe(db_session: Session, estado: str) -> None:
    """Escenario "Jornada en rendición" (D8): la cobranza queda sin jornada."""
    entorno = Entorno(db_session)
    entorno.crear_jornada(estado=estado)

    entorno.registrar()

    (cobranza,) = entorno.cobranzas()
    assert cobranza.jornada_id is None


def test_la_jornada_del_sobre_debe_ser_la_propia(db_session: Session) -> None:
    """Escenario "Jornada del sobre que no es la propia" (D8)."""
    entorno = Entorno(db_session)
    propia = entorno.crear_jornada()
    ajena = entorno.crear_otro_usuario_con_jornada()

    with pytest.raises(JornadaAjenaError) as error:
        entorno.enviar(entorno.contenido(), jornada_id=ajena)

    assert error.value.status_http == 409
    entorno.sin_efectos()
    # La propia sí se acepta, y es la que lleva la cobranza.
    entorno.enviar(entorno.contenido(), jornada_id=propia)
    (cobranza,) = entorno.cobranzas()
    assert cobranza.jornada_id == propia


def test_un_sobre_con_jornada_sin_jornada_abierta_propia_es_jornada_ajena(
    db_session: Session,
) -> None:
    """El sobre nombra una jornada pero la sesión no tiene ninguna abierta (D8)."""
    entorno = Entorno(db_session)
    ajena = entorno.crear_otro_usuario_con_jornada()

    with pytest.raises(JornadaAjenaError):
        entorno.enviar(entorno.contenido(), jornada_id=ajena)

    entorno.sin_efectos()


def test_el_sobre_no_elige_la_organizacion(entorno: Entorno, db_session: Session) -> None:
    """INV-21, TR-08: la organización sale del sobre (el token), nunca del contenido."""
    ajeno = Entorno(db_session)

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.registrar(organizacion_id=str(ajeno.org))

    entorno.sin_efectos()
    assert isinstance(entorno.org, UUID)
