"""Change 28, tarea 2.3: la corrida del servicio de tareas (`python -m app.tareas ahora`), su
registro, su salud y el aviso externo opcional (`design.md` D2, D5 c y d, D6).

Conectada como `app_mantenimiento`; los datos se confirman de verdad y se vacían al terminar.
Reglas citadas: INV-02, `02` §7.6, `02` §17, ADR-015.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from cuentas_corrientes_utiles import crear_organizacion
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session
from ventas_anular_utiles import EntornoAnulacion

from app.core.clock import FixedClock
from app.core.db import crear_session_factory
from app.tareas import __main__ as tareas_main
from app.tareas import verificacion
from app.tareas.estado import leer_estado

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

AHORA = datetime(2026, 11, 11, 5, 0, tzinfo=UTC)
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def sesion_real(_engine_de_sesion: Engine) -> Iterator[Session]:
    with crear_session_factory(_engine_de_sesion)() as sesion:
        yield sesion
        sesion.rollback()
    with _engine_de_sesion.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE intento_login, organizacion CASCADE"))


@pytest.fixture
def dos_organizaciones(sesion_real: Session) -> tuple[EntornoAnulacion, UUID]:
    ventas = EntornoAnulacion(sesion_real)  # con su cliente "Kiosco La Esquina" y su saldo
    vacia = crear_organizacion(sesion_real).id
    sesion_real.commit()
    return ventas, vacia


@pytest.fixture
def entorno(app_mantenimiento_engine: Engine, tmp_path: Path) -> dict[str, str]:
    return {
        "DATABASE_URL": app_mantenimiento_engine.url.render_as_string(hide_password=False),
        "ESTADO_DIR": str(tmp_path / "estado"),
        "TZ": "UTC",
    }


def _ahora(entorno: dict[str, str], reloj: FixedClock | None = None) -> int:
    return tareas_main.main(["ahora"], entorno=entorno, reloj=reloj or FixedClock(AHORA))


def _salud(entorno: dict[str, str], reloj: FixedClock | None = None) -> int:
    return tareas_main.main(["salud"], entorno=entorno, reloj=reloj or FixedClock(AHORA))


def _filas(motor: Engine, organizacion_id: UUID) -> list[Any]:
    with motor.connect() as conexion:
        return [
            tuple(fila)
            for fila in conexion.execute(
                text(
                    "SELECT resultado, ejecutada_en FROM verificacion_consistencia "
                    "WHERE organizacion_id = :o ORDER BY registered_at"
                ),
                {"o": organizacion_id},
            )
        ]


def _alterar_saldo(motor: Engine, organizacion_id: UUID, delta: str) -> None:
    with motor.begin() as conexion:
        conexion.execute(
            text("UPDATE saldo_cuenta SET saldo = saldo + :d WHERE organizacion_id = :o"),
            {"d": delta, "o": organizacion_id},
        )


def test_inv02_la_corrida_a_pedido_guarda_un_resultado_por_organizacion(
    dos_organizaciones: tuple[EntornoAnulacion, UUID],
    entorno: dict[str, str],
    app_mantenimiento_engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ventas, vacia = dos_organizaciones

    assert _ahora(entorno) == 0

    for organizacion_id in (ventas.org, vacia):
        assert _filas(app_mantenimiento_engine, organizacion_id) == [("SIN_DIFERENCIAS", AHORA)]
    assert "sin diferencias" in capsys.readouterr().out
    estado = leer_estado(Path(entorno["ESTADO_DIR"]))
    assert estado is not None and estado["resultado"] == "SIN_DIFERENCIAS"
    assert estado["ultima_corrida"] == AHORA.isoformat()


def test_la_corrida_a_pedido_tambien_limpia_los_intentos_de_login_viejos(
    dos_organizaciones: tuple[EntornoAnulacion, UUID],
    entorno: dict[str, str],
    _engine_de_sesion: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with _engine_de_sesion.begin() as conexion:
        for horas in (30, 2):
            conexion.execute(
                text(
                    "INSERT INTO intento_login (id, usuario_id, clave_intento, ip, exito, "
                    "creado_en) VALUES (gen_random_uuid(), NULL, :c, '10.0.0.1', false, :t)"
                ),
                {"c": "b" * 64, "t": AHORA - timedelta(hours=horas)},
            )

    assert _ahora(entorno) == 0

    with _engine_de_sesion.connect() as conexion:
        assert conexion.execute(text("SELECT count(*) FROM intento_login")).scalar_one() == 1
    assert "1 intento de inicio de sesión de más de 24 horas borrado" in capsys.readouterr().out


def test_una_diferencia_es_error_critico_sin_datos_personales_y_la_salud_cae_hasta_corregirla(
    dos_organizaciones: tuple[EntornoAnulacion, UUID],
    entorno: dict[str, str],
    app_mantenimiento_engine: Engine,
    app_migrations_engine: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ventas, vacia = dos_organizaciones
    _alterar_saldo(app_migrations_engine, ventas.org, "12.00")

    with caplog.at_level(logging.INFO, logger="app.tareas"):
        assert _ahora(entorno) == 1

    criticos = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(criticos) == 1
    mensaje = criticos[0].getMessage()
    assert str(ventas.org) in mensaje and "diferencias=1" in mensaje
    assert str(vacia) not in mensaje
    assert "Kiosco" not in caplog.text
    assert _filas(app_mantenimiento_engine, ventas.org)[0][0] == "CON_DIFERENCIAS"
    assert _salud(entorno) == 1

    _alterar_saldo(app_migrations_engine, ventas.org, "-12.00")
    manana = FixedClock(AHORA + timedelta(days=1))
    assert _ahora(entorno, manana) == 0
    assert _salud(entorno, manana) == 0
    assert [f[0] for f in _filas(app_mantenimiento_engine, ventas.org)] == [
        "CON_DIFERENCIAS",
        "SIN_DIFERENCIAS",
    ]


def test_la_falla_en_una_organizacion_no_frena_a_las_otras(
    dos_organizaciones: tuple[EntornoAnulacion, UUID],
    entorno: dict[str, str],
    app_mantenimiento_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ventas, vacia = dos_organizaciones
    original = verificacion.verificar_organizacion

    def _falla_en_una(organizacion_id: UUID, sesion: Session) -> list[dict[str, object]]:
        if organizacion_id == ventas.org:
            raise RuntimeError("detalle interno con el cliente Kiosco")
        return original(organizacion_id, sesion)

    monkeypatch.setattr(verificacion, "verificar_organizacion", _falla_en_una)

    with caplog.at_level(logging.INFO, logger="app.tareas"):
        assert _ahora(entorno) == 1

    assert _filas(app_mantenimiento_engine, ventas.org) == []
    assert _filas(app_mantenimiento_engine, vacia) == [("SIN_DIFERENCIAS", AHORA)]
    errores = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errores and "RuntimeError" in errores[0].getMessage()
    assert "Kiosco" not in caplog.text
    estado = leer_estado(Path(entorno["ESTADO_DIR"]))
    assert estado is not None and estado["resultado"] == "FALLIDA"
    assert _salud(entorno) == 1


def test_una_corrida_que_falla_se_ve_y_la_siguiente_vuelve_a_intentar(
    dos_organizaciones: tuple[EntornoAnulacion, UUID],
    entorno: dict[str, str],
    app_mantenimiento_engine: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ventas, _ = dos_organizaciones
    sin_base = {
        **entorno,
        "DATABASE_URL": "postgresql+psycopg://x:y@127.0.0.1:1/z?connect_timeout=2",
    }

    with caplog.at_level(logging.INFO, logger="app.tareas"):
        assert _ahora(sin_base) == 1

    assert any(r.levelno >= logging.ERROR for r in caplog.records)
    assert "x:y" not in caplog.text
    assert _salud(sin_base) == 1
    manana = FixedClock(AHORA + timedelta(days=1))
    assert _ahora(entorno, manana) == 0
    assert _salud(entorno, manana) == 0
    assert len(_filas(app_mantenimiento_engine, ventas.org)) == 1


class _Registro(BaseHTTPRequestHandler):
    llamadas: list[tuple[str, bytes]] = []

    def do_GET(self) -> None:
        self._anotar()

    def do_POST(self) -> None:
        self._anotar()

    def _anotar(self) -> None:
        largo = int(self.headers.get("Content-Length") or 0)
        self.llamadas.append((self.path, self.rfile.read(largo)))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        return None


@pytest.fixture
def servidor_de_aviso() -> Iterator[tuple[str, list[tuple[str, bytes]]]]:
    llamadas: list[tuple[str, bytes]] = []
    manejador = type("Manejador", (_Registro,), {"llamadas": llamadas})
    servidor = HTTPServer(("127.0.0.1", 0), manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{servidor.server_port}/ping/ABC", llamadas
    servidor.shutdown()
    servidor.server_close()


def test_con_aviso_url_sin_diferencias_llama_a_la_direccion_y_con_diferencias_a_fail(
    dos_organizaciones: tuple[EntornoAnulacion, UUID],
    entorno: dict[str, str],
    app_migrations_engine: Engine,
    servidor_de_aviso: tuple[str, list[tuple[str, bytes]]],
) -> None:
    ventas, _ = dos_organizaciones
    url, llamadas = servidor_de_aviso
    con_aviso = {**entorno, "AVISO_TAREAS_URL": url}

    assert _ahora(con_aviso) == 0
    assert [ruta for ruta, _ in llamadas] == ["/ping/ABC"]

    _alterar_saldo(app_migrations_engine, ventas.org, "5.00")
    assert _ahora(con_aviso) == 1
    assert [ruta for ruta, _ in llamadas] == ["/ping/ABC", "/ping/ABC/fail"]
    assert all(cuerpo == b"" for _, cuerpo in llamadas)


def test_sin_aviso_url_no_se_llama_a_nadie_y_un_aviso_caido_no_rompe_la_corrida(
    dos_organizaciones: tuple[EntornoAnulacion, UUID], entorno: dict[str, str]
) -> None:
    caido = {**entorno, "AVISO_TAREAS_URL": "http://127.0.0.1:1/ping/ABC"}
    assert _ahora(entorno) == 0
    assert _ahora(caido) == 0


def test_python_m_app_tareas_ahora_funciona_como_orden(
    dos_organizaciones: tuple[EntornoAnulacion, UUID], entorno: dict[str, str]
) -> None:
    resultado = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.tareas", "ahora"],
        cwd=BACKEND,
        env={**os.environ, **entorno},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "sin diferencias" in resultado.stdout
