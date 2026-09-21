"""Pruebas unitarias del dominio puro de `identidad` (tarea 5.1, 5.3).

Cubren las enumeraciones y validaciones de `organizacion` y
`configuracion_organizacion` (`docs/03-modelo-de-datos.md` §4). El dominio
no importa SQLAlchemy ni FastAPI (`docs/02-arquitectura.md` §5.2): estas
pruebas ejercitan funciones puras que reciben strings y devuelven el valor
validado o lanzan un error de dominio con código estable.
"""

from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.modules.identidad.domain.valores import (
    EstadoFacturacionInvalidoError,
    EstadoOrganizacionInvalidoError,
    ModalidadIvaInvalidaError,
    ModoImpositivoInvalidoError,
    PoliticaCreditoInvalidaError,
    RedondeoDireccionInvalidaError,
    SlugOrganizacionInvalidoError,
    ToleranciaOfflineTipoInvalidoError,
    validar_estado_facturacion_default,
    validar_estado_organizacion,
    validar_modalidad_iva_default,
    validar_modo_impositivo,
    validar_politica_credito_default,
    validar_redondeo_direccion,
    validar_slug_organizacion,
    validar_tolerancia_offline_tipo,
)


class TestSlugOrganizacion:
    """`ADR-021`: resuelve la organización en el login antes del token."""

    @pytest.mark.parametrize("valor", ["distribuidora-cuyo", "acme", "org2"])
    def test_acepta_slugs_bien_formados(self, valor: str) -> None:
        assert validar_slug_organizacion(valor) == valor

    @pytest.mark.parametrize(
        "valor",
        ["Distribuidora-Cuyo", "-empieza-con-guion", "termina-con-guion-", "con espacio", ""],
    )
    def test_rechaza_slugs_mal_formados(self, valor: str) -> None:
        with pytest.raises(SlugOrganizacionInvalidoError) as exc_info:
            validar_slug_organizacion(valor)

        assert exc_info.value.codigo == "IDENTIDAD_SLUG_ORGANIZACION_INVALIDO"


class TestEstadoOrganizacion:
    @pytest.mark.parametrize("valor", ["ACTIVA", "SUSPENDIDA"])
    def test_acepta_los_valores_del_dominio_cerrado(self, valor: str) -> None:
        assert validar_estado_organizacion(valor) == valor

    def test_rechaza_un_estado_desconocido(self) -> None:
        with pytest.raises(EstadoOrganizacionInvalidoError) as exc_info:
            validar_estado_organizacion("BORRADA")

        assert issubclass(EstadoOrganizacionInvalidoError, DomainError)
        assert exc_info.value.codigo == "IDENTIDAD_ESTADO_ORGANIZACION_INVALIDO"


class TestModoImpositivo:
    @pytest.mark.parametrize("valor", ["A", "B", "C"])
    def test_acepta_los_valores_del_dominio_cerrado(self, valor: str) -> None:
        assert validar_modo_impositivo(valor) == valor

    def test_rechaza_un_modo_fuera_de_dominio(self) -> None:
        with pytest.raises(ModoImpositivoInvalidoError):
            validar_modo_impositivo("D")


class TestPoliticaCreditoDefault:
    @pytest.mark.parametrize("valor", ["ADVERTIR", "AUTORIZAR", "BLOQUEAR"])
    def test_acepta_los_valores_del_dominio_cerrado(self, valor: str) -> None:
        assert validar_politica_credito_default(valor) == valor

    def test_rechaza_una_politica_fuera_de_dominio(self) -> None:
        with pytest.raises(PoliticaCreditoInvalidaError):
            validar_politica_credito_default("IGNORAR")


class TestToleranciaOfflineTipo:
    @pytest.mark.parametrize("valor", ["IMPORTE", "PORCENTAJE"])
    def test_acepta_los_valores_del_dominio_cerrado(self, valor: str) -> None:
        assert validar_tolerancia_offline_tipo(valor) == valor

    def test_rechaza_un_tipo_fuera_de_dominio(self) -> None:
        with pytest.raises(ToleranciaOfflineTipoInvalidoError):
            validar_tolerancia_offline_tipo("UNIDADES")


class TestRedondeoDireccion:
    @pytest.mark.parametrize("valor", ["ARRIBA", "CERCANO", "ABAJO"])
    def test_acepta_los_valores_del_dominio_cerrado(self, valor: str) -> None:
        assert validar_redondeo_direccion(valor) == valor

    def test_rechaza_una_direccion_fuera_de_dominio(self) -> None:
        with pytest.raises(RedondeoDireccionInvalidaError):
            validar_redondeo_direccion("MEDIO")


class TestEstadoFacturacionDefault:
    @pytest.mark.parametrize("valor", ["NO_REQUIERE", "PENDIENTE"])
    def test_acepta_los_valores_del_dominio_cerrado(self, valor: str) -> None:
        assert validar_estado_facturacion_default(valor) == valor

    def test_rechaza_un_estado_fuera_de_dominio(self) -> None:
        with pytest.raises(EstadoFacturacionInvalidoError):
            validar_estado_facturacion_default("FACTURADA")


class TestModalidadIvaDefault:
    @pytest.mark.parametrize("valor", ["CLIENTE", "ABSORBIDO"])
    def test_acepta_los_valores_del_dominio_cerrado(self, valor: str) -> None:
        assert validar_modalidad_iva_default(valor) == valor

    def test_rechaza_una_modalidad_fuera_de_dominio(self) -> None:
        with pytest.raises(ModalidadIvaInvalidaError):
            validar_modalidad_iva_default("MIXTA")
