"""Tarea 2.1 (change 22d; spec `ventas/anulacion-de-venta`, requisito "Qué rechaza y qué acepta la
anulación sin conexión"; `design.md` D2, CRÍTICA, aprobada el 2026-11-03), contra PostgreSQL real y
por `procesar_lote`.

- Se rechaza, sin efectos y sin fila de comando: venta ya anulada, indicación del dinero que no
  corresponde, observación de más de 500 caracteres, motivo de otra organización o de otro ámbito y
  ubicación inactiva.
- Se acepta: motivo del ámbito dado de baja después del bootstrap (sin observación), permiso
  revocado, jornada liberada y ubicación tomada al sincronizar (propia en rendición o de otro
  vendedor), con el reingreso sin jornada y la constancia en la auditoría.

Reglas citadas: VTA-20, VTA-22, VTA-24, STK-09, SYN-07, RUT-09, SYN-10, AUD-01, INV-06.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_offline import Ruta, lote
from venta_anular_offline_utiles import (
    anular,
    item_de_anulacion,
    observaciones,
    rechazada,
    sin_efectos,
    vender,
)
from ventas_anular_utiles import PERMISOS_DE_ANULADOR, EntornoAnulacion

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

SALDO_ANTES = Decimal("150000.00")
SALDO_CON_LA_VENTA = Decimal("181250.00")


@pytest.fixture
def entorno(db_session: Session) -> EntornoAnulacion:
    return EntornoAnulacion(db_session)


def _codigos(resultado: object) -> list[str]:
    return sorted(o.codigo for o in resultado.observaciones)  # type: ignore[attr-defined]


def _tomar_por_otra_jornada(entorno: EntornoAnulacion, ubicacion_id: UUID) -> UUID:
    """Pedro (otro usuario y dispositivo) abre una jornada `ABIERTA` sobre `ubicacion_id`."""
    otro_id, otro_dispositivo_id = crear_usuario_y_dispositivo(
        entorno.sesion, entorno.org, permisos=frozenset({"VENDER"})
    )
    return entorno.crear_jornada(
        usuario_id=otro_id, dispositivo_id=otro_dispositivo_id, ubicacion_id=ubicacion_id
    )


# --- lo que se rechaza ----------------------------------------------------------------------


def test_vta20_la_venta_ya_anulada_desde_administracion_se_rechaza_y_queda_una_sola_anulacion(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Venta ya anulada desde administración"
    """VTA-20, INV-06, SYN-06: `sup01` anuló con conexión; la anulación del teléfono llega
    después y es `VENTA_YA_ANULADA`, sin segunda acreditación ni segundo reingreso."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    entorno.anular(venta_id)
    item = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "VENTA_YA_ANULADA", item, entorno)
    assert len(entorno.anulaciones_de_venta()) == 1
    assert len(entorno.movimientos_de_stock("ANULACION_VENTA")) == 1
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48
    assert entorno.saldo() == SALDO_ANTES


def test_vta24_motivo_dado_de_baja_despues_del_bootstrap_se_acepta_sin_observacion(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Motivo dado de baja después del bootstrap"
    """VTA-24, ADR-063: el motivo del ámbito `ANULACION_VENTA`, activo en el bootstrap y
    desactivado antes de sincronizar, se acepta sin observación y la anulación lo guarda."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    motivo_id = entorno.crear_motivo("ANULACION_VENTA", "Otro", activo=False)
    entorno.sesion.commit()

    item, resultado = anular(entorno, ruta, venta_id, motivo_id=motivo_id)

    assert resultado.estado == "ACEPTADO"
    assert resultado.observaciones == ()
    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.motivo_id == motivo_id
    assert entorno.venta(venta_id).estado == "ANULADA"


def test_vta24_el_motivo_de_otro_ambito_se_rechaza_con_motivo_invalido(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Motivo de otro ámbito"
    """VTA-20, SYN-06: un motivo de `ANULACION_COBRANZA` no sirve para anular una venta."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    motivo_id = entorno.crear_motivo("ANULACION_COBRANZA", "Cobro cargado dos veces")
    entorno.sesion.commit()
    item = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id, motivo_id=motivo_id)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "MOTIVO_INVALIDO", item, entorno)
    sin_efectos(entorno, ruta, venta_id, saldo=str(SALDO_CON_LA_VENTA))


def test_vta24_el_motivo_de_otra_organizacion_sin_conexion_tambien_es_motivo_invalido(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Motivo de otro ámbito"
    """Triangulación (INV-21): sin conexión el motivo ajeno es `MOTIVO_INVALIDO` y no el 404
    genérico de la anulación con conexión; nada cambia."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    motivo_ajeno = entorno.crear_motivo(
        "ANULACION_VENTA", "Error de carga", org=entorno.otra_organizacion()
    )
    entorno.sesion.commit()
    item = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id, motivo_id=motivo_ajeno)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "MOTIVO_INVALIDO", item, entorno)
    sin_efectos(entorno, ruta, venta_id, saldo=str(SALDO_CON_LA_VENTA))


def test_vta22_devolver_dinero_de_una_venta_sin_cobranza_es_devolucion_invalida(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Devolución que no corresponde"
    """VTA-22, SYN-06: la venta no tiene cobranza y la anulación pide devolver dinero."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    item = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id, devuelve_dinero=True)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "DEVOLUCION_INVALIDA", item, entorno)
    sin_efectos(entorno, ruta, venta_id, saldo=str(SALDO_CON_LA_VENTA))


def test_vta22_una_venta_cobrada_sin_indicar_la_devolucion_es_devolucion_invalida(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Devolución que no corresponde"
    """Triangulación: con cobro en el acto la indicación es obligatoria; omitida, se rechaza."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta, cobranza=entorno.cobranza())
    item = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "DEVOLUCION_INVALIDA", item, entorno)
    assert entorno.venta(venta_id).estado == "CONFIRMADA"
    assert entorno.anulaciones_de_venta() == []


def test_vta20_la_observacion_de_mas_de_500_caracteres_se_rechaza(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Motivo de otro ámbito" (precedencia del contenido)
    """Triangulación: `OBSERVACION_INVALIDA`; con 500 exactos se acepta."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    largo = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id, observacion="x" * 501)

    rechazo = lote(entorno, largo)[largo.operation_id]
    _, aceptada = anular(entorno, ruta, venta_id, observacion="x" * 500, secuencia=3)

    rechazada(rechazo, "OBSERVACION_INVALIDA", largo, entorno)
    assert aceptada.estado == "ACEPTADO"


def test_stk02_la_ubicacion_inactiva_se_rechaza_con_ubicacion_inactiva(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Ubicación inactiva"
    """STK-02, VTA-21: la camioneta fue desactivada antes de sincronizar: no hay reingreso."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)
    entorno.sesion.execute(
        text("UPDATE ubicacion SET activo = false WHERE organizacion_id = :o AND id = :u"),
        {"o": entorno.org, "u": ruta.camioneta_id},
    )
    entorno.sesion.commit()
    item = item_de_anulacion(entorno, venta_id, jornada_id=ruta.jornada_id)

    resultado = lote(entorno, item)[item.operation_id]

    rechazada(resultado, "UBICACION_INACTIVA", item, entorno)
    sin_efectos(entorno, ruta, venta_id, saldo=str(SALDO_CON_LA_VENTA))


# --- lo que se acepta -----------------------------------------------------------------------


def test_syn10_el_permiso_revocado_se_acepta_con_permiso_revocado_sobre_la_venta(
    db_session: Session,
) -> None:
    # Escenario: "Permiso revocado"
    """SYN-10, VTA-24: al vendedor le quitaron `ANULAR_VENTA` después del bootstrap; se acepta
    con `PERMISO_REVOCADO` anotada sobre la venta y la anulación se registra."""
    entorno = EntornoAnulacion(db_session, permisos=frozenset({"VENDER"}))
    ruta = Ruta(entorno)
    venta_id = vender(ruta)

    _, resultado = anular(entorno, ruta, venta_id)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (observacion,) = resultado.observaciones
    assert observacion.codigo == "PERMISO_REVOCADO"
    assert (observacion.operacion_tipo, observacion.operacion_id) == ("VENTA", venta_id)
    assert observacion.detalle == {"permiso": "ANULAR_VENTA", "motivo": "PERMISO_QUITADO"}
    assert entorno.venta(venta_id).estado == "ANULADA"
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48


def test_rut09_la_jornada_liberada_se_acepta_con_jornada_liberada_sobre_la_venta(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Jornada liberada"
    """RUT-09, SYN-07: la jornada J1 fue liberada desde `/admin` mientras el teléfono no tenía
    señal; la anulación de una venta de J1 se acepta con `JORNADA_LIBERADA` sobre la venta."""
    ruta = Ruta(entorno, estado_jornada="LIBERADA")
    venta_id = vender(ruta)

    _, resultado = anular(entorno, ruta, venta_id)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (observacion,) = resultado.observaciones
    assert observacion.codigo == "JORNADA_LIBERADA"
    assert (observacion.operacion_tipo, observacion.operacion_id) == ("VENTA", venta_id)
    assert observacion.detalle is not None
    assert observacion.detalle["jornada_id"] == str(ruta.jornada_id)
    assert entorno.venta(venta_id).estado == "ANULADA"
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48


def test_rut09_la_jornada_abierta_o_en_rendicion_no_observa_la_liberacion(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Jornada liberada"
    """Triangulación: solo `LIBERADA` anota `JORNADA_LIBERADA`; con la jornada `ABIERTA` no hay
    observaciones."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)

    _, resultado = anular(entorno, ruta, venta_id)

    assert (resultado.estado, resultado.observaciones) == ("ACEPTADO", ())


def test_stk09_la_camioneta_tomada_por_otro_vendedor_se_acepta_con_dos_observaciones(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Camioneta tomada por otro vendedor al sincronizar"
    """STK-09, SYN-07, AUD-01: J1 fue liberada y Pedro tomó la camioneta 2 en una jornada
    `ABIERTA`; la anulación de un usuario SIN `LIBERAR_UBICACION` se acepta con `JORNADA_LIBERADA`
    y `UBICACION_TOMADA_AL_SINCRONIZAR`, el reingreso queda sin jornada y la auditoría nombra la
    jornada de Pedro."""
    ruta = Ruta(entorno, estado_jornada="LIBERADA")
    venta_id = vender(ruta)
    jornada_de_pedro = _tomar_por_otra_jornada(entorno, ruta.camioneta_id)

    item, resultado = anular(entorno, ruta, venta_id)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _codigos(resultado) == ["JORNADA_LIBERADA", "UBICACION_TOMADA_AL_SINCRONIZAR"]
    tomada = next(o for o in resultado.observaciones if o.codigo.startswith("UBICACION"))
    assert (tomada.operacion_tipo, tomada.operacion_id) == ("VENTA", venta_id)
    assert tomada.detalle == {
        "jornada_id": str(jornada_de_pedro),
        "ubicacion_id": str(ruta.camioneta_id),
    }
    (reingreso,) = entorno.movimientos_de_stock("ANULACION_VENTA")
    assert reingreso.jornada_id is None
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48
    assert entorno.venta(venta_id).estado == "ANULADA"
    (fila,) = entorno.auditoria_de(item.operation_id)
    assert fila.observacion == f"ubicación tomada por la jornada {jornada_de_pedro}"


def test_stk09_la_propia_jornada_en_rendicion_se_acepta_con_ubicacion_tomada(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Camioneta tomada por otro vendedor al sincronizar" (la propia en rendición)
    """Triangulación: la jornada del vendedor pasó a `EN_RENDICION` antes de sincronizar y la
    camioneta sigue tomada: se acepta solo con `UBICACION_TOMADA_AL_SINCRONIZAR` (nombra la propia
    jornada), reingreso sin jornada."""
    ruta = Ruta(entorno, estado_jornada="EN_RENDICION")
    venta_id = vender(ruta)

    item, resultado = anular(entorno, ruta, venta_id)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert _codigos(resultado) == ["UBICACION_TOMADA_AL_SINCRONIZAR"]
    (reingreso,) = entorno.movimientos_de_stock("ANULACION_VENTA")
    assert reingreso.jornada_id is None
    (fila,) = entorno.auditoria_de(item.operation_id)
    assert fila.observacion == f"ubicación tomada por la jornada {ruta.jornada_id}"
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48


def test_inv06_el_reenvio_de_una_anulacion_con_observaciones_no_registra_otra(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Reenvío de una anulación con observaciones"
    """INV-06, SYN-04: el reenvío del mismo `operation_id` trae las mismas observaciones y no se
    registra ninguna nueva."""
    ruta = Ruta(entorno, estado_jornada="LIBERADA")
    venta_id = vender(ruta)
    item, primero = anular(entorno, ruta, venta_id)
    antes = len(observaciones(entorno))

    segundo = lote(entorno, item)[item.operation_id]

    assert _codigos(primero) == ["JORNADA_LIBERADA"]
    assert (segundo.estado, _codigos(segundo)) == (primero.estado, _codigos(primero))
    assert len(observaciones(entorno)) == antes
    assert len(entorno.anulaciones_de_venta()) == 1
    assert len(entorno.auditoria_de(item.operation_id)) == 1


def test_permisos_de_anulador_no_incluyen_liberar_ubicacion() -> None:
    """Guarda del arnés: las pruebas de la ubicación tomada valen porque el usuario NO tiene
    `LIBERAR_UBICACION` (la excepción de toma sale del modo sin conexión, no del permiso)."""
    assert "LIBERAR_UBICACION" not in PERMISOS_DE_ANULADOR
