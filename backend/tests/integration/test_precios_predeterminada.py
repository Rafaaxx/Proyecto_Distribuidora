"""Change 13, tarea 10.3: `LISTA_PRECIO_PREDETERMINADA_DEFINIR` (spec delta
`organizacion/parametros-de-organizacion`; `design.md` D11 punto 2, D14).

El handler vive en `precios`; la escritura de `configuracion_organizacion.lista_precio_default_id`
va por `identidad/service.py`. Solo `ONLINE`, con `ADMIN_CONFIGURACION` (mismo criterio que
`CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR`: lo que se toca es la organización).

Reglas citadas: PRC-20, AUD-01, SEG-06, SEG-07, INV-02, INV-06, INV-11, INV-21, `design.md` D11.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from precios_utiles import MOMENTO, RELOJ, Entorno
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError
from app.core.errors import PermisoRequeridoError
from app.modules.precios.domain.errores import ListaInactivaError, RecursoNoEncontradoError
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PERMISOS = frozenset({"GESTIONAR_LISTAS", "GESTIONAR_CLIENTES", "ADMIN_CONFIGURACION"})
ACCION = "LISTA_PRECIO_PREDETERMINADA_DEFINIR"


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS)


def _auditoria_de_configuracion(entorno: Entorno) -> list[object]:
    return [a for a in entorno.auditorias(ACCION) if a.entidad == "configuracion_organizacion"]


def test_definir_la_lista_general_como_predeterminada(entorno: Entorno) -> None:
    """Escenario "Definir la lista General como predeterminada": auditoría con el valor
    anterior nulo y el nuevo (AUD-01)."""
    general = entorno.crear_lista("General")
    assert entorno.predeterminada() is None

    comando = entorno.definir_predeterminada(general)

    assert comando.estado == "ACEPTADO"
    assert comando.resultado == {"lista_id": str(general)}
    assert entorno.predeterminada() == general
    (auditoria,) = _auditoria_de_configuracion(entorno)
    assert auditoria.antes == {"lista_precio_default_id": None}  # type: ignore[attr-defined]
    assert auditoria.despues == {"lista_precio_default_id": str(general)}  # type: ignore[attr-defined]
    assert auditoria.usuario_id == entorno.usuario_id  # type: ignore[attr-defined]
    assert auditoria.entidad_id == entorno.org  # type: ignore[attr-defined]


def test_cambiar_la_predeterminada_no_toca_clientes_ni_versiones(entorno: Entorno) -> None:
    """Escenario "Cambiar la lista predeterminada"."""
    general, version_id = entorno.borrador_de_general("General")
    entorno.publicar_por_sql(version_id)
    mayorista = entorno.crear_lista("Mayorista")
    minorista = entorno.crear_lista("Minorista")
    cliente_id = entorno.crear_cliente(lista_precio_id=minorista)
    entorno.definir_predeterminada(general)
    version_antes = entorno.versiones(general)[0].estado
    precios_antes = {k: v.precio_final for k, v in entorno.precios(version_id).items()}

    entorno.definir_predeterminada(mayorista)

    assert entorno.predeterminada() == mayorista
    assert entorno.cliente(cliente_id).lista_precio_id == minorista, "el cliente conserva la suya"
    assert entorno.versiones(general)[0].estado == version_antes
    assert {k: v.precio_final for k, v in entorno.precios(version_id).items()} == precios_antes
    segunda = _auditoria_de_configuracion(entorno)[-1]
    assert segunda.antes == {"lista_precio_default_id": str(general)}  # type: ignore[attr-defined]
    assert segunda.despues == {"lista_precio_default_id": str(mayorista)}  # type: ignore[attr-defined]


def test_una_lista_inactiva_se_rechaza_y_la_configuracion_no_cambia(entorno: Entorno) -> None:
    """Escenario "Lista inactiva"."""
    general = entorno.crear_lista("General")
    especial = entorno.crear_lista("Especial")
    entorno.definir_predeterminada(general)
    entorno.desactivar_lista(especial, "Especial")

    with pytest.raises(ListaInactivaError) as error:
        entorno.definir_predeterminada(especial)

    assert error.value.codigo == "LISTA_INACTIVA"
    entorno.sesion.rollback()
    assert entorno.predeterminada() == general


def test_inv21_una_lista_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Lista de otra organización"."""
    ajena = Entorno(db_session, permisos=PERMISOS).crear_lista("General")

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.definir_predeterminada(ajena)

    assert error.value.status_http == 404
    entorno.sesion.rollback()
    assert entorno.predeterminada() is None


def test_una_lista_inexistente_responde_404(entorno: Entorno) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        entorno.definir_predeterminada(uuid4())


def test_sin_admin_configuracion_se_rechaza_con_403_y_no_cambia(entorno: Entorno) -> None:
    """Escenario "Sin permiso de configuración": `GESTIONAR_LISTAS` solo no alcanza (SEG-06)."""
    general = entorno.crear_lista("General")
    entorno.actuar_con_permisos(frozenset({"GESTIONAR_LISTAS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.definir_predeterminada(general)

    entorno.sesion.rollback()
    assert entorno.predeterminada() is None
    assert _auditoria_de_configuracion(entorno) == []


def test_el_doble_envio_devuelve_el_resultado_original_con_una_sola_auditoria(
    entorno: Entorno,
) -> None:
    """Escenario "Doble envío" (INV-06)."""
    general = entorno.crear_lista("General")
    operacion = uuid4()

    primero = entorno.definir_predeterminada(general, operation_id=operacion)
    segundo = entorno.definir_predeterminada(general, operation_id=operacion)

    assert primero.resultado == segundo.resultado
    assert len(_auditoria_de_configuracion(entorno)) == 1
    assert len(entorno.auditorias(ACCION)) == 2, "la del comando (bus) y la del cambio"


def test_el_mismo_operation_id_con_otra_lista_se_rechaza_como_inconsistente(
    entorno: Entorno,
) -> None:
    general = entorno.crear_lista("General")
    mayorista = entorno.crear_lista("Mayorista")
    operacion = uuid4()
    entorno.definir_predeterminada(general, operation_id=operacion)

    with pytest.raises(ComandoInconsistenteError):
        entorno.definir_predeterminada(mayorista, operation_id=operacion)

    entorno.sesion.rollback()
    assert entorno.predeterminada() == general


def test_el_comando_es_solo_online(entorno: Entorno) -> None:
    """Escenario "Solo con conexión" (`02` §6.5)."""
    general = entorno.crear_lista("General")
    item = ItemLote(
        operation_id=uuid4(),
        tipo=ACCION,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={"lista_id": str(general)},
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
    assert entorno.predeterminada() is None


def test_el_contenido_no_acepta_un_organizacion_id(entorno: Entorno) -> None:
    general = entorno.crear_lista("General")

    with pytest.raises(Exception) as error:  # noqa: PT011
        entorno.enviar(ACCION, {"lista_id": str(general), "organizacion_id": str(uuid4())})

    assert "organizacion_id" in str(error.value)


def test_la_base_rechaza_una_lista_inexistente_escrita_por_fuera_del_servicio(
    entorno: Entorno,
) -> None:
    """Escenario "La base rechaza una lista inexistente escrita por fuera del servicio"
    (INV-02): clave foránea compuesta."""
    with pytest.raises(IntegrityError):
        entorno.sesion.execute(
            text(
                "UPDATE configuracion_organizacion SET lista_precio_default_id = :l "
                "WHERE organizacion_id = :o"
            ),
            {"l": uuid4(), "o": entorno.org},
        )
        entorno.sesion.flush()
    entorno.sesion.rollback()


def test_la_predeterminada_inactivada_por_sql_deja_sin_lista_aplicable_pero_no_cambia_la_config(
    entorno: Entorno,
) -> None:
    """La desactivación de la predeterminada la rechaza `LISTA_EN_USO` (10.2): estando definida,
    ninguna lista se desactiva sin antes definir otra."""
    general = entorno.crear_lista("General")
    mayorista = entorno.crear_lista("Mayorista")
    entorno.definir_predeterminada(general)
    entorno.definir_predeterminada(mayorista)

    entorno.desactivar_lista(general, "General")

    assert entorno.predeterminada() == mayorista
