"""Tarea 5.1: `costeo/service.py` contra PostgreSQL real.

Reglas citadas: CST-10, CST-11, CST-12, CST-13, CST-14, INV-01, INV-02, INV-21 y
`design.md` D4, D6, D9, D10, D14.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql

from app.core.clock import FixedClock
from app.modules.costeo import service
from app.modules.costeo.domain.errores import (
    CantidadInvalidaError,
    CostoInvalidoError,
    OrigenDeCostoInvalidoError,
    PromedioInconsistenteError,
    RecursoNoEncontradoError,
)
from app.modules.costeo.models import CostoProducto, CostoProductoMov

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


class Entorno:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.producto_id = crear_producto_sql(sesion, self.org)

    def ingresar(
        self,
        cantidad: int,
        costo: str | Decimal,
        *,
        producto_id: UUID | None = None,
        origen_tipo: str = "STOCK_INICIAL",
    ) -> service.ResultadoDeIngresoAplicado:
        return service.aplicar_ingreso(
            self.org,
            self.sesion,
            RELOJ,
            producto_id=producto_id or self.producto_id,
            cantidad=cantidad,
            costo_unitario=costo,
            origen_tipo=origen_tipo,
            origen_id=uuid4(),
            operation_id=uuid4(),
        )

    def egresar(
        self, cantidad: int, *, producto_id: UUID | None = None
    ) -> service.ResultadoDeEgresoAplicado:
        return service.aplicar_egreso(
            self.org,
            self.sesion,
            RELOJ,
            producto_id=producto_id or self.producto_id,
            cantidad=cantidad,
        )

    def revertir(
        self, cantidad: int, costo: str | Decimal, *, producto_id: UUID | None = None
    ) -> service.ResultadoDeReversionAplicada:
        return service.revertir_ingreso(
            self.org,
            self.sesion,
            RELOJ,
            producto_id=producto_id or self.producto_id,
            cantidad=cantidad,
            costo_unitario=costo,
            origen_id=uuid4(),
            operation_id=uuid4(),
        )

    def costo(self, producto_id: UUID | None = None) -> CostoProducto:
        fila = self.sesion.scalars(
            select(CostoProducto)
            .where(
                CostoProducto.organizacion_id == self.org,
                CostoProducto.producto_id == (producto_id or self.producto_id),
            )
            .execution_options(populate_existing=True)
        ).one()
        return fila

    def historia(self, producto_id: UUID | None = None) -> list[CostoProductoMov]:
        return list(
            self.sesion.scalars(
                select(CostoProductoMov)
                .where(
                    CostoProductoMov.organizacion_id == self.org,
                    CostoProductoMov.producto_id == (producto_id or self.producto_id),
                )
                .order_by(CostoProductoMov.registered_at, CostoProductoMov.id)
            )
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- bloquear_costos (D9, D10) ------------------------------------------------


def test_bloquear_costos_crea_la_fila_perezosa_sin_promedio_y_en_cero(entorno: Entorno) -> None:
    """D10: `costo_promedio` nulo ("sin costo"), `stock_total` 0."""
    bloqueados = service.bloquear_costos(entorno.org, entorno.sesion, RELOJ, [entorno.producto_id])

    assert list(bloqueados) == [entorno.producto_id]
    assert bloqueados[entorno.producto_id].costo_promedio is None
    assert bloqueados[entorno.producto_id].stock_total == 0
    fila = entorno.costo()
    assert (fila.costo_promedio, fila.stock_total) == (None, 0)


def test_bloquear_costos_no_duplica_la_fila_ni_pisa_lo_que_ya_habia(entorno: Entorno) -> None:
    entorno.ingresar(60, "1000")

    service.bloquear_costos(entorno.org, entorno.sesion, RELOJ, [entorno.producto_id])
    bloqueados = service.bloquear_costos(entorno.org, entorno.sesion, RELOJ, [entorno.producto_id])

    assert bloqueados[entorno.producto_id].costo_promedio == Decimal("1000.000000")
    assert bloqueados[entorno.producto_id].stock_total == 60
    assert (
        entorno.sesion.scalar(
            select(func.count())
            .select_from(CostoProducto)
            .where(CostoProducto.organizacion_id == entorno.org)
        )
        == 1
    )


def test_bloquear_costos_ordena_por_producto_id_y_descarta_repetidos(entorno: Entorno) -> None:
    """`02` §7.3: costos por `producto_id` ascendente, sin importar el orden en que
    los pide quien llama."""
    productos = [entorno.producto_id] + [
        crear_producto_sql(entorno.sesion, entorno.org) for _ in range(3)
    ]

    bloqueados = service.bloquear_costos(
        entorno.org, entorno.sesion, RELOJ, [*reversed(productos), productos[0]]
    )

    assert list(bloqueados) == sorted(productos)


def test_bloquear_costos_sin_productos_no_hace_nada(entorno: Entorno) -> None:
    assert service.bloquear_costos(entorno.org, entorno.sesion, RELOJ, []) == {}


def test_bloquear_un_producto_inexistente_es_404(entorno: Entorno) -> None:
    with pytest.raises(RecursoNoEncontradoError) as error:
        service.bloquear_costos(entorno.org, entorno.sesion, RELOJ, [uuid4()])

    assert error.value.status_http == 404


def test_bloquear_un_producto_de_otra_organizacion_es_404(entorno: Entorno) -> None:
    """INV-02, INV-21: la FK compuesta lo rechaza y se traduce a 404."""
    otra = crear_organizacion(entorno.sesion).id
    producto_ajeno = crear_producto_sql(entorno.sesion, otra)

    with pytest.raises(RecursoNoEncontradoError):
        service.bloquear_costos(entorno.org, entorno.sesion, RELOJ, [producto_ajeno])

    assert (
        entorno.sesion.scalar(
            select(func.count())
            .select_from(CostoProducto)
            .where(CostoProducto.producto_id == producto_ajeno)
        )
        == 0
    )


# --- aplicar_ingreso (CST-11, CST-13) -----------------------------------------


def test_el_primer_ingreso_fija_el_promedio_y_deja_historia(entorno: Entorno) -> None:
    resultado = entorno.ingresar(60, "1000")

    assert resultado.promedio_anterior is None
    assert resultado.promedio_nuevo == Decimal("1000.000000")
    assert (resultado.stock_anterior, resultado.stock_nuevo) == (0, 60)
    fila = entorno.costo()
    assert (fila.costo_promedio, fila.stock_total) == (Decimal("1000.000000"), 60)
    (historia,) = entorno.historia()
    assert historia.origen_tipo == "STOCK_INICIAL"
    assert historia.cantidad == 60
    assert historia.costo_ingreso == Decimal("1000.000000")
    assert (historia.stock_anterior, historia.stock_nuevo) == (0, 60)
    assert historia.promedio_anterior is None
    assert historia.promedio_nuevo == Decimal("1000.000000")
    assert historia.recalculado is True
    assert historia.registered_at == MOMENTO


def test_un_segundo_ingreso_promedia_y_la_historia_encadena_los_valores(entorno: Entorno) -> None:
    """Escenario "Historia de un stock inicial" (CST-13)."""
    entorno.ingresar(60, "1000")

    resultado = entorno.ingresar(60, "1100")

    assert resultado.promedio_nuevo == Decimal("1050.000000")
    assert resultado.stock_nuevo == 120
    primera, segunda = entorno.historia()
    assert (segunda.stock_anterior, segunda.stock_nuevo) == (60, 120)
    assert segunda.promedio_anterior == primera.promedio_nuevo == Decimal("1000.000000")
    assert segunda.promedio_nuevo == Decimal("1050.000000")


def test_el_ejemplo_completo_de_01_6_2(entorno: Entorno) -> None:
    """`01` §6.2: 60 a 1000, +60 a 1100, egreso de 72, +60 a 1200."""
    assert entorno.ingresar(60, "1000").promedio_nuevo == Decimal("1000.000000")
    assert entorno.ingresar(60, "1100").promedio_nuevo == Decimal("1050.000000")
    egreso = entorno.egresar(72)
    assert (egreso.costo_valorizacion, egreso.stock_nuevo) == (Decimal("1050.000000"), 48)
    ultimo = entorno.ingresar(60, "1200")

    assert ultimo.promedio_nuevo == Decimal("1133.333333")
    assert ultimo.stock_nuevo == 108
    assert entorno.costo().costo_promedio == Decimal("1133.333333")
    assert len(entorno.historia()) == 3


def test_con_stock_total_cero_el_promedio_pasa_a_ser_el_costo_del_ingreso(
    entorno: Entorno,
) -> None:
    """Escenario "Corregir un costo mal cargado" (D4): llevar el stock a cero y
    recargar."""
    entorno.ingresar(60, "10000")
    entorno.egresar(60)

    resultado = entorno.ingresar(60, "1000")

    assert resultado.promedio_nuevo == Decimal("1000.000000")
    assert entorno.costo().stock_total == 60


def test_el_promedio_es_uno_solo_para_todas_las_ubicaciones(entorno: Entorno) -> None:
    """CST-10: el servicio de costeo no conoce ubicaciones."""
    entorno.ingresar(60, "1000")
    entorno.ingresar(60, "1100")

    assert entorno.costo().costo_promedio == Decimal("1050.000000")


def test_dos_productos_llevan_promedios_independientes(entorno: Entorno) -> None:
    otro = crear_producto_sql(entorno.sesion, entorno.org, nombre="Cerveza B")

    entorno.ingresar(10, "500")
    entorno.ingresar(10, "20", producto_id=otro)

    assert entorno.costo().costo_promedio == Decimal("500.000000")
    assert entorno.costo(otro).costo_promedio == Decimal("20.000000")


@pytest.mark.parametrize(
    "origen", ["COMPRA", "ANULACION_COMPRA", "STOCK_INICIAL", "ANULACION_VENTA"]
)
def test_los_cuatro_origenes_de_03_se_admiten(entorno: Entorno, origen: str) -> None:
    entorno.ingresar(1, "5", origen_tipo=origen)

    assert entorno.historia()[0].origen_tipo == origen


@pytest.mark.parametrize("origen", ["VENTA", "AJUSTE", "", "stock_inicial"])
def test_un_origen_fuera_del_catalogo_se_rechaza_sin_efectos(entorno: Entorno, origen: str) -> None:
    with pytest.raises(OrigenDeCostoInvalidoError):
        entorno.ingresar(1, "5", origen_tipo=origen)

    assert entorno.historia() == []


@pytest.mark.parametrize("costo", ["0", "-1", "1000.0000001", "abc", 1000, None])
def test_un_costo_invalido_no_deja_ningun_efecto(entorno: Entorno, costo: object) -> None:
    """D6: `COSTO_INVALIDO`, sin fila de costo ni historia."""
    with pytest.raises(CostoInvalidoError):
        entorno.ingresar(60, costo)  # type: ignore[arg-type]

    assert entorno.historia() == []
    assert (
        entorno.sesion.scalar(
            select(func.count())
            .select_from(CostoProducto)
            .where(CostoProducto.organizacion_id == entorno.org)
        )
        == 0
    )


@pytest.mark.parametrize("cantidad", [0, -5])
def test_un_ingreso_exige_cantidad_positiva(entorno: Entorno, cantidad: int) -> None:
    with pytest.raises(CantidadInvalidaError):
        entorno.ingresar(cantidad, "10")

    assert entorno.historia() == []


def test_un_ingreso_de_un_producto_ajeno_es_404_sin_efectos(entorno: Entorno) -> None:
    otra = crear_organizacion(entorno.sesion).id
    producto_ajeno = crear_producto_sql(entorno.sesion, otra)

    with pytest.raises(RecursoNoEncontradoError):
        entorno.ingresar(1, "10", producto_id=producto_ajeno)

    assert entorno.historia(producto_ajeno) == []


# --- aplicar_egreso (CST-12) --------------------------------------------------


def test_un_egreso_no_cambia_el_promedio_no_deja_historia_y_resta_del_stock(
    entorno: Entorno,
) -> None:
    entorno.ingresar(120, "1050")

    resultado = entorno.egresar(72)

    assert resultado.costo_valorizacion == Decimal("1050.000000")
    assert resultado.stock_nuevo == 48
    fila = entorno.costo()
    assert (fila.costo_promedio, fila.stock_total) == (Decimal("1050.000000"), 48)
    assert len(entorno.historia()) == 1  # solo el ingreso (CST-13: cambios del promedio)


def test_un_egreso_de_un_producto_sin_promedio_no_valoriza(entorno: Entorno) -> None:
    """D10."""
    resultado = entorno.egresar(4)

    assert resultado.costo_valorizacion is None
    assert resultado.stock_nuevo == -4
    assert entorno.costo().costo_promedio is None


@pytest.mark.parametrize("cantidad", [0, -1])
def test_un_egreso_exige_cantidad_positiva(entorno: Entorno, cantidad: int) -> None:
    with pytest.raises(CantidadInvalidaError):
        entorno.egresar(cantidad)


# --- revertir_ingreso (CMP-06, CST-13, D9) -------------------------------------


def test_revertir_recalcula_el_promedio_y_deja_la_fila_de_historia(entorno: Entorno) -> None:
    """CMP-06 y CST-13: 120 a 1050, se anula un ingreso de 60 a 1100."""
    entorno.ingresar(120, "1050")

    resultado = entorno.revertir(60, "1100")

    assert resultado.recalculado is True
    assert resultado.promedio_nuevo == Decimal("1000.000000")
    assert (resultado.stock_anterior, resultado.stock_nuevo) == (120, 60)
    fila = entorno.costo()
    assert (fila.costo_promedio, fila.stock_total) == (Decimal("1000.000000"), 60)
    _ingreso, reversion = entorno.historia()
    assert reversion.origen_tipo == "ANULACION_COMPRA"
    assert reversion.cantidad == -60
    assert reversion.costo_ingreso == Decimal("1100.000000")
    assert (reversion.stock_anterior, reversion.stock_nuevo) == (120, 60)
    assert reversion.promedio_anterior == Decimal("1050.000000")
    assert reversion.promedio_nuevo == Decimal("1000.000000")
    assert reversion.recalculado is True
    assert reversion.registered_at == MOMENTO


def test_revertir_sin_recalculo_mantiene_el_promedio_y_escribe_igual_la_historia(
    entorno: Entorno,
) -> None:
    """D9: la fila queda aunque el promedio no cambie (deuda del 09, CST-13)."""
    entorno.ingresar(48, "1050")

    resultado = entorno.revertir(60, "1100")

    assert resultado.recalculado is False
    assert resultado.promedio_nuevo == Decimal("1050.000000")
    assert resultado.stock_nuevo == -12
    fila = entorno.costo()
    assert (fila.costo_promedio, fila.stock_total) == (Decimal("1050.000000"), -12)
    _ingreso, reversion = entorno.historia()
    assert reversion.cantidad == -60
    assert reversion.costo_ingreso == Decimal("1100.000000")
    assert (reversion.stock_anterior, reversion.stock_nuevo) == (48, -12)
    assert reversion.promedio_anterior == reversion.promedio_nuevo == Decimal("1050.000000")
    assert reversion.recalculado is False


def test_la_historia_se_reconstruye_con_ingresos_y_reversiones(entorno: Entorno) -> None:
    """CST-13: cada fila encadena `stock_nuevo` y `promedio_nuevo` con la siguiente."""
    entorno.ingresar(60, "1000")
    entorno.ingresar(60, "1100")
    entorno.revertir(60, "1100")

    historia = entorno.historia()

    assert [(h.cantidad, h.promedio_nuevo, h.recalculado) for h in historia] == [
        (60, Decimal("1000.000000"), True),
        (60, Decimal("1050.000000"), True),
        (-60, Decimal("1000.000000"), True),
    ]
    for anterior, siguiente in zip(historia, historia[1:], strict=False):
        assert siguiente.stock_anterior == anterior.stock_nuevo
        assert siguiente.promedio_anterior == anterior.promedio_nuevo


def test_revertir_un_producto_sin_promedio_es_inconsistente_sin_efectos(
    entorno: Entorno,
) -> None:
    with pytest.raises(PromedioInconsistenteError):
        entorno.revertir(5, "100")

    assert entorno.historia() == []


@pytest.mark.parametrize("costo", ["0", "1.1234567", 100])
def test_revertir_con_costo_invalido_no_deja_efectos(entorno: Entorno, costo: object) -> None:
    entorno.ingresar(10, "100")

    with pytest.raises(CostoInvalidoError):
        entorno.revertir(5, costo)  # type: ignore[arg-type]

    assert len(entorno.historia()) == 1
    assert entorno.costo().stock_total == 10


@pytest.mark.parametrize("cantidad", [0, -1])
def test_revertir_exige_cantidad_positiva(entorno: Entorno, cantidad: int) -> None:
    entorno.ingresar(10, "100")

    with pytest.raises(CantidadInvalidaError):
        entorno.revertir(cantidad, "100")


def test_revertir_un_producto_ajeno_es_404_sin_efectos(entorno: Entorno) -> None:
    otra = crear_organizacion(entorno.sesion).id
    producto_ajeno = crear_producto_sql(entorno.sesion, otra)

    with pytest.raises(RecursoNoEncontradoError):
        entorno.revertir(1, "10", producto_id=producto_ajeno)

    assert entorno.historia(producto_ajeno) == []


# --- obtener_costo (CST-10) ---------------------------------------------------


def test_obtener_costo_de_un_producto_sin_fila_es_none(entorno: Entorno) -> None:
    assert service.obtener_costo(entorno.org, entorno.sesion, entorno.producto_id) is None
    assert service.obtener_promedio(entorno.org, entorno.sesion, entorno.producto_id) is None


def test_obtener_costo_devuelve_promedio_y_stock_total(entorno: Entorno) -> None:
    entorno.ingresar(60, "1000")
    entorno.ingresar(60, "1100")

    costo = service.obtener_costo(entorno.org, entorno.sesion, entorno.producto_id)

    assert costo is not None
    assert (costo.costo_promedio, costo.stock_total) == (Decimal("1050.000000"), 120)
    assert service.obtener_promedio(entorno.org, entorno.sesion, entorno.producto_id) == Decimal(
        "1050.000000"
    )


def test_obtener_costo_no_ve_la_fila_de_otra_organizacion(entorno: Entorno) -> None:
    """INV-02, INV-21."""
    otra = crear_organizacion(entorno.sesion).id
    entorno.ingresar(60, "1000")

    assert service.obtener_costo(otra, entorno.sesion, entorno.producto_id) is None


def test_obtener_promedios_devuelve_los_de_varios_productos(entorno: Entorno) -> None:
    otro = crear_producto_sql(entorno.sesion, entorno.org)
    sin_costo = crear_producto_sql(entorno.sesion, entorno.org)
    entorno.ingresar(10, "500")
    entorno.ingresar(10, "20", producto_id=otro)

    promedios = service.obtener_promedios(
        entorno.org, entorno.sesion, [entorno.producto_id, otro, sin_costo]
    )

    assert promedios == {
        entorno.producto_id: Decimal("500.000000"),
        otro: Decimal("20.000000"),
    }


# --- sin commit (`CLAUDE.md` §4) ---------------------------------------------


def test_el_servicio_no_confirma_la_transaccion(
    entorno: Entorno, _engine_de_sesion: Engine
) -> None:
    """Los handlers y servicios no hacen `commit`: la transacción es del bus."""
    entorno.ingresar(60, "1000")

    with _engine_de_sesion.connect() as otra_conexion:
        visibles = otra_conexion.execute(
            text("SELECT count(*) FROM costo_producto WHERE organizacion_id = :o"),
            {"o": entorno.org},
        ).scalar_one()

    assert visibles == 0
