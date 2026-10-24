"""Tarea 9.1 (change 18b; `design.md` D4, D18; specs `ventas/descuentos-en-la-venta` y
`ventas/credito-en-la-venta`; borrador del orden aprobado por el usuario el 2026-10-23): las
autorizaciones de descuento y de crédito con PIN y el orden de la transacción de
`confirmar_venta`, contra PostgreSQL real.

Orden de D18 A: contenido -> cliente -> precio -> descuento -> tope y motivo -> crédito -> PIN ->
stock -> número. Un rechazo no deja nada (INV-01), salvo el contador del intento fallido de PIN,
que se escribe en una transacción aparte (D3).

Reglas citadas: DSC-06, CRE-05, SEG-04, SEG-05, INV-01.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import EntornoVenta

from app.core.db import crear_engine, crear_session_factory
from app.core.errors import DomainError
from app.modules.identidad import service as identidad_service
from app.modules.identidad.models import Auditoria
from app.modules.ventas import repository as ventas_repository

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PIN = "482913"
PIN_MALO = "937104"
SUMA_DEL_EJEMPLO = "28750.00"  # 31250.00 con un general de 8 %


def _preparar(e: EntornoVenta) -> EntornoVenta:
    e.configurar(descuento_manual_habilitado=True)
    e.permitir("DESCUENTO_MANUAL")
    e.fijar_tope("0.05")
    return e


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return _preparar(EntornoVenta(db_session))


@pytest.fixture
def entorno_real(database_url: str, _engine_de_sesion) -> Iterator[EntornoVenta]:  # type: ignore[no-untyped-def]
    """Con commits reales: el intento fallido de PIN se escribe en una transacción aparte (D3), que
    no ve los datos de una transacción de prueba sin confirmar."""
    engine = crear_engine(database_url)
    try:
        with crear_session_factory(engine)() as sesion:
            yield _preparar(EntornoVenta(sesion))
    finally:
        with engine.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
        engine.dispose()


class Llamadas:
    """Cuenta las veces que se verifica un PIN (el éxito no escribe nada, así que sin esto no se
    podría saber)."""

    def __init__(self) -> None:
        self.autorizadores: list[UUID] = []


@pytest.fixture
def verificaciones(monkeypatch: pytest.MonkeyPatch) -> Llamadas:
    llamadas = Llamadas()
    original = identidad_service.verificar_pin_de_autorizacion

    def _espia(*args: Any, **kwargs: Any) -> Any:
        llamadas.autorizadores.append(kwargs["autorizador_id"])
        return original(*args, **kwargs)

    monkeypatch.setattr(identidad_service, "verificar_pin_de_autorizacion", _espia)
    return llamadas


def _venta(
    entorno: EntornoVenta,
    *,
    general: str = "0.08",
    importe: str = "2500.00",
    total: str = SUMA_DEL_EJEMPLO,
    descuento_autorizador: UUID | None = None,
    credito: dict[str, Any] | None = None,
    **cambios: Any,
) -> dict[str, Any]:
    """15 botellas ($31.250) con un general; por defecto 8 %, sobre el tope de 5 %."""
    extras: dict[str, Any] = dict(cambios)
    if descuento_autorizador is not None:
        extras["descuento_autorizador_id"] = str(descuento_autorizador)
    if credito is not None:
        extras["credito"] = credito
    return entorno.contenido(
        entorno.linea(
            descuentos=[
                {
                    "origen": "MANUAL",
                    "regla_id": None,
                    "porcentaje": f"{Decimal(general):.6f}",
                    "importe": importe,
                }
            ]
        ),
        total=total,
        descuento_manual_general=general,
        **extras,
    )


def _rechazo(entorno: EntornoVenta, contenido: dict[str, Any], *credenciales: Any) -> DomainError:
    with pytest.raises(DomainError) as error:
        entorno.enviar(contenido, credenciales=tuple(credenciales))
    return error.value


# --- una credencial por persona (D4) -----------------------------------------------------------


def test_sec05_el_pin_de_un_supervisor_autoriza_el_descuento_sobre_el_tope(
    entorno: EntornoVenta, verificaciones: Llamadas
) -> None:
    marta = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)

    entorno.enviar(
        _venta(entorno, descuento_autorizador=marta),
        credenciales=(entorno.credencial(marta, PIN),),
    )

    (descuento,) = entorno.descuentos_de_venta()
    assert descuento.autorizador_id == marta
    assert verificaciones.autorizadores == [marta]


def test_d4_la_misma_persona_autoriza_descuento_y_credito_con_una_sola_credencial(
    entorno: EntornoVenta, verificaciones: Llamadas
) -> None:
    marta = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO"}), pin=PIN)
    entorno.datos_de_credito(limite="160000.00", politica="AUTORIZAR")

    entorno.enviar(
        _venta(entorno, descuento_autorizador=marta, credito={"autorizador_id": str(marta)}),
        credenciales=(entorno.credencial(marta, PIN),),
    )

    (venta,) = entorno.ventas()
    assert (venta.credito_resolucion, venta.credito_autorizador_id) == ("PIN_SUPERVISOR", marta)
    (descuento,) = entorno.descuentos_de_venta()
    assert descuento.autorizador_id == marta
    assert verificaciones.autorizadores == [marta]  # verificada una vez, vale para las dos


def test_d4_dos_autorizadores_distintos_se_verifican_cada_uno_con_su_credencial(
    entorno: EntornoVenta, verificaciones: Llamadas
) -> None:
    marta = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)
    julia = entorno.crear_usuario(frozenset({"SUPERAR_CREDITO"}), pin="115599")
    entorno.datos_de_credito(limite="160000.00", politica="AUTORIZAR")

    entorno.enviar(
        _venta(entorno, descuento_autorizador=marta, credito={"autorizador_id": str(julia)}),
        credenciales=(entorno.credencial(marta, PIN), entorno.credencial(julia, "115599")),
    )

    (venta,) = entorno.ventas()
    assert venta.credito_autorizador_id == julia
    (descuento,) = entorno.descuentos_de_venta()
    assert descuento.autorizador_id == marta
    assert verificaciones.autorizadores == [marta, julia]


def test_d2_el_pin_solo_se_verifica_si_hace_falta(
    entorno: EntornoVenta, verificaciones: Llamadas
) -> None:
    """Dentro del tope no se necesita autorizador: una credencial enviada de más se ignora."""
    marta = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)

    entorno.enviar(
        _venta(entorno, general="0.05", importe="1562.50", total="29687.50"),
        credenciales=(entorno.credencial(marta, PIN_MALO),),
    )

    assert verificaciones.autorizadores == []
    assert entorno.intentos_de_pin() == 0


def test_d2_con_permiso_propio_no_se_verifica_el_pin_indicado(
    entorno: EntornoVenta, verificaciones: Llamadas
) -> None:
    entorno.permitir("AUTORIZAR_DESCUENTO")
    marta = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)

    entorno.enviar(
        _venta(entorno, descuento_autorizador=marta),
        credenciales=(entorno.credencial(marta, PIN_MALO),),
    )

    assert verificaciones.autorizadores == []
    assert entorno.intentos_de_pin() == 0


def test_d2_un_autorizador_nombrado_sin_credencial_es_una_autorizacion_requerida(
    entorno: EntornoVenta, verificaciones: Llamadas
) -> None:
    marta = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)

    error = _rechazo(entorno, _venta(entorno, descuento_autorizador=marta))

    assert error.codigo == "AUTORIZACION_REQUERIDA"
    assert verificaciones.autorizadores == []
    entorno.sin_efectos_de_venta()


def test_d2_el_credito_nombrado_sin_credencial_es_una_autorizacion_de_credito_requerida(
    entorno: EntornoVenta,
) -> None:
    julia = entorno.crear_usuario(frozenset({"SUPERAR_CREDITO"}), pin=PIN)
    entorno.datos_de_credito(limite="160000.00", politica="AUTORIZAR")
    contenido = entorno.contenido(credito={"autorizador_id": str(julia)})

    error = _rechazo(entorno, contenido)

    assert error.codigo == "AUTORIZACION_CREDITO_REQUERIDA"
    entorno.sin_efectos_de_venta()


# --- PIN_INCORRECTO y PIN_BLOQUEADO no dejan nada, salvo el contador (INV-01, D3) ----------------


def _auditorias_de_la_venta(entorno: EntornoVenta) -> int:
    entorno.sesion.rollback()
    return int(
        entorno.sesion.scalar(
            select(func.count())
            .select_from(Auditoria)
            .where(Auditoria.organizacion_id == entorno.org, Auditoria.accion == "VENTA_CONFIRMAR")
        )
        or 0
    )


def test_seg04_un_pin_incorrecto_rechaza_y_deja_solo_el_intento_fallido(
    entorno_real: EntornoVenta,
) -> None:
    marta = entorno_real.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)

    error = _rechazo(
        entorno_real,
        _venta(entorno_real, descuento_autorizador=marta),
        entorno_real.credencial(marta, PIN_MALO),
    )

    assert (error.codigo, error.status_http) == ("PIN_INCORRECTO", 403)
    assert entorno_real.intentos_de_pin() == 1
    entorno_real.sin_efectos_de_venta()
    assert entorno_real.descuentos_de_venta() == []
    assert entorno_real.cantidad_de_comandos() == 0
    assert _auditorias_de_la_venta(entorno_real) == 0


def test_seg04_con_el_limite_de_intentos_el_siguiente_es_pin_bloqueado_sin_verificar(
    entorno_real: EntornoVenta, verificaciones: Llamadas
) -> None:
    entorno_real.sesion.execute(text("UPDATE configuracion_organizacion SET intentos_pin_max = 2"))
    entorno_real.sesion.commit()
    marta = entorno_real.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)
    contenido = _venta(entorno_real, descuento_autorizador=marta)
    for _ in range(2):
        assert (
            _rechazo(entorno_real, contenido, entorno_real.credencial(marta, PIN_MALO)).codigo
            == "PIN_INCORRECTO"
        )

    error = _rechazo(entorno_real, contenido, entorno_real.credencial(marta, PIN))

    assert (error.codigo, error.status_http) == ("PIN_BLOQUEADO", 429)
    assert entorno_real.intentos_de_pin() == 2  # el rechazo por bloqueo no cuenta ni escribe
    entorno_real.sin_efectos_de_venta()


# --- precedencia: contenido -> cliente -> precio -> descuento -> tope y motivo -> crédito ->
# --- PIN -> stock -> número (D18) --------------------------------------------------------------


def test_d18_un_descuento_distinto_se_informa_antes_que_un_pin_incorrecto(
    entorno: EntornoVenta, verificaciones: Llamadas
) -> None:
    marta = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)
    entorno.crear_regla(umbral="1")  # aplica a la venta, pero el usuario no la vio

    error = _rechazo(
        entorno,
        _venta(entorno, descuento_autorizador=marta),
        entorno.credencial(marta, PIN_MALO),
    )

    assert error.codigo == "DESCUENTO_DIFIERE"
    assert verificaciones.autorizadores == []
    assert entorno.intentos_de_pin() == 0


def test_d18_el_tope_se_informa_antes_que_el_credito(entorno: EntornoVenta) -> None:
    entorno.datos_de_credito(limite="100000.00", politica="BLOQUEAR")

    error = _rechazo(entorno, _venta(entorno, total=SUMA_DEL_EJEMPLO))

    assert error.codigo == "AUTORIZACION_REQUERIDA"  # el descuento sobre el tope, no el crédito


def test_d18_el_credito_se_informa_antes_que_un_pin_incorrecto(
    entorno: EntornoVenta, verificaciones: Llamadas
) -> None:
    marta = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)
    entorno.datos_de_credito(limite="100000.00", politica="BLOQUEAR")
    entorno.sesion.commit()
    contenido = _venta(entorno, descuento_autorizador=marta)

    error = _rechazo(entorno, contenido, entorno.credencial(marta, PIN_MALO))

    assert error.codigo == "CREDITO_EXCEDIDO"
    assert verificaciones.autorizadores == []
    assert entorno.intentos_de_pin() == 0


def test_d18_el_pin_se_verifica_antes_que_el_stock(entorno_real: EntornoVenta) -> None:
    """Sin stock suficiente y con un PIN incorrecto, se informa el PIN."""
    marta = entorno_real.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)
    contenido = _venta(entorno_real, descuento_autorizador=marta)
    contenido["lineas"][0].update(cantidad=5000, importe_bruto="10416666.67")
    contenido["total"] = "9583333.34"
    contenido["lineas"][0]["descuentos"][0]["importe"] = "833333.33"
    contenido["lineas"][0]["descuentos"][0]["porcentaje"] = "0.080000"

    error = _rechazo(entorno_real, contenido, entorno_real.credencial(marta, PIN_MALO))

    assert error.codigo == "PIN_INCORRECTO"


def test_d18_el_credito_se_informa_antes_que_el_stock(entorno: EntornoVenta) -> None:
    entorno.datos_de_credito(limite="100000.00", politica="BLOQUEAR")
    contenido = entorno.contenido(entorno.linea(cantidad=5000))

    error = _rechazo(entorno, contenido)

    assert error.codigo == "CREDITO_EXCEDIDO"


# --- INV-01: una falla después de cada efecto nuevo no deja nada ---------------------------------


def _fallar_despues_de(
    monkeypatch: pytest.MonkeyPatch, modulo: object, nombre: str, mensaje: str
) -> None:
    original: Callable[..., object] = getattr(modulo, nombre)

    def _con_falla(*args: object, **kwargs: object) -> object:
        original(*args, **kwargs)
        raise RuntimeError(mensaje)

    monkeypatch.setattr(modulo, nombre, _con_falla)


def test_inv01_una_falla_despues_de_guardar_los_descuentos_no_deja_nada(
    entorno: EntornoVenta, monkeypatch: pytest.MonkeyPatch
) -> None:
    marta = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)
    _fallar_despues_de(
        monkeypatch, ventas_repository, "insertar_descuentos", "después de los descuentos"
    )

    with pytest.raises(RuntimeError, match="después de los descuentos"):
        entorno.enviar(
            _venta(entorno, descuento_autorizador=marta),
            credenciales=(entorno.credencial(marta, PIN),),
        )

    entorno.sin_efectos_de_venta()
    assert entorno.descuentos_de_venta() == []


def test_inv01_una_falla_despues_de_guardar_la_venta_con_su_snapshot_no_deja_nada(
    entorno: EntornoVenta, monkeypatch: pytest.MonkeyPatch
) -> None:
    entorno.datos_de_credito(limite="200000.00", politica="ADVERTIR")
    _fallar_despues_de(monkeypatch, ventas_repository, "insertar_venta", "después de la venta")

    with pytest.raises(RuntimeError, match="después de la venta"):
        entorno.enviar(entorno.contenido(credito={"acepta_exceso": True}))

    entorno.sin_efectos_de_venta()
    assert entorno.descuentos_de_venta() == []
