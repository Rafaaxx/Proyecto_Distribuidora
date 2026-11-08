"""Arnes compartido de las pruebas de backup (change 27a, Lote 3; D10 a D13).

Levanta un PostgreSQL 17 real con los scripts de roles de produccion montados como los monta el
compose (`/docker-entrypoint-initdb.d`), migra con `app_migrations` y construye la imagen de
`infra/backup/`. Todo con el SDK de Docker; si no hay motor de contenedores, falla con un
mensaje claro (igual que las pruebas de integracion).
"""

import os
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

RAIZ = Path(__file__).resolve().parents[3]
BACKEND = RAIZ / "backend"
INFRA = RAIZ / "infra"

IMAGEN_POSTGRES = "postgres:17"
SUPERUSUARIO = "distribuidora"
BASE = "distribuidora"
CLAVE_SUPER = "super-solo-pruebas"
CLAVE_MIGRACIONES = "migraciones-solo-pruebas"
CLAVE_RUNTIME = "runtime-solo-pruebas"
CLAVE_BACKUP = "backup-solo-pruebas"
ALIAS_BASE = "postgres"


@dataclass
class BaseMigrada:
    """Base de produccion de prueba: migrada, con datos y con los tres roles."""

    cliente: object
    red: str
    puerto: int

    def url(self, usuario: str, clave: str) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=usuario,
            password=clave,
            host="localhost",
            port=self.puerto,
            database=BASE,
        )


@pytest.fixture(scope="session")
def docker_cliente():
    try:
        import docker

        cliente = docker.from_env()
        cliente.ping()
    except Exception:
        pytest.fail(
            "No hay motor de contenedores disponible: las pruebas de backup necesitan Docker "
            "(docs/02-arquitectura.md §15).",
            pytrace=False,
        )
    yield cliente
    cliente.close()


@pytest.fixture(scope="session")
def base_migrada(docker_cliente) -> Iterator[BaseMigrada]:
    red = docker_cliente.networks.create(f"ensayo-backup-{uuid.uuid4().hex[:8]}")
    contenedor = docker_cliente.containers.run(
        IMAGEN_POSTGRES,
        detach=True,
        environment={
            "POSTGRES_USER": SUPERUSUARIO,
            "POSTGRES_PASSWORD": CLAVE_SUPER,
            "POSTGRES_DB": BASE,
            "APP_MIGRATIONS_DB_PASSWORD": CLAVE_MIGRACIONES,
            "APP_RUNTIME_DB_PASSWORD": CLAVE_RUNTIME,
            "APP_BACKUP_DB_PASSWORD": CLAVE_BACKUP,
        },
        volumes={
            str(INFRA / "postgres" / "init-app-roles.sh"): {
                "bind": "/docker-entrypoint-initdb.d/10-init-app-roles.sh",
                "mode": "ro",
            },
            str(INFRA / "postgres" / "20-init-backup-role.sh"): {
                "bind": "/docker-entrypoint-initdb.d/20-init-backup-role.sh",
                "mode": "ro",
            },
        },
        ports={"5432/tcp": None},
        network=red.name,
        labels={"ensayo": "backup-27a"},
    )
    red.disconnect(contenedor)
    red.connect(contenedor, aliases=[ALIAS_BASE])
    try:
        puerto = _esperar_base(docker_cliente, contenedor)
        base = BaseMigrada(cliente=docker_cliente, red=red.name, puerto=puerto)
        _migrar_y_sembrar(base)
        yield base
    finally:
        contenedor.remove(force=True, v=True)
        red.remove()


def _esperar_base(cliente, contenedor) -> int:
    # La imagen arranca dos veces (inicializacion y servicio): se espera a que acepte
    # conexiones con el rol de migraciones, que solo existe tras correr los scripts.
    limite = time.time() + 120
    while time.time() < limite:
        contenedor.reload()
        puertos = contenedor.attrs["NetworkSettings"]["Ports"].get("5432/tcp")
        if puertos:
            puerto = int(puertos[0]["HostPort"])
            try:
                motor = create_engine(
                    URL.create(
                        "postgresql+psycopg",
                        username="app_backup",
                        password=CLAVE_BACKUP,
                        host="localhost",
                        port=puerto,
                        database=BASE,
                    )
                )
                with motor.connect() as c:
                    c.execute(text("SELECT 1"))
                motor.dispose()
                return puerto
            except Exception:
                pass
        time.sleep(1)
    raise RuntimeError("PostgreSQL de prueba no arranco a tiempo")


def _migrar_y_sembrar(base: BaseMigrada) -> None:
    url = base.url("app_migrations", CLAVE_MIGRACIONES).render_as_string(hide_password=False)
    entorno = {**os.environ, "DATABASE_URL_MIGRATIONS": url}
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=entorno,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    motor = create_engine(base.url("app_migrations", CLAVE_MIGRACIONES))
    with motor.begin() as c:
        c.execute(
            text(
                "INSERT INTO organizacion "
                "(id, slug, nombre, moneda, zona_horaria, estado, actualizado_en) "
                "VALUES (gen_random_uuid(), 'prueba', 'Distribuidora de prueba', 'ARS', "
                "'America/Argentina/Mendoza', 'ACTIVA', now())"
            )
        )
        # Una secuencia con valor: pg_dump debe llevarla (SEQUENCE SET) con el rol de solo lectura.
        c.execute(text("CREATE SEQUENCE secuencia_de_prueba"))
        c.execute(text("SELECT nextval('secuencia_de_prueba')"))
    motor.dispose()


@pytest.fixture(scope="session")
def imagen_backup(docker_cliente) -> str:
    etiqueta = "distribuidora-backup:ensayo"
    docker_cliente.images.build(path=str(INFRA / "backup"), tag=etiqueta, rm=True)
    return etiqueta


class Corredor:
    """Corre comandos `sh` dentro de la imagen de backup, en la red de la base de prueba."""

    def __init__(self, cliente, imagen: str, red: str) -> None:
        self.cliente, self.imagen, self.red = cliente, imagen, red

    def correr(
        self,
        script: str,
        entorno: dict[str, str] | None = None,
        red: bool = True,
    ) -> tuple[int, str]:
        env = {
            "PGHOST": ALIAS_BASE,
            "PGUSER": "app_backup",
            "PGPASSWORD": CLAVE_BACKUP,
            "PGDATABASE": BASE,
            "BACKUP_DIR": "/tmp/respaldos",
            "BACKUP_RETENCION": "7",
            "TZ": "America/Argentina/Mendoza",
            **(entorno or {}),
        }
        c = self.cliente.containers.create(
            self.imagen,
            entrypoint=["sh", "-c", script],
            environment=env,
            network=self.red if red else "none",
        )
        try:
            c.start()
            codigo = c.wait()["StatusCode"]
            salida = c.logs(stdout=True, stderr=True).decode("utf-8", "replace")
        finally:
            c.remove(force=True)
        return codigo, salida


@pytest.fixture(scope="session")
def corredor(docker_cliente, base_migrada, imagen_backup) -> Corredor:
    return Corredor(docker_cliente, imagen_backup, base_migrada.red)
