"""Change 15, tarea 8.3: STK-09 en la compra, su anulación y la importación de stock inicial, por
el bus contra PostgreSQL real (spec `stock/toma-de-ubicacion`, requisito "La regla de toma
alcanza a todo camino que mueve stock", escenarios de compra y de importación; `design.md` D7).

Los comandos de `stock` están en `test_stock_comandos_con_toma.py` (tarea 8.2). La constancia de
la excepción en la auditoría es de la tarea 8.5.

Reglas citadas: STK-09, CMP-03, IMP-01, IMP-02, INV-01.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from compras_utiles import Entorno as EntornoDeCompras
from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from importacion_utiles import EntornoDeImportacion, contenido, errores_de, fila_de
from sqlalchemy import select
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

from app.modules.catalogo.domain.presentaciones import DatosPresentacion
from app.modules.identidad.models import Auditoria
from app.modules.importacion.domain.errores import ImportacionConErroresError
from app.modules.proveedores.models import Compra
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import UbicacionTomadaError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

ADMINISTRACION = frozenset({"REGISTRAR_COMPRA", "ANULAR_COMPRA"})
ADMINISTRADOR = ADMINISTRACION | {"LIBERAR_UBICACION"}


def _tomar(entorno: Any, ubicacion_id: UUID, *, estado: str = "ABIERTA") -> UUID:
    """La jornada de Juan (otro usuario, otro dispositivo) sobre `ubicacion_id`."""
    juan, telefono = crear_usuario_y_dispositivo(
        entorno.sesion, entorno.org, permisos=frozenset({"ABRIR_JORNADA"})
    )
    jornada_id = crear_jornada_sql(
        entorno.sesion,
        entorno.org,
        usuario_id=juan,
        dispositivo_id=telefono,
        ubicacion_id=ubicacion_id,
        estado=estado,
    )
    entorno.sesion.commit()
    return jornada_id


def _saldo_en(entorno: EntornoDeCompras, ubicacion_id: UUID) -> int:
    entorno.sesion.rollback()
    return stock_service.obtener_saldo(
        entorno.org, entorno.sesion, producto_id=entorno.vino_id, ubicacion_id=ubicacion_id
    )


def _camioneta(entorno: Any) -> UUID:
    ubicacion_id = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
    )
    entorno.sesion.commit()
    return ubicacion_id


# --- compras -------------------------------------------------------------------------------------


def test_stk09_cmp03_una_compra_a_un_vehiculo_tomado_se_rechaza_sin_efectos(
    db_session: Session,
) -> None:
    """Escenario "Compra con destino a un vehículo tomado": sin compra, sin movimiento de
    stock, sin cambio de promedio y sin movimiento en la cuenta del proveedor (INV-01)."""
    entorno = EntornoDeCompras(db_session, permisos=ADMINISTRACION)
    camioneta = _camioneta(entorno)
    _tomar(entorno, camioneta)

    with pytest.raises(UbicacionTomadaError) as error:
        entorno.enviar(entorno.contenido(ubicacion_id=str(camioneta)))

    assert error.value.codigo == "UBICACION_TOMADA"
    entorno.sin_efectos()
    assert entorno.promedio(entorno.vino_id) is None


def test_stk09_el_administrador_registra_la_misma_compra(db_session: Session) -> None:
    """Escenario "El Administrador registra la misma compra": se acepta y el movimiento queda
    sin jornada."""
    entorno = EntornoDeCompras(db_session, permisos=ADMINISTRADOR)
    camioneta = _camioneta(entorno)
    _tomar(entorno, camioneta)

    comando = entorno.enviar(entorno.contenido(ubicacion_id=str(camioneta)))

    assert comando.estado == "ACEPTADO"
    assert len(entorno.compras()) == 1
    assert {m.jornada_id for m in entorno.movimientos_de_stock()} == {None}
    assert _saldo_en(entorno, camioneta) == 60


def test_una_compra_a_un_vehiculo_sin_jornada_o_con_la_jornada_cerrada_se_acepta(
    db_session: Session,
) -> None:
    """La regla es sobre "tomada": vehículo sin jornada o con jornada terminada, libre."""
    entorno = EntornoDeCompras(db_session, permisos=ADMINISTRACION)
    libre = _camioneta(entorno)
    cerrada = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre="Camioneta 2", tipo="VEHICULO", requiere_toma=True
    )
    _tomar(entorno, cerrada, estado="CERRADA")

    assert entorno.enviar(entorno.contenido(ubicacion_id=str(libre))).estado == "ACEPTADO"
    assert entorno.enviar(entorno.contenido(ubicacion_id=str(cerrada))).estado == "ACEPTADO"


def test_stk09_anular_una_compra_cuyo_destino_quedo_tomado(db_session: Session) -> None:
    """Anulación de una compra cuyo destino quedó tomado: sin la excepción se rechaza y la
    compra sigue confirmada; con ella se acepta."""
    entorno = EntornoDeCompras(db_session, permisos=ADMINISTRACION)
    camioneta = _camioneta(entorno)
    compra = entorno.enviar(entorno.contenido(ubicacion_id=str(camioneta)))
    assert compra.resultado is not None
    compra_id = UUID(str(compra.resultado["compra_id"]))
    _tomar(entorno, camioneta)

    with pytest.raises(UbicacionTomadaError):
        entorno.anular(compra_id)

    db_session.rollback()
    assert db_session.scalars(select(Compra.estado)).one() == "CONFIRMADA"
    assert _saldo_en(entorno, camioneta) == 60


def test_stk09_el_administrador_anula_la_compra_de_un_destino_tomado(db_session: Session) -> None:
    entorno = EntornoDeCompras(db_session, permisos=ADMINISTRADOR)
    camioneta = _camioneta(entorno)
    compra = entorno.enviar(entorno.contenido(ubicacion_id=str(camioneta)))
    assert compra.resultado is not None
    _tomar(entorno, camioneta)

    anulacion = entorno.anular(UUID(str(compra.resultado["compra_id"])))

    assert anulacion.estado in {"ACEPTADO", "ACEPTADO_CON_OBSERVACIONES"}
    db_session.rollback()
    assert db_session.scalars(select(Compra.estado)).one() == "ANULADA"
    assert _saldo_en(entorno, camioneta) == 0


# --- importación de stock inicial ----------------------------------------------------------------


class Mundo:
    """Vino A sin movimientos, un depósito y "Camión 1" (vehículo con toma) tomado por otro
    usuario."""

    def __init__(self, entorno: EntornoDeImportacion) -> None:
        self.entorno = entorno
        self.vino_id = entorno.producto(
            "VA-750",
            [DatosPresentacion("Botella", 1, True, True, True)],
            nombre="Vino A",
            categoria_id=entorno.categoria("Vinos"),
            proveedor_id=entorno.proveedor("Bodega Sur"),
            alicuota_id=entorno.alicuota("21"),
        )
        self.deposito_id = entorno.ubicacion("Depósito Central")
        self.vehiculo_id = entorno.ubicacion("Camión 1", tipo="VEHICULO")
        self.jornada_id = _tomar(entorno, self.vehiculo_id)


def _fila(numero: int, ubicacion: str) -> dict[str, object]:
    return fila_de(
        numero,
        {
            "ubicacion": ubicacion,
            "producto_codigo": "VA-750",
            "cantidad_base": "60",
            "costo_unitario": "1000",
        },
    )


def test_stk09_imp01_la_importacion_con_una_fila_sobre_un_vehiculo_tomado_se_rechaza_entera(
    db_session: Session,
) -> None:
    """Escenario "Importación de stock inicial con una fila sobre un vehículo tomado": se
    rechaza entera y el informe señala la fila con `UBICACION_TOMADA` (IMP-01, IMP-02)."""
    entorno = EntornoDeImportacion(db_session)
    mundo = Mundo(entorno)

    with pytest.raises(ImportacionConErroresError) as error:
        entorno.enviar(
            contenido(
                "STOCK_INICIAL",
                [_fila(2, "Depósito Central"), _fila(3, "Camión 1")],
                "stock.csv",
            )
        )

    assert [(fila, codigo) for fila, _columna, codigo in errores_de(error.value)] == [
        (3, "UBICACION_TOMADA")
    ]
    assert entorno.movimientos_de_stock(mundo.vino_id) == []
    assert entorno.importaciones() == []
    assert entorno.saldo_de_stock(mundo.vino_id, mundo.deposito_id) == 0


def test_stk09_la_importacion_de_quien_tiene_liberar_ubicacion_entra_sin_jornada(
    db_session: Session,
) -> None:
    entorno = EntornoDeImportacion(
        db_session, permisos=frozenset({"IMPORTAR_DATOS", "LIBERAR_UBICACION"})
    )
    mundo = Mundo(entorno)

    comando = entorno.enviar(
        contenido("STOCK_INICIAL", [_fila(2, "Camión 1")], "stock.csv"), operation_id=uuid4()
    )

    assert comando.estado == "ACEPTADO"
    assert entorno.saldo_de_stock(mundo.vino_id, mundo.vehiculo_id) == 60
    assert {m.jornada_id for m in entorno.movimientos_de_stock(mundo.vino_id)} == {None}
    assert entorno.promedio(mundo.vino_id) == Decimal("1000.000000")


# --- constancia de la excepción en la auditoría (tarea 8.5, D8; AUD-02) ---


def _observaciones(entorno: Any, operation_id: UUID) -> list[str | None]:
    entorno.sesion.rollback()
    return list(
        entorno.sesion.scalars(
            select(Auditoria.observacion).where(
                Auditoria.organizacion_id == entorno.org, Auditoria.operation_id == operation_id
            )
        ).all()
    )


def test_aud02_la_compra_y_su_anulacion_por_excepcion_dejan_la_constancia(
    db_session: Session,
) -> None:
    entorno = EntornoDeCompras(db_session, permisos=ADMINISTRADOR)
    camioneta = _camioneta(entorno)
    jornada_id = _tomar(entorno, camioneta)
    esperado = f"ubicación tomada por la jornada {jornada_id}"

    compra = entorno.enviar(entorno.contenido(ubicacion_id=str(camioneta)))
    assert compra.resultado is not None
    anulacion = entorno.anular(UUID(str(compra.resultado["compra_id"])))

    assert _observaciones(entorno, compra.operation_id) == [esperado]
    assert _observaciones(entorno, anulacion.operation_id) == [esperado]


def test_aud02_la_compra_a_un_destino_libre_no_lleva_constancia(db_session: Session) -> None:
    entorno = EntornoDeCompras(db_session, permisos=ADMINISTRADOR)
    camioneta = _camioneta(entorno)

    compra = entorno.enviar(entorno.contenido(ubicacion_id=str(camioneta)))
    anulacion = entorno.anular(UUID(str(compra.resultado["compra_id"])))  # type: ignore[index]

    assert _observaciones(entorno, compra.operation_id) == [None]
    assert _observaciones(entorno, anulacion.operation_id) == [None]


def test_aud02_la_importacion_por_excepcion_deja_la_constancia(db_session: Session) -> None:
    entorno = EntornoDeImportacion(
        db_session, permisos=frozenset({"IMPORTAR_DATOS", "LIBERAR_UBICACION"})
    )
    mundo = Mundo(entorno)
    operation_id = uuid4()

    entorno.enviar(
        contenido("STOCK_INICIAL", [_fila(2, "Camión 1")], "stock.csv"), operation_id=operation_id
    )

    assert _observaciones(entorno, operation_id) == [
        f"ubicación tomada por la jornada {mundo.jornada_id}"
    ]


def test_aud02_la_importacion_sin_excepcion_no_lleva_constancia(db_session: Session) -> None:
    entorno = EntornoDeImportacion(db_session)
    Mundo(entorno)
    operation_id = uuid4()

    entorno.enviar(
        contenido("STOCK_INICIAL", [_fila(2, "Depósito Central")], "stock.csv"),
        operation_id=operation_id,
    )

    assert _observaciones(entorno, operation_id) == [None]
