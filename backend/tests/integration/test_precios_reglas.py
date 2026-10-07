"""Change 13, tarea 5.2: `REGLA_MARGEN_CREAR` y `REGLA_MARGEN_MODIFICAR` v1 por el bus,
contra PostgreSQL real (spec `precios/reglas-de-margen`).

Reglas citadas: PRC-04, PRC-12, PRC-13, PRC-16, INV-01, INV-02, INV-03, INV-06, INV-11,
INV-21, SYN-02, SEG-06, SEG-07, `design.md` D8, D13, D14.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from precios_utiles import MOMENTO, REGLA_CREAR, REGLA_MODIFICAR, RELOJ, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.core.errors import PermisoRequeridoError
from app.modules.precios.domain.errores import (
    AlcanceInvalidoError,
    MargenInvalidoError,
    RecursoNoEncontradoError,
    ReglaDuplicadaError,
)
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _crear(lista_id: UUID, **cambios: object) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "lista_id": str(lista_id),
        "tipo": "MARKUP",
        "valor": "0.300000",
        "alcance_tipo": "LISTA",
        "alcance_id": None,
    }
    cuerpo.update(cambios)
    return cuerpo


def _modificar(lista_id: UUID, regla_id: UUID, **cambios: object) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "lista_id": str(lista_id),
        "regla_id": str(regla_id),
        "tipo": "MARKUP",
        "valor": "0.300000",
        "activo": True,
    }
    cuerpo.update(cambios)
    return cuerpo


# --- REGLA_MARGEN_CREAR: el alta (PRC-12, PRC-13) -------------------------------------------


def test_regla_general_de_la_lista(entorno: Entorno) -> None:
    """Escenario "Regla general de la lista": ACEPTADO, activa y con una sola fila de
    auditoría (con el `operation_id`)."""
    lista_id = entorno.crear_lista()
    operation_id = uuid4()

    comando = entorno.enviar(REGLA_CREAR, _crear(lista_id), operation_id=operation_id)

    assert comando.estado == "ACEPTADO"
    (regla,) = entorno.reglas(lista_id)
    assert comando.resultado == {"regla_id": str(regla.id), "lista_id": str(lista_id)}
    assert (regla.alcance_tipo, regla.alcance_id) == ("LISTA", None)
    assert (regla.tipo, regla.valor, regla.activo) == ("MARKUP", Decimal("0.300000"), True)
    assert regla.creado_en == MOMENTO
    assert regla.actualizado_por_id == entorno.usuario_id
    (auditoria,) = entorno.auditorias(REGLA_CREAR)
    assert auditoria.operation_id == operation_id


@pytest.mark.parametrize("alcance", ["PRODUCTO", "MARCA", "CATEGORIA", "PROVEEDOR"])
def test_regla_por_cada_alcance_con_su_entidad(entorno: Entorno, alcance: str) -> None:
    """Escenario "Regla por categoría con margen bruto" y sus hermanos: el alcance es la
    entidad indicada y la columna generada correspondiente se llena."""
    lista_id = entorno.crear_lista()
    entidades = {
        "PRODUCTO": entorno.vino_id,
        "MARCA": entorno.marca_id,
        "CATEGORIA": entorno.categoria_id,
        "PROVEEDOR": entorno.proveedor_id,
    }

    entorno.crear_regla(
        lista_id, tipo="MARGEN_BRUTO", alcance_tipo=alcance, alcance_id=entidades[alcance]
    )

    (regla,) = entorno.reglas(lista_id)
    assert (regla.alcance_tipo, regla.alcance_id) == (alcance, entidades[alcance])
    generadas = {
        "PRODUCTO": regla.producto_id,
        "MARCA": regla.marca_id,
        "CATEGORIA": regla.categoria_id,
        "PROVEEDOR": regla.proveedor_id,
    }
    assert generadas[alcance] == entidades[alcance]
    assert [valor for clave, valor in generadas.items() if clave != alcance] == [None] * 3


def test_un_markup_mayor_al_cien_por_ciento_se_acepta(entorno: Entorno) -> None:
    """Escenario "Markup mayor que el 100%" (PRC-12: el límite `m < 1` es del margen bruto)."""
    lista_id = entorno.crear_lista()

    entorno.crear_regla(lista_id, tipo="MARKUP", valor="1.500000")

    assert [regla.valor for regla in entorno.reglas(lista_id)] == [Decimal("1.500000")]


@pytest.mark.parametrize(
    ("tipo", "valor"),
    [
        ("MARGEN_BRUTO", "1.000000"),
        ("MARGEN_BRUTO", "1.200000"),
        ("MARKUP", "-0.100000"),
        ("MARKUP", "0.3000001"),
        ("MARKUP", "treinta"),
        ("DESCUENTO", "0.1"),
    ],
)
def test_un_valor_invalido_se_rechaza_con_margen_invalido(
    entorno: Entorno, tipo: str, valor: str
) -> None:
    lista_id = entorno.crear_lista()

    with pytest.raises(MargenInvalidoError) as error:
        entorno.enviar(REGLA_CREAR, _crear(lista_id, tipo=tipo, valor=valor))

    assert error.value.codigo == "MARGEN_INVALIDO"
    entorno.sesion.rollback()
    assert entorno.reglas(lista_id) == []


@pytest.mark.parametrize(
    ("alcance_tipo", "alcance_id"),
    [("LISTA", "entidad"), ("MARCA", None), ("PRODUCTO", None), ("CLIENTE", "entidad")],
)
def test_un_alcance_incoherente_se_rechaza_con_alcance_invalido(
    entorno: Entorno, alcance_tipo: str, alcance_id: str | None
) -> None:
    lista_id = entorno.crear_lista()
    entidad = str(entorno.marca_id) if alcance_id == "entidad" else None

    with pytest.raises(AlcanceInvalidoError) as error:
        entorno.enviar(REGLA_CREAR, _crear(lista_id, alcance_tipo=alcance_tipo, alcance_id=entidad))

    assert error.value.codigo == "ALCANCE_INVALIDO"
    entorno.sesion.rollback()
    assert entorno.reglas(lista_id) == []


@pytest.mark.parametrize("alcance", ["PRODUCTO", "MARCA", "CATEGORIA", "PROVEEDOR"])
def test_inv21_la_entidad_del_alcance_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session, alcance: str
) -> None:
    """Escenario "Entidad del alcance de otra organización" (INV-21, INV-02): la clave
    foránea compuesta la rechaza y el repositorio la traduce a 404."""
    lista_id = entorno.crear_lista()
    ajena = Entorno(db_session)
    de_b = {
        "PRODUCTO": ajena.vino_id,
        "MARCA": ajena.marca_id,
        "CATEGORIA": ajena.categoria_id,
        "PROVEEDOR": ajena.proveedor_id,
    }

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.enviar(
            REGLA_CREAR, _crear(lista_id, alcance_tipo=alcance, alcance_id=str(de_b[alcance]))
        )

    assert error.value.status_http == 404
    db_session.rollback()
    assert entorno.reglas(lista_id) == []


def test_una_entidad_inexistente_responde_404(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()

    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(
            REGLA_CREAR, _crear(lista_id, alcance_tipo="CATEGORIA", alcance_id=str(uuid4()))
        )


def test_inv21_la_lista_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    lista_ajena = Entorno(db_session).crear_lista("General")

    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(REGLA_CREAR, _crear(lista_ajena))

    db_session.rollback()
    assert (
        db_session.execute(
            text("SELECT count(*) FROM regla_margen WHERE lista_id = :l"), {"l": lista_ajena}
        ).scalar_one()
        == 0
    )


def test_una_entidad_inactiva_puede_ser_el_alcance(entorno: Entorno) -> None:
    """La entidad del alcance puede estar inactiva (D8)."""
    lista_id = entorno.crear_lista()
    entorno.sesion.execute(
        text("UPDATE categoria SET activo = false WHERE id = :c"), {"c": entorno.categoria_id}
    )

    entorno.crear_regla(lista_id, alcance_tipo="CATEGORIA", alcance_id=entorno.categoria_id)

    assert len(entorno.reglas(lista_id)) == 1


def test_sin_gestionar_listas_se_rechaza_con_403_y_sin_reserva(entorno: Entorno) -> None:
    """Escenario "Sin permiso" (SEG-06): con solo `PUBLICAR_LISTAS` no se crea la regla."""
    lista_id = entorno.crear_lista()
    entorno.actuar_con_permisos(frozenset({"PUBLICAR_LISTAS"}))
    antes = len(entorno.comandos())

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(REGLA_CREAR, _crear(lista_id))

    entorno.sesion.rollback()
    assert entorno.reglas(lista_id) == []
    assert len(entorno.comandos()) == antes


def test_inv06_el_doble_envio_devuelve_el_resultado_original_y_no_duplica(
    entorno: Entorno,
) -> None:
    lista_id = entorno.crear_lista()
    operation_id = uuid4()

    primero = entorno.enviar(REGLA_CREAR, _crear(lista_id), operation_id=operation_id)
    segundo = entorno.enviar(REGLA_CREAR, _crear(lista_id), operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.reglas(lista_id)) == 1
    assert len(entorno.auditorias(REGLA_CREAR)) == 1
    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(REGLA_CREAR, _crear(lista_id, valor="0.5"), operation_id=operation_id)


def test_la_regla_es_solo_online(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()
    item = ItemLote(
        operation_id=uuid4(),
        tipo=REGLA_CREAR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=_crear(lista_id),
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )

    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert entorno.reglas(lista_id) == []


def test_el_contenido_no_acepta_la_organizacion(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(REGLA_CREAR, _crear(lista_id, organizacion_id=str(uuid4())))


# --- una sola regla activa por lista y alcance (D8) -----------------------------------------


def test_una_segunda_regla_activa_para_la_misma_categoria_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Segunda regla para la misma categoría": la existente no cambia."""
    lista_id = entorno.crear_lista()
    entorno.crear_regla(
        lista_id,
        tipo="MARGEN_BRUTO",
        alcance_tipo="CATEGORIA",
        alcance_id=entorno.categoria_id,
    )

    with pytest.raises(ReglaDuplicadaError) as error:
        entorno.enviar(
            REGLA_CREAR,
            _crear(
                lista_id,
                tipo="MARKUP",
                valor="0.400000",
                alcance_tipo="CATEGORIA",
                alcance_id=str(entorno.categoria_id),
            ),
        )

    assert error.value.codigo == "REGLA_DUPLICADA"
    entorno.sesion.rollback()
    (regla,) = entorno.reglas(lista_id)
    assert (regla.tipo, regla.valor) == ("MARGEN_BRUTO", Decimal("0.300000"))


def test_una_segunda_regla_activa_de_alcance_lista_tambien_se_rechaza(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()
    entorno.crear_regla(lista_id)

    with pytest.raises(ReglaDuplicadaError):
        entorno.enviar(REGLA_CREAR, _crear(lista_id, valor="0.5"))


def test_se_acepta_una_regla_nueva_si_la_anterior_esta_inactiva(entorno: Entorno) -> None:
    """Escenario "Reemplazo de una regla desactivada"."""
    lista_id = entorno.crear_lista()
    anterior = entorno.crear_regla(
        lista_id, alcance_tipo="CATEGORIA", alcance_id=entorno.categoria_id
    )
    entorno.enviar(REGLA_MODIFICAR, _modificar(lista_id, anterior, activo=False))

    entorno.crear_regla(
        lista_id, tipo="MARGEN_BRUTO", alcance_tipo="CATEGORIA", alcance_id=entorno.categoria_id
    )

    reglas = entorno.reglas(lista_id)
    assert [regla.activo for regla in reglas] == [False, True]


def test_la_misma_categoria_en_otra_lista_se_acepta(entorno: Entorno) -> None:
    """Escenario "La misma categoría en otra lista": las reglas pertenecen a su lista."""
    general = entorno.crear_lista("General")
    mayorista = entorno.crear_lista("Mayorista")

    entorno.crear_regla(general, alcance_tipo="CATEGORIA", alcance_id=entorno.categoria_id)
    entorno.crear_regla(mayorista, alcance_tipo="CATEGORIA", alcance_id=entorno.categoria_id)

    assert len(entorno.reglas(general)) == 1
    assert len(entorno.reglas(mayorista)) == 1


# --- REGLA_MARGEN_MODIFICAR (PRC-12, PRC-16) --------------------------------------------------


def test_modificar_tipo_valor_y_actividad(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()
    regla_id = entorno.crear_regla(lista_id, tipo="MARKUP", valor="0.300000")

    comando = entorno.enviar(
        REGLA_MODIFICAR, _modificar(lista_id, regla_id, tipo="MARGEN_BRUTO", valor="0.350000")
    )

    assert comando.estado == "ACEPTADO"
    assert comando.resultado == {"regla_id": str(regla_id), "lista_id": str(lista_id)}
    (regla,) = entorno.reglas(lista_id)
    assert (regla.tipo, regla.valor, regla.activo) == ("MARGEN_BRUTO", Decimal("0.350000"), True)
    assert (regla.alcance_tipo, regla.alcance_id) == ("LISTA", None)

    entorno.enviar(REGLA_MODIFICAR, _modificar(lista_id, regla_id, activo=False))
    (desactivada,) = entorno.reglas(lista_id)
    assert desactivada.activo is False  # nunca se borra


def test_el_alcance_y_la_lista_no_cambian(entorno: Entorno) -> None:
    """El esquema del comando no los define: mandarlos se rechaza como contenido inválido."""
    lista_id = entorno.crear_lista()
    regla_id = entorno.crear_regla(lista_id)

    for campo in ("alcance_tipo", "alcance_id"):
        with pytest.raises(ContenidoDeComandoInvalidoError):
            entorno.enviar(REGLA_MODIFICAR, {**_modificar(lista_id, regla_id), campo: str(uuid4())})


@pytest.mark.parametrize(
    ("tipo", "valor"),
    [("MARGEN_BRUTO", "1.2"), ("MARKUP", "-0.1"), ("MARKUP", "0.3000001")],
)
def test_modificar_con_un_valor_invalido_se_rechaza_y_no_cambia_la_regla(
    entorno: Entorno, tipo: str, valor: str
) -> None:
    lista_id = entorno.crear_lista()
    regla_id = entorno.crear_regla(lista_id)

    with pytest.raises(MargenInvalidoError):
        entorno.enviar(REGLA_MODIFICAR, _modificar(lista_id, regla_id, tipo=tipo, valor=valor))

    entorno.sesion.rollback()
    (regla,) = entorno.reglas(lista_id)
    assert (regla.tipo, regla.valor) == ("MARKUP", Decimal("0.300000"))


def test_reactivar_una_regla_con_otra_activa_para_el_mismo_alcance_se_rechaza(
    entorno: Entorno,
) -> None:
    lista_id = entorno.crear_lista()
    vieja = entorno.crear_regla(lista_id, alcance_tipo="MARCA", alcance_id=entorno.marca_id)
    entorno.enviar(REGLA_MODIFICAR, _modificar(lista_id, vieja, activo=False))
    entorno.crear_regla(lista_id, alcance_tipo="MARCA", alcance_id=entorno.marca_id)

    with pytest.raises(ReglaDuplicadaError):
        entorno.enviar(REGLA_MODIFICAR, _modificar(lista_id, vieja, activo=True))


def test_inv21_modificar_la_regla_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Regla de otra organización" (INV-21, SEG-07)."""
    ajena = Entorno(db_session)
    lista_ajena = ajena.crear_lista("General")
    regla_ajena = ajena.crear_regla(lista_ajena)
    lista_propia = entorno.crear_lista()

    for lista in (lista_ajena, lista_propia):
        with pytest.raises(RecursoNoEncontradoError):
            entorno.enviar(REGLA_MODIFICAR, _modificar(lista, regla_ajena, valor="0.9"))
        db_session.rollback()
        db_session.expire_all()

    (de_b,) = db_session.execute(
        text("SELECT valor FROM regla_margen WHERE id = :r"), {"r": regla_ajena}
    ).all()
    assert de_b.valor == Decimal("0.300000")


def test_una_regla_de_otra_lista_de_la_misma_organizacion_responde_404(entorno: Entorno) -> None:
    general = entorno.crear_lista("General")
    mayorista = entorno.crear_lista("Mayorista")
    regla_de_general = entorno.crear_regla(general)

    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(REGLA_MODIFICAR, _modificar(mayorista, regla_de_general))


def test_sin_gestionar_listas_modificar_se_rechaza_con_403(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()
    regla_id = entorno.crear_regla(lista_id)
    entorno.actuar_con_permisos(frozenset({"PUBLICAR_LISTAS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(REGLA_MODIFICAR, _modificar(lista_id, regla_id, valor="0.9"))

    entorno.sesion.rollback()
    (regla,) = entorno.reglas(lista_id)
    assert regla.valor == Decimal("0.300000")


def test_inv06_modificar_dos_veces_con_el_mismo_operation_id_aplica_una_vez(
    entorno: Entorno,
) -> None:
    lista_id = entorno.crear_lista()
    regla_id = entorno.crear_regla(lista_id)
    operation_id = uuid4()
    contenido = _modificar(lista_id, regla_id, valor="0.350000")

    primero = entorno.enviar(REGLA_MODIFICAR, contenido, operation_id=operation_id)
    segundo = entorno.enviar(REGLA_MODIFICAR, contenido, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.auditorias(REGLA_MODIFICAR)) == 1


def test_inv11_modificar_una_regla_no_toca_los_precios_de_una_version_publicada(
    entorno: Entorno,
) -> None:
    """Escenario "Subir el margen no cambia lo publicado" (PRC-04, PRC-16): el precio sigue
    con tipo `MARGEN_BRUTO` y valor `0.300000` guardados, y final `8600.00`."""
    lista_id = entorno.crear_lista()
    regla_id = entorno.crear_regla(lista_id, tipo="MARGEN_BRUTO")
    version_id, costo_id = uuid4(), _costo_informado(entorno)
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
            "unidades_referencia, costo_informado_id, costo_referencia, regla_margen_id, "
            "tipo_margen, valor_margen, precio_calculado, precio_final, manual) VALUES "
            "(:id, :org, :v, :p, 6, :c, 6000.000000, :r, 'MARGEN_BRUTO', 0.300000, "
            "8571.428571, 8600.00, false)"
        ),
        {
            "id": uuid4(),
            "org": entorno.org,
            "v": version_id,
            "p": entorno.vino_id,
            "c": costo_id,
            "r": regla_id,
        },
    )
    consulta = text(
        "SELECT tipo_margen, valor_margen, precio_calculado, precio_final, regla_margen_id "
        "FROM precio_item WHERE version_id = :v"
    )
    antes = entorno.sesion.execute(consulta, {"v": version_id}).all()

    entorno.enviar(
        REGLA_MODIFICAR, _modificar(lista_id, regla_id, tipo="MARGEN_BRUTO", valor="0.35")
    )
    entorno.enviar(
        REGLA_MODIFICAR,
        _modificar(lista_id, regla_id, tipo="MARGEN_BRUTO", valor="0.35", activo=False),
    )

    despues = entorno.sesion.execute(consulta, {"v": version_id}).all()
    assert despues == antes
    assert despues[0].valor_margen == Decimal("0.300000")
    assert despues[0].precio_final == Decimal("8600.00")


def _costo_informado(entorno: Entorno) -> UUID:
    presentacion_id = entorno.sesion.execute(
        text("SELECT id FROM presentacion WHERE producto_id = :p"), {"p": entorno.vino_id}
    ).scalar_one()
    costo_id = uuid4()
    entorno.sesion.execute(
        text(
            "INSERT INTO costo_informado (id, organizacion_id, proveedor_id, producto_id, "
            "presentacion_id, valor, incluye_iva, computa_credito_fiscal, bonificacion, "
            "alicuota_aplicada, costo_base, vigencia_desde, operation_id, usuario_id, "
            "creado_en) VALUES (:id, :org, :prov, :prod, :pres, 6000, false, true, 0, 0.21, "
            "1000, :vig, :op, :usr, :m)"
        ),
        {
            "id": costo_id,
            "org": entorno.org,
            "prov": entorno.proveedor_id,
            "prod": entorno.vino_id,
            "pres": presentacion_id,
            "vig": MOMENTO.date(),
            "op": uuid4(),
            "usr": entorno.usuario_id,
            "m": MOMENTO,
        },
    )
    return costo_id
