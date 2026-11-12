"""Reserva de idempotencia de `comando` (change 04, grupo 5, INV-06,
`design.md` D3, `02` §6.3, ADR-012).

La garantía de unicidad de `operation_id` por organización vive en la base
(`UNIQUE (organizacion_id, operation_id)`, migración `f6a7b8c9d0e1`, tarea
2.1): estas pruebas confirman que la aplicación la usa sin una consulta
previa (`INSERT ... ON CONFLICT DO NOTHING`) y que el resto del contrato de
reenvío (SYN-02) se cumple sobre esa base. PostgreSQL real (Testcontainers,
`db_session`), nunca SQLite.

Alcance de este grupo, acotado a propósito (ver `tasks.md` grupo 5, D3): NO
se implementa acá la transacción completa de siete pasos ni los reintentos
transitorios (grupo 6) -- `procesar_idempotente` es un mecanismo mínimo que
reserva, ejecuta un callable arbitrario (`ejecutar_handler`, que en estas
pruebas es un doble de prueba, no un handler real de negocio) solo si la
reserva es nueva, y persiste el resultado. El grupo 6 lo envuelve en la
transacción real con reintentos.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Organizacion
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


def _crear_organizacion(sesion: Session, *, slug: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba INV-06",
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
        prefijo=f"P{uuid4().hex[:2]}",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario.id, dispositivo.id


def _sobre(
    *,
    organizacion_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
    contenido: dict[str, object] | None = None,
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
        contenido=contenido or {},
    )


def _contar_comandos_con_operation_id(sesion: Session, operation_id: UUID) -> int:
    return sesion.scalar(
        select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
    )


class TestDosOrganizaciones:
    def test_dos_organizaciones_pueden_usar_el_mismo_identificador_de_operacion(
        self, db_session: Session
    ) -> None:
        """Escenario "Dos organizaciones pueden usar el mismo identificador
        de operación" (INV-06, INV-21): el mismo `operation_id` en dos
        organizaciones distintas se procesa dos veces, una por cada una."""
        organizacion_a = _crear_organizacion(db_session, slug=f"org-a-{uuid4().hex[:8]}")
        organizacion_b = _crear_organizacion(db_session, slug=f"org-b-{uuid4().hex[:8]}")
        usuario_a, dispositivo_a = _crear_usuario_y_dispositivo(db_session, organizacion_a.id)
        usuario_b, dispositivo_b = _crear_usuario_y_dispositivo(db_session, organizacion_b.id)
        operation_id_compartido = uuid4()

        llamadas: list[str] = []

        def _handler() -> tuple[str, dict[str, object] | None, str | None]:
            llamadas.append("ejecutado")
            return "ACEPTADO", {"ok": True}, None

        comando_a = sync_service.procesar_idempotente(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion_a.id,
                usuario_id=usuario_a,
                dispositivo_id=dispositivo_a,
                operation_id=operation_id_compartido,
            ),
            huella="huella-1",
            ejecutar_handler=_handler,
        )
        comando_b = sync_service.procesar_idempotente(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion_b.id,
                usuario_id=usuario_b,
                dispositivo_id=dispositivo_b,
                operation_id=operation_id_compartido,
            ),
            huella="huella-1",
            ejecutar_handler=_handler,
        )

        assert comando_a.organizacion_id == organizacion_a.id
        assert comando_b.organizacion_id == organizacion_b.id
        assert comando_a.id != comando_b.id
        assert llamadas == ["ejecutado", "ejecutado"]
        assert _contar_comandos_con_operation_id(db_session, operation_id_compartido) == 2

    def test_la_misma_organizacion_no_puede_registrar_dos_veces_el_mismo_identificador(
        self, db_session: Session
    ) -> None:
        """Triangulación (contraparte dentro de la misma organización): un
        segundo reenvío del mismo `operation_id` en la MISMA organización
        no crea una segunda fila -- reutiliza la reserva existente."""
        organizacion = _crear_organizacion(db_session, slug=f"org-unica-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        operation_id = uuid4()

        def _handler() -> tuple[str, dict[str, object] | None, str | None]:
            return "ACEPTADO", {"ok": True}, None

        sync_service.procesar_idempotente(
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
        sync_service.procesar_idempotente(
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

        assert _contar_comandos_con_operation_id(db_session, operation_id) == 1


class TestReenvio:
    def test_reenvio_identico_devuelve_el_resultado_guardado_sin_reejecutar(
        self, db_session: Session
    ) -> None:
        """Escenario "Reenvío idéntico devuelve el resultado guardado"
        (SYN-02, INV-06)."""
        organizacion = _crear_organizacion(db_session, slug=f"org-reenvio-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        operation_id = uuid4()
        llamadas: list[str] = []

        def _handler() -> tuple[str, dict[str, object] | None, str | None]:
            llamadas.append("ejecutado")
            return "ACEPTADO", {"usuario_id": "abc123"}, None

        primero = sync_service.procesar_idempotente(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-contenido-1",
            ejecutar_handler=_handler,
        )
        reenvio = sync_service.procesar_idempotente(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-contenido-1",
            ejecutar_handler=_handler,
        )

        assert llamadas == ["ejecutado"]  # el handler NO se ejecutó una segunda vez
        assert reenvio.id == primero.id
        assert reenvio.estado == "ACEPTADO"
        assert reenvio.resultado == {"usuario_id": "abc123"}
        assert _contar_comandos_con_operation_id(db_session, operation_id) == 1

    def test_reenvio_de_un_comando_rechazado_devuelve_el_mismo_rechazo(
        self, db_session: Session
    ) -> None:
        """Escenario "Reenvío de un comando rechazado devuelve el mismo
        rechazo" (SYN-02, SYN-09)."""
        organizacion = _crear_organizacion(db_session, slug=f"org-rechazo-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        operation_id = uuid4()

        def _handler() -> tuple[str, dict[str, object] | None, str | None]:
            return "RECHAZADO", None, "USUARIO_YA_EXISTE"

        primero = sync_service.procesar_idempotente(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-rechazo",
            ejecutar_handler=_handler,
        )
        reenvio = sync_service.procesar_idempotente(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-rechazo",
            ejecutar_handler=_handler,
        )

        assert primero.estado == "RECHAZADO"
        assert primero.error_codigo == "USUARIO_YA_EXISTE"
        assert reenvio.estado == "RECHAZADO"
        assert reenvio.error_codigo == "USUARIO_YA_EXISTE"
        assert reenvio.id == primero.id

    def test_mismo_identificador_con_contenido_distinto_se_rechaza(
        self, db_session: Session
    ) -> None:
        """Escenario "Mismo identificador con contenido distinto se
        rechaza" (SYN-02, SYN-06): huella distinta -> `COMANDO_INCONSISTENTE`,
        y el resultado original queda intacto."""
        organizacion = _crear_organizacion(db_session, slug=f"org-inconsist-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        operation_id = uuid4()

        def _handler_original() -> tuple[str, dict[str, object] | None, str | None]:
            return "ACEPTADO", {"usuario_id": "original"}, None

        def _handler_que_no_deberia_ejecutarse() -> tuple[
            str, dict[str, object] | None, str | None
        ]:
            raise AssertionError("El handler no debe ejecutarse ante una huella inconsistente.")

        original = sync_service.procesar_idempotente(
            db_session,
            FixedClock(MOMENTO),
            sobre=_sobre(
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                operation_id=operation_id,
            ),
            huella="huella-original",
            ejecutar_handler=_handler_original,
        )

        with pytest.raises(ComandoInconsistenteError) as exc_info:
            sync_service.procesar_idempotente(
                db_session,
                FixedClock(MOMENTO),
                sobre=_sobre(
                    organizacion_id=organizacion.id,
                    usuario_id=usuario,
                    dispositivo_id=dispositivo,
                    operation_id=operation_id,
                ),
                huella="huella-distinta",
                ejecutar_handler=_handler_que_no_deberia_ejecutarse,
            )
        assert exc_info.value.codigo == "COMANDO_INCONSISTENTE"

        db_session.refresh(original)
        assert original.estado == "ACEPTADO"
        assert original.resultado == {"usuario_id": "original"}
        assert _contar_comandos_con_operation_id(db_session, operation_id) == 1
