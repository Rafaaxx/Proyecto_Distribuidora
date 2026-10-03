"""Tareas 7.1, 7.4, 7.5: pruebas de integración de `identidad.service`.

Escenarios: "La configuración de una organización no es legible desde otra"
(a través del servicio, no solo del repositorio) y "La fecha de negocio se
deriva de la zona horaria de la organización".
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.identidad import repository, service
from app.modules.identidad.domain.valores import (
    CondicionIvaInvalidaError,
    ModoImpositivoIncompatibleError,
)
from app.modules.identidad.service import DatosConfiguracionInicial


def _configuracion_basica() -> DatosConfiguracionInicial:
    return DatosConfiguracionInicial(
        condicion_iva="RESPONSABLE_INSCRIPTO",
        modo_impositivo="A",
        politica_credito_default="AUTORIZAR",
        estado_facturacion_default="NO_REQUIERE",
        intentos_pin_max=5,
        descuento_manual_habilitado=True,
        motivo_obligatorio_lista=True,
    )


def test_la_configuracion_de_una_organizacion_no_es_legible_desde_otra(
    db_session: Session,
) -> None:
    reloj = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    org_a = service.crear_organizacion_con_configuracion(
        db_session,
        reloj,
        nombre="Organización A",
        slug="organizacion-a",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        configuracion=_configuracion_basica(),
    )
    org_b = service.crear_organizacion_con_configuracion(
        db_session,
        reloj,
        nombre="Organización B",
        slug="organizacion-b",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        configuracion=_configuracion_basica(),
    )

    configuracion_de_a = service.obtener_configuracion(org_a.id, db_session)
    configuracion_leida_como_b = service.obtener_configuracion(org_b.id, db_session)

    assert configuracion_de_a is not None
    assert configuracion_de_a.organizacion_id == org_a.id
    # Pedir la configuración "como si fuera" b nunca trae la de a: cada
    # organización solo alcanza su propia fila (TR-08).
    assert configuracion_leida_como_b is not None
    assert configuracion_leida_como_b.organizacion_id == org_b.id
    assert configuracion_leida_como_b.organizacion_id != configuracion_de_a.organizacion_id


def test_la_fecha_de_negocio_se_deriva_de_la_zona_horaria_de_la_organizacion(
    db_session: Session,
) -> None:
    # 2026-01-01 02:00 UTC es 2025-12-31 23:00 en America/Argentina/Mendoza
    # (UTC-3): la fecha de negocio debe ser el día anterior en esa zona.
    reloj = FixedClock(datetime(2026, 1, 1, 2, 0, tzinfo=UTC))
    organizacion = service.crear_organizacion_con_configuracion(
        db_session,
        reloj,
        nombre="Organización con zona horaria",
        slug="organizacion-con-zona-horaria",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        configuracion=_configuracion_basica(),
    )

    fecha = service.fecha_de_negocio(organizacion.id, db_session, reloj)

    assert fecha is not None
    assert fecha.isoformat() == "2025-12-31"


def test_la_fecha_de_negocio_usa_el_reloj_fijo_no_la_hora_real(db_session: Session) -> None:
    reloj_fijo = FixedClock(datetime(2030, 6, 15, 12, 0, tzinfo=UTC))
    organizacion = service.crear_organizacion_con_configuracion(
        db_session,
        reloj_fijo,
        nombre="Organización con reloj fijo",
        slug="organizacion-con-reloj-fijo",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        configuracion=_configuracion_basica(),
    )

    fecha = service.fecha_de_negocio(organizacion.id, db_session, reloj_fijo)

    assert fecha.isoformat() == "2030-06-15"


def test_no_hay_configuracion_para_una_organizacion_inexistente(db_session: Session) -> None:
    assert service.obtener_configuracion(uuid4(), db_session) is None


def _crear_organizacion_simple(sesion: Session, slug: str) -> object:
    from app.modules.identidad.models import Organizacion

    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba",
        slug=slug,
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=datetime(2026, 1, 1, tzinfo=UTC),
        actualizado_en=datetime(2026, 1, 1, tzinfo=UTC),
        actualizado_por_id=None,
    )
    sesion.add(organizacion)
    sesion.flush()
    return organizacion


def _crear_usuario_con_nombre(sesion: Session, organizacion_id, *, usuario: str, nombre: str):
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Rol de prueba",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=usuario,
        nombre=nombre,
        email=None,
        password_hash="hash-de-prueba",
        rol_id=rol.id,
        estado="ACTIVO",
        momento=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_obtener_nombres_de_usuarios_devuelve_el_nombre_de_cada_id_de_la_organizacion(
    db_session: Session,
) -> None:
    """Change 06, tarea 14.4: `proveedores` necesita mostrar quién registró
    cada costo informado (spec `administracion-de-proveedores`, "usuario y
    momento de registro"), sin importar `identidad.models`/`repository`
    directamente (`CLAUDE.md` §4). Búsqueda por lote, no N+1: un único
    llamado con un conjunto de ids devuelve el nombre de cada uno."""
    organizacion = _crear_organizacion_simple(db_session, "org-nombres-usuarios-1")
    usuario_a = _crear_usuario_con_nombre(
        db_session, organizacion.id, usuario="ana", nombre="Ana Pérez"
    )
    usuario_b = _crear_usuario_con_nombre(
        db_session, organizacion.id, usuario="beto", nombre="Beto Gómez"
    )

    nombres = service.obtener_nombres_de_usuarios(
        organizacion.id, {usuario_a.id, usuario_b.id}, db_session
    )

    assert nombres == {usuario_a.id: "Ana Pérez", usuario_b.id: "Beto Gómez"}


def test_obtener_nombres_de_usuarios_no_trae_usuarios_de_otra_organizacion(
    db_session: Session,
) -> None:
    """INV-21: un id de usuario de otra organización no aparece en el
    resultado, aunque se lo pida explícitamente -- mismo criterio que el
    resto de `identidad.repository` (`organizacion_id` filtra siempre)."""
    organizacion_a = _crear_organizacion_simple(db_session, "org-nombres-usuarios-2a")
    organizacion_b = _crear_organizacion_simple(db_session, "org-nombres-usuarios-2b")
    usuario_a = _crear_usuario_con_nombre(
        db_session, organizacion_a.id, usuario="carla", nombre="Carla Ruiz"
    )
    usuario_b = _crear_usuario_con_nombre(
        db_session, organizacion_b.id, usuario="dario", nombre="Darío Ferro"
    )

    nombres = service.obtener_nombres_de_usuarios(
        organizacion_a.id, {usuario_a.id, usuario_b.id}, db_session
    )

    assert nombres == {usuario_a.id: "Carla Ruiz"}


def test_obtener_nombres_de_usuarios_con_conjunto_vacio_no_consulta_nada(
    db_session: Session,
) -> None:
    organizacion = _crear_organizacion_simple(db_session, "org-nombres-usuarios-3")

    nombres = service.obtener_nombres_de_usuarios(organizacion.id, set(), db_session)

    assert nombres == {}


def _crear(db_session: Session, slug: str, **cambios: object) -> UUID:
    base = {
        "condicion_iva": "RESPONSABLE_INSCRIPTO",
        "modo_impositivo": "A",
        "politica_credito_default": "AUTORIZAR",
        "estado_facturacion_default": "NO_REQUIERE",
        "intentos_pin_max": 5,
        "descuento_manual_habilitado": True,
        "motivo_obligatorio_lista": True,
    }
    organizacion = service.crear_organizacion_con_configuracion(
        db_session,
        FixedClock(datetime(2026, 1, 1, tzinfo=UTC)),
        nombre=slug,
        slug=slug,
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        configuracion=DatosConfiguracionInicial(**{**base, **cambios}),  # type: ignore[arg-type]
    )
    return organizacion.id


@pytest.mark.parametrize("para_compartir", [False, True])
def test_obtener_condicion_iva_devuelve_la_de_cada_organizacion(
    db_session: Session, para_compartir: bool
) -> None:
    """CST-06, TR-08: cada organización alcanza solo su propia condición, con o sin
    bloqueo `FOR SHARE`."""
    inscripta = _crear(db_session, "org-inscripta")
    monotributista = _crear(db_session, "org-monotributista", condicion_iva="MONOTRIBUTO")

    assert (
        service.obtener_condicion_iva(inscripta, db_session, para_compartir=para_compartir)
        == "RESPONSABLE_INSCRIPTO"
    )
    assert (
        service.obtener_condicion_iva(monotributista, db_session, para_compartir=para_compartir)
        == "MONOTRIBUTO"
    )


def test_obtener_condicion_iva_de_una_organizacion_inexistente_es_none(
    db_session: Session,
) -> None:
    assert service.obtener_condicion_iva(uuid4(), db_session) is None
    assert service.obtener_condicion_iva(uuid4(), db_session, para_compartir=True) is None


@pytest.mark.parametrize(
    "cambios",
    [
        {"condicion_iva": "MONOTRIBUTO", "modo_impositivo": "B"},
        {"condicion_iva": "EXENTO", "modalidad_iva_default": "CLIENTE"},
    ],
)
def test_el_alta_de_una_organizacion_no_inscripta_rechaza_modo_o_modalidad_incompatibles(
    db_session: Session, cambios: dict[str, object]
) -> None:
    """D2: se valida en el dominio antes de escribir (la base lo vuelve a exigir)."""
    with pytest.raises(ModoImpositivoIncompatibleError):
        _crear(db_session, "org-incompatible", **cambios)


def test_el_alta_rechaza_una_condicion_desconocida(db_session: Session) -> None:
    with pytest.raises(CondicionIvaInvalidaError):
        _crear(db_session, "org-desconocida", condicion_iva="CONSUMIDOR_FINAL")
