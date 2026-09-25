"""Change 06, grupo 8: servicios de `proveedores` (`proveedores/service.py`)
y el puerto D9-A que `catalogo/service.py` expone.

Cubre las tareas 8.2 (alta/modificación/consultas de proveedor, D5/ADR-026),
8.3 (`informar_costos`, D3/D4/D12/D14, INV-01, [ALTA: cálculo de costos]),
8.4 (lecturas para el change 13) y 8.5 (verificador `costo_informado`,
INV-18, con el servicio de catálogo real -- sin verificador de prueba)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import UnidadesCongeladasError
from app.modules.catalogo.domain.presentaciones import DatosPresentacion
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad.models import Organizacion, Rol, Usuario
from app.modules.proveedores import service as proveedores_service
from app.modules.proveedores.domain.errores import (
    CuitInvalidoError,
    NombreDuplicadoError,
    NombreInvalidoError,
    PresentacionInvalidaError,
    ProductoInactivoError,
    ProveedorConProductosActivosError,
    ProveedorInactivoError,
    ProveedorNoCorrespondeError,
    RecursoNoEncontradoError,
)
from app.modules.proveedores.domain.lote import CostoDelLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

_MOMENTO = datetime(2026, 9, 24, tzinfo=UTC)
_RELOJ = FixedClock(_MOMENTO)


@pytest.fixture
def organizacion_id(db_session: Session) -> uuid.UUID:
    organizacion = Organizacion(
        id=uuid.uuid4(),
        nombre="Distribuidora de prueba",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Buenos_Aires",
        estado="ACTIVA",
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion.id


@pytest.fixture
def otra_organizacion_id(db_session: Session) -> uuid.UUID:
    organizacion = Organizacion(
        id=uuid.uuid4(),
        nombre="Otra distribuidora",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Buenos_Aires",
        estado="ACTIVA",
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion.id


@pytest.fixture
def alicuota_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    alicuota = AlicuotaIva(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        nombre="21%",
        valor=Decimal("0.210000"),
        activo=True,
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(alicuota)
    db_session.flush()
    return alicuota.id


@pytest.fixture
def usuario_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    rol = Rol(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        nombre="Rol de prueba",
        tope_descuento=Decimal("0"),
        activo=True,
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(rol)
    db_session.flush()

    usuario = Usuario(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        usuario=f"usuario-{uuid.uuid4().hex[:8]}",
        nombre="Usuario de prueba",
        email=None,
        password_hash="hash-de-prueba",
        rol_id=rol.id,
        estado="ACTIVO",
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(usuario)
    db_session.flush()
    return usuario.id


@pytest.fixture
def categoria_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    categoria = catalogo_service.crear_categoria(
        organizacion_id,
        db_session,
        _RELOJ,
        nombre=f"Categoria-{uuid.uuid4().hex[:6]}",
        actor_id=None,
    )
    return categoria.id


def _crear_proveedor(
    db_session: Session,
    organizacion_id: uuid.UUID,
    *,
    nombre: str | None = None,
) -> uuid.UUID:
    proveedor = proveedores_service.crear_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        nombre=nombre or f"Proveedor-{uuid.uuid4().hex[:8]}",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        actor_id=None,
    )
    return proveedor.id


def _crear_producto_con_presentacion(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    *,
    activo: bool = True,
    usar_en_compra: bool = True,
) -> tuple[uuid.UUID, uuid.UUID]:
    producto, presentaciones = catalogo_service.crear_producto(
        organizacion_id,
        db_session,
        _RELOJ,
        codigo=f"COD-{uuid.uuid4().hex[:8]}",
        nombre="Producto de prueba",
        categoria_id=categoria_id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="unidad",
        alicuota_id=alicuota_id,
        presentaciones=[
            DatosPresentacion(
                nombre="Caja x12",
                unidades_base=12,
                usar_en_venta=True,
                usar_en_compra=usar_en_compra,
                es_referencia=True,
            )
        ],
        actor_id=None,
    )
    if not activo:
        catalogo_service.modificar_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            producto_id=producto.id,
            codigo=producto.codigo,
            nombre=producto.nombre,
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base=producto.unidad_base,
            alicuota_id=alicuota_id,
            activo=False,
            actor_id=None,
        )
    return producto.id, presentaciones[0].id


# --- tarea 8.2: alta/modificación/consultas de proveedor -------------------


def test_crear_proveedor_normaliza_nombre_y_nace_activo(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    proveedor = proveedores_service.crear_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        nombre="  Bodega Andina  ",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        actor_id=None,
    )
    assert proveedor.nombre == "Bodega Andina"
    assert proveedor.activo is True


def test_crear_proveedor_nombre_duplicado_rechaza(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    nombre = f"Distribuidora Norte-{uuid.uuid4().hex[:6]}"
    _crear_proveedor(db_session, organizacion_id, nombre=nombre)
    with pytest.raises(NombreDuplicadoError):
        _crear_proveedor(db_session, organizacion_id, nombre=nombre)


def test_crear_proveedor_nombre_vacio_rechaza(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    """13.1 -- spec `fichas-de-proveedor`, escenario "Nombre vacío": sin
    prueba a nivel de servicio (solo existía a nivel de dominio puro en
    `test_proveedores_domain_normalizacion.py`)."""
    with pytest.raises(NombreInvalidoError):
        proveedores_service.crear_proveedor(
            organizacion_id,
            db_session,
            _RELOJ,
            nombre="   ",
            cuit=None,
            contacto=None,
            telefono=None,
            email=None,
            actor_id=None,
        )


def test_crear_proveedor_cuit_invalido_rechaza(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    with pytest.raises(CuitInvalidoError):
        proveedores_service.crear_proveedor(
            organizacion_id,
            db_session,
            _RELOJ,
            nombre="Bodega Andina",
            cuit="123",
            contacto=None,
            telefono=None,
            email=None,
            actor_id=None,
        )


def test_crear_proveedor_cuit_valido_se_normaliza(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    proveedor = proveedores_service.crear_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        nombre="Bodega Andina",
        cuit="30-71234567-1",
        contacto=None,
        telefono=None,
        email=None,
        actor_id=None,
    )
    assert proveedor.cuit == "30712345671"


def test_modificar_proveedor(db_session: Session, organizacion_id: uuid.UUID) -> None:
    proveedor_id = _crear_proveedor(db_session, organizacion_id)
    actualizado = proveedores_service.modificar_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        proveedor_id=proveedor_id,
        nombre="Nuevo nombre",
        cuit=None,
        contacto="Juan",
        telefono=None,
        email=None,
        activo=True,
        actor_id=None,
    )
    assert actualizado.nombre == "Nuevo nombre"
    assert actualizado.contacto == "Juan"


def test_modificar_proveedor_de_otra_organizacion_da_404(
    db_session: Session, organizacion_id: uuid.UUID, otra_organizacion_id: uuid.UUID
) -> None:
    proveedor_id = _crear_proveedor(db_session, otra_organizacion_id)
    with pytest.raises(RecursoNoEncontradoError):
        proveedores_service.modificar_proveedor(
            organizacion_id,
            db_session,
            _RELOJ,
            proveedor_id=proveedor_id,
            nombre="X",
            cuit=None,
            contacto=None,
            telefono=None,
            email=None,
            activo=True,
            actor_id=None,
        )


def test_d5_desactivar_proveedor_con_productos_activos_rechaza(
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    """ADR-026: simétrico con `CategoriaConProductosActivosError` del 05."""
    proveedor_id = _crear_proveedor(db_session, organizacion_id)
    _crear_producto_con_presentacion(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    with pytest.raises(ProveedorConProductosActivosError):
        proveedores_service.modificar_proveedor(
            organizacion_id,
            db_session,
            _RELOJ,
            proveedor_id=proveedor_id,
            nombre="Proveedor",
            cuit=None,
            contacto=None,
            telefono=None,
            email=None,
            activo=False,
            actor_id=None,
        )
    proveedor = proveedores_service.obtener_proveedor(organizacion_id, proveedor_id, db_session)
    assert proveedor is not None
    assert proveedor.activo is True


def test_desactivar_y_reactivar_proveedor_sin_productos_activos_conserva_historial(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """13.1 -- spec `fichas-de-proveedor`, escenario "Desactivar y
    reactivar un proveedor sin productos activos": sin prueba del ciclo
    completo (solo existían pruebas de cada mitad por separado); "su
    historial de costos no cambia" (CST-03) se verifica con un costo
    informado real antes y después del ciclo."""
    proveedor_id = _crear_proveedor(db_session, organizacion_id, nombre="Bodega Sur")
    producto_id, presentacion_id = _crear_producto_con_presentacion(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    filas = proveedores_service.informar_costos(
        organizacion_id,
        db_session,
        _RELOJ,
        proveedor_id=proveedor_id,
        costos=[
            CostoDelLote(
                producto_id=producto_id,
                presentacion_id=presentacion_id,
                valor=Decimal("1000.00"),
                incluye_iva=False,
                bonificacion=Decimal("0"),
                vigencia_desde=date(2026, 9, 1),
                observacion=None,
            )
        ],
        operation_id=uuid.uuid4(),
        actor_id=usuario_id,
    )
    costo_id = filas[0].id

    # Sin productos activos: el producto se desactiva antes de desactivar el
    # proveedor (D5/ADR-026, `test_d5_desactivar_proveedor_con_productos_activos_rechaza`
    # ya cubre el caso simétrico con el producto activo).
    catalogo_service.modificar_producto(
        organizacion_id,
        db_session,
        _RELOJ,
        producto_id=producto_id,
        codigo=(catalogo_service.obtener_producto(organizacion_id, producto_id, db_session)).codigo,
        nombre="Producto de prueba",
        categoria_id=categoria_id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="unidad",
        alicuota_id=alicuota_id,
        activo=False,
        actor_id=None,
    )

    desactivado = proveedores_service.modificar_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        proveedor_id=proveedor_id,
        nombre="Bodega Sur",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        activo=False,
        actor_id=None,
    )
    assert desactivado.activo is False

    reactivado = proveedores_service.modificar_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        proveedor_id=proveedor_id,
        nombre="Bodega Sur",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        activo=True,
        actor_id=None,
    )
    assert reactivado.activo is True

    costo_intacto = proveedores_service.obtener_costo_informado_vigente(
        organizacion_id, producto_id, date(2026, 9, 1), db_session
    )
    assert costo_intacto is not None
    assert costo_intacto.id == costo_id
    assert costo_intacto.valor == Decimal("1000.00")


def test_listar_proveedores_y_opciones(db_session: Session, organizacion_id: uuid.UUID) -> None:
    activo_id = _crear_proveedor(db_session, organizacion_id, nombre="Activo")
    inactivo_id = _crear_proveedor(db_session, organizacion_id, nombre="Inactivo")
    proveedores_service.modificar_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        proveedor_id=inactivo_id,
        nombre="Inactivo",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        activo=False,
        actor_id=None,
    )

    todos, _ = proveedores_service.listar_proveedores(organizacion_id, db_session)
    assert {p.id for p in todos} == {activo_id, inactivo_id}

    opciones, _ = proveedores_service.listar_opciones_de_proveedores(organizacion_id, db_session)
    assert [p.id for p in opciones] == [activo_id]


# --- tarea 8.3: informar_costos ([ALTA: cálculo de costos]) ----------------


def test_informar_costos_calcula_y_persiste(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor_id = _crear_proveedor(db_session, organizacion_id)
    producto_id, presentacion_id = _crear_producto_con_presentacion(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    costos = [
        CostoDelLote(
            producto_id=producto_id,
            presentacion_id=presentacion_id,
            valor=Decimal("18000.00"),
            incluye_iva=True,
            bonificacion=Decimal("0"),
            vigencia_desde=date(2026, 9, 1),
            observacion=None,
        )
    ]
    filas = proveedores_service.informar_costos(
        organizacion_id,
        db_session,
        _RELOJ,
        proveedor_id=proveedor_id,
        costos=costos,
        operation_id=uuid.uuid4(),
        actor_id=usuario_id,
    )
    assert len(filas) == 1
    fila = filas[0]
    # `01` §6.1: 18000 / 1.21 / 12 = 1239.669421 (redondeo hacia arriba).
    assert fila.costo_base == Decimal("1239.669421")
    assert fila.alicuota_aplicada == Decimal("0.210000")


def test_d3_informar_costos_proveedor_no_corresponde_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor_id = _crear_proveedor(db_session, organizacion_id)
    otro_proveedor_id = _crear_proveedor(db_session, organizacion_id)
    producto_id, presentacion_id = _crear_producto_con_presentacion(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    costos = [
        CostoDelLote(
            producto_id=producto_id,
            presentacion_id=presentacion_id,
            valor=Decimal("100.00"),
            incluye_iva=False,
            bonificacion=Decimal("0"),
            vigencia_desde=date(2026, 9, 1),
            observacion=None,
        )
    ]
    with pytest.raises(ProveedorNoCorrespondeError):
        proveedores_service.informar_costos(
            organizacion_id,
            db_session,
            _RELOJ,
            proveedor_id=otro_proveedor_id,
            costos=costos,
            operation_id=uuid.uuid4(),
            actor_id=usuario_id,
        )


def test_d5_informar_costos_proveedor_inactivo_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor_id = _crear_proveedor(db_session, organizacion_id)
    producto_id, presentacion_id = _crear_producto_con_presentacion(
        db_session,
        organizacion_id,
        categoria_id,
        alicuota_id,
        proveedor_id,
        # ADR-026: un proveedor con productos activos no se desactiva. Se
        # crea el producto ya inactivo para poder desactivar el proveedor y
        # así poder probar, con datos, que ese proveedor inactivo no recibe
        # costos (D5) sin chocar con esa otra regla.
        activo=False,
    )
    proveedores_service.modificar_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        proveedor_id=proveedor_id,
        nombre="Proveedor",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        activo=False,
        actor_id=None,
    )
    costos = [
        CostoDelLote(
            producto_id=producto_id,
            presentacion_id=presentacion_id,
            valor=Decimal("100.00"),
            incluye_iva=False,
            bonificacion=Decimal("0"),
            vigencia_desde=date(2026, 9, 1),
            observacion=None,
        )
    ]
    with pytest.raises(ProveedorInactivoError):
        proveedores_service.informar_costos(
            organizacion_id,
            db_session,
            _RELOJ,
            proveedor_id=proveedor_id,
            costos=costos,
            operation_id=uuid.uuid4(),
            actor_id=usuario_id,
        )


def test_informar_costos_producto_inactivo_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor_id = _crear_proveedor(db_session, organizacion_id)
    producto_id, presentacion_id = _crear_producto_con_presentacion(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id, activo=False
    )
    costos = [
        CostoDelLote(
            producto_id=producto_id,
            presentacion_id=presentacion_id,
            valor=Decimal("100.00"),
            incluye_iva=False,
            bonificacion=Decimal("0"),
            vigencia_desde=date(2026, 9, 1),
            observacion=None,
        )
    ]
    with pytest.raises(ProductoInactivoError):
        proveedores_service.informar_costos(
            organizacion_id,
            db_session,
            _RELOJ,
            proveedor_id=proveedor_id,
            costos=costos,
            operation_id=uuid.uuid4(),
            actor_id=usuario_id,
        )


def test_informar_costos_presentacion_que_no_es_de_compra_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor_id = _crear_proveedor(db_session, organizacion_id)
    producto_id, presentacion_id = _crear_producto_con_presentacion(
        db_session,
        organizacion_id,
        categoria_id,
        alicuota_id,
        proveedor_id,
        usar_en_compra=False,
    )
    costos = [
        CostoDelLote(
            producto_id=producto_id,
            presentacion_id=presentacion_id,
            valor=Decimal("100.00"),
            incluye_iva=False,
            bonificacion=Decimal("0"),
            vigencia_desde=date(2026, 9, 1),
            observacion=None,
        )
    ]
    with pytest.raises(PresentacionInvalidaError):
        proveedores_service.informar_costos(
            organizacion_id,
            db_session,
            _RELOJ,
            proveedor_id=proveedor_id,
            costos=costos,
            operation_id=uuid.uuid4(),
            actor_id=usuario_id,
        )


def test_inv01_tercer_costo_invalido_no_deja_nada_escrito(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """INV-01: si el tercer costo del lote es inválido (presentación que no
    es de compra), NINGUNO de los tres queda escrito -- ni siquiera los dos
    primeros, válidos por sí solos."""
    proveedor_id = _crear_proveedor(db_session, organizacion_id)
    producto_id, presentacion_id = _crear_producto_con_presentacion(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    _, presentacion_no_compra_id = _crear_producto_con_presentacion(
        db_session,
        organizacion_id,
        categoria_id,
        alicuota_id,
        proveedor_id,
        usar_en_compra=False,
    )
    costos = [
        CostoDelLote(
            producto_id=producto_id,
            presentacion_id=presentacion_id,
            valor=Decimal("100.00"),
            incluye_iva=False,
            bonificacion=Decimal("0"),
            vigencia_desde=date(2026, 1, 1),
            observacion=None,
        ),
        CostoDelLote(
            producto_id=producto_id,
            presentacion_id=presentacion_id,
            valor=Decimal("200.00"),
            incluye_iva=False,
            bonificacion=Decimal("0"),
            vigencia_desde=date(2026, 2, 1),
            observacion=None,
        ),
        CostoDelLote(
            producto_id=producto_id,
            presentacion_id=presentacion_no_compra_id,
            valor=Decimal("300.00"),
            incluye_iva=False,
            bonificacion=Decimal("0"),
            vigencia_desde=date(2026, 3, 1),
            observacion=None,
        ),
    ]
    with pytest.raises(PresentacionInvalidaError):
        proveedores_service.informar_costos(
            organizacion_id,
            db_session,
            _RELOJ,
            proveedor_id=proveedor_id,
            costos=costos,
            operation_id=uuid.uuid4(),
            actor_id=usuario_id,
        )
    historial, _ = proveedores_service.listar_historial_costos(
        organizacion_id, producto_id, db_session
    )
    assert historial == []


# --- tarea 8.4: lecturas para el change 13 ---------------------------------


def test_obtener_costo_informado_vigente_y_listar_historial(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor_id = _crear_proveedor(db_session, organizacion_id)
    producto_id, presentacion_id = _crear_producto_con_presentacion(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    proveedores_service.informar_costos(
        organizacion_id,
        db_session,
        _RELOJ,
        proveedor_id=proveedor_id,
        costos=[
            CostoDelLote(
                producto_id=producto_id,
                presentacion_id=presentacion_id,
                valor=Decimal("100.00"),
                incluye_iva=False,
                bonificacion=Decimal("0"),
                vigencia_desde=date(2026, 1, 1),
                observacion=None,
            )
        ],
        operation_id=uuid.uuid4(),
        actor_id=usuario_id,
    )

    vigente = proveedores_service.obtener_costo_informado_vigente(
        organizacion_id, producto_id, date(2026, 9, 24), db_session
    )
    assert vigente is not None

    historial, _ = proveedores_service.listar_historial_costos(
        organizacion_id, producto_id, db_session
    )
    assert len(historial) == 1

    # P11 (aprobado en la verificación manual 13.5, opción B): el último
    # costo informado por presentación, para la única presentación de este
    # producto, es el mismo que el vigente.
    por_presentacion = proveedores_service.listar_ultimo_costo_por_presentacion(
        organizacion_id, producto_id, date(2026, 9, 24), db_session
    )
    assert len(por_presentacion) == 1
    assert por_presentacion[0].id == vigente.id


# --- tarea 8.5: verificador de uso costo_informado (INV-18, D1) ------------


def test_inv18_presentacion_con_costo_informado_es_congelada(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """D1 (opción A): informar un costo cuenta como uso de la presentación
    -- el verificador registrado por este módulo en `catalogo_service`
    (ADR-023) hace que `modificar_presentacion` rechace un cambio de
    unidades con `UnidadesCongeladasError`, SIN ningún verificador de
    prueba de por medio (servicio de catálogo real)."""
    proveedor_id = _crear_proveedor(db_session, organizacion_id)
    producto_id, presentacion_id = _crear_producto_con_presentacion(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    proveedores_service.informar_costos(
        organizacion_id,
        db_session,
        _RELOJ,
        proveedor_id=proveedor_id,
        costos=[
            CostoDelLote(
                producto_id=producto_id,
                presentacion_id=presentacion_id,
                valor=Decimal("18000.00"),
                incluye_iva=True,
                bonificacion=Decimal("0"),
                vigencia_desde=date(2026, 9, 1),
                observacion=None,
            )
        ],
        operation_id=uuid.uuid4(),
        actor_id=usuario_id,
    )

    presentacion = catalogo_service.obtener_presentacion(
        organizacion_id, presentacion_id, db_session
    )
    assert presentacion is not None

    with pytest.raises(UnidadesCongeladasError):
        catalogo_service.modificar_presentacion(
            organizacion_id,
            db_session,
            _RELOJ,
            presentacion_id=presentacion_id,
            nombre=presentacion.nombre,
            unidades_base=presentacion.unidades_base + 1,
            usar_en_venta=presentacion.usar_en_venta,
            usar_en_compra=presentacion.usar_en_compra,
            activo=True,
            actor_id=None,
        )


def test_inv18_presentacion_sin_costo_informado_sigue_editable(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
) -> None:
    proveedor_id = _crear_proveedor(db_session, organizacion_id)
    _, presentacion_id = _crear_producto_con_presentacion(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    presentacion = catalogo_service.obtener_presentacion(
        organizacion_id, presentacion_id, db_session
    )
    assert presentacion is not None
    # `obtener_presentacion`/`modificar_presentacion` devuelven la MISMA
    # instancia ORM (identity map): se captura el valor original ANTES de
    # mutar, para no comparar contra el propio valor ya actualizado.
    unidades_originales = presentacion.unidades_base

    modificada = catalogo_service.modificar_presentacion(
        organizacion_id,
        db_session,
        _RELOJ,
        presentacion_id=presentacion_id,
        nombre=presentacion.nombre,
        unidades_base=unidades_originales + 1,
        usar_en_venta=presentacion.usar_en_venta,
        usar_en_compra=presentacion.usar_en_compra,
        activo=True,
        actor_id=None,
    )
    assert modificada.unidades_base == unidades_originales + 1
