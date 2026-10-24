"""Tarea 10.1 (change 18b; specs `ventas/descuentos-en-la-venta`, `ventas/credito-en-la-venta`,
`sync/observaciones` y `auditoria/registro-de-auditoria`; `design.md` D7, D9, D10, D17, D18, D19,
CRÍTICO; borrador aprobado por el usuario el 2026-10-23), contra PostgreSQL real y por
`procesar_lote` en modo `OFFLINE`.

Principio (SYN-05, INV-17): una venta sin conexión no se rechaza por lo que el dispositivo no pudo
saber. Los descuentos y la evaluación de crédito del dispositivo se congelan; lo que el servidor
ve distinto se observa (`DESCUENTO_DIFIERE` con causas, `EXCESO_CREDITO_DETECTADO_SYNC`) y cada
autorización queda con `AUTORIZACION_OFFLINE`. Solo se rechaza lo malformado
(`TOTALES_INCONSISTENTES`, `CREDITO_INCONSISTENTE`) o lo inexistente (SYN-06). Ninguna credencial
(PIN) se acepta por el lote.

Reglas citadas: DSC-06, DSC-08, DSC-09, CRE-05, CRE-06, CRE-08, CRE-09, CRE-10, SYN-05, SYN-06,
SYN-07, SYN-10, INV-01, INV-06, INV-14, INV-17, AUD-01, AUD-02.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_ventas_offline import Ruta, _observaciones, _rechazada, _sin_efectos, lote
from ventas_confirmar_utiles import EntornoVenta

from app.modules.sync.models import Observacion

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

LIMITE_REAL = "170000.00"


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    e = EntornoVenta(db_session)
    e.configurar(descuento_manual_habilitado=True)
    e.permitir("DESCUENTO_MANUAL")
    e.fijar_tope("0.05")
    db_session.commit()
    return e


# --- armado ---------------------------------------------------------------------------------


def _auto(regla: UUID, importe: str = "12500.00") -> dict[str, Any]:
    return {
        "origen": "AUTOMATICO",
        "regla_id": str(regla),
        "porcentaje": "0.050000",
        "importe": importe,
    }


def _manual(porcentaje: str, importe: str) -> dict[str, Any]:
    return {"origen": "MANUAL", "regla_id": None, "porcentaje": porcentaje, "importe": importe}


def _con_manual(
    ruta: Ruta, porcentaje: str, importe: str, total: str, **cambios: Any
) -> dict[str, Any]:
    """15 botellas de Vino A ($31.250) con un descuento general del `porcentaje` (fracción)."""
    return ruta.contenido(
        ruta.entorno.linea(descuentos=[_manual(f"{Decimal(porcentaje):.6f}", importe)]),
        total=total,
        descuento_manual_general=porcentaje,
        **cambios,
    )


def _de_volumen(ruta: Ruta, regla: UUID | None, **cambios: Any) -> dict[str, Any]:
    """120 botellas (20 cajas, `250000.00`); con la regla vista por el dispositivo: 5 %."""
    descuentos = [] if regla is None else [_auto(regla)]
    total = "250000.00" if regla is None else "237500.00"
    return ruta.contenido(
        ruta.entorno.linea(cantidad=120, descuentos=descuentos), total=total, **cambios
    )


def _enviar(entorno: EntornoVenta, ruta: Ruta, contenido: dict[str, Any]) -> Any:
    item = ruta.item(contenido)
    return item, lote(entorno, item)[item.operation_id]


def _por_codigo(entorno: EntornoVenta) -> dict[str, list[Observacion]]:
    agrupadas: dict[str, list[Observacion]] = {}
    for observacion in _observaciones(entorno):
        agrupadas.setdefault(observacion.codigo, []).append(observacion)
    return agrupadas


def _detalle(entorno: EntornoVenta, codigo: str) -> dict[str, Any]:
    (observacion,) = _por_codigo(entorno)[codigo]
    assert observacion.detalle is not None
    return dict(observacion.detalle)


def _causas(entorno: EntornoVenta) -> list[str]:
    return [causa["causa"] for causa in _detalle(entorno, "DESCUENTO_DIFIERE")["causas"]]


def _supervisor(entorno: EntornoVenta, *permisos: str) -> UUID:
    return entorno.crear_usuario(frozenset(permisos))


def _filas_de_auditoria(entorno: EntornoVenta, operation_id: UUID) -> dict[str, list[Any]]:
    entorno.sesion.rollback()
    filas: dict[str, list[Any]] = {}
    for fila in entorno.auditoria_de(operation_id):
        filas.setdefault(fila.accion, []).append(fila)
    return filas


def _credito_con_exceso(entorno: EntornoVenta, **cambios: Any) -> dict[str, Any]:
    """Límite $170.000, saldo $150.000 y una venta de $31.250: resultante $181.250, exceso
    $11.250 (según los números del dispositivo)."""
    valores: dict[str, Any] = {
        "limite": LIMITE_REAL,
        "saldo": "150000.00",
        "politica": "AUTORIZAR",
        "resolucion": "TOLERANCIA_OFFLINE",
    }
    valores.update(cambios)
    return entorno.credito_offline(**valores)


# =============================== DESCUENTOS ==================================================
# --- los descuentos del dispositivo se congelan (D10 puntos 2 y 3) -------------------------------


def test_dsc09_los_descuentos_del_dispositivo_se_congelan_y_si_coinciden_no_se_observa_nada(
    entorno: EntornoVenta,
) -> None:
    """La regla de volumen sigue vigente al `occurred_at`: el 5 % del dispositivo es el que calcula
    el servidor; la venta guarda lo que registró el dispositivo."""
    regla = entorno.crear_regla()
    ruta = Ruta(entorno, stock=200)

    _, resultado = _enviar(entorno, ruta, _de_volumen(ruta, regla))

    assert resultado.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert (venta.modo_confirmacion, venta.total, venta.total_neto) == (
        "OFFLINE",
        Decimal("237500.00"),
        Decimal("237500.00"),
    )
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert (linea.importe_bruto, linea.importe_descuento, linea.importe_neto) == (
        Decimal("250000.00"),
        Decimal("12500.00"),
        Decimal("237500.00"),
    )
    (descuento,) = entorno.descuentos_de_venta()
    assert (descuento.origen, descuento.regla_id, descuento.importe) == (
        "AUTOMATICO",
        regla,
        Decimal("12500.00"),
    )
    assert (descuento.motivo_id, descuento.autorizador_id) == (None, None)
    (debito,) = entorno.movimientos("VENTA")
    assert debito.importe == Decimal("237500.00")
    assert _observaciones(entorno) == []


def test_dsc09_una_regla_pausada_antes_del_momento_de_la_venta_da_calculo_y_se_congela_lo_enviado(
    entorno: EntornoVenta,
) -> None:
    """El dispositivo aplicó una regla que al sincronizar ya no rige: la venta se acepta con los
    descuentos del dispositivo y UNA `DESCUENTO_DIFIERE` con la causa `CALCULO` de esa línea
    (esperado = lo que registró el dispositivo, calculado = lo del servidor)."""
    regla = entorno.crear_regla()
    entorno.pausar_regla(regla)
    ruta = Ruta(entorno, stock=200)

    _, resultado = _enviar(entorno, ruta, _de_volumen(ruta, regla))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    assert venta.total == Decimal("237500.00")
    (descuento,) = entorno.descuentos_de_venta()
    assert (descuento.regla_id, descuento.importe) == (regla, Decimal("12500.00"))
    (causa,) = _detalle(entorno, "DESCUENTO_DIFIERE")["causas"]
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert causa["causa"] == "CALCULO"
    assert causa["linea_id"] == str(linea.id)
    assert [d["importe"] for d in causa["esperado"]] == ["12500.00"]
    assert causa["calculado"] == []


def test_dsc09_una_regla_que_el_dispositivo_no_aplico_tambien_da_calculo(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: la regla rige y el dispositivo no la aplicó (bootstrap viejo): se congela el
    total sin descuento y el servidor observa lo que habría aplicado."""
    entorno.crear_regla()
    ruta = Ruta(entorno, stock=200)

    _, resultado = _enviar(entorno, ruta, _de_volumen(ruta, None))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    assert venta.total == Decimal("250000.00")
    assert entorno.descuentos_de_venta() == []
    (causa,) = _detalle(entorno, "DESCUENTO_DIFIERE")["causas"]
    assert causa["esperado"] == []
    assert [d["importe"] for d in causa["calculado"]] == ["12500.00"]


def test_dsc06_un_manual_dentro_del_tope_se_acepta_sin_observaciones(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, _con_manual(ruta, "0.03", "937.50", "30312.50"))

    assert resultado.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert venta.total == Decimal("30312.50")
    (descuento,) = entorno.descuentos_de_venta()
    assert (descuento.origen, descuento.porcentaje, descuento.importe) == (
        "MANUAL",
        Decimal("0.030000"),
        Decimal("937.50"),
    )
    assert _observaciones(entorno) == []


def test_dsc08_el_motivo_y_el_autorizador_se_copian_a_la_fila_manual(
    entorno: EntornoVenta,
) -> None:
    motivo = entorno.crear_motivo("DESCUENTO_MANUAL", "Cliente frecuente")
    marta = _supervisor(entorno, "AUTORIZAR_DESCUENTO")
    entorno.sesion.commit()
    ruta = Ruta(entorno)

    _, resultado = _enviar(
        entorno,
        ruta,
        _con_manual(
            ruta,
            "0.10",
            "3125.00",
            "28125.00",
            motivo_descuento_id=str(motivo),
            descuento_autorizador_id=str(marta),
        ),
    )

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (descuento,) = entorno.descuentos_de_venta()
    assert (descuento.motivo_id, descuento.autorizador_id) == (motivo, marta)


# --- las causas de DESCUENTO_DIFIERE (D10 punto 4) ---------------------------------------------


def test_dsc06_un_manual_sobre_el_tope_sin_autorizacion_da_tope_y_se_acepta(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, _con_manual(ruta, "0.10", "3125.00", "28125.00"))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    assert venta.total == Decimal("28125.00")
    assert _causas(entorno) == ["TOPE"]
    assert "AUTORIZACION_OFFLINE" not in _por_codigo(entorno)


def test_dsc06_un_vendedor_sin_descuento_manual_da_permiso(db_session: Session) -> None:
    """Sin `DESCUENTO_MANUAL` hoy: la venta del dispositivo igual entra, con la causa `PERMISO`.
    Este vendedor tampoco tiene tope (0 %), así que el 3 % también da `TOPE` (D10: todas las
    causas que apliquen)."""
    entorno = EntornoVenta(db_session)
    entorno.configurar(descuento_manual_habilitado=True)
    db_session.commit()
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, _con_manual(ruta, "0.03", "937.50", "30312.50"))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _causas(entorno) == ["PERMISO", "TOPE"]


def test_dsc06_con_el_descuento_manual_deshabilitado_da_deshabilitado(
    entorno: EntornoVenta,
) -> None:
    entorno.configurar(descuento_manual_habilitado=False)
    entorno.sesion.commit()
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, _con_manual(ruta, "0.03", "937.50", "30312.50"))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _causas(entorno) == ["DESHABILITADO"]


def test_dsc06_con_motivo_obligatorio_y_sin_motivo_da_motivo(entorno: EntornoVenta) -> None:
    entorno.configurar(motivo_obligatorio_descuento=True)
    entorno.sesion.commit()
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, _con_manual(ruta, "0.03", "937.50", "30312.50"))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _causas(entorno) == ["MOTIVO"]


def test_dsc06_un_autorizador_que_perdio_el_permiso_da_autorizador_sin_permiso_y_la_venta_entra(
    entorno: EntornoVenta,
) -> None:
    luis = _supervisor(entorno)  # ya no tiene AUTORIZAR_DESCUENTO
    ruta = Ruta(entorno)

    _, resultado = _enviar(
        entorno,
        ruta,
        _con_manual(ruta, "0.10", "3125.00", "28125.00", descuento_autorizador_id=str(luis)),
    )

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _causas(entorno) == ["AUTORIZADOR_SIN_PERMISO"]
    detalle = _detalle(entorno, "AUTORIZACION_OFFLINE")
    assert detalle["autorizador_con_permiso"] is False
    (descuento,) = entorno.descuentos_de_venta()
    assert descuento.autorizador_id == luis


def test_dsc09_varias_causas_van_en_una_sola_observacion_por_venta(
    entorno: EntornoVenta,
) -> None:
    """Regla pausada (`CALCULO`) más un manual sobre el tope (`TOPE`) en la misma venta: una sola
    `DESCUENTO_DIFIERE` con las dos causas, en ese orden."""
    regla = entorno.crear_regla()
    entorno.pausar_regla(regla)
    ruta = Ruta(entorno, stock=200)
    contenido = ruta.contenido(
        entorno.linea(
            cantidad=120,
            descuentos=[_auto(regla), _manual("0.100000", "23750.00")],
        ),
        total="213750.00",
        descuento_manual_general="0.10",
    )

    _, resultado = _enviar(entorno, ruta, contenido)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert len(_por_codigo(entorno)["DESCUENTO_DIFIERE"]) == 1
    assert _causas(entorno) == ["CALCULO", "TOPE"]


def _causas_completas(entorno: EntornoVenta) -> list[dict[str, Any]]:
    return list(_detalle(entorno, "DESCUENTO_DIFIERE")["causas"])


def test_d10_tope_y_motivo_juntos_dan_las_dos_causas_con_sus_datos(
    entorno: EntornoVenta,
) -> None:
    """SYN-05, INV-17 (prueba manual del 2026-10-23): manual 10 % con tope 5 %, sin autorizador y
    sin motivo exigido: UNA `DESCUENTO_DIFIERE` con `MOTIVO` y `TOPE`; solo `TOPE` lleva el
    tope y el porcentaje."""
    entorno.configurar(motivo_obligatorio_descuento=True)
    entorno.sesion.commit()
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, _con_manual(ruta, "0.10", "3125.00", "28125.00"))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert len(_por_codigo(entorno)["DESCUENTO_DIFIERE"]) == 1
    assert _causas_completas(entorno) == [
        {"causa": "MOTIVO"},
        {"causa": "TOPE", "porcentaje_maximo": "0.100000", "tope": "0.050000"},
    ]


def test_d10_permiso_motivo_y_tope_juntos_dan_las_tres_causas(db_session: Session) -> None:
    """Sin `DESCUENTO_MANUAL` hoy (y sin tope) y con motivo exigido y ausente: `PERMISO`,
    `MOTIVO` y `TOPE`, en el orden de D12."""
    entorno = EntornoVenta(db_session)
    entorno.configurar(descuento_manual_habilitado=True, motivo_obligatorio_descuento=True)
    db_session.commit()
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, _con_manual(ruta, "0.03", "937.50", "30312.50"))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _causas(entorno) == ["PERMISO", "MOTIVO", "TOPE"]


def test_d10_calculo_motivo_y_tope_van_en_una_sola_observacion_en_orden_estable(
    entorno: EntornoVenta,
) -> None:
    """Regla pausada (`CALCULO`), motivo exigido y ausente, manual sobre el tope: el cálculo
    primero y después las causas del manual en el orden de D12."""
    entorno.configurar(motivo_obligatorio_descuento=True)
    regla = entorno.crear_regla()
    entorno.pausar_regla(regla)
    entorno.sesion.commit()
    ruta = Ruta(entorno, stock=200)
    contenido = ruta.contenido(
        entorno.linea(
            cantidad=120,
            descuentos=[_auto(regla), _manual("0.100000", "23750.00")],
        ),
        total="213750.00",
        descuento_manual_general="0.10",
    )

    _, resultado = _enviar(entorno, ruta, contenido)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert len(_por_codigo(entorno)["DESCUENTO_DIFIERE"]) == 1
    assert _causas(entorno) == ["CALCULO", "MOTIVO", "TOPE"]


def test_d10_deshabilitado_permiso_motivo_y_tope_juntos(db_session: Session) -> None:
    entorno = EntornoVenta(db_session)
    entorno.configurar(descuento_manual_habilitado=False, motivo_obligatorio_descuento=True)
    db_session.commit()
    ruta = Ruta(entorno)

    _enviar(entorno, ruta, _con_manual(ruta, "0.10", "3125.00", "28125.00"))

    assert _causas(entorno) == ["DESHABILITADO", "PERMISO", "MOTIVO", "TOPE"]


def test_d10_una_sola_causa_sigue_dando_una_sola_con_sus_datos(entorno: EntornoVenta) -> None:
    ruta = Ruta(entorno)

    _enviar(entorno, ruta, _con_manual(ruta, "0.10", "3125.00", "28125.00"))

    assert _causas_completas(entorno) == [
        {"causa": "TOPE", "porcentaje_maximo": "0.100000", "tope": "0.050000"}
    ]


# --- AUTORIZACION_OFFLINE del descuento (D9; decisiones 3 y 4) ---------------------------------


def test_cre05_un_manual_autorizado_con_pin_de_otra_persona_deja_autorizacion_offline(
    entorno: EntornoVenta,
) -> None:
    marta = _supervisor(entorno, "AUTORIZAR_DESCUENTO")
    ruta = Ruta(entorno)

    _, resultado = _enviar(
        entorno,
        ruta,
        _con_manual(ruta, "0.10", "3125.00", "28125.00", descuento_autorizador_id=str(marta)),
    )

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _detalle(entorno, "AUTORIZACION_OFFLINE") == {
        "tipo": "DESCUENTO",
        "resolucion": "PIN_SUPERVISOR",
        "autorizador_id": str(marta),
        "autorizador_con_permiso": True,
    }
    assert "DESCUENTO_DIFIERE" not in _por_codigo(entorno)  # con la autorización no supera el tope


def test_cre05_un_manual_sobre_el_tope_con_permiso_propio_deja_autorizacion_offline(
    entorno: EntornoVenta,
) -> None:
    entorno.permitir("AUTORIZAR_DESCUENTO")
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, _con_manual(ruta, "0.10", "3125.00", "28125.00"))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _detalle(entorno, "AUTORIZACION_OFFLINE") == {
        "tipo": "DESCUENTO",
        "resolucion": "PERMISO_PROPIO",
        "autorizador_id": str(entorno.usuario_id),
        "autorizador_con_permiso": True,
    }
    (descuento,) = entorno.descuentos_de_venta()
    assert descuento.autorizador_id == entorno.usuario_id


def test_cre05_el_mismo_usuario_como_autorizador_es_permiso_propio(
    entorno: EntornoVenta,
) -> None:
    entorno.permitir("AUTORIZAR_DESCUENTO")
    ruta = Ruta(entorno)

    _enviar(
        entorno,
        ruta,
        _con_manual(
            ruta,
            "0.10",
            "3125.00",
            "28125.00",
            descuento_autorizador_id=str(entorno.usuario_id),
        ),
    )

    assert _detalle(entorno, "AUTORIZACION_OFFLINE")["resolucion"] == "PERMISO_PROPIO"


def test_cre05_con_autorizador_enviado_y_hoy_dentro_del_tope_igual_se_observa(
    entorno: EntornoVenta,
) -> None:
    """Decisión 4 del usuario: el tope subió o el descuento es chico, pero el dispositivo registró
    una autorización: queda `AUTORIZACION_OFFLINE` (y ninguna `DESCUENTO_DIFIERE`)."""
    marta = _supervisor(entorno, "AUTORIZAR_DESCUENTO")
    ruta = Ruta(entorno)

    _enviar(
        entorno,
        ruta,
        _con_manual(ruta, "0.03", "937.50", "30312.50", descuento_autorizador_id=str(marta)),
    )

    assert set(_por_codigo(entorno)) == {"AUTORIZACION_OFFLINE"}


def test_cre05_con_permiso_propio_pero_dentro_del_tope_no_hay_autorizacion(
    entorno: EntornoVenta,
) -> None:
    entorno.permitir("AUTORIZAR_DESCUENTO")
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, _con_manual(ruta, "0.03", "937.50", "30312.50"))

    assert resultado.estado == "ACEPTADO"
    assert _observaciones(entorno) == []


# --- inexistente (SYN-06) y motivo (D10 punto 1) -----------------------------------------------


def test_syn06_un_autorizador_de_descuento_inexistente_se_rechaza_sin_efectos(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)
    item = ruta.item(
        _con_manual(ruta, "0.10", "3125.00", "28125.00", descuento_autorizador_id=str(uuid4()))
    )

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "RECURSO_NO_ENCONTRADO", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


def test_syn06_un_autorizador_de_otra_organizacion_se_trata_como_inexistente(
    entorno: EntornoVenta,
) -> None:
    ajeno = entorno.crear_usuario(
        frozenset({"AUTORIZAR_DESCUENTO"}), org=entorno.otra_organizacion()
    )
    ruta = Ruta(entorno)
    item = ruta.item(
        _con_manual(ruta, "0.10", "3125.00", "28125.00", descuento_autorizador_id=str(ajeno))
    )

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "RECURSO_NO_ENCONTRADO", item, entorno)


def test_syn06_una_regla_inexistente_se_rechaza_sin_efectos(entorno: EntornoVenta) -> None:
    ruta = Ruta(entorno, stock=200)
    item = ruta.item(_de_volumen(ruta, uuid4()))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "RECURSO_NO_ENCONTRADO", item, entorno)
    _sin_efectos(entorno, 200, ruta.camioneta_id)


def test_syn05_un_motivo_de_descuento_inactivo_se_acepta_sin_observacion(
    entorno: EntornoVenta,
) -> None:
    inactivo = entorno.crear_motivo("DESCUENTO_MANUAL", "Motivo viejo", activo=False)
    entorno.sesion.commit()
    ruta = Ruta(entorno)

    _, resultado = _enviar(
        entorno,
        ruta,
        _con_manual(ruta, "0.03", "937.50", "30312.50", motivo_descuento_id=str(inactivo)),
    )

    assert resultado.estado == "ACEPTADO"
    (descuento,) = entorno.descuentos_de_venta()
    assert descuento.motivo_id == inactivo


def test_syn06_un_motivo_de_descuento_de_otro_ambito_es_motivo_invalido(
    entorno: EntornoVenta,
) -> None:
    ajeno = entorno.crear_motivo("ANULACION_VENTA", "Otro ámbito")
    entorno.sesion.commit()
    ruta = Ruta(entorno)
    item = ruta.item(
        _con_manual(ruta, "0.03", "937.50", "30312.50", motivo_descuento_id=str(ajeno))
    )

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "MOTIVO_INVALIDO", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


def test_syn06_un_motivo_de_descuento_inexistente_es_recurso_no_encontrado(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)
    item = ruta.item(
        _con_manual(ruta, "0.03", "937.50", "30312.50", motivo_descuento_id=str(uuid4()))
    )

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "RECURSO_NO_ENCONTRADO", item, entorno)


# --- lo malformado (D10 punto 1) ---------------------------------------------------------------


def _malformada(caso: str, entorno: EntornoVenta, ruta: Ruta) -> dict[str, Any]:
    regla = uuid4()
    if caso == "importe_cero":
        return ruta.contenido(
            entorno.linea(descuentos=[_manual("0.000000", "0.00")]), total="31250.00"
        )
    if caso == "dos_manuales":
        return ruta.contenido(
            entorno.linea(
                descuentos=[_manual("0.010000", "312.50"), _manual("0.010000", "312.50")]
            ),
            total="30625.00",
        )
    if caso == "automatico_sin_regla":
        return ruta.contenido(
            entorno.linea(
                descuentos=[
                    {
                        "origen": "AUTOMATICO",
                        "regla_id": None,
                        "porcentaje": "0.050000",
                        "importe": "100.00",
                    }
                ]
            ),
            total="31150.00",
        )
    if caso == "manual_con_regla":
        return ruta.contenido(
            entorno.linea(
                descuentos=[
                    {
                        "origen": "MANUAL",
                        "regla_id": str(regla),
                        "porcentaje": "0.010000",
                        "importe": "312.50",
                    }
                ]
            ),
            total="30937.50",
        )
    if caso == "total_distinto_de_los_netos":
        return ruta.contenido(
            entorno.linea(descuentos=[_manual("0.030000", "937.50")]), total="31250.00"
        )
    assert caso == "descuento_mayor_al_bruto"
    return ruta.contenido(
        entorno.linea(descuentos=[_manual("1.500000", "46875.00")]), total="-15625.00"
    )


@pytest.mark.parametrize(
    "caso",
    [
        "importe_cero",
        "dos_manuales",
        "automatico_sin_regla",
        "manual_con_regla",
        "total_distinto_de_los_netos",
        "descuento_mayor_al_bruto",
    ],
)
def test_syn06_un_descuento_malformado_se_rechaza_con_totales_inconsistentes_sin_efectos(
    entorno: EntornoVenta, caso: str
) -> None:
    ruta = Ruta(entorno)
    item = ruta.item(_malformada(caso, entorno, ruta))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "TOTALES_INCONSISTENTES", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


# =============================== CRÉDITO =====================================================
# --- obligatorio y coherente (D7 punto 1; decisión 1 del usuario) -------------------------------


def test_syn06_una_venta_sin_conexion_sin_el_objeto_credito_se_rechaza(
    entorno: EntornoVenta,
) -> None:
    """Decisión del usuario, 2026-10-23: la app no tiene versiones viejas, así que el `credito`
    del dispositivo es obligatorio sin conexión; sin él, el comando está malformado."""
    ruta = Ruta(entorno)
    item = ruta.item(ruta.contenido(credito=None))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "CREDITO_INCONSISTENTE", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


@pytest.mark.parametrize("faltante", ["saldo_considerado", "politica", "resolucion"])
def test_syn06_un_dato_obligatorio_del_credito_ausente_se_rechaza(
    entorno: EntornoVenta, faltante: str
) -> None:
    ruta = Ruta(entorno)
    credito = entorno.credito_offline()
    credito[faltante] = None
    item = ruta.item(ruta.contenido(credito=credito))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "CREDITO_INCONSISTENTE", item, entorno)


def test_cre09_un_exceso_propio_con_resolucion_sin_exceso_es_credito_inconsistente(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)
    item = ruta.item(ruta.contenido(credito=_credito_con_exceso(entorno, resolucion="SIN_EXCESO")))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "CREDITO_INCONSISTENTE", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


@pytest.mark.parametrize("resolucion", ["PIN_SUPERVISOR", "PERMISO_PROPIO"])
def test_cre09_pin_o_permiso_propio_sin_autorizador_es_credito_inconsistente(
    entorno: EntornoVenta, resolucion: str
) -> None:
    ruta = Ruta(entorno)
    item = ruta.item(ruta.contenido(credito=_credito_con_exceso(entorno, resolucion=resolucion)))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "CREDITO_INCONSISTENTE", item, entorno)


def test_cre09_sin_limite_una_resolucion_distinta_de_sin_exceso_es_credito_inconsistente(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)
    credito = entorno.credito_offline(limite=None, resolucion="TOLERANCIA_OFFLINE")
    item = ruta.item(ruta.contenido(credito=credito))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "CREDITO_INCONSISTENTE", item, entorno)


def test_syn06_un_autorizador_de_credito_inexistente_se_rechaza(entorno: EntornoVenta) -> None:
    ruta = Ruta(entorno)
    credito = _credito_con_exceso(entorno, resolucion="PIN_SUPERVISOR", autorizador_id=uuid4())
    item = ruta.item(ruta.contenido(credito=credito))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "RECURSO_NO_ENCONTRADO", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


# --- la evaluación del dispositivo se congela (D7 punto 2; CRE-10) ----------------------------


def test_cre10_la_venta_congela_la_evaluacion_del_dispositivo_con_disponible_y_exceso_del_motor(
    entorno: EntornoVenta,
) -> None:
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="AUTORIZAR")
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, ruta.contenido(credito=_credito_con_exceso(entorno)))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    assert (
        venta.credito_limite,
        venta.credito_saldo_considerado,
        venta.credito_disponible,
        venta.credito_exceso,
        venta.credito_politica,
        venta.credito_resolucion,
        venta.credito_autorizador_id,
    ) == (
        Decimal("170000.00"),
        Decimal("150000.00"),
        Decimal("20000.00"),
        Decimal("11250.00"),
        "AUTORIZAR",
        "TOLERANCIA_OFFLINE",
        None,
    )


def test_cre10_sin_exceso_la_venta_congela_sin_exceso_y_no_observa(
    entorno: EntornoVenta,
) -> None:
    entorno.datos_de_credito(limite="500000.00", politica="AUTORIZAR")
    ruta = Ruta(entorno)

    _, resultado = _enviar(
        entorno,
        ruta,
        ruta.contenido(credito=entorno.credito_offline(limite="500000.00", politica="AUTORIZAR")),
    )

    assert resultado.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert (venta.credito_exceso, venta.credito_resolucion) == (
        Decimal("0.00"),
        "SIN_EXCESO",
    )


def test_cre01_sin_limite_la_venta_congela_el_saldo_con_limite_disponible_y_exceso_vacios(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, ruta.contenido())

    assert resultado.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert (
        venta.credito_limite,
        venta.credito_disponible,
        venta.credito_exceso,
        venta.credito_saldo_considerado,
        venta.credito_resolucion,
    ) == (None, None, None, Decimal("150000.00"), "SIN_EXCESO")


# --- observaciones por resolución del dispositivo (D7 punto 4) --------------------------------


def test_cre06_tolerancia_offline_deja_exceso_credito_autorizado_offline(
    entorno: EntornoVenta,
) -> None:
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="AUTORIZAR")
    ruta = Ruta(entorno)

    _enviar(entorno, ruta, ruta.contenido(credito=_credito_con_exceso(entorno)))

    assert set(_por_codigo(entorno)) == {"EXCESO_CREDITO_AUTORIZADO_OFFLINE"}
    assert _detalle(entorno, "EXCESO_CREDITO_AUTORIZADO_OFFLINE") == {
        "limite": "170000.00",
        "saldo_considerado": "150000.00",
        "exceso": "11250.00",
    }


def test_cre06_no_se_valida_el_tamano_de_la_tolerancia_que_uso_el_dispositivo(
    entorno: EntornoVenta,
) -> None:
    """Decisión 2 del usuario: aunque el exceso sea enorme, `TOLERANCIA_OFFLINE` se acepta; la
    oficina lo ve por la observación."""
    entorno.datos_de_credito(limite="10000.00", politica="AUTORIZAR")
    ruta = Ruta(entorno)

    _, resultado = _enviar(
        entorno,
        ruta,
        ruta.contenido(credito=_credito_con_exceso(entorno, limite="10000.00", saldo="0.00")),
    )

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _detalle(entorno, "EXCESO_CREDITO_AUTORIZADO_OFFLINE")["exceso"] == "21250.00"


def test_cre04_advertencia_aceptada_deja_exceso_credito_advertido(entorno: EntornoVenta) -> None:
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="ADVERTIR")
    ruta = Ruta(entorno)

    _enviar(
        entorno,
        ruta,
        ruta.contenido(
            credito=_credito_con_exceso(
                entorno, politica="ADVERTIR", resolucion="ADVERTENCIA_ACEPTADA"
            )
        ),
    )

    assert set(_por_codigo(entorno)) == {"EXCESO_CREDITO_ADVERTIDO"}
    assert _detalle(entorno, "EXCESO_CREDITO_ADVERTIDO")["exceso"] == "11250.00"


@pytest.mark.parametrize("resolucion", ["PIN_SUPERVISOR", "PERMISO_PROPIO"])
def test_cre05_pin_o_permiso_propio_de_credito_dejan_autorizacion_offline(
    entorno: EntornoVenta, resolucion: str
) -> None:
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="AUTORIZAR")
    marta = _supervisor(entorno, "SUPERAR_CREDITO")
    ruta = Ruta(entorno)

    _, resultado = _enviar(
        entorno,
        ruta,
        ruta.contenido(
            credito=_credito_con_exceso(entorno, resolucion=resolucion, autorizador_id=marta)
        ),
    )

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _detalle(entorno, "AUTORIZACION_OFFLINE") == {
        "tipo": "CREDITO",
        "resolucion": resolucion,
        "autorizador_id": str(marta),
        "autorizador_con_permiso": True,
    }
    (venta,) = entorno.ventas()
    assert (venta.credito_resolucion, venta.credito_autorizador_id) == (resolucion, marta)


def test_cre09_el_autorizador_que_perdio_el_permiso_deja_la_venta_con_permiso_false(
    entorno: EntornoVenta,
) -> None:
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="AUTORIZAR")
    luis = _supervisor(entorno)  # sin SUPERAR_CREDITO hoy
    ruta = Ruta(entorno)

    _, resultado = _enviar(
        entorno,
        ruta,
        ruta.contenido(
            credito=_credito_con_exceso(entorno, resolucion="PIN_SUPERVISOR", autorizador_id=luis)
        ),
    )

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _detalle(entorno, "AUTORIZACION_OFFLINE")["autorizador_con_permiso"] is False
    assert len(entorno.ventas()) == 1


# --- lo que el dispositivo no vio (CRE-08, CRE-09) --------------------------------------------


def test_cre09_un_exceso_real_que_el_dispositivo_no_vio_deja_detectado_sync_con_las_dos(
    entorno: EntornoVenta,
) -> None:
    """El dispositivo vio saldo $100.000 (venta de $31.250 sobre límite $170.000: sin exceso); el
    saldo real es $150.000 (la oficina registró otra venta): el real da un exceso de $11.250.
    Se congela lo del dispositivo y la observación trae las dos evaluaciones."""
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="BLOQUEAR")
    ruta = Ruta(entorno)

    _, resultado = _enviar(
        entorno,
        ruta,
        ruta.contenido(credito=entorno.credito_offline(limite=LIMITE_REAL, saldo="100000.00")),
    )

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    assert (venta.credito_saldo_considerado, venta.credito_exceso, venta.credito_resolucion) == (
        Decimal("100000.00"),
        Decimal("0.00"),
        "SIN_EXCESO",
    )
    assert _detalle(entorno, "EXCESO_CREDITO_DETECTADO_SYNC") == {
        "dispositivo": {
            "limite": "170000.00",
            "saldo_considerado": "100000.00",
            "disponible": "70000.00",
            "exceso": "0.00",
            "politica": "ADVERTIR",
            "resolucion": "SIN_EXCESO",
        },
        "servidor": {
            "limite": "170000.00",
            "saldo_considerado": "150000.00",
            "disponible": "20000.00",
            "exceso": "11250.00",
            "politica": "BLOQUEAR",
        },
    }


def test_cre09_si_el_dispositivo_ya_vio_el_exceso_no_se_agrega_detectado_sync(
    entorno: EntornoVenta,
) -> None:
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="AUTORIZAR")
    ruta = Ruta(entorno)

    _enviar(entorno, ruta, ruta.contenido(credito=_credito_con_exceso(entorno)))

    assert "EXCESO_CREDITO_DETECTADO_SYNC" not in _por_codigo(entorno)


def test_cre09_el_saldo_real_sin_exceso_no_agrega_detectado_sync(entorno: EntornoVenta) -> None:
    """Triangulación: el dispositivo vio saldo $100.000 y el real también (sin exceso)."""
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="AUTORIZAR")
    entorno.sesion.commit()
    ruta = Ruta(entorno)
    credito = entorno.credito_offline(limite="300000.00", saldo="100000.00")
    entorno.datos_de_credito(limite="300000.00", politica="AUTORIZAR")

    _, resultado = _enviar(entorno, ruta, ruta.contenido(credito=credito))

    assert resultado.estado == "ACEPTADO"


def test_cre09_la_politica_cambiada_a_bloquear_igual_se_acepta_con_su_observacion(
    entorno: EntornoVenta,
) -> None:
    """La política del cliente pasó a BLOQUEAR después del bootstrap: el servidor nunca rechaza
    por crédito sin conexión (SYN-05)."""
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="BLOQUEAR")
    ruta = Ruta(entorno)

    _, resultado = _enviar(entorno, ruta, ruta.contenido(credito=_credito_con_exceso(entorno)))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert set(_por_codigo(entorno)) == {"EXCESO_CREDITO_AUTORIZADO_OFFLINE"}


def test_syn05_exceso_cero_con_resolucion_distinta_de_sin_exceso_se_acepta_tal_cual(
    entorno: EntornoVenta,
) -> None:
    """Decisión 5 del usuario."""
    ruta = Ruta(entorno)
    credito = entorno.credito_offline(
        limite="500000.00", politica="ADVERTIR", resolucion="ADVERTENCIA_ACEPTADA"
    )
    entorno.datos_de_credito(limite="500000.00", politica="ADVERTIR")

    _, resultado = _enviar(entorno, ruta, ruta.contenido(credito=credito))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    assert (venta.credito_exceso, venta.credito_resolucion) == (
        Decimal("0.00"),
        "ADVERTENCIA_ACEPTADA",
    )


# --- consumidor final (D17) -------------------------------------------------------------------


def _consumidor_final(entorno: EntornoVenta) -> str:
    consumidor = entorno.crear_cliente(nombre="Consumidor final", es_consumidor_final=True)
    entorno.sesion.commit()
    return str(consumidor)


def test_d17_el_consumidor_final_con_deuda_solo_observa_consumidor_final_con_deuda(
    entorno: EntornoVenta,
) -> None:
    """Se congela con límite cero; ninguna observación de crédito se repite."""
    consumidor = _consumidor_final(entorno)
    ruta = Ruta(entorno)
    credito = entorno.credito_offline(
        limite="0.00", saldo="0.00", politica="AUTORIZAR", resolucion="TOLERANCIA_OFFLINE"
    )

    _, resultado = _enviar(entorno, ruta, ruta.contenido(cliente_id=consumidor, credito=credito))

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert set(_por_codigo(entorno)) == {"CONSUMIDOR_FINAL_CON_DEUDA"}
    (venta,) = entorno.ventas()
    assert (venta.credito_limite, venta.credito_resolucion) == (
        Decimal("0.00"),
        "TOLERANCIA_OFFLINE",
    )


def test_d17_el_consumidor_final_de_contado_se_congela_sin_exceso_y_sin_observaciones(
    entorno: EntornoVenta,
) -> None:
    consumidor = _consumidor_final(entorno)
    ruta = Ruta(entorno)
    credito = entorno.credito_offline(limite="0.00", saldo="0.00", politica="ADVERTIR")

    _, resultado = _enviar(
        entorno,
        ruta,
        ruta.contenido(
            cliente_id=consumidor,
            credito=credito,
            cobranza=entorno.cobranza((entorno.efectivo_id, "31250.00", None)),
        ),
    )

    assert resultado.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert (venta.credito_limite, venta.credito_exceso, venta.credito_resolucion) == (
        Decimal("0.00"),
        Decimal("0.00"),
        "SIN_EXCESO",
    )


def test_d17_el_consumidor_final_se_congela_con_limite_cero_aunque_el_dispositivo_mande_otro(
    entorno: EntornoVenta,
) -> None:
    consumidor = _consumidor_final(entorno)
    ruta = Ruta(entorno)
    credito = entorno.credito_offline(limite=None, saldo="0.00")

    _enviar(
        entorno,
        ruta,
        ruta.contenido(
            cliente_id=consumidor,
            credito=credito,
            cobranza=entorno.cobranza((entorno.efectivo_id, "31250.00", None)),
        ),
    )

    (venta,) = entorno.ventas()
    assert venta.credito_limite == Decimal("0.00")


# =============================== AUDITORÍA (D19) =============================================


def test_aud01_la_venta_sin_conexion_deja_las_filas_de_descuento_manual_y_de_credito(
    entorno: EntornoVenta,
) -> None:
    """Las dos filas reutilizan las del camino con conexión, con `modo` OFFLINE en `despues`,
    la resolución declarada por el dispositivo y el tope de hoy; ninguna lleva PIN."""
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="AUTORIZAR")
    marta = _supervisor(entorno, "AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO")
    motivo = entorno.crear_motivo("DESCUENTO_MANUAL", "Cliente frecuente")
    entorno.sesion.commit()
    ruta = Ruta(entorno)
    item, _ = _enviar(
        entorno,
        ruta,
        _con_manual(
            ruta,
            "0.10",
            "3125.00",
            "28125.00",
            descuento_autorizador_id=str(marta),
            motivo_descuento_id=str(motivo),
            credito=_credito_con_exceso(
                entorno, resolucion="PIN_SUPERVISOR", autorizador_id=marta, saldo="150000.00"
            ),
        ),
    )

    filas = _filas_de_auditoria(entorno, item.operation_id)

    assert set(filas) == {"VENTA_CONFIRMAR", "DESCUENTO_MANUAL", "AUTORIZACION_CREDITO"}
    (descuento,) = filas["DESCUENTO_MANUAL"]
    assert descuento.entidad == "venta"
    assert descuento.autorizador_id == marta
    assert descuento.motivo_id == motivo
    assert descuento.despues == {
        "porcentaje_maximo": "0.100000",
        "tope_aplicado": "0.050000",
        "resolucion": "AUTORIZADO_POR_SUPERVISOR",
        "modo": "OFFLINE",
    }
    (credito,) = filas["AUTORIZACION_CREDITO"]
    assert credito.autorizador_id == marta
    assert credito.despues["modo"] == "OFFLINE"
    assert credito.despues["resolucion"] == "PIN_SUPERVISOR"
    assert credito.despues["exceso"] == "8125.00"
    texto = json.dumps([[f.despues, f.observacion] for g in filas.values() for f in g], default=str)
    assert '"pin"' not in texto.lower()  # ninguna clave `pin`: el PIN nunca se guarda


def test_aud01_una_venta_sin_manual_ni_exceso_solo_deja_la_fila_del_comando(
    entorno: EntornoVenta,
) -> None:
    ruta = Ruta(entorno)
    item, _ = _enviar(entorno, ruta, ruta.contenido())

    assert set(_filas_de_auditoria(entorno, item.operation_id)) == {"VENTA_CONFIRMAR"}


def test_aud03_una_venta_rechazada_no_deja_filas(entorno: EntornoVenta) -> None:
    ruta = Ruta(entorno)
    item = ruta.item(ruta.contenido(credito=None))
    lote(entorno, item)

    assert _filas_de_auditoria(entorno, item.operation_id) == {}


# =============================== LOTE (INV-06) y credenciales ================================


def test_inv06_el_doble_envio_devuelve_el_resultado_original_con_las_mismas_observaciones(
    entorno: EntornoVenta,
) -> None:
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="AUTORIZAR")
    marta = _supervisor(entorno, "AUTORIZAR_DESCUENTO")
    ruta = Ruta(entorno)
    item = ruta.item(
        _con_manual(
            ruta,
            "0.10",
            "3125.00",
            "28125.00",
            descuento_autorizador_id=str(marta),
            credito=_credito_con_exceso(entorno),
        )
    )

    primero = lote(entorno, item)[item.operation_id]
    codigos = sorted(o.codigo for o in _observaciones(entorno))
    segundo = lote(entorno, item)[item.operation_id]

    assert primero.estado == segundo.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert primero.resultado == segundo.resultado
    assert sorted(o.codigo for o in _observaciones(entorno)) == codigos
    assert len(entorno.ventas()) == 1
    assert len(entorno.descuentos_de_venta()) == 1
    assert len(_filas_de_auditoria(entorno, item.operation_id)["DESCUENTO_MANUAL"]) == 1


def test_d2_el_lote_no_acepta_ninguna_credencial_en_una_venta_sin_conexion(
    entorno: EntornoVenta,
) -> None:
    """Ni el PIN ni el contenido con `credenciales` se guardan: el ítem es malformado."""
    marta = _supervisor(entorno, "AUTORIZAR_DESCUENTO")
    ruta = Ruta(entorno)
    contenido = _con_manual(
        ruta, "0.10", "3125.00", "28125.00", descuento_autorizador_id=str(marta)
    )
    contenido["credenciales"] = [{"autorizador_id": str(marta), "pin": "482913"}]
    item = ruta.item(contenido)

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "CONTENIDO_DE_COMANDO_INVALIDO", item, entorno)
    _sin_efectos(entorno, 48, ruta.camioneta_id)


def test_d2_ninguna_verificacion_de_pin_ni_intento_se_escribe_sin_conexion(
    entorno: EntornoVenta,
) -> None:
    """Sin conexión el servidor solo lee el permiso del autorizador: no verifica ni cuenta."""
    marta = _supervisor(entorno, "AUTORIZAR_DESCUENTO")
    ruta = Ruta(entorno)

    _enviar(
        entorno,
        ruta,
        _con_manual(ruta, "0.10", "3125.00", "28125.00", descuento_autorizador_id=str(marta)),
    )

    assert entorno.intentos_de_pin() == 0
    assert entorno.sesion.scalars(select(Observacion)).all()
