"""INV-12 contra PostgreSQL real, con Hypothesis (change 09, tarea 9.2).

INV-12 (`docs/01` §20, STK-04): el stock de cada producto y ubicación es igual a
la suma de sus movimientos. Acá se prueba con la base y el servicio reales: para
secuencias arbitrarias de movimientos de varias líneas sobre dos productos y tres
ubicaciones, registradas por `stock_service.registrar_movimientos`, al final:

- `stock_saldo` es igual a la suma SQL de `stock_movimiento` en cada par;
- `costo_producto.stock_total` es igual a la suma de los saldos del producto;
- ningún saldo es negativo (STK-05: un egreso que no alcanza se rechaza entero);
- `verificar_consistencia` no devuelve diferencias.

Los comandos que se rechazan por `STOCK_INSUFICIENTE` quedan sin efecto alguno
(INV-01): una línea que se aplicó antes de la que falló se deshace con ella.

INV-01: una falla inyectada a mitad de un comando de dos líneas deshace el
movimiento, el saldo y el costo juntos; lo confirmado antes queda intacto.

Change 14, tarea 15.2: la última prueba suma a la máquina de estados las transferencias, los
ajustes de ambos signos, las anulaciones de unas y otros y la desactivación de productos: al
final cada saldo es la suma de su libro, cada stock total la suma de los saldos, no hay
diferencias y ningún producto inactivo tiene stock (CAT-05, change 14 D4).

Cada ejemplo corre dentro de un `SAVEPOINT` que se revierte: es una prueba de la
invariante, no de concurrencia (esa confirma transacciones reales, tarea 9.6). La
contraparte de dominio puro es `test_inv12_stock_dominio.py`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import ProductoConStockError
from app.modules.costeo import service as costeo_service
from app.modules.proveedores import service as _proveedores_service  # noqa: F401  (puerto ADR-025)
from app.modules.stock import repository as stock_repository
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    ProductoInactivoError,
    ProductoSinCostoError,
    StockInsuficienteError,
)
from app.modules.stock.service import LineaDeAjuste, LineaDeMovimiento, LineaDeTransferencia
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import (
    crear_motivo_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

MOMENTO = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

# (indice de producto, indice de ubicación, cantidad con signo, costo en micro-unidades)
type Linea = tuple[int, int, int, int]

_CANTIDADES = st.integers(min_value=-40, max_value=60).filter(lambda n: n != 0)
_LINEAS = st.tuples(
    st.integers(min_value=0, max_value=1),
    st.integers(min_value=0, max_value=2),
    _CANTIDADES,
    st.integers(min_value=1, max_value=5_000_000_000),
)
_COMANDOS = st.lists(st.lists(_LINEAS, min_size=1, max_size=3), min_size=1, max_size=15)

_PROPIEDAD = settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


class _FallaInyectada(Exception):
    pass


class _Mundo:
    """Una organización con dos productos y tres ubicaciones, creada dentro del
    `SAVEPOINT` del ejemplo."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
        self.productos = [
            crear_producto_sql(sesion, self.org, nombre=f"Producto {i}") for i in range(2)
        ]
        self.ubicaciones = [
            crear_ubicacion_sql(sesion, self.org, nombre=f"Ubicación {i}") for i in range(3)
        ]

    def lineas(self, comando: list[Linea]) -> list[LineaDeMovimiento]:
        return [
            LineaDeMovimiento(
                producto_id=self.productos[producto],
                ubicacion_id=self.ubicaciones[ubicacion],
                cantidad_base=cantidad,
                tipo="COMPRA" if cantidad > 0 else "VENTA",
                costo_unitario=(Decimal(micro) / 1_000_000) if cantidad > 0 else None,
                origen_tipo="COMPRA" if cantidad > 0 else "VENTA",
                origen_id=uuid4(),
            )
            for producto, ubicacion, cantidad, micro in comando
        ]

    def registrar(self, comando: list[Linea]) -> bool:
        """Registra el comando. `False` si se rechazó por stock insuficiente (sin
        efectos); cualquier otra falla se propaga."""
        try:
            with self.sesion.begin_nested():
                stock_service.registrar_movimientos(
                    self.org,
                    self.sesion,
                    RELOJ,
                    lineas=self.lineas(comando),
                    usuario_id=self.usuario_id,
                    dispositivo_id=self.dispositivo_id,
                    operation_id=uuid4(),
                    occurred_at=MOMENTO,
                )
        except StockInsuficienteError:
            return False
        return True

    def suma_sql_del_libro(self) -> dict[tuple[UUID, UUID], int]:
        filas = self.sesion.execute(
            text(
                "SELECT producto_id, ubicacion_id, SUM(cantidad_base) FROM stock_movimiento "
                "WHERE organizacion_id = :o GROUP BY producto_id, ubicacion_id"
            ),
            {"o": self.org},
        ).all()
        return {(fila[0], fila[1]): int(fila[2]) for fila in filas}

    def saldos_materializados(self) -> dict[tuple[UUID, UUID], int]:
        filas = self.sesion.execute(
            text(
                "SELECT producto_id, ubicacion_id, cantidad_base FROM stock_saldo "
                "WHERE organizacion_id = :o"
            ),
            {"o": self.org},
        ).all()
        return {(fila[0], fila[1]): int(fila[2]) for fila in filas}

    def verificar_la_invariante(self) -> None:
        libro = self.suma_sql_del_libro()
        materializados = self.saldos_materializados()
        for clave in set(libro) | set(materializados):
            # Un par sin movimientos puede no tener fila de saldo (perezosa): su saldo es 0.
            assert materializados.get(clave, 0) == libro.get(clave, 0)
        assert all(saldo >= 0 for saldo in materializados.values())
        for (producto_id, ubicacion_id), suma in libro.items():
            assert (
                stock_service.obtener_saldo(
                    self.org, self.sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
                )
                == suma
            )
        por_producto: dict[UUID, int] = defaultdict(int)
        for (producto_id, _), suma in libro.items():
            por_producto[producto_id] += suma
        totales = costeo_service.obtener_stock_totales(self.org, self.sesion)
        for producto_id in self.productos:
            assert totales.get(producto_id, 0) == por_producto.get(producto_id, 0)
        assert stock_service.verificar_consistencia(self.org, self.sesion) == []


@_PROPIEDAD
@given(_COMANDOS)
def test_inv12_el_saldo_materializado_es_la_suma_sql_del_libro_en_cada_par(
    db_session: Session, comandos: list[list[Linea]]
) -> None:
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session)
        for comando in comandos:
            mundo.registrar(comando)

        mundo.verificar_la_invariante()
    finally:
        savepoint.rollback()


@_PROPIEDAD
@given(_COMANDOS, st.lists(_LINEAS, min_size=2, max_size=3))
def test_inv12_inv01_una_falla_inyectada_a_mitad_de_un_comando_no_altera_lo_confirmado(
    db_session: Session, confirmados: list[list[Linea]], interrumpido: list[Linea]
) -> None:
    savepoint = db_session.begin_nested()
    try:
        mundo = _Mundo(db_session)
        for comando in confirmados:
            mundo.registrar(comando)
        antes = (mundo.suma_sql_del_libro(), mundo.saldos_materializados())
        totales_antes = costeo_service.obtener_stock_totales(mundo.org, db_session)

        real = stock_repository.insertar_movimiento
        llamadas = 0

        def _falla_en_la_segunda(*args: object, **kwargs: object) -> object:
            nonlocal llamadas
            llamadas += 1
            if llamadas == 2:
                raise _FallaInyectada
            return real(*args, **kwargs)  # type: ignore[arg-type]

        # Todas las líneas ingresan: con el primer movimiento ya aplicado (saldo y
        # costo) y el segundo a punto de insertarse, la falla tiene que llevarse
        # también lo primero.
        ingresos = [(p, u, abs(c), m) for p, u, c, m in interrumpido]
        with (
            patch.object(stock_repository, "insertar_movimiento", _falla_en_la_segunda),
            pytest.raises(_FallaInyectada),
            db_session.begin_nested(),
        ):
            stock_service.registrar_movimientos(
                mundo.org,
                db_session,
                RELOJ,
                lineas=mundo.lineas(ingresos),
                usuario_id=mundo.usuario_id,
                dispositivo_id=mundo.dispositivo_id,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )

        assert llamadas == 2
        assert (mundo.suma_sql_del_libro(), mundo.saldos_materializados()) == antes
        assert costeo_service.obtener_stock_totales(mundo.org, db_session) == totales_antes
        mundo.verificar_la_invariante()
    finally:
        savepoint.rollback()


# --- change 14, tarea 15.2: transferencias, ajustes, anulaciones y desactivación ----------

_PRODUCTO = st.integers(min_value=0, max_value=1)
_UBICACION = st.integers(min_value=0, max_value=2)
_LINEAS_DE_TRANSFERENCIA = st.lists(
    st.tuples(_PRODUCTO, st.integers(1, 40)),
    min_size=1,
    max_size=2,
    unique_by=lambda linea: linea[0],
)
_LINEAS_DE_AJUSTE = st.lists(
    st.tuples(_PRODUCTO, st.integers(-30, 30).filter(lambda n: n != 0)),
    min_size=1,
    max_size=2,
    unique_by=lambda linea: linea[0],
)
_OPERACION = st.one_of(
    st.tuples(st.just("compra"), _PRODUCTO, _UBICACION, st.integers(1, 60)),
    st.tuples(st.just("venta"), _PRODUCTO, _UBICACION, st.integers(1, 40)),
    st.tuples(st.just("transferir"), _UBICACION, st.integers(1, 2), _LINEAS_DE_TRANSFERENCIA),
    st.tuples(st.just("ajustar"), _UBICACION, _LINEAS_DE_AJUSTE),
    st.tuples(st.just("anular_transferencia"), st.integers(0, 30)),
    st.tuples(st.just("anular_ajuste"), st.integers(0, 30)),
    *([st.tuples(st.just("desactivar"), _PRODUCTO)] * 3),
)

# Lo que el estado puede rechazar sin que sea un defecto: la operación no se aplica y no deja
# efectos (INV-01).
_RECHAZOS_ESPERADOS = (
    StockInsuficienteError,
    ProductoInactivoError,
    ProductoSinCostoError,
    ProductoConStockError,
)
_PERMISOS = frozenset({"TRANSFERIR_STOCK"})


class _MundoConOperaciones(_Mundo):
    """El mundo de INV-12 más las operaciones del change 14, aplicadas por sus servicios."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion)
        self.motivo_ajuste = crear_motivo_sql(sesion, self.org, ambito="AJUSTE_STOCK")
        self.motivo_anula_transferencia = crear_motivo_sql(
            sesion, self.org, ambito="ANULACION_TRANSFERENCIA"
        )
        self.motivo_anula_ajuste = crear_motivo_sql(sesion, self.org, ambito="ANULACION_AJUSTE")
        self.transferencias: list[UUID] = []
        self.ajustes: list[UUID] = []

    def _intentar(self, accion: Callable[[], object], nombre: str = "operación") -> bool:
        try:
            with self.sesion.begin_nested():
                accion()
        except _RECHAZOS_ESPERADOS as rechazo:
            event(f"{nombre} rechazada: {type(rechazo).__name__}")
            return False
        event(f"{nombre} aplicada")
        return True

    def movimiento(self, producto: int, ubicacion: int, cantidad_firmada: int) -> None:
        self._intentar(
            lambda: stock_service.registrar_movimientos(
                self.org,
                self.sesion,
                RELOJ,
                lineas=self.lineas([(producto, ubicacion, cantidad_firmada, 1_500_000_000)]),
                usuario_id=self.usuario_id,
                dispositivo_id=self.dispositivo_id,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )
        )

    def transferir(self, origen: int, desplazamiento: int, lineas: list[tuple[int, int]]) -> None:
        def _accion() -> None:
            resultado = stock_service.transferir(
                self.org,
                self.sesion,
                RELOJ,
                ubicacion_origen_id=self.ubicaciones[origen],
                ubicacion_destino_id=self.ubicaciones[(origen + desplazamiento) % 3],
                lineas=[LineaDeTransferencia(self.productos[p], c) for p, c in lineas],
                observacion=None,
                usuario_id=self.usuario_id,
                dispositivo_id=self.dispositivo_id,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )
            self.transferencias.append(resultado.transferencia.id)

        self._intentar(_accion, "transferir")

    def ajustar(self, ubicacion: int, lineas: list[tuple[int, int]]) -> None:
        def _accion() -> None:
            resultado = stock_service.ajustar(
                self.org,
                self.sesion,
                RELOJ,
                ubicacion_id=self.ubicaciones[ubicacion],
                motivo_id=self.motivo_ajuste,
                lineas=[LineaDeAjuste(self.productos[p], c) for p, c in lineas],
                observacion=None,
                usuario_id=self.usuario_id,
                dispositivo_id=self.dispositivo_id,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )
            self.ajustes.append(resultado.ajuste.id)

        self._intentar(_accion, "ajustar")

    def _confirmadas(self, tabla: str, ids: list[UUID]) -> list[UUID]:
        return [
            cabecera
            for cabecera in ids
            if self.sesion.execute(
                text(f"SELECT estado FROM {tabla} WHERE organizacion_id = :o AND id = :i"),  # noqa: S608
                {"o": self.org, "i": cabecera},
            ).scalar_one()
            == "CONFIRMADA"
        ]

    def anular_transferencia(self, indice: int) -> None:
        pendientes = self._confirmadas("transferencia", self.transferencias)
        if pendientes:
            elegida = pendientes[indice % len(pendientes)]
            self._intentar(
                lambda: stock_service.anular_transferencia(
                    self.org,
                    self.sesion,
                    RELOJ,
                    transferencia_id=elegida,
                    motivo_id=self.motivo_anula_transferencia,
                    permisos=_PERMISOS,
                    operation_id=uuid4(),
                    usuario_id=self.usuario_id,
                    dispositivo_id=self.dispositivo_id,
                    occurred_at=MOMENTO,
                ),
                "anular_transferencia",
            )

    def anular_ajuste(self, indice: int) -> None:
        pendientes = self._confirmadas("ajuste_stock", self.ajustes)
        if pendientes:
            elegido = pendientes[indice % len(pendientes)]
            self._intentar(
                lambda: stock_service.anular_ajuste(
                    self.org,
                    self.sesion,
                    RELOJ,
                    ajuste_id=elegido,
                    motivo_id=self.motivo_anula_ajuste,
                    permitir_negativo=False,
                    operation_id=uuid4(),
                    usuario_id=self.usuario_id,
                    dispositivo_id=self.dispositivo_id,
                    occurred_at=MOMENTO,
                ),
                "anular_ajuste",
            )

    def desactivar(self, producto: int) -> None:
        producto_id = self.productos[producto]
        ((codigo, nombre, categoria, marca, proveedor, unidad, alicuota),) = self.sesion.execute(
            text(
                "SELECT codigo, nombre, categoria_id, marca_id, proveedor_id, unidad_base, "
                "alicuota_id FROM producto WHERE organizacion_id = :o AND id = :p"
            ),
            {"o": self.org, "p": producto_id},
        ).all()
        aplicada = self._intentar(
            lambda: catalogo_service.modificar_producto(
                self.org,
                self.sesion,
                RELOJ,
                producto_id=producto_id,
                codigo=codigo,
                nombre=nombre,
                categoria_id=categoria,
                marca_id=marca,
                proveedor_id=proveedor,
                unidad_base=unidad,
                alicuota_id=alicuota,
                activo=False,
                actor_id=None,
            ),
            "desactivar",
        )
        if aplicada:  # CAT-05: solo se desactiva sin ningún saldo distinto de cero
            assert self.saldos_del_producto(producto_id) == {}

    def saldos_del_producto(self, producto_id: UUID) -> dict[UUID, int]:
        """Saldos distintos de cero del producto, por ubicación."""
        saldos = {
            ubicacion: stock_service.obtener_saldo(
                self.org, self.sesion, producto_id=producto_id, ubicacion_id=ubicacion
            )
            for ubicacion in self.ubicaciones
        }
        return {ubicacion: saldo for ubicacion, saldo in saldos.items() if saldo != 0}

    def productos_inactivos(self) -> list[UUID]:
        return [
            producto_id
            for producto_id in self.productos
            if not self.sesion.execute(
                text("SELECT activo FROM producto WHERE organizacion_id = :o AND id = :p"),
                {"o": self.org, "p": producto_id},
            ).scalar_one()
        ]


@_PROPIEDAD
@given(st.lists(_OPERACION, min_size=1, max_size=25))
def test_inv12_con_transferencias_ajustes_anulaciones_y_desactivaciones(
    db_session: Session, operaciones: list[tuple[Any, ...]]
) -> None:
    """INV-12 con la máquina de estados completa del change 14: compras y ventas, transferencias,
    ajustes de ambos signos, anulación de unas y otros y desactivación de productos. Al final cada
    `stock_saldo` es la suma SQL de su libro, cada `stock_total` la suma de los saldos de su
    producto, `verificar_consistencia` no informa diferencias y ningún producto inactivo tiene un
    saldo distinto de cero (solo se desactiva sin stock y, inactivo, no admite movimientos)."""
    savepoint = db_session.begin_nested()
    try:
        mundo = _MundoConOperaciones(db_session)
        for nombre, *argumentos in operaciones:
            if nombre == "compra":
                mundo.movimiento(argumentos[0], argumentos[1], argumentos[2])
            elif nombre == "venta":
                mundo.movimiento(argumentos[0], argumentos[1], -argumentos[2])
            elif nombre == "transferir":
                mundo.transferir(*argumentos)
            elif nombre == "ajustar":
                mundo.ajustar(*argumentos)
            elif nombre == "anular_transferencia":
                mundo.anular_transferencia(*argumentos)
            elif nombre == "anular_ajuste":
                mundo.anular_ajuste(*argumentos)
            else:
                mundo.desactivar(*argumentos)

        mundo.verificar_la_invariante()
        for producto_id in mundo.productos_inactivos():
            assert mundo.saldos_del_producto(producto_id) == {}, "Producto inactivo con stock."
    finally:
        savepoint.rollback()
