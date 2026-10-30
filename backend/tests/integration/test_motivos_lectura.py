"""Tarea 3.3 (change 20c; `design.md` D12, D15): `GET /api/v1/configuracion/motivos/todos` lee
todos los motivos (activos e inactivos) con `ADMIN_CONFIGURACION`; `GET /configuracion/motivos`
sigue devolviendo solo los activos del ámbito; `configuracion/service.py::listar_motivos_activos`
trae todos los ámbitos. Reglas citadas: TR-08, TR-09, CAT-05, INV-21.
"""

from __future__ import annotations

import medios_pago_utiles as utiles
import pytest
from fastapi.testclient import TestClient
from medios_pago_utiles import Entorno
from sqlalchemy.orm import Session
from stock_utiles import crear_motivo_sql

from app.modules.configuracion import service as configuracion_service

URL_TODOS = "/api/v1/configuracion/motivos/todos"
URL_ACTIVOS = "/api/v1/configuracion/motivos"

_limpiar_datos_confirmados = utiles._limpiar_datos_confirmados
cliente_http = utiles.cliente_http
sesion = utiles.sesion


def _motivo(
    entorno: Entorno, ambito: str, nombre: str, *, activo: bool = True, org: object = None
) -> None:
    crear_motivo_sql(
        entorno.sesion,
        org or entorno.org,  # type: ignore[arg-type]
        ambito=ambito,
        nombre=nombre,
        activo=activo,
    )


class TestLecturaCompleta:
    def test_devuelve_activos_e_inactivos_ordenados_por_ambito_y_nombre(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _motivo(entorno, "AJUSTE_STOCK", "rotura")
        _motivo(entorno, "AJUSTE_STOCK", "Merma", activo=False)
        _motivo(entorno, "ANULACION_VENTA", "Error de carga")
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.get(URL_TODOS, headers=headers)

        assert respuesta.status_code == 200, respuesta.text
        items = respuesta.json()["items"]
        assert [(m["ambito"], m["nombre"], m["activo"]) for m in items] == [
            ("AJUSTE_STOCK", "Merma", False),
            ("AJUSTE_STOCK", "rotura", True),
            ("ANULACION_VENTA", "Error de carga", True),
        ]
        assert all(m["actualizado_en"] and m["id"] for m in items)

    def test_con_ambito_filtra_solo_ese_ambito(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _motivo(entorno, "AJUSTE_STOCK", "Rotura", activo=False)
        _motivo(entorno, "ANULACION_VENTA", "Error de carga")
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.get(f"{URL_TODOS}?ambito=AJUSTE_STOCK", headers=headers)

        assert respuesta.status_code == 200
        assert [(m["nombre"], m["activo"]) for m in respuesta.json()["items"]] == [
            ("Rotura", False)
        ]

    @pytest.mark.parametrize("ambito", ["NO_EXISTE", "ajuste_stock"])
    def test_un_ambito_invalido_es_ambito_invalido_422(
        self, cliente_http: TestClient, sesion: Session, ambito: str
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.get(f"{URL_TODOS}?ambito={ambito}", headers=headers)

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "AMBITO_INVALIDO"

    def test_sin_admin_configuracion_responde_403(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _motivo(entorno, "AJUSTE_STOCK", "Rotura")
        headers = entorno.entrar(cliente_http, "cobrador1")

        respuesta = cliente_http.get(URL_TODOS, headers=headers)

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"

    def test_inv21_trae_solo_los_motivos_de_la_organizacion_del_token(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        una = Entorno(sesion)
        otra = Entorno(sesion)
        _motivo(una, "AJUSTE_STOCK", "De una")
        _motivo(otra, "AJUSTE_STOCK", "De otra")
        headers = una.entrar(cliente_http)

        respuesta = cliente_http.get(URL_TODOS, headers=headers)

        assert [m["nombre"] for m in respuesta.json()["items"]] == ["De una"]


class TestLecturaDeActivosSinCambios:
    def test_la_lectura_por_ambito_sigue_devolviendo_solo_activos_a_cualquier_sesion(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _motivo(entorno, "AJUSTE_STOCK", "Rotura")
        _motivo(entorno, "AJUSTE_STOCK", "Merma", activo=False)
        headers = entorno.entrar(cliente_http, "nadie1")

        respuesta = cliente_http.get(f"{URL_ACTIVOS}?ambito=AJUSTE_STOCK", headers=headers)

        assert respuesta.status_code == 200
        assert [m["nombre"] for m in respuesta.json()["items"]] == ["Rotura"]


class TestFuncionPublicaParaElBootstrap:
    def test_listar_motivos_activos_trae_todos_los_ambitos_con_ambito_y_actualizado_en(
        self, sesion: Session
    ) -> None:
        # D15: la función pública que el change 21 usará para bajar los motivos (SYN-11).
        entorno = Entorno(sesion)
        otra = Entorno(sesion)
        _motivo(entorno, "AJUSTE_STOCK", "Rotura")
        _motivo(entorno, "ANULACION_VENTA", "Error de carga")
        _motivo(entorno, "ANULACION_VENTA", "Viejo", activo=False)
        _motivo(otra, "AJUSTE_STOCK", "De otra")
        sesion.flush()

        motivos = configuracion_service.listar_motivos_activos(entorno.org, sesion)

        assert sorted((m.ambito, m.nombre) for m in motivos) == [
            ("AJUSTE_STOCK", "Rotura"),
            ("ANULACION_VENTA", "Error de carga"),
        ]
        assert all(m.actualizado_en is not None for m in motivos)
