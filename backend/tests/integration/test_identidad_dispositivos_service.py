"""Tareas 8.10 (registro/listado/revocación de dispositivos), 8.11 (último
correlativo) y 8.12 (el prefijo lo asigna el servidor).

Alcance de esta sesión: el REGISTRO de un dispositivo ocurre, por spec,
"en su primer inicio de sesión" (SEG-02) -- la parte de login está
bloqueada (ver el resumen de la sesión: cómo el endpoint de login resuelve
`organizacion_id` antes de que exista un token es un vacío de decisión no
cubierto por `docs/`/ADRs). Estas pruebas ejercitan `registrar_dispositivo`
como una función de servicio independiente (la usará el servicio de login
una vez resuelto ese vacío) y el resto de las operaciones de dispositivo,
que no dependen del login.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import CorrelativoNoAvanzaError
from app.modules.identidad.models import Auditoria, Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


def _crear_organizacion(sesion: Session, nombre: str = "Organización de prueba") -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre=nombre,
        slug=f"org-{nuevo_id().hex[:12]}",
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


def _crear_actor(sesion: Session, organizacion_id) -> object:
    """Un usuario cualquiera de `organizacion_id`, porque `auditoria.usuario_id`
    y `sesion_refresh.usuario_id` tienen FK compuesta a `usuario` (no
    aceptan un UUID que no exista)."""
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Actor de prueba",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    usuario = repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=f"actor-{nuevo_id().hex[:8]}",
        nombre="Actor de prueba",
        email=None,
        password_hash="hash-de-prueba",
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario.id


class TestIdentificadorDeDispositivoEntreOrganizaciones:
    """Corrección de esquema descubierta al implementar 8.3 (`03` §4:
    `dispositivo.id` lo genera el dispositivo, no el servidor; migración
    `d4e5f6a7b8c9`, PK compuesta). Escenario "Un identificador de
    dispositivo de otra organización no se reutiliza"."""

    def test_el_mismo_dispositivo_id_puede_registrarse_en_dos_organizaciones(
        self, db_session: Session
    ) -> None:
        dispositivo_id_compartido = nuevo_id()
        org_a = _crear_organizacion(db_session, "Organización A")
        org_b = _crear_organizacion(db_session, "Organización B")

        dispositivo_a = identidad_service.registrar_dispositivo(
            org_a.id, db_session, RELOJ, dispositivo_id=dispositivo_id_compartido, nombre="Tablet A"
        )
        dispositivo_b = identidad_service.registrar_dispositivo(
            org_b.id, db_session, RELOJ, dispositivo_id=dispositivo_id_compartido, nombre="Tablet B"
        )

        assert dispositivo_a.id == dispositivo_b.id == dispositivo_id_compartido
        # Son dos filas distintas: cada una con su propio prefijo, ninguna
        # alcanzable desde la organización de la otra (INV-21).
        assert dispositivo_a.prefijo == dispositivo_b.prefijo == "V01"
        assert (
            identidad_service.registrar_o_reutilizar_dispositivo(
                org_a.id, db_session, RELOJ, dispositivo_id=dispositivo_id_compartido, nombre="x"
            ).nombre
            == "Tablet A"
        )
        assert (
            identidad_service.registrar_o_reutilizar_dispositivo(
                org_b.id, db_session, RELOJ, dispositivo_id=dispositivo_id_compartido, nombre="x"
            ).nombre
            == "Tablet B"
        )

    def test_registrar_o_reutilizar_reutiliza_si_ya_existe_en_la_organizacion(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        dispositivo_id = nuevo_id()
        primero = identidad_service.registrar_o_reutilizar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=dispositivo_id, nombre="Tablet"
        )

        segundo = identidad_service.registrar_o_reutilizar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=dispositivo_id, nombre="Tablet"
        )

        assert segundo.id == primero.id
        assert segundo.prefijo == primero.prefijo


class TestRegistrarDispositivoYPrefijo:
    def test_un_dispositivo_recien_registrado_arranca_sin_correlativo_consumido(
        self, db_session: Session
    ) -> None:
        """Escenario "Un dispositivo recién registrado arranca sin
        correlativo consumido"."""
        organizacion = _crear_organizacion(db_session)

        dispositivo = identidad_service.registrar_dispositivo(
            organizacion.id,
            db_session,
            RELOJ,
            dispositivo_id=nuevo_id(),
            nombre="Tablet de reparto",
        )

        assert dispositivo.ultimo_correlativo == 0
        assert dispositivo.estado == "ACTIVO"

    def test_el_prefijo_lo_asigna_el_servidor(self, db_session: Session) -> None:
        """Escenario "El prefijo lo asigna el servidor": el prefijo que
        informa el dispositivo se ignora."""
        organizacion = _crear_organizacion(db_session)

        dispositivo = identidad_service.registrar_dispositivo(
            organizacion.id,
            db_session,
            RELOJ,
            dispositivo_id=nuevo_id(),
            nombre="Tablet de reparto",
            prefijo_informado_por_dispositivo="LO-QUE-SEA",
        )

        assert dispositivo.prefijo != "LO-QUE-SEA"

    def test_dos_dispositivos_de_la_misma_organizacion_reciben_prefijos_distintos(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)

        d1 = identidad_service.registrar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=nuevo_id(), nombre="Tablet 1"
        )
        d2 = identidad_service.registrar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=nuevo_id(), nombre="Tablet 2"
        )

        assert d1.prefijo != d2.prefijo


class TestAvanzarCorrelativo:
    def test_el_ultimo_correlativo_no_retrocede(self, db_session: Session) -> None:
        """Escenario "El último correlativo no retrocede"."""
        organizacion = _crear_organizacion(db_session)
        dispositivo = identidad_service.registrar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=nuevo_id(), nombre="Tablet"
        )
        identidad_service.avanzar_correlativo_dispositivo(
            organizacion.id, db_session, dispositivo_id=dispositivo.id, propuesto=5
        )

        with pytest.raises(CorrelativoNoAvanzaError):
            identidad_service.avanzar_correlativo_dispositivo(
                organizacion.id, db_session, dispositivo_id=dispositivo.id, propuesto=5
            )
        with pytest.raises(CorrelativoNoAvanzaError):
            identidad_service.avanzar_correlativo_dispositivo(
                organizacion.id, db_session, dispositivo_id=dispositivo.id, propuesto=3
            )

        actualizado = repository.obtener_dispositivo_por_id(
            organizacion.id, dispositivo.id, db_session
        )
        assert actualizado is not None
        assert actualizado.ultimo_correlativo == 5

    def test_avanzar_correlativo_a_un_numero_mayor_lo_actualiza(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        dispositivo = identidad_service.registrar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=nuevo_id(), nombre="Tablet"
        )

        identidad_service.avanzar_correlativo_dispositivo(
            organizacion.id, db_session, dispositivo_id=dispositivo.id, propuesto=1
        )
        identidad_service.avanzar_correlativo_dispositivo(
            organizacion.id, db_session, dispositivo_id=dispositivo.id, propuesto=2
        )

        actualizado = repository.obtener_dispositivo_por_id(
            organizacion.id, dispositivo.id, db_session
        )
        assert actualizado is not None
        assert actualizado.ultimo_correlativo == 2


class TestListarYRevocarDispositivos:
    def test_el_listado_incluye_los_revocados(self, db_session: Session) -> None:
        """Escenario "El listado incluye los revocados"."""
        organizacion = _crear_organizacion(db_session)
        activo = identidad_service.registrar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=nuevo_id(), nombre="Activo"
        )
        a_revocar = identidad_service.registrar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=nuevo_id(), nombre="A revocar"
        )
        actor_id = _crear_actor(db_session, organizacion.id)
        identidad_service.revocar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=a_revocar.id, actor_id=actor_id
        )

        listado = identidad_service.listar_dispositivos(organizacion.id, db_session)

        ids = {d.id for d in listado}
        assert activo.id in ids
        assert a_revocar.id in ids

    def test_revocar_un_dispositivo_invalida_sus_refresh_tokens(self, db_session: Session) -> None:
        """Escenario "Revocar un dispositivo invalida sus refresh tokens"."""
        organizacion = _crear_organizacion(db_session)
        dispositivo = identidad_service.registrar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=nuevo_id(), nombre="Tablet"
        )
        actor_id = _crear_actor(db_session, organizacion.id)
        sesion_refresh = repository.crear_sesion_refresh(
            organizacion.id,
            db_session,
            sesion_refresh_id=nuevo_id(),
            usuario_id=actor_id,
            dispositivo_id=dispositivo.id,
            token_hash="hash-de-token",
            familia_id=nuevo_id(),
            emitido_en=MOMENTO,
            expira_en=MOMENTO,
        )
        assert sesion_refresh.revocado_en is None

        identidad_service.revocar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=dispositivo.id, actor_id=actor_id
        )

        db_session.refresh(sesion_refresh)
        assert sesion_refresh.revocado_en == MOMENTO
        assert sesion_refresh.motivo_revocacion == "DISPOSITIVO_REVOCADO"

    def test_un_dispositivo_revocado_no_puede_volver_a_iniciar_sesion(
        self, db_session: Session
    ) -> None:
        """Escenario "Un dispositivo revocado no puede volver a iniciar
        sesión" -- a este nivel (sin login todavía), se verifica que el
        estado queda `REVOCADO`, la condición que el servicio de login
        (bloqueado) va a usar para rechazar."""
        organizacion = _crear_organizacion(db_session)
        dispositivo = identidad_service.registrar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=nuevo_id(), nombre="Tablet"
        )
        actor_id = _crear_actor(db_session, organizacion.id)

        identidad_service.revocar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=dispositivo.id, actor_id=actor_id
        )

        actualizado = repository.obtener_dispositivo_por_id(
            organizacion.id, dispositivo.id, db_session
        )
        assert actualizado is not None
        assert actualizado.estado == "REVOCADO"
        assert actualizado.revocado_en == MOMENTO

    def test_revocar_un_dispositivo_ya_revocado_no_cambia_nada(self, db_session: Session) -> None:
        """Escenario "Revocar un dispositivo ya revocado no cambia nada"."""
        organizacion = _crear_organizacion(db_session)
        dispositivo = identidad_service.registrar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=nuevo_id(), nombre="Tablet"
        )
        actor_id = _crear_actor(db_session, organizacion.id)
        identidad_service.revocar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=dispositivo.id, actor_id=actor_id
        )
        revocado_en_primera_vez = repository.obtener_dispositivo_por_id(
            organizacion.id, dispositivo.id, db_session
        ).revocado_en  # type: ignore[union-attr]

        identidad_service.revocar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=dispositivo.id, actor_id=actor_id
        )

        actualizado = repository.obtener_dispositivo_por_id(
            organizacion.id, dispositivo.id, db_session
        )
        assert actualizado is not None
        assert actualizado.revocado_en == revocado_en_primera_vez
        auditorias = (
            db_session.query(Auditoria)
            .filter_by(
                organizacion_id=organizacion.id, entidad="dispositivo", accion="REVOCAR_DISPOSITIVO"
            )
            .all()
        )
        assert len(auditorias) == 1  # no un segundo registro por el no-op.

    def test_la_revocacion_queda_auditada(self, db_session: Session) -> None:
        """Escenario "La revocación queda auditada"."""
        organizacion = _crear_organizacion(db_session)
        dispositivo = identidad_service.registrar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=nuevo_id(), nombre="Tablet"
        )
        actor_id = _crear_actor(db_session, organizacion.id)

        identidad_service.revocar_dispositivo(
            organizacion.id, db_session, RELOJ, dispositivo_id=dispositivo.id, actor_id=actor_id
        )

        auditoria = (
            db_session.query(Auditoria)
            .filter_by(
                organizacion_id=organizacion.id, entidad="dispositivo", accion="REVOCAR_DISPOSITIVO"
            )
            .one()
        )
        assert auditoria.entidad_id == dispositivo.id
        assert auditoria.usuario_id == actor_id
