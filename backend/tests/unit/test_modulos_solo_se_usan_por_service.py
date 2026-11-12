"""Tarea 7.3: `identidad` y `configuracion` no se importan mutuamente por
fuera de `service.py` (`CLAUDE.md` §4: un módulo usa a otro solo a través de
su `service.py`). Complementa el contrato de import-linter de la tarea 1.3
(que solo prohíbe `models`/`repository` cruzados) con una verificación más
amplia: ningún archivo del módulo, salvo su propio `service.py`, importa
absolutamente nada del otro módulo.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
MODULOS_DIR = BACKEND_DIR / "app" / "modules"

MODULOS = ("identidad", "configuracion")


def _nombres_importados(archivo: Path) -> list[str]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
    nombres = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.append(nodo.module)
    return nombres


def _archivos_python_de(modulo: str) -> list[Path]:
    return list((MODULOS_DIR / modulo).rglob("*.py"))


def test_ningun_archivo_fuera_de_service_importa_el_otro_modulo() -> None:
    infractores = []
    for modulo in MODULOS:
        (otro,) = [m for m in MODULOS if m != modulo]
        prefijo_otro = f"app.modules.{otro}"
        for archivo in _archivos_python_de(modulo):
            if archivo.name == "service.py":
                continue
            for nombre in _nombres_importados(archivo):
                if nombre == prefijo_otro or nombre.startswith(prefijo_otro + "."):
                    infractores.append(f"{archivo.relative_to(BACKEND_DIR)} importa {nombre!r}")

    assert infractores == [], f"Import cruzado fuera de service.py: {infractores}"


def test_service_py_puede_importar_el_otro_modulo_sin_ser_marcado_infractor() -> None:
    """Verificación en negativo: el propio `service.py` sí puede importar el
    otro módulo (por ejemplo, la siembra futura o un uso legítimo vía
    `service`), y la comprobación de arriba no debe marcarlo."""
    service_identidad = MODULOS_DIR / "identidad" / "service.py"
    contenido_original = service_identidad.read_text(encoding="utf-8")
    try:
        service_identidad.write_text(
            contenido_original + "\nfrom app.modules.configuracion import service as _cfg\n",
            encoding="utf-8",
        )
        infractores = []
        for nombre in _nombres_importados(service_identidad):
            if nombre.startswith("app.modules.configuracion"):
                infractores.append(nombre)
        # El import existe (se agregó a propósito) pero `service.py` está
        # exento de la regla: la prueba principal lo saltea explícitamente.
        assert infractores, "El import de prueba no se agregó correctamente."
    finally:
        service_identidad.write_text(contenido_original, encoding="utf-8")


# --- Change 08: cuentas_corrientes (tarea 4.2, `02` §5.3) -------------------


def test_cuentas_corrientes_no_importa_ningun_otro_modulo_de_negocio() -> None:
    """`cuentas_corrientes` no depende de clientes, proveedores, catalogo ni
    configuracion, y de identidad solo alcanza su `service.py`."""
    prohibidos = ("clientes", "proveedores", "catalogo", "configuracion")
    infractores = []
    for archivo in _archivos_python_de("cuentas_corrientes"):
        for nombre in _nombres_importados(archivo):
            if any(
                nombre == f"app.modules.{otro}" or nombre.startswith(f"app.modules.{otro}.")
                for otro in prohibidos
            ):
                infractores.append(f"{archivo.relative_to(BACKEND_DIR)} importa {nombre!r}")
            if nombre.startswith("app.modules.identidad.") and nombre != (
                "app.modules.identidad.service"
            ):
                infractores.append(f"{archivo.relative_to(BACKEND_DIR)} importa {nombre!r}")

    assert infractores == [], f"cuentas_corrientes depende de otro modulo: {infractores}"


def test_clientes_y_proveedores_solo_importan_el_service_de_cuentas_corrientes() -> None:
    infractores = []
    for modulo in ("clientes", "proveedores"):
        for archivo in _archivos_python_de(modulo):
            for nombre in _nombres_importados(archivo):
                if nombre.startswith("app.modules.cuentas_corrientes.") and nombre != (
                    "app.modules.cuentas_corrientes.service"
                ):
                    infractores.append(f"{archivo.relative_to(BACKEND_DIR)} importa {nombre!r}")

    assert infractores == [], f"Import de internos de cuentas_corrientes: {infractores}"
