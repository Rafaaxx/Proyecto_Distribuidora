"""Change 08, grupo 6, tareas 6.1 y 6.2: endpoints HTTP de `cuentas_corrientes`
(`POST /cuentas-corrientes/saldos-iniciales`, `GET /clientes/{id}/cuenta-corriente`
y `GET /proveedores/{id}/cuenta-corriente`).

Mismo arnés HTTP que `test_proveedores_api.py`: PostgreSQL real, motor propio de la
aplicación y `login` real (nunca un access token fabricado). Los movimientos con
fechas concretas se siembran con `service.registrar_movimiento` y un `commit`, porque
la ruta de escritura solo registra con el `occurred_at` del reloj.

Reglas citadas: CC-01, CC-04, CC-07, INV-03, INV-06, INV-21, SEG-06, SEG-07, TR-04,
TR-07 y `design.md` D1, D2, D9.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_proveedor,
)
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.cuentas_corrientes import service
from app.modules.identidad import repository as identidad_repository

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-cuentas-corrientes-api"
URL_SALDOS = "/api/v1/cuentas-corrientes/saldos-iniciales"


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
    """Una organización con su usuario, su dispositivo de siembra, un cliente y un
    proveedor."""

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
        self.cliente_id = crear_cliente(sesion, self.org)
        self.proveedor_id = crear_proveedor(sesion, self.org)

    def mover(
        self,
        *,
        cuenta_tipo: str = "CLIENTE",
        entidad_id: UUID | None = None,
        tipo: str = "SALDO_INICIAL",
        sentido: str = "AUMENTA",
        importe: str = "150000.00",
        occurred_at: datetime,
    ) -> None:
        if entidad_id is None:
            entidad_id = self.cliente_id if cuenta_tipo == "CLIENTE" else self.proveedor_id
        operation_id = uuid4()
        service.registrar_movimiento(
            self.org,
            self.sesion,
            FixedClock(occurred_at),
            cuenta_tipo=cuenta_tipo,
            entidad_id=entidad_id,
            tipo=tipo,
            sentido=sentido,
            importe=importe,
            origen_tipo=tipo,
            origen_id=operation_id,
            occurred_at=occurred_at,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=operation_id,
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


def _cuerpo_saldo(
    entidad_id: UUID, *, cuenta_tipo: str = "CLIENTE", **cambios: object
) -> dict[str, object]:
    cuerpo: dict[str, object] = {
        "cuenta_tipo": cuenta_tipo,
        "entidad_id": str(entidad_id),
        "importe": "150000.00",
        "sentido": "AUMENTA",
    }
    cuerpo.update(cambios)
    return cuerpo


def _movimientos_de(sesion: Session, organizacion_id: UUID) -> int:
    sesion.rollback()
    return int(
        sesion.scalar(
            text("select count(*) from cuenta_movimiento where organizacion_id = :o"),
            {"o": organizacion_id},
        )
        or 0
    )


class TestSaldoInicialRegistrar:
    def test_sin_operation_id_se_rechaza_con_400(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"IMPORTAR_DATOS"}))
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            URL_SALDOS, json=_cuerpo_saldo(entorno.cliente_id), headers=headers
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
        assert _movimientos_de(sesion, entorno.org) == 0

    def test_sin_importar_datos_responde_403_sin_efectos_ni_reserva(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        # D1: `GESTIONAR_CLIENTES` (Administración) no alcanza para escribir.
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
        headers = entorno.confirmar_y_entrar(cliente)
        operation_id = uuid4()

        respuesta = cliente.post(
            URL_SALDOS,
            json=_cuerpo_saldo(entorno.cliente_id),
            headers={**headers, "Operation-Id": str(operation_id)},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert _movimientos_de(sesion, entorno.org) == 0
        reservas = sesion.scalar(
            text("select count(*) from comando where operation_id = :oid"),
            {"oid": str(operation_id)},
        )
        assert reservas == 0

    def test_registra_el_saldo_inicial_de_un_cliente_y_de_un_proveedor(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"IMPORTAR_DATOS"}))
        headers = entorno.confirmar_y_entrar(cliente)

        de_cliente = cliente.post(
            URL_SALDOS,
            json=_cuerpo_saldo(entorno.cliente_id),
            headers={**headers, "Operation-Id": str(uuid4())},
        )
        de_proveedor = cliente.post(
            URL_SALDOS,
            json=_cuerpo_saldo(
                entorno.proveedor_id,
                cuenta_tipo="PROVEEDOR",
                importe="8500.50",
                sentido="REDUCE",
            ),
            headers={**headers, "Operation-Id": str(uuid4())},
        )

        assert de_cliente.status_code == 201, de_cliente.text
        assert de_cliente.json()["saldo"] == "150000.00"
        UUID(de_cliente.json()["movimiento_id"])
        assert de_proveedor.status_code == 201, de_proveedor.text
        assert de_proveedor.json()["saldo"] == "-8500.50"

    def test_reenviar_el_mismo_operation_id_no_duplica_el_movimiento(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"IMPORTAR_DATOS"}))
        headers = entorno.confirmar_y_entrar(cliente)
        headers = {**headers, "Operation-Id": str(uuid4())}
        cuerpo = _cuerpo_saldo(entorno.cliente_id)

        primera = cliente.post(URL_SALDOS, json=cuerpo, headers=headers)
        segunda = cliente.post(URL_SALDOS, json=cuerpo, headers=headers)

        assert primera.status_code == segunda.status_code == 201
        assert primera.json() == segunda.json()
        assert _movimientos_de(sesion, entorno.org) == 1

    def test_mismo_operation_id_con_otro_contenido_es_comando_inconsistente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"IMPORTAR_DATOS"}))
        headers = entorno.confirmar_y_entrar(cliente)
        headers = {**headers, "Operation-Id": str(uuid4())}

        cliente.post(URL_SALDOS, json=_cuerpo_saldo(entorno.cliente_id), headers=headers)
        segunda = cliente.post(
            URL_SALDOS, json=_cuerpo_saldo(entorno.cliente_id, importe="1.00"), headers=headers
        )

        assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"
        assert segunda.status_code == 409
        assert _movimientos_de(sesion, entorno.org) == 1

    def test_una_entidad_de_otra_organizacion_o_inexistente_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno_a = Entorno(sesion, permisos=frozenset({"IMPORTAR_DATOS"}), nombre_usuario="a1")
        entorno_b = Entorno(sesion, permisos=frozenset({"IMPORTAR_DATOS"}), nombre_usuario="b1")
        headers_b = entorno_b.confirmar_y_entrar(cliente)

        ajeno = cliente.post(
            URL_SALDOS,
            json=_cuerpo_saldo(entorno_a.cliente_id),
            headers={**headers_b, "Operation-Id": str(uuid4())},
        )
        inexistente = cliente.post(
            URL_SALDOS,
            json=_cuerpo_saldo(uuid4(), cuenta_tipo="PROVEEDOR"),
            headers={**headers_b, "Operation-Id": str(uuid4())},
        )

        assert ajeno.status_code == 404
        assert ajeno.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert inexistente.status_code == 404
        assert _movimientos_de(sesion, entorno_a.org) == 0

    @pytest.mark.parametrize("importe", [150000.5, 150000, "0.00", "1.005"])
    def test_un_importe_invalido_se_rechaza_con_422(
        self, cliente: TestClient, sesion: Session, importe: object
    ) -> None:
        # INV-03: un número JSON en vez de un string no se acepta ni se redondea.
        entorno = Entorno(sesion, permisos=frozenset({"IMPORTAR_DATOS"}))
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            URL_SALDOS,
            json=_cuerpo_saldo(entorno.cliente_id, importe=importe),
            headers={**headers, "Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "IMPORTE_INVALIDO"
        assert _movimientos_de(sesion, entorno.org) == 0

    def test_un_campo_extra_o_un_tipo_de_cuenta_desconocido_se_rechaza_con_422(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"IMPORTAR_DATOS"}))
        headers = {**entorno.confirmar_y_entrar(cliente), "Operation-Id": str(uuid4())}

        con_extra = cliente.post(
            URL_SALDOS,
            json=_cuerpo_saldo(entorno.cliente_id, organizacion_id=str(uuid4())),
            headers=headers,
        )
        tipo_raro = cliente.post(
            URL_SALDOS,
            json=_cuerpo_saldo(entorno.cliente_id, cuenta_tipo="EMPLEADO"),
            headers=headers,
        )

        assert con_extra.status_code == 422
        assert tipo_raro.status_code == 422
        assert _movimientos_de(sesion, entorno.org) == 0

    def test_un_sentido_fuera_del_catalogo_se_rechaza_con_422_sin_efectos(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"IMPORTAR_DATOS"}))
        headers = {**entorno.confirmar_y_entrar(cliente), "Operation-Id": str(uuid4())}

        respuesta = cliente.post(
            URL_SALDOS, json=_cuerpo_saldo(entorno.cliente_id, sentido="SUMA"), headers=headers
        )

        assert respuesta.status_code == 422
        assert _movimientos_de(sesion, entorno.org) == 0


def _url_cliente(cliente_id: UUID) -> str:
    return f"/api/v1/clientes/{cliente_id}/cuenta-corriente"


def _url_proveedor(proveedor_id: UUID) -> str:
    return f"/api/v1/proveedores/{proveedor_id}/cuenta-corriente"


class TestEstadoDeCuentaDeUnCliente:
    def test_dos_movimientos_con_saldo_acumulado_y_saldo_actual_como_string(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
        entorno.mover(occurred_at=datetime(2026, 3, 10, 15, 0, tzinfo=UTC))
        entorno.mover(
            tipo="COBRANZA",
            sentido="REDUCE",
            importe="20000.00",
            occurred_at=datetime(2026, 4, 10, 15, 0, tzinfo=UTC),
        )
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(_url_cliente(entorno.cliente_id), headers=headers)

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["saldo_anterior"] == "0.00"
        assert cuerpo["saldo_actual"] == "130000.00"
        # TR-04: la pantalla muestra las fechas en la zona de la organización.
        assert cuerpo["zona_horaria"] == "America/Argentina/Mendoza"
        assert cuerpo["cursor_siguiente"] is None
        assert [
            (m["tipo"], m["sentido"], m["importe"], m["saldo_acumulado"]) for m in cuerpo["items"]
        ] == [
            ("SALDO_INICIAL", "AUMENTA", "150000.00", "150000.00"),
            ("COBRANZA", "REDUCE", "20000.00", "130000.00"),
        ]
        assert set(cuerpo["items"][0]) == {
            "id",
            "tipo",
            "sentido",
            "importe",
            "origen_tipo",
            "origen_id",
            "occurred_at",
            "registered_at",
            "usuario_id",
            "operation_id",
            "saldo_acumulado",
        }

    def test_cuenta_sin_movimientos_tiene_lista_vacia_y_saldo_cero(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(_url_cliente(entorno.cliente_id), headers=headers)

        assert respuesta.status_code == 200
        assert respuesta.json() == {
            "saldo_anterior": "0.00",
            "saldo_actual": "0.00",
            "zona_horaria": "America/Argentina/Mendoza",
            "items": [],
            "cursor_siguiente": None,
        }

    def test_el_periodo_devuelve_el_saldo_anterior_y_continua_el_acumulado(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
        entorno.mover(occurred_at=datetime(2026, 3, 10, 15, 0, tzinfo=UTC))
        entorno.mover(
            tipo="COBRANZA",
            sentido="REDUCE",
            importe="20000.00",
            occurred_at=datetime(2026, 4, 10, 15, 0, tzinfo=UTC),
        )
        headers = entorno.confirmar_y_entrar(cliente)

        desde_abril = cliente.get(
            _url_cliente(entorno.cliente_id), params={"desde": "2026-04-01"}, headers=headers
        ).json()
        hasta_marzo = cliente.get(
            _url_cliente(entorno.cliente_id), params={"hasta": "2026-03-31"}, headers=headers
        ).json()

        assert desde_abril["saldo_anterior"] == "150000.00"
        assert [m["saldo_acumulado"] for m in desde_abril["items"]] == ["130000.00"]
        assert hasta_marzo["saldo_anterior"] == "0.00"
        assert [m["saldo_acumulado"] for m in hasta_marzo["items"]] == ["150000.00"]

    def test_la_segunda_pagina_continua_el_acumulado_sin_repetir_ni_omitir(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
        for dia in range(1, 6):
            entorno.mover(importe="100.00", occurred_at=datetime(2026, 3, dia, 15, 0, tzinfo=UTC))
        headers = entorno.confirmar_y_entrar(cliente)

        pagina_1 = cliente.get(
            _url_cliente(entorno.cliente_id), params={"limite": 2}, headers=headers
        ).json()
        pagina_2 = cliente.get(
            _url_cliente(entorno.cliente_id),
            params={"limite": 2, "cursor": pagina_1["cursor_siguiente"]},
            headers=headers,
        ).json()
        pagina_3 = cliente.get(
            _url_cliente(entorno.cliente_id),
            params={"limite": 2, "cursor": pagina_2["cursor_siguiente"]},
            headers=headers,
        ).json()

        paginas = (pagina_1, pagina_2, pagina_3)
        acumulados = [m["saldo_acumulado"] for p in paginas for m in p["items"]]
        assert acumulados == ["100.00", "200.00", "300.00", "400.00", "500.00"]
        ids = [m["id"] for p in paginas for m in p["items"]]
        assert len(set(ids)) == 5
        assert pagina_3["cursor_siguiente"] is None

    @pytest.mark.parametrize("limite", [201, 0, -1])
    def test_un_limite_fuera_de_rango_es_un_error_de_validacion(
        self, cliente: TestClient, sesion: Session, limite: int
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(
            _url_cliente(entorno.cliente_id), params={"limite": limite}, headers=headers
        )

        assert respuesta.status_code == 422

    def test_el_limite_maximo_se_acepta(self, cliente: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(
            _url_cliente(entorno.cliente_id), params={"limite": 200}, headers=headers
        )

        assert respuesta.status_code == 200

    def test_un_cursor_ilegible_y_un_rango_invertido_responden_422_con_codigo(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
        headers = entorno.confirmar_y_entrar(cliente)

        cursor = cliente.get(
            _url_cliente(entorno.cliente_id), params={"cursor": "no-es-un-cursor"}, headers=headers
        )
        rango = cliente.get(
            _url_cliente(entorno.cliente_id),
            params={"desde": "2026-04-02", "hasta": "2026-04-01"},
            headers=headers,
        )

        assert cursor.status_code == 422
        assert cursor.json()["codigo"] == "CURSOR_INVALIDO"
        assert rango.status_code == 422
        assert rango.json()["codigo"] == "RANGO_DE_FECHAS_INVALIDO"

    def test_sin_gestionar_clientes_responde_403(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        # D2: `GESTIONAR_PROVEEDORES` no habilita la cuenta de un cliente.
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_PROVEEDORES", "IMPORTAR_DATOS"}))
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(_url_cliente(entorno.cliente_id), headers=headers)

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"

    def test_un_cliente_de_otra_organizacion_o_inexistente_responde_404_sin_datos(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno_a = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}), nombre_usuario="a1")
        entorno_a.mover(occurred_at=datetime(2026, 3, 10, 15, 0, tzinfo=UTC))
        entorno_b = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}), nombre_usuario="b1")
        headers_b = entorno_b.confirmar_y_entrar(cliente)

        ajeno = cliente.get(_url_cliente(entorno_a.cliente_id), headers=headers_b)
        inexistente = cliente.get(_url_cliente(uuid4()), headers=headers_b)

        assert ajeno.status_code == 404
        assert ajeno.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert "150000" not in ajeno.text
        assert inexistente.status_code == 404


class TestEstadoDeCuentaDeUnProveedor:
    def test_movimientos_con_saldo_acumulado_de_proveedor(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_PROVEEDORES"}))
        entorno.mover(
            cuenta_tipo="PROVEEDOR",
            tipo="COMPRA",
            importe="9000.00",
            occurred_at=datetime(2026, 3, 10, 15, 0, tzinfo=UTC),
        )
        entorno.mover(
            cuenta_tipo="PROVEEDOR",
            tipo="PAGO",
            sentido="REDUCE",
            importe="12000.00",
            occurred_at=datetime(2026, 3, 11, 15, 0, tzinfo=UTC),
        )
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(_url_proveedor(entorno.proveedor_id), headers=headers)

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["saldo_actual"] == "-3000.00"
        assert [m["saldo_acumulado"] for m in cuerpo["items"]] == ["9000.00", "-3000.00"]

    def test_proveedor_sin_movimientos_y_periodo_con_saldo_anterior(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_PROVEEDORES"}))
        vacio = entorno.proveedor_id
        con_movimientos = crear_proveedor(sesion, entorno.org, nombre="Bodega Norte")
        entorno.mover(
            cuenta_tipo="PROVEEDOR",
            entidad_id=con_movimientos,
            tipo="COMPRA",
            importe="9000.00",
            occurred_at=datetime(2026, 3, 10, 15, 0, tzinfo=UTC),
        )
        headers = entorno.confirmar_y_entrar(cliente)

        sin = cliente.get(_url_proveedor(vacio), headers=headers).json()
        con = cliente.get(
            _url_proveedor(con_movimientos), params={"desde": "2026-04-01"}, headers=headers
        ).json()

        assert sin["items"] == [] and sin["saldo_actual"] == "0.00"
        assert con["saldo_anterior"] == "9000.00"
        assert con["items"] == []

    def test_sin_gestionar_proveedores_responde_403(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(_url_proveedor(entorno.proveedor_id), headers=headers)

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"

    def test_un_proveedor_de_otra_organizacion_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno_a = Entorno(
            sesion, permisos=frozenset({"GESTIONAR_PROVEEDORES"}), nombre_usuario="a1"
        )
        entorno_b = Entorno(
            sesion, permisos=frozenset({"GESTIONAR_PROVEEDORES"}), nombre_usuario="b1"
        )
        headers_b = entorno_b.confirmar_y_entrar(cliente)

        ajeno = cliente.get(_url_proveedor(entorno_a.proveedor_id), headers=headers_b)

        assert ajeno.status_code == 404
        assert ajeno.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
