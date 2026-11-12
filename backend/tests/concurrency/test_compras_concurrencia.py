"""Change 11, tarea 13.1: concurrencia real de `COMPRA_CONFIRMAR` y `COMPRA_ANULAR` contra
PostgreSQL real (Testcontainers, `READ COMMITTED`, `docs/02-arquitectura.md` §7.1), con el
mismo arnés que `test_importacion_concurrencia.py`: cada hilo tiene su propia
conexión/sesión, confirma su propia transacción y arranca junto a los otros en una
`threading.Barrier`. Nunca hay rollback externo (`CLAUDE.md` §4).

Escenarios (`design.md` D6, D7; specs `compras` y `anulacion-de-compras`):

- dos compras simultáneas al mismo proveedor con los productos en orden inverso: sin
  interbloqueo (orden global de bloqueo, `02` §7.3), con el stock, el promedio y el saldo de
  aplicar ambas (INV-12, INV-13);
- una compra en paralelo con un `STOCK_INICIAL_REGISTRAR` del mismo producto: mismo
  resultado, sin interbloqueo;
- dos anulaciones simultáneas de la misma compra: una `COMPRA_YA_ANULADA` y un solo egreso
  por línea;
- el mismo `Operation-Id` en paralelo: un solo efecto (INV-06).
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
from app.core.errors import DomainError
from app.modules.proveedores import commands as proveedores_commands
from app.modules.stock import service as stock_service
from app.modules.stock.service import LineaDeStockInicial
from app.modules.sync import service as sync_service
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import (
    crear_presentacion_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

MOMENTO = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
ESPERA_MAXIMA = 60
MICRO = Decimal("0.000001")
CONFIRMAR = "COMPRA_CONFIRMAR"
ANULAR = "COMPRA_ANULAR"
PERMISOS = frozenset({"REGISTRAR_COMPRA", "ANULAR_COMPRA", "PERMITIR_STOCK_NEGATIVO"})


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


def _con_iva(neto: str) -> Decimal:
    return (Decimal(neto) * Decimal("1.21")).quantize(Decimal("0.01"))


class _Escenario:
    """Una organización confirmada con un proveedor, dos productos en Botella (la
    presentación de referencia, una unidad base), un depósito y un usuario con
    `REGISTRAR_COMPRA` y `ANULAR_COMPRA`."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.org = crear_organizacion(sesion).id
            self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=PERMISOS
            )
            self.proveedor_id = crear_proveedor(sesion, self.org, nombre="Bodega Sur")
            self.productos: list[UUID] = []
            self.presentaciones: dict[UUID, UUID] = {}
            for nombre in ("Vino A", "Cerveza B"):
                producto_id = crear_producto_sql(
                    sesion, self.org, nombre=nombre, proveedor_id=self.proveedor_id
                )
                self.productos.append(producto_id)
                self.presentaciones[producto_id] = crear_presentacion_sql(
                    sesion,
                    self.org,
                    producto_id,
                    nombre="Botella",
                    unidades_base=1,
                    es_referencia=True,
                )
            self.productos.sort()  # ascendentes por id: el orden global de bloqueo
            self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
            self.motivo_id = uuid4()
            sesion.execute(
                text(
                    "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, "
                    "creado_en, actualizado_en) VALUES (:id, :org, 'ANULACION_COMPRA', "
                    "'Error de carga', true, :m, :m)"
                ),
                {"id": self.motivo_id, "org": self.org, "m": MOMENTO},
            )
            sesion.commit()
        finally:
            sesion.close()

    # --- comandos por el bus ---------------------------------------------------------

    def contenido_de_compra(self, lineas: list[tuple[UUID, int, str]]) -> dict[str, Any]:
        """`(producto, cantidad de botellas, valor por botella sin IVA)` por línea, a
        crédito, con el total de factura que corresponde (21 % de IVA)."""
        neto = sum(Decimal(cantidad) * Decimal(valor) for _, cantidad, valor in lineas)
        return {
            "proveedor_id": str(self.proveedor_id),
            "fecha": "2026-10-02",
            "ubicacion_id": str(self.deposito_id),
            "condicion": "CREDITO",
            "total_factura": str(_con_iva(str(neto))),
            "lineas": [
                {
                    "producto_id": str(producto_id),
                    "presentacion_id": str(self.presentaciones[producto_id]),
                    "cantidad": str(cantidad),
                    "valor": valor,
                    "incluye_iva": False,
                }
                for producto_id, cantidad, valor in lineas
            ],
        }

    def enviar(
        self, sesion: Session, contenido: dict[str, Any], operation_id: UUID, tipo: str = CONFIRMAR
    ) -> Any:
        sobre = SobreComando(
            operation_id=operation_id,
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)
        manejador = (
            proveedores_commands.manejar_compra_confirmar
            if tipo == CONFIRMAR
            else proveedores_commands.manejar_compra_anular
        )

        def _ejecutar(sesion_protegida: object) -> Any:
            return manejador(
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

    def confirmar(self, contenido: dict[str, Any]) -> UUID:
        """Confirma una compra en su propia transacción y devuelve su id."""
        sesion = _sesion_independiente(self.database_url)
        try:
            comando = self.enviar(sesion, contenido, uuid4())
            sesion.commit()
            assert comando.resultado is not None
            return UUID(str(comando.resultado["compra_id"]))
        finally:
            sesion.close()

    def contenido_de_anulacion(self, compra_id: UUID) -> dict[str, Any]:
        return {"compra_id": str(compra_id), "motivo_id": str(self.motivo_id)}

    def stock_inicial_por_pantalla(
        self, sesion: Session, lineas: list[tuple[UUID, int, str]]
    ) -> None:
        """Lo que hace `STOCK_INICIAL_REGISTRAR`: el servicio con sus líneas."""
        stock_service.registrar_stock_inicial(
            self.org,
            sesion,
            RELOJ,
            ubicacion_id=self.deposito_id,
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

    def saldo_de_cuenta(self) -> Decimal:
        ((saldo,),) = self.leer(
            "SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), 0) "
            "FROM cuenta_movimiento WHERE organizacion_id = :o "
            "AND cuenta_tipo = 'PROVEEDOR' AND entidad_id = :e",
            e=self.proveedor_id,
        )
        assert isinstance(saldo, Decimal | int)
        return Decimal(saldo)

    def cantidad_de(self, tabla: str, donde: str = "true") -> int:
        ((cantidad,),) = self.leer(
            f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o AND {donde}"  # noqa: S608
        )
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


class TestDosComprasAlMismoProveedorEnOrdenesOpuestos:
    """`02` §7.3, INV-12, INV-13: `COMPRA_CONFIRMAR` toma los bloqueos en orden global
    (proveedor, luego productos por id) aunque la compra traiga las líneas al revés."""

    @pytest.mark.parametrize("repeticion", range(5))
    def test_sin_interbloqueo_y_con_stock_promedio_y_saldo_de_aplicar_ambas(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        a, b = escenario.productos
        primera = escenario.contenido_de_compra([(a, 10, "100.00"), (b, 10, "200.00")])
        segunda = escenario.contenido_de_compra([(b, 10, "400.00"), (a, 10, "300.00")])
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, primera, uuid4()),
            lambda sesion: escenario.enviar(sesion, segunda, uuid4()),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        for producto_id in (a, b):
            assert escenario.saldo(producto_id) == 20
            assert escenario.suma_del_libro(producto_id) == 20
        # Promedio ponderado, igual en cualquier orden de aplicación.
        assert abs(escenario.promedio(a) - Decimal(200)) <= MICRO
        assert abs(escenario.promedio(b) - Decimal(300)) <= MICRO
        assert escenario.saldo_de_cuenta() == _con_iva("3000") + _con_iva("7000")
        assert escenario.cantidad_de("compra") == 2
        assert escenario.diferencias() == []


class TestCompraEnParaleloConStockInicial:
    """INV-12: una compra y un `STOCK_INICIAL_REGISTRAR` de los mismos productos se
    serializan por el mismo orden de bloqueo, sin interbloqueo."""

    @pytest.mark.parametrize("repeticion", range(5))
    def test_stock_y_promedio_son_los_de_aplicar_ambos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        a, b = escenario.productos
        compra = escenario.contenido_de_compra([(b, 10, "200.00"), (a, 10, "100.00")])
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, compra, uuid4()),
            lambda sesion: escenario.stock_inicial_por_pantalla(
                sesion, [(a, 20, "400"), (b, 20, "400")]
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert escenario.saldo(a) == escenario.suma_del_libro(a) == 30
        assert escenario.saldo(b) == escenario.suma_del_libro(b) == 30
        # (10 * 100 + 20 * 400) / 30 = 300 y (10 * 200 + 20 * 400) / 30 = 333,333333.
        assert abs(escenario.promedio(a) - Decimal(300)) <= MICRO
        assert abs(escenario.promedio(b) - Decimal("333.333333")) <= MICRO
        assert escenario.saldo_de_cuenta() == _con_iva("3000")
        assert escenario.diferencias() == []


class TestDosAnulacionesSimultaneas:
    """CMP-05: la anulación bloquea la compra; la segunda ve `ANULADA`."""

    @pytest.mark.parametrize("repeticion", range(3))
    def test_una_anula_y_la_otra_es_compra_ya_anulada_con_un_solo_egreso_por_linea(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        a, b = escenario.productos
        compra_id = escenario.confirmar(
            escenario.contenido_de_compra([(a, 10, "100.00"), (b, 10, "200.00")])
        )
        anulacion = escenario.contenido_de_anulacion(compra_id)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, anulacion, uuid4(), ANULAR),
            lambda sesion: escenario.enviar(sesion, anulacion, uuid4(), ANULAR),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        (error,) = errores.values()
        assert isinstance(error, DomainError)
        assert error.codigo == "COMPRA_YA_ANULADA"
        egresos = "tipo = 'ANULACION_COMPRA'"
        assert escenario.cantidad_de("stock_movimiento", egresos) == 2
        assert escenario.cantidad_de("cuenta_movimiento", egresos) == 1
        for producto_id in (a, b):
            assert escenario.saldo(producto_id) == 0
        assert escenario.saldo_de_cuenta() == Decimal("0.00")
        assert escenario.diferencias() == []


class TestMismoOperationIdSimultaneo:
    """INV-06: dos envíos simultáneos con el mismo `Operation-Id` producen un solo efecto;
    el segundo espera a la reserva del primero y recibe el resultado ya guardado."""

    def test_dos_compras_con_el_mismo_operation_id_dejan_un_solo_efecto(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        a, b = escenario.productos
        contenido = escenario.contenido_de_compra([(a, 10, "100.00"), (b, 10, "200.00")])
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, contenido, operation_id).resultado,
            lambda sesion: escenario.enviar(sesion, contenido, operation_id).resultado,
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert resultados[0] == resultados[1]
        assert escenario.cantidad_de("compra") == 1
        assert escenario.cantidad_de("stock_movimiento") == 2
        assert escenario.cantidad_de("cuenta_movimiento") == 1
        assert escenario.saldo_de_cuenta() == _con_iva("3000")
