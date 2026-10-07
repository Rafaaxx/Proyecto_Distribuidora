"""Change 13, tarea 9.1: resolución de precio en `precios/service.py` (PRC-20; spec
`precios/resolucion-de-precio`; `design.md` D1, D6, D11 punto 4).

La interfaz la usará el change 18a (venta); acá no depende de `clientes`: recibe la lista asignada
al cliente como dato (`lista_asignada_id`, o `None`).

Reglas citadas: PRC-20, PRC-10, PRC-03, INV-11, INV-21, SEG-07.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from precios_utiles import MOMENTO, RELOJ, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.catalogo import service as catalogo_service
from app.modules.precios import service as precios_service
from app.modules.precios.domain.errores import (
    ListaSinVersionVigenteError,
    RecursoNoEncontradoError,
    SinListaAplicableError,
)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS = frozenset({"GESTIONAR_LISTAS", "PUBLICAR_LISTAS"})
SEPTIEMBRE = datetime(2026, 9, 1, 3, 0, tzinfo=UTC)
OCTUBRE = datetime(2026, 10, 1, 3, 0, tzinfo=UTC)


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS)


def _definir_predeterminada(entorno: Entorno, lista_id: UUID | None) -> None:
    entorno.sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET lista_precio_default_id = :l "
            "WHERE organizacion_id = :o"
        ),
        {"l": lista_id, "o": entorno.org},
    )


def _lista_con_dos_versiones(entorno: Entorno) -> UUID:
    """`General`: la versión n.º 1 desde el 01/09 con Vino A a `7800.00` (markup 30% sobre
    `6000.000000`) y la n.º 2 desde el 01/10 con Vino A a `8600.00` (margen bruto 30%)."""
    lista_id = entorno.crear_lista("General", "100.00", "ARRIBA")
    regla_id = entorno.crear_regla(lista_id, tipo="MARKUP", valor="0.300000")
    entorno.informar_costo(entorno.vino_id, "1000")
    entorno.generar_borrador(lista_id)
    entorno.publicar_por_sql(entorno.versiones(lista_id)[0].id, desde=SEPTIEMBRE)
    entorno.enviar(
        "REGLA_MARGEN_MODIFICAR",
        {
            "lista_id": str(lista_id),
            "regla_id": str(regla_id),
            "tipo": "MARGEN_BRUTO",
            "valor": "0.300000",
            "activo": True,
        },
    )
    entorno.generar_borrador(lista_id)
    entorno.publicar_por_sql(entorno.versiones(lista_id)[1].id, desde=OCTUBRE)
    return lista_id


# --- la lista aplicable --------------------------------------------------------------------


def test_prc20_el_cliente_con_lista_asignada_usa_esa_aunque_haya_predeterminada(
    entorno: Entorno,
) -> None:
    """Escenario "Cliente con lista asignada"."""
    general = entorno.crear_lista("General")
    mayorista = entorno.crear_lista("Mayorista")
    _definir_predeterminada(entorno, general)

    aplicable = precios_service.resolver_lista_aplicable(
        entorno.org, entorno.sesion, lista_asignada_id=mayorista
    )

    assert aplicable.lista_id == mayorista
    assert aplicable.nombre == "Mayorista"


def test_prc20_el_cliente_sin_lista_usa_la_predeterminada_de_la_organizacion(
    entorno: Entorno,
) -> None:
    """Escenario "Cliente sin lista asignada"."""
    general = entorno.crear_lista("General")
    entorno.crear_lista("Mayorista")
    _definir_predeterminada(entorno, general)

    aplicable = precios_service.resolver_lista_aplicable(
        entorno.org, entorno.sesion, lista_asignada_id=None
    )

    assert (aplicable.lista_id, aplicable.nombre) == (general, "General")


def test_prc20_sin_lista_asignada_ni_predeterminada_se_informa_sin_lista_aplicable(
    entorno: Entorno,
) -> None:
    """Escenario "Sin lista asignada ni predeterminada"."""
    entorno.crear_lista("General")

    with pytest.raises(SinListaAplicableError) as error:
        precios_service.resolver_lista_aplicable(
            entorno.org, entorno.sesion, lista_asignada_id=None
        )

    assert error.value.codigo == "SIN_LISTA_APLICABLE"


def test_prc20_una_lista_asignada_inactiva_no_es_aplicable_ni_cae_a_la_predeterminada(
    entorno: Entorno,
) -> None:
    general = entorno.crear_lista("General")
    especial = entorno.crear_lista("Especial")
    _definir_predeterminada(entorno, general)
    entorno.sesion.execute(
        text("UPDATE lista_precio SET activo = false WHERE id = :l"), {"l": especial}
    )

    with pytest.raises(SinListaAplicableError):
        precios_service.resolver_lista_aplicable(
            entorno.org, entorno.sesion, lista_asignada_id=especial
        )


def test_prc20_una_predeterminada_inactiva_tampoco_es_aplicable(entorno: Entorno) -> None:
    general = entorno.crear_lista("General")
    _definir_predeterminada(entorno, general)
    entorno.sesion.execute(
        text("UPDATE lista_precio SET activo = false WHERE id = :l"), {"l": general}
    )

    with pytest.raises(SinListaAplicableError):
        precios_service.resolver_lista_aplicable(
            entorno.org, entorno.sesion, lista_asignada_id=None
        )


def test_inv21_una_lista_asignada_de_otra_organizacion_responde_como_inexistente(
    db_session: Session,
) -> None:
    propia = Entorno(db_session, permisos=PERMISOS)
    ajena = Entorno(db_session, permisos=PERMISOS)
    lista_ajena = ajena.crear_lista("Mayorista")

    with pytest.raises(RecursoNoEncontradoError):
        precios_service.resolver_lista_aplicable(
            propia.org, db_session, lista_asignada_id=lista_ajena
        )


def test_inv21_la_predeterminada_de_otra_organizacion_no_se_usa(db_session: Session) -> None:
    propia = Entorno(db_session, permisos=PERMISOS)
    ajena = Entorno(db_session, permisos=PERMISOS)
    lista_ajena = ajena.crear_lista("General")
    _definir_predeterminada(ajena, lista_ajena)

    with pytest.raises(SinListaAplicableError):
        precios_service.resolver_lista_aplicable(propia.org, db_session, lista_asignada_id=None)


# --- el precio en la versión vigente --------------------------------------------------------


def test_prc20_el_precio_vigente_de_un_producto_trae_el_precio_y_las_unidades_de_referencia(
    entorno: Entorno,
) -> None:
    """Escenario "Precio vigente de un producto"."""
    lista_id = _lista_con_dos_versiones(entorno)

    resuelto = precios_service.resolver_precios(
        entorno.org,
        entorno.sesion,
        lista_id=lista_id,
        momento=MOMENTO,
        producto_ids=[entorno.vino_id],
    )

    assert resuelto.numero == 2
    assert resuelto.version_id == entorno.versiones(lista_id)[1].id
    precio = resuelto.precios[entorno.vino_id]
    assert precio.precio_final == Decimal("8600.00")
    assert precio.unidades_referencia == 6
    assert resuelto.productos_sin_precio == ()


def test_prc20_se_usa_la_version_vigente_al_momento_pedido(entorno: Entorno) -> None:
    """Escenario "Se usa la versión vigente al momento pedido": `7800.00` el 15/09 y `8600.00`
    el 02/10."""
    lista_id = _lista_con_dos_versiones(entorno)

    en_septiembre = precios_service.resolver_precios(
        entorno.org,
        entorno.sesion,
        lista_id=lista_id,
        momento=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        producto_ids=[entorno.vino_id],
    )
    en_octubre = precios_service.resolver_precios(
        entorno.org,
        entorno.sesion,
        lista_id=lista_id,
        momento=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        producto_ids=[entorno.vino_id],
    )

    assert en_septiembre.numero == 1
    assert en_septiembre.precios[entorno.vino_id].precio_final == Decimal("7800.00")
    assert en_octubre.numero == 2
    assert en_octubre.precios[entorno.vino_id].precio_final == Decimal("8600.00")


def test_prc03_el_limite_de_la_vigencia_es_inclusivo_en_el_desde(entorno: Entorno) -> None:
    lista_id = _lista_con_dos_versiones(entorno)

    justo_antes = precios_service.resolver_precios(
        entorno.org,
        entorno.sesion,
        lista_id=lista_id,
        momento=datetime(2026, 10, 1, 2, 59, 59, tzinfo=UTC),
        producto_ids=None,
    )
    justo_en = precios_service.resolver_precios(
        entorno.org, entorno.sesion, lista_id=lista_id, momento=OCTUBRE, producto_ids=None
    )

    assert (justo_antes.numero, justo_en.numero) == (1, 2)


def test_prc20_una_lista_sin_version_vigente_se_informa(entorno: Entorno) -> None:
    """Escenario "Lista sin versión vigente": solo un borrador."""
    lista_id, _ = entorno.borrador_de_general()

    with pytest.raises(ListaSinVersionVigenteError) as error:
        precios_service.resolver_precios(
            entorno.org,
            entorno.sesion,
            lista_id=lista_id,
            momento=MOMENTO,
            producto_ids=[entorno.vino_id],
        )

    assert error.value.codigo == "LISTA_SIN_VERSION_VIGENTE"


def test_prc20_antes_de_la_primera_vigencia_no_hay_version_vigente(entorno: Entorno) -> None:
    lista_id = _lista_con_dos_versiones(entorno)

    with pytest.raises(ListaSinVersionVigenteError):
        precios_service.resolver_precios(
            entorno.org,
            entorno.sesion,
            lista_id=lista_id,
            momento=datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
            producto_ids=None,
        )


def test_prc10_un_producto_sin_precio_se_informa_sin_inventarle_uno(entorno: Entorno) -> None:
    """Escenario "Producto sin precio en la versión vigente"."""
    lista_id = _lista_con_dos_versiones(entorno)
    gaseosa_id = entorno.crear_producto("Gaseosa C")

    resuelto = precios_service.resolver_precios(
        entorno.org,
        entorno.sesion,
        lista_id=lista_id,
        momento=MOMENTO,
        producto_ids=[entorno.vino_id, gaseosa_id],
    )

    assert set(resuelto.precios) == {entorno.vino_id}
    assert resuelto.productos_sin_precio == (gaseosa_id,)


def test_sin_filtrar_se_devuelven_todos_los_precios_de_la_version(entorno: Entorno) -> None:
    lista_id = _lista_con_dos_versiones(entorno)

    resuelto = precios_service.resolver_precios(
        entorno.org, entorno.sesion, lista_id=lista_id, momento=MOMENTO, producto_ids=None
    )

    assert set(resuelto.precios) == {entorno.vino_id}
    assert resuelto.productos_sin_precio == ()


def test_prc10_las_unidades_de_referencia_son_las_del_precio_no_las_actuales(
    entorno: Entorno,
) -> None:
    """Escenario "Las unidades de referencia son las del precio, no las actuales" (D1)."""
    lista_id = _lista_con_dos_versiones(entorno)
    caja_x12 = entorno.crear_presentacion(entorno.vino_id, "Caja x12", 12)
    catalogo_service.cambiar_referencia(
        entorno.org,
        entorno.sesion,
        RELOJ,
        producto_id=entorno.vino_id,
        presentacion_id=caja_x12,
        actor_id=entorno.usuario_id,
    )

    resuelto = precios_service.resolver_precios(
        entorno.org,
        entorno.sesion,
        lista_id=lista_id,
        momento=MOMENTO,
        producto_ids=[entorno.vino_id],
    )

    precio = resuelto.precios[entorno.vino_id]
    assert (precio.precio_final, precio.unidades_referencia) == (Decimal("8600.00"), 6)


def test_prc03_una_version_anulada_no_se_resuelve(entorno: Entorno) -> None:
    lista_id = _lista_con_dos_versiones(entorno)
    entorno.sesion.execute(
        text(
            "UPDATE lista_version SET estado = 'ANULADA', anulado_en = :m, anulado_por_id = :u "
            "WHERE lista_id = :l AND numero = 2"
        ),
        {"l": lista_id, "m": MOMENTO, "u": entorno.usuario_id},
    )

    resuelto = precios_service.resolver_precios(
        entorno.org, entorno.sesion, lista_id=lista_id, momento=MOMENTO, producto_ids=None
    )

    assert resuelto.numero == 1, "la anulada nunca es vigente: la vigencia vuelve a la anterior"


def test_inv21_resolver_precios_de_una_lista_de_otra_organizacion_responde_404(
    db_session: Session,
) -> None:
    propia = Entorno(db_session, permisos=PERMISOS)
    ajena = Entorno(db_session, permisos=PERMISOS)
    lista_ajena = _lista_con_dos_versiones(ajena)

    with pytest.raises(RecursoNoEncontradoError):
        precios_service.resolver_precios(
            propia.org, db_session, lista_id=lista_ajena, momento=MOMENTO, producto_ids=None
        )


def test_una_lista_inexistente_responde_404(entorno: Entorno) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        precios_service.resolver_precios(
            entorno.org, entorno.sesion, lista_id=uuid4(), momento=MOMENTO, producto_ids=None
        )


def test_el_momento_debe_tener_zona_horaria(entorno: Entorno) -> None:
    lista_id = _lista_con_dos_versiones(entorno)

    with pytest.raises(ValueError, match="zona horaria"):
        precios_service.resolver_precios(
            entorno.org,
            entorno.sesion,
            lista_id=lista_id,
            momento=datetime(2026, 10, 2, 12, 0),  # noqa: DTZ001 - es lo que se prueba
            producto_ids=None,
        )
