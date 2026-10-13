"""Change 15, tarea 12.1 (`design.md` D19, ADR-028 D9.3-B): `identidad` pregunta a `stock`, por un
puerto de registro, si un usuario tiene una jornada no cerrada en un dispositivo. Sin consulta
registrada el puerto responde "no hay jornada" (falla cerrado hacia el corte).

Reglas citadas: INV-21 (aislamiento por organización), INV-16 (jornada no cerrada).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

from app.modules.identidad import service as identidad_service
from app.modules.stock import service as stock_service

BACKEND = Path(__file__).resolve().parents[2]


def _jornada(sesion: Session, org: UUID, usuario: UUID, dispositivo: UUID, estado: str) -> None:
    ubicacion = crear_ubicacion_sql(sesion, org, requiere_toma=True, tipo="VEHICULO")
    crear_jornada_sql(
        sesion,
        org,
        usuario_id=usuario,
        dispositivo_id=dispositivo,
        ubicacion_id=ubicacion,
        estado=estado,
    )


class TestPuertoDeIdentidad:
    def test_sin_consulta_registrada_responde_que_no_hay_jornada(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(identidad_service, "_CONSULTA_JORNADA_NO_CERRADA", None)
        org = crear_organizacion(db_session).id
        usuario, dispositivo = crear_usuario_y_dispositivo(db_session, org)
        _jornada(db_session, org, usuario, dispositivo, "ABIERTA")

        assert (
            identidad_service.hay_jornada_no_cerrada(org, usuario, dispositivo, db_session) is False
        )

    def test_con_consulta_registrada_devuelve_lo_que_responde(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(identidad_service, "_CONSULTA_JORNADA_NO_CERRADA", None)
        llamadas: list[tuple[UUID, UUID, UUID]] = []

        def consulta(org: UUID, usuario: UUID, dispositivo: UUID, sesion: Session) -> bool:
            llamadas.append((org, usuario, dispositivo))
            return usuario == llamadas[0][1]

        identidad_service.registrar_consulta_jornada_no_cerrada(consulta)
        a, b, c = uuid4(), uuid4(), uuid4()

        assert identidad_service.hay_jornada_no_cerrada(a, b, c, db_session) is True
        assert identidad_service.hay_jornada_no_cerrada(a, uuid4(), c, db_session) is False
        assert llamadas[0] == (a, b, c)


class TestConsultaDeStock:
    @pytest.mark.parametrize("estado", ["ABIERTA", "EN_RENDICION"])
    def test_inv16_una_jornada_no_cerrada_del_usuario_en_el_dispositivo_es_verdadero(
        self, db_session: Session, estado: str
    ) -> None:
        org = crear_organizacion(db_session).id
        usuario, dispositivo = crear_usuario_y_dispositivo(db_session, org)
        _jornada(db_session, org, usuario, dispositivo, estado)

        assert stock_service.tiene_jornada_no_cerrada(org, usuario, dispositivo, db_session)

    @pytest.mark.parametrize("estado", ["CERRADA", "LIBERADA"])
    def test_una_jornada_terminada_es_falso(self, db_session: Session, estado: str) -> None:
        org = crear_organizacion(db_session).id
        usuario, dispositivo = crear_usuario_y_dispositivo(db_session, org)
        _jornada(db_session, org, usuario, dispositivo, estado)

        assert not stock_service.tiene_jornada_no_cerrada(org, usuario, dispositivo, db_session)

    def test_la_jornada_de_otro_usuario_o_de_otro_dispositivo_es_falso(
        self, db_session: Session
    ) -> None:
        org = crear_organizacion(db_session).id
        usuario, dispositivo = crear_usuario_y_dispositivo(db_session, org)
        otro_usuario, otro_dispositivo = crear_usuario_y_dispositivo(db_session, org)
        _jornada(db_session, org, otro_usuario, dispositivo, "ABIERTA")
        _jornada(db_session, org, usuario, otro_dispositivo, "ABIERTA")

        assert not stock_service.tiene_jornada_no_cerrada(org, usuario, dispositivo, db_session)
        assert stock_service.tiene_jornada_no_cerrada(org, otro_usuario, dispositivo, db_session)
        assert stock_service.tiene_jornada_no_cerrada(org, usuario, otro_dispositivo, db_session)

    def test_inv21_la_jornada_de_otra_organizacion_es_falso(self, db_session: Session) -> None:
        org = crear_organizacion(db_session).id
        otra = crear_organizacion(db_session).id
        usuario, dispositivo = crear_usuario_y_dispositivo(db_session, org)
        _jornada(db_session, org, usuario, dispositivo, "ABIERTA")

        assert not stock_service.tiene_jornada_no_cerrada(otra, usuario, dispositivo, db_session)


class TestRegistroAlArrancar:
    def test_tras_importar_app_main_la_consulta_de_stock_esta_registrada(self) -> None:
        codigo = (
            "import app.main\n"
            "from app.modules.identidad import service as s\n"
            "from app.modules.stock import service as t\n"
            "assert s._CONSULTA_JORNADA_NO_CERRADA is t.tiene_jornada_no_cerrada\n"
        )
        resultado = subprocess.run(
            [sys.executable, "-c", codigo],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            check=False,
        )
        assert resultado.returncode == 0, resultado.stderr
