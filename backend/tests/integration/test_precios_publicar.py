"""Change 13, tareas 8.2 y 8.4: `LISTA_PUBLICAR` v1 por el bus, contra PostgreSQL real (spec
`precios/versiones-de-lista`, requisito "Un borrador se publica por comando con su vigencia").

Reglas citadas: PRC-02, PRC-03, PRC-04, PRC-06, PRC-10, PRC-20, AUD-01, INV-01, INV-06, INV-11,
INV-21, SYN-02, SEG-06, SEG-07, `01` §21, `design.md` D6 y D14.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from precios_utiles import MOMENTO, PUBLICAR, RELOJ, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_ubicacion_sql, insertar_stock_movimiento_sql

from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.core.errors import PermisoRequeridoError
from app.modules.precios import repository as precios_repository
from app.modules.precios.domain.errores import (
    ListaInactivaError,
    RecursoNoEncontradoError,
    VersionNoEsBorradorError,
    VersionSinPreciosError,
    VigenciaDuplicadaError,
    VigenciaInvalidaError,
)
from app.modules.precios.domain.versiones import PROGRAMADA, VersionDeLista, estado_derivado
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS_DE_PUBLICACION = frozenset({"GESTIONAR_LISTAS", "PUBLICAR_LISTAS"})


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS_DE_PUBLICACION)


# --- publicación inmediata y programada ---------------------------------------------------------


def test_publicacion_inmediata_sin_vigencia_desde(entorno: Entorno) -> None:
    """Escenario "Publicación con vigencia inmediata": `PUBLICADA` con vigencia desde igual al
    momento de la publicación, con usuario y momento, y una sola fila de auditoría."""
    lista_id, version_id = entorno.borrador_de_general()
    operation_id = uuid4()

    comando = entorno.publicar(lista_id, version_id, operation_id=operation_id)

    assert comando.estado == "ACEPTADO"
    (version,) = entorno.versiones(lista_id)
    assert (version.estado, version.numero) == ("PUBLICADA", 1)
    assert version.vigencia_desde == MOMENTO
    assert version.vigencia_hasta is None
    assert version.publicado_por_id == entorno.usuario_id
    assert version.publicado_en == MOMENTO
    assert version.anulado_en is None
    assert comando.resultado == {
        "version_id": str(version_id),
        "numero": 1,
        "vigencia_desde": MOMENTO.isoformat(),
        "vigencia_hasta": None,
        "cantidad_precios": 1,
    }
    (auditoria,) = entorno.auditorias(PUBLICAR)
    assert auditoria.operation_id == operation_id
    assert entorno.precios(version_id)[entorno.vino_id].precio_final == Decimal("8600.00")


def test_publicacion_programada_con_vigencias(entorno: Entorno) -> None:
    """Escenario "Publicación programada": desde dentro de tres días hasta dentro de treinta y
    tres; su estado derivado es `PROGRAMADA`."""
    lista_id, version_id = entorno.borrador_de_general()
    desde, hasta = MOMENTO + timedelta(days=3), MOMENTO + timedelta(days=33)

    entorno.publicar(lista_id, version_id, desde=desde, hasta=hasta)

    (version,) = entorno.versiones(lista_id)
    assert (version.estado, version.vigencia_desde, version.vigencia_hasta) == (
        "PUBLICADA",
        desde,
        hasta,
    )
    derivado = estado_derivado(
        VersionDeLista(
            version.id,
            version.numero,
            version.estado,
            version.vigencia_desde,
            version.vigencia_hasta,
        ),
        None,
        MOMENTO,
    )
    assert derivado == PROGRAMADA


def test_publicar_no_recalcula_precios_ni_cambia_las_otras_versiones(entorno: Entorno) -> None:
    lista_id, primera_id = entorno.borrador_de_general()
    entorno.publicar(lista_id, primera_id, desde=MOMENTO - timedelta(days=0))
    entorno.informar_costo(entorno.vino_id, "1100", creado_en=MOMENTO + timedelta(minutes=1))
    entorno.generar_borrador(lista_id)
    segunda_id = entorno.versiones(lista_id)[1].id
    antes = entorno.sesion.execute(
        text("SELECT * FROM lista_version WHERE id = :v"), {"v": primera_id}
    ).one()

    entorno.publicar(lista_id, segunda_id, desde=MOMENTO + timedelta(days=1))

    despues = entorno.sesion.execute(
        text("SELECT * FROM lista_version WHERE id = :v"), {"v": primera_id}
    ).one()
    assert despues == antes
    assert entorno.precios(segunda_id)[entorno.vino_id].precio_final == Decimal("9500.00")


# --- vigencias inválidas ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        (MOMENTO - timedelta(seconds=1), None),  # hacia atrás
        (MOMENTO - timedelta(days=30), None),
        (MOMENTO + timedelta(days=1), MOMENTO + timedelta(days=1)),  # hasta igual al desde
        (MOMENTO + timedelta(days=2), MOMENTO + timedelta(days=1)),  # hasta anterior al desde
        (None, MOMENTO),  # sin desde: rige el momento y el hasta no es posterior
    ],
)
def test_una_vigencia_invalida_se_rechaza_y_la_version_sigue_en_borrador(
    entorno: Entorno, desde: object, hasta: object
) -> None:
    """Escenarios "Vigencia desde en el pasado" y "Vigencia hasta no posterior a la vigencia
    desde" (PRC-02, PRC-20, D6)."""
    lista_id, version_id = entorno.borrador_de_general()

    with pytest.raises(VigenciaInvalidaError) as error:
        entorno.publicar(lista_id, version_id, desde=desde, hasta=hasta)  # type: ignore[arg-type]

    assert error.value.codigo == "VIGENCIA_INVALIDA"
    entorno.sesion.rollback()
    (version,) = entorno.versiones(lista_id)
    assert (version.estado, version.vigencia_desde, version.publicado_en) == (
        "BORRADOR",
        None,
        None,
    )
    assert entorno.auditorias(PUBLICAR) == []


def test_la_misma_vigencia_desde_que_otra_publicada_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Misma vigencia desde que otra versión publicada"."""
    lista_id, primera_id = entorno.borrador_de_general()
    desde = MOMENTO + timedelta(days=5)
    entorno.publicar(lista_id, primera_id, desde=desde)
    entorno.generar_borrador(lista_id)
    segunda_id = entorno.versiones(lista_id)[1].id

    with pytest.raises(VigenciaDuplicadaError) as error:
        entorno.publicar(lista_id, segunda_id, desde=desde)

    assert error.value.codigo == "VIGENCIA_DUPLICADA"
    entorno.sesion.rollback()
    assert entorno.versiones(lista_id)[1].estado == "BORRADOR"


def test_un_borrador_sin_precios_no_se_publica(entorno: Entorno) -> None:
    """Escenario "Borrador sin precios" (PRC-10)."""
    lista_id = entorno.crear_lista()
    entorno.generar_borrador(lista_id)
    version_id = entorno.versiones(lista_id)[0].id

    with pytest.raises(VersionSinPreciosError) as error:
        entorno.publicar(lista_id, version_id)

    assert error.value.codigo == "VERSION_SIN_PRECIOS"
    entorno.sesion.rollback()
    assert entorno.versiones(lista_id)[0].estado == "BORRADOR"


def test_publicar_dos_veces_se_rechaza_y_la_version_no_cambia(entorno: Entorno) -> None:
    """Escenario "Publicar dos veces" (PRC-04, INV-11): otro `Operation-Id`."""
    lista_id, version_id = entorno.borrador_de_general()
    entorno.publicar(lista_id, version_id)
    antes = entorno.sesion.execute(
        text("SELECT * FROM lista_version WHERE id = :v"), {"v": version_id}
    ).one()

    with pytest.raises(VersionNoEsBorradorError) as error:
        entorno.publicar(lista_id, version_id, desde=MOMENTO + timedelta(days=9))

    assert error.value.codigo == "VERSION_NO_ES_BORRADOR"
    entorno.sesion.rollback()
    despues = entorno.sesion.execute(
        text("SELECT * FROM lista_version WHERE id = :v"), {"v": version_id}
    ).one()
    assert despues == antes


def test_una_lista_inactiva_no_publica(entorno: Entorno) -> None:
    lista_id, version_id = entorno.borrador_de_general()
    entorno.enviar(
        "LISTA_PRECIO_MODIFICAR",
        {
            "lista_id": str(lista_id),
            "nombre": "General",
            "redondeo_multiplo": "100.00",
            "redondeo_direccion": "ARRIBA",
            "activo": False,
        },
    )

    with pytest.raises(ListaInactivaError):
        entorno.publicar(lista_id, version_id)

    entorno.sesion.rollback()
    assert entorno.versiones(lista_id)[0].estado == "BORRADOR"


# --- permisos, aislamiento, modo e idempotencia ---------------------------------------------------


def test_sin_publicar_listas_se_rechaza_con_403(entorno: Entorno) -> None:
    """Escenario "Sin permiso de publicar" (PRC-06, SEG-06): el rol Administración
    (`GESTIONAR_LISTAS` sin `PUBLICAR_LISTAS`) no publica."""
    lista_id, version_id = entorno.borrador_de_general()
    entorno.actuar_con_permisos(frozenset({"GESTIONAR_LISTAS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.publicar(lista_id, version_id)

    entorno.sesion.rollback()
    assert entorno.versiones(lista_id)[0].estado == "BORRADOR"


def test_inv21_publicar_la_version_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Versión de otra organización" (INV-21, SEG-07)."""
    otra = Entorno(db_session, permisos=PERMISOS_DE_PUBLICACION)
    lista_ajena, version_ajena = otra.borrador_de_general()
    lista_propia, version_propia = entorno.borrador_de_general()

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.publicar(lista_ajena, version_ajena)
    assert error.value.status_http == 404
    with pytest.raises(RecursoNoEncontradoError):
        entorno.publicar(lista_propia, version_ajena)
    with pytest.raises(RecursoNoEncontradoError):
        entorno.publicar(lista_ajena, version_propia)
    with pytest.raises(RecursoNoEncontradoError):
        entorno.publicar(lista_propia, uuid4())

    db_session.rollback()
    assert otra.versiones(lista_ajena)[0].estado == "BORRADOR"
    assert entorno.versiones(lista_propia)[0].estado == "BORRADOR"


def test_publicar_es_solo_online(entorno: Entorno) -> None:
    """Escenario "Solo con conexión" (`02` §6.5)."""
    lista_id, version_id = entorno.borrador_de_general()
    item = ItemLote(
        operation_id=uuid4(),
        tipo=PUBLICAR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={
            "lista_id": str(lista_id),
            "version_id": str(version_id),
            "vigencia_desde": None,
            "vigencia_hasta": None,
        },
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
    assert entorno.versiones(lista_id)[0].estado == "BORRADOR"


def test_una_fecha_sin_zona_horaria_se_rechaza_como_contenido_invalido(entorno: Entorno) -> None:
    """Una vigencia sin zona no dice qué instante es: no se adivina."""
    lista_id, version_id = entorno.borrador_de_general()

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(
            PUBLICAR,
            {
                "lista_id": str(lista_id),
                "version_id": str(version_id),
                "vigencia_desde": "2026-12-01T00:00:00",
                "vigencia_hasta": None,
            },
        )


def test_inv06_el_doble_envio_devuelve_el_resultado_original_y_otro_contenido_es_inconsistente(
    entorno: Entorno,
) -> None:
    """Escenario "Doble envío de la publicación" (INV-06, SYN-02)."""
    lista_id, version_id = entorno.borrador_de_general()
    operation_id = uuid4()
    desde = MOMENTO + timedelta(days=2)

    primero = entorno.publicar(lista_id, version_id, desde=desde, operation_id=operation_id)
    segundo = entorno.publicar(lista_id, version_id, desde=desde, operation_id=operation_id)
    with pytest.raises(ComandoInconsistenteError):
        entorno.publicar(
            lista_id, version_id, desde=desde + timedelta(days=1), operation_id=operation_id
        )

    assert primero.resultado == segundo.resultado
    entorno.sesion.rollback()
    assert len(entorno.auditorias(PUBLICAR)) == 1
    assert entorno.versiones(lista_id)[0].vigencia_desde == desde


# --- atomicidad (tarea 8.4) -----------------------------------------------------------------


def test_inv01_una_falla_despues_de_marcar_la_version_la_deja_en_borrador_y_sin_auditoria(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "La publicación es atómica" (INV-01): la falla ocurre después de que el
    `UPDATE` de la versión ya se ejecutó y antes de terminar el comando."""
    lista_id, version_id = entorno.borrador_de_general()
    original = precios_repository.marcar_publicada

    def _falla_despues_de_marcar(*argumentos: object, **opciones: object) -> object:
        resultado = original(*argumentos, **opciones)  # type: ignore[arg-type]
        raise RuntimeError("falla inyectada después de marcar la versión")
        return resultado  # pragma: no cover

    monkeypatch.setattr(precios_repository, "marcar_publicada", _falla_despues_de_marcar)

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.publicar(lista_id, version_id)

    entorno.sesion.rollback()
    (version,) = entorno.versiones(lista_id)
    assert (version.estado, version.vigencia_desde, version.publicado_por_id) == (
        "BORRADOR",
        None,
        None,
    )
    assert entorno.auditorias(PUBLICAR) == []
    assert entorno.precios(version_id)[entorno.vino_id].precio_final == Decimal("8600.00")


# --- sin efectos fuera de la lista (01 §21) -------------------------------------------------


def test_publicar_no_cambia_stock_costo_promedio_ni_saldos(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Publicar no afecta costos, stock ni cuentas" (`01` §21, fila "Versión
    publicada")."""
    ubicacion_id = crear_ubicacion_sql(db_session, entorno.org)
    insertar_stock_movimiento_sql(
        db_session,
        organizacion_id=entorno.org,
        producto_id=entorno.vino_id,
        ubicacion_id=ubicacion_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
    )
    lista_id, version_id = entorno.borrador_de_general()
    tablas = (
        "stock_movimiento",
        "stock_saldo",
        "costo_producto",
        "costo_producto_mov",
        "cuenta_movimiento",
        "saldo_cuenta",
    )

    def _foto() -> dict[str, list[tuple[object, ...]]]:
        return {
            tabla: [
                tuple(fila)
                for fila in db_session.execute(
                    text(f"SELECT * FROM {tabla} WHERE organizacion_id = :o ORDER BY 1, 2"),
                    {"o": entorno.org},
                ).all()
            ]
            for tabla in tablas
        }

    antes = _foto()
    assert antes["stock_movimiento"], "la prueba parte de un stock real"

    entorno.publicar(lista_id, version_id)

    assert _foto() == antes
