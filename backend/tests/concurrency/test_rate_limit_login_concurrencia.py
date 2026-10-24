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
from app.modules.identidad.domain.clave_intento import clave_de_intento_login
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
                clave_intento=clave_de_intento_login(organizacion.slug, usuario.usuario),
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
        total_por_usuario = repository.contar_fallos_de_login_en_ventana(
            sesion_verificacion,
            clave_intento=clave_de_intento_login(organizacion.slug, usuario.usuario),
            desde_exclusivo=MOMENTO - timedelta(minutes=15),
            hasta_inclusivo=MOMENTO,
        )
        total_por_ip = repository.contar_fallos_de_login_en_ventana(
            sesion_verificacion,
            ip="10.0.0.1",
            desde_exclusivo=MOMENTO - timedelta(minutes=15),
            hasta_inclusivo=MOMENTO,
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
            clave_intento=clave_de_intento_login(organizacion.slug, usuario.usuario),
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
            clave_intento=clave_de_intento_login(organizacion.slug, usuario.usuario),
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


@pytest.mark.parametrize(
    "nombre_escrito", ["vendedor1", "fantasma"], ids=["usuario_real", "par_inexistente"]
)
def test_adr057_el_limite_se_alcanza_con_el_mismo_total_en_un_par_inexistente_y_en_uno_real(
    database_url: str, _engine_de_sesion, nombre_escrito: str
) -> None:
    """ADR-057 punto 11, SEG-01: fallos reales del login repartidos entre conexiones
    independientes, cada una confirmando sus propias transacciones. Contra un usuario real y
    contra un par que no corresponde a nadie el límite se alcanza con el MISMO total: con cuatro
    fallos el quinto todavía prueba credenciales y el sexto intento recibe el 429."""
    from app.core.clock import FixedClock
    from app.modules.identidad import service as identidad_service
    from app.modules.identidad.domain.usuarios import (
        CredencialesInvalidasError,
        LoginBloqueadoPorIntentosError,
    )

    sesion_setup = _sesion_independiente(database_url)
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba",
        slug=f"org-concurrencia-p57-{nombre_escrito}",
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
    _crear_usuario(sesion_setup, organizacion.id)
    sesion_setup.close()

    def _intentar(numero: int, password: str):
        sesion = _sesion_independiente(database_url)
        try:
            identidad_service.iniciar_sesion(
                sesion,
                FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario=nombre_escrito,
                password=password,
                dispositivo_id=nuevo_id(),
                nombre_dispositivo="Tablet",
                jwt_secreto="secreto-de-prueba",
                jwt_kid="1",
                ip=f"10.57.0.{numero}",
            )
        except CredencialesInvalidasError:
            sesion.commit()  # el fallo queda en `intento_login` (como el login real).
            raise
        finally:
            sesion.rollback()
            sesion.close()

    resultados: list[str] = []

    def _worker(inicio: int) -> None:
        for numero in (inicio, inicio + 1):
            try:
                _intentar(numero, "mal")
            except CredencialesInvalidasError:
                resultados.append("fallo")

    hilos = [threading.Thread(target=_worker, args=(i,)) for i in (1, 3)]  # 2 + 2 fallos
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert resultados == ["fallo"] * 4

    with pytest.raises(CredencialesInvalidasError):  # el quinto todavía prueba credenciales
        _intentar(5, PASSWORD if nombre_escrito == "fantasma" else "mal")
    with pytest.raises(LoginBloqueadoPorIntentosError) as bloqueado:
        _intentar(6, PASSWORD)  # el sexto: 429, también con la contraseña correcta
    assert bloqueado.value.codigo == "IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS"
    assert str(bloqueado.value).startswith("Demasiados intentos. Probá de nuevo a las ")
