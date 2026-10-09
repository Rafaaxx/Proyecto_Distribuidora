"""Change 14, tarea 8.1: un producto con stock no se desactiva (spec delta
`catalogo/productos-y-presentaciones`, `design.md` D4, D4.1, D4.2), probado en
`catalogo/service.py::modificar_producto` con un verificador de prueba en el puerto
`registrar_verificador_de_stock`. Que `stock` registre el verificador real es de la tarea 8.2.

Reglas citadas: CAT-05, ADR-038 punto 5, INV-21.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_catalogo_service import (  # noqa: F401  (fixtures y ayudas reutilizadas)
    _crear_producto_valido,
    alicuota_id,
    categoria_id,
    organizacion_id,
    proveedor_id,
)

from app.core.clock import FixedClock
from app.modules.catalogo import repository as catalogo_repository
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import ProductoConStockError
from app.modules.catalogo.models import Producto

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

_RELOJ = FixedClock(datetime.now(UTC))


class VerificadorDePrueba:
    """Registra con qué se lo consultó y responde lo que se le pidió."""

    def __init__(self, respuesta: bool) -> None:
        self.respuesta = respuesta
        self.consultas: list[tuple[uuid.UUID, uuid.UUID]] = []

    def __call__(self, organizacion_id: uuid.UUID, producto_id: uuid.UUID, sesion: Session) -> bool:
        self.consultas.append((organizacion_id, producto_id))
        return self.respuesta


@pytest.fixture
def producto(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> Producto:
    creado, _ = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    assert isinstance(creado, Producto)
    return creado


def _modificar(
    db_session: Session,
    organizacion_id: uuid.UUID,
    producto: Producto,
    *,
    activo: bool,
    nombre: str | None = None,
) -> Producto:
    return catalogo_service.modificar_producto(
        organizacion_id,
        db_session,
        _RELOJ,
        producto_id=producto.id,
        codigo=producto.codigo,
        nombre=nombre or producto.nombre,
        categoria_id=producto.categoria_id,
        marca_id=producto.marca_id,
        proveedor_id=producto.proveedor_id,
        unidad_base=producto.unidad_base,
        alicuota_id=producto.alicuota_id,
        activo=activo,
        actor_id=None,
    )


def _activo_en_base(db_session: Session, organizacion_id: uuid.UUID, producto: Producto) -> bool:
    fila = db_session.execute(
        text("SELECT activo FROM producto WHERE organizacion_id = :o AND id = :p"),
        {"o": organizacion_id, "p": producto.id},
    ).scalar_one()
    return bool(fila)


def test_desactivar_con_stock_es_producto_con_stock_y_sigue_activo(
    db_session: Session,
    organizacion_id: uuid.UUID,
    producto: Producto,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verificador = VerificadorDePrueba(True)
    monkeypatch.setattr(catalogo_service, "_VERIFICADOR_DE_STOCK", verificador)

    with pytest.raises(ProductoConStockError) as error:
        _modificar(db_session, organizacion_id, producto, activo=False)

    assert (error.value.codigo, error.value.status_http) == ("PRODUCTO_CON_STOCK", 409)
    assert verificador.consultas == [(organizacion_id, producto.id)]
    assert _activo_en_base(db_session, organizacion_id, producto) is True


def test_desactivar_sin_stock_se_acepta(
    db_session: Session,
    organizacion_id: uuid.UUID,
    producto: Producto,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verificador = VerificadorDePrueba(False)
    monkeypatch.setattr(catalogo_service, "_VERIFICADOR_DE_STOCK", verificador)

    modificado = _modificar(db_session, organizacion_id, producto, activo=False)

    assert modificado.activo is False
    assert verificador.consultas == [(organizacion_id, producto.id)]
    assert _activo_en_base(db_session, organizacion_id, producto) is False


def test_modificar_otros_datos_dejando_el_producto_activo_no_consulta_el_verificador(
    db_session: Session,
    organizacion_id: uuid.UUID,
    producto: Producto,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verificador = VerificadorDePrueba(True)
    monkeypatch.setattr(catalogo_service, "_VERIFICADOR_DE_STOCK", verificador)

    modificado = _modificar(db_session, organizacion_id, producto, activo=True, nombre="Vino B")

    assert modificado.nombre == "Vino B"
    assert verificador.consultas == []


@pytest.mark.parametrize("activo_final", [False, True])
def test_un_producto_ya_inactivo_se_guarda_o_se_reactiva_sin_consultar_el_verificador(
    db_session: Session,
    organizacion_id: uuid.UUID,
    producto: Producto,
    monkeypatch: pytest.MonkeyPatch,
    activo_final: bool,
) -> None:
    """Un inactivo con stock heredado (anterior a la regla) se puede editar y reactivar."""
    db_session.execute(
        text("UPDATE producto SET activo = false WHERE organizacion_id = :o AND id = :p"),
        {"o": organizacion_id, "p": producto.id},
    )
    db_session.expire_all()
    verificador = VerificadorDePrueba(True)
    monkeypatch.setattr(catalogo_service, "_VERIFICADOR_DE_STOCK", verificador)

    modificado = _modificar(db_session, organizacion_id, producto, activo=activo_final)

    assert modificado.activo is activo_final
    assert verificador.consultas == []


def test_sin_verificador_registrado_desactivar_falla_cerrado_y_el_producto_sigue_activo(
    db_session: Session,
    organizacion_id: uuid.UUID,
    producto: Producto,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D4.1: un error de configuración nunca deja desactivar un producto sin comprobar."""
    monkeypatch.setattr(catalogo_service, "_VERIFICADOR_DE_STOCK", None)

    with pytest.raises(RuntimeError, match="No hay verificador de stock registrado"):
        _modificar(db_session, organizacion_id, producto, activo=False)

    assert _activo_en_base(db_session, organizacion_id, producto) is True


def test_sin_verificador_registrado_las_demas_modificaciones_no_fallan(
    db_session: Session,
    organizacion_id: uuid.UUID,
    producto: Producto,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(catalogo_service, "_VERIFICADOR_DE_STOCK", None)

    modificado = _modificar(db_session, organizacion_id, producto, activo=True, nombre="Vino C")

    assert modificado.nombre == "Vino C"


def test_modificar_toma_el_producto_for_update_antes_de_decidir(
    db_session: Session,
    organizacion_id: uuid.UUID,
    producto: Producto,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D4.2: el bloqueo exclusivo del producto serializa la desactivación con todo movimiento
    de stock, que lo toma `FOR SHARE`. La carrera real se prueba en el grupo 14."""
    llamadas: list[str] = []
    original = catalogo_repository.obtener_producto_por_id_para_actualizar

    def espiar(*args: object, **kwargs: object) -> Producto | None:
        llamadas.append("para_actualizar")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    verificador = VerificadorDePrueba(False)

    def verificar(org: uuid.UUID, producto_id: uuid.UUID, sesion: Session) -> bool:
        llamadas.append("verificador")
        return verificador(org, producto_id, sesion)

    monkeypatch.setattr(catalogo_repository, "obtener_producto_por_id_para_actualizar", espiar)
    monkeypatch.setattr(catalogo_service, "_VERIFICADOR_DE_STOCK", verificar)

    _modificar(db_session, organizacion_id, producto, activo=False)

    assert llamadas == ["para_actualizar", "verificador"]
