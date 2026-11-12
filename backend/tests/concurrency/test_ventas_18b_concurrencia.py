"""Change 18b, tarea 16.1 (`design.md` D3, D18, D21; specs `ventas/credito-en-la-venta`,
`ventas/descuentos-en-la-venta`, `identidad/pin-de-autorizacion`): concurrencia real de la venta con
descuentos, crédito y PIN contra PostgreSQL real (Testcontainers, `READ COMMITTED`, `02` §7.1).

Mismo arnés que `test_ventas_concurrencia.py`: cada hilo tiene su propia conexión/sesión, confirma
su propia transacción y arranca junto a los otros en una `threading.Barrier`. Nunca hay rollback
externo (`CLAUDE.md` §4): lo que se compara es lo confirmado, leído desde una sesión nueva. Donde el
resultado depende del orden de llegada se prueba además de forma determinista con `_encadenado`.

- CRE-02, INV-13: dos ventas al mismo cliente con BLOQUEAR, de las que solo cabe una en el límite:
  una se confirma y la otra responde `CREDITO_EXCEDIDO` (en carrera libre y en orden forzado);
- CRE-02, INV-13: venta y cobranza del mismo cliente (la cobranza que llega primero baja el saldo y
  deja entrar a la venta; si llega después, la venta ya había sido rechazada);
- CRE-10: venta y `CLIENTE_CREDITO_MODIFICAR`: la venta congela el crédito de antes o el de después,
  nunca una mezcla;
- DSC-09: venta y pausa de la regla que aplica: o la venta lleva el descuento automático o responde
  `DESCUENTO_DIFIERE`, nunca un estado mezclado;
- SEG-05, ADR-011: venta y rotación del PIN del autorizador; venta y "Mi PIN" del autorizador (la
  venta valida con el PIN anterior o con el nuevo, nunca con una mezcla); dos "Mi PIN" del mismo
  usuario a la vez (queda entero uno de los dos);
- SEG-04, D3: cinco ventas a la vez con el PIN incorrecto del mismo autorizador (el contador del par
  llega exacto al bloqueo) y veinte de cuatro vendedores (el tope general llega exacto);
- INV-06: el mismo comando con descuento y PIN, enviado dos veces a la vez, tiene un solo efecto.

Ningún escenario termina en interbloqueo: un hilo colgado hace fallar la prueba (`ESPERA_MAXIMA`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import (
    MOMENTO_VENTA,
    PERMISOS_DE_VENTA,
    RELOJ_VENTA,
    VENTA_CONFIRMAR,
)

from app.commands import registro
from app.commands.credenciales import CredencialDePin
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.db import crear_engine
from app.core.seguridad import hashear_password
from app.modules.clientes import service as clientes_service
from app.modules.clientes.domain.errores import CreditoExcedidoError
from app.modules.descuentos import service as descuentos_service
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import PinBloqueadoError, PinIncorrectoError
from app.modules.sync import service as sync_service
from app.modules.ventas.domain.errores import DescuentoDifiereError
from tests.concurrency.test_pagos_proveedor_concurrencia import _en_paralelo, _sesion_independiente
from tests.concurrency.test_transferencias_ajustes_concurrencia import OK, _encadenado
from tests.concurrency.test_ventas_concurrencia import REPETICIONES, _Escenario

CREDITO_EXCEDIDO = CreditoExcedidoError.__name__
DESCUENTO_DIFIERE = DescuentoDifiereError.__name__
PIN_INCORRECTO = PinIncorrectoError.__name__
PIN_BLOQUEADO = PinBloqueadoError.__name__

PIN = "482913"
PIN_NUEVO = "735194"
PIN_MALO = "937104"
CLAVE_DE_MARTA = "clave-de-marta-2026"
PERMISOS_DE_VENDEDOR_CON_DESCUENTO = frozenset({"VENDER", "DESCUENTO_MANUAL"})
ANTES_DE_LA_VENTA = FixedClock(MOMENTO_VENTA - timedelta(minutes=30))
DESPUES_DE_LA_VENTA = FixedClock(MOMENTO_VENTA + timedelta(minutes=1))


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


class _Mundo(_Escenario):
    """El escenario de ventas de 18a, con stock de sobra, descuento manual habilitado y lo que
    pide 18b: credenciales de PIN, supervisores y vendedores con descuento."""

    def __init__(self, database_url: str, **opciones: Any) -> None:
        super().__init__(database_url, **{"stock_inicial": 500, **opciones})
        self.armar(lambda e: e.configurar(descuento_manual_habilitado=True, intentos_pin_max=5))
        self.armar(lambda e: e.permitir("DESCUENTO_MANUAL"))

    # --- armado ------------------------------------------------------------------------

    def supervisor(self, permisos: frozenset[str], *, con_clave: bool = False) -> UUID:
        """Un supervisor con PIN definido (una hora antes de la venta, como en las pruebas de
        integración). `con_clave` le pone una contraseña real, para "Mi PIN"."""
        creado: list[UUID] = []

        def _crear(e: Any) -> None:
            usuario_id = e.crear_usuario(permisos, pin=PIN)
            if con_clave:
                e.sesion.execute(
                    text(
                        "UPDATE usuario SET password_hash = :h "
                        "WHERE organizacion_id = :o AND id = :u"
                    ),
                    {"h": hashear_password(CLAVE_DE_MARTA), "o": self.org, "u": usuario_id},
                )
                e.sesion.commit()
            creado.append(usuario_id)

        self.armar(_crear)
        return creado[0]

    def vendedor(self) -> tuple[UUID, UUID, str]:
        """Otro vendedor con descuento manual y tope cero, con su dispositivo y su prefijo."""
        usuario_id, dispositivo_id = self.otro_vendedor(PERMISOS_DE_VENDEDOR_CON_DESCUENTO)
        ((prefijo,),) = self.leer("SELECT prefijo FROM dispositivo WHERE id = :d", d=dispositivo_id)
        return usuario_id, dispositivo_id, str(prefijo)

    def credito(self, limite: str | None, politica: str = "BLOQUEAR") -> None:
        self.armar(lambda e: e.datos_de_credito(limite=limite, politica=politica))

    # --- contenidos ----------------------------------------------------------------------

    def venta_con_general(
        self, *, autorizador: UUID | None = None, general: str = "0.08", importe: str = "2500.00"
    ) -> dict[str, Any]:
        """15 botellas ($31.250) con un general de `general` (8 %, sobre el tope de 5 %)."""
        e = self.entorno
        total = Decimal("31250.00") - Decimal(importe)
        extras: dict[str, Any] = {}
        if autorizador is not None:
            extras["descuento_autorizador_id"] = str(autorizador)
        return e.contenido(
            e.linea(
                descuentos=[
                    {
                        "origen": "MANUAL",
                        "regla_id": None,
                        "porcentaje": f"{Decimal(general):.6f}",
                        "importe": importe,
                    }
                ]
            ),
            total=str(total),
            descuento_manual_general=general,
            **extras,
        )

    def venta_de_otro(self, prefijo: str, **kwargs: Any) -> dict[str, Any]:
        """Lo mismo, con un número del dispositivo de otro vendedor."""
        contenido = self.venta_con_general(**kwargs)
        contenido["numero"] = f"{prefijo}-{uuid4().int % 900000 + 100000:06d}"
        return contenido

    # --- comandos con credenciales ---------------------------------------------------------

    def _sobre_de(
        self,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None,
        usuario_id: UUID | None,
        dispositivo_id: UUID | None,
    ) -> SobreComando:
        e = self.entorno
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=VENTA_CONFIRMAR,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=usuario_id or e.usuario_id,
            dispositivo_id=dispositivo_id or e.dispositivo_id,
            occurred_at=MOMENTO_VENTA,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )

    def enviar_con(  # type: ignore[override]
        self,
        sesion: Session,
        contenido: dict[str, Any],
        *credenciales: CredencialDePin,
        operation_id: UUID | None = None,
        usuario_id: UUID | None = None,
        dispositivo_id: UUID | None = None,
    ) -> Any:
        """El bus completo (reserva, handler, auditoría y `commit`) con las credenciales de PIN
        como dato efímero (D2)."""
        sobre = self._sobre_de(
            contenido,
            operation_id=operation_id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: Any) -> Any:
            return registrado.funcion(
                sobre,
                validado,
                sesion=sesion_protegida,
                reloj=RELOJ_VENTA,
                credenciales=credenciales,
            )

        return sync_service.procesar_comando(
            sesion,
            RELOJ_VENTA,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def vender_srv(
        self, contenido: dict[str, Any], *credenciales: CredencialDePin
    ) -> Callable[[Session], object]:
        """El handler de la venta sobre la sesión del hilo, SIN confirmar (para `_encadenado`)."""
        sobre = self._sobre_de(contenido, operation_id=None, usuario_id=None, dispositivo_id=None)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)
        return lambda sesion: registrado.funcion(
            sobre, validado, sesion=sesion, reloj=RELOJ_VENTA, credenciales=credenciales
        )

    def vender(
        self, contenido: dict[str, Any], *credenciales: CredencialDePin, **kwargs: Any
    ) -> Callable[[Session], object]:
        """Un trabajo para `_en_paralelo`: la venta por el bus."""
        return lambda sesion: self.enviar_con(sesion, contenido, *credenciales, **kwargs)

    def credencial(self, autorizador_id: UUID, pin: str) -> CredencialDePin:
        return self.entorno.credencial(autorizador_id, pin)

    # --- servicios sobre la sesión del hilo, SIN confirmar --------------------------------

    def cobrar_srv(self, importe: str) -> Callable[[Session], object]:
        from app.modules.cobranzas import service as cobranzas_service
        from app.modules.cobranzas.service import MedioACobrar

        e = self.entorno
        return lambda sesion: cobranzas_service.registrar_cobranza(
            self.org,
            sesion,
            RELOJ_VENTA,
            cobranza_id=uuid4(),
            cliente_id=e.cliente_id,
            importe=Decimal(importe),
            medios=[MedioACobrar(e.efectivo_id, Decimal(importe), None)],
            observacion=None,
            jornada_del_sobre=None,
            operation_id=uuid4(),
            usuario_id=e.usuario_id,
            dispositivo_id=e.dispositivo_id,
            occurred_at=MOMENTO_VENTA,
        )

    def modificar_limite_srv(self, limite: str, politica: str) -> Callable[[Session], object]:
        e = self.entorno
        return lambda sesion: clientes_service.modificar_credito_cliente(
            self.org,
            sesion,
            RELOJ_VENTA,
            cliente_id=e.cliente_id,
            limite_credito=Decimal(limite),
            politica_credito=politica,
            tolerancia_offline_tipo=None,
            tolerancia_offline_valor=None,
            actor_id=e.usuario_id,
            operation_id=uuid4(),
        )

    def pausar_srv(self, regla_id: UUID) -> Callable[[Session], object]:
        e = self.entorno
        return lambda sesion: descuentos_service.pausar_regla(
            self.org, sesion, RELOJ_VENTA, regla_id=regla_id, actor_id=e.usuario_id
        )

    def rotar_pin_srv(
        self, usuario_id: UUID, pin: str, reloj: FixedClock = ANTES_DE_LA_VENTA
    ) -> Callable[[Session], object]:
        return lambda sesion: identidad_service.establecer_pin_autorizacion(
            self.org, sesion, reloj, usuario_id=usuario_id, pin=pin, actor_id=usuario_id
        )

    def mi_pin_srv(self, usuario_id: UUID, pin: str) -> Callable[[Session], object]:
        return lambda sesion: identidad_service.definir_pin_propio(
            self.org,
            sesion,
            ANTES_DE_LA_VENTA,
            usuario_id=usuario_id,
            password_actual=CLAVE_DE_MARTA,
            pin=pin,
            ip=f"10.0.{uuid4().int % 250}.{uuid4().int % 250}",
            dispositivo_id=None,
        )

    # --- lecturas confirmadas ----------------------------------------------------------------

    def ventas(self) -> list[tuple[Any, ...]]:
        return self.leer(
            "SELECT credito_limite, credito_exceso, credito_resolucion, total FROM venta "
            "WHERE organizacion_id = :o"
        )

    def descuentos(self, origen: str | None = None) -> int:
        filtro = "true" if origen is None else f"origen = '{origen}'"
        return self.cantidad_de("venta_linea_descuento", filtro)

    def fallos_de_pin(self) -> int:
        return self.cantidad_de("intento_pin_autorizacion", "NOT exito")

    def bloqueos_de_pin(self) -> list[str]:
        return sorted(
            str(fila[0])
            for fila in self.leer(
                "SELECT despues->>'alcance' FROM auditoria WHERE organizacion_id = :o "
                "AND accion = 'PIN_AUTORIZACION_BLOQUEADO'"
            )
        )

    def pin_vigente(self, autorizador_id: UUID, candidatos: tuple[str, ...]) -> list[str]:
        """Cuáles de `candidatos` valida hoy el PIN de `autorizador_id` (lectura desde una sesión
        nueva; los fallos que esto deja no importan al final de la prueba)."""
        intentante, _ = self.otro_vendedor(PERMISOS_DE_VENTA)
        validos: list[str] = []
        for candidato in candidatos:
            sesion = _sesion_independiente(self.database_url)
            try:
                identidad_service.verificar_pin_de_autorizacion(
                    self.org,
                    sesion,
                    RELOJ_VENTA,
                    autorizador_id=autorizador_id,
                    intentante_id=intentante,
                    pin=candidato,
                    permiso="AUTORIZAR_DESCUENTO",
                )
                validos.append(candidato)
            except PinIncorrectoError:
                pass
            finally:
                sesion.close()
        return validos


def _nombres(errores: dict[int, BaseException]) -> list[str]:
    return sorted(type(error).__name__ for error in errores.values())


# --- crédito: dos ventas, venta y cobranza, venta y cambio de límite --------------------------


class TestCreditoConcurrente:
    """CRE-02, CRE-07, CRE-10, INV-13: el crédito se evalúa con el saldo bloqueado (nivel 1)."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_cre02_dos_ventas_al_mismo_cliente_con_bloquear_solo_una_cabe_en_el_limite(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        """Saldo 150.000 y límite 190.000: una venta de 31.250 deja 181.250 (cabe) y la segunda
        llegaría a 212.500. Una se confirma y la otra responde `CREDITO_EXCEDIDO`."""
        mundo = _Mundo(database_url)
        mundo.credito("190000.00")
        e = mundo.entorno
        trabajos = [mundo.vender(e.contenido()), mundo.vender(e.contenido())]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert _nombres(errores) == [CREDITO_EXCEDIDO]
        assert mundo.cantidad_de("venta") == 1
        assert mundo.saldo_de_la_cuenta() == Decimal("181250.00")
        ((limite, exceso, resolucion, _),) = mundo.ventas()
        assert (limite, exceso, resolucion) == (Decimal("190000.00"), Decimal("0.00"), "SIN_EXCESO")
        mundo.verificar_libros()

    def test_cre02_orden_forzado_la_segunda_espera_y_evalua_con_la_deuda_de_la_primera(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        mundo = _Mundo(database_url)
        mundo.credito("190000.00")
        e = mundo.entorno

        primero, segundo = _encadenado(
            database_url, mundo.vender_srv(e.contenido()), mundo.vender(e.contenido())
        )

        assert (primero, segundo) == (OK, CREDITO_EXCEDIDO)
        assert mundo.cantidad_de("venta") == 1
        assert mundo.saldo_de_la_cuenta() == Decimal("181250.00")
        mundo.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_cre02_venta_y_cobranza_del_mismo_cliente_dejan_un_saldo_coherente(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        """Límite 160.000 con saldo 150.000: la venta sola excede (BLOQUEAR). Si la cobranza de
        30.000 llega antes, la venta cabe (151.250); si llega después, la venta ya fue rechazada
        (120.000). Cualquiera de los dos finales es válido; el libro siempre cuadra (INV-13)."""
        mundo = _Mundo(database_url)
        mundo.credito("160000.00")
        e = mundo.entorno

        resultados, errores = _en_paralelo(
            database_url, [mundo.vender(e.contenido()), mundo.cobrar_srv("30000.00")]
        )

        saldo = mundo.saldo_de_la_cuenta()
        if errores:
            assert _nombres(errores) == [CREDITO_EXCEDIDO], f"{resultados}, errores={errores}"
            assert mundo.cantidad_de("venta") == 0
            assert saldo == Decimal("120000.00")
        else:
            assert mundo.cantidad_de("venta") == 1
            assert saldo == Decimal("151250.00")
        assert mundo.cantidad_de("cobranza") == 1
        mundo.verificar_libros()

    def test_cre02_orden_forzado_la_cobranza_primero_deja_entrar_a_la_venta(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        mundo = _Mundo(database_url)
        mundo.credito("160000.00")
        e = mundo.entorno

        primero, segundo = _encadenado(
            database_url, mundo.cobrar_srv("30000.00"), mundo.vender(e.contenido())
        )

        assert (primero, segundo) == (OK, OK)
        assert mundo.saldo_de_la_cuenta() == Decimal("151250.00")
        mundo.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_cre10_venta_y_cambio_de_limite_congelan_el_credito_de_antes_o_el_de_despues(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        """Con 190.000 la venta cabe; con 160.000 no. La venta congela uno u otro, nunca una
        mezcla (un exceso con el límite viejo, o el límite nuevo sin exceso)."""
        mundo = _Mundo(database_url)
        mundo.credito("190000.00")
        e = mundo.entorno

        resultados, errores = _en_paralelo(
            database_url,
            [mundo.vender(e.contenido()), mundo.modificar_limite_srv("160000.00", "BLOQUEAR")],
        )

        if errores:
            assert _nombres(errores) == [CREDITO_EXCEDIDO], f"{resultados}, errores={errores}"
            assert mundo.cantidad_de("venta") == 0
        else:
            ((limite, exceso, resolucion, _),) = mundo.ventas()
            assert (limite, exceso, resolucion) == (
                Decimal("190000.00"),
                Decimal("0.00"),
                "SIN_EXCESO",
            )
        ((limite_final,),) = mundo.leer(
            "SELECT limite_credito FROM cliente WHERE organizacion_id = :o AND id = :c",
            c=e.cliente_id,
        )
        assert limite_final == Decimal("160000.00")
        mundo.verificar_libros()


# --- descuentos: venta y pausa de la regla --------------------------------------------------


class TestDescuentoAutomaticoConcurrente:
    """DSC-09, D11, D18: las reglas se leen sin bloqueo; la comparación hace visible el cambio."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_dsc09_venta_y_pausa_de_la_regla_o_lleva_el_descuento_o_difiere_nunca_mezclado(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        mundo = _Mundo(database_url)
        regla_id: list[UUID] = []
        mundo.armar(lambda e: regla_id.append(e.crear_regla(umbral="1")))
        e = mundo.entorno
        contenido = e.contenido(
            e.linea(
                descuentos=[
                    {
                        "origen": "AUTOMATICO",
                        "regla_id": str(regla_id[0]),
                        "porcentaje": "0.050000",
                        "importe": "1562.50",
                    }
                ]
            ),
            total="29687.50",
        )

        resultados, errores = _en_paralelo(
            database_url, [mundo.vender(contenido), mundo.pausar_srv(regla_id[0])]
        )

        if errores:
            assert _nombres(errores) == [DESCUENTO_DIFIERE], f"{resultados}, errores={errores}"
            assert mundo.cantidad_de("venta") == 0
            assert mundo.descuentos() == 0
        else:
            ((_, _, _, total),) = mundo.ventas()
            assert total == Decimal("29687.50")
            assert mundo.descuentos("AUTOMATICO") == 1
        ((estado,),) = mundo.leer(
            "SELECT estado FROM regla_descuento WHERE organizacion_id = :o AND id = :r",
            r=regla_id[0],
        )
        assert estado == "PAUSADA"
        mundo.verificar_libros()


# --- PIN: venta frente a la rotación y a "Mi PIN" del autorizador -----------------------------


class TestPinDelAutorizadorConcurrente:
    """SEG-05, ADR-011: la venta valida el PIN anterior o el nuevo, nunca una mezcla."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_seg05_venta_y_rotacion_del_pin_validan_con_el_anterior_o_con_el_nuevo(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        mundo = _Mundo(database_url)
        marta = mundo.supervisor(frozenset({"AUTORIZAR_DESCUENTO"}))
        contenido = mundo.venta_con_general(autorizador=marta)

        resultados, errores = _en_paralelo(
            database_url,
            [
                mundo.vender(contenido, mundo.credencial(marta, PIN)),
                mundo.rotar_pin_srv(marta, PIN_NUEVO),
            ],
        )

        if errores:
            assert _nombres(errores) == [PIN_INCORRECTO], f"{resultados}, errores={errores}"
            assert mundo.cantidad_de("venta") == 0
            assert mundo.fallos_de_pin() == 1
        else:
            assert mundo.cantidad_de("venta") == 1
            assert mundo.fallos_de_pin() == 0
        assert mundo.pin_vigente(marta, (PIN, PIN_NUEVO)) == [PIN_NUEVO]
        mundo.verificar_libros()

    def test_seg05_orden_forzado_el_pin_anterior_vale_hasta_que_la_rotacion_confirma(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """La verificación lee lo confirmado: mientras la rotación no confirma, el PIN anterior
        sigue valiendo. Cuando confirma, ya no."""
        mundo = _Mundo(database_url)
        marta = mundo.supervisor(frozenset({"AUTORIZAR_DESCUENTO"}))
        contenido = mundo.venta_con_general(autorizador=marta)

        primero, segundo = _encadenado(
            database_url,
            mundo.rotar_pin_srv(marta, PIN_NUEVO),
            mundo.vender(contenido, mundo.credencial(marta, PIN)),
        )

        assert (primero, segundo) == (OK, OK)
        assert mundo.cantidad_de("venta") == 1
        assert mundo.pin_vigente(marta, (PIN, PIN_NUEVO)) == [PIN_NUEVO]

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_seg05_venta_y_mi_pin_del_autorizador_validan_con_el_anterior_o_con_el_nuevo(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        mundo = _Mundo(database_url)
        marta = mundo.supervisor(frozenset({"AUTORIZAR_DESCUENTO"}), con_clave=True)
        contenido = mundo.venta_con_general(autorizador=marta)

        resultados, errores = _en_paralelo(
            database_url,
            [
                mundo.vender(contenido, mundo.credencial(marta, PIN)),
                mundo.mi_pin_srv(marta, PIN_NUEVO),
            ],
        )

        if errores:
            assert _nombres(errores) == [PIN_INCORRECTO], f"{resultados}, errores={errores}"
            assert mundo.cantidad_de("venta") == 0
        else:
            assert mundo.cantidad_de("venta") == 1
        assert mundo.pin_vigente(marta, (PIN, PIN_NUEVO)) == [PIN_NUEVO]
        mundo.verificar_libros()

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_seg05_dos_mi_pin_simultaneos_del_mismo_usuario_dejan_entero_uno_de_los_dos(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        mundo = _Mundo(database_url)
        marta = mundo.supervisor(frozenset({"AUTORIZAR_DESCUENTO"}), con_clave=True)
        otro_pin = "264801"

        resultados, errores = _en_paralelo(
            database_url, [mundo.mi_pin_srv(marta, PIN_NUEVO), mundo.mi_pin_srv(marta, otro_pin)]
        )

        assert not errores, f"{resultados}, errores={errores}"
        vigentes = mundo.pin_vigente(marta, (PIN, PIN_NUEVO, otro_pin))
        assert len(vigentes) == 1
        assert vigentes[0] in (PIN_NUEVO, otro_pin)
        # Una fila marcador por cada definición (el PIN inicial de la siembra suma otra).
        assert mundo.cantidad_de("intento_pin_autorizacion", "exito") == 3


# --- PIN: contadores exactos --------------------------------------------------------------------


class TestContadoresDelPinConcurrentes:
    """SEG-04, D3 revisada: el contador del par y el tope general llegan exactos, aun con los
    intentos a la vez (el candado por autorizador los serializa)."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_seg04_cinco_ventas_a_la_vez_con_el_pin_incorrecto_llegan_exactas_al_bloqueo_del_par(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        mundo = _Mundo(database_url)
        marta = mundo.supervisor(frozenset({"AUTORIZAR_DESCUENTO"}))
        malo = mundo.credencial(marta, PIN_MALO)
        trabajos = [
            mundo.vender(mundo.venta_con_general(autorizador=marta), malo) for _ in range(5)
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not resultados, f"{resultados}"
        assert _nombres(errores) == [PIN_INCORRECTO] * 5
        assert mundo.fallos_de_pin() == 5
        assert mundo.bloqueos_de_pin() == ["USUARIO"]
        assert mundo.cantidad_de("venta") == 0
        # Bloqueado: ni el PIN correcto sirve, y el intento bloqueado no cuenta.
        sesion = _sesion_independiente(database_url)
        try:
            with pytest.raises(PinBloqueadoError):
                mundo.enviar_con(
                    sesion,
                    mundo.venta_con_general(autorizador=marta),
                    mundo.credencial(marta, PIN),
                )
        finally:
            sesion.close()
        assert mundo.fallos_de_pin() == 5
        assert mundo.bloqueos_de_pin() == ["USUARIO"]

    @pytest.mark.parametrize("repeticion", range(2))
    def test_seg04_siete_intentos_a_la_vez_cinco_se_cuentan_y_dos_chocan_con_el_bloqueo(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        mundo = _Mundo(database_url)
        marta = mundo.supervisor(frozenset({"AUTORIZAR_DESCUENTO"}))
        malo = mundo.credencial(marta, PIN_MALO)
        trabajos = [
            mundo.vender(mundo.venta_con_general(autorizador=marta), malo) for _ in range(7)
        ]

        _, errores = _en_paralelo(database_url, trabajos)

        assert _nombres(errores) == sorted([PIN_INCORRECTO] * 5 + [PIN_BLOQUEADO] * 2)
        assert mundo.fallos_de_pin() == 5
        assert mundo.bloqueos_de_pin() == ["USUARIO"]

    def test_seg04_otro_vendedor_sigue_autorizando_con_el_pin_de_la_supervisora_bloqueada_al_par(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        mundo = _Mundo(database_url)
        marta = mundo.supervisor(frozenset({"AUTORIZAR_DESCUENTO"}))
        malo = mundo.credencial(marta, PIN_MALO)
        _en_paralelo(
            database_url,
            [mundo.vender(mundo.venta_con_general(autorizador=marta), malo) for _ in range(5)],
        )
        juan, dispositivo_de_juan, prefijo = mundo.vendedor()
        sesion = _sesion_independiente(database_url)
        try:
            mundo.enviar_con(
                sesion,
                mundo.venta_de_otro(prefijo, autorizador=marta),
                mundo.credencial(marta, PIN),
                usuario_id=juan,
                dispositivo_id=dispositivo_de_juan,
            )
        finally:
            sesion.close()

        assert mundo.cantidad_de("venta") == 1
        (descuento,) = mundo.leer(
            "SELECT autorizador_id FROM venta_linea_descuento WHERE organizacion_id = :o"
        )
        assert descuento[0] == marta

    def test_seg04_veinte_intentos_de_cuatro_vendedores_llegan_exactos_al_tope_general(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        mundo = _Mundo(database_url)
        marta = mundo.supervisor(frozenset({"AUTORIZAR_DESCUENTO"}))
        malo = mundo.credencial(marta, PIN_MALO)
        vendedores = [mundo.vendedor() for _ in range(4)]
        trabajos = [
            mundo.vender(
                mundo.venta_de_otro(prefijo, autorizador=marta),
                malo,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
            )
            for usuario_id, dispositivo_id, prefijo in vendedores
            for _ in range(5)
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not resultados, f"{resultados}"
        assert _nombres(errores) == [PIN_INCORRECTO] * 20
        assert mundo.fallos_de_pin() == 20
        # Cada vendedor llega a su límite (5) y el vigésimo fallo alcanza el tope general (20).
        assert mundo.bloqueos_de_pin() == ["GENERAL", "USUARIO", "USUARIO", "USUARIO", "USUARIO"]
        # Bloqueada para todos: un quinto vendedor con el PIN correcto choca con el bloqueo.
        pedro, dispositivo_de_pedro, prefijo = mundo.vendedor()
        sesion = _sesion_independiente(database_url)
        try:
            with pytest.raises(PinBloqueadoError):
                mundo.enviar_con(
                    sesion,
                    mundo.venta_de_otro(prefijo, autorizador=marta),
                    mundo.credencial(marta, PIN),
                    usuario_id=pedro,
                    dispositivo_id=dispositivo_de_pedro,
                )
        finally:
            sesion.close()
        # Definir un PIN nuevo reinicia los dos contadores y desbloquea para todos.
        sesion = _sesion_independiente(database_url)
        try:
            mundo.rotar_pin_srv(marta, PIN_NUEVO, DESPUES_DE_LA_VENTA)(sesion)
            sesion.commit()
        finally:
            sesion.close()
        sesion = _sesion_independiente(database_url)
        try:
            mundo.enviar_con(
                sesion,
                mundo.venta_de_otro(prefijo, autorizador=marta),
                mundo.credencial(marta, PIN_NUEVO),
                usuario_id=pedro,
                dispositivo_id=dispositivo_de_pedro,
            )
        finally:
            sesion.close()
        assert mundo.cantidad_de("venta") == 1


# --- INV-06 ------------------------------------------------------------------------------------


class TestDobleEnvioConDescuentoYPin:
    """INV-06: el mismo comando con descuento autorizado por PIN, enviado dos veces a la vez,
    deja un solo efecto y el PIN no deja fallos."""

    @pytest.mark.parametrize("repeticion", range(REPETICIONES))
    def test_inv06_dos_ventas_con_el_mismo_operation_id_dejan_un_solo_efecto(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        mundo = _Mundo(database_url)
        marta = mundo.supervisor(frozenset({"AUTORIZAR_DESCUENTO"}))
        contenido = mundo.venta_con_general(autorizador=marta)
        operation_id = uuid4()
        credencial = mundo.credencial(marta, PIN)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: (
                mundo.enviar_con(sesion, contenido, credencial, operation_id=operation_id).resultado
            ),
            lambda sesion: (
                mundo.enviar_con(sesion, contenido, credencial, operation_id=operation_id).resultado
            ),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, f"{resultados}, errores={errores}"
        assert resultados[0] == resultados[1]
        assert mundo.cantidad_de("venta") == 1
        assert mundo.descuentos("MANUAL") == 1
        assert mundo.cantidad_de("cuenta_movimiento", "tipo = 'VENTA'") == 1
        assert mundo.fallos_de_pin() == 0
        assert mundo.saldo_de_la_cuenta() == Decimal("178750.00")
        mundo.verificar_libros()
