"""Tarea 10.1 (change 18a; spec `ventas/confirmacion-de-venta`, requisito "La venta confirmada
deja una sola fila de auditoría del comando"; `design.md` D20, ampliada el 2026-10-20; gobernanza
ALTA), contra PostgreSQL real.

La fila genérica del bus por cada `VENTA_CONFIRMAR` aceptado; con otra lista o una versión no
vigente lleva el motivo y una observación con la lista y la versión; con una ubicación tomada por
otra jornada (excepción de `LIBERAR_UBICACION`) lleva la constancia de STK-09; con ambas, los dos
textos separados por `; `. Un rechazo no deja fila ni motivo.

Reglas citadas: AUD-01, AUD-02, STK-09, SYN-04, PRC-21.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_ubicacion_sql
from ventas_confirmar_utiles import PERMISOS_DE_SUPERVISOR, PERMISOS_DE_VENTA, EntornoVenta

from app.core.errors import DomainError
from app.modules.identidad.models import Auditoria

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

AYER = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
HOY_TEMPRANO = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)
PERMISOS_DE_SUPERVISORA = PERMISOS_DE_SUPERVISOR | {"LIBERAR_UBICACION"}


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session, permisos=PERMISOS_DE_SUPERVISORA)


def _fila_unica(entorno: EntornoVenta, operation_id: UUID) -> Auditoria:
    entorno.sesion.rollback()
    (fila,) = entorno.auditoria_de(operation_id)
    return fila


def _nombre_de_general(entorno: EntornoVenta) -> str:
    """El nombre de la lista predeterminada (el entorno le agrega un sufijo aleatorio)."""
    return str(
        entorno.sesion.scalar(
            text("SELECT nombre FROM lista_precio WHERE organizacion_id = :o AND id = :l"),
            {"o": entorno.org, "l": entorno.lista_id},
        )
    )


def _con_version_nueva(entorno: EntornoVenta) -> UUID:
    """General con la versión 1 ($12.500, histórica) y la 2 vigente; devuelve la 1."""
    entorno.crear_version(entorno.lista_id, 2, HOY_TEMPRANO, precio_vino="13000.00")
    entorno.sesion.commit()
    return entorno.version_id


def _camioneta_tomada_por_otra_jornada(
    entorno: EntornoVenta, db_session: Session
) -> tuple[UUID, UUID]:
    """Camioneta 2 con 48 botellas, tomada por la jornada de Juan (otro usuario); devuelve
    `(camioneta_id, jornada_de_juan_id)`. El stock entra ANTES de la toma (STK-09)."""
    camioneta_id = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre="Camioneta 2", requiere_toma=True
    )
    entorno.comprar(entorno.vino_id, 48, "1050", ubicacion_id=camioneta_id)
    juan_id, juan_dispositivo_id = crear_usuario_y_dispositivo(
        db_session, entorno.org, permisos=PERMISOS_DE_VENTA
    )
    jornada_id = entorno.crear_jornada(
        usuario_id=juan_id, dispositivo_id=juan_dispositivo_id, ubicacion_id=camioneta_id
    )
    return camioneta_id, jornada_id


# --- la fila genérica (AUD-01) ------------------------------------------------------------------


def test_aud01_una_venta_comun_deja_una_fila_sin_motivo_ni_observacion(
    entorno: EntornoVenta,
) -> None:
    # Escenario: "Venta común"
    comando = entorno.vender()

    fila = _fila_unica(entorno, comando.operation_id)
    assert (fila.accion, fila.entidad, fila.origen) == ("VENTA_CONFIRMAR", "comando", "COMANDO")
    assert (fila.motivo_id, fila.observacion) == (None, None)


def test_aud01_elegir_lo_que_ya_corresponde_no_lleva_motivo_ni_observacion(
    entorno: EntornoVenta,
) -> None:
    comando = entorno.vender(
        lista_id=str(entorno.lista_id), lista_version_id=str(entorno.version_id)
    )

    fila = _fila_unica(entorno, comando.operation_id)
    assert (fila.motivo_id, fila.observacion) == (None, None)


# --- otra lista o versión no vigente (AUD-01, AUD-02, PRC-21) -----------------------------------


def test_aud02_otra_lista_deja_el_motivo_y_la_observacion_con_lista_y_version(
    entorno: EntornoVenta,
) -> None:
    # Escenario: "Otra lista o versión anterior"
    mayorista = entorno.crear_lista("Mayorista")
    version = entorno.crear_version(mayorista, 1, AYER, precio_vino="11000.00")
    entorno.sesion.commit()

    comando = entorno.vender(
        entorno.linea(precio="11000.00", version_id=version),
        lista_id=str(mayorista),
        motivo_lista_id=str(entorno.motivo_lista_id),
    )

    fila = _fila_unica(entorno, comando.operation_id)
    assert fila.motivo_id == entorno.motivo_lista_id
    assert fila.observacion == (
        'Lista "Mayorista", versión 1: lista distinta de la que le corresponde al cliente'
    )


def test_aud02_una_version_anterior_deja_el_motivo_y_la_observacion_con_lista_y_version(
    entorno: EntornoVenta,
) -> None:
    # Escenario: "Otra lista o versión anterior"
    v1 = _con_version_nueva(entorno)

    comando = entorno.vender(
        entorno.linea(precio="12500.00", version_id=v1),
        lista_id=str(entorno.lista_id),
        lista_version_id=str(v1),
        motivo_lista_id=str(entorno.motivo_lista_id),
    )

    fila = _fila_unica(entorno, comando.operation_id)
    assert fila.motivo_id == entorno.motivo_lista_id
    assert fila.observacion == (
        f'Lista "{_nombre_de_general(entorno)}", versión 1: versión no vigente'
    )


def test_aud02_otra_lista_y_version_no_vigente_nombra_las_dos_razones(
    entorno: EntornoVenta,
) -> None:
    mayorista = entorno.crear_lista("Mayorista")
    antigua = entorno.crear_version(mayorista, 1, AYER, precio_vino="11000.00")
    entorno.crear_version(mayorista, 2, HOY_TEMPRANO, precio_vino="11500.00")
    entorno.sesion.commit()

    comando = entorno.vender(
        entorno.linea(precio="11000.00", version_id=antigua),
        lista_id=str(mayorista),
        lista_version_id=str(antigua),
        motivo_lista_id=str(entorno.motivo_lista_id),
    )

    fila = _fila_unica(entorno, comando.operation_id)
    assert fila.observacion == (
        'Lista "Mayorista", versión 1: lista distinta de la que le corresponde al cliente '
        "y versión no vigente"
    )


def test_aud02_si_la_organizacion_no_exige_motivo_la_observacion_queda_igual(
    entorno: EntornoVenta,
) -> None:
    """Sin motivo (la organización no lo exige) la fila no lleva `motivo_id`, pero la
    observación sigue nombrando la lista y la versión usadas."""
    entorno.configurar(motivo_obligatorio_lista=False)
    v1 = _con_version_nueva(entorno)

    comando = entorno.vender(
        entorno.linea(precio="12500.00", version_id=v1),
        lista_id=str(entorno.lista_id),
        lista_version_id=str(v1),
    )

    fila = _fila_unica(entorno, comando.operation_id)
    assert fila.motivo_id is None
    assert fila.observacion == (
        f'Lista "{_nombre_de_general(entorno)}", versión 1: versión no vigente'
    )


# --- ubicación tomada por otra jornada (AUD-02, STK-09) -----------------------------------------


def test_stk09_la_venta_desde_una_ubicacion_tomada_deja_la_constancia(
    entorno: EntornoVenta, db_session: Session
) -> None:
    camioneta_id, jornada_de_juan = _camioneta_tomada_por_otra_jornada(entorno, db_session)

    comando = entorno.vender(ubicacion_id=str(camioneta_id))

    fila = _fila_unica(entorno, comando.operation_id)
    assert fila.motivo_id is None
    assert fila.observacion == f"ubicación tomada por la jornada {jornada_de_juan}"
    (movimiento,) = entorno.movimientos_de_stock()
    assert movimiento.jornada_id is None


def test_stk09_una_venta_desde_una_ubicacion_libre_no_lleva_constancia(
    entorno: EntornoVenta, db_session: Session
) -> None:
    _camioneta_tomada_por_otra_jornada(entorno, db_session)

    comando = entorno.vender(ubicacion_id=str(entorno.deposito_id))

    assert _fila_unica(entorno, comando.operation_id).observacion is None


def test_aud02_lista_no_vigente_y_ubicacion_tomada_llevan_los_dos_textos(
    entorno: EntornoVenta, db_session: Session
) -> None:
    # Escenario: "Las dos cosas a la vez"
    camioneta_id, jornada_de_juan = _camioneta_tomada_por_otra_jornada(entorno, db_session)
    v1 = _con_version_nueva(entorno)

    comando = entorno.vender(
        entorno.linea(precio="12500.00", version_id=v1),
        ubicacion_id=str(camioneta_id),
        lista_id=str(entorno.lista_id),
        lista_version_id=str(v1),
        motivo_lista_id=str(entorno.motivo_lista_id),
    )

    fila = _fila_unica(entorno, comando.operation_id)
    assert fila.motivo_id == entorno.motivo_lista_id
    assert fila.observacion == (
        f'Lista "{_nombre_de_general(entorno)}", versión 1: versión no vigente; '
        f"ubicación tomada por la jornada {jornada_de_juan}"
    )


# --- un rechazo no deja motivo ni observación (AUD-01, SYN-04) ----------------------------------


def test_syn04_una_venta_rechazada_con_otra_lista_no_deja_fila_ni_motivo(
    entorno: EntornoVenta,
) -> None:
    # Escenario: "Venta rechazada"
    mayorista = entorno.crear_lista("Mayorista")
    version = entorno.crear_version(mayorista, 1, AYER, precio_vino="11000.00")
    entorno.sesion.commit()
    operation_id = UUID(int=7)

    with pytest.raises(DomainError) as error:
        entorno.enviar(
            entorno.contenido(
                entorno.linea(precio="11000.00", version_id=version),
                lista_id=str(mayorista),
                motivo_lista_id=str(entorno.motivo_lista_id),
                total="1.00",
            ),
            operation_id=operation_id,
        )

    assert error.value.codigo == "PRECIO_DIFIERE"
    entorno.sesion.rollback()
    assert entorno.auditoria_de(operation_id) == []
    assert entorno.ventas() == []


def test_syn04_una_venta_rechazada_desde_una_ubicacion_tomada_no_deja_constancia(
    db_session: Session,
) -> None:
    """Sin `LIBERAR_UBICACION` la venta desde la ubicación tomada se rechaza: ni fila ni
    constancia."""
    entorno = EntornoVenta(db_session, permisos=PERMISOS_DE_VENTA)
    camioneta_id, _ = _camioneta_tomada_por_otra_jornada(entorno, db_session)
    operation_id = UUID(int=8)

    with pytest.raises(DomainError) as error:
        entorno.enviar(entorno.contenido(ubicacion_id=str(camioneta_id)), operation_id=operation_id)

    assert error.value.codigo == "UBICACION_TOMADA"
    entorno.sesion.rollback()
    assert entorno.auditoria_de(operation_id) == []
