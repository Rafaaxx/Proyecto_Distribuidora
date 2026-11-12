"""Change 13, tarea 5.3: `REDONDEO_CATEGORIA_DEFINIR` v1 por el bus, contra PostgreSQL real
(spec `precios/listas-de-precios`, requisito "El redondeo de una lista puede sobrescribirse
por categoría").

Reglas citadas: PRC-14, INV-02, INV-06, INV-21, SEG-06, `design.md` D9, D13, D14.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from precios_utiles import MOMENTO, REDONDEO_DEFINIR, Entorno
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.core.errors import PermisoRequeridoError
from app.modules.precios.domain.errores import RecursoNoEncontradoError, RedondeoInvalidoError
from app.modules.precios.models import RedondeoCategoria

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _definir(lista_id: UUID, categoria_id: UUID, **cambios: object) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "lista_id": str(lista_id),
        "categoria_id": str(categoria_id),
        "multiplo": "10.00",
        "direccion": "ARRIBA",
    }
    cuerpo.update(cambios)
    return cuerpo


def _redondeos(entorno: Entorno, lista_id: UUID) -> list[RedondeoCategoria]:
    return list(
        entorno.sesion.scalars(
            select(RedondeoCategoria).where(
                RedondeoCategoria.organizacion_id == entorno.org,
                RedondeoCategoria.lista_id == lista_id,
            )
        )
    )


def test_sobrescritura_para_una_categoria(entorno: Entorno) -> None:
    """Escenario "Sobrescritura para una categoría": activa, y el redondeo general de la
    lista no cambia."""
    lista_id = entorno.crear_lista(multiplo="100.00", direccion="CERCANO")
    golosinas = entorno.crear_categoria("Golosinas")
    operation_id = uuid4()

    comando = entorno.enviar(
        REDONDEO_DEFINIR, _definir(lista_id, golosinas), operation_id=operation_id
    )

    assert comando.estado == "ACEPTADO"
    (redondeo,) = _redondeos(entorno, lista_id)
    assert comando.resultado == {
        "redondeo_id": str(redondeo.id),
        "lista_id": str(lista_id),
        "categoria_id": str(golosinas),
    }
    assert (redondeo.multiplo, redondeo.direccion, redondeo.activo) == (
        Decimal("10.00"),
        "ARRIBA",
        True,
    )
    assert redondeo.creado_en == MOMENTO
    assert redondeo.actualizado_por_id == entorno.usuario_id
    (lista,) = entorno.listas()
    assert (lista.redondeo_multiplo, lista.redondeo_direccion) == (Decimal("100.00"), "CERCANO")
    (auditoria,) = entorno.auditorias(REDONDEO_DEFINIR)
    assert auditoria.operation_id == operation_id


def test_definir_dos_veces_la_misma_categoria_actualiza_la_existente(entorno: Entorno) -> None:
    """Escenario "Definir dos veces la misma categoría": una sola fila, con el múltiplo nuevo."""
    lista_id = entorno.crear_lista()
    golosinas = entorno.crear_categoria("Golosinas")
    entorno.enviar(REDONDEO_DEFINIR, _definir(lista_id, golosinas, multiplo="10.00"))
    (primera,) = _redondeos(entorno, lista_id)

    entorno.enviar(
        REDONDEO_DEFINIR, _definir(lista_id, golosinas, multiplo="50.00", direccion="ABAJO")
    )

    (unica,) = _redondeos(entorno, lista_id)
    assert unica.id == primera.id
    assert (unica.multiplo, unica.direccion) == (Decimal("50.00"), "ABAJO")


def test_dos_categorias_distintas_tienen_cada_una_su_sobrescritura(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()
    golosinas = entorno.crear_categoria("Golosinas")

    entorno.enviar(REDONDEO_DEFINIR, _definir(lista_id, golosinas, multiplo="10"))
    entorno.enviar(REDONDEO_DEFINIR, _definir(lista_id, entorno.categoria_id, multiplo="500"))

    assert sorted(r.multiplo for r in _redondeos(entorno, lista_id)) == [
        Decimal("10.00"),
        Decimal("500.00"),
    ]


def test_la_misma_categoria_en_otra_lista_es_otra_sobrescritura(entorno: Entorno) -> None:
    general = entorno.crear_lista("General")
    mayorista = entorno.crear_lista("Mayorista")

    entorno.enviar(REDONDEO_DEFINIR, _definir(general, entorno.categoria_id, multiplo="10"))
    entorno.enviar(REDONDEO_DEFINIR, _definir(mayorista, entorno.categoria_id, multiplo="20"))

    assert [r.multiplo for r in _redondeos(entorno, general)] == [Decimal("10.00")]
    assert [r.multiplo for r in _redondeos(entorno, mayorista)] == [Decimal("20.00")]


def test_desactivar_la_sobrescritura_la_conserva_inactiva(entorno: Entorno) -> None:
    """Escenario "Sobrescritura desactivada": no se borra, y no se aplica (el generador del
    borrador solo lee las activas)."""
    lista_id = entorno.crear_lista()
    golosinas = entorno.crear_categoria("Golosinas")
    entorno.enviar(REDONDEO_DEFINIR, _definir(lista_id, golosinas))

    entorno.enviar(REDONDEO_DEFINIR, _definir(lista_id, golosinas, activo=False))

    (redondeo,) = _redondeos(entorno, lista_id)
    assert redondeo.activo is False
    entorno.enviar(REDONDEO_DEFINIR, _definir(lista_id, golosinas, activo=True))
    (reactivada,) = _redondeos(entorno, lista_id)
    assert reactivada.activo is True


@pytest.mark.parametrize(
    ("multiplo", "direccion"),
    [("0", "ARRIBA"), ("-10", "ARRIBA"), ("0.005", "ARRIBA"), ("diez", "ARRIBA"), ("10", "MITAD")],
)
def test_un_redondeo_invalido_se_rechaza_con_redondeo_invalido(
    entorno: Entorno, multiplo: str, direccion: str
) -> None:
    lista_id = entorno.crear_lista()

    with pytest.raises(RedondeoInvalidoError) as error:
        entorno.enviar(
            REDONDEO_DEFINIR,
            _definir(lista_id, entorno.categoria_id, multiplo=multiplo, direccion=direccion),
        )

    assert error.value.codigo == "REDONDEO_INVALIDO"
    entorno.sesion.rollback()
    assert _redondeos(entorno, lista_id) == []


def test_inv21_una_categoria_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Categoría de otra organización" (INV-21, INV-02): 404 y no se crea nada."""
    lista_id = entorno.crear_lista()
    categoria_ajena = Entorno(db_session).categoria_id

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.enviar(REDONDEO_DEFINIR, _definir(lista_id, categoria_ajena))

    assert error.value.status_http == 404
    db_session.rollback()
    assert _redondeos(entorno, lista_id) == []


def test_una_categoria_inexistente_responde_404(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()

    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(REDONDEO_DEFINIR, _definir(lista_id, uuid4()))


def test_inv21_la_lista_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    lista_ajena = Entorno(db_session).crear_lista("General")

    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(REDONDEO_DEFINIR, _definir(lista_ajena, entorno.categoria_id))

    db_session.rollback()


def test_sin_gestionar_listas_se_rechaza_con_403_y_no_crea_nada(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()
    entorno.actuar_con_permisos(frozenset({"PUBLICAR_LISTAS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(REDONDEO_DEFINIR, _definir(lista_id, entorno.categoria_id))

    entorno.sesion.rollback()
    assert _redondeos(entorno, lista_id) == []


def test_inv06_el_doble_envio_devuelve_el_resultado_original_y_no_duplica(
    entorno: Entorno,
) -> None:
    lista_id = entorno.crear_lista()
    operation_id = uuid4()
    contenido = _definir(lista_id, entorno.categoria_id)

    primero = entorno.enviar(REDONDEO_DEFINIR, contenido, operation_id=operation_id)
    segundo = entorno.enviar(REDONDEO_DEFINIR, contenido, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(_redondeos(entorno, lista_id)) == 1
    assert len(entorno.auditorias(REDONDEO_DEFINIR)) == 1
    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(
            REDONDEO_DEFINIR,
            _definir(lista_id, entorno.categoria_id, multiplo="99"),
            operation_id=operation_id,
        )


def test_el_contenido_no_acepta_la_organizacion_ni_el_multiplo_como_numero(
    entorno: Entorno,
) -> None:
    lista_id = entorno.crear_lista()

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(
            REDONDEO_DEFINIR,
            _definir(lista_id, entorno.categoria_id, organizacion_id=str(uuid4())),
        )
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(REDONDEO_DEFINIR, _definir(lista_id, entorno.categoria_id, multiplo=10))
