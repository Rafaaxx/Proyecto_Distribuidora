"""Change 16, tareas 10.1 y 10.2: lo que `descuentos/service.py` entrega a la venta (change 18b) y
al bootstrap (change 21): las reglas aplicables a un momento, con sus alcances, y el cálculo de
los descuentos, de punta a punta sobre la base y sin HTTP (spec `descuentos/reglas-de-descuento`,
requisito "La vigencia delimita cuándo aplica una regla"; spec `descuentos/motor-de-descuentos`).

Reglas citadas: DSC-01, DSC-05, DSC-06, DSC-07, TR-05, TR-08, INV-21, `design.md` D11, D16, D20.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from descuentos_utiles import MODIFICAR, MOMENTO, Entorno
from sqlalchemy.orm import Session

from app.modules.descuentos import service as descuentos_service
from app.modules.descuentos.service import AlcanceRegla, LineaVenta

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

DIA = timedelta(days=1)


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _aplicables(entorno: Entorno, momento=MOMENTO, *, org: UUID | None = None):  # type: ignore[no-untyped-def]
    return descuentos_service.reglas_aplicables(org or entorno.org, entorno.sesion, momento)


def _activa(entorno: Entorno, **cambios: object) -> UUID:
    regla_id = entorno.crear_regla_descuento(**cambios)
    entorno.activar_regla(regla_id)
    return regla_id


# --- reglas_aplicables (10.1) -------------------------------------------------------------------


def test_devuelve_solo_las_activas_vigentes_con_sus_alcances(entorno: Entorno) -> None:
    activa = _activa(
        entorno,
        nombre="Marca",
        tipo="VOLUMEN_ALCANCE",
        alcances=[
            {"tipo": "MARCA", "entidad_id": str(entorno.marca_id)},
            {"tipo": "PRODUCTO", "entidad_id": str(entorno.vino_id)},
        ],
        acumulable=True,
        prioridad=3,
    )

    (regla,) = _aplicables(entorno)

    assert regla.id == str(activa)
    assert (regla.tipo, regla.medida, regla.operador) == (
        "VOLUMEN_ALCANCE",
        "CAJAS_EQUIVALENTES",
        "GTE",
    )
    assert regla.umbral == Decimal("20")
    assert (regla.accion_tipo, regla.accion_porcentaje, regla.accion_importe) == (
        "PORCENTAJE",
        Decimal("0.050000"),
        None,
    )
    assert (regla.acumulable, regla.prioridad) == (True, 3)
    assert set(regla.alcances) == {
        AlcanceRegla("MARCA", str(entorno.marca_id)),
        AlcanceRegla("PRODUCTO", str(entorno.vino_id)),
    }


def test_excluye_borradores_pausadas_programadas_y_vencidas(entorno: Entorno) -> None:
    """Escenarios "Regla programada", "Regla vencida" y "Regla pausada"."""
    entorno.crear_regla_descuento(nombre="Borrador")
    vigente = _activa(entorno, nombre="Vigente")
    pausada = _activa(entorno, nombre="Pausada")
    entorno.pausar_regla(pausada)
    _activa(entorno, nombre="Programada", vigencia_desde=(MOMENTO + 7 * DIA).isoformat())
    vencida = _activa(entorno, nombre="Vencida", vigencia_desde=(MOMENTO - 10 * DIA).isoformat())
    entorno.enviar(
        MODIFICAR, {"regla_id": str(vencida), "vigencia_hasta": (MOMENTO - DIA).isoformat()}
    )

    assert [r.id for r in _aplicables(entorno)] == [str(vigente)]


def test_usa_el_momento_pedido_y_no_el_actual(entorno: Entorno) -> None:
    """Escenario "Las reglas aplicables son las del momento de la operación" (TR-05): una regla
    vigente desde el día 10 y otra vigente hasta el día 10; el día 9 figura solo la segunda."""
    dia_10 = MOMENTO + 9 * DIA
    desde_el_10 = _activa(
        entorno, nombre="Desde el 10", vigencia_desde=dia_10.isoformat(), prioridad=1
    )
    hasta_el_10 = _activa(
        entorno,
        nombre="Hasta el 10",
        vigencia_desde=(MOMENTO - 20 * DIA).isoformat(),
        vigencia_hasta=dia_10.isoformat(),
        prioridad=2,
    )

    assert [r.id for r in _aplicables(entorno, dia_10 - DIA)] == [str(hasta_el_10)]
    assert [r.id for r in _aplicables(entorno, dia_10)] == [str(desde_el_10)]
    assert [r.id for r in _aplicables(entorno, dia_10 + 5 * DIA)] == [str(desde_el_10)]


def test_el_extremo_hasta_esta_excluido_y_el_desde_incluido(entorno: Entorno) -> None:
    fin = MOMENTO + 3 * DIA
    regla = _activa(
        entorno, vigencia_desde=(MOMENTO - DIA).isoformat(), vigencia_hasta=fin.isoformat()
    )

    assert [r.id for r in _aplicables(entorno, fin - timedelta(microseconds=1))] == [str(regla)]
    assert _aplicables(entorno, fin) == []
    assert [r.id for r in _aplicables(entorno, MOMENTO - DIA)] == [str(regla)]


def test_inv21_no_devuelve_reglas_de_otra_organizacion(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Reglas aplicables de otra organización" (INV-21, TR-08)."""
    propia = _activa(entorno)
    ajena = Entorno(db_session)
    regla_ajena = _activa(ajena, nombre="Ajena")

    assert [r.id for r in _aplicables(entorno)] == [str(propia)]
    assert [r.id for r in _aplicables(ajena, org=ajena.org)] == [str(regla_ajena)]


def test_las_devuelve_por_prioridad_y_luego_por_antiguedad(entorno: Entorno) -> None:
    segunda = _activa(entorno, nombre="B", prioridad=2)
    primera_creada = _activa(entorno, nombre="A", prioridad=1)
    empate = _activa(entorno, nombre="C", prioridad=1)

    assert [r.id for r in _aplicables(entorno)] == [
        str(primera_creada),
        str(empate),
        str(segunda),
    ]


# --- calcular_descuentos de punta a punta (10.2) -------------------------------------------------


def _lineas(
    entorno: Entorno, *, manual_vino_a: Decimal | None = None
) -> tuple[LineaVenta, LineaVenta]:
    """El escenario "Gana la de mayor beneficio total": 12 cajas de Vino A ($150.000,00) y 10 de
    Vino B ($86.000,00), referencia de 6 unidades."""
    vino_b = entorno.crear_producto("Vino B", unidades_base=6)
    return (
        LineaVenta(
            id="l-vino-a",
            bruto=Decimal("150000.00"),
            cantidad_base=72,
            unidades_referencia=6,
            producto_id=str(entorno.vino_id),
            categoria_id=str(entorno.categoria_id),
            marca_id=str(entorno.marca_id),
            descuento_manual=manual_vino_a,
        ),
        LineaVenta(
            id="l-vino-b",
            bruto=Decimal("86000.00"),
            cantidad_base=60,
            unidades_referencia=6,
            producto_id=str(vino_b),
            categoria_id=str(entorno.categoria_id),
            marca_id=str(entorno.marca_id),
            descuento_manual=None,
        ),
    )


def _r1_r2_r3(entorno: Entorno) -> None:
    """R1 "cajas >= 20 -> 5%" (toda la venta), R2 "cajas >= 10 de Vino A -> 8%" y la
    acumulable R3 "importe bruto >= 200.000 -> 2%", las tres activas."""
    _activa(entorno, nombre="R1", prioridad=1)
    _activa(
        entorno,
        nombre="R2",
        tipo="VOLUMEN_ALCANCE",
        umbral="10",
        accion_valor="0.080000",
        prioridad=2,
        alcances=[{"tipo": "PRODUCTO", "entidad_id": str(entorno.vino_id)}],
    )
    _activa(
        entorno,
        nombre="R3",
        medida="IMPORTE_BRUTO",
        umbral="200000",
        accion_valor="0.020000",
        acumulable=True,
        prioridad=3,
    )


def test_el_servicio_calcula_la_acumulable_despues_de_la_ganadora(entorno: Entorno) -> None:
    """Escenario "Una acumulable después de la ganadora" con reglas leídas de la base:
    $135.240,00 y $84.280,00 (DSC-05, DSC-07)."""
    _r1_r2_r3(entorno)
    vino_a, vino_b = _lineas(entorno)

    reglas = descuentos_service.reglas_aplicables(entorno.org, entorno.sesion, MOMENTO)
    resultado = descuentos_service.calcular_descuentos((vino_a, vino_b), reglas, None)

    assert len(reglas) == 3
    a, b = resultado.lineas
    assert (a.neto, b.neto) == (Decimal("135240.00"), Decimal("84280.00"))
    assert [d.importe for d in a.descuentos] == [Decimal("12000.00"), Decimal("2760.00")]
    assert [d.importe for d in b.descuentos] == [Decimal("1720.00")]
    assert resultado.porcentaje_manual_maximo is None


def test_el_servicio_aplica_el_manual_general_y_el_propio_de_una_linea(entorno: Entorno) -> None:
    """General 5% y Vino A con propio 10% (D11): el propio reemplaza al general; los netos son
    $121.716,00 y $80.066,00 y el máximo es `0.100000`."""
    _r1_r2_r3(entorno)
    vino_a, vino_b = _lineas(entorno, manual_vino_a=Decimal("0.100000"))

    reglas = descuentos_service.reglas_aplicables(entorno.org, entorno.sesion, MOMENTO)
    resultado = descuentos_service.calcular_descuentos(
        (vino_a, vino_b), reglas, Decimal("0.050000")
    )

    a, b = resultado.lineas
    assert (a.neto, b.neto) == (Decimal("121716.00"), Decimal("80066.00"))
    assert (a.descuentos[-1].origen, a.descuentos[-1].importe) == ("MANUAL", Decimal("13524.00"))
    assert (b.descuentos[-1].origen, b.descuentos[-1].importe) == ("MANUAL", Decimal("4214.00"))
    assert resultado.porcentaje_manual_maximo == Decimal("0.100000")


def test_una_regla_pausada_no_participa_del_calculo(entorno: Entorno) -> None:
    """Sin la regla ganadora R2 (pausada), gana R1 (5%) y la venta cambia: el cálculo usa solo
    lo que `reglas_aplicables` entrega."""
    _r1_r2_r3(entorno)
    pausada = next(r for r in entorno.reglas_de_descuento() if r.nombre == "R2")
    entorno.pausar_regla(pausada.id)
    vino_a, vino_b = _lineas(entorno)

    reglas = descuentos_service.reglas_aplicables(entorno.org, entorno.sesion, MOMENTO)
    resultado = descuentos_service.calcular_descuentos((vino_a, vino_b), reglas, None)

    assert len(reglas) == 2
    assert resultado.lineas[0].descuentos[0].importe == Decimal("7500.00")  # 5% de 150.000
