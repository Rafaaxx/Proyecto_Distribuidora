"""Change 10, tarea 9.1: concurrencia real de `IMPORTACION_REGISTRAR` contra PostgreSQL
real (Testcontainers, `READ COMMITTED`, `docs/02-arquitectura.md` §7.1), con el mismo arnés
que `test_stock_concurrencia.py`: cada hilo tiene su propia conexión/sesión, confirma su
propia transacción y arranca junto a los otros en una `threading.Barrier`. Nunca hay
rollback externo (`CLAUDE.md` §4).

Escenarios de `specs/importacion/puesta-en-marcha` y `registro-de-importaciones`:

- una importación de stock con los productos en orden inverso al de sus ids, en paralelo con
  un `STOCK_INICIAL_REGISTRAR` de los mismos productos: sin interbloqueo, y stock y promedio
  son los de aplicar ambos (orden global de bloqueo, `02` §7.3, INV-12);
- dos importaciones simultáneas con el mismo `Operation-Id`: un solo efecto (INV-06).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.db import crear_engine, crear_session_factory
from app.modules.importacion import commands as importacion_commands
from app.modules.stock import service as stock_service
from app.modules.stock.service import LineaDeStockInicial
from app.modules.sync import service as sync_service
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import crear_producto_sql, crear_ubicacion_sql

MOMENTO = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
ESPERA_MAXIMA = 60
MICRO = Decimal("0.000001")
CODIGOS = ("PROD-A", "PROD-B", "PROD-C")


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _sesion_independiente(database_url: str) -> Session:
    """Conexión/sesión propia que confirma sus propias transacciones: simula un
    worker de FastAPI distinto (`02` §16.2)."""
    factory = crear_session_factory(crear_engine(database_url))
    return factory()


class _Escenario:
    """Una organización confirmada con tres productos (códigos `PROD-A`, `PROD-B` y
    `PROD-C`), un depósito y un usuario con `IMPORTAR_DATOS`."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.org = crear_organizacion(sesion).id
            self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=frozenset({"IMPORTAR_DATOS"})
            )
            self.productos = [
                crear_producto_sql(sesion, self.org, nombre=f"Producto {codigo}")
                for codigo in CODIGOS
            ]
            for codigo, producto_id in zip(CODIGOS, self.productos, strict=True):
                sesion.execute(
                    text("UPDATE producto SET codigo = :c WHERE id = :id"),
                    {"c": codigo, "id": producto_id},
                )
            self.deposito = crear_ubicacion_sql(sesion, self.org, nombre="Depósito Central")
            sesion.commit()
        finally:
            sesion.close()

    def codigo_de(self, producto_id: UUID) -> str:
        return CODIGOS[self.productos.index(producto_id)]

    # --- la importación por el bus --------------------------------------------------

    def contenido_de_stock(self, filas: list[tuple[str, int, str]]) -> dict[str, Any]:
        """`(código de producto, cantidad, costo con coma)` por fila, en el depósito."""
        return {
            "tipo": "STOCK_INICIAL",
            "archivo_nombre": "stock.csv",
            "filas": [
                {
                    "fila": numero,
                    "valores": {
                        "ubicacion": "Depósito Central",
                        "producto_codigo": codigo,
                        "cantidad_base": str(cantidad),
                        "costo_unitario": costo,
                    },
                }
                for numero, (codigo, cantidad, costo) in enumerate(filas, start=2)
            ],
        }

    def importar(self, sesion: Session, cuerpo: dict[str, Any], operation_id: UUID) -> Any:
        sobre = SobreComando(
            operation_id=operation_id,
            tipo="IMPORTACION_REGISTRAR",
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=cuerpo,
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return importacion_commands.manejar_importacion_registrar(
                sobre,
                validado,  # type: ignore[arg-type]
                sesion=sesion_protegida,
                reloj=RELOJ,
            )

        return sync_service.procesar_comando(
            sesion,
            RELOJ,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def stock_inicial_por_pantalla(
        self, sesion: Session, lineas: list[tuple[UUID, int, str]]
    ) -> None:
        """Lo que hace `STOCK_INICIAL_REGISTRAR`: el servicio con sus líneas."""
        stock_service.registrar_stock_inicial(
            self.org,
            sesion,
            RELOJ,
            ubicacion_id=self.deposito,
            lineas=[
                LineaDeStockInicial(producto_id=p, cantidad_base=c, costo_unitario=costo)
                for p, c, costo in lineas
            ],
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
        )

    # --- lecturas confirmadas --------------------------------------------------------

    def leer(self, consulta: str, **parametros: object) -> list[tuple[object, ...]]:
        sesion = _sesion_independiente(self.database_url)
        try:
            filas = sesion.execute(text(consulta), {"o": self.org, **parametros}).all()
            return [tuple(fila) for fila in filas]
        finally:
            sesion.close()

    def saldo(self, producto_id: UUID) -> int:
        ((saldo,),) = self.leer(
            "SELECT COALESCE(SUM(cantidad_base), 0) FROM stock_saldo "
            "WHERE organizacion_id = :o AND producto_id = :p",
            p=producto_id,
        )
        assert isinstance(saldo, int | Decimal)
        return int(saldo)

    def suma_del_libro(self, producto_id: UUID) -> int:
        ((suma,),) = self.leer(
            "SELECT COALESCE(SUM(cantidad_base), 0) FROM stock_movimiento "
            "WHERE organizacion_id = :o AND producto_id = :p",
            p=producto_id,
        )
        assert isinstance(suma, int | Decimal)
        return int(suma)

    def promedio(self, producto_id: UUID) -> Decimal:
        ((promedio,),) = self.leer(
            "SELECT costo_promedio FROM costo_producto "
            "WHERE organizacion_id = :o AND producto_id = :p",
            p=producto_id,
        )
        assert isinstance(promedio, Decimal)
        return promedio

    def cantidad_de(self, tabla: str) -> int:
        ((cantidad,),) = self.leer(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o")  # noqa: S608
        assert isinstance(cantidad, int)
        return cantidad

    def diferencias(self) -> list[object]:
        sesion = _sesion_independiente(self.database_url)
        try:
            return list(stock_service.verificar_consistencia(self.org, sesion))
        finally:
            sesion.close()


def _en_paralelo(
    database_url: str, trabajos: list[Callable[[Session], Any]]
) -> tuple[dict[int, Any], dict[int, BaseException]]:
    """Corre cada trabajo en su hilo y su sesión, todos arrancando juntos. Cada trabajo
    confirma su transacción o levanta; el valor devuelto se guarda por índice."""
    barrera = threading.Barrier(len(trabajos))
    resultados: dict[int, Any] = {}
    errores: dict[int, BaseException] = {}

    def _worker(indice: int) -> None:
        sesion = _sesion_independiente(database_url)
        try:
            barrera.wait(timeout=10)
            resultados[indice] = trabajos[indice](sesion)
            sesion.commit()
        except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
            sesion.rollback()
            errores[indice] = error
        finally:
            sesion.close()

    hilos = [threading.Thread(target=_worker, args=(i,)) for i in range(len(trabajos))]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=ESPERA_MAXIMA)
    assert not any(hilo.is_alive() for hilo in hilos), (
        "Un hilo quedó colgado (posible interbloqueo real)."
    )
    return resultados, errores


class TestImportacionDeStockFrenteAUnStockInicialPorPantalla:
    """`02` §7.3, INV-12: la importación escribe por (producto, ubicación) ascendentes
    aunque el archivo traiga los productos en orden inverso, así que no se interbloquea
    con un stock inicial por pantalla (que también bloquea en orden ascendente)."""

    @pytest.mark.parametrize("repeticion", range(5))
    def test_sin_interbloqueo_y_con_el_stock_y_el_promedio_de_aplicar_ambos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        ascendentes = sorted(escenario.productos)
        descendentes = list(reversed(ascendentes))
        # El archivo: 10 unidades a 100 en cada producto, en orden inverso al de sus ids.
        archivo = escenario.contenido_de_stock(
            [(escenario.codigo_de(p), 10, "100") for p in descendentes]
        )
        # La pantalla: 20 unidades a 400 de los mismos productos.
        lineas = [(p, 20, "400") for p in ascendentes]
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.importar(sesion, archivo, uuid4()),
            lambda sesion: escenario.stock_inicial_por_pantalla(sesion, lineas),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        for producto_id in escenario.productos:
            assert escenario.saldo(producto_id) == 30
            assert escenario.suma_del_libro(producto_id) == 30
            # (10 * 100 + 20 * 400) / 30 = 300: igual en cualquier orden de aplicación.
            assert abs(escenario.promedio(producto_id) - Decimal(300)) <= MICRO
        assert escenario.cantidad_de("importacion") == 1
        assert escenario.diferencias() == []

    def test_dos_importaciones_de_stock_en_ordenes_opuestos_no_se_interbloquean(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        ascendentes = sorted(escenario.productos)
        codigos_asc = [escenario.codigo_de(p) for p in ascendentes]
        primero = escenario.contenido_de_stock([(c, 5, "100") for c in codigos_asc])
        segundo = escenario.contenido_de_stock([(c, 5, "300") for c in reversed(codigos_asc)])
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.importar(sesion, primero, uuid4()),
            lambda sesion: escenario.importar(sesion, segundo, uuid4()),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        for producto_id in escenario.productos:
            assert escenario.saldo(producto_id) == 10
            assert abs(escenario.promedio(producto_id) - Decimal(200)) <= MICRO
        assert escenario.cantidad_de("importacion") == 2
        assert escenario.diferencias() == []


class TestMismoOperationIdSimultaneo:
    """INV-06: dos envíos simultáneos del mismo archivo con el mismo `Operation-Id`
    producen un solo efecto. La restricción única de la reserva bloquea al segundo
    hasta que el primero confirma; entonces ve el resultado ya guardado."""

    def test_dos_importaciones_simultaneas_con_el_mismo_operation_id_dejan_un_solo_efecto(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        archivo = escenario.contenido_de_stock(
            [(escenario.codigo_de(p), 10, "100") for p in escenario.productos]
        )
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.importar(sesion, archivo, operation_id).resultado,
            lambda sesion: escenario.importar(sesion, archivo, operation_id).resultado,
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert resultados[0] == resultados[1]
        assert resultados[0]["filas_ok"] == 3
        assert escenario.cantidad_de("importacion") == 1
        assert escenario.cantidad_de("stock_movimiento") == 3
        for producto_id in escenario.productos:
            assert escenario.saldo(producto_id) == 10
        assert escenario.diferencias() == []
