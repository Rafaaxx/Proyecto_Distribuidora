"""Change 25, tarea 6.1: `GET /api/v1/observaciones`, la bandeja por operación (spec
`sync/revision-de-observaciones`, requisito "La bandeja muestra las observaciones por operación";
`design.md` D3).

Reglas citadas: SYN-07, SYN-08, CRE-09, DSC-09, INV-21, INV-02, SEG-06.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from fastapi.testclient import TestClient
from revision_utiles import sembrar_observaciones
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    Entorno,
    _con_op,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)
from ventas_utiles import sembrar_venta_sql

URL = "/api/v1/observaciones"
REVISOR = frozenset({"REVISAR_OBSERVACIONES"})
LLEGADA = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def _sembrar(entorno: Entorno, *codigos: str, **cambios: object):  # type: ignore[no-untyped-def]
    cambios.setdefault("usuario_id", entorno.usuario_id)
    cambios.setdefault("dispositivo_id", entorno.dispositivo_id)
    return sembrar_observaciones(
        entorno.sesion,
        entorno.org,
        codigos=codigos or ("STOCK_NEGATIVO",),
        **cambios,  # type: ignore[arg-type]
    )


def _leer(cliente_http: TestClient, headers: dict[str, str], **filtros: object):  # type: ignore[no-untyped-def]
    respuesta = cliente_http.get(URL, params=filtros, headers=headers)  # type: ignore[arg-type]
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _resolver(
    cliente_http: TestClient, headers: dict[str, str], ids: list[UUID], comentario: str = "Revisado"
) -> None:
    respuesta = cliente_http.post(
        f"{URL}/resolucion",
        json={"observaciones": [str(i) for i in ids], "comentario": comentario},
        headers=_con_op(headers),
    )
    assert respuesta.status_code == 200, respuesta.text


def test_una_venta_con_varios_avisos_es_una_sola_entrada(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Una venta con varios avisos es una sola entrada" (SYN-07, SYN-08)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    venta = _sembrar(entorno, "STOCK_NEGATIVO", "STOCK_NEGATIVO", "DESCUENTO_DIFIERE")
    headers = entorno.confirmar_y_entrar(cliente)

    cuerpo = _leer(cliente, headers)

    assert [(e["operacion_tipo"], e["operacion_id"]) for e in cuerpo["items"]] == [
        ("VENTA", str(venta.operacion_id))
    ]
    entrada = cuerpo["items"][0]
    assert entrada["estado"] == "PENDIENTE"
    assert sorted(o["codigo"] for o in entrada["observaciones"]) == [
        "DESCUENTO_DIFIERE",
        "STOCK_NEGATIVO",
        "STOCK_NEGATIVO",
    ]
    assert {o["id"] for o in entrada["observaciones"]} == {str(i) for i in venta.observaciones}
    assert cuerpo["cursor_siguiente"] is None


def test_la_entrada_trae_quien_registro_donde_y_cuando_y_el_resumen_de_la_operacion(
    cliente: TestClient, sesion: Session
) -> None:
    """D3 y D4: tipo, resumen, usuario, dispositivo, jornada, modo y momentos."""
    entorno = Entorno(sesion, permisos=REVISOR)
    cliente_id = crear_cliente(sesion, entorno.org, nombre="Kiosco La Esquina")
    venta_sembrada = sembrar_venta_sql(
        sesion,
        entorno.org,
        cliente_id=cliente_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        numero="V01-000777",
        total="37500.00",
        total_neto="37500.00",
    )
    jornada = crear_jornada_sql(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(sesion, entorno.org, tipo="VEHICULO", requiere_toma=True),
    )
    _sembrar(
        entorno,
        "STOCK_NEGATIVO",
        operacion_id=venta_sembrada.venta_id,
        jornada_id=jornada,
        registered_at=LLEGADA,
    )
    headers = entorno.confirmar_y_entrar(cliente)

    entrada = _leer(cliente, headers)["items"][0]

    assert entrada["resumen"]["titulo"] == "Venta V01-000777"
    assert entrada["resumen"]["tercero"] == "Kiosco La Esquina"
    assert entrada["resumen"]["total"] == "37500.00"
    assert entrada["usuario_id"] == str(entorno.usuario_id)
    assert entrada["usuario_nombre"] == "Persona de prueba"
    assert entrada["dispositivo_id"] == str(entorno.dispositivo_id)
    assert entrada["jornada_id"] == str(jornada)
    assert entrada["modo"] == "OFFLINE"
    assert datetime.fromisoformat(entrada["registered_at"]) == LLEGADA
    assert datetime.fromisoformat(entrada["occurred_at"]) == LLEGADA


def test_una_operacion_que_no_se_encuentra_tiene_resumen_nulo(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    _sembrar(entorno, "STOCK_NEGATIVO")
    headers = entorno.confirmar_y_entrar(cliente)

    entrada = _leer(cliente, headers)["items"][0]

    assert entrada["resumen"] is None


def test_el_detalle_de_los_descuentos_y_del_credito_llega_completo(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "El detalle de los descuentos y del crédito" (DSC-09, CRE-09, ADR-055)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    autorizador = str(uuid4())
    detalles: tuple[dict[str, object] | None, ...] = (
        {"linea_id": str(uuid4()), "causa": "TOPE", "porcentaje": "0.150000", "tope": "0.100000"},
        {
            "tipo": "DESCUENTO",
            "resolucion": "PIN",
            "autorizador_id": autorizador,
            "conserva_permiso": False,
        },
        {
            "dispositivo": {"limite": "100000.00", "disponible": "20000.00", "exceso": "0.00"},
            "servidor": {"limite": "100000.00", "disponible": "-5000.00", "exceso": "5000.00"},
        },
    )
    _sembrar(
        entorno,
        "DESCUENTO_DIFIERE",
        "AUTORIZACION_OFFLINE",
        "EXCESO_CREDITO_DETECTADO_SYNC",
        detalles=detalles,
    )
    headers = entorno.confirmar_y_entrar(cliente)

    observaciones = _leer(cliente, headers)["items"][0]["observaciones"]

    por_codigo = {o["codigo"]: o["detalle"] for o in observaciones}
    assert por_codigo["DESCUENTO_DIFIERE"] == detalles[0]
    assert por_codigo["AUTORIZACION_OFFLINE"] == detalles[1]
    assert por_codigo["EXCESO_CREDITO_DETECTADO_SYNC"] == detalles[2]


def test_cobranza_jornada_y_consumidor_final_se_filtran_por_su_codigo(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Códigos de cobranza, de jornada y de consumidor final" (SYN-07, ADR-052,
    ADR-054, ADR-068)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    cobranza = _sembrar(
        entorno,
        "MEDIO_INACTIVO",
        "REFERENCIA_FALTANTE",
        operacion_tipo="COBRANZA",
        tipo_de_comando="COBRANZA_REGISTRAR",
        detalles=({"medio": "Transferencia", "importe": "20000.00"}, {"medio": "Cheque"}),
    )
    consumidor = _sembrar(
        entorno,
        "CONSUMIDOR_FINAL_CON_DEUDA",
        detalles=({"total": "9000.00", "cobrado": "4000.00"},),
    )
    rendida = _sembrar(
        entorno,
        "JORNADA_RENDIDA",
        detalles=({"jornada_id": str(uuid4()), "rendida_en": "2026-11-05T10:00:00+00:00"},),
    )
    headers = entorno.confirmar_y_entrar(cliente)

    for codigo, esperado in (
        ("MEDIO_INACTIVO", cobranza),
        ("REFERENCIA_FALTANTE", cobranza),
        ("CONSUMIDOR_FINAL_CON_DEUDA", consumidor),
        ("JORNADA_RENDIDA", rendida),
    ):
        items = _leer(cliente, headers, codigo=codigo)["items"]

        assert [i["operacion_id"] for i in items] == [str(esperado.operacion_id)], codigo
    items = _leer(cliente, headers, codigo=["MEDIO_INACTIVO", "JORNADA_RENDIDA"])["items"]
    assert {i["operacion_id"] for i in items} == {
        str(cobranza.operacion_id),
        str(rendida.operacion_id),
    }


def test_filtrar_por_un_codigo_igual_muestra_todos_los_avisos_de_la_operacion(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    _sembrar(entorno, "STOCK_NEGATIVO", "VENTA_SIN_COSTO")
    headers = entorno.confirmar_y_entrar(cliente)

    items = _leer(cliente, headers, codigo="VENTA_SIN_COSTO")["items"]

    assert sorted(o["codigo"] for o in items[0]["observaciones"]) == [
        "STOCK_NEGATIVO",
        "VENTA_SIN_COSTO",
    ]


def test_filtro_por_jornada_por_vendedor_por_tipo_y_por_fechas(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Filtro por jornada y por vendedor" (SYN-07)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    otro_usuario, otro_dispositivo = crear_usuario_y_dispositivo(sesion, entorno.org)
    ubicacion = crear_ubicacion_sql(sesion, entorno.org, tipo="VEHICULO", requiere_toma=True)
    jornada = crear_jornada_sql(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=ubicacion,
    )
    de_juan = _sembrar(entorno, "STOCK_NEGATIVO", jornada_id=jornada, registered_at=LLEGADA)
    del_otro = _sembrar(
        entorno,
        "STOCK_NEGATIVO",
        usuario_id=otro_usuario,
        dispositivo_id=otro_dispositivo,
        registered_at=LLEGADA + timedelta(hours=2),
    )
    cobranza = _sembrar(
        entorno,
        "MEDIO_INACTIVO",
        operacion_tipo="COBRANZA",
        tipo_de_comando="COBRANZA_REGISTRAR",
        registered_at=LLEGADA + timedelta(days=2),
    )
    headers = entorno.confirmar_y_entrar(cliente)

    def _ids(**filtros: object) -> set[str]:
        return {i["operacion_id"] for i in _leer(cliente, headers, **filtros)["items"]}

    assert _ids(jornada_id=str(jornada)) == {str(de_juan.operacion_id)}
    assert _ids(usuario_id=str(otro_usuario)) == {str(del_otro.operacion_id)}
    assert _ids(tipo="COBRANZA") == {str(cobranza.operacion_id)}
    assert _ids(desde=(LLEGADA + timedelta(hours=1)).isoformat()) == {
        str(del_otro.operacion_id),
        str(cobranza.operacion_id),
    }
    assert _ids(hasta=(LLEGADA + timedelta(hours=1)).isoformat()) == {str(de_juan.operacion_id)}
    assert _ids(usuario_id=str(otro_usuario), tipo="COBRANZA") == set()


def test_otra_organizacion_no_aparece(cliente: TestClient, sesion: Session) -> None:
    """Escenario "Otra organización no aparece" (INV-21, INV-02)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    propia = _sembrar(entorno, "STOCK_NEGATIVO")
    otra_org = crear_organizacion(sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(sesion, otra_org)
    sembrar_observaciones(
        sesion,
        otra_org,
        usuario_id=usuario,
        dispositivo_id=dispositivo,
        codigos=("STOCK_NEGATIVO",),
    )
    headers = entorno.confirmar_y_entrar(cliente)

    items = _leer(cliente, headers, estado="TODAS")["items"]

    assert [i["operacion_id"] for i in items] == [str(propia.operacion_id)]


def test_sin_el_permiso_no_se_lee_la_bandeja(cliente: TestClient, sesion: Session) -> None:
    """Escenario "Sin permiso no se lee la bandeja" (`01` §19)."""
    entorno = Entorno(sesion, permisos=frozenset({"VENDER"}))
    _sembrar(entorno, "STOCK_NEGATIVO")
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get(URL, headers=headers)

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def test_el_estado_decide_entre_pendientes_resueltas_y_todas(
    cliente: TestClient, sesion: Session
) -> None:
    """Una operación es `PENDIENTE` si tiene al menos un aviso pendiente; `RESUELTA` solo si
    están todos resueltos. Las resueltas muestran quién, cuándo y el comentario."""
    entorno = Entorno(sesion, permisos=REVISOR)
    pendiente = _sembrar(entorno, "STOCK_NEGATIVO")
    mitad = _sembrar(entorno, "STOCK_NEGATIVO", "VENTA_SIN_COSTO")
    resuelta = _sembrar(entorno, "MEDIO_INACTIVO", operacion_tipo="COBRANZA")
    headers = entorno.confirmar_y_entrar(cliente)
    _resolver(cliente, headers, [mitad.observaciones[0]])
    _resolver(cliente, headers, resuelta.observaciones, "Ya hablé con el cliente")

    def _ids(**filtros: object) -> set[str]:
        return {i["operacion_id"] for i in _leer(cliente, headers, **filtros)["items"]}

    assert _ids() == {str(pendiente.operacion_id), str(mitad.operacion_id)}
    assert _ids(estado="PENDIENTE") == _ids()
    assert _ids(estado="RESUELTA") == {str(resuelta.operacion_id)}
    assert _ids(estado="TODAS") == {
        str(pendiente.operacion_id),
        str(mitad.operacion_id),
        str(resuelta.operacion_id),
    }
    entrada = next(i for i in _leer(cliente, headers, estado="RESUELTA")["items"])
    observacion = entrada["observaciones"][0]
    assert entrada["estado"] == "RESUELTA"
    assert observacion["estado"] == "RESUELTA"
    assert observacion["comentario"] == "Ya hablé con el cliente"
    assert observacion["resuelto_por_id"] == str(entorno.usuario_id)
    assert observacion["resuelto_por_nombre"] == "Persona de prueba"
    assert observacion["resuelto_en"] is not None
    parcial = next(
        i for i in _leer(cliente, headers)["items"] if i["operacion_id"] == str(mitad.operacion_id)
    )
    assert parcial["estado"] == "PENDIENTE"
    assert sorted(o["estado"] for o in parcial["observaciones"]) == ["PENDIENTE", "RESUELTA"]


def test_la_pagina_va_de_la_llegada_mas_reciente_a_la_mas_antigua_y_sigue_por_cursor(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    operaciones = [
        _sembrar(entorno, "STOCK_NEGATIVO", registered_at=LLEGADA + timedelta(minutes=minuto))
        for minuto in range(5)
    ]
    esperado = [str(o.operacion_id) for o in reversed(operaciones)]
    headers = entorno.confirmar_y_entrar(cliente)

    primera = _leer(cliente, headers, limite=2)
    segunda = _leer(cliente, headers, limite=2, cursor=primera["cursor_siguiente"])
    tercera = _leer(cliente, headers, limite=2, cursor=segunda["cursor_siguiente"])

    assert [i["operacion_id"] for i in primera["items"]] == esperado[0:2]
    assert [i["operacion_id"] for i in segunda["items"]] == esperado[2:4]
    assert [i["operacion_id"] for i in tercera["items"]] == esperado[4:5]
    assert tercera["cursor_siguiente"] is None


def test_un_cursor_ilegible_o_un_limite_fuera_de_rango_se_rechazan(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    headers = entorno.confirmar_y_entrar(cliente)

    ilegible = cliente.get(URL, params={"cursor": "basura"}, headers=headers)
    sin_limite = cliente.get(URL, params={"limite": 0}, headers=headers)
    demasiado = cliente.get(URL, params={"limite": 201}, headers=headers)

    assert ilegible.status_code == 422
    assert ilegible.json()["codigo"] == "CURSOR_INVALIDO"
    assert sin_limite.status_code == 422
    assert demasiado.status_code == 422
