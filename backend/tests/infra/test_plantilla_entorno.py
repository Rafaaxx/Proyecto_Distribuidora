"""Plantilla del archivo de entorno de producción (change 27a, Lote 2; D1, D8).

Spec `sistema/despliegue`, escenario «La plantilla no trae valores».
"""

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
PLANTILLA = RAIZ / "infra" / "produccion.env.example"
COMPOSE = RAIZ / "docker-compose.prod.yml"

SECRETOS = {
    "POSTGRES_PASSWORD",
    "APP_MIGRATIONS_DB_PASSWORD",
    "APP_RUNTIME_DB_PASSWORD",
    "APP_BACKUP_DB_PASSWORD",
    "JWT_SECRET",
}


def _asignaciones() -> dict[str, str]:
    resultado: dict[str, str] = {}
    for linea in PLANTILLA.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", linea.strip())
        if m:
            resultado[m.group(1)] = m.group(2)
    return resultado


def test_los_secretos_aparecen_sin_valor():
    asignaciones = _asignaciones()
    for secreto in SECRETOS:
        assert secreto in asignaciones, f"falta {secreto}"
        assert asignaciones[secreto] == "", f"{secreto} no debe traer valor"


def test_lista_todas_las_variables_que_usa_el_compose():
    usadas = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", COMPOSE.read_text(encoding="utf-8")))
    faltantes = usadas - set(_asignaciones())
    assert not faltantes, f"la plantilla no lista: {sorted(faltantes)}"


def test_incluye_las_variables_de_operacion_de_la_decision_d8():
    esperadas = {
        "DOMINIO", "CADDY_TLS", "APP_VERSION", "WEB_CONCURRENCY", "LOG_LEVEL", "JWT_KID",
        "BACKUP_DIR", "BACKUP_HORA", "BACKUP_RETENCION", "TZ",
    }  # fmt: skip
    assert esperadas <= set(_asignaciones())


def test_caddy_tls_reemplaza_a_acme_email_y_explica_los_dos_modos():
    texto = PLANTILLA.read_text(encoding="utf-8")
    assert "ACME_EMAIL" not in texto
    assert "internal" in texto
    assert "Let's Encrypt" in texto
    assert "localhost" in texto


def test_nada_con_aspecto_de_secreto_en_ninguna_linea():
    for linea in PLANTILLA.read_text(encoding="utf-8").splitlines():
        if linea.lstrip().startswith("#"):
            continue
        assert not re.search(r"[0-9a-f]{32,}", linea), linea


def test_gitignore_ignora_env_pero_no_la_plantilla():
    def ignorado(ruta: str) -> bool:
        r = subprocess.run(
            ["git", "check-ignore", "-q", ruta], cwd=RAIZ, capture_output=True, check=False
        )
        return r.returncode == 0

    assert ignorado("produccion.env")
    assert ignorado("infra/produccion.env")
    assert not ignorado("infra/produccion.env.example")
    assert not ignorado(".env.example")
