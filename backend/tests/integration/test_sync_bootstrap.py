"""Change 21, grupo 2 (spec `sync/bootstrap`): `GET /api/v1/sync/bootstrap` por HTTP, con
PostgreSQL real y `login` real.

Reglas citadas: RUT-03, SYN-10, SYN-11, VTA-06, VTA-13, ADR-006, ADR-011, ADR-028, ADR-059,
ADR-060, DSC-06, TR-09, INV-02, INV-03, INV-04, INV-12, INV-13, INV-21, `02` §12.4, `design.md`
D2, D4 a D9.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_cliente, crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql
from ventas_confirmar_utiles import EntornoVenta
from ventas_utiles import insertar_sql

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.seguridad import derivar_pin_autorizacion, hashear_password
from app.main import crear_app

PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-bootstrap"
URL = "/api/v1/sync/bootstrap"
PIN = "482915"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente_http(database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    engine = app.dependency_overrides[sistema._get_engine]()
    try:
        yield TestClient(app)
    finally:
        engine.dispose()


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


class Escenario:
    """Una organización con su vendedor (con permisos a elección) que inicia sesión desde un
    dispositivo propio y tiene, si se pide, una jornada abierta sobre el depósito."""

    def __init__(self, sesion: Session, **opciones: Any) -> None:
        self.sesion = sesion
        self.entorno = EntornoVenta(sesion, **opciones)
        self.org = self.entorno.org
        self.usuario_id = self.entorno.usuario_id
        sesion.execute(
            text("UPDATE usuario SET password_hash = :h WHERE organizacion_id = :o AND id = :u"),
            {"h": hashear_password(PASSWORD), "o": self.org, "u": self.usuario_id},
        )
        sesion.commit()
        self.dispositivo_id = uuid4()

    def entrar(self, cliente_http: TestClient, usuario_id: UUID | None = None) -> dict[str, str]:
        slug = self.sesion.execute(
            text("SELECT slug FROM organizacion WHERE id = :o"), {"o": self.org}
        ).scalar_one()
        nombre = self.sesion.execute(
            text("SELECT usuario FROM usuario WHERE id = :u"), {"u": usuario_id or self.usuario_id}
        ).scalar_one()
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": slug,
                "usuario": nombre,
                "contrasena": PASSWORD,
                "dispositivo_id": str(self.dispositivo_id),
                "nombre_dispositivo": "Teléfono",
            },
        )
        assert respuesta.status_code == 200, respuesta.text
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}

    def abrir_jornada(self, *, estado: str = "ABIERTA", dispositivo_id: UUID | None = None) -> UUID:
        jornada_id = crear_jornada_sql(
            self.sesion,
            self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=dispositivo_id or self.dispositivo_id,
            ubicacion_id=self.entorno.deposito_id,
            estado=estado,
        )
        self.sesion.commit()
        return jornada_id

    def pedir(
        self, cliente_http: TestClient, headers: dict[str, str], **params: str
    ) -> dict[str, Any]:
        respuesta = cliente_http.get(URL, headers=headers, params=params)
        assert respuesta.status_code == 200, respuesta.text
        return dict(respuesta.json())


def _listo(
    cliente_http: TestClient, sesion: Session, **opciones: Any
) -> tuple[Escenario, dict[str, str], UUID]:
    escenario = Escenario(sesion, **opciones)
    headers = escenario.entrar(cliente_http)
    return escenario, headers, escenario.abrir_jornada()


def _sin_hora(respuesta: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in respuesta.items() if k != "generado_en"}


def _claves(valor: object) -> set[str]:
    if isinstance(valor, dict):
        return set(valor) | {c for v in valor.values() for c in _claves(v)}
    if isinstance(valor, list):
        return {c for v in valor for c in _claves(v)}
    return set()


def _contar(sesion: Session, tabla: str) -> int:
    return int(sesion.execute(text(f"SELECT count(*) FROM {tabla}")).scalar_one())


# --- jornada abierta en el dispositivo (RUT-03, D2) -------------------------------------------


def test_rut03_con_la_jornada_abierta_responde_200_con_la_jornada_y_su_ubicacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, jornada_id = _listo(cliente_http, sesion)

    cuerpo = escenario.pedir(cliente_http, headers)

    assert cuerpo["sesion"]["jornada"]["id"] == str(jornada_id)
    assert cuerpo["sesion"]["jornada"]["ubicacion_id"] == str(escenario.entorno.deposito_id)
    assert cuerpo["sesion"]["jornada"]["ubicacion_nombre"] == "Depósito central"
    assert cuerpo["sesion"]["usuario"]["id"] == str(escenario.usuario_id)
    assert set(cuerpo) == {
        "generado_en",
        "sesion",
        "configuracion",
        "contexto_venta",
        "catalogos",
        "productos",
        "clientes",
        "listas",
        "reglas_descuento",
        "stock",
        "autorizadores",
    }


@pytest.mark.parametrize("caso", ["sin_jornada", "en_rendicion", "otro_dispositivo"])
def test_rut03_sin_jornada_abierta_propia_en_el_dispositivo_responde_409(
    cliente_http: TestClient, sesion: Session, caso: str
) -> None:
    escenario = Escenario(sesion)
    headers = escenario.entrar(cliente_http)
    if caso == "en_rendicion":
        escenario.abrir_jornada(estado="EN_RENDICION")
    elif caso == "otro_dispositivo":
        otro = crear_usuario_y_dispositivo(sesion, escenario.org)[1]
        escenario.abrir_jornada(dispositivo_id=otro)

    respuesta = cliente_http.get(URL, headers=headers)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "JORNADA_REQUERIDA"
    assert "clientes" not in respuesta.json()


def test_adr028_un_usuario_dado_de_baja_con_jornada_abierta_es_rechazado(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    sesion.execute(
        text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :u"), {"u": escenario.usuario_id}
    )
    sesion.commit()

    respuesta = cliente_http.get(URL, headers=headers)

    assert respuesta.status_code == 401


def test_sin_token_responde_401(cliente_http: TestClient) -> None:
    assert cliente_http.get(URL).status_code == 401


def test_adr006_since_se_ignora_y_la_respuesta_es_siempre_completa(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)

    sin = escenario.pedir(cliente_http, headers)
    con = escenario.pedir(cliente_http, headers, since="2026-10-01T00:00:00Z")

    assert _sin_hora(con) == _sin_hora(sin)
    assert len(con["clientes"]) >= 1


def test_syn02_el_doble_pedido_es_igual_y_no_escribe_nada(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    tablas = ["comando", "auditoria", "stock_movimiento", "cuenta_movimiento", "jornada"]
    antes = {t: _contar(sesion, t) for t in tablas}

    primera = escenario.pedir(cliente_http, headers)
    segunda = escenario.pedir(cliente_http, headers)

    assert _sin_hora(primera) == _sin_hora(segunda)
    assert {t: _contar(sesion, t) for t in tablas} == antes


# --- catálogo, clientes, listas, reglas ---------------------------------------------------------


def test_syn11_el_producto_trae_categoria_marca_alicuota_y_presentaciones(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    entorno = escenario.entorno
    marca_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO marca (id, organizacion_id, nombre, activo, creado_en, actualizado_en) "
            "VALUES (:i, :o, 'Bodega Norte', true, now(), now())"
        ),
        {"i": marca_id, "o": escenario.org},
    )
    sesion.execute(
        text("UPDATE producto SET marca_id = :m WHERE id = :p"),
        {"m": marca_id, "p": entorno.vino_id},
    )
    inactivo, _ = entorno.crear_producto("Dado de baja")
    sesion.execute(text("UPDATE producto SET activo = false WHERE id = :p"), {"p": inactivo})
    sesion.commit()

    cuerpo = escenario.pedir(cliente_http, headers)

    (vino,) = cuerpo["productos"]
    fila = sesion.execute(
        text("SELECT categoria_id, alicuota_id FROM producto WHERE id = :p"),
        {"p": entorno.vino_id},
    ).one()
    assert vino["id"] == str(entorno.vino_id)
    assert vino["categoria_id"] == str(fila.categoria_id)
    assert vino["marca_id"] == str(marca_id)
    assert vino["alicuota_id"] == str(fila.alicuota_id)
    assert vino["alicuota_valor"] == "0.210000"
    assert vino["presentacion_referencia_id"] == str(entorno.caja_id)
    assert [(p["unidades_base"], p["es_referencia"]) for p in vino["presentaciones"]] == [
        (1, False),
        (6, True),
    ]


def test_cartera_del_vendedor_solo_sus_clientes_en_cartera_y_sin_correo_ni_vendedor(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Cartera del vendedor": ve los tres clientes y el consumidor final, con solo sus
    dos en cartera; el cliente inactivo no baja."""
    escenario, headers, _ = _listo(cliente_http, sesion)
    entorno = escenario.entorno
    otro_vendedor = crear_usuario_y_dispositivo(sesion, escenario.org)[0]
    mio_2 = crear_cliente(sesion, escenario.org, nombre="Almacén Don Pedro")
    ajeno = crear_cliente(sesion, escenario.org, nombre="Del otro vendedor")
    final = crear_cliente(
        sesion, escenario.org, nombre="Consumidor final", es_consumidor_final=True
    )
    inactivo = crear_cliente(sesion, escenario.org, nombre="Inactivo", estado="INACTIVO")
    for cliente, vendedor in (
        (entorno.cliente_id, escenario.usuario_id),
        (mio_2, escenario.usuario_id),
        (ajeno, otro_vendedor),
    ):
        sesion.execute(
            text("UPDATE cliente SET vendedor_id = :v, email = 'x@example.com' WHERE id = :c"),
            {"v": vendedor, "c": cliente},
        )
    sesion.commit()

    cuerpo = escenario.pedir(cliente_http, headers)

    por_id = {c["id"]: c for c in cuerpo["clientes"]}
    assert set(por_id) == {str(entorno.cliente_id), str(mio_2), str(ajeno), str(final)}
    assert str(inactivo) not in por_id
    assert {i for i, c in por_id.items() if c["en_cartera"]} == {
        str(entorno.cliente_id),
        str(mio_2),
    }
    assert por_id[str(final)]["es_consumidor_final"] is True
    assert not {"email", "vendedor_id"} & _claves(cuerpo["clientes"])


def test_cartera_vacia_marca_a_todos_los_clientes_en_cartera(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    crear_cliente(sesion, escenario.org, nombre="Otro")
    sesion.commit()

    cuerpo = escenario.pedir(cliente_http, headers)

    assert len(cuerpo["clientes"]) == 2
    assert all(c["en_cartera"] for c in cuerpo["clientes"])


def test_cre01_cre03_el_cliente_trae_saldo_y_credito_resuelto(
    cliente_http: TestClient, sesion: Session
) -> None:
    """Escenario "Saldo y crédito": política `AUTORIZAR` y tolerancia `PORCENTAJE` `"5.00"` de la
    organización; el saldo es la suma de los movimientos (150000.00 del arnés)."""
    escenario, headers, _ = _listo(cliente_http, sesion)
    escenario.entorno.configurar(
        politica_credito_default="AUTORIZAR",
        tolerancia_offline_tipo="PORCENTAJE",
        tolerancia_offline_valor="5.00",
    )
    sesion.commit()

    (cliente,) = escenario.pedir(cliente_http, headers)["clientes"]

    assert cliente["saldo"] == "150000.00"
    assert cliente["credito"] == {
        "limite": None,
        "politica": "AUTORIZAR",
        "tolerancia_tipo": "PORCENTAJE",
        "tolerancia_valor": "5.00",
    }


def _lista_con_versiones(escenario: Escenario) -> dict[str, UUID]:
    """La lista predeterminada: la 1 y la 2 históricas, la 3 vigente y la 4 programada para mañana,
    una anulada (5) y un borrador (6); y otra lista activa no asignada a nadie."""
    e = escenario.entorno
    ahora = datetime.now(UTC)
    ids = {
        "v2": e.crear_version(e.lista_id, 2, ahora - timedelta(days=20), precio_vino="13000.00"),
        "v3": e.crear_version(e.lista_id, 3, ahora - timedelta(days=1), precio_vino="14000.00"),
        "v4": e.crear_version(e.lista_id, 4, ahora + timedelta(days=1), precio_vino="15000.00"),
        "anulada": e.crear_version(
            e.lista_id, 5, ahora - timedelta(days=2), estado="ANULADA", precio_vino="1.00"
        ),
        "borrador": e.crear_version(e.lista_id, 6, ahora, estado="BORRADOR", precio_vino="2.00"),
    }
    ids["otra_lista"] = e.crear_lista("Mayorista")
    e.crear_version(ids["otra_lista"], 1, ahora - timedelta(days=3), precio_vino="9000.00")
    escenario.sesion.commit()
    return ids


def _numeros(lista: dict[str, Any]) -> set[int]:
    return {v["numero"] for v in lista["versiones"]}


def test_prc20_sin_usar_lista_anterior_trae_vigente_y_programada_de_las_aplicables(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    _lista_con_versiones(escenario)

    cuerpo = escenario.pedir(cliente_http, headers)

    (lista,) = cuerpo["listas"]  # la otra lista no está asignada a nadie
    assert lista["id"] == str(escenario.entorno.lista_id)
    assert lista["es_predeterminada"] is True
    assert _numeros(lista) == {3, 4}
    estados = {v["numero"]: v["estado"] for v in lista["versiones"]}
    assert estados == {3: "VIGENTE", 4: "PROGRAMADA"}


def test_prc21_con_usar_lista_anterior_trae_todas_las_listas_con_historicas(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(
        cliente_http, sesion, permisos=frozenset({"VENDER", "USAR_LISTA_ANTERIOR"})
    )
    ids = _lista_con_versiones(escenario)

    cuerpo = escenario.pedir(cliente_http, headers)

    por_id = {lista["id"]: lista for lista in cuerpo["listas"]}
    assert set(por_id) == {str(escenario.entorno.lista_id), str(ids["otra_lista"])}
    assert _numeros(por_id[str(escenario.entorno.lista_id)]) == {1, 2, 3, 4}
    assert _numeros(por_id[str(ids["otra_lista"])]) == {1}


def test_prc22_prc23_el_precio_trae_importe_como_string_y_unidades_como_entero(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)

    (lista,) = escenario.pedir(cliente_http, headers)["listas"]

    (version,) = lista["versiones"]
    assert version["precios"] == [
        {
            "producto_id": str(escenario.entorno.vino_id),
            "precio_referencia": "12500.00",
            "unidades_referencia": 6,
        }
    ]


def _regla(escenario: Escenario, nombre: str, desde: datetime, hasta: datetime | None) -> UUID:
    regla_id = uuid4()
    insertar_sql(
        escenario.sesion,
        "regla_descuento",
        {
            "id": regla_id,
            "organizacion_id": escenario.org,
            "nombre": nombre,
            "tipo": "VOLUMEN_OPERACION",
            "medida": "CAJAS_EQUIVALENTES",
            "operador": "GTE",
            "umbral": "20",
            "accion_tipo": "PORCENTAJE",
            "accion_porcentaje": "0.050000",
            "prioridad": 1,
            "acumulable": False,
            "vigencia_desde": desde,
            "vigencia_hasta": hasta,
            "estado": "ACTIVA",
            "creado_en": desde,
            "actualizado_en": desde,
        },
    )
    escenario.sesion.commit()
    return regla_id


def test_dsc01_la_regla_programada_baja_con_su_vigencia_y_la_vencida_no(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    ahora = datetime.now(UTC)
    tarde = _regla(escenario, "De la tarde", ahora + timedelta(hours=6), None)
    _regla(escenario, "Vencida", ahora - timedelta(days=10), ahora - timedelta(days=1))

    (regla,) = escenario.pedir(cliente_http, headers)["reglas_descuento"]

    assert regla["id"] == str(tarde)
    assert regla["nombre"] == "De la tarde"
    assert regla["umbral"] == "20.0000"
    assert regla["accion_porcentaje"] == "0.050000"
    assert regla["vigencia_hasta"] is None
    assert regla["alcances"] == []


def test_dsc06_el_contexto_trae_el_tope_propio_y_el_permiso_del_descuento_manual(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(
        cliente_http, sesion, permisos=frozenset({"VENDER", "DESCUENTO_MANUAL"})
    )
    sesion.execute(
        text("UPDATE usuario SET tope_descuento_override = 0.05 WHERE id = :u"),
        {"u": escenario.usuario_id},
    )
    escenario.entorno.configurar(descuento_manual_habilitado=True)
    sesion.commit()

    contexto = escenario.pedir(cliente_http, headers)["contexto_venta"]

    assert contexto["descuento_manual"]["tope"] == "0.050000"
    assert contexto["descuento_manual"]["tiene_permiso"] is True
    assert contexto["descuento_manual"]["habilitado"] is True
    assert contexto["puede_superar_credito"] is False


def test_tr09_los_catalogos_traen_solo_activos_de_todos_los_ambitos(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    e = escenario.entorno
    e.crear_medio("Cheque", requiere_referencia=True, activo=False)
    baja = e.crear_motivo("ANULACION_VENTA", "De baja", activo=False)
    e.crear_motivo("ANULACION_VENTA", "Error de carga")
    sesion.execute(
        text(
            "INSERT INTO alicuota_iva (id, organizacion_id, nombre, valor, activo, creado_en, "
            "actualizado_en) VALUES (:i, :o, '10,5%', 0.105000, false, now(), now())"
        ),
        {"i": uuid4(), "o": escenario.org},
    )
    sesion.commit()

    catalogos = escenario.pedir(cliente_http, headers)["catalogos"]

    assert {m["nombre"] for m in catalogos["medios_pago"]} == {"Efectivo", "Transferencia"}
    ambitos = {(m["ambito"], m["nombre"]) for m in catalogos["motivos"]}
    assert ("ANULACION_VENTA", "Error de carga") in ambitos
    assert ("LISTA_ANTERIOR", "Precio acordado con el cliente") in ambitos
    assert str(baja) not in {m["id"] for m in catalogos["motivos"]}
    assert [a["valor"] for a in catalogos["alicuotas"]] == ["0.210000"]


# --- permisos del momento, autorizadores, stock, numeración, configuración --------------------


def test_syn10_sin_vender_el_contexto_y_los_autorizadores_vienen_vacios(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion, permisos=frozenset({"REGISTRAR_COBRANZA"}))
    supervisor = crear_usuario_y_dispositivo(
        sesion, escenario.org, permisos=frozenset({"AUTORIZAR_DESCUENTO"})
    )[0]
    hash_hex, sal, iteraciones = derivar_pin_autorizacion(PIN, iteraciones=1_000)
    sesion.execute(
        text(
            "UPDATE usuario SET pin_autorizacion_hash = :h, pin_autorizacion_sal = :s, "
            "pin_autorizacion_iteraciones = :i WHERE id = :u"
        ),
        {"h": hash_hex, "s": sal, "i": iteraciones, "u": supervisor},
    )
    sesion.commit()

    cuerpo = escenario.pedir(cliente_http, headers)

    assert "VENDER" not in cuerpo["sesion"]["permisos"]
    assert cuerpo["contexto_venta"] is None
    assert cuerpo["autorizadores"] == []
    assert len(cuerpo["clientes"]) == 1  # lo demás se baja igual (D2)


def test_sec05_los_autorizadores_traen_la_derivacion_de_su_pin_y_no_a_quien_no_tiene_pin(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    sup01 = crear_usuario_y_dispositivo(
        sesion, escenario.org, permisos=frozenset({"AUTORIZAR_DESCUENTO"})
    )[0]
    sin_pin = crear_usuario_y_dispositivo(
        sesion, escenario.org, permisos=frozenset({"SUPERAR_CREDITO"})
    )[0]
    hash_hex, sal, iteraciones = derivar_pin_autorizacion(PIN, iteraciones=1_000)
    sesion.execute(
        text(
            "UPDATE usuario SET pin_autorizacion_hash = :h, pin_autorizacion_sal = :s, "
            "pin_autorizacion_iteraciones = :i WHERE id = :u"
        ),
        {"h": hash_hex, "s": sal, "i": iteraciones, "u": sup01},
    )
    sesion.commit()

    autorizadores = escenario.pedir(cliente_http, headers)["autorizadores"]

    assert [a["id"] for a in autorizadores] == [str(sup01)]
    assert str(sin_pin) not in {a["id"] for a in autorizadores}
    assert autorizadores[0]["permisos"] == ["AUTORIZAR_DESCUENTO"]
    assert (
        autorizadores[0]["pin_hash"],
        autorizadores[0]["pin_sal"],
        autorizadores[0]["iteraciones"],
    ) == (hash_hex, sal, iteraciones)


def test_rut04_el_stock_es_el_de_la_ubicacion_tomada_en_unidad_base(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    e = escenario.entorno
    otra = crear_ubicacion_sql(sesion, escenario.org, nombre="Otra bodega")
    e.comprar(e.vino_id, 500, "1000", ubicacion_id=otra)
    sesion.commit()

    stock = escenario.pedir(cliente_http, headers)["stock"]

    assert stock == [{"producto_id": str(e.vino_id), "cantidad_base": 48}]
    assert isinstance(stock[0]["cantidad_base"], int)


def test_vta06_la_numeracion_es_la_del_dispositivo(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    sesion.execute(
        text("UPDATE dispositivo SET prefijo = 'V03', ultimo_correlativo = 142 WHERE id = :d"),
        {"d": escenario.dispositivo_id},
    )
    sesion.commit()

    numeracion = escenario.pedir(cliente_http, headers)["sesion"]["numeracion"]

    assert numeracion == {"prefijo": "V03", "ultimo_correlativo": 142}


def test_vta13_la_configuracion_trae_los_datos_de_la_nota_y_los_de_la_organizacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    escenario.entorno.configurar(
        nota_venta_domicilio="Av. Libertador 123",
        nota_venta_telefono="261 555 0000",
        nota_venta_muestra_saldo=True,
        intentos_pin_max=4,
    )
    sesion.execute(
        text(
            "UPDATE organizacion SET cuit = '30712345678', nombre = 'Distribuidora Sur' "
            "WHERE id = :o"
        ),
        {"o": escenario.org},
    )
    sesion.commit()

    configuracion = escenario.pedir(cliente_http, headers)["configuracion"]

    assert configuracion["nota"] == {
        "domicilio": "Av. Libertador 123",
        "telefono": "261 555 0000",
        "muestra_saldo": True,
    }
    assert configuracion["nombre"] == "Distribuidora Sur"
    assert configuracion["cuit"] == "30712345678"
    assert configuracion["condicion_iva"] == "MONOTRIBUTO"
    assert configuracion["intentos_pin_max"] == 4
    assert configuracion["moneda"] == "ARS"


def test_syn10_los_permisos_son_los_del_momento(cliente_http: TestClient, sesion: Session) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)
    assert "VENDER" in escenario.pedir(cliente_http, headers)["sesion"]["permisos"]
    sesion.execute(
        text(
            "DELETE FROM rol_permiso WHERE permiso_codigo = 'VENDER' AND rol_id = "
            "(SELECT rol_id FROM usuario WHERE id = :u)"
        ),
        {"u": escenario.usuario_id},
    )
    sesion.commit()

    cuerpo = escenario.pedir(cliente_http, headers)

    assert "VENDER" not in cuerpo["sesion"]["permisos"]
    assert cuerpo["contexto_venta"] is None


def test_inv03_inv04_importes_como_string_y_cantidades_como_entero(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(cliente_http, sesion)

    cuerpo = escenario.pedir(cliente_http, headers)

    cliente = cuerpo["clientes"][0]
    assert isinstance(cliente["saldo"], str)
    assert isinstance(cuerpo["listas"][0]["versiones"][0]["precios"][0]["precio_referencia"], str)
    assert isinstance(cuerpo["listas"][0]["versiones"][0]["precios"][0]["unidades_referencia"], int)
    assert all(isinstance(s["cantidad_base"], int) for s in cuerpo["stock"])
    assert isinstance(cuerpo["productos"][0]["presentaciones"][0]["unidades_base"], int)


# --- organización y costos (INV-21, INV-02, D7) -------------------------------------------------


def test_inv21_nada_de_otra_organizacion_en_el_bootstrap(
    cliente_http: TestClient, sesion: Session
) -> None:
    propio, headers, _ = _listo(cliente_http, sesion)
    ajeno = Escenario(sesion)
    ajeno.entorno.crear_medio("Medio ajeno", requiere_referencia=False)
    _regla(ajeno, "Regla ajena", datetime.now(UTC) - timedelta(days=1), None)
    ajeno.entorno.crear_producto("Producto ajeno")
    sesion.commit()

    cuerpo = propio.pedir(cliente_http, headers)

    texto = str(cuerpo)
    for id_ajeno in (
        ajeno.org,
        ajeno.entorno.cliente_id,
        ajeno.entorno.vino_id,
        ajeno.entorno.lista_id,
        ajeno.usuario_id,
    ):
        assert str(id_ajeno) not in texto
    assert "Medio ajeno" not in texto
    assert "Regla ajena" not in texto
    assert "Producto ajeno" not in texto


def test_inv02_sin_costos_ni_margenes_aunque_tenga_ver_costos(
    cliente_http: TestClient, sesion: Session
) -> None:
    escenario, headers, _ = _listo(
        cliente_http, sesion, permisos=frozenset({"VENDER", "VER_COSTOS"})
    )

    cuerpo = escenario.pedir(cliente_http, headers)

    assert "VER_COSTOS" in cuerpo["sesion"]["permisos"]
    prohibidas = {
        c for c in _claves(cuerpo) if any(p in c for p in ("costo", "margen", "utilidad", "markup"))
    }
    assert prohibidas == set()


def test_adr011_ninguna_respuesta_ni_log_incluye_pin_ni_contrasena(
    cliente_http: TestClient, sesion: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """4.3 (gobernanza ALTA): ni el PIN en claro, ni la contraseña, ni `password_hash` en la
    respuesta; la derivación (hash, sal, iteraciones) sí baja por diseño (D8) pero no se registra
    en el log."""
    escenario, headers, _ = _listo(cliente_http, sesion)
    sup = crear_usuario_y_dispositivo(
        sesion, escenario.org, permisos=frozenset({"AUTORIZAR_DESCUENTO"})
    )[0]
    hash_hex, sal, iteraciones = derivar_pin_autorizacion(PIN, iteraciones=1_000)
    sesion.execute(
        text(
            "UPDATE usuario SET pin_autorizacion_hash = :h, pin_autorizacion_sal = :s, "
            "pin_autorizacion_iteraciones = :i WHERE id = :u"
        ),
        {"h": hash_hex, "s": sal, "i": iteraciones, "u": sup},
    )
    sesion.commit()
    password_hash = sesion.execute(
        text("SELECT password_hash FROM usuario WHERE id = :u"), {"u": escenario.usuario_id}
    ).scalar_one()

    with caplog.at_level(logging.DEBUG):
        respuesta = cliente_http.get(URL, headers=headers)

    assert respuesta.status_code == 200
    crudo = respuesta.text
    assert PIN not in crudo and PASSWORD not in crudo and password_hash not in crudo
    assert not {c for c in _claves(respuesta.json()) if "password" in c or "contrasena" in c}
    registro = "\n".join(r.getMessage() for r in caplog.records)
    for secreto in (PIN, PASSWORD, password_hash, hash_hex, sal):
        assert secreto not in registro
    assert not sesion.execute(
        text("SELECT 1 FROM auditoria a WHERE a::text LIKE :p LIMIT 1"), {"p": f"%{hash_hex}%"}
    ).first()


def test_inv21_ratchet_el_bootstrap_es_de_lectura_y_de_otra_organizacion_no_se_ve(
    cliente_http: TestClient, sesion: Session
) -> None:
    """La ruta no recibe ningún id: el aislamiento es estructural (todo sale del token). Un
    vendedor de B con jornada propia recibe solo lo de B."""
    propio, headers_a, _ = _listo(cliente_http, sesion)
    ajeno, headers_b, _ = _listo(cliente_http, sesion)

    de_a = propio.pedir(cliente_http, headers_a)
    de_b = ajeno.pedir(cliente_http, headers_b)

    assert {c["id"] for c in de_a["clientes"]}.isdisjoint({c["id"] for c in de_b["clientes"]})
    assert de_a["sesion"]["usuario"]["id"] != de_b["sesion"]["usuario"]["id"]
