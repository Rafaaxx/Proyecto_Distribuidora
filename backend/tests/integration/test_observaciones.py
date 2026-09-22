"""Observaciones (change 04, grupo 9, tareas 9.1-9.4, 9.6;
`docs/02-arquitectura.md` §6.3, spec `sync/observaciones`, SYN-04, SYN-07,
SYN-08, INV-01, INV-02, INV-21).

Dos niveles de prueba, mismo criterio que los grupos 6 y 8:

- A nivel de `sync_service.procesar_comando` (handlers que reciben la
  sesión directamente, mismo patrón que `test_bus_transaccion.py`): para
  ejercer el mecanismo de registro y su reversión transaccional sin
  depender del registro de handlers real.
- A nivel de `sync_service.procesar_lote` con un tipo de comando registrado
  en `app.commands.catalogo`/`app.commands.registro` (mismo patrón que
  `test_bus_lote_sincronizacion.py`): para ejercer la integración real de
  la tarea 9.5, donde `_procesar_item_de_lote` extrae las observaciones del
  resultado de un handler de verdad.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands import catalogo, registro
from app.commands.errores import CodigoDeObservacionInvalidoError
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Organizacion, Usuario
from app.modules.sync import repository as sync_repository
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote, ObservacionProducida

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


def _crear_organizacion(sesion: Session, *, slug: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba observaciones",
        slug=slug,
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
    return organizacion


def _crear_usuario_y_dispositivo(sesion: Session, organizacion_id: UUID) -> tuple[UUID, UUID]:
    rol = identidad_repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Vendedor",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    usuario = identidad_repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=f"vendedor-{uuid4().hex[:8]}",
        nombre="Persona de prueba",
        email=None,
        password_hash="hash",
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    dispositivo = identidad_repository.crear_dispositivo(
        organizacion_id,
        sesion,
        dispositivo_id=nuevo_id(),
        nombre="Dispositivo de prueba",
        prefijo=f"O{uuid4().hex[:2]}",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario.id, dispositivo.id


def _sobre(
    *, organizacion_id: UUID, usuario_id: UUID, dispositivo_id: UUID, operation_id: UUID
) -> SobreComando:
    return SobreComando(
        operation_id=operation_id,
        tipo="USUARIO_CREAR",
        version=1,
        modo="ONLINE",
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={},
    )


def _contar_comandos(sesion: Session, operation_id: UUID) -> int:
    return sesion.scalar(
        select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
    )


def _contar_observaciones_de(sesion: Session, comando_id: UUID) -> int:
    return sesion.scalar(
        select(func.count()).select_from(Observacion).where(Observacion.comando_id == comando_id)
    )


# --- Nivel `procesar_comando`: mecanismo directo -----------------------


class TestNacimientoDeUnaObservacion:
    """Tarea 9.1, escenarios "La observación queda asociada a su comando y
    a su operación" y "Un comando aceptado con observaciones lo refleja en
    su estado"."""

    def test_la_observacion_queda_asociada_a_su_comando_y_a_su_operacion(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-obs-9.1a-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()
        operacion_observada_id = uuid4()

        def _handler(sesion: object) -> sync_service.ResultadoHandler:
            comando_actual = sync_repository.obtener_comando_por_operation_id(
                sesion,  # type: ignore[arg-type]
                organizacion.id,
                operation_id,
            )
            assert comando_actual is not None
            sync_service.registrar_observacion(
                sesion,  # type: ignore[arg-type]
                comando_id=comando_actual.id,
                organizacion_id=organizacion.id,
                observacion=ObservacionProducida(
                    codigo="STOCK_NEGATIVO",
                    operacion_tipo="VENTA",
                    operacion_id=operacion_observada_id,
                    detalle={"cantidad_faltante": 3},
                ),
            )
            return "ACEPTADO_CON_OBSERVACIONES", {"ok": True}, None

        comando = sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-1",
            ejecutar_handler=_handler,
        )

        observacion = db_session.scalars(
            select(Observacion).where(Observacion.comando_id == comando.id)
        ).one()
        assert observacion.comando_id == comando.id
        assert observacion.operacion_tipo == "VENTA"
        assert observacion.operacion_id == operacion_observada_id
        assert observacion.estado == "PENDIENTE"
        assert observacion.codigo == "STOCK_NEGATIVO"
        assert observacion.detalle == {"cantidad_faltante": 3}

    def test_un_comando_aceptado_con_dos_observaciones_queda_aceptado_con_observaciones(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-obs-9.1b-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()

        def _handler(sesion: object) -> sync_service.ResultadoHandler:
            comando_actual = sync_repository.obtener_comando_por_operation_id(
                sesion,  # type: ignore[arg-type]
                organizacion.id,
                operation_id,
            )
            assert comando_actual is not None
            sync_service.registrar_observaciones(
                sesion,  # type: ignore[arg-type]
                comando_id=comando_actual.id,
                organizacion_id=organizacion.id,
                observaciones=(
                    ObservacionProducida(
                        codigo="STOCK_NEGATIVO", operacion_tipo="VENTA", operacion_id=uuid4()
                    ),
                    ObservacionProducida(
                        codigo="LISTA_NO_VIGENTE", operacion_tipo="VENTA", operacion_id=uuid4()
                    ),
                ),
            )
            return "ACEPTADO_CON_OBSERVACIONES", {}, None

        comando = sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-1",
            ejecutar_handler=_handler,
        )

        assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
        assert _contar_observaciones_de(db_session, comando.id) == 2


class TestObservacionesNegativas:
    """Tarea 9.2, escenarios "Un comando rechazado no deja observaciones" y
    "Las observaciones se revierten con el comando que falla"."""

    def test_un_comando_rechazado_no_deja_observaciones(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-obs-9.2a-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()

        comando = sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-1",
            ejecutar_handler=lambda _sesion: ("RECHAZADO", None, "REGLA_DE_NEGOCIO_INCUMPLIDA"),
        )

        assert comando.estado == "RECHAZADO"
        assert _contar_observaciones_de(db_session, comando.id) == 0

    def test_las_observaciones_se_revierten_con_el_comando_que_falla(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-obs-9.2b-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()

        def _handler_que_observa_y_despues_falla(sesion: object) -> sync_service.ResultadoHandler:
            comando_actual = sync_repository.obtener_comando_por_operation_id(
                sesion,  # type: ignore[arg-type]
                organizacion.id,
                operation_id,
            )
            assert comando_actual is not None
            sync_service.registrar_observacion(
                sesion,  # type: ignore[arg-type]
                comando_id=comando_actual.id,
                organizacion_id=organizacion.id,
                observacion=ObservacionProducida(
                    codigo="STOCK_NEGATIVO", operacion_tipo="VENTA", operacion_id=uuid4()
                ),
            )
            raise RuntimeError("una regla de negocio incumplida, simulada")

        with pytest.raises(RuntimeError, match="una regla de negocio incumplida"):
            sync_service.procesar_comando(
                db_session,
                FixedClock(MOMENTO),
                sobre=_sobre(
                    organizacion_id=organizacion.id,
                    usuario_id=usuario,
                    dispositivo_id=dispositivo,
                    operation_id=operation_id,
                ),
                huella="huella-1",
                ejecutar_handler=_handler_que_observa_y_despues_falla,
            )

        assert _contar_comandos(db_session, operation_id) == 0
        assert (
            db_session.scalar(select(func.count()).select_from(Observacion)) == 0
        )  # ninguna observación de ninguna organización sobrevivió: la única
        # que se intentó insertar se revirtió con la transacción entera.


class TestReenvioNoDuplicaObservaciones:
    """Tarea 9.3, escenario "El reenvío de un comando ya aceptado no
    duplica sus observaciones"."""

    def test_el_reenvio_de_un_comando_aceptado_no_duplica_sus_observaciones(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-obs-9.3-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()
        llamadas_al_handler = {"n": 0}

        def _handler(sesion: object) -> sync_service.ResultadoHandler:
            llamadas_al_handler["n"] += 1
            comando_actual = sync_repository.obtener_comando_por_operation_id(
                sesion,  # type: ignore[arg-type]
                organizacion.id,
                operation_id,
            )
            assert comando_actual is not None
            sync_service.registrar_observacion(
                sesion,  # type: ignore[arg-type]
                comando_id=comando_actual.id,
                organizacion_id=organizacion.id,
                observacion=ObservacionProducida(
                    codigo="STOCK_NEGATIVO", operacion_tipo="VENTA", operacion_id=uuid4()
                ),
            )
            return "ACEPTADO_CON_OBSERVACIONES", {}, None

        sobre = _sobre(
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            operation_id=operation_id,
        )
        primero = sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=sobre,
            huella="huella-1",
            ejecutar_handler=_handler,
        )
        segundo = sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=sobre,
            huella="huella-1",
            ejecutar_handler=_handler,
        )

        assert primero.id == segundo.id
        assert llamadas_al_handler["n"] == 1  # el reenvío no reejecuta el handler (SYN-02).
        assert _contar_observaciones_de(db_session, primero.id) == 1


class TestCatalogoDeCodigos:
    """Tarea 9.4, escenarios "Un código fuera del catálogo no se registra"
    y "La observación conserva el detalle del caso"."""

    def test_un_codigo_fuera_del_catalogo_no_se_registra(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-obs-9.4a-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()

        def _handler_con_codigo_invalido(sesion: object) -> sync_service.ResultadoHandler:
            comando_actual = sync_repository.obtener_comando_por_operation_id(
                sesion,  # type: ignore[arg-type]
                organizacion.id,
                operation_id,
            )
            assert comando_actual is not None
            sync_service.registrar_observacion(
                sesion,  # type: ignore[arg-type]
                comando_id=comando_actual.id,
                organizacion_id=organizacion.id,
                observacion=ObservacionProducida(
                    codigo="CODIGO_QUE_NO_EXISTE", operacion_tipo="VENTA", operacion_id=uuid4()
                ),
            )
            return "ACEPTADO", {}, None

        with pytest.raises(CodigoDeObservacionInvalidoError):
            sync_service.procesar_comando(
                db_session,
                FixedClock(MOMENTO),
                sobre=_sobre(
                    organizacion_id=organizacion.id,
                    usuario_id=usuario,
                    dispositivo_id=dispositivo,
                    operation_id=operation_id,
                ),
                huella="huella-1",
                ejecutar_handler=_handler_con_codigo_invalido,
            )

        assert _contar_comandos(db_session, operation_id) == 0
        assert db_session.scalar(select(func.count()).select_from(Observacion)) == 0

    def test_la_observacion_conserva_el_detalle_del_caso(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-obs-9.4b-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        operation_id = uuid4()
        detalle_esperado = {"tope_credito": "50000.00", "saldo_actual": "62500.00"}

        def _handler(sesion: object) -> sync_service.ResultadoHandler:
            comando_actual = sync_repository.obtener_comando_por_operation_id(
                sesion,  # type: ignore[arg-type]
                organizacion.id,
                operation_id,
            )
            assert comando_actual is not None
            sync_service.registrar_observacion(
                sesion,  # type: ignore[arg-type]
                comando_id=comando_actual.id,
                organizacion_id=organizacion.id,
                observacion=ObservacionProducida(
                    codigo="EXCESO_CREDITO_DETECTADO_SYNC",
                    operacion_tipo="VENTA",
                    operacion_id=uuid4(),
                    detalle=detalle_esperado,
                ),
            )
            return "ACEPTADO_CON_OBSERVACIONES", {}, None

        comando = sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-1",
            ejecutar_handler=_handler,
        )

        observacion = db_session.scalars(
            select(Observacion).where(Observacion.comando_id == comando.id)
        ).one()
        assert observacion.codigo == "EXCESO_CREDITO_DETECTADO_SYNC"
        assert observacion.detalle == detalle_esperado


class TestObservacionPendiente:
    """Tarea 9.6, escenarios "La observación no altera la operación
    observada" y "Las observaciones pendientes se consultan por
    organización y código"."""

    def test_la_observacion_no_altera_la_operacion_observada(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-obs-9.6a-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        usuario_observado = db_session.get(Usuario, usuario)
        assert usuario_observado is not None
        estado_antes = usuario_observado.estado
        nombre_antes = usuario_observado.nombre

        operation_id = uuid4()

        def _handler(sesion: object) -> sync_service.ResultadoHandler:
            comando_actual = sync_repository.obtener_comando_por_operation_id(
                sesion,  # type: ignore[arg-type]
                organizacion.id,
                operation_id,
            )
            assert comando_actual is not None
            sync_service.registrar_observacion(
                sesion,  # type: ignore[arg-type]
                comando_id=comando_actual.id,
                organizacion_id=organizacion.id,
                observacion=ObservacionProducida(
                    codigo="PERMISO_REVOCADO", operacion_tipo="USUARIO", operacion_id=usuario
                ),
            )
            return "ACEPTADO_CON_OBSERVACIONES", {}, None

        sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-1",
            ejecutar_handler=_handler,
        )

        db_session.expire_all()
        usuario_despues = db_session.get(Usuario, usuario)
        assert usuario_despues is not None
        assert usuario_despues.estado == estado_antes
        assert usuario_despues.nombre == nombre_antes

    def test_las_observaciones_pendientes_se_consultan_por_organizacion_y_codigo(
        self, db_session: Session
    ) -> None:
        organizacion_a = _crear_organizacion(db_session, slug=f"org-obs-9.6b-a-{uuid4().hex[:8]}")
        organizacion_b = _crear_organizacion(db_session, slug=f"org-obs-9.6b-b-{uuid4().hex[:8]}")
        usuario_a, dispositivo_a = _crear_usuario_y_dispositivo(db_session, organizacion_a.id)
        usuario_b, dispositivo_b = _crear_usuario_y_dispositivo(db_session, organizacion_b.id)
        db_session.commit()

        def _handler_con(
            codigo: str, organizacion_id: UUID, operation_id: UUID
        ) -> Callable[[object], sync_service.ResultadoHandler]:
            def _inner(sesion: object) -> sync_service.ResultadoHandler:
                comando_actual = sync_repository.obtener_comando_por_operation_id(
                    sesion,  # type: ignore[arg-type]
                    organizacion_id,
                    operation_id,
                )
                assert comando_actual is not None
                sync_service.registrar_observacion(
                    sesion,  # type: ignore[arg-type]
                    comando_id=comando_actual.id,
                    organizacion_id=organizacion_id,
                    observacion=ObservacionProducida(
                        codigo=codigo, operacion_tipo="VENTA", operacion_id=uuid4()
                    ),
                )
                return "ACEPTADO_CON_OBSERVACIONES", {}, None

            return _inner

        # Organización A: una pendiente con STOCK_NEGATIVO.
        op_a1 = uuid4()
        sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion_a.id,
                usuario_id=usuario_a,
                dispositivo_id=dispositivo_a,
                operation_id=op_a1,
            ),
            huella="huella-a1",
            ejecutar_handler=_handler_con("STOCK_NEGATIVO", organizacion_a.id, op_a1),
        )
        # Organización A: una pendiente con otro código -- no debe aparecer.
        op_a2 = uuid4()
        sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion_a.id,
                usuario_id=usuario_a,
                dispositivo_id=dispositivo_a,
                operation_id=op_a2,
            ),
            huella="huella-a2",
            ejecutar_handler=_handler_con("LISTA_NO_VIGENTE", organizacion_a.id, op_a2),
        )
        # Organización B: una pendiente con STOCK_NEGATIVO -- otra organización,
        # no debe aparecer en la consulta de A (INV-02, INV-21).
        op_b1 = uuid4()
        sync_service.procesar_comando(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion_b.id,
                usuario_id=usuario_b,
                dispositivo_id=dispositivo_b,
                operation_id=op_b1,
            ),
            huella="huella-b1",
            ejecutar_handler=_handler_con("STOCK_NEGATIVO", organizacion_b.id, op_b1),
        )

        pendientes_de_a = sync_repository.listar_observaciones_pendientes(
            db_session, organizacion_a.id, "STOCK_NEGATIVO"
        )

        assert len(pendientes_de_a) == 1
        assert pendientes_de_a[0].organizacion_id == organizacion_a.id
        assert pendientes_de_a[0].codigo == "STOCK_NEGATIVO"


# --- Nivel `procesar_lote`: integración real con un handler registrado ----


class _EsquemaPruebaObservacion(BaseModel):
    resultado: Literal["ACEPTADO", "RECHAZADO"] = "ACEPTADO"
    produce_observacion: bool = False


def _handler_prueba_observacion(
    sobre: SobreComando, contenido: _EsquemaPruebaObservacion
) -> sync_service.ResultadoHandler | sync_service.ResultadoHandlerConObservaciones:
    observaciones: tuple[ObservacionProducida, ...] = ()
    if contenido.produce_observacion:
        observaciones = (
            ObservacionProducida(
                codigo="STOCK_NEGATIVO", operacion_tipo="VENTA", operacion_id=uuid4()
            ),
        )
    if contenido.resultado == "RECHAZADO":
        # SYN-04: un handler no debería producir observaciones junto a un
        # rechazo, pero si lo hiciera (bug), no deben quedar registradas
        # (tarea 9.2) -- se ejercita literalmente ese caso acá.
        return "RECHAZADO", None, "RECHAZADO_DE_PRUEBA", observaciones
    if observaciones:
        return "ACEPTADO", {}, None, observaciones
    return "ACEPTADO", {}, None


@pytest.fixture(autouse=True)
def _catalogo_y_registro_aislados(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})
    monkeypatch.setattr("app.commands.registro._REGISTRO", {})
    catalogo.declarar_tipo("PRUEBA_OBSERVACION", admite_online=True, admite_offline=True)
    registro.registrar_handler("PRUEBA_OBSERVACION", 1, _EsquemaPruebaObservacion)(
        _handler_prueba_observacion
    )


def _item_observacion(
    *,
    usuario_id: UUID,
    dispositivo_id: UUID,
    secuencia: int,
    produce_observacion: bool,
    resultado: str = "ACEPTADO",
    operation_id: UUID | None = None,
) -> ItemLote:
    return ItemLote(
        operation_id=operation_id or uuid4(),
        tipo="PRUEBA_OBSERVACION",
        version=1,
        modo="ONLINE",
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=secuencia,
        app_version="1.0.0",
        contenido={"resultado": resultado, "produce_observacion": produce_observacion},
    )


class TestIntegracionRealConElBus:
    """Tarea 9.5: el registro de observaciones desde el resultado de un
    handler REAL, resuelto por `app.commands.registro` y ejecutado a
    través de `sync_service.procesar_lote` (no un doble directo, a
    diferencia de las demás clases de este archivo)."""

    def test_un_handler_que_produce_una_observacion_deja_el_comando_aceptado_con_observaciones(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-obs-lote-a-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        item = _item_observacion(
            usuario_id=usuario, dispositivo_id=dispositivo, secuencia=1, produce_observacion=True
        )
        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item],
        )

        assert resultados[0].estado == "ACEPTADO_CON_OBSERVACIONES"
        comando = db_session.scalars(
            select(Comando).where(Comando.operation_id == item.operation_id)
        ).one()
        assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
        assert _contar_observaciones_de(db_session, comando.id) == 1
        observacion = db_session.scalars(
            select(Observacion).where(Observacion.comando_id == comando.id)
        ).one()
        assert observacion.estado == "PENDIENTE"

    def test_un_handler_sin_observaciones_deja_el_comando_aceptado_simple(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-obs-lote-b-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        item = _item_observacion(
            usuario_id=usuario, dispositivo_id=dispositivo, secuencia=1, produce_observacion=False
        )
        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item],
        )

        assert resultados[0].estado == "ACEPTADO"
        comando = db_session.scalars(
            select(Comando).where(Comando.operation_id == item.operation_id)
        ).one()
        assert _contar_observaciones_de(db_session, comando.id) == 0

    def test_un_handler_rechazado_con_observaciones_no_las_deja_registradas(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-obs-lote-c-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        item = _item_observacion(
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            secuencia=1,
            produce_observacion=True,
            resultado="RECHAZADO",
        )
        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item],
        )

        assert resultados[0].estado == "RECHAZADO"
        comando = db_session.scalars(
            select(Comando).where(Comando.operation_id == item.operation_id)
        ).one()
        assert _contar_observaciones_de(db_session, comando.id) == 0
