"""Change 17, tareas 12.2 y 12.3: el camino `OFFLINE` de punta a punta por HTTP, con login real,
renovación de sesión y `COBRANZA_REGISTRAR` real (no un tipo de prueba).

- Un vendedor `INACTIVO` (o con su rol inactivo) con su jornada `ABIERTA` en el dispositivo renueva
  su sesión por la excepción de ADR-049 punto 18 y sincroniza su cola: la cobranza `OFFLINE` se
  acepta con `PERMISO_REVOCADO` (motivo `USUARIO_INACTIVO` o `ROL_INACTIVO`), el saldo del cliente
  baja y la observación queda sobre la cobranza. Un comando `ONLINE` del mismo lote se rechaza y el
  lote sigue.
- `COBRANZA_ANULAR` (solo `ONLINE`) enviado en modo `OFFLINE` por el lote no se admite.

Reglas citadas: SYN-05, SYN-09, SYN-10, SEG-06, INV-17 y ADR-028 (D9.3-B, D9.4-A), ADR-049 punto 18.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_cliente
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

from app.api_v1 import sistema
from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.identidad import repository
from app.modules.identidad.models import Organizacion, Usuario
from app.modules.sync.models import Observacion

MOMENTO = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
PASSWORD = "una-contrasena-larga-de-prueba-offline-123"
JWT_SECRET = "secreto-de-prueba-permiso-revocado"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    """Estas pruebas confirman transacciones reales: limpian explícitamente al terminar."""
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


class Vendedor:
    """Un vendedor con `REGISTRAR_COBRANZA`, ya logueado en su dispositivo, con su jornada
    `ABIERTA` y un cliente con saldo `150000.00`."""

    def __init__(self, cliente: TestClient, sesion: Session) -> None:
        self.http = cliente
        self.sesion = sesion
        organizacion = Organizacion(
            id=nuevo_id(),
            nombre="Organización de prueba",
            slug=f"org-offline-{uuid4().hex[:8]}",
            cuit=None,
            moneda="ARS",
            zona_horaria="America/Argentina/Mendoza",
            estado="ACTIVA",
            creado_en=MOMENTO,
            actualizado_en=MOMENTO,
            actualizado_por_id=None,
        )
        sesion.add(organizacion)
        sesion.flush()
        self.org = organizacion.id
        self.slug = organizacion.slug
        rol = repository.crear_rol(
            self.org,
            sesion,
            rol_id=nuevo_id(),
            nombre="Vendedor",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO,
        )
        self.rol_id = rol.id
        repository.asignar_permiso_a_rol(
            self.org, sesion, rol_id=rol.id, permiso_codigo="REGISTRAR_COBRANZA"
        )
        usuario: Usuario = repository.crear_usuario(
            self.org,
            sesion,
            usuario_id=nuevo_id(),
            usuario=f"vendedor-{uuid4().hex[:8]}",
            nombre="Persona de prueba",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )
        self.usuario_id = usuario.id
        self.nombre_usuario = usuario.usuario
        self.cliente_id = crear_cliente(sesion, self.org, nombre="Kiosco La Esquina")
        self.medio_id = uuid4()
        sesion.execute(
            text(
                "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, "
                "activo, creado_en, actualizado_en) "
                "VALUES (:id, :org, 'Efectivo', false, true, :m, :m)"
            ),
            {"id": self.medio_id, "org": self.org, "m": MOMENTO},
        )
        sesion.commit()
        self.dispositivo_id = uuid4()
        respuesta = cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": self.nombre_usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(self.dispositivo_id),
                "nombre_dispositivo": "Teléfono",
            },
        )
        assert respuesta.status_code == 200
        self.cookie = respuesta.cookies["refresh_token"]
        cuentas_service.registrar_saldo_inicial(
            self.org,
            sesion,
            RELOJ,
            cuenta_tipo="CLIENTE",
            entidad_id=self.cliente_id,
            importe="150000.00",
            sentido="AUMENTA",
            occurred_at=MOMENTO,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
        )
        self.jornada_id = crear_jornada_sql(
            sesion,
            self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            ubicacion_id=crear_ubicacion_sql(sesion, self.org, requiere_toma=True),
        )
        sesion.commit()

    def inactivar_usuario(self) -> None:
        self.sesion.execute(
            text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :id"), {"id": self.usuario_id}
        )
        self.sesion.commit()

    def inactivar_rol(self) -> None:
        self.sesion.execute(
            text("UPDATE rol SET activo = false WHERE id = :id"), {"id": self.rol_id}
        )
        self.sesion.commit()

    def renovar(self) -> dict[str, str]:
        """Renueva la sesión (la excepción de jornada no cerrada) y devuelve la cabecera."""
        respuesta = self.http.post(
            "/api/v1/auth/refresh",
            json={"dispositivo_id": str(self.dispositivo_id)},
            cookies={"refresh_token": self.cookie},
        )
        assert respuesta.status_code == 200
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}

    def item(
        self, *, secuencia: int, modo: str, tipo: str = "COBRANZA_REGISTRAR", contenido=None
    ) -> dict[str, object]:
        return {
            "operation_id": str(uuid4()),
            "tipo": tipo,
            "version": 1,
            "modo": modo,
            "usuario_id": str(self.usuario_id),
            "dispositivo_id": str(self.dispositivo_id),
            "occurred_at": MOMENTO.isoformat(),
            "secuencia": secuencia,
            "app_version": "1.0.0",
            "jornada_id": str(self.jornada_id),
            "contenido": contenido
            if contenido is not None
            else {
                "cobranza_id": str(uuid4()),
                "cliente_id": str(self.cliente_id),
                "importe": "50000.00",
                "medios": [
                    {"medio_pago_id": str(self.medio_id), "importe": "50000.00", "referencia": None}
                ],
            },
        }

    def sincronizar(
        self, cabecera: dict[str, str], *items: dict[str, object]
    ) -> dict[str, dict[str, object]]:
        respuesta = self.http.post(
            "/api/v1/sync/comandos", json={"items": list(items)}, headers=cabecera
        )
        assert respuesta.status_code == 200
        return {r["operation_id"]: r for r in respuesta.json()["resultados"]}

    def saldo(self) -> Decimal:
        self.sesion.expire_all()
        return cuentas_service.obtener_saldo(
            self.org, self.sesion, cuenta_tipo="CLIENTE", entidad_id=self.cliente_id
        )

    def observaciones(self) -> list[Observacion]:
        self.sesion.expire_all()
        return list(
            self.sesion.scalars(
                select(Observacion).where(Observacion.organizacion_id == self.org)
            ).all()
        )


@pytest.fixture
def vendedor(cliente: TestClient, sesion: Session) -> Vendedor:
    return Vendedor(cliente, sesion)


def test_adr028_cobranza_offline_de_un_usuario_dado_de_baja_se_acepta_con_permiso_revocado(
    vendedor: Vendedor,
) -> None:
    """Escenario "Cobranza offline de un usuario dado de baja": renueva por la excepción de
    jornada, envía el lote, la cobranza se acepta con `PERMISO_REVOCADO` (motivo
    `USUARIO_INACTIVO`) y el saldo baja `50000.00`. El comando `ONLINE` del mismo lote se rechaza
    y no impide el resto."""
    vendedor.inactivar_usuario()
    cabecera = vendedor.renovar()
    sin_conexion = vendedor.item(secuencia=1, modo="OFFLINE")
    con_conexion = vendedor.item(secuencia=2, modo="ONLINE")

    resultados = vendedor.sincronizar(cabecera, sin_conexion, con_conexion)

    aceptada = resultados[sin_conexion["operation_id"]]
    assert aceptada["estado"] == "ACEPTADO_CON_OBSERVACIONES"
    assert aceptada["resultado"]["importe"] == "50000.00"
    assert aceptada["resultado"]["saldo"] == "100000.00"
    rechazada = resultados[con_conexion["operation_id"]]
    assert (rechazada["estado"], rechazada["error_codigo"]) == (
        "RECHAZADO",
        "PERMISO_REQUERIDO",
    )
    assert vendedor.saldo() == Decimal("100000.00")
    (observacion,) = vendedor.observaciones()
    assert observacion.codigo == "PERMISO_REVOCADO"
    assert observacion.detalle == {"permiso": "REGISTRAR_COBRANZA", "motivo": "USUARIO_INACTIVO"}
    assert observacion.operacion_tipo == "COBRANZA"
    assert str(observacion.operacion_id) == aceptada["resultado"]["cobranza_id"]


def test_adr028_cobranza_offline_con_el_rol_inactivo_queda_con_rol_inactivo(
    vendedor: Vendedor,
) -> None:
    """Escenario "Un rol desactivado" (D9.4-A) de punta a punta."""
    vendedor.inactivar_rol()
    cabecera = vendedor.renovar()
    item = vendedor.item(secuencia=1, modo="OFFLINE")

    resultados = vendedor.sincronizar(cabecera, item)

    assert resultados[item["operation_id"]]["estado"] == "ACEPTADO_CON_OBSERVACIONES"
    assert vendedor.saldo() == Decimal("100000.00")
    (observacion,) = vendedor.observaciones()
    assert observacion.detalle == {"permiso": "REGISTRAR_COBRANZA", "motivo": "ROL_INACTIVO"}


def test_un_vendedor_activo_con_el_permiso_sincroniza_sin_observacion(vendedor: Vendedor) -> None:
    """Escenario "Con el permiso no hay observación" con el tipo real."""
    cabecera = vendedor.renovar()
    item = vendedor.item(secuencia=1, modo="OFFLINE")

    resultados = vendedor.sincronizar(cabecera, item)

    assert resultados[item["operation_id"]]["estado"] == "ACEPTADO"
    assert vendedor.saldo() == Decimal("100000.00")
    assert vendedor.observaciones() == []


def test_un_tipo_solo_online_enviado_offline_por_el_lote_no_se_admite(vendedor: Vendedor) -> None:
    """Pipeline de comandos, modo: `COBRANZA_ANULAR` es solo `ONLINE`; el modo `OFFLINE` por el lote
    se rechaza y el catálogo no se toca (D10)."""
    cabecera = vendedor.renovar()
    item = vendedor.item(
        secuencia=1,
        modo="OFFLINE",
        tipo="COBRANZA_ANULAR",
        contenido={"cobranza_id": str(uuid4()), "motivo_id": str(uuid4())},
    )

    resultados = vendedor.sincronizar(cabecera, item)

    resultado = resultados[item["operation_id"]]
    assert (resultado["estado"], resultado["error_codigo"]) == (
        "RECHAZADO",
        "MODO_NO_ADMITIDO_PARA_TIPO",
    )


def test_la_cobranza_se_acepta_por_el_lote_y_no_por_rest_en_modo_offline(
    vendedor: Vendedor,
) -> None:
    """Escenario de modo de `pipeline-de-comandos`: el modo `OFFLINE` solo entra por el lote; el
    endpoint REST no lo admite (ADR-012, `02` §6.2)."""
    from app.commands.sobre import ModoNoAdmitidoPorRestError, construir_sobre_online

    with pytest.raises(ModoNoAdmitidoPorRestError):
        construir_sobre_online(
            operation_id=uuid4(),
            tipo="COBRANZA_REGISTRAR",
            version=1,
            modo="OFFLINE",
            organizacion_id=vendedor.org,
            usuario_id=vendedor.usuario_id,
            dispositivo_id=vendedor.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido={},
        )
    cabecera = vendedor.renovar()
    item = vendedor.item(secuencia=1, modo="OFFLINE")
    assert vendedor.sincronizar(cabecera, item)[item["operation_id"]]["estado"] == "ACEPTADO"


def test_el_uuid_de_la_cobranza_de_la_observacion_es_un_uuid(vendedor: Vendedor) -> None:
    """Triangulación del ancla: la operación observada es una cobranza existente."""
    vendedor.inactivar_usuario()
    cabecera = vendedor.renovar()
    item = vendedor.item(secuencia=1, modo="OFFLINE")
    vendedor.sincronizar(cabecera, item)

    (observacion,) = vendedor.observaciones()

    assert isinstance(observacion.operacion_id, UUID)
    existe = vendedor.sesion.scalar(
        text("SELECT count(*) FROM cobranza WHERE organizacion_id = :o AND id = :c"),
        {"o": vendedor.org, "c": observacion.operacion_id},
    )
    assert existe == 1
