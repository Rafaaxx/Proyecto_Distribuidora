"""Change 06, grupo 7: repositorio de `proveedores`
(`proveedores/repository.py`).

Cubre las tareas 7.1 (alta/lectura/bloqueos/traducción de `IntegrityError`),
7.2 (paginación por cursor y opciones reducidas) y 7.3 (inserción en lote,
`obtener_vigente`, `listar_historial_de_producto`,
`existe_costo_para_presentacion`, y la propiedad Hypothesis que compara
`obtener_vigente` contra `proveedores/domain/vigencia.py::elegir_vigente`,
`design.md` D4)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.modules.catalogo import repository as catalogo_repository
from app.modules.catalogo.models import Producto
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad.models import Organizacion, Rol, Usuario
from app.modules.proveedores import repository as proveedores_repository
from app.modules.proveedores.domain.errores import CuitDuplicadoError, NombreDuplicadoError
from app.modules.proveedores.domain.vigencia import CandidatoVigencia, elegir_vigente
from app.modules.proveedores.models import CostoInformado, Proveedor

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

_MOMENTO = datetime(2026, 9, 24, tzinfo=UTC)


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


def _crear_proveedor(
    db_session: Session,
    organizacion_id: uuid.UUID,
    *,
    nombre: str | None = None,
    cuit: str | None = None,
    activo: bool = True,
) -> Proveedor:
    return proveedores_repository.crear_proveedor(
        organizacion_id,
        db_session,
        proveedor_id=nuevo_id(),
        nombre=nombre or f"Proveedor-{uuid.uuid4().hex[:8]}",
        cuit=cuit,
        contacto=None,
        telefono=None,
        email=None,
        activo=activo,
        momento=_MOMENTO,
    )


def _crear_producto_y_presentacion(
    db_session: Session, organizacion_id: uuid.UUID, alicuota_id: uuid.UUID, proveedor_id: uuid.UUID
) -> tuple[Producto, uuid.UUID]:
    categoria = catalogo_repository.crear_categoria(
        organizacion_id,
        db_session,
        categoria_id=nuevo_id(),
        nombre=f"Categoria-{uuid.uuid4().hex[:8]}",
        activo=True,
        momento=_MOMENTO,
    )
    producto = catalogo_repository.crear_producto(
        organizacion_id,
        db_session,
        producto_id=nuevo_id(),
        codigo=f"COD-{uuid.uuid4().hex[:8]}",
        nombre="Producto de prueba",
        categoria_id=categoria.id,
        marca_id=None,
        proveedor_id=proveedor_id,
        unidad_base="unidad",
        alicuota_id=alicuota_id,
        activo=True,
        momento=_MOMENTO,
    )
    presentacion = catalogo_repository.crear_presentacion(
        organizacion_id,
        db_session,
        presentacion_id=nuevo_id(),
        producto_id=producto.id,
        nombre="Caja x12",
        unidades_base=12,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=True,
        activo=True,
        momento=_MOMENTO,
    )
    return producto, presentacion.id


def _dato_costo(
    *,
    proveedor_id: uuid.UUID,
    producto_id: uuid.UUID,
    presentacion_id: uuid.UUID,
    vigencia_desde: date,
    momento: datetime,
    usuario_id: uuid.UUID,
    valor: Decimal = Decimal("18000.00"),
) -> proveedores_repository.DatosCostoInformado:
    return proveedores_repository.DatosCostoInformado(
        id=nuevo_id(),
        proveedor_id=proveedor_id,
        producto_id=producto_id,
        presentacion_id=presentacion_id,
        valor=valor,
        incluye_iva=True,
        bonificacion=Decimal("0"),
        alicuota_aplicada=Decimal("0.210000"),
        costo_base=Decimal("1239.669421"),
        vigencia_desde=vigencia_desde,
        observacion=None,
        operation_id=uuid.uuid4(),
        usuario_id=usuario_id,
        momento=momento,
    )


# --- tarea 7.1: alta/modificación/lectura, bloqueos, traducción -----------


def test_crear_y_obtener_proveedor_por_id(db_session: Session, organizacion_id: uuid.UUID) -> None:
    proveedor = _crear_proveedor(db_session, organizacion_id, nombre="Bodega Andina")
    releido = proveedores_repository.obtener_proveedor_por_id(
        organizacion_id, proveedor.id, db_session
    )
    assert releido is not None
    assert releido.nombre == "Bodega Andina"


def test_proveedor_de_otra_organizacion_no_se_encuentra(
    db_session: Session, organizacion_id: uuid.UUID, otra_organizacion_id: uuid.UUID
) -> None:
    proveedor = _crear_proveedor(db_session, otra_organizacion_id)
    assert (
        proveedores_repository.obtener_proveedor_por_id(organizacion_id, proveedor.id, db_session)
        is None
    )


def test_nombre_duplicado_se_traduce_a_error_de_dominio(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    nombre = f"Distribuidora Norte-{uuid.uuid4().hex[:6]}"
    _crear_proveedor(db_session, organizacion_id, nombre=nombre)
    with pytest.raises(NombreDuplicadoError):
        _crear_proveedor(db_session, organizacion_id, nombre=nombre)
    # La traducción usa un SAVEPOINT: la sesión sigue utilizable después.
    proveedores, _ = proveedores_repository.listar_proveedores_paginado(organizacion_id, db_session)
    assert len(proveedores) == 1


def test_cuit_duplicado_se_traduce_a_error_de_dominio(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    cuit = "30712345671"
    proveedores_repository.crear_proveedor(
        organizacion_id,
        db_session,
        proveedor_id=nuevo_id(),
        nombre="Proveedor A",
        cuit=cuit,
        contacto=None,
        telefono=None,
        email=None,
        activo=True,
        momento=_MOMENTO,
    )
    with pytest.raises(CuitDuplicadoError):
        proveedores_repository.crear_proveedor(
            organizacion_id,
            db_session,
            proveedor_id=nuevo_id(),
            nombre="Proveedor B",
            cuit=cuit,
            contacto=None,
            telefono=None,
            email=None,
            activo=True,
            momento=_MOMENTO,
        )


def test_actualizar_proveedor(db_session: Session, organizacion_id: uuid.UUID) -> None:
    proveedor = _crear_proveedor(db_session, organizacion_id)
    actualizado = proveedores_repository.actualizar_proveedor(
        organizacion_id,
        db_session,
        proveedor_id=proveedor.id,
        nombre="Nuevo nombre",
        cuit=None,
        contacto="Juan",
        telefono=None,
        email=None,
        activo=False,
        momento=_MOMENTO,
    )
    assert actualizado is not None
    assert actualizado.nombre == "Nuevo nombre"
    assert actualizado.activo is False


def test_obtener_proveedor_para_actualizar_bloquea_la_fila(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    proveedor = _crear_proveedor(db_session, organizacion_id)
    bloqueado = proveedores_repository.obtener_proveedor_por_id_para_actualizar(
        organizacion_id, proveedor.id, db_session
    )
    assert bloqueado is not None
    assert bloqueado.id == proveedor.id


def test_obtener_proveedor_para_compartir(db_session: Session, organizacion_id: uuid.UUID) -> None:
    proveedor = _crear_proveedor(db_session, organizacion_id)
    compartido = proveedores_repository.obtener_proveedor_por_id_para_compartir(
        organizacion_id, proveedor.id, db_session
    )
    assert compartido is not None
    assert compartido.id == proveedor.id


# --- tarea 7.2: paginación y opciones ---------------------------------------


def test_listar_proveedores_paginado_recorre_todos_sin_repetir(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    nombres = sorted(f"Prov-{i:03d}-{uuid.uuid4().hex[:4]}" for i in range(5))
    for nombre in nombres:
        _crear_proveedor(db_session, organizacion_id, nombre=nombre)

    vistos: list[str] = []
    cursor = None
    while True:
        pagina, cursor = proveedores_repository.listar_proveedores_paginado(
            organizacion_id, db_session, limite=2, cursor=cursor
        )
        vistos.extend(p.nombre for p in pagina)
        if cursor is None:
            break
    assert vistos == nombres


def test_listar_proveedores_filtra_por_texto_y_actividad(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    _crear_proveedor(db_session, organizacion_id, nombre="Bodega Andina")
    _crear_proveedor(db_session, organizacion_id, nombre="Distribuidora Norte", activo=False)

    solo_bodega, _ = proveedores_repository.listar_proveedores_paginado(
        organizacion_id, db_session, texto="andina"
    )
    assert [p.nombre for p in solo_bodega] == ["Bodega Andina"]

    solo_activos, _ = proveedores_repository.listar_proveedores_paginado(
        organizacion_id, db_session, activo=True
    )
    assert [p.nombre for p in solo_activos] == ["Bodega Andina"]


def test_listar_opciones_de_proveedores_solo_activos(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    _crear_proveedor(db_session, organizacion_id, nombre="Activo", activo=True)
    _crear_proveedor(db_session, organizacion_id, nombre="Inactivo", activo=False)

    opciones, cursor_siguiente = proveedores_repository.listar_opciones_de_proveedores(
        organizacion_id, db_session
    )
    assert [p.nombre for p in opciones] == ["Activo"]
    assert cursor_siguiente is None


def test_listar_opciones_de_proveedores_paginado_recorre_todos_sin_repetir(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    """Contrato-api.md P2 (aprobado 2026-09-24): `/proveedores/opciones`
    va paginado por cursor de `nombre`, mismo mecanismo que
    `listar_proveedores_paginado`."""
    nombres = sorted(f"Opcion-{i:03d}-{uuid.uuid4().hex[:4]}" for i in range(5))
    for nombre in nombres:
        _crear_proveedor(db_session, organizacion_id, nombre=nombre, activo=True)

    vistos: list[str] = []
    cursor = None
    while True:
        pagina, cursor = proveedores_repository.listar_opciones_de_proveedores(
            organizacion_id, db_session, limite=2, cursor=cursor
        )
        vistos.extend(p.nombre for p in pagina)
        if cursor is None:
            break
    assert vistos == nombres


def test_listar_proveedores_filtra_por_cuit(
    db_session: Session, organizacion_id: uuid.UUID
) -> None:
    """Contrato-api.md P5 (aprobado 2026-09-24): el filtro `texto` también
    busca por CUIT, no solo por nombre."""
    _crear_proveedor(db_session, organizacion_id, nombre="Bodega Andina", cuit="20123456789")
    _crear_proveedor(db_session, organizacion_id, nombre="Distribuidora Norte", cuit="27987654321")

    por_cuit, _ = proveedores_repository.listar_proveedores_paginado(
        organizacion_id, db_session, texto="20-1234"
    )
    assert [p.nombre for p in por_cuit] == ["Bodega Andina"]


# --- tarea 7.3: costos en lote, vigente, historial, verificador ------------


def test_insertar_costos_en_lote(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor = _crear_proveedor(db_session, organizacion_id)
    producto, presentacion_id = _crear_producto_y_presentacion(
        db_session, organizacion_id, alicuota_id, proveedor.id
    )
    datos = [
        _dato_costo(
            usuario_id=usuario_id,
            proveedor_id=proveedor.id,
            producto_id=producto.id,
            presentacion_id=presentacion_id,
            vigencia_desde=date(2026, 9, 1),
            momento=_MOMENTO,
        )
    ]
    filas = proveedores_repository.insertar_costos(organizacion_id, db_session, costos=datos)
    assert len(filas) == 1
    assert db_session.get(CostoInformado, filas[0].id) is not None


def test_obtener_vigente_elige_mayor_vigencia_que_no_supera_la_fecha(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor = _crear_proveedor(db_session, organizacion_id)
    producto, presentacion_id = _crear_producto_y_presentacion(
        db_session, organizacion_id, alicuota_id, proveedor.id
    )
    antiguo = _dato_costo(
        usuario_id=usuario_id,
        proveedor_id=proveedor.id,
        producto_id=producto.id,
        presentacion_id=presentacion_id,
        vigencia_desde=date(2026, 1, 1),
        momento=_MOMENTO,
        valor=Decimal("1000.00"),
    )
    reciente = _dato_costo(
        usuario_id=usuario_id,
        proveedor_id=proveedor.id,
        producto_id=producto.id,
        presentacion_id=presentacion_id,
        vigencia_desde=date(2026, 6, 1),
        momento=_MOMENTO + timedelta(seconds=1),
        valor=Decimal("2000.00"),
    )
    futuro = _dato_costo(
        usuario_id=usuario_id,
        proveedor_id=proveedor.id,
        producto_id=producto.id,
        presentacion_id=presentacion_id,
        vigencia_desde=date(2027, 1, 1),
        momento=_MOMENTO + timedelta(seconds=2),
        valor=Decimal("3000.00"),
    )
    proveedores_repository.insertar_costos(
        organizacion_id, db_session, costos=[antiguo, reciente, futuro]
    )

    vigente = proveedores_repository.obtener_vigente(
        organizacion_id, producto.id, date(2026, 9, 24), db_session
    )
    assert vigente is not None
    assert vigente.valor == Decimal("2000.00")

    ninguno_alcanza = proveedores_repository.obtener_vigente(
        organizacion_id, producto.id, date(2025, 1, 1), db_session
    )
    assert ninguno_alcanza is None


def test_obtener_vigente_desempata_por_creado_en_con_la_misma_vigencia(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """D4: con la misma `vigencia_desde` prevalece el registrado último."""
    proveedor = _crear_proveedor(db_session, organizacion_id)
    producto, presentacion_id = _crear_producto_y_presentacion(
        db_session, organizacion_id, alicuota_id, proveedor.id
    )
    primero = _dato_costo(
        usuario_id=usuario_id,
        proveedor_id=proveedor.id,
        producto_id=producto.id,
        presentacion_id=presentacion_id,
        vigencia_desde=date(2026, 9, 1),
        momento=_MOMENTO,
        valor=Decimal("1000.00"),
    )
    segundo = _dato_costo(
        usuario_id=usuario_id,
        proveedor_id=proveedor.id,
        producto_id=producto.id,
        presentacion_id=presentacion_id,
        vigencia_desde=date(2026, 9, 1),
        momento=_MOMENTO + timedelta(seconds=1),
        valor=Decimal("1500.00"),
    )
    proveedores_repository.insertar_costos(organizacion_id, db_session, costos=[primero, segundo])

    vigente = proveedores_repository.obtener_vigente(
        organizacion_id, producto.id, date(2026, 9, 24), db_session
    )
    assert vigente is not None
    assert vigente.valor == Decimal("1500.00")


def test_listar_historial_de_producto_recorre_todo_sin_repetir(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor = _crear_proveedor(db_session, organizacion_id)
    producto, presentacion_id = _crear_producto_y_presentacion(
        db_session, organizacion_id, alicuota_id, proveedor.id
    )
    datos = [
        _dato_costo(
            usuario_id=usuario_id,
            proveedor_id=proveedor.id,
            producto_id=producto.id,
            presentacion_id=presentacion_id,
            vigencia_desde=date(2026, 1, 1) + timedelta(days=30 * i),
            momento=_MOMENTO + timedelta(seconds=i),
        )
        for i in range(5)
    ]
    proveedores_repository.insertar_costos(organizacion_id, db_session, costos=datos)

    vistos: list[uuid.UUID] = []
    cursor = None
    while True:
        pagina, cursor = proveedores_repository.listar_historial_de_producto(
            organizacion_id, producto.id, db_session, limite=2, cursor=cursor
        )
        vistos.extend(fila.id for fila in pagina)
        if cursor is None:
            break
    assert len(vistos) == len(set(vistos)) == 5
    # Orden descendente (D4): el primero de la primera página es el de
    # mayor `vigencia_desde`.
    primera_pagina, _ = proveedores_repository.listar_historial_de_producto(
        organizacion_id, producto.id, db_session, limite=1
    )
    assert primera_pagina[0].id == datos[-1].id


def test_existe_costo_para_presentacion(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    proveedor = _crear_proveedor(db_session, organizacion_id)
    producto, presentacion_id = _crear_producto_y_presentacion(
        db_session, organizacion_id, alicuota_id, proveedor.id
    )
    assert (
        proveedores_repository.existe_costo_para_presentacion(
            organizacion_id, presentacion_id, db_session
        )
        is False
    )
    proveedores_repository.insertar_costos(
        organizacion_id,
        db_session,
        costos=[
            _dato_costo(
                usuario_id=usuario_id,
                proveedor_id=proveedor.id,
                producto_id=producto.id,
                presentacion_id=presentacion_id,
                vigencia_desde=date(2026, 9, 1),
                momento=_MOMENTO,
            )
        ],
    )
    assert (
        proveedores_repository.existe_costo_para_presentacion(
            organizacion_id, presentacion_id, db_session
        )
        is True
    )


# --- P11 (aprobado en la verificación manual 13.5, opción B):
# `obtener_ultimo_por_presentacion` --------------------------------------


def test_obtener_ultimo_por_presentacion_una_fila_por_presentacion_con_costo(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """`obtener_ultimo_por_presentacion` devuelve el último costo (D4:
    `vigencia_desde DESC, creado_en DESC, id DESC`) de CADA presentación
    con al menos un costo con `vigencia_desde <= fecha`: un costo futuro
    no se considera, y el desempate por `creado_en` aplica igual que en
    `obtener_vigente`."""
    proveedor = _crear_proveedor(db_session, organizacion_id)
    producto, presentacion_caja = _crear_producto_y_presentacion(
        db_session, organizacion_id, alicuota_id, proveedor.id
    )
    presentacion_botella = catalogo_repository.crear_presentacion(
        organizacion_id,
        db_session,
        presentacion_id=nuevo_id(),
        producto_id=producto.id,
        nombre="Botella",
        unidades_base=1,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=False,
        activo=True,
        momento=_MOMENTO,
    ).id

    # Caja x12: dos costos con la misma vigencia -- prevalece el `creado_en`
    # más reciente (D4); un tercero futuro no debe considerarse.
    caja_antiguo = _dato_costo(
        usuario_id=usuario_id,
        proveedor_id=proveedor.id,
        producto_id=producto.id,
        presentacion_id=presentacion_caja,
        vigencia_desde=date(2026, 9, 1),
        momento=_MOMENTO,
        valor=Decimal("18000.00"),
    )
    caja_reciente = _dato_costo(
        usuario_id=usuario_id,
        proveedor_id=proveedor.id,
        producto_id=producto.id,
        presentacion_id=presentacion_caja,
        vigencia_desde=date(2026, 9, 1),
        momento=_MOMENTO + timedelta(seconds=1),
        valor=Decimal("18500.00"),
    )
    caja_futuro = _dato_costo(
        usuario_id=usuario_id,
        proveedor_id=proveedor.id,
        producto_id=producto.id,
        presentacion_id=presentacion_caja,
        vigencia_desde=date(2027, 1, 1),
        momento=_MOMENTO + timedelta(seconds=2),
        valor=Decimal("99999.00"),
    )
    # Botella: un único costo, vigente.
    botella_unico = _dato_costo(
        usuario_id=usuario_id,
        proveedor_id=proveedor.id,
        producto_id=producto.id,
        presentacion_id=presentacion_botella,
        vigencia_desde=date(2026, 1, 1),
        momento=_MOMENTO,
        valor=Decimal("1000.00"),
    )
    proveedores_repository.insertar_costos(
        organizacion_id,
        db_session,
        costos=[caja_antiguo, caja_reciente, caja_futuro, botella_unico],
    )

    resultado = proveedores_repository.obtener_ultimo_por_presentacion(
        organizacion_id, producto.id, date(2026, 9, 24), db_session
    )

    por_presentacion = {fila.presentacion_id: fila for fila in resultado}
    assert len(resultado) == 2
    assert por_presentacion[presentacion_caja].valor == Decimal("18500.00")
    assert por_presentacion[presentacion_botella].valor == Decimal("1000.00")


def test_obtener_ultimo_por_presentacion_omite_presentacion_sin_costo(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """Una presentación sin ningún costo con `vigencia_desde <= fecha` se
    omite del resultado (no aparece con `None`)."""
    proveedor = _crear_proveedor(db_session, organizacion_id)
    producto, presentacion_caja = _crear_producto_y_presentacion(
        db_session, organizacion_id, alicuota_id, proveedor.id
    )
    catalogo_repository.crear_presentacion(
        organizacion_id,
        db_session,
        presentacion_id=nuevo_id(),
        producto_id=producto.id,
        nombre="Botella",
        unidades_base=1,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=False,
        activo=True,
        momento=_MOMENTO,
    )
    proveedores_repository.insertar_costos(
        organizacion_id,
        db_session,
        costos=[
            _dato_costo(
                usuario_id=usuario_id,
                proveedor_id=proveedor.id,
                producto_id=producto.id,
                presentacion_id=presentacion_caja,
                vigencia_desde=date(2026, 9, 1),
                momento=_MOMENTO,
            )
        ],
    )

    resultado = proveedores_repository.obtener_ultimo_por_presentacion(
        organizacion_id, producto.id, date(2026, 9, 24), db_session
    )

    assert len(resultado) == 1
    assert resultado[0].presentacion_id == presentacion_caja


def test_obtener_ultimo_por_presentacion_no_incluye_datos_de_otra_organizacion(
    db_session: Session,
    organizacion_id: uuid.UUID,
    otra_organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """INV-21: filtrar por una organización ajena al producto no devuelve
    sus costos."""
    proveedor = _crear_proveedor(db_session, organizacion_id)
    producto, presentacion_caja = _crear_producto_y_presentacion(
        db_session, organizacion_id, alicuota_id, proveedor.id
    )
    proveedores_repository.insertar_costos(
        organizacion_id,
        db_session,
        costos=[
            _dato_costo(
                usuario_id=usuario_id,
                proveedor_id=proveedor.id,
                producto_id=producto.id,
                presentacion_id=presentacion_caja,
                vigencia_desde=date(2026, 9, 1),
                momento=_MOMENTO,
            )
        ],
    )

    resultado = proveedores_repository.obtener_ultimo_por_presentacion(
        otra_organizacion_id, producto.id, date(2026, 9, 24), db_session
    )

    assert resultado == []


# --- propiedad: `obtener_vigente` (SQL) coincide con `elegir_vigente` -----


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    ofensas=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=20),  # offset de días de vigencia_desde
            st.integers(min_value=0, max_value=20),  # offset de segundos de creado_en
        ),
        min_size=1,
        max_size=6,
        unique=True,
    ),
    fecha_offset=st.integers(min_value=-5, max_value=25),
)
def test_property_obtener_vigente_coincide_con_elegir_vigente(
    db_session: Session,
    organizacion_id: uuid.UUID,
    alicuota_id: uuid.UUID,
    usuario_id: uuid.UUID,
    ofensas: list[tuple[int, int]],
    fecha_offset: int,
) -> None:
    """`design.md` D4, tarea 6.5/7.3: la consulta SQL real
    (`obtener_vigente`) debe elegir siempre el mismo candidato que la
    función pura (`elegir_vigente`) sobre los mismos datos.

    Cada ejemplo de Hypothesis reutiliza el mismo `db_session` (la misma
    transacción externa, revertida recién al final del test por el
    fixture) -- se envuelve en un `SAVEPOINT` propio (`begin_nested`) y se
    revierte explícitamente al final de CADA ejemplo, para no acumular
    datos entre ejemplos ni perder las filas de `organizacion_id`/
    `alicuota_id` creadas por los fixtures externos (que sí deben
    sobrevivir a todos los ejemplos)."""
    punto_de_guardado = db_session.begin_nested()
    try:
        proveedor = _crear_proveedor(db_session, organizacion_id)
        producto, presentacion_id = _crear_producto_y_presentacion(
            db_session, organizacion_id, alicuota_id, proveedor.id
        )
        base = date(2026, 1, 1)
        datos = [
            _dato_costo(
                usuario_id=usuario_id,
                proveedor_id=proveedor.id,
                producto_id=producto.id,
                presentacion_id=presentacion_id,
                vigencia_desde=base + timedelta(days=dias),
                momento=_MOMENTO + timedelta(seconds=segundos),
                valor=Decimal("1000.00") + Decimal(indice),
            )
            for indice, (dias, segundos) in enumerate(ofensas)
        ]
        proveedores_repository.insertar_costos(organizacion_id, db_session, costos=datos)

        fecha = base + timedelta(days=fecha_offset)
        candidatos = [
            CandidatoVigencia(
                id=dato.id,
                vigencia_desde=dato.vigencia_desde,
                creado_en=dato.momento,
                costo_base=dato.costo_base,
            )
            for dato in datos
        ]
        esperado = elegir_vigente(candidatos, fecha=fecha)

        obtenido = proveedores_repository.obtener_vigente(
            organizacion_id, producto.id, fecha, db_session
        )

        if esperado is None:
            assert obtenido is None
        else:
            assert obtenido is not None
            assert obtenido.id == esperado.id
    finally:
        punto_de_guardado.rollback()
