"""Change 06, grupo 12 (tareas 12.2, 12.3, 12.4): concurrencia real de
`proveedores` contra PostgreSQL real (Testcontainers, `READ COMMITTED`,
`docs/02-arquitectura.md` §7.1), mismo arnés que
`tests/concurrency/test_catalogo_concurrencia.py`: dos hilos, cada uno con
su propia conexión/sesión que confirma su propia transacción.

- 12.2: dos `PROVEEDOR_CREAR` con el mismo nombre -> uno `ACEPTADO`, el
  otro `NOMBRE_DUPLICADO` (D7, `ux_proveedor__nombre`, misma mecánica que
  CAT-01 en `catalogo`).
- 12.3: desactivar un proveedor mientras otro hilo le asigna un producto
  activo -> nunca queda un producto activo con un proveedor recién
  desactivado (D5/ADR-026, D14: `PROVEEDOR_MODIFICAR` toma `FOR UPDATE`
  sobre el proveedor; la asignación lo lee con `FOR SHARE` vía el puerto de
  ADR-025 -- se serializan, cualquiera sea el orden real de llegada).
- 12.4: dos `COSTO_INFORMAR` sobre los mismos dos productos, en orden
  inverso, terminan sin interbloqueo y con los cuatro costos registrados
  (D14: orden fijo -- proveedor, luego productos por `id` ascendente --
  independiente del orden de la lista de entrada)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.modules.catalogo import repository as catalogo_repository
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import (
    ProveedorInactivoError as CatalogoProveedorInactivoError,
)
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad.models import Organizacion, Rol, Usuario
from app.modules.proveedores import repository as proveedores_repository
from app.modules.proveedores import service as proveedores_service
from app.modules.proveedores.domain.errores import (
    NombreDuplicadoError,
    ProveedorConProductosActivosError,
)
from app.modules.proveedores.domain.lote import CostoDelLote
from app.modules.proveedores.models import CostoInformado, Proveedor

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _sesion_independiente(database_url: str) -> Session:
    """Conexión/sesión propia que confirma sus propias transacciones --
    simula un worker de FastAPI distinto (`02` §16.2)."""
    factory = crear_session_factory(crear_engine(database_url))
    return factory()


def _preparar_organizacion(database_url: str) -> UUID:
    sesion = _sesion_independiente(database_url)
    try:
        organizacion = Organizacion(
            id=nuevo_id(),
            nombre="Organización de prueba proveedores concurrencia",
            slug=f"org-prov-concurrencia-{uuid4().hex[:8]}",
            cuit=None,
            moneda="ARS",
            zona_horaria="America/Argentina/Mendoza",
            estado="ACTIVA",
            creado_en=MOMENTO,
            actualizado_en=MOMENTO,
            actualizado_por_id=None,
        )
        sesion.add(organizacion)
        sesion.flush()
        sesion.commit()
        return organizacion.id
    finally:
        sesion.close()


def _preparar_categoria_y_alicuota(database_url: str, organizacion_id: UUID) -> tuple[UUID, UUID]:
    sesion = _sesion_independiente(database_url)
    try:
        categoria = catalogo_repository.crear_categoria(
            organizacion_id,
            sesion,
            categoria_id=nuevo_id(),
            nombre=f"Categoria-{uuid4().hex[:8]}",
            activo=True,
            momento=MOMENTO,
        )
        alicuota = AlicuotaIva(
            id=nuevo_id(),
            organizacion_id=organizacion_id,
            nombre="21%",
            valor="0.210000",
            activo=True,
            creado_en=MOMENTO,
            actualizado_en=MOMENTO,
        )
        sesion.add(alicuota)
        sesion.commit()
        return categoria.id, alicuota.id
    finally:
        sesion.close()


def _preparar_proveedor(
    database_url: str, organizacion_id: UUID, *, nombre: str | None = None
) -> UUID:
    sesion = _sesion_independiente(database_url)
    try:
        proveedor = proveedores_repository.crear_proveedor(
            organizacion_id,
            sesion,
            proveedor_id=nuevo_id(),
            nombre=nombre or f"Proveedor-{uuid4().hex[:8]}",
            cuit=None,
            contacto=None,
            telefono=None,
            email=None,
            activo=True,
            momento=MOMENTO,
        )
        sesion.commit()
        return proveedor.id
    finally:
        sesion.close()


def _preparar_usuario(database_url: str, organizacion_id: UUID) -> UUID:
    """`costo_informado.usuario_id` es `NOT NULL` con FK compuesta a
    `usuario` (`fk_costo_informado__usuario`): `informar_costos` necesita
    un `actor_id` real, no un UUID inventado."""
    sesion = _sesion_independiente(database_url)
    try:
        rol = Rol(
            id=nuevo_id(),
            organizacion_id=organizacion_id,
            nombre="Rol de prueba",
            tope_descuento=Decimal("0"),
            activo=True,
            creado_en=MOMENTO,
            actualizado_en=MOMENTO,
        )
        sesion.add(rol)
        sesion.flush()
        usuario = Usuario(
            id=nuevo_id(),
            organizacion_id=organizacion_id,
            usuario=f"usuario-{uuid4().hex[:8]}",
            nombre="Usuario de prueba",
            email=None,
            password_hash="hash-de-prueba",
            rol_id=rol.id,
            estado="ACTIVO",
            creado_en=MOMENTO,
            actualizado_en=MOMENTO,
        )
        sesion.add(usuario)
        sesion.commit()
        return usuario.id
    finally:
        sesion.close()


def _preparar_producto_con_presentacion_de_compra(
    database_url: str,
    organizacion_id: UUID,
    categoria_id: UUID,
    alicuota_id: UUID,
    proveedor_id: UUID,
    *,
    codigo: str,
    unidades_base: int = 1,
) -> tuple[UUID, UUID]:
    sesion = _sesion_independiente(database_url)
    try:
        producto = catalogo_repository.crear_producto(
            organizacion_id,
            sesion,
            producto_id=nuevo_id(),
            codigo=codigo,
            nombre=f"Producto {codigo}",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="unidad",
            alicuota_id=alicuota_id,
            activo=True,
            momento=MOMENTO,
        )
        presentacion = catalogo_repository.crear_presentacion(
            organizacion_id,
            sesion,
            presentacion_id=nuevo_id(),
            producto_id=producto.id,
            nombre="Presentación de compra",
            unidades_base=unidades_base,
            usar_en_venta=True,
            usar_en_compra=True,
            es_referencia=True,
            activo=True,
            momento=MOMENTO,
        )
        sesion.commit()
        return producto.id, presentacion.id
    finally:
        sesion.close()


class TestProveedorCrearConcurrente:
    """Tarea 12.2: dos `PROVEEDOR_CREAR` simultáneos con el mismo nombre ->
    uno `ACEPTADO`, el otro `NOMBRE_DUPLICADO` (D7, `ux_proveedor__nombre`)."""

    def test_dos_altas_simultaneas_con_el_mismo_nombre_una_aceptada_una_nombre_duplicado(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        organizacion_id = _preparar_organizacion(database_url)
        nombre_compartido = f"Bodega Andina {uuid4().hex[:8]}"

        barrera = threading.Barrier(2)
        resultados: dict[int, str] = {}
        errores: dict[int, BaseException] = {}

        def _worker(indice_hilo: int) -> None:
            sesion = _sesion_independiente(database_url)
            try:
                barrera.wait(timeout=10)
                proveedores_service.crear_proveedor(
                    organizacion_id,
                    sesion,
                    FixedClock(MOMENTO),
                    nombre=nombre_compartido,
                    cuit=None,
                    contacto=None,
                    telefono=None,
                    email=None,
                    actor_id=None,
                )
                sesion.commit()
                resultados[indice_hilo] = "ACEPTADO"
            except NombreDuplicadoError as error:
                sesion.rollback()
                resultados[indice_hilo] = "NOMBRE_DUPLICADO"
                errores[indice_hilo] = error
            except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
                sesion.rollback()
                errores[indice_hilo] = error
                resultados[indice_hilo] = "ERROR_INESPERADO"
            finally:
                sesion.close()

        hilos = [threading.Thread(target=_worker, args=(i,)) for i in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        assert set(resultados.values()) == {"ACEPTADO", "NOMBRE_DUPLICADO"}, (
            f"Un hilo debía terminar ACEPTADO y el otro NOMBRE_DUPLICADO: {resultados}, "
            f"errores={errores}"
        )
        indice_duplicado = next(i for i, r in resultados.items() if r == "NOMBRE_DUPLICADO")
        assert isinstance(errores[indice_duplicado], NombreDuplicadoError)

        sesion_verificacion = _sesion_independiente(database_url)
        try:
            cantidad = sesion_verificacion.scalar(
                select(func.count())
                .select_from(Proveedor)
                .where(
                    Proveedor.organizacion_id == organizacion_id,
                    Proveedor.nombre == nombre_compartido,
                )
            )
        finally:
            sesion_verificacion.close()
        # Exactamente un proveedor con ese nombre quedó persistido -- el
        # segundo hilo nunca llegó a escribir (INV-01).
        assert cantidad == 1


class TestDesactivarProveedorMientrasSeAsignaUnProductoActivo:
    """Tarea 12.3: desactivar un proveedor mientras otro hilo le asigna un
    producto activo -> nunca queda un producto activo con un proveedor
    recién desactivado (D5/ADR-026, D14). Cualquiera sea el orden real de
    llegada de los dos hilos (`FOR UPDATE` del proveedor en la
    desactivación vs. `FOR SHARE` en la asignación, D14), el resultado
    final respeta el invariante: o el proveedor queda activo (y el
    producto quedó asignado a él), o el proveedor queda inactivo (y la
    asignación fue rechazada, `PROVEEDOR_INACTIVO`)."""

    def test_desactivacion_y_asignacion_no_dejan_producto_activo_con_proveedor_inactivo(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        organizacion_id = _preparar_organizacion(database_url)
        categoria_id, alicuota_id = _preparar_categoria_y_alicuota(database_url, organizacion_id)
        proveedor_a_desactivar_id = _preparar_proveedor(database_url, organizacion_id)
        proveedor_original_id = _preparar_proveedor(database_url, organizacion_id)
        producto_id, _presentacion_id = _preparar_producto_con_presentacion_de_compra(
            database_url,
            organizacion_id,
            categoria_id,
            alicuota_id,
            proveedor_original_id,
            codigo=f"VA-CONC-D5-{uuid4().hex[:8]}",
        )

        barrera = threading.Barrier(2)
        resultados: dict[str, str] = {}
        errores: dict[str, BaseException] = {}

        def _desactivar() -> None:
            sesion = _sesion_independiente(database_url)
            try:
                barrera.wait(timeout=10)
                proveedores_service.modificar_proveedor(
                    organizacion_id,
                    sesion,
                    FixedClock(MOMENTO),
                    proveedor_id=proveedor_a_desactivar_id,
                    nombre=f"Proveedor a desactivar {uuid4().hex[:8]}",
                    cuit=None,
                    contacto=None,
                    telefono=None,
                    email=None,
                    activo=False,
                    actor_id=None,
                )
                sesion.commit()
                resultados["desactivar"] = "ACEPTADO"
            except ProveedorConProductosActivosError as error:
                sesion.rollback()
                resultados["desactivar"] = "PROVEEDOR_CON_PRODUCTOS_ACTIVOS"
                errores["desactivar"] = error
            except BaseException as error:  # noqa: BLE001
                sesion.rollback()
                errores["desactivar"] = error
                resultados["desactivar"] = "ERROR_INESPERADO"
            finally:
                sesion.close()

        def _asignar() -> None:
            sesion = _sesion_independiente(database_url)
            try:
                barrera.wait(timeout=10)
                catalogo_service.modificar_producto(
                    organizacion_id,
                    sesion,
                    FixedClock(MOMENTO),
                    producto_id=producto_id,
                    codigo=f"VA-CONC-D5-{uuid4().hex[:8]}",
                    nombre="Producto reasignado",
                    categoria_id=categoria_id,
                    marca_id=None,
                    proveedor_id=proveedor_a_desactivar_id,
                    unidad_base="unidad",
                    alicuota_id=alicuota_id,
                    activo=True,
                    actor_id=None,
                )
                sesion.commit()
                resultados["asignar"] = "ACEPTADO"
            except CatalogoProveedorInactivoError as error:
                sesion.rollback()
                resultados["asignar"] = "PROVEEDOR_INACTIVO"
                errores["asignar"] = error
            except BaseException as error:  # noqa: BLE001
                sesion.rollback()
                errores["asignar"] = error
                resultados["asignar"] = "ERROR_INESPERADO"
            finally:
                sesion.close()

        hilos = [threading.Thread(target=_desactivar), threading.Thread(target=_asignar)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        assert "ERROR_INESPERADO" not in resultados.values(), (
            f"errores={errores}, resultados={resultados}"
        )

        sesion_verificacion = _sesion_independiente(database_url)
        try:
            proveedor = proveedores_repository.obtener_proveedor_por_id(
                organizacion_id, proveedor_a_desactivar_id, sesion_verificacion
            )
            assert proveedor is not None
            producto = catalogo_repository.obtener_producto_por_id(
                organizacion_id, producto_id, sesion_verificacion
            )
            assert producto is not None
        finally:
            sesion_verificacion.close()

        if proveedor.activo:
            # El proveedor sobrevivió activo: la desactivación fue rechazada
            # porque, para cuando tomó el lock, la asignación ya estaba
            # confirmada (producto activo con ese proveedor).
            assert resultados["desactivar"] == "PROVEEDOR_CON_PRODUCTOS_ACTIVOS"
            assert resultados["asignar"] == "ACEPTADO"
            assert producto.proveedor_id == proveedor_a_desactivar_id
        else:
            # El proveedor quedó inactivo: la asignación, si corrió después,
            # tuvo que ser rechazada -- el invariante central de esta prueba.
            assert resultados["desactivar"] == "ACEPTADO"
            assert resultados["asignar"] == "PROVEEDOR_INACTIVO"
            assert producto.proveedor_id == proveedor_original_id

        # Invariante central (D5/ADR-026), verificado independientemente de
        # cuál hilo ganó la carrera: nunca queda un producto activo
        # apuntando a un proveedor inactivo.
        if not proveedor.activo:
            assert not (producto.activo and producto.proveedor_id == proveedor_a_desactivar_id)


class TestCostoInformarConcurrenteSinInterbloqueo:
    """Tarea 12.4: dos `COSTO_INFORMAR` sobre los mismos dos productos, en
    orden inverso en la lista de entrada, terminan sin interbloqueo y con
    los cuatro costos registrados (D14: orden fijo de lock -- proveedor,
    luego productos por `id` ascendente -- independiente del orden de la
    lista de entrada de cada lote)."""

    def test_dos_lotes_en_orden_inverso_no_interbloquean_y_registran_los_cuatro_costos(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        organizacion_id = _preparar_organizacion(database_url)
        categoria_id, alicuota_id = _preparar_categoria_y_alicuota(database_url, organizacion_id)
        proveedor_id = _preparar_proveedor(database_url, organizacion_id)
        producto_1_id, presentacion_1_id = _preparar_producto_con_presentacion_de_compra(
            database_url,
            organizacion_id,
            categoria_id,
            alicuota_id,
            proveedor_id,
            codigo=f"VA-CONC-D14-1-{uuid4().hex[:8]}",
        )
        producto_2_id, presentacion_2_id = _preparar_producto_con_presentacion_de_compra(
            database_url,
            organizacion_id,
            categoria_id,
            alicuota_id,
            proveedor_id,
            codigo=f"VA-CONC-D14-2-{uuid4().hex[:8]}",
        )
        usuario_a_id = _preparar_usuario(database_url, organizacion_id)
        usuario_b_id = _preparar_usuario(database_url, organizacion_id)

        barrera = threading.Barrier(2)
        resultados: dict[str, str] = {}
        errores: dict[str, BaseException] = {}

        def _costo(producto_id: UUID, presentacion_id: UUID, vigencia_desde: date) -> CostoDelLote:
            return CostoDelLote(
                producto_id=producto_id,
                presentacion_id=presentacion_id,
                valor=Decimal("1000.00"),
                incluye_iva=False,
                bonificacion=Decimal("0"),
                vigencia_desde=vigencia_desde,
                observacion=None,
            )

        def _informar(clave: str, costos: list[CostoDelLote], actor_id: UUID) -> None:
            sesion = _sesion_independiente(database_url)
            try:
                barrera.wait(timeout=10)
                proveedores_service.informar_costos(
                    organizacion_id,
                    sesion,
                    FixedClock(MOMENTO),
                    proveedor_id=proveedor_id,
                    costos=costos,
                    operation_id=uuid4(),
                    actor_id=actor_id,
                )
                sesion.commit()
                resultados[clave] = "ACEPTADO"
            except BaseException as error:  # noqa: BLE001
                sesion.rollback()
                errores[clave] = error
                resultados[clave] = "ERROR_INESPERADO"
            finally:
                sesion.close()

        # Lote A: producto 1 primero, luego producto 2 (orden "natural").
        lote_a = [
            _costo(producto_1_id, presentacion_1_id, date(2026, 9, 1)),
            _costo(producto_2_id, presentacion_2_id, date(2026, 9, 1)),
        ]
        # Lote B: los MISMOS dos productos, en orden INVERSO en la lista de
        # entrada, con una vigencia distinta para no chocar con D4/CST-05.
        lote_b = [
            _costo(producto_2_id, presentacion_2_id, date(2026, 10, 1)),
            _costo(producto_1_id, presentacion_1_id, date(2026, 10, 1)),
        ]

        hilos = [
            threading.Thread(target=_informar, args=("A", lote_a, usuario_a_id)),
            threading.Thread(target=_informar, args=("B", lote_b, usuario_b_id)),
        ]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=30)

        assert not any(hilo.is_alive() for hilo in hilos), (
            "Un hilo quedó colgado (posible interbloqueo real)."
        )
        assert resultados == {"A": "ACEPTADO", "B": "ACEPTADO"}, (
            f"errores={errores}, resultados={resultados}"
        )

        sesion_verificacion = _sesion_independiente(database_url)
        try:
            cantidad = sesion_verificacion.scalar(
                select(func.count())
                .select_from(CostoInformado)
                .where(CostoInformado.organizacion_id == organizacion_id)
            )
        finally:
            sesion_verificacion.close()
        # Los cuatro costos (dos por lote) quedaron registrados -- ningún
        # lote se rechazó ni se perdió una fila.
        assert cantidad == 4
