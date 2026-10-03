"""Change 09, grupo 7, tareas 7.1 y 7.2: endpoints HTTP de `stock`.

Escrituras dedicadas (`POST /stock/ubicaciones`, `PUT /stock/ubicaciones/{id}`,
`POST /stock/iniciales`) y lecturas (`GET /stock/ubicaciones`,
`GET /stock/ubicaciones/{id}/saldos`, `GET /stock/kardex`).

Mismo arnés HTTP que `test_cuentas_corrientes_api.py`: PostgreSQL real, motor
propio de la aplicación y `login` real (nunca un access token fabricado). Los
movimientos con fechas concretas se siembran con el servicio y un `commit`,
porque la ruta de escritura solo registra con el `occurred_at` del reloj.

La ruta del costo promedio vive en `catalogo`
(`GET /catalogo/productos/{producto_id}/costo`, enmienda a D3 del 2026-09-30) y se
prueba al final de este archivo, con Administrador y Vendedor.

Reglas citadas: STK-01, STK-02, STK-04, STK-05, INV-03, INV-04, INV-06, INV-21,
SEG-06, SEG-07, TR-04, TR-07, CAT-08, CST-11 y `design.md` D1, D2, D3, D4, D5, D6,
D7, D8, D11.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_presentacion_referencia_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
    desactivar_producto_sql,
    insertar_stock_movimiento_sql,
)

from app.api_v1 import sistema
from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository as identidad_repository
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeStockInicial

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-stock-api"
URL_UBICACIONES = "/api/v1/stock/ubicaciones"
URL_INICIALES = "/api/v1/stock/iniciales"
URL_KARDEX = "/api/v1/stock/kardex"

ADMIN = frozenset({"ADMIN_CONFIGURACION", "IMPORTAR_DATOS", "TRANSFERIR_STOCK", "VER_COSTOS"})
VENDEDOR = frozenset({"TRANSFERIR_STOCK"})


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente(database_url: str) -> Iterator[TestClient]:
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
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


class Entorno:
    """Una organización con su usuario, un dispositivo de siembra, dos productos y
    un depósito."""

    def __init__(
        self, sesion: Session, *, permisos: frozenset[str], nombre_usuario: str = "admin1"
    ) -> None:
        self.sesion = sesion
        organizacion = crear_organizacion(sesion)
        self.org = organizacion.id
        self.slug = organizacion.slug
        self.nombre_usuario = nombre_usuario
        rol = identidad_repository.crear_rol(
            self.org,
            sesion,
            rol_id=nuevo_id(),
            nombre="Rol de prueba",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO,
        )
        for codigo in permisos:
            identidad_repository.asignar_permiso_a_rol(
                self.org, sesion, rol_id=rol.id, permiso_codigo=codigo
            )
        self.usuario_id = identidad_repository.crear_usuario(
            self.org,
            sesion,
            usuario_id=nuevo_id(),
            usuario=nombre_usuario,
            nombre="Persona de prueba",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        ).id
        self.dispositivo_id = identidad_repository.crear_dispositivo(
            self.org,
            sesion,
            dispositivo_id=nuevo_id(),
            nombre="Dispositivo de siembra",
            prefijo="S01",
            ultimo_correlativo=0,
            estado="ACTIVO",
            momento=MOMENTO,
        ).id
        self.producto_id = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.otro_producto_id = crear_producto_sql(sesion, self.org, nombre="Cerveza B")
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")

    def sembrar(
        self,
        producto_id: UUID,
        cantidad: int,
        costo: str | None,
        *,
        ubicacion_id: UUID | None = None,
        occurred_at: datetime = MOMENTO,
    ) -> None:
        stock_service.registrar_stock_inicial(
            self.org,
            self.sesion,
            FixedClock(occurred_at),
            ubicacion_id=ubicacion_id or self.deposito_id,
            lineas=[LineaDeStockInicial(producto_id, cantidad, costo)],
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=occurred_at,
        )

    def confirmar_y_entrar(self, cliente_http: TestClient) -> dict[str, str]:
        self.sesion.commit()
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": self.nombre_usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 200
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def _con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


def _cuerpo_inicial(
    entorno: Entorno, *, lineas: list[dict[str, object]] | None = None, **cambios: object
) -> dict[str, object]:
    cuerpo: dict[str, object] = {
        "ubicacion_id": str(entorno.deposito_id),
        "lineas": lineas
        if lineas is not None
        else [
            {
                "producto_id": str(entorno.producto_id),
                "cantidad_base": 60,
                "costo_unitario": "1000.00",
            }
        ],
    }
    cuerpo.update(cambios)
    return cuerpo


def _cuerpo_ubicacion(**cambios: object) -> dict[str, object]:
    cuerpo: dict[str, object] = {
        "nombre": "Depósito norte",
        "tipo": "DEPOSITO",
        "requiere_toma": False,
    }
    cuerpo.update(cambios)
    return cuerpo


def _contar(sesion: Session, tabla: str, organizacion_id: UUID) -> int:
    sesion.rollback()
    return int(
        sesion.scalar(
            text(f"select count(*) from {tabla} where organizacion_id = :o"),  # noqa: S608
            {"o": organizacion_id},
        )
        or 0
    )


# ======================= 7.1 escrituras: ubicaciones ==========================


class TestUbicacionCrear:
    def test_sin_operation_id_se_rechaza_con_400(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(URL_UBICACIONES, json=_cuerpo_ubicacion(), headers=headers)

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"

    def test_sin_admin_configuracion_responde_403_sin_efectos_ni_reserva(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        # D2: `IMPORTAR_DATOS` y `TRANSFERIR_STOCK` no alcanzan para administrar.
        entorno = Entorno(sesion, permisos=frozenset({"IMPORTAR_DATOS", "TRANSFERIR_STOCK"}))
        headers = entorno.confirmar_y_entrar(cliente)
        operation_id = uuid4()

        respuesta = cliente.post(
            URL_UBICACIONES, json=_cuerpo_ubicacion(), headers=_con_op(headers, operation_id)
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert _contar(sesion, "ubicacion", entorno.org) == 1  # solo el depósito de siembra
        assert (
            sesion.scalar(
                text("select count(*) from comando where operation_id = :o"),
                {"o": str(operation_id)},
            )
            == 0
        )

    def test_crea_un_deposito_activo_y_lo_devuelve(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            URL_UBICACIONES,
            json=_cuerpo_ubicacion(nombre="  Depósito norte "),
            headers=_con_op(headers),
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        UUID(cuerpo["id"])
        assert cuerpo["nombre"] == "Depósito norte"
        assert (cuerpo["tipo"], cuerpo["requiere_toma"], cuerpo["activo"]) == (
            "DEPOSITO",
            False,
            True,
        )
        assert "organizacion_id" not in cuerpo

    def test_reenviar_el_mismo_operation_id_no_duplica(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = _con_op(entorno.confirmar_y_entrar(cliente))

        primera = cliente.post(URL_UBICACIONES, json=_cuerpo_ubicacion(), headers=headers)
        segunda = cliente.post(URL_UBICACIONES, json=_cuerpo_ubicacion(), headers=headers)

        assert primera.status_code == segunda.status_code == 201
        assert primera.json()["id"] == segunda.json()["id"]
        assert _contar(sesion, "ubicacion", entorno.org) == 2

    def test_mismo_operation_id_con_otro_contenido_es_comando_inconsistente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = _con_op(entorno.confirmar_y_entrar(cliente))
        cliente.post(URL_UBICACIONES, json=_cuerpo_ubicacion(), headers=headers)

        segunda = cliente.post(
            URL_UBICACIONES, json=_cuerpo_ubicacion(nombre="Otro nombre"), headers=headers
        )

        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"
        assert _contar(sesion, "ubicacion", entorno.org) == 2

    def test_un_vehiculo_sin_toma_se_rechaza_y_con_toma_se_acepta(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)

        sin_toma = cliente.post(
            URL_UBICACIONES,
            json=_cuerpo_ubicacion(nombre="Camión 1", tipo="VEHICULO"),
            headers=_con_op(headers),
        )
        con_toma = cliente.post(
            URL_UBICACIONES,
            json=_cuerpo_ubicacion(nombre="Camión 1", tipo="VEHICULO", requiere_toma=True),
            headers=_con_op(headers),
        )

        assert sin_toma.status_code == 422
        assert sin_toma.json()["codigo"] == "VEHICULO_REQUIERE_TOMA"
        assert con_toma.status_code == 201
        assert con_toma.json()["requiere_toma"] is True

    def test_un_nombre_repetido_es_409_y_otra_organizacion_puede_repetirlo(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno_a = Entorno(sesion, permisos=ADMIN, nombre_usuario="a1")
        entorno_b = Entorno(sesion, permisos=ADMIN, nombre_usuario="b1")
        crear_ubicacion_sql(sesion, entorno_a.org, nombre="Camion unico")
        headers_a = entorno_a.confirmar_y_entrar(cliente)
        headers_b = entorno_b.confirmar_y_entrar(cliente)

        repetido = cliente.post(
            URL_UBICACIONES,
            json=_cuerpo_ubicacion(nombre=" CAMION UNICO"),
            headers=_con_op(headers_a),
        )
        de_otra_org = cliente.post(
            URL_UBICACIONES,
            json=_cuerpo_ubicacion(nombre="Camion unico"),
            headers=_con_op(headers_b),
        )

        assert repetido.status_code == 409
        assert repetido.json()["codigo"] == "NOMBRE_DUPLICADO"
        assert de_otra_org.status_code == 201
        assert _contar(sesion, "ubicacion", entorno_b.org) == 2

    @pytest.mark.parametrize(
        "cambios",
        [{"organizacion_id": str(uuid4())}, {"activo": False}, {"tipo": "CAMION"}, {"nombre": 7}],
    )
    def test_un_cuerpo_malformado_se_rechaza_con_422(
        self, cliente: TestClient, sesion: Session, cambios: dict[str, object]
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            URL_UBICACIONES, json=_cuerpo_ubicacion(**cambios), headers=_con_op(headers)
        )

        assert respuesta.status_code == 422
        assert _contar(sesion, "ubicacion", entorno.org) == 1


class TestUbicacionModificar:
    def _url(self, ubicacion_id: UUID) -> str:
        return f"{URL_UBICACIONES}/{ubicacion_id}"

    def _cuerpo(self, **cambios: object) -> dict[str, object]:
        cuerpo: dict[str, object] = {
            "nombre": "Depósito renombrado",
            "tipo": "DEPOSITO",
            "requiere_toma": True,
            "activo": True,
        }
        cuerpo.update(cambios)
        return cuerpo

    def test_modifica_los_datos_y_los_devuelve(self, cliente: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.put(
            self._url(entorno.deposito_id), json=self._cuerpo(), headers=_con_op(headers)
        )

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["id"] == str(entorno.deposito_id)
        assert (cuerpo["nombre"], cuerpo["requiere_toma"]) == ("Depósito renombrado", True)

    def test_sin_admin_configuracion_responde_403(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.put(
            self._url(entorno.deposito_id), json=self._cuerpo(), headers=_con_op(headers)
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"

    def test_una_ubicacion_de_otra_organizacion_o_inexistente_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno_a = Entorno(sesion, permisos=ADMIN, nombre_usuario="a1")
        entorno_b = Entorno(sesion, permisos=ADMIN, nombre_usuario="b1")
        headers_b = entorno_b.confirmar_y_entrar(cliente)

        ajena = cliente.put(
            self._url(entorno_a.deposito_id), json=self._cuerpo(), headers=_con_op(headers_b)
        )
        inexistente = cliente.put(
            self._url(uuid4()), json=self._cuerpo(), headers=_con_op(headers_b)
        )

        assert ajena.status_code == 404
        assert ajena.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert inexistente.status_code == 404
        nombre = sesion.scalar(
            text("select nombre from ubicacion where id = :i"), {"i": entorno_a.deposito_id}
        )
        assert nombre == "Depósito central"

    def test_no_se_desactiva_con_stock_pero_si_sin_stock_y_se_reactiva(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        vacia = crear_ubicacion_sql(sesion, entorno.org, nombre="Vacía")
        entorno.sembrar(entorno.producto_id, 60, "1000")
        headers = entorno.confirmar_y_entrar(cliente)

        con_stock = cliente.put(
            self._url(entorno.deposito_id),
            json=self._cuerpo(nombre="Depósito central", activo=False),
            headers=_con_op(headers),
        )
        desactivada = cliente.put(
            self._url(vacia),
            json=self._cuerpo(nombre="Vacía", activo=False),
            headers=_con_op(headers),
        )
        reactivada = cliente.put(
            self._url(vacia),
            json=self._cuerpo(nombre="Vacía", activo=True),
            headers=_con_op(headers),
        )

        assert con_stock.status_code == 409
        assert con_stock.json()["codigo"] == "UBICACION_CON_STOCK"
        assert desactivada.status_code == 200
        assert desactivada.json()["activo"] is False
        assert reactivada.json()["activo"] is True

    def test_un_vehiculo_sin_toma_o_un_nombre_ajeno_se_rechazan(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        camion = crear_ubicacion_sql(
            sesion, entorno.org, nombre="Camión 1", tipo="VEHICULO", requiere_toma=True
        )
        headers = entorno.confirmar_y_entrar(cliente)

        sin_toma = cliente.put(
            self._url(camion),
            json=self._cuerpo(nombre="Camión 1", tipo="VEHICULO", requiere_toma=False),
            headers=_con_op(headers),
        )
        duplicado = cliente.put(
            self._url(camion),
            json=self._cuerpo(nombre="depósito central"),
            headers=_con_op(headers),
        )

        assert sin_toma.status_code == 422
        assert sin_toma.json()["codigo"] == "VEHICULO_REQUIERE_TOMA"
        assert duplicado.status_code == 409
        assert duplicado.json()["codigo"] == "NOMBRE_DUPLICADO"

    def test_reenviar_el_mismo_operation_id_devuelve_lo_mismo(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = _con_op(entorno.confirmar_y_entrar(cliente))

        primera = cliente.put(self._url(entorno.deposito_id), json=self._cuerpo(), headers=headers)
        segunda = cliente.put(self._url(entorno.deposito_id), json=self._cuerpo(), headers=headers)

        assert primera.status_code == segunda.status_code == 200
        assert primera.json() == segunda.json()


# ======================= 7.1 escrituras: stock inicial ========================


class TestStockInicialRegistrar:
    def test_sin_operation_id_se_rechaza_con_400(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(URL_INICIALES, json=_cuerpo_inicial(entorno), headers=headers)

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
        assert _contar(sesion, "stock_movimiento", entorno.org) == 0

    def test_sin_importar_datos_responde_403_sin_efectos_ni_reserva(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        # D1: `ADMIN_CONFIGURACION` y `TRANSFERIR_STOCK` no alcanzan para cargar.
        entorno = Entorno(sesion, permisos=frozenset({"ADMIN_CONFIGURACION", "TRANSFERIR_STOCK"}))
        headers = entorno.confirmar_y_entrar(cliente)
        operation_id = uuid4()

        respuesta = cliente.post(
            URL_INICIALES, json=_cuerpo_inicial(entorno), headers=_con_op(headers, operation_id)
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert _contar(sesion, "stock_movimiento", entorno.org) == 0
        assert (
            sesion.scalar(
                text("select count(*) from comando where operation_id = :o"),
                {"o": str(operation_id)},
            )
            == 0
        )

    def test_registra_el_stock_inicial_y_no_devuelve_costos(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            URL_INICIALES, json=_cuerpo_inicial(entorno), headers=_con_op(headers)
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["ubicacion_id"] == str(entorno.deposito_id)
        (linea,) = cuerpo["lineas"]
        assert linea["producto_id"] == str(entorno.producto_id)
        assert (linea["cantidad_base"], linea["saldo"]) == (60, 60)
        UUID(linea["movimiento_id"])
        assert "costo" not in respuesta.text  # el resultado no expone costos (D3)

    def test_una_correccion_negativa_y_un_segundo_ingreso_se_acumulan(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)
        producto = str(entorno.producto_id)

        cliente.post(URL_INICIALES, json=_cuerpo_inicial(entorno), headers=_con_op(headers))
        segundo = cliente.post(
            URL_INICIALES,
            json=_cuerpo_inicial(
                entorno,
                lineas=[{"producto_id": producto, "cantidad_base": 60, "costo_unitario": "1100"}],
            ),
            headers=_con_op(headers),
        )
        correccion = cliente.post(
            URL_INICIALES,
            json=_cuerpo_inicial(entorno, lineas=[{"producto_id": producto, "cantidad_base": -12}]),
            headers=_con_op(headers),
        )

        assert segundo.json()["lineas"][0]["saldo"] == 120
        assert correccion.status_code == 201
        assert correccion.json()["lineas"][0]["saldo"] == 108

    def test_reenviar_el_mismo_operation_id_no_duplica(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = _con_op(entorno.confirmar_y_entrar(cliente))

        primera = cliente.post(URL_INICIALES, json=_cuerpo_inicial(entorno), headers=headers)
        segunda = cliente.post(URL_INICIALES, json=_cuerpo_inicial(entorno), headers=headers)

        assert primera.status_code == segunda.status_code == 201
        assert primera.json() == segunda.json()
        assert _contar(sesion, "stock_movimiento", entorno.org) == 1

    def test_mismo_operation_id_con_otro_contenido_es_comando_inconsistente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = _con_op(entorno.confirmar_y_entrar(cliente))
        cliente.post(URL_INICIALES, json=_cuerpo_inicial(entorno), headers=headers)
        otro = [
            {
                "producto_id": str(entorno.producto_id),
                "cantidad_base": 5,
                "costo_unitario": "9",
            }
        ]

        segunda = cliente.post(
            URL_INICIALES, json=_cuerpo_inicial(entorno, lineas=otro), headers=headers
        )

        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"
        assert _contar(sesion, "stock_movimiento", entorno.org) == 1

    @pytest.mark.parametrize("costo", [1000.5, 1000, "0", "-1", "1.1234567", "abc"])
    def test_un_costo_invalido_se_rechaza_con_422_y_codigo(
        self, cliente: TestClient, sesion: Session, costo: object
    ) -> None:
        # INV-03: un número JSON en vez de un string no se acepta ni se redondea.
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)
        lineas = [
            {"producto_id": str(entorno.producto_id), "cantidad_base": 5, "costo_unitario": costo}
        ]

        respuesta = cliente.post(
            URL_INICIALES, json=_cuerpo_inicial(entorno, lineas=lineas), headers=_con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "COSTO_INVALIDO"
        assert _contar(sesion, "stock_movimiento", entorno.org) == 0

    @pytest.mark.parametrize("cantidad", [1.5, "12", True, 0, None])
    def test_una_cantidad_que_no_es_un_entero_distinto_de_cero_se_rechaza_con_422(
        self, cliente: TestClient, sesion: Session, cantidad: object
    ) -> None:
        # INV-04.
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)
        lineas = [
            {
                "producto_id": str(entorno.producto_id),
                "cantidad_base": cantidad,
                "costo_unitario": "5",
            }
        ]

        respuesta = cliente.post(
            URL_INICIALES, json=_cuerpo_inicial(entorno, lineas=lineas), headers=_con_op(headers)
        )

        assert respuesta.status_code == 422
        assert _contar(sesion, "stock_movimiento", entorno.org) == 0

    def test_lineas_vacias_o_con_un_producto_repetido_o_de_mas_se_rechazan(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)
        linea = {
            "producto_id": str(entorno.producto_id),
            "cantidad_base": 5,
            "costo_unitario": "5",
        }

        vacias = cliente.post(
            URL_INICIALES, json=_cuerpo_inicial(entorno, lineas=[]), headers=_con_op(headers)
        )
        repetido = cliente.post(
            URL_INICIALES,
            json=_cuerpo_inicial(entorno, lineas=[linea, linea]),
            headers=_con_op(headers),
        )
        demasiadas = cliente.post(
            URL_INICIALES,
            json=_cuerpo_inicial(
                entorno,
                lineas=[{**linea, "producto_id": str(uuid4())} for _ in range(201)],
            ),
            headers=_con_op(headers),
        )

        assert (vacias.status_code, vacias.json()["codigo"]) == (422, "LINEAS_INVALIDAS")
        assert (repetido.status_code, repetido.json()["codigo"]) == (422, "PRODUCTO_REPETIDO")
        assert (demasiadas.status_code, demasiadas.json()["codigo"]) == (422, "LINEAS_INVALIDAS")
        assert _contar(sesion, "stock_movimiento", entorno.org) == 0

    def test_un_campo_extra_se_rechaza_con_422(self, cliente: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            URL_INICIALES,
            json=_cuerpo_inicial(entorno, organizacion_id=str(uuid4())),
            headers=_con_op(headers),
        )

        assert respuesta.status_code == 422

    def test_una_correccion_que_deja_negativo_es_409(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)
        lineas = [{"producto_id": str(entorno.producto_id), "cantidad_base": -1}]

        respuesta = cliente.post(
            URL_INICIALES, json=_cuerpo_inicial(entorno, lineas=lineas), headers=_con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "STOCK_INSUFICIENTE"

    def test_una_ubicacion_o_un_producto_de_otra_organizacion_o_inexistente_es_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno_a = Entorno(sesion, permisos=ADMIN, nombre_usuario="a1")
        entorno_b = Entorno(sesion, permisos=ADMIN, nombre_usuario="b1")
        headers_b = entorno_b.confirmar_y_entrar(cliente)

        ubicacion_ajena = cliente.post(
            URL_INICIALES,
            json=_cuerpo_inicial(entorno_b, ubicacion_id=str(entorno_a.deposito_id)),
            headers=_con_op(headers_b),
        )
        producto_ajeno = cliente.post(
            URL_INICIALES,
            json=_cuerpo_inicial(
                entorno_b,
                lineas=[
                    {
                        "producto_id": str(entorno_a.producto_id),
                        "cantidad_base": 5,
                        "costo_unitario": "5",
                    }
                ],
            ),
            headers=_con_op(headers_b),
        )
        inexistente = cliente.post(
            URL_INICIALES,
            json=_cuerpo_inicial(entorno_b, ubicacion_id=str(uuid4())),
            headers=_con_op(headers_b),
        )

        assert ubicacion_ajena.status_code == 404
        assert producto_ajeno.status_code == 404
        assert inexistente.status_code == 404
        assert _contar(sesion, "stock_movimiento", entorno_a.org) == 0
        assert _contar(sesion, "stock_movimiento", entorno_b.org) == 0

    def test_una_ubicacion_inactiva_es_409(self, cliente: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        inactiva = crear_ubicacion_sql(sesion, entorno.org, nombre="Inactiva", activo=False)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            URL_INICIALES,
            json=_cuerpo_inicial(entorno, ubicacion_id=str(inactiva)),
            headers=_con_op(headers),
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "UBICACION_INACTIVA"

    def test_un_producto_inactivo_es_409(self, cliente: TestClient, sesion: Session) -> None:
        """Escenario "Ubicación o producto inactivos" (CAT-05, D8), lado producto."""
        entorno = Entorno(sesion, permisos=ADMIN)
        desactivar_producto_sql(sesion, entorno.org, entorno.producto_id)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            URL_INICIALES, json=_cuerpo_inicial(entorno), headers=_con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "PRODUCTO_INACTIVO"
        assert _contar(sesion, "stock_movimiento", entorno.org) == 0

    def test_un_producto_con_operaciones_de_otro_tipo_es_409(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Producto con operaciones de otro tipo" (D4): el movimiento de
        otro tipo entra por el servicio, porque ninguna ruta lo escribe todavía."""
        entorno = Entorno(sesion, permisos=ADMIN)
        insertar_stock_movimiento_sql(
            sesion,
            organizacion_id=entorno.org,
            producto_id=entorno.producto_id,
            ubicacion_id=entorno.deposito_id,
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
            tipo="COMPRA",
            origen_tipo="COMPRA",
        )
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            URL_INICIALES, json=_cuerpo_inicial(entorno), headers=_con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "PRODUCTO_CON_OPERACIONES"


# ======================= 7.2 lecturas: ubicaciones ============================


class TestListarUbicaciones:
    def test_lista_solo_las_de_la_organizacion_con_sus_campos(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno_a = Entorno(sesion, permisos=VENDEDOR, nombre_usuario="a1")
        entorno_b = Entorno(sesion, permisos=VENDEDOR, nombre_usuario="b1")
        crear_ubicacion_sql(sesion, entorno_b.org, nombre="Solo de B")
        headers = entorno_a.confirmar_y_entrar(cliente)

        respuesta = cliente.get(URL_UBICACIONES, headers=headers)

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert [u["nombre"] for u in cuerpo["items"]] == ["Depósito central"]
        (ubicacion,) = cuerpo["items"]
        assert set(ubicacion) >= {"id", "nombre", "tipo", "requiere_toma", "activo"}
        assert cuerpo["cursor_siguiente"] is None

    def test_filtra_por_estado(self, cliente: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        crear_ubicacion_sql(sesion, entorno.org, nombre="Vieja", activo=False)
        headers = entorno.confirmar_y_entrar(cliente)

        activas = cliente.get(URL_UBICACIONES, params={"activo": "true"}, headers=headers)
        inactivas = cliente.get(URL_UBICACIONES, params={"activo": "false"}, headers=headers)
        todas = cliente.get(URL_UBICACIONES, headers=headers)

        assert [u["nombre"] for u in activas.json()["items"]] == ["Depósito central"]
        assert [u["nombre"] for u in inactivas.json()["items"]] == ["Vieja"]
        assert len(todas.json()["items"]) == 2

    def test_pagina_por_cursor(self, cliente: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        for i in range(2):
            crear_ubicacion_sql(sesion, entorno.org, nombre=f"Otra {i}")
        headers = entorno.confirmar_y_entrar(cliente)

        primera = cliente.get(URL_UBICACIONES, params={"limite": 2}, headers=headers).json()
        segunda = cliente.get(
            URL_UBICACIONES,
            params={"limite": 2, "cursor": primera["cursor_siguiente"]},
            headers=headers,
        ).json()

        assert len(primera["items"]) == 2
        assert len(segunda["items"]) == 1
        assert segunda["cursor_siguiente"] is None
        ids = [u["id"] for u in primera["items"] + segunda["items"]]
        assert len(set(ids)) == 3

    @pytest.mark.parametrize("limite", [201, 0, -1])
    def test_un_limite_fuera_de_rango_es_un_error_de_validacion(
        self, cliente: TestClient, sesion: Session, limite: int
    ) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(URL_UBICACIONES, params={"limite": limite}, headers=headers)

        assert respuesta.status_code == 422

    def test_el_limite_maximo_se_acepta_y_un_cursor_ilegible_es_422_con_codigo(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        headers = entorno.confirmar_y_entrar(cliente)

        maximo = cliente.get(URL_UBICACIONES, params={"limite": 200}, headers=headers)
        cursor = cliente.get(URL_UBICACIONES, params={"cursor": "no"}, headers=headers)

        assert maximo.status_code == 200
        assert cursor.status_code == 422
        assert cursor.json()["codigo"] == "CURSOR_INVALIDO"

    def test_sin_transferir_stock_responde_403(self, cliente: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"ADMIN_CONFIGURACION", "VER_COSTOS"}))
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(URL_UBICACIONES, headers=headers)

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


# ======================= 7.2 lecturas: saldos =================================


def _url_saldos(ubicacion_id: UUID) -> str:
    return f"{URL_UBICACIONES}/{ubicacion_id}/saldos"


class TestSaldosDeUbicacion:
    def test_con_ver_costos_muestra_cantidad_referencia_y_promedio_como_string(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        crear_presentacion_referencia_sql(sesion, entorno.org, entorno.producto_id, unidades_base=6)
        entorno.sembrar(entorno.producto_id, 60, "1000")
        entorno.sembrar(entorno.producto_id, 60, "1100")
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(_url_saldos(entorno.deposito_id), headers=headers)

        assert respuesta.status_code == 200, respuesta.text
        (linea,) = respuesta.json()["items"]
        assert linea["producto_id"] == str(entorno.producto_id)
        assert linea["producto_nombre"] == "Vino A"
        assert linea["cantidad_base"] == 120
        assert linea["unidades_referencia"] == 6
        assert linea["nombre_referencia"] == "Caja x6"
        assert linea["costo_promedio"] == "1050.000000"

    def test_sin_ver_costos_omite_el_campo_de_costo(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        # D3-A: el vendedor ve cantidades, nunca costos (`01` §19).
        entorno = Entorno(sesion, permisos=VENDEDOR)
        entorno.sembrar(entorno.producto_id, 60, "1000")
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(_url_saldos(entorno.deposito_id), headers=headers)

        assert respuesta.status_code == 200
        (linea,) = respuesta.json()["items"]
        assert linea["cantidad_base"] == 60
        assert "costo_promedio" not in linea
        assert "1000" not in respuesta.text

    def test_un_producto_sin_promedio_devuelve_null_solo_con_ver_costos(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        # Un stock inicial negativo no puede existir sin ingreso previo; se siembra
        # un movimiento por SQL sin costo para que el promedio siga nulo (D10).
        entorno = Entorno(sesion, permisos=ADMIN)
        sesion.execute(
            text(
                "INSERT INTO stock_saldo (organizacion_id, producto_id, ubicacion_id, "
                "cantidad_base, actualizado_en) VALUES (:o, :p, :u, 5, :m)"
            ),
            {"o": entorno.org, "p": entorno.producto_id, "u": entorno.deposito_id, "m": MOMENTO},
        )
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(_url_saldos(entorno.deposito_id), headers=headers)

        (linea,) = respuesta.json()["items"]
        assert "costo_promedio" in linea
        assert linea["costo_promedio"] is None

    def test_pagina_por_cursor_y_valida_el_limite(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        productos = [
            entorno.producto_id,
            entorno.otro_producto_id,
            crear_producto_sql(sesion, entorno.org),
        ]
        for producto in productos:
            entorno.sembrar(producto, 10, "5")
        headers = entorno.confirmar_y_entrar(cliente)

        primera = cliente.get(
            _url_saldos(entorno.deposito_id), params={"limite": 2}, headers=headers
        ).json()
        segunda = cliente.get(
            _url_saldos(entorno.deposito_id),
            params={"limite": 2, "cursor": primera["cursor_siguiente"]},
            headers=headers,
        ).json()
        fuera = cliente.get(
            _url_saldos(entorno.deposito_id), params={"limite": 201}, headers=headers
        )

        vistos = [li["producto_id"] for li in primera["items"] + segunda["items"]]
        assert len(primera["items"]) == 2 and len(segunda["items"]) == 1
        assert sorted(vistos) == sorted(str(p) for p in productos)
        assert segunda["cursor_siguiente"] is None
        assert fuera.status_code == 422

    def test_una_ubicacion_de_otra_organizacion_o_inexistente_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno_a = Entorno(sesion, permisos=VENDEDOR, nombre_usuario="a1")
        entorno_b = Entorno(sesion, permisos=VENDEDOR, nombre_usuario="b1")
        entorno_a.sembrar(entorno_a.producto_id, 60, "1000")
        headers_b = entorno_b.confirmar_y_entrar(cliente)

        ajena = cliente.get(_url_saldos(entorno_a.deposito_id), headers=headers_b)
        inexistente = cliente.get(_url_saldos(uuid4()), headers=headers_b)

        assert ajena.status_code == 404
        assert ajena.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert inexistente.status_code == 404
        assert "Vino A" not in ajena.text

    def test_sin_transferir_stock_responde_403(self, cliente: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"VER_COSTOS"}))
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(_url_saldos(entorno.deposito_id), headers=headers)

        assert respuesta.status_code == 403


# ======================= 7.2 lecturas: kardex =================================


def _params_kardex(entorno: Entorno, **cambios: object) -> dict[str, object]:
    params: dict[str, object] = {
        "producto_id": str(entorno.producto_id),
        "ubicacion_id": str(entorno.deposito_id),
    }
    params.update(cambios)
    return params


class TestKardex:
    def test_movimientos_con_acumulado_saldos_y_zona_horaria(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        entorno.sembrar(
            entorno.producto_id, 60, "1000", occurred_at=datetime(2026, 4, 1, 12, tzinfo=UTC)
        )
        entorno.sembrar(
            entorno.producto_id, -12, None, occurred_at=datetime(2026, 4, 2, 12, tzinfo=UTC)
        )
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(URL_KARDEX, params=_params_kardex(entorno), headers=headers)

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["saldo_anterior"] == 0
        assert cuerpo["saldo_actual"] == 48
        assert cuerpo["zona_horaria"] == "America/Argentina/Mendoza"
        assert cuerpo["producto_nombre"] == "Vino A"
        assert cuerpo["producto_codigo"].startswith("COD-")
        assert cuerpo["unidades_referencia"] is None
        assert cuerpo["nombre_referencia"] is None
        assert [(m["cantidad_base"], m["saldo_acumulado"]) for m in cuerpo["items"]] == [
            (60, 60),
            (-12, 48),
        ]
        assert cuerpo["items"][0]["tipo"] == "STOCK_INICIAL"
        assert cuerpo["items"][0]["costo_unitario"] == "1000.000000"
        assert cuerpo["items"][1]["costo_unitario"] == "1000.000000"  # egreso al promedio
        assert cuerpo["cursor_siguiente"] is None

    def test_sin_ver_costos_omite_el_costo_de_cada_movimiento(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        entorno.sembrar(entorno.producto_id, 60, "1000")
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(URL_KARDEX, params=_params_kardex(entorno), headers=headers)

        assert respuesta.status_code == 200
        (movimiento,) = respuesta.json()["items"]
        assert movimiento["saldo_acumulado"] == 60
        assert "costo_unitario" not in movimiento
        assert "1000" not in respuesta.text

    def test_el_periodo_devuelve_el_saldo_anterior_y_continua_el_acumulado(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        for dia, cantidad in ((1, 60), (10, 10), (20, 5)):
            entorno.sembrar(
                entorno.producto_id,
                cantidad,
                "1000",
                occurred_at=datetime(2026, 4, dia, 15, tzinfo=UTC),
            )
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(
            URL_KARDEX,
            params=_params_kardex(entorno, desde="2026-04-05", hasta="2026-04-10"),
            headers=headers,
        )

        cuerpo = respuesta.json()
        assert cuerpo["saldo_anterior"] == 60
        assert cuerpo["saldo_actual"] == 75
        assert [(m["cantidad_base"], m["saldo_acumulado"]) for m in cuerpo["items"]] == [(10, 70)]

    def test_la_segunda_pagina_continua_el_acumulado_sin_repetir(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        for dia in (1, 2, 3):
            entorno.sembrar(
                entorno.producto_id,
                10,
                "1000",
                occurred_at=datetime(2026, 4, dia, 15, tzinfo=UTC),
            )
        headers = entorno.confirmar_y_entrar(cliente)

        primera = cliente.get(
            URL_KARDEX, params=_params_kardex(entorno, limite=2), headers=headers
        ).json()
        segunda = cliente.get(
            URL_KARDEX,
            params=_params_kardex(entorno, limite=2, cursor=primera["cursor_siguiente"]),
            headers=headers,
        ).json()

        assert [m["saldo_acumulado"] for m in primera["items"]] == [10, 20]
        assert [m["saldo_acumulado"] for m in segunda["items"]] == [30]
        assert segunda["cursor_siguiente"] is None

    @pytest.mark.parametrize("limite", [201, 0, -1])
    def test_un_limite_fuera_de_rango_es_un_error_de_validacion(
        self, cliente: TestClient, sesion: Session, limite: int
    ) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(
            URL_KARDEX, params=_params_kardex(entorno, limite=limite), headers=headers
        )

        assert respuesta.status_code == 422

    def test_el_limite_maximo_se_acepta(self, cliente: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(
            URL_KARDEX, params=_params_kardex(entorno, limite=200), headers=headers
        )

        assert respuesta.status_code == 200

    def test_un_cursor_ilegible_y_un_rango_invertido_responden_422_con_codigo(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        headers = entorno.confirmar_y_entrar(cliente)

        cursor = cliente.get(
            URL_KARDEX, params=_params_kardex(entorno, cursor="no"), headers=headers
        )
        rango = cliente.get(
            URL_KARDEX,
            params=_params_kardex(entorno, desde="2026-04-02", hasta="2026-04-01"),
            headers=headers,
        )

        assert (cursor.status_code, cursor.json()["codigo"]) == (422, "CURSOR_INVALIDO")
        assert (rango.status_code, rango.json()["codigo"]) == (422, "RANGO_DE_FECHAS_INVALIDO")

    @pytest.mark.parametrize("faltante", ["producto_id", "ubicacion_id"])
    def test_producto_y_ubicacion_son_obligatorios(
        self, cliente: TestClient, sesion: Session, faltante: str
    ) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        headers = entorno.confirmar_y_entrar(cliente)
        params = _params_kardex(entorno)
        del params[faltante]

        respuesta = cliente.get(URL_KARDEX, params=params, headers=headers)

        assert respuesta.status_code == 422

    def test_un_producto_o_una_ubicacion_de_otra_organizacion_o_inexistente_es_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno_a = Entorno(sesion, permisos=VENDEDOR, nombre_usuario="a1")
        entorno_b = Entorno(sesion, permisos=VENDEDOR, nombre_usuario="b1")
        entorno_a.sembrar(entorno_a.producto_id, 60, "1000")
        headers_b = entorno_b.confirmar_y_entrar(cliente)

        producto_ajeno = cliente.get(
            URL_KARDEX,
            params=_params_kardex(entorno_b, producto_id=str(entorno_a.producto_id)),
            headers=headers_b,
        )
        ubicacion_ajena = cliente.get(
            URL_KARDEX,
            params=_params_kardex(entorno_b, ubicacion_id=str(entorno_a.deposito_id)),
            headers=headers_b,
        )
        ambos_ajenos = cliente.get(
            URL_KARDEX,
            params={
                "producto_id": str(entorno_a.producto_id),
                "ubicacion_id": str(entorno_a.deposito_id),
            },
            headers=headers_b,
        )
        inexistente = cliente.get(
            URL_KARDEX,
            params=_params_kardex(entorno_b, producto_id=str(uuid4())),
            headers=headers_b,
        )

        for respuesta in (producto_ajeno, ubicacion_ajena, ambos_ajenos, inexistente):
            assert respuesta.status_code == 404
            assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert "items" not in ambos_ajenos.json()

    def test_sin_transferir_stock_responde_403(self, cliente: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"VER_COSTOS"}))
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(URL_KARDEX, params=_params_kardex(entorno), headers=headers)

        assert respuesta.status_code == 403


# ======================= 7.2 lectura: costo promedio (catalogo) ================


def _url_costo(producto_id: UUID) -> str:
    return f"/api/v1/catalogo/productos/{producto_id}/costo"


class TestCostoPromedioDeProducto:
    def test_devuelve_el_promedio_y_el_stock_total_como_string_y_entero(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """CST-11: 60 a 1000 y 60 a 1100 dan 1050; 30 a 1200 más dan 1080 (todas las
        ubicaciones suman en un único promedio por organización)."""
        entorno = Entorno(sesion, permisos=ADMIN)
        entorno.sembrar(entorno.producto_id, 60, "1000")
        entorno.sembrar(entorno.producto_id, 60, "1100")
        entorno.sembrar(
            entorno.producto_id,
            30,
            "1200",
            ubicacion_id=crear_ubicacion_sql(
                sesion, entorno.org, nombre="Camión 1", tipo="VEHICULO", requiere_toma=True
            ),
        )
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(_url_costo(entorno.producto_id), headers=headers)

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json() == {
            "producto_id": str(entorno.producto_id),
            "costo_promedio": "1080.000000",
            "stock_total": 150,
        }

    def test_un_producto_sin_ingresos_responde_200_con_promedio_nulo(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """D10: "sin costo" no es lo mismo que "costo cero"."""
        entorno = Entorno(sesion, permisos=ADMIN)
        entorno.sembrar(entorno.producto_id, 60, "1000")
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(_url_costo(entorno.otro_producto_id), headers=headers)

        assert respuesta.status_code == 200
        assert respuesta.json() == {
            "producto_id": str(entorno.otro_producto_id),
            "costo_promedio": None,
            "stock_total": 0,
        }

    def test_un_vendedor_sin_ver_costos_recibe_403_aunque_vea_el_stock(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=VENDEDOR)
        entorno.sembrar(entorno.producto_id, 60, "1000")
        headers = entorno.confirmar_y_entrar(cliente)

        costo = cliente.get(_url_costo(entorno.producto_id), headers=headers)
        saldos = cliente.get(_url_saldos(entorno.deposito_id), headers=headers)

        assert costo.status_code == 403
        assert costo.json()["codigo"] == "PERMISO_REQUERIDO"
        assert "1000" not in costo.text
        assert saldos.status_code == 200

    def test_un_producto_de_otra_organizacion_o_inexistente_responde_404_sin_datos(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno_a = Entorno(sesion, permisos=ADMIN, nombre_usuario="a1")
        entorno_b = Entorno(sesion, permisos=ADMIN, nombre_usuario="b1")
        entorno_a.sembrar(entorno_a.producto_id, 60, "1000")
        headers_b = entorno_b.confirmar_y_entrar(cliente)

        ajeno = cliente.get(_url_costo(entorno_a.producto_id), headers=headers_b)
        inexistente = cliente.get(_url_costo(uuid4()), headers=headers_b)

        for respuesta in (ajeno, inexistente):
            assert respuesta.status_code == 404
            assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
            assert "1000" not in respuesta.text

    def test_un_id_que_no_es_uuid_es_422(self, cliente: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion, permisos=ADMIN)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get("/api/v1/catalogo/productos/no-es-uuid/costo", headers=headers)

        assert respuesta.status_code == 422
