"""Tarea 7.3 (change 18a; spec `ventas/composicion-de-venta`, requisitos de precio; `design.md`
D2, D6, D7, D9; gobernanza ALTA): el precio de `VENTA_CONFIRMAR` con conexión, contra
PostgreSQL real.

Lista aplicable y versión vigente al `occurred_at`; otra lista o una versión anterior con
`USAR_LISTA_ANTERIOR` y motivo; lo que no se puede resolver rechaza la venta entera; el precio
que vio el usuario se compara con el del servidor; los valores quedan congelados.

Reglas citadas: PRC-20, PRC-21, PRC-22, PRC-23, VTA-10, PRC-04, PRC-05, INV-10, INV-21, TR-05,
TR-10.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_presentacion_sql
from ventas_confirmar_utiles import (
    MOMENTO_VENTA,
    PERMISOS_DE_SUPERVISOR,
    PERMISOS_DE_VENTA,
    EntornoVenta,
)

from app.core.errors import DomainError, PermisoRequeridoError
from app.modules.precios.domain.errores import (
    ListaInactivaError,
    ListaSinVersionVigenteError,
    SinListaAplicableError,
)
from app.modules.ventas.domain.errores import (
    MomentoFueraDeRangoError,
    MotivoInvalidoError,
    PrecioDifiereError,
    ProductoSinPrecioError,
    VersionNoPermitidaError,
)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

AYER = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
HOY_TEMPRANO = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)
MAÑANA = datetime(2026, 10, 20, 0, 0, tzinfo=UTC)


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session, permisos=PERMISOS_DE_SUPERVISOR)


def _con_version_nueva(entorno: EntornoVenta) -> tuple[object, object]:
    """ "General" con la versión 1 ($12.500, histórica) y la 2 vigente ($13.000) desde hoy
    temprano; devuelve `(v1, v2)`."""
    v2 = entorno.crear_version(entorno.lista_id, 2, HOY_TEMPRANO, precio_vino="13000.00")
    entorno.sesion.commit()
    return entorno.version_id, v2


# --- la lista aplicable y la versión vigente (PRC-20, PRC-22, PRC-23) --------------------------


def test_prc20_la_venta_usa_la_version_vigente_al_momento_y_la_congela(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Precio de la lista del cliente" con una versión nueva vigente: precio
    `13000.00`, bruto de 15 botellas `32500.00`."""
    _, v2 = _con_version_nueva(entorno)

    entorno.vender(entorno.linea(precio="13000.00", version_id=v2))  # type: ignore[arg-type]

    (venta,) = entorno.ventas()
    assert venta.lista_id == entorno.lista_id
    assert venta.lista_version_id == v2
    assert venta.motivo_lista_id is None
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert linea.lista_version_id == v2
    assert (linea.precio_referencia, linea.unidades_referencia) == (Decimal("13000.00"), 6)
    assert linea.importe_bruto == Decimal("32500.00")


def test_prc20_el_cliente_con_lista_propia_usa_esa_lista(entorno: EntornoVenta) -> None:
    """Triangula: Kiosco La Esquina tiene asignada la lista "Mayorista" ($11.000), no la
    predeterminada."""
    mayorista = entorno.crear_lista("Mayorista")
    version = entorno.crear_version(mayorista, 1, AYER, precio_vino="11000.00")
    entorno.actualizar_cliente(entorno.cliente_id, lista_precio_id=mayorista)

    entorno.vender(entorno.linea(precio="11000.00", version_id=version))

    (venta,) = entorno.ventas()
    assert (venta.lista_id, venta.lista_version_id) == (mayorista, version)
    assert venta.total == Decimal("27500.00")


def test_prc22_una_unidad_suelta_usa_las_unidades_de_referencia_guardadas_en_el_precio(
    entorno: EntornoVenta,
) -> None:
    """El precio guardó 12 unidades de referencia (una "Caja x12" de entonces): el bruto de 1
    botella es `precio × 1 / 12`, aunque hoy la referencia sea la caja x6."""
    version = entorno.crear_version(entorno.lista_id, 2, HOY_TEMPRANO)
    entorno.poner_precio(version, entorno.vino_id, "12000.00", 12)
    entorno.sesion.commit()

    entorno.vender(
        entorno.linea(cantidad=1, precio="12000.00", unidades_referencia=12, version_id=version)
    )

    (venta,) = entorno.ventas()
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert (linea.unidades_referencia, linea.importe_bruto) == (12, Decimal("1000.00"))


# --- lo que no se puede resolver rechaza la venta entera (VTA-10, PRC-10, D7) -------------------


def test_vta10_sin_lista_aplicable_se_rechaza_sin_efectos(entorno: EntornoVenta) -> None:
    """Escenario "Sin lista aplicable": cliente sin lista y la organización sin predeterminada."""
    entorno.configurar(lista_precio_default_id=None)
    entorno.sesion.commit()

    with pytest.raises(SinListaAplicableError) as error:
        entorno.vender()

    assert (error.value.codigo, error.value.status_http) == ("SIN_LISTA_APLICABLE", 409)
    entorno.sin_efectos_de_venta()


def test_vta10_una_lista_asignada_inactiva_no_cae_a_la_predeterminada(
    entorno: EntornoVenta,
) -> None:
    inactiva = entorno.crear_lista("Vieja", activo=False)
    entorno.actualizar_cliente(entorno.cliente_id, lista_precio_id=inactiva)
    entorno.sesion.commit()

    with pytest.raises(SinListaAplicableError):
        entorno.vender()

    entorno.sin_efectos_de_venta()


def test_vta10_una_lista_sin_version_vigente_se_rechaza(entorno: EntornoVenta) -> None:
    """Escenario "Sin versión vigente": la única versión de la lista rige desde mañana."""
    nueva = entorno.crear_lista("Nueva")
    entorno.crear_version(nueva, 1, MAÑANA, precio_vino="12500.00")
    entorno.actualizar_cliente(entorno.cliente_id, lista_precio_id=nueva)
    entorno.sesion.commit()

    with pytest.raises(ListaSinVersionVigenteError):
        entorno.vender()

    entorno.sin_efectos_de_venta()


def test_vta10_un_producto_sin_precio_rechaza_la_venta_entera_y_nombra_al_producto(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Producto sin precio": Vino A con precio y Cerveza B sin precio; no se vende
    Vino A solo."""
    cerveza_id, caja_cerveza_id = entorno.crear_producto("Cerveza B")
    entorno.comprar(cerveza_id, 120, "600")
    entorno.sesion.commit()

    with pytest.raises(ProductoSinPrecioError) as error:
        entorno.vender(
            entorno.linea(),
            entorno.linea(
                cerveza_id, caja_cerveza_id, 1, unidades_presentacion=12, unidades_referencia=12
            ),
        )

    assert error.value.status_http == 409
    assert error.value.extension is not None
    assert error.value.extension["productos"] == [
        {"producto_id": str(cerveza_id), "nombre": "Cerveza B"}
    ]
    entorno.sin_efectos_de_venta()


# --- otra lista o una versión anterior (PRC-21, D6) --------------------------------------------


def test_prc21_una_version_anterior_con_motivo_congela_esa_version_y_ese_motivo(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Versión anterior con motivo": la 1 ($12.500) y la vigente 2 ($13.000)."""
    v1, _ = _con_version_nueva(entorno)

    entorno.vender(
        entorno.linea(precio="12500.00", version_id=v1),  # type: ignore[arg-type]
        lista_id=str(entorno.lista_id),
        lista_version_id=str(v1),
        motivo_lista_id=str(entorno.motivo_lista_id),
    )

    (venta,) = entorno.ventas()
    assert (venta.lista_id, venta.lista_version_id) == (entorno.lista_id, v1)
    assert venta.motivo_lista_id == entorno.motivo_lista_id
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert (linea.lista_version_id, linea.precio_referencia) == (v1, Decimal("12500.00"))


def test_prc21_otra_lista_activa_con_su_version_vigente_requiere_motivo_y_se_guarda(
    entorno: EntornoVenta,
) -> None:
    mayorista = entorno.crear_lista("Mayorista")
    version = entorno.crear_version(mayorista, 1, AYER, precio_vino="11000.00")
    entorno.sesion.commit()

    entorno.vender(
        entorno.linea(precio="11000.00", version_id=version),
        lista_id=str(mayorista),
        motivo_lista_id=str(entorno.motivo_lista_id),
    )

    (venta,) = entorno.ventas()
    assert (venta.lista_id, venta.lista_version_id) == (mayorista, version)
    assert venta.motivo_lista_id == entorno.motivo_lista_id


def test_prc21_elegir_la_lista_y_la_version_aplicables_no_pide_permiso_ni_motivo(
    db_session: Session,
) -> None:
    """Elegir lo mismo que ya corresponde no es "otra lista" ni "versión anterior"."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_VENTA)

    entorno.vender(lista_id=str(entorno.lista_id), lista_version_id=str(entorno.version_id))

    (venta,) = entorno.ventas()
    assert venta.motivo_lista_id is None


def test_prc21_sin_el_permiso_responde_403_sin_efectos(db_session: Session) -> None:
    """Escenario "Sin permiso" de `USAR_LISTA_ANTERIOR`."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_VENTA)
    v1, _ = _con_version_nueva(entorno)

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.vender(
            entorno.linea(precio="12500.00", version_id=v1),  # type: ignore[arg-type]
            lista_id=str(entorno.lista_id),
            lista_version_id=str(v1),
            motivo_lista_id=str(entorno.motivo_lista_id),
        )

    assert error.value.status_http == 403
    entorno.sin_efectos_de_venta()


def test_prc21_el_motivo_es_obligatorio_si_la_organizacion_lo_exige(entorno: EntornoVenta) -> None:
    # Escenario: "Motivo faltante cuando la organización lo exige"
    """Escenario "Motivo faltante": sin motivo y con un motivo de otro ámbito."""
    v1, _ = _con_version_nueva(entorno)
    otro_ambito = entorno.crear_motivo("AJUSTE_STOCK", "Rotura")
    entorno.sesion.commit()

    for motivo in (None, str(otro_ambito)):
        cambios: dict[str, object] = {}
        if motivo is not None:
            cambios["motivo_lista_id"] = motivo
        with pytest.raises(MotivoInvalidoError) as error:
            entorno.vender(
                entorno.linea(precio="12500.00", version_id=v1),  # type: ignore[arg-type]
                lista_id=str(entorno.lista_id),
                lista_version_id=str(v1),
                **cambios,
            )
        assert (error.value.codigo, error.value.status_http) == ("MOTIVO_INVALIDO", 422)
        entorno.sesion.rollback()

    entorno.sin_efectos_de_venta()


def test_prc21_un_motivo_inactivo_o_de_otra_organizacion_se_rechaza(
    entorno: EntornoVenta, db_session: Session
) -> None:
    v1, _ = _con_version_nueva(entorno)
    inactivo = entorno.crear_motivo("LISTA_ANTERIOR", "Viejo", activo=False)
    otra = EntornoVenta(db_session)
    ajeno = otra.crear_motivo("LISTA_ANTERIOR", "Ajeno")
    entorno.sesion.commit()

    for motivo in (inactivo, ajeno):
        with pytest.raises(MotivoInvalidoError):
            entorno.vender(
                entorno.linea(precio="12500.00", version_id=v1),  # type: ignore[arg-type]
                lista_id=str(entorno.lista_id),
                lista_version_id=str(v1),
                motivo_lista_id=str(motivo),
            )
        entorno.sesion.rollback()

    entorno.sin_efectos_de_venta()


def test_prc21_el_motivo_es_opcional_si_la_organizacion_no_lo_exige(entorno: EntornoVenta) -> None:
    """Escenario "Sin motivo cuando la organización no lo exige"."""
    entorno.configurar(motivo_obligatorio_lista=False)
    entorno.sesion.commit()
    v1, _ = _con_version_nueva(entorno)

    entorno.vender(
        entorno.linea(precio="12500.00", version_id=v1),  # type: ignore[arg-type]
        lista_id=str(entorno.lista_id),
        lista_version_id=str(v1),
    )

    (venta,) = entorno.ventas()
    assert (venta.lista_version_id, venta.motivo_lista_id) == (v1, None)


def test_prc21_una_version_programada_o_anulada_se_rechaza(entorno: EntornoVenta) -> None:
    """Escenario "Versión programada o anulada": una rige desde mañana y la otra está
    anulada."""
    programada = entorno.crear_version(entorno.lista_id, 2, MAÑANA, precio_vino="14000.00")
    anulada = entorno.crear_version(
        entorno.lista_id, 3, AYER, estado="ANULADA", precio_vino="9000.00"
    )
    entorno.sesion.commit()

    for version, precio in ((programada, "14000.00"), (anulada, "9000.00")):
        with pytest.raises(VersionNoPermitidaError) as error:
            entorno.vender(
                entorno.linea(precio=precio, version_id=version),
                lista_id=str(entorno.lista_id),
                lista_version_id=str(version),
                motivo_lista_id=str(entorno.motivo_lista_id),
            )
        assert (error.value.codigo, error.value.status_http) == ("VERSION_NO_PERMITIDA", 409)
        entorno.sesion.rollback()

    entorno.sin_efectos_de_venta()


def test_prc21_una_version_de_otra_lista_no_esta_permitida_y_la_ajena_responde_404(
    entorno: EntornoVenta, db_session: Session
) -> None:
    mayorista = entorno.crear_lista("Mayorista")
    de_otra_lista = entorno.crear_version(mayorista, 1, AYER, precio_vino="11000.00")
    ajena_lista = EntornoVenta(db_session)
    entorno.sesion.commit()

    with pytest.raises(VersionNoPermitidaError):
        entorno.vender(
            entorno.linea(precio="11000.00", version_id=de_otra_lista),
            lista_id=str(entorno.lista_id),
            lista_version_id=str(de_otra_lista),
            motivo_lista_id=str(entorno.motivo_lista_id),
        )
    entorno.sesion.rollback()
    with pytest.raises(DomainError) as error:
        entorno.vender(
            entorno.linea(),
            lista_id=str(entorno.lista_id),
            lista_version_id=str(ajena_lista.version_id),
            motivo_lista_id=str(entorno.motivo_lista_id),
        )
    assert (error.value.codigo, error.value.status_http) == ("RECURSO_NO_ENCONTRADO", 404)

    entorno.sin_efectos_de_venta()


def test_prc20_una_lista_elegida_inactiva_se_rechaza(entorno: EntornoVenta) -> None:
    """Escenario "Otra lista inactiva"."""
    inactiva = entorno.crear_lista("Vieja", activo=False)
    entorno.crear_version(inactiva, 1, AYER, precio_vino="9000.00")
    entorno.sesion.commit()

    with pytest.raises(ListaInactivaError) as error:
        entorno.vender(lista_id=str(inactiva), motivo_lista_id=str(entorno.motivo_lista_id))

    assert (error.value.codigo, error.value.status_http) == ("LISTA_INACTIVA", 409)
    entorno.sin_efectos_de_venta()


# --- el precio que vio el usuario (TR-10, D2) ---------------------------------------------------


def test_tr10_si_se_publico_una_version_entre_la_pantalla_y_la_confirmacion_se_rechaza(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Se publicó una versión entre la pantalla y la confirmación": la pantalla
    mostró $12.500 (bruto `31250.00`) y el servidor resuelve $13.000 (bruto `32500.00`)."""
    contenido = entorno.contenido()
    _con_version_nueva(entorno)

    with pytest.raises(PrecioDifiereError) as error:
        entorno.enviar(contenido)

    assert (error.value.codigo, error.value.status_http) == ("PRECIO_DIFIERE", 409)
    assert error.value.extension is not None
    (linea,) = error.value.extension["lineas"]
    assert (linea["precio_referencia"], linea["importe_bruto"]) == ("13000.00", "32500.00")
    assert error.value.extension["total"] == "32500.00"
    entorno.sin_efectos_de_venta()


def test_tr10_el_mismo_comando_se_acepta_con_los_valores_del_servidor(
    entorno: EntornoVenta,
) -> None:
    """Después del rechazo el usuario reconfirma con los valores del servidor."""
    _, v2 = _con_version_nueva(entorno)

    comando = entorno.vender(entorno.linea(precio="13000.00", version_id=v2))  # type: ignore[arg-type]

    assert comando.estado == "ACEPTADO"


def test_tr10_un_total_manipulado_se_rechaza(entorno: EntornoVenta) -> None:
    """Escenario "Total manipulado": total esperado `1.00` para un bruto de `31250.00`."""
    with pytest.raises(PrecioDifiereError):
        entorno.vender(total="1.00")

    entorno.sin_efectos_de_venta()


@pytest.mark.parametrize(
    "cambio",
    [
        {"precio_referencia": "12000.00"},
        {"unidades_referencia": 12},
        {"importe_bruto": "31249.99"},
    ],
)
def test_tr10_cualquier_valor_esperado_distinto_rechaza_la_venta(
    entorno: EntornoVenta, cambio: dict[str, object]
) -> None:
    linea = entorno.linea()
    linea.update(cambio)

    with pytest.raises(PrecioDifiereError):
        entorno.vender(linea, total="31250.00")

    entorno.sin_efectos_de_venta()


def test_tr10_otra_version_esperada_rechaza_la_venta(entorno: EntornoVenta) -> None:
    with pytest.raises(PrecioDifiereError):
        entorno.vender(entorno.linea(version_id=uuid4()))

    entorno.sin_efectos_de_venta()


# --- el momento de la venta (PRC-20, TR-05, D9) -------------------------------------------------


def test_tr05_un_reloj_atrasado_un_dia_se_rechaza(entorno: EntornoVenta) -> None:
    """Escenario "Reloj atrasado un día"."""
    with pytest.raises(MomentoFueraDeRangoError) as error:
        entorno.enviar(occurred_at=MOMENTO_VENTA - timedelta(days=1))

    assert (error.value.codigo, error.value.status_http) == ("MOMENTO_FUERA_DE_RANGO", 422)
    entorno.sin_efectos_de_venta()


def test_tr05_dos_minutos_antes_esta_dentro_del_margen_y_resuelve_la_version_de_ese_momento(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Dentro del margen": una versión nueva rige desde hace un minuto; el
    `occurred_at` de hace dos minutos todavía usa la anterior."""
    entorno.crear_version(
        entorno.lista_id, 2, MOMENTO_VENTA - timedelta(minutes=1), precio_vino="13000.00"
    )

    comando = entorno.enviar(occurred_at=MOMENTO_VENTA - timedelta(minutes=2))

    assert comando.estado == "ACEPTADO"
    (venta,) = entorno.ventas()
    assert venta.lista_version_id == entorno.version_id


def test_tr05_el_margen_de_la_organizacion_manda_sobre_el_de_300_segundos(
    entorno: EntornoVenta,
) -> None:
    entorno.configurar(desvio_reloj_max_segundos=60)
    entorno.sesion.commit()

    with pytest.raises(MomentoFueraDeRangoError) as error:
        entorno.enviar(occurred_at=MOMENTO_VENTA - timedelta(minutes=2))

    assert error.value.extension == {"margen_segundos": 60}
    entorno.sin_efectos_de_venta()


# --- los valores quedan congelados (PRC-23, PRC-04, INV-10) --------------------------------------


def test_prc23_publicar_una_version_nueva_no_cambia_la_venta(entorno: EntornoVenta) -> None:
    """Escenario "Publicar una versión nueva no cambia la venta"."""
    entorno.vender()

    entorno.sesion.commit()
    entorno.poner_precio(
        entorno.crear_version(entorno.lista_id, 2, MOMENTO_VENTA, precio_vino=None),
        entorno.vino_id,
        "13000.00",
        6,
    )
    entorno.sesion.commit()

    (venta,) = entorno.ventas()
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert (linea.precio_referencia, linea.unidades_referencia, linea.importe_bruto) == (
        Decimal("12500.00"),
        6,
        Decimal("31250.00"),
    )


def test_prc04_cambiar_la_referencia_del_producto_no_cambia_la_venta(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Cambiar la referencia del producto no cambia la venta": la referencia pasa
    a una "Caja x12" y la línea conserva las unidades de referencia 6."""
    entorno.vender()
    entorno.sesion.commit()

    entorno.sesion.execute(
        text("UPDATE presentacion SET es_referencia = false WHERE organizacion_id = :o"),
        {"o": entorno.org},
    )
    crear_presentacion_sql(
        entorno.sesion,
        entorno.org,
        entorno.vino_id,
        nombre="Caja x12",
        unidades_base=12,
        es_referencia=True,
    )
    entorno.sesion.commit()

    (venta,) = entorno.ventas()
    (linea,) = entorno.lineas_de_venta(venta.id)
    assert linea.unidades_referencia == 6
    assert linea.importe_bruto == Decimal("31250.00")
