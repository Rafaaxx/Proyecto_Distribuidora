"""Change 17, tarea 16.1 (D18): concurrencia real de `COBRANZA_REGISTRAR` y `COBRANZA_ANULAR`
contra PostgreSQL real (Testcontainers, `READ COMMITTED`, `02` §7.1), con el arnés de
`test_pagos_proveedor_concurrencia.py` y `test_transferencias_ajustes_concurrencia.py`: cada hilo
tiene su propia conexión/sesión, confirma su propia transacción y arranca junto a los otros en
una `threading.Barrier`. Nunca hay rollback externo (`CLAUDE.md` §4) y la limpieza se hace al
final con `TRUNCATE`.

Los escenarios cuyo resultado depende del orden de llegada se prueban además en los DOS órdenes
de forma determinista con `_encadenado` (la primera transacción deja sus bloqueos tomados y SIN
confirmar; se observa a la segunda esperando en `pg_stat_activity`; recién entonces confirma la
primera). No hay `sleep` para "dar tiempo".

- INV-13: dos cobranzas simultáneas al mismo cliente que juntas saldan exacto su deuda;
- INV-13, INV-01: dos anulaciones simultáneas de la misma cobranza, una sola anula;
- CC-08: una cobranza frente a un saldo inicial del mismo cliente, en los dos órdenes;
- RUT-09: una cobranza sin conexión frente a la liberación de su jornada, en los dos órdenes;
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

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.db import crear_engine
from app.modules.cobranzas import commands as cobranzas_commands
from app.modules.cobranzas import service as cobranzas_service
from app.modules.cobranzas.domain.errores import CobranzaYaAnuladaError
from app.modules.cobranzas.service import MedioACobrar
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.cuentas_corrientes.domain.errores import CuentaConOperacionesError
from app.modules.stock import service as stock_service
from app.modules.sync import service as sync_service
from tests.concurrency.test_pagos_proveedor_concurrencia import (
    MOMENTO,
    RELOJ,
    _en_paralelo,
    _sesion_independiente,
)
from tests.concurrency.test_transferencias_ajustes_concurrencia import OK, _encadenado
from tests.integration.cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import crear_jornada_sql, crear_ubicacion_sql

REGISTRAR = "COBRANZA_REGISTRAR"
ANULAR = "COBRANZA_ANULAR"
_MANEJADORES = {
    REGISTRAR: cobranzas_commands.manejar_cobranza_registrar,
    ANULAR: cobranzas_commands.manejar_cobranza_anular,
}
PERMISOS = frozenset({"REGISTRAR_COBRANZA", "ANULAR_COBRANZA"})
YA_ANULADA = CobranzaYaAnuladaError.__name__
CUENTA_CON_OPERACIONES = CuentaConOperacionesError.__name__


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


class _Escenario:
    """Una organización confirmada con un usuario con los permisos de cobranza, `Kiosco La
    Esquina` con saldo de `1000.00`, un medio en efectivo, el motivo de anulación y una jornada
    `ABIERTA` del usuario con su motivo de liberación."""

    def __init__(self, database_url: str, *, saldo_inicial: str | None = "1000.00") -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.org = crear_organizacion(sesion).id
            self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=PERMISOS
            )
            self.cliente_id = crear_cliente(sesion, self.org, nombre="Kiosco La Esquina")
            self.efectivo_id = uuid4()
            sesion.execute(
                text(
                    "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, "
                    "activo, creado_en, actualizado_en) VALUES (:id, :org, 'Efectivo', false, "
                    "true, :m, :m)"
                ),
                {"id": self.efectivo_id, "org": self.org, "m": MOMENTO},
            )
            self.motivo_id = self._motivo(sesion, "ANULACION_COBRANZA")
            self.motivo_liberacion_id = self._motivo(sesion, "LIBERACION_JORNADA")
            self.jornada_id = crear_jornada_sql(
                sesion,
                self.org,
                usuario_id=self.usuario_id,
                dispositivo_id=self.dispositivo_id,
                ubicacion_id=crear_ubicacion_sql(sesion, self.org, requiere_toma=True),
            )
            sesion.commit()
            if saldo_inicial is not None:
                self.saldo_inicial(sesion, saldo_inicial)
                sesion.commit()
        finally:
            sesion.close()

    def _motivo(self, sesion: Session, ambito: str) -> UUID:
        motivo_id = uuid4()
        sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, :ambito, 'Motivo', true, :m, :m)"
            ),
            {"id": motivo_id, "org": self.org, "ambito": ambito, "m": MOMENTO},
        )
        return motivo_id

    # --- contenidos y comandos -----------------------------------------------------------

    def contenido(self, importe: str, cobranza_id: UUID | None = None) -> dict[str, Any]:
        return {
            "cobranza_id": str(cobranza_id or uuid4()),
            "cliente_id": str(self.cliente_id),
            "importe": importe,
            "medios": [
                {"medio_pago_id": str(self.efectivo_id), "importe": importe, "referencia": None}
            ],
        }

    def contenido_de_anulacion(self, cobranza_id: UUID) -> dict[str, Any]:
        return {"cobranza_id": str(cobranza_id), "motivo_id": str(self.motivo_id)}

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

    def cobrar(self, importe: str) -> UUID:
        return UUID(self.ejecutar(REGISTRAR, self.contenido(importe))["cobranza_id"])

    # --- servicios sobre la sesión del hilo, SIN confirmar (para `_encadenado`) -----------

    def saldo_inicial(self, sesion: Session, importe: str) -> None:
        cuentas_service.registrar_saldo_inicial(
            self.org,
            sesion,
            RELOJ,
            cuenta_tipo="CLIENTE",
            entidad_id=self.cliente_id,
            importe=importe,
            sentido="AUMENTA",
            occurred_at=MOMENTO,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
        )

    def cobrar_srv(
        self, importe: str, *, offline: bool = False, observaciones: list[str] | None = None
    ) -> Callable[[Session], object]:
        def _cobrar(sesion: Session) -> object:
            resultado = cobranzas_service.registrar_cobranza(
                self.org,
                sesion,
                RELOJ,
                cobranza_id=uuid4(),
                cliente_id=self.cliente_id,
                importe=Decimal(importe),
                medios=[MedioACobrar(self.efectivo_id, Decimal(importe), None)],
                observacion=None,
                jornada_del_sobre=self.jornada_id if offline else None,
                operation_id=uuid4(),
                usuario_id=self.usuario_id,
                dispositivo_id=self.dispositivo_id,
                occurred_at=MOMENTO,
                modo="OFFLINE" if offline else "ONLINE",
            )
            if observaciones is not None:
                observaciones.extend(o.codigo for o in resultado.observaciones)
            return resultado

        return _cobrar

    def saldo_inicial_srv(self, importe: str) -> Callable[[Session], object]:
        return lambda sesion: self.saldo_inicial(sesion, importe)

    def liberar_srv(self) -> Callable[[Session], object]:
        return lambda sesion: stock_service.liberar_jornada(
            self.org,
            sesion,
            jornada_id=self.jornada_id,
            usuario_id=self.usuario_id,
            motivo_id=self.motivo_liberacion_id,
            observacion=None,
            occurred_at=MOMENTO,
        )

    # --- lecturas confirmadas ------------------------------------------------------------

    def leer(self, consulta: str, **parametros: object) -> list[tuple[object, ...]]:
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

    def suma_del_libro(self) -> Decimal:
        ((saldo,),) = self.leer(
            "SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), 0) "
            "FROM cuenta_movimiento WHERE organizacion_id = :o "
            "AND cuenta_tipo = 'CLIENTE' AND entidad_id = :e",
            e=self.cliente_id,
        )
        assert isinstance(saldo, Decimal | int)
        return Decimal(saldo)

    def saldo_de_la_cuenta(self) -> Decimal:
        ((saldo,),) = self.leer(
            "SELECT saldo FROM saldo_cuenta WHERE organizacion_id = :o "
            "AND cuenta_tipo = 'CLIENTE' AND entidad_id = :e",
            e=self.cliente_id,
        )
        assert isinstance(saldo, Decimal)
        return saldo

    def verificar_saldo_contra_el_libro(self) -> None:
        """INV-13: `saldo_cuenta` es la suma de `cuenta_movimiento`, comprobado con SQL."""
        assert self.saldo_de_la_cuenta() == self.suma_del_libro()


class TestDosCobranzasSimultaneasAlMismoCliente:
    """INV-13, D18: dos cobranzas al mismo cliente se serializan por el saldo bloqueado y el
    saldo es el de aplicar ambas."""

    @pytest.mark.parametrize("repeticion", range(5))
    def test_inv13_dos_cobranzas_que_saldan_exacto_la_deuda_dejan_saldo_cero(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)  # deuda de 1000,00
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(
                sesion, REGISTRAR, escenario.contenido("600.00"), uuid4()
            ),
            lambda sesion: escenario.enviar(
                sesion, REGISTRAR, escenario.contenido("400.00"), uuid4()
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert escenario.cantidad_de("cobranza", "estado = 'CONFIRMADA'") == 2
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'COBRANZA'") == 2
        assert escenario.saldo_de_la_cuenta() == Decimal("0.00")
        escenario.verificar_saldo_contra_el_libro()

    @pytest.mark.parametrize("repeticion", range(3))
    def test_inv13_dos_cobranzas_que_superan_la_deuda_dejan_saldo_a_favor_exacto(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(
                sesion, REGISTRAR, escenario.contenido("700.00"), uuid4()
            ),
            lambda sesion: escenario.enviar(
                sesion, REGISTRAR, escenario.contenido("800.00"), uuid4()
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert escenario.suma_del_libro() == Decimal("-500.00")
        escenario.verificar_saldo_contra_el_libro()


class TestDosAnulacionesSimultaneasDeLaMismaCobranza:
    """INV-13, INV-01, D18: la segunda anulación espera la cobranza `FOR UPDATE`, la relee
    `ANULADA` y falla; el saldo se devuelve una sola vez."""

    @pytest.mark.parametrize("repeticion", range(5))
    def test_una_sola_anula_y_la_otra_responde_cobranza_ya_anulada(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        cobranza_id = escenario.cobrar("300.00")  # saldo 700,00
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(
                sesion, ANULAR, escenario.contenido_de_anulacion(cobranza_id), uuid4()
            ),
            lambda sesion: escenario.enviar(
                sesion, ANULAR, escenario.contenido_de_anulacion(cobranza_id), uuid4()
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert [type(e).__name__ for e in errores.values()] == [YA_ANULADA]
        assert escenario.cantidad_de("cobranza_anulacion") == 1
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'ANULACION_COBRANZA'") == 1
        assert escenario.cantidad_de("cobranza", "estado = 'ANULADA'") == 1
        assert escenario.saldo_de_la_cuenta() == Decimal("1000.00")
        escenario.verificar_saldo_contra_el_libro()


class TestCobranzaFrenteASaldoInicial:
    """CC-08, D18: un saldo inicial solo entra mientras la cuenta no tenga movimientos de otro
    tipo. Con la cobranza primero, el saldo inicial espera el saldo bloqueado y se rechaza; con
    el saldo inicial primero, la cobranza espera y se aplica sobre él."""

    def test_cc08_cobranza_primero_el_saldo_inicial_se_rechaza(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url, saldo_inicial=None)

        primero, segundo = _encadenado(
            database_url, escenario.cobrar_srv("100.00"), escenario.saldo_inicial_srv("500.00")
        )

        assert (primero, segundo) == (OK, CUENTA_CON_OPERACIONES)
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'SALDO_INICIAL'") == 0
        assert escenario.saldo_de_la_cuenta() == Decimal("-100.00")
        escenario.verificar_saldo_contra_el_libro()

    def test_cc08_saldo_inicial_primero_la_cobranza_se_aplica_sobre_el_saldo_inicial(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url, saldo_inicial=None)

        primero, segundo = _encadenado(
            database_url, escenario.saldo_inicial_srv("500.00"), escenario.cobrar_srv("100.00")
        )

        assert (primero, segundo) == (OK, OK)
        assert escenario.saldo_de_la_cuenta() == Decimal("400.00")
        escenario.verificar_saldo_contra_el_libro()

    @pytest.mark.parametrize("repeticion", range(5))
    def test_cc08_en_carrera_libre_el_resultado_es_uno_de_los_dos_ordenes_validos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url, saldo_inicial=None)
        trabajos: list[Callable[[Session], Any]] = [
            escenario.cobrar_srv("100.00"),
            escenario.saldo_inicial_srv("500.00"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert 0 in resultados, f"{resultados}, errores={errores}"
        if 1 in resultados:
            assert escenario.saldo_de_la_cuenta() == Decimal("400.00")
        else:
            assert [type(e).__name__ for e in errores.values()] == [CUENTA_CON_OPERACIONES]
            assert escenario.saldo_de_la_cuenta() == Decimal("-100.00")
        escenario.verificar_saldo_contra_el_libro()


class TestCobranzaOfflineFrenteALiberacionDeSuJornada:
    """RUT-09, D12: la jornada se lee `FOR SHARE`, así que una liberación simultánea se ve o
    espera. La cobranza se acepta siempre; lleva `JORNADA_LIBERADA` solo si la liberación ya
    estaba confirmada cuando la leyó."""

    def test_rut09_cobranza_primero_la_liberacion_espera_y_la_cobranza_no_observa(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        observaciones: list[str] = []

        primero, segundo = _encadenado(
            database_url,
            escenario.cobrar_srv("100.00", offline=True, observaciones=observaciones),
            escenario.liberar_srv(),
        )

        assert (primero, segundo) == (OK, OK)
        assert observaciones == []
        assert escenario.cantidad_de("cobranza", f"jornada_id = '{escenario.jornada_id}'") == 1
        ((estado,),) = escenario.leer(
            "SELECT estado FROM jornada WHERE organizacion_id = :o AND id = :j",
            j=escenario.jornada_id,
        )
        assert estado == "LIBERADA"
        escenario.verificar_saldo_contra_el_libro()

    def test_rut09_liberacion_primero_la_cobranza_espera_y_se_acepta_con_jornada_liberada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        observaciones: list[str] = []

        primero, segundo = _encadenado(
            database_url,
            escenario.liberar_srv(),
            escenario.cobrar_srv("100.00", offline=True, observaciones=observaciones),
        )

        assert (primero, segundo) == (OK, OK)
        assert observaciones == ["JORNADA_LIBERADA"]
        assert escenario.cantidad_de("cobranza", f"jornada_id = '{escenario.jornada_id}'") == 1
        assert escenario.saldo_de_la_cuenta() == Decimal("900.00")
        escenario.verificar_saldo_contra_el_libro()


class TestMismoOperationIdSimultaneo:
    """INV-06: dos envíos simultáneos con el mismo `Operation-Id` producen un solo efecto; el
    segundo espera a la reserva del primero y recibe el resultado ya guardado."""

    def test_inv06_dos_cobranzas_con_el_mismo_operation_id_dejan_un_solo_efecto(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        contenido = escenario.contenido("250.00")
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, REGISTRAR, contenido, operation_id).resultado,
            lambda sesion: escenario.enviar(sesion, REGISTRAR, contenido, operation_id).resultado,
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert resultados[0] == resultados[1]
        assert escenario.cantidad_de("cobranza") == 1
        assert escenario.cantidad_de("cobranza_medio") == 1
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'COBRANZA'") == 1
        assert escenario.saldo_de_la_cuenta() == Decimal("750.00")

    def test_inv06_dos_anulaciones_con_el_mismo_operation_id_dejan_un_solo_efecto(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        cobranza_id = escenario.cobrar("250.00")
        contenido = escenario.contenido_de_anulacion(cobranza_id)
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.enviar(sesion, ANULAR, contenido, operation_id).resultado,
            lambda sesion: escenario.enviar(sesion, ANULAR, contenido, operation_id).resultado,
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert resultados[0] == resultados[1]
        assert escenario.cantidad_de("cobranza_anulacion") == 1
        assert escenario.cantidad_de("cuenta_movimiento", "tipo = 'ANULACION_COBRANZA'") == 1
        assert escenario.saldo_de_la_cuenta() == Decimal("1000.00")
