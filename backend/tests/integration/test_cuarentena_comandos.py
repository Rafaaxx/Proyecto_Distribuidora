"""Cuarentena de comandos de dispositivos revocados (change 04, grupo 8,
tareas 8.7-8.9; spec `sync/cuarentena-de-comandos`, SYN-06).

`test_inv05_comando_sin_delete.py` (grupo 2, tarea 2.9) ya cubre "La
aplicación no puede borrar un registro de cuarentena": no se repite acá.
PostgreSQL real (`db_session`, `docs/02` §15).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands import catalogo, registro
from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.models import Organizacion
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, ComandoCuarentena
from app.modules.sync.service import ItemLote

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


class _EsquemaPrueba(BaseModel):
    resultado: str = "ACEPTADO"


def _handler_prueba(
    sobre: object, contenido: _EsquemaPrueba
) -> tuple[str, dict[str, object] | None, str | None]:
    return "ACEPTADO", {}, None


@pytest.fixture(autouse=True)
def _catalogo_y_registro_aislados(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})
    monkeypatch.setattr("app.commands.registro._REGISTRO", {})
    catalogo.declarar_tipo("PRUEBA_CUARENTENA", admite_online=True, admite_offline=True)
    registro.registrar_handler("PRUEBA_CUARENTENA", 1, _EsquemaPrueba)(_handler_prueba)


def _crear_organizacion(sesion: Session, *, slug: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba cuarentena",
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


def _crear_usuario_y_dispositivo(
    sesion: Session, organizacion_id: UUID, *, dispositivo_revocado: bool = False
) -> tuple[UUID, UUID]:
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
    dispositivo_id = nuevo_id()
    identidad_repository.crear_dispositivo(
        organizacion_id,
        sesion,
        dispositivo_id=dispositivo_id,
        nombre="Dispositivo de prueba",
        prefijo=f"P{uuid4().hex[:2]}",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    sesion.flush()
    if dispositivo_revocado:
        identidad_service.revocar_dispositivo(
            organizacion_id,
            sesion,
            FixedClock(MOMENTO),
            dispositivo_id=dispositivo_id,
            actor_id=usuario.id,
        )
    return usuario.id, dispositivo_id


def _contar_comandos(sesion: Session, operation_id: UUID) -> int:
    return sesion.scalar(
        select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
    )


def _contar_cuarentena(sesion: Session, operation_id: UUID) -> int:
    return sesion.scalar(
        select(func.count())
        .select_from(ComandoCuarentena)
        .where(ComandoCuarentena.operation_id == operation_id)
    )


def _obtener_cuarentena(sesion: Session, operation_id: UUID) -> ComandoCuarentena | None:
    return sesion.scalars(
        select(ComandoCuarentena).where(ComandoCuarentena.operation_id == operation_id)
    ).one_or_none()


def _item(
    *, usuario_id: UUID, dispositivo_id: UUID, secuencia: int, operation_id: UUID | None = None
) -> ItemLote:
    return ItemLote(
        operation_id=operation_id or uuid4(),
        tipo="PRUEBA_CUARENTENA",
        version=1,
        modo="ONLINE",
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=secuencia,
        app_version="1.0.0",
        contenido={"resultado": "ACEPTADO", "nota": "contenido completo de prueba"},
    )


class TestComandoDeDispositivoRevocado:
    """Tareas 8.7 y 8.8."""

    def test_no_produce_efectos_de_negocio(self, db_session: Session) -> None:
        """Escenario "El comando de un dispositivo revocado no produce
        efectos"."""
        organizacion = _crear_organizacion(db_session, slug=f"org-cuar-1-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(
            db_session, organizacion.id, dispositivo_revocado=True
        )
        db_session.commit()

        item = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=1)

        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item],
        )

        assert resultados[0].estado == "RECHAZADO"
        assert _contar_comandos(db_session, item.operation_id) == 0

    def test_queda_en_cuarentena_con_su_contenido_completo(self, db_session: Session) -> None:
        """Escenario "El comando rechazado queda en cuarentena con su
        contenido completo"."""
        organizacion = _crear_organizacion(db_session, slug=f"org-cuar-2-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(
            db_session, organizacion.id, dispositivo_revocado=True
        )
        db_session.commit()

        item = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=1)

        sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item],
        )

        registro_cuarentena = _obtener_cuarentena(db_session, item.operation_id)
        assert registro_cuarentena is not None
        assert registro_cuarentena.tipo == "PRUEBA_CUARENTENA"
        assert registro_cuarentena.contenido == item.contenido
        assert registro_cuarentena.motivo == "DISPOSITIVO_REVOCADO"

    def test_la_cuarentena_sobrevive_al_rechazo_de_la_operacion(self, db_session: Session) -> None:
        """Escenario "La cuarentena sobrevive al rechazo de la operación":
        aunque el comando en sí NUNCA llega a `comando` (se rechaza antes de
        la reserva de idempotencia, `02` §6.3 paso 1), el registro de
        cuarentena -- confirmado en su propia transacción, D6 -- persiste de
        forma independiente de esa ausencia."""
        organizacion = _crear_organizacion(db_session, slug=f"org-cuar-3-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(
            db_session, organizacion.id, dispositivo_revocado=True
        )
        db_session.commit()

        item = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=1)

        sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item],
        )

        assert _contar_comandos(db_session, item.operation_id) == 0
        assert _contar_cuarentena(db_session, item.operation_id) == 1

    def test_un_lote_entero_de_un_dispositivo_revocado_queda_en_cuarentena(
        self, db_session: Session
    ) -> None:
        """Escenario "Un lote entero de un dispositivo revocado queda en
        cuarentena"."""
        organizacion = _crear_organizacion(db_session, slug=f"org-cuar-4-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(
            db_session, organizacion.id, dispositivo_revocado=True
        )
        db_session.commit()

        items = [
            _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=i) for i in range(1, 4)
        ]

        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=items,
        )

        assert len(resultados) == 3
        assert all(r.estado == "RECHAZADO" for r in resultados)
        for item in items:
            assert _contar_cuarentena(db_session, item.operation_id) == 1

    def test_el_reenvio_de_un_comando_ya_en_cuarentena_no_lo_duplica(
        self, db_session: Session
    ) -> None:
        """Escenario "El reenvío de un comando ya puesto en cuarentena no lo
        duplica"."""
        organizacion = _crear_organizacion(db_session, slug=f"org-cuar-5-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(
            db_session, organizacion.id, dispositivo_revocado=True
        )
        db_session.commit()

        operation_id = uuid4()
        item = _item(
            usuario_id=usuario, dispositivo_id=dispositivo, secuencia=1, operation_id=operation_id
        )

        primero = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item],
        )
        reenvio = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item],
        )

        assert primero[0].estado == "RECHAZADO"
        assert reenvio[0].estado == "RECHAZADO"
        assert _contar_cuarentena(db_session, operation_id) == 1


class TestAislamientoYNoBorrado:
    """Tarea 8.9. ("La aplicación no puede borrar" ya está cubierto por
    `test_inv05_comando_sin_delete.py`, grupo 2)."""

    def test_la_cuarentena_de_otra_organizacion_no_es_alcanzable(self, db_session: Session) -> None:
        """Escenario "La cuarentena de otra organización no es alcanzable"
        (INV-02, INV-21, TR-08)."""
        organizacion_a = _crear_organizacion(db_session, slug=f"org-cuar-a-{uuid4().hex[:8]}")
        organizacion_b = _crear_organizacion(db_session, slug=f"org-cuar-b-{uuid4().hex[:8]}")
        usuario_a, dispositivo_a = _crear_usuario_y_dispositivo(
            db_session, organizacion_a.id, dispositivo_revocado=True
        )
        db_session.commit()

        item = _item(usuario_id=usuario_a, dispositivo_id=dispositivo_a, secuencia=1)
        sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion_a.id,
            usuario_id=usuario_a,
            dispositivo_id=dispositivo_a,
            items=[item],
        )

        consulta_desde_b = sesion_scoped_a_organizacion(db_session, organizacion_b.id)
        assert item.operation_id not in {registro.operation_id for registro in consulta_desde_b}


def sesion_scoped_a_organizacion(sesion: Session, organizacion_id: UUID) -> list[ComandoCuarentena]:
    """Simula la consulta que cualquier `repository`/`service` de negocio
    haría, siempre filtrando por `organizacion_id` (`CLAUDE.md` §4: "Toda
    consulta lo filtra. Sin excepciones")."""
    return list(
        sesion.scalars(
            select(ComandoCuarentena).where(ComandoCuarentena.organizacion_id == organizacion_id)
        )
    )
