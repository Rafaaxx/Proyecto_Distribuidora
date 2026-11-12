"""Change 21, tarea 4.1 (`design.md` D8; `02` §12.4): el vector de derivación del PIN que comparten
Python y TypeScript. Con el mismo PIN, la misma sal y las mismas iteraciones, el servidor
(`verificar_pin_autorizacion`, PBKDF2-HMAC-SHA256) y el navegador (Web Crypto) obtienen el mismo
hash: es lo que permite que el dispositivo verifique sin conexión el PIN de un supervisor.

Los mismos casos corre Vitest en `frontend/tests/unit/lib/sesionLocal/derivacion.test.ts`.
Reglas citadas: ADR-011, ADR-019, ADR-055, SEG-05.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.core.seguridad import verificar_pin_autorizacion

VECTOR = Path(__file__).resolve().parents[3] / "shared" / "fixtures" / "pin" / "derivacion.json"


def _casos() -> list[dict[str, Any]]:
    contenido = json.loads(VECTOR.read_text(encoding="utf-8"))
    casos: list[dict[str, Any]] = contenido["casos"]
    assert len(casos) >= 2, "el vector necesita al menos dos casos para triangular"
    return casos


@pytest.mark.parametrize("caso", _casos(), ids=lambda caso: caso["id"])
def test_el_pin_del_vector_verifica_con_su_sal_e_iteraciones(caso: dict[str, Any]) -> None:
    assert verificar_pin_autorizacion(
        caso["pin"],
        hash_almacenado=caso["hash_hex"],
        sal=caso["sal_hex"],
        iteraciones=caso["iteraciones"],
    )


@pytest.mark.parametrize("caso", _casos(), ids=lambda caso: caso["id"])
def test_otro_pin_no_verifica(caso: dict[str, Any]) -> None:
    otro = "000000" if caso["pin"] != "000000" else "999999"
    assert not verificar_pin_autorizacion(
        otro,
        hash_almacenado=caso["hash_hex"],
        sal=caso["sal_hex"],
        iteraciones=caso["iteraciones"],
    )


@pytest.mark.parametrize("caso", _casos(), ids=lambda caso: caso["id"])
def test_el_hash_es_pbkdf2_hmac_sha256_hexadecimal_de_la_sal_fija(caso: dict[str, Any]) -> None:
    derivado = hashlib.pbkdf2_hmac(
        "sha256", caso["pin"].encode("utf-8"), bytes.fromhex(caso["sal_hex"]), caso["iteraciones"]
    )
    assert derivado.hex() == caso["hash_hex"]
    assert len(bytes.fromhex(caso["sal_hex"])) == 32  # la sal de 32 bytes de ADR-019


def test_el_vector_incluye_las_iteraciones_del_servidor() -> None:
    from app.core.seguridad import PIN_AUTORIZACION_ITERACIONES_DEFAULT

    assert PIN_AUTORIZACION_ITERACIONES_DEFAULT in {c["iteraciones"] for c in _casos()}
