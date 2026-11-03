"""Change 22c, tarea 4.1 (spec `sync/lote-de-comandos`, requisito "Una venta o cobranza sin conexión
nunca se rechaza por reglas de negocio"; `design.md` D8): la matriz de INV-17, por el lote y con
PostgreSQL real.

Una prueba de CARACTERIZACIÓN: reúne en un solo lugar, como la lista de SYN-05, una regla por caso
para la venta (`VENTA_CONFIRMAR`) y para la cobranza (`COBRANZA_REGISTRAR`) en modo `OFFLINE`; un
caso con todas a la vez; el control que sí se rechaza (`TOTALES_INCONSISTENTES`, SYN-06) y el doble
envío de una operación observada. Los detalles de cada observación ya los fijan las pruebas de
cada change (`test_ventas_offline*.py`, `test_lote_jornada_offline.py`); acá solo importa que NUNCA
se rechace y que quede la observación de la regla incumplida.

Reglas citadas: INV-17, SYN-05, SYN-06, SYN-07, SYN-10, INV-06.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from cobranzas_utiles import MOMENTO, RELOJ, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_offline import (
    Ruta,
    _codigos,
    _con_version_nueva,
    _observaciones,
    _producto_con_precio,
    _rechazada,
    lote,
)
from test_ventas_offline_descuentos_credito import LIMITE_REAL, _credito_con_exceso, _de_volumen
from ventas_confirmar_utiles import PERMISOS_DE_VENTA, EntornoVenta

from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

SOLO_COBRANZA = frozenset({"REGISTRAR_COBRANZA"})

# Un armado devuelve el entorno, la ruta y el contenido de la venta sin conexión que incumple una
# regla de SYN-05.
Armado = tuple[EntornoVenta, Ruta, dict[str, Any]]


# --- armado de la venta: una regla por función ---------------------------------------------------


def _venta_limpia(sesion: Session, **opciones: Any) -> tuple[EntornoVenta, Ruta]:
    entorno = EntornoVenta(sesion, **opciones)
    return entorno, Ruta(entorno)


def _stock(sesion: Session) -> Armado:
    entorno = EntornoVenta(sesion)
    ruta = Ruta(entorno, stock=5)
    return entorno, ruta, ruta.contenido(entorno.linea(cantidad=8))


def _credito(sesion: Session) -> Armado:
    entorno, ruta = _venta_limpia(sesion)
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="AUTORIZAR")
    return entorno, ruta, ruta.contenido(credito=_credito_con_exceso(entorno))


def _lista(sesion: Session) -> Armado:
    entorno = EntornoVenta(sesion)
    _con_version_nueva(entorno)
    ruta = Ruta(entorno)
    return entorno, ruta, ruta.contenido(motivo_lista_id=str(entorno.motivo_lista_id))


def _descuentos(sesion: Session) -> Armado:
    entorno = EntornoVenta(sesion)
    entorno.crear_regla()
    ruta = Ruta(entorno, stock=200)
    return entorno, ruta, _de_volumen(ruta, None)


def _cliente(estado: str) -> Callable[[Session], Armado]:
    def armar(sesion: Session) -> Armado:
        entorno, ruta = _venta_limpia(sesion)
        entorno.actualizar_cliente(entorno.cliente_id, estado=estado)
        return entorno, ruta, ruta.contenido()

    return armar


def _permiso_revocado(sesion: Session) -> Armado:
    entorno, ruta = _venta_limpia(sesion, permisos=SOLO_COBRANZA)
    return entorno, ruta, ruta.contenido()


def _medio_desactivado(sesion: Session) -> Armado:
    entorno, ruta = _venta_limpia(sesion)
    billetera = entorno.crear_medio("Billetera", requiere_referencia=False)
    sesion.commit()
    entorno.desactivar_medio(billetera)
    return entorno, ruta, ruta.contenido(cobranza=entorno.cobranza((billetera, "5000.00", None)))


def _referencia_faltante(sesion: Session) -> Armado:
    entorno, ruta = _venta_limpia(sesion)
    cobranza = entorno.cobranza((entorno.transferencia_id, "5000.00", None))
    return entorno, ruta, ruta.contenido(cobranza=cobranza)


def _desactivar(tabla: str) -> Callable[[Session], Armado]:
    def armar(sesion: Session) -> Armado:
        entorno, ruta = _venta_limpia(sesion)
        id_ = entorno.vino_id if tabla == "producto" else entorno.botella_id
        sesion.execute(
            text(f"UPDATE {tabla} SET activo = false WHERE organizacion_id = :o AND id = :i"),
            {"o": entorno.org, "i": id_},
        )
        sesion.commit()
        return entorno, ruta, ruta.contenido()

    return armar


def _producto_desactivado_con_otro(sesion: Session) -> Armado:
    entorno = EntornoVenta(sesion)
    _producto_con_precio(entorno, "Vino B", "24000.00")
    return _desactivar("producto")(sesion)


def _ubicacion_tomada(sesion: Session) -> Armado:
    entorno = EntornoVenta(sesion)
    ruta = Ruta(entorno, estado_jornada="EN_RENDICION")
    return entorno, ruta, ruta.contenido()


def _motivo_dado_de_baja(sesion: Session) -> Armado:
    entorno = EntornoVenta(sesion)
    _con_version_nueva(entorno)
    inactivo = entorno.crear_motivo("LISTA_ANTERIOR", "Motivo viejo", activo=False)
    sesion.commit()
    ruta = Ruta(entorno)
    return entorno, ruta, ruta.contenido(motivo_lista_id=str(inactivo))


# (armado, observaciones que debe dejar; vacío = se acepta sin observación)
REGLAS_DE_LA_VENTA: dict[str, tuple[Callable[[Session], Armado], set[str]]] = {
    "stock": (_stock, {"STOCK_NEGATIVO"}),
    "credito": (_credito, {"EXCESO_CREDITO_AUTORIZADO_OFFLINE"}),
    "lista": (_lista, {"LISTA_NO_VIGENTE"}),
    "descuentos": (_descuentos, {"DESCUENTO_DIFIERE"}),
    "cliente_suspendido": (_cliente("SUSPENDIDO"), {"CLIENTE_NO_HABILITADO"}),
    "cliente_inactivo": (_cliente("INACTIVO"), {"CLIENTE_NO_HABILITADO"}),
    "permiso_revocado": (_permiso_revocado, {"PERMISO_REVOCADO"}),
    "medio_desactivado": (_medio_desactivado, {"MEDIO_INACTIVO"}),
    "referencia_faltante": (_referencia_faltante, {"REFERENCIA_FALTANTE"}),
    "producto_desactivado": (_desactivar("producto"), set()),
    "presentacion_desactivada": (_desactivar("presentacion"), set()),
    "ubicacion_tomada": (_ubicacion_tomada, {"UBICACION_TOMADA_AL_SINCRONIZAR"}),
    # El motivo dado de baja no tiene observación propia; lo que queda es la de la lista.
    "motivo_dado_de_baja": (_motivo_dado_de_baja, {"LISTA_NO_VIGENTE"}),
}


@pytest.mark.parametrize("regla", sorted(REGLAS_DE_LA_VENTA))
def test_inv17_una_venta_sin_conexion_que_incumple_una_regla_se_acepta(
    db_session: Session, regla: str
) -> None:
    """Escenario "Cada regla por separado": la venta de Juan incumple UNA regla de SYN-05 y llega
    por el lote: se acepta (con la observación de esa regla, o sin ninguna si no la tiene), deja
    su venta y su movimiento de stock, y nunca queda rechazada."""
    armar, esperadas = REGLAS_DE_LA_VENTA[regla]
    entorno, ruta, contenido = armar(db_session)
    item = ruta.item(contenido)

    resultado = lote(entorno, item)[item.operation_id]

    assert resultado.error_codigo is None
    assert resultado.estado == ("ACEPTADO_CON_OBSERVACIONES" if esperadas else "ACEPTADO")
    assert set(_codigos(entorno)) == esperadas
    assert {o.codigo for o in resultado.observaciones} == esperadas
    assert len(entorno.ventas()) == 1
    assert len(entorno.movimientos_de_stock()) >= 1


def test_inv17_la_matriz_cubre_cada_regla_de_syn05_de_la_venta() -> None:
    """La lista de la spec: stock, crédito, lista, descuentos, cliente suspendido e inactivo,
    permiso revocado, medio desactivado, referencia faltante, producto y presentación
    desactivados, ubicación tomada y motivo dado de baja."""
    assert set(REGLAS_DE_LA_VENTA) == {
        "stock",
        "credito",
        "lista",
        "descuentos",
        "cliente_suspendido",
        "cliente_inactivo",
        "permiso_revocado",
        "medio_desactivado",
        "referencia_faltante",
        "producto_desactivado",
        "presentacion_desactivada",
        "ubicacion_tomada",
        "motivo_dado_de_baja",
    }


def test_inv17_una_venta_que_incumple_todas_las_reglas_a_la_vez_se_acepta_con_todas(
    db_session: Session,
) -> None:
    """Escenario "Todas a la vez": stock, crédito, lista, cliente suspendido, permiso, medio
    desactivado y referencia faltante en la misma venta con cobranza. Se acepta, el stock y el
    saldo quedan registrados y todas las observaciones salen."""
    entorno = EntornoVenta(db_session, permisos=SOLO_COBRANZA)
    entorno.actualizar_cliente(entorno.cliente_id, estado="SUSPENDIDO")
    entorno.datos_de_credito(limite=LIMITE_REAL, politica="AUTORIZAR")
    _con_version_nueva(entorno)
    billetera = entorno.crear_medio("Billetera", requiere_referencia=False)
    db_session.commit()
    ruta = Ruta(entorno, stock=5)
    entorno.desactivar_medio(billetera)
    cobranza = entorno.cobranza(
        (billetera, "5000.00", None), (entorno.transferencia_id, "5000.00", None)
    )
    item = ruta.item(
        ruta.contenido(
            entorno.linea(cantidad=8),
            cobranza=cobranza,
            credito=_credito_con_exceso(entorno),
            motivo_lista_id=str(entorno.motivo_lista_id),
        )
    )

    resultado = lote(entorno, item)[item.operation_id]

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert set(_codigos(entorno)) >= {
        "STOCK_NEGATIVO",
        "EXCESO_CREDITO_AUTORIZADO_OFFLINE",
        "LISTA_NO_VIGENTE",
        "CLIENTE_NO_HABILITADO",
        "PERMISO_REVOCADO",
        "MEDIO_INACTIVO",
        "REFERENCIA_FALTANTE",
    }
    assert len(entorno.ventas()) == 1
    assert len(entorno.cobranzas()) == 1
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == -3
    # 8 botellas a $12.500 la caja de 6 (16.666,67) menos los $10.000 cobrados.
    assert entorno.saldo() == Decimal("150000.00") + Decimal("16666.67") - Decimal("10000.00")


# --- la cobranza sin conexión ------------------------------------------------------------------


def _cobranza_en_el_lote(
    entorno: Entorno, contenido: dict[str, Any]
) -> sync_service.ResultadoItemLote:
    item = ItemLote(
        operation_id=uuid4(),
        tipo="COBRANZA_REGISTRAR",
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=contenido,
        jornada_id=entorno.crear_jornada(),
    )
    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )
    entorno.sesion.rollback()
    return resultado


def _cobranza_consumidor_final(entorno: Entorno) -> dict[str, Any]:
    """En la cobranza solo el consumidor final observa `CLIENTE_NO_HABILITADO` (change 17, D13);
    un cliente inactivo se acepta sin observación (ver el caso siguiente)."""
    cliente = entorno.crear_cliente(nombre="Consumidor final", es_consumidor_final=True)
    entorno.sesion.commit()
    return entorno.contenido(cliente_id=str(cliente))


def _cobranza_cliente_inactivo(entorno: Entorno) -> dict[str, Any]:
    cliente = entorno.crear_cliente(nombre="Almacén Don Pedro", estado="INACTIVO")
    entorno.sesion.commit()
    return entorno.contenido(cliente_id=str(cliente))


def _cobranza_medio_desactivado(entorno: Entorno) -> dict[str, Any]:
    billetera = entorno.crear_medio("Billetera", requiere_referencia=False)
    entorno.sesion.commit()
    entorno.desactivar_medio(billetera)
    return entorno.contenido(importe="5000.00", medios=entorno.medios((billetera, "5000.00", None)))


def _cobranza_sin_referencia(entorno: Entorno) -> dict[str, Any]:
    return entorno.contenido(
        importe="5000.00", medios=entorno.medios((entorno.transferencia_id, "5000.00", None))
    )


COBRANZA: dict[str, tuple[Callable[[Entorno], dict[str, Any]], set[str]]] = {
    "consumidor_final": (_cobranza_consumidor_final, {"CLIENTE_NO_HABILITADO"}),
    # Un cliente inactivo no deja observación en la cobranza: se acepta igual (INV-17).
    "cliente_inactivo": (_cobranza_cliente_inactivo, set()),
    "medio_desactivado": (_cobranza_medio_desactivado, {"MEDIO_INACTIVO"}),
    "referencia_faltante": (_cobranza_sin_referencia, {"REFERENCIA_FALTANTE"}),
}


@pytest.mark.parametrize("regla", sorted(COBRANZA))
def test_inv17_una_cobranza_sin_conexion_que_incumple_una_regla_se_acepta(
    db_session: Session, regla: str
) -> None:
    """Escenario "Cobranza sin conexión" (una regla por caso): se acepta con la observación."""
    armar, esperadas = COBRANZA[regla]
    entorno = Entorno(db_session)

    resultado = _cobranza_en_el_lote(entorno, armar(entorno))

    assert resultado.error_codigo is None
    assert resultado.estado == ("ACEPTADO_CON_OBSERVACIONES" if esperadas else "ACEPTADO")
    assert {o.codigo for o in resultado.observaciones} == esperadas
    assert len(entorno.cobranzas()) == 1


def test_inv17_una_cobranza_de_quien_perdio_el_permiso_se_acepta_con_permiso_revocado(
    db_session: Session,
) -> None:
    entorno = Entorno(db_session, permisos=frozenset({"VENDER"}))

    resultado = _cobranza_en_el_lote(entorno, entorno.contenido())

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert {o.codigo for o in resultado.observaciones} == {"PERMISO_REVOCADO"}
    assert len(entorno.cobranzas()) == 1


def test_inv17_la_cobranza_con_consumidor_final_medio_desactivado_y_sin_permiso(
    db_session: Session,
) -> None:
    """Escenario "Cobranza sin conexión": cliente no habilitado (el consumidor final, único que la
    cobranza observa), medio desactivado y un usuario que perdió `REGISTRAR_COBRANZA`:
    `CLIENTE_NO_HABILITADO`, `MEDIO_INACTIVO` y `PERMISO_REVOCADO`."""
    entorno = Entorno(db_session, permisos=frozenset({"VENDER"}))
    cliente = entorno.crear_cliente(nombre="Consumidor final", es_consumidor_final=True)
    billetera = entorno.crear_medio("Billetera", requiere_referencia=False)
    db_session.commit()
    entorno.desactivar_medio(billetera)
    contenido = entorno.contenido(
        cliente_id=str(cliente),
        importe="5000.00",
        medios=entorno.medios((billetera, "5000.00", None)),
    )

    resultado = _cobranza_en_el_lote(entorno, contenido)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert {o.codigo for o in resultado.observaciones} == {
        "CLIENTE_NO_HABILITADO",
        "MEDIO_INACTIVO",
        "PERMISO_REVOCADO",
    }


# --- lo que sí se rechaza y el doble envío -------------------------------------------------------


def test_syn06_un_comando_malformado_si_se_rechaza_con_totales_inconsistentes(
    db_session: Session,
) -> None:
    """Escenario "Un comando malformado sí se rechaza": el bruto enviado no es el del motor. Es el
    límite de INV-17: solo SYN-06 rechaza."""
    entorno, ruta = _venta_limpia(db_session)
    item = ruta.item(ruta.contenido(entorno.linea(bruto="31251.00")))

    resultado = lote(entorno, item)[item.operation_id]

    _rechazada(resultado, "TOTALES_INCONSISTENTES", item, entorno)
    assert resultado.observaciones == ()
    assert entorno.ventas() == []


def test_inv06_el_doble_envio_de_una_venta_observada_baja_el_stock_una_sola_vez(
    db_session: Session,
) -> None:
    """Escenario "Doble envío de una venta observada": `STOCK_NEGATIVO` (8 sobre 5) enviada dos
    veces con el mismo `operation_id`: el mismo resultado, una observación y el stock en -3."""
    entorno, ruta, contenido = _stock(db_session)
    item = ruta.item(contenido)

    primero = lote(entorno, item)[item.operation_id]
    segundo = lote(entorno, item)[item.operation_id]

    assert (primero.estado, segundo.estado) == ("ACEPTADO_CON_OBSERVACIONES",) * 2
    assert segundo.observaciones == primero.observaciones
    assert len(_observaciones(entorno)) == 1
    assert len(entorno.ventas()) == 1
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == -3


def test_inv17_el_permiso_de_venta_completo_no_deja_permiso_revocado(db_session: Session) -> None:
    """Triangulación de control: con los permisos vigentes la misma venta limpia no observa nada,
    así que las observaciones de la matriz se deben a la regla incumplida y no al armado."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_VENTA)
    ruta = Ruta(entorno)
    item = ruta.item()

    resultado = lote(entorno, item)[item.operation_id]

    assert (resultado.estado, resultado.observaciones) == ("ACEPTADO", ())
    assert _codigos(entorno) == []
