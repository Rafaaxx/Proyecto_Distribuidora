"""Tarea 5.2: `stock/service.py` contra PostgreSQL real.

Reglas citadas: STK-01, STK-02, STK-03, STK-04, STK-05, CST-10, CST-11, CST-12,
CST-13, INV-01, INV-02, INV-04, INV-12, INV-21 y `design.md` D4, D5, D6, D7, D8,
D9, D10, D11, D12.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_motivo_sql,
    crear_presentacion_referencia_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
    desactivar_producto_sql,
)

from app.core.clock import FixedClock
from app.core.errors import DomainError
from app.modules.costeo import service as costeo_service
from app.modules.costeo.domain.errores import CostoInvalidoError as CostoInvalidoDeCosteoError
from app.modules.costeo.models import CostoProducto, CostoProductoMov
from app.modules.stock import service
from app.modules.stock.domain.errores import (
    CantidadInvalidaError,
    CostoInvalidoError,
    CursorInvalidoError,
    LineasInvalidasError,
    NombreDuplicadoError,
    NombreInvalidoError,
    ProductoConOperacionesError,
    ProductoInactivoError,
    ProductoRepetidoError,
    RangoDeFechasInvalidoError,
    RecursoNoEncontradoError,
    StockInsuficienteError,
    TipoDeMovimientoInvalidoError,
    TipoDeUbicacionInvalidoError,
    UbicacionConStockError,
    UbicacionInactivaError,
    VehiculoRequiereTomaError,
)
from app.modules.stock.domain.movimientos import LineaDeMovimiento, LineaDeStockInicial
from app.modules.stock.models import StockMovimiento, StockSaldo, Ubicacion

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
DIA = timedelta(days=1)


class Entorno:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.producto_id = crear_producto_sql(sesion, self.org)
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")
        self.vehiculo_id = crear_ubicacion_sql(
            sesion, self.org, nombre="Camión 1", tipo="VEHICULO", requiere_toma=True
        )

    def producto(self, nombre: str = "Cerveza B") -> UUID:
        return crear_producto_sql(self.sesion, self.org, nombre=nombre)

    def inicial(
        self,
        *lineas: tuple[UUID, int, str | None],
        ubicacion_id: UUID | None = None,
        occurred_at: datetime = MOMENTO,
        operation_id: UUID | None = None,
    ) -> list[service.ResultadoDeMovimiento]:
        return service.registrar_stock_inicial(
            self.org,
            self.sesion,
            RELOJ,
            ubicacion_id=ubicacion_id or self.deposito_id,
            lineas=[LineaDeStockInicial(p, c, costo) for p, c, costo in lineas],
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=operation_id or uuid4(),
            occurred_at=occurred_at,
        )

    def mover(
        self,
        *lineas: LineaDeMovimiento,
        occurred_at: datetime = MOMENTO,
        operation_id: UUID | None = None,
    ) -> list[service.ResultadoDeMovimiento]:
        return service.registrar_movimientos(
            self.org,
            self.sesion,
            RELOJ,
            lineas=list(lineas),
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=operation_id or uuid4(),
            occurred_at=occurred_at,
        )

    def linea(
        self,
        cantidad: int,
        costo: str | None = None,
        *,
        tipo: str = "COMPRA",
        producto_id: UUID | None = None,
        ubicacion_id: UUID | None = None,
        motivo_id: UUID | None = None,
        jornada_id: UUID | None = None,
    ) -> LineaDeMovimiento:
        return LineaDeMovimiento(
            producto_id=producto_id or self.producto_id,
            ubicacion_id=ubicacion_id or self.deposito_id,
            cantidad_base=cantidad,
            tipo=tipo,
            costo_unitario=costo,
            origen_tipo=tipo,
            origen_id=uuid4(),
            motivo_id=motivo_id,
            jornada_id=jornada_id,
        )

    def saldo(self, producto_id: UUID | None = None, ubicacion_id: UUID | None = None) -> int:
        return service.obtener_saldo(
            self.org,
            self.sesion,
            producto_id=producto_id or self.producto_id,
            ubicacion_id=ubicacion_id or self.deposito_id,
        )

    def costo(self, producto_id: UUID | None = None) -> costeo_service.CostoVigente | None:
        return costeo_service.obtener_costo(self.org, self.sesion, producto_id or self.producto_id)

    def movimientos(self, producto_id: UUID | None = None) -> list[StockMovimiento]:
        return list(
            self.sesion.scalars(
                select(StockMovimiento)
                .where(
                    StockMovimiento.organizacion_id == self.org,
                    StockMovimiento.producto_id == (producto_id or self.producto_id),
                )
                .order_by(StockMovimiento.occurred_at, StockMovimiento.id)
            )
        )

    def cantidad_de_filas(self, modelo: type) -> int:
        return int(
            self.sesion.scalar(
                select(func.count()).select_from(modelo).where(modelo.organizacion_id == self.org)  # type: ignore[attr-defined]
            )
            or 0
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# =============================== ubicaciones ==================================


def _crear(entorno: Entorno, **cambios: object) -> Ubicacion:
    argumentos: dict[str, object] = {
        "nombre": "Depósito norte",
        "tipo": "DEPOSITO",
        "requiere_toma": False,
        "actor_id": entorno.usuario_id,
        **cambios,
    }
    return service.crear_ubicacion(entorno.org, entorno.sesion, RELOJ, **argumentos)  # type: ignore[arg-type]


def test_crear_un_deposito_lo_deja_activo_con_sus_datos(entorno: Entorno) -> None:
    """STK-02, D7."""
    ubicacion = _crear(entorno, nombre="  Depósito norte  ")

    assert ubicacion.nombre == "Depósito norte"
    assert (ubicacion.tipo, ubicacion.requiere_toma, ubicacion.activo) == ("DEPOSITO", False, True)
    assert ubicacion.organizacion_id == entorno.org
    assert ubicacion.actualizado_por_id == entorno.usuario_id
    assert ubicacion.creado_en == ubicacion.actualizado_en == MOMENTO
    assert service.obtener_ubicacion(entorno.org, entorno.sesion, ubicacion.id) is not None


def test_crear_un_vehiculo_con_toma(entorno: Entorno) -> None:
    ubicacion = _crear(entorno, nombre="Camión 2", tipo="VEHICULO", requiere_toma=True)

    assert (ubicacion.tipo, ubicacion.requiere_toma) == ("VEHICULO", True)


def test_un_vehiculo_sin_toma_se_rechaza_y_no_crea_nada(entorno: Entorno) -> None:
    antes = entorno.cantidad_de_filas(Ubicacion)

    with pytest.raises(VehiculoRequiereTomaError):
        _crear(entorno, nombre="Camión 2", tipo="VEHICULO", requiere_toma=False)

    assert entorno.cantidad_de_filas(Ubicacion) == antes


@pytest.mark.parametrize(
    ("cambios", "error"),
    [
        ({"nombre": "   "}, NombreInvalidoError),
        ({"tipo": "CAMION"}, TipoDeUbicacionInvalidoError),
    ],
)
def test_una_ubicacion_invalida_se_rechaza(
    entorno: Entorno, cambios: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        _crear(entorno, **cambios)


def test_el_nombre_no_se_repite_sin_distinguir_mayusculas_ni_espacios(entorno: Entorno) -> None:
    """D7, escenario "Nombre repetido": ` depósito central ` contra
    `Depósito central`; y la sesión sigue usable después del rechazo."""
    with pytest.raises(NombreDuplicadoError) as error:
        _crear(entorno, nombre=" depósito central ")

    assert error.value.codigo == "NOMBRE_DUPLICADO"
    assert _crear(entorno, nombre="Otro lugar").activo is True


def test_el_nombre_de_una_inactiva_tambien_cuenta(entorno: Entorno) -> None:
    inactiva = crear_ubicacion_sql(entorno.sesion, entorno.org, nombre="Vieja", activo=False)
    assert inactiva is not None

    with pytest.raises(NombreDuplicadoError):
        _crear(entorno, nombre="vieja")


def test_otra_organizacion_puede_repetir_el_nombre(entorno: Entorno) -> None:
    """TR-08."""
    otra = crear_organizacion(entorno.sesion).id

    ubicacion = service.crear_ubicacion(
        otra,
        entorno.sesion,
        RELOJ,
        nombre="Depósito central",
        tipo="DEPOSITO",
        requiere_toma=False,
        actor_id=None,
    )

    assert ubicacion.organizacion_id == otra


def _modificar(entorno: Entorno, ubicacion_id: UUID, **cambios: object) -> Ubicacion:
    actual = service.obtener_ubicacion(entorno.org, entorno.sesion, ubicacion_id)
    assert actual is not None
    argumentos: dict[str, object] = {
        "ubicacion_id": ubicacion_id,
        "nombre": actual.nombre,
        "tipo": actual.tipo,
        "requiere_toma": actual.requiere_toma,
        "activo": actual.activo,
        "actor_id": entorno.usuario_id,
        **cambios,
    }
    return service.modificar_ubicacion(entorno.org, entorno.sesion, RELOJ, **argumentos)  # type: ignore[arg-type]


def test_modificar_cambia_los_datos_y_deja_quien_y_cuando(entorno: Entorno) -> None:
    ubicacion = _modificar(
        entorno, entorno.deposito_id, nombre="  Depósito viejo ", tipo="OTRO", requiere_toma=True
    )

    assert (ubicacion.nombre, ubicacion.tipo, ubicacion.requiere_toma) == (
        "Depósito viejo",
        "OTRO",
        True,
    )
    assert ubicacion.actualizado_por_id == entorno.usuario_id


def test_modificar_conservando_el_propio_nombre_no_choca_con_si_misma(entorno: Entorno) -> None:
    ubicacion = _modificar(entorno, entorno.deposito_id, nombre="DEPÓSITO CENTRAL")

    assert ubicacion.nombre == "DEPÓSITO CENTRAL"


def test_modificar_al_nombre_de_otra_se_rechaza(entorno: Entorno) -> None:
    with pytest.raises(NombreDuplicadoError):
        _modificar(entorno, entorno.deposito_id, nombre="camión 1")


def test_modificar_un_vehiculo_para_que_no_requiera_toma_se_rechaza(entorno: Entorno) -> None:
    with pytest.raises(VehiculoRequiereTomaError):
        _modificar(entorno, entorno.vehiculo_id, requiere_toma=False)


def test_modificar_una_ubicacion_ajena_o_inexistente_es_404(entorno: Entorno) -> None:
    """INV-21, SEG-07."""
    otra = crear_organizacion(entorno.sesion).id
    ajena = crear_ubicacion_sql(entorno.sesion, otra)

    for ubicacion_id in (ajena, uuid4()):
        with pytest.raises(RecursoNoEncontradoError) as error:
            service.modificar_ubicacion(
                entorno.org,
                entorno.sesion,
                RELOJ,
                ubicacion_id=ubicacion_id,
                nombre="X",
                tipo="DEPOSITO",
                requiere_toma=False,
                activo=True,
                actor_id=None,
            )
        assert error.value.status_http == 404


def test_obtener_una_ubicacion_ajena_devuelve_none(entorno: Entorno) -> None:
    otra = crear_organizacion(entorno.sesion).id

    assert service.obtener_ubicacion(otra, entorno.sesion, entorno.deposito_id) is None


def test_listar_ubicaciones_devuelve_solo_las_de_la_organizacion(entorno: Entorno) -> None:
    """Escenario "Listar ubicaciones": solo las de A, TR-08."""
    otra = crear_organizacion(entorno.sesion).id
    crear_ubicacion_sql(entorno.sesion, otra, nombre="Depósito de B")

    pagina = service.listar_ubicaciones(
        entorno.org, entorno.sesion, activo=None, cursor=None, limite=None
    )

    assert {u.nombre for u in pagina.ubicaciones} == {"Depósito central", "Camión 1"}
    assert all(u.organizacion_id == entorno.org for u in pagina.ubicaciones)
    assert pagina.cursor_siguiente is None


def test_listar_ubicaciones_filtra_por_estado(entorno: Entorno) -> None:
    crear_ubicacion_sql(entorno.sesion, entorno.org, nombre="Vieja", activo=False)

    activas = service.listar_ubicaciones(
        entorno.org, entorno.sesion, activo=True, cursor=None, limite=None
    )
    inactivas = service.listar_ubicaciones(
        entorno.org, entorno.sesion, activo=False, cursor=None, limite=None
    )
    todas = service.listar_ubicaciones(
        entorno.org, entorno.sesion, activo=None, cursor=None, limite=None
    )

    assert {u.nombre for u in activas.ubicaciones} == {"Depósito central", "Camión 1"}
    assert [u.nombre for u in inactivas.ubicaciones] == ["Vieja"]
    assert len(todas.ubicaciones) == 3


def test_listar_ubicaciones_pagina_por_cursor_sin_repetir_ni_omitir(entorno: Entorno) -> None:
    for i in range(3):
        crear_ubicacion_sql(entorno.sesion, entorno.org, nombre=f"Otra {i}")

    primera = service.listar_ubicaciones(
        entorno.org, entorno.sesion, activo=None, cursor=None, limite=2
    )
    segunda = service.listar_ubicaciones(
        entorno.org, entorno.sesion, activo=None, cursor=primera.cursor_siguiente, limite=2
    )
    tercera = service.listar_ubicaciones(
        entorno.org, entorno.sesion, activo=None, cursor=segunda.cursor_siguiente, limite=2
    )

    vistos = [u.id for p in (primera, segunda, tercera) for u in p.ubicaciones]
    assert [len(p.ubicaciones) for p in (primera, segunda, tercera)] == [2, 2, 1]
    assert len(vistos) == len(set(vistos)) == 5
    assert primera.cursor_siguiente is not None
    assert tercera.cursor_siguiente is None


def test_listar_ubicaciones_con_cursor_ilegible_se_rechaza(entorno: Entorno) -> None:
    with pytest.raises(CursorInvalidoError):
        service.listar_ubicaciones(
            entorno.org, entorno.sesion, activo=None, cursor="no", limite=None
        )


def test_desactivar_sin_stock_y_reactivar(entorno: Entorno) -> None:
    """D8: una ubicación sin saldos distintos de cero se desactiva y se reactiva."""
    assert _modificar(entorno, entorno.deposito_id, activo=False).activo is False
    assert _modificar(entorno, entorno.deposito_id, activo=True).activo is True


def test_desactivar_con_stock_se_rechaza_y_sigue_activa(entorno: Entorno) -> None:
    entorno.inicial((entorno.producto_id, 60, "1000"))

    with pytest.raises(UbicacionConStockError) as error:
        _modificar(entorno, entorno.deposito_id, activo=False)

    assert error.value.codigo == "UBICACION_CON_STOCK"
    ubicacion = service.obtener_ubicacion(entorno.org, entorno.sesion, entorno.deposito_id)
    assert ubicacion is not None
    assert ubicacion.activo is True


def test_desactivar_con_saldo_en_cero_es_posible(entorno: Entorno) -> None:
    """D8: el criterio es "algún saldo distinto de cero"."""
    entorno.inicial((entorno.producto_id, 60, "1000"))
    entorno.inicial((entorno.producto_id, -60, None))

    assert _modificar(entorno, entorno.deposito_id, activo=False).activo is False


def test_modificar_sin_desactivar_con_stock_es_posible(entorno: Entorno) -> None:
    entorno.inicial((entorno.producto_id, 60, "1000"))

    assert _modificar(entorno, entorno.deposito_id, nombre="Depósito principal").nombre == (
        "Depósito principal"
    )


# ============================ stock inicial ===================================


def test_stock_inicial_en_el_deposito(entorno: Entorno) -> None:
    """Escenario "Stock inicial en el depósito"."""
    operacion = uuid4()
    ocurrido = MOMENTO - DIA

    (resultado,) = entorno.inicial(
        (entorno.producto_id, 60, "1000.000000"), occurred_at=ocurrido, operation_id=operacion
    )

    assert resultado.saldo == 60
    assert entorno.saldo() == 60
    costo = entorno.costo()
    assert costo is not None
    assert (costo.costo_promedio, costo.stock_total) == (Decimal("1000.000000"), 60)
    (movimiento,) = entorno.movimientos()
    assert movimiento.cantidad_base == 60
    assert movimiento.tipo == movimiento.origen_tipo == "STOCK_INICIAL"
    assert movimiento.origen_id == operacion
    assert movimiento.operation_id == operacion
    assert movimiento.costo_unitario == Decimal("1000.000000")
    assert movimiento.usuario_id == entorno.usuario_id
    assert movimiento.dispositivo_id == entorno.dispositivo_id
    assert movimiento.occurred_at == ocurrido
    assert movimiento.registered_at == MOMENTO
    assert movimiento.ubicacion_id == entorno.deposito_id
    assert entorno.cantidad_de_filas(CostoProductoMov) == 1


def test_stock_inicial_en_otra_ubicacion_recalcula_el_promedio(entorno: Entorno) -> None:
    """Escenario "Stock inicial en otra ubicación recalcula el promedio"."""
    entorno.inicial((entorno.producto_id, 60, "1000.000000"))

    entorno.inicial((entorno.producto_id, 60, "1100.000000"), ubicacion_id=entorno.vehiculo_id)

    costo = entorno.costo()
    assert costo is not None
    assert (costo.costo_promedio, costo.stock_total) == (Decimal("1050.000000"), 120)
    assert entorno.saldo() == 60
    assert entorno.saldo(ubicacion_id=entorno.vehiculo_id) == 60


def test_varias_lineas_en_un_comando(entorno: Entorno) -> None:
    """Escenario "Varias líneas en un comando": ambos con su saldo y su promedio."""
    cerveza = entorno.producto()

    resultados = entorno.inicial((entorno.producto_id, 60, "1000"), (cerveza, 24, "350.5"))

    assert [r.saldo for r in resultados] == [60, 24]
    assert entorno.saldo(cerveza) == 24
    costo = entorno.costo(cerveza)
    assert costo is not None
    assert costo.costo_promedio == Decimal("350.500000")


def test_corregir_una_cantidad_cargada_de_mas(entorno: Entorno) -> None:
    """Escenario "Corregir una cantidad cargada de más" (D4): el egreso se
    valoriza al promedio y no lo recalcula (CST-12)."""
    entorno.inicial((entorno.producto_id, 60, "1000"))

    (resultado,) = entorno.inicial((entorno.producto_id, -12, None))

    assert resultado.saldo == 48
    costo = entorno.costo()
    assert costo is not None
    assert (costo.costo_promedio, costo.stock_total) == (Decimal("1000.000000"), 48)
    ingreso, correccion = entorno.movimientos()
    assert (ingreso.cantidad_base, correccion.cantidad_base) == (60, -12)
    assert correccion.costo_unitario == Decimal("1000.000000")
    assert correccion.tipo == "STOCK_INICIAL"
    assert entorno.cantidad_de_filas(CostoProductoMov) == 1


def test_corregir_un_costo_mal_cargado(entorno: Entorno) -> None:
    """Escenario "Corregir un costo mal cargado" (D4)."""
    entorno.inicial((entorno.producto_id, 60, "10000"))
    entorno.inicial((entorno.producto_id, -60, None))

    entorno.inicial((entorno.producto_id, 60, "1000"))

    costo = entorno.costo()
    assert costo is not None
    assert (costo.costo_promedio, costo.stock_total) == (Decimal("1000.000000"), 60)


def test_una_correccion_que_dejaria_negativo_se_rechaza_sin_efectos(entorno: Entorno) -> None:
    """Escenario "Corrección que dejaría negativo"."""
    entorno.inicial((entorno.producto_id, 10, "1000"))

    with pytest.raises(StockInsuficienteError) as error:
        entorno.inicial((entorno.producto_id, -11, None))

    assert error.value.codigo == "STOCK_INSUFICIENTE"
    assert entorno.saldo() == 10
    assert len(entorno.movimientos()) == 1


def test_una_correccion_de_un_producto_sin_saldo_es_stock_insuficiente(entorno: Entorno) -> None:
    with pytest.raises(StockInsuficienteError):
        entorno.inicial((entorno.producto_id, -1, None))

    assert entorno.movimientos() == []


def test_un_producto_con_operaciones_de_otro_tipo_no_admite_stock_inicial(
    entorno: Entorno,
) -> None:
    """Escenario "Producto con operaciones de otro tipo" (D4): un movimiento de
    otro tipo insertado por el servicio (en otra ubicación)."""
    entorno.mover(entorno.linea(10, "500", tipo="COMPRA", ubicacion_id=entorno.vehiculo_id))

    with pytest.raises(ProductoConOperacionesError) as error:
        entorno.inicial((entorno.producto_id, 60, "1000"))

    assert error.value.codigo == "PRODUCTO_CON_OPERACIONES"
    assert len(entorno.movimientos()) == 1
    assert entorno.saldo() == 0


def test_un_movimiento_de_otro_tipo_sin_costo_tambien_bloquea_el_stock_inicial(
    entorno: Entorno,
) -> None:
    """Un ajuste o una venta no recalculan el promedio (CST-12) y no dejan
    historia de costo, pero también son "operaciones" (D4)."""
    entorno.inicial((entorno.producto_id, 60, "1000"))
    entorno.mover(entorno.linea(-1, None, tipo="VENTA"))

    with pytest.raises(ProductoConOperacionesError):
        entorno.inicial((entorno.producto_id, 1, "1000"))


def test_el_stock_inicial_de_otro_producto_no_se_ve_afectado_por_las_operaciones_de_uno(
    entorno: Entorno,
) -> None:
    entorno.mover(entorno.linea(10, "500", tipo="COMPRA"))
    cerveza = entorno.producto()

    entorno.inicial((cerveza, 5, "100"))

    assert entorno.saldo(cerveza) == 5


def test_un_producto_o_ubicacion_ajenos_o_inexistentes_es_404_sin_efectos(
    entorno: Entorno,
) -> None:
    """INV-21, SEG-07."""
    otra = crear_organizacion(entorno.sesion).id
    producto_ajeno = crear_producto_sql(entorno.sesion, otra)
    ubicacion_ajena = crear_ubicacion_sql(entorno.sesion, otra)

    for producto_id, ubicacion_id in (
        (producto_ajeno, entorno.deposito_id),
        (uuid4(), entorno.deposito_id),
        (entorno.producto_id, ubicacion_ajena),
        (entorno.producto_id, uuid4()),
    ):
        with pytest.raises(RecursoNoEncontradoError) as error:
            entorno.inicial((producto_id, 10, "5"), ubicacion_id=ubicacion_id)
        assert error.value.status_http == 404

    assert entorno.cantidad_de_filas(StockMovimiento) == 0
    assert entorno.cantidad_de_filas(StockSaldo) == 0
    assert entorno.cantidad_de_filas(CostoProducto) == 0


def test_una_ubicacion_inactiva_no_recibe_stock(entorno: Entorno) -> None:
    """D8: `UBICACION_INACTIVA`."""
    inactiva = crear_ubicacion_sql(entorno.sesion, entorno.org, activo=False)

    with pytest.raises(UbicacionInactivaError) as error:
        entorno.inicial((entorno.producto_id, 10, "5"), ubicacion_id=inactiva)

    assert error.value.codigo == "UBICACION_INACTIVA"
    assert entorno.cantidad_de_filas(StockMovimiento) == 0


def test_un_producto_inactivo_no_recibe_stock(entorno: Entorno) -> None:
    """CAT-05, D8: `PRODUCTO_INACTIVO`."""
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.producto_id)

    with pytest.raises(ProductoInactivoError) as error:
        entorno.inicial((entorno.producto_id, 10, "5"))

    assert error.value.codigo == "PRODUCTO_INACTIVO"
    assert entorno.cantidad_de_filas(StockMovimiento) == 0


@pytest.mark.parametrize(
    ("lineas_de", "error"),
    [
        (lambda e: [], LineasInvalidasError),
        (lambda e: [(e.producto_id, 1, "1")] * 2, ProductoRepetidoError),
        (lambda e: [(e.producto_id, 0, "1")], CantidadInvalidaError),
        (lambda e: [(e.producto_id, 1, None)], CostoInvalidoError),
        (lambda e: [(e.producto_id, -1, "1")], CostoInvalidoError),
        (lambda e: [(e.producto_id, 1, "0")], CostoInvalidoDeCosteoError),
        (lambda e: [(e.producto_id, 1, "1000.0000001")], CostoInvalidoDeCosteoError),
        (lambda e: [(e.producto_id, 1, "abc")], CostoInvalidoDeCosteoError),
    ],
)
def test_un_contenido_invalido_se_rechaza_sin_efectos(
    entorno: Entorno, lineas_de: object, error: type[Exception]
) -> None:
    """Escenarios "Contenido inválido" y "El costo del ingreso es positivo y
    exacto"."""
    with pytest.raises(error):
        entorno.inicial(*lineas_de(entorno))  # type: ignore[operator]

    assert entorno.cantidad_de_filas(StockMovimiento) == 0
    assert entorno.cantidad_de_filas(StockSaldo) == 0
    assert entorno.cantidad_de_filas(CostoProducto) == 0


def test_mas_de_doscientas_lineas_se_rechazan(entorno: Entorno) -> None:
    lineas = [(uuid4(), 1, "1") for _ in range(201)]

    with pytest.raises(LineasInvalidasError):
        entorno.inicial(*lineas)


def test_una_falla_a_mitad_del_comando_no_deja_nada(entorno: Entorno) -> None:
    """INV-01: con la primera línea valida y la segunda de un producto ajeno, la
    transacción que revierte el bus (acá, un SAVEPOINT) no deja ningún movimiento,
    saldo ni historia."""
    otra = crear_organizacion(entorno.sesion).id
    producto_ajeno = crear_producto_sql(entorno.sesion, otra)

    with pytest.raises(RecursoNoEncontradoError), entorno.sesion.begin_nested():
        entorno.inicial((entorno.producto_id, 60, "1000"), (producto_ajeno, 1, "1"))

    assert entorno.cantidad_de_filas(StockMovimiento) == 0
    assert entorno.cantidad_de_filas(StockSaldo) == 0
    assert entorno.cantidad_de_filas(CostoProducto) == 0
    assert entorno.cantidad_de_filas(CostoProductoMov) == 0


def test_una_cantidad_que_desborda_el_integer_se_rechaza(entorno: Entorno) -> None:
    entorno.inicial((entorno.producto_id, 2_147_483_647, "1"))

    with pytest.raises(DomainError) as error:
        entorno.inicial((entorno.producto_id, 1, "1"))

    assert error.value.codigo in {"CANTIDAD_FUERA_DE_RANGO", "STOCK_FUERA_DE_RANGO"}


# ======================= registrar_movimientos (genérico) =====================


def test_un_ingreso_y_un_egreso_se_valorizan_y_dejan_saldo(entorno: Entorno) -> None:
    """CST-11, CST-12: el egreso se valoriza al promedio vigente."""
    entorno.mover(entorno.linea(60, "1000"))
    entorno.mover(entorno.linea(60, "1100"))

    (resultado,) = entorno.mover(entorno.linea(-72, None, tipo="VENTA"))

    assert resultado.saldo == 48
    assert resultado.movimiento.costo_unitario == Decimal("1050.000000")
    costo = entorno.costo()
    assert costo is not None
    assert (costo.costo_promedio, costo.stock_total) == (Decimal("1050.000000"), 48)


def test_un_egreso_mayor_que_el_saldo_es_stock_insuficiente(entorno: Entorno) -> None:
    """Escenario "Egreso mayor que el saldo" (`02` §7.4, STK-05)."""
    entorno.mover(entorno.linea(10, "1000"))

    with pytest.raises(StockInsuficienteError):
        entorno.mover(entorno.linea(-11, None, tipo="VENTA"))

    assert entorno.saldo() == 10
    costo = entorno.costo()
    assert costo is not None
    assert costo.stock_total == 10


def test_el_egreso_no_se_toma_del_saldo_de_otra_ubicacion(entorno: Entorno) -> None:
    entorno.mover(entorno.linea(10, "1000", ubicacion_id=entorno.vehiculo_id))

    with pytest.raises(StockInsuficienteError):
        entorno.mover(entorno.linea(-1, None, tipo="VENTA"))


def test_un_movimiento_guarda_motivo_jornada_y_origen(entorno: Entorno) -> None:
    entorno.mover(entorno.linea(10, "10"))
    motivo_id = crear_motivo_sql(entorno.sesion, entorno.org)
    jornada_id = uuid4()
    linea = entorno.linea(-5, None, tipo="AJUSTE", motivo_id=motivo_id, jornada_id=jornada_id)

    (resultado,) = entorno.mover(linea)

    assert resultado.movimiento.motivo_id == motivo_id
    assert resultado.movimiento.jornada_id == jornada_id
    assert resultado.movimiento.origen_tipo == "AJUSTE"
    assert resultado.movimiento.origen_id == linea.origen_id


def test_un_ingreso_de_un_tipo_sin_reglas_de_costo_se_rechaza_sin_efectos(
    entorno: Entorno,
) -> None:
    """Un ajuste positivo no recalcula el promedio (CST-12) y todavía no tiene
    reglas propias: lo define el change 14."""
    with pytest.raises(TipoDeMovimientoInvalidoError):
        entorno.mover(entorno.linea(5, "10", tipo="AJUSTE"))

    assert entorno.cantidad_de_filas(StockMovimiento) == 0


def test_un_motivo_ajeno_es_404_sin_efectos(entorno: Entorno) -> None:
    otra = crear_organizacion(entorno.sesion).id
    motivo_ajeno = crear_motivo_sql(entorno.sesion, otra)
    entorno.mover(entorno.linea(10, "10"))

    with pytest.raises(RecursoNoEncontradoError), entorno.sesion.begin_nested():
        entorno.mover(entorno.linea(-5, None, tipo="AJUSTE", motivo_id=motivo_ajeno))

    assert len(entorno.movimientos()) == 1
    assert entorno.saldo() == 10


def test_un_tipo_fuera_del_catalogo_se_rechaza(entorno: Entorno) -> None:
    with pytest.raises(TipoDeMovimientoInvalidoError):
        entorno.mover(entorno.linea(5, "10", tipo="DEVOLUCION"))


def test_las_lineas_de_un_mismo_par_se_aplican_en_orden(entorno: Entorno) -> None:
    """Una línea puede depender de la anterior: +10 y luego -10 del mismo par."""
    resultados = entorno.mover(entorno.linea(10, "5"), entorno.linea(-10, None, tipo="VENTA"))

    assert [r.saldo for r in resultados] == [10, 0]
    assert entorno.saldo() == 0


def test_varios_productos_y_ubicaciones_en_un_movimiento(entorno: Entorno) -> None:
    cerveza = entorno.producto()

    entorno.mover(
        entorno.linea(10, "5", producto_id=cerveza, ubicacion_id=entorno.vehiculo_id),
        entorno.linea(20, "7"),
        entorno.linea(1, "3", producto_id=cerveza),
    )

    assert entorno.saldo() == 20
    assert entorno.saldo(cerveza) == 1
    assert entorno.saldo(cerveza, entorno.vehiculo_id) == 10
    costo = entorno.costo(cerveza)
    assert costo is not None
    assert costo.stock_total == 11


def test_el_servicio_no_confirma_la_transaccion(
    entorno: Entorno, _engine_de_sesion: Engine
) -> None:
    """Los handlers y servicios no hacen `commit`: la transacción es del bus."""
    entorno.inicial((entorno.producto_id, 60, "1000"))

    with _engine_de_sesion.connect() as otra_conexion:
        visibles = otra_conexion.execute(
            text("SELECT count(*) FROM stock_movimiento WHERE organizacion_id = :o"),
            {"o": entorno.org},
        ).scalar_one()

    assert visibles == 0


# ============================ lecturas: stock =================================


def test_obtener_saldo_sin_movimientos_es_cero(entorno: Entorno) -> None:
    assert entorno.saldo() == 0


def test_stock_por_ubicacion_muestra_cantidad_referencia_y_promedio(entorno: Entorno) -> None:
    """Escenario "Stock del depósito": 31 unidades base y 6 de referencia."""
    crear_presentacion_referencia_sql(
        entorno.sesion, entorno.org, entorno.producto_id, unidades_base=6
    )
    entorno.inicial((entorno.producto_id, 31, "1000"))

    pagina = service.stock_por_ubicacion(
        entorno.org, entorno.sesion, ubicacion_id=entorno.deposito_id, cursor=None, limite=None
    )

    (linea,) = pagina.lineas
    assert linea.producto_id == entorno.producto_id
    assert linea.producto_nombre == "Vino A"
    assert linea.producto_codigo.startswith("COD-")
    assert linea.cantidad_base == 31
    assert linea.unidades_referencia == 6
    assert linea.costo_promedio == Decimal("1000.000000")
    assert pagina.cursor_siguiente is None


def test_stock_por_ubicacion_omite_los_saldos_en_cero_y_los_de_otras_ubicaciones(
    entorno: Entorno,
) -> None:
    cerveza = entorno.producto()
    entorno.inicial((entorno.producto_id, 10, "5"), (cerveza, 4, "8"))
    entorno.inicial((cerveza, -4, None))
    entorno.inicial((entorno.producto_id, 3, "5"), ubicacion_id=entorno.vehiculo_id)

    pagina = service.stock_por_ubicacion(
        entorno.org, entorno.sesion, ubicacion_id=entorno.deposito_id, cursor=None, limite=None
    )

    assert [(li.producto_id, li.cantidad_base) for li in pagina.lineas] == [
        (entorno.producto_id, 10)
    ]
    assert pagina.lineas[0].unidades_referencia is None  # sin presentación de referencia


def test_stock_por_ubicacion_pagina_por_cursor(entorno: Entorno) -> None:
    productos = [entorno.producto(f"Producto {i}") for i in range(5)]
    entorno.inicial(*[(p, i + 1, "10") for i, p in enumerate(productos)])

    primera = service.stock_por_ubicacion(
        entorno.org, entorno.sesion, ubicacion_id=entorno.deposito_id, cursor=None, limite=2
    )
    segunda = service.stock_por_ubicacion(
        entorno.org,
        entorno.sesion,
        ubicacion_id=entorno.deposito_id,
        cursor=primera.cursor_siguiente,
        limite=2,
    )
    tercera = service.stock_por_ubicacion(
        entorno.org,
        entorno.sesion,
        ubicacion_id=entorno.deposito_id,
        cursor=segunda.cursor_siguiente,
        limite=2,
    )

    vistos = [li.producto_id for pagina in (primera, segunda, tercera) for li in pagina.lineas]
    assert [len(p.lineas) for p in (primera, segunda, tercera)] == [2, 2, 1]
    assert vistos == sorted(productos)
    assert primera.cursor_siguiente is not None
    assert tercera.cursor_siguiente is None


def test_stock_por_ubicacion_con_cursor_ilegible_o_ajena(entorno: Entorno) -> None:
    with pytest.raises(CursorInvalidoError):
        service.stock_por_ubicacion(
            entorno.org, entorno.sesion, ubicacion_id=entorno.deposito_id, cursor="no", limite=None
        )
    otra = crear_organizacion(entorno.sesion).id
    ajena = crear_ubicacion_sql(entorno.sesion, otra)
    with pytest.raises(RecursoNoEncontradoError):
        service.stock_por_ubicacion(
            entorno.org, entorno.sesion, ubicacion_id=ajena, cursor=None, limite=None
        )


# ============================== kardex ========================================


def _kardex(entorno: Entorno, **cambios: object) -> service.Kardex:
    argumentos: dict[str, object] = {
        "producto_id": entorno.producto_id,
        "ubicacion_id": entorno.deposito_id,
        "desde": None,
        "hasta": None,
        "cursor": None,
        "limite": None,
        **cambios,
    }
    return service.kardex(entorno.org, entorno.sesion, **argumentos)  # type: ignore[arg-type]


def test_el_kardex_muestra_los_movimientos_con_acumulado(entorno: Entorno) -> None:
    """Escenario "Kardex de una ubicación": acumulados 60 y 48, saldo actual 48."""
    entorno.inicial((entorno.producto_id, 60, "1000"), occurred_at=MOMENTO)
    entorno.inicial((entorno.producto_id, -12, None), occurred_at=MOMENTO + timedelta(hours=1))

    kardex = _kardex(entorno)

    assert [(m.cantidad_base, m.saldo_acumulado) for m in kardex.movimientos] == [
        (60, 60),
        (-12, 48),
    ]
    assert [m.costo_unitario for m in kardex.movimientos] == [
        Decimal("1000.000000"),
        Decimal("1000.000000"),
    ]
    assert (kardex.saldo_anterior, kardex.saldo_actual) == (0, 48)
    assert kardex.zona_horaria == "America/Argentina/Mendoza"
    assert kardex.cursor_siguiente is None


def test_el_kardex_identifica_el_producto_y_su_presentacion_de_referencia(
    entorno: Entorno,
) -> None:
    """La pantalla muestra las cantidades en cajas + unidades (CAT-08) sin pedirle
    el producto a `catalogo`, que exige otro permiso."""
    crear_presentacion_referencia_sql(
        entorno.sesion, entorno.org, entorno.producto_id, unidades_base=6
    )
    cerveza = entorno.producto("Cerveza B")
    entorno.inicial((entorno.producto_id, 60, "1000"), (cerveza, 5, "10"))

    con_referencia = _kardex(entorno)
    sin_referencia = _kardex(entorno, producto_id=cerveza)

    assert con_referencia.producto_nombre == "Vino A"
    assert con_referencia.producto_codigo.startswith("COD-")
    assert con_referencia.unidades_referencia == 6
    assert sin_referencia.producto_nombre == "Cerveza B"
    assert sin_referencia.unidades_referencia is None


def test_el_kardex_filtra_por_periodo_con_saldo_anterior(entorno: Entorno) -> None:
    """Escenario "Filtro de período con saldo anterior"."""
    entorno.inicial((entorno.producto_id, 60, "1000"), occurred_at=MOMENTO - 2 * DIA)
    entorno.inicial((entorno.producto_id, -12, None), occurred_at=MOMENTO)
    entorno.inicial((entorno.producto_id, 5, "1000"), occurred_at=MOMENTO + 2 * DIA)
    dia = MOMENTO.date()

    kardex = _kardex(entorno, desde=dia, hasta=dia)

    assert kardex.saldo_anterior == 60
    assert [(m.cantidad_base, m.saldo_acumulado) for m in kardex.movimientos] == [(-12, 48)]
    assert kardex.saldo_actual == 53


def test_un_movimiento_con_occurred_at_anterior_se_ubica_en_su_lugar(entorno: Entorno) -> None:
    """Escenario "Movimiento con `occurred_at` anterior"."""
    entorno.inicial((entorno.producto_id, 60, "1000"), occurred_at=MOMENTO)
    entorno.inicial((entorno.producto_id, -10, None), occurred_at=MOMENTO + timedelta(hours=2))
    entorno.inicial((entorno.producto_id, 5, "1000"), occurred_at=MOMENTO + timedelta(hours=1))

    kardex = _kardex(entorno)

    assert [(m.cantidad_base, m.saldo_acumulado) for m in kardex.movimientos] == [
        (60, 60),
        (5, 65),
        (-10, 55),
    ]


def test_el_kardex_pagina_por_cursor_sin_reiniciar_el_acumulado(entorno: Entorno) -> None:
    for indice in range(5):
        entorno.inicial(
            (entorno.producto_id, 10, "1000"), occurred_at=MOMENTO + timedelta(minutes=indice)
        )

    primera = _kardex(entorno, limite=2)
    segunda = _kardex(entorno, limite=2, cursor=primera.cursor_siguiente)
    tercera = _kardex(entorno, limite=2, cursor=segunda.cursor_siguiente)

    acumulados = [m.saldo_acumulado for p in (primera, segunda, tercera) for m in p.movimientos]
    assert acumulados == [10, 20, 30, 40, 50]
    assert primera.cursor_siguiente is not None
    assert tercera.cursor_siguiente is None


def test_el_kardex_no_mezcla_otros_productos_ni_ubicaciones(entorno: Entorno) -> None:
    cerveza = entorno.producto()
    entorno.inicial((entorno.producto_id, 60, "1000"), (cerveza, 7, "9"))
    entorno.inicial((entorno.producto_id, 5, "1000"), ubicacion_id=entorno.vehiculo_id)

    kardex = _kardex(entorno)

    assert [(m.cantidad_base, m.saldo_acumulado) for m in kardex.movimientos] == [(60, 60)]


def test_el_kardex_de_algo_ajeno_es_404_y_los_parametros_invalidos_se_rechazan(
    entorno: Entorno,
) -> None:
    otra = crear_organizacion(entorno.sesion).id
    ubicacion_ajena = crear_ubicacion_sql(entorno.sesion, otra)
    producto_ajeno = crear_producto_sql(entorno.sesion, otra)

    with pytest.raises(RecursoNoEncontradoError):
        _kardex(entorno, ubicacion_id=ubicacion_ajena)
    with pytest.raises(RecursoNoEncontradoError):
        _kardex(entorno, producto_id=producto_ajeno)
    with pytest.raises(RangoDeFechasInvalidoError):
        _kardex(entorno, desde=date(2026, 5, 2), hasta=date(2026, 5, 1))
    with pytest.raises(CursorInvalidoError):
        _kardex(entorno, cursor="basura")


# ============================ consistencia (INV-12) ===========================


def test_una_base_consistente_no_informa_diferencias(entorno: Entorno) -> None:
    """INV-12, `02` §7.6."""
    cerveza = entorno.producto()
    entorno.inicial((entorno.producto_id, 60, "1000"), (cerveza, 7, "9"))
    entorno.inicial((entorno.producto_id, 10, "1100"), ubicacion_id=entorno.vehiculo_id)
    entorno.inicial((entorno.producto_id, -5, None))

    assert service.verificar_consistencia(entorno.org, entorno.sesion) == []


def test_un_saldo_que_no_coincide_con_el_libro_se_informa(entorno: Entorno) -> None:
    entorno.inicial((entorno.producto_id, 60, "1000"))
    entorno.sesion.execute(
        text("UPDATE stock_saldo SET cantidad_base = 61 WHERE organizacion_id = :o"),
        {"o": entorno.org},
    )

    diferencias = service.verificar_consistencia(entorno.org, entorno.sesion)

    assert [
        (d.producto_id, d.ubicacion_id, d.valor_materializado, d.valor_esperado)
        for d in diferencias
        if d.ubicacion_id is not None
    ] == [(entorno.producto_id, entorno.deposito_id, 61, 60)]


def test_un_movimiento_sin_fila_de_saldo_se_informa(entorno: Entorno) -> None:
    entorno.inicial((entorno.producto_id, 60, "1000"))
    entorno.sesion.execute(
        text("DELETE FROM stock_saldo WHERE organizacion_id = :o"), {"o": entorno.org}
    )

    diferencias = service.verificar_consistencia(entorno.org, entorno.sesion)

    assert any(
        (d.producto_id, d.ubicacion_id, d.valor_materializado, d.valor_esperado)
        == (entorno.producto_id, entorno.deposito_id, 0, 60)
        for d in diferencias
    )


def test_un_stock_total_que_no_coincide_con_los_saldos_se_informa(entorno: Entorno) -> None:
    entorno.inicial((entorno.producto_id, 60, "1000"))
    entorno.sesion.execute(
        text("UPDATE costo_producto SET stock_total = 59 WHERE organizacion_id = :o"),
        {"o": entorno.org},
    )

    diferencias = service.verificar_consistencia(entorno.org, entorno.sesion)

    assert [
        (d.producto_id, d.ubicacion_id, d.valor_materializado, d.valor_esperado)
        for d in diferencias
        if d.ubicacion_id is None
    ] == [(entorno.producto_id, None, 59, 60)]


def test_la_consistencia_solo_mira_la_organizacion_pedida(entorno: Entorno) -> None:
    otra = crear_organizacion(entorno.sesion).id
    entorno.inicial((entorno.producto_id, 60, "1000"))
    entorno.sesion.execute(
        text("UPDATE stock_saldo SET cantidad_base = 1 WHERE organizacion_id = :o"),
        {"o": entorno.org},
    )

    assert service.verificar_consistencia(otra, entorno.sesion) == []
