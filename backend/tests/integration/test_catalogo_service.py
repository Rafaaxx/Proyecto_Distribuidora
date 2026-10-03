"""Change 05, grupo 7: servicio de catálogo (`catalogo/service.py`).
Cubre las tareas 7.1 a 7.7: verificadores de uso (D2), categoría/marca
(CAT-01, CAT-05, D11), alta de producto (INV-01, CAT-01 a CAT-06),
modificación de producto, presentaciones (CAT-02, CAT-03, CAT-04, INV-18)
y las lecturas públicas."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from cuentas_corrientes_utiles import agregar_configuracion
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.catalogo import repository as catalogo_repository
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import (
    AlicuotaInactivaError,
    CategoriaConProductosActivosError,
    CategoriaInactivaError,
    CodigoDuplicadoError,
    NombreDuplicadoError,
    NombreInvalidoError,
    ProductoSinPresentacionesError,
    ProveedorInactivoError,
    RecursoNoEncontradoError,
    ReferenciaInvalidaError,
    UnidadesCongeladasError,
    UnidadesInvalidasError,
)
from app.modules.catalogo.domain.presentaciones import DatosPresentacion
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad.models import Organizacion, Rol, Usuario

# Change 06, tarea 8.1: importar `proveedores.service` registra en
# `catalogo_service` el puerto de consulta de proveedor (D9-A, ADR-025) y
# el verificador de uso de `costo_informado` (D1) -- mismo patrón que
# `app.main` (import de efecto secundario). Sin este import, `catalogo`
# falla cerrado (`RuntimeError`, D9-A) apenas se intenta crear/modificar un
# producto.
from app.modules.proveedores import service as proveedores_service
from app.modules.proveedores.domain.lote import CostoDelLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

_MOMENTO = datetime.now(UTC)
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
    agregar_configuracion(db_session, organizacion.id)
    return organizacion.id


@pytest.fixture
def alicuota_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    alicuota = AlicuotaIva(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        nombre="21%",
        valor="0.210000",
        activo=True,
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(alicuota)
    db_session.flush()
    return alicuota.id


@pytest.fixture
def alicuota_inactiva_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    alicuota = AlicuotaIva(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        nombre="10.5%",
        valor="0.105000",
        activo=False,
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(alicuota)
    db_session.flush()
    return alicuota.id


@pytest.fixture
def categoria_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    categoria = catalogo_service.crear_categoria(
        organizacion_id, db_session, _RELOJ, nombre=f"Vinos-{uuid.uuid4().hex[:6]}", actor_id=None
    )
    return categoria.id


@pytest.fixture
def proveedor_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    """Change 06, D9-A: `crear_producto`/`modificar_producto` ahora exigen
    un proveedor activo y existente en la organización."""
    proveedor = proveedores_service.crear_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        nombre=f"Proveedor-{uuid.uuid4().hex[:8]}",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        actor_id=None,
    )
    return proveedor.id


@pytest.fixture
def proveedor_inactivo_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    proveedor = proveedores_service.crear_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        nombre=f"Proveedor inactivo-{uuid.uuid4().hex[:8]}",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        actor_id=None,
    )
    proveedores_service.modificar_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        proveedor_id=proveedor.id,
        nombre=proveedor.nombre,
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        activo=False,
        actor_id=None,
    )
    return proveedor.id


@pytest.fixture
def usuario_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    """`costo_informado.usuario_id` tiene FK compuesta a `usuario` (D14):
    hace falta un usuario real, no un UUID inventado (mismo patrón que
    `test_proveedores_service.py`)."""
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


def _presentaciones_validas() -> list[DatosPresentacion]:
    return [
        DatosPresentacion(
            nombre="Botella",
            unidades_base=1,
            usar_en_venta=True,
            usar_en_compra=True,
            es_referencia=False,
        ),
        DatosPresentacion(
            nombre="Caja x6",
            unidades_base=6,
            usar_en_venta=True,
            usar_en_compra=True,
            es_referencia=True,
        ),
    ]


def _crear_producto_valido(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> tuple[object, list[object]]:
    return catalogo_service.crear_producto(
        organizacion_id,
        db_session,
        _RELOJ,
        codigo=f"VA-{uuid.uuid4().hex[:8]}",
        nombre="Vino A",
        categoria_id=categoria_id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="botella",
        alicuota_id=alicuota_id,
        presentaciones=_presentaciones_validas(),
        actor_id=None,
    )


# --- tarea 7.1: puerto de verificadores de uso (D2) -----------------------


def test_sin_verificadores_ninguna_presentacion_esta_usada(
    db_session: Session, organizacion_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(catalogo_service, "_REGISTRO_VERIFICADORES", {})
    assert (
        catalogo_service.presentacion_fue_usada(organizacion_id, uuid.uuid4(), db_session) is False
    )


def test_con_un_verificador_que_responde_true_la_presentacion_esta_usada(
    db_session: Session, organizacion_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(catalogo_service, "_REGISTRO_VERIFICADORES", {})
    catalogo_service.registrar_verificador_uso("modulo_de_prueba", lambda org, pres, ses: True)
    assert (
        catalogo_service.presentacion_fue_usada(organizacion_id, uuid.uuid4(), db_session) is True
    )


# --- tarea 7.2: categoria y marca (CAT-01, CAT-05, D11) -------------------


def test_crear_categoria_normaliza_nombre_y_nace_activa(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    categoria = catalogo_service.crear_categoria(
        organizacion_id, db_session, _RELOJ, nombre="  Licores  ", actor_id=None
    )
    assert categoria.nombre == "Licores"
    assert categoria.activo is True


def test_crear_categoria_nombre_duplicado_rechaza(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    nombre = f"Vinos-{uuid.uuid4().hex[:6]}"
    catalogo_service.crear_categoria(
        organizacion_id, db_session, _RELOJ, nombre=nombre, actor_id=None
    )
    with pytest.raises(NombreDuplicadoError):
        catalogo_service.crear_categoria(
            organizacion_id, db_session, _RELOJ, nombre=nombre, actor_id=None
        )


def test_crear_marca_nombre_vacio_rechaza(db_session: Session, organizacion_id: uuid.UUID) -> None:
    with pytest.raises(NombreInvalidoError):
        catalogo_service.crear_marca(
            organizacion_id, db_session, _RELOJ, nombre="   ", actor_id=None
        )


def test_d11_desactivar_categoria_con_productos_activos_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    _crear_producto_valido(db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id)
    with pytest.raises(CategoriaConProductosActivosError):
        catalogo_service.modificar_categoria(
            organizacion_id,
            db_session,
            _RELOJ,
            categoria_id=categoria_id,
            nombre="Vinos",
            activo=False,
            actor_id=None,
        )
    categoria = catalogo_service.obtener_categoria(organizacion_id, categoria_id, db_session)
    assert categoria is not None
    assert categoria.activo is True


def test_marca_se_desactiva_libremente_con_productos(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    marca = catalogo_service.crear_marca(
        organizacion_id, db_session, _RELOJ, nombre=f"Bodega-{uuid.uuid4().hex[:6]}", actor_id=None
    )
    catalogo_service.crear_producto(
        organizacion_id,
        db_session,
        _RELOJ,
        codigo=f"VA-{uuid.uuid4().hex[:8]}",
        nombre="Vino A",
        categoria_id=categoria_id,
        marca_id=marca.id,
        proveedor_id=proveedor_id,
        unidad_base="botella",
        alicuota_id=alicuota_id,
        presentaciones=_presentaciones_validas(),
        actor_id=None,
    )
    desactivada = catalogo_service.modificar_marca(
        organizacion_id,
        db_session,
        _RELOJ,
        marca_id=marca.id,
        nombre=marca.nombre,
        activo=False,
        actor_id=None,
    )
    assert desactivada.activo is False


# --- tarea 7.3: alta de producto (INV-01, CAT-01 a CAT-06) ----------------


def test_crear_producto_con_presentaciones_en_una_sola_unidad(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    assert producto.activo is True
    assert len(presentaciones) == 2
    releidas = catalogo_service.listar_presentaciones_de_producto(
        organizacion_id, producto.id, db_session
    )
    assert len(releidas) == 2


def test_crear_producto_alicuota_inexistente_da_404(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        catalogo_service.crear_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            codigo=f"VA-{uuid.uuid4().hex[:8]}",
            nombre="Vino A",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="botella",
            alicuota_id=uuid.uuid4(),
            presentaciones=_presentaciones_validas(),
            actor_id=None,
        )


def test_crear_producto_alicuota_inactiva_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_inactiva_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    with pytest.raises(AlicuotaInactivaError):
        catalogo_service.crear_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            codigo=f"VA-{uuid.uuid4().hex[:8]}",
            nombre="Vino A",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="botella",
            alicuota_id=alicuota_inactiva_id,
            presentaciones=_presentaciones_validas(),
            actor_id=None,
        )


def test_crear_producto_categoria_inactiva_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    categoria = catalogo_service.crear_categoria(
        organizacion_id, db_session, _RELOJ, nombre=f"Licores-{uuid.uuid4().hex[:6]}", actor_id=None
    )
    catalogo_service.modificar_categoria(
        organizacion_id,
        db_session,
        _RELOJ,
        categoria_id=categoria.id,
        nombre=categoria.nombre,
        activo=False,
        actor_id=None,
    )
    with pytest.raises(CategoriaInactivaError):
        catalogo_service.crear_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            codigo=f"VA-{uuid.uuid4().hex[:8]}",
            nombre="Vino A",
            categoria_id=categoria.id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            presentaciones=_presentaciones_validas(),
            actor_id=None,
        )


def test_crear_producto_codigo_duplicado_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    codigo = f"VA-{uuid.uuid4().hex[:8]}"
    catalogo_service.crear_producto(
        organizacion_id,
        db_session,
        _RELOJ,
        codigo=codigo,
        nombre="Vino A",
        categoria_id=categoria_id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="botella",
        alicuota_id=alicuota_id,
        presentaciones=_presentaciones_validas(),
        actor_id=None,
    )
    with pytest.raises(CodigoDuplicadoError):
        catalogo_service.crear_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            codigo=codigo,
            nombre="Otro",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            presentaciones=_presentaciones_validas(),
            actor_id=None,
        )


def test_crear_producto_sin_presentaciones_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    with pytest.raises(ProductoSinPresentacionesError):
        catalogo_service.crear_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            codigo=f"VA-{uuid.uuid4().hex[:8]}",
            nombre="Vino A",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            presentaciones=[],
            actor_id=None,
        )


def test_una_presentacion_invalida_no_deja_nada_escrito(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    """INV-01, CAT-02: la validación ocurre ANTES de escribir nada -- ni el
    producto ni la primera presentación quedan en la base."""
    codigo = f"VA-{uuid.uuid4().hex[:8]}"
    presentaciones = [
        DatosPresentacion(
            nombre="Botella",
            unidades_base=1,
            usar_en_venta=True,
            usar_en_compra=True,
            es_referencia=True,
        ),
        DatosPresentacion(
            nombre="Media docena",
            unidades_base=0,
            usar_en_venta=True,
            usar_en_compra=True,
            es_referencia=False,
        ),
    ]
    with pytest.raises(UnidadesInvalidasError):
        catalogo_service.crear_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            codigo=codigo,
            nombre="Vino A",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            presentaciones=presentaciones,
            actor_id=None,
        )
    productos, _ = catalogo_repository.listar_productos_paginado(
        organizacion_id, db_session, texto=codigo
    )
    assert productos == []


# --- tarea 7.4: modificar producto -----------------------------------------


def test_desactivar_y_reactivar_producto_conserva_presentaciones(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    producto, _ = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )

    inactivo = catalogo_service.modificar_producto(
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
    assert inactivo.activo is False
    presentaciones = catalogo_service.listar_presentaciones_de_producto(
        organizacion_id, producto.id, db_session
    )
    assert all(presentacion.activo for presentacion in presentaciones)


def test_cambiar_la_alicuota_del_producto(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    """Spec `productos-y-presentaciones`, escenario "Cambiar la alícuota del
    producto" (CAT-01; VTA-03 congela la alícuota de ventas ya confirmadas,
    fuera del alcance de este change)."""
    producto, _ = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    otra_alicuota = AlicuotaIva(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        nombre="10,5%",
        valor="0.105000",
        activo=True,
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(otra_alicuota)
    db_session.flush()

    modificado = catalogo_service.modificar_producto(
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
        alicuota_id=otra_alicuota.id,
        activo=True,
        actor_id=None,
    )

    assert modificado.alicuota_id == otra_alicuota.id


def test_modificar_producto_de_otra_organizacion_da_404(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        catalogo_service.modificar_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            producto_id=uuid.uuid4(),
            codigo="X",
            nombre="X",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            activo=True,
            actor_id=None,
        )


# --- 13.1: gaps de D9-A (spec productos-y-presentaciones, MODIFIED) -------
# Escenarios "Proveedor ausente, inexistente, inactivo o ajeno", "Sin
# consulta de proveedor registrada se rechaza", "Cambiar el proveedor del
# producto", "Asignar un proveedor inactivo" y "Conservar un proveedor que
# quedó inactivo": ninguno tenía una prueba a nivel de `catalogo.service`
# (la tarea 8.1 solo adaptó las pruebas existentes para pasarles un
# `proveedor_id` real, sin agregar los casos negativos nuevos).


def test_crear_producto_proveedor_inexistente_da_404(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        catalogo_service.crear_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            codigo=f"VA-{uuid.uuid4().hex[:8]}",
            nombre="Vino A",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=uuid.uuid4(),
            unidad_base="botella",
            alicuota_id=alicuota_id,
            presentaciones=_presentaciones_validas(),
            actor_id=None,
        )


def test_crear_producto_proveedor_de_otra_organizacion_da_404(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
) -> None:
    otra_organizacion = Organizacion(
        id=uuid.uuid4(),
        nombre="Otra organización",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Buenos_Aires",
        estado="ACTIVA",
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(otra_organizacion)
    db_session.flush()
    agregar_configuracion(db_session, otra_organizacion.id)
    proveedor_ajeno = proveedores_service.crear_proveedor(
        otra_organizacion.id,
        db_session,
        _RELOJ,
        nombre="Proveedor ajeno",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        actor_id=None,
    )
    with pytest.raises(RecursoNoEncontradoError):
        catalogo_service.crear_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            codigo=f"VA-{uuid.uuid4().hex[:8]}",
            nombre="Vino A",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_ajeno.id,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            presentaciones=_presentaciones_validas(),
            actor_id=None,
        )


def test_crear_producto_proveedor_inactivo_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_inactivo_id: uuid.UUID,
) -> None:
    with pytest.raises(ProveedorInactivoError):
        catalogo_service.crear_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            codigo=f"VA-{uuid.uuid4().hex[:8]}",
            nombre="Vino A",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_inactivo_id,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            presentaciones=_presentaciones_validas(),
            actor_id=None,
        )


def test_crear_producto_sin_consulta_de_proveedor_registrada_falla_cerrado(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`design.md` D9-A / ADR-025: sin la consulta de proveedor registrada,
    `catalogo` NUNCA acepta un `PRODUCTO_CREAR` sin validar el proveedor --
    falla cerrado con `RuntimeError`, no con un `PROVEEDOR_INACTIVO` ni un
    404 que sugerirían que sí se llegó a consultar."""
    monkeypatch.setattr(catalogo_service, "_CONSULTA_PROVEEDOR", None)
    with pytest.raises(RuntimeError, match="No hay consulta de proveedor registrada"):
        catalogo_service.crear_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            codigo=f"VA-{uuid.uuid4().hex[:8]}",
            nombre="Vino A",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            presentaciones=_presentaciones_validas(),
            actor_id=None,
        )


def test_modificar_producto_asigna_proveedor_inactivo_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    proveedor_inactivo_id: uuid.UUID,
) -> None:
    producto, _ = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    with pytest.raises(ProveedorInactivoError):
        catalogo_service.modificar_producto(
            organizacion_id,
            db_session,
            _RELOJ,
            producto_id=producto.id,
            codigo=producto.codigo,
            nombre=producto.nombre,
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_inactivo_id,
            unidad_base=producto.unidad_base,
            alicuota_id=alicuota_id,
            activo=True,
            actor_id=None,
        )
    sin_cambios = catalogo_service.obtener_producto(organizacion_id, producto.id, db_session)
    assert sin_cambios is not None
    assert sin_cambios.proveedor_id == proveedor_id


def test_modificar_producto_conserva_proveedor_inactivo_actual(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    """D5/D9-A: conservar el proveedor actual del producto se acepta aunque
    esté inactivo -- mismo criterio que el proveedor provisorio de la
    migración (`design.md` D2). Un proveedor CON un producto activo nunca
    se desactiva por el camino normal (`ProveedorConProductosActivosError`,
    D5/ADR-026): la única forma real de llegar a este estado es la que usa
    la migración, un `UPDATE` directo sobre `proveedor.activo`, sin pasar
    por `proveedores_service.modificar_proveedor`."""
    producto, _ = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    db_session.execute(
        text("UPDATE proveedor SET activo = false WHERE id = :id"), {"id": proveedor_id}
    )
    db_session.flush()
    db_session.expire_all()

    modificado = catalogo_service.modificar_producto(
        organizacion_id,
        db_session,
        _RELOJ,
        producto_id=producto.id,
        codigo=producto.codigo,
        nombre="Vino A renombrado",
        categoria_id=categoria_id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base=producto.unidad_base,
        alicuota_id=alicuota_id,
        activo=True,
        actor_id=None,
    )

    assert modificado.nombre == "Vino A renombrado"
    assert modificado.proveedor_id == proveedor_id


def test_modificar_producto_cambia_proveedor_sin_afectar_costos_informados(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    presentacion_de_compra = next(p for p in presentaciones if p.usar_en_compra)
    costos_registrados = proveedores_service.informar_costos(
        organizacion_id,
        db_session,
        _RELOJ,
        proveedor_id=proveedor_id,
        costos=[
            CostoDelLote(
                producto_id=producto.id,
                presentacion_id=presentacion_de_compra.id,
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
    costo_id = costos_registrados[0].id

    otro_proveedor = proveedores_service.crear_proveedor(
        organizacion_id,
        db_session,
        _RELOJ,
        nombre=f"Otro proveedor-{uuid.uuid4().hex[:8]}",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        actor_id=None,
    )

    modificado = catalogo_service.modificar_producto(
        organizacion_id,
        db_session,
        _RELOJ,
        producto_id=producto.id,
        codigo=producto.codigo,
        nombre=producto.nombre,
        categoria_id=categoria_id,
        marca_id=None,
        proveedor_id=otro_proveedor.id,
        unidad_base=producto.unidad_base,
        alicuota_id=alicuota_id,
        activo=True,
        actor_id=None,
    )

    assert modificado.proveedor_id == otro_proveedor.id
    costo_sin_cambios = proveedores_service.obtener_costo_informado_vigente(
        organizacion_id, producto.id, date(2026, 9, 1), db_session
    )
    assert costo_sin_cambios is not None
    assert costo_sin_cambios.id == costo_id
    assert costo_sin_cambios.proveedor_id == proveedor_id
    assert costo_sin_cambios.valor == Decimal("1000.00")


# --- tarea 7.5: presentaciones (CAT-02, CAT-04, INV-18) --------------------


def test_agregar_presentacion_de_compra(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    producto, _ = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    nueva = catalogo_service.agregar_presentacion(
        organizacion_id,
        db_session,
        _RELOJ,
        producto_id=producto.id,
        nombre="Pack x24",
        unidades_base=24,
        usar_en_venta=False,
        usar_en_compra=True,
        actor_id=None,
    )
    assert nueva.es_referencia is False
    assert nueva.activo is True


def test_cambiar_unidades_de_presentacion_sin_uso_es_permitido(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    referencia = next(p for p in presentaciones if p.es_referencia)
    modificada = catalogo_service.modificar_presentacion(
        organizacion_id,
        db_session,
        _RELOJ,
        presentacion_id=referencia.id,
        nombre=referencia.nombre,
        unidades_base=12,
        usar_en_venta=True,
        usar_en_compra=True,
        activo=True,
        actor_id=None,
    )
    assert modificada.unidades_base == 12


def test_inv18_cambiar_unidades_de_presentacion_usada_es_congelado(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """INV-18: un verificador de uso que declara la presentación como
    usada hace que el cambio de unidades se rechace con
    `UNIDADES_CONGELADAS`, conservando las unidades originales."""
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    no_referencia = next(p for p in presentaciones if not p.es_referencia)
    monkeypatch.setattr(catalogo_service, "_REGISTRO_VERIFICADORES", {})
    catalogo_service.registrar_verificador_uso("prueba_inv18", lambda org, pres, ses: True)

    with pytest.raises(UnidadesCongeladasError):
        catalogo_service.modificar_presentacion(
            organizacion_id,
            db_session,
            _RELOJ,
            presentacion_id=no_referencia.id,
            nombre=no_referencia.nombre,
            unidades_base=no_referencia.unidades_base + 1,
            usar_en_venta=no_referencia.usar_en_venta,
            usar_en_compra=no_referencia.usar_en_compra,
            activo=True,
            actor_id=None,
        )
    releida = catalogo_service.obtener_presentacion(organizacion_id, no_referencia.id, db_session)
    assert releida is not None
    assert releida.unidades_base == no_referencia.unidades_base


def test_cat04_presentacion_usada_puede_renombrarse_y_desactivarse(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    no_referencia = next(p for p in presentaciones if not p.es_referencia)
    monkeypatch.setattr(catalogo_service, "_REGISTRO_VERIFICADORES", {})
    catalogo_service.registrar_verificador_uso("prueba_cat04", lambda org, pres, ses: True)

    actualizada = catalogo_service.modificar_presentacion(
        organizacion_id,
        db_session,
        _RELOJ,
        presentacion_id=no_referencia.id,
        nombre="Botella (discontinuada)",
        unidades_base=no_referencia.unidades_base,
        usar_en_venta=no_referencia.usar_en_venta,
        usar_en_compra=no_referencia.usar_en_compra,
        activo=False,
        actor_id=None,
    )
    assert actualizada.nombre == "Botella (discontinuada)"
    assert actualizada.activo is False


def test_desactivar_referencia_directamente_rechaza(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    referencia = next(p for p in presentaciones if p.es_referencia)
    with pytest.raises(ReferenciaInvalidaError):
        catalogo_service.modificar_presentacion(
            organizacion_id,
            db_session,
            _RELOJ,
            presentacion_id=referencia.id,
            nombre=referencia.nombre,
            unidades_base=referencia.unidades_base,
            usar_en_venta=referencia.usar_en_venta,
            usar_en_compra=referencia.usar_en_compra,
            activo=False,
            actor_id=None,
        )


# --- tarea 7.6: cambiar referencia (CAT-03, D5) ---------------------------


def test_cambiar_referencia(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    anterior = next(p for p in presentaciones if p.es_referencia)
    nueva = next(p for p in presentaciones if not p.es_referencia)

    catalogo_service.cambiar_referencia(
        organizacion_id,
        db_session,
        _RELOJ,
        producto_id=producto.id,
        presentacion_id=nueva.id,
        actor_id=None,
    )

    nueva_releida = catalogo_service.obtener_presentacion(organizacion_id, nueva.id, db_session)
    anterior_releida = catalogo_service.obtener_presentacion(
        organizacion_id, anterior.id, db_session
    )
    assert nueva_releida is not None and nueva_releida.es_referencia is True
    assert anterior_releida is not None and anterior_releida.es_referencia is False


def test_cambiar_referencia_hacia_inactiva_conserva_la_anterior(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    anterior = next(p for p in presentaciones if p.es_referencia)
    candidata = next(p for p in presentaciones if not p.es_referencia)
    catalogo_service.modificar_presentacion(
        organizacion_id,
        db_session,
        _RELOJ,
        presentacion_id=candidata.id,
        nombre=candidata.nombre,
        unidades_base=candidata.unidades_base,
        usar_en_venta=candidata.usar_en_venta,
        usar_en_compra=candidata.usar_en_compra,
        activo=False,
        actor_id=None,
    )

    with pytest.raises(ReferenciaInvalidaError):
        catalogo_service.cambiar_referencia(
            organizacion_id,
            db_session,
            _RELOJ,
            producto_id=producto.id,
            presentacion_id=candidata.id,
            actor_id=None,
        )

    anterior_releida = catalogo_service.obtener_presentacion(
        organizacion_id, anterior.id, db_session
    )
    assert anterior_releida is not None
    assert anterior_releida.es_referencia is True


# --- tarea 7.7: lecturas públicas -------------------------------------------


def test_lecturas_publicas_de_producto_y_referencia(
    db_session: Session,
    organizacion_id: uuid.UUID,
    categoria_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id, proveedor_id
    )
    referencia_esperada = next(p for p in presentaciones if p.es_referencia)

    assert catalogo_service.obtener_producto(organizacion_id, producto.id, db_session) is not None
    referencia = catalogo_service.obtener_referencia_de_producto(
        organizacion_id, producto.id, db_session
    )
    assert referencia is not None
    assert referencia.id == referencia_esperada.id
