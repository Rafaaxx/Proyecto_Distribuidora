"""Change 28, tarea 6.1 (D14): siembra del escenario de aceptación (`python -m app.seed
--escenario-aceptacion`). Spec `sistema/aceptacion-etapa-1`, escenario «La siembra del escenario es
repetible». Regla: `02` §16.1 (datos de ejemplo cargables con un comando, con el escenario de la
demo). Cita INV-21: la segunda organización queda aparte de la primera."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.seguridad import verificar_password
from app.modules.catalogo import service as catalogo_service
from app.modules.descuentos.models import ReglaDescuento
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.permisos import (
    ADMINISTRACION,
    ADMINISTRADOR,
    CONSULTA_DIRECCION,
    SUPERVISOR_COMERCIAL,
    VENDEDOR_REPARTIDOR,
)
from app.modules.identidad.models import Organizacion, Usuario
from app.modules.stock import service as stock_service
from app.seed import (
    CATEGORIAS_DE_ACEPTACION,
    PASSWORD_DE_PRUEBA_ACEPTACION,
    SLUG_ORGANIZACION_INICIAL,
    SLUG_SEGUNDA_ORGANIZACION,
    USUARIOS_DE_ACEPTACION,
    sembrar_escenario_aceptacion,
)

RELOJ = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))


def _organizacion(sesion: Session, slug: str) -> Organizacion:
    organizacion = identidad_service.resolver_organizacion_por_slug(slug, sesion)
    assert organizacion is not None
    return organizacion


def test_la_siembra_crea_la_organizacion_con_los_usuarios_de_desarrollo(
    db_session: Session,
) -> None:
    assert sembrar_escenario_aceptacion(db_session, RELOJ) is True

    organizacion = _organizacion(db_session, SLUG_ORGANIZACION_INICIAL)
    esperados = {
        "admin": ADMINISTRADOR,
        "administracion": ADMINISTRACION,
        "ges01": ADMINISTRACION,
        "consulta": CONSULTA_DIRECCION,
        "supervisor": SUPERVISOR_COMERCIAL,
        "sup01": SUPERVISOR_COMERCIAL,
        "vendedor": VENDEDOR_REPARTIDOR,
        "vendedor2": VENDEDOR_REPARTIDOR,
    }
    assert dict(USUARIOS_DE_ACEPTACION) == esperados
    roles = {
        rol.id: rol.nombre for rol in identidad_repository.listar_roles(organizacion.id, db_session)
    }
    for nombre_usuario, rol in esperados.items():
        usuario = identidad_repository.obtener_usuario_por_nombre_usuario(
            organizacion.id, nombre_usuario, db_session
        )
        assert usuario is not None, nombre_usuario
        assert roles[usuario.rol_id] == rol
        assert usuario.estado == "ACTIVO"
        assert verificar_password(PASSWORD_DE_PRUEBA_ACEPTACION, usuario.password_hash)


def test_la_siembra_deja_ubicaciones_credito_regla_de_volumen_y_tope_del_vendedor(
    db_session: Session,
) -> None:
    sembrar_escenario_aceptacion(db_session, RELOJ)
    organizacion = _organizacion(db_session, SLUG_ORGANIZACION_INICIAL)

    ubicaciones = stock_service.listar_ubicaciones(
        organizacion.id, db_session, activo=True, cursor=None, limite=None
    ).ubicaciones
    assert {(u.tipo, u.requiere_toma) for u in ubicaciones} == {
        ("DEPOSITO", False),
        ("VEHICULO", True),
    }

    configuracion = identidad_service.obtener_configuracion(organizacion.id, db_session)
    assert configuracion is not None
    assert configuracion.politica_credito_default == "AUTORIZAR"
    assert configuracion.tolerancia_offline_tipo == "IMPORTE"
    assert configuracion.tolerancia_offline_valor == Decimal("50000.00")

    reglas = list(
        db_session.scalars(
            select(ReglaDescuento).where(ReglaDescuento.organizacion_id == organizacion.id)
        )
    )
    assert [(r.tipo, r.estado, r.accion_porcentaje) for r in reglas] == [
        ("VOLUMEN_OPERACION", "ACTIVA", Decimal("0.050000"))
    ]

    roles = {
        rol.nombre: rol for rol in identidad_repository.listar_roles(organizacion.id, db_session)
    }
    assert roles[VENDEDOR_REPARTIDOR].tope_descuento == Decimal("0.100000")


def test_la_siembra_deja_las_categorias_que_las_planillas_de_productos_referencian(
    db_session: Session,
) -> None:
    """IMP-04: las planillas referencian la categoría por nombre y no la crean al vuelo."""
    sembrar_escenario_aceptacion(db_session, RELOJ)
    organizacion = _organizacion(db_session, SLUG_ORGANIZACION_INICIAL)

    nombres = {c.nombre for c in catalogo_service.listar_categorias(organizacion.id, db_session)}
    assert nombres == {"Vinos", "Cervezas"}
    assert set(CATEGORIAS_DE_ACEPTACION) == nombres
    segunda = _organizacion(db_session, SLUG_SEGUNDA_ORGANIZACION)
    assert catalogo_service.listar_categorias(segunda.id, db_session) == []


def test_la_segunda_organizacion_es_aparte_y_tiene_solo_su_administrador(
    db_session: Session,
) -> None:
    """INV-21: la segunda organización es otra, con su propio `admin`."""
    sembrar_escenario_aceptacion(db_session, RELOJ)
    primera = _organizacion(db_session, SLUG_ORGANIZACION_INICIAL)
    segunda = _organizacion(db_session, SLUG_SEGUNDA_ORGANIZACION)

    assert segunda.id != primera.id
    usuarios = list(
        db_session.scalars(select(Usuario.usuario).where(Usuario.organizacion_id == segunda.id))
    )
    assert usuarios == ["admin"]
    admin = identidad_repository.obtener_usuario_por_nombre_usuario(segunda.id, "admin", db_session)
    assert admin is not None
    assert verificar_password(PASSWORD_DE_PRUEBA_ACEPTACION, admin.password_hash)


def test_la_siembra_es_repetible_la_segunda_corrida_no_cambia_nada(db_session: Session) -> None:
    assert sembrar_escenario_aceptacion(db_session, RELOJ) is True
    antes = _fotografia(db_session)

    assert sembrar_escenario_aceptacion(db_session, RELOJ) is False

    assert _fotografia(db_session) == antes
    assert antes["organizaciones"] == 2


def test_una_siembra_a_medias_se_completa_sin_duplicar(db_session: Session) -> None:
    """Triangula la repetibilidad: con solo la organización inicial común ya sembrada (la de
    producción), el escenario agrega lo que falta."""
    from app.seed import sembrar

    sembrar(db_session, RELOJ, password_administrador="otra-contrasena-123")

    assert sembrar_escenario_aceptacion(db_session, RELOJ) is True

    assert _fotografia(db_session)["organizaciones"] == 2
    assert sembrar_escenario_aceptacion(db_session, RELOJ) is False


def _fotografia(sesion: Session) -> dict[str, int]:
    return {
        "organizaciones": sesion.scalar(select(func.count()).select_from(Organizacion)) or 0,
        "usuarios": sesion.scalar(select(func.count()).select_from(Usuario)) or 0,
        "reglas": sesion.scalar(select(func.count()).select_from(ReglaDescuento)) or 0,
    }
