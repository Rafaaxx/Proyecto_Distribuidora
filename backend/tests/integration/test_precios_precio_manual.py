"""Change 13, tareas 7.3 y 7.4: `LISTA_BORRADOR_PRECIO_FIJAR` v1 por el bus y la conservación de
los precios manuales al generar y regenerar (spec `precios/borrador-de-lista`, requisitos "El
precio de un producto puede fijarse a mano en el borrador" y "Los precios manuales se conservan
y se señalan si su margen es menor que el de la regla").

Reglas citadas: PRC-04, PRC-10, PRC-11, PRC-16, PRC-17, TR-01, INV-01, INV-03, INV-06, INV-11,
INV-21, SYN-02, SEG-06, SEG-07, CAT-05, `design.md` D5, D7 y D13.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from precios_utiles import MOMENTO, PRECIO_FIJAR, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.commands.huella import ContenidoNoSerializableError
from app.core.errors import PermisoRequeridoError
from app.modules.precios import service as precios_service
from app.modules.precios.domain.errores import (
    ImporteInvalidoError,
    ProductoInactivoError,
    RecursoNoEncontradoError,
    VersionNoEsBorradorError,
)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _borrador_de_general(entorno: Entorno) -> tuple[UUID, UUID]:
    """`General` (margen bruto 30%, redondeo 100 hacia arriba) con su borrador generado:
    Vino A a `8600.00`, costo de referencia `6000.000000`, calculado `8571.428571`."""
    lista_id = entorno.crear_lista("General", "100.00", "ARRIBA")
    entorno.crear_regla(lista_id, tipo="MARGEN_BRUTO", valor="0.300000")
    entorno.informar_costo(entorno.vino_id, "1000")
    entorno.generar_borrador(lista_id)
    return lista_id, entorno.versiones(lista_id)[-1].id


# --- fijar un precio manual (D7) --------------------------------------------------------------


def test_fijar_un_precio_manual_guarda_el_calculo_de_ese_momento(entorno: Entorno) -> None:
    """Escenario "Fijar un precio manual": `9000.00`, `manual = true`, costo de referencia
    `6000.000000` y precio calculado `8571.428571`."""
    lista_id, version_id = _borrador_de_general(entorno)
    regla_id = entorno.reglas(lista_id)[0].id
    operation_id = uuid4()

    comando = entorno.fijar_precio(
        lista_id, version_id, entorno.vino_id, "9000.00", operation_id=operation_id
    )

    assert comando.estado == "ACEPTADO"
    assert comando.resultado == {
        "version_id": str(version_id),
        "producto_id": str(entorno.vino_id),
        "precio_final": "9000.00",
        "manual": True,
    }
    (precio,) = entorno.precios(version_id).values()
    assert (precio.precio_final, precio.manual) == (Decimal("9000.00"), True)
    assert precio.costo_referencia == Decimal("6000.000000")
    assert precio.precio_calculado == Decimal("8571.428571")
    assert precio.regla_margen_id == regla_id
    assert (precio.tipo_margen, precio.valor_margen) == ("MARGEN_BRUTO", Decimal("0.300000"))
    assert precio.unidades_referencia == 6
    (auditoria,) = entorno.auditorias(PRECIO_FIJAR)
    assert auditoria.operation_id == operation_id


def test_el_precio_manual_no_se_redondea_con_el_de_la_lista(entorno: Entorno) -> None:
    """Escenario "El precio manual no se redondea": `8990.00` en una lista que redondea a
    `100.00` hacia arriba (con C quedaría en `9000.00`)."""
    lista_id, version_id = _borrador_de_general(entorno)

    entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "8990.00")

    (precio,) = entorno.precios(version_id).values()
    assert precio.precio_final == Decimal("8990.00")


def test_fijar_dos_veces_deja_un_solo_precio_por_producto_prc_10(entorno: Entorno) -> None:
    lista_id, version_id = _borrador_de_general(entorno)

    entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")
    entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9100.00")

    precios = entorno.precios(version_id)
    assert entorno.cantidad("precio_item") == 1
    assert precios[entorno.vino_id].precio_final == Decimal("9100.00")


def test_precio_manual_de_un_producto_sin_costo(entorno: Entorno) -> None:
    """Escenario "Precio manual de un producto sin costo": `12000.00` con costo de
    referencia, regla y precio calculado en nulo y las unidades de su referencia guardadas."""
    lista_id, version_id = _borrador_de_general(entorno)
    gaseosa_id = entorno.crear_producto("Gaseosa C", unidades_base=12)

    entorno.fijar_precio(lista_id, version_id, gaseosa_id, "12000.00")

    precio = entorno.precios(version_id)[gaseosa_id]
    assert (precio.precio_final, precio.manual) == (Decimal("12000.00"), True)
    assert precio.unidades_referencia == 12
    assert precio.costo_informado_id is None
    assert precio.costo_referencia is None
    assert precio.regla_margen_id is None
    assert precio.tipo_margen is None
    assert precio.valor_margen is None
    assert precio.precio_calculado is None


def test_precio_manual_con_costo_y_sin_regla_guarda_solo_el_costo(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista("Sin reglas")
    entorno.informar_costo(entorno.vino_id, "1000")
    entorno.generar_borrador(lista_id)
    version_id = entorno.versiones(lista_id)[0].id

    entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")

    precio = entorno.precios(version_id)[entorno.vino_id]
    assert precio.costo_referencia == Decimal("6000.000000")
    assert precio.costo_informado_id is not None
    assert precio.regla_margen_id is None
    assert precio.precio_calculado is None


@pytest.mark.parametrize("importe", ["0.00", "-10.00", "8600.005", "abc", "0"])
def test_un_importe_invalido_se_rechaza_y_el_precio_no_cambia(
    entorno: Entorno, importe: str
) -> None:
    """Escenario "Importe inválido" (TR-01, INV-03)."""
    lista_id, version_id = _borrador_de_general(entorno)

    with pytest.raises(ImporteInvalidoError) as error:
        entorno.fijar_precio(lista_id, version_id, entorno.vino_id, importe)

    assert error.value.codigo == "IMPORTE_INVALIDO"
    entorno.sesion.rollback()
    precio = entorno.precios(version_id)[entorno.vino_id]
    assert (precio.precio_final, precio.manual) == (Decimal("8600.00"), False)


def test_el_importe_como_numero_json_se_rechaza_inv_03(entorno: Entorno) -> None:
    """Un `9000.5` JSON ni siquiera tiene huella canónica: los importes viajan como string."""
    lista_id, version_id = _borrador_de_general(entorno)

    with pytest.raises(ContenidoNoSerializableError):
        entorno.enviar(
            PRECIO_FIJAR,
            {
                "lista_id": str(lista_id),
                "version_id": str(version_id),
                "producto_id": str(entorno.vino_id),
                "precio_final": 9000.5,
            },
        )


def test_el_importe_es_obligatorio_aunque_pueda_ser_nulo(entorno: Entorno) -> None:
    """Omitirlo no quita la marca manual en silencio: quitarla es mandar `null`."""
    lista_id, version_id = _borrador_de_general(entorno)

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(
            PRECIO_FIJAR,
            {
                "lista_id": str(lista_id),
                "version_id": str(version_id),
                "producto_id": str(entorno.vino_id),
            },
        )


# --- quitar la marca manual -------------------------------------------------------------------


def test_quitar_la_marca_manual_vuelve_a_calcular_el_precio(entorno: Entorno) -> None:
    """Escenario "Quitar la marca manual": `9000.00` manual → `8600.00`, `manual = false`."""
    lista_id, version_id = _borrador_de_general(entorno)
    entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")

    comando = entorno.fijar_precio(lista_id, version_id, entorno.vino_id, None)

    assert comando.resultado == {
        "version_id": str(version_id),
        "producto_id": str(entorno.vino_id),
        "precio_final": "8600.00",
        "manual": False,
    }
    precio = entorno.precios(version_id)[entorno.vino_id]
    assert (precio.precio_final, precio.manual) == (Decimal("8600.00"), False)
    assert precio.precio_calculado == Decimal("8571.428571")
    assert entorno.cantidad("precio_item") == 1


def test_quitar_la_marca_de_un_producto_que_no_puede_calcularse_lo_deja_sin_precio(
    entorno: Entorno,
) -> None:
    lista_id, version_id = _borrador_de_general(entorno)
    gaseosa_id = entorno.crear_producto("Gaseosa C")
    entorno.fijar_precio(lista_id, version_id, gaseosa_id, "12000.00")

    comando = entorno.fijar_precio(lista_id, version_id, gaseosa_id, None)

    assert gaseosa_id not in entorno.precios(version_id)
    assert comando.resultado is not None
    assert comando.resultado["precio_final"] is None
    assert comando.resultado["manual"] is False


def test_quitar_la_marca_de_un_precio_que_no_era_manual_lo_deja_como_estaba(
    entorno: Entorno,
) -> None:
    lista_id, version_id = _borrador_de_general(entorno)

    entorno.fijar_precio(lista_id, version_id, entorno.vino_id, None)

    precio = entorno.precios(version_id)[entorno.vino_id]
    assert (precio.precio_final, precio.manual) == (Decimal("8600.00"), False)


# --- rechazos ---------------------------------------------------------------------------------


def test_inv11_fijar_un_precio_en_una_version_publicada_se_rechaza(entorno: Entorno) -> None:
    """Escenario "Fijar un precio en una versión publicada" (INV-11, PRC-04)."""
    lista_id, version_id = _borrador_de_general(entorno)
    entorno.publicar_por_sql(version_id)

    with pytest.raises(VersionNoEsBorradorError) as error:
        entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")

    assert error.value.codigo == "VERSION_NO_ES_BORRADOR"
    entorno.sesion.rollback()
    precio = entorno.precios(version_id)[entorno.vino_id]
    assert (precio.precio_final, precio.manual) == (Decimal("8600.00"), False)


def test_un_producto_inactivo_se_rechaza(entorno: Entorno) -> None:
    lista_id, version_id = _borrador_de_general(entorno)
    entorno.sesion.execute(
        text("UPDATE producto SET activo = false WHERE id = :p"), {"p": entorno.vino_id}
    )

    with pytest.raises(ProductoInactivoError) as error:
        entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")

    assert error.value.codigo == "PRODUCTO_INACTIVO"


def test_un_producto_inexistente_o_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    lista_id, version_id = _borrador_de_general(entorno)
    ajeno = Entorno(db_session).vino_id

    with pytest.raises(RecursoNoEncontradoError):
        entorno.fijar_precio(lista_id, version_id, ajeno, "9000.00")
    with pytest.raises(RecursoNoEncontradoError):
        entorno.fijar_precio(lista_id, version_id, uuid4(), "9000.00")


def test_inv21_la_version_de_otra_organizacion_o_de_otra_lista_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    lista_id, version_id = _borrador_de_general(entorno)
    otra = Entorno(db_session)
    lista_ajena = otra.crear_lista("General")
    otra.informar_costo(otra.vino_id, "1000")
    otra.crear_regla(lista_ajena)
    otra.generar_borrador(lista_ajena)
    version_ajena = otra.versiones(lista_ajena)[0].id
    otra_lista_propia = entorno.crear_lista("Mayorista")

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.fijar_precio(lista_ajena, version_ajena, entorno.vino_id, "9000.00")
    assert error.value.status_http == 404
    with pytest.raises(RecursoNoEncontradoError):
        entorno.fijar_precio(lista_id, version_ajena, entorno.vino_id, "9000.00")
    with pytest.raises(RecursoNoEncontradoError):
        entorno.fijar_precio(otra_lista_propia, version_id, entorno.vino_id, "9000.00")

    db_session.rollback()
    assert otra.precios(version_ajena)[otra.vino_id].manual is False


def test_sin_gestionar_listas_se_rechaza_con_403(entorno: Entorno) -> None:
    """Escenario "Sin permiso" (SEG-06): `PUBLICAR_LISTAS` solo no alcanza."""
    lista_id, version_id = _borrador_de_general(entorno)
    entorno.actuar_con_permisos(frozenset({"PUBLICAR_LISTAS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")

    entorno.sesion.rollback()
    assert entorno.precios(version_id)[entorno.vino_id].manual is False


def test_inv06_el_doble_envio_devuelve_el_resultado_original(entorno: Entorno) -> None:
    lista_id, version_id = _borrador_de_general(entorno)
    operation_id = uuid4()

    primero = entorno.fijar_precio(
        lista_id, version_id, entorno.vino_id, "9000.00", operation_id=operation_id
    )
    segundo = entorno.fijar_precio(
        lista_id, version_id, entorno.vino_id, "9000.00", operation_id=operation_id
    )

    assert primero.resultado == segundo.resultado
    assert len(entorno.auditorias(PRECIO_FIJAR)) == 1


def test_inv06_el_mismo_operation_id_con_otro_importe_es_inconsistente(
    entorno: Entorno,
) -> None:
    lista_id, version_id = _borrador_de_general(entorno)
    operation_id = uuid4()
    entorno.fijar_precio(
        lista_id, version_id, entorno.vino_id, "9000.00", operation_id=operation_id
    )

    with pytest.raises(ComandoInconsistenteError):
        entorno.fijar_precio(
            lista_id, version_id, entorno.vino_id, "9100.00", operation_id=operation_id
        )

    entorno.sesion.rollback()
    assert entorno.precios(version_id)[entorno.vino_id].precio_final == Decimal("9000.00")


# --- conservación de manuales al generar y regenerar (tarea 7.4) ----------------------------------


def _con_un_manual_publicado(entorno: Entorno) -> tuple[UUID, UUID]:
    """`General` con la versión n.º 1 publicada con Vino A manual a `9000.00`."""
    lista_id, version_id = _borrador_de_general(entorno)
    entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")
    entorno.publicar_por_sql(version_id)
    return lista_id, version_id


def test_el_manual_de_la_version_base_se_conserva_al_llegar_un_costo_nuevo(
    entorno: Entorno,
) -> None:
    """Escenario "El manual se conserva al llegar un costo nuevo": sigue a `9000.00` y
    manual, con costo de referencia `6600.000000` y calculado `9428.571429`."""
    lista_id, base_id = _con_un_manual_publicado(entorno)
    entorno.informar_costo(entorno.vino_id, "1100", creado_en=MOMENTO + timedelta(minutes=1))

    entorno.generar_borrador(lista_id)

    borrador = entorno.versiones(lista_id)[1]
    precio = entorno.precios(borrador.id)[entorno.vino_id]
    assert (precio.precio_final, precio.manual) == (Decimal("9000.00"), True)
    assert precio.costo_referencia == Decimal("6600.000000")
    assert precio.precio_calculado == Decimal("9428.571429")
    assert entorno.precios(base_id)[entorno.vino_id].costo_referencia == Decimal("6000.000000")


def test_el_manual_fijado_en_el_borrador_se_conserva_al_regenerarlo(entorno: Entorno) -> None:
    """Escenario "Manual fijado en el borrador y regenerado" (D5)."""
    lista_id, version_id = _borrador_de_general(entorno)
    entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")
    entorno.informar_costo(entorno.vino_id, "1100", creado_en=MOMENTO + timedelta(minutes=1))

    entorno.generar_borrador(lista_id)

    (borrador,) = entorno.versiones(lista_id)
    precio = entorno.precios(borrador.id)[entorno.vino_id]
    assert (precio.precio_final, precio.manual) == (Decimal("9000.00"), True)
    assert precio.precio_calculado == Decimal("9428.571429")


def test_quitar_la_marca_en_el_borrador_gana_sobre_el_manual_de_la_base(
    entorno: Entorno,
) -> None:
    """El borrador regenerado parte de sí mismo, no de la base: lo que el usuario decidió en
    él (quitar la marca) no se deshace al regenerar."""
    lista_id, _base_id = _con_un_manual_publicado(entorno)
    entorno.generar_borrador(lista_id)
    borrador = entorno.versiones(lista_id)[1]
    assert entorno.precios(borrador.id)[entorno.vino_id].manual is True
    entorno.fijar_precio(lista_id, borrador.id, entorno.vino_id, None)

    entorno.generar_borrador(lista_id)

    precio = entorno.precios(borrador.id)[entorno.vino_id]
    assert (precio.precio_final, precio.manual) == (Decimal("8600.00"), False)


def test_un_manual_sin_costo_se_conserva_y_toma_el_calculo_cuando_llega_el_costo(
    entorno: Entorno,
) -> None:
    lista_id, version_id = _borrador_de_general(entorno)
    gaseosa_id = entorno.crear_producto("Gaseosa C", unidades_base=12)
    entorno.fijar_precio(lista_id, version_id, gaseosa_id, "12000.00")

    entorno.generar_borrador(lista_id)
    sin_costo = entorno.precios(version_id)[gaseosa_id]
    assert (sin_costo.precio_final, sin_costo.precio_calculado) == (Decimal("12000.00"), None)
    entorno.informar_costo(gaseosa_id, "1000", creado_en=MOMENTO + timedelta(minutes=1))
    entorno.generar_borrador(lista_id)

    con_costo = entorno.precios(version_id)[gaseosa_id]
    assert (con_costo.precio_final, con_costo.manual) == (Decimal("12000.00"), True)
    assert con_costo.costo_referencia == Decimal("12000.000000")
    assert con_costo.precio_calculado == Decimal("17142.857143")


def test_un_manual_de_un_producto_inactivo_no_pasa_al_borrador(entorno: Entorno) -> None:
    lista_id, _base_id = _con_un_manual_publicado(entorno)
    entorno.sesion.execute(
        text("UPDATE producto SET activo = false WHERE id = :p"), {"p": entorno.vino_id}
    )

    entorno.generar_borrador(lista_id)

    borrador = entorno.versiones(lista_id)[1]
    assert entorno.precios(borrador.id) == {}


def test_un_manual_conservado_mantiene_las_unidades_con_que_se_fijo_su_precio_d1(
    entorno: Entorno,
) -> None:
    """Si cambia la referencia del producto, el precio manual sigue diciendo "por 6 unidades":
    el importe fijado a mano corresponde a esa cantidad y el cálculo que lo acompaña se hace
    sobre ella (D1)."""
    lista_id, _base_id = _con_un_manual_publicado(entorno)
    entorno.sesion.execute(
        text("UPDATE presentacion SET es_referencia = false WHERE id = :p"),
        {"p": entorno.vino_presentacion_id},
    )
    caja_x12 = entorno.crear_presentacion(entorno.vino_id, "Caja x12", 12)
    entorno.sesion.execute(
        text("UPDATE presentacion SET es_referencia = true WHERE id = :p"), {"p": caja_x12}
    )

    entorno.generar_borrador(lista_id)

    borrador = entorno.versiones(lista_id)[1]
    precio = entorno.precios(borrador.id)[entorno.vino_id]
    assert (precio.precio_final, precio.unidades_referencia) == (Decimal("9000.00"), 6)
    assert precio.costo_referencia == Decimal("6000.000000")


# --- señales de margen y de sin costo (PRC-17, D7) ------------------------------------------------


def _senales(entorno: Entorno, lista_id: UUID):  # type: ignore[no-untyped-def]
    return precios_service.senales_del_borrador(entorno.org, entorno.sesion, lista_id=lista_id)


def test_un_manual_por_debajo_del_calculado_lleva_la_senal_de_margen_menor(
    entorno: Entorno,
) -> None:
    """Escenario "Señal de margen menor que el de la regla": `9000.00` < `9428.571429`."""
    lista_id, _base_id = _con_un_manual_publicado(entorno)
    entorno.informar_costo(entorno.vino_id, "1100", creado_en=MOMENTO + timedelta(minutes=1))
    entorno.generar_borrador(lista_id)

    senales = _senales(entorno, lista_id)

    assert senales[entorno.vino_id].margen_menor is True
    assert senales[entorno.vino_id].sin_costo is False


def test_un_manual_con_margen_suficiente_no_lleva_la_senal(entorno: Entorno) -> None:
    """Escenario "Manual con margen suficiente": `9000.00` >= `8571.428571`."""
    lista_id, version_id = _borrador_de_general(entorno)
    entorno.fijar_precio(lista_id, version_id, entorno.vino_id, "9000.00")

    senales = _senales(entorno, lista_id)

    assert senales[entorno.vino_id].margen_menor is False


def test_un_precio_calculado_no_lleva_senales_de_manual(entorno: Entorno) -> None:
    lista_id, _version_id = _borrador_de_general(entorno)

    senales = _senales(entorno, lista_id)

    assert senales[entorno.vino_id].margen_menor is False
    assert senales[entorno.vino_id].sin_costo is False


def test_un_manual_sin_costo_lleva_el_aviso_de_sin_costo_y_no_la_senal_de_margen(
    entorno: Entorno,
) -> None:
    """PRC-17, D7: "sin costo o sin regla no hay esa señal, y el precio se señala como sin
    costo"."""
    lista_id, version_id = _borrador_de_general(entorno)
    gaseosa_id = entorno.crear_producto("Gaseosa C")
    entorno.fijar_precio(lista_id, version_id, gaseosa_id, "12000.00")

    senales = _senales(entorno, lista_id)

    assert senales[gaseosa_id].sin_costo is True
    assert senales[gaseosa_id].margen_menor is False


def test_las_senales_de_una_lista_sin_borrador_estan_vacias(entorno: Entorno) -> None:
    lista_id = entorno.crear_lista()

    assert _senales(entorno, lista_id) == {}


def test_las_senales_de_una_lista_ajena_responden_404(
    entorno: Entorno, db_session: Session
) -> None:
    ajena = Entorno(db_session).crear_lista("General")

    with pytest.raises(RecursoNoEncontradoError):
        _senales(entorno, ajena)
