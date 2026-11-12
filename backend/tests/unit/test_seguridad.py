"""Pruebas unitarias de las primitivas de seguridad de `core/seguridad.py`
(change 03, tareas 7.1, 7.2 y 7.4).

Dominio de infraestructura pura (criptografía): sin acceso a base de datos
ni a FastAPI. Las pruebas que requieren un usuario o una sesión real
(inicio de sesión, rotación de refresh, etc.) están en el grupo 8
(`identidad/service.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.seguridad import (
    AccessTokenExpiradoError,
    AccessTokenInvalidoError,
    derivar_hash_refresh_token,
    derivar_pin_autorizacion,
    emitir_access_token,
    generar_refresh_token,
    hashear_password,
    verificar_access_token,
    verificar_password,
    verificar_pin_autorizacion,
)


class TestHashPassword:
    def test_verifica_una_contrasena_correcta(self) -> None:
        hash_almacenado = hashear_password("una-contrasena-larga-123")
        assert verificar_password("una-contrasena-larga-123", hash_almacenado) is True

    def test_rechaza_una_contrasena_incorrecta(self) -> None:
        hash_almacenado = hashear_password("una-contrasena-larga-123")
        assert verificar_password("otra-contrasena", hash_almacenado) is False

    def test_la_misma_contrasena_deriva_distinto_cada_vez(self) -> None:
        """Argon2id genera una sal aleatoria por llamada: dos derivaciones de
        la misma contraseña no deben coincidir como cadena, aunque ambas
        verifiquen correctamente."""
        primer_hash = hashear_password("una-contrasena-larga-123")
        segundo_hash = hashear_password("una-contrasena-larga-123")

        assert primer_hash != segundo_hash
        assert verificar_password("una-contrasena-larga-123", primer_hash) is True
        assert verificar_password("una-contrasena-larga-123", segundo_hash) is True

    def test_el_hash_es_argon2id(self) -> None:
        hash_almacenado = hashear_password("una-contrasena-larga-123")
        assert hash_almacenado.startswith("$argon2id$")


class TestAccessToken:
    def test_el_token_contiene_usuario_organizacion_y_dispositivo(self) -> None:
        usuario_id, organizacion_id, dispositivo_id = uuid4(), uuid4(), uuid4()
        emitido_en = datetime.now(UTC)

        token = emitir_access_token(
            usuario_id=usuario_id,
            organizacion_id=organizacion_id,
            dispositivo_id=dispositivo_id,
            secreto="secreto-de-prueba",
            kid="1",
            emitido_en=emitido_en,
        )
        claims = verificar_access_token(token, claves_por_kid={"1": "secreto-de-prueba"})

        assert claims.usuario_id == usuario_id
        assert claims.organizacion_id == organizacion_id
        assert claims.dispositivo_id == dispositivo_id

    def test_el_token_no_contiene_permisos(self) -> None:
        """`design.md` D5: los permisos nunca viajan en el token, se cargan
        sin caché en cada petición."""
        token = emitir_access_token(
            usuario_id=uuid4(),
            organizacion_id=uuid4(),
            dispositivo_id=uuid4(),
            secreto="secreto-de-prueba",
            kid="1",
            emitido_en=datetime.now(UTC),
        )
        payload_sin_verificar = jwt.decode(token, options={"verify_signature": False})
        assert "permisos" not in payload_sin_verificar

    def test_vence_a_los_15_minutos(self) -> None:
        emitido_en = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        token = emitir_access_token(
            usuario_id=uuid4(),
            organizacion_id=uuid4(),
            dispositivo_id=uuid4(),
            secreto="secreto-de-prueba",
            kid="1",
            emitido_en=emitido_en,
        )

        # Un segundo antes de los 15 minutos: todavía verifica.
        verificar_access_token(
            token,
            claves_por_kid={"1": "secreto-de-prueba"},
            ahora=emitido_en + timedelta(minutes=15) - timedelta(seconds=1),
        )

        with pytest.raises(AccessTokenExpiradoError):
            verificar_access_token(
                token,
                claves_por_kid={"1": "secreto-de-prueba"},
                ahora=emitido_en + timedelta(minutes=15, seconds=1),
            )

    def test_una_firma_alterada_no_verifica(self) -> None:
        token = emitir_access_token(
            usuario_id=uuid4(),
            organizacion_id=uuid4(),
            dispositivo_id=uuid4(),
            secreto="secreto-de-prueba",
            kid="1",
            emitido_en=datetime(2026, 1, 1, tzinfo=UTC),
        )
        # Se altera un caracter bien adentro de la firma (no el último grupo
        # base64, cuyos bits de relleno a veces no cambian el byte
        # decodificado y volvería la prueba intermitente).
        posicion = len(token) - 10
        caracter_alterado = "A" if token[posicion] != "A" else "B"
        token_alterado = token[:posicion] + caracter_alterado + token[posicion + 1 :]

        with pytest.raises(AccessTokenInvalidoError):
            verificar_access_token(token_alterado, claves_por_kid={"1": "secreto-de-prueba"})

    def test_un_kid_desconocido_no_verifica(self) -> None:
        token = emitir_access_token(
            usuario_id=uuid4(),
            organizacion_id=uuid4(),
            dispositivo_id=uuid4(),
            secreto="secreto-de-prueba",
            kid="clave-vieja",
            emitido_en=datetime(2026, 1, 1, tzinfo=UTC),
        )

        with pytest.raises(AccessTokenInvalidoError):
            verificar_access_token(token, claves_por_kid={"1": "secreto-de-prueba"})


class TestRefreshTokenOpaco:
    def test_genera_un_token_con_entropia_suficiente(self) -> None:
        token = generar_refresh_token()
        assert len(token) >= 32

    def test_dos_tokens_generados_son_distintos(self) -> None:
        assert generar_refresh_token() != generar_refresh_token()

    def test_la_derivacion_es_deterministica(self) -> None:
        token = generar_refresh_token()
        assert derivar_hash_refresh_token(token) == derivar_hash_refresh_token(token)

    def test_el_servidor_no_guarda_el_refresh_token_en_claro(self) -> None:
        """La derivación almacenable nunca coincide con el token en claro:
        lo único persistido es la derivación, no reconstruible al valor
        original (`design.md` D4/`03` §4: `sesion_refresh.token_hash`)."""
        token = generar_refresh_token()
        hash_derivado = derivar_hash_refresh_token(token)

        assert hash_derivado != token

    def test_tokens_distintos_derivan_hashes_distintos(self) -> None:
        primero = generar_refresh_token()
        segundo = generar_refresh_token()
        assert derivar_hash_refresh_token(primero) != derivar_hash_refresh_token(segundo)


class TestPinDeAutorizacion:
    """Tarea 9.1 (`ADR-019`): PBKDF2-HMAC-SHA256, sal aleatoria de 32 bytes,
    iteraciones altas guardadas junto con la derivación."""

    def test_el_pin_nunca_queda_almacenado_en_claro(self) -> None:
        hash_derivado, sal, iteraciones = derivar_pin_autorizacion("482913")

        assert "482913" not in hash_derivado
        assert "482913" not in sal
        assert iteraciones > 0

    def test_la_misma_derivacion_se_reproduce_con_el_pin_correcto(self) -> None:
        hash_derivado, sal, iteraciones = derivar_pin_autorizacion("482913")

        assert (
            verificar_pin_autorizacion(
                "482913", hash_almacenado=hash_derivado, sal=sal, iteraciones=iteraciones
            )
            is True
        )
        assert (
            verificar_pin_autorizacion(
                "000000", hash_almacenado=hash_derivado, sal=sal, iteraciones=iteraciones
            )
            is False
        )

    def test_dos_pines_iguales_derivan_distinto_por_la_sal(self) -> None:
        hash_1, sal_1, _ = derivar_pin_autorizacion("482913")
        hash_2, sal_2, _ = derivar_pin_autorizacion("482913")

        assert sal_1 != sal_2
        assert hash_1 != hash_2
