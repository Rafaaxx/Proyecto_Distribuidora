"""Change 13, tarea 8.5: `LISTA_ANULAR_VERSION` v1 por el bus, contra PostgreSQL real (spec
`precios/versiones-de-lista`, requisito "Solo se anula una versión publicada cuya vigencia aún
no comenzó").

Reglas citadas: PRC-03, PRC-04, PRC-05, PRC-06, AUD-01, TR-06, INV-06, INV-11, INV-21, SYN-02,
SEG-06, SEG-07, `design.md` D6 y D14.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from precios_utiles import ANULAR_VERSION, MOMENTO, RELOJ, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError
from app.core.errors import PermisoRequeridoError
from app.modules.precios import repository as precios_repository
from app.modules.precios.domain.errores import (
    RecursoNoEncontradoError,
    VersionNoEsBorradorError,
    VersionNoPublicadaError,
    VersionYaVigenteError,
)
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS = frozenset({"GESTIONAR_LISTAS", "PUBLICAR_LISTAS"})


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS)


def _programada(entorno: Entorno, *, dias: int = 9) -> tuple[UUID, UUID]:
    """`General` con su versión n.º 1 publicada con vigencia desde dentro de `dias` días."""
    lista_id, version_id = entorno.borrador_de_general()
    entorno.publicar(lista_id, version_id, desde=MOMENTO + timedelta(days=dias))
    return lista_id, version_id


# --- anular una versión programada ----------------------------------------------------------------


def test_anular_una_version_programada(entorno: Entorno) -> None:
    """Escenario "Anular una versión programada": queda `ANULADA` con usuario y momento,
    conserva sus precios y hay una fila de auditoría."""
    lista_id, version_id = _programada(entorno)
    operation_id = uuid4()

    comando = entorno.anular_version(lista_id, version_id, operation_id=operation_id)

    assert comando.estado == "ACEPTADO"
    assert comando.resultado == {"version_id": str(version_id), "numero": 1}
    (version,) = entorno.versiones(lista_id)
    assert version.estado == "ANULADA"
    assert version.anulado_por_id == entorno.usuario_id
    assert version.anulado_en == MOMENTO
    assert version.vigencia_desde == MOMENTO + timedelta(days=9), "la vigencia no se borra"
    assert version.publicado_por_id == entorno.usuario_id, "quién la publicó queda"
    precio = entorno.precios(version_id)[entorno.vino_id]
    assert precio.precio_final == Decimal("8600.00")
    (auditoria,) = entorno.auditorias(ANULAR_VERSION)
    assert auditoria.operation_id == operation_id


def test_la_vigente_sigue_siendo_la_anterior_tambien_despues_de_la_fecha_de_la_anulada(
    entorno: Entorno,
) -> None:
    """La n.º 1 rige desde ahora; la n.º 2 se programa y se anula: después de su fecha la
    vigente sigue siendo la n.º 1 (PRC-03: una anulada nunca es vigente)."""
    lista_id, primera_id = entorno.borrador_de_general()
    entorno.publicar(lista_id, primera_id)
    entorno.informar_costo(entorno.vino_id, "1100", creado_en=MOMENTO + timedelta(minutes=1))
    entorno.generar_borrador(lista_id)
    segunda_id = entorno.versiones(lista_id)[1].id
    entorno.publicar(lista_id, segunda_id, desde=MOMENTO + timedelta(days=9))
    vigente_antes, _ = precios_repository.resumen_de_versiones(
        entorno.org, entorno.sesion, ahora=MOMENTO + timedelta(days=10)
    )
    assert vigente_antes[lista_id] == 2

    entorno.anular_version(lista_id, segunda_id)

    vigente_despues, _ = precios_repository.resumen_de_versiones(
        entorno.org, entorno.sesion, ahora=MOMENTO + timedelta(days=10)
    )
    assert vigente_despues[lista_id] == 1


def test_la_vigencia_de_una_anulada_queda_libre_para_otra_publicacion(entorno: Entorno) -> None:
    """El único parcial de vigencia desde es entre las `PUBLICADA` (D6)."""
    lista_id, primera_id = _programada(entorno)
    entorno.anular_version(lista_id, primera_id)
    entorno.generar_borrador(lista_id)
    segunda_id = entorno.versiones(lista_id)[1].id

    entorno.publicar(lista_id, segunda_id, desde=MOMENTO + timedelta(days=9))

    assert [v.estado for v in entorno.versiones(lista_id)] == ["ANULADA", "PUBLICADA"]


# --- rechazos de estado -------------------------------------------------------------------------


def test_una_version_que_ya_rige_no_se_anula(entorno: Entorno) -> None:
    """Escenario "Anular una versión que ya rige" (PRC-05, PRC-04): con la vigencia desde ya
    comenzada."""
    lista_id, version_id = entorno.borrador_de_general()
    entorno.publicar_por_sql(version_id, desde=MOMENTO - timedelta(days=1))
    entorno.sesion.commit()

    with pytest.raises(VersionYaVigenteError) as error:
        entorno.anular_version(lista_id, version_id)

    assert error.value.codigo == "VERSION_YA_VIGENTE"
    entorno.sesion.rollback()
    (version,) = entorno.versiones(lista_id)
    assert (version.estado, version.anulado_en) == ("PUBLICADA", None)
    assert entorno.auditorias(ANULAR_VERSION) == []


def test_una_version_publicada_con_vigencia_inmediata_ya_rige_en_el_mismo_instante(
    entorno: Entorno,
) -> None:
    """Publicada sin vigencia desde, rige desde el momento: anularla en ese instante exacto
    se rechaza (la vigencia desde tiene que ser posterior al momento)."""
    lista_id, version_id = entorno.borrador_de_general()
    entorno.publicar(lista_id, version_id)

    with pytest.raises(VersionYaVigenteError):
        entorno.anular_version(lista_id, version_id)


def test_un_borrador_no_se_anula(entorno: Entorno) -> None:
    """Escenario "Anular un borrador o una versión anulada"."""
    lista_id, version_id = entorno.borrador_de_general()

    with pytest.raises(VersionNoPublicadaError) as error:
        entorno.anular_version(lista_id, version_id)

    assert error.value.codigo == "VERSION_NO_PUBLICADA"
    entorno.sesion.rollback()
    assert entorno.versiones(lista_id)[0].estado == "BORRADOR"


def test_una_version_anulada_no_se_vuelve_a_anular_ni_cambia_de_estado(
    entorno: Entorno,
) -> None:
    """Una `ANULADA` no vuelve a otro estado: ni se anula, ni se publica, ni se le fija un
    precio."""
    lista_id, version_id = _programada(entorno)
    entorno.anular_version(lista_id, version_id)

    with pytest.raises(VersionNoPublicadaError):
        entorno.anular_version(lista_id, version_id)
    entorno.sesion.rollback()
    with pytest.raises(VersionNoEsBorradorError):
        entorno.publicar(lista_id, version_id, desde=MOMENTO + timedelta(days=20))
    entorno.sesion.rollback()
    with pytest.raises(VersionNoEsBorradorError):
        entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")
    entorno.sesion.rollback()

    assert entorno.versiones(lista_id)[0].estado == "ANULADA"
    assert entorno.precios(version_id)[entorno.vino_id].precio_final == Decimal("8600.00")


# --- permisos, aislamiento, modo e idempotencia ---------------------------------------------------


def test_sin_publicar_listas_se_rechaza_con_403(entorno: Entorno) -> None:
    """Escenario "Sin permiso" (SEG-06): `GESTIONAR_LISTAS` sin `PUBLICAR_LISTAS`."""
    lista_id, version_id = _programada(entorno)
    entorno.actuar_con_permisos(frozenset({"GESTIONAR_LISTAS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.anular_version(lista_id, version_id)

    entorno.sesion.rollback()
    assert entorno.versiones(lista_id)[0].estado == "PUBLICADA"


def test_inv21_anular_la_version_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Versión de otra organización" (INV-21, SEG-07)."""
    otra = Entorno(db_session, permisos=PERMISOS)
    lista_ajena, version_ajena = _programada(otra)
    lista_propia, _version_propia = _programada(entorno)

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.anular_version(lista_ajena, version_ajena)
    assert error.value.status_http == 404
    with pytest.raises(RecursoNoEncontradoError):
        entorno.anular_version(lista_propia, version_ajena)
    with pytest.raises(RecursoNoEncontradoError):
        entorno.anular_version(lista_propia, uuid4())

    db_session.rollback()
    assert otra.versiones(lista_ajena)[0].estado == "PUBLICADA"
    assert entorno.versiones(lista_propia)[0].estado == "PUBLICADA"


def test_anular_es_solo_online(entorno: Entorno) -> None:
    lista_id, version_id = _programada(entorno)
    item = ItemLote(
        operation_id=uuid4(),
        tipo=ANULAR_VERSION,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={"lista_id": str(lista_id), "version_id": str(version_id)},
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert entorno.versiones(lista_id)[0].estado == "PUBLICADA"


def test_inv06_el_doble_envio_devuelve_el_resultado_original_con_una_sola_auditoria(
    entorno: Entorno,
) -> None:
    """Escenario "Doble envío de la anulación" (INV-06, SYN-02)."""
    lista_id, version_id = _programada(entorno)
    operation_id = uuid4()

    primero = entorno.anular_version(lista_id, version_id, operation_id=operation_id)
    segundo = entorno.anular_version(lista_id, version_id, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.auditorias(ANULAR_VERSION)) == 1


def test_inv06_el_mismo_operation_id_sobre_otra_version_es_inconsistente(
    entorno: Entorno,
) -> None:
    lista_id, version_id = _programada(entorno)
    operation_id = uuid4()
    entorno.anular_version(lista_id, version_id, operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.anular_version(lista_id, uuid4(), operation_id=operation_id)


def test_la_anulacion_no_borra_ni_modifica_ninguna_fila_de_precio(entorno: Entorno) -> None:
    """Escenario "La anulación no borra nada" (TR-06, INV-11)."""
    lista_id, version_id = _programada(entorno)
    antes = entorno.sesion.execute(
        text("SELECT * FROM precio_item WHERE version_id = :v ORDER BY producto_id"),
        {"v": version_id},
    ).all()

    entorno.anular_version(lista_id, version_id)

    despues = entorno.sesion.execute(
        text("SELECT * FROM precio_item WHERE version_id = :v ORDER BY producto_id"),
        {"v": version_id},
    ).all()
    assert despues == antes
    assert len(despues) == 1
