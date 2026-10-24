"""ADR-057 (enmienda a ADR-018, SEG-01): clave del contador de fallos del login.

`clave_de_intento_login(slug, usuario)` resume el par escrito, sin normalizar, con la misma
comparación exacta que el login. Función pura: sin base de datos.
"""

from __future__ import annotations

import re

from app.modules.identidad.domain.clave_intento import clave_de_intento_login

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def test_es_determinista() -> None:
    assert clave_de_intento_login("org", "marta") == clave_de_intento_login("org", "marta")


def test_distingue_mayusculas_del_usuario_y_del_slug() -> None:
    base = clave_de_intento_login("org", "marta")
    assert clave_de_intento_login("org", "Marta") != base
    assert clave_de_intento_login("ORG", "marta") != base


def test_distingue_espacios_sin_recortar() -> None:
    base = clave_de_intento_login("org", "marta")
    assert clave_de_intento_login("org", " marta") != base
    assert clave_de_intento_login("org", "marta ") != base
    assert clave_de_intento_login("org ", "marta") != base


def test_el_mismo_usuario_en_dos_organizaciones_son_dos_claves() -> None:
    assert clave_de_intento_login("org-a", "marta") != clave_de_intento_login("org-b", "marta")


def test_la_codificacion_no_es_ambigua_entre_slug_y_usuario() -> None:
    assert clave_de_intento_login("a b", "c") != clave_de_intento_login("a", "b c")
    assert clave_de_intento_login("a", "bc") != clave_de_intento_login("ab", "c")
    assert clave_de_intento_login('a","b', "c") != clave_de_intento_login("a", 'b","c')


def test_siempre_son_64_caracteres_hexadecimales() -> None:
    for slug, usuario in [("", ""), ("org", "marta"), ("ñandú", "Ángel 🙂")]:
        assert _HEX_64.match(clave_de_intento_login(slug, usuario))


def test_el_largo_no_crece_con_entradas_enormes() -> None:
    enorme = "x" * 10_000
    clave = clave_de_intento_login(enorme, enorme)
    assert _HEX_64.match(clave)
    assert clave != clave_de_intento_login(enorme, enorme + "x")
