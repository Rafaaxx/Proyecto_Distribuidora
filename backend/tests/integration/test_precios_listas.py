"""Change 13, tarea 5.1: `LISTA_PRECIO_CREAR` y `LISTA_PRECIO_MODIFICAR` v1 por el bus,
contra PostgreSQL real (spec `precios/listas-de-precios`).

Se procesa por `sync_service.procesar_comando`, que maneja la transacción (mismo criterio
que `test_pagos_proveedor_registrar.py`). La cobertura HTTP es de `test_precios_api.py`
(tarea 5.4).

Reglas citadas: PRC-01, PRC-04, PRC-14, INV-01, INV-02, INV-03, INV-06, INV-11, INV-21,
SYN-02, SEG-06, SEG-07, TR-10, `design.md` D9, D13.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from precios_utiles import (
    LISTA_CREAR,
    LISTA_MODIFICAR,
    MOMENTO,
    RELOJ,
    Entorno,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.commands.huella import ContenidoNoSerializableError
from app.core.errors import PermisoRequeridoError
from app.modules.precios.domain.errores import (
    NombreDuplicadoError,
    NombreInvalidoError,
    RecursoNoEncontradoError,
    RedondeoInvalidoError,
)
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _contenido(**cambios: object) -> dict[str, object]:
    cuerpo: dict[str, object] = {
        "nombre": "General",
        "redondeo_multiplo": "100.00",
        "redondeo_direccion": "ARRIBA",
    }
    cuerpo.update(cambios)
    return cuerpo


def _modificar(lista_id: UUID, **cambios: object) -> dict[str, object]:
    cuerpo: dict[str, object] = {
        "lista_id": str(lista_id),
        "nombre": "General",
        "redondeo_multiplo": "100.00",
        "redondeo_direccion": "ARRIBA",
        "activo": True,
    }
    cuerpo.update(cambios)
    return cuerpo


# --- LISTA_PRECIO_CREAR: el alta (PRC-01, PRC-14) -----------------------------------------


def test_alta_de_la_lista_general(entorno: Entorno) -> None:
    """Escenario "Alta de la lista General": ACEPTADO, activa, sin versiones y con una sola
    fila de auditoría con el `operation_id` (AUD-01)."""
    operation_id = uuid4()

    comando = entorno.enviar(LISTA_CREAR, _contenido(), operation_id=operation_id)

    assert comando.estado == "ACEPTADO"
    (lista,) = entorno.listas()
    assert comando.resultado == {"lista_id": str(lista.id)}
    assert lista.nombre == "General"
    assert lista.redondeo_multiplo == Decimal("100.00")
    assert lista.redondeo_direccion == "ARRIBA"
    assert lista.activo is True
    assert lista.creado_en == MOMENTO
    assert lista.actualizado_por_id == entorno.usuario_id
    assert entorno.cantidad("lista_version") == 0
    (auditoria,) = entorno.auditorias(LISTA_CREAR)
    assert auditoria.operation_id == operation_id
    assert auditoria.usuario_id == entorno.usuario_id


def test_el_identificador_lo_genera_el_servidor_como_uuid_v7(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()

    assert lista_id.version == 7


def test_el_nombre_se_guarda_recortado_y_el_multiplo_con_dos_decimales(entorno: Entorno) -> None:
    entorno.enviar(LISTA_CREAR, _contenido(nombre="  Mayorista  ", redondeo_multiplo="50"))

    (lista,) = entorno.listas()
    assert lista.nombre == "Mayorista"
    assert str(lista.redondeo_multiplo) == "50.00"


@pytest.mark.parametrize("direccion", ["ARRIBA", "CERCANO", "ABAJO"])
def test_las_tres_direcciones_se_aceptan(entorno: Entorno, direccion: str) -> None:
    entorno.enviar(LISTA_CREAR, _contenido(redondeo_direccion=direccion))

    (lista,) = entorno.listas()
    assert lista.redondeo_direccion == direccion


def test_un_nombre_repetido_sin_distinguir_mayusculas_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Nombre repetido": ` general ` choca con `General`."""
    entorno.crear_lista("General")

    with pytest.raises(NombreDuplicadoError) as error:
        entorno.enviar(LISTA_CREAR, _contenido(nombre=" general "))

    assert error.value.codigo == "NOMBRE_DUPLICADO"
    entorno.sesion.rollback()
    assert [lista.nombre for lista in entorno.listas()] == ["General"]


def test_el_mismo_nombre_en_otra_organizacion_se_acepta(
    entorno: Entorno, db_session: Session
) -> None:
    entorno.crear_lista("General")
    otra = Entorno(db_session)

    otra.crear_lista("General")

    assert len(otra.listas()) == 1
    assert len(entorno.listas()) == 1


@pytest.mark.parametrize("nombre", ["", "   ", "\t"])
def test_un_nombre_vacio_se_rechaza(entorno: Entorno, nombre: str) -> None:
    with pytest.raises(NombreInvalidoError):
        entorno.enviar(LISTA_CREAR, _contenido(nombre=nombre))

    entorno.sesion.rollback()
    assert entorno.listas() == []


@pytest.mark.parametrize(
    ("multiplo", "direccion"),
    [
        ("0", "ARRIBA"),
        ("-100", "ARRIBA"),
        ("0.005", "ARRIBA"),
        ("cien", "ARRIBA"),
        ("100.00", "MITAD"),
    ],
)
def test_un_redondeo_invalido_se_rechaza_y_no_crea_la_lista(
    entorno: Entorno, multiplo: str, direccion: str
) -> None:
    with pytest.raises(RedondeoInvalidoError) as error:
        entorno.enviar(
            LISTA_CREAR, _contenido(redondeo_multiplo=multiplo, redondeo_direccion=direccion)
        )

    assert error.value.codigo == "REDONDEO_INVALIDO"
    entorno.sesion.rollback()
    assert entorno.listas() == []


@pytest.mark.parametrize("multiplo", [100, None])
def test_inv03_un_multiplo_que_no_viaja_como_string_se_rechaza(
    entorno: Entorno, multiplo: object
) -> None:
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(LISTA_CREAR, _contenido(redondeo_multiplo=multiplo))

    assert entorno.listas() == []


def test_inv03_un_multiplo_de_punto_flotante_ni_siquiera_llega_al_handler(
    entorno: Entorno,
) -> None:
    """La huella canónica del bus no admite `float`: se rechaza antes de ejecutar nada."""
    with pytest.raises(ContenidoNoSerializableError):
        entorno.enviar(LISTA_CREAR, _contenido(redondeo_multiplo=100.0))

    assert entorno.listas() == []


def test_un_campo_ajeno_en_el_contenido_se_rechaza(entorno: Entorno) -> None:
    """El contenido no acepta `organizacion_id`: sale siempre del token (INV-21)."""
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(LISTA_CREAR, _contenido(organizacion_id=str(uuid4())))

    assert entorno.listas() == []


def test_sin_gestionar_listas_se_rechaza_con_403_y_sin_reserva(db_session: Session) -> None:
    """Escenario "Sin permiso" (SEG-06): `PUBLICAR_LISTAS` no alcanza para crear una lista;
    no queda ni la lista ni la reserva del `operation_id`."""
    entorno = Entorno(db_session, permisos=frozenset({"PUBLICAR_LISTAS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(LISTA_CREAR, _contenido(), operation_id=uuid4())

    db_session.rollback()
    assert entorno.listas() == []
    assert entorno.comandos() == []


def test_la_lista_es_solo_online(entorno: Entorno) -> None:
    """Escenario "Solo con conexión" (`02` §6.5): un lote `OFFLINE` la rechaza sin efectos."""
    item = ItemLote(
        operation_id=uuid4(),
        tipo=LISTA_CREAR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=_contenido(),
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
    assert entorno.listas() == []


def test_inv06_el_doble_envio_devuelve_el_resultado_original_y_no_duplica(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()

    primero = entorno.enviar(LISTA_CREAR, _contenido(), operation_id=operation_id)
    segundo = entorno.enviar(LISTA_CREAR, _contenido(), operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.listas()) == 1
    assert len(entorno.auditorias(LISTA_CREAR)) == 1


def test_inv06_el_mismo_operation_id_con_otro_nombre_es_inconsistente(entorno: Entorno) -> None:
    operation_id = uuid4()
    entorno.enviar(LISTA_CREAR, _contenido(), operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(LISTA_CREAR, _contenido(nombre="Mayorista"), operation_id=operation_id)

    entorno.sesion.rollback()
    assert [lista.nombre for lista in entorno.listas()] == ["General"]


# --- LISTA_PRECIO_MODIFICAR (PRC-01, PRC-04, INV-11, INV-21) -------------------------------


def test_cambiar_el_redondeo_de_la_lista(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()

    comando = entorno.enviar(
        LISTA_MODIFICAR,
        _modificar(lista_id, redondeo_multiplo="50.00", redondeo_direccion="ABAJO"),
    )

    assert comando.estado == "ACEPTADO"
    assert comando.resultado == {"lista_id": str(lista_id)}
    (lista,) = entorno.listas()
    assert (lista.redondeo_multiplo, lista.redondeo_direccion) == (Decimal("50.00"), "ABAJO")
    assert lista.actualizado_por_id == entorno.usuario_id


def test_renombrar_la_lista_y_conservar_su_identificador(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista("General")

    entorno.enviar(LISTA_MODIFICAR, _modificar(lista_id, nombre="  GENERAL 2026  "))

    (lista,) = entorno.listas()
    assert (lista.id, lista.nombre) == (lista_id, "GENERAL 2026")


def test_cambiar_solo_las_mayusculas_del_propio_nombre_no_choca_consigo_misma(
    entorno: Entorno,
) -> None:
    lista_id = entorno.crear_lista("General")

    entorno.enviar(LISTA_MODIFICAR, _modificar(lista_id, nombre="GENERAL"))

    (lista,) = entorno.listas()
    assert lista.nombre == "GENERAL"


def test_renombrar_con_el_nombre_de_otra_lista_se_rechaza(entorno: Entorno) -> None:
    entorno.crear_lista("General")
    especial = entorno.crear_lista("Especial")

    with pytest.raises(NombreDuplicadoError):
        entorno.enviar(LISTA_MODIFICAR, _modificar(especial, nombre="general"))

    entorno.sesion.rollback()
    assert sorted(lista.nombre for lista in entorno.listas()) == ["Especial", "General"]


def test_desactivar_y_reactivar_una_lista_sin_uso(entorno: Entorno) -> None:
    """Escenario "Desactivar una lista sin uso": queda inactiva y sigue existiendo."""
    lista_id = entorno.crear_lista("Especial")

    entorno.enviar(LISTA_MODIFICAR, _modificar(lista_id, nombre="Especial", activo=False))
    assert [lista.activo for lista in entorno.listas()] == [False]

    entorno.enviar(LISTA_MODIFICAR, _modificar(lista_id, nombre="Especial", activo=True))
    assert [lista.activo for lista in entorno.listas()] == [True]


@pytest.mark.parametrize(
    ("cambios", "error"),
    [
        ({"nombre": " "}, NombreInvalidoError),
        ({"redondeo_multiplo": "0"}, RedondeoInvalidoError),
        ({"redondeo_multiplo": "10.005"}, RedondeoInvalidoError),
        ({"redondeo_direccion": "MITAD"}, RedondeoInvalidoError),
    ],
)
def test_modificar_con_datos_invalidos_se_rechaza_y_no_cambia_la_lista(
    entorno: Entorno, cambios: dict[str, object], error: type[Exception]
) -> None:
    lista_id = entorno.crear_lista()

    with pytest.raises(error):
        entorno.enviar(LISTA_MODIFICAR, _modificar(lista_id, **cambios))

    entorno.sesion.rollback()
    (lista,) = entorno.listas()
    assert (lista.nombre, lista.redondeo_multiplo, lista.redondeo_direccion) == (
        "General",
        Decimal("100.00"),
        "ARRIBA",
    )


def test_inv21_modificar_la_lista_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Lista de otra organización" (INV-21, SEG-07)."""
    ajena = Entorno(db_session).crear_lista("General")

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.enviar(LISTA_MODIFICAR, _modificar(ajena, redondeo_direccion="ABAJO"))

    assert error.value.status_http == 404
    db_session.rollback()
    (de_b,) = db_session.execute(
        text("SELECT redondeo_direccion FROM lista_precio WHERE id = :l"), {"l": ajena}
    ).all()
    assert de_b.redondeo_direccion == "ARRIBA"


def test_modificar_una_lista_inexistente_responde_404(entorno: Entorno) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(LISTA_MODIFICAR, _modificar(uuid4()))


def test_sin_gestionar_listas_modificar_se_rechaza_con_403(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()
    entorno.actuar_con_permisos(frozenset({"PUBLICAR_LISTAS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(LISTA_MODIFICAR, _modificar(lista_id, redondeo_direccion="ABAJO"))

    entorno.sesion.rollback()
    (lista,) = entorno.listas()
    assert lista.redondeo_direccion == "ARRIBA"


def test_inv06_modificar_dos_veces_con_el_mismo_operation_id_aplica_una_vez(
    entorno: Entorno,
) -> None:
    lista_id = entorno.crear_lista()
    operation_id = uuid4()
    contenido = _modificar(lista_id, redondeo_direccion="CERCANO")

    primero = entorno.enviar(LISTA_MODIFICAR, contenido, operation_id=operation_id)
    segundo = entorno.enviar(LISTA_MODIFICAR, contenido, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.auditorias(LISTA_MODIFICAR)) == 1
    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(
            LISTA_MODIFICAR,
            _modificar(lista_id, redondeo_direccion="ABAJO"),
            operation_id=operation_id,
        )


# --- INV-11: cambiar el redondeo no toca lo publicado --------------------------------------


def test_inv11_cambiar_el_redondeo_de_la_lista_no_toca_una_version_publicada(
    entorno: Entorno,
) -> None:
    """Escenario "Cambiar el redondeo no toca lo publicado" (PRC-04): Vino A sigue a
    `8600.00` en la versión publicada después de pasar la lista a `ABAJO`."""
    lista_id = entorno.crear_lista()
    version_id = uuid4()
    entorno.sesion.execute(
        text(
            "INSERT INTO lista_version (id, organizacion_id, lista_id, numero, estado, "
            "vigencia_desde, creado_por_id, creado_en, publicado_por_id, publicado_en, "
            "operation_id) VALUES (:id, :org, :lista, 1, 'PUBLICADA', :m, :u, :m, :u, :m, :op)"
        ),
        {
            "id": version_id,
            "org": entorno.org,
            "lista": lista_id,
            "m": MOMENTO,
            "u": entorno.usuario_id,
            "op": uuid4(),
        },
    )
    entorno.sesion.execute(
        text(
            "INSERT INTO precio_item (id, organizacion_id, version_id, producto_id, "
            "unidades_referencia, precio_final, manual) "
            "VALUES (:id, :org, :v, :p, 6, 8600.00, true)"
        ),
        {"id": uuid4(), "org": entorno.org, "v": version_id, "p": entorno.vino_id},
    )
    antes = _filas_de_la_version(entorno.sesion, version_id)

    entorno.enviar(
        LISTA_MODIFICAR,
        _modificar(lista_id, redondeo_multiplo="500.00", redondeo_direccion="ABAJO"),
    )

    assert _filas_de_la_version(entorno.sesion, version_id) == antes
    assert antes[1] == [(entorno.vino_id, Decimal("8600.00"), 6)]


def _filas_de_la_version(sesion: Session, version_id: UUID) -> tuple[object, list[object]]:
    version = sesion.execute(
        text(
            "SELECT numero, estado, vigencia_desde, vigencia_hasta FROM lista_version WHERE id = :v"
        ),
        {"v": version_id},
    ).one()
    precios = sesion.execute(
        text(
            "SELECT producto_id, precio_final, unidades_referencia FROM precio_item "
            "WHERE version_id = :v ORDER BY producto_id"
        ),
        {"v": version_id},
    ).all()
    return tuple(version), [tuple(precio) for precio in precios]  # type: ignore[return-value]
