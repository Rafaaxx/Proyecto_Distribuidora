"""Imagen de producción del backend (change 27a, D5; `02` §16.2, §18).

Lectura de `backend/Dockerfile.produccion`: no requiere Docker.
"""

import re
from pathlib import Path

RAIZ_BACKEND = Path(__file__).resolve().parents[2]
DOCKERFILE = RAIZ_BACKEND / "Dockerfile.produccion"
DOCKERFILE_DEV = RAIZ_BACKEND / "Dockerfile"


def _instrucciones() -> list[str]:
    r"""Instrucciones del Dockerfile, sin comentarios y con las
    continuaciones de línea (`\`) unidas."""
    texto = DOCKERFILE.read_text(encoding="utf-8")
    texto = re.sub(r"\\r?\n", " ", texto)
    return [
        linea.strip()
        for linea in texto.splitlines()
        if linea.strip() and not linea.strip().startswith("#")
    ]


def _comando() -> str:
    cmds = [i for i in _instrucciones() if i.startswith(("CMD", "ENTRYPOINT"))]
    assert cmds, "el Dockerfile de producción no define CMD"
    return cmds[-1]


def test_dockerfile_produccion_existe():
    assert DOCKERFILE.is_file()


def test_instala_solo_requirements_sin_dev():
    instalaciones = [i for i in _instrucciones() if "pip install" in i]
    assert instalaciones
    for i in instalaciones:
        assert "requirements.txt" in i
        assert "requirements-dev" not in i


def test_no_copia_tests_ni_lo_instala_en_la_imagen():
    texto = DOCKERFILE.read_text(encoding="utf-8")
    assert "requirements-dev" not in texto
    ignore = (RAIZ_BACKEND / ".dockerignore").read_text(encoding="utf-8")
    lineas = {linea.strip().rstrip("/") for linea in ignore.splitlines()}
    assert "tests" in lineas


def test_dockerignore_excluye_entorno_virtual_y_secretos():
    ignore = (RAIZ_BACKEND / ".dockerignore").read_text(encoding="utf-8")
    lineas = {linea.strip().rstrip("/") for linea in ignore.splitlines()}
    assert {".venv", ".env", "__pycache__"} <= lineas


def test_define_usuario_no_root():
    usuarios = [i.split(maxsplit=1)[1] for i in _instrucciones() if i.startswith("USER ")]
    assert usuarios, "falta la instrucción USER"
    assert usuarios[-1].split(":")[0] not in {"root", "0"}


def test_comando_usa_workers_proxy_headers_y_forwarded_allow_ips():
    cmd = _comando()
    assert "--workers" in cmd
    assert "--proxy-headers" in cmd
    assert "--forwarded-allow-ips" in cmd


def test_comando_no_recarga_codigo():
    assert "--reload" not in _comando()


def test_comando_arranca_la_aplicacion():
    assert "app.main:app" in _comando()


def test_dockerfile_de_desarrollo_sigue_igual():
    # El de desarrollo conserva la recarga y las dependencias de desarrollo.
    texto = DOCKERFILE_DEV.read_text(encoding="utf-8")
    assert "--reload" in texto
    assert "requirements-dev.txt" in texto


def test_verifica_la_configuracion_antes_de_uvicorn():
    # Paso 0 (D6): el contenedor sale con error si la configuración está mal,
    # antes de que uvicorn lance sus workers.
    cmd = _comando()
    assert "app.core.verificar_config" in cmd
    assert cmd.index("app.core.verificar_config") < cmd.index("uvicorn")
    assert "&&" in cmd[: cmd.index("uvicorn")]
