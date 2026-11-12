"""Utilidades de las pruebas HTTP de la configuración de la organización (change 18b, grupo 5):
una organización con un usuario con los permisos dados y el login real contra la API (nunca un
access token fabricado). Es un módulo y no un `conftest.py` por el mismo motivo que
`stock_utiles`: `tests/integration` no es un paquete."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from cuentas_corrientes_utiles import crear_organizacion
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.modules.identidad import repository as identidad_repository

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-configuracion-18b"


def como_la_organizacion_sembrada(sesion: Session, organizacion_id: UUID) -> None:
    """La configuración de una organización sembrada (`app/seed.py`): descuento manual
    habilitado con el motivo sin definir y política de crédito `AUTORIZAR` sin tolerancia."""
    sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET descuento_manual_habilitado = true, "
            "motivo_obligatorio_descuento = NULL, politica_credito_default = 'AUTORIZAR', "
            "tolerancia_offline_tipo = NULL, tolerancia_offline_valor = NULL "
            "WHERE organizacion_id = :o"
        ),
        {"o": organizacion_id},
    )


class EntornoHttp:
    """Una organización con un usuario con `permisos`."""

    def __init__(
        self, sesion: Session, *, permisos: frozenset[str], usuario: str = "usuario1"
    ) -> None:
        self.sesion = sesion
        organizacion = crear_organizacion(sesion)
        self.org = organizacion.id
        como_la_organizacion_sembrada(sesion, self.org)
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
        self.usuario_id = nuevo_id()
        identidad_repository.crear_usuario(
            self.org,
            sesion,
            usuario_id=self.usuario_id,
            usuario=usuario,
            nombre="Persona de prueba",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )

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

    def configuracion(self) -> dict[str, object]:
        """La fila de `configuracion_organizacion` tal como está en la base."""
        self.sesion.expire_all()
        fila = (
            self.sesion.execute(
                text("SELECT * FROM configuracion_organizacion WHERE organizacion_id = :o"),
                {"o": self.org},
            )
            .mappings()
            .one()
        )
        return dict(fila)

    def auditorias(self, accion: str) -> list[dict[str, object]]:
        """Las filas de auditoría de la ESCRITURA (entidad `configuracion_organizacion`), no la
        fila genérica que el bus deja por cada comando."""
        self.sesion.expire_all()
        return [
            dict(fila)
            for fila in self.sesion.execute(
                text(
                    "SELECT * FROM auditoria WHERE organizacion_id = :o AND accion = :a "
                    "AND entidad = 'configuracion_organizacion'"
                ),
                {"o": self.org, "a": accion},
            ).mappings()
        ]


def con_operation_id(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}
