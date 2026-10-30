"""Tareas 4.2, 4.4 y 4.5 (change 20c; `design.md` D1, D6, D7, D8, D9, D13): `ALICUOTA_CREAR` y
`ALICUOTA_MODIFICAR` por `POST` y `PUT /api/v1/configuracion/alicuotas`.

Mismo arnés que `test_motivo_comandos.py`: PostgreSQL real, motor propio de la aplicación y
`login` real. Reglas citadas: TR-09, TR-02, TR-06, CAT-01, CAT-05, VTA-03, IMP-04, INV-01,
INV-03, INV-06, INV-21 y ADR-061.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import medios_pago_utiles as utiles
import pytest
from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from medios_pago_utiles import Entorno, con_op
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_presentacion_sql, crear_producto_sql

from app.core.clock import FixedClock
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

URL_ALICUOTAS = "/api/v1/configuracion/alicuotas"
URL_PRODUCTOS = "/api/v1/catalogo/productos"

_limpiar_datos_confirmados = utiles._limpiar_datos_confirmados
cliente_http = utiles.cliente_http
sesion = utiles.sesion

MOMENTO = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def _crear_alicuota(
    entorno: Entorno,
    nombre: str,
    valor: str,
    *,
    activo: bool = True,
    org: UUID | None = None,
) -> UUID:
    alicuota_id = uuid4()
    entorno.sesion.execute(
        text(
            "INSERT INTO alicuota_iva (id, organizacion_id, nombre, valor, activo, creado_en, "
            "actualizado_en) VALUES (:id, :org, :n, :v, :a, :m, :m)"
        ),
        {
            "id": alicuota_id,
            "org": org or entorno.org,
            "n": nombre,
            "v": Decimal(valor),
            "a": activo,
            "m": MOMENTO,
        },
    )
    entorno.sesion.commit()
    return alicuota_id


def _producto_con_alicuota(entorno: Entorno, alicuota_id: UUID, *, activo: bool = True) -> UUID:
    producto_id = crear_producto_sql(entorno.sesion, entorno.org)
    entorno.sesion.execute(
        text("UPDATE producto SET alicuota_id = :a, activo = :act WHERE id = :p"),
        {"a": alicuota_id, "act": activo, "p": producto_id},
    )
    entorno.sesion.commit()
    return producto_id


def _filas(entorno: Entorno) -> list[dict[str, Any]]:
    entorno.sesion.rollback()
    filas = entorno.sesion.execute(
        text(
            "SELECT id, nombre, valor::text AS valor, activo FROM alicuota_iva "
            "WHERE organizacion_id = :o ORDER BY valor"
        ),
        {"o": entorno.org},
    ).mappings()
    return [dict(f) for f in filas]


def _auditoria(entorno: Entorno, accion: str) -> list[dict[str, Any]]:
    return entorno.auditoria_de(accion, entidad="alicuota_iva")


def _cuerpo(**cambios: object) -> dict[str, object]:
    cuerpo: dict[str, object] = {"nombre": "27%", "valor": "0.270000"}
    cuerpo.update(cambios)
    return cuerpo


def _url(alicuota_id: UUID) -> str:
    return f"{URL_ALICUOTAS}/{alicuota_id}"


def _sembrar_general(entorno: Entorno) -> tuple[UUID, UUID, UUID]:
    """La siembra del `01` §4: 21 %, 10,5 % y 0 %."""
    return (
        _crear_alicuota(entorno, "21%", "0.210000"),
        _crear_alicuota(entorno, "10,5%", "0.105000"),
        _crear_alicuota(entorno, "0%", "0.000000"),
    )


# ======================= ALICUOTA_CREAR (4.2) =========================================


class TestAlicuotaCrear:
    def test_tr09_alta_de_27_por_ciento_activa_con_el_valor_como_string(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _sembrar_general(entorno)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_ALICUOTAS, json=_cuerpo(nombre="  27% "), headers=con_op(headers)
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        UUID(cuerpo["id"])
        assert (cuerpo["nombre"], cuerpo["valor"], cuerpo["activo"]) == ("27%", "0.270000", True)
        assert "organizacion_id" not in cuerpo
        assert [f["nombre"] for f in _filas(entorno)] == ["0%", "10,5%", "21%", "27%"]

    @pytest.mark.parametrize("valor", ["0.105", "0.1", "0.000001"])
    def test_inv03_el_valor_se_guarda_exacto_y_se_devuelve_con_seis_decimales(
        self, cliente_http: TestClient, sesion: Session, valor: str
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_ALICUOTAS, json=_cuerpo(nombre="X", valor=valor), headers=con_op(headers)
        )

        assert respuesta.status_code == 201, respuesta.text
        assert respuesta.json()["valor"] == f"{Decimal(valor):.6f}"

    @pytest.mark.parametrize("valor", ["1.000000", "-0.010000", "0.2100001", "abc", "1.5"])
    def test_tr02_fuera_de_rango_o_con_mas_decimales_es_valor_invalido_422(
        self, cliente_http: TestClient, sesion: Session, valor: str
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_ALICUOTAS, json=_cuerpo(valor=valor), headers=con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] in {
            "CONFIGURACION_VALOR_ALICUOTA_INVALIDO",
            "CONTENIDO_INVALIDO",
        }
        assert _filas(entorno) == []

    @pytest.mark.parametrize("valor", [0.27, 1, 0])
    def test_inv03_un_valor_numerico_json_se_rechaza_y_no_crea_nada(
        self, cliente_http: TestClient, sesion: Session, valor: float
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_ALICUOTAS, json=_cuerpo(valor=valor), headers=con_op(headers)
        )

        assert respuesta.status_code == 422
        assert _filas(entorno) == []

    @pytest.mark.parametrize("nombre", ["", "   "])
    def test_nombre_vacio_es_nombre_invalido_422(
        self, cliente_http: TestClient, sesion: Session, nombre: str
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_ALICUOTAS, json=_cuerpo(nombre=nombre), headers=con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "NOMBRE_INVALIDO"

    @pytest.mark.parametrize("repetido", ["21%", "21% ", " 21%"])
    def test_inv02_un_nombre_repetido_es_409(
        self, cliente_http: TestClient, sesion: Session, repetido: str
    ) -> None:
        entorno = Entorno(sesion)
        _sembrar_general(entorno)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_ALICUOTAS, json=_cuerpo(nombre=repetido), headers=con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "NOMBRE_DUPLICADO"
        assert len(_filas(entorno)) == 3

    def test_inv02_el_nombre_se_compara_sin_distinguir_mayusculas_y_contra_las_de_baja(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _crear_alicuota(entorno, "IVA General", "0.210000", activo=False)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_ALICUOTAS, json=_cuerpo(nombre="iva general"), headers=con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "NOMBRE_DUPLICADO"

    @pytest.mark.parametrize("repetido", ["0.210000", "0.21"])
    def test_imp04_un_valor_repetido_es_valor_duplicado_409(
        self, cliente_http: TestClient, sesion: Session, repetido: str
    ) -> None:
        entorno = Entorno(sesion)
        _sembrar_general(entorno)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_ALICUOTAS,
            json=_cuerpo(nombre="IVA general", valor=repetido),
            headers=con_op(headers),
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "VALOR_DUPLICADO"
        assert len(_filas(entorno)) == 3

    def test_imp04_el_valor_repetido_tambien_cuenta_contra_una_de_baja(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _crear_alicuota(entorno, "Vieja", "0.270000", activo=False)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(URL_ALICUOTAS, json=_cuerpo(), headers=con_op(headers))

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "VALOR_DUPLICADO"

    def test_inv21_otra_organizacion_acepta_el_mismo_nombre_y_valor(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        una = Entorno(sesion)
        otra = Entorno(sesion)
        _sembrar_general(una)
        headers_otra = otra.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_ALICUOTAS,
            json=_cuerpo(nombre="21%", valor="0.210000"),
            headers=con_op(headers_otra),
        )

        assert respuesta.status_code == 201

    def test_seg06_sin_admin_configuracion_responde_403_sin_efectos_ni_reserva(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http, "cobrador1")

        respuesta = cliente_http.post(URL_ALICUOTAS, json=_cuerpo(), headers=con_op(headers))

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert _filas(entorno) == []
        assert entorno.contar_comandos("ALICUOTA_CREAR") == 0

    def test_inv06_reenviar_el_mismo_operation_id_no_duplica(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = con_op(entorno.entrar(cliente_http))

        primera = cliente_http.post(URL_ALICUOTAS, json=_cuerpo(), headers=headers)
        segunda = cliente_http.post(URL_ALICUOTAS, json=_cuerpo(), headers=headers)

        assert primera.status_code == segunda.status_code == 201
        assert primera.json()["id"] == segunda.json()["id"]
        assert len(_filas(entorno)) == 1
        assert len(_auditoria(entorno, "ALICUOTA_CREAR")) == 1

    def test_un_cuerpo_con_organizacion_id_se_rechaza(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_ALICUOTAS, json=_cuerpo(organizacion_id=str(uuid4())), headers=con_op(headers)
        )

        assert respuesta.status_code == 422
        assert _filas(entorno) == []

    def test_aud01_deja_una_fila_de_auditoria_con_el_estado_despues(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = con_op(entorno.entrar(cliente_http))

        creado = cliente_http.post(URL_ALICUOTAS, json=_cuerpo(), headers=headers).json()

        filas = _auditoria(entorno, "ALICUOTA_CREAR")
        assert len(filas) == 1
        assert str(filas[0]["entidad_id"]) == creado["id"]
        assert filas[0]["antes"] is None
        assert filas[0]["despues"] == {"nombre": "27%", "valor": "0.270000", "activo": True}
        assert filas[0]["usuario_id"] == entorno.usuarios["admin1"]
        assert filas[0]["origen"] == "COMANDO"


# ======================= ALICUOTA_MODIFICAR (4.4) =====================================


class TestAlicuotaModificar:
    def test_d6_renombra_conservando_el_id_y_el_valor(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _, reducida, _ = _sembrar_general(entorno)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(reducida),
            json={"nombre": " IVA reducido 10,5% ", "valor": "0.105000", "activo": True},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["id"] == str(reducida)
        assert respuesta.json()["nombre"] == "IVA reducido 10,5%"
        assert respuesta.json()["valor"] == "0.105000"

    def test_d6_el_valor_puede_viajar_con_otra_escala_si_es_el_mismo(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _, reducida, _ = _sembrar_general(entorno)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(reducida),
            json={"nombre": "10,5", "valor": "0.105", "activo": True},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 200, respuesta.text

    @pytest.mark.parametrize("otro", ["0.270000", "0.105001", "0"])
    def test_d6_un_valor_distinto_es_valor_no_modificable_422_y_nada_cambia(
        self, cliente_http: TestClient, sesion: Session, otro: str
    ) -> None:
        entorno = Entorno(sesion)
        general, _, _ = _sembrar_general(entorno)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(general),
            json={"nombre": "21%", "valor": otro, "activo": True},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "VALOR_NO_MODIFICABLE"
        assert {f["nombre"]: f["valor"] for f in _filas(entorno)}["21%"] == "0.210000"

    def test_el_valor_es_obligatorio_para_reemplazo_completo(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        general, _, _ = _sembrar_general(entorno)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(general), json={"nombre": "21%", "activo": True}, headers=con_op(headers)
        )

        assert respuesta.status_code == 422

    def test_inv02_renombrar_a_un_nombre_ajeno_es_nombre_duplicado_409(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        general, _, _ = _sembrar_general(entorno)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(general),
            json={"nombre": "10,5%", "valor": "0.210000", "activo": True},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "NOMBRE_DUPLICADO"

    def test_nombre_vacio_es_nombre_invalido_422(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        general, _, _ = _sembrar_general(entorno)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(general),
            json={"nombre": " ", "valor": "0.210000", "activo": True},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "NOMBRE_INVALIDO"

    def test_cat01_con_productos_activos_la_baja_es_alicuota_en_uso_con_la_cantidad(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        general, _, _ = _sembrar_general(entorno)
        _producto_con_alicuota(entorno, general)
        _producto_con_alicuota(entorno, general)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(general),
            json={"nombre": "21%", "valor": "0.210000", "activo": False},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "ALICUOTA_EN_USO"
        assert respuesta.json()["productos"] == 2
        assert {f["nombre"]: f["activo"] for f in _filas(entorno)}["21%"] is True

    def test_cat01_otra_organizacion_no_cuenta_en_el_uso(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        otra = Entorno(sesion)
        general, _, _ = _sembrar_general(entorno)
        general_otra = _crear_alicuota(otra, "21%", "0.210000")
        _producto_con_alicuota(otra, general_otra)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(general),
            json={"nombre": "21%", "valor": "0.210000", "activo": False},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 200, respuesta.text

    def test_cat05_solo_productos_inactivos_no_impiden_la_baja_y_el_alta_nueva_la_rechaza(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _, _, cero = _sembrar_general(entorno)
        _producto_con_alicuota(entorno, cero, activo=False)
        entorno.agregar_usuario("gestor1", frozenset({"GESTIONAR_CATALOGO"}))
        headers = entorno.entrar(cliente_http)

        baja = cliente_http.put(
            _url(cero),
            json={"nombre": "0%", "valor": "0.000000", "activo": False},
            headers=con_op(headers),
        )
        categoria = entorno.sesion.execute(
            text("SELECT id FROM categoria WHERE organizacion_id = :o LIMIT 1"), {"o": entorno.org}
        ).scalar_one()
        alta = cliente_http.post(
            URL_PRODUCTOS,
            json={
                "codigo": "NUEVO-1",
                "nombre": "Nuevo",
                "categoria_id": str(categoria),
                "proveedor_id": str(entorno.proveedor_id),
                "unidad_base": "unidad",
                "alicuota_id": str(cero),
                "presentaciones": [
                    {
                        "nombre": "Unidad",
                        "unidades_base": 1,
                        "usar_en_venta": True,
                        "usar_en_compra": True,
                        "es_referencia": True,
                    }
                ],
            },
            headers=con_op(entorno.entrar(cliente_http, "gestor1")),
        )

        assert baja.status_code == 200, baja.text
        assert baja.json()["activo"] is False
        assert alta.status_code in {409, 422}, alta.text
        assert alta.json()["codigo"] == "ALICUOTA_INACTIVA"

    def test_d8_la_ultima_activa_sin_uso_es_ultima_alicuota_activa_409(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        unica = _crear_alicuota(entorno, "21%", "0.210000")
        _crear_alicuota(entorno, "Vieja", "0.270000", activo=False)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(unica),
            json={"nombre": "21%", "valor": "0.210000", "activo": False},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "ULTIMA_ALICUOTA_ACTIVA"
        assert {f["nombre"]: f["activo"] for f in _filas(entorno)}["21%"] is True

    def test_cat05_reactivar_no_valida_uso_y_vuelve_a_ofrecerse(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _sembrar_general(entorno)
        vieja = _crear_alicuota(entorno, "27%", "0.270000", activo=False)
        headers = entorno.entrar(cliente_http)

        alta = cliente_http.put(
            _url(vieja),
            json={"nombre": "27%", "valor": "0.270000", "activo": True},
            headers=con_op(headers),
        )
        listado = cliente_http.get(URL_ALICUOTAS, headers=headers)

        assert alta.status_code == 200
        assert alta.json()["activo"] is True
        assert "27%" in [a["nombre"] for a in listado.json()["items"] if a["activo"]]

    def test_renombrar_una_inactiva_sin_otras_activas_no_es_una_baja(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # Solo una baja (activa -> inactiva) valida uso y última activa.
        entorno = Entorno(sesion)
        activa = _crear_alicuota(entorno, "21%", "0.210000")
        inactiva = _crear_alicuota(entorno, "27%", "0.270000", activo=False)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(inactiva),
            json={"nombre": "27% viejo", "valor": "0.270000", "activo": False},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 200, respuesta.text
        assert activa is not None

    def test_tr06_vta03_la_historia_congelada_no_cambia_al_renombrar_y_dar_de_baja(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # `costo_informado` (como `compra_linea` y `venta_linea`) copia `alicuota_aplicada`:
        # no apunta a la alícuota, así que renombrar o dar de baja no la toca.
        entorno = Entorno(sesion)
        general, reducida, _ = _sembrar_general(entorno)
        producto = _producto_con_alicuota(entorno, general, activo=False)
        presentacion = crear_presentacion_sql(
            entorno.sesion,
            entorno.org,
            producto,
            nombre="Caja",
            unidades_base=6,
            es_referencia=True,
        )
        entorno.sesion.execute(
            text(
                "INSERT INTO costo_informado (id, organizacion_id, proveedor_id, producto_id, "
                "presentacion_id, valor, incluye_iva, computa_credito_fiscal, bonificacion, "
                "alicuota_aplicada, costo_base, vigencia_desde, operation_id, usuario_id, "
                "creado_en) VALUES (:id, :org, :prov, :prod, :pres, 1000, false, false, 0, "
                "0.21, 1000, :vig, :op, :usr, :m)"
            ),
            {
                "id": uuid4(),
                "org": entorno.org,
                "prov": entorno.proveedor_id,
                "prod": producto,
                "pres": presentacion,
                "vig": MOMENTO.date(),
                "op": uuid4(),
                "usr": entorno.usuarios["admin1"],
                "m": MOMENTO,
            },
        )
        entorno.sesion.commit()
        headers = entorno.entrar(cliente_http)

        renombrada = cliente_http.put(
            _url(general),
            json={"nombre": "IVA general", "valor": "0.210000", "activo": True},
            headers=con_op(headers),
        )
        baja = cliente_http.put(
            _url(general),
            json={"nombre": "IVA general", "valor": "0.210000", "activo": False},
            headers=con_op(headers),
        )

        assert renombrada.status_code == baja.status_code == 200, baja.text
        entorno.sesion.rollback()
        aplicada = entorno.sesion.execute(
            text("SELECT alicuota_aplicada::text FROM costo_informado WHERE organizacion_id = :o"),
            {"o": entorno.org},
        ).scalar_one()
        assert aplicada == "0.210000"
        assert reducida is not None

    def test_inv21_una_alicuota_ajena_o_inexistente_es_404(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        una = Entorno(sesion)
        otra = Entorno(sesion)
        _sembrar_general(una)
        de_otra = _crear_alicuota(otra, "21%", "0.210000")
        headers = una.entrar(cliente_http)
        cuerpo = {"nombre": "X", "valor": "0.210000", "activo": True}

        ajena = cliente_http.put(_url(de_otra), json=cuerpo, headers=con_op(headers))
        inexistente = cliente_http.put(_url(uuid4()), json=cuerpo, headers=con_op(headers))

        assert ajena.status_code == inexistente.status_code == 404
        assert _filas(otra)[0]["nombre"] == "21%"

    def test_seg06_sin_admin_configuracion_responde_403(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        general, _, _ = _sembrar_general(entorno)
        headers = entorno.entrar(cliente_http, "cobrador1")

        respuesta = cliente_http.put(
            _url(general),
            json={"nombre": "X", "valor": "0.210000", "activo": True},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"

    def test_inv06_reenviar_el_mismo_operation_id_aplica_una_sola_vez(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        general, _, _ = _sembrar_general(entorno)
        headers = con_op(entorno.entrar(cliente_http))
        cuerpo = {"nombre": "IVA general", "valor": "0.210000", "activo": True}

        primera = cliente_http.put(_url(general), json=cuerpo, headers=headers)
        segunda = cliente_http.put(_url(general), json=cuerpo, headers=headers)

        assert primera.status_code == segunda.status_code == 200
        assert len(_auditoria(entorno, "ALICUOTA_MODIFICAR")) == 1

    def test_aud01_deja_una_fila_de_auditoria_con_antes_y_despues(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _, reducida, _ = _sembrar_general(entorno)
        headers = con_op(entorno.entrar(cliente_http))

        cliente_http.put(
            _url(reducida),
            json={"nombre": "Reducido", "valor": "0.105000", "activo": True},
            headers=headers,
        )

        filas = _auditoria(entorno, "ALICUOTA_MODIFICAR")
        assert len(filas) == 1
        assert filas[0]["antes"] == {"nombre": "10,5%", "valor": "0.105000", "activo": True}
        assert filas[0]["despues"] == {"nombre": "Reducido", "valor": "0.105000", "activo": True}
        assert filas[0]["usuario_id"] == entorno.usuarios["admin1"]


# ======================= lectura (4.5) ================================================


class TestAlicuotasLectura:
    def test_get_admite_admin_configuracion_ademas_de_los_permisos_de_siempre(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _sembrar_general(entorno)
        entorno.agregar_usuario("gestor1", frozenset({"GESTIONAR_CATALOGO"}))
        entorno.agregar_usuario("compras1", frozenset({"REGISTRAR_COMPRA"}))

        for usuario in ("admin1", "gestor1", "compras1"):
            respuesta = cliente_http.get(
                URL_ALICUOTAS, headers=entorno.entrar(cliente_http, usuario)
            )
            assert respuesta.status_code == 200, (usuario, respuesta.text)
            assert len(respuesta.json()["items"]) == 3

    def test_get_sin_ninguno_de_los_permisos_responde_403(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)

        respuesta = cliente_http.get(URL_ALICUOTAS, headers=entorno.entrar(cliente_http, "nadie1"))

        assert respuesta.status_code == 403


# ======================= catálogo y lote del bus (4.5) ================================


@pytest.mark.parametrize("tipo", ["ALICUOTA_CREAR", "ALICUOTA_MODIFICAR"])
def test_los_dos_tipos_estan_declarados_solo_online(tipo: str) -> None:
    import app.main  # noqa: F401  (puebla el catálogo real)
    from app.commands.catalogo import tipo_declarado

    declarado = tipo_declarado(tipo)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert declarado.permisos == ("ADMIN_CONFIGURACION",)


def _item_de_lote(
    entorno: Entorno,
    tipo: str,
    modo: str,
    contenido: dict[str, object],
    *,
    con_permiso: bool = True,
) -> tuple[ItemLote, UUID, UUID]:
    permisos = frozenset({"ADMIN_CONFIGURACION"}) if con_permiso else frozenset[str]()
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(
        entorno.sesion, entorno.org, permisos=permisos
    )
    entorno.sesion.commit()
    return (
        ItemLote(
            operation_id=uuid4(),
            tipo=tipo,
            version=1,
            modo=modo,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,  # type: ignore[arg-type]
        ),
        usuario_id,
        dispositivo_id,
    )


def _procesar(
    sesion: Session, entorno: Entorno, item: ItemLote, usuario_id: UUID, dispositivo_id: UUID
) -> Any:
    (resultado,) = sync_service.procesar_lote(
        sesion,
        FixedClock(MOMENTO),
        organizacion_id=entorno.org,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        items=[item],
    )
    return resultado


@pytest.mark.parametrize("tipo", ["ALICUOTA_CREAR", "ALICUOTA_MODIFICAR"])
def test_el_lote_rechaza_los_comandos_de_alicuotas_enviados_sin_conexion(
    sesion: Session, tipo: str
) -> None:
    entorno = Entorno(sesion)
    contenido: dict[str, object] = {"nombre": "27%", "valor": "0.270000"}
    item, usuario_id, dispositivo_id = _item_de_lote(entorno, tipo, "OFFLINE", contenido)

    resultado = _procesar(sesion, entorno, item, usuario_id, dispositivo_id)

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert _filas(entorno) == []


def test_por_el_lote_en_modo_online_se_comporta_igual_que_por_rest(sesion: Session) -> None:
    entorno = Entorno(sesion)
    contenido: dict[str, object] = {"nombre": "27%", "valor": "0.270000"}
    item, usuario_id, dispositivo_id = _item_de_lote(entorno, "ALICUOTA_CREAR", "ONLINE", contenido)

    resultado = _procesar(sesion, entorno, item, usuario_id, dispositivo_id)

    assert resultado.estado == "ACEPTADO", resultado
    assert [(f["nombre"], f["valor"], f["activo"]) for f in _filas(entorno)] == [
        ("27%", "0.270000", True)
    ]
    assert len(_auditoria(entorno, "ALICUOTA_CREAR")) == 1


@pytest.mark.parametrize("tipo", ["ALICUOTA_CREAR", "ALICUOTA_MODIFICAR"])
def test_por_el_lote_sin_el_permiso_responde_permiso_requerido_y_no_escribe(
    sesion: Session, tipo: str
) -> None:
    entorno = Entorno(sesion)
    contenido: dict[str, object] = {"nombre": "27%", "valor": "0.270000"}
    if tipo == "ALICUOTA_MODIFICAR":
        contenido = {
            "alicuota_id": str(uuid4()),
            "nombre": "27%",
            "valor": "0.270000",
            "activo": True,
        }
    item, usuario_id, dispositivo_id = _item_de_lote(
        entorno, tipo, "ONLINE", contenido, con_permiso=False
    )

    resultado = _procesar(sesion, entorno, item, usuario_id, dispositivo_id)

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "PERMISO_REQUERIDO"
    assert _filas(entorno) == []
