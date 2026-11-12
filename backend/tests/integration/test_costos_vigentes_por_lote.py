"""Change 13, tarea 6.2: `proveedores/service.py` entrega el costo informado vigente de varios
productos a una fecha en una consulta, con el mismo resultado que
`obtener_costo_informado_vigente` producto por producto (CST-03, incluido el desempate), su
presentación y su `computa_credito_fiscal` (CST-06), y avisa si los costos vigentes por
presentación de un producto difieren por unidad base (`design.md` D2).

Reglas citadas: CST-03, CST-06, INV-21, `design.md` D2, D3 y D4.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from precios_utiles import MOMENTO, Entorno
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.modules.proveedores import service as proveedores_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

HOY = MOMENTO.date()


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _lote(
    entorno: Entorno, productos: list[UUID], fecha: date = HOY
) -> dict[UUID, proveedores_service.CostoVigente]:
    return proveedores_service.obtener_costos_informados_vigentes(
        entorno.org, productos, fecha, entorno.sesion
    )


def test_coincide_con_la_lectura_por_producto_incluido_el_desempate_de_misma_vigencia(
    entorno: Entorno,
) -> None:
    """CST-03: a igual `vigencia_desde` gana el de `creado_en` más reciente; a igual
    `creado_en`, el de mayor `id`. Un costo con vigencia futura no cuenta."""
    vino = entorno.vino_id
    cerveza = entorno.crear_producto("Cerveza B", unidades_base=12)
    gaseosa = entorno.crear_producto("Gaseosa C")
    entorno.informar_costo(vino, "900", vigencia=HOY - timedelta(days=10))
    entorno.informar_costo(vino, "1000", creado_en=MOMENTO)
    entorno.informar_costo(vino, "1100", creado_en=MOMENTO + timedelta(minutes=1))
    entorno.informar_costo(vino, "5000", vigencia=HOY + timedelta(days=1))
    # Misma vigencia y mismo `creado_en`: desempata el `id` mayor.
    entorno.informar_costo(cerveza, "1815")
    entorno.informar_costo(cerveza, "1816")
    productos = [vino, cerveza, gaseosa]

    por_lote = _lote(entorno, productos)

    assert gaseosa not in por_lote, "un producto sin costo vigente no aparece"
    for producto_id in (vino, cerveza):
        individual = proveedores_service.obtener_costo_informado_vigente(
            entorno.org, producto_id, HOY, entorno.sesion
        )
        assert individual is not None
        assert por_lote[producto_id].costo_informado_id == individual.id
        assert por_lote[producto_id].costo_base == individual.costo_base
    assert por_lote[vino].costo_base == Decimal("1100.000000")


def test_a_otra_fecha_resuelve_el_costo_de_esa_fecha(entorno: Entorno) -> None:
    entorno.informar_costo(entorno.vino_id, "900", vigencia=HOY - timedelta(days=10))
    entorno.informar_costo(entorno.vino_id, "1000", vigencia=HOY)

    antes = _lote(entorno, [entorno.vino_id], fecha=HOY - timedelta(days=5))
    despues = _lote(entorno, [entorno.vino_id], fecha=HOY)

    assert antes[entorno.vino_id].costo_base == Decimal("900.000000")
    assert despues[entorno.vino_id].costo_base == Decimal("1000.000000")
    assert _lote(entorno, [entorno.vino_id], fecha=HOY - timedelta(days=11)) == {}


def test_entrega_la_presentacion_y_la_regla_de_iva_con_que_se_registro(
    entorno: Entorno,
) -> None:
    cerveza = entorno.crear_producto("Cerveza B", unidades_base=12)
    x12 = entorno.presentacion_de_referencia(cerveza)
    entorno.informar_costo(entorno.vino_id, "1000", computa=True)
    entorno.informar_costo(cerveza, "1815", computa=False)

    por_lote = _lote(entorno, [entorno.vino_id, cerveza])

    assert por_lote[entorno.vino_id].presentacion_id == entorno.vino_presentacion_id
    assert por_lote[entorno.vino_id].computa_credito_fiscal is True
    assert por_lote[cerveza].presentacion_id == x12
    assert por_lote[cerveza].computa_credito_fiscal is False


def test_avisa_si_los_costos_vigentes_por_presentacion_difieren_por_unidad_base_d2(
    entorno: Entorno,
) -> None:
    """Caja x6 a 1000 por unidad y, con la misma vigencia y registrada después, Caja x12 a
    950 por unidad: el costo usado es el de Caja x12 y el producto lo avisa."""
    caja_x12 = entorno.crear_presentacion(entorno.vino_id, "Caja x12", 12)
    entorno.informar_costo(entorno.vino_id, "1000")
    entorno.informar_costo(
        entorno.vino_id,
        "950",
        presentacion_id=caja_x12,
        creado_en=MOMENTO + timedelta(minutes=1),
    )

    costo = _lote(entorno, [entorno.vino_id])[entorno.vino_id]

    assert costo.presentacion_id == caja_x12
    assert costo.costo_base == Decimal("950.000000")
    assert costo.costos_distintos_por_presentacion is True


def test_no_avisa_si_las_presentaciones_cuestan_lo_mismo_por_unidad_o_hay_una_sola(
    entorno: Entorno,
) -> None:
    cerveza = entorno.crear_producto("Cerveza B", unidades_base=12)
    caja_x12 = entorno.crear_presentacion(entorno.vino_id, "Caja x12", 12)
    entorno.informar_costo(entorno.vino_id, "1000")
    entorno.informar_costo(
        entorno.vino_id, "1000", presentacion_id=caja_x12, creado_en=MOMENTO + timedelta(minutes=1)
    )
    entorno.informar_costo(cerveza, "1815")

    por_lote = _lote(entorno, [entorno.vino_id, cerveza])

    assert por_lote[entorno.vino_id].costos_distintos_por_presentacion is False
    assert por_lote[cerveza].costos_distintos_por_presentacion is False


def test_el_aviso_usa_el_ultimo_costo_de_cada_presentacion_y_no_los_anteriores(
    entorno: Entorno,
) -> None:
    """Un costo viejo de Caja x12 a otro valor ya no cuenta: solo el último de cada
    presentación a la fecha."""
    caja_x12 = entorno.crear_presentacion(entorno.vino_id, "Caja x12", 12)
    entorno.informar_costo(
        entorno.vino_id, "700", presentacion_id=caja_x12, vigencia=HOY - timedelta(days=30)
    )
    entorno.informar_costo(
        entorno.vino_id, "1000", presentacion_id=caja_x12, vigencia=HOY - timedelta(days=1)
    )
    entorno.informar_costo(entorno.vino_id, "1000")

    costo = _lote(entorno, [entorno.vino_id])[entorno.vino_id]

    assert costo.costos_distintos_por_presentacion is False


def test_solo_devuelve_los_productos_pedidos_de_la_organizacion(db_session: Session) -> None:
    propia = Entorno(db_session)
    ajena = Entorno(db_session)
    propia.informar_costo(propia.vino_id, "1000")
    ajena.informar_costo(ajena.vino_id, "2000")

    pedido_ajeno = proveedores_service.obtener_costos_informados_vigentes(
        propia.org, [ajena.vino_id], HOY, db_session
    )
    sin_pedido = proveedores_service.obtener_costos_informados_vigentes(
        propia.org, [], HOY, db_session
    )

    assert pedido_ajeno == {}
    assert sin_pedido == {}


def test_la_cantidad_de_consultas_no_depende_de_la_cantidad_de_productos(
    entorno: Entorno,
) -> None:
    productos = [entorno.vino_id]
    for numero in range(6):
        producto = entorno.crear_producto(f"Producto {numero}")
        entorno.informar_costo(producto, "100")
        productos.append(producto)
    entorno.informar_costo(entorno.vino_id, "1000")
    consultas: list[str] = []

    def _contar(_conexion: object, _cursor: object, sentencia: str, *_resto: object) -> None:
        consultas.append(sentencia)

    motor = entorno.sesion.get_bind()
    event.listen(motor, "before_cursor_execute", _contar)
    try:
        por_lote = _lote(entorno, productos)
    finally:
        event.remove(motor, "before_cursor_execute", _contar)

    assert len(por_lote) == 7
    assert len(consultas) <= 2
