"""Change 13, tarea 8.3 (INV-11): una versión de lista publicada no cambia.

Una vez `PUBLICADA` (o `ANULADA`), una versión NO cambia sus precios, sus vigencias ni ningún
dato del cálculo, por ningún comando ni por cambios posteriores en la lista, sus reglas, su
redondeo, los costos informados o el catálogo. El único cambio admitido es su anulación antes
de la vigencia. La garantía vive en el servicio (`design.md` D13: `precios/service.py::
escribir_precios`, la función única de escritura de precios, exige un `BORRADOR` con el candado
de la lista tomado); estas pruebas la ejercitan por todos los caminos.

Reglas citadas: INV-11, INV-18, PRC-03, PRC-04, PRC-16, `design.md` D1, D13 y D14.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from precios_utiles import MOMENTO, REDONDEO_DEFINIR, REGLA_MODIFICAR, RELOJ, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.catalogo import service as catalogo_service
from app.modules.precios import service as precios_service
from app.modules.precios.domain.errores import VersionNoEsBorradorError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS = frozenset({"GESTIONAR_LISTAS", "PUBLICAR_LISTAS"})


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS)


def _publicada(entorno: Entorno, *, dias: int = 0) -> tuple[UUID, UUID]:
    """`General` con la versión n.º 1 publicada (con vigencia desde dentro de `dias` días):
    Vino A a `8600.00`, costo de referencia `6000.000000`, unidades de referencia `6`."""
    lista_id, version_id = entorno.borrador_de_general()
    entorno.publicar(lista_id, version_id, desde=MOMENTO + timedelta(days=dias))
    return lista_id, version_id


def _foto_de_la_version(entorno: Entorno, version_id: UUID) -> tuple[list[object], list[object]]:
    """La fila de la versión y todas sus filas de precio, tal como están en la base."""
    version = entorno.sesion.execute(
        text("SELECT * FROM lista_version WHERE organizacion_id = :o AND id = :v"),
        {"o": entorno.org, "v": version_id},
    ).all()
    precios = entorno.sesion.execute(
        text(
            "SELECT * FROM precio_item WHERE organizacion_id = :o AND version_id = :v "
            "ORDER BY producto_id"
        ),
        {"o": entorno.org, "v": version_id},
    ).all()
    return [tuple(fila) for fila in version], [tuple(fila) for fila in precios]


# --- ningún camino modifica una versión publicada -----------------------------------------------


def test_fijar_un_precio_en_una_version_publicada_se_rechaza_y_el_precio_no_cambia(
    entorno: Entorno,
) -> None:
    lista_id, version_id = _publicada(entorno)
    antes = _foto_de_la_version(entorno, version_id)

    with pytest.raises(VersionNoEsBorradorError):
        entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")
    entorno.sesion.rollback()
    with pytest.raises(VersionNoEsBorradorError):
        entorno.fijar_precio(lista_id, version_id, entorno.vino_id, None)
    entorno.sesion.rollback()

    assert _foto_de_la_version(entorno, version_id) == antes
    assert entorno.precios(version_id)[entorno.vino_id].precio_final == Decimal("8600.00")


def test_publicar_de_nuevo_se_rechaza_y_la_version_no_cambia(entorno: Entorno) -> None:
    lista_id, version_id = _publicada(entorno)
    antes = _foto_de_la_version(entorno, version_id)

    with pytest.raises(VersionNoEsBorradorError):
        entorno.publicar(lista_id, version_id, desde=MOMENTO + timedelta(days=5))
    entorno.sesion.rollback()

    assert _foto_de_la_version(entorno, version_id) == antes


def test_regenerar_deja_intacta_la_version_publicada_y_arma_un_borrador_aparte(
    entorno: Entorno,
) -> None:
    """Regenerar una lista con una versión publicada no reescribe esa versión: crea el
    borrador siguiente (PRC-17) y la publicada conserva cada fila."""
    lista_id, version_id = _publicada(entorno)
    entorno.informar_costo(entorno.vino_id, "1100", creado_en=MOMENTO + timedelta(minutes=1))
    antes = _foto_de_la_version(entorno, version_id)

    entorno.generar_borrador(lista_id)

    assert _foto_de_la_version(entorno, version_id) == antes
    borrador = entorno.versiones(lista_id)[1]
    assert (borrador.numero, borrador.estado) == (2, "BORRADOR")
    assert entorno.precios(borrador.id)[entorno.vino_id].precio_final == Decimal("9500.00")


@pytest.mark.parametrize("estado", ["PUBLICADA", "ANULADA"])
def test_la_funcion_unica_de_escritura_de_precios_exige_un_borrador(
    entorno: Entorno, estado: str
) -> None:
    """D13: el servicio no escribe precios de una versión publicada ni anulada, ni siquiera
    con el candado de la lista tomado por quien llama."""
    lista_id, version_id = _publicada(entorno, dias=9)
    if estado == "ANULADA":
        entorno.anular_version(lista_id, version_id)
    antes = _foto_de_la_version(entorno, version_id)
    version = entorno.versiones(lista_id)[0]
    assert version.estado == estado

    with pytest.raises(VersionNoEsBorradorError):
        precios_service.escribir_precios(
            entorno.org, entorno.sesion, version, [], producto_ids=None
        )
    entorno.sesion.rollback()

    assert _foto_de_la_version(entorno, version_id) == antes


# --- los cambios de la lista, las reglas, los costos y el catálogo no la tocan -------------------


def test_modificar_la_lista_su_redondeo_una_regla_y_el_costo_no_altera_ningun_dato_publicado(
    entorno: Entorno,
) -> None:
    """Escenarios "Un costo nuevo no cambia lo publicado" y "Subir el margen no cambia lo
    publicado": comparación fila por fila antes y después."""
    lista_id, version_id = _publicada(entorno)
    antes = _foto_de_la_version(entorno, version_id)
    regla_id = entorno.reglas(lista_id)[0].id

    entorno.enviar(
        "LISTA_PRECIO_MODIFICAR",
        {
            "lista_id": str(lista_id),
            "nombre": "General 2027",
            "redondeo_multiplo": "500.00",
            "redondeo_direccion": "ABAJO",
            "activo": True,
        },
    )
    entorno.enviar(
        REGLA_MODIFICAR,
        {
            "lista_id": str(lista_id),
            "regla_id": str(regla_id),
            "tipo": "MARGEN_BRUTO",
            "valor": "0.500000",
            "activo": True,
        },
    )
    entorno.enviar(
        REDONDEO_DEFINIR,
        {
            "lista_id": str(lista_id),
            "categoria_id": str(entorno.categoria_id),
            "multiplo": "1000.00",
            "direccion": "ARRIBA",
            "activo": True,
        },
    )
    entorno.informar_costo_por_comando(entorno.vino_id, "9999.00")
    entorno.generar_borrador(lista_id)

    assert _foto_de_la_version(entorno, version_id) == antes
    precio = entorno.precios(version_id)[entorno.vino_id]
    assert (precio.precio_final, precio.costo_referencia) == (
        Decimal("8600.00"),
        Decimal("6000.000000"),
    )
    assert (precio.tipo_margen, precio.valor_margen) == ("MARGEN_BRUTO", Decimal("0.300000"))


def test_publicar_otra_version_no_toca_la_anterior(entorno: Entorno) -> None:
    """Escenario "Publicar otra versión no toca la anterior": la n.º 2 conserva todos sus
    datos, incluida su vigencia hasta nula."""
    lista_id, segunda_id = _publicada(entorno)
    entorno.informar_costo(entorno.vino_id, "1100", creado_en=MOMENTO + timedelta(minutes=1))
    entorno.generar_borrador(lista_id)
    tercera_id = entorno.versiones(lista_id)[1].id
    antes = _foto_de_la_version(entorno, segunda_id)

    entorno.publicar(lista_id, tercera_id, desde=MOMENTO + timedelta(days=30))

    assert _foto_de_la_version(entorno, segunda_id) == antes
    assert entorno.versiones(lista_id)[0].vigencia_hasta is None


def test_anular_una_version_no_cambia_ni_borra_sus_precios(entorno: Entorno) -> None:
    lista_id, version_id = entorno.borrador_de_general()
    entorno.publicar(lista_id, version_id, desde=MOMENTO + timedelta(days=9))
    precios_antes = _foto_de_la_version(entorno, version_id)[1]

    entorno.anular_version(lista_id, version_id)

    assert entorno.versiones(lista_id)[0].estado == "ANULADA"
    assert _foto_de_la_version(entorno, version_id)[1] == precios_antes


def test_inv18_cambiar_la_presentacion_de_referencia_deja_el_precio_y_las_unidades_intactos(
    entorno: Entorno,
) -> None:
    """Escenario "Cambiar la presentación de referencia" (D1, INV-18): la versión sigue
    informando `8600.00` con unidades de referencia `6`; el borrador siguiente calcula sobre la
    referencia nueva."""
    lista_id, version_id = _publicada(entorno)
    caja_x12 = entorno.crear_presentacion(entorno.vino_id, "Caja x12", 12)
    antes = _foto_de_la_version(entorno, version_id)

    catalogo_service.cambiar_referencia(
        entorno.org,
        entorno.sesion,
        RELOJ,
        producto_id=entorno.vino_id,
        presentacion_id=caja_x12,
        actor_id=entorno.usuario_id,
    )

    assert _foto_de_la_version(entorno, version_id) == antes
    publicado = entorno.precios(version_id)[entorno.vino_id]
    assert (publicado.precio_final, publicado.unidades_referencia) == (Decimal("8600.00"), 6)
    entorno.generar_borrador(lista_id)
    borrador = entorno.versiones(lista_id)[1]
    nuevo = entorno.precios(borrador.id)[entorno.vino_id]
    assert nuevo.unidades_referencia == 12
    assert nuevo.costo_referencia == Decimal("12000.000000")
    assert nuevo.precio_final == Decimal("17200.00")
    assert _foto_de_la_version(entorno, version_id) == antes
