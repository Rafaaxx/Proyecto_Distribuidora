"""Tarea 6.2 (change 20; spec `ventas/nota-de-venta`; `design.md` D2, D4, D5, D13, D14):
`GET /api/v1/ventas/{venta_id}/nota` con todo lo que la nota imprime, contra PostgreSQL real y
login real (mismo arnés que `test_ventas_anular_api.py`).

Las ventas de modo B y C se INSERTAN por SQL: la confirmación las rechaza hasta la etapa 4
(`MODO_IMPOSITIVO_NO_SOPORTADO`). La lectura devuelve lo congelado, sin recalcular ni rechazar
por modo (D14); el rechazo de C es del frontend.

Reglas citadas: VTA-13, VTA-03, VTA-04, INV-10, INV-14, INV-03, INV-21, SEG-06, SEG-07, CRE-02.
"""
# ruff: noqa: F811
# (los fixtures `cliente_http` y `sesion` se importan de `test_ventas_anular_api`)

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_anular_api import (  # noqa: F401
    URL_VENTAS,
    Sesion,
    _con_op,
    _limpiar_datos_confirmados,
    cliente_http,
    sesion,
)
from ventas_anular_utiles import PERMISOS_DE_ANULADOR
from ventas_lecturas_utiles import sembrar, usuario_con
from ventas_utiles import insertar_sql, valores_de_linea

SOLO_VENDER = frozenset({"VENDER"})
SOLO_ANULAR = frozenset({"ANULAR_VENTA"})


def _nota(
    cliente_http: TestClient, headers: dict[str, str], venta_id: object, *, esperado: int = 200
) -> dict[str, Any]:
    respuesta = cliente_http.get(f"{URL_VENTAS}/{venta_id}/nota", headers=headers)
    assert respuesta.status_code == esperado, respuesta.text
    cuerpo: dict[str, Any] = respuesta.json()
    return cuerpo


def _configurar_nota(
    sesion: Session,
    s: Sesion,
    *,
    muestra_saldo: bool = False,
    domicilio: str | None = None,
    telefono: str | None = None,
    cuit: str | None = None,
) -> None:
    sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET nota_venta_muestra_saldo = :m, "
            "nota_venta_domicilio = :d, nota_venta_telefono = :t WHERE organizacion_id = :o"
        ),
        {"m": muestra_saldo, "d": domicilio, "t": telefono, "o": s.entorno.org},
    )
    sesion.execute(
        text("UPDATE organizacion SET cuit = :c WHERE id = :o"),
        {"c": cuit, "o": s.entorno.org},
    )
    sesion.commit()


def test_vta13_la_nota_trae_organizacion_cliente_lineas_totales_y_cobranza(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Datos de la organización con domicilio y teléfono, cliente con documento y dirección,
    la línea congelada, el total y la cobranza con su medio (sin la referencia)."""
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    _configurar_nota(
        sesion,
        s,
        domicilio="Av. San Martín 1234",
        telefono="261 555-0000",
        cuit="20-12345678-9",
    )
    sesion.execute(
        text(
            "UPDATE cliente SET razon_social = 'Kiosco La Esquina SRL', documento_tipo = 'CUIT', "
            "documento_numero = '30711111112', direccion = 'Calle Falsa 123' "
            "WHERE id = :c"
        ),
        {"c": s.entorno.cliente_id},
    )
    sesion.commit()
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers, cobranza=s.entorno.cobranza())

    nota = _nota(cliente_http, headers, venta_id)

    assert nota["organizacion"] == {
        "nombre": "Organización de prueba cuentas corrientes",
        "cuit": "20-12345678-9",
        "domicilio": "Av. San Martín 1234",
        "telefono": "261 555-0000",
    }
    assert nota["zona_horaria"] == "America/Argentina/Mendoza"
    assert nota["cliente"] == {
        "nombre": "Kiosco La Esquina",
        "razon_social": "Kiosco La Esquina SRL",
        "documento_tipo": "CUIT",
        "documento_numero": "30711111112",
        "direccion": "Calle Falsa 123",
        "es_consumidor_final": False,
    }
    assert nota["numero"] == f"{s.prefijo}-000001"
    guardado = sesion.scalar(text("SELECT occurred_at FROM venta WHERE id = :v"), {"v": venta_id})
    assert datetime.fromisoformat(nota["occurred_at"]) == guardado
    assert nota["vendedor_nombre"] == "Persona de prueba"
    assert nota["estado"] == "CONFIRMADA"
    assert nota["modo_impositivo"] == "A"
    (linea,) = nota["lineas"]
    assert linea == {
        "orden": 0,
        "producto_nombre": "Vino A",
        "presentacion_nombre": "Botella",
        "cantidad": 15,
        "unidades_presentacion": 1,
        "precio_referencia": "12500.00",
        "unidades_referencia": 6,
        "importe_bruto": "31250.00",
        "importe_descuento": "0.00",
        "importe_neto": "31250.00",
        "alicuota": linea["alicuota"],
        "importe_iva": "0.00",
    }
    assert isinstance(linea["alicuota"], str)
    assert (nota["total_neto"], nota["total_iva"], nota["total"]) == (
        "31250.00",
        "0.00",
        "31250.00",
    )
    assert nota["cobranza"] == {
        "importe": "20000.00",
        "estado": "CONFIRMADA",
        "medios": [{"nombre": "Efectivo", "importe": "20000.00"}],
    }
    assert nota["anulacion"] is None


def test_vta13_la_organizacion_sin_domicilio_ni_telefono_ni_cuit_los_trae_nulos(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=SOLO_VENDER)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)

    nota = _nota(cliente_http, headers, venta_id)

    assert nota["organizacion"]["domicilio"] is None
    assert nota["organizacion"]["telefono"] is None
    assert nota["organizacion"]["cuit"] is None
    assert nota["cobranza"] is None


def test_vta13_la_nota_refleja_el_nombre_y_el_cuit_cargados_por_el_comando(
    cliente_http: TestClient, sesion: Session
) -> None:
    """D15: tras `ORGANIZACION_DATOS_CONFIGURAR` la nota (ya emitida) trae el nombre nuevo y el
    CUIT en 11 dígitos; al vaciar el CUIT vuelve a `null`."""
    s = Sesion(sesion, permisos=SOLO_VENDER | {"ADMIN_CONFIGURACION"})
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)
    url = "/api/v1/configuracion/organizacion"

    cargado = cliente_http.post(
        url,
        json={"nombre": " Distribuidora Norte ", "cuit": "30-71234567-8"},
        headers=_con_op(headers),
    )
    nota = _nota(cliente_http, headers, venta_id)

    assert cargado.status_code == 200, cargado.text
    assert nota["organizacion"]["nombre"] == "Distribuidora Norte"
    assert nota["organizacion"]["cuit"] == "30712345678"

    vaciado = cliente_http.post(
        url, json={"nombre": "Distribuidora Norte", "cuit": ""}, headers=_con_op(headers)
    )
    nota = _nota(cliente_http, headers, venta_id)

    assert vaciado.status_code == 200, vaciado.text
    assert nota["organizacion"]["nombre"] == "Distribuidora Norte"
    assert nota["organizacion"]["cuit"] is None


def test_vta13_los_medios_de_la_cobranza_van_en_orden_con_su_importe_y_sin_referencia(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=SOLO_VENDER)
    headers = s.entrar(cliente_http)
    e = s.entorno
    cobranza = e.cobranza(
        (e.efectivo_id, "10000.00", None), (e.transferencia_id, "5000.00", "0042")
    )
    venta_id = s.vender(cliente_http, headers, cobranza=cobranza)

    nota = _nota(cliente_http, headers, venta_id)

    assert nota["cobranza"]["importe"] == "15000.00"
    assert nota["cobranza"]["medios"] == [
        {"nombre": "Efectivo", "importe": "10000.00"},
        {"nombre": "Transferencia", "importe": "5000.00"},
    ]
    assert "0042" not in json.dumps(nota)


def test_vta13_inv10_las_lineas_van_en_su_orden_y_conservan_sus_importes_aunque_cambie_la_lista(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=SOLO_VENDER)
    headers = s.entrar(cliente_http)
    e = s.entorno
    primera = e.linea(e.vino_id, e.caja_id, cantidad=1, unidades_presentacion=6)
    segunda = e.linea(e.vino_id, e.botella_id, cantidad=3)
    venta_id = s.vender(cliente_http, headers, lineas=[primera, segunda], total="18750.00")

    sesion.execute(
        text("UPDATE precio_item SET precio_final = 99999.00 WHERE organizacion_id = :o"),
        {"o": e.org},
    )
    sesion.commit()
    nota = _nota(cliente_http, headers, venta_id)

    assert [(linea["orden"], linea["cantidad"]) for linea in nota["lineas"]] == [(0, 1), (1, 3)]
    assert [linea["importe_bruto"] for linea in nota["lineas"]] == ["12500.00", "6250.00"]
    assert [linea["presentacion_nombre"] for linea in nota["lineas"]] == ["Caja x6", "Botella"]
    assert [linea["precio_referencia"] for linea in nota["lineas"]] == ["12500.00", "12500.00"]
    assert nota["total"] == "18750.00"


def test_vta13_la_nota_no_lleva_costos_ni_credito_y_los_importes_son_texto(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Sin costos ni crédito aunque el usuario los pueda ver en el detalle (D2, INV-03)."""
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR | {"VER_COSTOS"})
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers, cobranza=s.entorno.cobranza())

    nota = _nota(cliente_http, headers, venta_id)

    texto = json.dumps(nota)
    assert "costo" not in texto
    assert "credito" not in texto
    assert "autorizador" not in texto
    for campo in ("total_neto", "total_iva", "total"):
        assert isinstance(nota[campo], str)
    for linea in nota["lineas"]:
        for campo in (
            "precio_referencia",
            "importe_bruto",
            "importe_descuento",
            "importe_neto",
            "alicuota",
            "importe_iva",
        ):
            assert isinstance(linea[campo], str)
    assert isinstance(nota["cobranza"]["importe"], str)


# --- saldo (D4) ------------------------------------------------------------------------


def test_cre02_con_mostrar_saldo_la_nota_trae_el_saldo_resultante(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Saldo $150.000 + total $31.250 - cobranza $20.000 = $161.250 (CRE-02)."""
    s = Sesion(sesion, permisos=SOLO_VENDER)
    _configurar_nota(sesion, s, muestra_saldo=True)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers, cobranza=s.entorno.cobranza())

    nota = _nota(cliente_http, headers, venta_id)

    assert nota["muestra_saldo"] is True
    assert nota["saldo_resultante"] == "161250.00"


def test_cre02_sin_cobranza_el_saldo_suma_todo_el_total(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=SOLO_VENDER)
    _configurar_nota(sesion, s, muestra_saldo=True)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)

    assert _nota(cliente_http, headers, venta_id)["saldo_resultante"] == "181250.00"


def test_vta13_el_saldo_es_el_congelado_aunque_el_saldo_actual_cambie(
    cliente_http: TestClient, sesion: Session
) -> None:
    """La reimpresión reproduce la nota original: usa el snapshot de la venta (D4)."""
    s = Sesion(sesion, permisos=SOLO_VENDER)
    _configurar_nota(sesion, s, muestra_saldo=True)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers, cobranza=s.entorno.cobranza())
    primera = _nota(cliente_http, headers, venta_id)["saldo_resultante"]
    otra = s.vender(
        cliente_http, headers, numero=f"{s.prefijo}-000002", cobranza=s.entorno.cobranza()
    )

    segunda = _nota(cliente_http, headers, venta_id)["saldo_resultante"]

    assert primera == segunda == "161250.00"
    assert _nota(cliente_http, headers, otra)["saldo_resultante"] == "172500.00"


def test_vta13_con_el_parametro_inactivo_la_nota_no_trae_saldo(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=SOLO_VENDER)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers, cobranza=s.entorno.cobranza())

    nota = _nota(cliente_http, headers, venta_id)

    assert nota["muestra_saldo"] is False
    assert nota["saldo_resultante"] is None


def test_cli03_al_consumidor_final_no_se_le_trae_saldo_aunque_el_parametro_este_activo(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=SOLO_VENDER)
    _configurar_nota(sesion, s, muestra_saldo=True)
    sesion.execute(
        text("UPDATE cliente SET es_consumidor_final = true WHERE id = :c"),
        {"c": s.entorno.cliente_id},
    )
    sesion.commit()
    venta = sembrar(sesion, s, credito_saldo_considerado="1000.00")
    headers = s.entrar(cliente_http)

    nota = _nota(cliente_http, headers, venta.venta_id)

    assert nota["cliente"]["es_consumidor_final"] is True
    assert nota["saldo_resultante"] is None


def test_vta13_una_venta_sin_snapshot_de_credito_no_trae_saldo(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Una venta anterior al change 18b (sin `credito_saldo_considerado`)."""
    s = Sesion(sesion, permisos=SOLO_VENDER)
    _configurar_nota(sesion, s, muestra_saldo=True)
    venta = sembrar(sesion, s)
    headers = s.entrar(cliente_http)

    nota = _nota(cliente_http, headers, venta.venta_id)

    assert nota["muestra_saldo"] is True
    assert nota["saldo_resultante"] is None


# --- anulación (D5) --------------------------------------------------------------------


def _anular(
    cliente_http: TestClient, s: Sesion, headers: dict[str, str], venta_id: str, **cuerpo: Any
) -> None:
    respuesta = cliente_http.post(
        f"{URL_VENTAS}/{venta_id}/anulacion",
        json={"motivo_id": str(s.entorno.motivo_anulacion_id), **cuerpo},
        headers=_con_op(headers),
    )
    assert respuesta.status_code == 200, respuesta.text


def test_vta22_la_nota_de_una_venta_anulada_con_devolucion_trae_la_anulacion_y_no_el_saldo(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    _configurar_nota(sesion, s, muestra_saldo=True)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers, cobranza=s.entorno.cobranza())
    _anular(cliente_http, s, headers, venta_id, devuelve_dinero=True)

    nota = _nota(cliente_http, headers, venta_id)

    assert nota["estado"] == "ANULADA"
    assert nota["saldo_resultante"] is None
    assert nota["anulacion"]["motivo_nombre"] == "Error de carga"
    assert nota["anulacion"]["devuelve_dinero"] is True
    assert datetime.fromisoformat(nota["anulacion"]["anulada_en"])
    assert nota["cobranza"]["estado"] == "ANULADA"
    assert nota["cobranza"]["importe"] == "20000.00"


def test_vta22_anulada_sin_devolucion_la_cobranza_sigue_y_se_informa_el_destino(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers, cobranza=s.entorno.cobranza())
    _anular(cliente_http, s, headers, venta_id, devuelve_dinero=False)

    nota = _nota(cliente_http, headers, venta_id)

    assert nota["anulacion"]["devuelve_dinero"] is False
    assert nota["cobranza"]["estado"] == "CONFIRMADA"


def test_vta20_anulada_sin_cobranza_el_destino_es_nulo(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)
    _anular(cliente_http, s, headers, venta_id)

    nota = _nota(cliente_http, headers, venta_id)

    assert nota["estado"] == "ANULADA"
    assert nota["anulacion"]["devuelve_dinero"] is None
    assert nota["cobranza"] is None


# --- permisos y aislamiento --------------------------------------------------------------


def test_d13_con_vender_y_con_anular_venta_se_puede_leer_la_nota(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)
    solo_vender = usuario_con(cliente_http, sesion, s, SOLO_VENDER)
    solo_anular = usuario_con(cliente_http, sesion, s, SOLO_ANULAR)

    assert _nota(cliente_http, solo_vender, venta_id)["numero"]
    assert _nota(cliente_http, solo_anular, venta_id)["numero"]


def test_seg06_sin_vender_ni_anular_venta_responde_403(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)
    sin_permiso = usuario_con(cliente_http, sesion, s, frozenset({"VER_COSTOS"}))

    respuesta = cliente_http.get(f"{URL_VENTAS}/{venta_id}/nota", headers=sin_permiso)

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def test_seg07_una_venta_inexistente_responde_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    s = Sesion(sesion, permisos=SOLO_VENDER)
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.get(f"{URL_VENTAS}/{uuid4()}/nota", headers=headers)

    assert respuesta.status_code == 404


def test_inv21_seg07_la_nota_de_una_venta_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    propia = Sesion(sesion, permisos=SOLO_VENDER)
    ajena = Sesion(sesion, permisos=SOLO_VENDER)
    headers_propia = propia.entrar(cliente_http)
    headers_ajena = ajena.entrar(cliente_http)
    venta_propia = propia.vender(cliente_http, headers_propia)

    respuesta = cliente_http.get(f"{URL_VENTAS}/{venta_propia}/nota", headers=headers_ajena)

    assert respuesta.status_code == 404
    assert _nota(cliente_http, headers_propia, venta_propia)["numero"]


# --- modos impositivos B y C (D14): ventas insertadas por SQL ------------------------------


def _insertar_lineas(sesion: Session, s: Sesion, venta: Any, lineas: list[dict[str, str]]) -> None:
    for orden, cambios in enumerate(lineas):
        insertar_sql(
            sesion,
            "venta_linea",
            valores_de_linea(
                s.entorno.org,
                venta.venta_id,
                producto_id=venta.producto_id,
                presentacion_id=venta.presentacion_id,
                version_id=venta.version_id,
                orden=orden,
                **cambios,
            ),
        )
    sesion.commit()


def test_vta04_inv14_una_venta_de_modo_b_se_lee_con_sus_alicuotas_y_totales_congelados(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Netos $10.000 y $4.000 al 21 % y $2.000 al 10,5 %: IVA de línea $2.100, $840 y $210; la
    lectura devuelve lo guardado, sin recalcular el IVA sobre la suma de netos (D14)."""
    s = Sesion(sesion, permisos=SOLO_VENDER)
    venta = sembrar(
        sesion,
        s,
        con_linea=False,
        modo_impositivo="B",
        total_neto="16000.00",
        total_iva="3150.00",
        total="19150.00",
    )
    _insertar_lineas(
        sesion,
        s,
        venta,
        [
            {
                "importe_bruto": "10000.00",
                "importe_neto": "10000.00",
                "alicuota": "0.210000",
                "importe_iva": "2100.00",
            },
            {
                "importe_bruto": "4000.00",
                "importe_neto": "4000.00",
                "alicuota": "0.210000",
                "importe_iva": "840.00",
            },
            {
                "importe_bruto": "2000.00",
                "importe_neto": "2000.00",
                "alicuota": "0.105000",
                "importe_iva": "210.00",
            },
        ],
    )
    headers = s.entrar(cliente_http)

    nota = _nota(cliente_http, headers, venta.venta_id)

    assert nota["modo_impositivo"] == "B"
    assert (nota["total_neto"], nota["total_iva"], nota["total"]) == (
        "16000.00",
        "3150.00",
        "19150.00",
    )
    assert [(ln["alicuota"], ln["importe_iva"], ln["importe_neto"]) for ln in nota["lineas"]] == [
        ("0.210000", "2100.00", "10000.00"),
        ("0.210000", "840.00", "4000.00"),
        ("0.105000", "210.00", "2000.00"),
    ]


def test_vta04_inv14_una_venta_de_modo_c_tambien_se_lee_con_200_y_lo_congelado(
    cliente_http: TestClient, sesion: Session
) -> None:
    """D14: la lectura no rechaza por modo (el rechazo de C es del frontend). Valores congelados
    arbitrarios: la prueba no asume la semántica de las columnas en modo C (Q1)."""
    s = Sesion(sesion, permisos=SOLO_VENDER)
    venta = sembrar(
        sesion,
        s,
        con_linea=False,
        modo_impositivo="C",
        total_neto="10000.00",
        total_iva="2100.00",
        total="12100.00",
    )
    _insertar_lineas(
        sesion,
        s,
        venta,
        [
            {
                "importe_bruto": "10000.00",
                "importe_neto": "10000.00",
                "alicuota": "0.210000",
                "importe_iva": "2100.00",
            },
            {
                "importe_bruto": "0.00",
                "importe_neto": "0.00",
                "alicuota": "0.000000",
                "importe_iva": "0.00",
            },
        ],
    )
    headers = s.entrar(cliente_http)

    nota = _nota(cliente_http, headers, venta.venta_id)

    assert nota["modo_impositivo"] == "C"
    assert (nota["total_neto"], nota["total_iva"], nota["total"]) == (
        "10000.00",
        "2100.00",
        "12100.00",
    )
    assert [(ln["alicuota"], ln["importe_iva"]) for ln in nota["lineas"]] == [
        ("0.210000", "2100.00"),
        ("0.000000", "0.00"),
    ]


def test_vta04_la_lectura_no_depende_de_la_condicion_actual_de_la_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    """INV-10: una venta de modo A sigue leyéndose en modo A aunque la organización hoy sea
    responsable inscripta en modo B."""
    s = Sesion(sesion, permisos=SOLO_VENDER)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)
    s.entorno.configurar(condicion_iva="RESPONSABLE_INSCRIPTO", modo_impositivo="B")
    sesion.commit()

    nota = _nota(cliente_http, headers, venta_id)

    assert nota["modo_impositivo"] == "A"
    assert nota["total_iva"] == "0.00"
