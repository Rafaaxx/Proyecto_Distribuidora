"""Change 25, tarea 4.1: `OBSERVACION_RESOLVER` por HTTP contra PostgreSQL real (spec
`sync/revision-de-observaciones`, requisito "Las observaciones se resuelven con un comentario y
sin tocar la operación"; `design.md` D1).

La concurrencia (dos personas a la vez) se prueba en el Lote 7 con commits reales.

Reglas citadas: SYN-08, INV-01, INV-02, INV-06, INV-21, SEG-06.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from revision_utiles import estados_de, sembrar_observaciones
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    Entorno,
    _con_op,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)

URL = "/api/v1/observaciones/resolucion"
REVISOR = frozenset({"REVISAR_OBSERVACIONES"})
COMENTARIO = "Se corrigió con un ajuste"


def _sembrar(entorno: Entorno, *codigos: str, **cambios: object):  # type: ignore[no-untyped-def]
    return sembrar_observaciones(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        codigos=codigos or ("STOCK_NEGATIVO", "STOCK_NEGATIVO"),
        **cambios,  # type: ignore[arg-type]
    )


def _cuerpo(ids: list[UUID], comentario: str = COMENTARIO) -> dict[str, object]:
    return {"observaciones": [str(id_) for id_ in ids], "comentario": comentario}


def _foto_de_la_operacion(sesion: Session, organizacion_id: UUID) -> dict[str, object]:
    """Todo lo que resolver NO puede tocar: comandos, ventas, libros y el código y detalle de las
    observaciones."""
    sesion.rollback()
    return {
        "comandos": sesion.execute(
            text(
                "SELECT id, estado, resultado::text, error_codigo FROM comando "
                "WHERE organizacion_id = :o AND tipo <> 'OBSERVACION_RESOLVER' ORDER BY id"
            ),
            {"o": organizacion_id},
        ).all(),
        "libros": [
            sesion.scalar(
                text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"),
                {"o": organizacion_id},
            )  # noqa: S608, E501
            for tabla in ("stock_movimiento", "cuenta_movimiento", "costo_producto_mov", "venta")
        ],
        "observaciones": sesion.execute(
            text(
                "SELECT id, comando_id, operacion_tipo, operacion_id, codigo, detalle::text "
                "FROM observacion WHERE organizacion_id = :o ORDER BY id"
            ),
            {"o": organizacion_id},
        ).all(),
    }


def test_resolver_los_avisos_de_una_venta_deja_quien_cuando_y_por_que_sin_tocar_la_operacion(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Resolver los avisos de una venta" (SYN-08)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    observado = _sembrar(entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    antes = _foto_de_la_operacion(sesion, entorno.org)

    respuesta = cliente.post(URL, json=_cuerpo(observado.observaciones), headers=_con_op(headers))

    assert respuesta.status_code == 200, respuesta.text
    assert sorted(respuesta.json()["observaciones"]) == sorted(
        str(id_) for id_ in observado.observaciones
    )
    sesion.rollback()
    filas = sesion.execute(
        text(
            "SELECT estado, resuelto_por_id, resuelto_en, comentario FROM observacion "
            "WHERE id = ANY(:ids)"
        ),
        {"ids": observado.observaciones},
    ).all()
    assert len(filas) == 2
    for fila in filas:
        assert fila.estado == "RESUELTA"
        assert fila.resuelto_por_id == entorno.usuario_id
        assert fila.resuelto_en is not None
        assert fila.comentario == COMENTARIO
    assert _foto_de_la_operacion(sesion, entorno.org) == antes


def test_el_comentario_se_guarda_sin_los_espacios_de_los_extremos(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    observado = _sembrar(entorno, "STOCK_NEGATIVO")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL, json=_cuerpo(observado.observaciones, "   Lo revisé   "), headers=_con_op(headers)
    )

    assert respuesta.status_code == 200, respuesta.text
    sesion.rollback()
    assert (
        sesion.scalar(
            text("SELECT comentario FROM observacion WHERE id = :i"),
            {"i": observado.observaciones[0]},
        )
        == "Lo revisé"
    )


def test_una_resolucion_en_bloque_resuelve_los_avisos_de_operaciones_distintas(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Resolución en bloque de varias operaciones" (INV-01)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    venta = _sembrar(entorno, "STOCK_NEGATIVO", "VENTA_SIN_COSTO")
    cobranza = _sembrar(
        entorno,
        "MEDIO_INACTIVO",
        operacion_tipo="COBRANZA",
        tipo_de_comando="COBRANZA_REGISTRAR",
    )
    todas = [*venta.observaciones, *cobranza.observaciones]
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(todas), headers=_con_op(headers))

    assert respuesta.status_code == 200, respuesta.text
    assert set(estados_de(sesion, todas).values()) == {"RESUELTA"}


def test_una_ya_resuelta_impide_toda_la_resolucion_y_se_nombra(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Una ya resuelta impide toda la resolución" (INV-01; `01` §18)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    observado = _sembrar(entorno, "STOCK_NEGATIVO", "VENTA_SIN_COSTO", "DESCUENTO_DIFIERE")
    headers = entorno.confirmar_y_entrar(cliente)
    ya_resuelta = observado.observaciones[1]
    primera = cliente.post(URL, json=_cuerpo([ya_resuelta]), headers=_con_op(headers))
    assert primera.status_code == 200, primera.text

    respuesta = cliente.post(URL, json=_cuerpo(observado.observaciones), headers=_con_op(headers))

    assert respuesta.status_code == 409
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "OBSERVACION_YA_RESUELTA"
    assert cuerpo["observaciones"] == [str(ya_resuelta)]
    estados = estados_de(sesion, observado.observaciones)
    assert estados[observado.observaciones[0]] == "PENDIENTE"
    assert estados[observado.observaciones[2]] == "PENDIENTE"
    assert estados[ya_resuelta] == "RESUELTA"


@pytest.mark.parametrize("comentario", ["", "    ", "x" * 501, "  " + "x" * 501 + "  "])
def test_un_comentario_vacio_o_demasiado_largo_se_rechaza_y_nada_cambia(
    cliente: TestClient, sesion: Session, comentario: str
) -> None:
    """Escenario "Comentario vacío o demasiado largo" (SYN-08)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    observado = _sembrar(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL, json=_cuerpo(observado.observaciones, comentario), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "COMENTARIO_INVALIDO"
    assert set(estados_de(sesion, observado.observaciones).values()) == {"PENDIENTE"}


def test_un_comentario_de_exactamente_500_caracteres_se_acepta(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    observado = _sembrar(entorno, "STOCK_NEGATIVO")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL, json=_cuerpo(observado.observaciones, "x" * 500), headers=_con_op(headers)
    )

    assert respuesta.status_code == 200, respuesta.text


def test_una_lista_vacia_repetida_o_de_mas_de_cien_se_rechaza_y_nada_cambia(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Lista vacía, repetida o de más de 100" (INV-01)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    observado = _sembrar(entorno)
    headers = entorno.confirmar_y_entrar(cliente)
    repetida = [observado.observaciones[0], observado.observaciones[0]]
    demasiadas = [uuid4() for _ in range(101)]

    for lista in ([], repetida, demasiadas):
        respuesta = cliente.post(URL, json=_cuerpo(lista), headers=_con_op(headers))

        assert respuesta.status_code == 422, respuesta.text
        assert respuesta.json()["codigo"] == "OBSERVACIONES_INVALIDAS"
    assert set(estados_de(sesion, observado.observaciones).values()) == {"PENDIENTE"}


def test_cien_observaciones_distintas_son_el_maximo_aceptado(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    observado = _sembrar(entorno, *(["STOCK_NEGATIVO"] * 100))
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(observado.observaciones), headers=_con_op(headers))

    assert respuesta.status_code == 200, respuesta.text
    assert len(respuesta.json()["observaciones"]) == 100


def test_una_observacion_de_otra_organizacion_responde_404_y_no_se_resuelve_ninguna(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Observación de otra organización" (INV-21, INV-02)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    propia = _sembrar(entorno, "STOCK_NEGATIVO")
    otra_org = crear_organizacion(sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(sesion, otra_org, permisos=REVISOR)
    ajena = sembrar_observaciones(
        sesion,
        otra_org,
        usuario_id=usuario,
        dispositivo_id=dispositivo,
        codigos=("STOCK_NEGATIVO",),
    )
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        URL,
        json=_cuerpo([*propia.observaciones, *ajena.observaciones]),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert set(estados_de(sesion, [*propia.observaciones, *ajena.observaciones]).values()) == {
        "PENDIENTE"
    }


def test_una_observacion_inexistente_responde_404(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo([uuid4()]), headers=_con_op(headers))

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


def test_sin_el_permiso_responde_403_y_nada_cambia(cliente: TestClient, sesion: Session) -> None:
    """Escenario "Sin permiso" (SEG-06; `01` §19): el Vendedor no tiene `REVISAR_OBSERVACIONES`."""
    entorno = Entorno(sesion, permisos=frozenset({"VENDER"}))
    observado = _sembrar(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(observado.observaciones), headers=_con_op(headers))

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
    assert set(estados_de(sesion, observado.observaciones).values()) == {"PENDIENTE"}


def test_sin_operation_id_se_rechaza_con_400(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    observado = _sembrar(entorno)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.post(URL, json=_cuerpo(observado.observaciones), headers=headers)

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


def test_el_doble_envio_devuelve_el_resultado_original_y_audita_una_sola_vez(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Doble envío de la resolución" (SYN-02, INV-06)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    observado = _sembrar(entorno)
    headers = _con_op(entorno.confirmar_y_entrar(cliente))

    primera = cliente.post(URL, json=_cuerpo(observado.observaciones), headers=headers)
    segunda = cliente.post(URL, json=_cuerpo(observado.observaciones), headers=headers)

    assert primera.status_code == 200, primera.text
    assert segunda.status_code == 200, segunda.text
    assert segunda.json() == primera.json()
    sesion.rollback()
    auditorias = sesion.scalar(
        text("SELECT count(*) FROM auditoria WHERE organizacion_id = :o AND operation_id = :op"),
        {"o": entorno.org, "op": UUID(headers["Operation-Id"])},
    )
    assert auditorias == 1


def test_el_mismo_operation_id_con_otro_contenido_es_un_conflicto(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    observado = _sembrar(entorno)
    headers = _con_op(entorno.confirmar_y_entrar(cliente))
    primera = cliente.post(URL, json=_cuerpo(observado.observaciones), headers=headers)
    assert primera.status_code == 200, primera.text

    segunda = cliente.post(
        URL, json=_cuerpo(observado.observaciones, "Otro comentario"), headers=headers
    )

    assert segunda.status_code == 409
    assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"
