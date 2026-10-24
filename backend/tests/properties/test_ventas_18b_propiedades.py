"""Change 18b, tarea 17.1: propiedades (Hypothesis) del crédito y de los descuentos de la venta.

Dominio puro (sin base):

- CRE-01, CRE-02, CRE-03, D5: el exceso es siempre `>= 0` y nunca supera la parte no cobrada de la
  venta (`máx(0, total - cobranza)`) ni lo que el saldo resultante pasa del límite; una venta
  cobrada entera nunca tiene exceso (aunque el cliente ya esté excedido); sin límite no hay exceso;
- CRE-06, D8: la tolerancia es monótona: con más tolerancia la venta sin conexión nunca se rechaza
  más (si con una tolerancia se confirma, con otra mayor también); para tolerancia en importe y en
  porcentaje del límite.

Contra PostgreSQL real, con la base como juez (consultas SQL, no las estructuras de la prueba):

- INV-14, DSC-07: por línea, `importe_neto = importe_bruto - Σ descuentos` y `importe_descuento = Σ
  descuentos` (suma de `venta_linea_descuento`), con reglas automáticas y descuento manual
  general o propio, aleatorios; y los totales de la cabecera siguen sumando sus líneas;
- DSC-08: a lo sumo un descuento `MANUAL` por línea, con el porcentaje propio si lo hay y el
  general si no (el propio reemplaza al general, sea mayor o menor).

Cada ejemplo crea su propia organización dentro de la transacción de `db_session`, que se revierte
al terminar la prueba (mismo criterio que `test_ventas_propiedades.py`).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import EntornoVenta

from app.modules.clientes.domain.credito import calcular_exceso, evaluar_credito
from app.modules.clientes.domain.errores import CreditoExcedidoError

CERO = Decimal("0.00")
CENTAVOS = Decimal("0.01")

_IMPORTE = st.integers(0, 50_000_000).map(lambda centavos: Decimal(centavos).scaleb(-2))
_LIMITE = st.one_of(st.none(), _IMPORTE)

_PROPIEDAD_PURA = settings(max_examples=300, deadline=None)
_PROPIEDAD_CON_BASE = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# --- crédito: exceso -----------------------------------------------------------------------------


# Escenario: "CRE-03 — el exceso es lo que la venta agrega por encima del límite"
@_PROPIEDAD_PURA
@given(_LIMITE, _IMPORTE, _IMPORTE, _IMPORTE)
def test_cre03_el_exceso_no_es_negativo_ni_supera_la_parte_no_cobrada(
    limite: Decimal | None, saldo: Decimal, total: Decimal, cobranza: Decimal
) -> None:
    calculo = calcular_exceso(
        limite=limite, saldo_actual=saldo, total_venta=total, cobranza=cobranza
    )

    no_cobrado = max(CERO, total - cobranza)
    assert calculo.exceso >= CERO
    assert calculo.exceso <= no_cobrado
    if limite is None:
        assert calculo.exceso == CERO  # sin límite no hay control (CRE-01)
        assert calculo.disponible is None
    else:
        assert calculo.exceso <= max(CERO, calculo.saldo_resultante - limite)
        assert calculo.disponible == limite - saldo


# Escenario: "CRE-07 — una venta cobrada entera no tiene exceso aunque el cliente ya esté excedido"
@_PROPIEDAD_PURA
@given(
    _LIMITE,
    _IMPORTE,
    _IMPORTE,
    _IMPORTE,
)
def test_cre07_una_venta_cobrada_entera_nunca_tiene_exceso(
    limite: Decimal | None, saldo: Decimal, total: Decimal, de_mas: Decimal
) -> None:
    calculo = calcular_exceso(
        limite=limite, saldo_actual=saldo, total_venta=total, cobranza=total + de_mas
    )

    assert calculo.exceso == CERO


# Escenario: "CRE-02 — el saldo resultante es saldo más total menos cobranza"
@_PROPIEDAD_PURA
@given(_LIMITE, _IMPORTE, _IMPORTE, _IMPORTE)
def test_cre02_el_exceso_es_exacto_cuando_la_venta_queda_toda_sin_cobrar(
    limite: Decimal | None, saldo: Decimal, total: Decimal, cobranza: Decimal
) -> None:
    """Sin cobranza el exceso es lo que el saldo resultante pasa del límite, hasta el total."""
    calculo = calcular_exceso(limite=limite, saldo_actual=saldo, total_venta=total, cobranza=CERO)

    assert calculo.saldo_resultante == saldo + total
    if limite is not None:
        assert calculo.exceso == min(total, max(CERO, saldo + total - limite))


# --- crédito: tolerancia monótona -----------------------------------------------------------


def _se_confirma_sin_conexion(
    *, limite: Decimal, saldo: Decimal, total: Decimal, tipo: str, valor: Decimal
) -> bool:
    """La venta sin conexión con política AUTORIZAR, sin permiso propio ni PIN: pasa solo por la
    tolerancia (si no, se comporta como BLOQUEAR)."""
    try:
        evaluar_credito(
            limite=limite,
            saldo_actual=saldo,
            total_venta=total,
            cobranza=CERO,
            politica="AUTORIZAR",
            tolerancia_tipo=tipo,
            tolerancia_valor=valor,
            modo="SIN_CONEXION",
            acepta_exceso=False,
            usuario_id="vendedor",
            permisos_usuario=(),
            autorizador=None,
        )
    except CreditoExcedidoError:
        return False
    return True


# Escenario: "CRE-06 — con más tolerancia nunca se rechaza más"
@_PROPIEDAD_PURA
@given(
    st.integers(1, 50_000_000).map(lambda c: Decimal(c).scaleb(-2)),
    _IMPORTE,
    _IMPORTE,
    st.sampled_from(["IMPORTE", "PORCENTAJE"]),
    st.integers(0, 200_000),
    st.integers(0, 200_000),
)
def test_cre06_la_tolerancia_es_monotona(
    limite: Decimal,
    saldo: Decimal,
    total: Decimal,
    tipo: str,
    centavos_a: int,
    centavos_b: int,
) -> None:
    menor, mayor = sorted((centavos_a, centavos_b))
    # En porcentaje, dos decimales (`2.50` = 2,50 %, ADR-032); en importe, centavos.
    con_menos = _se_confirma_sin_conexion(
        limite=limite, saldo=saldo, total=total, tipo=tipo, valor=Decimal(menor).scaleb(-2)
    )
    con_mas = _se_confirma_sin_conexion(
        limite=limite, saldo=saldo, total=total, tipo=tipo, valor=Decimal(mayor).scaleb(-2)
    )

    if con_menos:
        assert con_mas  # lo que pasa con menos tolerancia pasa con más


# --- descuentos: INV-14 y DSC-08 contra la base ---------------------------------------------

# Una venta: cantidad de botellas de Vino A, cantidad del producto B (0 = no lleva), porcentaje
# general (0 = ninguno) y porcentaje propio por línea (0 = ninguno), en puntos porcentuales.
type Pedido = tuple[int, int, int, int, int]
_PEDIDO = st.tuples(
    st.integers(1, 40),
    st.integers(0, 30),
    st.integers(0, 60),
    st.integers(0, 60),
    st.integers(0, 60),
)
_PEDIDOS = st.lists(_PEDIDO, min_size=1, max_size=3)
_CON_REGLA = st.booleans()

UMBRAL_DE_LA_REGLA = "5000"
PORCENTAJE_DE_LA_REGLA = Decimal("0.05")


def _fraccion(puntos: int) -> str | None:
    return None if puntos == 0 else f"{Decimal(puntos) / 100:.6f}"


def _redondear(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


class _Mundo:
    """`EntornoVenta` con stock de sobra, un segundo producto a $100 la unidad y quien vende con
    `DESCUENTO_MANUAL` y `AUTORIZAR_DESCUENTO` (cualquier porcentaje pasa por permiso propio)."""

    def __init__(self, sesion: Session, *, con_regla: bool) -> None:
        self.entorno = e = EntornoVenta(sesion, stock_inicial=100_000)
        e.configurar(descuento_manual_habilitado=True)
        e.permitir("DESCUENTO_MANUAL", "AUTORIZAR_DESCUENTO")
        self.producto_b, self.presentacion_b = e.producto_a("100.00", stock=100_000)
        self.regla_id = (
            e.crear_regla(medida="IMPORTE_BRUTO", umbral=UMBRAL_DE_LA_REGLA)
            if (con_regla)
            else None
        )
        self.manuales_esperados = 0
        self.ventas = 0

    def _contenido(self, pedido: Pedido) -> tuple[dict[str, Any], int]:
        """El contenido con los descuentos del servidor y cuántos `MANUAL` esperar."""
        e = self.entorno
        botellas, unidades_b, general, propio_a, propio_b = pedido
        lineas: list[dict[str, Any]] = [e.linea(cantidad=botellas)]
        propios = [propio_a]
        if unidades_b > 0:
            lineas.append(
                e.linea(
                    self.producto_b,
                    self.presentacion_b,
                    unidades_b,
                    precio="100.00",
                    unidades_referencia=1,
                )
            )
            propios.append(propio_b)
        brutos = [Decimal(linea["importe_bruto"]) for linea in lineas]
        con_regla = self.regla_id is not None and sum(brutos) >= Decimal(UMBRAL_DE_LA_REGLA)

        total = CERO
        manuales = 0
        for linea, bruto, propio in zip(lineas, brutos, propios, strict=True):
            descuentos: list[dict[str, Any]] = []
            neto = bruto
            if con_regla:
                automatico = _redondear(bruto * PORCENTAJE_DE_LA_REGLA)
                if automatico > 0:
                    descuentos.append(
                        {
                            "origen": "AUTOMATICO",
                            "regla_id": str(self.regla_id),
                            "porcentaje": "0.050000",
                            "importe": str(automatico),
                        }
                    )
                    neto -= automatico
            puntos = propio if propio != 0 else general  # el propio reemplaza al general
            if puntos != 0:
                manual = _redondear(neto * Decimal(puntos) / 100)
                if manual > 0:
                    descuentos.append(
                        {
                            "origen": "MANUAL",
                            "regla_id": None,
                            "porcentaje": _fraccion(puntos),
                            "importe": str(manual),
                        }
                    )
                    neto -= manual
                    manuales += 1
            linea["descuentos"] = descuentos
            if propio != 0:
                linea["descuento_manual"] = _fraccion(propio)
            total += neto
        cambios: dict[str, Any] = {"total": str(total)}
        if general != 0:
            cambios["descuento_manual_general"] = _fraccion(general)
        return e.contenido(*lineas, **cambios), manuales

    def vender(self, pedido: Pedido) -> None:
        contenido, manuales = self._contenido(pedido)
        self.entorno.enviar(contenido)
        self.manuales_esperados += manuales
        self.ventas += 1

    def _contar(self, consulta: str) -> int:
        e = self.entorno
        return int(e.sesion.execute(text(consulta), {"o": e.org}).scalar_one())

    def verificar_inv14(self) -> None:
        """Por línea, el neto es el bruto menos la suma de sus descuentos y el descuento de la
        línea es esa suma; la cabecera suma sus líneas (INV-14, DSC-07)."""
        assert (
            self._contar(
                "SELECT count(*) FROM venta_linea l WHERE l.organizacion_id = :o AND "
                "l.importe_neto <> l.importe_bruto - COALESCE((SELECT SUM(d.importe) FROM "
                "venta_linea_descuento d WHERE d.organizacion_id = l.organizacion_id "
                "AND d.venta_linea_id = l.id), 0)"
            )
            == 0
        )
        assert (
            self._contar(
                "SELECT count(*) FROM venta_linea l WHERE l.organizacion_id = :o AND "
                "l.importe_descuento <> COALESCE((SELECT SUM(d.importe) FROM "
                "venta_linea_descuento d WHERE d.organizacion_id = l.organizacion_id "
                "AND d.venta_linea_id = l.id), 0)"
            )
            == 0
        )
        assert (
            self._contar(
                "SELECT count(*) FROM venta v WHERE v.organizacion_id = :o AND "
                "(v.total <> v.total_neto + v.total_iva OR v.total_neto <> (SELECT "
                "COALESCE(SUM(l.importe_neto), 0) FROM venta_linea l WHERE "
                "l.organizacion_id = v.organizacion_id AND l.venta_id = v.id))"
            )
            == 0
        )

    def verificar_dsc08(self) -> None:
        """A lo sumo un `MANUAL` por línea, y tantos como pidió el modelo (el propio reemplaza al
        general: nunca los dos)."""
        assert (
            self._contar(
                "SELECT count(*) FROM (SELECT venta_linea_id FROM venta_linea_descuento WHERE "
                "organizacion_id = :o AND origen = 'MANUAL' GROUP BY venta_linea_id "
                "HAVING count(*) > 1) repetidas"
            )
            == 0
        )
        assert (
            self._contar(
                "SELECT count(*) FROM venta_linea_descuento WHERE organizacion_id = :o "
                "AND origen = 'MANUAL'"
            )
            == self.manuales_esperados
        )
        assert (
            self._contar(
                "SELECT count(*) FROM venta_linea_descuento WHERE organizacion_id = :o "
                "AND origen = 'MANUAL' AND (regla_id IS NOT NULL OR importe <= 0)"
            )
            == 0
        )


# Escenario: "INV-14 — por línea, neto = bruto - descuentos"
# Escenario: "DSC-08 — un solo descuento manual por línea"
@_PROPIEDAD_CON_BASE
@given(_PEDIDOS, _CON_REGLA)
def test_inv14_dsc08_neto_por_linea_y_un_solo_manual_tras_ventas_con_descuentos_aleatorios(
    db_session: Session, pedidos: list[Pedido], con_regla: bool
) -> None:
    mundo = _Mundo(db_session, con_regla=con_regla)

    for pedido in pedidos:
        mundo.vender(pedido)
        mundo.verificar_inv14()
        mundo.verificar_dsc08()

    assert mundo._contar("SELECT count(*) FROM venta WHERE organizacion_id = :o") == mundo.ventas


def test_inv14_dsc08_la_propiedad_no_es_vacia_hay_automaticos_y_manuales(
    db_session: Session,
) -> None:
    """Un pedido fijo: la regla aplica a las dos líneas y cada una lleva un manual (el propio de
    20 % en el vino reemplaza al general de 10 %, que rige en el producto B)."""
    mundo = _Mundo(db_session, con_regla=True)

    mundo.vender((40, 10, 10, 20, 0))

    assert (
        mundo._contar(
            "SELECT count(*) FROM venta_linea_descuento WHERE organizacion_id = :o "
            "AND origen = 'AUTOMATICO'"
        )
        == 2
    )
    assert (
        mundo._contar(
            "SELECT count(*) FROM venta_linea_descuento WHERE organizacion_id = :o "
            "AND origen = 'MANUAL' AND porcentaje = 0.2"
        )
        == 1
    )
    assert (
        mundo._contar(
            "SELECT count(*) FROM venta_linea_descuento WHERE organizacion_id = :o "
            "AND origen = 'MANUAL' AND porcentaje = 0.1"
        )
        == 1
    )
    mundo.verificar_inv14()
    mundo.verificar_dsc08()
