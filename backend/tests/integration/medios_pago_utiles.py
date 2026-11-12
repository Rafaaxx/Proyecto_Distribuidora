"""Entorno compartido de las pruebas de medios de pago administrables (change 17b): una
organización con un administrador (`ADMIN_CONFIGURACION`), un usuario que cobra y paga y uno
sin permisos de nada, los medios de la siembra del 17b (Transferencia, Cheque y Tarjeta piden
referencia) y un cliente y un proveedor para ejercitar cobranzas y pagos con conexión.

Mismo arnés HTTP que `test_cobranzas_api.py`: PostgreSQL real, motor propio de la aplicación y
`login` real. Las fixtures `cliente_http`, `sesion` y `_limpiar_datos_confirmados` se importan
en cada archivo de prueba."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from cuentas_corrientes_utiles import crear_cliente, crear_organizacion, crear_proveedor
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository as identidad_repository

MOMENTO = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-medios-pago"
URL_MEDIOS = "/api/v1/configuracion/medios-pago"
URL_COBRANZAS = "/api/v1/cobranzas"
URL_PAGOS = "/api/v1/pagos-proveedores"

ADMIN = frozenset({"ADMIN_CONFIGURACION"})
COBRADOR_Y_PAGADOR = frozenset({"REGISTRAR_COBRANZA", "REGISTRAR_PAGO_PROVEEDOR"})
SIN_PERMISOS: frozenset[str] = frozenset()


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


def con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


class Entorno:
    """Una organización con administrador, cobrador-pagador y un usuario sin permisos."""

    def __init__(self, sesion: Session, *, con_medios: bool = True) -> None:
        self.sesion = sesion
        organizacion = crear_organizacion(sesion)
        self.org = organizacion.id
        self.slug = organizacion.slug
        self.usuarios: dict[str, UUID] = {}
        self.agregar_usuario("admin1", ADMIN)
        self.agregar_usuario("cobrador1", COBRADOR_Y_PAGADOR)
        self.agregar_usuario("nadie1", SIN_PERMISOS)
        self.cliente_id = crear_cliente(sesion, self.org, nombre="Kiosco La Esquina")
        self.proveedor_id = crear_proveedor(sesion, self.org, nombre="Bodega Sur")
        self.medios: dict[str, UUID] = {}
        if con_medios:
            for nombre, referencia in (
                ("Efectivo", False),
                ("Transferencia", True),
                ("Cheque", True),
                ("Billetera", False),
                ("Tarjeta", True),
            ):
                self.medios[nombre] = self.crear_medio(nombre, requiere_referencia=referencia)

    def agregar_usuario(self, nombre_usuario: str, permisos: frozenset[str]) -> UUID:
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
        usuario_id = identidad_repository.crear_usuario(
            self.org,
            self.sesion,
            usuario_id=nuevo_id(),
            usuario=nombre_usuario,
            nombre=nombre_usuario,
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        ).id
        self.usuarios[nombre_usuario] = usuario_id
        return usuario_id

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

    def entrar(self, cliente_http: TestClient, usuario: str = "admin1") -> dict[str, str]:
        self.sesion.commit()
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 200
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}

    def dar_de_baja_en_sql(self, *nombres: str) -> None:
        for nombre in nombres:
            self.sesion.execute(
                text("UPDATE medio_pago SET activo = false WHERE id = :i"),
                {"i": self.medios[nombre]},
            )
        self.sesion.commit()

    # --- cuerpos de cobranza y de pago ----------------------------------------------

    def cuerpo_cobranza(self, medio: str, referencia: str | None = None) -> dict[str, Any]:
        linea: dict[str, Any] = {"medio_pago_id": str(self.medios[medio]), "importe": "20000.00"}
        if referencia is not None:
            linea["referencia"] = referencia
        return {
            "cobranza_id": str(uuid4()),
            "cliente_id": str(self.cliente_id),
            "importe": "20000.00",
            "medios": [linea],
        }

    def cuerpo_pago(self, medio: str, referencia: str | None = None) -> dict[str, Any]:
        linea: dict[str, Any] = {"medio_pago_id": str(self.medios[medio]), "importe": "20000.00"}
        if referencia is not None:
            linea["referencia"] = referencia
        return {
            "proveedor_id": str(self.proveedor_id),
            "fecha": datetime.now(ZoneInfo("America/Argentina/Mendoza")).date().isoformat(),
            "importe": "20000.00",
            "medios": [linea],
        }

    # --- lectura de la base ---------------------------------------------------------

    def filas_de_medio(self) -> list[dict[str, Any]]:
        self.sesion.rollback()
        filas = self.sesion.execute(
            text(
                "SELECT id, nombre, requiere_referencia, activo FROM medio_pago "
                "WHERE organizacion_id = :o ORDER BY nombre"
            ),
            {"o": self.org},
        ).mappings()
        return [dict(fila) for fila in filas]

    def auditoria_de(self, accion: str, entidad: str = "medio_pago") -> list[dict[str, Any]]:
        """Filas de auditoría de la entidad (por omisión la propia del medio; la fila genérica
        del bus es `entidad = 'comando'`)."""
        self.sesion.rollback()
        filas = self.sesion.execute(
            text(
                "SELECT accion, entidad, entidad_id, antes, despues, usuario_id, operation_id, "
                "origen FROM auditoria WHERE organizacion_id = :o AND accion = :a AND entidad = :e "
                "ORDER BY registered_at"
            ),
            {"o": self.org, "a": accion, "e": entidad},
        ).mappings()
        return [dict(fila) for fila in filas]

    def contar_comandos(self, tipo: str) -> int:
        self.sesion.rollback()
        return int(
            self.sesion.execute(
                text("SELECT count(*) FROM comando WHERE organizacion_id = :o AND tipo = :t"),
                {"o": self.org, "t": tipo},
            ).scalar_one()
        )
