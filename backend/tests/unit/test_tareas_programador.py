"""Change 28, tarea 2.3: la parte pura del servicio de tareas (`design.md` D2, D5, D6): cuándo es
la próxima corrida, cómo se lee la configuración del entorno y cuándo la salud es no sana.

Reglas citadas: `02` §7.6 (verificación diaria), ADR-015, `02` §17.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.tareas.configuracion import ConfiguracionDeTareas, ConfiguracionInvalidaError
from app.tareas.estado import MAXIMO_SIN_CORRIDA, evaluar_salud
from app.tareas.programador import parsear_hora, proxima_corrida

MENDOZA = ZoneInfo("America/Argentina/Mendoza")  # UTC-3 todo el año


def _utc(*partes: int) -> datetime:
    return datetime(*partes, tzinfo=UTC)


# --- próxima corrida (D6) -----------------------------------------------------------------


def test_antes_de_la_hora_corre_hoy() -> None:
    # 07:00 UTC = 04:00 en Mendoza; la corrida de las 05:00 es hoy (08:00 UTC).
    assert proxima_corrida(_utc(2026, 11, 11, 7, 0), time(5, 0), MENDOZA) == _utc(
        2026, 11, 11, 8, 0
    )


def test_despues_de_la_hora_corre_manana() -> None:
    # 09:00 UTC = 06:00 en Mendoza: ya pasó las 05:00, la próxima es mañana.
    assert proxima_corrida(_utc(2026, 11, 11, 9, 0), time(5, 0), MENDOZA) == _utc(
        2026, 11, 12, 8, 0
    )


def test_a_la_hora_exacta_corre_manana_y_no_se_repite() -> None:
    assert proxima_corrida(_utc(2026, 11, 11, 8, 0), time(5, 0), MENDOZA) == _utc(
        2026, 11, 12, 8, 0
    )


def test_el_dia_lo_decide_la_zona_y_no_utc() -> None:
    # 02:00 UTC del 11 es el 10 a las 23:00 en Mendoza: las 05:00 locales son el 11 a las 08:00 UTC.
    assert proxima_corrida(_utc(2026, 11, 11, 2, 0), time(5, 0), MENDOZA) == _utc(
        2026, 11, 11, 8, 0
    )


def test_la_misma_hora_en_otra_zona_es_otro_momento() -> None:
    ahora = _utc(2026, 11, 11, 7, 0)
    en_utc = proxima_corrida(ahora, time(5, 0), ZoneInfo("UTC"))
    assert en_utc == _utc(2026, 11, 12, 5, 0)
    assert en_utc != proxima_corrida(ahora, time(5, 0), MENDOZA)


def test_con_cambio_de_hora_de_verano_sigue_siendo_las_cinco_locales() -> None:
    nueva_york = ZoneInfo("America/New_York")
    # El 8 de marzo de 2026 adelantan el reloj: el 7 las 05:00 son 10:00 UTC y el 8, 09:00 UTC.
    primera = proxima_corrida(_utc(2026, 3, 7, 6, 0), time(5, 0), nueva_york)
    segunda = proxima_corrida(primera, time(5, 0), nueva_york)
    assert (primera, segunda) == (_utc(2026, 3, 7, 10, 0), _utc(2026, 3, 8, 9, 0))
    assert segunda - primera == timedelta(hours=23)


@pytest.mark.parametrize("texto", ["5:00", "24:00", "05:60", "mediodia", "", "05:00:00"])
def test_una_hora_mal_escrita_se_rechaza(texto: str) -> None:
    with pytest.raises(ConfiguracionInvalidaError, match="TAREAS_HORA"):
        parsear_hora(texto)


def test_una_hora_valida_se_lee() -> None:
    assert (parsear_hora("05:00"), parsear_hora("23:59")) == (time(5, 0), time(23, 59))


# --- configuración del entorno (D2, D3) ---------------------------------------------------


def test_la_configuracion_usa_los_valores_por_defecto() -> None:
    config = ConfiguracionDeTareas.desde_entorno({"DATABASE_URL": "postgresql+psycopg://x"})
    assert config.hora == time(5, 0)
    assert config.zona == MENDOZA
    assert config.aviso_url is None
    assert config.database_url == "postgresql+psycopg://x"


def test_la_configuracion_lee_hora_zona_y_aviso() -> None:
    config = ConfiguracionDeTareas.desde_entorno(
        {
            "DATABASE_URL": "postgresql+psycopg://x",
            "TAREAS_HORA": "06:30",
            "TZ": "UTC",
            "AVISO_TAREAS_URL": "http://aviso/ping/1",
            "ESTADO_DIR": "/otro",
        }
    )
    assert (config.hora, config.zona, config.aviso_url) == (
        time(6, 30),
        ZoneInfo("UTC"),
        "http://aviso/ping/1",
    )
    assert config.estado_dir == Path("/otro")


def test_sin_database_url_el_error_nombra_la_variable() -> None:
    with pytest.raises(ConfiguracionInvalidaError, match="DATABASE_URL"):
        ConfiguracionDeTareas.desde_entorno({})


def test_una_zona_desconocida_nombra_la_variable() -> None:
    with pytest.raises(ConfiguracionInvalidaError, match="TZ"):
        ConfiguracionDeTareas.desde_entorno({"DATABASE_URL": "x", "TZ": "Marte/Olimpo"})


def test_el_error_de_configuracion_no_repite_la_url_de_la_base() -> None:
    with pytest.raises(ConfiguracionInvalidaError) as error:
        ConfiguracionDeTareas.desde_entorno(
            {"DATABASE_URL": "postgresql+psycopg://u:secreto@h/b", "TAREAS_HORA": "xx"}
        )
    assert "secreto" not in str(error.value)


# --- salud (D5 c, D6) ----------------------------------------------------------------------

AHORA = _utc(2026, 11, 11, 12, 0)


def _estado(**cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "arranque": (AHORA - timedelta(days=3)).isoformat(),
        "ultima_corrida": (AHORA - timedelta(hours=7)).isoformat(),
        "resultado": "SIN_DIFERENCIAS",
        "diferencias": 0,
    }
    base.update(cambios)
    return base


def test_la_salud_es_sana_con_la_ultima_corrida_sin_diferencias() -> None:
    assert evaluar_salud(_estado(), AHORA) == (True, "ok")


def test_la_salud_no_es_sana_con_diferencias() -> None:
    sana, motivo = evaluar_salud(_estado(resultado="CON_DIFERENCIAS", diferencias=2), AHORA)
    assert not sana and "diferencias" in motivo


def test_la_salud_no_es_sana_si_la_ultima_corrida_fallo() -> None:
    sana, motivo = evaluar_salud(_estado(resultado="FALLIDA"), AHORA)
    assert not sana and "fall" in motivo


def test_la_salud_no_es_sana_sin_corrida_en_mas_de_26_horas() -> None:
    assert timedelta(hours=26) == MAXIMO_SIN_CORRIDA
    vieja = (AHORA - timedelta(hours=26, minutes=1)).isoformat()
    sana, motivo = evaluar_salud(_estado(ultima_corrida=vieja), AHORA)
    assert not sana and "26" in motivo
    justo = (AHORA - timedelta(hours=26)).isoformat()
    assert evaluar_salud(_estado(ultima_corrida=justo), AHORA)[0]


def test_recien_arrancado_sin_corrida_es_sano_hasta_las_26_horas() -> None:
    nuevo = {"arranque": (AHORA - timedelta(hours=2)).isoformat()}
    assert evaluar_salud(nuevo, AHORA)[0]
    viejo = {"arranque": (AHORA - timedelta(hours=27)).isoformat()}
    assert not evaluar_salud(viejo, AHORA)[0]


def test_sin_archivo_de_estado_no_es_sano() -> None:
    sana, motivo = evaluar_salud(None, AHORA)
    assert not sana and "estado" in motivo


# --- el bucle del servicio (D2, D6) ---------------------------------------------------------


class _RelojQueAvanza:
    """Reloj que solo avanza cuando el servicio espera."""

    def __init__(self, inicio: datetime) -> None:
        self.ahora = inicio
        self.esperas: list[float] = []

    def now(self) -> datetime:
        return self.ahora

    def esperar(self, segundos: float) -> bool:
        self.esperas.append(segundos)
        self.ahora += timedelta(seconds=segundos)
        return False


def test_el_servicio_corre_a_la_hora_cada_dia_y_para_cuando_se_lo_piden(tmp_path) -> None:
    from app.tareas.servicio import servir

    reloj = _RelojQueAvanza(_utc(2026, 11, 11, 7, 0))  # 04:00 en Mendoza
    corridas: list[datetime] = []
    config = ConfiguracionDeTareas.desde_entorno(
        {"DATABASE_URL": "x", "ESTADO_DIR": str(tmp_path), "TAREAS_HORA": "05:00"}
    )

    def correr() -> None:
        corridas.append(reloj.now())

    def esperar(segundos: float) -> bool:
        reloj.esperar(segundos)
        return len(corridas) == 2  # a la segunda corrida piden parar

    servir(config, reloj, correr, esperar)

    assert corridas == [_utc(2026, 11, 11, 8, 0), _utc(2026, 11, 12, 8, 0)]
    # Nunca duerme más de una hora de una vez (un salto del reloj no la adelanta ni la atrasa).
    assert max(reloj.esperas) <= 3600.0
    assert leer_estado_de(tmp_path)["arranque"] == _utc(2026, 11, 11, 7, 0).isoformat()


def leer_estado_de(directorio):
    from app.tareas.estado import leer_estado

    estado = leer_estado(directorio)
    assert estado is not None
    return estado
