"""Change 05, grupo 11 (tareas 11.2, 11.3): concurrencia real de CAT-01 y
CAT-03 contra PostgreSQL real (Testcontainers, aislamiento por defecto
`READ COMMITTED`, `docs/02-arquitectura.md` §7.1).

Mismo arnés que `test_inv06_reserva_idempotencia_concurrencia.py`: dos
hilos, cada uno con su propia conexión/sesión que confirma su propia
transacción (simula dos workers distintos, `02` §16.2). A diferencia de
`test_bus_reintentos_concurrencia.py`, acá NO hace falta elevar a
`SERIALIZABLE`: ambos escenarios ya se resuelven bajo `READ COMMITTED`
porque dependen de una restricción de base que bloquea/aborta el segundo
`INSERT`/`UPDATE` (CAT-01: `ux_producto__codigo`, traducido por
`guardar_con_traduccion_de_integridad`; CAT-03: `SELECT ... FOR UPDATE`
sobre `producto` en `cambiar_referencia`, `design.md` D5), no de un
conflicto de serialización.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.modules.catalogo import repository as catalogo_repository
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import CodigoDuplicadoError
from app.modules.catalogo.domain.presentaciones import DatosPresentacion
from app.modules.catalogo.models import Presentacion, Producto
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad.models import Organizacion
from app.modules.proveedores import repository as proveedores_repository

# Change 06, grupo 9: registra el puerto D9/ADR-025 que `catalogo_service.
# crear_producto` consulta para validar `proveedor_id` -- sin este import,
# "No hay consulta de proveedor registrada" (falla cerrado) en vez del
# escenario de concurrencia que esta prueba ejercita.
from app.modules.proveedores import service as proveedores_service  # noqa: F401

# Change 06, grupo 5: sin importar `proveedores/models.py`, SQLAlchemy no
# puede resolver la tabla `proveedor` al configurar el mapper de
# `Producto` (`fk_producto__proveedor`), lo que revienta con
# `NoReferencedTableError` en vez del error de negocio esperado. Mismo
# patrón que `tests/integration/test_proveedores_migracion.py`.
from app.modules.proveedores.models import CostoInformado, Proveedor  # noqa: F401

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
            nombre="Organización de prueba catálogo concurrencia",
            slug=f"org-cat-concurrencia-{uuid4().hex[:8]}",
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


def _preparar_proveedor(database_url: str, organizacion_id: UUID) -> UUID:
    """`producto.proveedor_id` es `NOT NULL` desde change 06 grupo 4 (D2):
    ambos escenarios de concurrencia necesitan un proveedor activo real."""
    sesion = _sesion_independiente(database_url)
    try:
        proveedor = proveedores_repository.crear_proveedor(
            organizacion_id,
            sesion,
            proveedor_id=nuevo_id(),
            nombre=f"Proveedor-{uuid4().hex[:8]}",
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


class TestCat01DosAltasSimultaneasConElMismoCodigo:
    """Tarea 11.2: dos `PRODUCTO_CREAR` simultáneos con el mismo código ->
    uno aceptado, el otro `CODIGO_DUPLICADO` (CAT-01, `03` §5: `UNIQUE
    (organizacion_id, codigo)`, `design.md` D6: el handler lanza la
    `DomainError` directamente, no la persiste como `RECHAZADO`)."""

    def test_dos_altas_simultaneas_con_el_mismo_codigo_una_aceptada_una_codigo_duplicado(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        organizacion_id = _preparar_organizacion(database_url)
        categoria_id, alicuota_id = _preparar_categoria_y_alicuota(database_url, organizacion_id)
        proveedor_id = _preparar_proveedor(database_url, organizacion_id)
        codigo_compartido = f"VA-CONC-{uuid4().hex[:8]}"

        barrera = threading.Barrier(2)
        resultados: dict[int, str] = {}
        errores: dict[int, BaseException] = {}

        def _presentaciones() -> list[DatosPresentacion]:
            return [
                DatosPresentacion(
                    nombre="Botella",
                    unidades_base=1,
                    usar_en_venta=True,
                    usar_en_compra=True,
                    es_referencia=True,
                )
            ]

        def _worker(indice_hilo: int) -> None:
            sesion = _sesion_independiente(database_url)
            try:
                barrera.wait(timeout=10)
                catalogo_service.crear_producto(
                    organizacion_id,
                    sesion,
                    FixedClock(MOMENTO),
                    codigo=codigo_compartido,
                    nombre=f"Vino {indice_hilo}",
                    categoria_id=categoria_id,
                    marca_id=None,
                    proveedor_id=proveedor_id,
                    unidad_base="botella",
                    alicuota_id=alicuota_id,
                    presentaciones=_presentaciones(),
                    actor_id=None,
                )
                sesion.commit()
                resultados[indice_hilo] = "ACEPTADO"
            except CodigoDuplicadoError as error:
                sesion.rollback()
                resultados[indice_hilo] = "CODIGO_DUPLICADO"
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

        assert set(resultados.values()) == {"ACEPTADO", "CODIGO_DUPLICADO"}, (
            f"Un hilo debía terminar ACEPTADO y el otro CODIGO_DUPLICADO: {resultados}, "
            f"errores={errores}"
        )
        indice_duplicado = next(i for i, r in resultados.items() if r == "CODIGO_DUPLICADO")
        assert isinstance(errores[indice_duplicado], CodigoDuplicadoError)

        sesion_verificacion = _sesion_independiente(database_url)
        try:
            cantidad = sesion_verificacion.scalar(
                select(func.count())
                .select_from(Producto)
                .where(
                    Producto.organizacion_id == organizacion_id,
                    Producto.codigo == codigo_compartido,
                )
            )
        finally:
            sesion_verificacion.close()
        # Exactamente un producto con ese código quedó persistido -- el
        # segundo hilo nunca llegó a escribir (INV-01: su transacción se
        # revirtió entera).
        assert cantidad == 1


class TestCat03DosCambiosDeReferenciaSimultaneos:
    """Tarea 11.3: dos `PRESENTACION_REFERENCIA_CAMBIAR` simultáneos sobre
    el MISMO producto -> al final hay exactamente una referencia (CAT-03,
    `design.md` D5: `SELECT ... FOR UPDATE` sobre `producto` serializa los
    dos cambios; bajo `READ COMMITTED` el segundo hilo se BLOQUEA hasta que
    el primero confirma, en vez de abortar)."""

    def _preparar_producto_con_dos_presentaciones(
        self,
        database_url: str,
        organizacion_id: UUID,
        categoria_id: UUID,
        alicuota_id: UUID,
        proveedor_id: UUID,
    ) -> tuple[UUID, UUID, UUID]:
        sesion = _sesion_independiente(database_url)
        try:
            producto, presentaciones = catalogo_service.crear_producto(
                organizacion_id,
                sesion,
                FixedClock(MOMENTO),
                codigo=f"VA-CONC-REF-{uuid4().hex[:8]}",
                nombre="Vino con dos presentaciones",
                categoria_id=categoria_id,
                marca_id=None,
                proveedor_id=proveedor_id,
                unidad_base="botella",
                alicuota_id=alicuota_id,
                presentaciones=[
                    DatosPresentacion(
                        nombre="Botella",
                        unidades_base=1,
                        usar_en_venta=True,
                        usar_en_compra=True,
                        es_referencia=True,
                    ),
                    DatosPresentacion(
                        nombre="Caja x6",
                        unidades_base=6,
                        usar_en_venta=True,
                        usar_en_compra=True,
                        es_referencia=False,
                    ),
                ],
                actor_id=None,
            )
            sesion.commit()
            botella = next(p for p in presentaciones if p.nombre == "Botella")
            caja = next(p for p in presentaciones if p.nombre == "Caja x6")
            return producto.id, botella.id, caja.id
        finally:
            sesion.close()

    def test_dos_cambios_de_referencia_simultaneos_dejan_exactamente_una_referencia(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        organizacion_id = _preparar_organizacion(database_url)
        categoria_id, alicuota_id = _preparar_categoria_y_alicuota(database_url, organizacion_id)
        proveedor_id = _preparar_proveedor(database_url, organizacion_id)
        producto_id, botella_id, caja_id = self._preparar_producto_con_dos_presentaciones(
            database_url, organizacion_id, categoria_id, alicuota_id, proveedor_id
        )
        # Empieza en "Botella" (referencia inicial); un hilo la cambia a
        # "Caja x6", el otro la vuelve a cambiar a "Botella" -- ambos
        # destinos son válidos (activos, usados en venta), así que ninguno
        # falla por CAT-03/`ReferenciaInvalidaError`: lo que se ejerce acá
        # es la serialización del `FOR UPDATE`, no una validación.
        destinos = {0: caja_id, 1: botella_id}

        barrera = threading.Barrier(2)
        resultados: dict[int, str] = {}
        errores: dict[int, BaseException] = {}

        def _worker(indice_hilo: int) -> None:
            sesion = _sesion_independiente(database_url)
            try:
                barrera.wait(timeout=10)
                catalogo_service.cambiar_referencia(
                    organizacion_id,
                    sesion,
                    FixedClock(MOMENTO),
                    producto_id=producto_id,
                    presentacion_id=destinos[indice_hilo],
                    actor_id=None,
                )
                sesion.commit()
                resultados[indice_hilo] = "ACEPTADO"
            except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
                sesion.rollback()
                errores[indice_hilo] = error
                resultados[indice_hilo] = "ERROR"
            finally:
                sesion.close()

        hilos = [threading.Thread(target=_worker, args=(i,)) for i in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        assert not errores, f"Ningún hilo debía fallar: {errores}"
        assert resultados == {0: "ACEPTADO", 1: "ACEPTADO"}

        sesion_verificacion = _sesion_independiente(database_url)
        try:
            referencias = sesion_verificacion.scalars(
                select(Presentacion).where(
                    Presentacion.organizacion_id == organizacion_id,
                    Presentacion.producto_id == producto_id,
                    Presentacion.es_referencia.is_(True),
                )
            ).all()
        finally:
            sesion_verificacion.close()
        # Exactamente una referencia al final, sin importar el orden real
        # de ejecución de los dos hilos (el `FOR UPDATE` los serializa).
        assert len(referencias) == 1
        assert referencias[0].id in {botella_id, caja_id}
