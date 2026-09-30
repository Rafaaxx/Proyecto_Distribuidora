"""Interfaz pública de `cuentas_corrientes` (`CLAUDE.md` §4: un módulo usa a otro
solo a través de su `service.py`).

La usan `clientes` y `proveedores` (`02` §5.3) y, más adelante, compras (11),
pagos (12), cobranzas (17) y ventas (18a, 19): registrar un movimiento con la
fila de saldo bloqueada, leer o bloquear el saldo, saber si una cuenta tiene
movimientos, registrar un saldo inicial, el estado de cuenta y la verificación de
consistencia.

Sin `commit`: la transacción la gestiona el bus de comandos o quien llama en
pruebas (`CLAUDE.md` §4). Todas las funciones reciben `organizacion_id` como
primer parámetro y lo usan para filtrar.

Toda la validación vive en `domain/`; acá solo se orquesta el orden: validar,
bloquear la fila de saldo (que serializa todo movimiento de la cuenta, `02` §7.3,
ADR-015), decidir con la cuenta ya bloqueada, insertar y actualizar. El libro no
importa `clientes` ni `proveedores`: que la entidad exista en la organización lo
garantiza la FK compuesta de D6, que el repositorio traduce a 404 (D7). El
consumidor final (D4) se reconoce con la configuración de la organización, leída
por `identidad/service.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.modules.cuentas_corrientes import repository
from app.modules.cuentas_corrientes.domain.catalogo import (
    CLIENTE,
    SALDO_INICIAL,
    sentido_de_tipo,
    validar_cuenta_tipo,
    validar_sentido,
    validar_tipo_de_movimiento,
)
from app.modules.cuentas_corrientes.domain.errores import (
    RecursoNoEncontradoError,
    SentidoInvalidoError,
)
from app.modules.cuentas_corrientes.domain.estado_de_cuenta import (
    DiferenciaDeSaldo,
    EstadoDeCuenta,
    rango_de_instantes,
)
from app.modules.cuentas_corrientes.domain.importe import validar_importe
from app.modules.cuentas_corrientes.domain.reglas import (
    efecto_sobre_saldo,
    validar_cuenta_con_titular,
    validar_saldo_inicial_admitido,
)
from app.modules.cuentas_corrientes.models import CuentaMovimiento
from app.modules.cuentas_corrientes.schemas import (
    EstadoDeCuentaResponse,
    estado_de_cuenta_response,
)
from app.modules.identidad import service as identidad_service

__all__ = [
    "DiferenciaDeSaldo",
    "EstadoDeCuenta",
    "EstadoDeCuentaResponse",
    "ResultadoDeMovimiento",
    "bloquear_saldo",
    "cuenta_tiene_movimientos",
    "estado_de_cuenta",
    "estado_de_cuenta_response",
    "obtener_saldo",
    "registrar_movimiento",
    "registrar_saldo_inicial",
    "verificar_consistencia",
]

CERO = Decimal("0.00")


@dataclass(frozen=True)
class ResultadoDeMovimiento:
    """El movimiento insertado y el saldo de la cuenta después de aplicarlo."""

    movimiento: CuentaMovimiento
    saldo: Decimal


def bloquear_saldo(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    cuenta_tipo: str,
    entidad_id: UUID,
) -> Decimal:
    """Bloquea la fila de saldo de la cuenta (`SELECT ... FOR UPDATE`) y devuelve
    el saldo. Si la fila no existe la crea en cero sin carrera (D10). Es el
    primer nivel del orden global de bloqueo (`02` §7.3): el change 18b lo usa
    para evaluar crédito con la fila tomada. Una entidad que no existe en la
    organización es `RecursoNoEncontradoError` (D6, D7)."""
    validar_cuenta_tipo(cuenta_tipo)
    repository.asegurar_saldo(
        organizacion_id,
        sesion,
        cuenta_tipo=cuenta_tipo,
        entidad_id=entidad_id,
        momento=reloj.now(),
    )
    fila = repository.bloquear_saldo(
        organizacion_id, sesion, cuenta_tipo=cuenta_tipo, entidad_id=entidad_id
    )
    if fila is None:  # pragma: no cover -- `asegurar_saldo` acaba de crearla o ya existía
        raise RecursoNoEncontradoError("La cuenta no existe en esta organización.")
    return fila.saldo


def obtener_saldo(
    organizacion_id: UUID, sesion: Session, *, cuenta_tipo: str, entidad_id: UUID
) -> Decimal:
    """Saldo materializado sin bloquear; `0.00` si la cuenta nunca tuvo un
    movimiento (CC-04). No valida que la entidad exista: quien lo expone (la
    ruta de la ficha) ya respondió 404 antes."""
    validar_cuenta_tipo(cuenta_tipo)
    saldo = repository.obtener_saldo(
        organizacion_id, sesion, cuenta_tipo=cuenta_tipo, entidad_id=entidad_id
    )
    return CERO if saldo is None else saldo


def cuenta_tiene_movimientos(
    organizacion_id: UUID, sesion: Session, *, cuenta_tipo: str, entidad_id: UUID
) -> bool:
    """¿La cuenta tiene algún movimiento, de cualquier tipo? Es la respuesta de
    CLI-06 (D8): un cliente con movimientos no vuelve de `INACTIVO` a
    `ACTIVO`. Como ventas y cobranzas también escriben en el libro, la misma
    consulta las cubre cuando lleguen."""
    validar_cuenta_tipo(cuenta_tipo)
    return repository.existe_movimiento(
        organizacion_id, sesion, cuenta_tipo=cuenta_tipo, entidad_id=entidad_id
    )


def _registrar_con_saldo_bloqueado(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    cuenta_tipo: str,
    entidad_id: UUID,
    tipo: str,
    sentido: str,
    importe: Decimal,
    origen_tipo: str,
    origen_id: UUID,
    occurred_at: datetime,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
) -> ResultadoDeMovimiento:
    """Inserta el movimiento y actualiza el saldo. La fila de saldo YA está
    bloqueada por quien llama."""
    ahora = reloj.now()
    movimiento = repository.insertar_movimiento(
        organizacion_id,
        sesion,
        movimiento_id=nuevo_id(),
        cuenta_tipo=cuenta_tipo,
        entidad_id=entidad_id,
        tipo=tipo,
        sentido=sentido,
        importe=importe,
        origen_tipo=origen_tipo,
        origen_id=origen_id,
        occurred_at=occurred_at,
        registered_at=ahora,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )
    saldo = repository.actualizar_saldo(
        organizacion_id,
        sesion,
        cuenta_tipo=cuenta_tipo,
        entidad_id=entidad_id,
        efecto=efecto_sobre_saldo(sentido, importe),
        momento=ahora,
    )
    return ResultadoDeMovimiento(movimiento=movimiento, saldo=saldo)


def registrar_movimiento(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    cuenta_tipo: str,
    entidad_id: UUID,
    tipo: str,
    sentido: str,
    importe: object,
    origen_tipo: str,
    origen_id: UUID,
    occurred_at: datetime,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
) -> ResultadoDeMovimiento:
    """Registra un movimiento en el libro: valida, bloquea la fila de saldo
    (creándola si hace falta, D10), inserta el movimiento y actualiza el saldo,
    todo en la transacción de quien llama (INV-01, INV-13, `02` §7.2).

    `dispositivo_id` sale del sobre del comando y se escribe en el propio libro
    (D14). `importe` se recibe como `object` a propósito: solo un `str` o un
    `Decimal` es dinero exacto (INV-03) y `validar_importe` rechaza el resto con
    `IMPORTE_INVALIDO`, en vez de que el tipo de la firma lo esconda.
    `registered_at` es el momento del reloj inyectable (TR-05). Un tipo
    con sentido fijo (`VENTA` aumenta, `COBRANZA` reduce, CC-05) no admite el
    contrario."""
    validar_tipo_de_movimiento(cuenta_tipo, tipo)
    validar_sentido(sentido)
    esperado = sentido_de_tipo(tipo)
    if esperado is not None and sentido != esperado:
        raise SentidoInvalidoError(f"Un movimiento {tipo} siempre {esperado.lower()} el saldo.")
    importe_validado = validar_importe(importe)

    bloquear_saldo(organizacion_id, sesion, reloj, cuenta_tipo=cuenta_tipo, entidad_id=entidad_id)
    return _registrar_con_saldo_bloqueado(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=cuenta_tipo,
        entidad_id=entidad_id,
        tipo=tipo,
        sentido=sentido,
        importe=importe_validado,
        origen_tipo=origen_tipo,
        origen_id=origen_id,
        occurred_at=occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )


def _es_consumidor_final(
    organizacion_id: UUID, sesion: Session, *, cuenta_tipo: str, entidad_id: UUID
) -> bool:
    """D4: el consumidor final es el cliente que la configuración de la
    organización señala (CLI-03, ADR-029). Un proveedor nunca lo es."""
    if cuenta_tipo != CLIENTE:
        return False
    configuracion = identidad_service.obtener_configuracion(organizacion_id, sesion)
    return configuracion is not None and configuracion.cliente_consumidor_final_id == entidad_id


def registrar_saldo_inicial(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    cuenta_tipo: str,
    entidad_id: UUID,
    importe: object,
    sentido: str,
    occurred_at: datetime,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
) -> ResultadoDeMovimiento:
    """`SALDO_INICIAL_REGISTRAR` (D3, D4, D5).

    Admite cualquier estado de la entidad salvo el consumidor final (D4), y
    varios saldos iniciales por cuenta mientras no tenga movimientos de otro
    tipo (D3): un error de carga se corrige con otro en sentido inverso. La
    comprobación de D3 se hace con la fila de saldo ya bloqueada, así que ningún
    movimiento de otro tipo puede colarse entre la lectura y la inserción.
    `origen_id` es el `operation_id`: no hay una tabla de saldos iniciales a la que
    apuntar (D5)."""
    validar_cuenta_tipo(cuenta_tipo)
    validar_sentido(sentido)
    importe_validado = validar_importe(importe)
    validar_cuenta_con_titular(
        cuenta_tipo,
        es_consumidor_final=_es_consumidor_final(
            organizacion_id, sesion, cuenta_tipo=cuenta_tipo, entidad_id=entidad_id
        ),
    )

    bloquear_saldo(organizacion_id, sesion, reloj, cuenta_tipo=cuenta_tipo, entidad_id=entidad_id)
    validar_saldo_inicial_admitido(
        tiene_movimientos_de_otro_tipo=repository.existe_movimiento(
            organizacion_id,
            sesion,
            cuenta_tipo=cuenta_tipo,
            entidad_id=entidad_id,
            excluyendo_tipo=SALDO_INICIAL,
        )
    )
    return _registrar_con_saldo_bloqueado(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=cuenta_tipo,
        entidad_id=entidad_id,
        tipo=SALDO_INICIAL,
        sentido=sentido,
        importe=importe_validado,
        origen_tipo=SALDO_INICIAL,
        origen_id=operation_id,
        occurred_at=occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )


def estado_de_cuenta(
    organizacion_id: UUID,
    sesion: Session,
    *,
    cuenta_tipo: str,
    entidad_id: UUID,
    desde: date | None,
    hasta: date | None,
    cursor: str | None,
    limite: int | None,
) -> EstadoDeCuenta:
    """Estado de cuenta (CC-07, D9): movimientos en orden `(occurred_at, id)` con
    saldo acumulado real, `saldo_anterior` al período, saldo actual y cursor de la
    página siguiente. `desde` y `hasta` son fechas de negocio en la zona horaria de
    la organización (TR-04); `hasta` se incluye entero."""
    validar_cuenta_tipo(cuenta_tipo)
    organizacion = identidad_service.obtener_organizacion(organizacion_id, sesion)
    if organizacion is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    inicio, fin = rango_de_instantes(desde, hasta, organizacion.zona_horaria)

    movimientos, cursor_siguiente = repository.estado_de_cuenta(
        organizacion_id,
        sesion,
        cuenta_tipo=cuenta_tipo,
        entidad_id=entidad_id,
        desde=inicio,
        hasta=fin,
        cursor=cursor,
        limite=limite,
    )
    saldo_anterior = (
        CERO
        if inicio is None
        else repository.saldo_anterior(
            organizacion_id,
            sesion,
            cuenta_tipo=cuenta_tipo,
            entidad_id=entidad_id,
            antes_de=inicio,
        )
    )
    return EstadoDeCuenta(
        saldo_anterior=saldo_anterior,
        saldo_actual=obtener_saldo(
            organizacion_id, sesion, cuenta_tipo=cuenta_tipo, entidad_id=entidad_id
        ),
        zona_horaria=organizacion.zona_horaria,
        movimientos=movimientos,
        cursor_siguiente=cursor_siguiente,
    )


def verificar_consistencia(organizacion_id: UUID, sesion: Session) -> list[DiferenciaDeSaldo]:
    """Cuentas cuyo saldo materializado no coincide con la suma de su libro
    (INV-13, `02` §7.6). Solo informa: no corrige nada (ADR-015). La tarea diaria
    que la ejecuta y notifica es del change 28."""
    return repository.verificar_consistencia(organizacion_id, sesion)
