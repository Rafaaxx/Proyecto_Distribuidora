"""Change 18a, tarea 14.1 (`design.md` D17, D4, D18): concurrencia real de `VENTA_CONFIRMAR`
contra PostgreSQL real (Testcontainers, `READ COMMITTED`, `02` §7.1), con el arnés de
`test_cobranzas_concurrencia.py`: cada hilo tiene su propia conexión/sesión, confirma su propia
transacción y arranca junto a los otros en una `threading.Barrier`. Nunca hay rollback externo
(`CLAUDE.md` §4) y la limpieza se hace al final con `TRUNCATE`.

Los escenarios cuyo resultado depende del orden de llegada se prueban además en los DOS órdenes de
forma determinista con `_encadenado` (la primera transacción deja sus bloqueos tomados y SIN
confirmar; se observa a la segunda esperando en `pg_stat_activity`; recién entonces confirma la
primera). Para sostener una transacción sin confirmar, la "primera" corre el handler de
`VENTA_CONFIRMAR` directamente sobre la sesión del hilo (los handlers no confirman, `CLAUDE.md`
§4): son los mismos bloqueos del orden de D17, sin la reserva ni la auditoría del bus. Las carreras
libres y el doble envío usan el bus completo (`sync_service.procesar_comando`). No hay `sleep` para
"dar tiempo".

- INV-12, INV-13: dos ventas al mismo cliente y producto dejan stock y saldo exactos; con stock
  que alcanza para una sola, una vende y la otra responde `STOCK_INSUFICIENTE`;
- INV-12, INV-10, VTA-05: venta y compra del mismo producto, en los dos órdenes;
- INV-12, INV-15: venta y transferencia desde la misma ubicación;
- INV-18: venta y `PRESENTACION_MODIFICAR` de la presentación vendida;
- PRC-01, D14: venta y desactivación de la lista usada;
- VTA-06, INV-01, D4: dos ventas con el mismo número, una sola (la carrera real de la
  numeración, con clientes y productos distintos para que nada las serialice antes del insert);
- STK-09, INV-16, RUT-04: venta y apertura o liberación de la jornada de su ubicación;
- SYN-05, RUT-09, STK-09: venta sin conexión frente a la liberación y a la nueva toma de la
  ubicación de su jornada (`JORNADA_LIBERADA`, `UBICACION_TOMADA_AL_SINCRONIZAR`);
- INV-06: el mismo comando enviado dos veces a la vez tiene un solo efecto.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import (
    MOMENTO_VENTA,
    PERMISOS_DE_SUPERVISOR,
    PERMISOS_DE_VENTA,
    RELOJ_VENTA,
    VENTA_CONFIRMAR,
    EntornoVenta,
)

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.db import crear_engine
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import UnidadesCongeladasError
from app.modules.precios import service as precios_service
from app.modules.precios.domain.errores import ListaInactivaError
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import StockInsuficienteError, UbicacionTomadaError
from app.modules.stock.domain.movimientos import LineaDeMovimiento
from app.modules.stock.service import LineaDeTransferencia
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote
from app.modules.ventas.domain.errores import (
    JornadaAjenaError,
    NumeroDuplicadoError,
    PrecioDifiereError,
    UbicacionRequeridaError,
)
from tests.concurrency.test_pagos_proveedor_concurrencia import _en_paralelo, _sesion_independiente
from tests.concurrency.test_transferencias_ajustes_concurrencia import OK, _encadenado
from tests.integration.cuentas_corrientes_utiles import crear_cliente, crear_usuario_y_dispositivo
from tests.integration.stock_utiles import crear_ubicacion_sql

REPETICIONES = 5
STOCK_INSUFICIENTE = StockInsuficienteError.__name__
NUMERO_DUPLICADO = NumeroDuplicadoError.__name__
UBICACION_TOMADA = UbicacionTomadaError.__name__
LISTA_INACTIVA = ListaInactivaError.__name__
PRECIO_DIFIERE = PrecioDifiereError.__name__
UNIDADES_CONGELADAS = UnidadesCongeladasError.__name__
SIN_UBICACION_NI_JORNADA = {UbicacionRequeridaError.__name__, JornadaAjenaError.__name__}


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


class _Escenario:
    """La organización de `EntornoVenta` (Kiosco La Esquina con saldo de `150000.00`, Vino A con
    48 botellas a $1.050 en "Depósito central", lista General con Vino A a $12.500 la caja x6),
    confirmada en su propia sesión, más lo que pide cada escenario."""

    def __init__(
        self,
        database_url: str,
        *,
        permisos: frozenset[str] = PERMISOS_DE_VENTA,
        **opciones: Any,
    ) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.entorno = EntornoVenta(sesion, permisos=permisos, **opciones)
        finally:
            sesion.close()
        self.org = self.entorno.org

    # --- armado (cada paso confirma en su propia sesión) ---------------------------------

    def armar(self, paso: Callable[[EntornoVenta], object]) -> None:
        """Corre `paso` con la sesión del entorno y confirma."""
        sesion = _sesion_independiente(self.database_url)
        self.entorno.sesion = sesion
        try:
            paso(self.entorno)
            sesion.commit()
        finally:
            sesion.close()

    def cliente_nuevo(self, nombre: str) -> UUID:
        sesion = _sesion_independiente(self.database_url)
        try:
            cliente_id = crear_cliente(sesion, self.org, nombre=nombre)
            sesion.commit()
            return cliente_id
        finally:
            sesion.close()

    def otro_vendedor(self, permisos: frozenset[str]) -> tuple[UUID, UUID]:
        sesion = _sesion_independiente(self.database_url)
        try:
            ids = crear_usuario_y_dispositivo(sesion, self.org, permisos=permisos)
            sesion.commit()
            return ids
        finally:
            sesion.close()

    # --- comandos -------------------------------------------------------------------------

    def sobre(
        self,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
        modo: str = "ONLINE",
        jornada_id: UUID | None = None,
    ) -> SobreComando:
        e = self.entorno
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=VENTA_CONFIRMAR,
            version=1,
            modo=modo,
            organizacion_id=self.org,
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            occurred_at=MOMENTO_VENTA,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
            jornada_id=jornada_id,
        )

    def venta_srv(
        self,
        contenido: dict[str, Any],
        *,
        modo: str = "ONLINE",
        jornada_id: UUID | None = None,
        observaciones: list[str] | None = None,
    ) -> Callable[[Session], object]:
        """El handler de `VENTA_CONFIRMAR` sobre la sesión del hilo, SIN confirmar (para
        `_encadenado` y `_en_paralelo`, que confirman o revierten)."""
        sobre = self.sobre(contenido, modo=modo, jornada_id=jornada_id)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _vender(sesion: Session) -> object:
            resultado = registrado.funcion(sobre, validado, sesion=sesion, reloj=RELOJ_VENTA)
            if observaciones is not None and isinstance(resultado, tuple) and len(resultado) > 3:
                observaciones.extend(o.codigo for o in resultado[3])
            return resultado

        return _vender

    def enviar(
        self,
        sesion: Session,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
        jornada_id: UUID | None = None,
    ) -> Any:
        """El bus completo (reserva, handler, auditoría y `commit`) con conexión."""
        sobre = self.sobre(contenido, operation_id=operation_id, jornada_id=jornada_id)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> Any:
            return registrado.funcion(
                sobre,
                validado,  # type: ignore[arg-type]
                sesion=sesion_protegida,  # type: ignore[arg-type]
                reloj=RELOJ_VENTA,
            )

        return sync_service.procesar_comando(
            sesion,
            RELOJ_VENTA,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def enviar_en_lote(
        self, sesion: Session, contenido: dict[str, Any], jornada_id: UUID
    ) -> sync_service.ResultadoItemLote:
        """El lote de sincronización (`OFFLINE`), que confirma por comando."""
        e = self.entorno
        item = ItemLote(
            operation_id=uuid4(),
            tipo=VENTA_CONFIRMAR,
            version=1,
            modo="OFFLINE",
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            occurred_at=MOMENTO_VENTA,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
            jornada_id=jornada_id,
        )
        (resultado,) = sync_service.procesar_lote(
            sesion,
            RELOJ_VENTA,
            organizacion_id=self.org,
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            items=[item],
        )
        return resultado

    def comprar_srv(self, cantidad: int, costo: str) -> Callable[[Session], object]:
        e = self.entorno
        return lambda sesion: stock_service.registrar_movimientos(
            self.org,
            sesion,
            RELOJ_VENTA,
            lineas=[
                LineaDeMovimiento(
                    producto_id=e.vino_id,
                    ubicacion_id=e.deposito_id,
                    cantidad_base=cantidad,
                    tipo="COMPRA",
                    costo_unitario=costo,
                    origen_tipo="COMPRA",
                    origen_id=uuid4(),
                )
            ],
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO_VENTA,
        )

    def transferir_srv(self, destino_id: UUID, cantidad: int) -> Callable[[Session], object]:
        e = self.entorno
        return lambda sesion: stock_service.transferir(
            self.org,
            sesion,
            RELOJ_VENTA,
            ubicacion_origen_id=e.deposito_id,
            ubicacion_destino_id=destino_id,
            lineas=[LineaDeTransferencia(producto_id=e.vino_id, cantidad_base=cantidad)],
            observacion=None,
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO_VENTA,
        )

    def modificar_botella_srv(self, unidades_base: int) -> Callable[[Session], object]:
        e = self.entorno
        return lambda sesion: catalogo_service.modificar_presentacion(
            self.org,
            sesion,
            RELOJ_VENTA,
            presentacion_id=e.botella_id,
            nombre="Botella",
            unidades_base=unidades_base,
            usar_en_venta=True,
            usar_en_compra=True,
            activo=True,
            actor_id=e.usuario_id,
        )

    def desactivar_lista_srv(self, lista_id: UUID) -> Callable[[Session], object]:
        e = self.entorno
        return lambda sesion: precios_service.modificar_lista(
            self.org,
            sesion,
            RELOJ_VENTA,
            lista_id=lista_id,
            nombre="Mayorista",
            redondeo_multiplo="100",
            redondeo_direccion="ARRIBA",
            activo=False,
            actor_id=e.usuario_id,
        )

    def abrir_jornada_srv(
        self, usuario_id: UUID, dispositivo_id: UUID, ubicacion_id: UUID
    ) -> Callable[[Session], object]:
        return lambda sesion: stock_service.abrir_jornada(
            self.org,
            sesion,
            RELOJ_VENTA,
            ubicacion_id=ubicacion_id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO_VENTA,
        )

    def liberar_srv(self, jornada_id: UUID, motivo_id: UUID) -> Callable[[Session], object]:
        return lambda sesion: stock_service.liberar_jornada(
            self.org,
            sesion,
            jornada_id=jornada_id,
            usuario_id=self.entorno.usuario_id,
            motivo_id=motivo_id,
            observacion=None,
            occurred_at=MOMENTO_VENTA,
        )

    # --- lecturas confirmadas ------------------------------------------------------------

    def leer(self, consulta: str, **parametros: object) -> list[tuple[Any, ...]]:
        sesion = _sesion_independiente(self.database_url)
        try:
            filas = sesion.execute(text(consulta), {"o": self.org, **parametros}).all()
            return [tuple(fila) for fila in filas]
        finally:
            sesion.close()

    def cantidad_de(self, tabla: str, donde: str = "true") -> int:
        ((cantidad,),) = self.leer(
            f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o AND {donde}"  # noqa: S608
        )
        assert isinstance(cantidad, int)
        return cantidad

    def saldo_de_stock(self, ubicacion_id: UUID | None = None) -> int:
        ((saldo,),) = self.leer(
            "SELECT COALESCE(SUM(cantidad_base), 0) FROM stock_saldo WHERE organizacion_id = :o "
            "AND producto_id = :p AND ubicacion_id = :u",
            p=self.entorno.vino_id,
            u=ubicacion_id or self.entorno.deposito_id,
        )
        return int(saldo)

    def saldo_de_la_cuenta(self, cliente_id: UUID | None = None) -> Decimal:
        ((saldo,),) = self.leer(
            "SELECT saldo FROM saldo_cuenta WHERE organizacion_id = :o "
            "AND cuenta_tipo = 'CLIENTE' AND entidad_id = :e",
            e=cliente_id or self.entorno.cliente_id,
        )
        assert isinstance(saldo, Decimal)
        return saldo

    def suma_del_libro(self, cliente_id: UUID | None = None) -> Decimal:
        ((saldo,),) = self.leer(
            "SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), 0) "
            "FROM cuenta_movimiento WHERE organizacion_id = :o "
            "AND cuenta_tipo = 'CLIENTE' AND entidad_id = :e",
            e=cliente_id or self.entorno.cliente_id,
        )
        return Decimal(saldo)

    def costo_y_stock_total(self) -> tuple[Decimal, int]:
        ((promedio, total),) = self.leer(
            "SELECT costo_promedio, stock_total FROM costo_producto "
            "WHERE organizacion_id = :o AND producto_id = :p",
            p=self.entorno.vino_id,
        )
        return Decimal(promedio), int(total)

    def verificar_libros(self, *clientes: UUID) -> None:
        """INV-12 (saldos = suma de movimientos, stock total = suma de saldos) e INV-13 (saldo de
        cada cuenta = suma de su libro), comprobados con SQL sobre lo confirmado."""
        sesion = _sesion_independiente(self.database_url)
        try:
            assert stock_service.verificar_consistencia(self.org, sesion) == []
        finally:
            sesion.close()
        for cliente_id in clientes or (self.entorno.cliente_id,):
            assert self.saldo_de_la_cuenta(cliente_id) == self.suma_del_libro(cliente_id)
        ((total, suma),) = self.leer(
            "SELECT (SELECT stock_total FROM costo_producto WHERE organizacion_id = :o "
            "AND producto_id = :p), (SELECT COALESCE(SUM(cantidad_base), 0) FROM stock_saldo "
            "WHERE organizacion_id = :o AND producto_id = :p)",
            p=self.entorno.vino_id,
        )
        assert total == suma

    def codigos_de_observacion(self) -> list[str]:
        return sorted(
            str(fila[0])
            for fila in self.leer("SELECT codigo FROM observacion WHERE organizacion_id = :o")
        )


def _nombres(errores: dict[int, BaseException]) -> list[str]:
    return sorted(type(error).__name__ for error in errores.values())


class TestDosVentasAlMismoClienteYProducto:
    """INV-12, INV-13, D17: dos ventas al mismo cliente y producto se serializan por el saldo del
    cliente; el stock y el saldo son los de aplicar ambas."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_inv12_inv13_las_dos_se_confirman_con_stock_y_saldo_exactos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        e = escenario.entorno
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(e.contenido()),
            escenario.venta_srv(e.contenido(e.linea(cantidad=20))),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert escenario.cantidad_de("venta") == 2
        assert escenario.cantidad_de("stock_movimiento", "tipo = 'VENTA'") == 2
        assert escenario.saldo_de_stock() == 48 - 15 - 20
        # 150000,00 + 31250,00 (15 botellas) + 41666,67 (20 botellas)
        assert escenario.saldo_de_la_cuenta() == Decimal("222916.67")
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'VENTA'") == 2
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_inv12_con_stock_para_una_sola_la_otra_responde_stock_insuficiente(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        e = escenario.entorno
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(e.contenido(e.linea(cantidad=30))),
            escenario.venta_srv(e.contenido(e.linea(cantidad=30))),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert _nombres(errores) == [STOCK_INSUFICIENTE]
        assert escenario.cantidad_de("venta") == 1
        assert escenario.saldo_de_stock() == 18
        assert escenario.saldo_de_la_cuenta() == Decimal("212500.00")
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_inv12_dos_clientes_distintos_del_mismo_producto_tambien_quedan_exactos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        """Sin saldo en común las dos esperan en el producto y el costo (niveles 2 y 3)."""
        escenario = _Escenario(database_url)
        e = escenario.entorno
        otro_id = escenario.cliente_nuevo("Almacén Don Pedro")
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(e.contenido()),
            escenario.venta_srv(e.contenido(cliente_id=str(otro_id))),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert escenario.saldo_de_stock() == 18
        assert escenario.saldo_de_la_cuenta(otro_id) == Decimal("31250.00")
        assert escenario.saldo_de_la_cuenta() == Decimal("181250.00")
        escenario.verificar_libros(e.cliente_id, otro_id)


class TestVentaYCompraDelMismoProducto:
    """INV-12, INV-10, VTA-05, D17: el costo de la línea es el promedio vigente cuando la venta
    toma el costo; sale distinto según qué transacción llega primera, pero el stock y el promedio
    finales son los de aplicar ambas en ese orden."""

    PROMEDIO_VENTA_PRIMERO = Decimal("1239.473684")  # (33 x 1050 + 24 x 1500) / 57
    PROMEDIO_COMPRA_PRIMERO = Decimal("1200.000000")  # (48 x 1050 + 24 x 1500) / 72

    def _costo_de_la_venta(self, escenario: _Escenario) -> tuple[Decimal, Decimal]:
        ((unitario, total),) = escenario.leer(
            "SELECT costo_unitario, costo_total FROM venta_linea WHERE organizacion_id = :o"
        )
        return Decimal(unitario), Decimal(total)

    def test_venta_primero_la_compra_espera_y_la_venta_cuesta_el_promedio_anterior(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)

        primero, segundo = _encadenado(
            database_url,
            escenario.venta_srv(escenario.entorno.contenido()),
            escenario.comprar_srv(24, "1500"),
        )

        assert (primero, segundo) == (OK, OK)
        assert self._costo_de_la_venta(escenario) == (Decimal("1050.000000"), Decimal("15750.00"))
        assert escenario.costo_y_stock_total() == (self.PROMEDIO_VENTA_PRIMERO, 57)
        escenario.verificar_libros()

    def test_compra_primero_la_venta_espera_y_cuesta_el_promedio_nuevo(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)

        primero, segundo = _encadenado(
            database_url,
            escenario.comprar_srv(24, "1500"),
            escenario.venta_srv(escenario.entorno.contenido()),
        )

        assert (primero, segundo) == (OK, OK)
        assert self._costo_de_la_venta(escenario) == (Decimal("1200.000000"), Decimal("18000.00"))
        assert escenario.costo_y_stock_total() == (self.PROMEDIO_COMPRA_PRIMERO, 57)
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_en_carrera_libre_el_resultado_es_uno_de_los_dos_ordenes_validos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(escenario.entorno.contenido()),
            escenario.comprar_srv(24, "1500"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        costo = self._costo_de_la_venta(escenario)
        if costo[0] == Decimal("1050.000000"):
            assert escenario.costo_y_stock_total() == (self.PROMEDIO_VENTA_PRIMERO, 57)
        else:
            assert costo == (Decimal("1200.000000"), Decimal("18000.00"))
            assert escenario.costo_y_stock_total() == (self.PROMEDIO_COMPRA_PRIMERO, 57)
        escenario.verificar_libros()


class TestVentaYTransferenciaDesdeLaMismaUbicacion:
    """INV-12, INV-15, D17: venta y transferencia toman los mismos saldos en el mismo orden global
    (producto, luego ubicación); no se esperan en círculo y nunca dejan stock negativo."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_las_dos_se_aplican_cuando_el_stock_alcanza(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        sucursal_id = self._sucursal(escenario)
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(escenario.entorno.contenido()),
            escenario.transferir_srv(sucursal_id, 20),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert escenario.saldo_de_stock() == 13
        assert escenario.saldo_de_stock(sucursal_id) == 20
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_con_stock_para_una_sola_la_otra_responde_stock_insuficiente(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        """48 botellas: la venta de 15 deja 33 (no alcanzan 40) y la transferencia de 40 deja 8
        (no alcanzan 15); gane quien gane, la otra se rechaza y nada queda en negativo."""
        escenario = _Escenario(database_url)
        sucursal_id = self._sucursal(escenario)
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(escenario.entorno.contenido()),
            escenario.transferir_srv(sucursal_id, 40),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert _nombres(errores) == [STOCK_INSUFICIENTE]
        if escenario.cantidad_de("venta") == 1:
            assert (escenario.saldo_de_stock(), escenario.saldo_de_stock(sucursal_id)) == (33, 0)
        else:
            assert (escenario.saldo_de_stock(), escenario.saldo_de_stock(sucursal_id)) == (8, 40)
        escenario.verificar_libros()

    def _sucursal(self, escenario: _Escenario) -> UUID:
        resultado: list[UUID] = []
        escenario.armar(
            lambda e: resultado.append(crear_ubicacion_sql(e.sesion, e.org, nombre="Sucursal"))
        )
        return resultado[0]


class TestVentaYModificacionDeLaPresentacion:
    """INV-18, D17: `PRESENTACION_MODIFICAR` toma el producto `FOR UPDATE` y la venta lo toma
    `FOR SHARE` antes de leer las unidades; o la venta congela las unidades viejas y la
    modificación se rechaza, o la modificación gana y la venta ve las unidades nuevas."""

    def test_venta_primero_la_modificacion_espera_y_se_rechaza_por_unidades_congeladas(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)

        primero, segundo = _encadenado(
            database_url,
            escenario.venta_srv(escenario.entorno.contenido()),
            escenario.modificar_botella_srv(2),
        )

        assert (primero, segundo) == (OK, UNIDADES_CONGELADAS)
        assert self._unidades_de_la_botella(escenario) == 1
        assert escenario.cantidad_de("venta_linea", "unidades_presentacion = 1") == 1

    def test_modificacion_primero_la_venta_espera_y_ve_las_unidades_nuevas(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)

        primero, segundo = _encadenado(
            database_url,
            escenario.modificar_botella_srv(2),
            escenario.venta_srv(escenario.entorno.contenido()),
        )

        assert (primero, segundo) == (OK, PRECIO_DIFIERE)
        assert self._unidades_de_la_botella(escenario) == 2
        assert escenario.cantidad_de("venta") == 0
        assert escenario.saldo_de_stock() == 48
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_en_carrera_libre_nunca_hay_una_linea_con_unidades_que_la_presentacion_ya_no_tiene(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        # Escenario: "Venta y modificación simultáneas"
        escenario = _Escenario(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(escenario.entorno.contenido()),
            escenario.modificar_botella_srv(2),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert _nombres(errores) in ([UNIDADES_CONGELADAS], [PRECIO_DIFIERE])
        if escenario.cantidad_de("venta") == 1:
            assert self._unidades_de_la_botella(escenario) == 1
        else:
            assert self._unidades_de_la_botella(escenario) == 2
        assert (
            escenario.cantidad_de(
                "venta_linea",
                "unidades_presentacion <> (SELECT unidades_base FROM presentacion p WHERE "
                "p.organizacion_id = venta_linea.organizacion_id "
                "AND p.id = venta_linea.presentacion_id)",
            )
            == 0
        )

    def _unidades_de_la_botella(self, escenario: _Escenario) -> int:
        ((unidades,),) = escenario.leer(
            "SELECT unidades_base FROM presentacion WHERE organizacion_id = :o AND id = :p",
            p=escenario.entorno.botella_id,
        )
        return int(unidades)


class TestVentaYDesactivacionDeLaLista:
    """PRC-01, D14, D17: la venta lee la lista `FOR SHARE` y su desactivación la toma `FOR
    UPDATE`; una lista nunca queda inactiva con una venta nueva que la use."""

    def _mayorista(self, escenario: _Escenario) -> tuple[UUID, UUID]:
        ids: list[UUID] = []

        def _armar(e: EntornoVenta) -> None:
            lista_id = e.crear_lista("Mayorista")
            version_id = e.crear_version(
                lista_id, 1, MOMENTO_VENTA.replace(day=1), precio_vino="12500.00"
            )
            ids.extend([lista_id, version_id])

        escenario.armar(_armar)
        return ids[0], ids[1]

    def _contenido(self, escenario: _Escenario, lista_id: UUID, version_id: UUID) -> dict[str, Any]:
        e = escenario.entorno
        return e.contenido(
            e.linea(version_id=version_id),
            lista_id=str(lista_id),
            motivo_lista_id=str(e.motivo_lista_id),
        )

    def test_venta_primero_la_desactivacion_espera_y_se_aplica_despues(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url, permisos=PERMISOS_DE_SUPERVISOR)
        lista_id, version_id = self._mayorista(escenario)

        primero, segundo = _encadenado(
            database_url,
            escenario.venta_srv(self._contenido(escenario, lista_id, version_id)),
            escenario.desactivar_lista_srv(lista_id),
        )

        assert (primero, segundo) == (OK, OK)
        assert escenario.cantidad_de("venta", f"lista_id = '{lista_id}'") == 1
        assert escenario.cantidad_de("lista_precio", f"id = '{lista_id}' AND NOT activo") == 1
        escenario.verificar_libros()

    def test_desactivacion_primero_la_venta_espera_y_responde_lista_inactiva(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url, permisos=PERMISOS_DE_SUPERVISOR)
        lista_id, version_id = self._mayorista(escenario)

        primero, segundo = _encadenado(
            database_url,
            escenario.desactivar_lista_srv(lista_id),
            escenario.venta_srv(self._contenido(escenario, lista_id, version_id)),
        )

        assert (primero, segundo) == (OK, LISTA_INACTIVA)
        assert escenario.cantidad_de("venta") == 0
        assert escenario.saldo_de_stock() == 48
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_en_carrera_libre_el_resultado_es_uno_de_los_dos_ordenes_validos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url, permisos=PERMISOS_DE_SUPERVISOR)
        lista_id, version_id = self._mayorista(escenario)
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(self._contenido(escenario, lista_id, version_id)),
            escenario.desactivar_lista_srv(lista_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert 1 in resultados, f"{resultados}, errores={errores}"
        if 0 in resultados:
            assert not errores
            assert escenario.cantidad_de("venta") == 1
        else:
            assert _nombres(errores) == [LISTA_INACTIVA]
            assert escenario.cantidad_de("venta") == 0
        escenario.verificar_libros()


class TestDosVentasConElMismoNumero:
    """VTA-06, INV-01, D4: el número es único en la organización. Con clientes y productos
    distintos nada serializa a las dos antes del insert de la cabecera: es el índice
    `ux_venta__numero` quien decide, y la perdedora revierte TODO (stock, saldo, correlativo)."""

    def _segundo_producto(self, escenario: _Escenario) -> tuple[UUID, UUID]:
        ids: list[UUID] = []

        def _armar(e: EntornoVenta) -> None:
            producto_id, caja_id = e.crear_producto("Cerveza B", unidades_caja=12)
            e.poner_precio(e.version_id, producto_id, "24000.00", 12)
            e.comprar(producto_id, 24, "700")
            ids.extend([producto_id, caja_id])

        escenario.armar(_armar)
        return ids[0], ids[1]

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_vta06_inv01_solo_una_se_confirma_y_la_otra_no_deja_ningun_efecto(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        # Escenario: "Dos ventas simultáneas con el mismo número"
        escenario = _Escenario(database_url)
        e = escenario.entorno
        cerveza_id, caja_id = self._segundo_producto(escenario)
        otro_id = escenario.cliente_nuevo("Almacén Don Pedro")
        numero = e.siguiente_numero()
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(e.contenido(numero=numero)),
            escenario.venta_srv(
                e.contenido(
                    e.linea(
                        cerveza_id,
                        caja_id,
                        2,
                        unidades_presentacion=12,
                        precio="24000.00",
                        unidades_referencia=12,
                    ),
                    numero=numero,
                    cliente_id=str(otro_id),
                )
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert _nombres(errores) == [NUMERO_DUPLICADO]
        assert escenario.cantidad_de("venta") == 1
        assert escenario.cantidad_de("venta", f"numero = '{numero}'") == 1
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'VENTA'") == 1
        assert escenario.cantidad_de("stock_movimiento", "tipo = 'VENTA'") == 1
        # La perdedora no dejó stock ni saldo: la cuenta del que no vendió sigue en cero.
        if resultados.get(0) is not None:
            assert escenario.saldo_de_stock() == 33
            assert escenario.cantidad_de("cuenta_movimiento", f"entidad_id = '{otro_id}'") == 0
        else:
            assert escenario.saldo_de_stock() == 48
            assert escenario.saldo_de_la_cuenta() == Decimal("150000.00")
        escenario.verificar_libros(e.cliente_id)

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_vta06_con_el_mismo_cliente_la_segunda_ve_el_numero_ocupado(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        e = escenario.entorno
        numero = e.siguiente_numero()
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(e.contenido(numero=numero)),
            escenario.venta_srv(e.contenido(numero=numero)),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert _nombres(errores) == [NUMERO_DUPLICADO]
        assert escenario.cantidad_de("venta") == 1
        assert escenario.saldo_de_stock() == 33
        assert escenario.saldo_de_la_cuenta() == Decimal("181250.00")
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_d4_dos_ventas_con_numeros_distintos_dejan_el_mayor_correlativo(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        """El correlativo del dispositivo se sube con `GREATEST` como último bloqueo: no baja
        aunque las dos terminen en cualquier orden."""
        escenario = _Escenario(database_url)
        e = escenario.entorno
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(e.contenido(numero=f"{e.prefijo}-000007")),
            escenario.venta_srv(e.contenido(numero=f"{e.prefijo}-000012")),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        ((correlativo,),) = escenario.leer(
            "SELECT ultimo_correlativo FROM dispositivo WHERE organizacion_id = :o AND id = :d",
            d=e.dispositivo_id,
        )
        assert correlativo == 12


class TestVentaFrenteALaJornadaDeSuUbicacion:
    """STK-09, INV-16, RUT-04, D17: la ubicación con toma se lee con su jornada en el nivel 5 del
    orden de bloqueo. La venta desde la oficina y la apertura de una jornada sobre la misma
    ubicación se serializan; la liberación de la jornada propia, también."""

    def _camioneta(self, escenario: _Escenario) -> UUID:
        resultado: list[UUID] = []

        def _armar(e: EntornoVenta) -> None:
            camioneta_id = crear_ubicacion_sql(
                e.sesion, e.org, nombre="Camioneta 2", requiere_toma=True
            )
            e.comprar(e.vino_id, 48, "1050", ubicacion_id=camioneta_id)
            resultado.append(camioneta_id)

        escenario.armar(_armar)
        return resultado[0]

    def test_stk09_venta_primero_la_apertura_espera_y_se_abre(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id = self._camioneta(escenario)
        pedro, dispositivo_de_pedro = escenario.otro_vendedor(frozenset({"ABRIR_JORNADA"}))
        e = escenario.entorno

        primero, segundo = _encadenado(
            database_url,
            escenario.venta_srv(e.contenido(ubicacion_id=str(camioneta_id))),
            escenario.abrir_jornada_srv(pedro, dispositivo_de_pedro, camioneta_id),
        )

        assert (primero, segundo) == (OK, OK)
        assert escenario.cantidad_de("venta", f"ubicacion_id = '{camioneta_id}'") == 1
        assert escenario.cantidad_de("jornada", "estado = 'ABIERTA'") == 1
        assert escenario.saldo_de_stock(camioneta_id) == 33
        escenario.verificar_libros()

    def test_stk09_apertura_primero_la_venta_sin_liberar_ubicacion_responde_ubicacion_tomada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id = self._camioneta(escenario)
        pedro, dispositivo_de_pedro = escenario.otro_vendedor(frozenset({"ABRIR_JORNADA"}))
        e = escenario.entorno

        primero, segundo = _encadenado(
            database_url,
            escenario.abrir_jornada_srv(pedro, dispositivo_de_pedro, camioneta_id),
            escenario.venta_srv(e.contenido(ubicacion_id=str(camioneta_id))),
        )

        assert (primero, segundo) == (OK, UBICACION_TOMADA)
        assert escenario.cantidad_de("venta") == 0
        assert escenario.saldo_de_stock(camioneta_id) == 48
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_stk09_apertura_y_venta_en_carrera_libre_son_uno_de_los_dos_ordenes_validos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id = self._camioneta(escenario)
        pedro, dispositivo_de_pedro = escenario.otro_vendedor(frozenset({"ABRIR_JORNADA"}))
        e = escenario.entorno
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(e.contenido(ubicacion_id=str(camioneta_id))),
            escenario.abrir_jornada_srv(pedro, dispositivo_de_pedro, camioneta_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert 1 in resultados, f"{resultados}, errores={errores}"
        if 0 in resultados:
            assert escenario.saldo_de_stock(camioneta_id) == 33
        else:
            assert _nombres(errores) == [UBICACION_TOMADA]
            assert escenario.saldo_de_stock(camioneta_id) == 48
        assert escenario.cantidad_de("jornada", "estado = 'ABIERTA'") == 1
        escenario.verificar_libros()

    def _vendedor_con_jornada(self, escenario: _Escenario) -> tuple[UUID, UUID, UUID]:
        """La camioneta con su stock, la jornada `ABIERTA` del usuario del entorno y el motivo de
        liberación."""
        resultado: list[UUID] = []

        def _armar(e: EntornoVenta) -> None:
            camioneta_id = crear_ubicacion_sql(
                e.sesion, e.org, nombre="Camioneta 2", requiere_toma=True
            )
            e.comprar(e.vino_id, 48, "1050", ubicacion_id=camioneta_id)
            e.sesion.commit()
            jornada_id = e.crear_jornada(ubicacion_id=camioneta_id)
            resultado.extend(
                [camioneta_id, jornada_id, e.crear_motivo("LIBERACION_JORNADA", "Motivo")]
            )

        escenario.armar(_armar)
        return resultado[0], resultado[1], resultado[2]

    def test_rut04_venta_primero_la_liberacion_espera_y_la_venta_queda_en_la_jornada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id, jornada_id, motivo_id = self._vendedor_con_jornada(escenario)

        primero, segundo = _encadenado(
            database_url,
            escenario.venta_srv(escenario.entorno.contenido(ubicacion_id=None)),
            escenario.liberar_srv(jornada_id, motivo_id),
        )

        assert (primero, segundo) == (OK, OK)
        assert escenario.cantidad_de("venta", f"jornada_id = '{jornada_id}'") == 1
        assert escenario.cantidad_de("jornada", "estado = 'LIBERADA'") == 1
        assert escenario.saldo_de_stock(camioneta_id) == 33
        escenario.verificar_libros()

    def test_rut04_liberacion_primero_la_venta_se_decide_con_la_jornada_ya_liberada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """La jornada propia se lee sin bloquear (D3) y la decisión de toma se toma después, con
        la jornada `FOR SHARE` (nivel 5, D17). Con la liberación sin confirmar, la venta lee la
        jornada `ABIERTA`, espera en el nivel 5 y, confirmada la liberación, relee: la ubicación
        quedó libre, así que el egreso es de una ubicación libre y la venta queda SIN jornada
        (la misma que el movimiento de stock). Nunca una venta de una jornada liberada."""
        escenario = _Escenario(database_url)
        camioneta_id, jornada_id, motivo_id = self._vendedor_con_jornada(escenario)

        primero, segundo = _encadenado(
            database_url,
            escenario.liberar_srv(jornada_id, motivo_id),
            escenario.venta_srv(escenario.entorno.contenido(ubicacion_id=None)),
        )

        assert primero == OK
        assert segundo in {OK, *SIN_UBICACION_NI_JORNADA}
        assert escenario.cantidad_de("jornada", "estado = 'LIBERADA'") == 1
        assert escenario.cantidad_de("venta", f"jornada_id = '{jornada_id}'") == 0
        assert escenario.cantidad_de("stock_movimiento", f"jornada_id = '{jornada_id}'") == 0
        if segundo == OK:
            assert escenario.cantidad_de("venta", "jornada_id IS NULL") == 1
            assert escenario.saldo_de_stock(camioneta_id) == 33
        else:
            assert escenario.cantidad_de("venta") == 0
            assert escenario.saldo_de_stock(camioneta_id) == 48
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_rut04_liberacion_y_venta_en_carrera_libre_son_uno_de_los_dos_ordenes_validos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id, jornada_id, motivo_id = self._vendedor_con_jornada(escenario)
        trabajos: list[Callable[[Session], Any]] = [
            escenario.venta_srv(escenario.entorno.contenido(ubicacion_id=None)),
            escenario.liberar_srv(jornada_id, motivo_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert 1 in resultados, f"{resultados}, errores={errores}"
        # Tres desenlaces válidos: la venta se confirmó primero (en la jornada), la liberación se
        # confirmó antes de que la venta decidiera la toma (venta SIN jornada, ubicación libre) o
        # la venta ya no encontró su jornada. Nunca una venta de una jornada liberada.
        assert not (errores.keys() - {0}), f"{resultados}, errores={errores}"
        assert {type(error).__name__ for error in errores.values()} <= SIN_UBICACION_NI_JORNADA
        assert escenario.cantidad_de("jornada", "estado = 'LIBERADA'") == 1
        en_la_jornada = escenario.cantidad_de("venta", f"jornada_id = '{jornada_id}'")
        sin_jornada = escenario.cantidad_de("venta", "jornada_id IS NULL")
        assert en_la_jornada + sin_jornada == len(resultados) - 1
        assert (
            escenario.cantidad_de("stock_movimiento", "tipo = 'VENTA' AND jornada_id IS NULL")
            == sin_jornada
        )
        assert escenario.saldo_de_stock(camioneta_id) == 48 - 15 * (en_la_jornada + sin_jornada)
        escenario.verificar_libros()


class TestVentaSinConexionFrenteALaLiberacionYLaNuevaTomaDeSuJornada:
    """SYN-05, RUT-09, STK-09, INV-17: la mercadería ya se entregó, así que la venta sin conexión
    se acepta siempre; lo que cambia es lo que se observa según lo que ya estuviera confirmado
    cuando leyó la jornada y la ubicación (`JORNADA_LIBERADA`,
    `UBICACION_TOMADA_AL_SINCRONIZAR`)."""

    def _ruta(self, escenario: _Escenario, *, estado: str = "ABIERTA") -> tuple[UUID, UUID, UUID]:
        """La camioneta con stock, la jornada del vendedor (en el `estado` pedido) y el motivo
        de liberación. Con `LIBERADA` la ubicación queda libre."""
        resultado: list[UUID] = []

        def _armar(e: EntornoVenta) -> None:
            camioneta_id = crear_ubicacion_sql(
                e.sesion, e.org, nombre="Camioneta 2", requiere_toma=True
            )
            e.comprar(e.vino_id, 48, "1050", ubicacion_id=camioneta_id)
            e.sesion.commit()
            jornada_id = e.crear_jornada(estado=estado, ubicacion_id=camioneta_id)
            resultado.extend(
                [camioneta_id, jornada_id, e.crear_motivo("LIBERACION_JORNADA", "Motivo")]
            )

        escenario.armar(_armar)
        return resultado[0], resultado[1], resultado[2]

    def _contenido(self, escenario: _Escenario) -> dict[str, Any]:
        # Change 18b, D7: sin conexión el `credito` del dispositivo es obligatorio.
        return escenario.entorno.contenido(
            ubicacion_id=None, credito=escenario.entorno.credito_offline()
        )

    def test_rut09_venta_primero_la_liberacion_espera_y_la_venta_no_observa(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id, jornada_id, motivo_id = self._ruta(escenario)
        observaciones: list[str] = []

        primero, segundo = _encadenado(
            database_url,
            escenario.venta_srv(
                self._contenido(escenario),
                modo="OFFLINE",
                jornada_id=jornada_id,
                observaciones=observaciones,
            ),
            escenario.liberar_srv(jornada_id, motivo_id),
        )

        assert (primero, segundo) == (OK, OK)
        assert observaciones == []
        assert escenario.cantidad_de("venta", f"jornada_id = '{jornada_id}'") == 1
        assert escenario.saldo_de_stock(camioneta_id) == 33
        escenario.verificar_libros()

    def test_rut09_liberacion_primero_la_venta_se_acepta_con_jornada_liberada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id, jornada_id, motivo_id = self._ruta(escenario)
        observaciones: list[str] = []

        primero, segundo = _encadenado(
            database_url,
            escenario.liberar_srv(jornada_id, motivo_id),
            escenario.venta_srv(
                self._contenido(escenario),
                modo="OFFLINE",
                jornada_id=jornada_id,
                observaciones=observaciones,
            ),
        )

        assert (primero, segundo) == (OK, OK)
        assert observaciones == ["JORNADA_LIBERADA"]
        assert escenario.cantidad_de("venta", f"jornada_id = '{jornada_id}'") == 1
        assert escenario.saldo_de_stock(camioneta_id) == 33
        escenario.verificar_libros()

    def test_syn05_nueva_toma_primero_la_venta_se_acepta_con_las_dos_observaciones(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """La jornada ya estaba liberada; otro vendedor abre una jornada sobre la camioneta y su
        apertura sigue sin confirmar cuando llega la venta: espera, y al confirmarse la apertura
        la venta se acepta con `JORNADA_LIBERADA` y `UBICACION_TOMADA_AL_SINCRONIZAR`, sin
        `LIBERAR_UBICACION` y con el stock descontado igual."""
        escenario = _Escenario(database_url)
        camioneta_id, jornada_id, _ = self._ruta(escenario, estado="LIBERADA")
        pedro, dispositivo_de_pedro = escenario.otro_vendedor(frozenset({"ABRIR_JORNADA"}))
        observaciones: list[str] = []

        primero, segundo = _encadenado(
            database_url,
            escenario.abrir_jornada_srv(pedro, dispositivo_de_pedro, camioneta_id),
            escenario.venta_srv(
                self._contenido(escenario),
                modo="OFFLINE",
                jornada_id=jornada_id,
                observaciones=observaciones,
            ),
        )

        assert (primero, segundo) == (OK, OK)
        assert sorted(observaciones) == ["JORNADA_LIBERADA", "UBICACION_TOMADA_AL_SINCRONIZAR"]
        assert escenario.cantidad_de("venta", f"jornada_id = '{jornada_id}'") == 1
        assert escenario.saldo_de_stock(camioneta_id) == 33
        escenario.verificar_libros()

    def test_syn05_venta_primero_la_apertura_espera_y_la_venta_solo_observa_la_liberacion(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id, jornada_id, _ = self._ruta(escenario, estado="LIBERADA")
        pedro, dispositivo_de_pedro = escenario.otro_vendedor(frozenset({"ABRIR_JORNADA"}))
        observaciones: list[str] = []

        primero, segundo = _encadenado(
            database_url,
            escenario.venta_srv(
                self._contenido(escenario),
                modo="OFFLINE",
                jornada_id=jornada_id,
                observaciones=observaciones,
            ),
            escenario.abrir_jornada_srv(pedro, dispositivo_de_pedro, camioneta_id),
        )

        assert (primero, segundo) == (OK, OK)
        assert observaciones == ["JORNADA_LIBERADA"]
        assert escenario.saldo_de_stock(camioneta_id) == 33
        escenario.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_syn05_en_carrera_libre_por_el_lote_la_venta_se_acepta_siempre(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        camioneta_id, jornada_id, _ = self._ruta(escenario, estado="LIBERADA")
        pedro, dispositivo_de_pedro = escenario.otro_vendedor(frozenset({"ABRIR_JORNADA"}))
        contenido = self._contenido(escenario)
        estados: list[str] = []

        def _vender(sesion: Session) -> object:
            resultado = escenario.enviar_en_lote(sesion, contenido, jornada_id)
            estados.append(resultado.estado)
            return resultado

        trabajos: list[Callable[[Session], Any]] = [
            _vender,
            escenario.abrir_jornada_srv(pedro, dispositivo_de_pedro, camioneta_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert estados == ["ACEPTADO_CON_OBSERVACIONES"]
        codigos = escenario.codigos_de_observacion()
        assert codigos in (
            ["JORNADA_LIBERADA"],
            ["JORNADA_LIBERADA", "UBICACION_TOMADA_AL_SINCRONIZAR"],
        )
        assert escenario.saldo_de_stock(camioneta_id) == 33
        assert escenario.cantidad_de("jornada", "estado = 'ABIERTA'") == 1
        escenario.verificar_libros()


class TestMismoOperationIdSimultaneo:
    """INV-06: dos envíos simultáneos con el mismo `Operation-Id` producen un solo efecto; el
    segundo espera a la reserva del primero y recibe el resultado ya guardado."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_inv06_dos_ventas_con_el_mismo_operation_id_dejan_un_solo_efecto(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        e = escenario.entorno
        contenido = e.contenido(cobranza=e.cobranza())
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, contenido, operation_id=operation_id).resultado,
            lambda sesion: escenario.enviar(sesion, contenido, operation_id=operation_id).resultado,
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert resultados[0] == resultados[1]
        assert escenario.cantidad_de("venta") == 1
        assert escenario.cantidad_de("venta_linea") == 1
        assert escenario.cantidad_de("cobranza") == 1
        assert escenario.cantidad_de("stock_movimiento", "tipo = 'VENTA'") == 1
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'VENTA'") == 1
        assert escenario.saldo_de_stock() == 33
        # 150000,00 + 31250,00 - 20000,00
        assert escenario.saldo_de_la_cuenta() == Decimal("161250.00")
        escenario.verificar_libros()

    def test_inv06_el_mismo_operation_id_con_otro_contenido_es_conflicto_y_no_vende_dos_veces(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        e = escenario.entorno
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, e.contenido(), operation_id=operation_id),
            lambda sesion: escenario.enviar(
                sesion, e.contenido(e.linea(cantidad=20)), operation_id=operation_id
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert escenario.cantidad_de("venta") == 1
        assert escenario.cantidad_de("stock_movimiento", "tipo = 'VENTA'") == 1
        escenario.verificar_libros()
