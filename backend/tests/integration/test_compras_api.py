"""Change 11, tarea 5.3: `POST /api/v1/compras` (`COMPRA_CONFIRMAR`) por HTTP.

Mismo arnés que `test_stock_api.py`: PostgreSQL real, motor propio de la aplicación y
`login` real (nunca un access token fabricado). Cubre el contrato HTTP: `Operation-Id`
obligatorio, Problem Details con la línea en los errores de línea, importes como string,
permiso, idempotencia y aislamiento (INV-21).

Reglas citadas: CMP-01, CMP-02, CMP-03, INV-03, INV-04, INV-06, INV-07, INV-21, SEG-06,
SEG-07, TR-07 y `design.md` D1, D5, D12, D14.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_proveedor
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_presentacion_sql, crear_producto_sql, crear_ubicacion_sql

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository as identidad_repository

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-compras-api"
URL_COMPRAS = "/api/v1/compras"

COMPRADOR = frozenset({"REGISTRAR_COMPRA"})
COMPRADOR_Y_ANULADOR = frozenset({"REGISTRAR_COMPRA", "ANULAR_COMPRA"})


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
    """Una organización con su usuario, un proveedor, `Vino A` (Caja x6), `Cerveza B`
    (Botella) y un depósito."""

    def __init__(
        self, sesion: Session, *, permisos: frozenset[str] = COMPRADOR, usuario: str = "comprador1"
    ) -> None:
        self.sesion = sesion
        organizacion = crear_organizacion(sesion)
        self.org = organizacion.id
        self.slug = organizacion.slug
        self.usuario = usuario
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
        identidad_repository.crear_usuario(
            self.org,
            sesion,
            usuario_id=nuevo_id(),
            usuario=usuario,
            nombre="Persona de prueba",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )
        self.proveedor_id = crear_proveedor(sesion, self.org, nombre="Bodega Sur")
        self.vino_id = crear_producto_sql(
            sesion, self.org, nombre="Vino A", proveedor_id=self.proveedor_id
        )
        self.caja_x6_id = crear_presentacion_sql(
            sesion, self.org, self.vino_id, nombre="Caja x6", unidades_base=6, es_referencia=True
        )
        self.cerveza_id = crear_producto_sql(
            sesion, self.org, nombre="Cerveza B", proveedor_id=self.proveedor_id
        )
        self.botella_id = crear_presentacion_sql(
            sesion, self.org, self.cerveza_id, nombre="Botella", unidades_base=1, es_referencia=True
        )
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")

    def crear_motivo(
        self, ambito: str = "ANULACION_COMPRA", nombre: str = "Error de carga"
    ) -> UUID:
        motivo_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, :ambito, :nombre, true, :m, :m)"
            ),
            {"id": motivo_id, "org": self.org, "ambito": ambito, "nombre": nombre, "m": MOMENTO},
        )
        return motivo_id

    def crear_medio(self, nombre: str = "Efectivo") -> UUID:
        medio_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, "
                "activo, creado_en, actualizado_en) "
                "VALUES (:id, :org, :nombre, false, true, :m, :m)"
            ),
            {"id": medio_id, "org": self.org, "nombre": nombre, "m": MOMENTO},
        )
        return medio_id

    def agregar_proveedor(self, nombre: str) -> tuple[UUID, UUID, UUID]:
        """Otro proveedor de la organización con un producto (Caja x6) propio."""
        proveedor_id = crear_proveedor(self.sesion, self.org, nombre=nombre)
        producto_id = crear_producto_sql(
            self.sesion, self.org, nombre=f"Producto de {nombre}", proveedor_id=proveedor_id
        )
        presentacion_id = crear_presentacion_sql(
            self.sesion,
            self.org,
            producto_id,
            nombre="Caja x6",
            unidades_base=6,
            es_referencia=True,
        )
        return proveedor_id, producto_id, presentacion_id

    def entrar(self, cliente_http: TestClient) -> dict[str, str]:
        self.sesion.commit()
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": self.usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 200
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}

    def cuerpo(self, **cambios: object) -> dict[str, Any]:
        base: dict[str, Any] = {
            "proveedor_id": str(self.proveedor_id),
            "fecha": datetime.now(ZoneInfo("America/Argentina/Mendoza")).date().isoformat(),
            "ubicacion_id": str(self.deposito_id),
            "condicion": "CREDITO",
            "total_factura": "152460.00",
            "lineas": [
                {
                    "producto_id": str(self.vino_id),
                    "presentacion_id": str(self.caja_x6_id),
                    "cantidad": "10",
                    "valor": "6000.00",
                    "incluye_iva": False,
                },
                {
                    "producto_id": str(self.cerveza_id),
                    "presentacion_id": str(self.botella_id),
                    "cantidad": "60",
                    "valor": "1100.00",
                    "incluye_iva": False,
                },
            ],
        }
        base.update(cambios)
        return base


def _con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


def _contar(sesion: Session, tabla: str, organizacion_id: UUID) -> int:
    return int(
        sesion.execute(
            text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"),
            {"o": organizacion_id},
        ).scalar_one()
    )


def test_confirmar_una_compra_a_credito_responde_201_con_importes_como_string(
    cliente: TestClient, sesion: Session
) -> None:
    """CMP-01 a CMP-03, `00` §9 criterio 2, INV-03: los importes viajan como string."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(URL_COMPRAS, json=entorno.cuerpo(), headers=_con_op(headers))

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["total_neto"] == "126000.00"
    assert cuerpo["total_factura"] == "152460.00"
    assert cuerpo["pago_id"] is None
    assert cuerpo["diferencias_de_costo"][0]["costo_base_compra"] == "1000.000000"
    assert cuerpo["diferencias_de_costo"][0]["costo_base_vigente"] is None
    assert _contar(sesion, "compra", entorno.org) == 1
    assert _contar(sesion, "compra_linea", entorno.org) == 2
    assert _contar(sesion, "stock_movimiento", entorno.org) == 2
    saldo = sesion.execute(
        text("SELECT saldo FROM saldo_cuenta WHERE organizacion_id = :o"), {"o": entorno.org}
    ).scalar_one()
    assert str(saldo) == "152460.00"


def test_sin_operation_id_se_rechaza_con_400_y_sin_efectos(
    cliente: TestClient, sesion: Session
) -> None:
    """TR-07, SYN-01."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(URL_COMPRAS, json=entorno.cuerpo(), headers=headers)

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
    assert _contar(sesion, "compra", entorno.org) == 0


def test_sin_sesion_responde_401(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion)
    entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_COMPRAS, json=entorno.cuerpo(), headers={"Operation-Id": str(uuid4())}
    )

    assert respuesta.status_code == 401


def test_sin_registrar_compra_responde_403_sin_efectos_ni_reserva(
    cliente: TestClient, sesion: Session
) -> None:
    """`01` §19, D14."""
    entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_PROVEEDORES"}))
    headers = entorno.entrar(cliente)
    operation_id = uuid4()

    respuesta = cliente.post(
        URL_COMPRAS, json=entorno.cuerpo(), headers=_con_op(headers, operation_id)
    )

    assert respuesta.status_code == 403
    assert _contar(sesion, "compra", entorno.org) == 0
    assert (
        sesion.execute(
            text("SELECT count(*) FROM comando WHERE operation_id = :id"), {"id": operation_id}
        ).scalar_one()
        == 0
    )


def test_un_error_de_linea_indica_la_linea_en_el_problem_details(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-04, `02` §11: la línea 1 (0-based) trae 2,3 cajas x6 = 13,8 unidades."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    cuerpo = entorno.cuerpo()
    cuerpo["lineas"][1] = {**cuerpo["lineas"][0], "cantidad": "2.3"}

    respuesta = cliente.post(URL_COMPRAS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 422
    problema = respuesta.json()
    assert problema["codigo"] == "CANTIDAD_INVALIDA"
    assert problema["linea"] == 1
    assert _contar(sesion, "compra", entorno.org) == 0


def test_inv07_una_compra_sin_lineas_responde_422_con_su_codigo(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(URL_COMPRAS, json=entorno.cuerpo(lineas=[]), headers=_con_op(headers))

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "COMPRA_SIN_LINEAS"


@pytest.mark.parametrize("campo", ["total_factura", "cantidad", "valor"])
def test_inv03_un_numero_json_en_lugar_de_un_string_se_rechaza(
    cliente: TestClient, sesion: Session, campo: str
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    cuerpo = entorno.cuerpo()
    if campo == "total_factura":
        cuerpo["total_factura"] = 152460.0
    else:
        cuerpo["lineas"][0][campo] = 10.5

    respuesta = cliente.post(URL_COMPRAS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 422
    assert _contar(sesion, "compra", entorno.org) == 0


def test_el_cuerpo_no_acepta_organizacion_id(cliente: TestClient, sesion: Session) -> None:
    """INV-21, TR-08: la organización sale del token. Un campo extra se ignora en el
    cuerpo HTTP y NUNCA llega al contenido del comando."""
    entorno = Entorno(sesion)
    otra = crear_organizacion(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_COMPRAS,
        json=entorno.cuerpo(organizacion_id=str(otra.id)),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 201
    assert _contar(sesion, "compra", entorno.org) == 1
    assert _contar(sesion, "compra", otra.id) == 0


def test_inv06_el_reenvio_con_el_mismo_operation_id_devuelve_lo_mismo_y_no_duplica(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    operation_id = uuid4()

    primera = cliente.post(
        URL_COMPRAS, json=entorno.cuerpo(), headers=_con_op(headers, operation_id)
    )
    segunda = cliente.post(
        URL_COMPRAS, json=entorno.cuerpo(), headers=_con_op(headers, operation_id)
    )

    assert primera.status_code == segunda.status_code == 201
    assert primera.json() == segunda.json()
    assert _contar(sesion, "compra", entorno.org) == 1
    assert _contar(sesion, "stock_movimiento", entorno.org) == 2


def test_inv06_el_mismo_operation_id_con_otro_contenido_responde_409(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    operation_id = uuid4()
    cliente.post(URL_COMPRAS, json=entorno.cuerpo(), headers=_con_op(headers, operation_id))

    respuesta = cliente.post(
        URL_COMPRAS,
        json=entorno.cuerpo(total_factura="153720.00"),
        headers=_con_op(headers, operation_id),
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "COMANDO_INCONSISTENTE"


def test_inv21_un_proveedor_de_otra_organizacion_responde_404_sin_efectos(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21, SEG-07: el usuario de B compra con el proveedor, la ubicación y los
    productos de A."""
    entorno_a = Entorno(sesion, usuario="comprador_a")
    entorno_b = Entorno(sesion, usuario="comprador_b")
    headers_b = entorno_b.entrar(cliente)

    respuesta = cliente.post(
        URL_COMPRAS,
        json=entorno_b.cuerpo(proveedor_id=str(entorno_a.proveedor_id)),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 404
    assert _contar(sesion, "compra", entorno_a.org) == 0
    assert _contar(sesion, "compra", entorno_b.org) == 0


def test_inv21_una_ubicacion_ajena_responde_404(cliente: TestClient, sesion: Session) -> None:
    entorno_a = Entorno(sesion, usuario="comprador_a")
    entorno_b = Entorno(sesion, usuario="comprador_b")
    headers_b = entorno_b.entrar(cliente)

    respuesta = cliente.post(
        URL_COMPRAS,
        json=entorno_b.cuerpo(ubicacion_id=str(entorno_a.deposito_id)),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 404
    assert _contar(sesion, "stock_movimiento", entorno_b.org) == 0


def test_inv21_un_producto_ajeno_responde_404(cliente: TestClient, sesion: Session) -> None:
    entorno_a = Entorno(sesion, usuario="comprador_a")
    entorno_b = Entorno(sesion, usuario="comprador_b")
    headers_b = entorno_b.entrar(cliente)
    cuerpo = entorno_b.cuerpo()
    cuerpo["lineas"][0]["producto_id"] = str(entorno_a.vino_id)

    respuesta = cliente.post(URL_COMPRAS, json=cuerpo, headers=_con_op(headers_b))

    assert respuesta.status_code == 404
    assert respuesta.json()["linea"] == 0


def test_la_compra_de_otro_proveedor_de_la_organizacion_responde_422_con_su_linea(
    cliente: TestClient, sesion: Session
) -> None:
    """D4, CAT-06."""
    entorno = Entorno(sesion)
    otro = crear_proveedor(sesion, entorno.org, nombre="Distribuidora Norte")
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_COMPRAS, json=entorno.cuerpo(proveedor_id=str(otro)), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "PROVEEDOR_NO_CORRESPONDE"
    assert respuesta.json()["linea"] == 0


# --- POST /compras/{id}/anulacion (COMPRA_ANULAR, tarea 9.3) ------------------------------


def _confirmar(
    cliente: TestClient, entorno: Entorno, headers: dict[str, str], **cambios: object
) -> str:
    respuesta = cliente.post(URL_COMPRAS, json=entorno.cuerpo(**cambios), headers=_con_op(headers))
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["compra_id"])


def _url_anulacion(compra_id: str) -> str:
    return f"{URL_COMPRAS}/{compra_id}/anulacion"


def test_anular_una_compra_a_credito_responde_200_con_su_resultado(
    cliente: TestClient, sesion: Session
) -> None:
    """CMP-05, CC-03: compra anulada, stock y cuenta revertidos."""
    entorno = Entorno(sesion, permisos=COMPRADOR_Y_ANULADOR)
    motivo = entorno.crear_motivo()
    headers = entorno.entrar(cliente)
    compra_id = _confirmar(cliente, entorno, headers)

    respuesta = cliente.post(
        _url_anulacion(compra_id), json={"motivo_id": str(motivo)}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "compra_id": compra_id,
        "estado": "ANULADA",
        "pago_anulado": False,
        "observaciones": ["ANULACION_COMPRA_SIN_RECALCULO"],
    }
    estado = sesion.execute(
        text("SELECT estado FROM compra WHERE id = :id"), {"id": compra_id}
    ).scalar_one()
    assert estado == "ANULADA"
    saldo = sesion.execute(
        text("SELECT saldo FROM saldo_cuenta WHERE organizacion_id = :o"), {"o": entorno.org}
    ).scalar_one()
    assert str(saldo) == "0.00"
    assert _contar(sesion, "stock_movimiento", entorno.org) == 4
    estado_comando = sesion.execute(
        text("SELECT estado FROM comando WHERE tipo = 'COMPRA_ANULAR' AND organizacion_id = :o"),
        {"o": entorno.org},
    ).scalar_one()
    assert estado_comando == "ACEPTADO_CON_OBSERVACIONES"


def test_anular_una_compra_de_contado_devolviendo_el_pago(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=COMPRADOR_Y_ANULADOR)
    motivo = entorno.crear_motivo()
    medio = entorno.crear_medio()
    headers = entorno.entrar(cliente)
    compra_id = _confirmar(
        cliente,
        entorno,
        headers,
        condicion="CONTADO",
        medios=[{"medio_pago_id": str(medio), "importe": "152460.00"}],
    )

    respuesta = cliente.post(
        _url_anulacion(compra_id),
        json={"motivo_id": str(motivo), "devuelve_pago": True},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["pago_anulado"] is True
    estado_pago = sesion.execute(
        text("SELECT estado FROM pago_proveedor WHERE compra_id = :id"), {"id": compra_id}
    ).scalar_one()
    assert estado_pago == "ANULADA"


def test_confirmar_de_contado_con_un_medio_inexistente_indica_el_medio(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_COMPRAS,
        json=entorno.cuerpo(
            condicion="CONTADO", medios=[{"medio_pago_id": str(uuid4()), "importe": "152460.00"}]
        ),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["medio"] == 0
    assert _contar(sesion, "compra", entorno.org) == 0


def test_la_anulacion_sin_operation_id_responde_400(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=COMPRADOR_Y_ANULADOR)
    motivo = entorno.crear_motivo()
    headers = entorno.entrar(cliente)
    compra_id = _confirmar(cliente, entorno, headers)

    respuesta = cliente.post(
        _url_anulacion(compra_id), json={"motivo_id": str(motivo)}, headers=headers
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


def test_la_anulacion_sin_permiso_responde_403_y_la_compra_sigue_confirmada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)  # solo REGISTRAR_COMPRA
    motivo = entorno.crear_motivo()
    headers = entorno.entrar(cliente)
    compra_id = _confirmar(cliente, entorno, headers)

    respuesta = cliente.post(
        _url_anulacion(compra_id), json={"motivo_id": str(motivo)}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 403
    estado = sesion.execute(
        text("SELECT estado FROM compra WHERE id = :id"), {"id": compra_id}
    ).scalar_one()
    assert estado == "CONFIRMADA"


def test_inv21_anular_la_compra_de_otra_organizacion_responde_404(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=COMPRADOR_Y_ANULADOR)
    motivo = entorno.crear_motivo()
    ajena = Entorno(sesion, permisos=COMPRADOR_Y_ANULADOR, usuario="otro")
    headers_ajenos = ajena.entrar(cliente)
    compra_ajena = _confirmar(cliente, ajena, headers_ajenos)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        _url_anulacion(compra_ajena), json={"motivo_id": str(motivo)}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 404
    estado = sesion.execute(
        text("SELECT estado FROM compra WHERE id = :id"), {"id": compra_ajena}
    ).scalar_one()
    assert estado == "CONFIRMADA"


def test_anular_dos_veces_responde_409_compra_ya_anulada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=COMPRADOR_Y_ANULADOR)
    motivo = entorno.crear_motivo()
    headers = entorno.entrar(cliente)
    compra_id = _confirmar(cliente, entorno, headers)
    url = _url_anulacion(compra_id)
    primera = cliente.post(url, json={"motivo_id": str(motivo)}, headers=_con_op(headers))
    assert primera.status_code == 200

    segunda = cliente.post(url, json={"motivo_id": str(motivo)}, headers=_con_op(headers))

    assert segunda.status_code == 409
    assert segunda.json()["codigo"] == "COMPRA_YA_ANULADA"


def test_inv06_el_reenvio_de_la_anulacion_devuelve_lo_mismo_y_no_duplica(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=COMPRADOR_Y_ANULADOR)
    motivo = entorno.crear_motivo()
    headers = entorno.entrar(cliente)
    compra_id = _confirmar(cliente, entorno, headers)
    operation_id = uuid4()
    url = _url_anulacion(compra_id)

    primera = cliente.post(
        url, json={"motivo_id": str(motivo)}, headers=_con_op(headers, operation_id)
    )
    segunda = cliente.post(
        url, json={"motivo_id": str(motivo)}, headers=_con_op(headers, operation_id)
    )

    assert (primera.status_code, segunda.status_code) == (200, 200)
    assert segunda.json() == primera.json()
    assert _contar(sesion, "stock_movimiento", entorno.org) == 4


def test_la_anulacion_con_motivo_de_otro_ambito_responde_422(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=COMPRADOR_Y_ANULADOR)
    ajuste = entorno.crear_motivo("AJUSTE_STOCK", "Rotura")
    headers = entorno.entrar(cliente)
    compra_id = _confirmar(cliente, entorno, headers)

    respuesta = cliente.post(
        _url_anulacion(compra_id), json={"motivo_id": str(ajuste)}, headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "MOTIVO_INVALIDO"


def test_la_anulacion_no_acepta_campos_ajenos(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=COMPRADOR_Y_ANULADOR)
    motivo = entorno.crear_motivo()
    headers = entorno.entrar(cliente)
    compra_id = _confirmar(cliente, entorno, headers)

    respuesta = cliente.post(
        _url_anulacion(compra_id),
        json={"motivo_id": str(motivo), "organizacion_id": str(uuid4())},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422


# --- GET /compras y GET /compras/{id} (tarea 10.1) ------------------------------------------


def _cuerpo_de(proveedor: tuple[UUID, UUID, UUID], **cambios: object) -> dict[str, Any]:
    """Una compra de 10 cajas del producto del proveedor `(proveedor, producto, presentacion)`."""
    proveedor_id, producto_id, presentacion_id = proveedor
    base: dict[str, Any] = {
        "proveedor_id": str(proveedor_id),
        "fecha": "2026-01-10",
        "condicion": "CREDITO",
        "total_factura": "72600.00",
        "lineas": [
            {
                "producto_id": str(producto_id),
                "presentacion_id": str(presentacion_id),
                "cantidad": "10",
                "valor": "6000.00",
                "incluye_iva": False,
            }
        ],
    }
    base.update(cambios)
    return base


def _publicar(
    cliente: TestClient,
    entorno: Entorno,
    headers: dict[str, str],
    proveedor: tuple[UUID, UUID, UUID],
    **cambios: object,
) -> str:
    cuerpo = _cuerpo_de(proveedor, ubicacion_id=str(entorno.deposito_id), **cambios)
    respuesta = cliente.post(URL_COMPRAS, json=cuerpo, headers=_con_op(headers))
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["compra_id"])


def _principal(entorno: Entorno) -> tuple[UUID, UUID, UUID]:
    return entorno.proveedor_id, entorno.vino_id, entorno.caja_x6_id


def _ids(respuesta_json: dict[str, Any]) -> list[str]:
    return [item["id"] for item in respuesta_json["items"]]


def test_listar_compras_devuelve_las_de_la_organizacion_de_la_mas_reciente_a_la_mas_vieja(
    cliente: TestClient, sesion: Session
) -> None:
    """`02` §11: orden descendente de fecha; importes como string."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    vieja = _publicar(cliente, entorno, headers, _principal(entorno), fecha="2026-01-05")
    nueva = _publicar(cliente, entorno, headers, _principal(entorno), fecha="2026-01-20")
    media = _publicar(
        cliente,
        entorno,
        headers,
        _principal(entorno),
        fecha="2026-01-12",
        numero_comprobante="A-0003-00012345",
    )

    respuesta = cliente.get(URL_COMPRAS, headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert _ids(cuerpo) == [nueva, media, vieja]
    assert cuerpo["cursor_siguiente"] is None
    item = next(i for i in cuerpo["items"] if i["id"] == media)
    assert item["fecha"] == "2026-01-12"
    assert item["proveedor_id"] == str(entorno.proveedor_id)
    assert item["proveedor_nombre"] == "Bodega Sur"
    assert item["condicion"] == "CREDITO"
    assert item["estado"] == "CONFIRMADA"
    assert item["total_neto"] == "60000.00"
    assert item["total_factura"] == "72600.00"
    assert item["numero_comprobante"] == "A-0003-00012345"


def test_listar_compras_filtra_por_proveedor_y_cada_una_aparece_una_vez(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Filtro por proveedor": solo las de P, una vez a lo largo de las páginas."""
    entorno = Entorno(sesion)
    otro = entorno.agregar_proveedor("Distribuidora Norte")
    headers = entorno.entrar(cliente)
    de_p = [
        _publicar(cliente, entorno, headers, _principal(entorno), fecha=f"2026-01-{dia:02d}")
        for dia in (3, 4, 5)
    ]
    _publicar(cliente, entorno, headers, otro, fecha="2026-01-06")

    primera = cliente.get(
        URL_COMPRAS,
        params={"proveedor_id": str(entorno.proveedor_id), "limite": 2},
        headers=headers,
    ).json()
    segunda = cliente.get(
        URL_COMPRAS,
        params={
            "proveedor_id": str(entorno.proveedor_id),
            "limite": 2,
            "cursor": primera["cursor_siguiente"],
        },
        headers=headers,
    ).json()

    assert len(primera["items"]) == 2
    assert primera["cursor_siguiente"] is not None
    assert segunda["cursor_siguiente"] is None
    assert sorted(_ids(primera) + _ids(segunda)) == sorted(de_p)


def test_listar_compras_pagina_por_cursor_sin_repetir_ni_omitir(
    cliente: TestClient, sesion: Session
) -> None:
    """Paginación por cursor con fechas repetidas: el desempate por `id` no pierde filas."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    publicadas = [
        _publicar(cliente, entorno, headers, _principal(entorno), fecha="2026-01-10")
        for _ in range(5)
    ]
    vistas: list[str] = []
    cursor: str | None = None

    for _ in range(5):
        params: dict[str, Any] = {"limite": 2}
        if cursor is not None:
            params["cursor"] = cursor
        pagina = cliente.get(URL_COMPRAS, params=params, headers=headers).json()
        vistas.extend(_ids(pagina))
        cursor = pagina["cursor_siguiente"]
        if cursor is None:
            break

    assert cursor is None
    assert len(vistas) == 5
    assert sorted(vistas) == sorted(publicadas)


def test_listar_compras_filtra_por_estado(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=COMPRADOR_Y_ANULADOR)
    motivo = entorno.crear_motivo()
    headers = entorno.entrar(cliente)
    anulada = _publicar(cliente, entorno, headers, _principal(entorno))
    vigente = _publicar(cliente, entorno, headers, _principal(entorno))
    assert (
        cliente.post(
            _url_anulacion(anulada), json={"motivo_id": str(motivo)}, headers=_con_op(headers)
        ).status_code
        == 200
    )

    solo_anuladas = cliente.get(URL_COMPRAS, params={"estado": "ANULADA"}, headers=headers).json()
    solo_confirmadas = cliente.get(
        URL_COMPRAS, params={"estado": "CONFIRMADA"}, headers=headers
    ).json()

    assert _ids(solo_anuladas) == [anulada]
    assert _ids(solo_confirmadas) == [vigente]


def test_listar_compras_con_un_estado_desconocido_responde_422(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_COMPRAS, params={"estado": "BORRADOR"}, headers=headers)

    assert respuesta.status_code == 422


def test_listar_compras_filtra_por_rango_de_fechas_inclusivo(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    por_fecha = {
        fecha: _publicar(cliente, entorno, headers, _principal(entorno), fecha=fecha)
        for fecha in ("2026-01-01", "2026-01-10", "2026-01-20", "2026-01-31")
    }

    dentro = cliente.get(
        URL_COMPRAS, params={"desde": "2026-01-10", "hasta": "2026-01-20"}, headers=headers
    ).json()
    desde = cliente.get(URL_COMPRAS, params={"desde": "2026-01-20"}, headers=headers).json()
    hasta = cliente.get(URL_COMPRAS, params={"hasta": "2026-01-01"}, headers=headers).json()

    assert sorted(_ids(dentro)) == sorted([por_fecha["2026-01-10"], por_fecha["2026-01-20"]])
    assert sorted(_ids(desde)) == sorted([por_fecha["2026-01-20"], por_fecha["2026-01-31"]])
    assert _ids(hasta) == [por_fecha["2026-01-01"]]


def test_listar_compras_con_el_rango_invertido_responde_422(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(
        URL_COMPRAS, params={"desde": "2026-02-01", "hasta": "2026-01-01"}, headers=headers
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "RANGO_DE_FECHAS_INVALIDO"


def test_listar_compras_busca_por_numero_de_comprobante(
    cliente: TestClient, sesion: Session
) -> None:
    """D13: el número de comprobante es buscable en el listado."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    buscada = _publicar(
        cliente, entorno, headers, _principal(entorno), numero_comprobante="A-0003-00012345"
    )
    _publicar(cliente, entorno, headers, _principal(entorno), numero_comprobante="B-0001-00000001")
    _publicar(cliente, entorno, headers, _principal(entorno))

    respuesta = cliente.get(URL_COMPRAS, params={"numero_comprobante": "0003-000"}, headers=headers)

    assert _ids(respuesta.json()) == [buscada]


@pytest.mark.parametrize("limite", [0, -1, 201])
def test_listar_compras_con_limite_fuera_de_rango_responde_422(
    cliente: TestClient, sesion: Session, limite: int
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_COMPRAS, params={"limite": limite}, headers=headers)

    assert respuesta.status_code == 422


def test_listar_compras_acepta_el_limite_maximo(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    assert cliente.get(URL_COMPRAS, params={"limite": 200}, headers=headers).status_code == 200
    assert cliente.get(URL_COMPRAS, params={"limite": 1}, headers=headers).status_code == 200


def test_listar_compras_con_un_cursor_ilegible_responde_422(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_COMPRAS, params={"cursor": "no-es-un-cursor"}, headers=headers)

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "CURSOR_INVALIDO"


@pytest.mark.parametrize(
    ("permisos", "esperado"),
    [
        (frozenset({"REGISTRAR_COMPRA"}), 200),
        (frozenset({"ANULAR_COMPRA"}), 200),
        (frozenset({"GESTIONAR_PROVEEDORES"}), 403),
    ],
)
def test_leer_compras_exige_registrar_o_anular_compra(
    cliente: TestClient, sesion: Session, permisos: frozenset[str], esperado: int
) -> None:
    """D14: `REGISTRAR_COMPRA` o `ANULAR_COMPRA`; cualquier otro permiso, 403."""
    entorno = Entorno(sesion, permisos=permisos)
    headers = entorno.entrar(cliente)

    listado = cliente.get(URL_COMPRAS, headers=headers)
    detalle = cliente.get(f"{URL_COMPRAS}/{uuid4()}", headers=headers)

    assert listado.status_code == esperado
    assert detalle.status_code == (404 if esperado == 200 else 403)


def test_listar_compras_sin_sesion_responde_401(cliente: TestClient, sesion: Session) -> None:
    Entorno(sesion).entrar(cliente)

    assert cliente.get(URL_COMPRAS).status_code == 401


def test_inv21_el_listado_no_devuelve_compras_de_otra_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    ajena = Entorno(sesion, usuario="otro")
    headers_ajenos = ajena.entrar(cliente)
    compra_ajena = _publicar(cliente, ajena, headers_ajenos, _principal(ajena))
    propia = _publicar(cliente, entorno, entorno.entrar(cliente), _principal(entorno))
    headers = entorno.entrar(cliente)

    todas = cliente.get(URL_COMPRAS, headers=headers).json()
    con_proveedor_ajeno = cliente.get(
        URL_COMPRAS, params={"proveedor_id": str(ajena.proveedor_id)}, headers=headers
    ).json()

    assert _ids(todas) == [propia]
    assert compra_ajena not in _ids(todas)
    assert con_proveedor_ajeno["items"] == []


def test_el_detalle_devuelve_lineas_pago_y_sin_anulacion(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    medio = entorno.crear_medio("Efectivo")
    headers = entorno.entrar(cliente)
    compra_id = _publicar(
        cliente,
        entorno,
        headers,
        _principal(entorno),
        condicion="CONTADO",
        observacion="entrega en depósito",
        medios=[{"medio_pago_id": str(medio), "importe": "72600.00", "referencia": "recibo 9"}],
    )

    respuesta = cliente.get(f"{URL_COMPRAS}/{compra_id}", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id"] == compra_id
    assert cuerpo["estado"] == "CONFIRMADA"
    assert cuerpo["condicion"] == "CONTADO"
    assert cuerpo["observacion"] == "entrega en depósito"
    assert cuerpo["ubicacion_id"] == str(entorno.deposito_id)
    assert cuerpo["total_factura"] == "72600.00"
    assert cuerpo["anulacion"] is None
    (linea,) = cuerpo["lineas"]
    assert linea["orden"] == 1
    assert linea["producto_id"] == str(entorno.vino_id)
    assert linea["producto_nombre"] == "Vino A"
    assert linea["presentacion_nombre"] == "Caja x6"
    assert linea["unidades_presentacion"] == 6
    assert linea["unidades_referencia"] == 6
    assert linea["nombre_referencia"] == "Caja x6"
    assert linea["cantidad"] == "10.000"
    assert linea["cantidad_base"] == 60
    assert linea["valor_presentacion"] == "6000.00"
    assert linea["incluye_iva"] is False
    assert linea["bonificacion"] == "0.000000"
    assert linea["alicuota_aplicada"] == "0.210000"
    assert linea["costo_base"] == "1000.000000"
    assert linea["importe_neto"] == "60000.00"
    pago = cuerpo["pago"]
    assert pago["importe"] == "72600.00"
    assert pago["estado"] == "CONFIRMADA"
    assert pago["anulado_en"] is None
    assert [(m["medio_nombre"], m["importe"], m["referencia"]) for m in pago["medios"]] == [
        ("Efectivo", "72600.00", "recibo 9")
    ]


def test_el_detalle_de_una_compra_a_credito_no_tiene_pago(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    compra_id = _publicar(cliente, entorno, headers, _principal(entorno))

    cuerpo = cliente.get(f"{URL_COMPRAS}/{compra_id}", headers=headers).json()

    assert cuerpo["pago"] is None


def test_el_detalle_de_una_compra_anulada_incluye_la_anulacion_y_el_pago_anulado(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=COMPRADOR_Y_ANULADOR)
    motivo = entorno.crear_motivo(nombre="Devolución al proveedor")
    medio = entorno.crear_medio()
    headers = entorno.entrar(cliente)
    compra_id = _publicar(
        cliente,
        entorno,
        headers,
        _principal(entorno),
        condicion="CONTADO",
        medios=[{"medio_pago_id": str(medio), "importe": "72600.00"}],
    )
    anulada = cliente.post(
        _url_anulacion(compra_id),
        json={"motivo_id": str(motivo), "devuelve_pago": True},
        headers=_con_op(headers),
    )
    assert anulada.status_code == 200

    cuerpo = cliente.get(f"{URL_COMPRAS}/{compra_id}", headers=headers).json()

    assert cuerpo["estado"] == "ANULADA"
    assert cuerpo["anulacion"]["motivo_id"] == str(motivo)
    assert cuerpo["anulacion"]["motivo_nombre"] == "Devolución al proveedor"
    assert cuerpo["anulacion"]["anulada_por_id"] is not None
    assert cuerpo["anulacion"]["anulada_en"] is not None
    assert cuerpo["pago"]["estado"] == "ANULADA"
    assert cuerpo["pago"]["anulado_en"] is not None


def test_inv21_el_detalle_de_una_compra_de_otra_organizacion_responde_404(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Compra de otra organización"."""
    entorno = Entorno(sesion)
    ajena = Entorno(sesion, usuario="otro")
    compra_ajena = _publicar(cliente, ajena, ajena.entrar(cliente), _principal(ajena))
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(f"{URL_COMPRAS}/{compra_ajena}", headers=headers)

    assert respuesta.status_code == 404
    assert str(ajena.proveedor_id) not in respuesta.text


def test_el_detalle_con_un_id_que_no_es_uuid_responde_422(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    assert cliente.get(f"{URL_COMPRAS}/no-es-uuid", headers=headers).status_code == 422


# --- GET /catalogo/productos?proveedor_id= (tarea 10.2) -----------------------------------

URL_PRODUCTOS = "/api/v1/catalogo/productos"
CATALOGADOR = frozenset({"GESTIONAR_CATALOGO"})


def test_listar_productos_filtra_por_proveedor_y_activo_con_paginacion(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Filtro por proveedor": solo los del proveedor P, paginados por cursor."""
    entorno = Entorno(sesion, permisos=CATALOGADOR)
    otro_proveedor, otro_producto, _ = entorno.agregar_proveedor("Distribuidora Norte")
    inactivo = crear_producto_sql(
        sesion, entorno.org, nombre="Vino viejo", proveedor_id=entorno.proveedor_id
    )
    sesion.execute(
        text("UPDATE producto SET activo = false WHERE organizacion_id = :o AND id = :p"),
        {"o": entorno.org, "p": inactivo},
    )
    headers = entorno.entrar(cliente)

    primera = cliente.get(
        URL_PRODUCTOS,
        params={"proveedor_id": str(entorno.proveedor_id), "activo": "true", "limite": 1},
        headers=headers,
    ).json()
    segunda = cliente.get(
        URL_PRODUCTOS,
        params={
            "proveedor_id": str(entorno.proveedor_id),
            "activo": "true",
            "limite": 1,
            "cursor": primera["cursor_siguiente"],
        },
        headers=headers,
    ).json()

    ids = [item["id"] for item in primera["items"] + segunda["items"]]
    assert sorted(ids) == sorted([str(entorno.vino_id), str(entorno.cerveza_id)])
    assert str(otro_producto) not in ids
    assert str(inactivo) not in ids
    assert segunda["cursor_siguiente"] is None
    assert otro_proveedor != entorno.proveedor_id


def test_listar_productos_sin_filtro_devuelve_los_de_todos_los_proveedores(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=CATALOGADOR)
    _, otro_producto, _ = entorno.agregar_proveedor("Distribuidora Norte")
    headers = entorno.entrar(cliente)

    cuerpo = cliente.get(URL_PRODUCTOS, headers=headers).json()

    assert str(otro_producto) in [item["id"] for item in cuerpo["items"]]
    assert len(cuerpo["items"]) == 3


def test_inv21_filtrar_por_el_proveedor_de_otra_organizacion_devuelve_lista_vacia(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=CATALOGADOR)
    ajena = Entorno(sesion, permisos=CATALOGADOR, usuario="otro")
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(
        URL_PRODUCTOS, params={"proveedor_id": str(ajena.proveedor_id)}, headers=headers
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {"items": [], "cursor_siguiente": None}


# --- GET /configuracion/medios-pago y /configuracion/motivos (tarea 10.3) ----------------

URL_MEDIOS = "/api/v1/configuracion/medios-pago"
URL_MOTIVOS = "/api/v1/configuracion/motivos"


def test_medios_de_pago_devuelve_solo_los_activos_de_la_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    """Cualquier usuario autenticado (D14), sin permiso de compras."""
    entorno = Entorno(sesion, permisos=frozenset())
    efectivo = entorno.crear_medio("Efectivo")
    sesion.execute(
        text(
            "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, activo, "
            "creado_en, actualizado_en) VALUES (:id, :org, 'Transferencia', true, true, :m, :m), "
            "(:id2, :org, 'Cheque', false, false, :m, :m)"
        ),
        {"id": uuid4(), "id2": uuid4(), "org": entorno.org, "m": MOMENTO},
    )
    ajena = Entorno(sesion, usuario="otro")
    ajena.crear_medio("Efectivo ajeno")
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_MEDIOS, headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    medios = {m["nombre"]: m for m in respuesta.json()["items"]}
    assert sorted(medios) == ["Efectivo", "Transferencia"]
    assert medios["Efectivo"]["id"] == str(efectivo)
    assert medios["Efectivo"]["requiere_referencia"] is False
    assert medios["Transferencia"]["requiere_referencia"] is True
    assert set(medios["Efectivo"]) == {"id", "nombre", "requiere_referencia"}


def test_motivos_devuelve_solo_los_activos_del_ambito_pedido_de_la_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=frozenset())
    anulacion = entorno.crear_motivo("ANULACION_COMPRA", "Error de carga")
    entorno.crear_motivo("AJUSTE_STOCK", "Rotura")
    sesion.execute(
        text(
            "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :org, 'ANULACION_COMPRA', 'Viejo', false, :m, :m)"
        ),
        {"id": uuid4(), "org": entorno.org, "m": MOMENTO},
    )
    ajena = Entorno(sesion, usuario="otro")
    ajena.crear_motivo("ANULACION_COMPRA", "Ajeno")
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_MOTIVOS, params={"ambito": "ANULACION_COMPRA"}, headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["items"] == [{"id": str(anulacion), "nombre": "Error de carga"}]


def test_motivos_con_un_ambito_fuera_de_la_lista_responde_422_ambito_invalido(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=frozenset())
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_MOTIVOS, params={"ambito": "CUALQUIERA"}, headers=headers)

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "AMBITO_INVALIDO"


def test_motivos_sin_ambito_responde_422(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=frozenset())
    headers = entorno.entrar(cliente)

    assert cliente.get(URL_MOTIVOS, headers=headers).status_code == 422


@pytest.mark.parametrize("url", [URL_MEDIOS, f"{URL_MOTIVOS}?ambito=ANULACION_COMPRA"])
def test_medios_y_motivos_sin_sesion_responden_401(
    cliente: TestClient, sesion: Session, url: str
) -> None:
    Entorno(sesion).entrar(cliente)

    assert cliente.get(url).status_code == 401


@pytest.mark.parametrize(
    ("permisos", "esperado"),
    [
        (frozenset({"REGISTRAR_COMPRA"}), 200),
        (frozenset({"GESTIONAR_CATALOGO"}), 200),
        (frozenset({"ANULAR_COMPRA"}), 403),
    ],
)
def test_leer_productos_acepta_gestionar_catalogo_o_registrar_compra(
    cliente: TestClient, sesion: Session, permisos: frozenset[str], esperado: int
) -> None:
    """D17: la LECTURA del catálogo de productos (listado con `proveedor_id` y detalle con
    presentaciones) la abre `REGISTRAR_COMPRA`, para llenar el formulario de compra."""
    entorno = Entorno(sesion, permisos=permisos)
    headers = entorno.entrar(cliente)

    listado = cliente.get(
        "/api/v1/catalogo/productos",
        params={"proveedor_id": str(entorno.proveedor_id)},
        headers=headers,
    )
    detalle = cliente.get(f"/api/v1/catalogo/productos/{entorno.vino_id}", headers=headers)

    assert listado.status_code == esperado
    assert detalle.status_code == esperado
    if esperado == 200:
        assert {p["nombre"] for p in listado.json()["items"]} == {"Vino A", "Cerveza B"}
        assert len(detalle.json()["presentaciones"]) == 1


def test_editar_productos_sigue_exigiendo_gestionar_catalogo(
    cliente: TestClient, sesion: Session
) -> None:
    """D17: abrir la lectura NO abre la escritura."""
    entorno = Entorno(sesion, permisos=COMPRADOR)
    headers = entorno.entrar(cliente)

    respuesta = cliente.put(
        f"/api/v1/catalogo/productos/{entorno.vino_id}",
        json={"nombre": "Otro"},
        headers={**headers, "Operation-Id": str(uuid4())},
    )

    assert respuesta.status_code == 403


@pytest.mark.parametrize(
    ("permisos", "esperado"),
    [
        (frozenset({"REGISTRAR_COMPRA"}), 200),
        (frozenset({"GESTIONAR_CATALOGO"}), 200),
        (frozenset({"ANULAR_COMPRA"}), 403),
    ],
)
def test_leer_alicuotas_acepta_gestionar_catalogo_o_registrar_compra(
    cliente: TestClient, sesion: Session, permisos: frozenset[str], esperado: int
) -> None:
    """Corolario de D17: la vista previa de la línea necesita la alícuota del producto, así
    que la LECTURA de alícuotas también la abre `REGISTRAR_COMPRA`."""
    entorno = Entorno(sesion, permisos=permisos)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get("/api/v1/configuracion/alicuotas", headers=headers)

    assert respuesta.status_code == esperado


@pytest.mark.parametrize(
    ("url", "permisos", "esperado"),
    [
        ("/api/v1/proveedores/opciones", frozenset({"REGISTRAR_COMPRA"}), 200),
        ("/api/v1/proveedores/opciones", frozenset({"GESTIONAR_CATALOGO"}), 200),
        ("/api/v1/proveedores/opciones", frozenset({"ANULAR_COMPRA"}), 403),
        ("/api/v1/stock/ubicaciones", frozenset({"REGISTRAR_COMPRA"}), 200),
        ("/api/v1/stock/ubicaciones", frozenset({"TRANSFERIR_STOCK"}), 200),
        ("/api/v1/stock/ubicaciones", frozenset({"ANULAR_COMPRA"}), 403),
    ],
)
def test_lecturas_de_apoyo_de_la_compra_aceptan_registrar_compra(
    cliente: TestClient, sesion: Session, url: str, permisos: frozenset[str], esperado: int
) -> None:
    """D18 (corolario de D17): el formulario de compra necesita la lista de proveedores y de
    ubicaciones; esas dos LECTURAS también las abre `REGISTRAR_COMPRA`, sin quitar el
    permiso que ya las abría (INV-21 sigue filtrando por organización del token)."""
    entorno = Entorno(sesion, permisos=permisos)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(url, headers=headers)

    assert respuesta.status_code == esperado


def test_abrir_las_lecturas_de_apoyo_no_abre_escrituras(
    cliente: TestClient, sesion: Session
) -> None:
    """D18: crear ubicación sigue exigiendo `UBICACION_CREAR`."""
    entorno = Entorno(sesion, permisos=COMPRADOR)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        "/api/v1/stock/ubicaciones",
        json={"nombre": "Otra", "tipo": "DEPOSITO", "requiere_toma": False},
        headers={**headers, "Operation-Id": str(uuid4())},
    )

    assert respuesta.status_code == 403


def test_el_detalle_de_un_producto_con_proveedor_inactivo_muestra_su_nombre(
    cliente: TestClient, sesion: Session
) -> None:
    """Spec `catalogo/productos-y-presentaciones` (CAT-06): el nombre del proveedor viene
    aunque esté inactivo, no un texto genérico."""
    entorno = Entorno(sesion, permisos=COMPRADOR)
    sesion.execute(
        text("UPDATE proveedor SET activo = false WHERE id = :id"), {"id": entorno.proveedor_id}
    )
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(f"/api/v1/catalogo/productos/{entorno.vino_id}", headers=headers)

    assert respuesta.status_code == 200
    assert respuesta.json()["proveedor_nombre"] == "Bodega Sur"
