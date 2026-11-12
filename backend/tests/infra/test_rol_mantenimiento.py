"""Rol de mantenimiento (change 28, Lote 1, tarea 1.1; D3).

Specs `sistema/despliegue` («El rol de mantenimiento se crea en un entorno nuevo y en uno
existente», escenario «Falta la contraseña del rol de mantenimiento») y
`sistema/permisos-de-base-de-datos` («El rol de mantenimiento solo puede lo que sus tareas
necesitan»). Cita INV-05, ADR-018 y ADR-020. Postgres 17 real con los scripts montados como los
monta el compose.
"""

from pathlib import Path

import pytest
from conftest import CLAVE_MANTENIMIENTO, SUPERUSUARIO
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

RAIZ = Path(__file__).resolve().parents[3]
SCRIPT = RAIZ / "infra" / "postgres" / "30-init-mantenimiento-role.sh"


def test_el_script_usa_la_variable_sin_valor_por_defecto_y_no_pega_la_clave_en_el_sql():
    texto = SCRIPT.read_text(encoding="utf-8")
    assert "APP_MANTENIMIENTO_DB_PASSWORD:?" in texto
    # La contraseña viaja como variable de psql (:'clave'), no interpolada en el SQL.
    assert ":'clave'" in texto
    assert "PASSWORD '${" not in texto
    assert b"\r\n" not in SCRIPT.read_bytes()


def test_sin_la_contrasena_el_script_falla_nombrando_la_variable(docker_cliente):
    contenedor = docker_cliente.containers.create(
        "postgres:17",
        entrypoint=["bash", "/script.sh"],
        environment={"POSTGRES_USER": SUPERUSUARIO, "POSTGRES_DB": "distribuidora"},
        volumes={str(SCRIPT): {"bind": "/script.sh", "mode": "ro"}},
    )
    try:
        contenedor.start()
        codigo = contenedor.wait()["StatusCode"]
        salida = contenedor.logs(stdout=True, stderr=True).decode("utf-8", "replace")
    finally:
        contenedor.remove(force=True)
    assert codigo != 0
    assert "APP_MANTENIMIENTO_DB_PASSWORD" in salida


def test_con_una_contrasena_vacia_tambien_falla(docker_cliente):
    contenedor = docker_cliente.containers.create(
        "postgres:17",
        entrypoint=["bash", "/script.sh"],
        environment={
            "POSTGRES_USER": SUPERUSUARIO,
            "POSTGRES_DB": "distribuidora",
            "APP_MANTENIMIENTO_DB_PASSWORD": "",
        },
        volumes={str(SCRIPT): {"bind": "/script.sh", "mode": "ro"}},
    )
    try:
        contenedor.start()
        codigo = contenedor.wait()["StatusCode"]
        salida = contenedor.logs(stdout=True, stderr=True).decode("utf-8", "replace")
    finally:
        contenedor.remove(force=True)
    assert codigo != 0
    assert "APP_MANTENIMIENTO_DB_PASSWORD" in salida


def test_el_rol_se_crea_con_ingreso_y_la_contrasena_del_entorno(base_migrada):
    motor = create_engine(base_migrada.url("app_mantenimiento", CLAVE_MANTENIMIENTO))
    with motor.connect() as c:
        assert c.execute(text("SELECT current_user")).scalar_one() == "app_mantenimiento"
    motor.dispose()


def test_una_contrasena_equivocada_no_entra(base_migrada):
    motor = create_engine(base_migrada.url("app_mantenimiento", "otra-clave"))
    with pytest.raises(OperationalError), motor.connect():
        pass
    motor.dispose()


def test_el_script_es_repetible_y_no_cambia_la_contrasena_existente(base_migrada):
    # Segunda corrida sobre la misma base, con otra contraseña en el entorno: no falla y el rol
    # conserva la contraseña con la que se creó (el runbook no pisa un secreto vigente).
    codigo, salida = base_migrada.contenedor.exec_run(
        ["bash", "/docker-entrypoint-initdb.d/30-init-mantenimiento-role.sh"],
        environment={
            "POSTGRES_USER": SUPERUSUARIO,
            "POSTGRES_DB": "distribuidora",
            "APP_MANTENIMIENTO_DB_PASSWORD": "otra-clave-distinta",
        },
    )
    assert codigo == 0, salida.decode("utf-8", "replace")
    motor = create_engine(base_migrada.url("app_mantenimiento", CLAVE_MANTENIMIENTO))
    with motor.connect() as c:
        assert c.execute(text("SELECT 1")).scalar_one() == 1
    motor.dispose()
