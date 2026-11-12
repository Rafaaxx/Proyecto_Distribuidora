"""Change 05, grupo 6: alta y lectura por id filtrando por organización
(tarea 6.1), traducción de `IntegrityError` (tarea 6.2), bloqueo
`FOR UPDATE` y consulta de productos activos por categoría (tarea 6.3), y
paginación por cursor (tarea 6.4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.modules.catalogo import repository as catalogo_repository
from app.modules.catalogo.domain.errores import (
    CodigoDuplicadoError,
    NombreDuplicadoError,
    ReferenciaInvalidaError,
)
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad.models import Organizacion

# Change 06, grupo 5: mismo patrón que `test_proveedores_migracion.py` --
# sin este import, SQLAlchemy no resuelve `fk_producto__proveedor` al
# configurar el mapper de `Producto`.
from app.modules.proveedores.models import CostoInformado, Proveedor  # noqa: F401

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

_MOMENTO = datetime.now(UTC)


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
        valor="0.210000",
        activo=True,
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
    )
    db_session.add(alicuota)
    db_session.flush()
    return alicuota.id


@pytest.fixture
def proveedor_id(db_session: Session, organizacion_id: uuid.UUID) -> uuid.UUID:
    """`producto.proveedor_id` es `NOT NULL` desde change 06 grupo 4 (D2):
    toda fixture de este archivo que crea un producto por repositorio
    necesita un proveedor real."""
    proveedor = Proveedor(
        id=uuid.uuid4(),
        organizacion_id=organizacion_id,
        nombre=f"Proveedor-{uuid.uuid4().hex[:6]}",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        activo=True,
        creado_en=_MOMENTO,
        actualizado_en=_MOMENTO,
        actualizado_por_id=None,
    )
    db_session.add(proveedor)
    db_session.flush()
    return proveedor.id


# --- tarea 6.1: alta y lectura por id filtrando por organización ---------


def test_crear_y_obtener_categoria_por_id(db_session: Session, organizacion_id: uuid.UUID) -> None:
    categoria = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"Vinos-{uuid.uuid4().hex[:6]}",
        activo=True,
        momento=_MOMENTO,
    )
    releida = catalogo_repository.obtener_categoria_por_id(
        organizacion_id, categoria.id, db_session
    )
    assert releida is not None
    assert releida.id == categoria.id


def test_categoria_de_otra_organizacion_no_se_encuentra(
    db_session: Session, organizacion_id: uuid.UUID, otra_organizacion_id: uuid.UUID
) -> None:
    categoria = catalogo_repository.crear_categoria(
        otra_organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"Vinos-{uuid.uuid4().hex[:6]}",
        activo=True,
        momento=_MOMENTO,
    )
    assert (
        catalogo_repository.obtener_categoria_por_id(organizacion_id, categoria.id, db_session)
        is None
    )


# --- tarea 6.2: traducción de IntegrityError ------------------------------


def test_nombre_duplicado_de_categoria_se_traduce_a_error_de_dominio(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    nombre = f"Vinos-{uuid.uuid4().hex[:6]}"
    catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=nombre,
        activo=True,
        momento=_MOMENTO,
    )
    with pytest.raises(NombreDuplicadoError):
        catalogo_repository.crear_categoria(
            organizacion_id,
            db_session,
            categoria_id=uuid.uuid4(),
            nombre=nombre,
            activo=True,
            momento=_MOMENTO,
        )
    # La traducción usa un SAVEPOINT (begin_nested): la sesión sigue
    # utilizable después del error, no queda en un estado roto.
    assert catalogo_repository.listar_categorias(organizacion_id, db_session) != []


def test_codigo_duplicado_de_producto_se_traduce_a_error_de_dominio(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    categoria = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"Vinos-{uuid.uuid4().hex[:6]}",
        activo=True,
        momento=_MOMENTO,
    )
    codigo = f"VA-{uuid.uuid4().hex[:8]}"
    catalogo_repository.crear_producto(
        organizacion_id,
        db_session,
        producto_id=uuid.uuid4(),
        codigo=codigo,
        nombre="Vino A",
        categoria_id=categoria.id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="botella",
        alicuota_id=alicuota_id,
        activo=True,
        momento=_MOMENTO,
    )
    with pytest.raises(CodigoDuplicadoError):
        catalogo_repository.crear_producto(
            organizacion_id,
            db_session,
            producto_id=uuid.uuid4(),
            codigo=codigo,
            nombre="Otro",
            categoria_id=categoria.id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            activo=True,
            momento=_MOMENTO,
        )


def test_segunda_referencia_directa_se_traduce_a_referencia_invalida(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    categoria = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"Vinos-{uuid.uuid4().hex[:6]}",
        activo=True,
        momento=_MOMENTO,
    )
    producto = catalogo_repository.crear_producto(
        organizacion_id,
        db_session,
        producto_id=uuid.uuid4(),
        codigo=f"VA-{uuid.uuid4().hex[:8]}",
        nombre="Vino A",
        categoria_id=categoria.id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="botella",
        alicuota_id=alicuota_id,
        activo=True,
        momento=_MOMENTO,
    )
    catalogo_repository.crear_presentacion(
        organizacion_id,
        db_session,
        presentacion_id=uuid.uuid4(),
        producto_id=producto.id,
        nombre="Botella",
        unidades_base=1,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=True,
        activo=True,
        momento=_MOMENTO,
    )
    with pytest.raises(ReferenciaInvalidaError):
        catalogo_repository.crear_presentacion(
            organizacion_id,
            db_session,
            presentacion_id=uuid.uuid4(),
            producto_id=producto.id,
            nombre="Caja x6",
            unidades_base=6,
            usar_en_venta=True,
            usar_en_compra=True,
            es_referencia=True,
            activo=True,
            momento=_MOMENTO,
        )


# --- tarea 6.3: FOR UPDATE y productos activos por categoría --------------


def test_obtener_producto_para_actualizar_bloquea_la_fila(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    categoria = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"Vinos-{uuid.uuid4().hex[:6]}",
        activo=True,
        momento=_MOMENTO,
    )
    producto = catalogo_repository.crear_producto(
        organizacion_id,
        db_session,
        producto_id=uuid.uuid4(),
        codigo=f"VA-{uuid.uuid4().hex[:8]}",
        nombre="Vino A",
        categoria_id=categoria.id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="botella",
        alicuota_id=alicuota_id,
        activo=True,
        momento=_MOMENTO,
    )
    bloqueado = catalogo_repository.obtener_producto_por_id_para_actualizar(
        organizacion_id, producto.id, db_session
    )
    assert bloqueado is not None
    assert bloqueado.id == producto.id


def test_existen_productos_activos_en_categoria(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    categoria = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"Vinos-{uuid.uuid4().hex[:6]}",
        activo=True,
        momento=_MOMENTO,
    )
    assert (
        catalogo_repository.existen_productos_activos_en_categoria(
            organizacion_id, categoria.id, db_session
        )
        is False
    )
    catalogo_repository.crear_producto(
        organizacion_id,
        db_session,
        producto_id=uuid.uuid4(),
        codigo=f"VA-{uuid.uuid4().hex[:8]}",
        nombre="Vino A",
        categoria_id=categoria.id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="botella",
        alicuota_id=alicuota_id,
        activo=True,
        momento=_MOMENTO,
    )
    assert (
        catalogo_repository.existen_productos_activos_en_categoria(
            organizacion_id, categoria.id, db_session
        )
        is True
    )


# --- tarea 6.4: paginación por cursor --------------------------------------


def test_listar_productos_paginado_recorre_todos_sin_repetir(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    categoria = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"Vinos-{uuid.uuid4().hex[:6]}",
        activo=True,
        momento=_MOMENTO,
    )
    prefijo = uuid.uuid4().hex[:6]
    codigos_creados = sorted(f"{prefijo}-{indice:03d}" for indice in range(5))
    for codigo in codigos_creados:
        catalogo_repository.crear_producto(
            organizacion_id,
            db_session,
            producto_id=uuid.uuid4(),
            codigo=codigo,
            nombre="Vino",
            categoria_id=categoria.id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            activo=True,
            momento=_MOMENTO,
        )

    vistos: list[str] = []
    cursor = None
    for _ in range(10):
        pagina, cursor = catalogo_repository.listar_productos_paginado(
            organizacion_id, db_session, limite=2, cursor=cursor, texto=prefijo
        )
        vistos.extend(producto.codigo for producto in pagina)
        if cursor is None:
            break

    assert vistos == codigos_creados
    assert cursor is None


def test_listar_productos_paginado_filtra_por_categoria(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    categoria_a = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"CatA-{uuid.uuid4().hex[:6]}",
        activo=True,
        momento=_MOMENTO,
    )
    categoria_b = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"CatB-{uuid.uuid4().hex[:6]}",
        activo=True,
        momento=_MOMENTO,
    )
    codigo_a = f"A-{uuid.uuid4().hex[:8]}"
    codigo_b = f"B-{uuid.uuid4().hex[:8]}"
    catalogo_repository.crear_producto(
        organizacion_id,
        db_session,
        producto_id=uuid.uuid4(),
        codigo=codigo_a,
        nombre="Producto A",
        categoria_id=categoria_a.id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="botella",
        alicuota_id=alicuota_id,
        activo=True,
        momento=_MOMENTO,
    )
    catalogo_repository.crear_producto(
        organizacion_id,
        db_session,
        producto_id=uuid.uuid4(),
        codigo=codigo_b,
        nombre="Producto B",
        categoria_id=categoria_b.id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="botella",
        alicuota_id=alicuota_id,
        activo=True,
        momento=_MOMENTO,
    )

    pagina, cursor = catalogo_repository.listar_productos_paginado(
        organizacion_id, db_session, categoria_id=categoria_a.id
    )
    assert [producto.codigo for producto in pagina] == [codigo_a]
    assert cursor is None


def test_listar_productos_paginado_filtra_por_texto_excluye_no_coincidentes(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> None:
    """Spec `administracion-de-catalogo`, escenario "Buscar por código": dado
    `VA-001` y `CB-001`, buscar `VA-` devuelve solo `VA-001` (CAT-01)."""
    categoria = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"Vinos-{uuid.uuid4().hex[:6]}",
        activo=True,
        momento=_MOMENTO,
    )
    sufijo = uuid.uuid4().hex[:8]
    codigo_va = f"VA-{sufijo}"
    codigo_cb = f"CB-{sufijo}"
    for codigo, nombre in ((codigo_va, "Vino A"), (codigo_cb, "Cerveza B")):
        catalogo_repository.crear_producto(
            organizacion_id,
            db_session,
            producto_id=uuid.uuid4(),
            codigo=codigo,
            nombre=nombre,
            categoria_id=categoria.id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="unidad",
            alicuota_id=alicuota_id,
            activo=True,
            momento=_MOMENTO,
        )

    pagina, cursor = catalogo_repository.listar_productos_paginado(
        organizacion_id, db_session, texto=f"VA-{sufijo}"
    )
    assert [producto.codigo for producto in pagina] == [codigo_va]
    assert cursor is None


def test_listar_categorias_paginado_solo_activas_excluye_inactivas(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    """Spec `categorias-y-marcas`, escenario "Listado filtrado por activas"
    (CAT-05): `Vinos` activa y `Licores` inactiva, listar solo activas
    devuelve solo `Vinos`."""
    sufijo = uuid.uuid4().hex[:6]
    activa = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"Vinos-{sufijo}",
        activo=True,
        momento=_MOMENTO,
    )
    inactiva = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=uuid.uuid4(),
        nombre=f"Licores-{sufijo}",
        activo=True,
        momento=_MOMENTO,
    )
    catalogo_repository.actualizar_categoria(
        organizacion_id,
        db_session,
        categoria_id=inactiva.id,
        nombre=inactiva.nombre,
        activo=False,
        momento=_MOMENTO,
    )

    pagina, cursor = catalogo_repository.listar_categorias_paginado(
        organizacion_id, db_session, solo_activas=True
    )
    ids_pagina = {categoria.id for categoria in pagina}
    assert activa.id in ids_pagina
    assert inactiva.id not in ids_pagina
    assert cursor is None


def test_listar_marcas_paginado_solo_activas_excluye_inactivas(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    """Spec `categorias-y-marcas`, escenario "Listado filtrado por activas"
    (CAT-05), simétrico para marcas."""
    sufijo = uuid.uuid4().hex[:6]
    activa = catalogo_repository.crear_marca(
        organizacion_id,
        db_session,
        marca_id=uuid.uuid4(),
        nombre=f"Bodega Norte-{sufijo}",
        activo=True,
        momento=_MOMENTO,
    )
    inactiva = catalogo_repository.crear_marca(
        organizacion_id,
        db_session,
        marca_id=uuid.uuid4(),
        nombre=f"Bodega Sur-{sufijo}",
        activo=True,
        momento=_MOMENTO,
    )
    catalogo_repository.actualizar_marca(
        organizacion_id,
        db_session,
        marca_id=inactiva.id,
        nombre=inactiva.nombre,
        activo=False,
        momento=_MOMENTO,
    )

    pagina, cursor = catalogo_repository.listar_marcas_paginado(
        organizacion_id, db_session, solo_activas=True
    )
    ids_pagina = {marca.id for marca in pagina}
    assert activa.id in ids_pagina
    assert inactiva.id not in ids_pagina
    assert cursor is None
