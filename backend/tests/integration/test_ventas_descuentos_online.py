"""Tarea 7.3 (change 18b; spec `ventas/descuentos-en-la-venta`; `design.md` D1, D11, D18):
`VENTA_CONFIRMAR` v1 con conexión aplica las reglas de descuento vigentes al `occurred_at`, compara
con los descuentos que vio el usuario (`DESCUENTO_DIFIERE`), evalúa el descuento manual una vez
(DSC-06) y guarda una fila de `venta_linea_descuento` por descuento informado, contra PostgreSQL
real. La verificación del PIN y la precedencia general están en `test_ventas_autorizaciones.py`.

Regla del ejemplo: "cajas equivalentes >= 20 -> 5 %". 120 botellas de Vino A (20 cajas x6) a
$12.500 la caja valen `250000.00` de bruto y el 5 % es `12500.00`.

Reglas citadas: DSC-03, DSC-05, DSC-06, DSC-07, DSC-08, DSC-09, INV-01, INV-06, INV-14, INV-21.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import MOMENTO_VENTA, EntornoVenta

from app.core.errors import DomainError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PIN = "482913"


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    entorno = EntornoVenta(db_session, stock_inicial=500)
    entorno.configurar(descuento_manual_habilitado=True)
    entorno.sesion.commit()
    return entorno


def _automatico(regla: UUID, importe: str = "12500.00") -> dict[str, Any]:
    return {
        "origen": "AUTOMATICO",
        "regla_id": str(regla),
        "porcentaje": "0.050000",
        "importe": importe,
    }


def _manual(porcentaje: str, importe: str) -> dict[str, Any]:
    return {"origen": "MANUAL", "regla_id": None, "porcentaje": porcentaje, "importe": importe}


def _rechazo(entorno: EntornoVenta, contenido: dict[str, Any], **kwargs: Any) -> DomainError:
    with pytest.raises(DomainError) as error:
        entorno.enviar(contenido, **kwargs)
    return error.value


def _venta_de_volumen(entorno: EntornoVenta, regla: UUID | None, **cambios: Any) -> dict[str, Any]:
    """120 botellas (20 cajas); con la regla vista por el usuario, con su descuento esperado."""
    descuentos = [] if regla is None else [_automatico(regla)]
    total = "250000.00" if regla is None else "237500.00"
    return entorno.contenido(
        entorno.linea(cantidad=120, descuentos=descuentos), total=total, **cambios
    )


# --- las reglas vigentes al momento de la venta (DSC-03, DSC-05, DSC-07, INV-14) ----------------


def test_dsc05_la_regla_de_volumen_deja_un_descuento_automatico_en_la_linea(
    entorno: EntornoVenta,
) -> None:
    regla = entorno.crear_regla()

    comando = entorno.enviar(_venta_de_volumen(entorno, regla))

    assert comando.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert venta.total == Decimal("237500.00")
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert (linea.importe_bruto, linea.importe_descuento, linea.importe_neto) == (
        Decimal("250000.00"),
        Decimal("12500.00"),
        Decimal("237500.00"),
    )
    (descuento,) = entorno.descuentos_de_venta()
    assert descuento.venta_linea_id == linea.id
    assert (descuento.orden, descuento.origen, descuento.regla_id) == (0, "AUTOMATICO", regla)
    assert (descuento.porcentaje, descuento.importe) == (Decimal("0.050000"), Decimal("12500.00"))
    assert (descuento.motivo_id, descuento.autorizador_id) == (None, None)
    (debito,) = entorno.movimientos("VENTA")
    assert debito.importe == Decimal("237500.00")


def test_dsc03_diecinueve_cajas_y_cinco_unidades_no_alcanzan_la_regla(
    entorno: EntornoVenta,
) -> None:
    """119 botellas son 19,83 cajas equivalentes: la regla no aplica y no se guarda descuento."""
    entorno.crear_regla()

    entorno.vender(entorno.linea(cantidad=119))

    (venta,) = entorno.ventas()
    assert venta.total == Decimal("247916.67")
    assert entorno.descuentos_de_venta() == []


@pytest.mark.parametrize(
    "caso",
    ["pausada", "vencida", "programada", "borrador"],
)
def test_dsc01_una_regla_que_no_esta_vigente_no_se_aplica(entorno: EntornoVenta, caso: str) -> None:
    desde = hasta = None
    estado = "ACTIVA"
    if caso == "pausada":
        estado = "PAUSADA"
    elif caso == "vencida":
        desde, hasta = MOMENTO_VENTA - timedelta(days=10), MOMENTO_VENTA - timedelta(days=1)
    elif caso == "programada":
        desde = MOMENTO_VENTA + timedelta(days=1)
    else:
        estado = "BORRADOR"
    entorno.crear_regla(estado=estado, desde=desde, hasta=hasta)

    entorno.enviar(_venta_de_volumen(entorno, None))

    (venta,) = entorno.ventas()
    assert venta.total == Decimal("250000.00")
    assert entorno.descuentos_de_venta() == []


def test_dsc01_una_regla_pausada_despues_de_armar_la_venta_hace_que_difiera(
    entorno: EntornoVenta,
) -> None:
    """Triangula: el usuario vio la regla, la pausaron antes de confirmar."""
    regla = entorno.crear_regla()
    contenido = _venta_de_volumen(entorno, regla)
    entorno.pausar_regla(regla)

    assert _rechazo(entorno, contenido).codigo == "DESCUENTO_DIFIERE"
    entorno.sin_efectos_de_venta(stock_esperado=500)


# --- DESCUENTO_DIFIERE (DSC-09, INV-01) ------------------------------------------------------


def test_dsc09_una_regla_activada_despues_de_armar_la_venta_difiere_y_trae_la_del_servidor(
    entorno: EntornoVenta,
) -> None:
    regla = entorno.crear_regla()

    error = _rechazo(entorno, _venta_de_volumen(entorno, None))

    assert (error.codigo, error.status_http) == ("DESCUENTO_DIFIERE", 409)
    (linea,) = error.extension["lineas"]  # type: ignore[index]
    assert linea["descuentos"] == [_automatico(regla)]
    entorno.sin_efectos_de_venta(stock_esperado=500)
    assert entorno.descuentos_de_venta() == []


def test_dsc09_un_centavo_de_diferencia_en_el_importe_difiere(entorno: EntornoVenta) -> None:
    regla = entorno.crear_regla()
    contenido = entorno.contenido(
        entorno.linea(cantidad=120, descuentos=[_automatico(regla, "12499.99")]),
        total="237500.00",
    )

    assert _rechazo(entorno, contenido).codigo == "DESCUENTO_DIFIERE"
    entorno.sin_efectos_de_venta(stock_esperado=500)


def test_dsc09_el_precio_distinto_se_informa_antes_que_el_descuento(entorno: EntornoVenta) -> None:
    """Precedencia: precio -> descuento. Con el precio mal y el descuento ausente se informa el
    precio."""
    entorno.crear_regla()
    contenido = entorno.contenido(
        entorno.linea(cantidad=120, precio="12000.00", bruto="240000.00"), total="240000.00"
    )

    assert _rechazo(entorno, contenido).codigo == "PRECIO_DIFIERE"


def test_dsc09_con_descuentos_iguales_un_total_distinto_sigue_siendo_precio_difiere(
    entorno: EntornoVenta,
) -> None:
    regla = entorno.crear_regla()
    contenido = entorno.contenido(
        entorno.linea(cantidad=120, descuentos=[_automatico(regla)]), total="250000.00"
    )

    assert _rechazo(entorno, contenido).codigo == "PRECIO_DIFIERE"


def test_inv06_el_doble_envio_devuelve_lo_mismo_sin_duplicar_descuentos(
    entorno: EntornoVenta,
) -> None:
    regla = entorno.crear_regla()
    contenido = _venta_de_volumen(entorno, regla)
    operation_id = uuid4()

    primero = entorno.enviar(contenido, operation_id=operation_id)
    segundo = entorno.enviar(contenido, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.ventas()) == 1
    assert len(entorno.descuentos_de_venta()) == 1


# --- el descuento manual se evalúa una vez (DSC-05, DSC-06, DSC-08) ----------------------------


def _venta_con_general(
    entorno: EntornoVenta, general: str, importe: str, neto: str, **cambios: Any
) -> dict[str, Any]:
    return entorno.contenido(
        entorno.linea(descuentos=[_manual(f"{Decimal(general):.6f}", importe)]),
        total=neto,
        descuento_manual_general=general,
        **cambios,
    )


def test_dsc06_dentro_del_tope_se_acepta_sin_autorizacion(entorno: EntornoVenta) -> None:
    entorno.permitir("DESCUENTO_MANUAL")
    entorno.fijar_tope("0.05")

    entorno.enviar(_venta_con_general(entorno, "0.05", "1562.50", "29687.50"))

    (venta,) = entorno.ventas()
    assert venta.total == Decimal("29687.50")
    (descuento,) = entorno.descuentos_de_venta()
    assert (descuento.origen, descuento.regla_id) == ("MANUAL", None)
    assert (descuento.porcentaje, descuento.importe) == (Decimal("0.050000"), Decimal("1562.50"))
    assert descuento.autorizador_id is None


def test_dsc06_sobre_el_tope_sin_autorizacion_se_rechaza_y_no_deja_nada(
    entorno: EntornoVenta,
) -> None:
    entorno.permitir("DESCUENTO_MANUAL")
    entorno.fijar_tope("0.05")

    error = _rechazo(entorno, _venta_con_general(entorno, "0.08", "2500.00", "28750.00"))

    assert (error.codigo, error.status_http) == ("AUTORIZACION_REQUERIDA", 403)
    entorno.sin_efectos_de_venta(stock_esperado=500)
    assert entorno.descuentos_de_venta() == []


def test_dsc06_el_permiso_propio_se_resuelve_primero_y_no_verifica_ningun_pin(
    entorno: EntornoVenta,
) -> None:
    """Un supervisor con `AUTORIZAR_DESCUENTO` vende con 30 % e indica a otro autorizador: se
    acepta por permiso propio, no se verifica el PIN del indicado y el descuento queda
    autorizado por el propio vendedor."""
    entorno.permitir("DESCUENTO_MANUAL", "AUTORIZAR_DESCUENTO")
    otro = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)

    entorno.enviar(
        _venta_con_general(
            entorno, "0.30", "9375.00", "21875.00", descuento_autorizador_id=str(otro)
        ),
        credenciales=(entorno.credencial(otro, "000000"),),
    )

    (descuento,) = entorno.descuentos_de_venta()
    assert descuento.autorizador_id == entorno.usuario_id
    assert entorno.intentos_de_pin() == 0


def test_dsc06_un_general_reemplazado_en_la_linea_no_cuenta_para_el_tope(
    entorno: EntornoVenta,
) -> None:
    """Tope 5 %, general 10 % y un propio de 3 % en la única línea: el máximo es 3 %."""
    entorno.permitir("DESCUENTO_MANUAL")
    entorno.fijar_tope("0.05")
    contenido = entorno.contenido(
        entorno.linea(descuento_manual="0.03", descuentos=[_manual("0.030000", "937.50")]),
        total="30312.50",
        descuento_manual_general="0.10",
    )

    entorno.enviar(contenido)

    (descuento,) = entorno.descuentos_de_venta()
    assert descuento.porcentaje == Decimal("0.030000")


def test_dsc05_el_propio_reemplaza_al_general_y_cada_manual_va_sobre_su_importe(
    entorno: EntornoVenta,
) -> None:
    """General de 5 %, propio de 10 % en el vino: el vino lleva un único `MANUAL` de 10 % y la
    otra línea el de 5 %."""
    entorno.permitir("DESCUENTO_MANUAL")
    entorno.fijar_tope("0.10")
    otro_id, otra_presentacion = entorno.producto_a("6000.00")
    vino = entorno.linea(descuento_manual="0.10", descuentos=[_manual("0.100000", "3125.00")])
    otro = entorno.linea(
        otro_id,
        otra_presentacion,
        cantidad=2,
        precio="6000.00",
        unidades_referencia=1,
        descuentos=[_manual("0.050000", "600.00")],
    )

    entorno.enviar(entorno.contenido(vino, otro, total="39525.00", descuento_manual_general="0.05"))

    (venta,) = entorno.ventas()
    assert venta.total == Decimal("39525.00")
    por_linea = {linea.producto_id: linea for linea in entorno.lineas_de_venta(venta.id)}
    assert por_linea[entorno.vino_id].importe_descuento == Decimal("3125.00")
    assert por_linea[otro_id].importe_descuento == Decimal("600.00")
    filas = entorno.descuentos_de_venta()
    assert sorted((f.porcentaje, f.importe) for f in filas) == [
        (Decimal("0.050000"), Decimal("600.00")),
        (Decimal("0.100000"), Decimal("3125.00")),
    ]
    assert {f.origen for f in filas} == {"MANUAL"}


def test_dsc06_sin_el_permiso_de_descuento_manual_se_rechaza(entorno: EntornoVenta) -> None:
    error = _rechazo(entorno, _venta_con_general(entorno, "0.02", "625.00", "30625.00"))

    assert error.codigo == "PERMISO_REQUERIDO"
    entorno.sin_efectos_de_venta(stock_esperado=500)


def test_dsc06_con_el_descuento_manual_deshabilitado_se_rechaza_aunque_haya_reglas(
    entorno: EntornoVenta,
) -> None:
    entorno.permitir("DESCUENTO_MANUAL")
    entorno.configurar(descuento_manual_habilitado=False)
    regla = entorno.crear_regla()
    contenido = entorno.contenido(
        entorno.linea(
            cantidad=120,
            descuentos=[_automatico(regla), _manual("0.020000", "4750.00")],
        ),
        total="232750.00",
        descuento_manual_general="0.02",
    )

    error = _rechazo(entorno, contenido)

    assert (error.codigo, error.status_http) == ("DESCUENTO_MANUAL_DESHABILITADO", 409)
    entorno.sin_efectos_de_venta(stock_esperado=500)


def test_dsc06_las_reglas_solas_no_necesitan_el_descuento_manual_habilitado(
    entorno: EntornoVenta,
) -> None:
    """Triangula: con el manual deshabilitado, una venta solo con reglas se confirma."""
    entorno.configurar(descuento_manual_habilitado=False)
    regla = entorno.crear_regla()

    entorno.enviar(_venta_de_volumen(entorno, regla))

    assert len(entorno.ventas()) == 1


def test_dsc06_un_autorizador_sin_el_permiso_se_rechaza_sin_contar_un_intento(
    entorno: EntornoVenta,
) -> None:
    entorno.permitir("DESCUENTO_MANUAL")
    entorno.fijar_tope("0.05")
    sin_permiso = entorno.crear_usuario(frozenset({"SUPERAR_CREDITO"}), pin=PIN)

    error = _rechazo(
        entorno,
        _venta_con_general(
            entorno, "0.08", "2500.00", "28750.00", descuento_autorizador_id=str(sin_permiso)
        ),
        credenciales=(entorno.credencial(sin_permiso, PIN),),
    )

    assert (error.codigo, error.status_http) == ("AUTORIZADOR_SIN_PERMISO", 403)
    assert entorno.intentos_de_pin() == 0
    entorno.sin_efectos_de_venta(stock_esperado=500)


def test_inv21_un_autorizador_de_otra_organizacion_responde_como_inexistente(
    entorno: EntornoVenta,
) -> None:
    entorno.permitir("DESCUENTO_MANUAL")
    entorno.fijar_tope("0.05")
    ajeno = entorno.crear_usuario(
        frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN, org=entorno.otra_organizacion()
    )

    error = _rechazo(
        entorno,
        _venta_con_general(
            entorno, "0.08", "2500.00", "28750.00", descuento_autorizador_id=str(ajeno)
        ),
        credenciales=(entorno.credencial(ajeno, PIN),),
    )

    assert (error.codigo, error.status_http) == ("RECURSO_NO_ENCONTRADO", 404)
    assert entorno.intentos_de_pin() == 0


# --- el motivo del descuento manual (DSC-06, DSC-08, TR-09) ------------------------------------


def _con_motivo(entorno: EntornoVenta, motivo: UUID | None) -> dict[str, Any]:
    cambios: dict[str, Any] = {} if motivo is None else {"motivo_descuento_id": str(motivo)}
    return _venta_con_general(entorno, "0.05", "1562.50", "29687.50", **cambios)


@pytest.fixture
def con_motivo_exigido(entorno: EntornoVenta) -> EntornoVenta:
    entorno.permitir("DESCUENTO_MANUAL")
    entorno.fijar_tope("0.05")
    entorno.configurar(motivo_obligatorio_descuento=True)
    entorno.sesion.commit()
    return entorno


def test_dsc06_el_motivo_exigido_se_copia_en_cada_descuento_manual(
    con_motivo_exigido: EntornoVenta,
) -> None:
    motivo = con_motivo_exigido.crear_motivo("DESCUENTO_MANUAL", "Negociación por volumen")

    con_motivo_exigido.enviar(_con_motivo(con_motivo_exigido, motivo))

    (descuento,) = con_motivo_exigido.descuentos_de_venta()
    assert descuento.motivo_id == motivo


def test_dsc06_el_motivo_exigido_y_ausente_se_rechaza(con_motivo_exigido: EntornoVenta) -> None:
    error = _rechazo(con_motivo_exigido, _con_motivo(con_motivo_exigido, None))

    assert (error.codigo, error.status_http) == ("MOTIVO_REQUERIDO", 422)
    con_motivo_exigido.sin_efectos_de_venta(stock_esperado=500)


@pytest.mark.parametrize("caso", ["otro-ambito", "inactivo"])
def test_tr09_un_motivo_de_otro_ambito_o_inactivo_es_invalido(
    con_motivo_exigido: EntornoVenta, caso: str
) -> None:
    motivo = (
        con_motivo_exigido.motivo_lista_id
        if caso == "otro-ambito"
        else con_motivo_exigido.crear_motivo("DESCUENTO_MANUAL", "Viejo", activo=False)
    )

    error = _rechazo(con_motivo_exigido, _con_motivo(con_motivo_exigido, motivo))

    assert (error.codigo, error.status_http) == ("MOTIVO_INVALIDO", 422)
    con_motivo_exigido.sin_efectos_de_venta(stock_esperado=500)


def test_inv21_un_motivo_de_otra_organizacion_responde_como_inexistente(
    con_motivo_exigido: EntornoVenta,
) -> None:
    ajeno = con_motivo_exigido.crear_motivo(
        "DESCUENTO_MANUAL", "De otra", org=con_motivo_exigido.otra_organizacion()
    )

    error = _rechazo(con_motivo_exigido, _con_motivo(con_motivo_exigido, ajeno))

    assert (error.codigo, error.status_http) == ("RECURSO_NO_ENCONTRADO", 404)


def test_dsc06_sin_descuento_manual_un_motivo_enviado_no_se_guarda(
    con_motivo_exigido: EntornoVenta,
) -> None:
    motivo = con_motivo_exigido.crear_motivo("DESCUENTO_MANUAL", "Negociación por volumen")

    con_motivo_exigido.enviar(con_motivo_exigido.contenido(motivo_descuento_id=str(motivo)))

    assert len(con_motivo_exigido.ventas()) == 1
    assert con_motivo_exigido.descuentos_de_venta() == []
