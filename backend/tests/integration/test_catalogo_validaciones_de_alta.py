"""Change 10, tarea 12.1: textos obligatorios del alta de producto
(`catalogo/service.py`, `specs/importacion/importacion-de-maestros` y delta de
`catalogo/productos-y-presentaciones`).

`PRODUCTO_CREAR` rechazaba un producto con nombre, unidad base o nombre de presentación
vacíos o solo espacios y los guardaba tal cual. La regla vive en el dominio de catálogo
(`domain/nombres.py`), así que la pantalla, el bus y la importación de productos la
comparten sin duplicarla (TR-10). Nada se escribe si falla (INV-01).

Códigos: `NOMBRE_INVALIDO` (el mismo de categoría, marca, proveedor, cliente y ubicación)
para el nombre del producto y el de una presentación, y `VALOR_OBLIGATORIO` para la unidad
base. Los textos válidos se guardan recortados, como el código (CAT-01).

Reglas citadas: CAT-01, CAT-02, INV-01, TR-10.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_proveedor
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import NombreInvalidoError, ValorObligatorioError
from app.modules.catalogo.domain.presentaciones import DatosPresentacion
from app.modules.catalogo.models import Presentacion, Producto
from app.modules.configuracion.models import AlicuotaIva

# Registra el puerto de consulta de proveedor que `crear_producto` exige (D9-A, ADR-025).
from app.modules.proveedores import service as proveedores_service  # noqa: F401

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

BOTELLA = DatosPresentacion("Botella", 1, True, True, True)
CAJA = DatosPresentacion("Caja x6", 6, True, True, False)


class Mundo:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.categoria_id = catalogo_service.crear_categoria(
            self.org, sesion, RELOJ, nombre="Vinos", actor_id=None
        ).id
        alicuota = AlicuotaIva(
            id=uuid.uuid4(),
            organizacion_id=self.org,
            nombre="21%",
            valor="0.210000",
            activo=True,
            creado_en=MOMENTO,
            actualizado_en=MOMENTO,
        )
        sesion.add(alicuota)
        sesion.flush()
        self.alicuota_id = alicuota.id
        self.proveedor_id = crear_proveedor(sesion, self.org)

    def crear(
        self,
        *,
        codigo: str = "VA-750",
        nombre: str = "Vino A",
        unidad_base: str = "botella",
        presentaciones: list[DatosPresentacion] | None = None,
    ) -> Producto:
        producto, _ = catalogo_service.crear_producto(
            self.org,
            self.sesion,
            RELOJ,
            codigo=codigo,
            nombre=nombre,
            categoria_id=self.categoria_id,
            marca_id=None,
            proveedor_id=self.proveedor_id,
            unidad_base=unidad_base,
            alicuota_id=self.alicuota_id,
            presentaciones=[BOTELLA] if presentaciones is None else presentaciones,
            actor_id=None,
        )
        return producto

    def cantidad(self, modelo: type[Producto] | type[Presentacion]) -> int:
        return (
            self.sesion.scalar(
                select(func.count()).select_from(modelo).where(modelo.organizacion_id == self.org)
            )
            or 0
        )


@pytest.fixture
def mundo(db_session: Session) -> Mundo:
    return Mundo(db_session)


# --- nombre del producto -------------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["", " ", "   \t "])
def test_nombre_de_producto_vacio_o_de_espacios_es_nombre_invalido_y_no_escribe(
    mundo: Mundo, nombre: str
) -> None:
    with pytest.raises(NombreInvalidoError) as error:
        mundo.crear(nombre=nombre)

    assert error.value.codigo == "NOMBRE_INVALIDO"
    assert (mundo.cantidad(Producto), mundo.cantidad(Presentacion)) == (0, 0)


# --- unidad base ------------------------------------------------------------------------------


@pytest.mark.parametrize("unidad_base", ["", " ", "\t"])
def test_unidad_base_vacia_o_de_espacios_es_valor_obligatorio_y_no_escribe(
    mundo: Mundo, unidad_base: str
) -> None:
    with pytest.raises(ValorObligatorioError) as error:
        mundo.crear(unidad_base=unidad_base)

    assert error.value.codigo == "VALOR_OBLIGATORIO"
    assert (mundo.cantidad(Producto), mundo.cantidad(Presentacion)) == (0, 0)


# --- nombre de una presentación ---------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["", "  "])
@pytest.mark.parametrize("lugar", [0, 1])
def test_nombre_de_presentacion_vacio_en_cualquier_lugar_rechaza_el_producto_entero(
    mundo: Mundo, nombre: str, lugar: int
) -> None:
    mala = DatosPresentacion(nombre, 6, True, True, False)
    presentaciones = (
        [BOTELLA, mala] if lugar == 1 else [mala, DatosPresentacion("Botella", 1, True, True, True)]
    )

    with pytest.raises(NombreInvalidoError):
        mundo.crear(presentaciones=presentaciones)

    assert (mundo.cantidad(Producto), mundo.cantidad(Presentacion)) == (0, 0)


# --- alta válida --------------------------------------------------------------------------------


def test_alta_valida_se_guarda_igual_y_con_los_textos_recortados(mundo: Mundo) -> None:
    exacto = mundo.crear(
        codigo="A-1", nombre="Vino A", unidad_base="botella", presentaciones=[BOTELLA, CAJA]
    )
    holgado = mundo.crear(
        codigo="A-2",
        nombre="  Vino B ",
        unidad_base=" botella  ",
        presentaciones=[DatosPresentacion(" Botella ", 1, True, True, True)],
    )

    mundo.sesion.refresh(exacto)
    mundo.sesion.refresh(holgado)
    assert (exacto.nombre, exacto.unidad_base) == ("Vino A", "botella")
    assert (holgado.nombre, holgado.unidad_base) == ("Vino B", "botella")
    nombres = sorted(
        p.nombre
        for p in mundo.sesion.scalars(
            select(Presentacion).where(Presentacion.organizacion_id == mundo.org)
        )
    )
    assert nombres == ["Botella", "Botella", "Caja x6"]


# --- modificación y presentaciones sueltas (misma regla, mismo dominio) --------------------------


def test_modificar_producto_con_nombre_o_unidad_vacios_rechaza_y_conserva_lo_guardado(
    mundo: Mundo,
) -> None:
    producto = mundo.crear()
    datos = {
        "codigo": "VA-750",
        "categoria_id": mundo.categoria_id,
        "marca_id": None,
        "proveedor_id": mundo.proveedor_id,
        "alicuota_id": mundo.alicuota_id,
        "activo": True,
        "actor_id": None,
    }

    with pytest.raises(NombreInvalidoError):
        catalogo_service.modificar_producto(
            mundo.org,
            mundo.sesion,
            RELOJ,
            producto_id=producto.id,
            nombre=" ",
            unidad_base="botella",
            **datos,
        )
    with pytest.raises(ValorObligatorioError):
        catalogo_service.modificar_producto(
            mundo.org,
            mundo.sesion,
            RELOJ,
            producto_id=producto.id,
            nombre="Vino A",
            unidad_base="",
            **datos,
        )

    mundo.sesion.refresh(producto)
    assert (producto.nombre, producto.unidad_base) == ("Vino A", "botella")


def test_agregar_presentacion_con_nombre_vacio_rechaza(mundo: Mundo) -> None:
    producto = mundo.crear()

    with pytest.raises(NombreInvalidoError):
        catalogo_service.agregar_presentacion(
            mundo.org,
            mundo.sesion,
            RELOJ,
            producto_id=producto.id,
            nombre="  ",
            unidades_base=6,
            usar_en_venta=True,
            usar_en_compra=True,
            actor_id=None,
        )

    assert mundo.cantidad(Presentacion) == 1


def test_modificar_presentacion_con_nombre_vacio_rechaza_y_con_nombre_valido_lo_recorta(
    mundo: Mundo,
) -> None:
    producto = mundo.crear(presentaciones=[BOTELLA, CAJA])
    caja = next(p for p in mundo.sesion.scalars(select(Presentacion)) if p.nombre == "Caja x6")
    cambios = {
        "unidades_base": 6,
        "usar_en_venta": True,
        "usar_en_compra": True,
        "activo": True,
        "actor_id": None,
    }

    with pytest.raises(NombreInvalidoError):
        catalogo_service.modificar_presentacion(
            mundo.org, mundo.sesion, RELOJ, presentacion_id=caja.id, nombre="", **cambios
        )
    modificada = catalogo_service.modificar_presentacion(
        mundo.org, mundo.sesion, RELOJ, presentacion_id=caja.id, nombre="  Caja x 6 ", **cambios
    )

    assert modificada.nombre == "Caja x 6"
    assert producto.id == modificada.producto_id
