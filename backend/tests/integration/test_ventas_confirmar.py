"""Tarea 7.1 (change 18a; spec `ventas/confirmacion-de-venta`, requisito "Una venta se confirma
por comando con todos sus efectos o con ninguno"; `design.md` D2, D12, D17): `VENTA_CONFIRMAR` v1
por el bus en modo `ONLINE`, contra PostgreSQL real.

Se procesa por `sync_service.procesar_comando`, que maneja la transacción. El resto del grupo 7
tiene su archivo: totales y modo (7.2), precio (7.3), stock y costo (7.4), cobranza (7.5),
ubicación y jornada (7.6).

Reglas citadas: VTA-12, VTA-05, CC-05, INV-01, INV-06, INV-14, INV-21, VTA-10, SEG-06, SEG-07.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import PERMISOS_DE_VENTA, EntornoVenta

from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.core.errors import PermisoRequeridoError
from app.modules.cobranzas import service as cobranzas_service
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.stock import service as stock_service
from app.modules.ventas.domain.errores import (
    ModoImpositivoNoSoportadoError,
    RecursoNoEncontradoError,
    VentaDuplicadaError,
)
from app.modules.ventas.models import VentaLinea

MOMENTO_DESPUES = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session)


# --- el ejemplo de la spec: venta con cobranza parcial (VTA-12, VTA-05, CC-05, INV-14) ---------


def test_vta12_la_venta_con_cobranza_parcial_deja_todos_sus_efectos(entorno: EntornoVenta) -> None:
    """Escenario "Venta con cobranza parcial": 15 botellas a $12.500 la caja x6 con $20.000 en
    efectivo; saldo previo $150.000, 48 botellas a $1.050."""
    comando = entorno.vender(cobranza=entorno.cobranza())

    assert comando.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert venta.estado == "CONFIRMADA"
    assert (venta.total_neto, venta.total_iva, venta.total) == (
        Decimal("31250.00"),
        Decimal("0.00"),
        Decimal("31250.00"),
    )
    assert venta.modo_confirmacion == "ONLINE"
    assert entorno.stock() == 33
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert linea.cantidad_base == 15
    assert linea.importe_bruto == linea.importe_neto == Decimal("31250.00")
    assert linea.costo_unitario == Decimal("1050.000000")
    assert linea.costo_total == Decimal("15750.00")
    (debito,) = entorno.movimientos("VENTA")
    assert (debito.sentido, debito.importe, debito.origen_id) == (
        "AUMENTA",
        Decimal("31250.00"),
        venta.id,
    )
    (credito,) = entorno.movimientos("COBRANZA")
    assert (credito.sentido, credito.importe) == ("REDUCE", Decimal("20000.00"))
    assert entorno.saldo() == Decimal("161250.00")
    (cobranza,) = entorno.cobranzas()
    assert (cobranza.origen, cobranza.venta_id) == ("VENTA", venta.id)
    assert entorno.ultimo_correlativo() == 1


def test_vta12_otra_venta_sin_cobranza_solo_deja_el_debito(entorno: EntornoVenta) -> None:
    """Triangula: otra cantidad, otro costo y sin cobranza (VTA-11: es opcional)."""
    entorno.vender(entorno.linea(cantidad=7))

    (venta,) = entorno.ventas()
    assert venta.total == Decimal("14583.33")
    assert entorno.stock() == 41
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert linea.costo_total == Decimal("7350.00")
    assert [m.tipo for m in entorno.movimientos()] == ["SALDO_INICIAL", "VENTA"]
    assert entorno.cobranzas() == []
    assert entorno.saldo() == Decimal("164583.33")


def test_vta12_el_resultado_trae_la_venta_el_numero_y_el_saldo(entorno: EntornoVenta) -> None:
    contenido = entorno.contenido(cobranza=entorno.cobranza())

    comando = entorno.enviar(contenido)

    assert comando.resultado is not None
    assert comando.resultado["venta_id"] == contenido["venta_id"]
    assert comando.resultado["numero"] == contenido["numero"]
    assert comando.resultado["total"] == "31250.00"
    assert comando.resultado["saldo"] == "161250.00"


def test_vta12_la_venta_queda_auditada_por_el_bus(entorno: EntornoVenta) -> None:
    operation_id = uuid4()

    entorno.enviar(operation_id=operation_id)

    assert entorno.auditorias(operation_id) == 1


# --- doble envío e identificador repetido (INV-06, SYN-02) --------------------------------------


def test_inv06_el_doble_envio_devuelve_el_resultado_original_sin_duplicar(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Doble envío"."""
    operation_id = uuid4()
    contenido = entorno.contenido(cobranza=entorno.cobranza())
    primero = entorno.enviar(contenido, operation_id=operation_id)

    segundo = entorno.enviar(contenido, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(entorno.ventas()) == 1
    assert len(entorno.movimientos_de_stock()) == 1
    assert len(entorno.movimientos("VENTA")) == 1
    assert len(entorno.cobranzas()) == 1
    assert entorno.stock() == 33


def test_inv06_el_mismo_operation_id_con_otra_cantidad_se_rechaza_como_inconsistente(
    entorno: EntornoVenta,
) -> None:
    operation_id = uuid4()
    venta_id = str(uuid4())
    entorno.enviar(entorno.contenido(venta_id=venta_id), operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(
            entorno.contenido(entorno.linea(cantidad=3), venta_id=venta_id),
            operation_id=operation_id,
        )

    entorno.sesion.rollback()
    assert len(entorno.ventas()) == 1
    assert entorno.stock() == 33


def test_vta12_un_identificador_de_venta_repetido_se_rechaza_y_la_original_no_cambia(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Identificador de venta repetido": otro `operation_id`, la misma venta."""
    venta_id = str(uuid4())
    entorno.enviar(entorno.contenido(venta_id=venta_id))
    entorno.sesion.commit()

    with pytest.raises(VentaDuplicadaError) as error:
        entorno.enviar(entorno.contenido(entorno.linea(cantidad=3), venta_id=venta_id))

    assert error.value.codigo == "VENTA_DUPLICADA"
    assert error.value.status_http == 409
    entorno.sesion.rollback()
    (venta,) = entorno.ventas()
    assert venta.total == Decimal("31250.00")
    assert entorno.stock() == 33


# --- permiso y organización (VTA-10, SEG-06, INV-21, SEG-07) ------------------------------------


def test_seg06_sin_el_permiso_vender_responde_403_sin_efectos(db_session: Session) -> None:
    """Escenario "Sin permiso"."""
    entorno = EntornoVenta(db_session, permisos=frozenset({"REGISTRAR_COBRANZA"}))

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.vender()

    assert error.value.status_http == 403
    entorno.sin_efectos_de_venta()


def test_seg06_el_permiso_vender_alcanza(db_session: Session) -> None:
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_VENTA)

    assert entorno.vender().estado == "ACEPTADO"


def test_inv21_el_contenido_no_elige_la_organizacion(entorno: EntornoVenta) -> None:
    """Escenario "Organización tomada del token": `organizacion_id` no es un campo."""
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.vender(organizacion_id=str(uuid4()))

    entorno.sin_efectos_de_venta()


def test_inv21_un_cliente_de_otra_organizacion_responde_404_sin_efectos(
    entorno: EntornoVenta, db_session: Session
) -> None:
    otra = EntornoVenta(db_session)

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.vender(cliente_id=str(otra.cliente_id))

    assert error.value.status_http == 404
    entorno.sin_efectos_de_venta()


def test_inv21_un_cliente_inexistente_responde_404(entorno: EntornoVenta) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        entorno.vender(cliente_id=str(uuid4()))

    entorno.sin_efectos_de_venta()


# --- una falla después de cada efecto no deja nada (INV-01, VTA-12) -----------------------------


def _fallar_despues_de(
    monkeypatch: pytest.MonkeyPatch, modulo: object, nombre: str, mensaje: str
) -> None:
    """Reemplaza `modulo.nombre` por un envoltorio que ejecuta el original y después falla: el
    efecto ya quedó escrito en la transacción, y debe revertirse."""
    original = getattr(modulo, nombre)

    def _con_falla(*args: object, **kwargs: object) -> object:
        original(*args, **kwargs)
        raise RuntimeError(mensaje)

    monkeypatch.setattr(modulo, nombre, _con_falla)


def test_inv01_una_falla_despues_del_movimiento_de_stock_no_deja_nada(
    entorno: EntornoVenta, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fallar_despues_de(monkeypatch, stock_service, "registrar_movimientos", "después del stock")

    with pytest.raises(RuntimeError, match="después del stock"):
        entorno.vender(cobranza=entorno.cobranza())

    entorno.sin_efectos_de_venta()
    assert entorno.costo().stock_total == 48


def test_inv01_una_falla_despues_del_debito_no_deja_nada(
    entorno: EntornoVenta, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = cuentas_service.registrar_movimiento

    def _falla_tras_el_debito(*args: object, **kwargs: object) -> object:
        resultado = original(*args, **kwargs)  # type: ignore[arg-type]
        if kwargs.get("tipo") == "VENTA":
            raise RuntimeError("después del débito")
        return resultado

    monkeypatch.setattr(cuentas_service, "registrar_movimiento", _falla_tras_el_debito)

    with pytest.raises(RuntimeError, match="después del débito"):
        entorno.vender(cobranza=entorno.cobranza())

    entorno.sin_efectos_de_venta()


def test_inv01_una_falla_despues_de_la_cobranza_no_deja_nada(
    entorno: EntornoVenta, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fallar_despues_de(
        monkeypatch, cobranzas_service, "registrar_cobranza", "después de la cobranza"
    )

    with pytest.raises(RuntimeError, match="después de la cobranza"):
        entorno.vender(cobranza=entorno.cobranza())

    entorno.sin_efectos_de_venta()


def test_inv01_una_falla_despues_de_actualizar_el_correlativo_no_deja_nada(
    entorno: EntornoVenta, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El nivel 6 (dispositivo) es lo último de la transacción (D17): si el bus falla después, el
    correlativo vuelve atrás junto con todo lo demás."""
    from app.modules.identidad import service as identidad_service

    _fallar_despues_de(
        monkeypatch, identidad_service, "registrar_correlativo_maximo", "después del correlativo"
    )

    with pytest.raises(RuntimeError, match="después del correlativo"):
        entorno.vender(cobranza=entorno.cobranza())

    entorno.sin_efectos_de_venta()


def test_inv01_un_rechazo_deja_el_numero_libre_y_se_puede_reintentar(
    entorno: EntornoVenta, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El mismo contenido, rechazado a mitad, se acepta al reintentarlo sin la falla."""
    contenido = entorno.contenido(cobranza=entorno.cobranza())
    with monkeypatch.context() as parche:
        _fallar_despues_de(parche, cobranzas_service, "registrar_cobranza", "falla")
        with pytest.raises(RuntimeError):
            entorno.enviar(contenido)
    entorno.sesion.rollback()

    reintento = entorno.enviar(contenido)

    assert reintento.estado == "ACEPTADO"
    assert len(entorno.ventas()) == 1
    assert entorno.ultimo_correlativo() == 1


# --- cajas y unidades: dos líneas del mismo producto (VTA-02, CAT-07, CAT-08) -------------------


def test_vta02_cajas_y_unidades_son_dos_lineas_con_su_cantidad_base(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Cajas y unidades son dos líneas": 2 "Caja x6" y 3 "Botella" de Vino A =
    12 y 3 unidades base (15 en total); brutos $25.000,00 y $6.250,00; un egreso por línea."""
    entorno.vender(
        entorno.linea(presentacion_id=entorno.caja_id, cantidad=2, unidades_presentacion=6),
        entorno.linea(cantidad=3),
    )

    (venta,) = entorno.ventas()
    caja, botella = entorno.lineas_de_venta(venta.id)
    assert (caja.orden, caja.unidades_presentacion, caja.cantidad, caja.cantidad_base) == (
        0,
        6,
        2,
        12,
    )
    assert (botella.orden, botella.cantidad, botella.cantidad_base) == (1, 3, 3)
    assert (caja.importe_bruto, botella.importe_bruto) == (Decimal("25000.00"), Decimal("6250.00"))
    assert venta.total == Decimal("31250.00")
    assert len(entorno.movimientos_de_stock()) == 2
    assert entorno.stock() == 33
    assert (caja.costo_total, botella.costo_total) == (Decimal("12600.00"), Decimal("3150.00"))


def test_vta02_una_venta_de_dos_productos_congela_el_precio_y_el_costo_de_cada_uno(
    entorno: EntornoVenta,
) -> None:
    """Triangula con otro producto, otro precio y otro costo (Cerveza B, caja x12)."""
    cerveza_id, caja_cerveza_id = entorno.crear_producto("Cerveza B", unidades_caja=12)
    entorno.poner_precio(entorno.version_id, cerveza_id, "9000.00", 12)
    entorno.comprar(cerveza_id, 120, "600")

    entorno.vender(
        entorno.linea(),
        entorno.linea(
            cerveza_id,
            caja_cerveza_id,
            2,
            unidades_presentacion=12,
            precio="9000.00",
            unidades_referencia=12,
        ),
    )

    (venta,) = entorno.ventas()
    vino, cerveza = entorno.lineas_de_venta(venta.id)
    assert (cerveza.precio_referencia, cerveza.unidades_referencia) == (
        Decimal("9000.00"),
        12,
    )
    assert cerveza.importe_bruto == Decimal("18000.00")
    assert (cerveza.costo_unitario, cerveza.costo_total) == (
        Decimal("600.000000"),
        Decimal("14400.00"),
    )
    assert vino.costo_total == Decimal("15750.00")
    assert venta.total == Decimal("49250.00")
    assert entorno.stock(cerveza_id) == 96


# --- 7.2: totales, modo impositivo y estado de facturación (INV-14, VTA-04, VTA-08) ------------


def test_inv14_el_total_es_la_suma_de_netos_mas_la_suma_de_iva(entorno: EntornoVenta) -> None:
    """Escenario "Totales de cabecera y líneas": dos líneas con brutos $25.000,00 y $6.250,00."""
    entorno.vender(
        entorno.linea(presentacion_id=entorno.caja_id, cantidad=2, unidades_presentacion=6),
        entorno.linea(cantidad=3),
    )

    (venta,) = entorno.ventas()
    suma_netos, suma_iva = entorno.sesion.execute(
        select(func.sum(VentaLinea.importe_neto), func.sum(VentaLinea.importe_iva)).where(
            VentaLinea.organizacion_id == entorno.org, VentaLinea.venta_id == venta.id
        )
    ).one()
    assert (venta.total_neto, venta.total_iva, venta.total) == (
        Decimal("31250.00"),
        Decimal("0.00"),
        Decimal("31250.00"),
    )
    assert (suma_netos, suma_iva) == (venta.total_neto, venta.total_iva)
    assert venta.total == suma_netos + suma_iva


def test_inv14_una_unidad_suelta_redondea_una_sola_vez_el_bruto(entorno: EntornoVenta) -> None:
    # Escenario: "Una unidad suelta"
    """Triangula con el caso de $8.600 la caja x6: 1 botella = `1433.33` (TR-03)."""
    version_2 = entorno.crear_version(entorno.lista_id, 2, MOMENTO_DESPUES, precio_vino="8600.00")

    entorno.vender(entorno.linea(cantidad=1, precio="8600.00", version_id=version_2))

    (venta,) = entorno.ventas()
    assert venta.total == Decimal("1433.33")


def test_vta04_una_organizacion_monotributista_congela_modo_a_y_la_alicuota_con_iva_cero(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Organización monotributista": modalidad de IVA nula y Vino A al 21 %."""
    entorno.vender()

    (venta,) = entorno.ventas()
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert venta.modo_impositivo == "A"
    assert (linea.alicuota, linea.importe_iva) == (Decimal("0.210000"), Decimal("0.00"))


@pytest.mark.parametrize("modo", ["B", "C"])
def test_vta04_los_modos_b_y_c_se_rechazan_sin_efectos(db_session: Session, modo: str) -> None:
    """Escenario "Modo B" (y C): son de la etapa 4."""
    entorno = EntornoVenta(db_session, condicion_iva="RESPONSABLE_INSCRIPTO", modo_impositivo=modo)

    with pytest.raises(ModoImpositivoNoSoportadoError) as error:
        entorno.vender()

    assert (error.value.codigo, error.value.status_http) == ("MODO_IMPOSITIVO_NO_SOPORTADO", 409)
    entorno.sin_efectos_de_venta()


def test_vta08_la_venta_nace_con_el_estado_de_facturacion_del_cliente_o_el_de_la_organizacion(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Estado del cliente y de la organización": organización `NO_REQUIERE`, Kiosco
    La Esquina `PENDIENTE` y Almacén Don Pedro sin estado propio."""
    entorno.configurar(estado_facturacion_default="NO_REQUIERE")
    entorno.actualizar_cliente(entorno.cliente_id, estado_facturacion_default="PENDIENTE")
    don_pedro = entorno.crear_cliente(nombre="Almacén Don Pedro")

    entorno.vender()
    entorno.vender(cliente_id=str(don_pedro))

    primera, segunda = entorno.ventas()
    assert (primera.estado_facturacion, primera.importe_facturado) == ("PENDIENTE", Decimal("0.00"))
    assert (segunda.estado_facturacion, segunda.importe_facturado) == (
        "NO_REQUIERE",
        Decimal("0.00"),
    )
