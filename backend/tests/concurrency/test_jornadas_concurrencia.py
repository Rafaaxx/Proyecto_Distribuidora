"""Change 15, grupo 15 (tareas 15.1 y 15.2): concurrencia real de las jornadas contra PostgreSQL
real (Testcontainers, `READ COMMITTED`, `02` §7.1), con el arnés de `test_stock_concurrencia.py`
y `test_transferencias_ajustes_concurrencia.py`: cada hilo tiene su propia conexión/sesión,
confirma su propia transacción y arranca junto a los otros en una `threading.Barrier`. Nunca hay
rollback externo (`CLAUDE.md` §4) y cada prueba limpia lo confirmado al terminar.

Los escenarios cuyo resultado depende del orden de llegada se prueban además en los DOS órdenes
de forma determinista con `_encadenado` (la primera transacción deja sus bloqueos tomados y SIN
confirmar, la segunda se observa esperando en `pg_stat_activity` y recién entonces confirma la
primera): no hay `sleep` para "dar tiempo".

Escenarios de `specs/stock/jornadas`, `specs/stock/toma-de-ubicacion` y `specs/sistema/
pipeline-de-comandos`:

- INV-16: dos aperturas simultáneas de dos usuarios sobre la misma ubicación, una sola jornada
  no cerrada; la garantía es del índice único parcial de la base (`02` §7.5), también cuando se
  inserta sin pasar por el servicio; un usuario o un dispositivo, a lo sumo una;
- INV-06: el mismo `Operation-Id` en paralelo tiene un solo efecto;
- STK-09, D9: apertura y transferencia ajena sobre la misma ubicación, en los dos órdenes;
- INV-12, D9: liberación y movimiento de la propia jornada, sin interbloqueo;
- INV-16: cierre y nueva apertura simultáneos;
- AUD-02: dos liberaciones simultáneas de la misma jornada, una sola fila de auditoría;
- D9 (orden de bloqueo por `ubicacion_id` ascendente): transferencias opuestas entre dos
  vehículos tomados, hechas con `LIBERAR_UBICACION`, sin interbloqueo.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.db import crear_engine
from app.modules.proveedores import service as _proveedores_service  # noqa: F401  (puerto ADR-025)
from app.modules.stock import commands as _stock_commands  # noqa: F401  (registra los handlers)
from app.modules.stock import jornadas_commands as _jornadas_commands  # noqa: F401
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    DispositivoConJornadaError,
    JornadaEstadoInvalidoError,
    UbicacionTomadaError,
    UsuarioConJornadaError,
)
from app.modules.stock.service import LineaDeTransferencia
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from tests.concurrency.test_stock_concurrencia import (
    MOMENTO,
    RELOJ,
    _en_paralelo,
    _Escenario,
    _sesion_independiente,
)
from tests.concurrency.test_transferencias_ajustes_concurrencia import OK, _encadenado
from tests.integration.cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from tests.integration.stock_utiles import crear_jornada_sql, crear_motivo_sql, crear_ubicacion_sql

ABRIR = "JORNADA_ABRIR"
RENDIR = "JORNADA_RENDIR"
CERRAR = "JORNADA_CERRAR"
LIBERAR = "JORNADA_LIBERAR"
TRANSFERIR = "STOCK_TRANSFERIR"

VENDEDOR = frozenset({"ABRIR_JORNADA", "TRANSFERIR_STOCK"})
SUPERVISORA = frozenset(
    {"ABRIR_JORNADA", "RENDIR_JORNADA", "LIBERAR_UBICACION", "TRANSFERIR_STOCK"}
)

TOMADA = UbicacionTomadaError.__name__
USUARIO_CON_JORNADA = UsuarioConJornadaError.__name__
DISPOSITIVO_CON_JORNADA = DispositivoConJornadaError.__name__
ESTADO_INVALIDO = JornadaEstadoInvalidoError.__name__
REPETICIONES = 6


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


class _Actor:
    def __init__(self, usuario_id: UUID, dispositivo_id: UUID) -> None:
        self.usuario_id = usuario_id
        self.dispositivo_id = dispositivo_id


class _Mundo(_Escenario):
    """La organización del escenario de stock (productos, depósito y "Camioneta" con toma) más
    una segunda camioneta, dos vendedores (Juan y Pedro), una Supervisora, un segundo
    dispositivo para Juan y el motivo de liberación. Todo confirmado en su propia sesión."""

    def __init__(self, database_url: str) -> None:
        super().__init__(database_url)
        sesion = _sesion_independiente(database_url)
        try:
            self.juan = _Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
            self.pedro = _Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
            self.sofia = _Actor(
                *crear_usuario_y_dispositivo(sesion, self.org, permisos=SUPERVISORA)
            )
            _, self.segundo_dispositivo_de_juan = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=frozenset({"VER_REPORTES"})
            )
            self.vehiculo_2 = crear_ubicacion_sql(
                sesion, self.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
            )
            self.motivo = crear_motivo_sql(sesion, self.org, ambito="LIBERACION_JORNADA")
            sesion.commit()
        finally:
            sesion.close()

    # --- armado de la situación (cada paso confirma en su propia sesión) ----------------

    def sembrar(self, ubicacion_id: UUID, cantidad: int, producto_id: UUID | None = None) -> None:
        sesion = _sesion_independiente(self.database_url)
        try:
            self.ingresar(
                sesion,
                (producto_id or self.producto_a, cantidad, "1000"),
                ubicacion_id=ubicacion_id,
            )
            sesion.commit()
        finally:
            sesion.close()

    def abrir(self, actor: _Actor, ubicacion_id: UUID | None = None) -> UUID:
        sesion = _sesion_independiente(self.database_url)
        try:
            jornada = stock_service.abrir_jornada(
                self.org,
                sesion,
                RELOJ,
                ubicacion_id=ubicacion_id or self.vehiculo,
                usuario_id=actor.usuario_id,
                dispositivo_id=actor.dispositivo_id,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )
            sesion.commit()
            return jornada.id
        finally:
            sesion.close()

    def rendir(self, jornada_id: UUID) -> None:
        sesion = _sesion_independiente(self.database_url)
        try:
            stock_service.rendir_jornada(
                self.org,
                sesion,
                jornada_id=jornada_id,
                usuario_id=self.sofia.usuario_id,
                occurred_at=MOMENTO,
            )
            sesion.commit()
        finally:
            sesion.close()

    # --- el bus, sobre la sesión del hilo (la transacción la confirma quien llama) ------

    def enviar(
        self,
        sesion: Session,
        tipo: str,
        actor: _Actor,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
    ) -> Comando:
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return registrado.funcion(  # type: ignore[call-arg, return-value]
                sobre, validado, sesion=sesion_protegida, reloj=RELOJ
            )

        return sync_service.procesar_comando(
            sesion,
            RELOJ,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def abrir_por_el_bus(
        self, actor: _Actor, ubicacion_id: UUID | None = None, *, operation_id: UUID | None = None
    ) -> Callable[[Session], Comando]:
        return lambda sesion: self.enviar(
            sesion,
            ABRIR,
            actor,
            {"ubicacion_id": str(ubicacion_id or self.vehiculo)},
            operation_id=operation_id,
        )

    def transferir_por_el_bus(
        self, actor: _Actor, origen: UUID, destino: UUID, cantidad: int = 10
    ) -> Callable[[Session], Comando]:
        contenido = {
            "ubicacion_origen_id": str(origen),
            "ubicacion_destino_id": str(destino),
            "lineas": [{"producto_id": str(self.producto_a), "cantidad_base": cantidad}],
        }
        return lambda sesion: self.enviar(sesion, TRANSFERIR, actor, contenido)

    def transicion_por_el_bus(
        self, tipo: str, actor: _Actor, jornada_id: UUID
    ) -> Callable[[Session], Comando]:
        contenido: dict[str, Any] = {"jornada_id": str(jornada_id)}
        if tipo == LIBERAR:
            contenido["motivo_id"] = str(self.motivo)
        return lambda sesion: self.enviar(sesion, tipo, actor, contenido)

    # --- el servicio, sobre la sesión del hilo y SIN confirmar ---------------------------
    # Los órdenes de llegada deterministas necesitan que la primera transacción conserve sus
    # bloqueos hasta que `_encadenado` la confirme; el bus confirma al terminar, el servicio no.

    def abrir_srv(
        self, actor: _Actor, ubicacion_id: UUID | None = None
    ) -> Callable[[Session], object]:
        return lambda sesion: stock_service.abrir_jornada(
            self.org,
            sesion,
            RELOJ,
            ubicacion_id=ubicacion_id or self.vehiculo,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
        )

    def transferir_srv(
        self, actor: _Actor, origen: UUID, destino: UUID, cantidad: int = 10
    ) -> Callable[[Session], object]:
        return lambda sesion: stock_service.transferir(
            self.org,
            sesion,
            RELOJ,
            ubicacion_origen_id=origen,
            ubicacion_destino_id=destino,
            lineas=[LineaDeTransferencia(self.producto_a, cantidad)],
            observacion=None,
            usuario_id=actor.usuario_id,
            dispositivo_id=actor.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
        )

    def liberar_srv(self, jornada_id: UUID) -> Callable[[Session], object]:
        return lambda sesion: stock_service.liberar_jornada(
            self.org,
            sesion,
            jornada_id=jornada_id,
            usuario_id=self.sofia.usuario_id,
            motivo_id=self.motivo,
            observacion=None,
            occurred_at=MOMENTO,
        )

    def cerrar_srv(self, jornada_id: UUID) -> Callable[[Session], object]:
        return lambda sesion: stock_service.cerrar_jornada(
            self.org,
            sesion,
            jornada_id=jornada_id,
            usuario_id=self.sofia.usuario_id,
            occurred_at=MOMENTO,
        )

    # --- lecturas confirmadas -----------------------------------------------------------

    def cantidad(self, consulta: str, **parametros: object) -> int:
        ((cuantos,),) = self.leer(consulta, **parametros)
        assert isinstance(cuantos, int)
        return cuantos

    def no_cerradas(self) -> int:
        return self.cantidad(
            "SELECT count(*) FROM jornada WHERE organizacion_id = :o "
            "AND estado IN ('ABIERTA', 'EN_RENDICION')"
        )

    def no_cerradas_en(self, ubicacion_id: UUID) -> int:
        return self.cantidad(
            "SELECT count(*) FROM jornada WHERE organizacion_id = :o AND ubicacion_id = :u "
            "AND estado IN ('ABIERTA', 'EN_RENDICION')",
            u=ubicacion_id,
        )

    def jornadas(self) -> int:
        return self.cantidad("SELECT count(*) FROM jornada WHERE organizacion_id = :o")

    def estado_de(self, jornada_id: UUID) -> str:
        ((estado,),) = self.leer(
            "SELECT estado FROM jornada WHERE organizacion_id = :o AND id = :j", j=jornada_id
        )
        assert isinstance(estado, str)
        return estado

    def movimientos_de_transferencia(self) -> int:
        return self.cantidad(
            "SELECT count(*) FROM stock_movimiento WHERE organizacion_id = :o "
            "AND origen_tipo = 'TRANSFERENCIA'"
        )

    def saldos_iguales_al_libro(self) -> None:
        """INV-12: cada `stock_saldo` es la suma de su libro, cada `stock_total` la suma de
        los saldos del producto y `verificar_consistencia` no informa diferencias."""
        libro = self.leer(
            "SELECT producto_id, ubicacion_id, SUM(cantidad_base) FROM stock_movimiento "
            "WHERE organizacion_id = :o GROUP BY producto_id, ubicacion_id"
        )
        for producto_id, ubicacion_id, suma in libro:
            assert isinstance(producto_id, UUID)
            assert isinstance(ubicacion_id, UUID)
            assert self.saldo(producto_id, ubicacion_id) == int(suma)  # type: ignore[arg-type]
        for producto_id in {fila[0] for fila in libro}:
            assert isinstance(producto_id, UUID)
            ((suma_saldos,),) = self.leer(
                "SELECT COALESCE(SUM(cantidad_base), 0) FROM stock_saldo "
                "WHERE organizacion_id = :o AND producto_id = :p",
                p=producto_id,
            )
            assert self.stock_total(producto_id) == int(suma_saldos)  # type: ignore[arg-type]
        assert self.diferencias() == []


def _dos_ordenes(nombre_primero: str, nombre_segundo: str) -> list[Any]:
    return [
        pytest.param(True, id=f"{nombre_primero}_primero"),
        pytest.param(False, id=f"{nombre_segundo}_primero"),
    ]


# --- 15.1 -----------------------------------------------------------------------------


class TestAperturasSimultaneasInv16:
    """INV-16, `02` §7.5, RUT-01: la apertura toma la ubicación `FOR UPDATE` y escribe la
    jornada; la unicidad la decide el índice único parcial (sin verificación previa que pueda
    perder una carrera)."""

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_dos_usuarios_en_dos_dispositivos_abren_la_misma_ubicacion(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        mundo = _Mundo(database_url)
        trabajos: list[Callable[[Session], object]] = [
            mundo.abrir_por_el_bus(mundo.juan),
            mundo.abrir_por_el_bus(mundo.pedro),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert sorted(resultados.values()) == sorted([OK, TOMADA]), (
            f"{resultados}, errores={errores}"
        )
        assert mundo.no_cerradas_en(mundo.vehiculo) == 1  # INV-16
        assert mundo.jornadas() == 1  # la rechazada no dejó jornada

    @pytest.mark.parametrize(
        ("indice", "otro_usuario", "otro_dispositivo", "otra_ubicacion"),
        [
            ("ux_jornada__ubicacion_abierta", True, True, False),
            ("ux_jornada__usuario_abierta", False, True, True),
            ("ux_jornada__dispositivo_abierta", True, False, True),
        ],
    )
    def test_la_base_rechaza_la_segunda_jornada_escrita_por_fuera_del_servicio(
        self,
        database_url: str,
        _engine_de_sesion,
        indice: str,
        otro_usuario: bool,
        otro_dispositivo: bool,
        otra_ubicacion: bool,
    ) -> None:
        """La garantía es de la base (`02` §7.5): dos `INSERT` directos que chocan en uno de los
        tres índices, el segundo falla con la violación de ese índice."""
        mundo = _Mundo(database_url)
        primero = _Actor(mundo.juan.usuario_id, mundo.juan.dispositivo_id)
        segundo = _Actor(
            mundo.pedro.usuario_id if otro_usuario else primero.usuario_id,
            mundo.pedro.dispositivo_id if otro_dispositivo else primero.dispositivo_id,
        )
        ubicaciones = [mundo.vehiculo, mundo.vehiculo_2 if otra_ubicacion else mundo.vehiculo]

        def _insertar(actor: _Actor, ubicacion_id: UUID) -> Callable[[Session], None]:
            def _trabajo(sesion: Session) -> None:
                crear_jornada_sql(
                    sesion,
                    mundo.org,
                    usuario_id=actor.usuario_id,
                    dispositivo_id=actor.dispositivo_id,
                    ubicacion_id=ubicacion_id,
                )

            return _trabajo

        resultados, errores = _en_paralelo(
            database_url, [_insertar(primero, ubicaciones[0]), _insertar(segundo, ubicaciones[1])]
        )

        assert sorted(resultados.values()) == sorted([OK, IntegrityError.__name__]), (
            f"{resultados}, errores={errores}"
        )
        (rechazo,) = errores.values()
        assert indice in str(rechazo)
        assert mundo.no_cerradas() == 1  # INV-16

    def test_el_mismo_usuario_abre_dos_ubicaciones_desde_dos_dispositivos(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        for _ in range(REPETICIONES):
            mundo = _Mundo(database_url)
            en_otro_dispositivo = _Actor(mundo.juan.usuario_id, mundo.segundo_dispositivo_de_juan)
            trabajos = [
                mundo.abrir_por_el_bus(mundo.juan, mundo.vehiculo),
                mundo.abrir_por_el_bus(en_otro_dispositivo, mundo.vehiculo_2),
            ]

            resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

            assert sorted(resultados.values()) == sorted([OK, USUARIO_CON_JORNADA]), (
                f"{resultados}, errores={errores}"
            )
            assert mundo.no_cerradas() == 1  # INV-16

    def test_el_mismo_usuario_y_dispositivo_abren_dos_ubicaciones_a_la_vez(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """Dos pedidos de la misma sesión: una sola jornada; el rechazo es el del usuario o el
        del dispositivo (ambos índices chocan; la base informa el primero que revisa)."""
        for _ in range(REPETICIONES):
            mundo = _Mundo(database_url)
            trabajos = [
                mundo.abrir_por_el_bus(mundo.juan, mundo.vehiculo),
                mundo.abrir_por_el_bus(mundo.juan, mundo.vehiculo_2),
            ]

            resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

            rechazo = [nombre for nombre in resultados.values() if nombre != OK]
            assert len(rechazo) == 1, f"{resultados}, errores={errores}"
            assert rechazo[0] in {USUARIO_CON_JORNADA, DISPOSITIVO_CON_JORNADA}
            assert mundo.no_cerradas() == 1  # INV-16

    def test_dos_usuarios_abren_desde_el_mismo_dispositivo(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        for _ in range(REPETICIONES):
            mundo = _Mundo(database_url)
            pedro_en_el_dispositivo_de_juan = _Actor(
                mundo.pedro.usuario_id, mundo.juan.dispositivo_id
            )
            trabajos = [
                mundo.abrir_por_el_bus(mundo.juan, mundo.vehiculo),
                mundo.abrir_por_el_bus(pedro_en_el_dispositivo_de_juan, mundo.vehiculo_2),
            ]

            resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

            assert sorted(resultados.values()) == sorted([OK, DISPOSITIVO_CON_JORNADA]), (
                f"{resultados}, errores={errores}"
            )
            assert mundo.no_cerradas() == 1  # INV-16

    def test_el_mismo_operation_id_en_paralelo_tiene_un_solo_efecto(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """INV-06: el reenvío simultáneo de la misma apertura devuelve el mismo resultado y no
        deja una segunda jornada, comando ni fila de auditoría."""
        mundo = _Mundo(database_url)
        operation_id = uuid4()
        resultados_del_comando: dict[int, object] = {}

        def _enviar(indice: int) -> Callable[[Session], None]:
            enviar = mundo.abrir_por_el_bus(mundo.juan, operation_id=operation_id)

            def _trabajo(sesion: Session) -> None:
                resultados_del_comando[indice] = enviar(sesion).resultado

            return _trabajo

        resultados, errores = _en_paralelo(database_url, [_enviar(0), _enviar(1)])

        assert set(resultados.values()) == {OK}, f"{resultados}, errores={errores}"
        assert resultados_del_comando[0] == resultados_del_comando[1]
        assert mundo.jornadas() == 1
        assert (
            mundo.cantidad(
                "SELECT count(*) FROM comando WHERE organizacion_id = :o AND operation_id = :op",
                op=operation_id,
            )
            == 1
        )
        assert (
            mundo.cantidad(
                "SELECT count(*) FROM auditoria WHERE organizacion_id = :o AND operation_id = :op",
                op=operation_id,
            )
            == 1
        )


# --- 15.2 -----------------------------------------------------------------------------


class TestAperturaContraTransferenciaAjena:
    """STK-09, D9: la apertura toma la ubicación `FOR UPDATE` y todo movimiento la toma
    `FOR SHARE`: o el movimiento ajeno se confirma antes de la toma, o ve la jornada y es
    `UBICACION_TOMADA`; nunca un movimiento ajeno confirmado después."""

    def _mundo(self, database_url: str) -> _Mundo:
        mundo = _Mundo(database_url)
        mundo.sembrar(mundo.deposito, 100)
        return mundo

    @pytest.mark.parametrize("apertura_primero", _dos_ordenes("apertura", "transferencia"))
    def test_en_los_dos_ordenes_de_llegada(
        self, database_url: str, _engine_de_sesion, apertura_primero: bool
    ) -> None:
        mundo = self._mundo(database_url)
        apertura = mundo.abrir_srv(mundo.juan)
        ajena = mundo.transferir_srv(mundo.pedro, mundo.deposito, mundo.vehiculo, 30)

        if apertura_primero:
            resultado = _encadenado(database_url, lambda s: apertura(s), lambda s: ajena(s))
            assert resultado == (OK, TOMADA)
            assert mundo.movimientos_de_transferencia() == 0  # nada ajeno después de la toma
            assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 0
        else:
            resultado = _encadenado(database_url, lambda s: ajena(s), lambda s: apertura(s))
            assert resultado == (OK, OK)  # la transferencia se confirmó ANTES de la toma
            assert mundo.movimientos_de_transferencia() == 2
            assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 30
            assert (
                mundo.cantidad(
                    "SELECT count(*) FROM stock_movimiento WHERE organizacion_id = :o "
                    "AND jornada_id IS NOT NULL"
                )
                == 0
            )  # la jornada no hizo ese movimiento
        assert mundo.no_cerradas_en(mundo.vehiculo) == 1  # INV-16
        mundo.saldos_iguales_al_libro()  # INV-12

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_en_carrera_libre(self, database_url: str, _engine_de_sesion, ronda: int) -> None:
        mundo = self._mundo(database_url)
        trabajos: list[Callable[[Session], object]] = [
            mundo.abrir_por_el_bus(mundo.juan),
            mundo.transferir_por_el_bus(mundo.pedro, mundo.deposito, mundo.vehiculo, 30),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert resultados[0] == OK, f"{resultados}, errores={errores}"
        assert resultados[1] in {OK, TOMADA}, f"{resultados}, errores={errores}"
        if resultados[1] == OK:
            assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 30
        else:
            assert mundo.movimientos_de_transferencia() == 0
            assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 0
        assert mundo.no_cerradas_en(mundo.vehiculo) == 1
        mundo.saldos_iguales_al_libro()


class TestLiberacionContraMovimientoDeLaPropiaJornada:
    """INV-12, D9: la liberación toma la jornada `FOR UPDATE` y el movimiento la lee `FOR SHARE`;
    se serializan sin interbloqueo. Si el movimiento llega primero queda con el `jornada_id`; si
    llega después ve la ubicación libre. En los dos casos el saldo es la suma del libro."""

    def _mundo(self, database_url: str) -> tuple[_Mundo, UUID]:
        mundo = _Mundo(database_url)
        mundo.sembrar(mundo.deposito, 100)
        jornada_id = mundo.abrir(mundo.juan)
        return mundo, jornada_id

    @pytest.mark.parametrize("movimiento_primero", _dos_ordenes("movimiento", "liberacion"))
    def test_en_los_dos_ordenes_de_llegada(
        self, database_url: str, _engine_de_sesion, movimiento_primero: bool
    ) -> None:
        mundo, jornada_id = self._mundo(database_url)
        propio = mundo.transferir_srv(mundo.juan, mundo.deposito, mundo.vehiculo, 30)
        liberar = mundo.liberar_srv(jornada_id)

        if movimiento_primero:
            resultado = _encadenado(database_url, lambda s: propio(s), lambda s: liberar(s))
            jornada_de_los_movimientos = 1  # el de la entrada a la camioneta: es de la jornada
        else:
            resultado = _encadenado(database_url, lambda s: liberar(s), lambda s: propio(s))
            jornada_de_los_movimientos = 0  # ya liberada: la ubicación estaba libre

        assert resultado == (OK, OK)
        assert mundo.estado_de(jornada_id) == "LIBERADA"
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 30
        assert (
            mundo.cantidad(
                "SELECT count(*) FROM stock_movimiento WHERE organizacion_id = :o "
                "AND jornada_id = :j",
                j=jornada_id,
            )
            == jornada_de_los_movimientos
        )
        mundo.saldos_iguales_al_libro()  # INV-12

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_en_carrera_libre_sin_interbloqueo(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        mundo, jornada_id = self._mundo(database_url)
        trabajos: list[Callable[[Session], object]] = [
            mundo.transferir_por_el_bus(mundo.juan, mundo.deposito, mundo.vehiculo, 30),
            mundo.transicion_por_el_bus(LIBERAR, mundo.sofia, jornada_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert set(resultados.values()) == {OK}, f"{resultados}, errores={errores}"
        assert mundo.estado_de(jornada_id) == "LIBERADA"
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 30
        mundo.saldos_iguales_al_libro()  # INV-12


class TestCierreYNuevaApertura:
    """INV-16, D9: la apertura solo se acepta si ve la jornada anterior cerrada. Si el cierre
    llega primero, la apertura espera su confirmación en el índice único y se acepta; si la
    apertura llega primero, ve la jornada en rendición y es `UBICACION_TOMADA`."""

    def _mundo(self, database_url: str) -> tuple[_Mundo, UUID]:
        mundo = _Mundo(database_url)
        jornada_id = mundo.abrir(mundo.juan)
        mundo.rendir(jornada_id)
        return mundo, jornada_id

    @pytest.mark.parametrize("cierre_primero", _dos_ordenes("cierre", "apertura"))
    def test_en_los_dos_ordenes_de_llegada(
        self, database_url: str, _engine_de_sesion, cierre_primero: bool
    ) -> None:
        mundo, jornada_id = self._mundo(database_url)
        cierre = mundo.cerrar_srv(jornada_id)
        apertura = mundo.abrir_srv(mundo.pedro)

        if cierre_primero:
            resultado = _encadenado(database_url, lambda s: cierre(s), lambda s: apertura(s))
            assert resultado == (OK, OK)
            assert mundo.estado_de(jornada_id) == "CERRADA"
            assert mundo.no_cerradas_en(mundo.vehiculo) == 1
        else:
            resultado = _encadenado(database_url, lambda s: apertura(s), lambda s: cierre(s))
            assert resultado == (TOMADA, OK)
            assert mundo.estado_de(jornada_id) == "CERRADA"
            assert mundo.no_cerradas_en(mundo.vehiculo) == 0
        assert mundo.no_cerradas() <= 1  # INV-16

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_en_carrera_libre(self, database_url: str, _engine_de_sesion, ronda: int) -> None:
        mundo, jornada_id = self._mundo(database_url)
        trabajos: list[Callable[[Session], object]] = [
            mundo.transicion_por_el_bus(CERRAR, mundo.sofia, jornada_id),
            mundo.abrir_por_el_bus(mundo.pedro),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert resultados[0] == OK, f"{resultados}, errores={errores}"
        assert resultados[1] in {OK, TOMADA}, f"{resultados}, errores={errores}"
        assert mundo.estado_de(jornada_id) == "CERRADA"
        # La apertura se aceptó solo si vio la jornada cerrada (INV-16).
        assert mundo.no_cerradas_en(mundo.vehiculo) == (1 if resultados[1] == OK else 0)


class TestDosLiberacionesDeLaMismaJornada:
    """RUT-09, AUD-02, D9: la segunda liberación espera la fila de la jornada, la ve ya liberada
    y es `JORNADA_ESTADO_INVALIDO`; el bus revierte todo, así que queda UNA fila de auditoría
    con el motivo."""

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_una_se_acepta_y_la_otra_es_estado_invalido(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        mundo = _Mundo(database_url)
        jornada_id = mundo.abrir(mundo.juan)
        trabajos: list[Callable[[Session], object]] = [
            mundo.transicion_por_el_bus(LIBERAR, mundo.sofia, jornada_id),
            mundo.transicion_por_el_bus(LIBERAR, mundo.sofia, jornada_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert sorted(resultados.values()) == sorted([OK, ESTADO_INVALIDO]), (
            f"{resultados}, errores={errores}"
        )
        assert mundo.estado_de(jornada_id) == "LIBERADA"
        filas = mundo.leer(
            "SELECT motivo_id FROM auditoria WHERE organizacion_id = :o AND accion = :a",
            a=LIBERAR,
        )
        assert [fila[0] for fila in filas] == [mundo.motivo]  # una sola fila, con el motivo
        assert (
            mundo.cantidad(
                "SELECT count(*) FROM comando WHERE organizacion_id = :o AND tipo = :t",
                t=LIBERAR,
            )
            == 1
        )


class TestTransferenciasOpuestasEntreVehiculosTomados:
    """D9: las jornadas se toman por `ubicacion_id` ascendente. Dos transferencias opuestas entre
    dos vehículos tomados, hechas por quien tiene `LIBERAR_UBICACION`, no se esperan en círculo,
    tampoco con una liberación y un cierre de esas mismas jornadas en medio (INV-12)."""

    def _mundo(self, database_url: str) -> tuple[_Mundo, UUID, UUID]:
        mundo = _Mundo(database_url)
        mundo.sembrar(mundo.vehiculo, 200)
        mundo.sembrar(mundo.vehiculo_2, 200)
        j1 = mundo.abrir(mundo.juan, mundo.vehiculo)
        j2 = mundo.abrir(mundo.pedro, mundo.vehiculo_2)
        return mundo, j1, j2

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_dos_transferencias_opuestas(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        mundo, j1, j2 = self._mundo(database_url)
        trabajos: list[Callable[[Session], object]] = []
        for _ in range(2):
            trabajos.append(
                mundo.transferir_por_el_bus(mundo.sofia, mundo.vehiculo, mundo.vehiculo_2)
            )
            trabajos.append(
                mundo.transferir_por_el_bus(mundo.sofia, mundo.vehiculo_2, mundo.vehiculo)
            )

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert set(resultados.values()) == {OK}, f"{resultados}, errores={errores}"
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 200
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo_2) == 200
        assert mundo.estado_de(j1) == "ABIERTA"
        assert mundo.estado_de(j2) == "ABIERTA"
        mundo.saldos_iguales_al_libro()  # INV-12

    @pytest.mark.parametrize("ronda", range(REPETICIONES))
    def test_con_una_liberacion_y_un_cierre_en_medio(
        self, database_url: str, _engine_de_sesion, ronda: int
    ) -> None:
        mundo, j1, j2 = self._mundo(database_url)
        mundo.rendir(j2)
        trabajos: list[Callable[[Session], object]] = [
            mundo.transferir_por_el_bus(mundo.sofia, mundo.vehiculo, mundo.vehiculo_2),
            mundo.transferir_por_el_bus(mundo.sofia, mundo.vehiculo_2, mundo.vehiculo),
            mundo.transicion_por_el_bus(LIBERAR, mundo.sofia, j1),
            mundo.transicion_por_el_bus(CERRAR, mundo.sofia, j2),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)  # type: ignore[arg-type]

        assert set(resultados.values()) == {OK}, f"{resultados}, errores={errores}"
        assert mundo.estado_de(j1) == "LIBERADA"
        assert mundo.estado_de(j2) == "CERRADA"
        assert mundo.no_cerradas() == 0
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo) == 200
        assert mundo.saldo(mundo.producto_a, mundo.vehiculo_2) == 200
        mundo.saldos_iguales_al_libro()  # INV-12
