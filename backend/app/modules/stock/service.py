"""Interfaz pública de `stock` (`CLAUDE.md` §4: un módulo usa a otro solo a través
de su `service.py`).

La usan, más adelante, importaciones (10), compras (11), ajustes y transferencias
(14), ventas de ruta (15, 18a, 19) y rendiciones (24): registrar movimientos con
las filas bloqueadas en el orden global, registrar stock inicial, administrar
ubicaciones y leer saldos, kardex y la verificación de consistencia.

Sin `commit`: la transacción la gestiona el bus de comandos o quien llama en
pruebas (`CLAUDE.md` §4). Todas las funciones reciben `organizacion_id` como
primer parámetro y lo usan para filtrar.

Toda la validación vive en `domain/`; acá solo se orquesta el orden. Un movimiento
bloquea, en este orden (`02` §7.3, ADR-015, `design.md` D9): las ubicaciones
`FOR SHARE` (D8), las filas de `costo_producto` por `producto_id` ascendente (vía
`costeo`, que es el único que las conoce) y las de `stock_saldo` por
`(producto_id, ubicacion_id)` ascendentes; recién entonces decide e inserta. Quien
necesite `saldo_cuenta` (11, 18a) lo bloquea ANTES de llamar a `stock`. El costo
promedio lo calcula solo `costeo` (CST-14): este módulo no calcula ni un costo. El
producto se valida por FK compuesta (404) y su estado por `catalogo/service.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.modules.catalogo import service as catalogo_service
from app.modules.costeo import service as costeo_service
from app.modules.identidad import service as identidad_service
from app.modules.stock import repository
from app.modules.stock.domain.errores import RecursoNoEncontradoError, StockInsuficienteError
from app.modules.stock.domain.kardex import (
    DiferenciaDeStock,
    Kardex,
    codificar_cursor_de_id,
    codificar_cursor_de_producto,
    decodificar_cursor_de_id,
    decodificar_cursor_de_producto,
    limite_efectivo,
    rango_de_instantes,
)
from app.modules.stock.domain.movimientos import (
    STOCK_INICIAL,
    LineaDeMovimiento,
    LineaDeStockInicial,
    diferencias_de_stock_total,
    validar_lineas_de_movimiento,
    validar_lineas_de_stock_inicial,
    validar_producto_activo,
    validar_stock_inicial_admitido,
    validar_ubicacion_activa,
)
from app.modules.stock.domain.ubicaciones import (
    validar_desactivacion,
    validar_ubicacion,
)
from app.modules.stock.models import StockMovimiento, Ubicacion

__all__ = [
    "DiferenciaDeStock",
    "Kardex",
    "LineaDeMovimiento",
    "LineaDeStock",
    "LineaDeStockInicial",
    "PaginaDeUbicaciones",
    "ResultadoDeMovimiento",
    "StockDeUbicacion",
    "buscar_ubicaciones_por_nombre",
    "crear_ubicacion",
    "kardex",
    "listar_ubicaciones",
    "modificar_ubicacion",
    "obtener_saldo",
    "obtener_ubicacion",
    "registrar_movimientos",
    "registrar_stock_inicial",
    "stock_por_ubicacion",
    "verificar_consistencia",
]


@dataclass(frozen=True)
class ResultadoDeMovimiento:
    """El movimiento insertado y el saldo del producto en la ubicación después de
    aplicarlo."""

    movimiento: StockMovimiento
    saldo: int


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

    1. Ubicaciones `FOR SHARE` (existen, D8: activas) y productos (existen, CAT-05:
       activos), en orden ascendente de id.
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
    for producto_id in productos:
        producto = catalogo_service.obtener_producto(organizacion_id, producto_id, sesion)
        if producto is None:
            raise RecursoNoEncontradoError("El producto no existe en esta organización.")
        validar_producto_activo(activo=producto.activo)

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
        if linea.cantidad_base > 0:
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
            saldo = repository.ingresar_al_saldo(
                organizacion_id,
                sesion,
                producto_id=linea.producto_id,
                ubicacion_id=linea.ubicacion_id,
                cantidad=linea.cantidad_base,
                momento=ahora,
            )
            costo_unitario = costeo_service.validar_costo(linea.costo_unitario)
        else:
            magnitud = -linea.cantidad_base
            nuevo_saldo = repository.egresar_del_saldo(
                organizacion_id,
                sesion,
                producto_id=linea.producto_id,
                ubicacion_id=linea.ubicacion_id,
                cantidad=magnitud,
                momento=ahora,
            )
            if nuevo_saldo is None:
                actual = repository.obtener_saldo(
                    organizacion_id,
                    sesion,
                    producto_id=linea.producto_id,
                    ubicacion_id=linea.ubicacion_id,
                )
                raise StockInsuficienteError(
                    f"El saldo es {actual or 0} y se pretende egresar {magnitud}."
                )
            saldo = nuevo_saldo
            egreso = costeo_service.aplicar_egreso(
                organizacion_id,
                sesion,
                reloj,
                producto_id=linea.producto_id,
                cantidad=magnitud,
            )
            costo_unitario = egreso.costo_valorizacion

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
        resultados.append(ResultadoDeMovimiento(movimiento=movimiento, saldo=saldo))
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
) -> list[ResultadoDeMovimiento]:
    """Registra movimientos de stock con todas las filas bloqueadas en el orden
    global (`02` §7.3), todo en la transacción de quien llama (INV-01, INV-12).

    Reúne los pares, valida (tipo del catálogo, cantidad entera distinta de cero,
    costo según el signo, ubicación y producto existentes y activos), bloquea
    ubicaciones, costos y saldos en orden y recién entonces aplica cada línea. Los
    ingresos que recalculan el promedio son los de compra, stock inicial y anulación
    de venta (CST-11); los egresos, de cualquier tipo, se valorizan al promedio
    vigente y no dejan el saldo negativo (STK-05, `02` §7.4, D4). Un ingreso de otro
    tipo (ajuste, transferencia, rendición) se rechaza: lo definen los changes 14,
    15 y 24. Una referencia ajena o inexistente es 404 (INV-21)."""
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
                costo_promedio=promedios.get(producto_id),
            )
        )
    cursor_siguiente = (
        codificar_cursor_de_producto(lineas[-1].producto_id)
        if len(filas) > limite_pagina and lineas
        else None
    )
    return StockDeUbicacion(lineas=lineas, cursor_siguiente=cursor_siguiente)


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
