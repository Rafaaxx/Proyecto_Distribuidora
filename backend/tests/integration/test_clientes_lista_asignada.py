"""Change 13, tarea 10.1: la lista de precios asignada al cliente en `CLIENTE_CREAR` y
`CLIENTE_MODIFICAR` (spec delta `clientes/fichas-de-cliente`; `design.md` D11 punto 1).

`clientes` valida la lista solo por `precios/service.py` (404 si no existe en la organización,
`LISTA_INACTIVA` si está inactiva) y la base garantiza la clave foránea compuesta. Reemplaza la
decisión D2 del change 07 (la lista asignada no se ofrecía).

Reglas citadas: CLI-01, PRC-20, INV-02, INV-06, INV-21, SEG-07, `design.md` D11.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from precios_utiles import Entorno
from sqlalchemy.orm import Session

from app.modules.precios.domain.errores import ListaInactivaError, RecursoNoEncontradoError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS = frozenset({"GESTIONAR_LISTAS", "GESTIONAR_CLIENTES", "ADMIN_CONFIGURACION"})


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS)


def test_asignar_una_lista_al_cliente_la_guarda(entorno: Entorno) -> None:
    """Escenario "Asignar una lista al cliente"."""
    mayorista = entorno.crear_lista("Mayorista")
    cliente_id = entorno.crear_cliente()
    assert entorno.cliente(cliente_id).lista_precio_id is None

    comando = entorno.modificar_cliente(cliente_id, lista_precio_id=mayorista)

    assert comando.estado == "ACEPTADO"
    assert entorno.cliente(cliente_id).lista_precio_id == mayorista


def test_crear_el_cliente_con_la_lista_asignada(entorno: Entorno) -> None:
    mayorista = entorno.crear_lista("Mayorista")

    cliente_id = entorno.crear_cliente(lista_precio_id=mayorista)

    assert entorno.cliente(cliente_id).lista_precio_id == mayorista


def test_crear_el_cliente_sin_lista_lo_deja_sin_asignar(entorno: Entorno) -> None:
    """Sin lista asignada compra con la predeterminada de la organización (PRC-20)."""
    cliente_id = entorno.crear_cliente()

    assert entorno.cliente(cliente_id).lista_precio_id is None


def test_quitar_la_lista_asignada_con_nulo(entorno: Entorno) -> None:
    """Escenario "Quitar la lista asignada"."""
    mayorista = entorno.crear_lista("Mayorista")
    cliente_id = entorno.crear_cliente(lista_precio_id=mayorista)

    entorno.modificar_cliente(cliente_id, lista_precio_id=None)

    assert entorno.cliente(cliente_id).lista_precio_id is None


def test_modificar_sin_el_campo_lista_conserva_la_asignada(entorno: Entorno) -> None:
    """Escenario "Modificar un cliente sin mandar la lista conserva la asignada" (ajuste A,
    PUT: ausente = conservar, nulo = quitar)."""
    mayorista = entorno.crear_lista("Mayorista")
    cliente_id = entorno.crear_cliente(lista_precio_id=mayorista)

    entorno.modificar_cliente(cliente_id, nombre="Kiosco Renombrado")

    cliente = entorno.cliente(cliente_id)
    assert (cliente.lista_precio_id, cliente.nombre) == (mayorista, "Kiosco Renombrado")


def test_modificar_sin_el_campo_lista_conserva_aunque_este_inactiva_con_el_cliente_inactivo(
    entorno: Entorno,
) -> None:
    """Conservar no revalida: corregir un dato de un cliente `INACTIVO` con lista inactiva
    no obliga a tocar la lista."""
    especial = entorno.crear_lista("Especial")
    cliente_id = entorno.crear_cliente(lista_precio_id=especial)
    entorno.modificar_cliente(cliente_id, lista_precio_id=especial, estado="INACTIVO")
    entorno.desactivar_lista(especial)

    entorno.modificar_cliente(cliente_id, estado="INACTIVO", nombre="Otro nombre")

    cliente = entorno.cliente(cliente_id)
    assert (cliente.lista_precio_id, cliente.nombre) == (especial, "Otro nombre")


def test_reactivar_sin_el_campo_lista_con_la_asignada_inactiva_se_rechaza(
    entorno: Entorno,
) -> None:
    """Conservar no salta D11: el cliente que queda activo revalida la lista que conserva."""
    especial = entorno.crear_lista("Especial")
    cliente_id = entorno.crear_cliente(lista_precio_id=especial)
    entorno.modificar_cliente(cliente_id, lista_precio_id=especial, estado="INACTIVO")
    entorno.desactivar_lista(especial)

    with pytest.raises(ListaInactivaError):
        entorno.modificar_cliente(cliente_id, estado="ACTIVO")
    entorno.sesion.rollback()

    assert entorno.cliente(cliente_id).estado == "INACTIVO"


def test_cambiar_de_una_lista_a_otra(entorno: Entorno) -> None:
    mayorista = entorno.crear_lista("Mayorista")
    minorista = entorno.crear_lista("Minorista")
    cliente_id = entorno.crear_cliente(lista_precio_id=mayorista)

    entorno.modificar_cliente(cliente_id, lista_precio_id=minorista)

    assert entorno.cliente(cliente_id).lista_precio_id == minorista


def test_una_lista_inactiva_se_rechaza_al_crear_y_no_queda_el_cliente(
    entorno: Entorno,
) -> None:
    """Escenario "Lista inactiva" (alta)."""
    especial = entorno.crear_lista("Especial")
    entorno.desactivar_lista(especial, "Especial")
    antes = entorno.cantidad("cliente")

    with pytest.raises(ListaInactivaError) as error:
        entorno.crear_cliente(lista_precio_id=especial)

    assert error.value.codigo == "LISTA_INACTIVA"
    entorno.sesion.rollback()
    assert entorno.cantidad("cliente") == antes


def test_una_lista_inactiva_se_rechaza_al_modificar_y_el_cliente_no_cambia(
    entorno: Entorno,
) -> None:
    """Escenario "Lista inactiva" (modificación)."""
    mayorista = entorno.crear_lista("Mayorista")
    especial = entorno.crear_lista("Especial")
    entorno.desactivar_lista(especial, "Especial")
    cliente_id = entorno.crear_cliente(lista_precio_id=mayorista)

    with pytest.raises(ListaInactivaError):
        entorno.modificar_cliente(cliente_id, lista_precio_id=especial, nombre="Otro nombre")

    entorno.sesion.rollback()
    cliente = entorno.cliente(cliente_id)
    assert (cliente.lista_precio_id, cliente.nombre) == (mayorista, "Kiosco El Faro")


def test_inv21_una_lista_de_otra_organizacion_responde_404_y_el_cliente_no_cambia(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Lista de otra organización"."""
    lista_ajena = Entorno(db_session, permisos=PERMISOS).crear_lista("Mayorista")
    cliente_id = entorno.crear_cliente()

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.modificar_cliente(cliente_id, lista_precio_id=lista_ajena)

    assert error.value.status_http == 404
    entorno.sesion.rollback()
    assert entorno.cliente(cliente_id).lista_precio_id is None


def test_inv21_crear_con_una_lista_inexistente_o_ajena_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    lista_ajena = Entorno(db_session, permisos=PERMISOS).crear_lista("Mayorista")

    with pytest.raises(RecursoNoEncontradoError):
        entorno.crear_cliente(lista_precio_id=lista_ajena)
    entorno.sesion.rollback()
    with pytest.raises(RecursoNoEncontradoError):
        entorno.crear_cliente(lista_precio_id=uuid4())


def test_inv06_el_doble_envio_con_lista_asignada_devuelve_el_resultado_original(
    entorno: Entorno,
) -> None:
    """Escenario "Doble envío con lista asignada"."""
    mayorista = entorno.crear_lista("Mayorista")
    cliente_id = entorno.crear_cliente()
    operacion = uuid4()

    primero = entorno.modificar_cliente(
        cliente_id, lista_precio_id=mayorista, operation_id=operacion
    )
    segundo = entorno.modificar_cliente(
        cliente_id, lista_precio_id=mayorista, operation_id=operacion
    )

    assert primero.resultado == segundo.resultado
    assert len(entorno.auditorias("CLIENTE_MODIFICAR")) == 1
    assert entorno.cliente(cliente_id).lista_precio_id == mayorista


def test_reactivar_un_cliente_con_una_lista_inactiva_se_rechaza(entorno: Entorno) -> None:
    """Un cliente `ACTIVO` nunca queda con una lista inactiva: reactivar uno `INACTIVO` que
    conserva una lista que después se desactivó se rechaza hasta que se cambie la lista."""
    especial = entorno.crear_lista("Especial")
    cliente_id = entorno.crear_cliente(lista_precio_id=especial)
    entorno.modificar_cliente(cliente_id, lista_precio_id=especial, estado="INACTIVO")
    entorno.desactivar_lista(especial, "Especial")

    with pytest.raises(ListaInactivaError):
        entorno.modificar_cliente(cliente_id, lista_precio_id=especial, estado="ACTIVO")

    entorno.sesion.rollback()
    assert entorno.cliente(cliente_id).estado == "INACTIVO"


def test_editar_otros_datos_de_un_cliente_inactivo_con_una_lista_inactiva_se_permite(
    entorno: Entorno,
) -> None:
    """No se obliga a cambiar una lista que ya tenía para corregir otro dato de un cliente
    `INACTIVO` (la lista inactiva solo se rechaza si el cliente queda activo o si se la elige)."""
    especial = entorno.crear_lista("Especial")
    cliente_id = entorno.crear_cliente(lista_precio_id=especial)
    entorno.modificar_cliente(cliente_id, lista_precio_id=especial, estado="INACTIVO")
    entorno.desactivar_lista(especial, "Especial")

    entorno.modificar_cliente(
        cliente_id, lista_precio_id=especial, estado="INACTIVO", nombre="Nombre corregido"
    )

    cliente = entorno.cliente(cliente_id)
    assert (cliente.nombre, cliente.lista_precio_id) == ("Nombre corregido", especial)
