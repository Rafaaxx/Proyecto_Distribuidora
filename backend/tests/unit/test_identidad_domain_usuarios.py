"""Change 20b, tareas 1.1, 1.2 y 4.5 (parte pura): reglas puras de administración de usuarios
(`design.md` D3, D5, D7, D9, D20; ADR-053, ADR-028, ADR-018, `01` §18, INV-01).

Dominio puro: sin SQLAlchemy ni FastAPI. Las reglas reciben datos y devuelven un resultado o
lanzan un error de dominio con código estable.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.errors import DomainError
from app.modules.identidad.domain.usuarios import (
    PERMISOS_AUTORIZACION_EXCEPCION,
    AutobajaError,
    ContrasenaInvalidaError,
    ContrasenaNuevaIgualAActualError,
    NombreDeRolInvalidoError,
    NombreDeUsuarioInvalidoError,
    RolInactivoError,
    SinAdministradorError,
    TransicionEstadoUsuarioInvalidaError,
    UsuarioDuplicadoError,
    debe_borrar_pin,
    normalizar_email,
    normalizar_nombre_de_rol,
    normalizar_nombre_de_usuario,
    queda_administrador,
    validar_baja_de_usuario,
    validar_contrasena,
    validar_contrasena_nueva,
    validar_queda_administrador,
    validar_reactivacion,
    validar_rol_asignable,
)


class TestQuedaAdministrador:
    """ADR-053, INV-01: la regla generalizada recibe cuántos administradores quedarían."""

    def test_cero_administradores_despues_del_cambio_se_rechaza(self) -> None:
        with pytest.raises(SinAdministradorError) as error:
            queda_administrador(0)

        assert error.value.codigo == "IDENTIDAD_SIN_ADMINISTRADOR"
        assert error.value.status_http == 409

    @pytest.mark.parametrize("despues", [1, 3])
    def test_con_uno_o_mas_no_hay_error(self, despues: int) -> None:
        queda_administrador(despues)

    def test_el_viejo_validar_queda_administrador_sigue_igual(self) -> None:
        """La regla del 17b se reescribe sobre la generalizada sin cambiar su resultado."""
        with pytest.raises(SinAdministradorError):
            validar_queda_administrador(
                administradores_en_otros_roles=0,
                conserva_el_permiso=False,
                rol_activo=True,
                usuarios_activos_del_rol=1,
            )
        validar_queda_administrador(
            administradores_en_otros_roles=0,
            conserva_el_permiso=True,
            rol_activo=True,
            usuarios_activos_del_rol=2,
        )


class TestBajaDeUsuario:
    """D5 (autobaja prohibida) y D1 (transición de estado), ADR-028, `01` §18."""

    def test_darse_de_baja_a_uno_mismo_se_rechaza(self) -> None:
        yo = uuid4()

        with pytest.raises(AutobajaError) as error:
            validar_baja_de_usuario(actor_id=yo, usuario_id=yo, estado="ACTIVO")

        assert error.value.codigo == "IDENTIDAD_AUTOBAJA"
        assert error.value.status_http == 409

    def test_la_autobaja_se_rechaza_antes_que_la_transicion(self) -> None:
        yo = uuid4()

        with pytest.raises(AutobajaError):
            validar_baja_de_usuario(actor_id=yo, usuario_id=yo, estado="INACTIVO")

    def test_dar_de_baja_a_otro_usuario_activo_es_valido(self) -> None:
        validar_baja_de_usuario(actor_id=uuid4(), usuario_id=uuid4(), estado="ACTIVO")

    def test_dar_de_baja_a_un_inactivo_es_una_transicion_invalida_409(self) -> None:
        with pytest.raises(TransicionEstadoUsuarioInvalidaError) as error:
            validar_baja_de_usuario(actor_id=uuid4(), usuario_id=uuid4(), estado="INACTIVO")

        assert error.value.codigo == "IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA"
        assert error.value.status_http == 409


class TestReactivacion:
    def test_reactivar_un_inactivo_es_valido(self) -> None:
        validar_reactivacion("INACTIVO")

    def test_reactivar_un_activo_es_una_transicion_invalida_409(self) -> None:
        with pytest.raises(TransicionEstadoUsuarioInvalidaError) as error:
            validar_reactivacion("ACTIVO")

        assert error.value.status_http == 409


class TestRolAsignable:
    """D7, D9: un rol de baja no se asigna ni en el alta ni en el cambio de rol."""

    def test_un_rol_activo_se_puede_asignar(self) -> None:
        validar_rol_asignable(True)

    def test_un_rol_inactivo_se_rechaza_con_409(self) -> None:
        with pytest.raises(RolInactivoError) as error:
            validar_rol_asignable(False)

        assert error.value.codigo == "IDENTIDAD_ROL_INACTIVO"
        assert error.value.status_http == 409


class TestUsuarioDuplicado:
    def test_es_un_error_de_dominio_409_con_codigo_estable(self) -> None:
        assert issubclass(UsuarioDuplicadoError, DomainError)
        assert UsuarioDuplicadoError.codigo == "IDENTIDAD_USUARIO_DUPLICADO"
        assert UsuarioDuplicadoError.status_http == 409


class TestNombreDeUsuario:
    """D9: obligatorio, recortado, hasta 200 caracteres."""

    @pytest.mark.parametrize(
        ("escrito", "esperado"),
        [("  Laura Pérez  ", "Laura Pérez"), ("Juan", "Juan"), ("a" * 200, "a" * 200)],
    )
    def test_recorta_y_acepta_hasta_200_caracteres(self, escrito: str, esperado: str) -> None:
        assert normalizar_nombre_de_usuario(escrito) == esperado

    @pytest.mark.parametrize("escrito", ["", "   ", "a" * 201])
    def test_vacio_o_de_201_caracteres_responde_422(self, escrito: str) -> None:
        with pytest.raises(NombreDeUsuarioInvalidoError) as error:
            normalizar_nombre_de_usuario(escrito)

        assert error.value.codigo == "IDENTIDAD_NOMBRE_DE_USUARIO_INVALIDO"
        assert error.value.status_http == 422

    def test_el_largo_se_mide_despues_de_recortar(self) -> None:
        assert normalizar_nombre_de_usuario(" " + "a" * 200 + " ") == "a" * 200


class TestEmail:
    """D9: opcional; vacío es nulo; sin verificar dominio."""

    @pytest.mark.parametrize("escrito", [None, "", "   "])
    def test_vacio_o_nulo_es_nulo(self, escrito: str | None) -> None:
        assert normalizar_email(escrito) is None

    @pytest.mark.parametrize(
        ("escrito", "esperado"),
        [(" laura@ejemplo.com ", "laura@ejemplo.com"), ("a@b", "a@b")],
    )
    def test_recorta_y_conserva_el_valor(self, escrito: str, esperado: str) -> None:
        assert normalizar_email(escrito) == esperado


class TestDebeBorrarPin:
    """D7, ADR-011: el PIN se borra si el rol nuevo no autoriza excepciones."""

    def test_sin_ningun_permiso_de_autorizacion_se_borra(self) -> None:
        assert debe_borrar_pin({"VENDER", "REGISTRAR_COBRANZA"}) is True
        assert debe_borrar_pin(frozenset()) is True

    @pytest.mark.parametrize("permiso", sorted(PERMISOS_AUTORIZACION_EXCEPCION))
    def test_con_uno_solo_de_los_cuatro_no_se_borra(self, permiso: str) -> None:
        assert debe_borrar_pin({"VENDER", permiso}) is False


class TestContrasena:
    """D9/D20, ADR-018: mínimo de 8 caracteres, sin reglas de composición, y no en blanco."""

    @pytest.mark.parametrize(
        "valor", ["una-clave-larga-1", "12345678", "abcdefgh", "sin mayus ni 1", "ñandú-ñ1"]
    )
    def test_ocho_o_mas_caracteres_es_valida(self, valor: str) -> None:
        assert validar_contrasena(valor) == valor

    @pytest.mark.parametrize("valor", ["x", "1234567", "abcdefg", "ñandú-1"])
    def test_siete_o_menos_caracteres_responde_422(self, valor: str) -> None:
        with pytest.raises(ContrasenaInvalidaError) as error:
            validar_contrasena(valor)

        assert error.value.codigo == "IDENTIDAD_CONTRASENA_INVALIDA"
        assert error.value.status_http == 422
        assert valor not in str(error.value)

    @pytest.mark.parametrize("valor", ["", "    ", " " * 8])
    def test_en_blanco_responde_422(self, valor: str) -> None:
        with pytest.raises(ContrasenaInvalidaError) as error:
            validar_contrasena(valor)

        assert error.value.codigo == "IDENTIDAD_CONTRASENA_INVALIDA"
        assert error.value.status_http == 422

    def test_el_mensaje_no_incluye_el_valor(self) -> None:
        with pytest.raises(ContrasenaInvalidaError) as error:
            validar_contrasena("   ")

        assert "   " not in str(error.value).replace("  ", "")


class TestContrasenaNueva:
    """D20, ADR-018, INV-01: la nueva cumple las reglas del alta y es distinta de la actual."""

    @pytest.mark.parametrize(
        ("actual", "nueva"),
        [("vieja-clave-123", "nueva-clave-456"), ("abc", "abcd1234")],
    )
    def test_dos_nuevas_validas_distintas_de_la_actual(self, actual: str, nueva: str) -> None:
        assert validar_contrasena_nueva(actual, nueva) == nueva

    @pytest.mark.parametrize(
        ("actual", "nueva"),
        [("misma-clave-123", "misma-clave-123"), ("12345678", "12345678")],
    )
    def test_igual_a_la_actual_responde_422_con_su_codigo(self, actual: str, nueva: str) -> None:
        with pytest.raises(ContrasenaNuevaIgualAActualError) as error:
            validar_contrasena_nueva(actual, nueva)

        assert error.value.codigo == "IDENTIDAD_CONTRASENA_NUEVA_IGUAL_A_ACTUAL"
        assert error.value.status_http == 422

    @pytest.mark.parametrize("nueva", ["", "   ", "1234567"])
    def test_en_blanco_o_corta_responde_contrasena_invalida(self, nueva: str) -> None:
        with pytest.raises(ContrasenaInvalidaError):
            validar_contrasena_nueva("vieja-clave-123", nueva)

    def test_los_mensajes_no_incluyen_ninguna_de_las_dos_contrasenas(self) -> None:
        with pytest.raises(ContrasenaNuevaIgualAActualError) as error:
            validar_contrasena_nueva("secreta-8841", "secreta-8841")

        assert "secreta-8841" not in str(error.value)


class TestNombreDeRol:
    """D10, INV-01: el nombre se recorta y tiene de 1 a 100 caracteres."""

    @pytest.mark.parametrize(
        ("valor", "esperado"),
        [("  Repartidor ", "Repartidor"), ("x" * 100, "x" * 100), ("Ñandú", "Ñandú")],
    )
    def test_se_recorta_y_acepta_hasta_100(self, valor: str, esperado: str) -> None:
        assert normalizar_nombre_de_rol(valor) == esperado

    @pytest.mark.parametrize("valor", ["", "    ", "x" * 101, " " + "x" * 101])
    def test_vacio_o_de_mas_de_100_responde_422(self, valor: str) -> None:
        with pytest.raises(NombreDeRolInvalidoError) as error:
            normalizar_nombre_de_rol(valor)

        assert error.value.codigo == "IDENTIDAD_NOMBRE_DE_ROL_INVALIDO"
        assert error.value.status_http == 422
