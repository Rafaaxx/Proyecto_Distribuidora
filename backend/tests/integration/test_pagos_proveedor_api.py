"""Change 12, tarea 4.3: `POST /api/v1/pagos-proveedores` (`PAGO_PROVEEDOR_REGISTRAR`) por
HTTP.

Mismo arnés que `test_compras_api.py`: PostgreSQL real, motor propio de la aplicación y
`login` real (nunca un access token fabricado). Cubre el contrato HTTP: `Operation-Id`
obligatorio, importes como string, Problem Details con el índice del medio en los errores
de medio, 201 con el pago y el saldo resultante, permiso, idempotencia y aislamiento
(INV-21).

Reglas citadas: PAG-01, PAG-02, INV-03, INV-06, INV-08, INV-21, SEG-06, SEG-07, TR-04,
TR-07, TR-09 y `design.md` D3, D4, D5, D6, D10, D14.
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
JWT_SECRET = "secreto-de-prueba-pagos-api"
URL_PAGOS = "/api/v1/pagos-proveedores"
URL_COMPRAS = "/api/v1/compras"

PAGADOR = frozenset({"REGISTRAR_PAGO_PROVEEDOR"})
PAGADOR_Y_COMPRADOR = frozenset({"REGISTRAR_PAGO_PROVEEDOR", "REGISTRAR_COMPRA"})
ANULADOR = frozenset({"REGISTRAR_PAGO_PROVEEDOR", "ANULAR_PAGO_PROVEEDOR", "REGISTRAR_COMPRA"})
"""Para armar la deuda que el pago cancela hace falta `REGISTRAR_COMPRA` (PAG-02)."""


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
    """Una organización con su usuario, un proveedor, `Vino A` (Caja x6) y un depósito."""

    def __init__(
        self, sesion: Session, *, permisos: frozenset[str] = PAGADOR, usuario: str = "pagador1"
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
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")
        self.efectivo_id = self.crear_medio("Efectivo", requiere_referencia=False)
        self.transferencia_id = self.crear_medio("Transferencia", requiere_referencia=True)

    def crear_medio(
        self,
        nombre: str,
        *,
        requiere_referencia: bool,
        activo: bool = True,
        org: UUID | None = None,
    ) -> UUID:
        medio_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, "
                "activo, creado_en, actualizado_en) "
                "VALUES (:id, :org, :nombre, :ref, :activo, :m, :m)"
            ),
            {
                "id": medio_id,
                "org": org or self.org,
                "nombre": nombre,
                "ref": requiere_referencia,
                "activo": activo,
                "m": MOMENTO,
            },
        )
        return medio_id

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

    def agregar_usuario(
        self,
        cliente_http: TestClient,
        nombre_usuario: str,
        *,
        permisos: frozenset[str],
        nombre: str = "Persona de prueba",
    ) -> dict[str, str]:
        """Alta un usuario más de la MISMA organización con exactamente esos permisos y
        entra con él.

        Sirve para reproducir literalmente el escenario de `design.md` D8 ("un usuario con
        solo `REGISTRAR_PAGO_PROVEEDOR`") sobre una cuenta que YA tiene movimientos: el
        primero arma la deuda por HTTP y este la lee sin ningún otro permiso."""
        rol = identidad_repository.crear_rol(
            self.org,
            self.sesion,
            rol_id=nuevo_id(),
            nombre=f"Rol de {nombre_usuario}",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO,
        )
        for codigo in permisos:
            identidad_repository.asignar_permiso_a_rol(
                self.org, self.sesion, rol_id=rol.id, permiso_codigo=codigo
            )
        identidad_repository.crear_usuario(
            self.org,
            self.sesion,
            usuario_id=nuevo_id(),
            usuario=nombre_usuario,
            nombre=nombre,
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )
        anterior = self.usuario
        self.usuario = nombre_usuario
        try:
            return self.entrar(cliente_http)
        finally:
            self.usuario = anterior

    def hoy(self) -> str:
        return datetime.now(ZoneInfo("America/Argentina/Mendoza")).date().isoformat()

    def cuerpo(self, **cambios: object) -> dict[str, Any]:
        base: dict[str, Any] = {
            "proveedor_id": str(self.proveedor_id),
            "fecha": self.hoy(),
            "importe": "152460.00",
            "medios": [
                {"medio_pago_id": str(self.efectivo_id), "importe": "100000.00"},
                {
                    "medio_pago_id": str(self.transferencia_id),
                    "importe": "52460.00",
                    "referencia": "0042",
                },
            ],
        }
        base.update(cambios)
        return base

    def cuerpo_compra(self, total_factura: str = "153720.00") -> dict[str, Any]:
        """Una compra a crédito que deja al proveedor debiendo `total_factura`."""
        return {
            "proveedor_id": str(self.proveedor_id),
            "fecha": self.hoy(),
            "ubicacion_id": str(self.deposito_id),
            "condicion": "CREDITO",
            "total_factura": total_factura,
            "lineas": [
                {
                    "producto_id": str(self.vino_id),
                    "presentacion_id": str(self.caja_x6_id),
                    "cantidad": "10",
                    "valor": "6000.00",
                    "incluye_iva": False,
                }
            ],
        }

    def dejar_deuda(self, cliente_http: TestClient, headers: dict[str, str], total: str) -> None:
        respuesta = cliente_http.post(
            URL_COMPRAS, json=self.cuerpo_compra(total), headers=_con_op(headers)
        )
        assert respuesta.status_code == 201


def _con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


def _contar(sesion: Session, tabla: str, organizacion_id: UUID) -> int:
    return int(
        sesion.execute(
            text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"),
            {"o": organizacion_id},
        ).scalar_one()
    )


def _saldo(sesion: Session, organizacion_id: UUID) -> str:
    return str(
        sesion.execute(
            text("SELECT saldo FROM saldo_cuenta WHERE organizacion_id = :o"),
            {"o": organizacion_id},
        ).scalar_one()
    )


# --- 201 con el pago y el saldo resultante (PAG-01, PAG-02, CC-04) -----------------------


def test_registrar_un_pago_responde_201_con_el_pago_y_el_saldo_resultante(
    cliente: TestClient, sesion: Session
) -> None:
    """PAG-01, PAG-02, CC-04, INV-03: los importes viajan y vuelven como string, y el
    saldo es el que queda después de aplicar el pago."""
    entorno = Entorno(sesion, permisos=PAGADOR_Y_COMPRADOR)
    headers = entorno.entrar(cliente)
    entorno.dejar_deuda(cliente, headers, "153720.00")

    respuesta = cliente.post(
        URL_PAGOS,
        json=entorno.cuerpo(
            importe="100000.00",
            medios=[{"medio_pago_id": str(entorno.efectivo_id), "importe": "100000.00"}],
        ),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "CONFIRMADA"
    assert cuerpo["importe"] == "100000.00"
    assert cuerpo["saldo"] == "53720.00"
    assert _contar(sesion, "pago_proveedor", entorno.org) == 1
    assert _contar(sesion, "pago_proveedor_medio", entorno.org) == 1
    assert _saldo(sesion, entorno.org) == "53720.00"


def test_la_observacion_se_guarda_recortada(cliente: TestClient, sesion: Session) -> None:
    """D6, PAG-01."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_PAGOS,
        json=entorno.cuerpo(observacion="  paga factura 0001-123  "),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 201
    observacion = sesion.execute(
        text("SELECT observacion FROM pago_proveedor WHERE organizacion_id = :o"),
        {"o": entorno.org},
    ).scalar_one()
    assert observacion == "paga factura 0001-123"


def test_la_observacion_de_exactamente_500_caracteres_se_acepta_y_se_guarda_completa(
    cliente: TestClient, sesion: Session
) -> None:
    """D6, INV-03: el límite es de 500 caracteres y 500 pasan."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    observacion = "a" * 500

    respuesta = cliente.post(
        URL_PAGOS, json=entorno.cuerpo(observacion=observacion), headers=_con_op(headers)
    )

    assert respuesta.status_code == 201
    guardada = sesion.execute(
        text("SELECT observacion FROM pago_proveedor WHERE organizacion_id = :o"),
        {"o": entorno.org},
    ).scalar_one()
    assert guardada == observacion


@pytest.mark.parametrize(
    "observacion",
    ["a" * 501, "a" * 500 + " ", " " * 501],
    ids=["501_caracteres", "500_mas_un_espacio", "501_espacios"],
)
def test_una_observacion_de_mas_de_500_caracteres_responde_422_y_sin_efectos(
    cliente: TestClient, sesion: Session, observacion: str
) -> None:
    """D6: el largo se mide sobre el texto recibido, igual que el formulario (Zod
    `max(500)` sin recortar). Sin pago, sin medios y sin movimiento de cuenta."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_PAGOS, json=entorno.cuerpo(observacion=observacion), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    (error,) = respuesta.json()["detail"]
    assert error["loc"] == ["body", "observacion"]
    assert error["type"] == "string_too_long"
    assert _contar(sesion, "pago_proveedor", entorno.org) == 0
    assert _contar(sesion, "pago_proveedor_medio", entorno.org) == 0
    assert _contar(sesion, "cuenta_movimiento", entorno.org) == 0


def test_500_caracteres_con_espacios_en_los_bordes_se_acepta_y_se_guarda_recortada(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    observacion = " " + "a" * 498 + " "

    respuesta = cliente.post(
        URL_PAGOS, json=entorno.cuerpo(observacion=observacion), headers=_con_op(headers)
    )

    assert respuesta.status_code == 201
    guardada = sesion.execute(
        text("SELECT observacion FROM pago_proveedor WHERE organizacion_id = :o"),
        {"o": entorno.org},
    ).scalar_one()
    assert guardada == "a" * 498


# --- contrato HTTP (TR-07, SYN-01, INV-03, SEG-06, SEG-07, INV-21) ------------------------


def test_sin_operation_id_se_rechaza_con_400_y_sin_efectos(
    cliente: TestClient, sesion: Session
) -> None:
    """TR-07, SYN-01."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(URL_PAGOS, json=entorno.cuerpo(), headers=headers)

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
    assert _contar(sesion, "pago_proveedor", entorno.org) == 0


def test_sin_sesion_responde_401(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion)
    entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_PAGOS, json=entorno.cuerpo(), headers={"Operation-Id": str(uuid4())}
    )

    assert respuesta.status_code == 401


def test_sin_registrar_pago_proveedor_responde_403_sin_efectos_ni_reserva(
    cliente: TestClient, sesion: Session
) -> None:
    """`01` §19, D14, SEG-06."""
    entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_PROVEEDORES"}))
    headers = entorno.entrar(cliente)
    operation_id = uuid4()

    respuesta = cliente.post(
        URL_PAGOS, json=entorno.cuerpo(), headers=_con_op(headers, operation_id)
    )

    assert respuesta.status_code == 403
    assert _contar(sesion, "pago_proveedor", entorno.org) == 0
    assert (
        sesion.execute(
            text("SELECT count(*) FROM comando WHERE operation_id = :id"), {"id": operation_id}
        ).scalar_one()
        == 0
    )


@pytest.mark.parametrize("campo", ["importe", "medio"])
def test_inv03_un_numero_json_en_lugar_de_un_string_se_rechaza(
    cliente: TestClient, sesion: Session, campo: str
) -> None:
    """INV-03: los importes viajan como string; un número JSON no pasa."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    cuerpo = entorno.cuerpo()
    if campo == "importe":
        cuerpo["importe"] = 152460.0
    else:
        cuerpo["medios"][0]["importe"] = 100000.0

    respuesta = cliente.post(URL_PAGOS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 422
    assert _contar(sesion, "pago_proveedor", entorno.org) == 0


def test_el_cuerpo_no_acepta_organizacion_id(cliente: TestClient, sesion: Session) -> None:
    """INV-21, TR-08: la organización sale del token. Un campo extra se ignora en el
    cuerpo HTTP y NUNCA llega al contenido del comando."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_PAGOS, json=entorno.cuerpo(organizacion_id=str(uuid4())), headers=_con_op(headers)
    )

    assert respuesta.status_code == 201
    pago = sesion.execute(
        text("SELECT organizacion_id FROM pago_proveedor WHERE id = :id"),
        {"id": respuesta.json()["pago_id"]},
    ).scalar_one()
    assert pago == entorno.org


# --- Problem Details con el índice del medio (PAG-01, TR-09, INV-21, `02` §11) -------------


@pytest.mark.parametrize("indice", [0, 1])
def test_un_error_de_medio_indica_el_medio_en_el_problem_details(
    cliente: TestClient, sesion: Session, indice: int
) -> None:
    """PAG-01: la transferencia exige referencia; el medio que lo causó viene en el
    Problem Details con su índice 0-based, que cambia con la posición en la lista."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    efectivo = {"medio_pago_id": str(entorno.efectivo_id), "importe": "100000.00"}
    transferencia = {"medio_pago_id": str(entorno.transferencia_id), "importe": "52460.00"}
    medios = [efectivo, transferencia]
    medios.insert(indice, medios.pop(1))
    cuerpo = entorno.cuerpo(medios=medios)

    respuesta = cliente.post(URL_PAGOS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 422
    problema = respuesta.json()
    assert problema["codigo"] == "REFERENCIA_OBLIGATORIA"
    assert problema["medio"] == indice
    assert _contar(sesion, "pago_proveedor", entorno.org) == 0


def test_un_medio_ajeno_responde_404_con_el_medio(cliente: TestClient, sesion: Session) -> None:
    """INV-21, SEG-07."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    ajeno = Entorno(sesion, permisos=PAGADOR, usuario="pagador2")
    medio_ajeno = ajeno.crear_medio("Efectivo", requiere_referencia=False, org=ajeno.org)
    sesion.commit()

    respuesta = cliente.post(
        URL_PAGOS,
        json=entorno.cuerpo(
            importe="100000.00",
            medios=[{"medio_pago_id": str(medio_ajeno), "importe": "100000.00"}],
        ),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 404
    problema = respuesta.json()
    assert problema["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert problema["medio"] == 0
    assert _contar(sesion, "pago_proveedor", entorno.org) == 0


def test_un_medio_inactivo_responde_422_con_el_medio(cliente: TestClient, sesion: Session) -> None:
    """TR-09."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    inactivo = entorno.crear_medio("Billetera vieja", requiere_referencia=False, activo=False)
    sesion.commit()

    respuesta = cliente.post(
        URL_PAGOS,
        json=entorno.cuerpo(
            importe="100000.00",
            medios=[{"medio_pago_id": str(inactivo), "importe": "100000.00"}],
        ),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422
    problema = respuesta.json()
    assert problema["codigo"] == "MEDIO_PAGO_INACTIVO"
    assert problema["medio"] == 0


def test_los_medios_que_no_suman_el_importe_responden_422(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-08: los medios por defecto suman `"152460.00"`; el pago pide un centavo más."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_PAGOS, json=entorno.cuerpo(importe="152460.01"), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "MEDIOS_NO_SUMAN_IMPORTE"


def test_una_fecha_futura_responde_422_con_fecha_invalida(
    cliente: TestClient, sesion: Session
) -> None:
    """TR-04, D4."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)

    respuesta = cliente.post(
        URL_PAGOS, json=entorno.cuerpo(fecha="2099-01-01"), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "FECHA_INVALIDA"


def test_un_proveedor_ajeno_responde_404(cliente: TestClient, sesion: Session) -> None:
    """INV-21, SEG-07, TR-08, en los dos sentidos: ni el usuario de A paga al proveedor de
    B, ni el de B paga al proveedor de A."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    otro = Entorno(sesion, permisos=PAGADOR, usuario="pagador2")
    headers_de_otro = otro.entrar(cliente)

    ajena = cliente.post(
        URL_PAGOS,
        json=entorno.cuerpo(proveedor_id=str(otro.proveedor_id)),
        headers=_con_op(headers),
    )
    propia = cliente.post(
        URL_PAGOS,
        json=otro.cuerpo(proveedor_id=str(entorno.proveedor_id)),
        headers=_con_op(headers_de_otro),
    )

    assert ajena.status_code == 404
    assert ajena.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert propia.status_code == 404
    assert propia.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert _contar(sesion, "pago_proveedor", entorno.org) == 0
    assert _contar(sesion, "pago_proveedor", otro.org) == 0


# --- idempotencia (INV-06, SYN-02) --------------------------------------------------------


def test_el_doble_envio_con_el_mismo_operation_id_devuelve_el_mismo_resultado(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-06, SYN-02."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    operation_id = uuid4()

    primera = cliente.post(URL_PAGOS, json=entorno.cuerpo(), headers=_con_op(headers, operation_id))
    segunda = cliente.post(URL_PAGOS, json=entorno.cuerpo(), headers=_con_op(headers, operation_id))

    assert primera.status_code == 201
    assert primera.json() == segunda.json()
    assert _contar(sesion, "pago_proveedor", entorno.org) == 1
    assert _contar(sesion, "pago_proveedor_medio", entorno.org) == 2
    assert (
        sesion.execute(
            text("SELECT count(*) FROM comando WHERE operation_id = :id"), {"id": operation_id}
        ).scalar_one()
        == 1
    )


def test_el_mismo_operation_id_con_otro_importe_responde_409(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-06, SYN-02."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente)
    operation_id = uuid4()
    cliente.post(URL_PAGOS, json=entorno.cuerpo(), headers=_con_op(headers, operation_id))

    respuesta = cliente.post(
        URL_PAGOS, json=entorno.cuerpo(importe="160000.00"), headers=_con_op(headers, operation_id)
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "COMANDO_INCONSISTENTE"
    assert _contar(sesion, "pago_proveedor", entorno.org) == 1


# --- un pago a un proveedor inactivo con deuda (D5) ---------------------------------------


def test_se_puede_pagar_a_un_proveedor_inactivo_con_deuda(
    cliente: TestClient, sesion: Session
) -> None:
    """`design.md` D5 opción A, ADR-034 punto 3."""
    entorno = Entorno(sesion, permisos=PAGADOR_Y_COMPRADOR)
    headers = entorno.entrar(cliente)
    entorno.dejar_deuda(cliente, headers, "80000.00")
    sesion.execute(
        text("UPDATE proveedor SET activo = false WHERE organizacion_id = :o AND id = :p"),
        {"o": entorno.org, "p": entorno.proveedor_id},
    )
    sesion.commit()

    respuesta = cliente.post(
        URL_PAGOS,
        json=entorno.cuerpo(
            importe="80000.00",
            medios=[{"medio_pago_id": str(entorno.efectivo_id), "importe": "80000.00"}],
        ),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["saldo"] == "0.00"


# --- anulación por HTTP (change 12, tarea 5.4: PAG-03, CC-04; `design.md` D1, D5, D14) ---


def _crear_motivo(sesion: Session, entorno: Entorno, ambito: str) -> UUID:
    """Un motivo activo del `ambito` pedido. Lo crea por SQL (no hay endpoint de motivos:
    es catálogo del change 11)."""
    motivo_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO motivo (id, organizacion_id, nombre, ambito, activo, "
            "creado_en, actualizado_en) "
            "VALUES (:id, :org, :nombre, :ambito, true, :m, :m)"
        ),
        {
            "id": motivo_id,
            "org": entorno.org,
            "nombre": f"Motivo {ambito}",
            "ambito": ambito,
            "m": MOMENTO,
        },
    )
    sesion.commit()
    return motivo_id


def _pagar(cliente: TestClient, headers: dict[str, str], entorno: Entorno) -> dict[str, Any]:
    """Registra el pago del escenario: deja al proveedor debiendo `80000.00`, lo que se le
    paga y quedan en `"0.00"`."""
    entorno.dejar_deuda(cliente, headers, "80000.00")
    respuesta = cliente.post(
        URL_PAGOS,
        json=entorno.cuerpo(
            importe="80000.00",
            medios=[{"medio_pago_id": str(entorno.efectivo_id), "importe": "80000.00"}],
        ),
        headers=_con_op(headers),
    )
    assert respuesta.status_code == 201
    return respuesta.json()


def test_anular_un_pago_responde_200_con_el_estado_y_el_saldo_resultante(
    cliente: TestClient, sesion: Session
) -> None:
    """PAG-03, CC-04, INV-03: `POST /pagos-proveedores/{id}/anulacion` devuelve el estado
    del pago y el saldo del proveedor DESPUÉS de la anulación, con los importes como
    string."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente)
    pago = _pagar(cliente, headers, entorno)
    motivo_id = _crear_motivo(sesion, entorno, "ANULACION_PAGO")

    respuesta = cliente.post(
        f"{URL_PAGOS}/{pago['pago_id']}/anulacion",
        json={"motivo_id": str(motivo_id)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "pago_id": pago["pago_id"],
        "estado": "ANULADA",
        "saldo": "80000.00",
    }
    assert _saldo(sesion, entorno.org) == "80000.00"
    assert _contar(sesion, "pago_proveedor", entorno.org) == 1


def test_el_doble_envio_de_la_anulacion_con_el_mismo_operation_id_devuelve_lo_mismo(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-06, SYN-02: el reenvío con el mismo `Operation-Id` devuelve exactamente el
    mismo resultado y no agrega un segundo `ANULACION_PAGO`."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente)
    pago = _pagar(cliente, headers, entorno)
    motivo_id = _crear_motivo(sesion, entorno, "ANULACION_PAGO")
    operation_id = uuid4()
    url = f"{URL_PAGOS}/{pago['pago_id']}/anulacion"

    primera = cliente.post(
        url, json={"motivo_id": str(motivo_id)}, headers=_con_op(headers, operation_id)
    )
    segunda = cliente.post(
        url, json={"motivo_id": str(motivo_id)}, headers=_con_op(headers, operation_id)
    )

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert segunda.json() == primera.json()
    anulaciones = sesion.execute(
        text(
            "SELECT count(*) FROM cuenta_movimiento WHERE organizacion_id = :o "
            "AND tipo = 'ANULACION_PAGO'"
        ),
        {"o": entorno.org},
    ).scalar_one()
    assert anulaciones == 1


def test_sin_operation_id_la_anulacion_se_rechaza_con_400_y_sin_efectos(
    cliente: TestClient, sesion: Session
) -> None:
    """TR-08: sin `Operation-Id` no hay idempotencia posible, así que se rechaza antes de
    tocar nada."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente)
    pago = _pagar(cliente, headers, entorno)
    motivo_id = _crear_motivo(sesion, entorno, "ANULACION_PAGO")

    respuesta = cliente.post(
        f"{URL_PAGOS}/{pago['pago_id']}/anulacion",
        json={"motivo_id": str(motivo_id)},
        headers=headers,
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
    assert _saldo(sesion, entorno.org) == "0.00"


def test_sin_anular_pago_proveedor_la_anulacion_responde_403_sin_efectos(
    cliente: TestClient, sesion: Session
) -> None:
    """SEG-06: `ANULAR_PAGO_PROVEEDOR` es permiso propio, no el de registrar."""
    entorno = Entorno(sesion, permisos=PAGADOR_Y_COMPRADOR)
    headers = entorno.entrar(cliente)
    pago = _pagar(cliente, headers, entorno)
    motivo_id = _crear_motivo(sesion, entorno, "ANULACION_PAGO")

    respuesta = cliente.post(
        f"{URL_PAGOS}/{pago['pago_id']}/anulacion",
        json={"motivo_id": str(motivo_id)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 403
    assert _saldo(sesion, entorno.org) == "0.00"
    assert _contar(sesion, "pago_proveedor", entorno.org) == 1


def test_un_pago_ajeno_responde_404_y_un_pago_inexistente_tambien(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21: un recurso de otra organización responde 404, no 403; y el código es el
    mismo que el de un id que no existe, para no filtrar existencia."""
    ajena = Entorno(sesion, permisos=ANULADOR, usuario="pagador2")
    headers_ajena = ajena.entrar(cliente)
    pago_ajeno = _pagar(cliente, headers_ajena, ajena)
    ajena.sesion.commit()

    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente)
    motivo_id = _crear_motivo(sesion, entorno, "ANULACION_PAGO")

    por_ajeno = cliente.post(
        f"{URL_PAGOS}/{pago_ajeno['pago_id']}/anulacion",
        json={"motivo_id": str(motivo_id)},
        headers=_con_op(headers),
    )
    por_inexistente = cliente.post(
        f"{URL_PAGOS}/{uuid4()}/anulacion",
        json={"motivo_id": str(motivo_id)},
        headers=_con_op(headers),
    )

    assert por_ajeno.status_code == 404
    assert por_inexistente.status_code == 404
    assert por_ajeno.json()["codigo"] == por_inexistente.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


def test_un_motivo_de_otro_ambito_responde_422_y_sin_efectos(
    cliente: TestClient, sesion: Session
) -> None:
    """D1: la anulación de un pago solo admite motivos del ámbito `ANULACION_PAGO`."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente)
    pago = _pagar(cliente, headers, entorno)
    motivo_id = _crear_motivo(sesion, entorno, "ANULACION_COMPRA")

    respuesta = cliente.post(
        f"{URL_PAGOS}/{pago['pago_id']}/anulacion",
        json={"motivo_id": str(motivo_id)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "MOTIVO_INVALIDO"
    assert _saldo(sesion, entorno.org) == "0.00"


def test_se_puede_anular_el_pago_de_un_proveedor_inactivo(
    cliente: TestClient, sesion: Session
) -> None:
    """`design.md` D5 opción A: la inactividad del proveedor no impide anular su pago."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente)
    pago = _pagar(cliente, headers, entorno)
    motivo_id = _crear_motivo(sesion, entorno, "ANULACION_PAGO")
    sesion.execute(
        text("UPDATE proveedor SET activo = false WHERE organizacion_id = :o AND id = :p"),
        {"o": entorno.org, "p": entorno.proveedor_id},
    )
    sesion.commit()

    respuesta = cliente.post(
        f"{URL_PAGOS}/{pago['pago_id']}/anulacion",
        json={"motivo_id": str(motivo_id)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["saldo"] == "80000.00"


def test_el_cuerpo_de_la_anulacion_no_acepta_organizacion_id(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21, TR-08: la organización sale del token. Un campo extra se ignora en el
    cuerpo HTTP y NUNCA llega al contenido del comando, así que ni siquiera puede
    alterar la anulación."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente)
    pago = _pagar(cliente, headers, entorno)
    motivo_id = _crear_motivo(sesion, entorno, "ANULACION_PAGO")

    respuesta = cliente.post(
        f"{URL_PAGOS}/{pago['pago_id']}/anulacion",
        json={"motivo_id": str(motivo_id), "organizacion_id": str(uuid4())},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200
    organizacion = sesion.execute(
        text("SELECT organizacion_id FROM pago_proveedor WHERE id = :id"),
        {"id": respuesta.json()["pago_id"]},
    ).scalar_one()
    assert organizacion == entorno.org


# --- listado y detalle (change 12, tarea 6.1: PAG-01, TR-04; `design.md` D11, D14) ---------

LECTOR = frozenset({"REGISTRAR_PAGO_PROVEEDOR"})


def _otro_proveedor(sesion: Session, entorno: Entorno, nombre: str = "Bodega Norte") -> UUID:
    proveedor_id = crear_proveedor(sesion, entorno.org, nombre=nombre)
    sesion.commit()
    return proveedor_id


def _pagar_en(
    cliente: TestClient,
    headers: dict[str, str],
    entorno: Entorno,
    *,
    fecha: str,
    importe: str = "100000.00",
    proveedor_id: UUID | None = None,
    observacion: str | None = None,
) -> str:
    """Registra un pago independiente y devuelve su id. La deuda no importa para el
    listado: PAG-02 no exige comprobante (D3)."""
    respuesta = cliente.post(
        URL_PAGOS,
        json=entorno.cuerpo(
            proveedor_id=str(proveedor_id or entorno.proveedor_id),
            fecha=fecha,
            importe=importe,
            medios=[{"medio_pago_id": str(entorno.efectivo_id), "importe": importe}],
            observacion=observacion,
        ),
        headers=_con_op(headers),
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["pago_id"]


def _contado(
    cliente: TestClient, sesion: Session, headers: dict[str, str], entorno: Entorno
) -> tuple[str, str]:
    """Una compra de contado, que nace con su pago de origen `COMPRA` (CMP-03). Devuelve
    `(compra_id, pago_id)`."""
    respuesta = cliente.post(
        URL_COMPRAS,
        json=entorno.cuerpo_compra("152460.00")
        | {
            "condicion": "CONTADO",
            "medios": [{"medio_pago_id": str(entorno.efectivo_id), "importe": "152460.00"}],
        },
        headers=_con_op(headers),
    )
    assert respuesta.status_code == 201, respuesta.text
    compra_id = respuesta.json()["compra_id"]
    pago_id = sesion.execute(
        text("SELECT id FROM pago_proveedor WHERE organizacion_id = :o AND compra_id = :c"),
        {"o": entorno.org, "c": compra_id},
    ).scalar_one()
    return compra_id, str(pago_id)


def _ids_de(cuerpo: dict[str, Any]) -> list[str]:
    return [item["pago_id"] for item in cuerpo["items"]]


def test_listar_pagos_devuelve_los_de_la_organizacion_del_mas_reciente_al_mas_viejo(
    cliente: TestClient, sesion: Session
) -> None:
    """`02` §11 y `design.md` D11: orden descendente de fecha, una fila por pago, con
    fecha, proveedor, importe, origen y estado; importes como string (INV-03)."""
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)
    viejo = _pagar_en(cliente, headers, entorno, fecha="2026-01-05", importe="100000.00")
    nuevo = _pagar_en(cliente, headers, entorno, fecha="2026-01-20", importe="80000.00")

    respuesta = cliente.get(URL_PAGOS, headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert _ids_de(cuerpo) == [nuevo, viejo]
    assert cuerpo["cursor_siguiente"] is None
    assert cuerpo["items"][0] == {
        "pago_id": nuevo,
        "fecha": "2026-01-20",
        "proveedor_id": str(entorno.proveedor_id),
        "proveedor_nombre": "Bodega Sur",
        "importe": "80000.00",
        "origen": "INDEPENDIENTE",
        "estado": "CONFIRMADA",
        "compra_id": None,
    }


def test_listar_pagos_filtra_por_proveedor(cliente: TestClient, sesion: Session) -> None:
    """Escenario "Filtro por proveedor": solo los del proveedor pedido."""
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)
    otro = _otro_proveedor(sesion, entorno)
    mio = _pagar_en(cliente, headers, entorno, fecha="2026-01-05")
    suyo = _pagar_en(
        cliente, headers, entorno, fecha="2026-01-06", importe="80000.00", proveedor_id=otro
    )

    del_mio = cliente.get(
        URL_PAGOS, params={"proveedor_id": str(entorno.proveedor_id)}, headers=headers
    ).json()
    assert _ids_de(
        cliente.get(URL_PAGOS, params={"proveedor_id": str(otro)}, headers=headers).json()
    ) == [suyo]
    assert _ids_de(del_mio) == [mio]


def test_listar_pagos_filtra_por_estado(cliente: TestClient, sesion: Session) -> None:
    """Escenario "Filtro por estado": los anulados van a su propia lista."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente)
    anulado = _pagar_en(cliente, headers, entorno, fecha="2026-01-05")
    vigente = _pagar_en(cliente, headers, entorno, fecha="2026-01-06", importe="80000.00")
    motivo_id = _crear_motivo(sesion, entorno, "ANULACION_PAGO")
    assert (
        cliente.post(
            f"{URL_PAGOS}/{anulado}/anulacion",
            json={"motivo_id": str(motivo_id)},
            headers=_con_op(headers),
        ).status_code
        == 200
    )

    solo_anulados = cliente.get(URL_PAGOS, params={"estado": "ANULADA"}, headers=headers).json()
    solo_confirmados = cliente.get(
        URL_PAGOS, params={"estado": "CONFIRMADA"}, headers=headers
    ).json()

    assert _ids_de(solo_anulados) == [anulado]
    assert solo_anulados["items"][0]["estado"] == "ANULADA"
    assert _ids_de(solo_confirmados) == [vigente]


def test_listar_pagos_incluye_los_de_origen_compra_con_su_compra_id(
    cliente: TestClient, sesion: Session
) -> None:
    """`design.md` D11: los pagos de origen `COMPRA` también aparecen, con su `compra_id`
    para el enlace; el de contado nace con la compra (CMP-03)."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente)
    compra_id, pago_de_contado = _contado(cliente, sesion, headers, entorno)
    independiente = _pagar_en(cliente, headers, entorno, fecha="2026-01-06")

    cuerpo = cliente.get(URL_PAGOS, params={"origen": "COMPRA"}, headers=headers).json()

    assert _ids_de(cuerpo) == [pago_de_contado]
    assert cuerpo["items"][0]["compra_id"] == compra_id
    todos = cliente.get(URL_PAGOS, headers=headers).json()
    assert sorted(_ids_de(todos)) == sorted([pago_de_contado, independiente])
    assert (
        next(item for item in todos["items"] if item["pago_id"] == independiente)["compra_id"]
        is None
    )


def test_listar_pagos_filtra_por_rango_de_fechas_inclusivo(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Listado de la semana": `desde` y `hasta` son inclusivos (TR-04)."""
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)
    antes = _pagar_en(cliente, headers, entorno, fecha="2026-01-09", importe="10000.00")
    primero = _pagar_en(cliente, headers, entorno, fecha="2026-01-10", importe="20000.00")
    ultimo = _pagar_en(cliente, headers, entorno, fecha="2026-01-12", importe="30000.00")
    despues = _pagar_en(cliente, headers, entorno, fecha="2026-01-13", importe="40000.00")

    cuerpo = cliente.get(
        URL_PAGOS,
        params={"desde": "2026-01-10", "hasta": "2026-01-12"},
        headers=headers,
    ).json()

    assert _ids_de(cuerpo) == [ultimo, primero]
    assert antes not in _ids_de(cuerpo)
    assert despues not in _ids_de(cuerpo)


def test_listar_pagos_con_el_rango_invertido_responde_422(
    cliente: TestClient, sesion: Session
) -> None:
    """`RangoDeFechasInvalidoError`: `desde` posterior a `hasta` es 422."""
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(
        URL_PAGOS, params={"desde": "2026-01-12", "hasta": "2026-01-10"}, headers=headers
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "RANGO_DE_FECHAS_INVALIDO"


def test_listar_pagos_pagina_por_cursor_sin_repetir_ni_omitir(
    cliente: TestClient, sesion: Session
) -> None:
    """Paginación por cursor con fechas repetidas: el desempate por `id` no pierde filas
    (índice `(organizacion_id, fecha DESC, id DESC)`, D12)."""
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)
    publicados = [
        _pagar_en(cliente, headers, entorno, fecha="2026-01-10", importe=f"{1000 + n}.00")
        for n in range(5)
    ]
    vistos: list[str] = []
    cursor: str | None = None

    for _ in range(5):
        params: dict[str, Any] = {"limite": 2}
        if cursor is not None:
            params["cursor"] = cursor
        pagina = cliente.get(URL_PAGOS, params=params, headers=headers).json()
        vistos.extend(_ids_de(pagina))
        cursor = pagina["cursor_siguiente"]
        if cursor is None:
            break

    assert cursor is None
    assert len(vistos) == 5
    assert sorted(vistos) == sorted(publicados)


@pytest.mark.parametrize("limite", [0, 201])
def test_listar_pagos_con_un_limite_fuera_de_rango_responde_422(
    cliente: TestClient, sesion: Session, limite: int
) -> None:
    """El límite va de 1 a 200; fuera de rango es 422, no un recorte silencioso."""
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)

    assert cliente.get(URL_PAGOS, params={"limite": limite}, headers=headers).status_code == 422
    assert cliente.get(URL_PAGOS, params={"limite": 200}, headers=headers).status_code == 200


def test_listar_pagos_con_un_cursor_ilegible_responde_422(
    cliente: TestClient, sesion: Session
) -> None:
    """`CursorInvalidoError`: un cursor que no se puede leer es 422."""
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_PAGOS, params={"cursor": "no-es-un-cursor"}, headers=headers)

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "CURSOR_INVALIDO"


@pytest.mark.parametrize(
    ("filtro", "valor"),
    [("estado", "BORRADA"), ("origen", "TRANSFERENCIA")],
)
def test_listar_pagos_con_un_filtro_desconocido_responde_422(
    cliente: TestClient, sesion: Session, filtro: str, valor: str
) -> None:
    """Los valores de `estado` y `origen` son cerrados: un valor desconocido no se ignora."""
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_PAGOS, params={filtro: valor}, headers=headers)

    assert respuesta.status_code == 422


def test_listar_pagos_sin_los_dos_permisos_responde_403(
    cliente: TestClient, sesion: Session
) -> None:
    """D7: leer pagos exige `REGISTRAR_PAGO_PROVEEDOR` o `ANULAR_PAGO_PROVEEDOR`; con
    `GESTIONAR_PROVEEDORES` solo no alcanza."""
    entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_PROVEEDORES"}))
    headers = entorno.entrar(cliente)

    assert cliente.get(URL_PAGOS, headers=headers).status_code == 403


def test_listar_pagos_sin_sesion_responde_401(cliente: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion, permisos=LECTOR)
    entorno.entrar(cliente)

    assert cliente.get(URL_PAGOS).status_code == 401


def test_inv21_el_listado_no_muestra_los_pagos_de_otra_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21: el listado filtra por `organizacion_id`, así que los pagos ajenos no
    aparecen ni se pueden filtrar."""
    ajena = Entorno(sesion, permisos=LECTOR, usuario="pagador2")
    headers_ajena = ajena.entrar(cliente)
    _pagar_en(cliente, headers_ajena, ajena, fecha="2026-01-05")

    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)
    mio = _pagar_en(cliente, headers, entorno, fecha="2026-01-06")

    cuerpo = cliente.get(URL_PAGOS, headers=headers).json()

    assert _ids_de(cuerpo) == [mio]
    filtrado = cliente.get(
        URL_PAGOS, params={"proveedor_id": str(ajena.proveedor_id)}, headers=headers
    ).json()
    assert filtrado["items"] == []


def test_el_detalle_muestra_medios_con_nombre_observacion_y_sin_anulacion(
    cliente: TestClient, sesion: Session
) -> None:
    """PAG-01, PAG-03: medios con importe y referencia, observación, y sin anulación
    mientras el pago esté `CONFIRMADA`."""
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)
    pago_id = _pagar_en(
        cliente,
        headers,
        entorno,
        fecha="2026-01-05",
        importe="52460.00",
        observacion="  Recibo 42  ",
    )
    sesion.execute(
        text(
            "INSERT INTO pago_proveedor_medio (id, organizacion_id, pago_id, medio_pago_id, "
            "importe, referencia) VALUES (:id, :o, :p, :m, :i, :r)"
        ),
        {
            "id": uuid4(),
            "o": entorno.org,
            "p": pago_id,
            "m": entorno.transferencia_id,
            "i": Decimal("52460.00"),
            "r": "0042",
        },
    )
    sesion.commit()

    respuesta = cliente.get(f"{URL_PAGOS}/{pago_id}", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["pago_id"] == pago_id
    assert cuerpo["fecha"] == "2026-01-05"
    assert cuerpo["proveedor_id"] == str(entorno.proveedor_id)
    assert cuerpo["proveedor_nombre"] == "Bodega Sur"
    assert cuerpo["importe"] == "52460.00"
    assert cuerpo["estado"] == "CONFIRMADA"
    assert cuerpo["origen"] == "INDEPENDIENTE"
    assert cuerpo["compra_id"] is None
    assert cuerpo["observacion"] == "Recibo 42"
    assert cuerpo["anulacion"] is None
    medios = {medio["medio_nombre"]: medio for medio in cuerpo["medios"]}
    assert set(medios) == {"Efectivo", "Transferencia"}
    assert medios["Transferencia"]["importe"] == "52460.00"
    assert medios["Transferencia"]["referencia"] == "0042"
    assert medios["Efectivo"]["referencia"] is None


def test_el_detalle_de_un_pago_de_compra_enlaza_con_su_compra(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Pago de una compra vigente": el detalle trae `compra_id` y el estado de
    la compra, que es lo que permite a la pantalla no ofrecer "Anular" (CMP-05, D2)."""
    # `REGISTRAR_COMPRA` solo para poder registrar la compra de contado: la LECTURA del pago
    # la abre `REGISTRAR_PAGO_PROVEEDOR` (`design.md` D7).
    entorno = Entorno(sesion, permisos=PAGADOR_Y_COMPRADOR)
    headers = entorno.entrar(cliente)
    compra_id, pago_id = _contado(cliente, sesion, headers, entorno)

    cuerpo = cliente.get(f"{URL_PAGOS}/{pago_id}", headers=headers).json()

    assert cuerpo["origen"] == "COMPRA"
    assert cuerpo["compra_id"] == compra_id
    assert cuerpo["compra_estado"] == "CONFIRMADA"


def test_el_detalle_de_un_pago_anulado_incluye_motivo_usuario_y_momento(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Anulación desde el detalle": el pago anulado muestra motivo, usuario y
    momento (PAG-03)."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    headers = entorno.entrar(cliente)
    pago_id = _pagar_en(cliente, headers, entorno, fecha="2026-01-05")
    motivo_id = _crear_motivo(sesion, entorno, "ANULACION_PAGO")
    sesion.execute(
        text("UPDATE motivo SET nombre = :n WHERE id = :i"),
        {"n": "Pago rechazado o devuelto", "i": motivo_id},
    )
    sesion.commit()
    cliente.post(
        f"{URL_PAGOS}/{pago_id}/anulacion",
        json={"motivo_id": str(motivo_id)},
        headers=_con_op(headers),
    )

    cuerpo = cliente.get(f"{URL_PAGOS}/{pago_id}", headers=headers).json()

    assert cuerpo["estado"] == "ANULADA"
    anulacion = cuerpo["anulacion"]
    assert anulacion["motivo_id"] == str(motivo_id)
    assert anulacion["motivo_nombre"] == "Pago rechazado o devuelto"
    assert anulacion["anulado_por_id"] is not None
    assert anulacion["anulado_por_nombre"] == "Persona de prueba"
    assert anulacion["anulado_en"] is not None
    # El movimiento original y el inverso conviven en el libro (CC-03, INV-05).
    tipos = (
        sesion.execute(
            text(
                "SELECT tipo FROM cuenta_movimiento WHERE organizacion_id = :o "
                "AND origen_tipo = 'ANULACION_PAGO' AND origen_id = :p"
            ),
            {"o": entorno.org, "p": pago_id},
        )
        .scalars()
        .all()
    )
    assert list(tipos) == ["ANULACION_PAGO"]


def test_el_detalle_nombra_a_quien_anulo_aunque_sea_otro_usuario_que_quien_pago(
    cliente: TestClient, sesion: Session
) -> None:
    """PAG-03: el detalle trae el NOMBRE de quien anuló, no solo su id; si anuló otra
    persona que la que registró el pago, es el nombre de la que anuló."""
    entorno = Entorno(sesion, permisos=PAGADOR)
    headers_pagador = entorno.entrar(cliente)
    pago_id = _pagar_en(cliente, headers_pagador, entorno, fecha="2026-01-05")
    motivo_id = _crear_motivo(sesion, entorno, "ANULACION_PAGO")
    headers_anulador = entorno.agregar_usuario(
        cliente, "anuladora", permisos=ANULADOR, nombre="Marta Anuladora"
    )
    anulacion = cliente.post(
        f"{URL_PAGOS}/{pago_id}/anulacion",
        json={"motivo_id": str(motivo_id)},
        headers=_con_op(headers_anulador),
    )
    assert anulacion.status_code == 200, anulacion.text

    cuerpo = cliente.get(f"{URL_PAGOS}/{pago_id}", headers=headers_anulador).json()

    assert cuerpo["anulacion"]["anulado_por_nombre"] == "Marta Anuladora"
    assert cuerpo["anulacion"]["anulado_por_nombre"] != "Persona de prueba"


def test_inv21_el_detalle_de_un_pago_de_otra_organizacion_responde_404(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21: un pago de otra organización es inexistente, 404 y no 403."""
    ajena = Entorno(sesion, permisos=LECTOR, usuario="pagador2")
    headers_ajena = ajena.entrar(cliente)
    pago_ajeno = _pagar_en(cliente, headers_ajena, ajena, fecha="2026-01-05")

    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)

    ajeno = cliente.get(f"{URL_PAGOS}/{pago_ajeno}", headers=headers)
    inexistente = cliente.get(f"{URL_PAGOS}/{uuid4()}", headers=headers)

    assert ajeno.status_code == 404
    assert inexistente.status_code == 404
    assert ajeno.json()["codigo"] == inexistente.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


def test_el_detalle_con_un_id_que_no_es_uuid_responde_422(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)

    assert cliente.get(f"{URL_PAGOS}/no-es-uuid", headers=headers).status_code == 422


# --- saldo del proveedor (change 12, tarea 6.2: D8; CC-04, INV-03, INV-21, SEG-06) ---------

URL_SALDO = "/api/v1/proveedores/{proveedor_id}/saldo"


def _saldo_de(cliente: TestClient, headers: dict[str, str], proveedor_id: UUID) -> str:
    respuesta = cliente.get(URL_SALDO.format(proveedor_id=proveedor_id), headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["saldo"]


def test_el_saldo_de_un_proveedor_con_deuda_llega_como_string(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Saldo de un proveedor con deuda" (D8, CC-04, INV-03): un usuario con
    SOLO `REGISTRAR_PAGO_PROVEEDOR` pide el saldo de un proveedor que debe
    `"153720.00"` y lo recibe como string, no como número."""
    entorno = Entorno(sesion, permisos=PAGADOR_Y_COMPRADOR)
    headers = entorno.entrar(cliente)
    entorno.dejar_deuda(cliente, headers, "153720.00")
    solo_pagador = entorno.agregar_usuario(
        cliente, "tesorero_solo_pago", permisos=frozenset({"REGISTRAR_PAGO_PROVEEDOR"})
    )

    respuesta = cliente.get(
        URL_SALDO.format(proveedor_id=entorno.proveedor_id), headers=solo_pagador
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["saldo"] == "153720.00"


def test_el_saldo_de_un_proveedor_sin_movimientos_es_cero(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Proveedor sin movimientos" (CC-04): `"0.00"`, no `null` ni `"0"`."""
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)

    assert _saldo_de(cliente, headers, entorno.proveedor_id) == "0.00"


def test_el_saldo_tras_registrar_un_pago_es_el_que_queda(
    cliente: TestClient, sesion: Session
) -> None:
    """Triangulación contra el libro: el saldo que se lee es el del comando, no un cálculo
    aparte. Deuda `"153720.00"`, pago de `"100000.00"` (PAG-02, CC-04) → `"53720.00"`,
    que es el mismo `saldo` que devolvió el 201 del pago."""
    entorno = Entorno(sesion, permisos=PAGADOR_Y_COMPRADOR)
    headers = entorno.entrar(cliente)
    entorno.dejar_deuda(cliente, headers, "153720.00")
    respuesta_pago = cliente.post(
        URL_PAGOS,
        json=entorno.cuerpo(
            fecha=entorno.hoy(),
            importe="100000.00",
            medios=[{"medio_pago_id": str(entorno.efectivo_id), "importe": "100000.00"}],
        ),
        headers=_con_op(headers),
    )
    assert respuesta_pago.status_code == 201, respuesta_pago.text

    assert _saldo_de(cliente, headers, entorno.proveedor_id) == "53720.00"
    assert respuesta_pago.json()["saldo"] == "53720.00"


def test_el_saldo_a_nuestro_favor_viene_con_signo_negativo(
    cliente: TestClient, sesion: Session
) -> None:
    """D3: un pago MAYOR que la deuda deja el saldo a favor de la organización, negativo y
    con signo (INV-03). Deuda `"153720.00"`, pago de `"160000.00"` → `"-6280.00"`."""
    entorno = Entorno(sesion, permisos=PAGADOR_Y_COMPRADOR)
    headers = entorno.entrar(cliente)
    entorno.dejar_deuda(cliente, headers, "153720.00")
    _pagar_en(cliente, headers, entorno, fecha=entorno.hoy(), importe="160000.00")

    assert _saldo_de(cliente, headers, entorno.proveedor_id) == "-6280.00"


@pytest.mark.parametrize(
    ("permisos", "esperado"),
    [
        (frozenset({"GESTIONAR_PROVEEDORES"}), 200),
        (frozenset({"REGISTRAR_PAGO_PROVEEDOR"}), 200),
        (frozenset({"REGISTRAR_COMPRA"}), 200),
        (frozenset({"ANULAR_PAGO_PROVEEDOR"}), 403),
        (frozenset({"ANULAR_COMPRA"}), 403),
        (frozenset({"GESTIONAR_CATALOGO"}), 403),
    ],
)
def test_el_saldo_se_pide_con_los_tres_permisos_de_pagar_y_no_con_cualesquiera_otro(
    cliente: TestClient, sesion: Session, permisos: frozenset[str], esperado: int
) -> None:
    """D8: `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `REGISTRAR_COMPRA` abren la
    lectura del saldo; ningún otro permiso la abre (SEG-06, `01` §19). Los tres permisos
    por separado, y tres permisos que de otro modo sirven para otra cosa, en ambos
    sentidos."""
    entorno = Entorno(sesion, permisos=permisos)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_SALDO.format(proveedor_id=entorno.proveedor_id), headers=headers)

    assert respuesta.status_code == esperado


def test_inv21_el_saldo_de_un_proveedor_de_otra_organizacion_responde_404(
    cliente: TestClient, sesion: Session
) -> None:
    """INV-21, SEG-07: el proveedor ajeno es inexistente; el mismo código y el mismo 404
    que un id que no existe, y la respuesta no revela el saldo de la otra organización."""
    ajena = Entorno(sesion, permisos=PAGADOR_Y_COMPRADOR, usuario="pagadora_ajena")
    ajena.dejar_deuda(cliente, ajena.entrar(cliente), "999999.00")

    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)

    ajeno = cliente.get(URL_SALDO.format(proveedor_id=ajena.proveedor_id), headers=headers)
    inexistente = cliente.get(URL_SALDO.format(proveedor_id=uuid4()), headers=headers)

    assert ajeno.status_code == 404
    assert inexistente.status_code == 404
    assert ajeno.json()["codigo"] == inexistente.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert "999999" not in ajeno.text


# --- selector de proveedores (change 12, tarea 6.3: D7; SEG-06) ------------------------

URL_OPCIONES = "/api/v1/proveedores/opciones"


@pytest.mark.parametrize(
    ("permisos", "esperado"),
    [
        # Los permisos anteriores: el selector que ya consumía el alta de producto y el de
        # compra (`01` §19, `design.md` D7 opción A).
        (frozenset({"GESTIONAR_CATALOGO"}), 200),
        (frozenset({"REGISTRAR_COMPRA"}), 200),
        # El nuevo de D7: elegir proveedor es parte de registrar el pago.
        (frozenset({"REGISTRAR_PAGO_PROVEEDOR"}), 200),
        # Y los que no alcanzan: anular un pago no es elegir al proveedor.
        (frozenset({"ANULAR_PAGO_PROVEEDOR"}), 403),
        (frozenset({"ANULAR_COMPRA"}), 403),
    ],
)
def test_el_selector_de_proveedores_responde_con_el_permiso_de_registrar_el_pago(
    cliente: TestClient, sesion: Session, permisos: frozenset[str], esperado: int
) -> None:
    """D7: `GET /proveedores/opciones` SUMA `REGISTRAR_PAGO_PROVEEDOR` y no deja de
    responder para los permisos que ya loaban. Es la lectura de apoyo del alta de pago: el
    rol "Tesorería" con solo ese permiso tiene que poder elegir al proveedor (INV-21 sigue
    filtrando por la organización del token)."""
    entorno = Entorno(sesion, permisos=permisos)
    headers = entorno.entrar(cliente)

    respuesta = cliente.get(URL_OPCIONES, headers=headers)

    assert respuesta.status_code == esperado


def test_leer_el_selector_de_proveedores_no_abre_la_edicion_de_proveedores(
    cliente: TestClient, sesion: Session
) -> None:
    """Corolario de D7: el selector abre SOLO su lectura. Con solo
    `REGISTRAR_PAGO_PROVEEDOR` se elige al proveedor del pago, pero crear o modificar
    proveedores sigue exigiendo `GESTIONAR_PROVEEDORES` (SEG-06)."""
    entorno = Entorno(sesion, permisos=LECTOR)
    headers = entorno.entrar(cliente)

    assert cliente.get(URL_OPCIONES, headers=headers).status_code == 200
    crear = cliente.post(
        "/api/v1/proveedores",
        json={"nombre": "Bodega Pirata"},
        headers={**headers, "Operation-Id": str(uuid4())},
    )
    modificar = cliente.put(
        f"/api/v1/proveedores/{entorno.proveedor_id}",
        json={"nombre": "Bodega Secuestrada", "activo": True},
        headers={**headers, "Operation-Id": str(uuid4())},
    )

    assert crear.status_code == 403
    assert modificar.status_code == 403
    # Y la ficha del proveedor tampoco se abre con este permiso.
    ficha = cliente.get(f"/api/v1/proveedores/{entorno.proveedor_id}", headers=headers)
    assert ficha.status_code == 403


def test_con_solo_anular_pago_proveedor_se_lista_y_se_abre_el_detalle(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Lectura con solo el permiso de anular" (D7, `01` §19): un usuario con
    `ANULAR_PAGO_PROVEEDOR` y sin `REGISTRAR_PAGO_PROVEEDOR` lee el listado y el detalle
    de un pago que registró otro usuario."""
    entorno = Entorno(sesion, permisos=PAGADOR)
    headers = entorno.entrar(cliente)
    pago_id = _pagar_en(cliente, headers, entorno, fecha="2026-01-05", importe="52460.00")
    solo_anulador = entorno.agregar_usuario(
        cliente, "anulador_sin_registrar", permisos=frozenset({"ANULAR_PAGO_PROVEEDOR"})
    )

    listado = cliente.get(URL_PAGOS, headers=solo_anulador)
    detalle = cliente.get(f"{URL_PAGOS}/{pago_id}", headers=solo_anulador)

    assert listado.status_code == 200, listado.text
    assert _ids_de(listado.json()) == [pago_id]
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["importe"] == "52460.00"
    # Y sigue sin poder registrar: el permiso de anular no abre la escritura (SEG-06).
    registrar = cliente.post(
        URL_PAGOS,
        json=entorno.cuerpo(
            importe="1.00", medios=[{"medio_pago_id": str(entorno.efectivo_id), "importe": "1.00"}]
        ),
        headers=_con_op(solo_anulador),
    )
    assert registrar.status_code == 403
