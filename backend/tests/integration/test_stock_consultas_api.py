"""Change 14, tareas 10.1, 10.2 y 10.3: lecturas de transferencias y ajustes y movimientos del
kardex con motivo y estado, por HTTP contra PostgreSQL real (specs `stock/transferencias`,
`stock/ajustes-de-stock` y `stock/kardex`; `design.md` D5, D5.1, D7).

Mismo arnés que `test_stock_api.py` (login real, motor propio de la aplicación). Los datos se
siembran con los servicios y un `commit`, con `occurred_at` distintos para que el orden sea
determinista; las rutas de escritura se prueban en `test_stock_transferencias_api.py` y
`test_stock_ajustes_api.py`.

Reglas citadas: STK-04, STK-07, STK-08, TR-04, TR-06, CAT-08, INV-03, INV-21, SEG-06, ADR-036.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from stock_utiles import crear_motivo_sql, crear_presentacion_referencia_sql, crear_ubicacion_sql
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    Entorno,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)

from app.core.clock import FixedClock
from app.modules.stock import service as stock_service
from app.modules.stock.service import LineaDeAjuste, LineaDeTransferencia

URL_TRANSFERENCIAS = "/api/v1/stock/transferencias"
URL_AJUSTES = "/api/v1/stock/ajustes"
URL_KARDEX = "/api/v1/stock/kardex"

BASE = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)

TRANSFERIDOR = frozenset({"TRANSFERIR_STOCK"})
ADMINISTRADOR = frozenset(
    {
        "TRANSFERIR_STOCK",
        "AJUSTAR_STOCK",
        "ANULAR_TRANSFERENCIA",
        "PERMITIR_STOCK_NEGATIVO",
        "VER_COSTOS",
    }
)
AJUSTADOR = frozenset({"AJUSTAR_STOCK"})


class Mundo(Entorno):
    """El `Entorno` de `test_stock_api.py` con dos camionetas, motivos de los tres ámbitos
    y Vino A (120 a 1050) con su caja de 6 en el depósito."""

    camioneta_id: UUID
    camioneta_2_id: UUID
    rotura_id: UUID
    vencimiento_id: UUID
    error_transferencia_id: UUID
    error_ajuste_id: UUID

    def transferir(
        self,
        destino_id: UUID,
        cantidad: int = 48,
        *,
        origen_id: UUID | None = None,
        minutos: int = 0,
        cuando: datetime | None = None,
        observacion: str | None = None,
    ) -> UUID:
        momento = cuando or BASE + timedelta(minutes=minutos)
        resultado = stock_service.transferir(
            self.org,
            self.sesion,
            FixedClock(momento),
            ubicacion_origen_id=origen_id or self.deposito_id,
            ubicacion_destino_id=destino_id,
            lineas=[LineaDeTransferencia(self.producto_id, cantidad)],
            observacion=observacion,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=momento,
            permitir_negativo=True,
        )
        self.sesion.commit()
        return resultado.transferencia.id

    def anular_transferencia(self, transferencia_id: UUID, *, minutos: int = 30) -> None:
        momento = BASE + timedelta(minutes=minutos)
        stock_service.anular_transferencia(
            self.org,
            self.sesion,
            FixedClock(momento),
            transferencia_id=transferencia_id,
            motivo_id=self.error_transferencia_id,
            permisos=ADMINISTRADOR,
            operation_id=uuid4(),
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=momento,
        )
        self.sesion.commit()

    def ajustar(
        self, cantidad: int = -6, *, motivo_id: UUID | None = None, minutos: int = 0
    ) -> UUID:
        momento = BASE + timedelta(minutes=minutos)
        resultado = stock_service.ajustar(
            self.org,
            self.sesion,
            FixedClock(momento),
            ubicacion_id=self.deposito_id,
            motivo_id=motivo_id or self.rotura_id,
            lineas=[LineaDeAjuste(self.producto_id, cantidad)],
            observacion="conteo del lunes",
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=momento,
        )
        self.sesion.commit()
        return resultado.ajuste.id

    def anular_ajuste(self, ajuste_id: UUID, *, minutos: int = 30) -> None:
        momento = BASE + timedelta(minutes=minutos)
        stock_service.anular_ajuste(
            self.org,
            self.sesion,
            FixedClock(momento),
            ajuste_id=ajuste_id,
            motivo_id=self.error_ajuste_id,
            permitir_negativo=False,
            operation_id=uuid4(),
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=momento,
        )
        self.sesion.commit()


def _mundo(sesion: Session, permisos: frozenset[str], nombre_usuario: str = "admin1") -> Mundo:
    mundo = Mundo(sesion, permisos=permisos, nombre_usuario=nombre_usuario)
    mundo.sembrar(mundo.producto_id, 120, "1050")
    crear_presentacion_referencia_sql(sesion, mundo.org, mundo.producto_id, unidades_base=6)
    mundo.camioneta_id = crear_ubicacion_sql(
        sesion, mundo.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
    )
    mundo.camioneta_2_id = crear_ubicacion_sql(
        sesion, mundo.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
    )
    mundo.rotura_id = crear_motivo_sql(sesion, mundo.org, nombre="Rotura")
    mundo.vencimiento_id = crear_motivo_sql(sesion, mundo.org, nombre="Vencimiento")
    mundo.error_transferencia_id = crear_motivo_sql(
        sesion, mundo.org, ambito="ANULACION_TRANSFERENCIA", nombre="Error de carga"
    )
    mundo.error_ajuste_id = crear_motivo_sql(
        sesion, mundo.org, ambito="ANULACION_AJUSTE", nombre="Error de carga"
    )
    sesion.commit()
    return mundo


# ============================== 10.1 transferencias ==========================================


def test_el_listado_va_de_la_mas_reciente_a_la_mas_vieja_con_estado_nombres_y_lineas(
    cliente: TestClient, sesion: Session
) -> None:
    mundo = _mundo(sesion, ADMINISTRADOR)
    primera = mundo.transferir(mundo.camioneta_id, 10, minutos=0, observacion="carga de la mañana")
    segunda = mundo.transferir(mundo.camioneta_2_id, 20, minutos=5)
    mundo.anular_transferencia(primera)
    headers = mundo.confirmar_y_entrar(cliente)

    respuesta = cliente.get(URL_TRANSFERENCIAS, headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert [fila["id"] for fila in cuerpo["items"]] == [str(segunda), str(primera)]
    assert cuerpo["cursor_siguiente"] is None
    reciente, vieja = cuerpo["items"]
    assert reciente["estado"] == "CONFIRMADA"
    assert reciente["ubicacion_origen_nombre"] == "Depósito central"
    assert reciente["ubicacion_destino_nombre"] == "Camioneta 2"
    assert reciente["cantidad_de_lineas"] == 1
    assert reciente["usuario_nombre"] == "Persona de prueba"
    assert vieja["estado"] == "ANULADA"
    assert vieja["observacion"] == "carga de la mañana"
    assert "costo" not in respuesta.text


def test_el_filtro_de_ubicacion_alcanza_origen_y_destino(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Listado filtrado por ubicación"."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    a_la_1 = mundo.transferir(mundo.camioneta_id, 10, minutos=0)
    mundo.transferir(mundo.camioneta_2_id, 10, minutos=1)
    de_la_1 = mundo.transferir(mundo.deposito_id, 5, origen_id=mundo.camioneta_id, minutos=2)
    headers = mundo.confirmar_y_entrar(cliente)

    respuesta = cliente.get(
        URL_TRANSFERENCIAS, params={"ubicacion_id": str(mundo.camioneta_id)}, headers=headers
    )

    assert [fila["id"] for fila in respuesta.json()["items"]] == [str(de_la_1), str(a_la_1)]


def test_las_fechas_son_de_negocio_en_la_zona_de_la_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    """TR-04: 02:30Z del 10/03 es el 09/03 a las 23:30 en Mendoza (UTC-3)."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    nueve = mundo.transferir(mundo.camioneta_id, 1, cuando=datetime(2026, 3, 10, 2, 30, tzinfo=UTC))
    diez = mundo.transferir(mundo.camioneta_id, 1, cuando=datetime(2026, 3, 10, 3, 30, tzinfo=UTC))
    headers = mundo.confirmar_y_entrar(cliente)

    del_nueve = cliente.get(
        URL_TRANSFERENCIAS, params={"desde": "2026-03-09", "hasta": "2026-03-09"}, headers=headers
    )
    del_diez = cliente.get(
        URL_TRANSFERENCIAS, params={"desde": "2026-03-10", "hasta": "2026-03-10"}, headers=headers
    )

    assert [fila["id"] for fila in del_nueve.json()["items"]] == [str(nueve)]
    assert [fila["id"] for fila in del_diez.json()["items"]] == [str(diez)]


def test_paginacion_por_cursor_y_limite_acotado(cliente: TestClient, sesion: Session) -> None:
    mundo = _mundo(sesion, ADMINISTRADOR)
    ids = [mundo.transferir(mundo.camioneta_id, 1, minutos=n) for n in range(3)]
    headers = mundo.confirmar_y_entrar(cliente)

    primera = cliente.get(URL_TRANSFERENCIAS, params={"limite": 2}, headers=headers).json()
    segunda = cliente.get(
        URL_TRANSFERENCIAS,
        params={"limite": 2, "cursor": primera["cursor_siguiente"]},
        headers=headers,
    ).json()

    vistos = [fila["id"] for fila in primera["items"] + segunda["items"]]
    assert vistos == [str(i) for i in reversed(ids)]
    assert len(primera["items"]) == 2 and len(segunda["items"]) == 1
    assert primera["cursor_siguiente"] is not None and segunda["cursor_siguiente"] is None
    for limite in (0, 201):
        fuera = cliente.get(URL_TRANSFERENCIAS, params={"limite": limite}, headers=headers)
        assert fuera.status_code == 422


def test_rango_de_fechas_invertido_y_cursor_ilegible(cliente: TestClient, sesion: Session) -> None:
    mundo = _mundo(sesion, ADMINISTRADOR)
    headers = mundo.confirmar_y_entrar(cliente)

    invertido = cliente.get(
        URL_TRANSFERENCIAS, params={"desde": "2026-03-10", "hasta": "2026-03-09"}, headers=headers
    )
    ilegible = cliente.get(
        URL_TRANSFERENCIAS, params={"cursor": "no-es-un-cursor"}, headers=headers
    )

    assert (invertido.status_code, invertido.json()["codigo"]) == (422, "RANGO_DE_FECHAS_INVALIDO")
    assert (ilegible.status_code, ilegible.json()["codigo"]) == (422, "CURSOR_INVALIDO")


def test_leer_transferencias_exige_transferir_stock_y_anular_ajenas_no_alcanza(
    cliente: TestClient, sesion: Session
) -> None:
    """SEG-06, D5.4: ni el listado ni el detalle se abren a `ANULAR_TRANSFERENCIA` solo."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    transferencia_id = mundo.transferir(mundo.camioneta_id)
    mundo.agregar_usuario(frozenset({"ANULAR_TRANSFERENCIA"}), "auditor")
    mundo.agregar_usuario(AJUSTADOR, "ajustador")

    for nombre in ("auditor", "ajustador"):
        headers = mundo.entrar_como(cliente, nombre)
        assert cliente.get(URL_TRANSFERENCIAS, headers=headers).status_code == 403
        assert (
            cliente.get(f"{URL_TRANSFERENCIAS}/{transferencia_id}", headers=headers).status_code
            == 403
        )


def test_el_detalle_trae_origen_destino_lineas_con_referencia_y_ningun_costo(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Detalle de una transferencia": un Vendedor, 48 unidades base, referencia de 6."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    transferencia_id = mundo.transferir(mundo.camioneta_id, 48, observacion="para la ruta")
    mundo.agregar_usuario(TRANSFERIDOR, "vendedor")
    headers = mundo.entrar_como(cliente, "vendedor")

    respuesta = cliente.get(f"{URL_TRANSFERENCIAS}/{transferencia_id}", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id"] == str(transferencia_id)
    assert cuerpo["estado"] == "CONFIRMADA"
    assert cuerpo["ubicacion_origen_id"] == str(mundo.deposito_id)
    assert cuerpo["ubicacion_origen_nombre"] == "Depósito central"
    assert cuerpo["ubicacion_destino_id"] == str(mundo.camioneta_id)
    assert cuerpo["ubicacion_destino_nombre"] == "Camioneta 1"
    assert cuerpo["observacion"] == "para la ruta"
    assert cuerpo["usuario_id"] == str(mundo.usuario_id)
    assert cuerpo["usuario_nombre"] == "Persona de prueba"
    assert datetime.fromisoformat(cuerpo["occurred_at"]) == BASE
    assert cuerpo["anulacion"] is None
    (linea,) = cuerpo["lineas"]
    assert linea["producto_id"] == str(mundo.producto_id)
    assert linea["producto_nombre"] == "Vino A"
    assert linea["producto_codigo"].startswith("COD-")
    assert (linea["cantidad_base"], linea["unidades_referencia"]) == (48, 6)
    assert linea["nombre_referencia"] == "Caja x6"
    assert "costo" not in respuesta.text


def test_el_detalle_de_una_anulada_trae_motivo_usuario_y_momento(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Detalle de una transferencia anulada"."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    transferencia_id = mundo.transferir(mundo.camioneta_id, 60)
    mundo.anular_transferencia(transferencia_id, minutos=30)
    headers = mundo.confirmar_y_entrar(cliente)

    detalle = cliente.get(f"{URL_TRANSFERENCIAS}/{transferencia_id}", headers=headers).json()
    listado = cliente.get(URL_TRANSFERENCIAS, headers=headers).json()

    assert detalle["estado"] == "ANULADA"
    assert detalle["anulacion"]["motivo_id"] == str(mundo.error_transferencia_id)
    assert detalle["anulacion"]["motivo_nombre"] == "Error de carga"
    assert detalle["anulacion"]["anulada_por_id"] == str(mundo.usuario_id)
    assert detalle["anulacion"]["anulada_por_nombre"] == "Persona de prueba"
    assert datetime.fromisoformat(detalle["anulacion"]["anulada_en"]) == BASE + timedelta(
        minutes=30
    )
    assert [fila["estado"] for fila in listado["items"]] == ["ANULADA"]


def test_inv21_una_transferencia_ajena_o_inexistente_es_404_y_no_aparece_en_el_listado(
    cliente: TestClient, sesion: Session
) -> None:
    mundo_a = _mundo(sesion, ADMINISTRADOR, "a1")
    mundo_b = _mundo(sesion, ADMINISTRADOR, "b1")
    de_a = mundo_a.transferir(mundo_a.camioneta_id)
    mundo_b.transferir(mundo_b.camioneta_id)
    headers_b = mundo_b.confirmar_y_entrar(cliente)

    ajena = cliente.get(f"{URL_TRANSFERENCIAS}/{de_a}", headers=headers_b)
    inexistente = cliente.get(f"{URL_TRANSFERENCIAS}/{uuid4()}", headers=headers_b)
    listado = cliente.get(URL_TRANSFERENCIAS, headers=headers_b).json()

    assert ajena.status_code == inexistente.status_code == 404
    assert str(de_a) not in str(listado)
    assert len(listado["items"]) == 1


# ================================ 10.2 ajustes ===============================================


def test_el_listado_de_ajustes_se_filtra_por_motivo_ubicacion_y_trae_el_estado(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Listado filtrado por motivo"."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    rotura = mundo.ajustar(-6, motivo_id=mundo.rotura_id, minutos=0)
    vencimiento = mundo.ajustar(-2, motivo_id=mundo.vencimiento_id, minutos=5)
    mundo.anular_ajuste(rotura)
    headers = mundo.confirmar_y_entrar(cliente)

    todos = cliente.get(URL_AJUSTES, headers=headers).json()
    por_motivo = cliente.get(
        URL_AJUSTES, params={"motivo_id": str(mundo.rotura_id)}, headers=headers
    ).json()
    por_ubicacion = cliente.get(
        URL_AJUSTES, params={"ubicacion_id": str(mundo.camioneta_id)}, headers=headers
    ).json()

    assert [fila["id"] for fila in todos["items"]] == [str(vencimiento), str(rotura)]
    assert [fila["id"] for fila in por_motivo["items"]] == [str(rotura)]
    assert por_ubicacion["items"] == []
    primero, segundo = todos["items"]
    assert (primero["estado"], primero["motivo_nombre"]) == ("CONFIRMADA", "Vencimiento")
    assert (segundo["estado"], segundo["motivo_nombre"]) == ("ANULADA", "Rotura")
    assert primero["ubicacion_nombre"] == "Depósito central"
    assert primero["cantidad_de_lineas"] == 1
    assert "costo" not in str(todos)


def test_ajustes_fechas_cursor_y_limite(cliente: TestClient, sesion: Session) -> None:
    mundo = _mundo(sesion, ADMINISTRADOR)
    ids = [mundo.ajustar(-1, minutos=n) for n in range(3)]
    headers = mundo.confirmar_y_entrar(cliente)

    primera = cliente.get(URL_AJUSTES, params={"limite": 2}, headers=headers).json()
    segunda = cliente.get(
        URL_AJUSTES, params={"limite": 2, "cursor": primera["cursor_siguiente"]}, headers=headers
    ).json()
    invertido = cliente.get(
        URL_AJUSTES, params={"desde": "2026-10-09", "hasta": "2026-10-08"}, headers=headers
    )
    ilegible = cliente.get(URL_AJUSTES, params={"cursor": "xx"}, headers=headers)
    del_dia = cliente.get(
        URL_AJUSTES, params={"desde": "2026-10-08", "hasta": "2026-10-08"}, headers=headers
    )
    de_otro_dia = cliente.get(URL_AJUSTES, params={"desde": "2026-10-09"}, headers=headers)

    assert [f["id"] for f in primera["items"] + segunda["items"]] == [str(i) for i in reversed(ids)]
    assert cliente.get(URL_AJUSTES, params={"limite": 0}, headers=headers).status_code == 422
    assert cliente.get(URL_AJUSTES, params={"limite": 201}, headers=headers).status_code == 422
    assert invertido.json()["codigo"] == "RANGO_DE_FECHAS_INVALIDO"
    assert ilegible.json()["codigo"] == "CURSOR_INVALIDO"
    assert len(del_dia.json()["items"]) == 3
    assert de_otro_dia.json()["items"] == []


def test_el_costo_de_una_linea_de_ajuste_depende_de_ver_costos(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Costo según permiso": un Administrador y un rol con `AJUSTAR_STOCK` sin
    `VER_COSTOS` (INV-03: el costo viaja como string)."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    ajuste_id = mundo.ajustar(-6)
    mundo.agregar_usuario(AJUSTADOR, "ajustador")
    con_costos = mundo.confirmar_y_entrar(cliente)
    sin_costos = mundo.entrar_como(cliente, "ajustador")

    del_administrador = cliente.get(f"{URL_AJUSTES}/{ajuste_id}", headers=con_costos)
    del_ajustador = cliente.get(f"{URL_AJUSTES}/{ajuste_id}", headers=sin_costos)

    assert del_administrador.status_code == del_ajustador.status_code == 200
    (linea,) = del_administrador.json()["lineas"]
    assert linea["costo_unitario"] == "1050.000000"
    assert (linea["cantidad_base"], linea["unidades_referencia"]) == (-6, 6)
    (linea_sin_costo,) = del_ajustador.json()["lineas"]
    assert "costo_unitario" not in linea_sin_costo
    assert "costo" not in del_ajustador.text


def test_el_detalle_de_un_ajuste_anulado_trae_el_motivo_del_ajuste_y_el_de_la_anulacion(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Detalle de un ajuste anulado"."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    ajuste_id = mundo.ajustar(-6)
    mundo.anular_ajuste(ajuste_id, minutos=30)
    headers = mundo.confirmar_y_entrar(cliente)

    detalle = cliente.get(f"{URL_AJUSTES}/{ajuste_id}", headers=headers).json()

    assert detalle["estado"] == "ANULADA"
    assert detalle["ubicacion_id"] == str(mundo.deposito_id)
    assert detalle["ubicacion_nombre"] == "Depósito central"
    assert (detalle["motivo_id"], detalle["motivo_nombre"]) == (str(mundo.rotura_id), "Rotura")
    assert detalle["observacion"] == "conteo del lunes"
    assert detalle["usuario_nombre"] == "Persona de prueba"
    assert detalle["anulacion"]["motivo_nombre"] == "Error de carga"
    assert detalle["anulacion"]["anulado_por_id"] == str(mundo.usuario_id)
    assert detalle["anulacion"]["anulado_por_nombre"] == "Persona de prueba"
    assert datetime.fromisoformat(detalle["anulacion"]["anulado_en"]) == BASE + timedelta(
        minutes=30
    )


def test_leer_ajustes_exige_ajustar_stock_y_un_ajuste_ajeno_es_404(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Lectura sin permiso o ajena" (SEG-06, INV-21)."""
    mundo_a = _mundo(sesion, ADMINISTRADOR, "a1")
    mundo_b = _mundo(sesion, ADMINISTRADOR, "b1")
    de_a = mundo_a.ajustar()
    mundo_b.ajustar()
    mundo_b.agregar_usuario(TRANSFERIDOR, "vendedor")
    del_vendedor = mundo_b.entrar_como(cliente, "vendedor")
    headers_b = mundo_b.confirmar_y_entrar(cliente)

    assert cliente.get(URL_AJUSTES, headers=del_vendedor).status_code == 403
    assert cliente.get(f"{URL_AJUSTES}/{de_a}", headers=del_vendedor).status_code == 403
    ajeno = cliente.get(f"{URL_AJUSTES}/{de_a}", headers=headers_b)
    inexistente = cliente.get(f"{URL_AJUSTES}/{uuid4()}", headers=headers_b)
    listado = cliente.get(URL_AJUSTES, headers=headers_b).json()
    assert ajeno.status_code == inexistente.status_code == 404
    assert str(de_a) not in str(listado)
    assert len(listado["items"]) == 1


# ============================== 10.3 kardex ==================================================


def _kardex(
    cliente: TestClient, headers: dict[str, str], mundo: Mundo, ubicacion_id: UUID
) -> list[dict[str, object]]:
    respuesta = cliente.get(
        URL_KARDEX,
        params={"producto_id": str(mundo.producto_id), "ubicacion_id": str(ubicacion_id)},
        headers=headers,
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["items"]  # type: ignore[no-any-return]


def test_el_ajuste_aparece_con_su_motivo_su_origen_y_su_estado_sin_costo_para_un_vendedor(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Ajuste en el kardex" (STK-08)."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    ajuste_id = mundo.ajustar(-6)
    mundo.agregar_usuario(TRANSFERIDOR, "vendedor")
    headers = mundo.entrar_como(cliente, "vendedor")

    inicial, ajuste = _kardex(cliente, headers, mundo, mundo.deposito_id)

    assert (ajuste["tipo"], ajuste["cantidad_base"]) == ("AJUSTE", -6)
    assert ajuste["motivo_nombre"] == "Rotura"
    assert (ajuste["origen_tipo"], ajuste["origen_id"]) == ("AJUSTE_STOCK", str(ajuste_id))
    assert ajuste["estado_origen"] == "CONFIRMADA"
    assert ajuste["saldo_acumulado"] == 114
    assert "costo_unitario" not in ajuste
    assert inicial["tipo"] == "STOCK_INICIAL"
    assert inicial["motivo_nombre"] is None and inicial["estado_origen"] is None


def test_la_transferencia_aparece_en_las_dos_ubicaciones_con_el_mismo_origen(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Transferencia en el kardex de las dos ubicaciones" (STK-07)."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    transferencia_id = mundo.transferir(mundo.camioneta_id, 48)
    headers = mundo.confirmar_y_entrar(cliente)

    _, salida = _kardex(cliente, headers, mundo, mundo.deposito_id)
    (entrada,) = _kardex(cliente, headers, mundo, mundo.camioneta_id)

    assert (salida["tipo"], salida["cantidad_base"]) == ("TRANSFERENCIA_SALIDA", -48)
    assert (entrada["tipo"], entrada["cantidad_base"]) == ("TRANSFERENCIA_ENTRADA", 48)
    for movimiento in (salida, entrada):
        assert movimiento["origen_tipo"] == "TRANSFERENCIA"
        assert movimiento["origen_id"] == str(transferencia_id)
        assert movimiento["estado_origen"] == "CONFIRMADA"
        assert movimiento["motivo_nombre"] is None


def test_la_transferencia_anulada_muestra_el_original_anulado_y_el_inverso_con_su_origen(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Transferencia anulada en el kardex" (TR-06, D5.1): el saldo vuelve a cero."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    transferencia_id = mundo.transferir(mundo.camioneta_id, 60)
    mundo.anular_transferencia(transferencia_id)
    headers = mundo.confirmar_y_entrar(cliente)

    entrada, inverso = _kardex(cliente, headers, mundo, mundo.camioneta_id)

    assert (entrada["tipo"], entrada["cantidad_base"], entrada["saldo_acumulado"]) == (
        "TRANSFERENCIA_ENTRADA",
        60,
        60,
    )
    assert (entrada["origen_tipo"], entrada["estado_origen"]) == ("TRANSFERENCIA", "ANULADA")
    assert (inverso["tipo"], inverso["cantidad_base"], inverso["saldo_acumulado"]) == (
        "TRANSFERENCIA_SALIDA",
        -60,
        0,
    )
    assert inverso["origen_tipo"] == "ANULACION_TRANSFERENCIA"
    assert entrada["origen_id"] == inverso["origen_id"] == str(transferencia_id)
    assert inverso["estado_origen"] is None


def test_el_ajuste_anulado_muestra_los_dos_motivos(cliente: TestClient, sesion: Session) -> None:
    """Escenario "Ajuste anulado en el kardex": "Rotura" y "Error de carga"."""
    mundo = _mundo(sesion, ADMINISTRADOR)
    ajuste_id = mundo.ajustar(-6)
    mundo.anular_ajuste(ajuste_id)
    headers = mundo.confirmar_y_entrar(cliente)

    _, ajuste, inverso = _kardex(cliente, headers, mundo, mundo.deposito_id)

    assert (ajuste["tipo"], ajuste["cantidad_base"], ajuste["motivo_nombre"]) == (
        "AJUSTE",
        -6,
        "Rotura",
    )
    assert (ajuste["origen_tipo"], ajuste["estado_origen"]) == ("AJUSTE_STOCK", "ANULADA")
    assert (inverso["tipo"], inverso["cantidad_base"], inverso["motivo_nombre"]) == (
        "AJUSTE",
        6,
        "Error de carga",
    )
    assert inverso["origen_tipo"] == "ANULACION_AJUSTE_STOCK"
    assert ajuste["origen_id"] == inverso["origen_id"] == str(ajuste_id)
    assert inverso["saldo_acumulado"] == 120


@pytest.mark.parametrize("con_ver_costos", [True, False])
def test_el_costo_del_kardex_sigue_dependiendo_de_ver_costos(
    cliente: TestClient, sesion: Session, con_ver_costos: bool
) -> None:
    mundo = _mundo(sesion, ADMINISTRADOR)
    mundo.ajustar(-6)
    mundo.agregar_usuario(TRANSFERIDOR | ({"VER_COSTOS"} if con_ver_costos else set()), "lector")
    headers = mundo.entrar_como(cliente, "lector")

    _, ajuste = _kardex(cliente, headers, mundo, mundo.deposito_id)

    assert ("costo_unitario" in ajuste) is con_ver_costos
    if con_ver_costos:
        assert ajuste["costo_unitario"] == "1050.000000"
