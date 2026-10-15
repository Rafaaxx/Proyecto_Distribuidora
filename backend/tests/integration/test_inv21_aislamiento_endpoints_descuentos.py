"""Change 16, tarea 11.1: cobertura de aislamiento (INV-21, SEG-07) de las cuatro escrituras de
`descuentos/api.py` (alta, edición, activación y pausa de una regla) y de sus dos lecturas
(listado y detalle, tarea 9.1).

Mismo arnés HTTP que `test_inv21_aislamiento_endpoints_precios.py`: Postgres real, `cliente` con
motor propio y login real de dos organizaciones (nunca un access token fabricado a mano). La
organización A tiene reglas en los tres estados; un usuario de B, con `GESTIONAR_DESCUENTOS`,
ejerce cada ruta sobre los recursos de A y recibe 404 (nunca 403: no se revela si existe) sin
ningún efecto sobre A. La ruta de alta se prueba de la otra forma: B nunca puede apuntar a una
entidad de A en el alcance, y `organizacion_id` en el cuerpo se rechaza (la organización sale
solo del token).

Reglas citadas: INV-21, SEG-07, `CLAUDE.md` §4 (un recurso de otra organización responde 404).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from descuentos_utiles import Entorno as EntornoDeDatos
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

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-aislamiento-descuentos"
URL = "/api/v1/descuentos/reglas"


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
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


class Entorno(EntornoDeDatos):
    """Los datos de `descuentos_utiles.Entorno` más usuarios que pueden entrar por `login`."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion)
        self.sesion.commit()
        self.slug = sesion.execute(
            text("SELECT slug FROM organizacion WHERE id = :o"), {"o": self.org}
        ).scalar_one()

    def usuario_con(self, cliente_http: TestClient, *permisos: str) -> dict[str, str]:
        """Alta un usuario de ESTA organización con exactamente esos permisos y entra con él."""
        nombre_usuario = f"usuario-{uuid4().hex[:8]}"
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
            nombre="Persona de prueba",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )
        self.sesion.commit()
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": nombre_usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 200
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def _con_op(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Operation-Id": str(uuid4())}


def _regla(**cambios: Any) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "nombre": "Volumen 20 cajas",
        "tipo": "VOLUMEN_OPERACION",
        "medida": "CAJAS_EQUIVALENTES",
        "operador": "GTE",
        "umbral": "20",
        "accion_tipo": "PORCENTAJE",
        "accion_valor": "0.050000",
        "prioridad": 1,
        "acumulable": False,
        "alcances": [],
    }
    cuerpo.update(cambios)
    return cuerpo


class Escenario:
    """La organización A con un borrador, una regla activa y una pausada (con alcance), y un
    usuario de B con `GESTIONAR_DESCUENTOS`."""

    def __init__(self, cliente: TestClient, sesion: Session) -> None:
        self.a = Entorno(sesion)
        self.borrador_a = self.a.crear_regla_descuento(nombre="Borrador de A")
        self.activa_a = self.a.crear_regla_descuento(
            nombre="Activa de A",
            tipo="VOLUMEN_ALCANCE",
            alcances=[{"tipo": "MARCA", "entidad_id": str(self.a.marca_id)}],
        )
        self.a.activar_regla(self.activa_a)
        self.pausada_a = self.a.crear_regla_descuento(nombre="Pausada de A")
        self.a.activar_regla(self.pausada_a)
        self.a.pausar_regla(self.pausada_a)
        self.a.sesion.commit()

        self.b = Entorno(sesion)
        self.de_b = self.b.usuario_con(cliente, "GESTIONAR_DESCUENTOS")

    def estado_de_a(self) -> list[Any]:
        """Todo lo de A que una ruta de B podría tocar, tal como está en la base."""
        consultas = (
            "SELECT * FROM regla_descuento WHERE organizacion_id = :o ORDER BY id",
            "SELECT * FROM regla_descuento_alcance WHERE organizacion_id = :o ORDER BY id",
        )
        self.a.sesion.rollback()
        return [
            [tuple(fila) for fila in self.a.sesion.execute(text(sql), {"o": self.a.org})]
            for sql in consultas
        ]


@pytest.fixture
def escenario(cliente: TestClient, sesion: Session) -> Escenario:
    return Escenario(cliente, sesion)


def test_inv21_toda_escritura_sobre_una_regla_de_otra_organizacion_responde_404_sin_efectos(
    cliente: TestClient, escenario: Escenario
) -> None:
    """La edición, la activación y la pausa de una regla de A (en cada estado) responden 404 a
    un usuario de B con `GESTIONAR_DESCUENTOS`, y nada de A cambia."""
    antes = escenario.estado_de_a()
    llamadas: list[tuple[str, str, dict[str, Any] | None]] = []
    for regla in (escenario.borrador_a, escenario.activa_a, escenario.pausada_a):
        llamadas += [
            ("put", f"{URL}/{regla}", _regla(umbral="1")),
            ("put", f"{URL}/{regla}", {"vigencia_hasta": "2027-01-01T00:00:00+00:00"}),
            ("post", f"{URL}/{regla}/activacion", None),
            ("post", f"{URL}/{regla}/pausa", None),
        ]

    for metodo, url, cuerpo in llamadas:
        enviar = {"put": cliente.put, "post": cliente.post}[metodo]
        respuesta = enviar(url, json=cuerpo, headers=_con_op(escenario.de_b))
        assert respuesta.status_code == 404, (metodo, url, respuesta.text)
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO", (metodo, url)

    assert escenario.estado_de_a() == antes


@pytest.mark.parametrize("tipo", ["PRODUCTO", "CATEGORIA", "MARCA"])
def test_inv21_el_alta_con_una_entidad_de_a_en_el_alcance_responde_404_sin_efectos(
    cliente: TestClient, escenario: Escenario, tipo: str
) -> None:
    """El usuario de B no puede apuntar el alcance de su regla a un producto, categoría o marca
    de A: 404 y no se crea ninguna regla."""
    de_a = {
        "PRODUCTO": escenario.a.vino_id,
        "CATEGORIA": escenario.a.categoria_id,
        "MARCA": escenario.a.marca_id,
    }
    antes = escenario.estado_de_a()

    respuesta = cliente.post(
        URL,
        json=_regla(
            tipo="VOLUMEN_ALCANCE", alcances=[{"tipo": tipo, "entidad_id": str(de_a[tipo])}]
        ),
        headers=_con_op(escenario.de_b),
    )

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert escenario.estado_de_a() == antes
    assert escenario.b.reglas_de_descuento() == []


def test_inv21_el_alta_de_b_crea_la_regla_en_b_y_a_no_la_ve(
    cliente: TestClient, escenario: Escenario
) -> None:
    """Contraste: el alta de B funciona y queda en B (la organización sale del token)."""
    antes = escenario.estado_de_a()

    respuesta = cliente.post(URL, json=_regla(), headers=_con_op(escenario.de_b))

    assert respuesta.status_code == 201
    assert escenario.estado_de_a() == antes
    assert len(escenario.b.reglas_de_descuento()) == 1


def test_inv21_un_organizacion_id_de_a_en_el_cuerpo_se_rechaza(
    cliente: TestClient, escenario: Escenario
) -> None:
    antes = escenario.estado_de_a()

    respuesta = cliente.post(
        URL,
        json=_regla(organizacion_id=str(escenario.a.org)),
        headers=_con_op(escenario.de_b),
    )

    assert respuesta.status_code == 422
    assert escenario.estado_de_a() == antes
    assert escenario.b.reglas_de_descuento() == []


def test_inv21_las_mismas_rutas_funcionan_para_la_organizacion_duena(
    cliente: TestClient, escenario: Escenario
) -> None:
    """Contraste: A sobre sus propios recursos responde 200 (los 404 de arriba no son por una
    URL mal armada)."""
    de_a = escenario.a.usuario_con(cliente, "GESTIONAR_DESCUENTOS")

    activada = cliente.post(f"{URL}/{escenario.borrador_a}/activacion", headers=_con_op(de_a))
    pausada = cliente.post(f"{URL}/{escenario.activa_a}/pausa", headers=_con_op(de_a))

    assert (activada.status_code, pausada.status_code) == (200, 200)


def test_inv21_el_detalle_de_una_regla_de_a_responde_404_a_un_usuario_de_b(
    cliente: TestClient, escenario: Escenario
) -> None:
    """Las tres reglas de A (borrador, activa y pausada) responden 404 en el detalle."""
    for regla in (escenario.borrador_a, escenario.activa_a, escenario.pausada_a):
        respuesta = cliente.get(f"{URL}/{regla}", headers=escenario.de_b)
        assert respuesta.status_code == 404, (regla, respuesta.text)
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"


def test_inv21_el_listado_de_b_no_trae_nada_de_a_y_el_de_a_trae_lo_suyo(
    cliente: TestClient, escenario: Escenario
) -> None:
    de_a = escenario.a.usuario_con(cliente, "GESTIONAR_DESCUENTOS")
    cliente.post(URL, json=_regla(nombre="De B"), headers=_con_op(escenario.de_b))

    de_b_ve = cliente.get(URL, headers=escenario.de_b).json()["items"]
    de_a_ve = cliente.get(URL, headers=de_a).json()["items"]

    assert [r["nombre"] for r in de_b_ve] == ["De B"]
    assert {r["nombre"] for r in de_a_ve} == {"Borrador de A", "Activa de A", "Pausada de A"}
    # El detalle de A sobre lo propio responde 200 (los 404 de arriba no son por URL mal armada).
    assert cliente.get(f"{URL}/{escenario.activa_a}", headers=de_a).status_code == 200
