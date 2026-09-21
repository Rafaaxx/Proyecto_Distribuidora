"""Grupo 11, tarea 11.2: "Los intentos fallidos se cuentan de forma
uniforme entre procesos" (`ADR-018`, `02` §16.2 -- varios workers de
FastAPI).

Prueba de concurrencia real (no un mock): abre conexiones/sesiones
INDEPENDIENTES contra la misma base -- cada una simula un worker distinto
-- confirma sus propias transacciones (no usa `db_session`, que revierte al
final) y verifica, desde una tercera conexión también independiente, que el
conteo ve el total repartido entre todas, sin importar cuál lo escribió.
Limpieza explícita (`conftest.py` documenta esta convención para pruebas que
confirman contra `database_url`).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.modules.identidad import repository
from app.modules.identidad.models import Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
        conexion.execute(text("TRUNCATE TABLE intento_login"))
    engine.dispose()


def _sesion_independiente(database_url: str) -> Session:
    """Una conexión/sesión nueva, propia, que confirma sus propias
    transacciones -- simula un worker de FastAPI distinto (`02` §16.2)."""
    factory = crear_session_factory(crear_engine(database_url))
    return factory()


def _crear_usuario(sesion: Session, organizacion_id) -> object:
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Vendedor",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    usuario = repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario="vendedor1",
        nombre="Persona de prueba",
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    sesion.commit()
    return usuario


def test_los_intentos_fallidos_se_cuentan_igual_repartidos_entre_conexiones(
    database_url: str, _engine_de_sesion
) -> None:
    """Escenario "Los intentos fallidos se cuentan de forma uniforme entre
    procesos": 12 intentos fallidos, repartidos entre 3 conexiones/hilos
    independientes (4 cada una, simulando 3 workers distintos), deben
    contarse como 12 desde una CUARTA conexión, también independiente --
    ninguna cuenta solo lo que escribió ella misma."""
    sesion_setup = _sesion_independiente(database_url)
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba",
        slug="org-concurrencia-1",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
        actualizado_por_id=None,
    )
    sesion_setup.add(organizacion)
    sesion_setup.flush()
    usuario = _crear_usuario(sesion_setup, organizacion.id)
    sesion_setup.close()

    def _worker(indice_worker: int) -> None:
        sesion_worker = _sesion_independiente(database_url)
        for _ in range(4):
            repository.registrar_intento_login(
                sesion_worker,
                intento_id=nuevo_id(),
                usuario_id=usuario.id,
                ip="10.0.0.1",
                exito=False,
                momento=MOMENTO,
            )
            sesion_worker.commit()
        sesion_worker.close()

    hilos = [threading.Thread(target=_worker, args=(i,)) for i in range(3)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    sesion_verificacion = _sesion_independiente(database_url)
    try:
        total_por_usuario = repository.contar_intentos_fallidos_por_usuario(
            sesion_verificacion, usuario_id=usuario.id, desde=MOMENTO - timedelta(minutes=15)
        )
        total_por_ip = repository.contar_intentos_fallidos_por_ip(
            sesion_verificacion, ip="10.0.0.1", desde=MOMENTO - timedelta(minutes=15)
        )
    finally:
        sesion_verificacion.close()

    assert total_por_usuario == 12
    assert total_por_ip == 12


def test_el_limite_se_alcanza_con_la_misma_cantidad_total_repartido_entre_conexiones(
    database_url: str, _engine_de_sesion
) -> None:
    """Triangulación: exactamente el umbral (5 por usuario), repartido en
    2+3 entre dos conexiones distintas, deja al usuario bloqueado igual que
    si los 5 vinieran de una sola conexión (11.2)."""
    from app.core.clock import FixedClock
    from app.modules.identidad import service as identidad_service
    from app.modules.identidad.domain.usuarios import LoginBloqueadoPorIntentosError

    sesion_setup = _sesion_independiente(database_url)
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba",
        slug="org-concurrencia-2",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
        actualizado_por_id=None,
    )
    sesion_setup.add(organizacion)
    sesion_setup.flush()
    usuario = _crear_usuario(sesion_setup, organizacion.id)
    sesion_setup.close()

    sesion_conexion_a = _sesion_independiente(database_url)
    for _ in range(2):
        repository.registrar_intento_login(
            sesion_conexion_a,
            intento_id=nuevo_id(),
            usuario_id=usuario.id,
            ip="10.0.0.2",
            exito=False,
            momento=MOMENTO,
        )
        sesion_conexion_a.commit()
    sesion_conexion_a.close()

    sesion_conexion_b = _sesion_independiente(database_url)
    for _ in range(3):
        repository.registrar_intento_login(
            sesion_conexion_b,
            intento_id=nuevo_id(),
            usuario_id=usuario.id,
            ip="10.0.0.2",
            exito=False,
            momento=MOMENTO,
        )
        sesion_conexion_b.commit()
    sesion_conexion_b.close()

    sesion_login = _sesion_independiente(database_url)
    try:
        with pytest.raises(LoginBloqueadoPorIntentosError):
            identidad_service.iniciar_sesion(
                sesion_login,
                FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                dispositivo_id=nuevo_id(),
                nombre_dispositivo="Tablet",
                jwt_secreto="secreto-de-prueba",
                jwt_kid="1",
                ip="10.0.0.2",
            )
    finally:
        sesion_login.rollback()
        sesion_login.close()
