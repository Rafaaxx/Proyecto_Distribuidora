"""Utilidades de las pruebas de lectura de `ventas` (change 18a, grupo 9).

Un segundo (o tercer) usuario de la MISMA organización con otros permisos, que inicia sesión por
HTTP, y el sembrado por SQL de ventas con rasgos concretos (fecha, usuario, ubicación, jornada).
Es un módulo y no un `conftest.py` porque `tests/integration` no es un paquete.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_api import PASSWORD, Sesion
from ventas_utiles import VentaSembrada, sembrar_venta_sql

from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.modules.identidad import repository as identidad_repository

MOMENTO = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def otro_usuario(sesion: Session, s: Sesion, usuario: str, permisos: frozenset[str]) -> UUID:
    """Un usuario de la organización de `s` con exactamente esos permisos."""
    rol = identidad_repository.crear_rol(
        s.entorno.org,
        sesion,
        rol_id=nuevo_id(),
        nombre=f"Rol {usuario}",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    for codigo in sorted(permisos):
        identidad_repository.asignar_permiso_a_rol(
            s.entorno.org, sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    creado = identidad_repository.crear_usuario(
        s.entorno.org,
        sesion,
        usuario_id=nuevo_id(),
        usuario=usuario,
        nombre=f"Persona {usuario}",
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    sesion.commit()
    return creado.id


def entrar_como(cliente_http: TestClient, s: Sesion, usuario: str) -> dict[str, str]:
    slug = s.sesion.execute(
        text("SELECT slug FROM organizacion WHERE id = :o"), {"o": s.entorno.org}
    ).scalar_one()
    respuesta = cliente_http.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": slug,
            "usuario": usuario,
            "contrasena": PASSWORD,
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "Teléfono",
        },
    )
    assert respuesta.status_code == 200
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def usuario_con(
    cliente_http: TestClient, sesion: Session, s: Sesion, permisos: frozenset[str]
) -> dict[str, str]:
    """Encabezados de un usuario nuevo de la organización de `s` con esos permisos."""
    nombre = f"u{uuid4().hex[:8]}"
    otro_usuario(sesion, s, nombre, permisos)
    return entrar_como(cliente_http, s, nombre)


def sembrar(
    sesion: Session, s: Sesion, *, usuario_id: UUID | None = None, **cambios: object
) -> VentaSembrada:
    """Una venta de la organización de `s` escrita por SQL (con su línea)."""
    venta = sembrar_venta_sql(
        sesion,
        s.entorno.org,
        cliente_id=cambios.pop("cliente_id", s.entorno.cliente_id),  # type: ignore[arg-type]
        usuario_id=usuario_id or s.entorno.usuario_id,
        dispositivo_id=s.entorno.dispositivo_id,
        **cambios,
    )
    sesion.commit()
    return venta
