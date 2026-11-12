"""Grupo 11 (`ADR-018`): rate limit de login por usuario y por IP.

Tareas 11.2 (conteo con los umbrales del ADR), 11.3 (propiedades que no
dependen de los valores concretos: aislamiento entre usuarios, no revela
existencia, queda auditado) y 11.4 (desbloqueo automático al vencer la
ventana; el desbloqueo manual está en `test_identidad_desbloqueo_manual_service.py`).

La prueba de "uniforme entre procesos" (11.2) que ejercita conexiones
realmente independientes vive en `tests/concurrency/
test_rate_limit_login_concurrencia.py` (Testcontainers, sin mocks); acá se
prueba la lógica de conteo/umbral con `db_session` (una sola transacción,
suficiente para la lógica de negocio en sí).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.clave_intento import clave_de_intento_login
from app.modules.identidad.domain.usuarios import (
    CredencialesInvalidasError,
    LoginBloqueadoPorIntentosError,
)
from app.modules.identidad.models import Auditoria, IntentoLogin, Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRETO = "secreto-de-prueba"
JWT_KID = "1"


def _crear_organizacion(sesion: Session, slug: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba",
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


def _crear_usuario(sesion: Session, organizacion_id, nombre_usuario: str) -> object:
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre=f"Vendedor {nuevo_id()}",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    return repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=nombre_usuario,
        nombre="Persona de prueba",
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )


def _login(
    sesion: Session,
    *,
    reloj,
    organizacion_slug: str,
    nombre_usuario: str,
    password: str = PASSWORD,
    ip: str = "10.0.0.1",
):
    return identidad_service.iniciar_sesion(
        sesion,
        reloj,
        organizacion_slug=organizacion_slug,
        nombre_usuario=nombre_usuario,
        password=password,
        dispositivo_id=nuevo_id(),
        nombre_dispositivo="Tablet de reparto",
        jwt_secreto=JWT_SECRETO,
        jwt_kid=JWT_KID,
        ip=ip,
    )


class TestLimitePorUsuario:
    def test_5_intentos_fallidos_bloquean_al_usuario(self, db_session: Session) -> None:
        """Escenario homónimo de `ADR-018`: 5 intentos fallidos en la
        ventana bloquean, incluso con la contraseña correcta en el sexto."""
        organizacion = _crear_organizacion(db_session, "org-rl-1")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")

        for _ in range(5):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario.usuario,
                    password="mal",
                )

        with pytest.raises(LoginBloqueadoPorIntentosError):
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,  # correcta: el bloqueo igual rechaza.
            )

    def test_4_intentos_fallidos_todavia_no_bloquean(self, db_session: Session) -> None:
        """Triangulación: un intento menos que el umbral no bloquea."""
        organizacion = _crear_organizacion(db_session, "org-rl-2")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")

        for _ in range(4):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario.usuario,
                    password="mal",
                )

        resultado = _login(
            db_session,
            reloj=FixedClock(MOMENTO),
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
        )
        assert resultado.usuario_id == usuario.id


class TestLimitePorIp:
    def test_20_intentos_fallidos_por_ip_bloquean_aunque_sean_de_usuarios_distintos(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-rl-3")
        usuarios = [_crear_usuario(db_session, organizacion.id, f"vendedor{i}") for i in range(4)]

        for i in range(20):
            usuario = usuarios[i % len(usuarios)]
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario.usuario,
                    password="mal",
                    ip="10.0.0.99",
                )

        with pytest.raises(LoginBloqueadoPorIntentosError):
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuarios[0].usuario,
                password=PASSWORD,
                ip="10.0.0.99",
            )


class TestPropiedadesIndependientesDelValor:
    def test_un_usuario_bloqueado_no_penaliza_a_otro(self, db_session: Session) -> None:
        """Escenario "Un inicio de sesión exitoso no queda penalizado por
        intentos de otro usuario"."""
        organizacion = _crear_organizacion(db_session, "org-rl-4")
        usuario_a = _crear_usuario(db_session, organizacion.id, "usuario_a")
        usuario_b = _crear_usuario(db_session, organizacion.id, "usuario_b")

        for _ in range(5):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario_a.usuario,
                    password="mal",
                    ip="10.0.0.1",
                )

        # Usuario B, desde OTRA dirección de origen: no está bloqueado.
        resultado = _login(
            db_session,
            reloj=FixedClock(MOMENTO),
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario_b.usuario,
            password=PASSWORD,
            ip="10.0.0.2",
        )
        assert resultado.usuario_id == usuario_b.id

    def test_el_bloqueo_no_revela_si_el_usuario_existe(self, db_session: Session) -> None:
        """Escenario "El bloqueo por intentos no revela si el usuario
        existe": agotar el límite por IP con un usuario inexistente produce
        el mismo error, con el mismo código, que agotarlo contra uno real."""
        organizacion = _crear_organizacion(db_session, "org-rl-5")
        _crear_usuario(db_session, organizacion.id, "usuario_real")

        for i in range(20):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    # Nombres distintos: con el mismo nombre escrito el sexto fallo ya se
                    # bloquea por par (ADR-057) antes de llegar al límite por IP.
                    nombre_usuario=f"no-existe-ningun-usuario-asi-{i}",
                    password="mal",
                    ip="10.0.0.50",
                )

        with pytest.raises(LoginBloqueadoPorIntentosError) as excinfo_inexistente:
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario="no-existe-ningun-usuario-asi",
                password="mal",
                ip="10.0.0.50",
            )

        with pytest.raises(LoginBloqueadoPorIntentosError) as excinfo_real:
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario="usuario_real",
                password=PASSWORD,
                ip="10.0.0.50",
            )

        assert excinfo_inexistente.value.codigo == excinfo_real.value.codigo
        assert str(excinfo_inexistente.value) == str(excinfo_real.value)

    def test_un_bloqueo_por_intentos_queda_auditado(self, db_session: Session) -> None:
        """Escenario "Un bloqueo por intentos queda auditado"."""
        organizacion = _crear_organizacion(db_session, "org-rl-6")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")

        for _ in range(5):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario.usuario,
                    password="mal",
                    ip="10.0.0.7",
                )
        with pytest.raises(LoginBloqueadoPorIntentosError):
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                ip="10.0.0.7",
            )

        auditorias = (
            db_session.query(Auditoria)
            .filter_by(
                organizacion_id=organizacion.id,
                accion="LOGIN_BLOQUEADO_POR_INTENTOS",
            )
            .all()
        )
        assert len(auditorias) == 1
        assert auditorias[0].usuario_id == usuario.id


class TestDesbloqueoAutomatico:
    def test_desbloqueo_automatico_al_vencer_la_ventana(self, db_session: Session) -> None:
        """Escenario homónimo (tarea 11.4): pasados los 15 minutos, los
        intentos fallidos anteriores dejan de contar."""
        organizacion = _crear_organizacion(db_session, "org-rl-7")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")

        for _ in range(5):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=FixedClock(MOMENTO),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario.usuario,
                    password="mal",
                    ip="10.0.0.8",
                )
        with pytest.raises(LoginBloqueadoPorIntentosError):
            _login(
                db_session,
                reloj=FixedClock(MOMENTO),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                ip="10.0.0.8",
            )

        momento_futuro = MOMENTO + timedelta(minutes=16)
        resultado = _login(
            db_session,
            reloj=FixedClock(momento_futuro),
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            ip="10.0.0.8",
        )
        assert resultado.usuario_id == usuario.id


DIEZ = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def _a(hora: int, minuto: int) -> FixedClock:
    return FixedClock(DIEZ.replace(hour=hora, minute=minuto))


def _filas(sesion: Session, **filtro) -> int:
    return sesion.query(IntentoLogin).filter_by(**filtro).count()


def _fallar(sesion, organizacion, nombre, minutos, ip, password="mal") -> None:
    for minuto in minutos:
        with pytest.raises(CredencialesInvalidasError):
            _login(
                sesion,
                reloj=_a(10, minuto),
                organizacion_slug=organizacion.slug,
                nombre_usuario=nombre,
                password=password,
                ip=ip,
            )


class TestBloqueoDesdeElUltimoFallo:
    """`design.md` D24 (enmienda a ADR-018): el bloqueo dura 15 minutos desde el ULTIMO fallo y un
    intento bloqueado no cuenta ni se inserta en `intento_login`."""

    def test_cinco_fallos_bloquean_hasta_el_ultimo_mas_15_minutos_sin_fila_nueva(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-d24-1")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")
        _fallar(db_session, organizacion, usuario.usuario, (2, 5, 7, 9, 10), "10.24.0.1")
        antes = _filas(db_session, usuario_id=usuario.id)

        # 10:20: el fallo mas antiguo (10:02) ya salio de los 15 minutos, pero rige el ultimo.
        with pytest.raises(LoginBloqueadoPorIntentosError) as bloqueado:
            _login(
                db_session,
                reloj=_a(10, 20),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                ip="10.24.0.1",
            )
        # 10:25 UTC es 07:25 en Mendoza (zona de la organizacion), sin segundos ni offset.
        assert str(bloqueado.value) == "Demasiados intentos. Probá de nuevo a las 07:25."
        assert _filas(db_session, usuario_id=usuario.id) == antes

        # Insistir durante el bloqueo no lo extiende: a las 10:25 entra.
        with pytest.raises(LoginBloqueadoPorIntentosError):
            _login(
                db_session,
                reloj=_a(10, 24),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password="mal",
                ip="10.24.0.1",
            )
        resultado = _login(
            db_session,
            reloj=_a(10, 25),
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            ip="10.24.0.1",
        )
        assert resultado.usuario_id == usuario.id

    def test_un_fallo_pasado_el_bloqueo_es_el_primero_de_su_ventana(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-d24-2")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")
        _fallar(db_session, organizacion, usuario.usuario, (2, 5, 7, 9, 10), "10.24.0.2")
        _fallar(db_session, organizacion, usuario.usuario, (26,), "10.24.0.2")
        # Un solo fallo en su ventana: no hay bloqueo.
        resultado = _login(
            db_session,
            reloj=_a(10, 27),
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            ip="10.24.0.2",
        )
        assert resultado.usuario_id == usuario.id

    def test_el_limite_por_ip_rige_igual_desde_el_ultimo_fallo(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, "org-d24-3")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")
        for i in range(20):
            _fallar(db_session, organizacion, f"no-existe-{i}", (min(i, 10),), "10.24.0.3")
        antes = _filas(db_session, ip="10.24.0.3")
        with pytest.raises(LoginBloqueadoPorIntentosError) as bloqueado:
            _login(
                db_session,
                reloj=_a(10, 20),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                ip="10.24.0.3",
            )
        # 10:25 UTC es 07:25 en Mendoza (zona de la organizacion), sin segundos ni offset.
        assert str(bloqueado.value) == "Demasiados intentos. Probá de nuevo a las 07:25."
        assert _filas(db_session, ip="10.24.0.3") == antes
        resultado = _login(
            db_session,
            reloj=_a(10, 25),
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            ip="10.24.0.3",
        )
        assert resultado.usuario_id == usuario.id

    def test_el_desbloqueo_manual_reinicia_solo_el_limite_por_usuario(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-d24-4")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")
        actor = _crear_usuario(db_session, organizacion.id, "admin1")
        _fallar(db_session, organizacion, usuario.usuario, (2, 5, 7, 9, 10), "10.24.0.4")
        identidad_service.desbloquear_usuario(
            organizacion.id, db_session, _a(10, 12), usuario_id=usuario.id, actor_id=actor.id
        )
        resultado = _login(
            db_session,
            reloj=_a(10, 13),
            organizacion_slug=organizacion.slug,
            nombre_usuario=usuario.usuario,
            password=PASSWORD,
            ip="10.24.0.4",
        )
        assert resultado.usuario_id == usuario.id

    def test_el_bloqueo_por_usuario_sigue_auditado_en_cada_intento_bloqueado(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-d24-5")
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")
        _fallar(db_session, organizacion, usuario.usuario, (2, 5, 7, 9, 10), "10.24.0.5")
        for minuto in (11, 12):
            with pytest.raises(LoginBloqueadoPorIntentosError):
                _login(
                    db_session,
                    reloj=_a(10, minuto),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario=usuario.usuario,
                    password=PASSWORD,
                    ip="10.24.0.5",
                )
        auditorias = (
            db_session.query(Auditoria)
            .filter_by(organizacion_id=organizacion.id, accion="LOGIN_BLOQUEADO_POR_INTENTOS")
            .count()
        )
        assert auditorias == 2


class TestMensajeDeBloqueoLegible:
    """El 429 dice la hora de desbloqueo en HH:MM. Con el bloqueo por usuario usa la zona de la
    organización; el bloqueo por IP (que se evalúa antes de resolver organización o usuario) usa
    SIEMPRE la zona por defecto `America/Argentina/Buenos_Aires`, así el texto no revela si la
    organización o el usuario existen (ADR-018 3b: el mensaje no revela datos)."""

    def test_slug_inexistente_con_bloqueo_por_ip_usa_la_hora_de_la_zona_por_defecto(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-msg-1")
        for i in range(20):
            _fallar(db_session, organizacion, f"no-existe-{i}", (10,), "10.25.0.1")
        with pytest.raises(LoginBloqueadoPorIntentosError) as bloqueado:
            _login(
                db_session,
                reloj=_a(10, 20),
                organizacion_slug="slug-que-no-existe",
                nombre_usuario="nadie",
                password="mal",
                ip="10.25.0.1",
            )
        # 10:25 UTC es 07:25 en Buenos Aires (UTC-3), sin segundos ni offset.
        assert str(bloqueado.value) == "Demasiados intentos. Probá de nuevo a las 07:25."
        assert bloqueado.value.codigo == "IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS"

    def test_el_bloqueo_por_ip_dice_lo_mismo_exista_o_no_la_organizacion_y_el_usuario(
        self, db_session: Session
    ) -> None:
        """Una organización real en otra zona (Tokio), un usuario real, un usuario inexistente
        y un slug inexistente: mismo texto, mismo código, misma clase de error."""
        organizacion = _crear_organizacion(db_session, "org-msg-3")
        organizacion.zona_horaria = "Asia/Tokyo"
        db_session.flush()
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor3")
        for i in range(20):
            _fallar(db_session, organizacion, f"no-existe-{i}", (10,), "10.25.0.3")
        casos = [
            (organizacion.slug, usuario.usuario),
            (organizacion.slug, "usuario-que-no-existe"),
            ("slug-que-no-existe", usuario.usuario),
            ("slug-que-no-existe", "usuario-que-no-existe"),
        ]
        respuestas = set()
        for slug, nombre in casos:
            with pytest.raises(LoginBloqueadoPorIntentosError) as bloqueado:
                _login(
                    db_session,
                    reloj=_a(10, 20),
                    organizacion_slug=slug,
                    nombre_usuario=nombre,
                    password=PASSWORD,
                    ip="10.25.0.3",
                )
            respuestas.add((str(bloqueado.value), bloqueado.value.codigo))
        assert respuestas == {
            (
                "Demasiados intentos. Probá de nuevo a las 07:25.",
                "IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS",
            )
        }

    def test_la_hora_del_login_no_depende_de_la_zona_de_la_organizacion(
        self, db_session: Session
    ) -> None:
        """Cambio del 2026-10-24 (ADR-057): el 429 del login, también el de un usuario real, sale
        siempre en `America/Argentina/Buenos_Aires` (antes usaba la zona de la organización)."""
        organizacion = _crear_organizacion(db_session, "org-msg-2")
        organizacion.zona_horaria = "Asia/Tokyo"  # UTC+9: 10:25 UTC serían las 19:25
        db_session.flush()
        usuario = _crear_usuario(db_session, organizacion.id, "vendedor1")
        _fallar(db_session, organizacion, usuario.usuario, (2, 5, 7, 9, 10), "10.25.0.2")
        with pytest.raises(LoginBloqueadoPorIntentosError) as bloqueado:
            _login(
                db_session,
                reloj=_a(10, 20),
                organizacion_slug=organizacion.slug,
                nombre_usuario=usuario.usuario,
                password=PASSWORD,
                ip="10.25.0.2",
            )
        assert str(bloqueado.value) == "Demasiados intentos. Probá de nuevo a las 07:25."


# --- ADR-057 (change 18b, tarea 24.4): el límite de 5 cuenta por el par escrito ------------------

TEXTO_DE_ARGENTINA = "Demasiados intentos. Probá de nuevo a las 07:25."  # 10:25 UTC, UTC-3


def _claves_de(sesion: Session, **filtro) -> list[str | None]:
    filas = sesion.query(IntentoLogin).filter_by(**filtro).all()
    return [fila.clave_intento for fila in filas]


def _bloqueo(sesion: Session, *, minuto: int, slug: str, nombre: str, ip: str):
    with pytest.raises(LoginBloqueadoPorIntentosError) as bloqueado:
        _login(
            sesion,
            reloj=_a(10, minuto),
            organizacion_slug=slug,
            nombre_usuario=nombre,
            password=PASSWORD,
            ip=ip,
        )
    return bloqueado.value


def _cinco_fallos_desde_ips_distintas(sesion, slug, nombre, prefijo_ip) -> None:
    for posicion, minuto in enumerate((2, 5, 7, 9, 10)):
        with pytest.raises(CredencialesInvalidasError):
            _login(
                sesion,
                reloj=_a(10, minuto),
                organizacion_slug=slug,
                nombre_usuario=nombre,
                password="mal",
                ip=f"{prefijo_ip}.{posicion}",
            )


class TestBloqueoPorParEscrito:
    """ADR-057, ADR-018, SEG-01: un nombre inexistente se bloquea en el mismo intento (el sexto)
    y con el mismo texto que uno existente."""

    def test_un_nombre_inexistente_se_bloquea_igual_que_uno_existente(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-p57-1")
        _crear_usuario(db_session, organizacion.id, "marta")
        _cinco_fallos_desde_ips_distintas(db_session, organizacion.slug, "marta", "10.57.1")
        _cinco_fallos_desde_ips_distintas(db_session, organizacion.slug, "martha", "10.57.2")
        antes = db_session.query(IntentoLogin).count()

        real = _bloqueo(
            db_session, minuto=20, slug=organizacion.slug, nombre="marta", ip="10.57.1.9"
        )
        inexistente = _bloqueo(
            db_session, minuto=20, slug=organizacion.slug, nombre="martha", ip="10.57.2.9"
        )

        assert real.codigo == inexistente.codigo == "IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS"
        assert str(real) == str(inexistente) == TEXTO_DE_ARGENTINA
        assert db_session.query(IntentoLogin).count() == antes  # ninguno inserta fila

    def test_con_cuatro_fallos_el_nombre_inexistente_todavia_no_se_bloquea(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-p57-2")
        for posicion in range(4):
            with pytest.raises(CredencialesInvalidasError):
                _login(
                    db_session,
                    reloj=_a(10, 2 + posicion),
                    organizacion_slug=organizacion.slug,
                    nombre_usuario="nadie",
                    password="mal",
                    ip=f"10.57.3.{posicion}",
                )
        with pytest.raises(CredencialesInvalidasError):
            _login(
                db_session,
                reloj=_a(10, 8),
                organizacion_slug=organizacion.slug,
                nombre_usuario="nadie",
                password="mal",
                ip="10.57.3.9",
            )

    def test_un_slug_inexistente_tambien_se_bloquea_a_los_cinco_fallos(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-p57-3")
        _crear_usuario(db_session, organizacion.id, "marta")
        _cinco_fallos_desde_ips_distintas(db_session, "slug-que-no-existe", "marta", "10.57.4")
        _cinco_fallos_desde_ips_distintas(db_session, organizacion.slug, "marta", "10.57.5")
        antes = db_session.query(IntentoLogin).count()

        sin_organizacion = _bloqueo(
            db_session, minuto=20, slug="slug-que-no-existe", nombre="marta", ip="10.57.4.9"
        )
        con_organizacion = _bloqueo(
            db_session, minuto=20, slug=organizacion.slug, nombre="marta", ip="10.57.5.9"
        )

        assert sin_organizacion.codigo == con_organizacion.codigo
        assert str(sin_organizacion) == str(con_organizacion) == TEXTO_DE_ARGENTINA
        assert db_session.query(IntentoLogin).count() == antes

    def test_la_hora_del_429_del_login_sale_siempre_en_zona_argentina(
        self, db_session: Session
    ) -> None:
        """Decisión del usuario del 2026-10-24: también para una organización en otra zona y
        también en el bloqueo por par (no solo por IP)."""
        organizacion = _crear_organizacion(db_session, "org-p57-4")
        organizacion.zona_horaria = "Asia/Tokyo"
        db_session.flush()
        _crear_usuario(db_session, organizacion.id, "marta")
        _cinco_fallos_desde_ips_distintas(db_session, organizacion.slug, "marta", "10.57.6")
        _cinco_fallos_desde_ips_distintas(db_session, organizacion.slug, "martha", "10.57.7")

        real = _bloqueo(
            db_session, minuto=20, slug=organizacion.slug, nombre="marta", ip="10.57.6.9"
        )
        inexistente = _bloqueo(
            db_session, minuto=20, slug=organizacion.slug, nombre="martha", ip="10.57.7.9"
        )

        assert str(real) == str(inexistente) == TEXTO_DE_ARGENTINA  # no "19:25" de Tokio

    def test_el_desbloqueo_es_el_ultimo_fallo_mas_15_minutos_tambien_para_un_par_inexistente(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-p57-5")
        _cinco_fallos_desde_ips_distintas(db_session, organizacion.slug, "nadie", "10.57.8")
        _bloqueo(db_session, minuto=24, slug=organizacion.slug, nombre="nadie", ip="10.57.8.9")
        # A las 10:25 vuelve el cupo entero: el primer fallo abre una ventana nueva.
        with pytest.raises(CredencialesInvalidasError):
            _login(
                db_session,
                reloj=_a(10, 25),
                organizacion_slug=organizacion.slug,
                nombre_usuario="nadie",
                password="mal",
                ip="10.57.8.9",
            )

    def test_el_contador_sigue_al_texto_exacto_juan_y_juan_son_distintos(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-p57-6")
        usuario = _crear_usuario(db_session, organizacion.id, "juan")
        _cinco_fallos_desde_ips_distintas(db_session, organizacion.slug, "Juan", "10.57.9")

        resultado = _login(
            db_session,
            reloj=_a(10, 12),
            organizacion_slug=organizacion.slug,
            nombre_usuario="juan",
            password=PASSWORD,
            ip="10.57.9.9",
        )
        assert resultado.usuario_id == usuario.id
        # y el espacio al final tampoco consume el cupo de "juan"
        _cinco_fallos_desde_ips_distintas(db_session, organizacion.slug, "juan ", "10.57.10")
        assert (
            _login(
                db_session,
                reloj=_a(10, 13),
                organizacion_slug=organizacion.slug,
                nombre_usuario="juan",
                password=PASSWORD,
                ip="10.57.10.9",
            ).usuario_id
            == usuario.id
        )

    def test_el_mismo_usuario_en_dos_organizaciones_son_dos_contadores(
        self, db_session: Session
    ) -> None:
        org_a = _crear_organizacion(db_session, "org-p57-7a")
        org_b = _crear_organizacion(db_session, "org-p57-7b")
        _crear_usuario(db_session, org_a.id, "marta")
        usuario_b = _crear_usuario(db_session, org_b.id, "marta")
        _cinco_fallos_desde_ips_distintas(db_session, org_a.slug, "marta", "10.57.11")

        _bloqueo(db_session, minuto=12, slug=org_a.slug, nombre="marta", ip="10.57.11.9")
        resultado = _login(
            db_session,
            reloj=_a(10, 12),
            organizacion_slug=org_b.slug,
            nombre_usuario="marta",
            password=PASSWORD,
            ip="10.57.11.9",
        )
        assert resultado.usuario_id == usuario_b.id

    def test_todo_fallo_nuevo_lleva_la_clave_del_par_escrito(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, "org-p57-8")
        usuario = _crear_usuario(db_session, organizacion.id, "marta")
        _fallar(db_session, organizacion, "marta", (2,), "10.57.12.1")  # usuario real
        _fallar(db_session, organizacion, "nadie", (3,), "10.57.12.2")  # usuario inexistente
        with pytest.raises(CredencialesInvalidasError):  # slug inexistente
            _login(
                db_session,
                reloj=_a(10, 4),
                organizacion_slug="slug-que-no-existe",
                nombre_usuario="marta",
                password="mal",
                ip="10.57.12.3",
            )

        assert _claves_de(db_session, ip="10.57.12.1") == [
            clave_de_intento_login(organizacion.slug, "marta")
        ]
        assert _claves_de(db_session, ip="10.57.12.2") == [
            clave_de_intento_login(organizacion.slug, "nadie")
        ]
        assert _claves_de(db_session, ip="10.57.12.3") == [
            clave_de_intento_login("slug-que-no-existe", "marta")
        ]
        # `usuario_id` se sigue llenando cuando el par resuelve un usuario.
        assert db_session.query(IntentoLogin).filter_by(ip="10.57.12.1").one().usuario_id == (
            usuario.id
        )
        assert db_session.query(IntentoLogin).filter_by(ip="10.57.12.2").one().usuario_id is None

    def test_el_rechazo_por_dispositivo_tambien_lleva_la_clave(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, "org-p57-9")
        _crear_usuario(db_session, organizacion.id, "marta")
        with pytest.raises(CredencialesInvalidasError):
            identidad_service.iniciar_sesion(
                db_session,
                _a(10, 2),
                organizacion_slug=organizacion.slug,
                nombre_usuario="marta",
                password=PASSWORD,
                dispositivo_id=None,
                nombre_dispositivo="Tablet",
                jwt_secreto=JWT_SECRETO,
                jwt_kid=JWT_KID,
                ip="10.57.13.1",
            )
        assert _claves_de(db_session, ip="10.57.13.1") == [
            clave_de_intento_login(organizacion.slug, "marta")
        ]


class TestAuditoriaYLogDelBloqueoPorPar:
    """ADR-057 punto 8 (confirmado el 2026-10-24): el bloqueo de un par inexistente no escribe
    auditoría y deja log WARNING sin el texto escrito; el de un usuario real sigue auditando."""

    def test_el_bloqueo_de_un_par_inexistente_no_escribe_auditoria_y_deja_log_sin_el_texto(
        self, db_session: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-p57-10")
        texto_escrito = "texto-escrito-que-no-debe-aparecer"
        _cinco_fallos_desde_ips_distintas(db_session, organizacion.slug, texto_escrito, "10.57.14")
        antes = db_session.query(Auditoria).filter_by(accion="LOGIN_BLOQUEADO_POR_INTENTOS").count()

        with caplog.at_level("WARNING", logger="app.identidad"):
            _bloqueo(
                db_session,
                minuto=20,
                slug=organizacion.slug,
                nombre=texto_escrito,
                ip="10.57.14.9",
            )

        assert (
            db_session.query(Auditoria).filter_by(accion="LOGIN_BLOQUEADO_POR_INTENTOS").count()
            == antes
        )
        registros = [r for r in caplog.records if r.levelname == "WARNING"]
        assert registros, "el bloqueo de un par inexistente debe dejar un WARNING"
        clave = clave_de_intento_login(organizacion.slug, texto_escrito)
        mensajes = " ".join(r.getMessage() for r in registros)
        assert clave[:8] in mensajes and "10.57.14.9" in mensajes
        assert texto_escrito not in mensajes and PASSWORD not in mensajes

    def test_el_bloqueo_de_un_usuario_real_sigue_escribiendo_la_auditoria(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, "org-p57-11")
        usuario = _crear_usuario(db_session, organizacion.id, "marta")
        _cinco_fallos_desde_ips_distintas(db_session, organizacion.slug, "marta", "10.57.15")

        _bloqueo(db_session, minuto=20, slug=organizacion.slug, nombre="marta", ip="10.57.15.9")

        auditorias = (
            db_session.query(Auditoria)
            .filter_by(organizacion_id=organizacion.id, accion="LOGIN_BLOQUEADO_POR_INTENTOS")
            .all()
        )
        assert [a.usuario_id for a in auditorias] == [usuario.id]
