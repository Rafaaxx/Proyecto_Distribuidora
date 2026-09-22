"""Pruebas unitarias de `procesar_comando` (change 04, grupo 6, tareas 6.3,
6.4, 6.5): el clasificador de errores transitorios y el bucle de reintentos
en aislamiento, sin tocar PostgreSQL real -- `sync_service.procesar_idempotente`
se reemplaza con un doble de prueba vía `monkeypatch` porque acá lo que se
ejercita es el bucle de `procesar_comando`, no la reserva (ya cubierta por
`tests/integration/test_inv06_reserva_idempotencia.py`, grupo 5).

Las pruebas que necesitan persistencia real (6.1, 6.2, 6.6, 6.8) están en
`tests/integration/test_bus_transaccion.py`; la de concurrencia real (6.7)
en `tests/concurrency/test_bus_reintentos_concurrencia.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.modules.sync import service as sync_service

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


def _sobre() -> SobreComando:
    return SobreComando(
        operation_id=uuid4(),
        tipo="USUARIO_CREAR",
        version=1,
        modo="ONLINE",
        organizacion_id=uuid4(),
        usuario_id=uuid4(),
        dispositivo_id=uuid4(),
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={},
    )


class _ErrorDeBaseFalso(Exception):
    """Simula una excepción de SQLAlchemy que envuelve un error de driver
    con `.orig.sqlstate` (`DBAPIError`/subclases), sin depender de
    PostgreSQL real -- lo que clasifica `es_error_transitorio` es
    exclusivamente ese atributo."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"simulado sqlstate={sqlstate}")
        self.orig = SimpleNamespace(sqlstate=sqlstate)


class TestClasificadorDeErroresTransitorios:
    """Tarea 6.4: `40001` y `40P01` son transitorios; un error de dominio y
    cualquier otro fallo no lo son."""

    def test_serializacion_40001_es_transitorio(self) -> None:
        assert sync_service.es_error_transitorio(_ErrorDeBaseFalso("40001")) is True

    def test_interbloqueo_40p01_es_transitorio(self) -> None:
        assert sync_service.es_error_transitorio(_ErrorDeBaseFalso("40P01")) is True

    def test_un_error_de_dominio_no_se_reintenta(self) -> None:
        """Escenario "Un error de dominio no se reintenta"."""
        from app.commands.errores import ComandoInconsistenteError

        assert sync_service.es_error_transitorio(ComandoInconsistenteError("mensaje")) is False

    def test_cualquier_otro_sqlstate_no_es_transitorio(self) -> None:
        assert sync_service.es_error_transitorio(_ErrorDeBaseFalso("23505")) is False

    def test_una_excepcion_sin_orig_no_es_transitoria(self) -> None:
        assert sync_service.es_error_transitorio(RuntimeError("cualquier fallo")) is False


class TestHandlerNoPuedeConfirmar:
    """Tarea 6.3: un handler no puede confirmar la transacción por su
    cuenta."""

    def test_el_handler_no_puede_hacer_commit_de_la_sesion(self) -> None:
        sesion_real = MagicMock()

        def _handler(sesion_recibida: object) -> sync_service.ResultadoHandler:
            sesion_recibida.commit()  # type: ignore[attr-defined]
            return "ACEPTADO", {}, None

        with pytest.raises(sync_service.HandlerNoPuedeConfirmarError):
            sync_service.procesar_comando(
                sesion_real,
                FixedClock(MOMENTO),
                sobre=_sobre(),
                huella="huella-1",
                ejecutar_handler=_handler,
            )
        sesion_real.commit.assert_not_called()

    def test_el_handler_no_puede_hacer_rollback_de_la_sesion(self) -> None:
        """Triangulación: la misma protección aplica a `rollback`, no solo
        a `commit`."""
        sesion_real = MagicMock()

        def _handler(sesion_recibida: object) -> sync_service.ResultadoHandler:
            sesion_recibida.rollback()  # type: ignore[attr-defined]
            return "ACEPTADO", {}, None

        with pytest.raises(sync_service.HandlerNoPuedeConfirmarError):
            sync_service.procesar_comando(
                sesion_real,
                FixedClock(MOMENTO),
                sobre=_sobre(),
                huella="huella-1",
                ejecutar_handler=_handler,
            )

    def test_un_handler_normal_si_puede_usar_la_sesion_para_leer_y_escribir(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Contraparte positiva: la sesión protegida delega todo lo demás
        (`add`, `flush`, `execute`, ...) con normalidad. La reserva en sí
        (`reservar_comando`, con su SQL real) ya está cubierta por
        `tests/integration/test_inv06_reserva_idempotencia.py`; acá se
        reemplaza `procesar_idempotente` por un doble para aislar
        exclusivamente el comportamiento de la sesión protegida."""

        def _procesar_idempotente_falso(sesion, reloj, *, sobre, huella, ejecutar_handler):
            estado, resultado, error_codigo = ejecutar_handler()
            return SimpleNamespace(
                id=uuid4(), estado=estado, resultado=resultado, error_codigo=error_codigo
            )

        monkeypatch.setattr(sync_service, "procesar_idempotente", _procesar_idempotente_falso)

        sesion_real = MagicMock()
        sesion_real.execute.return_value = "resultado-de-consulta"
        llamadas: list[str] = []

        def _handler(sesion_recibida: object) -> sync_service.ResultadoHandler:
            resultado = sesion_recibida.execute("select 1")  # type: ignore[attr-defined]
            llamadas.append(str(resultado))
            return "ACEPTADO", {"eco": resultado}, None

        comando = sync_service.procesar_comando(
            sesion_real,
            FixedClock(MOMENTO),
            sobre=_sobre(),
            huella="huella-1",
            ejecutar_handler=_handler,
        )

        assert llamadas == ["resultado-de-consulta"]
        assert comando.estado == "ACEPTADO"
        sesion_real.commit.assert_called_once()


class TestReintentoDeErroresTransitorios:
    """Tarea 6.5: reintenta la transacción completa hasta el máximo
    configurado, con espera entre intentos."""

    def test_reintenta_y_termina_aceptado_si_el_transitorio_no_persiste(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        llamadas = {"n": 0}

        def _procesar_idempotente_falso(sesion, reloj, *, sobre, huella, ejecutar_handler):
            llamadas["n"] += 1
            if llamadas["n"] < 3:
                raise _ErrorDeBaseFalso("40001")
            estado, resultado, error_codigo = ejecutar_handler()
            return SimpleNamespace(
                id=uuid4(), estado=estado, resultado=resultado, error_codigo=error_codigo
            )

        monkeypatch.setattr(sync_service, "procesar_idempotente", _procesar_idempotente_falso)

        esperas: list[float] = []
        sesion_real = MagicMock()

        comando = sync_service.procesar_comando(
            sesion_real,
            FixedClock(MOMENTO),
            sobre=_sobre(),
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("ACEPTADO", {"ok": True}, None),
            dormir=esperas.append,
        )

        assert llamadas["n"] == 3
        assert comando.estado == "ACEPTADO"
        assert len(esperas) == 2  # una espera entre cada uno de los 2 fallos y el reintento
        assert all(espera >= 0 for espera in esperas)
        sesion_real.commit.assert_called_once()
        assert sesion_real.rollback.call_count == 2

    def test_agotados_los_reintentos_la_respuesta_es_transitoria_y_no_un_rechazo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Escenario "Agotados los reintentos, la respuesta es transitoria y
        no un rechazo"."""

        def _siempre_transitorio(sesion, reloj, *, sobre, huella, ejecutar_handler):
            raise _ErrorDeBaseFalso("40P01")

        monkeypatch.setattr(sync_service, "procesar_idempotente", _siempre_transitorio)
        sesion_real = MagicMock()

        with pytest.raises(sync_service.ErrorTransitorioAgotadoError) as exc_info:
            sync_service.procesar_comando(
                sesion_real,
                FixedClock(MOMENTO),
                sobre=_sobre(),
                huella="huella-1",
                ejecutar_handler=lambda _sesion: ("ACEPTADO", {}, None),
                config=sync_service.ConfiguracionReintentos(intentos_maximos=3),
                dormir=lambda _segundos: None,
            )

        assert exc_info.value.intentos == 3
        assert exc_info.value.codigo == "ERROR_TRANSITORIO"
        sesion_real.commit.assert_not_called()

    def test_un_error_no_transitorio_no_se_reintenta_y_se_relanza_tal_cual(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Triangulación de 6.4 a nivel del bucle: un fallo que no es
        transitorio corta en el primer intento."""
        llamadas = {"n": 0}

        def _procesar_idempotente_falso(sesion, reloj, *, sobre, huella, ejecutar_handler):
            llamadas["n"] += 1
            raise ValueError("fallo no transitorio, de programación")

        monkeypatch.setattr(sync_service, "procesar_idempotente", _procesar_idempotente_falso)
        sesion_real = MagicMock()

        with pytest.raises(ValueError, match="fallo no transitorio"):
            sync_service.procesar_comando(
                sesion_real,
                FixedClock(MOMENTO),
                sobre=_sobre(),
                huella="huella-1",
                ejecutar_handler=lambda _sesion: ("ACEPTADO", {}, None),
                dormir=lambda _segundos: None,
            )

        assert llamadas["n"] == 1


class TestVerificarPermiso:
    """`verificar_permiso` corre antes que el handler y, si lanza, revierte
    la transacción igual que un fallo del handler (adelanto de la tarea
    7.5, ejercitado acá porque el mecanismo es de `procesar_comando`)."""

    def test_un_permiso_faltante_no_ejecuta_el_handler(self) -> None:
        sesion_real = MagicMock()
        llamadas: list[str] = []

        class _PermisoFalso(Exception):
            pass

        def _verificar_permiso() -> None:
            raise _PermisoFalso("sin permiso")

        def _handler(_sesion: object) -> sync_service.ResultadoHandler:
            llamadas.append("ejecutado")
            return "ACEPTADO", {}, None

        with pytest.raises(_PermisoFalso):
            sync_service.procesar_comando(
                sesion_real,
                FixedClock(MOMENTO),
                sobre=_sobre(),
                huella="huella-1",
                verificar_permiso=_verificar_permiso,
                ejecutar_handler=_handler,
            )

        assert llamadas == []
        sesion_real.commit.assert_not_called()
        sesion_real.rollback.assert_called_once()
