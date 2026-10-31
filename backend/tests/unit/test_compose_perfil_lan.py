"""Change 21, tarea 20.1 (D20 = A, ADR-062): el perfil `lan` de Docker Compose con Caddy de
desarrollo para probar la PWA en un teléfono real. Revisa el archivo, sin levantar nada."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[3]


def _compose() -> dict[str, Any]:
    return dict(yaml.safe_load((RAIZ / "docker-compose.yml").read_text(encoding="utf-8")))


def test_caddy_y_la_compilacion_solo_se_levantan_con_el_perfil_lan() -> None:
    servicios = _compose()["services"]

    assert servicios["caddy"]["profiles"] == ["lan"]
    assert servicios["pwa-build"]["profiles"] == ["lan"]
    for nombre in ("postgres", "backend", "frontend"):
        assert "profiles" not in servicios[nombre]  # `docker compose up` sigue igual


def test_caddy_sirve_la_compilacion_de_produccion_y_espera_a_que_termine() -> None:
    compose = _compose()
    caddy = compose["services"]["caddy"]

    assert "pwa_dist:/srv:ro" in caddy["volumes"]
    assert "pwa_dist:/dist" in compose["services"]["pwa-build"]["volumes"]
    assert caddy["depends_on"]["pwa-build"]["condition"] == "service_completed_successfully"
    assert "443:443" in caddy["ports"]
    assert {"pwa_dist", "caddy_data"} <= set(compose["volumes"])


def test_el_caddyfile_de_desarrollo_usa_tls_interno_en_la_ip_y_no_cachea_el_service_worker() -> (
    None
):
    caddyfile = (RAIZ / "infra" / "caddy" / "Caddyfile.dev").read_text(encoding="utf-8")

    assert "https://{$LAN_IP}" in caddyfile
    assert "tls internal" in caddyfile
    # un navegador que entra por IP no manda SNI y Docker oculta la dirección local
    assert "default_sni {$LAN_IP}" in caddyfile
    assert "reverse_proxy backend:8000" in caddyfile
    assert "/sw.js" in caddyfile and "no-cache" in caddyfile
    assert "try_files {path} /index.html" in caddyfile
