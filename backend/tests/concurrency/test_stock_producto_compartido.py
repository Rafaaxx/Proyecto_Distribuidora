"""Change 14, tarea 4.3: un movimiento toma su producto `FOR SHARE` (`design.md` D4.2,
spec delta `stock/libro-de-stock`, requisito "Un movimiento toma su producto en modo
compartido"). Dos sesiones reales, commits reales (`CLAUDE.md` §4, `02` §15).

La desactivación del producto la hace el change 14 (grupo 8, lote 2) con `FOR UPDATE`; acá
una transacción que simula ese bloqueo (`SELECT ... FOR UPDATE` y `UPDATE activo = false`)
muestra que el movimiento ESPERA y, al confirmarse la desactivación, responde
`PRODUCTO_INACTIVO` en vez de dejar stock en un producto inactivo.

Reglas citadas: CAT-05, ADR-038 punto 5.
"""

from __future__ import annotations

import threading

from sqlalchemy import text

from app.modules.stock.domain.errores import ProductoInactivoError
from tests.concurrency.test_stock_concurrencia import (  # noqa: F401
    ESPERA_MAXIMA,
    _Escenario,
    _limpiar_datos_confirmados,
    _sesion_independiente,
)


def test_un_movimiento_espera_la_desactivacion_del_producto_y_responde_producto_inactivo(
    database_url: str, _engine_de_sesion
) -> None:
    escenario = _Escenario(database_url)
    desactivacion_tomo_el_producto = threading.Event()
    puede_confirmar = threading.Event()
    movimiento_termino = threading.Event()
    resultado: dict[str, object] = {}

    def _desactivar() -> None:
        sesion = _sesion_independiente(database_url)
        try:
            sesion.execute(
                text("SELECT id FROM producto WHERE organizacion_id = :o AND id = :p FOR UPDATE"),
                {"o": escenario.org, "p": escenario.producto_a},
            )
            sesion.execute(
                text("UPDATE producto SET activo = false WHERE organizacion_id = :o AND id = :p"),
                {"o": escenario.org, "p": escenario.producto_a},
            )
            desactivacion_tomo_el_producto.set()
            assert puede_confirmar.wait(timeout=ESPERA_MAXIMA)
            sesion.commit()
        finally:
            sesion.close()

    def _mover() -> None:
        sesion = _sesion_independiente(database_url)
        try:
            assert desactivacion_tomo_el_producto.wait(timeout=10)
            try:
                escenario.ingresar(sesion, (escenario.producto_a, 6, "1000"))
                sesion.commit()
                resultado["movimiento"] = "OK"
            except ProductoInactivoError as error:
                sesion.rollback()
                resultado["movimiento"] = type(error).__name__
        finally:
            movimiento_termino.set()
            sesion.close()

    hilos = [threading.Thread(target=_desactivar), threading.Thread(target=_mover)]
    for hilo in hilos:
        hilo.start()
    assert desactivacion_tomo_el_producto.wait(timeout=10)

    # Mientras la desactivación no confirma, el movimiento no puede terminar: espera.
    esperando = not movimiento_termino.wait(timeout=1.5)
    puede_confirmar.set()
    for hilo in hilos:
        hilo.join(timeout=ESPERA_MAXIMA + 10)

    assert not any(hilo.is_alive() for hilo in hilos)
    assert esperando, "El movimiento no esperó al producto bloqueado FOR UPDATE."
    assert resultado["movimiento"] == ProductoInactivoError.__name__
    assert escenario.saldo(escenario.producto_a) == 0
    assert escenario.cantidad_de_filas("stock_movimiento", escenario.producto_a) == 0
    assert escenario.diferencias() == []


def test_sin_desactivacion_en_curso_el_movimiento_no_espera(
    database_url: str, _engine_de_sesion
) -> None:
    """Dos movimientos del mismo producto no se bloquean por el producto: ambos lo toman
    `FOR SHARE` (compatibles entre sí); se serializan después por `costo_producto`."""
    escenario = _Escenario(database_url)
    primero_tomo = threading.Event()
    puede_confirmar = threading.Event()
    segundo_termino = threading.Event()

    def _primero() -> None:
        sesion = _sesion_independiente(database_url)
        try:
            sesion.execute(
                text("SELECT id FROM producto WHERE organizacion_id = :o AND id = :p FOR SHARE"),
                {"o": escenario.org, "p": escenario.producto_a},
            )
            primero_tomo.set()
            assert puede_confirmar.wait(timeout=ESPERA_MAXIMA)
            sesion.commit()
        finally:
            sesion.close()

    def _segundo() -> None:
        sesion = _sesion_independiente(database_url)
        try:
            assert primero_tomo.wait(timeout=10)
            escenario.ingresar(sesion, (escenario.producto_a, 6, "1000"))
            sesion.commit()
        finally:
            segundo_termino.set()
            sesion.close()

    hilos = [threading.Thread(target=_primero), threading.Thread(target=_segundo)]
    for hilo in hilos:
        hilo.start()

    termino_sin_esperar = segundo_termino.wait(timeout=10)
    puede_confirmar.set()
    for hilo in hilos:
        hilo.join(timeout=ESPERA_MAXIMA + 10)

    assert termino_sin_esperar, "Un FOR SHARE no debería bloquear a otro FOR SHARE."
    assert escenario.saldo(escenario.producto_a) == 6
