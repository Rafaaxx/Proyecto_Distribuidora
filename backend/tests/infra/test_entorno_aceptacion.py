"""Entorno de aceptacion (change 28, Lote 6, tarea 6.2; D13).

Spec `sistema/aceptacion-etapa-1`, requisito «La suite corre contra un entorno igual al de
produccion y desechable», escenario «El entorno de aceptacion no toca otros datos». Lee los
archivos: no requiere Docker. Cita INV-05 (cada rol con su contrasena) y `02` §15, §16.
"""

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
ENTORNO = RAIZ / "infra" / "aceptacion.env"
COMPOSE = RAIZ / "docker-compose.prod.yml"
GUION = RAIZ / "frontend" / "scripts" / "aceptacion.mjs"
PAQUETE = RAIZ / "frontend" / "package.json"


def _asignaciones() -> dict[str, str]:
    resultado: dict[str, str] = {}
    for linea in ENTORNO.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", linea.strip())
        if m:
            resultado[m.group(1)] = m.group(2)
    return resultado


def test_el_archivo_de_entorno_esta_versionado_y_no_ignorado():
    r = subprocess.run(
        ["git", "check-ignore", "-q", "infra/aceptacion.env"],
        cwd=RAIZ,
        capture_output=True,
        check=False,
    )
    assert r.returncode == 1, "infra/aceptacion.env debe poder subirse a git"


def test_define_todas_las_variables_obligatorias_del_compose():
    obligatorias = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", COMPOSE.read_text(encoding="utf-8")))
    asignaciones = _asignaciones()
    vacias = {n for n in obligatorias if not asignaciones.get(n)}
    assert not vacias, f"aceptacion.env no define o deja vacias: {sorted(vacias)}"


def test_sirve_en_localhost_con_la_autoridad_propia_y_otros_puertos():
    a = _asignaciones()
    assert a["DOMINIO"] == "localhost"
    assert a["CADDY_TLS"] == "internal"
    assert a["CADDY_HTTPS_PORT"] != "443" and a["CADDY_HTTP_PORT"] != "80"
    # No chocan con el perfil `lan` de desarrollo (80/443) ni con el compose de desarrollo.
    assert int(a["CADDY_HTTPS_PORT"]) > 1024 and int(a["CADDY_HTTP_PORT"]) > 1024


def test_usa_otra_subred_para_no_chocar_con_la_del_entorno_de_produccion_del_equipo():
    a = _asignaciones()
    assert a["FRENTE_SUBRED"] != "172.30.10.0/24"
    assert a["FRENTE_SUBRED"].startswith("172.30.")


def test_la_copia_externa_es_local_y_los_secretos_son_de_prueba_y_distintos():
    a = _asignaciones()
    assert a["COPIA_TIPO"] == "local"
    secretos = [
        a[n]
        for n in (
            "POSTGRES_PASSWORD",
            "APP_MIGRATIONS_DB_PASSWORD",
            "APP_RUNTIME_DB_PASSWORD",
            "APP_BACKUP_DB_PASSWORD",
            "APP_MANTENIMIENTO_DB_PASSWORD",
            "JWT_SECRET",
        )
    ]
    assert len(set(secretos)) == len(secretos), "cada secreto debe ser distinto (INV-05)"
    assert all(s.startswith("prueba-aceptacion-") for s in secretos), "valores solo de prueba"
    assert len(a["JWT_SECRET"]) >= 32


def test_el_guion_usa_un_proyecto_aparte_y_nunca_toca_el_de_desarrollo():
    texto = GUION.read_text(encoding="utf-8")
    assert "distribuidora-aceptacion" in texto
    assert "infra/aceptacion.env" in texto
    assert "--escenario-aceptacion" in texto
    assert '"down", "-v"' in texto
    # Siempre con -p distribuidora-aceptacion: ningun comando de compose sin proyecto.
    assert re.search(r'"-p",\s*PROYECTO', texto)
    assert 'PROYECTO = "distribuidora-aceptacion"' in texto


def test_los_scripts_de_npm_corren_el_guion_y_hay_una_opcion_para_mantener_el_entorno():
    import json

    scripts = json.loads(PAQUETE.read_text(encoding="utf-8"))["scripts"]
    assert "aceptacion.mjs" in scripts["test:e2e"]
    assert "--mantener" in scripts["test:e2e:mantener"]
