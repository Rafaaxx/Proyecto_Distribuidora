"""Change 25, lote extra (2026-11-06, D3/D12): la bandeja trae en el servidor los nombres que el
detalle solo nombra por id: autorizador, producto y número de línea, y el vendedor de la jornada que
tenía la ubicación. Una consulta por tipo de entidad para toda la página;
nunca de otra organización.

Reglas citadas: SYN-07, SYN-08, INV-21.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from uuid import UUID, uuid4

from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from fastapi.testclient import TestClient
from revision_utiles import sembrar_observaciones
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_producto_sql, crear_ubicacion_sql
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    Entorno,
    cliente,
    sesion,
)
from ventas_utiles import sembrar_venta_sql

URL = "/api/v1/observaciones"
REVISOR = frozenset({"REVISAR_OBSERVACIONES"})
SIN_REFERENCIA = "(no existe)"

Observacion = dict[str, object]


def _nombrar_usuario(sesion: Session, usuario_id: UUID, nombre: str) -> None:
    sesion.execute(
        text("UPDATE usuario SET nombre = :n WHERE id = :id"), {"n": nombre, "id": usuario_id}
    )


def _bandeja(
    cliente_http: TestClient,
    entorno: Entorno,
    codigos: tuple[str, ...],
    detalles: tuple[dict[str, object] | None, ...],
    **cambios: object,
) -> list[Observacion]:
    sembrar_observaciones(
        entorno.sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        codigos=codigos,
        detalles=detalles,
        **cambios,  # type: ignore[arg-type]
    )
    headers = entorno.confirmar_y_entrar(cliente_http)
    respuesta = cliente_http.get(URL, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return [o for e in respuesta.json()["items"] for o in e["observaciones"]]


def _nombres(observaciones: list[Observacion], codigo: str, campo: str) -> list[object]:
    """El campo de `nombres` de cada observación del código (None si no trae `nombres`)."""
    return sorted(
        (
            None if o["nombres"] is None else o["nombres"][campo]  # type: ignore[index]
            for o in observaciones
            if o["codigo"] == codigo
        ),
        key=str,
    )


def test_el_autorizador_llega_con_su_nombre_y_uno_que_no_existe_con_el_marcador(
    cliente: TestClient, sesion: Session
) -> None:
    """SYN-07: `AUTORIZACION_OFFLINE` nombra al autorizador; si ya no existe, «(no existe)»."""
    entorno = Entorno(sesion, permisos=REVISOR)
    autorizador, _ = crear_usuario_y_dispositivo(sesion, entorno.org)
    _nombrar_usuario(sesion, autorizador, "Ana Supervisora")
    base = {"tipo": "DESCUENTO", "resolucion": "PIN_SUPERVISOR", "autorizador_con_permiso": True}

    observaciones = _bandeja(
        cliente,
        entorno,
        ("AUTORIZACION_OFFLINE", "AUTORIZACION_OFFLINE"),
        ({**base, "autorizador_id": str(autorizador)}, {**base, "autorizador_id": str(uuid4())}),
    )

    assert _nombres(observaciones, "AUTORIZACION_OFFLINE", "autorizador") == sorted(
        ["Ana Supervisora", SIN_REFERENCIA]
    )


def test_una_autorizacion_sin_autorizador_no_inventa_nombre(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    observaciones = _bandeja(
        cliente,
        entorno,
        ("AUTORIZACION_OFFLINE",),
        ({"tipo": "CREDITO", "resolucion": "PERMISO_PROPIO", "autorizador_id": None},),
    )
    nombres = observaciones[0]["nombres"]
    assert nombres is None or nombres["autorizador"] is None  # type: ignore[index]


def test_el_producto_y_el_numero_de_la_linea_llegan_en_los_codigos_que_traen_la_linea(
    cliente: TestClient, sesion: Session
) -> None:
    """STOCK_NEGATIVO, VENTA_SIN_COSTO y PRODUCTO_DESACTIVADO traen `linea_id` y `producto_id`."""
    entorno = Entorno(sesion, permisos=REVISOR)
    cliente_id = crear_cliente(sesion, entorno.org, nombre="Kiosco")
    venta = sembrar_venta_sql(
        sesion,
        entorno.org,
        cliente_id=cliente_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
    )
    producto = crear_producto_sql(sesion, entorno.org, nombre="Cerveza Rubia")
    linea = {"linea_id": str(venta.linea_id), "producto_id": str(producto)}

    observaciones = _bandeja(
        cliente,
        entorno,
        ("STOCK_NEGATIVO", "VENTA_SIN_COSTO", "PRODUCTO_DESACTIVADO"),
        ({**linea, "saldo_resultante": -3}, linea, {**linea, "inactivo": "PRODUCTO"}),
        operacion_id=venta.venta_id,
    )

    for codigo in ("STOCK_NEGATIVO", "VENTA_SIN_COSTO", "PRODUCTO_DESACTIVADO"):
        assert _nombres(observaciones, codigo, "producto") == ["Cerveza Rubia"]
        assert _nombres(observaciones, codigo, "linea") == [1]


def test_un_producto_inexistente_o_de_otra_organizacion_es_sin_referencia_y_sin_linea(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21: el producto de otra organización no se nombra."""
    entorno = Entorno(sesion, permisos=REVISOR)
    otra = crear_organizacion(sesion).id
    ajeno = crear_producto_sql(sesion, otra, nombre="Producto Ajeno")

    observaciones = _bandeja(
        cliente,
        entorno,
        ("VENTA_SIN_COSTO", "STOCK_NEGATIVO"),
        (
            {"linea_id": str(uuid4()), "producto_id": str(ajeno)},
            {"linea_id": str(uuid4()), "producto_id": str(uuid4()), "saldo_resultante": -1},
        ),
    )

    for codigo in ("VENTA_SIN_COSTO", "STOCK_NEGATIVO"):
        assert _nombres(observaciones, codigo, "producto") == [SIN_REFERENCIA]
        assert _nombres(observaciones, codigo, "linea") == [None]
    assert "Producto Ajeno" not in str(observaciones)


def test_la_ubicacion_tomada_nombra_al_vendedor_de_la_jornada_que_la_tenia(
    cliente: TestClient, sesion: Session
) -> None:
    """D12: «Tomada por la jornada de {vendedor}»; el servidor manda el vendedor de esa jornada."""
    entorno = Entorno(sesion, permisos=REVISOR)
    vendedor, dispositivo = crear_usuario_y_dispositivo(sesion, entorno.org)
    _nombrar_usuario(sesion, vendedor, "Beto Vendedor")
    ubicacion = crear_ubicacion_sql(sesion, entorno.org, tipo="VEHICULO", requiere_toma=True)
    jornada = crear_jornada_sql(
        sesion,
        entorno.org,
        usuario_id=vendedor,
        dispositivo_id=dispositivo,
        ubicacion_id=ubicacion,
    )

    observaciones = _bandeja(
        cliente,
        entorno,
        ("UBICACION_TOMADA_AL_SINCRONIZAR", "UBICACION_TOMADA_AL_SINCRONIZAR"),
        (
            {"jornada_id": str(jornada), "ubicacion_id": str(ubicacion)},
            {"jornada_id": str(uuid4()), "ubicacion_id": str(ubicacion)},
        ),
    )

    assert _nombres(observaciones, "UBICACION_TOMADA_AL_SINCRONIZAR", "vendedor_de_jornada") == (
        sorted(["Beto Vendedor", SIN_REFERENCIA])
    )


def test_un_codigo_sin_nombres_que_enriquecer_no_trae_el_campo(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    observaciones = _bandeja(
        cliente, entorno, ("JORNADA_RENDIDA",), ({"rendida_en": "2026-11-05T12:00:00Z"},)
    )
    assert observaciones[0]["nombres"] is None
