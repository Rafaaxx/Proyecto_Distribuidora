"""Tareas 8.1 y 8.2: servicio de auditoría (AUD-02, TR-05, INV-01).

Sin `commit`: la transacción la gestiona quien llama (`02` §5.2); si esa
transacción se revierte, el registro de auditoría se revierte con ella
(INV-01, tarea 8.2).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.identidad import repository, service
from app.modules.identidad.models import Auditoria, Organizacion, RolPermiso

MOMENTO_EVENTO = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
MOMENTO_REGISTRO = MOMENTO_EVENTO + timedelta(seconds=3)


def _crear_organizacion(sesion: Session) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba",
        slug=f"org-{nuevo_id().hex[:12]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=MOMENTO_EVENTO,
        actualizado_en=MOMENTO_EVENTO,
        actualizado_por_id=None,
    )
    sesion.add(organizacion)
    sesion.flush()
    return organizacion


class TestRegistrarAuditoria:
    def test_un_evento_auditado_registra_sus_dos_momentos(self, db_session: Session) -> None:
        """Escenario "Un evento auditado registra sus dos momentos" (TR-05):
        `occurred_at` es el momento del evento; `registered_at` el del
        servidor al escribir, tomado de `core/clock.py`."""
        organizacion = _crear_organizacion(db_session)
        reloj = FixedClock(MOMENTO_REGISTRO)

        registro = service.registrar_auditoria(
            organizacion.id,
            db_session,
            reloj,
            accion="INICIO_SESION",
            entidad="usuario",
            ocurrido_en=MOMENTO_EVENTO,
        )

        assert registro.occurred_at == MOMENTO_EVENTO
        assert registro.registered_at == MOMENTO_REGISTRO
        assert registro.occurred_at != registro.registered_at

    def test_un_cambio_de_valor_registra_el_antes_y_el_despues(self, db_session: Session) -> None:
        """Escenario "Un cambio de valor registra el antes y el después"."""
        organizacion = _crear_organizacion(db_session)
        reloj = FixedClock(MOMENTO_REGISTRO)

        registro = service.registrar_auditoria(
            organizacion.id,
            db_session,
            reloj,
            accion="MODIFICAR_ROL",
            entidad="rol",
            ocurrido_en=MOMENTO_EVENTO,
            antes={"tope_descuento": "0.100000"},
            despues={"tope_descuento": "0.150000"},
        )

        assert registro.antes == {"tope_descuento": "0.100000"}
        assert registro.despues == {"tope_descuento": "0.150000"}

    def test_un_evento_sin_cambio_de_valor_no_inventa_uno(self, db_session: Session) -> None:
        """Escenario "Un evento sin cambio de valor no inventa uno": sin
        pasar `antes`/`despues`, quedan `None`, no `{}`."""
        organizacion = _crear_organizacion(db_session)
        reloj = FixedClock(MOMENTO_REGISTRO)

        registro = service.registrar_auditoria(
            organizacion.id,
            db_session,
            reloj,
            accion="INICIO_SESION",
            entidad="usuario",
            ocurrido_en=MOMENTO_EVENTO,
        )

        assert registro.antes is None
        assert registro.despues is None


def test_si_la_operacion_auditada_falla_no_queda_registro_de_auditoria(
    db_session: Session,
) -> None:
    """Escenario "Si la operación auditada falla, no queda registro de
    auditoría". Cita INV-01: una operación de negocio se registra completa
    o no se registra -- el registro de auditoría de una operación que
    fallara junto con ella tiene que desaparecer con el mismo rollback."""
    organizacion = _crear_organizacion(db_session)
    reloj = FixedClock(MOMENTO_REGISTRO)

    punto_de_guardado = db_session.begin_nested()
    try:
        service.registrar_auditoria(
            organizacion.id,
            db_session,
            reloj,
            accion="MODIFICAR_ROL",
            entidad="rol",
            ocurrido_en=MOMENTO_EVENTO,
        )
        # Simula que la operación de negocio que este evento acompaña falla
        # dentro de la misma transacción (acá, una FK compuesta violada):
        # referencia un rol y un permiso que no existen.
        db_session.add(
            RolPermiso(
                organizacion_id=organizacion.id,
                rol_id=nuevo_id(),
                permiso_codigo="PERMISO_INEXISTENTE",
            )
        )
        db_session.flush()
    except IntegrityError:
        punto_de_guardado.rollback()
    else:
        pytest.fail("Se esperaba que la FK compuesta de RolPermiso fallara.")

    cantidad = db_session.execute(
        select(func.count())
        .select_from(Auditoria)
        .where(Auditoria.organizacion_id == organizacion.id)
    ).scalar_one()
    assert cantidad == 0


class TestAislamientoDeAuditoriaEntreOrganizaciones:
    """Tarea 12.5, escenario "Un registro de auditoría pertenece a una
    organización" (spec `registro-de-auditoria`): un evento auditado en la
    organización A no aparece al consultar por la organización B. No hay
    endpoint de lectura de auditoría en este change (ningún escenario de
    este grupo lo exige, YAGNI -- mismo criterio que 8.9/10.7), así que la
    prueba consulta directamente la tabla filtrando por `organizacion_id`,
    que es la única fuente que cualquier lectura futura podría usar
    (`03` §4, INV-02). Regla: INV-02, INV-21, TR-08."""

    def test_un_registro_de_auditoria_de_una_organizacion_no_aparece_en_otra(
        self, db_session: Session
    ) -> None:
        organizacion_a = _crear_organizacion(db_session)
        organizacion_b = _crear_organizacion(db_session)
        reloj = FixedClock(MOMENTO_REGISTRO)

        service.registrar_auditoria(
            organizacion_a.id,
            db_session,
            reloj,
            accion="INICIO_SESION",
            entidad="usuario",
            ocurrido_en=MOMENTO_EVENTO,
        )
        service.registrar_auditoria(
            organizacion_b.id,
            db_session,
            reloj,
            accion="INICIO_SESION",
            entidad="usuario",
            ocurrido_en=MOMENTO_EVENTO,
        )

        registros_de_b = (
            db_session.execute(
                select(Auditoria).where(Auditoria.organizacion_id == organizacion_b.id)
            )
            .scalars()
            .all()
        )

        assert len(registros_de_b) == 1
        assert all(r.organizacion_id == organizacion_b.id for r in registros_de_b)
        assert all(r.organizacion_id != organizacion_a.id for r in registros_de_b)

    def test_dos_organizaciones_auditan_el_mismo_tipo_de_evento_sin_mezclarse(
        self, db_session: Session
    ) -> None:
        """Triangulación (distinto caso: varios eventos por organización,
        no solo uno) -- el conteo por organización se mantiene exacto
        incluso cuando ambas generan el mismo tipo de evento varias veces."""
        organizacion_a = _crear_organizacion(db_session)
        organizacion_b = _crear_organizacion(db_session)
        reloj = FixedClock(MOMENTO_REGISTRO)

        for _ in range(3):
            service.registrar_auditoria(
                organizacion_a.id,
                db_session,
                reloj,
                accion="CAMBIAR_COMPOSICION_ROL",
                entidad="rol",
                ocurrido_en=MOMENTO_EVENTO,
            )
        service.registrar_auditoria(
            organizacion_b.id,
            db_session,
            reloj,
            accion="CAMBIAR_COMPOSICION_ROL",
            entidad="rol",
            ocurrido_en=MOMENTO_EVENTO,
        )

        cantidad_a = db_session.execute(
            select(func.count())
            .select_from(Auditoria)
            .where(Auditoria.organizacion_id == organizacion_a.id)
        ).scalar_one()
        cantidad_b = db_session.execute(
            select(func.count())
            .select_from(Auditoria)
            .where(Auditoria.organizacion_id == organizacion_b.id)
        ).scalar_one()

        assert cantidad_a == 3
        assert cantidad_b == 1


class TestUnRegistroDeAuditoriaNoContieneSecretos:
    """Escenario "Un registro de auditoría no contiene secretos" (spec
    `registro-de-auditoria`): distinto de la tarea 7.5
    (`test_secretos_no_se_registran.py`), que inspecciona los REGISTROS DE
    LOG de una petición HTTP -- acá se inspecciona el contenido de la FILA
    de `auditoria` que cada operación deja en la base, para un alta de
    usuario (contraseña), una rotación de PIN (PIN) y un inicio de sesión
    (contraseña y tokens), citando `02` §17."""

    def _crear_organizacion(self, sesion: Session) -> Organizacion:
        return _crear_organizacion(sesion)

    def _crear_actor(self, sesion: Session, organizacion_id) -> object:
        rol_actor = repository.crear_rol(
            organizacion_id,
            sesion,
            rol_id=nuevo_id(),
            nombre="Actor de prueba",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO_EVENTO,
        )
        return repository.crear_usuario(
            organizacion_id,
            sesion,
            usuario_id=nuevo_id(),
            usuario=f"actor-{nuevo_id().hex[:8]}",
            nombre="Actor de prueba",
            email=None,
            password_hash="hash-de-prueba",
            rol_id=rol_actor.id,
            estado="ACTIVO",
            momento=MOMENTO_EVENTO,
        )

    def _filas_de(self, sesion: Session, organizacion_id) -> list[Auditoria]:
        return list(
            sesion.execute(select(Auditoria).where(Auditoria.organizacion_id == organizacion_id))
            .scalars()
            .all()
        )

    def _texto_de_las_filas(self, filas: list[Auditoria]) -> str:
        partes: list[str] = []
        for fila in filas:
            partes.append(fila.accion)
            partes.append(fila.entidad)
            partes.append(fila.observacion or "")
            partes.append(str(fila.antes) if fila.antes is not None else "")
            partes.append(str(fila.despues) if fila.despues is not None else "")
        return "\n".join(partes)

    def test_el_alta_de_un_usuario_no_expone_la_contrasena_en_la_auditoria(
        self, db_session: Session
    ) -> None:
        organizacion = self._crear_organizacion(db_session)
        actor = self._crear_actor(db_session, organizacion.id)
        rol = repository.crear_rol(
            organizacion.id,
            db_session,
            rol_id=nuevo_id(),
            nombre="Vendedor",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO_EVENTO,
        )
        contrasena = "contrasena-distintiva-de-auditoria-321"

        service.crear_usuario(
            organizacion.id,
            db_session,
            FixedClock(MOMENTO_REGISTRO),
            usuario="vendedor-auditado",
            nombre="Vendedor Auditado",
            email=None,
            password=contrasena,
            rol_id=rol.id,
            actor_id=actor.id,
        )

        texto = self._texto_de_las_filas(self._filas_de(db_session, organizacion.id))
        assert contrasena not in texto

    def test_la_rotacion_de_pin_no_expone_el_pin_en_la_auditoria(self, db_session: Session) -> None:
        organizacion = self._crear_organizacion(db_session)
        rol = repository.crear_rol(
            organizacion.id,
            db_session,
            rol_id=nuevo_id(),
            nombre="Supervisor",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO_EVENTO,
        )
        repository.asignar_permiso_a_rol(
            organizacion.id, db_session, rol_id=rol.id, permiso_codigo="AUTORIZAR_DESCUENTO"
        )
        supervisor = repository.crear_usuario(
            organizacion.id,
            db_session,
            usuario_id=nuevo_id(),
            usuario="supervisor-auditado",
            nombre="Supervisor Auditado",
            email=None,
            password_hash="hash-de-prueba",
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO_EVENTO,
        )
        pin = "739284"

        service.establecer_pin_autorizacion(
            organizacion.id,
            db_session,
            FixedClock(MOMENTO_REGISTRO),
            usuario_id=supervisor.id,
            pin=pin,
            actor_id=supervisor.id,
        )

        texto = self._texto_de_las_filas(self._filas_de(db_session, organizacion.id))
        assert pin not in texto

    def test_un_inicio_de_sesion_no_expone_la_contrasena_ni_los_tokens_en_la_auditoria(
        self, db_session: Session
    ) -> None:
        organizacion = self._crear_organizacion(db_session)
        rol = repository.crear_rol(
            organizacion.id,
            db_session,
            rol_id=nuevo_id(),
            nombre="Vendedor",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO_EVENTO,
        )
        contrasena = "contrasena-de-login-distintiva-555"
        from app.core.seguridad import hashear_password

        repository.crear_usuario(
            organizacion.id,
            db_session,
            usuario_id=nuevo_id(),
            usuario="vendedor-login-auditado",
            nombre="Vendedor Auditado",
            email=None,
            password_hash=hashear_password(contrasena),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO_EVENTO,
        )

        resultado = service.iniciar_sesion(
            db_session,
            FixedClock(MOMENTO_REGISTRO),
            organizacion_slug=organizacion.slug,
            nombre_usuario="vendedor-login-auditado",
            password=contrasena,
            dispositivo_id=nuevo_id(),
            nombre_dispositivo="Dispositivo de prueba",
            jwt_secreto="secreto-de-prueba-suficientemente-largo",
            jwt_kid="1",
            ip="127.0.0.1",
        )

        texto = self._texto_de_las_filas(self._filas_de(db_session, organizacion.id))
        assert contrasena not in texto
        assert resultado.access_token not in texto
        assert resultado.refresh_token not in texto


class TestOrigenDeAuditoria:
    """Grupo 10 (change 04, tareas 10.2, 10.3): `auditoria.origen`
    distingue un evento generado por el bus de comandos (`COMANDO`, con
    `operation_id` obligatorio) de uno generado fuera de él (`SISTEMA`,
    sin `operation_id`), con la restricción de verificación
    `ck_auditoria__operation_id_segun_origen` (migración `f6a7b8c9d0e1`)
    exigiéndolo en la base, no solo en la aplicación."""

    def test_un_registro_de_origen_comando_sin_operation_id_no_llega_a_la_base(
        self, db_session: Session
    ) -> None:
        """Escenario "Un registro de origen comando sin identificador de
        operación no llega a la base": el INSERT directo con
        `origen='COMANDO'` y `operation_id=None` viola el CHECK de la base
        (no una validación de Python -- por eso se espera `IntegrityError`,
        no un `DomainError`)."""
        organizacion = _crear_organizacion(db_session)

        with pytest.raises(IntegrityError):
            repository.crear_auditoria(
                organizacion.id,
                db_session,
                auditoria_id=nuevo_id(),
                accion="INICIO_SESION",
                entidad="usuario",
                occurred_at=MOMENTO_EVENTO,
                registered_at=MOMENTO_REGISTRO,
                origen="COMANDO",
                operation_id=None,
            )
        db_session.rollback()

    def test_un_registro_de_origen_sistema_con_operation_id_no_llega_a_la_base(
        self, db_session: Session
    ) -> None:
        """Triangulación (10.2): el CHECK es una equivalencia, no una
        implicación en un solo sentido -- `origen='SISTEMA'` con
        `operation_id` presente también lo viola."""
        organizacion = _crear_organizacion(db_session)

        with pytest.raises(IntegrityError):
            repository.crear_auditoria(
                organizacion.id,
                db_session,
                auditoria_id=nuevo_id(),
                accion="INICIO_SESION",
                entidad="usuario",
                occurred_at=MOMENTO_EVENTO,
                registered_at=MOMENTO_REGISTRO,
                origen="SISTEMA",
                operation_id=nuevo_id(),
            )
        db_session.rollback()

    def test_el_inicio_de_sesion_sigue_auditado_con_origen_sistema_y_sin_operation_id(
        self, db_session: Session
    ) -> None:
        """Escenario "El inicio de sesión sigue auditado y sin
        identificador de operación": `iniciar_sesion` (change 03) declara
        `origen='SISTEMA'` explícitamente (tarea 10.5), sin depender del
        `server_default` silencioso de la columna."""
        organizacion = _crear_organizacion(db_session)
        rol = repository.crear_rol(
            organizacion.id,
            db_session,
            rol_id=nuevo_id(),
            nombre="Vendedor",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO_EVENTO,
        )
        contrasena = "contrasena-de-prueba-origen-999"
        from app.core.seguridad import hashear_password

        repository.crear_usuario(
            organizacion.id,
            db_session,
            usuario_id=nuevo_id(),
            usuario="vendedor-origen-sistema",
            nombre="Vendedor de prueba",
            email=None,
            password_hash=hashear_password(contrasena),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO_EVENTO,
        )

        service.iniciar_sesion(
            db_session,
            FixedClock(MOMENTO_REGISTRO),
            organizacion_slug=organizacion.slug,
            nombre_usuario="vendedor-origen-sistema",
            password=contrasena,
            dispositivo_id=nuevo_id(),
            nombre_dispositivo="Dispositivo de prueba",
            jwt_secreto="secreto-de-prueba-suficientemente-largo",
            jwt_kid="1",
            ip="127.0.0.1",
        )

        filas = list(
            db_session.execute(
                select(Auditoria).where(
                    Auditoria.organizacion_id == organizacion.id,
                    Auditoria.accion == "INICIO_SESION",
                )
            )
            .scalars()
            .all()
        )
        assert len(filas) == 1
        assert filas[0].origen == "SISTEMA"
        assert filas[0].operation_id is None
