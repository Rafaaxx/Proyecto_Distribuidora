"""Runbook, CI y reglas de saltos de linea (change 27a, Lote 4; D1, D16, D17).

Spec `sistema/despliegue`, «Primera puesta en marcha documentada» y «Actualizacion a una version
nueva». Son pruebas de lectura de archivos: no requieren Docker.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
RUNBOOK = RAIZ / "docs" / "runbook" / "puesta-en-marcha.md"
CI = RAIZ / ".github" / "workflows" / "ci.yml"
README = RAIZ / "README.md"


def test_gitattributes_fuerza_lf_en_los_caddyfile():
    texto = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^Caddyfile\*\s+text\s+eol=lf\s*$", texto, re.MULTILINE)


def test_ci_corre_las_pruebas_de_infra_en_el_trabajo_de_integracion():
    texto = CI.read_text(encoding="utf-8")
    bloque = texto.split("integracion-testcontainers:")[1].split("build-frontend:")[0]
    assert re.search(r"pytest\s+tests/integration\s+tests/infra", bloque)


def test_readme_enlaza_al_runbook():
    assert "docs/runbook/puesta-en-marcha.md" in README.read_text(encoding="utf-8")


def _runbook() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "fragmento",
    [
        "CADDY_TLS=internal",  # escenario 1
        "icacls",  # archivo de entorno protegido en Windows
        "pki/authorities/local/root.crt",  # certificado raiz de Caddy
        "Ajustes de confianza de certificados",  # iPhone
        "openssl rand -hex 32",  # secretos
        "Read-Host -AsSecureString",  # siembra en PowerShell
        "read -s",  # siembra en Git Bash / Linux
        "python -m app.seed",
        "run --rm backup ahora",  # backup a pedido
        "api/v1/version",  # verificar la actualizacion
        "CREATE ROLE app_backup",  # SQL sobre un volumen existente
        "pg_read_all_data",
        "/etc/distribuidora/produccion.env",  # escenario 2
        "chmod 600",
        "Let's Encrypt",
        "port forwarding",  # limitacion de la oficina
        "reserva DHCP",
        "New-NetFirewallRule",
        "git checkout",  # actualizacion
    ],
)
def test_runbook_cubre_lo_que_pide_la_tarea(fragmento):
    assert fragmento in _runbook()


def test_runbook_presenta_primero_la_pc_de_la_oficina():
    texto = _runbook()
    esc1 = texto.index("## Escenario 1:")
    esc2 = texto.index("## Escenario 2:")
    comun = texto.index("## Pasos comunes")
    assert esc1 < esc2 < comun


def test_runbook_no_trae_secretos_con_valor():
    texto = _runbook()
    # Ninguna asignacion de secreto con un valor hexadecimal largo pegado.
    assert not re.search(r"(PASSWORD|JWT_SECRET)=[0-9a-f]{32,}", texto)


def test_enlaces_relativos_del_runbook_existen():
    for destino in re.findall(r"\]\((?!https?:|#)([^)#]+)", _runbook()):
        assert (RUNBOOK.parent / destino).resolve().exists(), destino


def _seccion_actualizar() -> str:
    texto = _runbook()
    inicio = texto.index("### C9 Actualizar")
    return texto[inicio : texto.index("### C10", inicio)]


def test_actualizar_migra_con_run_antes_de_reemplazar_con_up():
    # Observado en el ensayo (D15, paso 18): `up -d` con migraciones fallidas deja el sistema caido.
    seccion = _seccion_actualizar()
    run = seccion.index("run --rm migraciones")
    up = seccion.index("dc up -d")
    assert run < up


def test_actualizar_explica_que_hacer_si_las_migraciones_fallan_y_si_quedo_caido():
    seccion = _seccion_actualizar()
    assert "Si las migraciones fallan" in seccion
    assert "Si el sistema quedó caído" in seccion
    assert "sigue funcionando" in seccion


def test_runbook_no_afirma_que_up_protege_al_backend_viejo():
    assert "no reemplaza el backend" not in _runbook()
