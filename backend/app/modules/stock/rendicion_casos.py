"""Casos de uso de la rendición de una jornada (change 24; `design.md` D2, D3, D5).

Orquestan el orden de las operaciones: leen con `rendicion_repository` y `jornadas_repository` y
deciden con `domain/rendicion.py` y `domain/jornadas.py`. NUNCA importan `service.py` (que delega
en este archivo): la puerta del libro se recibe como parámetro (`PuertaDelLibro`) para no cerrar
un ciclo. Sin `commit`: la transacción la gestiona el bus (`CLAUDE.md` §4).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.modules.catalogo import service as catalogo_service
from app.modules.stock import jornadas_repository, rendicion_repository
from app.modules.stock.domain import jornadas as dominio_jornadas
from app.modules.stock.domain import rendicion as dominio
from app.modules.stock.domain.errores import RecursoNoEncontradoError
from app.modules.stock.domain.movimientos import (
    DIFERENCIA_RENDICION,
    ORIGEN_RENDICION,
    LineaDeMovimiento,
)
from app.modules.stock.domain.rendicion import LineaContada
from app.modules.stock.models import Jornada, Rendicion, RendicionLinea, StockMovimiento
from app.modules.stock.rendicion_repository import DesgloseDeProducto, LineaParaInsertar

PuertaDelLibro = Callable[[Sequence[LineaDeMovimiento], UUID], Sequence[StockMovimiento]]
"""La única puerta del libro (D3): recibe las líneas y la jornada que se rinde
(`rendicion_de_jornada`) y devuelve los movimientos escritos, en el orden de las líneas."""

_SIN_DESGLOSE = DesgloseDeProducto(
    al_abrir=0, ingresos=0, ventas=0, anulaciones=0, otros=0, con_movimiento_en_la_ventana=False
)


@dataclass(frozen=True)
class ResultadoDeRendicion:
    jornada: Jornada
    rendicion: Rendicion
    lineas: list[RendicionLinea]


def rendir_jornada(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    puerta: PuertaDelLibro,
    rechazos_pendientes: Callable[[], int],
    jornada_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
    lineas: Sequence[LineaContada[UUID]],
    observacion: str | None,
) -> ResultadoDeRendicion:
    """`JORNADA_RENDIR` v2 (RUT-05, RUT-06, `design.md` D2, D3, D5).

    Orden de bloqueo (D3, sin ciclos): la ubicación de la jornada `FOR UPDATE`, después la jornada
    `FOR NO KEY UPDATE` (ver `jornadas_repository.bloquear_jornada`); con ambas se revalida
    estado y entrega, se leen los esperados por SQL (estables:
    ningún movimiento sobre esa ubicación puede estar en curso ni empezar) y recién entonces se
    llama UNA vez a la puerta con las diferencias. No toma `saldo_cuenta`.

    Change 25 (D9 = B): `rechazos_pendientes` (el puerto de `sync`, recibido como parámetro para no
    importar `sync`) se consulta con la jornada tomada y antes del conteo; con rechazos sin
    resolver se rechaza con `RECHAZOS_PENDIENTES` sin escribir nada.

    Escribe la rendición, una línea por producto del conteo (con el desglose del esperado
    congelado y el costo de la diferencia) y deja la jornada `EN_RENDICION`. Un producto
    agregado fuera del conjunto a contar tiene esperado cero (sobrante)."""
    ubicacion_id = jornadas_repository.leer_ubicacion_de_jornada(
        organizacion_id, sesion, jornada_id=jornada_id
    )
    if ubicacion_id is None:
        raise RecursoNoEncontradoError(f"La jornada {jornada_id} no existe en esta organización.")
    ubicacion = jornadas_repository.bloquear_ubicacion(
        organizacion_id, sesion, ubicacion_id=ubicacion_id
    )
    jornada = jornadas_repository.bloquear_jornada(
        organizacion_id, sesion, jornada_id=jornada_id, despues_de_la_ubicacion=True
    )
    if ubicacion is None or jornada is None:
        raise RecursoNoEncontradoError(f"La jornada {jornada_id} no existe en esta organización.")

    nuevo_estado = dominio_jornadas.validar_para_rendir(
        jornada.estado, entregada=jornada.entregada_en is not None
    )
    # Change 25, D9 = B: con la jornada ya tomada y antes del conteo, en una consulta aparte, no
    # se rinde mientras queden rechazos sin resolver (RUT-05, SYN-06). Solo lee: no toma filas.
    dominio.validar_sin_rechazos_pendientes(rechazos_pendientes())
    observacion_normalizada = dominio.normalizar_observacion(observacion)

    desgloses = _desglose_de(organizacion_id, sesion, jornada)
    lineas_rendidas = _validar_conteo(desgloses, lineas)
    _exigir_productos_existentes(organizacion_id, sesion, lineas_rendidas, desgloses)

    ahora = reloj.now()
    rendicion = rendicion_repository.insertar_rendicion(
        organizacion_id,
        sesion,
        rendicion_id=nuevo_id(),
        jornada_id=jornada.id,
        observacion=observacion_normalizada,
        operation_id=operation_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=occurred_at,
        registered_at=ahora,
    )

    con_diferencia = [x for x in lineas_rendidas if x.diferencia != 0]
    costos = _escribir_diferencias(
        puerta, con_diferencia, ubicacion_id=ubicacion_id, rendicion=rendicion, jornada=jornada
    )

    filas = rendicion_repository.insertar_lineas(
        organizacion_id,
        sesion,
        rendicion_id=rendicion.id,
        lineas=[
            LineaParaInsertar(
                producto_id=x.producto,
                desglose=desgloses.get(x.producto, _SIN_DESGLOSE),
                contado=x.contado,
                diferencia=x.diferencia,
                costo_unitario=costos.get(x.producto),
            )
            for x in lineas_rendidas
        ],
    )

    jornada.estado = nuevo_estado
    jornada.rendida_en = occurred_at
    jornada.rendida_por_id = usuario_id
    sesion.flush()
    return ResultadoDeRendicion(jornada=jornada, rendicion=rendicion, lineas=filas)


def _desglose_de(
    organizacion_id: UUID, sesion: Session, jornada: Jornada
) -> dict[UUID, DesgloseDeProducto]:
    """El desglose por producto de la ubicación de la jornada con la ventana desde su apertura."""
    return rendicion_repository.desglose_por_producto(
        organizacion_id,
        sesion,
        ubicacion_id=jornada.ubicacion_id,
        abierta_en=jornada.abierta_en,
    )


def _validar_conteo(
    desgloses: dict[UUID, DesgloseDeProducto], lineas: Sequence[LineaContada[UUID]]
) -> list[dominio.LineaRendida[UUID]]:
    """Valida el conteo con el dominio puro. Los productos viajan como texto porque van en la
    extensión de los errores (`CONTEO_INCOMPLETO`, `ESPERADO_DIFIERE`), que es JSON."""
    esperados = {str(p): d.esperado for p, d in desgloses.items()}
    conjunto = dominio.conjunto_a_contar(
        esperados,
        con_movimiento=[str(p) for p, d in desgloses.items() if d.con_movimiento_en_la_ventana],
    )
    rendidas = dominio.validar_conteo(
        conjunto=conjunto,
        esperados=esperados,
        lineas=[
            LineaContada(producto=str(x.producto), contada=x.contada, esperada=x.esperada)
            for x in lineas
        ],
    )
    return [
        dominio.LineaRendida(
            producto=UUID(x.producto),
            esperado=x.esperado,
            contado=x.contado,
            diferencia=x.diferencia,
        )
        for x in rendidas
    ]


def _exigir_productos_existentes(
    organizacion_id: UUID,
    sesion: Session,
    lineas: Sequence[dominio.LineaRendida[UUID]],
    desgloses: dict[UUID, DesgloseDeProducto],
) -> None:
    """Un producto agregado fuera del conjunto a contar tiene que existir en la organización
    (INV-21); la actividad la exige la puerta si tiene diferencia (CAT-05)."""
    for linea in lineas:
        if linea.producto in desgloses:
            continue
        if catalogo_service.obtener_producto(organizacion_id, linea.producto, sesion) is None:
            raise RecursoNoEncontradoError(
                "El producto no existe en esta organización.",
                extension={"producto_id": str(linea.producto)},
            )


def _escribir_diferencias(
    puerta: PuertaDelLibro,
    con_diferencia: Sequence[dominio.LineaRendida[UUID]],
    *,
    ubicacion_id: UUID,
    rendicion: Rendicion,
    jornada: Jornada,
) -> dict[UUID, Decimal | None]:
    """Un `DIFERENCIA_RENDICION` por producto con diferencia, en UNA llamada a la puerta (D3,
    D5). Devuelve el costo con que se valorizó cada una."""
    if not con_diferencia:
        return {}
    movimientos = puerta(
        [
            LineaDeMovimiento(
                producto_id=x.producto,
                ubicacion_id=ubicacion_id,
                cantidad_base=x.diferencia,
                tipo=DIFERENCIA_RENDICION,
                costo_unitario=None,
                origen_tipo=ORIGEN_RENDICION,
                origen_id=rendicion.id,
            )
            for x in con_diferencia
        ],
        jornada.id,
    )
    return {m.producto_id: m.costo_unitario for m in movimientos}


@dataclass(frozen=True)
class ResultadoDeCierre[T]:
    """La jornada cerrada y, si el cierre devolvió el remanente, lo que devolvió la transferencia
    (el tipo lo decide quien llama: este archivo no importa `service.py`)."""

    jornada: Jornada
    devolucion: T | None


def cerrar_jornada[T](
    organizacion_id: UUID,
    sesion: Session,
    *,
    jornada_id: UUID,
    usuario_id: UUID,
    occurred_at: datetime,
    destino_id: UUID | None,
    devolver: Callable[[UUID], T] | None,
) -> ResultadoDeCierre[T]:
    """`JORNADA_CERRAR` v2 (RUT-08, `design.md` D3, D6): el mismo orden de bloqueo que la
    rendición (la ubicación de la jornada `FOR UPDATE`, después la jornada `FOR NO KEY UPDATE`),
    con o sin devolución, así ningún movimiento de esa ubicación está en curso ni empieza hasta el
    cierre. Con la jornada `EN_RENDICION` revalidada, el destino se valida (distinto, activo y sin
    toma) y recién entonces `devolver(ubicacion_de_la_jornada)` llama UNA vez a la transferencia
    común; después la jornada queda `CERRADA`. No toma `saldo_cuenta`. Si algo falla, nada queda
    (la transacción es de quien llama)."""
    ubicacion_id = jornadas_repository.leer_ubicacion_de_jornada(
        organizacion_id, sesion, jornada_id=jornada_id
    )
    if ubicacion_id is None:
        raise RecursoNoEncontradoError(f"La jornada {jornada_id} no existe en esta organización.")
    jornadas_repository.bloquear_ubicacion(organizacion_id, sesion, ubicacion_id=ubicacion_id)
    jornada = jornadas_repository.bloquear_jornada(
        organizacion_id, sesion, jornada_id=jornada_id, despues_de_la_ubicacion=True
    )
    if jornada is None:
        raise RecursoNoEncontradoError(f"La jornada {jornada_id} no existe en esta organización.")

    nuevo_estado = dominio_jornadas.cerrar(jornada.estado)
    devolucion: T | None = None
    if destino_id is not None and devolver is not None:
        destino = rendicion_repository.leer_ubicacion(
            organizacion_id, sesion, ubicacion_id=destino_id
        )
        if destino is None:
            raise RecursoNoEncontradoError(
                f"La ubicación {destino_id} no existe en esta organización."
            )
        dominio_jornadas.validar_destino_de_devolucion(
            origen_id=ubicacion_id,
            destino_id=destino_id,
            activa=destino.activo,
            requiere_toma=destino.requiere_toma,
        )
        devolucion = devolver(ubicacion_id)

    jornada.estado = nuevo_estado
    jornada.cerrada_en = occurred_at
    jornada.cerrada_por_id = usuario_id
    sesion.flush()
    return ResultadoDeCierre(jornada=jornada, devolucion=devolucion)
