"""Los cuerpos de las peticiones rechazan campos desconocidos (auditoría de seguridad).

Todo modelo que una ruta recibe en el cuerpo declara `extra="forbid"`: un campo que el servidor no
conoce (por ejemplo un `organizacion_id` que intenta colarse, INV-21) es un 422 y no se descarta
en silencio. Las excepciones están en `EXCEPCIONES` con su razón; una excepción nueva se
justifica acá, no se agrega sin más.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.core.config import Settings
from app.main import crear_app

# Modelo -> razón. Los seis de configuración de `identidad/api.py` conservan `extra="ignore"` a
# propósito: sus pruebas de INV-21/TR-08 (`test_*_configurar.py`, `test_condicion_iva_api.py`,
# `test_redondeo_por_defecto.py`) fijan que un `organizacion_id` ajeno en el cuerpo se ignora y
# la organización sale del token.
_RAZON_INV21 = "INV-21/TR-08: un organizacion_id en el cuerpo se ignora (pruebas de integración)"
EXCEPCIONES: dict[str, str] = {
    "CondicionIvaCambiarRequest": _RAZON_INV21,
    "DescuentoManualConfigurarRequest": _RAZON_INV21,
    "CreditoOrganizacionConfigurarRequest": _RAZON_INV21,
    "NotaVentaConfigurarRequest": _RAZON_INV21,
    "RedondeoPorDefectoDefinirRequest": _RAZON_INV21,
    "OrganizacionDatosConfigurarRequest": _RAZON_INV21,
}

# Pendientes: cuerpos que hoy ignoran los campos extra y todavía no se pasaron a `forbid`. Hacerlo
# exige revisar antes lo que envía cada pantalla y el sobre del lote de sincronización (la PWA con
# versiones viejas en el teléfono), por eso quedan fuera de la pasada de seguridad que cubrió el
# login y la identidad. La lista es un храповик: solo puede achicarse (ver el último test).
_RAZON_PENDIENTE = "pendiente: revisar lo que envía el frontend antes de pasar a forbid"
EXCEPCIONES.update(
    dict.fromkeys(
        [
            "CategoriaCrearRequest",
            "CategoriaModificarRequest",
            "ClienteCrearRequest",
            "ClienteCreditoModificarRequest",
            "ClienteModificarRequest",
            "ClienteVendedorAsignarRequest",
            "CobranzaAnularRequest",
            "CobranzaRegistrarRequest",
            "CompraConfirmarRequest",
            "ConsumidorFinalConfigurarRequest",
            "CostoInformarRequest",
            "LoteComandosRequest",
            "MarcaCrearRequest",
            "MarcaModificarRequest",
            "PagoProveedorAnularRequest",
            "PagoProveedorRegistrarRequest",
            "PresentacionAgregarRequest",
            "PresentacionModificarRequest",
            "PresentacionReferenciaCambiarRequest",
            "ProductoCrearRequest",
            "ProductoModificarRequest",
            "ProveedorCrearRequest",
            "ProveedorModificarRequest",
            "VentaConfirmarRequest",
        ],
        _RAZON_PENDIENTE,
    )
)


@pytest.fixture
def modelos(monkeypatch: pytest.MonkeyPatch) -> dict[str, type[BaseModel]]:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.setenv("JWT_SECRET", "un-secreto-de-prueba-suficientemente-largo")
    return _modelos_de_cuerpo(crear_app(Settings(_env_file=None)))


def _rutas(rutas: Iterable[object]) -> Iterator[APIRoute]:
    """Las rutas con su cuerpo, entrando a los routers incluidos (FastAPI 0.14x los envuelve)."""
    for ruta in rutas:
        if isinstance(ruta, APIRoute):
            yield ruta
        else:
            interno = getattr(ruta, "original_router", None)
            if interno is not None:
                yield from _rutas(interno.routes)


def _modelos_de_cuerpo(app: FastAPI) -> dict[str, type[BaseModel]]:
    modelos: dict[str, type[BaseModel]] = {}
    for ruta in _rutas(app.routes):
        for parametro in ruta.dependant.body_params:
            tipo = parametro.field_info.annotation
            if isinstance(tipo, type) and issubclass(tipo, BaseModel):
                modelos[tipo.__name__] = tipo
    return modelos


def test_se_encuentran_los_modelos_de_cuerpo_de_las_rutas(
    modelos: dict[str, type[BaseModel]],
) -> None:
    assert "LoginRequest" in modelos
    assert "LoteComandosRequest" in modelos


def test_todo_cuerpo_de_peticion_prohibe_campos_extra(
    modelos: dict[str, type[BaseModel]],
) -> None:
    sin_forbid = sorted(
        nombre
        for nombre, modelo in modelos.items()
        if modelo.model_config.get("extra") != "forbid" and nombre not in EXCEPCIONES
    )
    assert sin_forbid == []


def test_las_excepciones_siguen_existiendo_y_siguen_sin_forbid(
    modelos: dict[str, type[BaseModel]],
) -> None:
    obsoletas = sorted(
        nombre
        for nombre in EXCEPCIONES
        if nombre not in modelos or modelos[nombre].model_config.get("extra") == "forbid"
    )
    assert obsoletas == []
