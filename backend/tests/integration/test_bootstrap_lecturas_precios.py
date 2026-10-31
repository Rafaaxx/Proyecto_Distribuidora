"""Change 21, tarea 1.2 (`design.md` D5, D6; spec `sync/bootstrap`): las versiones de lista con sus
precios que el bootstrap baja al dispositivo, y las listas aplicables a un conjunto de clientes, en
`precios/service.py`, solo lectura.

Reglas citadas: PRC-20, PRC-21, PRC-22, INV-11, INV-21.
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

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS = frozenset({"GESTIONAR_LISTAS", "PUBLICAR_LISTAS"})


def _fecha(mes: int, dia: int) -> datetime:
    return datetime(2026, mes, dia, 3, 0, tzinfo=UTC)


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS)


def _lista_con_versiones(entorno: Entorno, nombre: str = "General") -> tuple[UUID, dict[int, UUID]]:
    """La lista con Vino A: la 1 anulada, la 2 y la 3 históricas ($8.000 y $8.600), la 4 vigente
    ($9.000), la 5 programada después de `MOMENTO` ($9.500) y un borrador (6). Devuelve la lista
    y `{número: id}`."""
    lista_id = entorno.crear_lista(nombre, "100.00", "ARRIBA")
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


def _definir_predeterminada(entorno: Entorno, lista_id: UUID) -> None:
    entorno.sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET lista_precio_default_id = :l "
            "WHERE organizacion_id = :o"
        ),
        {"l": lista_id, "o": entorno.org},
    )


def _numeros(lista: precios_service.ListaParaDispositivo) -> list[tuple[int, str]]:
    return sorted((v.numero, v.estado) for v in lista.versiones)


# --- versiones con precios (PRC-20, PRC-21, D5, D6) ---------------------------------------------


def test_prc20_sin_historicas_trae_la_vigente_y_las_programadas(entorno: Entorno) -> None:
    """Escenario "Vendedor sin USAR_LISTA_ANTERIOR": la 4 vigente y la 5 programada; no la 2 ni la
    3 históricas, ni la 1 anulada, ni el borrador."""
    lista_id, _ = _lista_con_versiones(entorno)

    (lista,) = precios_service.listas_para_dispositivo(
        entorno.org,
        entorno.sesion,
        momento=MOMENTO,
        lista_ids=[lista_id],
        producto_ids=[entorno.vino_id],
        con_historicas=False,
    )

    assert _numeros(lista) == [(4, "VIGENTE"), (5, "PROGRAMADA")]


def test_prc21_con_historicas_trae_vigente_programadas_e_historicas(entorno: Entorno) -> None:
    """Escenario "Con USAR_LISTA_ANTERIOR": además las históricas elegibles (2 y 3); nunca la
    anulada (1) ni el borrador (6) (INV-11)."""
    lista_id, ids = _lista_con_versiones(entorno)

    (lista,) = precios_service.listas_para_dispositivo(
        entorno.org,
        entorno.sesion,
        momento=MOMENTO,
        lista_ids=[lista_id],
        producto_ids=[entorno.vino_id],
        con_historicas=True,
    )

    assert _numeros(lista) == [
        (2, "HISTORICA"),
        (3, "HISTORICA"),
        (4, "VIGENTE"),
        (5, "PROGRAMADA"),
    ]
    assert ids[1] not in {v.version_id for v in lista.versiones}
    assert ids[6] not in {v.version_id for v in lista.versiones}


def test_cada_version_trae_su_vigencia_y_sus_precios_con_unidades_de_referencia(
    entorno: Entorno,
) -> None:
    """PRC-22, PRC-23: `precio_referencia` es Decimal exacto y `unidades_referencia` entero."""
    lista_id, ids = _lista_con_versiones(entorno)

    (lista,) = precios_service.listas_para_dispositivo(
        entorno.org,
        entorno.sesion,
        momento=MOMENTO,
        lista_ids=[lista_id],
        producto_ids=[entorno.vino_id],
        con_historicas=False,
    )

    vigente = next(v for v in lista.versiones if v.version_id == ids[4])
    programada = next(v for v in lista.versiones if v.version_id == ids[5])
    assert vigente.vigencia_desde == _fecha(10, 1)
    assert programada.vigencia_desde == _fecha(11, 1)
    (precio,) = vigente.precios
    assert precio.producto_id == entorno.vino_id
    assert precio.precio_referencia == Decimal("9000.00")
    assert isinstance(precio.precio_referencia, Decimal)
    assert precio.unidades_referencia == 6
    assert programada.precios[0].precio_referencia == Decimal("9500.00")


def test_solo_baja_los_precios_de_los_productos_pedidos(entorno: Entorno) -> None:
    """D5: un producto inactivo (que el bootstrap no pide) no aparece con precio."""
    lista_id, _ = _lista_con_versiones(entorno)

    (lista,) = precios_service.listas_para_dispositivo(
        entorno.org,
        entorno.sesion,
        momento=MOMENTO,
        lista_ids=[lista_id],
        producto_ids=[],
        con_historicas=False,
    )

    assert all(v.precios == () for v in lista.versiones)


def test_una_version_vencida_que_ya_termino_es_historica_no_vigente(entorno: Entorno) -> None:
    """PRC-03: la 4 con vigencia hasta en el pasado deja de ser vigente; la vigente vuelve a la
    anterior."""
    lista_id, ids = _lista_con_versiones(entorno)
    entorno.sesion.execute(
        text("UPDATE lista_version SET vigencia_hasta = :h WHERE id = :v"),
        {"h": _fecha(10, 5), "v": ids[4]},
    )

    (lista,) = precios_service.listas_para_dispositivo(
        entorno.org,
        entorno.sesion,
        momento=MOMENTO,
        lista_ids=[lista_id],
        producto_ids=[entorno.vino_id],
        con_historicas=False,
    )

    assert _numeros(lista) == [(3, "VIGENTE"), (5, "PROGRAMADA")]


def test_marca_cual_es_la_lista_predeterminada(entorno: Entorno) -> None:
    general, _ = _lista_con_versiones(entorno, "General")
    otra = entorno.crear_lista("Mayorista", "100.00", "ARRIBA")
    _definir_predeterminada(entorno, general)

    listas = {
        lista.lista_id: lista
        for lista in precios_service.listas_para_dispositivo(
            entorno.org,
            entorno.sesion,
            momento=MOMENTO,
            lista_ids=None,
            producto_ids=[entorno.vino_id],
            con_historicas=False,
        )
    }

    assert listas[general].es_predeterminada is True
    assert listas[general].nombre == "General"
    assert listas[otra].es_predeterminada is False


def test_sin_lista_ids_baja_todas_las_listas_activas_y_no_las_inactivas(entorno: Entorno) -> None:
    activa = entorno.crear_lista("Activa", "100.00", "ARRIBA")
    inactiva = entorno.crear_lista("Inactiva", "100.00", "ARRIBA")
    entorno.sesion.execute(
        text("UPDATE lista_precio SET activo = false WHERE id = :l"), {"l": inactiva}
    )

    ids = {
        lista.lista_id
        for lista in precios_service.listas_para_dispositivo(
            entorno.org,
            entorno.sesion,
            momento=MOMENTO,
            lista_ids=None,
            producto_ids=[],
            con_historicas=True,
        )
    }

    assert ids == {activa}


def test_inv21_no_baja_listas_ni_versiones_de_otra_organizacion(db_session: Session) -> None:
    propio = Entorno(db_session, permisos=PERMISOS)
    ajeno = Entorno(db_session, permisos=PERMISOS)
    mia, _ = _lista_con_versiones(propio)
    ajena, _ = _lista_con_versiones(ajeno)

    todas = precios_service.listas_para_dispositivo(
        propio.org,
        db_session,
        momento=MOMENTO,
        lista_ids=None,
        producto_ids=[propio.vino_id, ajeno.vino_id],
        con_historicas=True,
    )
    pedida_ajena = precios_service.listas_para_dispositivo(
        propio.org,
        db_session,
        momento=MOMENTO,
        lista_ids=[ajena],
        producto_ids=[ajeno.vino_id],
        con_historicas=True,
    )

    assert [lista.lista_id for lista in todas] == [mia]
    assert all(
        v.precios == () or v.precios[0].producto_id == propio.vino_id for v in todas[0].versiones
    )
    assert pedida_ajena == []


# --- listas aplicables a un conjunto de clientes (PRC-20) --------------------------------------


def test_prc20_las_aplicables_son_las_asignadas_mas_la_predeterminada(entorno: Entorno) -> None:
    general, _ = _lista_con_versiones(entorno, "General")
    mayorista = entorno.crear_lista("Mayorista", "100.00", "ARRIBA")
    entorno.crear_lista("Sin clientes", "100.00", "ARRIBA")
    _definir_predeterminada(entorno, general)

    aplicables = precios_service.listas_aplicables_a_clientes(
        entorno.org, entorno.sesion, lista_asignada_ids=[mayorista, mayorista]
    )

    assert set(aplicables) == {general, mayorista}


def test_prc20_sin_asignadas_la_aplicable_es_la_predeterminada(entorno: Entorno) -> None:
    general, _ = _lista_con_versiones(entorno, "General")
    _definir_predeterminada(entorno, general)

    assert precios_service.listas_aplicables_a_clientes(
        entorno.org, entorno.sesion, lista_asignada_ids=[]
    ) == [general]


def test_prc20_sin_predeterminada_y_sin_asignadas_no_hay_aplicables(entorno: Entorno) -> None:
    assert (
        precios_service.listas_aplicables_a_clientes(
            entorno.org, entorno.sesion, lista_asignada_ids=[]
        )
        == []
    )


def test_prc20_una_lista_inactiva_o_ajena_no_es_aplicable(db_session: Session) -> None:
    propio = Entorno(db_session, permisos=PERMISOS)
    ajeno = Entorno(db_session, permisos=PERMISOS)
    inactiva = propio.crear_lista("Inactiva", "100.00", "ARRIBA")
    propio.sesion.execute(
        text("UPDATE lista_precio SET activo = false WHERE id = :l"), {"l": inactiva}
    )
    ajena = ajeno.crear_lista("Ajena", "100.00", "ARRIBA")

    assert (
        precios_service.listas_aplicables_a_clientes(
            propio.org, db_session, lista_asignada_ids=[inactiva, ajena, uuid4()]
        )
        == []
    )
