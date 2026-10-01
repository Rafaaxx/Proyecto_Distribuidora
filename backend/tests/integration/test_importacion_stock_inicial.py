"""Tarea 7.1 (change 10): importación de stock inicial por `IMPORTACION_REGISTRAR`,
contra PostgreSQL real (`specs/importacion/puesta-en-marcha`, `design.md` D4, D7, D13).

Cada fila es una línea de `stock.service.registrar_stock_inicial` (las mismas reglas que
`STOCK_INICIAL_REGISTRAR`, ADR-037, TR-10): un ingreso con costo recalcula el promedio
(CST-11); una cantidad negativa corrige sin recalcularlo (CST-12) y no deja negativo el
saldo. El momento de los movimientos es el `occurred_at` del sobre (D7-A).

Reglas citadas: CST-10, CST-11, CST-12, STK-10, INV-01, INV-04, INV-06, INV-21.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from importacion_utiles import (
    MOMENTO,
    RELOJ,
    EntornoDeImportacion,
    contenido,
    errores_de,
    fila_de,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.catalogo.domain.presentaciones import DatosPresentacion
from app.modules.importacion.domain.errores import ImportacionConErroresError
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeMovimiento
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

TIPO = "STOCK_INICIAL"


def fila(
    numero: int, ubicacion: str, producto: str, cantidad: str, costo: str
) -> dict[str, object]:
    return fila_de(
        numero,
        {
            "ubicacion": ubicacion,
            "producto_codigo": producto,
            "cantidad_base": cantidad,
            "costo_unitario": costo,
        },
    )


class Mundo:
    """Vino A (`VA-750`) y Cerveza B (`CB-473`) sin movimientos, un depósito y un
    vehículo."""

    def __init__(self, entorno: EntornoDeImportacion) -> None:
        self.entorno = entorno
        categoria_id = entorno.categoria("Vinos")
        alicuota_id = entorno.alicuota("21")
        proveedor_id = entorno.proveedor("Bodega Sur")
        presentacion = [DatosPresentacion("Botella", 1, True, True, True)]
        self.vino_id = entorno.producto(
            "VA-750",
            presentacion,
            nombre="Vino A",
            categoria_id=categoria_id,
            proveedor_id=proveedor_id,
            alicuota_id=alicuota_id,
        )
        self.cerveza_id = entorno.producto(
            "CB-473",
            presentacion,
            nombre="Cerveza B",
            categoria_id=categoria_id,
            proveedor_id=proveedor_id,
            alicuota_id=alicuota_id,
        )
        self.deposito_id = entorno.ubicacion("Depósito Central")
        self.vehiculo_id = entorno.ubicacion("Camión 1", tipo="VEHICULO")


@pytest.fixture
def entorno(db_session: Session) -> EntornoDeImportacion:
    return EntornoDeImportacion(db_session)


@pytest.fixture
def mundo(entorno: EntornoDeImportacion) -> Mundo:
    return Mundo(entorno)


def importar(
    entorno: EntornoDeImportacion, *filas: dict[str, object], operation_id: UUID | None = None
) -> Comando:
    return entorno.enviar(contenido(TIPO, list(filas), "stock.csv"), operation_id=operation_id)


def fallar(
    entorno: EntornoDeImportacion, *filas: dict[str, object]
) -> list[tuple[int, str | None, str]]:
    with pytest.raises(ImportacionConErroresError) as excinfo:
        importar(entorno, *filas)
    return errores_de(excinfo.value)


# --- escenarios de ingreso y promedio -------------------------------------------------


def test_stock_inicial_de_dos_ubicaciones_da_promedio_1050(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """CST-10, CST-11, STK-10: 60 a 1000 en el depósito y 60 a 1100 en el vehículo."""
    operation_id = uuid4()

    comando = importar(
        entorno,
        fila(2, "Depósito Central", "VA-750", "60", "1000"),
        fila(3, "Camión 1", "VA-750", "60", "1100"),
        operation_id=operation_id,
    )

    assert comando.resultado is not None
    assert (comando.resultado["filas_total"], comando.resultado["filas_ok"]) == (2, 2)
    assert entorno.saldo_de_stock(mundo.vino_id, mundo.deposito_id) == 60
    assert entorno.saldo_de_stock(mundo.vino_id, mundo.vehiculo_id) == 60
    assert str(entorno.promedio(mundo.vino_id)) == "1050.000000"
    movimientos = entorno.movimientos_de_stock(mundo.vino_id)
    assert {m.tipo for m in movimientos} == {"STOCK_INICIAL"}
    assert {m.origen_id for m in movimientos} == {operation_id}
    assert {m.occurred_at for m in movimientos} == {MOMENTO}
    assert len(entorno.importaciones()) == 1
    assert entorno.auditorias(operation_id) == 1


def test_el_promedio_pondera_por_cantidad_y_costo_de_cada_fila(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """Triangula: 10 a 100 y 30 a 200 dan (1000 + 6000) / 40 = 175; otro producto
    en el mismo archivo no se mezcla."""
    importar(
        entorno,
        fila(2, "Depósito Central", "VA-750", "10", "100"),
        fila(3, "Depósito Central", "CB-473", "5", "50,5"),
        fila(4, "Camión 1", "VA-750", "30", "200"),
    )

    assert str(entorno.promedio(mundo.vino_id)) == "175.000000"
    assert str(entorno.promedio(mundo.cerveza_id)) == "50.500000"
    assert entorno.saldo_de_stock(mundo.cerveza_id, mundo.vehiculo_id) == 0


def test_correccion_negativa_en_el_mismo_archivo_no_cambia_el_promedio(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """STK-10, CST-12."""
    importar(
        entorno,
        fila(2, "Depósito Central", "VA-750", "60", "1000"),
        fila(3, "Depósito Central", "VA-750", "-12", ""),
    )

    assert entorno.saldo_de_stock(mundo.vino_id, mundo.deposito_id) == 48
    assert str(entorno.promedio(mundo.vino_id)) == "1000.000000"
    cantidades = [m.cantidad_base for m in entorno.movimientos_de_stock(mundo.vino_id)]
    assert cantidades == [60, -12]


def test_la_correccion_sigue_a_su_ingreso_aunque_haya_otras_filas_en_el_medio(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """El orden de bloqueo es por (producto, ubicación) y estable: la corrección no puede
    quedar antes de su ingreso (si no, daría `STOCK_INSUFICIENTE`)."""
    importar(
        entorno,
        fila(2, "Camión 1", "CB-473", "20", "80"),
        fila(3, "Depósito Central", "VA-750", "60", "1000"),
        fila(4, "Camión 1", "CB-473", "-5", ""),
        fila(5, "Depósito Central", "VA-750", "-12", ""),
    )

    assert entorno.saldo_de_stock(mundo.cerveza_id, mundo.vehiculo_id) == 15
    assert entorno.saldo_de_stock(mundo.vino_id, mundo.deposito_id) == 48


def test_los_productos_se_escriben_en_orden_ascendente_de_id_sin_importar_el_del_archivo(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """`02` §7.3: el archivo trae los productos en orden inverso al de sus ids."""
    primero, segundo = sorted([mundo.vino_id, mundo.cerveza_id])
    codigo = {mundo.vino_id: "VA-750", mundo.cerveza_id: "CB-473"}
    importar(
        entorno,
        fila(2, "Depósito Central", codigo[segundo], "10", "100"),
        fila(3, "Depósito Central", codigo[primero], "10", "100"),
    )

    orden = [m.producto_id for m in entorno.movimientos_de_stock()]

    assert orden == [primero, segundo]


# --- costos y cantidades ilegibles o fuera de regla -------------------------------------------


@pytest.mark.parametrize(
    ("cantidad", "costo"),
    [("60", "0"), ("60", "1000,1234567"), ("60", ""), ("-12", "500")],
)
def test_costo_que_no_corresponde_da_costo_invalido_y_no_escribe_nada(
    entorno: EntornoDeImportacion, mundo: Mundo, cantidad: str, costo: str
) -> None:
    """ADR-037 puntos 5 y 6: cero, más de seis decimales (sin redondear), faltante en un
    ingreso y presente en una corrección son `COSTO_INVALIDO`."""
    importar(entorno, fila(2, "Depósito Central", "VA-750", "100", "1000"))
    sesion_antes = len(entorno.movimientos_de_stock())

    errores = fallar(entorno, fila(2, "Depósito Central", "VA-750", cantidad, costo))

    assert errores == [(2, "costo_unitario", "COSTO_INVALIDO")]
    assert len(entorno.movimientos_de_stock()) == sesion_antes


def test_cantidad_cero_o_decimal_o_ilegible_da_su_error_en_cantidad_base(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """INV-04."""
    errores = fallar(
        entorno,
        fila(2, "Depósito Central", "VA-750", "0", "1000"),
        fila(3, "Depósito Central", "VA-750", "10,5", "1000"),
        fila(4, "Depósito Central", "VA-750", "diez", "1000"),
    )

    assert errores == [
        (2, "cantidad_base", "CANTIDAD_INVALIDA"),
        (3, "cantidad_base", "CANTIDAD_INVALIDA"),
        (4, "cantidad_base", "CANTIDAD_INVALIDA"),
    ]


def test_costo_con_punto_es_numero_invalido(entorno: EntornoDeImportacion, mundo: Mundo) -> None:
    """D12: coma decimal, sin separador de miles."""
    errores = fallar(entorno, fila(2, "Depósito Central", "VA-750", "10", "1.000"))

    assert errores == [(2, "costo_unitario", "NUMERO_INVALIDO")]


# --- reglas de STK-10 y de la ubicación/producto -----------------------------------------------


def test_producto_con_operaciones_de_otro_tipo_da_producto_con_operaciones(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """STK-10: insertando una compra por el servicio."""
    usuario_dispositivo = (entorno.usuario_id, entorno.dispositivo_id)
    stock_service.registrar_movimientos(
        entorno.org,
        entorno.sesion,
        RELOJ,
        lineas=[
            LineaDeMovimiento(
                producto_id=mundo.vino_id,
                ubicacion_id=mundo.vehiculo_id,
                cantidad_base=10,
                tipo="COMPRA",
                costo_unitario="500",
                origen_tipo="COMPRA",
                origen_id=uuid4(),
            )
        ],
        usuario_id=usuario_dispositivo[0],
        dispositivo_id=usuario_dispositivo[1],
        operation_id=uuid4(),
        occurred_at=MOMENTO,
    )
    entorno.sesion.commit()

    errores = fallar(
        entorno,
        fila(2, "Depósito Central", "VA-750", "60", "1000"),
        fila(3, "Depósito Central", "CB-473", "60", "1000"),
    )

    assert errores == [(2, "producto_codigo", "PRODUCTO_CON_OPERACIONES")]


def test_correccion_que_deja_negativo_da_stock_insuficiente_aun_con_permitir_stock_negativo(
    db_session: Session,
) -> None:
    """STK-10, ADR-037 punto 1: no hay excepción por permiso en una corrección."""
    entorno = EntornoDeImportacion(
        db_session, permisos=frozenset({"IMPORTAR_DATOS", "PERMITIR_STOCK_NEGATIVO"})
    )
    mundo = Mundo(entorno)
    importar(entorno, fila(2, "Camión 1", "VA-750", "10", "1000"))

    errores = fallar(entorno, fila(2, "Camión 1", "VA-750", "-12", ""))

    assert errores == [(2, "cantidad_base", "STOCK_INSUFICIENTE")]
    assert entorno.saldo_de_stock(mundo.vino_id, mundo.vehiculo_id) == 10


def test_correccion_mayor_que_el_ingreso_del_mismo_archivo_da_stock_insuficiente_en_su_fila(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    errores = fallar(
        entorno,
        fila(2, "Camión 1", "VA-750", "10", "1000"),
        fila(3, "Camión 1", "VA-750", "-12", ""),
    )

    assert errores == [(3, "cantidad_base", "STOCK_INSUFICIENTE")]


def test_ubicacion_inactiva_da_ubicacion_inactiva(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    entorno.ubicacion("Camión 2", tipo="VEHICULO", activa=False)

    errores = fallar(
        entorno,
        fila(2, "Camión 2", "VA-750", "10", "1000"),
        fila(3, "Depósito Central", "VA-750", "10", "1000"),
    )

    assert errores == [(2, "ubicacion", "UBICACION_INACTIVA")]


def test_producto_inactivo_da_producto_inactivo(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """CAT-05."""
    entorno.sesion.execute(
        text("UPDATE producto SET activo = false WHERE id = :id"), {"id": mundo.vino_id}
    )
    entorno.sesion.commit()

    errores = fallar(
        entorno,
        fila(2, "Depósito Central", "VA-750", "10", "1000"),
        fila(3, "Depósito Central", "CB-473", "10", "1000"),
    )

    assert errores == [(2, "producto_codigo", "PRODUCTO_INACTIVO")]


# --- claves naturales ----------------------------------------------------------------------


def test_ubicacion_y_producto_inexistentes_son_referencia_no_encontrada_cada_uno_en_su_columna(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    errores = fallar(
        entorno,
        fila(2, "Depósito Fantasma", "VA-750", "10", "1000"),
        fila(3, "Depósito Central", "NO-EXISTE", "10", "1000"),
    )

    assert errores == [
        (2, "ubicacion", "REFERENCIA_NO_ENCONTRADA"),
        (3, "producto_codigo", "REFERENCIA_NO_ENCONTRADA"),
    ]


def test_las_claves_se_comparan_sin_mayusculas_ni_espacios_al_borde(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    importar(entorno, fila(2, "  depósito central ", " va-750", "10", "1000"))

    assert entorno.saldo_de_stock(mundo.vino_id, mundo.deposito_id) == 10


def test_ubicacion_de_otra_organizacion_es_no_encontrada(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """INV-21: igual que si no existiera."""
    otra = EntornoDeImportacion(entorno.sesion)
    otra.ubicacion("Galpón Ajeno")

    errores = fallar(entorno, fila(2, "Galpón Ajeno", "VA-750", "10", "1000"))

    assert errores == [(2, "ubicacion", "REFERENCIA_NO_ENCONTRADA")]


# --- todo o nada, informe completo, idempotencia ------------------------------------------------


def test_una_fila_mala_impide_importar_las_buenas_y_se_informan_todos_los_errores(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """INV-01."""
    errores = fallar(
        entorno,
        fila(2, "Depósito Central", "VA-750", "10", "1000"),
        fila(3, "Depósito Central", "CB-473", "10", "0"),
        fila(4, "Camión 1", "CB-473", "diez", "100"),
    )

    assert errores == [
        (3, "costo_unitario", "COSTO_INVALIDO"),
        (4, "cantidad_base", "CANTIDAD_INVALIDA"),
    ]
    assert entorno.movimientos_de_stock() == []
    assert entorno.importaciones() == []
    assert entorno.promedio(mundo.vino_id) is None


def test_doble_envio_con_el_mismo_operation_id_no_duplica_el_stock(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """INV-06."""
    operation_id = uuid4()
    filas = (fila(2, "Depósito Central", "VA-750", "60", "1000"),)

    primero = importar(entorno, *filas, operation_id=operation_id)
    segundo = importar(entorno, *filas, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert entorno.saldo_de_stock(mundo.vino_id, mundo.deposito_id) == 60
    assert len(entorno.movimientos_de_stock()) == 1
    assert len(entorno.importaciones()) == 1
    assert entorno.auditorias(operation_id) == 1


def test_el_momento_es_el_occurred_at_del_sobre_y_no_el_de_corte(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """D7-A: sin fecha de corte."""
    importar(entorno, fila(2, "Depósito Central", "VA-750", "60", "1000"))

    [movimiento] = entorno.movimientos_de_stock()

    assert movimiento.occurred_at == datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    assert movimiento.costo_unitario == Decimal("1000.000000")
