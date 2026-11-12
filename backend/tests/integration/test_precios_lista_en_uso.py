"""Change 13, tarea 10.2: una lista en uso no se desactiva (`LISTA_EN_USO`; spec
`precios/listas-de-precios`; `design.md` D11 punto 3, mismo criterio que ADR-024 y ADR-026).

Está en uso la lista predeterminada de la organización y la asignada a algún cliente que no
está `INACTIVO`. `clientes` registra en `precios` un verificador de uso (patrón de ADR-023), así
que `precios` no importa `clientes` (`02` §5.3: `clientes -> precios`, nunca al revés).

Reglas citadas: PRC-01, PRC-20, CLI-01, CLI-06, INV-21, TR-06, `design.md` D11 y D14.
"""

from __future__ import annotations

import pytest
from precios_utiles import Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.precios import service as precios_service
from app.modules.precios.domain.errores import ListaEnUsoError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS = frozenset({"GESTIONAR_LISTAS", "GESTIONAR_CLIENTES", "ADMIN_CONFIGURACION"})


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS)


def _activa(entorno: Entorno, lista_id: object) -> bool:
    (lista,) = [lista for lista in entorno.listas() if lista.id == lista_id]
    entorno.sesion.refresh(lista)
    return lista.activo


def test_una_lista_asignada_a_un_cliente_activo_no_se_desactiva(entorno: Entorno) -> None:
    """Escenario "Desactivar una lista asignada a un cliente"."""
    mayorista = entorno.crear_lista("Mayorista")
    entorno.crear_cliente("Kiosco El Faro", lista_precio_id=mayorista)

    with pytest.raises(ListaEnUsoError) as error:
        entorno.desactivar_lista(mayorista, "Mayorista")

    assert error.value.codigo == "LISTA_EN_USO"
    assert error.value.status_http == 409
    entorno.sesion.rollback()
    assert _activa(entorno, mayorista)


def test_una_lista_asignada_a_un_cliente_suspendido_tampoco_se_desactiva(
    entorno: Entorno,
) -> None:
    """Solo un cliente `INACTIVO` libera la lista: `SUSPENDIDO` sigue siendo "no inactivo"."""
    mayorista = entorno.crear_lista("Mayorista")
    cliente_id = entorno.crear_cliente(lista_precio_id=mayorista)
    entorno.modificar_cliente(cliente_id, lista_precio_id=mayorista, estado="SUSPENDIDO")

    with pytest.raises(ListaEnUsoError):
        entorno.desactivar_lista(mayorista, "Mayorista")


def test_una_lista_asignada_solo_a_un_cliente_inactivo_se_desactiva(entorno: Entorno) -> None:
    """Escenario "con el cliente `INACTIVO` ... sí"."""
    mayorista = entorno.crear_lista("Mayorista")
    cliente_id = entorno.crear_cliente(lista_precio_id=mayorista)
    entorno.modificar_cliente(cliente_id, lista_precio_id=mayorista, estado="INACTIVO")

    entorno.desactivar_lista(mayorista, "Mayorista")

    assert not _activa(entorno, mayorista)
    assert entorno.cliente(cliente_id).lista_precio_id == mayorista, "el cliente no se toca"


def test_reasignar_al_cliente_libera_la_lista(entorno: Entorno) -> None:
    mayorista = entorno.crear_lista("Mayorista")
    minorista = entorno.crear_lista("Minorista")
    cliente_id = entorno.crear_cliente(lista_precio_id=mayorista)
    entorno.modificar_cliente(cliente_id, lista_precio_id=minorista)

    entorno.desactivar_lista(mayorista, "Mayorista")

    assert not _activa(entorno, mayorista)
    with pytest.raises(ListaEnUsoError):
        entorno.desactivar_lista(minorista, "Minorista")


def test_la_lista_predeterminada_no_se_desactiva(entorno: Entorno) -> None:
    """Escenario "Desactivar la lista predeterminada"."""
    general = entorno.crear_lista("General")
    entorno.sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET lista_precio_default_id = :l "
            "WHERE organizacion_id = :o"
        ),
        {"l": general, "o": entorno.org},
    )

    with pytest.raises(ListaEnUsoError):
        entorno.desactivar_lista(general, "General")

    entorno.sesion.rollback()


def test_una_lista_sin_uso_se_desactiva_y_conserva_sus_versiones(entorno: Entorno) -> None:
    """Escenario "Desactivar una lista sin uso"."""
    lista_id, version_id = entorno.borrador_de_general("Especial")

    entorno.desactivar_lista(lista_id, "Especial")

    assert not _activa(entorno, lista_id)
    assert [version.id for version in entorno.versiones(lista_id)] == [version_id]


def test_modificar_una_lista_en_uso_sin_desactivarla_se_permite(entorno: Entorno) -> None:
    mayorista = entorno.crear_lista("Mayorista")
    entorno.crear_cliente(lista_precio_id=mayorista)

    entorno.enviar(
        "LISTA_PRECIO_MODIFICAR",
        {
            "lista_id": str(mayorista),
            "nombre": "Mayorista Plus",
            "redondeo_multiplo": "50.00",
            "redondeo_direccion": "CERCANO",
            "activo": True,
        },
    )

    (lista,) = [lista for lista in entorno.listas() if lista.id == mayorista]
    assert lista.nombre == "Mayorista Plus"


def test_el_uso_en_otra_organizacion_no_bloquea(entorno: Entorno, db_session: Session) -> None:
    """La lista de A solo cuenta los clientes de A (INV-21)."""
    de_a = entorno.crear_lista("Mayorista")
    otra = Entorno(db_session, permisos=PERMISOS)
    otra.crear_cliente("Kiosco B", lista_precio_id=otra.crear_lista("Mayorista"))

    entorno.desactivar_lista(de_a, "Mayorista")

    assert not _activa(entorno, de_a)


def test_clientes_registra_su_verificador_de_uso_al_cargarse() -> None:
    """Sin el registro de `clientes` el uso por clientes no se vería: la aplicación lo registra
    al importar su `service.py` (patrón de ADR-023)."""
    import app.modules.clientes.service  # noqa: F401

    assert "clientes" in precios_service.verificadores_de_uso_de_lista()


def test_lista_esta_en_uso_responde_por_la_predeterminada_y_por_los_clientes(
    entorno: Entorno,
) -> None:
    sin_uso = entorno.crear_lista("Sin uso")
    predeterminada = entorno.crear_lista("General")
    asignada = entorno.crear_lista("Mayorista")
    entorno.definir_predeterminada(predeterminada)
    entorno.crear_cliente(lista_precio_id=asignada)

    def en_uso(lista_id: object) -> bool:
        return precios_service.lista_esta_en_uso(entorno.org, lista_id, entorno.sesion)  # type: ignore[arg-type]

    assert (en_uso(sin_uso), en_uso(predeterminada), en_uso(asignada)) == (False, True, True)
