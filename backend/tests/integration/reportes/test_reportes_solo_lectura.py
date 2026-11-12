"""Tarea 8.1 (change 26, spec `reportes/area-de-reportes`, «Consultar un reporte no cambia
nada»; `design.md` D6): pedir TODOS los reportes con un usuario de solo lectura no cambia ninguna
tabla (mismas filas y mismos valores antes y después).

El recorrido sale de `RUTAS_DEL_AREA` (la lista cerrada del área), así que un reporte nuevo sin
caso acá hace fallar la prueba. PostgreSQL real y login real.

Reglas citadas: REP-01, INV-05.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_api`)

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from reportes_utiles import (
    LineaContada,
    LineaDePrueba,
    anular_venta,
    crear_vendedor,
    dia,
    fijar_reloj,
    mover_cuenta,
    sembrar_ajuste,
    sembrar_cliente_de_cartera,
    sembrar_cobranza,
    sembrar_jornada,
    sembrar_proveedor_de_prueba,
    sembrar_rendicion,
    sembrar_venta,
)
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_reportes_rutas import RUTAS_DEL_AREA
from test_ventas_api import (  # noqa: F401
    Sesion,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_lecturas_utiles import usuario_con

SOLO_LECTURA = frozenset({"VER_REPORTES", "VER_UTILIDAD", "VER_COSTOS", "GESTIONAR_PROVEEDORES"})
PERIODO = {"desde": "2026-11-01", "hasta": "2026-11-30"}


def _huella_de_la_base(sesion: Session) -> dict[str, tuple[int, str]]:
    """Por tabla: cantidad de filas y un hash de todos sus valores (orden estable)."""
    tablas = sesion.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    ).scalars()
    huella: dict[str, tuple[int, str]] = {}
    for tabla in list(tablas):
        fila = sesion.execute(
            text(
                "SELECT count(*), coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '') "
                f'FROM "{tabla}" t'
            )
        ).one()
        huella[tabla] = (fila[0], fila[1])
    sesion.rollback()
    return huella


def _sembrar_un_dia_de_operaciones(sesion: Session, s: Sesion) -> UUID:
    e = s.entorno
    vendedor = crear_vendedor(sesion, s, "Juan")
    jornada = sembrar_jornada(sesion, s, vendedor=vendedor, estado="CERRADA")
    sembrar_venta(sesion, s, occurred_at=dia(11, 3), lineas=[LineaDePrueba(neto="900.00")])
    anulada = sembrar_venta(
        sesion, s, occurred_at=dia(11, 4), lineas=[LineaDePrueba(neto="300.00")]
    )
    anular_venta(sesion, s, anulada.venta_id, anulada_en=dia(11, 5))
    sembrar_venta(
        sesion,
        s,
        vendedor_id=vendedor.usuario_id,
        occurred_at=dia(11, 3, 10),
        lineas=[LineaDePrueba(neto="100.00", costo_total=None)],
        modo_confirmacion="OFFLINE",
        jornada_id=jornada,
    )
    sembrar_cobranza(
        sesion,
        s,
        jornada,
        [(e.efectivo_id, "100.00")],
        cuando=dia(11, 3, 14),
        vendedor=vendedor,
    )
    sembrar_rendicion(
        sesion, s, jornada, vendedor=vendedor, lineas=[LineaContada(e.vino_id, 10, 8)]
    )
    sembrar_ajuste(
        sesion,
        s,
        motivo="Rotura",
        lineas=[(e.vino_id, -2, "10.000000")],
        occurred_at=dia(11, 3),
    )
    cliente = sembrar_cliente_de_cartera(sesion, s, nombre="Kiosco", limite_credito="5000.00")
    mover_cuenta(sesion, s, "CLIENTE", cliente, "VENTA", "1500.00")
    proveedor = sembrar_proveedor_de_prueba(sesion, s, nombre="Bodega Sur")
    mover_cuenta(sesion, s, "PROVEEDOR", proveedor, "COMPRA", "8000.00")
    return jornada


def test_pedir_todos_los_reportes_no_cambia_ninguna_tabla(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion)
    jornada = _sembrar_un_dia_de_operaciones(sesion, s)
    headers = usuario_con(cliente_http, sesion, s, SOLO_LECTURA)
    fijar_reloj(cliente_http, dia(11, 6))
    antes = _huella_de_la_base(sesion)
    pedidas: set[tuple[str, str]] = set()

    for metodo, ruta in sorted(RUTAS_DEL_AREA):
        url = ruta.replace("{jornada_id}", str(jornada))
        respuesta = cliente_http.request(metodo, url, params=PERIODO, headers=headers)
        assert respuesta.status_code == 200, (ruta, respuesta.text)
        pedidas.add((metodo, ruta))
    despues = _huella_de_la_base(sesion)

    assert pedidas == RUTAS_DEL_AREA
    cambiadas = sorted(t for t in antes if antes[t] != despues.get(t))
    assert cambiadas == []
    # Los reportes se pidieron con datos de verdad: la base no estaba vacía.
    assert antes["venta"][0] > 0 and antes["saldo_cuenta"][0] > 0


def test_la_huella_detecta_una_escritura(cliente_http: TestClient, sesion: Session) -> None:
    """Valida la prueba de arriba: un cambio en cualquier tabla cambia la huella."""
    s = Sesion(sesion)
    _sembrar_un_dia_de_operaciones(sesion, s)
    antes = _huella_de_la_base(sesion)

    sesion.execute(
        text("UPDATE cliente SET contacto = :c WHERE organizacion_id = :o"),
        {"c": f"cambio-{uuid4().hex}", "o": s.entorno.org},
    )
    sesion.commit()
    despues = _huella_de_la_base(sesion)

    assert [t for t in antes if antes[t] != despues.get(t)] == ["cliente"]
