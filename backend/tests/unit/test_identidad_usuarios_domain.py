"""Pruebas unitarias del dominio puro de usuarios, dispositivos, tope de
descuento, PIN de autorización y permisos de autorización de excepciones
(change 03, tarea 5.1 a 5.5).

Dominio puro: no importa SQLAlchemy ni FastAPI (`docs/02-arquitectura.md`
§5.2, `CLAUDE.md` §5, verificado además por `import_linter` en la tarea 5.6).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.core.money import EntradaNoEsDineroExactoError
from app.modules.identidad.domain.usuarios import (
    ESTADOS_DISPOSITIVO,
    ESTADOS_USUARIO,
    PERMISOS_AUTORIZACION_EXCEPCION,
    EstadoDispositivoInvalidoError,
    EstadoUsuarioInvalidoError,
    PinAutorizacionInvalidoError,
    TopeDescuentoFueraDeRangoError,
    TransicionEstadoDispositivoInvalidaError,
    TransicionEstadoUsuarioInvalidaError,
    resolver_tope_descuento_aplicable,
    rol_confiere_autorizacion_excepcion,
    transicionar_estado_dispositivo,
    transicionar_estado_usuario,
    validar_estado_dispositivo,
    validar_estado_usuario,
    validar_formato_pin_autorizacion,
    validar_tope_descuento,
)


class TestEstadoUsuario:
    @pytest.mark.parametrize("valor", ESTADOS_USUARIO)
    def test_acepta_los_valores_del_dominio_cerrado(self, valor: str) -> None:
        assert validar_estado_usuario(valor) == valor

    def test_rechaza_un_estado_desconocido(self) -> None:
        with pytest.raises(EstadoUsuarioInvalidoError) as exc_info:
            validar_estado_usuario("SUSPENDIDO")

        assert issubclass(EstadoUsuarioInvalidoError, DomainError)
        assert exc_info.value.codigo == "IDENTIDAD_ESTADO_USUARIO_INVALIDO"


class TestTransicionEstadoUsuario:
    def test_activo_a_inactivo_es_valida(self) -> None:
        assert transicionar_estado_usuario("ACTIVO", "INACTIVO") == "INACTIVO"

    def test_inactivo_a_activo_es_valida(self) -> None:
        assert transicionar_estado_usuario("INACTIVO", "ACTIVO") == "ACTIVO"

    def test_rechaza_transicion_al_mismo_estado(self) -> None:
        with pytest.raises(TransicionEstadoUsuarioInvalidaError) as exc_info:
            transicionar_estado_usuario("ACTIVO", "ACTIVO")

        assert exc_info.value.codigo == "IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA"

    def test_rechaza_estado_destino_desconocido(self) -> None:
        with pytest.raises(EstadoUsuarioInvalidoError):
            transicionar_estado_usuario("ACTIVO", "BORRADO")


class TestEstadoDispositivo:
    @pytest.mark.parametrize("valor", ESTADOS_DISPOSITIVO)
    def test_acepta_los_valores_del_dominio_cerrado(self, valor: str) -> None:
        assert validar_estado_dispositivo(valor) == valor

    def test_rechaza_un_estado_desconocido(self) -> None:
        with pytest.raises(EstadoDispositivoInvalidoError) as exc_info:
            validar_estado_dispositivo("SUSPENDIDO")

        assert exc_info.value.codigo == "IDENTIDAD_ESTADO_DISPOSITIVO_INVALIDO"


class TestTransicionEstadoDispositivo:
    def test_activo_a_revocado_es_valida(self) -> None:
        assert transicionar_estado_dispositivo("ACTIVO", "REVOCADO") == "REVOCADO"

    def test_revocado_es_terminal(self) -> None:
        """Un dispositivo revocado no puede volver a estar activo (`03` §7.7:
        la revocación no se deshace; se registra un dispositivo nuevo)."""
        with pytest.raises(TransicionEstadoDispositivoInvalidaError) as exc_info:
            transicionar_estado_dispositivo("REVOCADO", "ACTIVO")

        assert exc_info.value.codigo == "IDENTIDAD_TRANSICION_ESTADO_DISPOSITIVO_INVALIDA"

    def test_rechaza_transicion_al_mismo_estado(self) -> None:
        with pytest.raises(TransicionEstadoDispositivoInvalidaError):
            transicionar_estado_dispositivo("ACTIVO", "ACTIVO")


class TestResolverTopeDescuentoAplicable:
    def test_sin_tope_propio_rige_el_del_rol(self) -> None:
        tope_rol = Decimal("0.150000")
        assert resolver_tope_descuento_aplicable(tope_rol=tope_rol, tope_propio=None) == tope_rol

    def test_con_tope_propio_menor_rige_el_del_usuario(self) -> None:
        tope_rol = Decimal("0.150000")
        tope_propio = Decimal("0.050000")
        assert (
            resolver_tope_descuento_aplicable(tope_rol=tope_rol, tope_propio=tope_propio)
            == tope_propio
        )

    def test_con_tope_propio_mayor_rige_el_del_usuario(self) -> None:
        tope_rol = Decimal("0.050000")
        tope_propio = Decimal("0.150000")
        assert (
            resolver_tope_descuento_aplicable(tope_rol=tope_rol, tope_propio=tope_propio)
            == tope_propio
        )

    def test_tope_propio_cero_rige_sobre_el_del_rol(self) -> None:
        """Un tope propio en `0` es un valor definido (no lo mismo que
        `None`); TR-08: `0` deshabilita el descuento, no cae al del rol."""
        tope_rol = Decimal("0.150000")
        tope_propio = Decimal("0")
        assert (
            resolver_tope_descuento_aplicable(tope_rol=tope_rol, tope_propio=tope_propio)
            == tope_propio
        )


class TestValidarTopeDescuento:
    def test_el_10_por_ciento_se_representa_en_decimal_exacto(self) -> None:
        assert validar_tope_descuento(Decimal("0.10")) == Decimal("0.100000")

    def test_rechaza_recibir_el_tope_como_punto_flotante(self) -> None:
        with pytest.raises(EntradaNoEsDineroExactoError):
            validar_tope_descuento(0.10)  # type: ignore[arg-type]

    def test_rechaza_un_tope_negativo(self) -> None:
        with pytest.raises(TopeDescuentoFueraDeRangoError) as exc_info:
            validar_tope_descuento(Decimal("-0.01"))

        assr = exc_info.value
        assert assr.codigo == "IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO"

    def test_rechaza_un_tope_mayor_a_uno(self) -> None:
        with pytest.raises(TopeDescuentoFueraDeRangoError):
            validar_tope_descuento(Decimal("1.000001"))

    def test_acepta_el_limite_superior_exacto(self) -> None:
        assert validar_tope_descuento(Decimal("1.000000")) == Decimal("1.000000")

    def test_acepta_el_limite_inferior_exacto(self) -> None:
        assert validar_tope_descuento(Decimal("0")) == Decimal("0.000000")


class TestValidarFormatoPinAutorizacion:
    def test_acepta_seis_digitos(self) -> None:
        assert validar_formato_pin_autorizacion("482913") == "482913"

    def test_acepta_mas_de_seis_digitos(self) -> None:
        assert validar_formato_pin_autorizacion("12345678") == "12345678"

    def test_rechaza_menos_de_seis_digitos(self) -> None:
        with pytest.raises(PinAutorizacionInvalidoError) as exc_info:
            validar_formato_pin_autorizacion("12345")

        assert exc_info.value.codigo == "IDENTIDAD_PIN_AUTORIZACION_INVALIDO"

    def test_rechaza_caracteres_que_no_son_digitos(self) -> None:
        with pytest.raises(PinAutorizacionInvalidoError):
            validar_formato_pin_autorizacion("12a456")


class TestRolConfiereAutorizacionExcepcion:
    def test_un_vendedor_no_puede_definir_pin_de_autorizacion(self) -> None:
        permisos_vendedor = {"VENDER", "REGISTRAR_COBRANZA", "ABRIR_JORNADA", "TRANSFERIR_STOCK"}
        assert rol_confiere_autorizacion_excepcion(permisos_vendedor) is False

    def test_un_supervisor_con_autorizar_descuento_puede_definir_pin(self) -> None:
        permisos_supervisor = {"AUTORIZAR_DESCUENTO", "VER_COSTOS"}
        assert rol_confiere_autorizacion_excepcion(permisos_supervisor) is True

    @pytest.mark.parametrize("permiso", sorted(PERMISOS_AUTORIZACION_EXCEPCION))
    def test_cualquiera_de_los_cuatro_permisos_alcanza(self, permiso: str) -> None:
        assert rol_confiere_autorizacion_excepcion({permiso}) is True

    def test_quitarle_al_rol_los_permisos_de_autorizacion_cambia_el_resultado(self) -> None:
        """Regla pura consumida por el servicio de roles (grupo 8/9) para
        decidir si invalidar el PIN de los usuarios del rol al quitarle su
        último permiso de autorización de excepciones."""
        permisos_antes = {"AUTORIZAR_DESCUENTO", "LIBERAR_UBICACION"}
        permisos_despues = {"LIBERAR_UBICACION"}
        assert rol_confiere_autorizacion_excepcion(permisos_antes) is True
        assert rol_confiere_autorizacion_excepcion(permisos_despues) is False

    def test_conjunto_vacio_no_confiere_autorizacion(self) -> None:
        assert rol_confiere_autorizacion_excepcion(set()) is False
