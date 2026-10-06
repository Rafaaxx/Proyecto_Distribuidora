"""Change 12, tarea 10.1: concurrencia real de `PAGO_PROVEEDOR_REGISTRAR` y
`PAGO_PROVEEDOR_ANULAR` contra PostgreSQL real (Testcontainers, `READ COMMITTED`,
`docs/02-arquitectura.md` §7.1), con el mismo arnés que `test_compras_concurrencia.py`: cada
hilo tiene su propia conexión/sesión, confirma su propia transacción y arranca junto a los
otros en una `threading.Barrier`. Nunca hay rollback externo (`CLAUDE.md` §4) y la limpieza
se hace al final con `TRUNCATE`.

Escenarios (`design.md` D2, D10; specs `pagos-a-proveedores` y `anulacion-de-pagos`):

- dos pagos simultáneos al mismo proveedor: ambos aplicados y saldo igual a la suma del
  libro, con `saldo_cuenta` coherente (INV-13);
- un pago en paralelo con una compra a crédito del mismo proveedor: ambos aplicados;
- dos anulaciones simultáneas del mismo pago (independiente y de origen `COMPRA`): una
  `PAGO_YA_ANULADO` y una sola `ANULACION_PAGO`;
- `COMPRA_ANULAR` con `devuelve_pago = true` en paralelo con `PAGO_PROVEEDOR_ANULAR` de su
  pago: sin interbloqueo (D10: compra, luego pago, luego `saldo_cuenta`) y una sola
  `ANULACION_PAGO`;
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
CONFIRMAR = "COMPRA_CONFIRMAR"
ANULAR_COMPRA = "COMPRA_ANULAR"
PAGAR = "PAGO_PROVEEDOR_REGISTRAR"
ANULAR_PAGO = "PAGO_PROVEEDOR_ANULAR"
_MANEJADORES = {
    CONFIRMAR: proveedores_commands.manejar_compra_confirmar,
    ANULAR_COMPRA: proveedores_commands.manejar_compra_anular,
    PAGAR: proveedores_commands.manejar_pago_proveedor_registrar,
    ANULAR_PAGO: proveedores_commands.manejar_pago_proveedor_anular,
}
PERMISOS = frozenset(
    {
        "REGISTRAR_COMPRA",
        "ANULAR_COMPRA",
        "PERMITIR_STOCK_NEGATIVO",
        "REGISTRAR_PAGO_PROVEEDOR",
        "ANULAR_PAGO_PROVEEDOR",
    }
)


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _sesion_independiente(database_url: str) -> Session:
    """Conexión/sesión propia que confirma sus propias transacciones: simula un worker
    de FastAPI distinto (`02` §16.2)."""
    factory = crear_session_factory(crear_engine(database_url))
    return factory()


class _Escenario:
    """Una organización confirmada con un proveedor, un producto (Botella, una unidad
    base), un depósito, un medio de pago en efectivo, los motivos de anulación de compra
    y de pago, y un usuario con los permisos de compra y de pago."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.org = crear_organizacion(sesion).id
            self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=PERMISOS
            )
            self.proveedor_id = crear_proveedor(sesion, self.org, nombre="Bodega Sur")
            self.producto_id = crear_producto_sql(
                sesion, self.org, nombre="Vino A", proveedor_id=self.proveedor_id
            )
            self.presentacion_id = crear_presentacion_sql(
                sesion,
                self.org,
                self.producto_id,
                nombre="Botella",
                unidades_base=1,
                es_referencia=True,
            )
            self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
            self.efectivo_id = uuid4()
            sesion.execute(
                text(
                    "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, "
                    "activo, creado_en, actualizado_en) VALUES (:id, :org, 'Efectivo', false, "
                    "true, :m, :m)"
                ),
                {"id": self.efectivo_id, "org": self.org, "m": MOMENTO},
            )
            self.motivo_compra_id = self._motivo(sesion, "ANULACION_COMPRA")
            self.motivo_pago_id = self._motivo(sesion, "ANULACION_PAGO")
            sesion.commit()
        finally:
            sesion.close()

    def _motivo(self, sesion: Session, ambito: str) -> UUID:
        motivo_id = uuid4()
        sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, :ambito, 'Error de carga', true, :m, :m)"
            ),
            {"id": motivo_id, "org": self.org, "ambito": ambito, "m": MOMENTO},
        )
        return motivo_id

    # --- contenidos ------------------------------------------------------------------

    def contenido_de_compra(self, *, contado: bool = False) -> dict[str, Any]:
        """10 botellas a 100,00 sin IVA: total de factura 1210,00 (21 % de IVA)."""
        contenido: dict[str, Any] = {
            "proveedor_id": str(self.proveedor_id),
            "fecha": "2026-10-02",
            "ubicacion_id": str(self.deposito_id),
            "condicion": "CONTADO" if contado else "CREDITO",
            "total_factura": "1210.00",
            "lineas": [
                {
                    "producto_id": str(self.producto_id),
                    "presentacion_id": str(self.presentacion_id),
                    "cantidad": "10",
                    "valor": "100.00",
                    "incluye_iva": False,
                }
            ],
        }
        if contado:
            contenido["medios"] = [
                {"medio_pago_id": str(self.efectivo_id), "importe": "1210.00", "referencia": None}
            ]
        return contenido

    def contenido_de_pago(self, importe: str) -> dict[str, Any]:
        return {
            "proveedor_id": str(self.proveedor_id),
            "fecha": "2026-10-02",
            "importe": importe,
            "medios": [
                {"medio_pago_id": str(self.efectivo_id), "importe": importe, "referencia": None}
            ],
        }

    def contenido_de_anulacion_de_pago(self, pago_id: UUID) -> dict[str, Any]:
        return {"pago_id": str(pago_id), "motivo_id": str(self.motivo_pago_id)}

    def contenido_de_anulacion_de_compra(
        self, compra_id: UUID, *, devuelve_pago: bool | None = None
    ) -> dict[str, Any]:
        contenido: dict[str, Any] = {
            "compra_id": str(compra_id),
            "motivo_id": str(self.motivo_compra_id),
        }
        if devuelve_pago is not None:
            contenido["devuelve_pago"] = devuelve_pago
        return contenido

    # --- comandos por el bus ---------------------------------------------------------

    def enviar(
        self, sesion: Session, tipo: str, contenido: dict[str, Any], operation_id: UUID
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
        manejador = _MANEJADORES[tipo]

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

    def ejecutar(self, tipo: str, contenido: dict[str, Any]) -> dict[str, Any]:
        """Un comando en su propia transacción confirmada; devuelve su resultado."""
        sesion = _sesion_independiente(self.database_url)
        try:
            comando = self.enviar(sesion, tipo, contenido, uuid4())
            sesion.commit()
            assert comando.resultado is not None
            return dict(comando.resultado)
        finally:
            sesion.close()

    def comprar_a_credito(self) -> UUID:
        return UUID(self.ejecutar(CONFIRMAR, self.contenido_de_compra())["compra_id"])

    def comprar_de_contado(self) -> UUID:
        return UUID(self.ejecutar(CONFIRMAR, self.contenido_de_compra(contado=True))["compra_id"])

    def pagar(self, importe: str) -> UUID:
        return UUID(self.ejecutar(PAGAR, self.contenido_de_pago(importe))["pago_id"])

    def pago_de_la_compra(self, compra_id: UUID) -> UUID:
        ((pago_id,),) = self.leer(
            "SELECT id FROM pago_proveedor WHERE organizacion_id = :o AND compra_id = :c",
            c=compra_id,
        )
        assert isinstance(pago_id, UUID)
        return pago_id

    # --- lecturas confirmadas --------------------------------------------------------

    def leer(self, consulta: str, **parametros: object) -> list[tuple[object, ...]]:
        sesion = _sesion_independiente(self.database_url)
        try:
            filas = sesion.execute(text(consulta), {"o": self.org, **parametros}).all()
            return [tuple(fila) for fila in filas]
        finally:
            sesion.close()

    def suma_del_libro(self) -> Decimal:
        ((saldo,),) = self.leer(
            "SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), 0) "
            "FROM cuenta_movimiento WHERE organizacion_id = :o "
            "AND cuenta_tipo = 'PROVEEDOR' AND entidad_id = :e",
            e=self.proveedor_id,
        )
        assert isinstance(saldo, Decimal | int)
        return Decimal(saldo)

    def saldo_de_la_cuenta(self) -> Decimal:
        ((saldo,),) = self.leer(
            "SELECT saldo FROM saldo_cuenta WHERE organizacion_id = :o "
            "AND cuenta_tipo = 'PROVEEDOR' AND entidad_id = :e",
            e=self.proveedor_id,
        )
        assert isinstance(saldo, Decimal)
        return saldo

    def cantidad_de(self, tabla: str, donde: str = "true") -> int:
        ((cantidad,),) = self.leer(
            f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o AND {donde}"  # noqa: S608
        )
        assert isinstance(cantidad, int)
        return cantidad

    def estado_del_pago(self, pago_id: UUID) -> str:
        ((estado,),) = self.leer(
            "SELECT estado FROM pago_proveedor WHERE organizacion_id = :o AND id = :p",
            p=pago_id,
        )
        assert isinstance(estado, str)
        return estado

    def verificar_saldo_contra_el_libro(self) -> None:
        """INV-13: `saldo_cuenta` es la suma de `cuenta_movimiento`, comprobado con SQL."""
        assert self.saldo_de_la_cuenta() == self.suma_del_libro()


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


class TestDosPagosSimultaneosAlMismoProveedor:
    """INV-13, PAG-02: dos pagos al mismo proveedor se serializan por `bloquear_saldo` y
    el saldo es el de aplicar ambos."""

    @pytest.mark.parametrize("repeticion", range(5))
    def test_ambos_se_aplican_y_el_saldo_es_la_suma_del_libro(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        escenario.comprar_a_credito()  # deuda de 1210,00
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(
                sesion, PAGAR, escenario.contenido_de_pago("300.00"), uuid4()
            ),
            lambda sesion: escenario.enviar(
                sesion, PAGAR, escenario.contenido_de_pago("400.00"), uuid4()
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert escenario.cantidad_de("pago_proveedor", "estado = 'CONFIRMADA'") == 2
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'PAGO'") == 2
        assert escenario.suma_del_libro() == Decimal("510.00")
        escenario.verificar_saldo_contra_el_libro()

    @pytest.mark.parametrize("repeticion", range(3))
    def test_dos_pagos_que_juntos_superan_la_deuda_dejan_saldo_a_favor_exacto(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        escenario.comprar_a_credito()  # deuda de 1210,00
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(
                sesion, PAGAR, escenario.contenido_de_pago("800.00"), uuid4()
            ),
            lambda sesion: escenario.enviar(
                sesion, PAGAR, escenario.contenido_de_pago("700.00"), uuid4()
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert escenario.suma_del_libro() == Decimal("-290.00")
        escenario.verificar_saldo_contra_el_libro()


class TestPagoEnParaleloConCompraACredito:
    """INV-13: un pago y una compra a crédito del mismo proveedor toman el saldo en el
    mismo orden y el resultado es el de aplicar ambos."""

    @pytest.mark.parametrize("repeticion", range(5))
    def test_ambos_se_aplican_y_el_saldo_es_compra_menos_pago(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        escenario.comprar_a_credito()  # deuda previa de 1210,00
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(
                sesion, PAGAR, escenario.contenido_de_pago("500.00"), uuid4()
            ),
            lambda sesion: escenario.enviar(
                sesion, CONFIRMAR, escenario.contenido_de_compra(), uuid4()
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert escenario.cantidad_de("compra") == 2
        assert escenario.cantidad_de("pago_proveedor") == 1
        # 1210 + 1210 - 500.
        assert escenario.suma_del_libro() == Decimal("1920.00")
        escenario.verificar_saldo_contra_el_libro()


class TestDosAnulacionesSimultaneasDelMismoPago:
    """PAG-03, D10: la anulación bloquea el pago; la segunda lo ve `ANULADA`."""

    @pytest.mark.parametrize("repeticion", range(3))
    def test_pago_independiente_una_anula_y_la_otra_es_pago_ya_anulado(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        escenario.comprar_a_credito()
        pago_id = escenario.pagar("1210.00")
        anulacion = escenario.contenido_de_anulacion_de_pago(pago_id)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, ANULAR_PAGO, anulacion, uuid4()),
            lambda sesion: escenario.enviar(sesion, ANULAR_PAGO, anulacion, uuid4()),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        (error,) = errores.values()
        assert isinstance(error, DomainError)
        assert error.codigo == "PAGO_YA_ANULADO"
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'ANULACION_PAGO'") == 1
        assert escenario.estado_del_pago(pago_id) == "ANULADA"
        assert escenario.suma_del_libro() == Decimal("1210.00")
        escenario.verificar_saldo_contra_el_libro()

    @pytest.mark.parametrize("repeticion", range(3))
    def test_pago_de_compra_ya_anulada_sin_devolucion_tambien_una_sola_anulacion(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        compra_id = escenario.comprar_de_contado()
        pago_id = escenario.pago_de_la_compra(compra_id)
        escenario.ejecutar(
            ANULAR_COMPRA,
            escenario.contenido_de_anulacion_de_compra(compra_id, devuelve_pago=False),
        )
        assert escenario.suma_del_libro() == Decimal("-1210.00")
        anulacion = escenario.contenido_de_anulacion_de_pago(pago_id)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, ANULAR_PAGO, anulacion, uuid4()),
            lambda sesion: escenario.enviar(sesion, ANULAR_PAGO, anulacion, uuid4()),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        (error,) = errores.values()
        assert isinstance(error, DomainError)
        assert error.codigo == "PAGO_YA_ANULADO"
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'ANULACION_PAGO'") == 1
        assert escenario.suma_del_libro() == Decimal("0.00")
        escenario.verificar_saldo_contra_el_libro()


class TestAnularCompraConDevolucionEnParaleloConAnularSuPago:
    """D10: ambos comandos piden primero la fila de la compra, después la del pago y
    recién después `saldo_cuenta`: no hay interbloqueo y queda una sola `ANULACION_PAGO`."""

    @pytest.mark.parametrize("repeticion", range(8))
    def test_sin_interbloqueo_y_una_sola_anulacion_de_pago(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        compra_id = escenario.comprar_de_contado()
        pago_id = escenario.pago_de_la_compra(compra_id)
        anular_compra = escenario.contenido_de_anulacion_de_compra(compra_id, devuelve_pago=True)
        anular_pago = escenario.contenido_de_anulacion_de_pago(pago_id)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, ANULAR_COMPRA, anular_compra, uuid4()),
            lambda sesion: escenario.enviar(sesion, ANULAR_PAGO, anular_pago, uuid4()),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        # La anulación de la compra siempre gana: el pago de una compra vigente no se
        # anula por separado (D2) y, si la compra ya se anuló, el pago ya está `ANULADA`.
        assert 0 in resultados, f"{resultados}, errores={errores}"
        assert set(errores) <= {1}
        for error in errores.values():
            assert isinstance(error, DomainError)
            assert error.codigo in {"PAGO_YA_ANULADO", "PAGO_DE_COMPRA_VIGENTE"}
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'ANULACION_PAGO'") == 1
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'ANULACION_COMPRA'") == 1
        assert escenario.estado_del_pago(pago_id) == "ANULADA"
        assert escenario.suma_del_libro() == Decimal("0.00")
        escenario.verificar_saldo_contra_el_libro()


class TestMismoOperationIdSimultaneo:
    """INV-06: dos envíos simultáneos con el mismo `Operation-Id` producen un solo efecto;
    el segundo espera a la reserva del primero y recibe el resultado ya guardado."""

    def test_dos_pagos_con_el_mismo_operation_id_dejan_un_solo_efecto(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        escenario.comprar_a_credito()
        contenido = escenario.contenido_de_pago("500.00")
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, PAGAR, contenido, operation_id).resultado,
            lambda sesion: escenario.enviar(sesion, PAGAR, contenido, operation_id).resultado,
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert resultados[0] == resultados[1]
        assert escenario.cantidad_de("pago_proveedor") == 1
        assert escenario.cantidad_de("pago_proveedor_medio") == 1
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'PAGO'") == 1
        assert escenario.suma_del_libro() == Decimal("710.00")

    def test_dos_anulaciones_con_el_mismo_operation_id_dejan_un_solo_efecto(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        escenario.comprar_a_credito()
        pago_id = escenario.pagar("500.00")
        contenido = escenario.contenido_de_anulacion_de_pago(pago_id)
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, ANULAR_PAGO, contenido, operation_id).resultado,
            lambda sesion: escenario.enviar(sesion, ANULAR_PAGO, contenido, operation_id).resultado,
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert resultados[0] == resultados[1]
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'ANULACION_PAGO'") == 1
        assert escenario.suma_del_libro() == Decimal("1210.00")
