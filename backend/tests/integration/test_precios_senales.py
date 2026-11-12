"""Change 13, tarea 7.5: las señales de costo del borrador (spec `precios/borrador-de-lista`,
requisito "El borrador señala los costos que requieren atención").

- Un precio calculado con un costo informado registrado con otra regla de IVA que la actual de
  la organización lleva la señal, y la generación informa cuántos son, sin bloquearse (CST-06,
  D3).
- Un precio cuyo producto tiene costos vigentes por presentación con distinto costo por unidad
  base lleva la señal y la presentación de la que salió el costo usado (CST-03, D2).

Reglas citadas: CST-03, CST-06, PRC-11, ADR-045 punto 10, `design.md` D2 y D3.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from precios_utiles import MOMENTO, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.precios import service as precios_service

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _lista_markup_cercano(entorno: Entorno) -> UUID:
    """Markup 30% y redondeo a `100.00` al más cercano."""
    lista_id = entorno.crear_lista("General", "100.00", "CERCANO")
    entorno.crear_regla(lista_id, tipo="MARKUP", valor="0.300000")
    return lista_id


def _senales(entorno: Entorno, lista_id: UUID):  # type: ignore[no-untyped-def]
    return precios_service.senales_del_borrador(entorno.org, entorno.sesion, lista_id=lista_id)


def _ser_monotributista(entorno: Entorno) -> None:
    entorno.sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET condicion_iva = 'MONOTRIBUTO', "
            "modo_impositivo = 'A', modalidad_iva_default = NULL WHERE organizacion_id = :o"
        ),
        {"o": entorno.org},
    )


# --- costos registrados con otra regla de IVA (D3) -----------------------------------------------


def test_un_costo_con_la_regla_de_iva_anterior_se_usa_y_se_senala(entorno: Entorno) -> None:
    """Escenario "Costo calculado con la regla de IVA anterior": la organización es hoy
    responsable inscripto y Cerveza B tiene su costo registrado sin computar crédito fiscal:
    `28300.00` con la señal, y el resultado informa 1 precio en esa situación."""
    lista_id = _lista_markup_cercano(entorno)
    cerveza_id = entorno.crear_producto("Cerveza B", unidades_base=12)
    entorno.informar_costo(cerveza_id, "1815", computa=False)

    comando = entorno.generar_borrador(lista_id)

    (version,) = entorno.versiones(lista_id)
    assert entorno.precios(version.id)[cerveza_id].precio_final == Decimal("28300.00")
    assert comando.resultado is not None
    assert comando.resultado["precios_con_otra_regla_iva"] == 1
    assert _senales(entorno, lista_id)[cerveza_id].costo_otra_regla_iva is True


def test_una_organizacion_que_no_cambio_de_condicion_no_tiene_la_senal(
    entorno: Entorno,
) -> None:
    """Escenario "Organización que no cambió de condición": monotributo con todos sus costos
    registrados sin computar crédito fiscal."""
    _ser_monotributista(entorno)
    lista_id = _lista_markup_cercano(entorno)
    cerveza_id = entorno.crear_producto("Cerveza B", unidades_base=12)
    entorno.informar_costo(cerveza_id, "1815", computa=False)
    entorno.informar_costo(entorno.vino_id, "1000", computa=False)

    comando = entorno.generar_borrador(lista_id)

    assert comando.resultado is not None
    assert comando.resultado["precios_con_otra_regla_iva"] == 0
    assert all(not s.costo_otra_regla_iva for s in _senales(entorno, lista_id).values())


def test_el_cambio_inverso_tambien_se_senala(entorno: Entorno) -> None:
    """Un responsable inscripto que pasa a monotributo deja costos registrados computando
    crédito fiscal: también son de otra regla."""
    _ser_monotributista(entorno)
    lista_id = _lista_markup_cercano(entorno)
    entorno.informar_costo(entorno.vino_id, "1000", computa=True)

    comando = entorno.generar_borrador(lista_id)

    assert comando.resultado is not None
    assert comando.resultado["precios_con_otra_regla_iva"] == 1
    assert _senales(entorno, lista_id)[entorno.vino_id].costo_otra_regla_iva is True


def test_la_senal_no_bloquea_la_generacion_ni_cambia_el_precio(entorno: Entorno) -> None:
    """D3: CST-03 no se altera; el precio sale igual que con la regla actual."""
    lista_id = _lista_markup_cercano(entorno)
    entorno.informar_costo(entorno.vino_id, "1000", computa=False)

    comando = entorno.generar_borrador(lista_id)

    assert comando.estado == "ACEPTADO"
    (version,) = entorno.versiones(lista_id)
    assert entorno.precios(version.id)[entorno.vino_id].precio_final == Decimal("7800.00")


def test_la_cuenta_de_precios_con_otra_regla_cuenta_solo_los_que_tienen_precio(
    entorno: Entorno,
) -> None:
    lista_id = _lista_markup_cercano(entorno)
    cerveza_id = entorno.crear_producto("Cerveza B", unidades_base=12)
    entorno.informar_costo(cerveza_id, "1815", computa=False)
    entorno.informar_costo(entorno.vino_id, "1000", computa=True)
    entorno.crear_producto("Gaseosa C")

    comando = entorno.generar_borrador(lista_id)

    assert comando.resultado is not None
    assert comando.resultado["cantidad_precios"] == 2
    assert comando.resultado["precios_con_otra_regla_iva"] == 1


# --- costos distintos por presentación (D2) -----------------------------------------------


def _vino_con_dos_presentaciones(entorno: Entorno, *, segundo_costo: str) -> tuple[UUID, UUID]:
    """Vino A con costo informado `Caja x6` a 1000 por unidad y, registrado después con la
    misma vigencia, `Caja x12` a `segundo_costo` por unidad."""
    lista_id = _lista_markup_cercano(entorno)
    caja_x12 = entorno.crear_presentacion(entorno.vino_id, "Caja x12", 12)
    entorno.informar_costo(entorno.vino_id, "1000")
    entorno.informar_costo(
        entorno.vino_id,
        segundo_costo,
        presentacion_id=caja_x12,
        creado_en=MOMENTO + timedelta(minutes=1),
    )
    return lista_id, caja_x12


def test_costos_distintos_por_presentacion_toma_el_ultimo_y_lo_senala(
    entorno: Entorno,
) -> None:
    """Escenario "Costos distintos por presentación": `7400.00` con costo de referencia
    `5700.000000`, el costo salió de `Caja x12` y lleva la señal."""
    lista_id, caja_x12 = _vino_con_dos_presentaciones(entorno, segundo_costo="950")

    comando = entorno.generar_borrador(lista_id)

    (version,) = entorno.versiones(lista_id)
    precio = entorno.precios(version.id)[entorno.vino_id]
    assert precio.precio_final == Decimal("7400.00")
    assert precio.costo_referencia == Decimal("5700.000000")
    senales = _senales(entorno, lista_id)[entorno.vino_id]
    assert senales.costos_distintos_por_presentacion is True
    assert senales.presentacion_del_costo_id == caja_x12
    assert comando.resultado is not None
    assert comando.resultado["precios_con_costos_distintos"] == 1


def test_el_costo_usado_es_el_informado_de_la_presentacion_ganadora(entorno: Entorno) -> None:
    lista_id, caja_x12 = _vino_con_dos_presentaciones(entorno, segundo_costo="950")

    entorno.generar_borrador(lista_id)

    (version,) = entorno.versiones(lista_id)
    precio = entorno.precios(version.id)[entorno.vino_id]
    presentacion_del_costo = entorno.sesion.execute(
        text("SELECT presentacion_id FROM costo_informado WHERE id = :c"),
        {"c": precio.costo_informado_id},
    ).scalar_one()
    assert presentacion_del_costo == caja_x12


def test_sin_diferencia_por_unidad_no_hay_senal_de_presentaciones(entorno: Entorno) -> None:
    lista_id, _caja_x12 = _vino_con_dos_presentaciones(entorno, segundo_costo="1000")

    comando = entorno.generar_borrador(lista_id)

    assert comando.resultado is not None
    assert comando.resultado["precios_con_costos_distintos"] == 0
    assert _senales(entorno, lista_id)[entorno.vino_id].costos_distintos_por_presentacion is False


def test_la_senal_de_presentaciones_se_ve_al_regenerar_con_un_costo_nuevo(
    entorno: Entorno,
) -> None:
    """Al informar para Caja x6 el mismo costo por unidad, la diferencia desaparece."""
    lista_id, _caja_x12 = _vino_con_dos_presentaciones(entorno, segundo_costo="950")
    entorno.generar_borrador(lista_id)
    entorno.informar_costo(entorno.vino_id, "950", creado_en=MOMENTO + timedelta(minutes=2))

    comando = entorno.generar_borrador(lista_id)

    assert comando.resultado is not None
    assert comando.resultado["precios_con_costos_distintos"] == 0
    assert _senales(entorno, lista_id)[entorno.vino_id].costos_distintos_por_presentacion is False


def test_un_manual_sin_costo_no_tiene_senales_de_costo(entorno: Entorno) -> None:
    lista_id = _lista_markup_cercano(entorno)
    entorno.generar_borrador(lista_id)
    version_id = entorno.versiones(lista_id)[0].id
    entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")

    senales = _senales(entorno, lista_id)[entorno.vino_id]

    assert senales.sin_costo is True
    assert senales.costo_otra_regla_iva is False
    assert senales.costos_distintos_por_presentacion is False
    assert senales.presentacion_del_costo_id is None
