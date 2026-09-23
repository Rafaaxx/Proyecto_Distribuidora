"""Change 05, grupo 7: servicio de catálogo (`catalogo/service.py`).
Cubre las tareas 7.1 a 7.7: verificadores de uso (D2), categoría/marca
(CAT-01, CAT-05, D11), alta de producto (INV-01, CAT-01 a CAT-06),
modificación de producto, presentaciones (CAT-02, CAT-03, CAT-04, INV-18)
y las lecturas públicas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
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
    RecursoNoEncontradoError,
    ReferenciaInvalidaError,
    UnidadesCongeladasError,
    UnidadesInvalidasError,
)
from app.modules.catalogo.domain.presentaciones import DatosPresentacion
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad.models import Organizacion

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
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> tuple[object, list[object]]:
    return catalogo_service.crear_producto(
        organizacion_id,
        db_session,
        _RELOJ,
        codigo=f"VA-{uuid.uuid4().hex[:8]}",
        nombre="Vino A",
        categoria_id=categoria_id,
        marca_id=None,
        proveedor_id=None,
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
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    _crear_producto_valido(db_session, organizacion_id, categoria_id, alicuota_id)
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
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
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
        proveedor_id=None,
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
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id
    )
    assert producto.activo is True
    assert len(presentaciones) == 2
    releidas = catalogo_service.listar_presentaciones_de_producto(
        organizacion_id, producto.id, db_session
    )
    assert len(releidas) == 2


def test_crear_producto_alicuota_inexistente_da_404(
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID
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
            proveedor_id=None,
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
            proveedor_id=None,
            unidad_base="botella",
            alicuota_id=alicuota_inactiva_id,
            presentaciones=_presentaciones_validas(),
            actor_id=None,
        )


def test_crear_producto_categoria_inactiva_rechaza(
    db_session: Session, organizacion_id: uuid.UUID, alicuota_id: uuid.UUID
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
            proveedor_id=None,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            presentaciones=_presentaciones_validas(),
            actor_id=None,
        )


def test_crear_producto_codigo_duplicado_rechaza(
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
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
        proveedor_id=None,
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
            proveedor_id=None,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            presentaciones=_presentaciones_validas(),
            actor_id=None,
        )


def test_crear_producto_sin_presentaciones_rechaza(
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
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
            proveedor_id=None,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            presentaciones=[],
            actor_id=None,
        )


def test_una_presentacion_invalida_no_deja_nada_escrito(
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
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
            proveedor_id=None,
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
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    producto, _ = _crear_producto_valido(db_session, organizacion_id, categoria_id, alicuota_id)

    inactivo = catalogo_service.modificar_producto(
        organizacion_id,
        db_session,
        _RELOJ,
        producto_id=producto.id,
        codigo=producto.codigo,
        nombre=producto.nombre,
        categoria_id=categoria_id,
        marca_id=None,
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
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    """Spec `productos-y-presentaciones`, escenario "Cambiar la alícuota del
    producto" (CAT-01; VTA-03 congela la alícuota de ventas ya confirmadas,
    fuera del alcance de este change)."""
    producto, _ = _crear_producto_valido(db_session, organizacion_id, categoria_id, alicuota_id)
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
        unidad_base=producto.unidad_base,
        alicuota_id=otra_alicuota.id,
        activo=True,
        actor_id=None,
    )

    assert modificado.alicuota_id == otra_alicuota.id


def test_modificar_producto_de_otra_organizacion_da_404(
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
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
            unidad_base="botella",
            alicuota_id=alicuota_id,
            activo=True,
            actor_id=None,
        )


# --- tarea 7.5: presentaciones (CAT-02, CAT-04, INV-18) --------------------


def test_agregar_presentacion_de_compra(
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    producto, _ = _crear_producto_valido(db_session, organizacion_id, categoria_id, alicuota_id)
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
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """INV-18: un verificador de uso que declara la presentación como
    usada hace que el cambio de unidades se rechace con
    `UNIDADES_CONGELADAS`, conservando las unidades originales."""
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id
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
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id
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
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id
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
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id
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
    db_session: Session, organizacion_id: uuid.UUID, categoria_id: uuid.UUID, alicuota_id: uuid.UUID
) -> None:
    producto, presentaciones = _crear_producto_valido(
        db_session, organizacion_id, categoria_id, alicuota_id
    )
    referencia_esperada = next(p for p in presentaciones if p.es_referencia)

    assert catalogo_service.obtener_producto(organizacion_id, producto.id, db_session) is not None
    referencia = catalogo_service.obtener_referencia_de_producto(
        organizacion_id, producto.id, db_session
    )
    assert referencia is not None
    assert referencia.id == referencia_esperada.id
