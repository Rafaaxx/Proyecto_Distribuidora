"""Escaneo de dependencias y de secretos en CI (auditoría de seguridad)."""

import tomllib
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[3]


def _yaml(ruta: str) -> dict[str, Any]:
    datos = yaml.safe_load((RAIZ / ruta).read_text(encoding="utf-8"))
    assert isinstance(datos, dict)
    return datos


def _pasos_de_seguridad() -> str:
    pasos = _yaml(".github/workflows/ci.yml")["jobs"]["seguridad"]["steps"]
    return "\n".join(str(paso.get("run", "")) for paso in pasos)


def test_ci_audita_las_dependencias_de_produccion() -> None:
    texto = _pasos_de_seguridad()
    assert "pip_audit -r requirements.txt" in texto
    assert "npm audit --omit=dev --audit-level=high" in texto


def test_ci_corre_gitleaks_con_version_y_suma_de_verificacion_fijas() -> None:
    job = _yaml(".github/workflows/ci.yml")["jobs"]["seguridad"]
    assert job["env"]["GITLEAKS_VERSION"].count(".") == 2
    assert len(job["env"]["GITLEAKS_SHA256"]) == 64
    texto = _pasos_de_seguridad()
    assert "sha256sum --check" in texto
    assert "--config .gitleaks.toml" in texto


def test_pip_audit_esta_en_los_requisitos_de_desarrollo() -> None:
    # Gotcha: una herramienta que solo está en el `.venv` rompe la CI.
    lineas = (RAIZ / "backend" / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
    assert any(linea.lower().startswith("pip_audit==") for linea in lineas)


def test_dependabot_cubre_pip_npm_docker_y_actions_semanalmente() -> None:
    actualizaciones = _yaml(".github/dependabot.yml")["updates"]
    ecosistemas = {a["package-ecosystem"] for a in actualizaciones}
    assert ecosistemas == {"pip", "npm", "docker", "github-actions"}
    for a in actualizaciones:
        assert a["schedule"]["interval"] == "weekly"
        assert a["open-pull-requests-limit"] <= 3


def test_dependabot_cubre_cada_carpeta_con_dockerfile() -> None:
    carpetas = {
        "/" + str(p.parent.relative_to(RAIZ)).replace("\\", "/")
        for p in RAIZ.glob("**/Dockerfile*")
        if "node_modules" not in p.parts and p.suffix != ".dockerignore"
    }
    cubiertas = {
        a["directory"]
        for a in _yaml(".github/dependabot.yml")["updates"]
        if a["package-ecosystem"] == "docker"
    }
    assert carpetas <= cubiertas


def test_gitleaks_solo_exceptua_el_entorno_de_aceptacion() -> None:
    config = tomllib.loads((RAIZ / ".gitleaks.toml").read_text(encoding="utf-8"))
    assert config["extend"]["useDefault"] is True
    (lista,) = config["allowlists"]
    assert lista["paths"] == [r"^infra/aceptacion\.env$"]
    assert lista["description"]
