"""Caddyfile e imagen de Caddy de producción (change 27a, Lote 2; D1, D2, D4).

Spec `sistema/despliegue`, «HTTPS obligatorio con el mismo origen». Cita
`docs/02-arquitectura.md` §11, §18 y ADR-062. Las pruebas de lectura no
requieren Docker; las de validación corren `caddy` en un contenedor `caddy:2`
(Caddyfile por entrada estándar, sin montajes) y se omiten si Docker no está.
"""

import base64
import json
import re
import shutil
import socket
import ssl
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parents[3]
CADDYFILE = RAIZ / "infra" / "caddy" / "Caddyfile"
CADDYFILE_DEV = RAIZ / "infra" / "caddy" / "Caddyfile.dev"
DOCKERFILE = RAIZ / "infra" / "caddy" / "Dockerfile"
DOCKERIGNORE = RAIZ / "infra" / "caddy" / "Dockerfile.dockerignore"
ENCABEZADOS = RAIZ / "infra" / "caddy" / "encabezados.caddy"

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


def test_el_caddyfile_de_desarrollo_sigue_en_tls_interno_sobre_la_ip():
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
    assert "infra/caddy/encabezados.caddy /etc/caddy/encabezados.caddy" in texto


def test_el_contexto_de_la_imagen_deja_afuera_node_modules_y_dist():
    lineas = {
        linea.strip()
        for linea in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.startswith("#")
    }
    assert "**/node_modules" in lineas
    assert "**/dist" in lineas
    # El fragmento de encabezados (change 28) tiene que entrar al contexto o `COPY` falla.
    assert "!infra/caddy/encabezados.caddy" in lineas


# --- Validación con Caddy real -------------------------------------------------------------

_DOCKER = shutil.which("docker")
requiere_docker = pytest.mark.skipif(_DOCKER is None, reason="requiere Docker")


def _b64(texto: str) -> str:
    return base64.b64encode(texto.encode("utf-8")).decode("ascii")


def _fragmento() -> str:
    return _b64(ENCABEZADOS.read_text(encoding="utf-8"))


_ESCRIBIR_FRAGMENTO = 'printf %s "$ENCABEZADOS" | base64 -d > /etc/caddy/encabezados.caddy'


def _caddy(comando: str, tls: str, dominio: str = "localhost") -> subprocess.CompletedProcess[str]:
    # El fragmento de encabezados va en /etc/caddy, donde lo importan los dos Caddyfile.
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
            "-e",
            f"ENCABEZADOS={_fragmento()}",
            "caddy:2",
            "sh",
            "-c",
            f"{_ESCRIBIR_FRAGMENTO} && cat > /tmp/Caddyfile && {comando}",
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


# --- Encabezados de seguridad y CSP (change 28, Lote 4; D8, D9) -------------------------------
# Spec `sistema/despliegue`, «Encabezados de seguridad y política de contenido en todas las
# respuestas». Cita `docs/02-arquitectura.md` §18 y ADR-071.

CSP_ESPERADA = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
    "font-src 'self' data:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
IMPORTACION = "import /etc/caddy/encabezados.caddy"
TEXTO_FRAGMENTO = ENCABEZADOS.read_text(encoding="utf-8") if ENCABEZADOS.exists() else ""
FRAGMENTO = _sin_comentarios(TEXTO_FRAGMENTO)


def test_los_dos_caddyfile_importan_el_mismo_fragmento_de_encabezados():
    dev = _sin_comentarios(CADDYFILE_DEV.read_text(encoding="utf-8"))
    assert IMPORTACION in SIN_COMENTARIOS
    assert IMPORTACION in dev


def test_el_fragmento_declara_la_politica_de_contenido_de_d9_sin_excepciones():
    m = re.search(r'Content-Security-Policy\s+"([^"]+)"', FRAGMENTO)
    assert m
    assert m.group(1) == CSP_ESPERADA
    assert "unsafe-eval" not in FRAGMENTO
    assert "unsafe-inline" not in FRAGMENTO
    # La política se aplica: no se deja en modo «solo informar».
    assert "Report-Only" not in FRAGMENTO


def test_el_fragmento_declara_los_encabezados_complementarios_y_quita_server():
    assert re.search(r'X-Content-Type-Options\s+"nosniff"', FRAGMENTO)
    assert re.search(r'Referrer-Policy\s+"same-origin"', FRAGMENTO)
    assert re.search(r'Cross-Origin-Opener-Policy\s+"same-origin"', FRAGMENTO)
    assert re.search(r'X-Frame-Options\s+"DENY"', FRAGMENTO)
    permisos = re.search(r'Permissions-Policy\s+"([^"]+)"', FRAGMENTO)
    assert permisos
    for funcion in ("camera", "microphone", "geolocation", "payment"):
        assert f"{funcion}=()" in permisos.group(1)
    assert re.search(r"^\s*-Server\s*$", FRAGMENTO, re.MULTILINE)


def test_el_hsts_queda_en_el_caddyfile_de_produccion_y_no_en_el_fragmento():
    # ADR-071: el HSTS de un año es de producción; el fragmento solo trae los encabezados nuevos.
    assert "Strict-Transport-Security" not in FRAGMENTO
    assert "Strict-Transport-Security" in SIN_COMENTARIOS


@requiere_docker
@pytest.mark.parametrize(
    ("tls", "dominio"),
    [("internal", "localhost"), ("sistemas@ejemplo.com.ar", "app.ejemplo.com.ar")],
)
def test_la_configuracion_compilada_pone_los_encabezados_en_los_dos_modos_de_tls(tls, dominio):
    r = _caddy("caddy adapt --config /tmp/Caddyfile --adapter caddyfile", tls, dominio)
    assert r.returncode == 0, r.stderr
    assert CSP_ESPERADA in r.stdout
    assert "nosniff" in r.stdout
    assert "Cross-Origin-Opener-Policy" in r.stdout


@requiere_docker
def test_el_caddyfile_de_desarrollo_valida_con_el_fragmento():
    r = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "-e",
            "LAN_IP=192.168.1.50",
            "-e",
            f"ENCABEZADOS={_fragmento()}",
            "caddy:2",
            "sh",
            "-c",
            f"{_ESCRIBIR_FRAGMENTO} && cat > /tmp/Caddyfile"
            " && caddy validate --config /tmp/Caddyfile --adapter caddyfile",
        ],  # fmt: skip
        input=CADDYFILE_DEV.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert r.returncode == 0, r.stderr


# --- Respuestas reales: Caddy levantado y un «backend» de mentira que anuncia `Server` -----------

RUTAS = ["/", "/admin", "/sw.js", "/api/v1/salud"]


def _levantar(caddyfile: Path, entorno: dict[str, str]) -> tuple[str, int]:
    """Levanta Caddy con el Caddyfile y el fragmento; devuelve (contenedor, puerto 443 local)."""
    nombre = f"caddy-prueba-{uuid.uuid4().hex[:8]}"
    # `backend` apunta a 127.0.0.1 y `caddy respond` hace de backend en :8000 con su propio
    # `Server` (como uvicorn): se comprueba que Caddy lo quita también en las respuestas de /api.
    arranque = (
        f"{_ESCRIBIR_FRAGMENTO}"
        ' && printf %s "$CADDYFILE" | base64 -d > /etc/caddy/Caddyfile'
        " && mkdir -p /srv && echo '<html></html>' > /srv/index.html && echo x > /srv/sw.js"
        " && (caddy respond --listen :8000 --header 'Server: uvicorn' --body ok &)"
        " && exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile"
    )
    args = ["docker", "run", "-d", "--name", nombre, "--add-host", "backend:127.0.0.1"]
    args += ["-p", "127.0.0.1::443"]
    for clave, valor in entorno.items():
        args += ["-e", f"{clave}={valor}"]
    args += ["-e", f"ENCABEZADOS={_fragmento()}"]
    args += ["-e", f"CADDYFILE={_b64(caddyfile.read_text(encoding='utf-8'))}"]
    args += ["caddy:2", "sh", "-c", arranque]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)
    assert r.returncode == 0, r.stderr
    p = subprocess.run(
        ["docker", "port", nombre, "443/tcp"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return nombre, int(p.stdout.splitlines()[0].rsplit(":", 1)[1])


def _pedir(puerto: int, nombre_tls: str, ruta: str) -> dict[str, str]:
    """GET por HTTPS (certificado propio de Caddy: no se verifica); encabezados en minúscula."""
    contexto = ssl.create_default_context()
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    limite = time.monotonic() + 30
    pedido = f"GET {ruta} HTTP/1.1\r\nHost: {nombre_tls}\r\nConnection: close\r\n\r\n".encode()
    while True:
        try:
            with (
                socket.create_connection(("127.0.0.1", puerto), timeout=5) as crudo,
                contexto.wrap_socket(crudo, server_hostname=nombre_tls) as seguro,
            ):
                seguro.sendall(pedido)
                datos = b""
                while pedazo := seguro.recv(4096):
                    datos += pedazo
            break
        except OSError:
            if time.monotonic() > limite:
                raise
            time.sleep(0.5)
    cabecera = datos.split(b"\r\n\r\n", 1)[0].decode("latin-1").split("\r\n")
    assert " 200 " in cabecera[0], cabecera[0]
    pares = (linea.split(":", 1) for linea in cabecera[1:] if ":" in linea)
    return {k.lower(): v.strip() for k, v in pares}


def _verificar(encabezados: dict[str, str], con_hsts: bool) -> None:
    csp = encabezados["content-security-policy"]
    assert csp == CSP_ESPERADA
    assert "unsafe-eval" not in csp
    assert "unsafe-inline" not in csp
    assert encabezados["x-content-type-options"] == "nosniff"
    assert encabezados["referrer-policy"] == "same-origin"
    assert "camera=()" in encabezados["permissions-policy"]
    assert encabezados["cross-origin-opener-policy"] == "same-origin"
    assert encabezados["x-frame-options"] == "DENY"
    assert ("strict-transport-security" in encabezados) is con_hsts
    assert "server" not in encabezados


@requiere_docker
@pytest.mark.parametrize("ruta", RUTAS)
def test_produccion_con_tls_internal_envia_los_encabezados_en_toda_respuesta(ruta):
    nombre, puerto = _levantar(CADDYFILE, {"DOMINIO": "localhost", "CADDY_TLS": "internal"})
    try:
        _verificar(_pedir(puerto, "localhost", ruta), con_hsts=True)
    finally:
        subprocess.run(["docker", "rm", "-f", nombre], capture_output=True, check=False)


@requiere_docker
@pytest.mark.parametrize("ruta", RUTAS)
def test_el_perfil_lan_envia_los_mismos_encabezados(ruta):
    nombre, puerto = _levantar(CADDYFILE_DEV, {"LAN_IP": "localhost"})
    try:
        _verificar(_pedir(puerto, "localhost", ruta), con_hsts=False)
    finally:
        subprocess.run(["docker", "rm", "-f", nombre], capture_output=True, check=False)
