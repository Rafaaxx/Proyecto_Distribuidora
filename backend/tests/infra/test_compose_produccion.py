"""Compose de producción (change 27a, Lote 2; D3, D7, D8, D14).

Lee `docker-compose.prod.yml` con PyYAML: no requiere Docker. Cita INV-05,
ADR-020 y `docs/02-arquitectura.md` §16.2. El servicio `backup` llega con el
Lote 3 (tarea 3.5), que amplía estas pruebas.
"""

import ipaddress
import re
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

RAIZ = Path(__file__).resolve().parents[3]
COMPOSE = RAIZ / "docker-compose.prod.yml"

SECRETOS = (
    "POSTGRES_PASSWORD",
    "APP_MIGRATIONS_DB_PASSWORD",
    "APP_RUNTIME_DB_PASSWORD",
    "APP_BACKUP_DB_PASSWORD",
    "JWT_SECRET",
)
LARGA_VIDA = ("caddy", "backend", "postgres", "backup")


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    cargado: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return cargado


@pytest.fixture(scope="module")
def servicios(compose: dict[str, Any]) -> dict[str, Any]:
    servicios: dict[str, Any] = compose["services"]
    return servicios


def _entorno(servicio: dict[str, Any]) -> dict[str, str]:
    env = servicio.get("environment", {})
    if isinstance(env, list):
        return dict(item.split("=", 1) for item in env)
    return {k: str(v) for k, v in env.items()}


def test_proyecto_y_servicios(compose, servicios):
    assert compose["name"] == "distribuidora"
    assert {"caddy", "backend", "postgres", "migraciones"} <= set(servicios)


def test_solo_caddy_publica_puertos(servicios):
    # Spec: «El compose de producción no publica la base ni el backend».
    con_puertos = {n for n, s in servicios.items() if s.get("ports")}
    assert con_puertos == {"caddy"}
    publicados = {str(p).split(":")[1].split("/")[0] for p in servicios["caddy"]["ports"]}
    assert publicados == {"80", "443"}
    assert any(str(p).endswith("/udp") for p in servicios["caddy"]["ports"])


def test_redes_frente_y_datos(compose, servicios):
    redes = compose["networks"]
    assert redes["datos"]["internal"] is True
    assert not redes["frente"].get("internal", False)
    assert set(servicios["caddy"]["networks"]) == {"frente"}
    assert set(servicios["backend"]["networks"]) == {"frente", "datos"}
    assert set(servicios["postgres"]["networks"]) == {"datos"}
    assert set(servicios["migraciones"]["networks"]) == {"datos"}


def test_frente_tiene_subred_fija_igual_a_forwarded_allow_ips(compose, servicios):
    subred = compose["networks"]["frente"]["ipam"]["config"][0]["subnet"]
    ipaddress.ip_network(subred)
    assert _entorno(servicios["backend"])["FORWARDED_ALLOW_IPS"] == subred


def test_backend_usa_app_runtime_y_no_conoce_la_conexion_de_migraciones(servicios):
    env = _entorno(servicios["backend"])
    assert "DATABASE_URL_MIGRATIONS" not in env
    assert env["DATABASE_URL"].startswith("postgresql+psycopg://app_runtime:")
    assert "@postgres:5432/" in env["DATABASE_URL"]
    assert env["ENVIRONMENT"] == "production"


def test_migraciones_usa_app_migrations_y_termina(servicios):
    s = servicios["migraciones"]
    env = _entorno(s)
    assert env["DATABASE_URL_MIGRATIONS"].startswith("postgresql+psycopg://app_migrations:")
    assert "DATABASE_URL" not in env
    assert s["command"] == ["alembic", "upgrade", "head"]
    assert s["restart"] == "no"
    assert s["depends_on"]["postgres"]["condition"] == "service_healthy"


def test_backend_y_migraciones_se_construyen_del_mismo_codigo(servicios):
    # Nombres distintos: dos servicios no pueden construir el mismo nombre de imagen en paralelo.
    assert servicios["backend"]["image"] != servicios["migraciones"]["image"]
    assert servicios["backend"]["build"] == servicios["migraciones"]["build"]
    assert servicios["backend"]["build"]["dockerfile"] == "Dockerfile.produccion"
    assert servicios["migraciones"]["build"]["dockerfile"] == "Dockerfile.produccion"


def test_dependencias_de_arranque(servicios):
    dep_backend = servicios["backend"]["depends_on"]
    assert dep_backend["postgres"]["condition"] == "service_healthy"
    assert dep_backend["migraciones"]["condition"] == "service_completed_successfully"
    assert servicios["caddy"]["depends_on"]["backend"]["condition"] == "service_healthy"


@pytest.mark.parametrize("nombre", LARGA_VIDA)
def test_servicios_de_larga_vida_se_reinician_y_declaran_salud(servicios, nombre):
    s = servicios[nombre]
    assert s["restart"] == "unless-stopped"
    assert s["healthcheck"]["test"]
    assert s["healthcheck"]["interval"]


def test_salud_de_backend_y_postgres(servicios):
    assert "/api/v1/salud" in " ".join(servicios["backend"]["healthcheck"]["test"])
    assert "pg_isready" in " ".join(servicios["postgres"]["healthcheck"]["test"])
    # El punto de administracion de Caddy escucha solo en IPv4: `localhost` resuelve a ::1 y falla.
    assert "http://127.0.0.1:2019/" in " ".join(servicios["caddy"]["healthcheck"]["test"])


@pytest.mark.parametrize("nombre", [*LARGA_VIDA, "migraciones"])
def test_registros_rotan(servicios, nombre):
    # Spec: «Registros acotados».
    log = servicios[nombre]["logging"]
    assert log["driver"] == "json-file"
    assert log["options"]["max-size"] == "10m"
    assert log["options"]["max-file"] == "5"


def test_postgres_solo_monta_el_script_de_roles_y_su_volumen(compose, servicios):
    montajes = servicios["postgres"]["volumes"]
    assert "postgres_data:/var/lib/postgresql/data" in montajes
    assert any("init-app-roles.sh" in m and m.endswith(":ro") for m in montajes)
    assert {"postgres_data", "caddy_data", "caddy_config"} <= set(compose["volumes"])


def test_backend_y_migraciones_no_reciben_la_contrasena_del_superusuario(servicios):
    for nombre in ("backend", "migraciones"):
        env = _entorno(servicios[nombre])
        assert "POSTGRES_PASSWORD" not in env


def test_todo_secreto_exige_valor_y_sin_valor_por_defecto():
    texto = COMPOSE.read_text(encoding="utf-8")
    for secreto in SECRETOS:
        usos = re.findall(r"\$\{" + secreto + r"([^}]*)\}", texto)
        assert usos, f"{secreto} no se usa en el compose"
        for resto in usos:
            assert resto.startswith(":?"), f"{secreto} sin ':?' ({resto!r})"
            assert len(resto) > 2, f"{secreto}: falta el mensaje del error"


def test_las_variables_obligatorias_no_secretas_tambien_exigen_valor():
    texto = COMPOSE.read_text(encoding="utf-8")
    for variable in ("DOMINIO", "CADDY_TLS", "APP_VERSION"):
        usos = re.findall(r"\$\{" + variable + r"([^}]*)\}", texto)
        assert usos, f"{variable} no se usa en el compose"
        assert all(u.startswith(":?") for u in usos)


def test_caddy_recibe_dominio_y_modo_de_certificado(servicios):
    env = _entorno(servicios["caddy"])
    assert set(env) >= {"DOMINIO", "CADDY_TLS"}
    build = servicios["caddy"]["build"]
    assert build["dockerfile"] == "infra/caddy/Dockerfile"
    assert "APP_VERSION" in build["args"]


def test_ningun_valor_literal_parece_un_secreto():
    texto = COMPOSE.read_text(encoding="utf-8")
    assert not re.search(r"^\s*\w*(PASSWORD|SECRET)\s*:\s*[^$\s'\"]", texto, re.MULTILINE)


def test_postgres_crea_el_rol_de_backup_solo_en_produccion(servicios):
    # D11: el script del rol se monta solo aqui; el compose de desarrollo no lo conoce.
    montajes = servicios["postgres"]["volumes"]
    assert any(
        m.startswith("./infra/postgres/20-init-backup-role.sh:") and m.endswith(":ro")
        for m in montajes
    )
    assert "APP_BACKUP_DB_PASSWORD" in _entorno(servicios["postgres"])
    dev = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert "20-init-backup-role" not in dev
    assert "app_backup" not in dev


def test_backup_usa_el_rol_de_solo_lectura_y_solo_la_red_de_datos(servicios):
    b = servicios["backup"]
    env = _entorno(b)
    assert env["PGUSER"] == "app_backup"
    assert env["PGHOST"] == "postgres"
    assert "APP_BACKUP_DB_PASSWORD" in env["PGPASSWORD"]
    assert set(env) >= {"BACKUP_HORA", "BACKUP_RETENCION", "TZ", "BACKUP_DIR"}
    for prohibida in ("POSTGRES_PASSWORD", "APP_RUNTIME_DB_PASSWORD", "APP_MIGRATIONS_DB_PASSWORD"):
        assert prohibida not in env
    assert b["networks"] == ["datos"]
    assert "ports" not in b
    assert b["depends_on"]["postgres"]["condition"] == "service_healthy"


def test_backup_se_construye_de_su_propia_imagen_y_la_salud_la_da_salud_sh(servicios):
    b = servicios["backup"]
    assert b["build"]["context"] == "./infra/backup"
    assert b["image"].startswith("distribuidora-backup:")
    assert "salud.sh" in " ".join(b["healthcheck"]["test"])


def test_backup_escribe_en_una_carpeta_del_equipo_fuera_de_los_volumenes(compose, servicios):
    # Spec «Los backups viven fuera de los volumenes de Docker».
    montajes = servicios["backup"]["volumes"]
    assert len(montajes) == 1
    origen, destino = montajes[0].rsplit(":", 1)
    assert (
        origen.startswith("${BACKUP_DIR:?")
        and destino == _entorno(servicios["backup"])["BACKUP_DIR"]
    )
    assert not set(compose["volumes"]) & {"backups", "backup_data"}


def test_backup_dir_es_obligatorio():
    texto = COMPOSE.read_text(encoding="utf-8")
    usos = re.findall(r"\$\{BACKUP_DIR([^}]*)\}", texto)
    assert usos and all(u.startswith(":?") and len(u) > 2 for u in usos)
