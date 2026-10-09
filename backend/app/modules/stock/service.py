"""Interfaz pública de `stock` (`CLAUDE.md` §4: un módulo usa a otro solo a través
de su `service.py`).

La usan importaciones (10), compras (11), transferencias y ajustes (14) y, más
adelante, ventas de ruta (15, 18a, 19) y rendiciones (24): registrar movimientos con
las filas bloqueadas en el orden global, registrar stock inicial, administrar
ubicaciones y leer saldos, kardex y la verificación de consistencia.

Sin `commit`: la transacción la gestiona el bus de comandos o quien llama en
pruebas (`CLAUDE.md` §4). Todas las funciones reciben `organizacion_id` como
primer parámetro y lo usan para filtrar.

Toda la validación vive en `domain/`; acá solo se orquesta el orden. Un movimiento
bloquea, en este orden (`02` §7.3, ADR-015, `design.md` D9): las ubicaciones
`FOR SHARE` (D8), las filas de `costo_producto` por `producto_id` ascendente (vía
`costeo`, que es el único que las conoce) y las de `stock_saldo` por
`(producto_id, ubicacion_id)` ascendentes; recién entonces decide e inserta. Desde el
change 14 los productos se toman `FOR SHARE` (por id ascendente) entre las ubicaciones y
las filas de costo (D4.2). Quien
necesite `saldo_cuenta` (11, 18a) lo bloquea ANTES de llamar a `stock`. El costo
promedio lo calcula solo `costeo` (CST-14): este módulo no calcula ni un costo. El
producto se valida por FK compuesta (404) y su estado por `catalogo/service.py`.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import DomainError, PermisoRequeridoError
from app.core.ids import nuevo_id
from app.modules.catalogo import service as catalogo_service
from app.modules.configuracion import service as configuracion_service
from app.modules.costeo import service as costeo_service
from app.modules.identidad import service as identidad_service
from app.modules.stock import repository
from app.modules.stock.domain.anulaciones import (
    AMBITO_ANULACION_AJUSTE,
    AMBITO_ANULACION_TRANSFERENCIA,
    PERMISO_PERMITIR_STOCK_NEGATIVO,
    LineaDeAjusteOriginal,
    MovimientoOriginal,
    expandir_anulacion_ajuste,
    expandir_anulacion_transferencia,
    puede_anular_transferencia,
    validar_anulable,
    validar_motivo_de_anulacion,
)
from app.modules.stock.domain.errores import (
    ProductoInactivoError,
    ProductoSinCostoError,
    RecursoNoEncontradoError,
    StockInsuficienteError,
)
from app.modules.stock.domain.kardex import (
    DiferenciaDeStock,
    Kardex,
    LineaDeKardex,
    codificar_cursor_de_id,
    codificar_cursor_de_producto,
    decodificar_cursor_de_id,
    decodificar_cursor_de_producto,
    limite_efectivo,
    rango_de_instantes,
)
from app.modules.stock.domain.movimientos import (
    AJUSTE,
    ANULACION_COMPRA,
    ORIGEN_AJUSTE,
    ORIGEN_TRANSFERENCIA,
    STOCK_INICIAL,
    TIPOS_QUE_INGRESAN_SIN_COSTO,
    LineaDeMovimiento,
    LineaDeStockInicial,
    diferencias_de_stock_total,
    lleva_el_costo_original,
    productos_que_exigen_estar_activos,
    puede_quedar_negativo,
    validar_lineas_de_movimiento,
    validar_lineas_de_stock_inicial,
    validar_producto_activo,
    validar_stock_inicial_admitido,
    validar_ubicacion_activa,
)
from app.modules.stock.domain.operaciones import (
    LineaDeOperacion,
    expandir_ajuste,
    expandir_transferencia,
    validar_ajuste,
    validar_ingreso_con_costo,
    validar_motivo_de_ajuste,
    validar_transferencia,
)
from app.modules.stock.domain.ubicaciones import (
    validar_desactivacion,
    validar_ubicacion,
)
from app.modules.stock.models import (
    AjusteStock,
    AjusteStockLinea,
    StockMovimiento,
    Transferencia,
    TransferenciaLinea,
    Ubicacion,
)

__all__ = [
    "DiferenciaDeStock",
    "Kardex",
    "LineaDeAjuste",
    "LineaDeMovimiento",
    "LineaDeStock",
    "LineaDeStockInicial",
    "LineaDeTransferencia",
    "ResultadoDeAjuste",
    "ResultadoDeTransferencia",
    "SaldoDeLinea",
    "SaldoDeLineaDeAjuste",
    "SaldoNegativo",
    "PaginaDeUbicaciones",
    "ResultadoDeMovimiento",
    "StockDeUbicacion",
    "ajustar",
    "anular_ajuste",
    "anular_transferencia",
    "buscar_ubicaciones_por_nombre",
    "crear_ubicacion",
    "kardex",
    "lineas_de_ajuste",
    "listar_ubicaciones",
    "modificar_ubicacion",
    "obtener_saldo",
    "obtener_ubicacion",
    "producto_tiene_stock",
    "registrar_movimientos",
    "registrar_stock_inicial",
    "stock_por_ubicacion",
    "transferir",
    "verificar_consistencia",
]


@dataclass(frozen=True)
class ResultadoDeMovimiento:
    """El movimiento insertado y el saldo del producto en la ubicación después de
    aplicarlo."""

    movimiento: StockMovimiento
    saldo: int
    saldo_negativo: bool = False
    """El egreso dejó el saldo de la ubicación por debajo de cero (CMP-07, D10)."""
    promedio_recalculado: bool | None = None
    """Solo en un egreso `ANULACION_COMPRA`: si `costeo` recalculó el promedio (CMP-06);
    `None` en cualquier otro movimiento."""


@dataclass(frozen=True)
class LineaDeStock:
    """El stock de un producto en una ubicación (STK-01): cantidad en unidad base,
    las unidades de la presentación de referencia para mostrarla en cajas + unidades
    (CAT-08, `None` si el producto no tiene una) y el costo promedio vigente (`None`
    sin ingresos con costo, D10). Quien expone el promedio decide si el usuario lo
    ve (`VER_COSTOS`, D3)."""

    producto_id: UUID
    producto_codigo: str
    producto_nombre: str
    cantidad_base: int
    unidades_referencia: int | None
    nombre_referencia: str | None
    costo_promedio: Decimal | None


@dataclass(frozen=True)
class PaginaDeUbicaciones:
    """Una página de ubicaciones y el cursor de la siguiente."""

    ubicaciones: list[Ubicacion]
    cursor_siguiente: str | None


@dataclass(frozen=True)
class StockDeUbicacion:
    """Una página del stock de una ubicación y el cursor de la siguiente."""

    lineas: list[LineaDeStock]
    cursor_siguiente: str | None


# --- ubicaciones (STK-02, D7, D8) -----------------------------------------------


def crear_ubicacion(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    tipo: str,
    requiere_toma: bool,
    actor_id: UUID | None,
) -> Ubicacion:
    """`UBICACION_CREAR`: valida (nombre, tipo, `VEHICULO_REQUIERE_TOMA`) y crea la
    ubicación activa. Un nombre repetido en la organización, activo o no y sin
    distinguir mayúsculas, es `NOMBRE_DUPLICADO` (D7)."""
    datos = validar_ubicacion(nombre=nombre, tipo=tipo, requiere_toma=requiere_toma)
    return repository.crear_ubicacion(
        organizacion_id,
        sesion,
        ubicacion_id=nuevo_id(),
        nombre=datos.nombre,
        tipo=datos.tipo,
        requiere_toma=datos.requiere_toma,
        activo=True,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )


def listar_ubicaciones(
    organizacion_id: UUID,
    sesion: Session,
    *,
    activo: bool | None,
    cursor: str | None,
    limite: int | None,
) -> PaginaDeUbicaciones:
    """Ubicaciones de la organización, en orden de alta, con filtro opcional por
    estado y paginadas por cursor (D11: mismo contrato que el resto de las
    listas). Un cursor ilegible es `CURSOR_INVALIDO`."""
    despues_de = None if cursor is None else decodificar_cursor_de_id(cursor)
    limite_pagina = limite_efectivo(limite)
    filas = repository.listar_ubicaciones(
        organizacion_id,
        sesion,
        activo=activo,
        despues_de_id=despues_de,
        limite=limite_pagina + 1,
    )
    pagina = filas[:limite_pagina]
    cursor_siguiente = (
        codificar_cursor_de_id(pagina[-1].id) if len(filas) > limite_pagina and pagina else None
    )
    return PaginaDeUbicaciones(ubicaciones=pagina, cursor_siguiente=cursor_siguiente)


def obtener_ubicacion(
    organizacion_id: UUID, sesion: Session, ubicacion_id: UUID
) -> Ubicacion | None:
    """Lectura pública: la ubicación de la organización, o `None` (que quien la
    expone responde como 404, INV-21)."""
    return repository.obtener_ubicacion(organizacion_id, sesion, ubicacion_id=ubicacion_id)


def buscar_ubicaciones_por_nombre(
    organizacion_id: UUID, nombre: str, sesion: Session
) -> list[Ubicacion]:
    """Lectura pública para la importación (change 10, `design.md` D4): ubicaciones de
    la organización con ese nombre, sin distinguir mayúsculas ni espacios al borde,
    activas o no (el stock inicial rechaza después una inactiva con
    `UBICACION_INACTIVA`)."""
    return repository.buscar_ubicaciones_por_nombre(organizacion_id, sesion, nombre=nombre)


def modificar_ubicacion(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    ubicacion_id: UUID,
    nombre: str,
    tipo: str,
    requiere_toma: bool,
    activo: bool,
    actor_id: UUID | None,
) -> Ubicacion:
    """`UBICACION_MODIFICAR`: valida como el alta y aplica D8. La ubicación se toma
    `FOR UPDATE` primero (ningún movimiento se registra sobre ella mientras se
    decide) y, si se desactiva, se comprueba con las filas de saldo leídas `FOR
    SHARE` que ninguna sea distinta de cero (`UBICACION_CON_STOCK`). Una
    ubicación ajena o inexistente es `RecursoNoEncontradoError` (INV-21)."""
    datos = validar_ubicacion(nombre=nombre, tipo=tipo, requiere_toma=requiere_toma)
    ubicacion = repository.obtener_ubicacion(
        organizacion_id, sesion, ubicacion_id=ubicacion_id, para_actualizar=True
    )
    if ubicacion is None:
        raise RecursoNoEncontradoError("La ubicación no existe en esta organización.")

    if ubicacion.activo and not activo:
        validar_desactivacion(
            tiene_saldos_distintos_de_cero=repository.hay_saldos_distintos_de_cero(
                organizacion_id, sesion, ubicacion_id=ubicacion_id
            )
        )
    return repository.modificar_ubicacion(
        organizacion_id,
        sesion,
        ubicacion=ubicacion,
        nombre=datos.nombre,
        tipo=datos.tipo,
        requiere_toma=datos.requiere_toma,
        activo=activo,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )


# --- movimientos (STK-03, STK-05, D4, D5, D8, D9) --------------------------------


def _con_costo_validado(linea: LineaDeMovimiento) -> LineaDeMovimiento:
    """Valida el costo de una línea que ingresa con las reglas de `costeo` (D6) y
    lo deja como `Decimal` con 6 decimales. `stock` no valida costos: lo hace su
    dueño (CST-14)."""
    if linea.costo_unitario is None:
        return linea
    return replace(linea, costo_unitario=costeo_service.validar_costo(linea.costo_unitario))


def _preparar(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    lineas: Sequence[LineaDeMovimiento],
) -> list[LineaDeMovimiento]:
    """Valida las líneas contra la base y toma los bloqueos en el orden global.

    1. Ubicaciones `FOR SHARE` (existen, D8: activas) y después productos `FOR SHARE`
       (existen, CAT-05: activos), cada grupo en orden ascendente de id. El producto
       compartido serializa el movimiento con la desactivación del producto, que lo toma
       `FOR UPDATE` (change 14, D4.2, enmienda `02` §7.3).
    2. `costo_producto` por `producto_id` ascendente (vía `costeo`).
    3. `stock_saldo` por `(producto_id, ubicacion_id)` ascendentes, creando la fila
       en cero si no existe, sin carrera (D10).

    Devuelve las líneas con el costo validado. NO escribe ningún movimiento."""
    validadas = [_con_costo_validado(linea) for linea in lineas]

    ubicaciones = repository.bloquear_ubicaciones_compartidas(
        organizacion_id, sesion, ubicaciones={linea.ubicacion_id for linea in validadas}
    )
    for ubicacion_id in sorted({linea.ubicacion_id for linea in validadas}):
        ubicacion = ubicaciones.get(ubicacion_id)
        if ubicacion is None:
            raise RecursoNoEncontradoError("La ubicación no existe en esta organización.")
        validar_ubicacion_activa(activo=ubicacion.activo)

    productos = sorted({linea.producto_id for linea in validadas})
    exigen_activo = productos_que_exigen_estar_activos(validadas)
    for producto_id in productos:
        producto = catalogo_service.obtener_producto_para_compartir(
            organizacion_id, producto_id, sesion
        )
        if producto is None:
            raise RecursoNoEncontradoError(
                "El producto no existe en esta organización.",
                extension={"producto_id": str(producto_id)},
            )
        if producto_id in exigen_activo:  # D11: la reversión admite un producto inactivo
            try:
                validar_producto_activo(activo=producto.activo)
            except ProductoInactivoError as error:
                error.extension = {"producto_id": str(producto_id)}
                raise

    costeo_service.bloquear_costos(organizacion_id, sesion, reloj, productos)

    ahora = reloj.now()
    pares = sorted({(linea.producto_id, linea.ubicacion_id) for linea in validadas})
    for producto_id, ubicacion_id in pares:
        repository.asegurar_saldo(
            organizacion_id,
            sesion,
            producto_id=producto_id,
            ubicacion_id=ubicacion_id,
            momento=ahora,
        )
        repository.bloquear_saldo(
            organizacion_id, sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
        )
    return validadas


def _costo_original(linea: LineaDeMovimiento) -> Decimal | None:
    """D5.2: el costo que lleva un inverso de anulación, validado por `costeo`; `None` si
    el movimiento original no tenía costo."""
    if linea.costo_unitario is None:
        return None
    return costeo_service.validar_costo(linea.costo_unitario)


def _aplicar(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    lineas: Sequence[LineaDeMovimiento],
    *,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
    permitir_negativo: bool = False,
) -> list[ResultadoDeMovimiento]:
    """Aplica las líneas, en el orden recibido, con todos los bloqueos tomados por
    `_preparar`: cada una actualiza `costo_producto` (vía `costeo`) y
    `stock_saldo` e inserta su movimiento. Un ingreso recalcula el promedio y se
    guarda con su costo; un egreso se valoriza al promedio vigente y solo se aplica
    si el saldo alcanza (`02` §7.4, STK-05)."""
    ahora = reloj.now()
    resultados: list[ResultadoDeMovimiento] = []
    for linea in lineas:
        costo_unitario: Decimal | None
        promedio_recalculado: bool | None = None
        if linea.cantidad_base > 0:
            if linea.tipo == AJUSTE and not lleva_el_costo_original(linea):
                # D3, D9: con la fila de costo ya bloqueada por `_preparar`: un ajuste
                # positivo de un producto sin promedio no se admite.
                try:
                    validar_ingreso_con_costo(
                        cantidad_base=linea.cantidad_base,
                        costo_promedio=costeo_service.obtener_promedio(
                            organizacion_id, sesion, linea.producto_id
                        ),
                    )
                except ProductoSinCostoError as error:
                    error.extension = {"producto_id": str(linea.producto_id)}
                    raise
            if linea.tipo in TIPOS_QUE_INGRESAN_SIN_COSTO:
                # CST-12, D9: no recalcula ni deja historia; se valoriza al promedio
                # vigente, salvo el inverso de una anulación, que repite el costo del
                # movimiento original (D5.2) y descarta el valor que devuelve `costeo`.
                promedio_vigente = costeo_service.aplicar_ingreso_sin_recalculo(
                    organizacion_id,
                    sesion,
                    reloj,
                    producto_id=linea.producto_id,
                    cantidad=linea.cantidad_base,
                )
                costo_unitario = (
                    _costo_original(linea) if lleva_el_costo_original(linea) else promedio_vigente
                )
            else:
                costeo_service.aplicar_ingreso(
                    organizacion_id,
                    sesion,
                    reloj,
                    producto_id=linea.producto_id,
                    cantidad=linea.cantidad_base,
                    costo_unitario=linea.costo_unitario,
                    origen_tipo=linea.tipo,
                    origen_id=linea.origen_id,
                    operation_id=operation_id,
                )
                costo_unitario = costeo_service.validar_costo(linea.costo_unitario)
            saldo = repository.ingresar_al_saldo(
                organizacion_id,
                sesion,
                producto_id=linea.producto_id,
                ubicacion_id=linea.ubicacion_id,
                cantidad=linea.cantidad_base,
                momento=ahora,
            )
        else:
            magnitud = -linea.cantidad_base
            nuevo_saldo = repository.egresar_del_saldo(
                organizacion_id,
                sesion,
                producto_id=linea.producto_id,
                ubicacion_id=linea.ubicacion_id,
                cantidad=magnitud,
                momento=ahora,
                permitir_negativo=puede_quedar_negativo(linea, permitir_negativo=permitir_negativo),
            )
            if nuevo_saldo is None:
                actual = repository.obtener_saldo(
                    organizacion_id,
                    sesion,
                    producto_id=linea.producto_id,
                    ubicacion_id=linea.ubicacion_id,
                )
                raise StockInsuficienteError(
                    f"El saldo es {actual or 0} y se pretende egresar {magnitud}.",
                    extension={
                        "producto_id": str(linea.producto_id),
                        "ubicacion_id": str(linea.ubicacion_id),
                    },
                )
            saldo = nuevo_saldo
            if linea.tipo == ANULACION_COMPRA:
                # D9: revierte el ingreso en `costeo` y queda con el costo de la línea.
                reversion = costeo_service.revertir_ingreso(
                    organizacion_id,
                    sesion,
                    reloj,
                    producto_id=linea.producto_id,
                    cantidad=magnitud,
                    costo_unitario=linea.costo_unitario,
                    origen_id=linea.origen_id,
                    operation_id=operation_id,
                )
                costo_unitario = costeo_service.validar_costo(linea.costo_unitario)
                promedio_recalculado = reversion.recalculado
            else:
                egreso = costeo_service.aplicar_egreso(
                    organizacion_id,
                    sesion,
                    reloj,
                    producto_id=linea.producto_id,
                    cantidad=magnitud,
                )
                # D5.2: el inverso de una anulación guarda el costo del original (puede ser
                # nulo) y no el promedio vigente; `costeo` solo mueve el stock total.
                costo_unitario = (
                    _costo_original(linea)
                    if lleva_el_costo_original(linea)
                    else egreso.costo_valorizacion
                )

        movimiento = repository.insertar_movimiento(
            organizacion_id,
            sesion,
            movimiento_id=nuevo_id(),
            producto_id=linea.producto_id,
            ubicacion_id=linea.ubicacion_id,
            cantidad_base=linea.cantidad_base,
            tipo=linea.tipo,
            origen_tipo=linea.origen_tipo,
            origen_id=linea.origen_id,
            costo_unitario=costo_unitario,
            jornada_id=linea.jornada_id,
            motivo_id=linea.motivo_id,
            operation_id=operation_id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=occurred_at,
            registered_at=ahora,
        )
        resultados.append(
            ResultadoDeMovimiento(
                movimiento=movimiento,
                saldo=saldo,
                saldo_negativo=saldo < 0,
                promedio_recalculado=promedio_recalculado,
            )
        )
    return resultados


def registrar_movimientos(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    lineas: Sequence[LineaDeMovimiento],
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
    permitir_negativo: bool = False,
) -> list[ResultadoDeMovimiento]:
    """Registra movimientos de stock con todas las filas bloqueadas en el orden
    global (`02` §7.3), todo en la transacción de quien llama (INV-01, INV-12).

    Reúne los pares, valida (tipo del catálogo, cantidad entera distinta de cero,
    costo según el signo, ubicación y producto existentes y activos), bloquea
    ubicaciones, costos y saldos en orden y recién entonces aplica cada línea. Los
    ingresos que recalculan el promedio son los de compra, stock inicial y anulación
    de venta (CST-11); los egresos, de cualquier tipo, se valorizan al promedio
    vigente y no dejan el saldo negativo (STK-05, `02` §7.4, D4). Change 14: la entrada
    de transferencia y el ajuste positivo no llevan costo, suben `stock_total` y se
    valorizan al promedio vigente sin recalcularlo (CST-12, D9); la salida de una
    transferencia admite saldo negativo con permiso y un ajuste nunca (D1 = B); un
    inverso de anulación lleva el costo del movimiento original (D5.2). Un ingreso de
    rendición se rechaza (change 24). Una referencia ajena o inexistente es 404
    (INV-21).

    Change 11: un egreso `ANULACION_COMPRA` lleva el costo base de la línea que
    revierte y delega en `costeo.revertir_ingreso` (CMP-06, D9); admite un producto
    inactivo (CAT-05, D11) y, con `permitir_negativo` (el permiso
    `PERMITIR_STOCK_NEGATIVO`, CMP-07), puede dejar el saldo negativo, que el
    resultado marca (D10). `permitir_negativo` no alcanza a otros tipos."""
    validadas = validar_lineas_de_movimiento(lineas)
    preparadas = _preparar(organizacion_id, sesion, reloj, validadas)
    return _aplicar(
        organizacion_id,
        sesion,
        reloj,
        preparadas,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
        occurred_at=occurred_at,
        permitir_negativo=permitir_negativo,
    )


def registrar_stock_inicial(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    ubicacion_id: UUID,
    lineas: Sequence[LineaDeStockInicial],
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
) -> list[ResultadoDeMovimiento]:
    """`STOCK_INICIAL_REGISTRAR` (D4, D5, D6, D8).

    De 1 a 200 líneas, un producto por línea, `cantidad_base` entera distinta de
    cero. Una línea positiva es un ingreso con costo que recalcula el promedio
    (CST-11); una negativa es una corrección que egresa al promedio vigente sin
    recalcularlo y no deja negativo el saldo (`STOCK_INSUFICIENTE`, D4). El stock
    inicial se admite solo mientras el producto no tenga en la organización
    movimientos de otro tipo (`PRODUCTO_CON_OPERACIONES`): se comprueba con la fila
    de costo del producto ya bloqueada, así que ningún movimiento de otro tipo puede
    colarse entre la lectura y la inserción. `origen_id` es el `operation_id`: no
    hay una tabla de stock inicial a la que apuntar (D5). Atómico (INV-01): todas
    las validaciones ocurren antes de escribir el primer movimiento."""
    validadas = validar_lineas_de_stock_inicial(lineas)
    movimientos = [
        LineaDeMovimiento(
            producto_id=linea.producto_id,
            ubicacion_id=ubicacion_id,
            cantidad_base=linea.cantidad_base,
            tipo=STOCK_INICIAL,
            costo_unitario=linea.costo_unitario,
            origen_tipo=STOCK_INICIAL,
            origen_id=operation_id,
        )
        for linea in validadas
    ]
    preparadas = _preparar(organizacion_id, sesion, reloj, movimientos)

    for linea in preparadas:
        validar_stock_inicial_admitido(
            tiene_movimientos_de_otro_tipo=repository.existe_movimiento(
                organizacion_id,
                sesion,
                producto_id=linea.producto_id,
                excluyendo_tipo=STOCK_INICIAL,
            )
        )
    return _aplicar(
        organizacion_id,
        sesion,
        reloj,
        preparadas,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
        occurred_at=occurred_at,
    )


# --- transferencias (STK-07, change 14, D1, D6, D9) -------------------------------


@dataclass(frozen=True)
class LineaDeTransferencia:
    """Una línea del comando `STOCK_TRANSFERIR`: producto y `cantidad_base` (> 0)."""

    producto_id: UUID
    cantidad_base: int


@dataclass(frozen=True)
class SaldoDeLinea:
    """Los saldos que quedaron en el origen y en el destino para la línea de un producto."""

    producto_id: UUID
    cantidad_base: int
    saldo_origen: int
    saldo_destino: int


@dataclass(frozen=True)
class SaldoNegativo:
    """Un producto en una ubicación que quedó bajo cero (STK-05, D1): alimenta la
    observación `STOCK_NEGATIVO` del comando."""

    producto_id: UUID
    ubicacion_id: UUID
    saldo: int


@dataclass(frozen=True)
class ResultadoDeTransferencia:
    transferencia: Transferencia
    lineas: list[TransferenciaLinea]
    saldos: list[SaldoDeLinea]
    negativos: list[SaldoNegativo]


def _indicar_la_linea(error: DomainError, lineas: Sequence[LineaDeOperacion]) -> None:
    """Contrato de la API (P9): si el error nombra un producto, agrega el índice 0-based de
    la línea que lo causó en `extension["linea"]`, para que la pantalla lo muestre junto a
    esa línea."""
    producto_id = (error.extension or {}).get("producto_id")
    for indice, linea in enumerate(lineas):
        if str(linea.producto_id) == producto_id:
            error.extension = {**(error.extension or {}), "linea": indice}
            return


def transferir(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    ubicacion_origen_id: UUID,
    ubicacion_destino_id: UUID,
    lineas: Sequence[LineaDeTransferencia],
    observacion: str | None,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
    permitir_negativo: bool = False,
) -> ResultadoDeTransferencia:
    """`STOCK_TRANSFERIR` (STK-07, `design.md` D1, D6, D9): valida el contenido, llama UNA
    sola vez a `registrar_movimientos` con `[salida_1, entrada_1, salida_2, ...]` (los
    bloqueos se toman una vez en el orden global y cada salida se aplica antes que su
    entrada) y, con los movimientos ya aplicados, inserta la cabecera `CONFIRMADA` y sus
    líneas. Todo o nada en la transacción de quien llama (INV-01).

    Una ubicación o un producto ajeno o inexistente es 404 (INV-21); inactivos, rechazo
    (`UBICACION_INACTIVA`, `PRODUCTO_INACTIVO`). Sin `permitir_negativo`, una salida que
    no alcanza es `STOCK_INSUFICIENTE`; con él se aplica y el resultado informa cada saldo
    que quedó bajo cero. El stock total y el promedio no cambian (INV-15, CST-12)."""
    validada = validar_transferencia(
        ubicacion_origen_id=ubicacion_origen_id,
        ubicacion_destino_id=ubicacion_destino_id,
        lineas=[LineaDeOperacion(linea.producto_id, linea.cantidad_base) for linea in lineas],
        observacion=observacion,
    )
    transferencia_id = nuevo_id()
    try:
        resultados = registrar_movimientos(
            organizacion_id,
            sesion,
            reloj,
            lineas=expandir_transferencia(validada, transferencia_id=transferencia_id),
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            occurred_at=occurred_at,
            permitir_negativo=permitir_negativo,
        )
    except DomainError as error:
        _indicar_la_linea(error, validada.lineas)
        raise

    transferencia = repository.insertar_transferencia(
        organizacion_id,
        sesion,
        transferencia_id=transferencia_id,
        ubicacion_origen_id=validada.ubicacion_origen_id,
        ubicacion_destino_id=validada.ubicacion_destino_id,
        observacion=validada.observacion,
        operation_id=operation_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=occurred_at,
        registered_at=reloj.now(),
    )
    lineas_insertadas = [
        repository.insertar_transferencia_linea(
            organizacion_id,
            sesion,
            linea_id=nuevo_id(),
            transferencia_id=transferencia_id,
            orden=orden,
            producto_id=linea.producto_id,
            cantidad_base=linea.cantidad_base,
        )
        for orden, linea in enumerate(validada.lineas, start=1)
    ]

    # `resultados` viene como [salida, entrada] por cada línea, en el orden de la expansión.
    saldos = [
        SaldoDeLinea(
            producto_id=linea.producto_id,
            cantidad_base=linea.cantidad_base,
            saldo_origen=resultados[2 * posicion].saldo,
            saldo_destino=resultados[2 * posicion + 1].saldo,
        )
        for posicion, linea in enumerate(validada.lineas)
    ]
    negativos = [
        SaldoNegativo(
            producto_id=resultado.movimiento.producto_id,
            ubicacion_id=resultado.movimiento.ubicacion_id,
            saldo=resultado.saldo,
        )
        for resultado in resultados
        if resultado.saldo_negativo
    ]
    return ResultadoDeTransferencia(
        transferencia=transferencia, lineas=lineas_insertadas, saldos=saldos, negativos=negativos
    )


# --- ajustes (STK-08, change 14, D1, D2, D3, D6, D9) ------------------------------------


@dataclass(frozen=True)
class LineaDeAjuste:
    """Una línea del comando `STOCK_AJUSTAR`: producto y `cantidad_base` con signo."""

    producto_id: UUID
    cantidad_base: int


@dataclass(frozen=True)
class SaldoDeLineaDeAjuste:
    """El saldo que quedó en la ubicación para la línea de un producto."""

    producto_id: UUID
    cantidad_base: int
    saldo: int


@dataclass(frozen=True)
class ResultadoDeAjuste:
    ajuste: AjusteStock
    lineas: list[AjusteStockLinea]
    saldos: list[SaldoDeLineaDeAjuste]
    negativos: list[SaldoNegativo] = field(default_factory=list)
    """Solo en la anulación de un ajuste con permiso (D5 punto 6): un ajuste nuevo nunca
    deja un saldo negativo (D1 = B)."""


def ajustar(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    ubicacion_id: UUID,
    motivo_id: UUID,
    lineas: Sequence[LineaDeAjuste],
    observacion: str | None,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
) -> ResultadoDeAjuste:
    """`STOCK_AJUSTAR` (STK-08, `design.md` D1, D3, D6, D9): valida el contenido y el motivo
    (`configuracion`: activo y del ámbito `AJUSTE_STOCK`, si no `MOTIVO_INVALIDO`; ajeno o
    inexistente, 404), llama UNA sola vez a `registrar_movimientos` con un `AJUSTE` por línea
    y, con los movimientos ya aplicados, inserta la cabecera `CONFIRMADA` y sus líneas con el
    costo con que se valorizó cada movimiento. Todo o nada en la transacción de quien llama
    (INV-01).

    Un ajuste NUNCA deja un saldo negativo, tampoco con `PERMITIR_STOCK_NEGATIVO` (D1 = B):
    por eso no recibe `permitir_negativo`. Un ajuste positivo de un producto sin promedio es
    `PRODUCTO_SIN_COSTO` (D3). No cambia el promedio ni deja historia de costo (CST-12,
    CST-13)."""
    validado = validar_ajuste(
        ubicacion_id=ubicacion_id,
        motivo_id=motivo_id,
        lineas=[LineaDeOperacion(linea.producto_id, linea.cantidad_base) for linea in lineas],
        observacion=observacion,
    )
    motivo = configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
    if motivo is None:
        raise RecursoNoEncontradoError("El motivo no existe en esta organización.")
    validar_motivo_de_ajuste(activo=motivo.activo, ambito=motivo.ambito)

    ajuste_id = nuevo_id()
    try:
        resultados = registrar_movimientos(
            organizacion_id,
            sesion,
            reloj,
            lineas=expandir_ajuste(validado, ajuste_id=ajuste_id),
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            occurred_at=occurred_at,
        )
    except DomainError as error:
        _indicar_la_linea(error, validado.lineas)
        raise

    ajuste = repository.insertar_ajuste(
        organizacion_id,
        sesion,
        ajuste_id=ajuste_id,
        ubicacion_id=validado.ubicacion_id,
        motivo_id=validado.motivo_id,
        observacion=validado.observacion,
        operation_id=operation_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=occurred_at,
        registered_at=reloj.now(),
    )
    # `resultados` viene en el orden de las líneas validadas (un movimiento por línea).
    pares = list(zip(validado.lineas, resultados, strict=True))
    lineas_insertadas = [
        repository.insertar_ajuste_linea(
            organizacion_id,
            sesion,
            linea_id=nuevo_id(),
            ajuste_id=ajuste_id,
            orden=orden,
            producto_id=linea.producto_id,
            cantidad_base=linea.cantidad_base,
            costo_unitario=resultado.movimiento.costo_unitario,
        )
        for orden, (linea, resultado) in enumerate(pares, start=1)
    ]
    saldos = [
        SaldoDeLineaDeAjuste(
            producto_id=linea.producto_id,
            cantidad_base=linea.cantidad_base,
            saldo=resultado.saldo,
        )
        for linea, resultado in pares
    ]
    return ResultadoDeAjuste(ajuste=ajuste, lineas=lineas_insertadas, saldos=saldos)


def lineas_de_ajuste(
    organizacion_id: UUID, sesion: Session, ajuste_id: UUID
) -> list[AjusteStockLinea]:
    """Lectura pública: las líneas de un ajuste de la organización con el costo con que se
    valorizó cada una (quien las expone decide si el usuario tiene `VER_COSTOS`)."""
    return repository.lineas_de_ajuste(organizacion_id, sesion, ajuste_id=ajuste_id)


# --- anulaciones (TR-06, change 14, D5, D5.1, D5.2, D5.4) ----------------------------------


def _motivo_de_anulacion(
    organizacion_id: UUID, sesion: Session, motivo_id: UUID, *, ambito: str
) -> None:
    """TR-09: el motivo es de la organización (ajeno o inexistente, 404) y está activo en el
    ámbito de la operación (si no, `MOTIVO_INVALIDO`)."""
    motivo = configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
    if motivo is None:
        raise RecursoNoEncontradoError("El motivo no existe en esta organización.")
    validar_motivo_de_anulacion(activo=motivo.activo, ambito=motivo.ambito, ambito_esperado=ambito)


def _negativos(resultados: Sequence[ResultadoDeMovimiento]) -> list[SaldoNegativo]:
    return [
        SaldoNegativo(
            producto_id=resultado.movimiento.producto_id,
            ubicacion_id=resultado.movimiento.ubicacion_id,
            saldo=resultado.saldo,
        )
        for resultado in resultados
        if resultado.saldo_negativo
    ]


def anular_transferencia(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    transferencia_id: UUID,
    motivo_id: UUID,
    permisos: Collection[str],
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
) -> ResultadoDeTransferencia:
    """`STOCK_TRANSFERENCIA_ANULAR` (TR-06, `design.md` D5, D5.1, D5.2, D5.4): anula por
    completo una transferencia `CONFIRMADA`, una sola vez.

    Toma la cabecera `FOR UPDATE` ANTES de todo lo demás (`02` §7.3), comprueba quién puede
    anularla (la propia con `TRANSFERIR_STOCK`; la ajena además con `ANULAR_TRANSFERENCIA`,
    si no 403), revalida el estado (`TRANSFERENCIA_YA_ANULADA`) y el motivo, lee del libro los
    movimientos originales y llama UNA vez a `registrar_movimientos` con los inversos: la
    salida del destino y la entrada al origen de cada línea, al costo original. Sin
    `PERMITIR_STOCK_NEGATIVO` una salida que no alcanza es `STOCK_INSUFICIENTE`; con él se
    aplica y el resultado informa cada saldo bajo cero. El stock total y el promedio no
    cambian (INV-15, CST-12). Un producto o una ubicación inactivos la rechazan (D4).
    Todo o nada en la transacción de quien llama (INV-01)."""
    transferencia = repository.obtener_transferencia_para_actualizar(
        organizacion_id, sesion, transferencia_id=transferencia_id
    )
    if transferencia is None:
        raise RecursoNoEncontradoError("La transferencia no existe en esta organización.")
    if not puede_anular_transferencia(transferencia.usuario_id, usuario_id, permisos):
        raise PermisoRequeridoError(
            "Solo se anulan las transferencias propias; para anular la de otro usuario falta "
            "el permiso ANULAR_TRANSFERENCIA."
        )
    validar_anulable(transferencia.estado, operacion="TRANSFERENCIA")
    _motivo_de_anulacion(organizacion_id, sesion, motivo_id, ambito=AMBITO_ANULACION_TRANSFERENCIA)

    lineas = [
        LineaDeOperacion(linea.producto_id, linea.cantidad_base)
        for linea in repository.lineas_de_transferencia(
            organizacion_id, sesion, transferencia_id=transferencia_id
        )
    ]
    originales = [
        MovimientoOriginal(
            producto_id=movimiento.producto_id,
            ubicacion_id=movimiento.ubicacion_id,
            cantidad_base=movimiento.cantidad_base,
            tipo=movimiento.tipo,
            costo_unitario=movimiento.costo_unitario,
        )
        for movimiento in repository.movimientos_de_origen(
            organizacion_id, sesion, origen_tipo=ORIGEN_TRANSFERENCIA, origen_id=transferencia_id
        )
    ]
    try:
        resultados = registrar_movimientos(
            organizacion_id,
            sesion,
            reloj,
            lineas=expandir_anulacion_transferencia(
                transferencia_id=transferencia_id, lineas=lineas, originales=originales
            ),
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            occurred_at=occurred_at,
            permitir_negativo=PERMISO_PERMITIR_STOCK_NEGATIVO in permisos,
        )
    except DomainError as error:
        _indicar_la_linea(error, lineas)
        raise

    repository.anular_transferencia(
        organizacion_id,
        sesion,
        transferencia=transferencia,
        motivo_id=motivo_id,
        usuario_id=usuario_id,
        momento=reloj.now(),
    )
    # `resultados` viene como [salida del destino, entrada al origen] por cada línea.
    saldos = [
        SaldoDeLinea(
            producto_id=linea.producto_id,
            cantidad_base=linea.cantidad_base,
            saldo_origen=resultados[2 * posicion + 1].saldo,
            saldo_destino=resultados[2 * posicion].saldo,
        )
        for posicion, linea in enumerate(lineas)
    ]
    return ResultadoDeTransferencia(
        transferencia=transferencia,
        lineas=repository.lineas_de_transferencia(
            organizacion_id, sesion, transferencia_id=transferencia_id
        ),
        saldos=saldos,
        negativos=_negativos(resultados),
    )


def anular_ajuste(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    ajuste_id: UUID,
    motivo_id: UUID,
    permitir_negativo: bool,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
) -> ResultadoDeAjuste:
    """`STOCK_AJUSTE_ANULAR` (TR-06, `design.md` D5, D5.1, D5.2): anula por completo un ajuste
    `CONFIRMADA` (propio o ajeno), una sola vez.

    Toma la cabecera `FOR UPDATE` primero, revalida el estado (`AJUSTE_YA_ANULADO`) y el
    motivo (ámbito `ANULACION_AJUSTE`) y llama UNA vez a `registrar_movimientos` con un
    `AJUSTE` de signo contrario por línea, al costo de la línea original (nulo incluido) y con
    el motivo de la ANULACIÓN. `PRODUCTO_SIN_COSTO` no se aplica a un inverso. El inverso de
    una línea positiva puede dejar el saldo negativo solo con `PERMITIR_STOCK_NEGATIVO`; si no,
    `STOCK_INSUFICIENTE` (D5 punto 6: es una anulación, no un ajuste). El stock total se mueve
    en sentido contrario al ajuste; el promedio no cambia (CST-12, CST-13)."""
    ajuste = repository.obtener_ajuste_para_actualizar(organizacion_id, sesion, ajuste_id=ajuste_id)
    if ajuste is None:
        raise RecursoNoEncontradoError("El ajuste no existe en esta organización.")
    validar_anulable(ajuste.estado, operacion="AJUSTE")
    _motivo_de_anulacion(organizacion_id, sesion, motivo_id, ambito=AMBITO_ANULACION_AJUSTE)

    originales = repository.lineas_de_ajuste(organizacion_id, sesion, ajuste_id=ajuste_id)
    lineas = [LineaDeOperacion(linea.producto_id, linea.cantidad_base) for linea in originales]
    try:
        resultados = registrar_movimientos(
            organizacion_id,
            sesion,
            reloj,
            lineas=expandir_anulacion_ajuste(
                ajuste_id=ajuste_id,
                ubicacion_id=ajuste.ubicacion_id,
                motivo_anulacion_id=motivo_id,
                lineas=[
                    LineaDeAjusteOriginal(
                        linea.producto_id, linea.cantidad_base, linea.costo_unitario
                    )
                    for linea in originales
                ],
            ),
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            occurred_at=occurred_at,
            permitir_negativo=permitir_negativo,
        )
    except DomainError as error:
        _indicar_la_linea(error, lineas)
        raise

    repository.anular_ajuste(
        organizacion_id,
        sesion,
        ajuste=ajuste,
        motivo_id=motivo_id,
        usuario_id=usuario_id,
        momento=reloj.now(),
    )
    return ResultadoDeAjuste(
        ajuste=ajuste,
        lineas=originales,
        saldos=[
            SaldoDeLineaDeAjuste(
                producto_id=linea.producto_id,
                cantidad_base=linea.cantidad_base,
                saldo=resultado.saldo,
            )
            for linea, resultado in zip(lineas, resultados, strict=True)
        ],
        negativos=_negativos(resultados),
    )


# --- producto con stock (CAT-05, change 14, D4, D4.1, D4.2) -------------------------


def producto_tiene_stock(organizacion_id: UUID, producto_id: UUID, sesion: Session) -> bool:
    """`True` si el producto tiene algún saldo distinto de cero en la organización. Es el
    verificador que este módulo registra en `catalogo` (más abajo): `catalogo` no desactiva un
    producto con stock (`PRODUCTO_CON_STOCK`). Lee los saldos `FOR SHARE`; el producto ya lo
    tiene `FOR UPDATE` quien lo desactiva. No mira saldos de otra organización (INV-21)."""
    return repository.hay_saldos_del_producto_distintos_de_cero(
        organizacion_id, sesion, producto_id=producto_id
    )


catalogo_service.registrar_verificador_de_stock(producto_tiene_stock)


# --- lecturas (STK-01, STK-04, D11) -------------------------------------------------


def obtener_saldo(
    organizacion_id: UUID, sesion: Session, *, producto_id: UUID, ubicacion_id: UUID
) -> int:
    """Saldo materializado sin bloquear; `0` si el par nunca tuvo un movimiento
    (STK-04). No valida que existan: quien lo expone ya respondió 404."""
    saldo = repository.obtener_saldo(
        organizacion_id, sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
    )
    return 0 if saldo is None else saldo


def stock_por_ubicacion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ubicacion_id: UUID,
    cursor: str | None,
    limite: int | None,
) -> StockDeUbicacion:
    """Stock de una ubicación por producto, en unidad base entera (STK-01), sin
    los saldos en cero, ordenado por `producto_id` y paginado por cursor (D11). Cada
    línea trae las unidades de la presentación de referencia (CAT-08) y el promedio
    vigente. Una ubicación ajena o inexistente es `RecursoNoEncontradoError`."""
    if repository.obtener_ubicacion(organizacion_id, sesion, ubicacion_id=ubicacion_id) is None:
        raise RecursoNoEncontradoError("La ubicación no existe en esta organización.")
    despues_de = None if cursor is None else decodificar_cursor_de_producto(cursor)
    limite_pagina = limite_efectivo(limite)

    filas = repository.saldos_de_ubicacion(
        organizacion_id,
        sesion,
        ubicacion_id=ubicacion_id,
        despues_de_producto_id=despues_de,
        limite=limite_pagina + 1,
    )
    pagina = filas[:limite_pagina]
    promedios = costeo_service.obtener_promedios(
        organizacion_id, sesion, [producto_id for producto_id, _ in pagina]
    )
    lineas = []
    for producto_id, cantidad in pagina:
        producto = catalogo_service.obtener_producto(organizacion_id, producto_id, sesion)
        if producto is None:  # la FK compuesta del saldo lo impide (INV-02)
            raise RecursoNoEncontradoError("El producto no existe en esta organización.")
        referencia = catalogo_service.obtener_referencia_de_producto(
            organizacion_id, producto_id, sesion
        )
        lineas.append(
            LineaDeStock(
                producto_id=producto_id,
                producto_codigo=producto.codigo,
                producto_nombre=producto.nombre,
                cantidad_base=cantidad,
                unidades_referencia=None if referencia is None else referencia.unidades_base,
                nombre_referencia=None if referencia is None else referencia.nombre,
                costo_promedio=promedios.get(producto_id),
            )
        )
    cursor_siguiente = (
        codificar_cursor_de_producto(lineas[-1].producto_id)
        if len(filas) > limite_pagina and lineas
        else None
    )
    return StockDeUbicacion(lineas=lineas, cursor_siguiente=cursor_siguiente)


def _con_motivo_y_estado_de_origen(
    organizacion_id: UUID, sesion: Session, movimientos: list[LineaDeKardex]
) -> list[LineaDeKardex]:
    """Completa cada movimiento del kardex (change 14, D5.1, D7): el nombre del motivo de un
    `AJUSTE` (el del ajuste o el de su anulación) y el estado de la operación de origen de un
    movimiento con origen `TRANSFERENCIA` o `AJUSTE_STOCK`. Los demás quedan con ambos nulos."""
    estados = repository.estados_de_operaciones(
        organizacion_id,
        sesion,
        transferencias={m.origen_id for m in movimientos if m.origen_tipo == ORIGEN_TRANSFERENCIA},
        ajustes={m.origen_id for m in movimientos if m.origen_tipo == ORIGEN_AJUSTE},
    )
    nombres: dict[UUID, str] = {}
    for motivo_id in {m.motivo_id for m in movimientos if m.tipo == AJUSTE and m.motivo_id}:
        motivo = configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
        if motivo is not None:
            nombres[motivo_id] = motivo.nombre
    return [
        replace(
            movimiento,
            motivo_nombre=(
                nombres.get(movimiento.motivo_id)
                if movimiento.tipo == AJUSTE and movimiento.motivo_id is not None
                else None
            ),
            estado_origen=(
                estados.get(movimiento.origen_id)
                if movimiento.origen_tipo in (ORIGEN_TRANSFERENCIA, ORIGEN_AJUSTE)
                else None
            ),
        )
        for movimiento in movimientos
    ]


def kardex(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    ubicacion_id: UUID,
    desde: date | None,
    hasta: date | None,
    cursor: str | None,
    limite: int | None,
) -> Kardex:
    """Kardex de un producto en una ubicación (D11): movimientos en orden
    `(occurred_at, id)` con el saldo acumulado calculado en SQL sobre toda la
    historia, `saldo_anterior` al período, saldo actual y cursor de la página
    siguiente. `desde` y `hasta` son fechas de negocio en la zona horaria de la
    organización (TR-04); `hasta` se incluye entero. Un producto o una ubicación
    ajenos o inexistentes son `RecursoNoEncontradoError`."""
    if repository.obtener_ubicacion(organizacion_id, sesion, ubicacion_id=ubicacion_id) is None:
        raise RecursoNoEncontradoError("La ubicación no existe en esta organización.")
    producto = catalogo_service.obtener_producto(organizacion_id, producto_id, sesion)
    if producto is None:
        raise RecursoNoEncontradoError("El producto no existe en esta organización.")
    referencia = catalogo_service.obtener_referencia_de_producto(
        organizacion_id, producto_id, sesion
    )
    organizacion = identidad_service.obtener_organizacion(organizacion_id, sesion)
    if organizacion is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    inicio, fin = rango_de_instantes(desde, hasta, organizacion.zona_horaria)

    movimientos, cursor_siguiente = repository.kardex(
        organizacion_id,
        sesion,
        producto_id=producto_id,
        ubicacion_id=ubicacion_id,
        desde=inicio,
        hasta=fin,
        cursor=cursor,
        limite=limite,
    )
    movimientos = _con_motivo_y_estado_de_origen(organizacion_id, sesion, movimientos)
    anterior = (
        0
        if inicio is None
        else repository.saldo_anterior(
            organizacion_id,
            sesion,
            producto_id=producto_id,
            ubicacion_id=ubicacion_id,
            antes_de=inicio,
        )
    )
    return Kardex(
        saldo_anterior=anterior,
        saldo_actual=obtener_saldo(
            organizacion_id, sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
        ),
        zona_horaria=organizacion.zona_horaria,
        producto_codigo=producto.codigo,
        producto_nombre=producto.nombre,
        unidades_referencia=None if referencia is None else referencia.unidades_base,
        nombre_referencia=None if referencia is None else referencia.nombre,
        movimientos=movimientos,
        cursor_siguiente=cursor_siguiente,
    )


def verificar_consistencia(organizacion_id: UUID, sesion: Session) -> list[DiferenciaDeStock]:
    """Diferencias de INV-12 (`02` §7.6): cada `stock_saldo` contra la suma SQL de su
    libro y cada `stock_total` contra la suma SQL de los saldos del producto. Solo
    informa: no corrige nada (ADR-015). La tarea diaria que la ejecuta y notifica es
    del change 28."""
    diferencias = repository.diferencias_de_saldos_contra_el_libro(organizacion_id, sesion)
    diferencias.extend(
        diferencias_de_stock_total(
            costeo_service.obtener_stock_totales(organizacion_id, sesion),
            repository.sumas_de_saldos_por_producto(organizacion_id, sesion),
        )
    )
    return diferencias
