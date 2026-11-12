"""Change 13, tareas 7.1 y 7.2: `LISTA_GENERAR_BORRADOR` v1 por el bus, contra PostgreSQL real
(spec `precios/borrador-de-lista`, requisitos "El borrador de una lista se genera por comando",
"Un producto que no puede calcularse queda sin precio y se informa" y "Una lista tiene como
máximo un borrador, que se regenera").

Reglas citadas: PRC-01, PRC-02, PRC-10, PRC-11, PRC-12, PRC-13, PRC-14, PRC-15, PRC-16, PRC-17,
CST-03, CAT-05, INV-01, INV-02, INV-06, INV-11, INV-21, SYN-02, SEG-06, SEG-07, `design.md`
D4, D5 y D14.

Los precios esperados salen de `01` §7.2: costo base `1000.000000` x 6 = costo de referencia
`6000.000000`; margen bruto 30% = `8571.428571`; redondeo a `100.00` hacia arriba = `8600.00`.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from precios_utiles import (
    GENERAR_BORRADOR,
    MOMENTO,
    REGLA_MODIFICAR,
    RELOJ,
    Entorno,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands.errores import ContenidoDeComandoInvalidoError
from app.core.errors import PermisoRequeridoError
from app.modules.precios import repository as precios_repository
from app.modules.precios.domain.errores import (
    ListaInactivaError,
    ModoImpositivoNoSoportadoError,
    RecursoNoEncontradoError,
)
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _lista_general(entorno: Entorno, *, tipo: str = "MARGEN_BRUTO") -> UUID:
    """`General`: margen de la lista 30%, redondeo a 100 hacia arriba; Vino A con costo base
    1000 por unidad."""
    lista_id = entorno.crear_lista("General", "100.00", "ARRIBA")
    entorno.crear_regla(lista_id, tipo=tipo, valor="0.300000")
    entorno.informar_costo(entorno.vino_id, "1000")
    return lista_id


def _cerveza_b(entorno: Entorno) -> UUID:
    """Cerveza B, referencia `Caja x12`, costo base 1815 por unidad (21780 la caja)."""
    cerveza_id = entorno.crear_producto("Cerveza B", unidades_base=12)
    entorno.informar_costo(cerveza_id, "1815")
    return cerveza_id


def _generar(entorno: Entorno, lista_id: UUID, **argumentos: object):  # type: ignore[no-untyped-def]
    comando = entorno.generar_borrador(lista_id, **argumentos)  # type: ignore[arg-type]
    assert comando.resultado is not None
    return comando


# --- primer borrador ----------------------------------------------------------------------


def test_primer_borrador_de_una_lista(entorno: Entorno) -> None:
    """Escenario "Primer borrador de una lista": versión n.º 1 en `BORRADOR`, sin vigencia ni
    versión base, con Vino A a `8600.00` y todo lo que PRC-16 pide guardar."""
    lista_id = _lista_general(entorno)
    regla_id = entorno.reglas(lista_id)[0].id
    costo_id = entorno.sesion.execute(
        text("SELECT id FROM costo_informado WHERE producto_id = :p"), {"p": entorno.vino_id}
    ).scalar_one()
    operation_id = uuid4()

    comando = entorno.generar_borrador(lista_id, operation_id=operation_id)

    assert comando.estado == "ACEPTADO"
    (version,) = entorno.versiones(lista_id)
    assert (version.numero, version.estado) == (1, "BORRADOR")
    assert version.vigencia_desde is None
    assert version.vigencia_hasta is None
    assert version.version_base_id is None
    assert version.publicado_en is None
    assert version.generado_en == MOMENTO
    assert version.creado_por_id == entorno.usuario_id
    assert version.operation_id == operation_id
    (precio,) = entorno.precios(version.id).values()
    assert precio.producto_id == entorno.vino_id
    assert precio.precio_final == Decimal("8600.00")
    assert precio.manual is False
    assert precio.unidades_referencia == 6
    assert precio.costo_informado_id == costo_id
    assert precio.costo_referencia == Decimal("6000.000000")
    assert precio.regla_margen_id == regla_id
    assert (precio.tipo_margen, precio.valor_margen) == ("MARGEN_BRUTO", Decimal("0.300000"))
    assert precio.precio_calculado == Decimal("8571.428571")


def test_el_resultado_informa_cuantos_precios_tiene_y_los_productos_sin_precio(
    entorno: Entorno,
) -> None:
    lista_id = _lista_general(entorno)
    gaseosa_id = entorno.crear_producto("Gaseosa C")

    comando = _generar(entorno, lista_id)

    (version,) = entorno.versiones(lista_id)
    assert comando.resultado == {
        "version_id": str(version.id),
        "numero": 1,
        "regenerado": False,
        "cantidad_precios": 1,
        "productos_sin_precio": [{"producto_id": str(gaseosa_id), "causa": "SIN_COSTO"}],
        "precios_con_otra_regla_iva": 0,
        "precios_con_costos_distintos": 0,
    }


def test_generar_escribe_una_sola_fila_de_auditoria_con_el_operation_id(
    entorno: Entorno,
) -> None:
    lista_id = _lista_general(entorno)
    operation_id = uuid4()

    entorno.generar_borrador(lista_id, operation_id=operation_id)

    (auditoria,) = entorno.auditorias(GENERAR_BORRADOR)
    assert auditoria.operation_id == operation_id


# --- el borrador sale de los costos, las reglas y el redondeo ---------------------------------


def test_un_costo_nuevo_cambia_el_precio_en_el_borrador_y_la_vigente_queda_intacta(
    entorno: Entorno,
) -> None:
    """Escenario "Un costo nuevo cambia el precio en el borrador": `9500.00` con costo de
    referencia `6600.000000`; la versión vigente sigue con `8600.00`."""
    lista_id = _lista_general(entorno)
    entorno.generar_borrador(lista_id)
    primera = entorno.versiones(lista_id)[0]
    entorno.publicar_por_sql(primera.id)
    entorno.informar_costo(entorno.vino_id, "1100", creado_en=MOMENTO + timedelta(minutes=1))

    _generar(entorno, lista_id)

    vigente, borrador = entorno.versiones(lista_id)
    assert (borrador.numero, borrador.estado) == (2, "BORRADOR")
    assert borrador.version_base_id == vigente.id
    (nuevo,) = entorno.precios(borrador.id).values()
    assert nuevo.precio_final == Decimal("9500.00")
    assert nuevo.costo_referencia == Decimal("6600.000000")
    (anterior,) = entorno.precios(vigente.id).values()
    assert anterior.precio_final == Decimal("8600.00")
    assert anterior.costo_referencia == Decimal("6000.000000")


def test_un_producto_sin_cambios_queda_igual_a_la_version_base(entorno: Entorno) -> None:
    """Escenario "Un producto sin cambios queda igual": Cerveza B a `31200.00` (costo de
    referencia `21780.000000`, margen bruto 30%) tanto en la base como en el borrador."""
    lista_id = _lista_general(entorno)
    cerveza_id = _cerveza_b(entorno)
    entorno.generar_borrador(lista_id)
    base = entorno.versiones(lista_id)[0]
    entorno.publicar_por_sql(base.id)
    entorno.informar_costo(entorno.vino_id, "1100", creado_en=MOMENTO + timedelta(minutes=1))

    _generar(entorno, lista_id)

    borrador = entorno.versiones(lista_id)[1]
    precios_base = entorno.precios(base.id)
    precios_borrador = entorno.precios(borrador.id)
    assert precios_base[cerveza_id].precio_final == Decimal("31200.00")
    assert precios_borrador[cerveza_id].precio_final == Decimal("31200.00")
    assert precios_borrador[cerveza_id].costo_referencia == Decimal("21780.000000")
    assert precios_borrador[entorno.vino_id].precio_final == Decimal("9500.00")


def test_un_cambio_de_regla_tambien_llega_al_borrador(entorno: Entorno) -> None:
    """Escenario "Un cambio de regla también llega al borrador": margen bruto `0.350000` →
    Cerveza B a `33600.00`, aunque su costo no cambió (D4: se recalculan todos)."""
    lista_id = _lista_general(entorno)
    cerveza_id = _cerveza_b(entorno)
    entorno.generar_borrador(lista_id)
    base = entorno.versiones(lista_id)[0]
    entorno.publicar_por_sql(base.id)
    regla_id = entorno.reglas(lista_id)[0].id
    entorno.enviar(
        REGLA_MODIFICAR,
        {
            "lista_id": str(lista_id),
            "regla_id": str(regla_id),
            "tipo": "MARGEN_BRUTO",
            "valor": "0.350000",
            "activo": True,
        },
    )

    _generar(entorno, lista_id)

    borrador = entorno.versiones(lista_id)[1]
    assert entorno.precios(base.id)[cerveza_id].precio_final == Decimal("31200.00")
    assert entorno.precios(borrador.id)[cerveza_id].precio_final == Decimal("33600.00")
    assert entorno.precios(borrador.id)[cerveza_id].valor_margen == Decimal("0.350000")


def test_la_version_base_es_la_publicada_de_mayor_vigencia_aunque_sea_programada(
    entorno: Entorno,
) -> None:
    """D4: la base es la `PUBLICADA` no anulada de mayor vigencia desde (vigente o
    programada); una anulada no cuenta."""
    lista_id = _lista_general(entorno)
    entorno.generar_borrador(lista_id)
    primera = entorno.versiones(lista_id)[0]
    entorno.publicar_por_sql(primera.id, desde=MOMENTO - timedelta(days=30))
    entorno.generar_borrador(lista_id)
    segunda = entorno.versiones(lista_id)[1]
    entorno.publicar_por_sql(segunda.id, desde=MOMENTO + timedelta(days=5))
    entorno.generar_borrador(lista_id)
    tercera = entorno.versiones(lista_id)[2]
    entorno.publicar_por_sql(tercera.id, desde=MOMENTO + timedelta(days=10))
    entorno.sesion.execute(
        text(
            "UPDATE lista_version SET estado = 'ANULADA', anulado_en = :m, anulado_por_id = :u "
            "WHERE id = :v"
        ),
        {"m": MOMENTO, "u": entorno.usuario_id, "v": tercera.id},
    )

    _generar(entorno, lista_id)

    borrador = entorno.versiones(lista_id)[3]
    assert borrador.numero == 4
    assert borrador.version_base_id == segunda.id


def test_informar_un_costo_no_genera_un_borrador(entorno: Entorno) -> None:
    """Escenario "Informar un costo no genera un borrador" (`02` §6.5, D4)."""
    lista_id = _lista_general(entorno)

    entorno.informar_costo_por_comando(entorno.vino_id, "6600.00")

    assert entorno.versiones(lista_id) == []
    assert entorno.cantidad("precio_item") == 0


def test_el_redondeo_de_la_categoria_pisa_el_de_la_lista(entorno: Entorno) -> None:
    from precios_utiles import REDONDEO_DEFINIR

    lista_id = _lista_general(entorno)
    entorno.enviar(
        REDONDEO_DEFINIR,
        {
            "lista_id": str(lista_id),
            "categoria_id": str(entorno.categoria_id),
            "multiplo": "500.00",
            "direccion": "ARRIBA",
            "activo": True,
        },
    )

    _generar(entorno, lista_id)

    (version,) = entorno.versiones(lista_id)
    (precio,) = entorno.precios(version.id).values()
    assert precio.precio_final == Decimal("9000.00"), "8571.428571 a múltiplos de 500 hacia arriba"


def test_la_regla_mas_especifica_gana_producto_sobre_categoria_y_lista(
    entorno: Entorno,
) -> None:
    lista_id = _lista_general(entorno)
    entorno.crear_regla(
        lista_id,
        tipo="MARKUP",
        valor="0.500000",
        alcance_tipo="PRODUCTO",
        alcance_id=entorno.vino_id,
    )
    entorno.crear_regla(
        lista_id,
        tipo="MARKUP",
        valor="0.100000",
        alcance_tipo="CATEGORIA",
        alcance_id=entorno.categoria_id,
    )

    _generar(entorno, lista_id)

    (version,) = entorno.versiones(lista_id)
    (precio,) = entorno.precios(version.id).values()
    assert precio.precio_final == Decimal("9000.00"), "6000 x 1,5 = 9000"
    assert (precio.tipo_margen, precio.valor_margen) == ("MARKUP", Decimal("0.500000"))


# --- productos sin precio ----------------------------------------------------------------


def test_producto_sin_costo_queda_sin_precio_con_su_causa(entorno: Entorno) -> None:
    """Escenario "Producto sin costo"."""
    lista_id = _lista_general(entorno)
    gaseosa_id = entorno.crear_producto("Gaseosa C")

    comando = _generar(entorno, lista_id)

    (version,) = entorno.versiones(lista_id)
    assert gaseosa_id not in entorno.precios(version.id)
    assert comando.resultado is not None
    assert comando.resultado["productos_sin_precio"] == [
        {"producto_id": str(gaseosa_id), "causa": "SIN_COSTO"}
    ]


def test_producto_sin_presentacion_de_referencia_queda_sin_precio_con_su_causa(
    entorno: Entorno,
) -> None:
    """Escenario "Producto sin presentación de referencia" (decisión del 2026-10-06, D4): aunque
    tenga costo y regla aplicable, no recibe precio y se informa con su causa."""
    lista_id = _lista_general(entorno)
    sin_referencia_id = entorno.crear_producto_sin_referencia("Gaseosa sin referencia")
    entorno.informar_costo(sin_referencia_id, "500")

    comando = _generar(entorno, lista_id)

    (version,) = entorno.versiones(lista_id)
    assert sin_referencia_id not in entorno.precios(version.id)
    assert comando.resultado is not None
    assert comando.resultado["productos_sin_precio"] == [
        {"producto_id": str(sin_referencia_id), "causa": "SIN_PRESENTACION_DE_REFERENCIA"}
    ]
    assert comando.resultado["cantidad_precios"] == 1, "solo Vino A"


def test_un_producto_sin_referencia_y_otro_sin_costo_conviven_con_sus_causas(
    entorno: Entorno,
) -> None:
    lista_id = _lista_general(entorno)
    sin_referencia_id = entorno.crear_producto_sin_referencia("Gaseosa sin referencia")
    sin_costo_id = entorno.crear_producto("Gaseosa C")

    comando = _generar(entorno, lista_id)

    assert comando.resultado is not None
    causas = {
        fila["producto_id"]: fila["causa"] for fila in comando.resultado["productos_sin_precio"]
    }
    assert causas == {
        str(sin_referencia_id): "SIN_PRESENTACION_DE_REFERENCIA",
        str(sin_costo_id): "SIN_COSTO",
    }


def test_producto_sin_regla_aplicable_queda_sin_precio(entorno: Entorno) -> None:
    """Escenario "Producto sin regla aplicable": la única regla es de la categoría `Vinos`
    y Cerveza B es de otra categoría."""
    lista_id = entorno.crear_lista("Solo vinos")
    entorno.crear_regla(
        lista_id,
        tipo="MARGEN_BRUTO",
        valor="0.300000",
        alcance_tipo="CATEGORIA",
        alcance_id=entorno.categoria_id,
    )
    entorno.informar_costo(entorno.vino_id, "1000")
    cerveza_id = _cerveza_b(entorno)

    comando = _generar(entorno, lista_id)

    (version,) = entorno.versiones(lista_id)
    precios = entorno.precios(version.id)
    assert set(precios) == {entorno.vino_id}
    assert comando.resultado is not None
    assert comando.resultado["productos_sin_precio"] == [
        {"producto_id": str(cerveza_id), "causa": "SIN_REGLA"}
    ]


def test_un_redondeo_que_da_cero_deja_al_producto_sin_precio(entorno: Entorno) -> None:
    """`PRECIO_NO_POSITIVO` (D9): redondear hacia abajo a múltiplos mayores que el precio."""
    lista_id = entorno.crear_lista("Hacia abajo", "100000.00", "ABAJO")
    entorno.crear_regla(lista_id, tipo="MARGEN_BRUTO", valor="0.300000")
    entorno.informar_costo(entorno.vino_id, "1000")

    comando = _generar(entorno, lista_id)

    (version,) = entorno.versiones(lista_id)
    assert entorno.precios(version.id) == {}
    assert comando.resultado is not None
    assert comando.resultado["cantidad_precios"] == 0
    assert comando.resultado["productos_sin_precio"] == [
        {"producto_id": str(entorno.vino_id), "causa": "PRECIO_NO_POSITIVO"}
    ]


def test_un_producto_inactivo_no_entra_en_el_borrador(entorno: Entorno) -> None:
    """Escenario "Producto inactivo" (CAT-05): con costo vigente y precio en la base, el
    borrador no lo incluye y tampoco lo lista como sin precio."""
    lista_id = _lista_general(entorno)
    cerveza_id = _cerveza_b(entorno)
    entorno.generar_borrador(lista_id)
    base = entorno.versiones(lista_id)[0]
    entorno.publicar_por_sql(base.id)
    entorno.sesion.execute(
        text("UPDATE producto SET activo = false WHERE id = :p"), {"p": cerveza_id}
    )

    comando = _generar(entorno, lista_id)

    borrador = entorno.versiones(lista_id)[1]
    assert set(entorno.precios(borrador.id)) == {entorno.vino_id}
    assert comando.resultado is not None
    assert comando.resultado["productos_sin_precio"] == []


def test_un_borrador_sin_ningun_precio_calculable_se_genera_igual(entorno: Entorno) -> None:
    """Generar no exige precios: es publicar (`VERSION_SIN_PRECIOS`, grupo 8) lo que los
    exige."""
    lista_id = entorno.crear_lista()

    comando = _generar(entorno, lista_id)

    (version,) = entorno.versiones(lista_id)
    assert comando.resultado is not None
    assert comando.resultado["cantidad_precios"] == 0
    assert entorno.precios(version.id) == {}


# --- rechazos --------------------------------------------------------------------------------


def test_una_lista_inactiva_se_rechaza_con_lista_inactiva(entorno: Entorno) -> None:
    """Escenario "Lista inactiva"."""
    lista_id = _lista_general(entorno)
    entorno.enviar(
        "LISTA_PRECIO_MODIFICAR",
        {
            "lista_id": str(lista_id),
            "nombre": "General",
            "redondeo_multiplo": "100.00",
            "redondeo_direccion": "ARRIBA",
            "activo": False,
        },
    )

    with pytest.raises(ListaInactivaError) as error:
        entorno.generar_borrador(lista_id)

    assert error.value.codigo == "LISTA_INACTIVA"
    entorno.sesion.rollback()
    assert entorno.versiones(lista_id) == []


def test_inv21_una_lista_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Lista de otra organización" (INV-21, SEG-07)."""
    ajena = Entorno(db_session).crear_lista("General")

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.generar_borrador(ajena)

    assert error.value.status_http == 404
    db_session.rollback()
    assert (
        db_session.execute(
            text("SELECT count(*) FROM lista_version WHERE lista_id = :l"), {"l": ajena}
        ).scalar_one()
        == 0
    )


def test_una_lista_inexistente_responde_404(entorno: Entorno) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        entorno.generar_borrador(uuid4())


def test_sin_gestionar_listas_se_rechaza_con_403_y_no_se_crea_ningun_borrador(
    entorno: Entorno,
) -> None:
    """Escenario "Sin permiso" (SEG-06): `PUBLICAR_LISTAS` solo no alcanza."""
    lista_id = _lista_general(entorno)
    entorno.actuar_con_permisos(frozenset({"PUBLICAR_LISTAS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.generar_borrador(lista_id)

    entorno.sesion.rollback()
    assert entorno.versiones(lista_id) == []


def test_generar_es_solo_online(entorno: Entorno) -> None:
    """Escenario "Solo con conexión" (`02` §6.5)."""
    lista_id = _lista_general(entorno)
    item = ItemLote(
        operation_id=uuid4(),
        tipo=GENERAR_BORRADOR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={"lista_id": str(lista_id)},
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
    assert entorno.versiones(lista_id) == []


def test_el_contenido_no_acepta_un_organizacion_id(entorno: Entorno) -> None:
    lista_id = _lista_general(entorno)

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(
            GENERAR_BORRADOR, {"lista_id": str(lista_id), "organizacion_id": str(uuid4())}
        )


def test_prc15_un_modo_impositivo_c_se_rechaza_sin_generar_nada(entorno: Entorno) -> None:
    """Escenario "modo C rechazado" (PRC-15): el redondeo sobre el precio con IVA incluido es
    de la etapa 4."""
    lista_id = _lista_general(entorno)
    entorno.cambiar_modo_impositivo("C")

    with pytest.raises(ModoImpositivoNoSoportadoError) as error:
        entorno.generar_borrador(lista_id)

    assert error.value.codigo == "MODO_IMPOSITIVO_NO_SOPORTADO"
    entorno.sesion.rollback()
    assert entorno.versiones(lista_id) == []


# --- idempotencia ----------------------------------------------------------------------------


def test_inv06_el_doble_envio_devuelve_el_resultado_original_y_la_lista_sigue_con_un_borrador(
    entorno: Entorno,
) -> None:
    """Escenario "Doble envío" (INV-06, SYN-02)."""
    lista_id = _lista_general(entorno)
    operation_id = uuid4()

    primero = entorno.generar_borrador(lista_id, operation_id=operation_id)
    segundo = entorno.generar_borrador(lista_id, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.versiones(lista_id)) == 1
    assert len(entorno.auditorias(GENERAR_BORRADOR)) == 1


# --- regenerar el borrador (tarea 7.2) ---------------------------------------------------------


def test_regenerar_conserva_el_numero_del_borrador_y_un_solo_precio_por_producto(
    entorno: Entorno,
) -> None:
    """Escenario "Regenerar el borrador" (D5, PRC-10): sigue el mismo borrador, con Vino A a
    `9500.00` tras un costo nuevo y sin filas de más."""
    lista_id = _lista_general(entorno)
    for dias_atras in (3, 2, 1):  # tres versiones publicadas: el borrador siguiente es el n.º 4
        entorno.generar_borrador(lista_id)
        entorno.publicar_por_sql(
            entorno.versiones(lista_id)[-1].id, desde=MOMENTO - timedelta(days=dias_atras)
        )
    primer = _generar(entorno, lista_id)
    borrador = entorno.versiones(lista_id)[-1]
    assert borrador.numero == 4
    assert entorno.precios(borrador.id)[entorno.vino_id].precio_final == Decimal("8600.00")
    entorno.informar_costo(entorno.vino_id, "1100", creado_en=MOMENTO + timedelta(minutes=1))

    segundo = _generar(entorno, lista_id)

    versiones = entorno.versiones(lista_id)
    assert [v.estado for v in versiones].count("BORRADOR") == 1
    assert versiones[-1].id == borrador.id and versiones[-1].numero == 4
    assert entorno.cantidad("precio_item") == 3 + 1, "un precio por producto en cada versión"
    assert entorno.precios(borrador.id)[entorno.vino_id].precio_final == Decimal("9500.00")
    assert primer.resultado is not None and segundo.resultado is not None
    assert primer.resultado["regenerado"] is False
    assert segundo.resultado["regenerado"] is True
    assert segundo.resultado["version_id"] == primer.resultado["version_id"]


def test_regenerar_con_los_mismos_datos_deja_exactamente_lo_mismo(entorno: Entorno) -> None:
    lista_id = _lista_general(entorno)
    _cerveza_b(entorno)
    _generar(entorno, lista_id)
    borrador = entorno.versiones(lista_id)[0]
    antes = {
        producto: (p.precio_final, p.costo_referencia, p.precio_calculado)
        for producto, p in entorno.precios(borrador.id).items()
    }

    _generar(entorno, lista_id)

    despues = {
        producto: (p.precio_final, p.costo_referencia, p.precio_calculado)
        for producto, p in entorno.precios(borrador.id).items()
    }
    assert despues == antes


def test_regenerar_saca_del_borrador_al_producto_que_dejo_de_poder_calcularse(
    entorno: Entorno,
) -> None:
    lista_id = _lista_general(entorno)
    _generar(entorno, lista_id)
    borrador = entorno.versiones(lista_id)[0]
    regla = entorno.reglas(lista_id)[0]
    entorno.enviar(
        REGLA_MODIFICAR,
        {
            "lista_id": str(lista_id),
            "regla_id": str(regla.id),
            "tipo": "MARGEN_BRUTO",
            "valor": "0.300000",
            "activo": False,
        },
    )

    comando = _generar(entorno, lista_id)

    assert entorno.precios(borrador.id) == {}
    assert comando.resultado is not None
    assert comando.resultado["productos_sin_precio"] == [
        {"producto_id": str(entorno.vino_id), "causa": "SIN_REGLA"}
    ]


def test_inv01_una_falla_a_mitad_de_la_escritura_de_precios_no_deja_borrador_ni_precios(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "La generación es atómica" (INV-01)."""
    lista_id = _lista_general(entorno)
    _cerveza_b(entorno)
    original = precios_repository.insertar_precios

    def _falla_a_mitad(organizacion_id: UUID, sesion: Session, filas: list[object]) -> None:
        original(organizacion_id, sesion, filas[:1])  # type: ignore[arg-type]
        raise RuntimeError("falla inyectada a mitad de la escritura de precios")

    monkeypatch.setattr(precios_repository, "insertar_precios", _falla_a_mitad)

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.generar_borrador(lista_id)

    entorno.sesion.rollback()
    assert entorno.versiones(lista_id) == []
    assert entorno.cantidad("precio_item") == 0
    assert entorno.auditorias(GENERAR_BORRADOR) == []


def test_inv01_una_falla_al_regenerar_deja_el_borrador_como_estaba(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    lista_id = _lista_general(entorno)
    _generar(entorno, lista_id)
    borrador = entorno.versiones(lista_id)[0]
    entorno.informar_costo(entorno.vino_id, "1100", creado_en=MOMENTO + timedelta(minutes=1))
    entorno.sesion.commit()
    original = precios_repository.insertar_precios

    def _falla(organizacion_id: UUID, sesion: Session, filas: list[object]) -> None:
        original(organizacion_id, sesion, filas)  # type: ignore[arg-type]
        raise RuntimeError("falla inyectada después de escribir")

    monkeypatch.setattr(precios_repository, "insertar_precios", _falla)

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.generar_borrador(lista_id)

    entorno.sesion.rollback()
    assert entorno.precios(borrador.id)[entorno.vino_id].precio_final == Decimal("8600.00")
