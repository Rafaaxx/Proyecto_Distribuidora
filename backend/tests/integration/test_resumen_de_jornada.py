"""Change 24, tarea 10.1: el resumen de la jornada contra PostgreSQL real (spec
`stock/rendicion-de-jornada`, requisito "El resumen de la jornada cuadra y se congela al rendir";
`design.md` D4, D8).

Todo se siembra por SQL (el libro, las ventas, las cobranzas) salvo la rendición, que se registra
con `stock_service.rendir_jornada` para que quede congelada como en producción. La cobertura por
HTTP (permisos y 404) está en `test_jornadas_api.py`.

Reglas citadas: RUT-07, STK-04, COB-01, COB-05, INV-03, INV-12, INV-21, ADR-066.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_jornada_sql,
    crear_motivo_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
    insertar_stock_movimiento_sql,
)
from ventas_utiles import insertar_sql, sembrar_venta_sql

from app.core.clock import FixedClock
from app.modules.cobranzas import service as _cobranzas  # noqa: F401  (registra su lector)
from app.modules.stock import queries as stock_queries
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import RecursoNoEncontradoError
from app.modules.stock.domain.rendicion import LineaContada
from app.modules.stock.queries import ResumenDeJornada
from app.modules.ventas import service as _ventas  # noqa: F401  (registra su lector)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

DIA = datetime(2026, 11, 4, tzinfo=UTC)
CARGA = DIA + timedelta(hours=7)
APERTURA = DIA + timedelta(hours=8)
MEDIA_MANANA = DIA + timedelta(hours=10)
VENTA = DIA + timedelta(hours=11)
ENTREGA = DIA + timedelta(hours=17)
RENDICION = DIA + timedelta(hours=18)
TARDE = DIA + timedelta(hours=20)

VENDEDOR = frozenset({"ABRIR_JORNADA"})


class Entorno:
    """ "Camioneta 1" con la jornada de Juan abierta a las 8:00; Vino A y Agua 500; los medios
    Efectivo y Transferencia y el cliente Kiosco La Esquina."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.juan, self.dispositivo = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=VENDEDOR
        )
        self.camioneta = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.vino = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.agua = crear_producto_sql(sesion, self.org, nombre="Agua 500")
        self.cliente = crear_cliente(sesion, self.org)
        self.efectivo = self._medio("Efectivo")
        self.transferencia = self._medio("Transferencia")
        self.motivo_venta = crear_motivo_sql(sesion, self.org, ambito="ANULACION_VENTA")
        self.jornada_id = self.abrir()

    def _medio(self, nombre: str) -> UUID:
        medio_id = uuid4()
        insertar_sql(
            self.sesion,
            "medio_pago",
            {
                "id": medio_id,
                "organizacion_id": self.org,
                "nombre": nombre,
                "requiere_referencia": False,
                "activo": True,
                "creado_en": CARGA,
                "actualizado_en": CARGA,
            },
        )
        return medio_id

    def abrir(self, estado: str = "ABIERTA", **cambios: object) -> UUID:
        return crear_jornada_sql(
            self.sesion,
            self.org,
            usuario_id=self.juan,
            dispositivo_id=self.dispositivo,
            ubicacion_id=self.camioneta,
            estado=estado,
            abierta_en=APERTURA,
            **cambios,
        )

    # --- el libro --------------------------------------------------------------------------

    def mover(
        self,
        producto_id: UUID,
        cantidad: int,
        tipo: str,
        cuando: datetime,
        *,
        jornada: bool = False,
    ) -> None:
        origen = {
            "STOCK_INICIAL": "STOCK_INICIAL",
            "VENTA": "VENTA",
            "ANULACION_VENTA": "ANULACION_VENTA",
            "TRANSFERENCIA_ENTRADA": "TRANSFERENCIA",
            "TRANSFERENCIA_SALIDA": "TRANSFERENCIA",
            "AJUSTE": "AJUSTE_STOCK",
        }[tipo]
        insertar_stock_movimiento_sql(
            self.sesion,
            organizacion_id=self.org,
            producto_id=producto_id,
            ubicacion_id=self.camioneta,
            usuario_id=self.juan,
            dispositivo_id=self.dispositivo,
            cantidad_base=cantidad,
            tipo=tipo,
            origen_tipo=origen,
            costo_unitario=Decimal("1050.000000"),
            registered_at=cuando,
            occurred_at=cuando,
            jornada_id=self.jornada_id if jornada else None,
        )

    def cargar_el_dia(self) -> None:
        """Vino A: 10 antes de abrir, +36 de carga, -8 de ventas, +2 de anulación (esperado
        40). Agua 500: 12 antes de abrir, sin movimientos en la jornada (esperado 12)."""
        self.mover(self.vino, 10, "STOCK_INICIAL", CARGA)
        self.mover(self.agua, 12, "STOCK_INICIAL", CARGA)
        self.mover(self.vino, 36, "TRANSFERENCIA_ENTRADA", MEDIA_MANANA)
        self.mover(self.vino, -8, "VENTA", VENTA, jornada=True)
        self.mover(self.vino, 2, "ANULACION_VENTA", VENTA + timedelta(minutes=5), jornada=True)

    def sincronizar_saldos(self) -> None:
        """Deja `stock_saldo` igual a la suma del libro y el promedio de cada producto en
        1.050 (lo que dejaría la puerta si los movimientos hubieran entrado por ella, INV-12)."""
        self.sesion.execute(
            text(
                "INSERT INTO stock_saldo (organizacion_id, producto_id, ubicacion_id, "
                "cantidad_base, actualizado_en) "
                "SELECT organizacion_id, producto_id, ubicacion_id, SUM(cantidad_base), :m "
                "FROM stock_movimiento WHERE organizacion_id = :o "
                "GROUP BY organizacion_id, producto_id, ubicacion_id "
                "ON CONFLICT (organizacion_id, producto_id, ubicacion_id) "
                "DO UPDATE SET cantidad_base = EXCLUDED.cantidad_base"
            ),
            {"o": self.org, "m": RENDICION},
        )
        self.sesion.execute(
            text(
                "INSERT INTO costo_producto (organizacion_id, producto_id, costo_promedio, "
                "stock_total, actualizado_en) "
                "SELECT organizacion_id, producto_id, 1050.000000, SUM(cantidad_base), :m "
                "FROM stock_movimiento WHERE organizacion_id = :o "
                "GROUP BY organizacion_id, producto_id "
                "ON CONFLICT (organizacion_id, producto_id) DO UPDATE SET "
                "costo_promedio = 1050.000000, stock_total = EXCLUDED.stock_total"
            ),
            {"o": self.org, "m": RENDICION},
        )
        self.sesion.commit()

    def rendir(self, contadas: dict[UUID, int]) -> None:
        """Entrega y rinde la jornada con el conteo dado (esperado = lo que dice el libro)."""
        self.sincronizar_saldos()
        self.sesion.execute(
            text(
                "UPDATE jornada SET entregada_en = :m, entrega_occurred_at = :m, "
                "entrega_secuencia = 1 WHERE id = :id"
            ),
            {"m": ENTREGA, "id": self.jornada_id},
        )
        self.sesion.commit()
        esperados = {
            fila.producto_id: fila.esperado
            for fila in stock_queries.obtener_resumen_de_jornada(
                self.org, self.sesion, jornada_id=self.jornada_id, con_costos=False
            ).lineas
        }
        stock_service.rendir_jornada(
            self.org,
            self.sesion,
            FixedClock(RENDICION),
            jornada_id=self.jornada_id,
            usuario_id=self.juan,
            dispositivo_id=self.dispositivo,
            operation_id=uuid4(),
            occurred_at=RENDICION,
            lineas=[
                LineaContada(producto=p, contada=c, esperada=esperados.get(p, 0))
                for p, c in contadas.items()
            ],
            observacion=None,
        )
        self.sesion.commit()

    # --- el dinero -------------------------------------------------------------------------

    def vender(
        self,
        total: str,
        cuando: datetime,
        *,
        jornada_id: UUID | None = None,
        estado: str = "CONFIRMADA",
    ) -> UUID:
        venta = sembrar_venta_sql(
            self.sesion,
            self.org,
            cliente_id=self.cliente,
            usuario_id=self.juan,
            dispositivo_id=self.dispositivo,
            con_linea=False,
            total_neto=total,
            total=total,
            jornada_id=jornada_id or self.jornada_id,
            estado=estado,
            registered_at=cuando,
            occurred_at=cuando,
            modo_confirmacion="OFFLINE",
        )
        return venta.venta_id

    def anular(self, venta_id: UUID, cuando: datetime, *, jornada_id: UUID | None) -> None:
        self.sesion.execute(
            text("UPDATE venta SET estado = 'ANULADA' WHERE organizacion_id = :o AND id = :v"),
            {"o": self.org, "v": venta_id},
        )
        insertar_sql(
            self.sesion,
            "venta_anulacion",
            {
                "id": uuid4(),
                "organizacion_id": self.org,
                "venta_id": venta_id,
                "motivo_id": self.motivo_venta,
                "jornada_id": jornada_id,
                "operation_id": uuid4(),
                "usuario_id": self.juan,
                "dispositivo_id": self.dispositivo,
                "occurred_at": cuando,
                "registered_at": cuando,
            },
        )

    def cobrar(
        self,
        medios: list[tuple[UUID, str]],
        cuando: datetime,
        *,
        venta_id: UUID | None = None,
        estado: str = "CONFIRMADA",
    ) -> UUID:
        cobranza_id = uuid4()
        importe = sum((Decimal(importe) for _, importe in medios), Decimal(0))
        insertar_sql(
            self.sesion,
            "cobranza",
            {
                "id": cobranza_id,
                "organizacion_id": self.org,
                "cliente_id": self.cliente,
                "venta_id": venta_id,
                "origen": "VENTA" if venta_id else "INDEPENDIENTE",
                "importe": importe,
                "estado": estado,
                "jornada_id": self.jornada_id,
                "operation_id": uuid4(),
                "usuario_id": self.juan,
                "dispositivo_id": self.dispositivo,
                "occurred_at": cuando,
                "registered_at": cuando,
            },
        )
        for orden, (medio_id, importe_medio) in enumerate(medios):
            insertar_sql(
                self.sesion,
                "cobranza_medio",
                {
                    "id": uuid4(),
                    "organizacion_id": self.org,
                    "cobranza_id": cobranza_id,
                    "orden": orden,
                    "medio_pago_id": medio_id,
                    "importe": importe_medio,
                },
            )
        return cobranza_id

    # --- lectura ---------------------------------------------------------------------------

    def resumen(
        self, *, con_costos: bool = False, jornada_id: UUID | None = None
    ) -> ResumenDeJornada:
        self.sesion.commit()
        return stock_queries.obtener_resumen_de_jornada(
            self.org, self.sesion, jornada_id=jornada_id or self.jornada_id, con_costos=con_costos
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _por_producto(resumen: ResumenDeJornada) -> dict[UUID, object]:
    return {linea.producto_id: linea for linea in resumen.lineas}


def _cobranzas_por_medio(dinero: object, atributo: str) -> dict[str, Decimal]:
    return {medio.nombre: medio.total for medio in getattr(dinero, atributo).por_medio}


# --- El resumen cuadra (RUT-07, STK-04, INV-12) ----------------------------------------------


def test_el_resumen_cuadra_al_abrir_mas_movimientos_es_el_esperado(entorno: Entorno) -> None:
    """Spec "El resumen cuadra": Vino A muestra al abrir 10, ingresos 36, ventas 8, anulaciones
    2, otros 0 y esperado 40."""
    entorno.cargar_el_dia()

    vino = _por_producto(entorno.resumen())[entorno.vino]

    assert (vino.al_abrir, vino.ingresos, vino.ventas, vino.anulaciones, vino.otros) == (
        10,
        36,
        8,
        2,
        0,
    )
    assert vino.esperado == 40
    assert (
        vino.esperado == vino.al_abrir + vino.ingresos - vino.ventas + vino.anulaciones + vino.otros
    )


def test_los_otros_movimientos_se_suman_con_signo_y_lo_anterior_no_entra_en_la_ventana(
    entorno: Entorno,
) -> None:
    """Triangulación: salidas de transferencia y ajustes van a `otros` (neto, con signo); un
    ajuste anterior a la apertura queda en `al_abrir`; Agua 500 sin movimientos en la jornada
    igual figura (saldo distinto de cero) con esperado 12."""
    entorno.cargar_el_dia()
    entorno.mover(entorno.vino, -5, "TRANSFERENCIA_SALIDA", MEDIA_MANANA + timedelta(hours=1))
    entorno.mover(entorno.vino, -3, "AJUSTE", MEDIA_MANANA + timedelta(hours=2))
    entorno.mover(entorno.vino, 4, "AJUSTE", CARGA + timedelta(minutes=30))

    resumen = _por_producto(entorno.resumen())

    assert resumen[entorno.vino].otros == -8
    assert resumen[entorno.vino].al_abrir == 14
    assert resumen[entorno.vino].esperado == 40 - 8 + 4
    assert (resumen[entorno.agua].al_abrir, resumen[entorno.agua].esperado) == (12, 12)


def test_el_esperado_es_el_saldo_del_libro_y_no_hay_contado_antes_de_rendir(
    entorno: Entorno,
) -> None:
    entorno.cargar_el_dia()

    resumen = entorno.resumen()

    assert resumen.con_conteo is False
    assert all(linea.contado is None and linea.diferencia is None for linea in resumen.lineas)
    assert {linea.producto_id: linea.esperado for linea in resumen.lineas} == {
        entorno.vino: 40,
        entorno.agua: 12,
    }


# --- Congelado al rendir (D4) -----------------------------------------------------------------


def test_al_rendir_el_resumen_sale_de_lo_congelado_con_contado_y_diferencia(
    entorno: Entorno,
) -> None:
    """Spec "Lo tardío no cambia el resumen rendido": 37 contadas contra 40, -3; después llega
    otro movimiento y el stock del resumen no cambia."""
    entorno.cargar_el_dia()
    entorno.rendir({entorno.vino: 37, entorno.agua: 12})
    entorno.mover(entorno.vino, -1, "VENTA", TARDE, jornada=True)

    resumen = entorno.resumen()

    assert resumen.con_conteo is True
    vino = _por_producto(resumen)[entorno.vino]
    assert (vino.al_abrir, vino.ingresos, vino.ventas, vino.anulaciones, vino.otros) == (
        10,
        36,
        8,
        2,
        0,
    )
    assert (vino.esperado, vino.contado, vino.diferencia) == (40, 37, -3)
    agua = _por_producto(resumen)[entorno.agua]
    assert (agua.esperado, agua.contado, agua.diferencia) == (12, 12, 0)


def test_las_ventas_de_despues_de_la_rendicion_figuran_aparte(entorno: Entorno) -> None:
    """Spec "Lo tardío no cambia el resumen rendido": la venta sin conexión que llega después
    figura como registrada después de la rendición y no entra en las ventas de la jornada."""
    entorno.cargar_el_dia()
    entorno.vender("10000.00", VENTA)
    entorno.rendir({entorno.vino: 40, entorno.agua: 12})
    entorno.vender("2500.00", TARDE)
    resumen = entorno.resumen()

    assert (resumen.dinero.ventas.cantidad, resumen.dinero.ventas.total) == (1, Decimal("10000.00"))
    assert resumen.despues_de_la_rendicion is not None
    tardias = resumen.despues_de_la_rendicion
    assert (tardias.ventas.cantidad, tardias.ventas.total) == (1, Decimal("2500.00"))


def test_sin_rendicion_no_hay_nada_aparte(entorno: Entorno) -> None:
    entorno.vender("10000.00", TARDE)

    resumen = entorno.resumen()

    assert resumen.despues_de_la_rendicion is None
    assert resumen.dinero.ventas.cantidad == 1


# --- Dinero (COB-01, COB-05, INV-03, ADR-066) -------------------------------------------------


def test_las_ventas_vigentes_se_cuentan_con_su_total(entorno: Entorno) -> None:
    entorno.vender("30000.00", VENTA)
    entorno.vender("12500.50", VENTA + timedelta(minutes=10))

    ventas = entorno.resumen().dinero.ventas

    assert (ventas.cantidad, ventas.total) == (2, Decimal("42500.50"))


def test_las_cobranzas_se_suman_por_medio_de_pago(entorno: Entorno) -> None:
    """Spec "Cobranzas por medio de pago": una venta cobrada $30.000 en efectivo y una cobranza
    de $50.000 con $30.000 en efectivo y $20.000 por transferencia: efectivo $60.000,
    transferencia $20.000 (string, INV-03)."""
    venta = entorno.vender("30000.00", VENTA)
    entorno.cobrar([(entorno.efectivo, "30000.00")], VENTA, venta_id=venta)
    entorno.cobrar(
        [(entorno.efectivo, "30000.00"), (entorno.transferencia, "20000.00")],
        VENTA + timedelta(hours=1),
    )

    cobranzas = entorno.resumen().dinero.cobranzas

    assert _cobranzas_por_medio(entorno.resumen().dinero, "cobranzas") == {
        "Efectivo": Decimal("60000.00"),
        "Transferencia": Decimal("20000.00"),
    }
    assert (cobranzas.cantidad, cobranzas.total) == (2, Decimal("80000.00"))


def test_una_cobranza_de_otra_jornada_no_entra(entorno: Entorno) -> None:
    """Triangulación: solo cuentan las cobranzas de la jornada pedida."""
    entorno.cobrar([(entorno.efectivo, "1000.00")], VENTA)
    otra = entorno.abrir("LIBERADA")
    entorno.sesion.execute(
        text("UPDATE cobranza SET jornada_id = :otra WHERE organizacion_id = :o"),
        {"otra": otra, "o": entorno.org},
    )

    assert entorno.resumen().dinero.cobranzas.cantidad == 0
    assert entorno.resumen(jornada_id=otra).dinero.cobranzas.cantidad == 1


def test_una_cobranza_anulada_no_suma_en_su_medio_y_figura_entre_las_anuladas(
    entorno: Entorno,
) -> None:
    """Spec "Cobranza anulada aparte" (COB-05)."""
    entorno.cobrar([(entorno.efectivo, "30000.00")], VENTA)
    entorno.cobrar(
        [(entorno.efectivo, "5000.00"), (entorno.transferencia, "1500.00")],
        VENTA + timedelta(minutes=30),
        estado="ANULADA",
    )

    dinero = entorno.resumen().dinero

    assert _cobranzas_por_medio(dinero, "cobranzas") == {"Efectivo": Decimal("30000.00")}
    assert _cobranzas_por_medio(dinero, "cobranzas_anuladas") == {
        "Efectivo": Decimal("5000.00"),
        "Transferencia": Decimal("1500.00"),
    }
    assert (dinero.cobranzas_anuladas.cantidad, dinero.cobranzas_anuladas.total) == (
        1,
        Decimal("6500.00"),
    )


def test_la_anulacion_de_una_jornada_liberada_figura_entre_las_anuladas(
    entorno: Entorno,
) -> None:
    """Spec "Anulación de una jornada liberada" (ADR-066): se cuenta por la jornada de la
    anulación aunque la jornada se haya liberado."""
    liberada = entorno.abrir("LIBERADA")
    venta = entorno.vender("8000.00", VENTA, jornada_id=liberada)
    entorno.anular(venta, VENTA + timedelta(minutes=20), jornada_id=liberada)
    otra = entorno.vender("3000.00", VENTA)
    entorno.anular(otra, VENTA + timedelta(minutes=30), jornada_id=None)

    de_la_liberada = entorno.resumen(jornada_id=liberada).dinero
    de_la_abierta = entorno.resumen().dinero

    assert (de_la_liberada.anuladas.cantidad, de_la_liberada.anuladas.total) == (
        1,
        Decimal("8000.00"),
    )
    assert de_la_liberada.ventas.cantidad == 0
    assert de_la_abierta.anuladas.cantidad == 0


# --- Costos (`01` §19) ------------------------------------------------------------------------


def test_el_valor_de_las_diferencias_solo_con_ver_costos(entorno: Entorno) -> None:
    """Spec "Sin permiso de costos": -3 a $1.050 vale -$3.150,00 con `VER_COSTOS`; sin él no
    se informa."""
    entorno.cargar_el_dia()
    entorno.rendir({entorno.vino: 37, entorno.agua: 12})
    con = entorno.resumen(con_costos=True)
    sin = entorno.resumen(con_costos=False)

    assert sin.valor_de_diferencias is None
    assert all(linea.valor_diferencia is None for linea in sin.lineas)
    assert con.valor_de_diferencias == Decimal("-3150.00")
    assert _por_producto(con)[entorno.vino].valor_diferencia == Decimal("-3150.00")
    assert _por_producto(con)[entorno.agua].valor_diferencia == Decimal("0.00")


# --- Jornadas sin conteo (D8) -----------------------------------------------------------------


def test_una_jornada_cerrada_antes_del_change_informa_stock_y_dinero_sin_conteo(
    entorno: Entorno,
) -> None:
    """Spec "Jornada sin conteo": una `CERRADA` sin rendición (v1) y una `LIBERADA`: el stock
    calculado hasta su rendición o liberación, sin contado ni diferencias."""
    cerrada = entorno.abrir(
        "CERRADA", rendida_en=ENTREGA, cerrada_en=ENTREGA + timedelta(minutes=10)
    )
    entorno.mover(entorno.vino, 10, "STOCK_INICIAL", CARGA)
    entorno.mover(entorno.vino, -4, "VENTA", VENTA)
    entorno.mover(entorno.vino, -2, "VENTA", TARDE)  # después de la rendición: no entra
    entorno.cobrar([(entorno.efectivo, "900.00")], VENTA)

    resumen = entorno.resumen(jornada_id=cerrada)

    assert resumen.con_conteo is False
    vino = _por_producto(resumen)[entorno.vino]
    assert (vino.ventas, vino.esperado) == (4, 6)
    assert vino.contado is None and vino.diferencia is None
    assert resumen.valor_de_diferencias is None


def test_una_jornada_liberada_se_calcula_hasta_su_liberacion(entorno: Entorno) -> None:
    liberada = entorno.abrir("LIBERADA", liberada_en=VENTA + timedelta(minutes=1))
    entorno.mover(entorno.agua, 10, "STOCK_INICIAL", CARGA)
    entorno.mover(entorno.agua, -3, "VENTA", VENTA)
    entorno.mover(entorno.agua, -5, "VENTA", TARDE)

    resumen = entorno.resumen(jornada_id=liberada)

    agua = _por_producto(resumen)[entorno.agua]
    assert (agua.ventas, agua.esperado) == (3, 7)
    assert resumen.con_conteo is False


# --- Aislamiento (INV-21) ---------------------------------------------------------------------


def test_inv21_una_jornada_de_otra_organizacion_o_inexistente_es_404(
    entorno: Entorno, db_session: Session
) -> None:
    ajena = Entorno(db_session)

    for jornada_id in (ajena.jornada_id, uuid4()):
        with pytest.raises(RecursoNoEncontradoError):
            entorno.resumen(jornada_id=jornada_id)
