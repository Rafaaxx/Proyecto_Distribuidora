"""Tareas 8.1, 8.3, 8.6, 8.7: siembra idempotente de la organización inicial
(`design.md` D4, `docs/01-dominio.md` §4).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.configuracion import service as configuracion_service
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad import service as identidad_service
from app.seed import BaseSinMigrarError, sembrar

RELOJ = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))


def test_sembrar_crea_la_organizacion_inicial_con_los_valores_de_01_parrafo_4(
    db_session: Session,
) -> None:
    organizacion = sembrar(db_session, RELOJ)

    assert organizacion is not None
    assert organizacion.moneda == "ARS"
    assert organizacion.zona_horaria == "America/Argentina/Mendoza"
    assert organizacion.estado == "ACTIVA"

    configuracion = identidad_service.obtener_configuracion(organizacion.id, db_session)
    assert configuracion is not None
    assert configuracion.modo_impositivo == "A"
    assert configuracion.politica_credito_default == "AUTORIZAR"
    assert configuracion.descuento_manual_habilitado is True
    assert configuracion.motivo_obligatorio_lista is True
    assert configuracion.estado_facturacion_default == "NO_REQUIERE"
    assert configuracion.intentos_pin_max == 5


def test_los_parametros_a_definir_al_configurar_quedan_explicitamente_nulos(
    db_session: Session,
) -> None:
    """Escenario 'Un parámetro sin valor definido queda explícitamente sin
    definir' (tarea 8.3): no se inventan valores por omisión."""
    organizacion = sembrar(db_session, RELOJ)
    assert organizacion is not None

    configuracion = identidad_service.obtener_configuracion(organizacion.id, db_session)
    assert configuracion is not None
    assert configuracion.tolerancia_offline_tipo is None
    assert configuracion.tolerancia_offline_valor is None
    assert configuracion.motivo_obligatorio_descuento is None
    assert configuracion.redondeo_multiplo is None
    assert configuracion.redondeo_direccion is None
    assert configuracion.permite_consumidor_final is None
    assert configuracion.modalidad_iva_default is None
    # Tarea 8.4 (design.md D3): sin tabla destino todavía.
    assert configuracion.lista_precio_default_id is None
    assert configuracion.cliente_consumidor_final_id is None


def test_sembrar_dos_veces_no_duplica_ni_pisa(db_session: Session) -> None:
    """Escenario 'Sembrar dos veces no duplica ni pisa' (tarea 8.6)."""
    organizacion = sembrar(db_session, RELOJ)
    assert organizacion is not None

    identidad_repository.actualizar_configuracion(
        organizacion.id, db_session, momento=RELOJ.now(), politica_credito_default="BLOQUEAR"
    )
    db_session.flush()

    resultado_segunda_siembra = sembrar(db_session, RELOJ)

    total_organizaciones = db_session.execute(
        text("SELECT COUNT(*) FROM organizacion")
    ).scalar_one()
    assert total_organizaciones == 1
    assert resultado_segunda_siembra is None

    configuracion = identidad_service.obtener_configuracion(organizacion.id, db_session)
    assert configuracion is not None
    assert configuracion.politica_credito_default == "BLOQUEAR"


def test_sembrar_sobre_una_base_sin_migrar_falla_explicitamente(db_session: Session) -> None:
    """Escenario 'Sembrar sobre una base sin migrar falla explícitamente'
    (tarea 8.1)."""
    db_session.execute(text("DROP TABLE motivo, medio_pago, alicuota_iva CASCADE"))
    db_session.execute(text("DROP TABLE configuracion_organizacion, organizacion CASCADE"))
    db_session.flush()

    with pytest.raises(BaseSinMigrarError):
        sembrar(db_session, RELOJ)


def test_los_seis_motivos_de_ajuste_stock_se_listan_por_ambito_y_ninguno_de_otro_ambito(
    db_session: Session,
) -> None:
    """Escenario 'Los motivos se listan por ámbito' (tarea 8.7)."""
    organizacion = sembrar(db_session, RELOJ)
    assert organizacion is not None

    motivos = configuracion_service.listar_motivos_por_ambito(
        organizacion.id, db_session, "AJUSTE_STOCK"
    )

    assert len(motivos) == 6
    assert {motivo.nombre for motivo in motivos} == {
        "Rotura",
        "Vencimiento",
        "Muestra",
        "Consumo interno",
        "Diferencia de inventario",
        "Otro",
    }
    assert all(motivo.ambito == "AJUSTE_STOCK" for motivo in motivos)

    motivos_de_otro_ambito = configuracion_service.listar_motivos_por_ambito(
        organizacion.id, db_session, "ANULACION_VENTA"
    )
    assert motivos_de_otro_ambito == []


def test_un_elemento_desactivado_deja_de_ofrecerse_pero_sigue_legible_por_id(
    db_session: Session,
) -> None:
    """Escenario 'Un elemento desactivado deja de ofrecerse' (tarea 8.7)."""
    organizacion = sembrar(db_session, RELOJ)
    assert organizacion is not None
    motivos = configuracion_service.listar_motivos_por_ambito(
        organizacion.id, db_session, "AJUSTE_STOCK"
    )
    motivo_a_desactivar = motivos[0]

    configuracion_service.desactivar_motivo(
        organizacion.id, db_session, RELOJ, motivo_a_desactivar.id
    )

    activos = configuracion_service.listar_motivos_activos(organizacion.id, db_session)
    assert motivo_a_desactivar.id not in {motivo.id for motivo in activos}

    from app.modules.configuracion import repository as configuracion_repository

    todavia_legible = configuracion_repository.obtener_motivo_por_id(
        organizacion.id, db_session, motivo_a_desactivar.id
    )
    assert todavia_legible is not None
    assert todavia_legible.activo is False


def test_las_tres_alicuotas_y_cinco_medios_de_pago_iniciales(db_session: Session) -> None:
    from decimal import Decimal

    organizacion = sembrar(db_session, RELOJ)
    assert organizacion is not None

    alicuotas = configuracion_service.listar_alicuotas_activas(organizacion.id, db_session)
    valores = {(a.nombre, a.valor) for a in alicuotas}
    assert valores == {
        ("21%", Decimal("0.210000")),
        ("10,5%", Decimal("0.105000")),
        ("0%", Decimal("0.000000")),
    }

    medios = configuracion_service.listar_medios_pago_activos(organizacion.id, db_session)
    assert {m.nombre for m in medios} == {
        "Efectivo",
        "Transferencia",
        "Cheque",
        "Billetera",
        "Tarjeta",
    }
