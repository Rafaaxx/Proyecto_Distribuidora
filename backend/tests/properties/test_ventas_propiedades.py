"""Change 18a, tarea 15.1: INV-07, INV-12, INV-13, INV-14 y VTA-05 después de ventas, contra
PostgreSQL real y con Hypothesis.

- INV-14 (`docs/01` §20, VTA-04): en cada venta aceptada, con conexión o sin ella,
  `total = total_neto + total_iva`, los totales de la cabecera son la suma de sus líneas y cada
  línea cumple `importe_neto = importe_bruto - importe_descuento`; se comprueba con SQL sobre la
  base, no con las estructuras en memoria de la prueba;
- INV-07 (VTA-01): ninguna venta queda sin líneas (SQL);
- INV-12 (STK-04): para secuencias arbitrarias de compras, ventas (con conexión desde el depósito
  y sin conexión desde una camioneta, que puede dejar el stock en negativo, STK-06) y cobranzas,
  el saldo de cada producto y ubicación es la suma de sus movimientos y `stock_total` es la suma
  de sus saldos;
- INV-13 (CC-04): el saldo de la cuenta del cliente es la suma de su libro y, además, es el saldo
  inicial más lo vendido menos lo cobrado (las cobranzas hechas en el acto y las sueltas);
- VTA-05, INV-10: el costo de cada línea es el promedio vigente justo antes de la venta por la
  cantidad en unidad base, redondeado a centavos `ROUND_HALF_UP`.

Cada ejemplo crea su propia organización (todo se filtra por `organizacion_id`) dentro de la
transacción de `db_session`, que se revierte al terminar la prueba; no usa un `SAVEPOINT` por
ejemplo porque el bus confirma la transacción del comando. Es una prueba de las invariantes, no de
concurrencia (esa confirma transacciones reales, `tests/concurrency/test_ventas_concurrencia.py`).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID, uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_ubicacion_sql
from ventas_confirmar_utiles import MOMENTO_VENTA, PRECIO_VINO, RELOJ_VENTA, EntornoVenta

from app.modules.cobranzas import commands as _cobranzas_commands  # noqa: F401 (registra)
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.stock import service as stock_service
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

PERMISOS = frozenset({"VENDER", "REGISTRAR_COBRANZA"})
SALDO_INICIAL = Decimal("150000.00")
PRECIO_CERVEZA = "24000.00"
CENTAVOS = Decimal("0.01")

# Una línea: (producto 0 = Vino A, 1 = Cerveza B; vendida por caja si es verdadero; cantidad).
# Cerveza B solo se vende por caja; Vino A por botella suelta o por caja x6.
type LineaPedida = tuple[int, bool, int]
type Venta = tuple[list[LineaPedida], int, bool]

_LINEAS = st.lists(
    st.tuples(st.integers(0, 1), st.booleans(), st.integers(1, 12)),
    min_size=1,
    max_size=2,
    unique_by=lambda linea: linea[0],
)
# Una venta: sus líneas, el porcentaje del total que se cobra en el acto (0 = sin cobranza; puede
# pasar de 100, y entonces queda saldo a favor) y si es sin conexión.
_VENTA = st.tuples(_LINEAS, st.integers(0, 150), st.booleans())
# Una operación: compra (producto, cantidad, costo en centavos), venta o cobranza suelta.
_OPERACION = st.one_of(
    st.tuples(
        st.just("compra"),
        st.tuples(st.integers(0, 1), st.integers(1, 60), st.integers(100, 500_000)),
    ),
    st.tuples(st.just("venta"), _VENTA),
    st.tuples(st.just("cobranza"), st.integers(1, 50_000_000)),
)
_OPERACIONES = st.lists(_OPERACION, min_size=1, max_size=8)
_SOLO_VENTAS = st.lists(st.tuples(st.just("venta"), _VENTA), min_size=1, max_size=5)

_PROPIEDAD = settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _importe(centavos: int) -> str:
    return str(Decimal(centavos).scaleb(-2))


class _Mundo:
    """`EntornoVenta` (Kiosco La Esquina con saldo de `150000.00`, Vino A con 48 botellas a $1.050
    en el depósito) más Cerveza B (caja x12 a $24.000, 60 cajas-unidad a $700 en el depósito) y
    una camioneta con toma, con su jornada ya `LIBERADA` y 40 botellas de Vino A, para vender sin
    conexión. Todo dentro de la transacción del ejemplo."""

    def __init__(self, sesion: Session) -> None:
        self.entorno = e = EntornoVenta(sesion, permisos=PERMISOS)
        self.cerveza_id, self.cerveza_caja_id = e.crear_producto("Cerveza B", unidades_caja=12)
        e.poner_precio(e.version_id, self.cerveza_id, PRECIO_CERVEZA, 12)
        e.comprar(self.cerveza_id, 60, "700")
        self.camioneta_id = crear_ubicacion_sql(
            sesion, e.org, nombre="Camioneta 2", requiere_toma=True
        )
        e.comprar(e.vino_id, 40, "1050", ubicacion_id=self.camioneta_id)
        sesion.commit()
        # `LIBERADA`: sin jornada abierta propia las ventas con conexión salen del depósito
        # (RUT-04) y las del teléfono se aceptan con `JORNADA_LIBERADA` (RUT-09) desde la camioneta
        # libre.
        self.jornada_id = e.crear_jornada(estado="LIBERADA", ubicacion_id=self.camioneta_id)
        self.productos = [e.vino_id, self.cerveza_id]
        # Lo que el depósito tiene según la prueba, para no pedir de más con conexión.
        self.deposito = {e.vino_id: 48, self.cerveza_id: 60}
        self.ventas_aceptadas: list[UUID] = []

    # --- operaciones -----------------------------------------------------------------

    def comprar(self, producto: int, cantidad: int, centavos: int) -> None:
        producto_id = self.productos[producto]
        self.entorno.comprar(producto_id, cantidad, _importe(centavos))
        self.deposito[producto_id] += cantidad

    def _linea(self, pedida: LineaPedida) -> tuple[dict[str, Any], UUID, int]:
        """La línea del contenido, el producto y las unidades base que pide."""
        e = self.entorno
        producto, por_caja, cantidad = pedida
        if producto == 1:  # Cerveza B: solo por caja x12
            linea = e.linea(
                self.cerveza_id,
                self.cerveza_caja_id,
                cantidad,
                unidades_presentacion=12,
                precio=PRECIO_CERVEZA,
                unidades_referencia=12,
            )
            return linea, self.cerveza_id, cantidad * 12
        if por_caja:
            linea = e.linea(
                e.vino_id,
                e.caja_id,
                cantidad,
                unidades_presentacion=6,
                precio=PRECIO_VINO,
                unidades_referencia=6,
            )
            return linea, e.vino_id, cantidad * 6
        return e.linea(e.vino_id, e.botella_id, cantidad), e.vino_id, cantidad

    def vender(self, venta: Venta) -> None:
        """Con conexión, solo si el depósito alcanza (si no, se omite para que la secuencia siga
        siendo válida); sin conexión, siempre (puede dejar la camioneta en negativo, STK-06)."""
        e = self.entorno
        pedidas, porcentaje, sin_conexion = venta
        armadas = [self._linea(pedida) for pedida in pedidas]
        if not sin_conexion and any(base > self.deposito[p] for _, p, base in armadas):
            return
        total = sum((Decimal(linea["importe_bruto"]) for linea, _, _ in armadas), Decimal("0.00"))
        cambios: dict[str, Any] = {}
        importe_cobrado = (total * porcentaje / 100).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
        if importe_cobrado > 0:
            cambios["cobranza"] = e.cobranza((e.efectivo_id, str(importe_cobrado), None))
        if sin_conexion:
            cambios["ubicacion_id"] = None
        contenido = e.contenido(*(linea for linea, _, _ in armadas), **cambios)
        venta_id = UUID(contenido["venta_id"])
        promedios = {producto: self.promedio(producto) for _, producto, _ in armadas}

        if sin_conexion:
            self._enviar_en_lote(contenido)
        else:
            e.enviar(contenido)
            for _, producto, base in armadas:
                self.deposito[producto] -= base
        self.ventas_aceptadas.append(venta_id)
        self.verificar_costos_de(venta_id, promedios)

    def _enviar_en_lote(self, contenido: dict[str, Any]) -> None:
        e = self.entorno
        item = ItemLote(
            operation_id=uuid4(),
            tipo="VENTA_CONFIRMAR",
            version=1,
            modo="OFFLINE",
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            occurred_at=MOMENTO_VENTA,
            secuencia=1,
            app_version="1.0.0",
            contenido={**contenido, "credito": e.credito_offline()},  # D7: obligatorio
            jornada_id=self.jornada_id,
        )
        (resultado,) = sync_service.procesar_lote(
            e.sesion,
            RELOJ_VENTA,
            organizacion_id=e.org,
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            items=[item],
        )
        assert resultado.estado in {"ACEPTADO", "ACEPTADO_CON_OBSERVACIONES"}, resultado

    def cobrar(self, centavos: int) -> None:
        e = self.entorno
        importe = _importe(centavos)
        e.enviar(
            {
                "cobranza_id": str(uuid4()),
                "cliente_id": str(e.cliente_id),
                "importe": importe,
                "medios": e.medios((e.efectivo_id, importe, None)),
            },
            tipo="COBRANZA_REGISTRAR",
        )

    # --- lecturas --------------------------------------------------------------------

    def promedio(self, producto_id: UUID) -> Decimal | None:
        e = self.entorno
        valor = e.sesion.execute(
            text(
                "SELECT costo_promedio FROM costo_producto "
                "WHERE organizacion_id = :o AND producto_id = :p"
            ),
            {"o": e.org, "p": producto_id},
        ).scalar_one_or_none()
        return None if valor is None else Decimal(valor)

    def verificar_costos_de(self, venta_id: UUID, promedios: dict[UUID, Decimal | None]) -> None:
        """VTA-05: promedio previo por unidad base, y el total de la línea es ese promedio por la
        cantidad en unidad base redondeado a centavos."""
        e = self.entorno
        lineas = e.lineas_de_venta(venta_id)
        assert lineas
        for linea in lineas:
            promedio = promedios[linea.producto_id]
            assert promedio is not None  # los dos productos tienen costo desde el armado
            assert linea.costo_unitario == promedio
            esperado = (promedio * linea.cantidad_base).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
            assert linea.costo_total == esperado
            assert linea.cantidad_base == linea.cantidad * linea.unidades_presentacion

    def _contar(self, consulta: str, **parametros: object) -> int:
        e = self.entorno
        return int(
            e.sesion.execute(text(consulta), {"o": e.org, **parametros}).scalar_one()  # type: ignore[arg-type]
        )

    # --- invariantes, comprobadas con SQL --------------------------------------------

    def verificar_inv07(self) -> None:
        """Ninguna venta sin líneas."""
        assert (
            self._contar(
                "SELECT count(*) FROM venta v WHERE v.organizacion_id = :o AND NOT EXISTS ("
                "SELECT 1 FROM venta_linea l WHERE l.organizacion_id = v.organizacion_id "
                "AND l.venta_id = v.id)"
            )
            == 0
        )
        assert self._contar("SELECT count(*) FROM venta WHERE organizacion_id = :o") == len(
            self.ventas_aceptadas
        )

    def verificar_inv14(self) -> None:
        """El total es neto más IVA; la cabecera suma sus líneas; cada neto es bruto menos
        descuento. En las ventas con conexión y en las sin conexión."""
        assert (
            self._contar(
                "SELECT count(*) FROM venta WHERE organizacion_id = :o "
                "AND total <> total_neto + total_iva"
            )
            == 0
        )
        assert (
            self._contar(
                "SELECT count(*) FROM venta v WHERE v.organizacion_id = :o AND ("
                "v.total_neto <> (SELECT COALESCE(SUM(l.importe_neto), 0) FROM venta_linea l "
                "WHERE l.organizacion_id = v.organizacion_id AND l.venta_id = v.id) "
                "OR v.total_iva <> (SELECT COALESCE(SUM(l.importe_iva), 0) FROM venta_linea l "
                "WHERE l.organizacion_id = v.organizacion_id AND l.venta_id = v.id))"
            )
            == 0
        )
        assert (
            self._contar(
                "SELECT count(*) FROM venta_linea WHERE organizacion_id = :o "
                "AND importe_neto <> importe_bruto - importe_descuento"
            )
            == 0
        )

    def verificar_inv12(self) -> None:
        """Cada saldo es la suma de sus movimientos y `stock_total` la suma de sus saldos."""
        e = self.entorno
        assert (
            self._contar(
                "SELECT count(*) FROM stock_saldo s WHERE s.organizacion_id = :o "
                "AND s.cantidad_base <> (SELECT COALESCE(SUM(m.cantidad_base), 0) "
                "FROM stock_movimiento m "
                "WHERE m.organizacion_id = s.organizacion_id AND m.producto_id = s.producto_id "
                "AND m.ubicacion_id = s.ubicacion_id)"
            )
            == 0
        )
        assert (
            self._contar(
                "SELECT count(*) FROM costo_producto c WHERE c.organizacion_id = :o "
                "AND c.stock_total <> (SELECT COALESCE(SUM(s.cantidad_base), 0) FROM stock_saldo s "
                "WHERE s.organizacion_id = c.organizacion_id AND s.producto_id = c.producto_id)"
            )
            == 0
        )
        assert stock_service.verificar_consistencia(e.org, e.sesion) == []

    def verificar_inv13(self) -> None:
        """El saldo es la suma del libro y el saldo inicial más lo vendido menos lo cobrado."""
        e = self.entorno
        ((suma,),) = e.sesion.execute(
            text(
                "SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), "
                "0) FROM cuenta_movimiento WHERE organizacion_id = :o "
                "AND cuenta_tipo = 'CLIENTE' AND entidad_id = :e"
            ),
            {"o": e.org, "e": e.cliente_id},
        ).all()
        saldo = cuentas_service.obtener_saldo(
            e.org, e.sesion, cuenta_tipo="CLIENTE", entidad_id=e.cliente_id
        )
        assert saldo == suma
        ((vendido, cobrado),) = e.sesion.execute(
            text(
                "SELECT (SELECT COALESCE(SUM(total), 0) FROM venta WHERE organizacion_id = :o "
                "AND cliente_id = :c), (SELECT COALESCE(SUM(importe), 0) FROM cobranza "
                "WHERE organizacion_id = :o AND cliente_id = :c AND estado = 'CONFIRMADA')"
            ),
            {"o": e.org, "c": e.cliente_id},
        ).all()
        assert saldo == SALDO_INICIAL + vendido - cobrado
        assert cuentas_service.verificar_consistencia(e.org, e.sesion) == []

    def verificar(self) -> None:
        self.verificar_inv07()
        self.verificar_inv14()
        self.verificar_inv12()
        self.verificar_inv13()


# Escenario: "INV-07 — ninguna venta sin líneas"
# Escenario: "INV-14 — propiedad sobre ventas aceptadas en los dos modos"
@_PROPIEDAD
@given(_SOLO_VENTAS)
def test_inv07_inv14_tras_ventas_con_y_sin_conexion_aleatorias(
    db_session: Session, operaciones: list[tuple[str, Venta]]
) -> None:
    mundo = _Mundo(db_session)

    for _, venta in operaciones:
        mundo.vender(venta)
        mundo.verificar_inv07()
        mundo.verificar_inv14()

    mundo.verificar()


# Escenario: "INV-12 — stock igual a la suma de movimientos"
# Escenario: "INV-13 — saldo igual a la suma del libro"
# Escenario: "VTA-05 — costo de cada línea al promedio previo"
@_PROPIEDAD
@given(_OPERACIONES)
def test_inv12_inv13_vta05_tras_compras_ventas_y_cobranzas_aleatorias(
    db_session: Session, operaciones: list[tuple[str, Any]]
) -> None:
    mundo = _Mundo(db_session)

    for tipo, dato in operaciones:
        if tipo == "compra":
            mundo.comprar(*dato)
        elif tipo == "venta":
            mundo.vender(dato)  # VTA-05 se comprueba línea por línea al vender
        else:
            mundo.cobrar(dato)
        mundo.verificar_inv12()
        mundo.verificar_inv13()

    mundo.verificar()
