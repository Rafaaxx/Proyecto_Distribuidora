"""Tarea 6.1 (change 18a; spec `precios/resolucion-de-precio`; `design.md` D6): los precios de una
versión elegida y las versiones elegibles de una lista, en `precios/service.py`, solo lectura.

Reglas citadas: PRC-21, PRC-10, PRC-05, PRC-02, INV-21.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from precios_utiles import MOMENTO, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.precios import service as precios_service
from app.modules.precios.domain.errores import RecursoNoEncontradoError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS = frozenset({"GESTIONAR_LISTAS", "PUBLICAR_LISTAS"})


def _fecha(mes: int, dia: int) -> datetime:
    return datetime(2026, mes, dia, 3, 0, tzinfo=UTC)


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS)


def _lista_con_versiones(entorno: Entorno) -> tuple[UUID, dict[int, UUID]]:
    """ "General" con Vino A: las versiones 2 y 3 históricas ($8.000 y $8.600), la 4 vigente
    ($9.000), la 5 programada para después de `MOMENTO` ($9.500), la 1 anulada y un borrador (6).
    Devuelve la lista y `{número: id}`."""
    lista_id = entorno.crear_lista("General", "100.00", "ARRIBA")
    entorno.crear_regla(lista_id, tipo="MARGEN_BRUTO", valor="0.300000")
    entorno.informar_costo(entorno.vino_id, "1000")
    plan = [
        (1, "7500.00", _fecha(7, 1)),
        (2, "8000.00", _fecha(8, 1)),
        (3, "8600.00", _fecha(9, 1)),
        (4, "9000.00", _fecha(10, 1)),
        (5, "9500.00", _fecha(11, 1)),
    ]
    ids: dict[int, UUID] = {}
    for numero, precio, desde in plan:
        entorno.generar_borrador(lista_id)
        borrador = entorno.versiones(lista_id)[-1]
        assert borrador.numero == numero
        entorno.fijar_precio(lista_id, borrador.id, entorno.vino_id, precio)
        entorno.publicar_por_sql(borrador.id, desde=desde)
        ids[numero] = borrador.id
    entorno.sesion.execute(
        text(
            "UPDATE lista_version SET estado = 'ANULADA', anulado_por_id = :u, "
            "anulado_en = :m WHERE organizacion_id = :o AND id = :v"
        ),
        {"u": entorno.usuario_id, "m": MOMENTO, "o": entorno.org, "v": ids[1]},
    )
    entorno.generar_borrador(lista_id)
    ids[6] = entorno.versiones(lista_id)[-1].id
    return lista_id, ids


# --- versiones elegibles (PRC-21, PRC-02, PRC-05) -----------------------------------------


def test_prc21_las_elegibles_son_la_vigente_y_las_historicas_de_la_mas_nueva_a_la_mas_vieja(
    entorno: Entorno,
) -> None:
    """Escenario "Versiones elegibles": la 4 (vigente), la 3 y la 2 (históricas); no la 5
    programada, ni la 1 anulada, ni el borrador."""
    lista_id, ids = _lista_con_versiones(entorno)

    elegibles = precios_service.versiones_elegibles(
        entorno.org, entorno.sesion, lista_id=lista_id, momento=MOMENTO
    )

    assert [(v.numero, v.version_id, v.estado) for v in elegibles] == [
        (4, ids[4], "VIGENTE"),
        (3, ids[3], "HISTORICA"),
        (2, ids[2], "HISTORICA"),
    ]
    assert elegibles[0].vigencia_desde == _fecha(10, 1)


def test_prc21_al_adelantar_el_momento_la_programada_pasa_a_vigente(entorno: Entorno) -> None:
    """La elegibilidad depende del momento de la venta, no del reloj de la consulta."""
    lista_id, ids = _lista_con_versiones(entorno)

    elegibles = precios_service.versiones_elegibles(
        entorno.org, entorno.sesion, lista_id=lista_id, momento=_fecha(11, 15)
    )

    assert [(v.numero, v.estado) for v in elegibles] == [
        (5, "VIGENTE"),
        (4, "HISTORICA"),
        (3, "HISTORICA"),
        (2, "HISTORICA"),
    ]
    assert elegibles[0].version_id == ids[5]


def test_prc21_una_lista_sin_versiones_publicadas_no_tiene_elegibles(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista("Vacía")

    assert (
        precios_service.versiones_elegibles(
            entorno.org, entorno.sesion, lista_id=lista_id, momento=MOMENTO
        )
        == ()
    )


def test_inv21_las_versiones_de_una_lista_ajena_responden_como_inexistente(
    db_session: Session,
) -> None:
    propia = Entorno(db_session, permisos=PERMISOS)
    ajena = Entorno(db_session, permisos=PERMISOS)
    lista_ajena = ajena.crear_lista("Mayorista")

    with pytest.raises(RecursoNoEncontradoError):
        precios_service.versiones_elegibles(
            propia.org, db_session, lista_id=lista_ajena, momento=MOMENTO
        )
    with pytest.raises(RecursoNoEncontradoError):
        precios_service.versiones_elegibles(
            propia.org, db_session, lista_id=uuid4(), momento=MOMENTO
        )


def test_prc21_el_momento_sin_zona_horaria_se_rechaza(entorno: Entorno) -> None:
    lista_id, _ = _lista_con_versiones(entorno)

    with pytest.raises(ValueError, match="zona horaria"):
        precios_service.versiones_elegibles(
            entorno.org, entorno.sesion, lista_id=lista_id, momento=datetime(2026, 10, 6, 12, 0)
        )


# --- precios de la versión elegida (PRC-10, PRC-21) ----------------------------------------


def test_prc10_los_precios_de_la_version_3_traen_las_unidades_y_los_sin_precio_aparte(
    entorno: Entorno,
) -> None:
    """Escenario "Precios de la versión 3": Vino A a $8.600 con unidades de referencia 6 y
    Cerveza B (sin precio en esa versión) entre los productos sin precio."""
    lista_id, ids = _lista_con_versiones(entorno)
    cerveza_id = entorno.crear_producto("Cerveza B", unidades_base=12)

    resuelto = precios_service.resolver_precios_de_version(
        entorno.org,
        entorno.sesion,
        version_id=ids[3],
        producto_ids=[entorno.vino_id, cerveza_id],
    )

    assert (resuelto.version_id, resuelto.lista_id, resuelto.numero) == (ids[3], lista_id, 3)
    assert resuelto.precios[entorno.vino_id].precio_final == Decimal("8600.00")
    assert resuelto.precios[entorno.vino_id].unidades_referencia == 6
    assert cerveza_id not in resuelto.precios
    assert resuelto.productos_sin_precio == (cerveza_id,)


def test_prc21_cada_version_devuelve_su_propio_precio(entorno: Entorno) -> None:
    """Triangula con otra versión: el precio es el de la versión pedida, no el vigente."""
    _, ids = _lista_con_versiones(entorno)

    precios = {
        numero: precios_service.resolver_precios_de_version(
            entorno.org, entorno.sesion, version_id=ids[numero], producto_ids=[entorno.vino_id]
        )
        .precios[entorno.vino_id]
        .precio_final
        for numero in (2, 3, 4)
    }

    assert precios == {2: Decimal("8000.00"), 3: Decimal("8600.00"), 4: Decimal("9000.00")}


def test_prc10_sin_lista_de_productos_devuelve_todos_los_precios_de_la_version(
    entorno: Entorno,
) -> None:
    _, ids = _lista_con_versiones(entorno)

    resuelto = precios_service.resolver_precios_de_version(
        entorno.org, entorno.sesion, version_id=ids[4], producto_ids=None
    )

    assert set(resuelto.precios) == {entorno.vino_id}
    assert resuelto.productos_sin_precio == ()


def test_inv21_los_precios_de_una_version_ajena_responden_como_inexistente(
    db_session: Session,
) -> None:
    propia = Entorno(db_session, permisos=PERMISOS)
    ajena = Entorno(db_session, permisos=PERMISOS)
    _, ids_ajenos = _lista_con_versiones(ajena)

    with pytest.raises(RecursoNoEncontradoError):
        precios_service.resolver_precios_de_version(
            propia.org, db_session, version_id=ids_ajenos[3], producto_ids=[propia.vino_id]
        )
    with pytest.raises(RecursoNoEncontradoError):
        precios_service.resolver_precios_de_version(
            propia.org, db_session, version_id=uuid4(), producto_ids=None
        )
