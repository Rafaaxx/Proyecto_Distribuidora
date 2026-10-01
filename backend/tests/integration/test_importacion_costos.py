"""Tarea 6.2 (change 10): importación de costos informados por `IMPORTACION_REGISTRAR`,
contra PostgreSQL real (`specs/importacion/importacion-de-maestros`, `design.md` D4, D8).

Cada fila se registra por `proveedores.service.informar_costos` (lote de una fila, con el
proveedor actual del producto, CAT-06): costo base derivado según CST-02, sin sobrescribir
costos anteriores (CST-03), con presentación de compra activa del producto, y la
presentación queda congelada (INV-18). Los ejemplos de CST-02 son los de `01` §6.1.

Reglas citadas: CST-01, CST-02, CST-03, CAT-04, CAT-06, INV-01, INV-03, INV-06, INV-18,
INV-21, TR-02.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from importacion_utiles import RELOJ, EntornoDeImportacion, contenido, errores_de, fila_de
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import UnidadesCongeladasError
from app.modules.catalogo.domain.presentaciones import DatosPresentacion
from app.modules.importacion.domain.errores import ImportacionConErroresError
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

TIPO = "COSTOS"


def fila(numero: int, **cambios: str) -> dict[str, object]:
    valores = {
        "producto_codigo": "CB-473",
        "presentacion": "Caja x12",
        "valor": "18000",
        "incluye_iva": "N",
        "bonificacion": "",
        "vigencia_desde": "2026-10-01",
        "observacion": "",
    }
    valores.update(cambios)
    return fila_de(numero, valores)


class Mundo:
    """El entorno más Cerveza B (`CB-473`, IVA 21%, proveedor Bodega Sur) con su "Caja
    x12" de compra y una "Lata" de referencia solo de venta."""

    def __init__(self, entorno: EntornoDeImportacion) -> None:
        self.entorno = entorno
        categoria_id = entorno.categoria("Cervezas")
        self.alicuota_id = entorno.alicuota("21")
        self.proveedor_id = entorno.proveedor("Bodega Sur")
        self.producto_id = entorno.producto(
            "CB-473",
            [
                DatosPresentacion("Lata", 1, True, False, True),
                DatosPresentacion("Caja x12", 12, True, True, False),
            ],
            nombre="Cerveza B",
            categoria_id=categoria_id,
            proveedor_id=self.proveedor_id,
            alicuota_id=self.alicuota_id,
        )


@pytest.fixture
def entorno(db_session: Session) -> EntornoDeImportacion:
    return EntornoDeImportacion(db_session)


@pytest.fixture
def mundo(entorno: EntornoDeImportacion) -> Mundo:
    return Mundo(entorno)


def importar(entorno: EntornoDeImportacion, *filas: dict[str, object]) -> Comando:
    return entorno.enviar(contenido(TIPO, list(filas), "costos.csv"))


def fallar(
    entorno: EntornoDeImportacion, *filas: dict[str, object]
) -> list[tuple[int, str | None, str]]:
    with pytest.raises(ImportacionConErroresError) as excinfo:
        importar(entorno, *filas)
    return errores_de(excinfo.value)


# --- escenarios de CST-02 (`01` §6.1) ------------------------------------------------


def test_costo_por_caja_sin_iva_da_costo_base_1500(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """Escenario "Costo por caja sin IVA" (CST-01, CST-02)."""
    comando = importar(entorno, fila(2))

    assert comando.resultado is not None
    assert (comando.resultado["filas_total"], comando.resultado["filas_ok"]) == (1, 1)
    [costo] = entorno.costos()
    assert str(costo.costo_base) == "1500.000000"
    assert (costo.producto_id, costo.proveedor_id) == (mundo.producto_id, mundo.proveedor_id)
    assert (costo.valor, costo.incluye_iva, costo.bonificacion) == (
        Decimal("18000.00"),
        False,
        Decimal("0"),
    )
    assert costo.vigencia_desde == date(2026, 10, 1)
    assert costo.operation_id == comando.operation_id
    [importacion] = entorno.importaciones()
    assert (importacion.tipo, importacion.filas_total, importacion.filas_ok) == (TIPO, 1, 1)


def test_costo_con_iva_incluido_da_costo_base_1239_669421(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """Escenario "Costo con IVA incluido" (CST-02): el IVA de la alícuota del producto."""
    importar(entorno, fila(2, incluye_iva="S"))

    [costo] = entorno.costos()
    assert str(costo.costo_base) == "1239.669421"
    assert str(costo.alicuota_aplicada) == "0.210000"
    assert costo.incluye_iva is True


def test_costo_con_bonificacion_10_da_costo_base_1350(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """Escenario "Costo con bonificación" (CST-02, TR-02): `10` es el 10%."""
    importar(entorno, fila(2, bonificacion="10"))

    [costo] = entorno.costos()
    assert str(costo.costo_base) == "1350.000000"
    assert str(costo.bonificacion) == "0.100000"


def test_producto_y_presentacion_se_resuelven_por_clave_natural(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """D4: producto por código y presentación por nombre dentro del producto, sin
    distinguir mayúsculas ni espacios al borde; el importe admite coma decimal."""
    importar(
        entorno,
        fila(2, producto_codigo=" cb-473 ", presentacion=" CAJA X12 ", valor="18000,50"),
    )

    [costo] = entorno.costos()
    assert costo.valor == Decimal("18000.50")
    assert str(costo.costo_base) == "1500.041667"


def test_varias_filas_de_distintas_vigencias_no_se_sobrescriben(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """CST-03: el costo anterior queda."""
    importar(entorno, fila(2))

    importar(entorno, fila(2, valor="21600", vigencia_desde="01/11/2026", observacion="Aumento"))

    primero, segundo = entorno.costos()
    assert (str(primero.costo_base), primero.vigencia_desde) == ("1500.000000", date(2026, 10, 1))
    assert (str(segundo.costo_base), segundo.vigencia_desde) == ("1800.000000", date(2026, 11, 1))
    assert segundo.observacion == "Aumento"


# --- errores del servicio traducidos a su fila y columna --------------------------------


def test_presentacion_que_no_es_de_compra_da_presentacion_invalida(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """Escenario "Presentación que no es de compra" (CST-01): la "Lata" solo se vende."""
    errores = fallar(entorno, fila(2), fila(3, presentacion="Lata", vigencia_desde="2026-11-01"))

    assert errores == [(3, "presentacion", "PRESENTACION_INVALIDA")]
    assert entorno.costos() == []


def test_el_error_de_informar_costos_cae_en_la_fila_correcta_y_no_en_la_primera(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """El servicio informa el índice dentro del lote; con una fila por lote el índice es
    0, pero el informe señala la fila de la planilla (la 5)."""
    errores = fallar(
        entorno,
        fila(2),
        fila(3, vigencia_desde="2026-11-01"),
        fila(4, vigencia_desde="2026-12-01"),
        fila(5, presentacion="Lata"),
    )

    assert errores == [(5, "presentacion", "PRESENTACION_INVALIDA")]


@pytest.mark.parametrize(
    ("cambios", "esperado"),
    [
        ({"valor": "0"}, (2, "valor", "VALOR_INVALIDO")),
        ({"valor": "100,555"}, (2, "valor", "VALOR_INVALIDO")),
        ({"bonificacion": "100"}, (2, "bonificacion", "BONIFICACION_INVALIDA")),
        ({"bonificacion": "-5"}, (2, "bonificacion", "BONIFICACION_INVALIDA")),
        ({"valor": "18.000"}, (2, "valor", "NUMERO_INVALIDO")),
        ({"incluye_iva": "tal vez"}, (2, "incluye_iva", "VALOR_INVALIDO")),
        ({"vigencia_desde": "mañana"}, (2, "vigencia_desde", "FECHA_INVALIDA")),
        ({"bonificacion": "diez"}, (2, "bonificacion", "NUMERO_INVALIDO")),
    ],
)
def test_valores_fuera_de_regla_o_ilegibles_dan_su_error_de_fila_y_columna(
    entorno: EntornoDeImportacion,
    mundo: Mundo,
    cambios: dict[str, str],
    esperado: tuple[int, str, str],
) -> None:
    assert fallar(entorno, fila(2, **cambios)) == [esperado]
    assert entorno.costos() == []


def test_producto_inexistente_es_referencia_no_encontrada_en_cada_fila(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    errores = fallar(entorno, fila(2, producto_codigo="ZZ-1"), fila(3, producto_codigo="XX-9"))

    assert errores == [
        (2, "producto_codigo", "REFERENCIA_NO_ENCONTRADA"),
        (3, "producto_codigo", "REFERENCIA_NO_ENCONTRADA"),
    ]


def test_producto_que_existe_solo_en_otra_organizacion_no_se_ve(
    entorno: EntornoDeImportacion, db_session: Session
) -> None:
    ajena = EntornoDeImportacion(db_session)
    Mundo(ajena)  # `CB-473` solo existe en la otra organización

    assert fallar(entorno, fila(2)) == [(2, "producto_codigo", "REFERENCIA_NO_ENCONTRADA")]
    assert ajena.costos() == []


def test_presentacion_inexistente_en_el_producto_es_referencia_no_encontrada(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    errores = fallar(entorno, fila(2, presentacion="Pallet"))

    assert errores == [(2, "presentacion", "REFERENCIA_NO_ENCONTRADA")]


def test_producto_inactivo_da_producto_inactivo(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    entorno.sesion.execute(
        text("UPDATE producto SET activo = false WHERE id = :id"), {"id": mundo.producto_id}
    )
    entorno.sesion.commit()

    assert fallar(entorno, fila(2)) == [(2, "producto_codigo", "PRODUCTO_INACTIVO")]


def test_proveedor_inactivo_da_proveedor_inactivo(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    entorno.sesion.execute(
        text("UPDATE proveedor SET activo = false WHERE id = :id"), {"id": mundo.proveedor_id}
    )
    entorno.sesion.commit()

    assert fallar(entorno, fila(2)) == [(2, "producto_codigo", "PROVEEDOR_INACTIVO")]


# --- duplicados dentro del archivo, todo o nada y registro ---------------------------------


def test_la_misma_clave_dentro_del_archivo_da_fila_duplicada_en_la_segunda(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """Misma regla que el lote de `COSTO_INFORMAR`: producto, presentación y vigencia."""
    errores = fallar(
        entorno,
        fila(2),
        fila(3, valor="19000", vigencia_desde="01/10/2026"),
        fila(4, vigencia_desde="2026-11-01"),
    )

    assert errores == [(3, "producto_codigo", "FILA_DUPLICADA")]
    assert entorno.costos() == []


def test_una_fila_mala_impide_importar_las_buenas(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """INV-01."""
    errores = fallar(
        entorno,
        fila(2),
        fila(3, vigencia_desde="2026-11-01", valor="0"),
        fila(4, vigencia_desde="2026-12-01", presentacion="Pallet"),
    )

    assert errores == [
        (3, "valor", "VALOR_INVALIDO"),
        (4, "presentacion", "REFERENCIA_NO_ENCONTRADA"),
    ]
    assert entorno.costos() == []
    assert entorno.importaciones() == []


def test_doble_envio_con_el_mismo_operation_id_no_duplica_costos(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """INV-06."""
    operation_id = uuid4()
    cuerpo = contenido(TIPO, [fila(2), fila(3, vigencia_desde="2026-11-01")], "costos.csv")

    primero = entorno.enviar(cuerpo, operation_id=operation_id)
    segundo = entorno.enviar(cuerpo, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(entorno.costos()) == 2
    assert len(entorno.importaciones()) == 1
    assert entorno.auditorias(operation_id) == 1


# --- INV-18: la presentación con costo queda congelada ---------------------------------


def test_la_presentacion_con_costo_importado_queda_congelada(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """Escenario "La presentación con costo queda congelada" (CAT-04, INV-18)."""
    importar(entorno, fila(2))
    caja = next(
        p
        for p in catalogo_service.listar_presentaciones_de_producto(
            entorno.org, mundo.producto_id, entorno.sesion
        )
        if p.nombre == "Caja x12"
    )

    with pytest.raises(UnidadesCongeladasError):
        catalogo_service.modificar_presentacion(
            entorno.org,
            entorno.sesion,
            RELOJ,
            presentacion_id=caja.id,
            nombre="Caja x12",
            unidades_base=24,
            usar_en_venta=caja.usar_en_venta,
            usar_en_compra=caja.usar_en_compra,
            activo=True,
            actor_id=None,
        )


def test_una_presentacion_sin_costo_si_puede_cambiar_de_unidades(
    entorno: EntornoDeImportacion, mundo: Mundo
) -> None:
    """Contraste de INV-18: sin costo importado no hay congelamiento."""
    caja = next(
        p
        for p in catalogo_service.listar_presentaciones_de_producto(
            entorno.org, mundo.producto_id, entorno.sesion
        )
        if p.nombre == "Caja x12"
    )

    cambiada = catalogo_service.modificar_presentacion(
        entorno.org,
        entorno.sesion,
        RELOJ,
        presentacion_id=caja.id,
        nombre="Caja x12",
        unidades_base=24,
        usar_en_venta=caja.usar_en_venta,
        usar_en_compra=caja.usar_en_compra,
        activo=True,
        actor_id=None,
    )

    assert cambiada.unidades_base == 24
