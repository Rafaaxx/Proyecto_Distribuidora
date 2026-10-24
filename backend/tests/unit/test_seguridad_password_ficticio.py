"""ADR-057 punto 7 (SEG-01): `verificar_password_o_ficticio` siempre deriva una vez con Argon2id,
para que el tiempo de respuesta del login no revele si el usuario existe o está activo."""

from __future__ import annotations

from argon2 import PasswordHasher
from pytest import MonkeyPatch

from app.core.seguridad import hashear_password, verificar_password_o_ficticio


def _espiar_verify(monkeypatch: MonkeyPatch) -> list[tuple[str, str]]:
    llamadas: list[tuple[str, str]] = []
    original = PasswordHasher.verify

    def _verify(self: PasswordHasher, hash_: str | bytes, password: str | bytes) -> bool:
        llamadas.append((str(hash_), str(password)))
        return original(self, hash_, password)

    monkeypatch.setattr(PasswordHasher, "verify", _verify)
    return llamadas


def test_sin_hash_devuelve_false_y_deriva_una_vez(monkeypatch: MonkeyPatch) -> None:
    llamadas = _espiar_verify(monkeypatch)
    assert verificar_password_o_ficticio("lo-que-sea", None) is False
    assert len(llamadas) == 1


def test_sin_hash_nunca_acepta_ni_la_cadena_vacia(monkeypatch: MonkeyPatch) -> None:
    llamadas = _espiar_verify(monkeypatch)
    assert verificar_password_o_ficticio("", None) is False
    assert len(llamadas) == 1


def test_con_hash_real_acepta_la_correcta_y_rechaza_la_incorrecta(
    monkeypatch: MonkeyPatch,
) -> None:
    hash_real = hashear_password("una-contrasena-larga-123")
    llamadas = _espiar_verify(monkeypatch)
    assert verificar_password_o_ficticio("una-contrasena-larga-123", hash_real) is True
    assert verificar_password_o_ficticio("otra", hash_real) is False
    assert len(llamadas) == 2
    assert all(hash_ == hash_real for hash_, _ in llamadas)


def test_el_hash_ficticio_usa_los_parametros_de_hashear_password() -> None:
    from app.core.seguridad import _HASH_FICTICIO_LOGIN

    real = hashear_password("x")
    ficticio_parametros = _HASH_FICTICIO_LOGIN.split("$")[:4]
    real_parametros = real.split("$")[:4]
    assert ficticio_parametros == real_parametros
