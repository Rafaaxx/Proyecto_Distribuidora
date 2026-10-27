"""Change 19, tarea 11.1 (`design.md` D10 opción A, aprobada el 2026-10-27; `02` §7.3): concurrencia
real de `VENTA_ANULAR` contra PostgreSQL real (Testcontainers, `READ COMMITTED`, `02` §7.1), con el
arnés de `test_ventas_concurrencia.py`: cada hilo tiene su propia conexión/sesión, confirma su
propia transacción y arranca junto a los otros en una `threading.Barrier`. Nunca hay rollback
externo (`CLAUDE.md` §4) y la limpieza se hace al final con `TRUNCATE`.

Los escenarios cuyo resultado depende del orden de llegada se prueban además en los DOS órdenes de
forma determinista con `_encadenado` (la primera transacción deja sus bloqueos tomados y SIN
confirmar; se observa a la segunda esperando en `pg_stat_activity`; recién entonces confirma la
primera). Para sostener una transacción sin confirmar, la "primera" corre el handler sobre la
sesión del hilo (los handlers no confirman, `CLAUDE.md` §4): son los mismos bloqueos del orden
aprobado, sin la reserva ni la auditoría del bus. Las carreras libres y el doble envío usan el bus
completo (`sync_service.procesar_comando`). No hay `sleep` para "dar tiempo".

- INV-05, INV-01, TR-06: dos anulaciones de la misma venta, una gana y la otra responde
  `VENTA_YA_ANULADA`; una sola fila de anulación y un solo reingreso;
- INV-13, INV-05, VTA-22: la anulación con devolución frente a `COBRANZA_ANULAR` de su cobranza:
  la cobranza se anula una sola vez, en los dos órdenes;
- INV-12, INV-13, D10: la anulación frente a una venta nueva del mismo producto al mismo cliente:
  sin interbloqueo, con stock y saldo iguales a la suma de sus movimientos;
- CAT-05, ADR-044: la anulación frente a la desactivación del producto: el reingreso se acepta
  aunque el producto quede inactivo, en los dos órdenes;
- STK-09, INV-16, RUT-04: la anulación frente a `JORNADA_ABRIR` sobre la ubicación de la venta:
  o la anulación termina antes o ve la ubicación tomada.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_anular_utiles import (
    MOMENTO_ANULACION,
    PERMISOS_DE_ANULADOR,
    RELOJ_ANULACION,
    VENTA_ANULAR,
    EntornoAnulacion,
)
from ventas_confirmar_utiles import EntornoVenta

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.db import crear_engine
from app.modules.catalogo import service as catalogo_service
from app.modules.cobranzas import service as cobranzas_service
from app.modules.cobranzas.domain.errores import CobranzaYaAnuladaError
from app.modules.stock.domain.errores import UbicacionTomadaError
from app.modules.sync import service as sync_service
from app.modules.ventas.domain.errores import VentaYaAnuladaError
from tests.concurrency.test_pagos_proveedor_concurrencia import _en_paralelo, _sesion_independiente
from tests.concurrency.test_transferencias_ajustes_concurrencia import OK, _encadenado
from tests.concurrency.test_ventas_concurrencia import _Escenario as _EscenarioDeVentas
from tests.integration.stock_utiles import crear_ubicacion_sql

REPETICIONES = 5
VENTA_YA_ANULADA = VentaYaAnuladaError.__name__
COBRANZA_YA_ANULADA = CobranzaYaAnuladaError.__name__
UBICACION_TOMADA = UbicacionTomadaError.__name__
SALDO_INICIAL = Decimal("150000.00")
VENTA_DE_15_BOTELLAS = Decimal("31250.00")
COBRO = "20000.00"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


class _Escenario(_EscenarioDeVentas):
    """La organización de `EntornoAnulacion` (Kiosco La Esquina con saldo de `150000.00`, Vino A
    con 48 botellas a $1.050 en "Depósito central", motivo de `ANULACION_VENTA`), confirmada en su
    propia sesión, más lo que pide cada escenario."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.entorno: EntornoAnulacion = EntornoAnulacion(  # type: ignore[assignment]
                sesion, permisos=PERMISOS_DE_ANULADOR
            )
        finally:
            sesion.close()
        self.org = self.entorno.org

    # --- armado ---------------------------------------------------------------------------

    def vender(self, *lineas: dict[str, Any], con_cobro: bool = False, **cambios: Any) -> UUID:
        """Confirma una venta (por defecto 15 botellas, `31250.00`) en su propia sesión y devuelve
        su id."""
        resultado: list[UUID] = []

        def _armar(e: EntornoVenta) -> None:
            assert isinstance(e, EntornoAnulacion)
            if con_cobro:
                cambios["cobranza"] = e.cobranza((e.efectivo_id, COBRO, None))
            resultado.append(e.vender_y_obtener_id(*lineas, **cambios))

        self.armar(_armar)
        return resultado[0]

    def camioneta(self) -> UUID:
        """Una ubicación con toma, con 48 botellas, sin jornada."""
        resultado: list[UUID] = []

        def _armar(e: EntornoVenta) -> None:
            camioneta_id = crear_ubicacion_sql(
                e.sesion, e.org, nombre="Camioneta 2", requiere_toma=True
            )
            e.comprar(e.vino_id, 48, "1050", ubicacion_id=camioneta_id)
            resultado.append(camioneta_id)

        self.armar(_armar)
        return resultado[0]

    # --- comandos -------------------------------------------------------------------------

    def _sobre_de_anulacion(
        self, venta_id: UUID, operation_id: UUID | None, **opciones: Any
    ) -> SobreComando:
        e = self.entorno
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=VENTA_ANULAR,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            occurred_at=MOMENTO_ANULACION,
            secuencia=1,
            app_version="1.0.0",
            contenido=e.contenido_de_anulacion(venta_id, **opciones),
        )

    def anular_srv(self, venta_id: UUID, **opciones: Any) -> Callable[[Session], object]:
        """El handler de `VENTA_ANULAR` sobre la sesión del hilo, SIN confirmar (para
        `_encadenado`)."""
        sobre = self._sobre_de_anulacion(venta_id, None, **opciones)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)
        return lambda sesion: registrado.funcion(
            sobre, validado, sesion=sesion, reloj=RELOJ_ANULACION
        )

    def anular(self, sesion: Session, venta_id: UUID, **opciones: Any) -> Any:
        """El bus completo (reserva, handler, auditoría y `commit`) con conexión."""
        sobre = self._sobre_de_anulacion(venta_id, None, **opciones)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> Any:
            return registrado.funcion(
                sobre,
                validado,  # type: ignore[arg-type]
                sesion=sesion_protegida,  # type: ignore[arg-type]
                reloj=RELOJ_ANULACION,
            )

        return sync_service.procesar_comando(
            sesion,
            RELOJ_ANULACION,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def anular_cobranza_srv(self, venta_id: UUID) -> Callable[[Session], object]:
        """`COBRANZA_ANULAR` sobre la cobranza de la venta (origen `VENTA`), sin confirmar."""
        e = self.entorno
        ((cobranza_id,),) = self.leer(
            "SELECT id FROM cobranza WHERE organizacion_id = :o AND venta_id = :v", v=venta_id
        )
        return lambda sesion: cobranzas_service.anular_cobranza(
            self.org,
            sesion,
            RELOJ_ANULACION,
            cobranza_id=cobranza_id,
            motivo_id=e.motivo_anulacion_id,
            observacion=None,
            operation_id=uuid4(),
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            occurred_at=MOMENTO_ANULACION,
        )

    def desactivar_producto_srv(self) -> Callable[[Session], object]:
        e = self.entorno

        def _desactivar(sesion: Session) -> object:
            ((codigo, nombre, categoria, marca, proveedor, unidad, alicuota),) = sesion.execute(
                text(
                    "SELECT codigo, nombre, categoria_id, marca_id, proveedor_id, unidad_base, "
                    "alicuota_id FROM producto WHERE organizacion_id = :o AND id = :p"
                ),
                {"o": self.org, "p": e.vino_id},
            ).all()
            return catalogo_service.modificar_producto(
                self.org,
                sesion,
                RELOJ_ANULACION,
                producto_id=e.vino_id,
                codigo=codigo,
                nombre=nombre,
                categoria_id=categoria,
                marca_id=marca,
                proveedor_id=proveedor,
                unidad_base=unidad,
                alicuota_id=alicuota,
                activo=False,
                actor_id=None,
            )

        return _desactivar

    # --- lecturas confirmadas -------------------------------------------------------------

    def estado_de_la_venta(self, venta_id: UUID) -> str:
        ((estado,),) = self.leer(
            "SELECT estado FROM venta WHERE organizacion_id = :o AND id = :v", v=venta_id
        )
        return str(estado)

    def anulaciones(self) -> int:
        return self.cantidad_de("venta_anulacion")

    def producto_activo(self) -> bool:
        ((activo,),) = self.leer(
            "SELECT activo FROM producto WHERE organizacion_id = :o AND id = :p",
            p=self.entorno.vino_id,
        )
        return bool(activo)


def _nombres(errores: dict[int, BaseException]) -> list[str]:
    return sorted(type(error).__name__ for error in errores.values())


class TestDosAnulacionesDeLaMismaVenta:
    """INV-05, INV-01, TR-06, D10: la segunda anulación espera la venta `FOR UPDATE`, la relee
    `ANULADA` y responde `VENTA_YA_ANULADA`: una sola fila, un solo reingreso, el saldo acreditado
    una sola vez."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_inv05_una_gana_y_la_otra_responde_venta_ya_anulada(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        venta_id = escenario.vender()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.anular(sesion, venta_id),
            lambda sesion: escenario.anular(sesion, venta_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert _nombres(errores) == [VENTA_YA_ANULADA]
        assert escenario.anulaciones() == 1
        assert escenario.estado_de_la_venta(venta_id) == "ANULADA"
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'ANULACION_VENTA'") == 1
        assert escenario.cantidad_de("stock_movimiento", "tipo = 'ANULACION_VENTA'") == 1
        assert escenario.saldo_de_stock() == 48
        assert escenario.saldo_de_la_cuenta() == SALDO_INICIAL
        escenario.verificar_libros()

    def test_inv05_con_la_primera_sin_confirmar_la_segunda_espera_y_responde_venta_ya_anulada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        venta_id = escenario.vender()

        primero, segundo = _encadenado(
            database_url, escenario.anular_srv(venta_id), escenario.anular_srv(venta_id)
        )

        assert (primero, segundo) == (OK, VENTA_YA_ANULADA)
        assert escenario.anulaciones() == 1
        assert escenario.saldo_de_la_cuenta() == SALDO_INICIAL
        escenario.verificar_libros()


class TestAnulacionConDevolucionFrenteAAnularSuCobranza:
    """INV-13, INV-05, VTA-22, D10: la cobranza de una venta se toma `FOR UPDATE` antes que el
    saldo del cliente en los dos caminos. Anulada con la venta, `COBRANZA_ANULAR` la relee
    `ANULADA` (`COBRANZA_YA_ANULADA`); y si `COBRANZA_ANULAR` llegara primero se rechaza por ser de
    una venta: en ningún orden la cobranza se anula dos veces ni se devuelve dos veces."""

    def test_vta22_anulacion_primero_la_anulacion_de_la_cobranza_espera_y_responde_ya_anulada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        # Escenario: "Concurrencia con la cobranza" (cobranzas/anulacion-de-cobranzas). La spec
        # dice `COBRANZA_DE_VENTA`; con la cobranza ya `ANULADA` la regla de estado va primera
        # (`validar_cobranza_a_anular`), así que responde `COBRANZA_YA_ANULADA` (ver informe).
        escenario = _Escenario(database_url)
        venta_id = escenario.vender(con_cobro=True)

        primero, segundo = _encadenado(
            database_url,
            escenario.anular_srv(venta_id, devuelve_dinero=True),
            escenario.anular_cobranza_srv(venta_id),
        )

        assert (primero, segundo) == (OK, COBRANZA_YA_ANULADA)
        assert escenario.cantidad_de("cobranza_anulacion") == 1
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'ANULACION_COBRANZA'") == 1
        assert escenario.saldo_de_la_cuenta() == SALDO_INICIAL
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_vta22_en_carrera_libre_la_cobranza_se_anula_una_sola_vez(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        venta_id = escenario.vender(con_cobro=True)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.anular(sesion, venta_id, devuelve_dinero=True),
            escenario.anular_cobranza_srv(venta_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert 0 in resultados, f"{resultados}, errores={errores}"
        assert 1 not in resultados
        assert _nombres(errores) in ([COBRANZA_YA_ANULADA], ["CobranzaDeVentaError"])
        assert escenario.cantidad_de("cobranza_anulacion") == 1
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'ANULACION_COBRANZA'") == 1
        assert escenario.cantidad_de("cobranza", "estado = 'ANULADA'") == 1
        assert escenario.saldo_de_la_cuenta() == SALDO_INICIAL
        escenario.verificar_libros()


class TestAnulacionYVentaDelMismoProductoAlMismoCliente:
    """INV-12, INV-13, D10: la anulación toma el saldo del cliente (nivel 1) y luego el producto,
    igual que la venta: se serializan sin interbloqueo y el stock y el saldo son los de aplicar
    ambas."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_inv12_inv13_las_dos_se_aplican_con_stock_y_saldo_exactos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        # Escenario: "Anulación y venta del mismo producto a la vez" (ventas/anulacion-de-venta)
        escenario = _Escenario(database_url)
        e = escenario.entorno
        venta_id = escenario.vender()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.anular(sesion, venta_id),
            escenario.venta_srv(e.contenido(e.linea(cantidad=20))),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert escenario.estado_de_la_venta(venta_id) == "ANULADA"
        assert escenario.cantidad_de("venta") == 2
        assert escenario.cantidad_de("stock_movimiento", "tipo = 'VENTA'") == 2
        assert escenario.cantidad_de("stock_movimiento", "tipo = 'ANULACION_VENTA'") == 1
        # 48 - 15 (venta original) + 15 (anulación) - 20 (venta nueva)
        assert escenario.saldo_de_stock() == 28
        # 150000,00 + 31250,00 - 31250,00 + 41666,67 (20 botellas)
        assert escenario.saldo_de_la_cuenta() == Decimal("191666.67")
        escenario.verificar_libros()

    def test_inv13_con_la_venta_primero_la_anulacion_espera_y_se_aplica_despues(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        e = escenario.entorno
        venta_id = escenario.vender()

        primero, segundo = _encadenado(
            database_url,
            escenario.venta_srv(e.contenido(e.linea(cantidad=20))),
            escenario.anular_srv(venta_id),
        )

        assert (primero, segundo) == (OK, OK)
        assert escenario.saldo_de_stock() == 28
        assert escenario.saldo_de_la_cuenta() == Decimal("191666.67")
        escenario.verificar_libros()


class TestAnulacionYDesactivacionDelProducto:
    """CAT-05, ADR-044, D7, INV-12: un producto solo se desactiva sin stock. La venta se llevó las
    48 botellas: con la desactivación primero, la anulación reingresa igual a un producto inactivo
    (la exención de `ANULACION_VENTA`); con la anulación primero, la desactivación espera, ve las 48
    botellas que volvieron y se rechaza (`PRODUCTO_CON_STOCK`). En ningún orden falla la
    anulación."""

    PRODUCTO_CON_STOCK = "ProductoConStockError"

    def _vender_todo(self, escenario: _Escenario) -> UUID:
        e = escenario.entorno
        return escenario.vender(e.linea(cantidad=48))

    def test_cat05_desactivacion_primero_la_anulacion_reingresa_igual_a_un_producto_inactivo(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        venta_id = self._vender_todo(escenario)

        primero, segundo = _encadenado(
            database_url, escenario.desactivar_producto_srv(), escenario.anular_srv(venta_id)
        )

        assert (primero, segundo) == (OK, OK)
        assert escenario.estado_de_la_venta(venta_id) == "ANULADA"
        assert escenario.saldo_de_stock() == 48
        assert not escenario.producto_activo()
        assert escenario.saldo_de_la_cuenta() == SALDO_INICIAL
        escenario.verificar_libros()

    def test_cat05_anulacion_primero_la_desactivacion_espera_y_se_rechaza_porque_hay_stock(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        venta_id = self._vender_todo(escenario)

        primero, segundo = _encadenado(
            database_url, escenario.anular_srv(venta_id), escenario.desactivar_producto_srv()
        )

        assert (primero, segundo) == (OK, self.PRODUCTO_CON_STOCK)
        assert escenario.estado_de_la_venta(venta_id) == "ANULADA"
        assert escenario.saldo_de_stock() == 48
        assert escenario.producto_activo()
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_cat05_en_carrera_libre_la_anulacion_siempre_se_aplica(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        venta_id = self._vender_todo(escenario)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.anular(sesion, venta_id),
            escenario.desactivar_producto_srv(),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert 0 in resultados, f"{resultados}, errores={errores}"
        assert estados_validos(errores, self.PRODUCTO_CON_STOCK)
        assert escenario.estado_de_la_venta(venta_id) == "ANULADA"
        assert escenario.saldo_de_stock() == 48
        # O la desactivación llegó con el producto sin stock y el reingreso lo encontró inactivo,
        # o llegó después y vio las 48 botellas: nunca un producto inactivo con stock sin explicar.
        assert escenario.producto_activo() == (1 in errores)
        escenario.verificar_libros()


def estados_validos(errores: dict[int, BaseException], permitido: str) -> bool:
    """Solo hay errores del hilo `1` y es el permitido."""
    nombres = {type(error).__name__ for error in errores.values()}
    return set(errores) <= {1} and nombres <= {permitido}


class TestAnulacionFrenteALaAperturaDeJornadaDeSuUbicacion:
    """STK-09, INV-16, RUT-04, D6: la ubicación con toma se lee con su jornada en el último nivel
    del orden. Quien anula sin `LIBERAR_UBICACION` o termina antes que la apertura, o ve la
    ubicación tomada (`UBICACION_TOMADA`) y no deja ningún efecto."""

    def _con_pedro(self, escenario: _Escenario) -> tuple[UUID, UUID, UUID, UUID]:
        camioneta_id = escenario.camioneta()
        venta_id = escenario.vender(ubicacion_id=str(camioneta_id))
        pedro, dispositivo_de_pedro = escenario.otro_vendedor(frozenset({"ABRIR_JORNADA"}))
        return camioneta_id, venta_id, pedro, dispositivo_de_pedro

    def test_stk09_anulacion_primero_la_apertura_espera_y_se_abre(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id, venta_id, pedro, dispositivo_de_pedro = self._con_pedro(escenario)

        primero, segundo = _encadenado(
            database_url,
            escenario.anular_srv(venta_id),
            escenario.abrir_jornada_srv(pedro, dispositivo_de_pedro, camioneta_id),
        )

        assert (primero, segundo) == (OK, OK)
        assert escenario.estado_de_la_venta(venta_id) == "ANULADA"
        assert escenario.saldo_de_stock(camioneta_id) == 48
        assert escenario.cantidad_de("jornada", "estado = 'ABIERTA'") == 1
        assert escenario.cantidad_de("venta_anulacion", "jornada_id IS NOT NULL") == 0
        escenario.verificar_libros()

    def test_stk09_apertura_primero_la_anulacion_responde_ubicacion_tomada_sin_efectos(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id, venta_id, pedro, dispositivo_de_pedro = self._con_pedro(escenario)

        primero, segundo = _encadenado(
            database_url,
            escenario.abrir_jornada_srv(pedro, dispositivo_de_pedro, camioneta_id),
            escenario.anular_srv(venta_id),
        )

        assert (primero, segundo) == (OK, UBICACION_TOMADA)
        assert escenario.estado_de_la_venta(venta_id) == "CONFIRMADA"
        assert escenario.anulaciones() == 0
        assert escenario.saldo_de_stock(camioneta_id) == 33
        assert escenario.saldo_de_la_cuenta() == SALDO_INICIAL + VENTA_DE_15_BOTELLAS
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_stk09_en_carrera_libre_el_resultado_es_uno_de_los_dos_ordenes_validos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id, venta_id, pedro, dispositivo_de_pedro = self._con_pedro(escenario)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.anular(sesion, venta_id),
            escenario.abrir_jornada_srv(pedro, dispositivo_de_pedro, camioneta_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert 1 in resultados, f"{resultados}, errores={errores}"
        if 0 in resultados:
            assert escenario.estado_de_la_venta(venta_id) == "ANULADA"
            assert escenario.saldo_de_stock(camioneta_id) == 48
            assert escenario.saldo_de_la_cuenta() == SALDO_INICIAL
        else:
            assert _nombres(errores) == [UBICACION_TOMADA]
            assert escenario.estado_de_la_venta(venta_id) == "CONFIRMADA"
            assert escenario.anulaciones() == 0
            assert escenario.saldo_de_stock(camioneta_id) == 33
            assert escenario.saldo_de_la_cuenta() == SALDO_INICIAL + VENTA_DE_15_BOTELLAS
        assert escenario.cantidad_de("jornada", "estado = 'ABIERTA'") == 1
        escenario.verificar_libros()
