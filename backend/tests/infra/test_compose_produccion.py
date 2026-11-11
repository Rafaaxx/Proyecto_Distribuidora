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
    "APP_MANTENIMIENTO_DB_PASSWORD",
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
    # Puerto del contenedor: lo que sigue al ultimo ":" sin el protocolo.
    publicados = {str(p).rsplit(":", 1)[1].split("/")[0] for p in servicios["caddy"]["ports"]}
    assert publicados == {"80", "443"}
    assert any(str(p).endswith("/udp") for p in servicios["caddy"]["ports"])


def test_los_puertos_publicados_de_caddy_son_variables_con_el_80_y_el_443_por_defecto(servicios):
    # Change 28, D13: el entorno de aceptacion corre al lado del de desarrollo y necesita otros
    # puertos; en produccion, sin tocar nada, siguen siendo el 80 y el 443.
    puertos = [str(p) for p in servicios["caddy"]["ports"]]
    assert "${CADDY_HTTP_PORT:-80}:80" in puertos
    assert "${CADDY_HTTPS_PORT:-443}:443" in puertos
    assert "${CADDY_HTTPS_PORT:-443}:443/udp" in puertos


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
    # Change 28, D13: la subred es una variable (por defecto 172.30.10.0/24) para que el entorno
    # de aceptacion conviva con otro proyecto que ya ocupa esa; las dos referencias son la misma.
    assert subred == "${FRENTE_SUBRED:-172.30.10.0/24}"
    ipaddress.ip_network(subred.removeprefix("${FRENTE_SUBRED:-").removesuffix("}"))
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


def test_postgres_crea_el_rol_de_mantenimiento_con_contrasena_obligatoria(servicios):
    # Change 28, D3 (escenario «Falta la contraseña del rol de mantenimiento»): el script del
    # rol se monta en produccion y en desarrollo; sin la variable no se levanta nada.
    montajes = servicios["postgres"]["volumes"]
    assert any(
        m.startswith("./infra/postgres/30-init-mantenimiento-role.sh:")
        and m.endswith(":/docker-entrypoint-initdb.d/30-init-mantenimiento-role.sh:ro")
        for m in montajes
    ), montajes
    valor = _entorno(servicios["postgres"])["APP_MANTENIMIENTO_DB_PASSWORD"]
    assert valor.startswith("${APP_MANTENIMIENTO_DB_PASSWORD:?")
    assert "APP_MANTENIMIENTO_DB_PASSWORD" in valor[len("${APP_MANTENIMIENTO_DB_PASSWORD:?") :]


def test_el_compose_de_desarrollo_tambien_crea_el_rol_de_mantenimiento():
    # Sin el rol la migracion del change 28 falla: el entorno de desarrollo lo crea igual.
    dev = yaml.safe_load((RAIZ / "docker-compose.yml").read_text(encoding="utf-8"))
    postgres = dev["services"]["postgres"]
    assert any(
        m.startswith("./infra/postgres/30-init-mantenimiento-role.sh:")
        and m.endswith(":/docker-entrypoint-initdb.d/30-init-mantenimiento-role.sh:ro")
        for m in postgres["volumes"]
    ), postgres["volumes"]
    assert _entorno(postgres)["APP_MANTENIMIENTO_DB_PASSWORD"].startswith(
        "${APP_MANTENIMIENTO_DB_PASSWORD:?"
    )


def test_ningun_otro_servicio_recibe_la_contrasena_de_mantenimiento(servicios):
    # Solo postgres (para crear el rol): el backend, las migraciones y el backup no la conocen.
    # El servicio `tareas` (Lote 2) se conecta con ese rol y lo verifica su propia prueba.
    for nombre, servicio in servicios.items():
        if nombre in ("postgres", "tareas"):
            continue
        assert "APP_MANTENIMIENTO_DB_PASSWORD" not in str(servicio), nombre


def test_backup_usa_el_rol_de_solo_lectura_y_solo_la_red_de_datos(servicios):
    b = servicios["backup"]
    env = _entorno(b)
    assert env["PGUSER"] == "app_backup"
    assert env["PGHOST"] == "postgres"
    assert "APP_BACKUP_DB_PASSWORD" in env["PGPASSWORD"]
    assert set(env) >= {"BACKUP_HORA", "BACKUP_DIARIOS", "BACKUP_SEMANALES", "TZ", "BACKUP_DIR"}
    for prohibida in ("POSTGRES_PASSWORD", "APP_RUNTIME_DB_PASSWORD", "APP_MIGRATIONS_DB_PASSWORD"):
        assert prohibida not in env
    assert b["networks"] == ["datos"]
    assert "ports" not in b
    assert b["depends_on"]["postgres"]["condition"] == "service_healthy"


def test_backup_usa_la_retencion_14_mas_8_y_ya_no_backup_retencion(servicios):
    # Requisito «Retencion de 14 backups diarios y 8 semanales» (D1): configurable, 14 y 8.
    env = _entorno(servicios["backup"])
    assert "BACKUP_RETENCION" not in env
    assert env["BACKUP_DIARIOS"] == "${BACKUP_DIARIOS:-14}"
    assert env["BACKUP_SEMANALES"] == "${BACKUP_SEMANALES:-8}"
    assert "BACKUP_RETENCION" not in COMPOSE.read_text(encoding="utf-8")


def test_backup_corre_con_un_usuario_sin_privilegios(servicios):
    # Requisito «Los servicios de respaldo no corren como superusuario» (D11).
    usuario = servicios["backup"]["user"]
    assert usuario == "${BACKUP_UID:-999}:${BACKUP_GID:-999}"
    assert not usuario.startswith(("0:", "root"))


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


# --- Servicio `copia-externa` (change 27b, Lote 2; D4, D5, D6, D11) ----------------------------

SECRETOS_COPIA = (
    "COPIA_ACCESS_KEY_ID",
    "COPIA_SECRET_ACCESS_KEY",
    "COPIA_CLAVE_CIFRADO",
    "COPIA_SAL_CIFRADO",
)


def test_copia_externa_no_amplia_la_exposicion_ni_toca_la_base(compose, servicios):
    # Escenarios «Los servicios nuevos de respaldo no amplian la exposicion», «Roles de los
    # servicios de respaldo» (parte de `copia-externa`) y «El servicio de copia no puede llegar
    # a la base».
    s = servicios["copia-externa"]
    assert "ports" not in s
    assert s["networks"] == ["salida"]
    assert not compose["networks"]["salida"].get("internal", False)
    assert compose["networks"]["datos"]["internal"] is True
    assert "depends_on" not in s
    env = _entorno(s)
    assert not [v for v in env if v.startswith("PG") or "DB_PASSWORD" in v or "DATABASE" in v]
    for prohibida in ("POSTGRES_PASSWORD", "JWT_SECRET"):
        assert prohibida not in env


def test_copia_externa_lee_los_backups_solo_lectura_y_corre_sin_privilegios(servicios):
    s = servicios["copia-externa"]
    assert (
        s["image"]
        == "distribuidora-copia:${APP_VERSION:?Falta APP_VERSION en el archivo de entorno}"
    )
    assert s["build"]["dockerfile"] == "copia/Dockerfile"
    assert s["build"]["context"] == "./infra"
    montajes = s["volumes"]
    assert any(m.startswith("${BACKUP_DIR:?") and m.endswith(":/backups:ro") for m in montajes), (
        montajes
    )
    # La carpeta de `bajar` es una subcarpeta de BACKUP_DIR, montada aparte y con escritura.
    assert any(m.startswith("${BACKUP_DIR:?") and m.endswith("/bajados:/bajados") for m in montajes)
    assert s["user"] == "${BACKUP_UID:-999}:${BACKUP_GID:-999}"
    assert _entorno(s)["BACKUP_DIR"] == "/backups"


def test_copia_externa_se_reinicia_declara_salud_y_rota_registros(servicios):
    s = servicios["copia-externa"]
    assert s["restart"] == "unless-stopped"
    assert "salud.sh" in " ".join(s["healthcheck"]["test"])
    assert s["healthcheck"]["interval"]
    assert s["logging"]["options"]["max-size"] == "10m"


def test_copia_externa_recibe_la_configuracion_del_destino_y_la_retencion(servicios):
    env = _entorno(servicios["copia-externa"])
    assert set(env) >= {
        "COPIA_TIPO", "COPIA_RUTA", "COPIA_S3_PROVEEDOR", "COPIA_S3_ENDPOINT", "COPIA_S3_REGION",
        "BACKUP_DIARIOS", "BACKUP_SEMANALES", "TZ", "AVISO_URL", *SECRETOS_COPIA,
    }  # fmt: skip
    assert env["BACKUP_DIARIOS"] == "${BACKUP_DIARIOS:-14}"
    assert env["BACKUP_SEMANALES"] == "${BACKUP_SEMANALES:-8}"


def test_los_secretos_de_la_copia_externa_exigen_valor_y_nombran_la_variable():
    # Escenario «Falta la clave de cifrado de la copia externa».
    texto = COMPOSE.read_text(encoding="utf-8")
    for secreto in SECRETOS_COPIA:
        usos = re.findall(r"\$\{" + secreto + r"([^}]*)\}", texto)
        assert usos, f"{secreto} no se usa en el compose"
        for resto in usos:
            assert resto.startswith(":?") and len(resto) > 2, f"{secreto}: {resto!r}"
    for variable in ("COPIA_TIPO", "COPIA_RUTA"):
        usos = re.findall(r"\$\{" + variable + r"([^}]*)\}", texto)
        assert usos and all(u.startswith(":?") and len(u) > 2 for u in usos)


def test_el_compose_se_niega_a_levantar_sin_la_clave_de_cifrado(tmp_path):
    # Escenario «Falta la clave de cifrado de la copia externa», ejecutado con `docker compose
    # config`: el error nombra la variable. Se omite si no esta el cliente de compose.
    import shutil
    import subprocess

    if shutil.which("docker") is None:
        pytest.skip("sin cliente docker: la lectura del compose cubre el escenario")
    base = {
        "POSTGRES_PASSWORD": "a", "APP_MIGRATIONS_DB_PASSWORD": "b", "APP_RUNTIME_DB_PASSWORD": "c",
        "APP_BACKUP_DB_PASSWORD": "d", "APP_MANTENIMIENTO_DB_PASSWORD": "m", "JWT_SECRET": "e" * 32,
        "DOMINIO": "localhost",
        "CADDY_TLS": "internal", "APP_VERSION": "0.27.0", "BACKUP_DIR": "/tmp/b",
        "COPIA_TIPO": "local", "COPIA_RUTA": "/destino-local/x", "COPIA_ACCESS_KEY_ID": "n",
        "COPIA_SECRET_ACCESS_KEY": "n", "COPIA_CLAVE_CIFRADO": "k", "COPIA_SAL_CIFRADO": "s",
    }  # fmt: skip

    def config(valores: dict[str, str]) -> subprocess.CompletedProcess[str]:
        archivo = tmp_path / "entorno.env"
        archivo.write_text("\n".join(f"{k}={v}" for k, v in valores.items()), encoding="utf-8")
        return subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE), "--env-file", str(archivo), "config", "-q"],
            capture_output=True, text=True, check=False, env=dict(__import__("os").environ),
        )  # fmt: skip

    assert config(base).returncode == 0
    for falta in ("COPIA_CLAVE_CIFRADO", "COPIA_SAL_CIFRADO"):
        r = config({k: v for k, v in base.items() if k != falta})
        assert r.returncode != 0 and falta in r.stderr, r.stderr


def test_el_compose_se_niega_a_levantar_sin_la_contrasena_del_rol_de_mantenimiento(tmp_path):
    # Escenario «Falta la contraseña del rol de mantenimiento», ejecutado con `docker compose
    # config`: no se levanta ningun servicio y el error nombra la variable.
    import shutil
    import subprocess

    if shutil.which("docker") is None:
        pytest.skip("sin cliente docker: la lectura del compose cubre el escenario")
    base = {
        "POSTGRES_PASSWORD": "a", "APP_MIGRATIONS_DB_PASSWORD": "b", "APP_RUNTIME_DB_PASSWORD": "c",
        "APP_BACKUP_DB_PASSWORD": "d", "JWT_SECRET": "e" * 32, "DOMINIO": "localhost",
        "CADDY_TLS": "internal", "APP_VERSION": "0.28.0", "BACKUP_DIR": "/tmp/b",
        "COPIA_TIPO": "local", "COPIA_RUTA": "/destino-local/x", "COPIA_ACCESS_KEY_ID": "n",
        "COPIA_SECRET_ACCESS_KEY": "n", "COPIA_CLAVE_CIFRADO": "k", "COPIA_SAL_CIFRADO": "s",
    }  # fmt: skip
    archivo = tmp_path / "entorno.env"
    archivo.write_text("\n".join(f"{k}={v}" for k, v in base.items()), encoding="utf-8")
    r = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "--env-file", str(archivo), "config", "-q"],
        capture_output=True, text=True, check=False, env=dict(__import__("os").environ),
    )  # fmt: skip
    assert r.returncode != 0 and "APP_MANTENIMIENTO_DB_PASSWORD" in r.stderr, r.stderr


# --- Restauracion y prueba periodica (27b, Lote 3; D8, D10, D11) -------------------------------

SIN_CONEXION_A_LA_BASE = ("PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE", "DATABASE_URL")


def test_prueba_restauracion_no_tiene_red_ni_credenciales_ni_puertos(compose, servicios):
    # Escenarios «Los servicios nuevos de respaldo no amplian la exposicion», «Roles de los
    # servicios de respaldo» y «La prueba no toca produccion» (D10).
    s = servicios["prueba-restauracion"]
    assert s["network_mode"] == "none"
    assert "networks" not in s and "ports" not in s
    assert "depends_on" not in s
    env = _entorno(s)
    assert not [v for v in env if v in SIN_CONEXION_A_LA_BASE or "PASSWORD" in v or "SECRET" in v]
    assert not [v for v in env if v.startswith("PG") or "DB_PASSWORD" in v or "DATABASE" in v]


def test_prueba_restauracion_lee_los_backups_solo_lectura_sin_privilegios_y_con_salud(servicios):
    s = servicios["prueba-restauracion"]
    montajes = s["volumes"]
    assert any(m.startswith("${BACKUP_DIR:?") and m.endswith(":/backups:ro") for m in montajes), (
        montajes
    )
    # Sin otro montaje del equipo con escritura: solo el volumen con el estado de la salud.
    assert [m for m in montajes if not m.endswith(":ro")] == ["estado_prueba:/estado-prueba"]
    assert s["user"] == "${BACKUP_UID:-999}:${BACKUP_GID:-999}"
    assert s["restart"] == "unless-stopped"
    assert "salud_prueba.sh" in " ".join(s["healthcheck"]["test"])
    assert s["healthcheck"]["interval"]
    assert s["logging"]["options"]["max-size"] == "10m"


def test_prueba_restauracion_arranca_el_programador_mensual_con_dia_y_hora(servicios):
    s = servicios["prueba-restauracion"]
    assert s["entrypoint"] == ["sh", "/opt/backup/programar_prueba.sh"]
    assert s["build"]["context"] == "./infra/backup"
    assert s["image"].startswith("distribuidora-prueba-restauracion:${APP_VERSION:?")
    env = _entorno(s)
    assert env["PRUEBA_DIA"] == "${PRUEBA_DIA:-1}"
    assert env["PRUEBA_HORA"] == "${PRUEBA_HORA:-04:00}"
    assert env["BACKUP_DIR"] == "/backups"
    assert env["TZ"] == "${TZ:-America/Argentina/Mendoza}"


def test_restauracion_esta_en_un_perfil_aparte_y_se_conecta_como_dueno_del_esquema(
    compose, servicios
):
    # Escenarios «Los servicios nuevos de respaldo no amplian la exposicion» (perfil que `up` no
    # arranca) y «Roles de los servicios de respaldo» (app_migrations, ADR-020, D8).
    s = servicios["restauracion"]
    assert s["profiles"] == ["restauracion"]
    assert "ports" not in s
    assert s["networks"] == ["datos"]
    assert s["restart"] == "no"
    env = _entorno(s)
    assert env["PGUSER"] == "app_migrations"
    assert env["PGHOST"] == "postgres"
    assert env["PGPASSWORD"].startswith("${APP_MIGRATIONS_DB_PASSWORD:?")
    assert env["BACKUP_DIR"] == "/backups"
    for prohibida in ("POSTGRES_PASSWORD", "APP_RUNTIME_DB_PASSWORD", "APP_BACKUP_DB_PASSWORD",
                      "JWT_SECRET"):  # fmt: skip
        assert prohibida not in env and prohibida not in " ".join(env.values())


def test_restauracion_lee_los_backups_solo_lectura_y_corre_sin_privilegios(servicios):
    s = servicios["restauracion"]
    assert s["volumes"] and all(
        m.startswith("${BACKUP_DIR:?") and m.endswith(":/backups:ro") for m in s["volumes"]
    )
    assert s["user"] == "${BACKUP_UID:-999}:${BACKUP_GID:-999}"
    assert s["entrypoint"] == ["sh", "/opt/backup/restaurar.sh"]
    assert s["build"]["context"] == "./infra/backup"
    assert s["image"].startswith("distribuidora-restauracion:${APP_VERSION:?")


def test_solo_los_servicios_del_entorno_normal_arrancan_con_up(servicios):
    # `up` no arranca los servicios con perfil: la restauracion solo corre a pedido.
    con_perfil = {n for n, s in servicios.items() if s.get("profiles")}
    assert con_perfil == {"restauracion"}


def test_la_restauracion_usa_la_base_de_produccion_y_espera_a_que_este_sana(servicios):
    s = servicios["restauracion"]
    assert s["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert _entorno(s)["PGDATABASE"] == "${POSTGRES_DB:-distribuidora}"


def test_el_volumen_de_estado_de_la_prueba_esta_declarado(compose):
    assert "estado_prueba" in compose["volumes"]


@pytest.mark.parametrize(
    "nombre", ["backup", "copia-externa", "prueba-restauracion", "restauracion"]
)
def test_todo_servicio_de_respaldo_fija_la_zona_horaria(servicios, nombre):
    # Ajuste de la prueba manual: los registros de todos salen en la misma hora local.
    assert _entorno(servicios[nombre])["TZ"] == "${TZ:-America/Argentina/Mendoza}"


# --- Servicio `tareas` (change 28, Lote 2; D2, D3, D6) -----------------------------------------


def test_tareas_no_amplia_la_exposicion_y_declara_salud_restart_y_registros(servicios):
    # Escenario «El servicio de tareas no amplía la exposición».
    s = servicios["tareas"]
    assert "ports" not in s
    # `datos` (la base) y `salida` (solo saliente, para el aviso externo; ADR-073): ni `frente`,
    # y `datos` sigue sin salida a internet.
    assert set(s["networks"]) == {"datos", "salida"}
    assert "frente" not in s["networks"]
    assert s["restart"] == "unless-stopped"
    assert s["logging"] == servicios["backend"]["logging"]
    assert s["depends_on"]["postgres"]["condition"] == "service_healthy"
    # La migracion que crea la tabla y los permisos corre antes.
    assert s["depends_on"]["migraciones"]["condition"] == "service_completed_successfully"
    assert s["healthcheck"]["test"] == ["CMD", "python", "-m", "app.tareas", "salud"]


def test_tareas_usa_la_imagen_del_backend_y_se_puede_correr_a_pedido(servicios):
    # D2: misma imagen (mismo Dockerfile y contexto), orden `python -m app.tareas`; el
    # `entrypoint` hace que `run --rm tareas ahora` agregue `ahora` a la orden.
    s = servicios["tareas"]
    assert s["build"] == servicios["backend"]["build"]
    assert s["image"].startswith("distribuidora-tareas:")
    assert s["entrypoint"] == ["python", "-m", "app.tareas"]
    assert "command" not in s


def test_tareas_usa_su_propio_rol_y_ninguna_otra_contrasena(servicios):
    # Escenario «El servicio de tareas usa su propio rol» (ADR-018, ADR-020, D3).
    env = _entorno(servicios["tareas"])
    url = env["DATABASE_URL"]
    assert url.startswith(
        "postgresql+psycopg://app_mantenimiento:${APP_MANTENIMIENTO_DB_PASSWORD:?"
    )
    assert url.endswith("@postgres:5432/${POSTGRES_DB:-distribuidora}")
    for prohibida in (
        "POSTGRES_PASSWORD",
        "APP_RUNTIME_DB_PASSWORD",
        "APP_MIGRATIONS_DB_PASSWORD",
        "APP_BACKUP_DB_PASSWORD",
        "JWT_SECRET",
        "DATABASE_URL_MIGRATIONS",
    ):
        assert prohibida not in str(servicios["tareas"]), prohibida


def test_tareas_recibe_hora_zona_y_aviso_opcional(servicios):
    env = _entorno(servicios["tareas"])
    assert env["TAREAS_HORA"] == "${TAREAS_HORA:-05:00}"
    assert env["TZ"] == "${TZ:-America/Argentina/Mendoza}"
    # Variable propia (distinta de AVISO_URL de la copia): cada control del aviso es independiente.
    assert env["AVISO_TAREAS_URL"] == "${AVISO_TAREAS_URL:-}"
    assert "AVISO_URL" not in env


def test_tareas_sale_a_internet_solo_por_salida_y_datos_sigue_cerrada(compose, servicios):
    # ADR-073: `salida` tiene internet pero no ve ni Postgres ni el backend; `datos` sigue internal.
    assert compose["networks"]["datos"]["internal"] is True
    assert not compose["networks"]["salida"].get("internal", False)
    assert "ports" not in servicios["tareas"]
    assert "salida" not in servicios["postgres"]["networks"]
    assert "salida" not in servicios["backend"]["networks"]


def test_tareas_corre_sin_privilegios_y_sin_ningun_montaje(servicios):
    # Usa la imagen del backend, cuyo usuario no es root; el estado va a /tmp del contenedor.
    s = servicios["tareas"]
    assert "volumes" not in s
    assert "user" not in s  # el usuario `app` (10001) lo fija la imagen
