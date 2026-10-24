"""Tarea 6.3 (change 18b; `design.md` D3 revisada el 2026-10-22; spec
`identidad/pin-de-autorizacion`): el contador de fallos del PIN de autorización, por par (quien
intenta, autorizador) y general por autorizador, escrito en una transacción aparte.

Las pruebas usan una sesión con commits reales (el fallo se confirma aunque la transacción del
comando se revierta) y un reloj ajustable. La organización de prueba trae `intentos_pin_max = 3`;
acá se fija en 5, como el alta real, salvo donde se dice otra cosa.

Reglas citadas: SEG-04, ADR-011, INV-01.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import seguridad
from app.core.db import crear_engine, crear_session_factory
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import PinBloqueadoError, PinIncorrectoError

PIN = "482913"
PIN_MALO = "937104"
PERMISO = "AUTORIZAR_DESCUENTO"
MAÑANA = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)


class RelojAjustable:
    """Reloj de prueba que se mueve a mano: `en("10:10")` fija la hora del día."""

    def __init__(self) -> None:
        self.ahora = MAÑANA

    def en(self, hora: str) -> None:
        """`"10:10"` o `"10:10:30"`."""
        partes = [int(parte) for parte in hora.split(":")]
        self.ahora = MAÑANA.replace(
            hour=partes[0], minute=partes[1], second=partes[2] if len(partes) > 2 else 0
        )

    def now(self) -> datetime:
        return self.ahora


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = crear_engine(database_url)
    try:
        with crear_session_factory(engine)() as sesion_real:
            yield sesion_real
    finally:
        with engine.begin() as conexion:
            conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
        engine.dispose()


@pytest.fixture
def reloj() -> RelojAjustable:
    reloj = RelojAjustable()
    reloj.en("09:00")
    return reloj


class Escenario:
    """Una organización con Marta (autorizadora con PIN) y los usuarios que intentan."""

    def __init__(self, sesion: Session, reloj: RelojAjustable, *, intentos_pin_max: int = 5):
        self.sesion = sesion
        self.reloj = reloj
        self.organizacion = crear_organizacion(sesion)
        self.org = self.organizacion.id
        sesion.execute(
            text("UPDATE configuracion_organizacion SET intentos_pin_max = :n"),
            {"n": intentos_pin_max},
        )
        self.marta = self.usuario(frozenset({PERMISO}), con_pin=PIN)
        self.dispositivo = crear_usuario_y_dispositivo(sesion, self.org)[1]
        sesion.commit()

    def usuario(self, permisos: frozenset[str], *, con_pin: str | None = None) -> UUID:
        usuario_id, _ = crear_usuario_y_dispositivo(self.sesion, self.org, permisos=permisos)
        if con_pin is not None:
            identidad_service.establecer_pin_autorizacion(
                self.org,
                self.sesion,
                self.reloj,
                usuario_id=usuario_id,
                pin=con_pin,
                actor_id=usuario_id,
            )
        self.sesion.commit()
        return usuario_id

    def vendedor(self) -> UUID:
        return self.usuario(frozenset({"VENDER"}))

    def verificar(self, intentante: UUID, pin: str, *, hora: str | None = None) -> Any:
        if hora is not None:
            self.reloj.en(hora)
        return identidad_service.verificar_pin_de_autorizacion(
            self.org,
            self.sesion,
            self.reloj,
            autorizador_id=self.marta,
            intentante_id=intentante,
            pin=pin,
            permiso=PERMISO,
            dispositivo_id=self.dispositivo,
        )

    def falla(self, intentante: UUID, hora: str, pin: str = PIN_MALO) -> None:
        with pytest.raises(PinIncorrectoError):
            self.verificar(intentante, pin, hora=hora)

    def filas(self, *, exito: bool = False) -> list[dict[str, Any]]:
        """Las filas de `intento_pin_autorizacion` de la organización de la prueba. Con
        `exito=True` incluye el marcador de "PIN definido" (sin intentante) que escribe
        `establecer_pin_autorizacion` al dar de alta el PIN (ADR-011)."""
        self.sesion.rollback()
        resultado = self.sesion.execute(
            text(
                "SELECT autorizador_id, intentante_id, exito, creado_en "
                "FROM intento_pin_autorizacion WHERE organizacion_id = :org AND exito = :e "
                "ORDER BY creado_en"
            ),
            {"org": self.org, "e": exito},
        )
        return [dict(fila._mapping) for fila in resultado]

    def exitos_de_verificacion(self) -> list[dict[str, Any]]:
        """Los éxitos escritos por una verificación (con intentante), sin el marcador de alta."""
        return [fila for fila in self.filas(exito=True) if fila["intentante_id"] is not None]

    def bloqueos_auditados(self) -> list[dict[str, Any]]:
        self.sesion.rollback()
        resultado = self.sesion.execute(
            text(
                "SELECT entidad, entidad_id, usuario_id, despues::text AS despues_texto, "
                "despues FROM auditoria WHERE accion = 'PIN_AUTORIZACION_BLOQUEADO' "
                "ORDER BY registered_at, id"
            )
        )
        return [dict(fila._mapping) for fila in resultado]


@pytest.fixture
def escenario(sesion: Session, reloj: RelojAjustable) -> Escenario:
    return Escenario(sesion, reloj)


def _bloquear_a_pedro(e: Escenario, pedro: UUID) -> None:
    for hora in ("10:02", "10:05", "10:07", "10:09", "10:10"):
        e.falla(pedro, hora)


# --- por par (SEG-04, ADR-011) -------------------------------------------------------------


def test_seg04_cinco_fallos_de_pedro_lo_bloquean_aun_con_el_pin_correcto_y_juan_autoriza(
    escenario: Escenario,
) -> None:
    pedro, juan = escenario.vendedor(), escenario.vendedor()

    _bloquear_a_pedro(escenario, pedro)

    with pytest.raises(PinBloqueadoError) as error:
        escenario.verificar(pedro, PIN, hora="10:11")
    assert (error.value.codigo, error.value.status_http) == ("PIN_BLOQUEADO", 429)
    assert escenario.verificar(juan, PIN, hora="10:11").id == escenario.marta


def test_seg04_con_intentos_pin_max_3_el_tercer_fallo_bloquea(
    sesion: Session, reloj: RelojAjustable
) -> None:
    e = Escenario(sesion, reloj, intentos_pin_max=3)
    pedro = e.vendedor()

    e.falla(pedro, "10:00")
    e.falla(pedro, "10:01")
    assert e.verificar(pedro, PIN, hora="10:02").id == e.marta  # dos fallos: no bloquea
    e.falla(pedro, "10:03")  # el tercero bloquea

    with pytest.raises(PinBloqueadoError):
        e.verificar(pedro, PIN, hora="10:04")


def test_seg04_los_fallos_de_otro_usuario_no_bloquean_al_par(escenario: Escenario) -> None:
    pedro, juan = escenario.vendedor(), escenario.vendedor()
    for hora in ("10:00", "10:01", "10:02", "10:03"):
        escenario.falla(pedro, hora)
    for hora in ("10:04", "10:05", "10:06", "10:07"):
        escenario.falla(juan, hora)

    assert escenario.verificar(pedro, PIN, hora="10:08").id == escenario.marta
    assert escenario.verificar(juan, PIN, hora="10:08").id == escenario.marta


# --- tope general (SEG-04) -----------------------------------------------------------------


def test_seg04_veinte_fallos_de_cuatro_usuarios_bloquean_a_todos_con_el_mismo_codigo_y_mensaje(
    sesion: Session, reloj: RelojAjustable
) -> None:
    e = Escenario(sesion, reloj, intentos_pin_max=10)
    usuarios = [e.vendedor() for _ in range(4)]
    quinto = e.vendedor()
    segundo = 0
    for usuario in usuarios:
        for _ in range(5):
            e.falla(usuario, f"10:{segundo // 60:02d}:{segundo % 60:02d}")
            segundo += 30

    errores = []
    for usuario in (*usuarios, quinto):
        with pytest.raises(PinBloqueadoError) as error:
            e.verificar(usuario, PIN, hora="10:12")
        errores.append((error.value.codigo, error.value.status_http, str(error.value)))

    assert len(set(errores)) == 1
    assert errores[0][:2] == ("PIN_BLOQUEADO", 429)


def test_seg04_diecinueve_fallos_de_cuatro_usuarios_no_bloquean_a_nadie(
    sesion: Session, reloj: RelojAjustable
) -> None:
    e = Escenario(sesion, reloj, intentos_pin_max=10)
    usuarios = [e.vendedor() for _ in range(4)]
    otro = e.vendedor()
    segundo = 0
    for indice, usuario in enumerate(usuarios):
        for _ in range(5 if indice < 3 else 4):
            e.falla(usuario, f"10:{segundo // 60:02d}:{segundo % 60:02d}")
            segundo += 30

    assert e.verificar(otro, PIN, hora="10:12").id == e.marta
    assert e.verificar(usuarios[0], PIN, hora="10:12").id == e.marta


# --- 15 minutos desde el último fallo; los intentos bloqueados no cuentan -------------------


def test_seg04_un_intento_durante_el_bloqueo_no_verifica_no_cuenta_y_no_mueve_el_desbloqueo(
    escenario: Escenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    pedro = escenario.vendedor()
    _bloquear_a_pedro(escenario, pedro)
    antes = len(escenario.filas())
    derivaciones: list[int] = []
    original = seguridad.verificar_pin_autorizacion

    def espia(*args: Any, **kwargs: Any) -> bool:
        derivaciones.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(identidad_service, "verificar_pin_autorizacion", espia)

    for hora in ("10:11", "10:15", "10:20"):  # incluso con el PIN correcto
        with pytest.raises(PinBloqueadoError):
            escenario.verificar(pedro, PIN, hora=hora)

    assert derivaciones == []
    assert len(escenario.filas()) == antes
    # El último fallo contado fue 10:10: a las 10:25 se desbloquea.
    assert escenario.verificar(pedro, PIN, hora="10:25").id == escenario.marta


def test_seg04_pasado_el_bloqueo_el_siguiente_fallo_es_el_primero(escenario: Escenario) -> None:
    pedro = escenario.vendedor()
    _bloquear_a_pedro(escenario, pedro)

    escenario.falla(pedro, "10:26")  # primero de una ventana nueva

    for hora in ("10:27", "10:28", "10:29"):
        escenario.falla(pedro, hora)
    assert escenario.verificar(pedro, PIN, hora="10:30").id == escenario.marta  # cuatro: no bloquea
    escenario.falla(pedro, "10:31")
    with pytest.raises(PinBloqueadoError):
        escenario.verificar(pedro, PIN, hora="10:32")


def test_seg04_los_fallos_a_15_minutos_o_mas_no_cuentan(escenario: Escenario) -> None:
    pedro = escenario.vendedor()
    for hora in ("10:00", "10:01", "10:02", "10:03"):
        escenario.falla(pedro, hora)

    escenario.falla(pedro, "10:15")  # los tres primeros ya están fuera de la ventana: 2 en total

    assert escenario.verificar(pedro, PIN, hora="10:16").id == escenario.marta


# --- el fallo sobrevive al rollback del comando --------------------------------------------


def test_inv01_el_fallo_queda_aunque_la_transaccion_del_comando_se_revierta(
    escenario: Escenario,
) -> None:
    pedro = escenario.vendedor()
    with pytest.raises(PinIncorrectoError):
        escenario.verificar(pedro, PIN_MALO, hora="10:02")
    escenario.sesion.rollback()  # el comando se revierte

    (fila,) = escenario.filas()
    assert fila["intentante_id"] == pedro
    assert fila["autorizador_id"] == escenario.marta
    assert fila["creado_en"] == MAÑANA.replace(hour=10, minute=2)


def test_el_pin_correcto_no_escribe_nada(escenario: Escenario) -> None:
    pedro = escenario.vendedor()

    escenario.verificar(pedro, PIN, hora="10:02")

    assert escenario.filas() == []
    assert escenario.exitos_de_verificacion() == []
    assert escenario.bloqueos_auditados() == []


# --- auditoría (una fila por bloqueo, nunca el PIN) ---------------------------------------


def test_aud01_un_bloqueo_deja_una_fila_de_auditoria_con_alcance_intentante_y_hasta(
    escenario: Escenario,
) -> None:
    pedro = escenario.vendedor()
    for hora in ("10:02", "10:05", "10:07", "10:09"):
        escenario.falla(pedro, hora)
    assert escenario.bloqueos_auditados() == []

    escenario.falla(pedro, "10:10")  # el quinto bloquea

    (fila,) = escenario.bloqueos_auditados()
    assert fila["entidad"] == "usuario"
    assert fila["entidad_id"] == escenario.marta
    assert fila["usuario_id"] == pedro
    assert fila["despues"]["alcance"] == "USUARIO"
    assert fila["despues"]["intentante_id"] == str(pedro)
    assert datetime.fromisoformat(fila["despues"]["hasta"]) == MAÑANA.replace(hour=10, minute=25)
    assert PIN_MALO not in fila["despues_texto"]


def test_aud01_los_intentos_rechazados_por_el_bloqueo_no_dejan_auditoria(
    escenario: Escenario,
) -> None:
    pedro = escenario.vendedor()
    _bloquear_a_pedro(escenario, pedro)

    for hora in ("10:11", "10:12", "10:13"):
        with pytest.raises(PinBloqueadoError):
            escenario.verificar(pedro, PIN, hora=hora)

    assert len(escenario.bloqueos_auditados()) == 1


def test_aud01_un_fallo_que_alcanza_los_dos_limites_deja_dos_filas(
    sesion: Session, reloj: RelojAjustable, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(identidad_service, "LIMITE_FALLOS_PIN_POR_AUTORIZADOR", 2)
    e = Escenario(sesion, reloj, intentos_pin_max=2)
    pedro = e.vendedor()

    e.falla(pedro, "10:00")
    e.falla(pedro, "10:01")

    alcances = sorted(f["despues"]["alcance"] for f in e.bloqueos_auditados())
    assert alcances == ["GENERAL", "USUARIO"]


def test_aud01_el_tope_general_audita_con_alcance_general(
    sesion: Session, reloj: RelojAjustable, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(identidad_service, "LIMITE_FALLOS_PIN_POR_AUTORIZADOR", 3)
    e = Escenario(sesion, reloj, intentos_pin_max=10)
    a, b, c = e.vendedor(), e.vendedor(), e.vendedor()

    e.falla(a, "10:00")
    e.falla(b, "10:01")
    e.falla(c, "10:02")

    (fila,) = e.bloqueos_auditados()
    assert fila["despues"]["alcance"] == "GENERAL"
    assert fila["usuario_id"] == c
    assert datetime.fromisoformat(fila["despues"]["hasta"]) == MAÑANA.replace(hour=10, minute=17)


# --- registro (WARNING, sin el valor) ------------------------------------------------------


def test_sec04_cada_fallo_y_cada_rechazo_por_bloqueo_van_al_log_sin_el_pin(
    escenario: Escenario, caplog: pytest.LogCaptureFixture
) -> None:
    pedro = escenario.vendedor()
    with caplog.at_level(logging.WARNING):
        _bloquear_a_pedro(escenario, pedro)
        with pytest.raises(PinBloqueadoError):
            escenario.verificar(pedro, PIN, hora="10:11")

    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(avisos) == 6
    for registro in avisos:
        mensaje = registro.getMessage()
        assert str(escenario.marta) in mensaje
        assert str(pedro) in mensaje
        assert str(escenario.dispositivo) in mensaje
    assert PIN not in caplog.text
    assert PIN_MALO not in caplog.text


# --- el desbloqueo por definir el PIN es la tarea 6.6; acá solo que el cupo es por autorizador --


def test_el_bloqueo_de_un_autorizador_no_afecta_a_otro(escenario: Escenario) -> None:
    lucia = escenario.usuario(frozenset({PERMISO}), con_pin="735194")
    pedro = escenario.vendedor()
    _bloquear_a_pedro(escenario, pedro)

    resultado = identidad_service.verificar_pin_de_autorizacion(
        escenario.org,
        escenario.sesion,
        escenario.reloj,
        autorizador_id=lucia,
        intentante_id=pedro,
        pin="735194",
        permiso=PERMISO,
    )

    assert resultado.id == lucia
