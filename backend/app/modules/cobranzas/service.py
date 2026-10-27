"""Interfaz pública de `cobranzas` (`CLAUDE.md` §4: un módulo usa a otro solo a través de su
`service.py`).

Hoy expone `registrar_cobranza` (change 17, grupo 7; COB-01 a COB-03, `design.md` D1 a D5, D8,
D18). Sin `commit`: la transacción la gestiona el bus de comandos (`cobranzas/commands.py`) o
quien llame en pruebas (`CLAUDE.md` §4). Toda función recibe `organizacion_id` como primer
parámetro y lo usa para filtrar.

El servicio orquesta el orden (D18): primero las reglas puras y las lecturas sin bloqueo, que no
dejan nada tomado si fallan; después el saldo del cliente bloqueado `FOR UPDATE` (nivel 1 del
orden de bloqueo, `02` §7.3), la jornada `FOR SHARE` (nivel 5) y, con eso tomado, una sola
escritura de la cobranza con sus medios y su movimiento de cuenta.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.money import redondear_importe
from app.modules.clientes import service as clientes_service
from app.modules.cobranzas import repository
from app.modules.cobranzas.domain.cobranza import (
    CODIGO_JORNADA_LIBERADA,
    ESTADO_ANULADA,
    ORIGEN_INDEPENDIENTE,
    ORIGEN_VENTA,
    MedioResuelto,
    ObservacionDeCobranza,
    evaluar_cobranza_offline,
    referencias_a_guardar,
    validar_cobranza,
    validar_cobranza_a_anular,
    validar_observacion,
)
from app.modules.cobranzas.domain.errores import (
    CobranzaDuplicadaError,
    CobranzaYaAnuladaError,
    JornadaAjenaError,
    MedioPagoInactivoError,
    MotivoInvalidoError,
    RecursoNoEncontradoError,
)
from app.modules.cobranzas.models import Cobranza
from app.modules.configuracion import service as configuracion_service
from app.modules.cuentas_corrientes import service as cuentas_corrientes_service
from app.modules.stock import service as stock_service

__all__ = [
    "MedioACobrar",
    "ResultadoDeCobranza",
    "ResultadoDeAnulacion",
    "anular_cobranza",
    "anular_cobranza_de_venta",
    "registrar_cobranza",
    "tomar_cobranza_de_venta",
]

_CUENTA_CLIENTE = "CLIENTE"
_TIPO_MOVIMIENTO_COBRANZA = "COBRANZA"
_ORIGEN_TIPO_COBRANZA = "COBRANZA"
_TIPO_MOVIMIENTO_ANULACION = "ANULACION_COBRANZA"
_AMBITO_ANULACION_COBRANZA = "ANULACION_COBRANZA"


@dataclass(frozen=True)
class MedioACobrar:
    """Un medio de la cobranza tal como lo informa quien cobra (COB-02)."""

    medio_pago_id: UUID
    importe: Decimal
    referencia: str | None


@dataclass(frozen=True)
class ResultadoDeCobranza:
    """La cobranza confirmada y el saldo del cliente después de aplicarla (CC-04), con las
    observaciones que dejó si entró sin conexión (SYN-07, D13): vacías con conexión."""

    cobranza: Cobranza
    saldo: Decimal
    observaciones: tuple[ObservacionDeCobranza, ...] = ()


def _resolver_medios(
    organizacion_id: UUID,
    sesion: Session,
    medios: Sequence[MedioACobrar],
    *,
    con_conexion: bool = True,
) -> list[MedioResuelto]:
    """TR-09, INV-21: cada medio existe en la organización (404 si no) y está activo
    (`MEDIO_PAGO_INACTIVO`, con conexión, D13 punto 4); devuelve el medio resuelto con su
    nombre, si exige referencia y si está activo. Sin conexión (`con_conexion=False`, D13-C) un
    medio inactivo NO lanza: se informa en `activo` y la cobranza se acepta con `MEDIO_INACTIVO`.

    Los errores llevan la posición del medio en
    `extension["medio"]`, la misma clave que usa la validación compartida."""
    resueltos: list[MedioResuelto] = []
    for indice, medio in enumerate(medios):
        fila = configuracion_service.obtener_medio_pago(
            organizacion_id, medio.medio_pago_id, sesion
        )
        if fila is None:
            raise RecursoNoEncontradoError(
                f"El medio de pago {medio.medio_pago_id} no existe en esta organización.",
                extension={"medio": indice},
            )
        if con_conexion and not fila.activo:
            raise MedioPagoInactivoError(
                f"El medio de pago {medio.medio_pago_id} está inactivo.",
                extension={"medio": indice},
            )
        resueltos.append(
            MedioResuelto(
                medio_pago_id=fila.id,
                nombre=fila.nombre,
                importe=medio.importe,
                referencia=medio.referencia,
                requiere_referencia=fila.requiere_referencia,
                activo=fila.activo,
            )
        )
    return resueltos


def _jornada_de_la_cobranza(
    organizacion_id: UUID,
    sesion: Session,
    *,
    jornada_del_sobre: UUID | None,
    usuario_id: UUID,
    dispositivo_id: UUID,
) -> UUID | None:
    """D8: con conexión, la cobranza lleva la jornada `ABIERTA` del usuario y el dispositivo de
    la sesión (leída `FOR SHARE`, nivel 5); si no tiene, queda sin jornada (también con la
    jornada `EN_RENDICION`). Si el sobre nombra una jornada, tiene que ser esa
    (`JORNADA_AJENA`)."""
    propia = stock_service.jornada_abierta_de(
        organizacion_id, sesion, usuario_id=usuario_id, dispositivo_id=dispositivo_id
    )
    if jornada_del_sobre is not None and jornada_del_sobre != propia:
        raise JornadaAjenaError(
            f"La jornada {jornada_del_sobre} no es la jornada abierta de este usuario y "
            "dispositivo."
        )
    return propia


def _jornada_de_la_cobranza_offline(
    organizacion_id: UUID, sesion: Session, *, jornada_del_sobre: UUID | None
) -> tuple[UUID, ObservacionDeCobranza | None]:
    """D12: sin conexión la cobranza lleva la jornada del sobre en TODOS los casos aceptados. La
    jornada se lee `FOR SHARE` (nivel 5), así una liberación simultánea se ve o espera. Si está
    `LIBERADA`, la cobranza se acepta con `JORNADA_LIBERADA` (jornada y momento de la
    liberación, RUT-09); `ABIERTA`, `EN_RENDICION` y `CERRADA` no observan. Que el sobre traiga la
    jornada y sea del usuario y del dispositivo lo valida el bus antes de reservar."""
    if jornada_del_sobre is None:
        raise JornadaAjenaError("Una cobranza sin conexión pertenece a una jornada del sobre.")
    estado = stock_service.leer_estado_de_jornada(
        organizacion_id, sesion, jornada_id=jornada_del_sobre
    )
    if estado is None:
        raise RecursoNoEncontradoError(
            f"La jornada {jornada_del_sobre} no existe en esta organización."
        )
    if estado.estado != "LIBERADA":
        return estado.jornada_id, None
    return estado.jornada_id, ObservacionDeCobranza(
        CODIGO_JORNADA_LIBERADA,
        {
            "jornada_id": str(estado.jornada_id),
            "liberada_en": None if estado.liberada_en is None else estado.liberada_en.isoformat(),
        },
    )


def registrar_cobranza(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    cobranza_id: UUID,
    cliente_id: UUID,
    importe: Decimal,
    medios: Sequence[MedioACobrar],
    observacion: str | None,
    jornada_del_sobre: UUID | None,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
    modo: str = "ONLINE",
    origen: str = ORIGEN_INDEPENDIENTE,
    venta_id: UUID | None = None,
) -> ResultadoDeCobranza:
    """`COBRANZA_REGISTRAR` con conexión (`design.md` D1 a D5, D8, D18; COB-01 a COB-03, CC-05,
    CC-08, INV-01, INV-08, INV-13, INV-21, TR-09).

    La cobranza nace `CONFIRMADA` y de origen `INDEPENDIENTE`: reduce el saldo general del
    cliente, sin imputarse a ninguna venta (COB-03), por cualquier importe (si supera la deuda
    queda saldo a favor, D5) y a un cliente de cualquier estado salvo el consumidor final (D4).
    El momento es el `occurred_at` del comando (D3), y es el del movimiento `COBRANZA`.

    Sin conexión (`modo="OFFLINE"`, D12, D13-C, SYN-05, SYN-07, INV-17) NUNCA se rechaza por reglas
    de negocio: solo lo malformado (medios que no suman, INV-08) o inexistente (cliente o medio).
    Un medio inactivo, una referencia faltante, el consumidor final y una jornada liberada se
    aceptan con observación (`ResultadoDeCobranza.observaciones`); la cobranza lleva la jornada
    del sobre. Con conexión nada de eso cambia.

    Orden: 1) identificador libre; 2) medios y cliente (404 si no existen en la organización);
    3) reglas puras; 4) saldo del cliente bloqueado `FOR UPDATE`, que serializa dos cobranzas
    simultáneas al mismo cliente; 5) jornada; 6) una sola escritura de la cobranza, sus medios y
    el movimiento (INV-01).

    Change 18a (D12, ADR-052 punto 2): `ventas` registra la cobranza en el acto de su venta con
    `origen="VENTA"` y `venta_id`, dentro de la transacción de la venta; el comando
    `COBRANZA_REGISTRAR` nunca los envía. Sin ellos nada cambia (`INDEPENDIENTE`).
    """
    if (origen, venta_id is not None) not in {
        (ORIGEN_INDEPENDIENTE, False),
        (ORIGEN_VENTA, True),
    }:
        raise ValueError(
            f"El origen {origen!r} no es coherente con la venta {venta_id!r}: `origen` es "
            f"{ORIGEN_VENTA} si y solo si hay `venta_id` (COB-01)."
        )

    # 1) El identificador lo genera quien origina la cobranza; uno ya usado se rechaza.
    if repository.existe_cobranza(organizacion_id, sesion, cobranza_id=cobranza_id):
        raise CobranzaDuplicadaError(
            f"El identificador de cobranza {cobranza_id} ya fue usado por otra operación."
        )

    # 2) Referencias (INV-21): medios activos y cliente de la organización.
    sin_conexion = modo == "OFFLINE"
    resueltos = _resolver_medios(organizacion_id, sesion, medios, con_conexion=not sin_conexion)
    cliente = clientes_service.obtener_cliente_por_id(organizacion_id, cliente_id, sesion)
    if cliente is None:
        raise RecursoNoEncontradoError(f"El cliente {cliente_id} no existe en esta organización.")

    # 3) Reglas puras, antes de tomar ningún bloqueo (INV-01). La restricción del consumidor
    # final (COB-01, CC-08) es de la cobranza independiente: la de una venta de contado
    # (`origen="VENTA"`, change 18a, D5) la admite, y la regla del contado la evalúa `ventas`.
    es_consumidor_final = cliente.es_consumidor_final and origen == ORIGEN_INDEPENDIENTE
    observaciones: list[ObservacionDeCobranza] = []
    if sin_conexion:
        evaluacion = evaluar_cobranza_offline(
            importe,
            resueltos,
            observacion,
            cliente_id=cliente_id,
            es_consumidor_final=es_consumidor_final,
        )
        observacion_a_guardar = evaluacion.observacion
        referencias = evaluacion.referencias
        observaciones.extend(evaluacion.observaciones)
    else:
        observacion_a_guardar = validar_cobranza(
            importe, resueltos, observacion, es_consumidor_final=es_consumidor_final
        )
        referencias = referencias_a_guardar(resueltos)

    # 4) Saldo bloqueado: serializa dos cobranzas simultáneas al mismo cliente (D18, INV-13).
    cuentas_corrientes_service.bloquear_saldo(
        organizacion_id, sesion, reloj, cuenta_tipo=_CUENTA_CLIENTE, entidad_id=cliente_id
    )

    # 5) Jornada `FOR SHARE` (nivel 5).
    jornada_id: UUID | None
    if sin_conexion:
        jornada_id, jornada_liberada = _jornada_de_la_cobranza_offline(
            organizacion_id, sesion, jornada_del_sobre=jornada_del_sobre
        )
        if jornada_liberada is not None:
            observaciones.append(jornada_liberada)
    else:
        jornada_id = _jornada_de_la_cobranza(
            organizacion_id,
            sesion,
            jornada_del_sobre=jornada_del_sobre,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )

    # 6) Una sola escritura de la cobranza con sus medios y su movimiento (INV-01, INV-08).
    importe_a_guardar = redondear_importe(importe)
    cobranza = repository.insertar_cobranza(
        organizacion_id,
        sesion,
        cobranza=repository.DatosDeCobranza(
            id=cobranza_id,
            cliente_id=cliente_id,
            venta_id=venta_id,
            origen=origen,
            importe=importe_a_guardar,
            jornada_id=jornada_id,
            observacion=observacion_a_guardar,
            operation_id=operation_id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=occurred_at,
            registered_at=reloj.now(),
        ),
        medios=[
            repository.DatosDeMedioDeCobranza(
                medio_pago_id=medio.medio_pago_id,
                importe=redondear_importe(medio.importe),
                referencia=referencia,
            )
            for medio, referencia in zip(resueltos, referencias, strict=True)
        ],
    )
    movimiento = cuentas_corrientes_service.registrar_movimiento(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=_CUENTA_CLIENTE,
        entidad_id=cliente_id,
        tipo=_TIPO_MOVIMIENTO_COBRANZA,
        sentido="REDUCE",
        importe=importe_a_guardar,
        origen_tipo=_ORIGEN_TIPO_COBRANZA,
        origen_id=cobranza.id,
        occurred_at=occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )
    return ResultadoDeCobranza(
        cobranza=cobranza, saldo=movimiento.saldo, observaciones=tuple(observaciones)
    )


@dataclass(frozen=True)
class ResultadoDeAnulacion:
    """La cobranza anulada y el saldo del cliente después de devolverlo (CC-04)."""

    cobranza: Cobranza
    saldo: Decimal


@dataclass(frozen=True)
class CobranzaDeVenta:
    """La cobranza en el acto de una venta, como la muestra el detalle de la venta (change 18a,
    D19): identificador, importe y estado."""

    cobranza_id: UUID
    importe: Decimal
    estado: str


def cobranza_de_venta(
    organizacion_id: UUID, sesion: Session, *, venta_id: UUID
) -> CobranzaDeVenta | None:
    """La cobranza de origen `VENTA` de la venta, o `None` si se vendió sin cobrar (VTA-11). Solo
    lectura; una venta de otra organización no tiene cobranza visible (INV-21)."""
    cobranza = repository.obtener_cobranza_de_venta(organizacion_id, venta_id, sesion)
    if cobranza is None:
        return None
    return CobranzaDeVenta(cobranza.id, cobranza.importe, cobranza.estado)


def _validar_motivo_de_anulacion(organizacion_id: UUID, sesion: Session, motivo_id: UUID) -> None:
    """COB-05, TR-09, INV-21: el motivo existe en la organización (404 si no) y es un motivo
    activo del ámbito `ANULACION_COBRANZA` (`MOTIVO_INVALIDO` si no)."""
    motivo = configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
    if motivo is None:
        raise RecursoNoEncontradoError(f"El motivo {motivo_id} no existe en esta organización.")
    if not motivo.activo or motivo.ambito != _AMBITO_ANULACION_COBRANZA:
        raise MotivoInvalidoError(
            f"El motivo {motivo_id} no es un motivo activo de {_AMBITO_ANULACION_COBRANZA}."
        )


def anular_cobranza(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    cobranza_id: UUID,
    motivo_id: UUID,
    observacion: str | None,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
) -> ResultadoDeAnulacion:
    """`COBRANZA_ANULAR` con conexión (`design.md` D7, D18; COB-05, CC-02, CC-04, CC-06, INV-01,
    INV-05, INV-13, INV-21, TR-06).

    Anula una cobranza `CONFIRMADA` entera: la deja `ANULADA`, guarda su anulación con motivo y
    observación y registra `ANULACION_COBRANZA` `AUMENTA` por el importe completo. No borra ni
    edita nada más (TR-06). Se anula la de cualquier usuario, jornada o estado del cliente (D7).

    Orden (D18): 1) observación; 2) cobranza leída sin bloquear (404 si no es de la
    organización); 3) la cobranza `FOR UPDATE` y se revalida estado y origen con la fila tomada;
    4) motivo; 5) `saldo_cuenta` del cliente bloqueado; 6) una sola escritura.
    """
    observacion_a_guardar = validar_observacion(observacion)
    if repository.obtener_cobranza(organizacion_id, cobranza_id, sesion) is None:
        raise RecursoNoEncontradoError(f"La cobranza {cobranza_id} no existe en esta organización.")

    cobranza = repository.obtener_cobranza_para_actualizar(organizacion_id, cobranza_id, sesion)
    assert cobranza is not None  # recién se leyó; las cobranzas no se borran (INV-05)
    validar_cobranza_a_anular(cobranza.estado, cobranza.origen)
    _validar_motivo_de_anulacion(organizacion_id, sesion, motivo_id)

    cuentas_corrientes_service.bloquear_saldo(
        organizacion_id, sesion, reloj, cuenta_tipo=_CUENTA_CLIENTE, entidad_id=cobranza.cliente_id
    )
    repository.marcar_anulada(
        organizacion_id,
        sesion,
        cobranza=cobranza,
        anulacion=repository.DatosDeAnulacion(
            cobranza_id=cobranza.id,
            motivo_id=motivo_id,
            observacion=observacion_a_guardar,
            operation_id=operation_id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=occurred_at,
            registered_at=reloj.now(),
        ),
    )
    movimiento = cuentas_corrientes_service.registrar_movimiento(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=_CUENTA_CLIENTE,
        entidad_id=cobranza.cliente_id,
        tipo=_TIPO_MOVIMIENTO_ANULACION,
        sentido="AUMENTA",
        importe=cobranza.importe,
        origen_tipo=_ORIGEN_TIPO_COBRANZA,
        origen_id=cobranza.id,
        occurred_at=occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )
    return ResultadoDeAnulacion(cobranza=cobranza, saldo=movimiento.saldo)


def tomar_cobranza_de_venta(
    organizacion_id: UUID, sesion: Session, venta_id: UUID
) -> Cobranza | None:
    """Toma `FOR UPDATE` la cobranza de origen `VENTA` de la venta, o `None` (change 19, D9,
    D10: va después de la venta y antes de `saldo_cuenta`)."""
    return repository.tomar_cobranza_de_venta(organizacion_id, venta_id, sesion)


def anular_cobranza_de_venta(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    cobranza: Cobranza,
    motivo_id: UUID,
    observacion: str | None,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
) -> ResultadoDeAnulacion:
    """Anula la cobranza de una venta que se anula con devolución (change 19, D9; VTA-22,
    COB-05, CC-02, INV-05, INV-13). La llama `ventas` dentro de su transacción con la cobranza
    ya tomada `FOR UPDATE` (`tomar_cobranza_de_venta`). Usa el motivo y la observación de la
    venta (ADR-046 punto 2: sin validar el ámbito `ANULACION_COBRANZA`) y registra
    `ANULACION_COBRANZA` `AUMENTA` por el importe completo. `anular_cobranza`
    (`COBRANZA_ANULAR`) sigue rechazando las de origen `VENTA` con `COBRANZA_DE_VENTA`."""
    if cobranza.estado == ESTADO_ANULADA:
        raise CobranzaYaAnuladaError("La cobranza ya está anulada.")
    cuentas_corrientes_service.bloquear_saldo(
        organizacion_id, sesion, reloj, cuenta_tipo=_CUENTA_CLIENTE, entidad_id=cobranza.cliente_id
    )
    repository.marcar_anulada(
        organizacion_id,
        sesion,
        cobranza=cobranza,
        anulacion=repository.DatosDeAnulacion(
            cobranza_id=cobranza.id,
            motivo_id=motivo_id,
            observacion=observacion,
            operation_id=operation_id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=occurred_at,
            registered_at=reloj.now(),
        ),
    )
    movimiento = cuentas_corrientes_service.registrar_movimiento(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=_CUENTA_CLIENTE,
        entidad_id=cobranza.cliente_id,
        tipo=_TIPO_MOVIMIENTO_ANULACION,
        sentido="AUMENTA",
        importe=cobranza.importe,
        origen_tipo=_ORIGEN_TIPO_COBRANZA,
        origen_id=cobranza.id,
        occurred_at=occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )
    return ResultadoDeAnulacion(cobranza=cobranza, saldo=movimiento.saldo)
