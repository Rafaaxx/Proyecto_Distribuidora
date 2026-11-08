"""Caddyfile e imagen de Caddy de producción (change 27a, Lote 2; D1, D2, D4).

Spec `sistema/despliegue`, «HTTPS obligatorio con el mismo origen». Cita
`docs/02-arquitectura.md` §11, §18 y ADR-062. Las pruebas de lectura no
requieren Docker; las de validación corren `caddy` en un contenedor `caddy:2`
(Caddyfile por entrada estándar, sin montajes) y se omiten si Docker no está.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parents[3]
CADDYFILE = RAIZ / "infra" / "caddy" / "Caddyfile"
CADDYFILE_DEV = RAIZ / "infra" / "caddy" / "Caddyfile.dev"
DOCKERFILE = RAIZ / "infra" / "caddy" / "Dockerfile"
DOCKERIGNORE = RAIZ / "infra" / "caddy" / "Dockerfile.dockerignore"

TEXTO = CADDYFILE.read_text(encoding="utf-8")


def _sin_comentarios(texto: str) -> str:
    return "\n".join(linea for linea in texto.splitlines() if not linea.strip().startswith("#"))


SIN_COMENTARIOS = _sin_comentarios(TEXTO)


def test_atiende_el_dominio_con_el_emisor_elegido_por_variable():
    assert re.search(r"^\{\$DOMINIO\}\s*\{", SIN_COMENTARIOS, re.MULTILINE)
    assert re.search(r"^\s*tls \{\$CADDY_TLS\}\s*$", SIN_COMENTARIOS, re.MULTILINE)
    assert "default_sni {$DOMINIO}" in SIN_COMENTARIOS


def test_reenvia_la_api_al_backend_en_el_mismo_origen():
    assert re.search(r"handle /api/\*\s*\{\s*reverse_proxy backend:8000\s*\}", SIN_COMENTARIOS)


def test_devuelve_index_html_para_rutas_de_la_aplicacion():
    assert "try_files {path} /index.html" in SIN_COMENTARIOS
    assert "root * /srv" in SIN_COMENTARIOS


def test_las_cuatro_rutas_del_service_worker_van_sin_cache():
    m = re.search(r"@sin_cache path ([^\n]+)", SIN_COMENTARIOS)
    assert m
    assert set(m.group(1).split()) == {
        "/sw.js",
        "/registerSW.js",
        "/index.html",
        "/manifest.webmanifest",
    }
    assert 'header @sin_cache Cache-Control "no-cache"' in SIN_COMENTARIOS


def test_assets_con_hash_van_con_cache_larga_e_inmutable():
    assert "@assets path /assets/*" in SIN_COMENTARIOS
    assert "immutable" in SIN_COMENTARIOS
    assert "max-age=31536000" in SIN_COMENTARIOS


def test_hsts_de_un_anio_sin_subdominios_ni_preload():
    m = re.search(r'Strict-Transport-Security\s+"([^"]+)"', SIN_COMENTARIOS)
    assert m
    assert m.group(1) == "max-age=31536000"
    assert "includeSubDomains" not in SIN_COMENTARIOS
    assert "preload" not in SIN_COMENTARIOS


def test_comprime_las_respuestas():
    assert "encode gzip" in SIN_COMENTARIOS


def test_el_caddyfile_de_desarrollo_no_cambia():
    dev = CADDYFILE_DEV.read_text(encoding="utf-8")
    assert "tls internal" in dev
    assert "{$LAN_IP}" in dev
    assert "DOMINIO" not in dev


def test_imagen_en_dos_etapas_con_la_version_como_argumento():
    texto = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^FROM node:22-slim AS \w+", texto, re.MULTILINE)
    assert re.search(r"^FROM caddy:2\b", texto, re.MULTILINE)
    assert "ARG APP_VERSION" in texto
    assert re.search(r"^ENV APP_VERSION=\$APP_VERSION", texto, re.MULTILINE)
    assert "npm ci" in texto
    assert "npm run build" in texto
    assert "COPY --from=" in texto
    assert "/srv" in texto
    assert "infra/caddy/Caddyfile /etc/caddy/Caddyfile" in texto


def test_el_contexto_de_la_imagen_deja_afuera_node_modules_y_dist():
    lineas = {
        linea.strip()
        for linea in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.startswith("#")
    }
    assert "**/node_modules" in lineas
    assert "**/dist" in lineas


# --- Validación con Caddy real -------------------------------------------------------------

_DOCKER = shutil.which("docker")
requiere_docker = pytest.mark.skipif(_DOCKER is None, reason="requiere Docker")


def _caddy(comando: str, tls: str, dominio: str = "localhost") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "-e",
            f"DOMINIO={dominio}",
            "-e",
            f"CADDY_TLS={tls}",
            "caddy:2",
            "sh",
            "-c",
            f"cat > /tmp/Caddyfile && {comando}",
        ],  # fmt: skip
        input=TEXTO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@requiere_docker
@pytest.mark.parametrize(
    ("tls", "dominio"),
    [
        ("internal", "localhost"),
        ("internal", "192.168.1.50"),
        ("sistemas@ejemplo.com.ar", "app.ejemplo.com.ar"),
    ],
)
def test_caddy_validate_acepta_los_dos_modos(tls, dominio):
    r = _caddy("caddy validate --config /tmp/Caddyfile --adapter caddyfile", tls, dominio)
    assert r.returncode == 0, r.stderr


def _politicas_tls(tls: str, dominio: str) -> list[dict[str, Any]]:
    r = _caddy("caddy adapt --config /tmp/Caddyfile --adapter caddyfile", tls, dominio)
    assert r.returncode == 0, r.stderr
    config = json.loads(r.stdout)
    politicas: list[dict[str, Any]] = config["apps"]["tls"]["automation"]["policies"]
    return politicas


@requiere_docker
def test_con_internal_el_emisor_es_la_autoridad_propia_de_caddy():
    politicas = _politicas_tls("internal", "192.168.1.50")
    emisores = [i["module"] for p in politicas for i in p.get("issuers", [])]
    assert emisores == ["internal"]


@requiere_docker
def test_con_un_correo_el_emisor_es_acme_con_ese_correo():
    correo = "sistemas@ejemplo.com.ar"
    politicas = _politicas_tls(correo, "app.ejemplo.com.ar")
    emisores = [i for p in politicas for i in p.get("issuers", [])]
    # Caddy agrega por su cuenta un emisor de respaldo (ZeroSSL): todos son ACME con ese correo.
    assert emisores
    assert {e["module"] for e in emisores} == {"acme"}
    assert {e["email"] for e in emisores} == {correo}
