"""Tareas 8.1, 8.3, 8.6, 8.7: siembra idempotente de la organización inicial
(`design.md` D4, `docs/01-dominio.md` §4).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.seguridad import verificar_password
from app.modules.configuracion import service as configuracion_service
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.permisos import ADMINISTRADOR, PLANTILLAS_DE_ROL
from app.modules.identidad.domain.valores import computa_credito_fiscal
from app.seed import AdminPasswordNoDefinidaError, BaseSinMigrarError, sembrar

RELOJ = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
PASSWORD_ADMIN_DE_PRUEBA = "una-contrasena-larga-123"


def test_sembrar_crea_la_organizacion_inicial_con_los_valores_de_01_parrafo_4(
    db_session: Session,
) -> None:
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)

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


def test_la_organizacion_inicial_nace_monotributista_en_modo_a_sin_modalidad(
    db_session: Session,
) -> None:
    """D9, `00` §5: la siembra de una organización nueva usa `MONOTRIBUTO`; la
    modalidad de IVA al facturar no existe para un monotributista (D2). CST-06."""
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
    assert organizacion is not None

    configuracion = identidad_service.obtener_configuracion(organizacion.id, db_session)
    assert configuracion is not None
    assert configuracion.condicion_iva == "MONOTRIBUTO"
    assert configuracion.modo_impositivo == "A"
    assert configuracion.modalidad_iva_default is None
    condicion = identidad_service.obtener_condicion_iva(organizacion.id, db_session)
    assert condicion == "MONOTRIBUTO"
    assert computa_credito_fiscal(condicion) is False


def test_resembrar_no_pisa_una_condicion_cambiada(db_session: Session) -> None:
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
    assert organizacion is not None
    identidad_repository.actualizar_configuracion(
        organizacion.id, db_session, momento=RELOJ.now(), condicion_iva="RESPONSABLE_INSCRIPTO"
    )
    db_session.flush()

    segunda = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)

    assert segunda is None
    configuracion = identidad_service.obtener_configuracion(organizacion.id, db_session)
    assert configuracion is not None
    assert configuracion.condicion_iva == "RESPONSABLE_INSCRIPTO"


def test_los_parametros_a_definir_al_configurar_quedan_explicitamente_nulos(
    db_session: Session,
) -> None:
    """Escenario 'Un parámetro sin valor definido queda explícitamente sin
    definir' (tarea 8.3): no se inventan valores por omisión."""
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
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


def test_la_siembra_no_crea_listas_de_precios_y_la_predeterminada_queda_sin_definir(
    db_session: Session,
) -> None:
    """Escenario "La organización recién sembrada no tiene lista predeterminada" (change 13,
    D11): crear "General" exige un redondeo que `01` §4 deja "a definir", así que la lista se
    crea desde la pantalla y no se siembra."""
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
    assert organizacion is not None

    listas = db_session.execute(
        text("SELECT count(*) FROM lista_precio WHERE organizacion_id = :o"),
        {"o": organizacion.id},
    ).scalar_one()
    configuracion = identidad_service.obtener_configuracion(organizacion.id, db_session)
    assert listas == 0
    assert configuracion is not None
    assert configuracion.lista_precio_default_id is None


def test_sembrar_dos_veces_no_duplica_ni_pisa(db_session: Session) -> None:
    """Escenario 'Sembrar dos veces no duplica ni pisa' (tarea 8.6)."""
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
    assert organizacion is not None

    identidad_repository.actualizar_configuracion(
        organizacion.id, db_session, momento=RELOJ.now(), politica_credito_default="BLOQUEAR"
    )
    db_session.flush()

    resultado_segunda_siembra = sembrar(
        db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA
    )

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
        sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)


def test_los_seis_motivos_de_ajuste_stock_se_listan_por_ambito_y_ninguno_de_otro_ambito(
    db_session: Session,
) -> None:
    """Escenario 'Los motivos se listan por ámbito' (tarea 8.7)."""
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
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


def test_una_organizacion_nueva_tiene_los_tres_motivos_de_anulacion_de_compra(
    db_session: Session,
) -> None:
    """Change 11, tarea 3.2 (CMP-05, TR-09, `design.md` D8): la siembra crea los motivos
    del ámbito `ANULACION_COMPRA` aprobados el 2026-10-02."""
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
    assert organizacion is not None

    motivos = configuracion_service.listar_motivos_por_ambito(
        organizacion.id, db_session, "ANULACION_COMPRA"
    )

    assert sorted(motivo.nombre for motivo in motivos) == [
        "Devolución al proveedor",
        "Error de carga",
        "Otro",
    ]
    assert all(motivo.ambito == "ANULACION_COMPRA" and motivo.activo for motivo in motivos)


def test_una_organizacion_nueva_tiene_los_tres_motivos_de_anulacion_de_pago(
    db_session: Session,
) -> None:
    """Change 12, tarea 2.2 (PAG-03, TR-09, `design.md` D1, aprobados el 2026-10-03): sin
    un motivo de `ANULACION_PAGO` la organización no podría anular ningún pago a
    proveedor. La migración `d1e2f3a4b5c6` siembra los mismos nombres en las
    organizaciones existentes."""
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
    assert organizacion is not None

    motivos = configuracion_service.listar_motivos_por_ambito(
        organizacion.id, db_session, "ANULACION_PAGO"
    )

    assert sorted(motivo.nombre for motivo in motivos) == [
        "Error de carga",
        "Otro",
        "Pago rechazado o devuelto",
    ]
    assert all(motivo.ambito == "ANULACION_PAGO" and motivo.activo for motivo in motivos)
    # Los de la compra siguen intactos: son de otro ámbito.
    assert (
        len(
            configuracion_service.listar_motivos_por_ambito(
                organizacion.id, db_session, "ANULACION_COMPRA"
            )
        )
        == 3
    )


@pytest.mark.parametrize("ambito", ["ANULACION_TRANSFERENCIA", "ANULACION_AJUSTE"])
def test_una_organizacion_nueva_tiene_los_motivos_de_anulacion_de_stock(
    db_session: Session, ambito: str
) -> None:
    """Change 14, tarea 2.2 (TR-09, `design.md` D5.3, aprobada el 2026-10-07): "Error de
    carga" y "Otro" en cada ámbito; sin ellos la organización no podría anular una
    transferencia ni un ajuste. La migración `f3a4b5c6d7e8` siembra los mismos nombres en
    las organizaciones existentes."""
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
    assert organizacion is not None

    motivos = configuracion_service.listar_motivos_por_ambito(organizacion.id, db_session, ambito)

    assert sorted(motivo.nombre for motivo in motivos) == ["Error de carga", "Otro"]
    assert all(motivo.ambito == ambito and motivo.activo for motivo in motivos)


def test_solo_administrador_y_administracion_reciben_anular_transferencia(
    db_session: Session,
) -> None:
    """Change 14, tarea 2.2 (`01` §19, D5 punto 5): la siembra asigna el permiso a las
    plantillas Administrador y Administración (GES) y a ninguna otra."""
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
    assert organizacion is not None

    con_el_permiso = {
        rol.nombre
        for rol in identidad_repository.listar_roles(organizacion.id, db_session)
        if "ANULAR_TRANSFERENCIA"
        in identidad_repository.listar_permisos_de_rol(organizacion.id, rol.id, db_session)
    }

    assert con_el_permiso == {"Administrador", "Administración"}


def test_sembrar_dos_veces_no_duplica_los_motivos_de_anulacion_de_compra(
    db_session: Session,
) -> None:
    sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
    assert sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA) is None

    cantidad = db_session.execute(
        text("SELECT count(*) FROM motivo WHERE ambito = 'ANULACION_COMPRA'")
    ).scalar_one()
    assert cantidad == 3


def test_un_elemento_desactivado_deja_de_ofrecerse_pero_sigue_legible_por_id(
    db_session: Session,
) -> None:
    """Escenario 'Un elemento desactivado deja de ofrecerse' (tarea 8.7)."""
    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
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

    organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
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


class TestPlantillasDeRolYAdministradorInicial:
    """Tarea 8.13 (`design.md` D8): la puesta en marcha crea las cinco
    plantillas de rol y un usuario administrador sin contraseña por
    omisión."""

    def test_las_cinco_plantillas_de_rol_quedan_disponibles(self, db_session: Session) -> None:
        organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
        assert organizacion is not None

        roles = identidad_repository.listar_roles(organizacion.id, db_session)
        assert {rol.nombre for rol in roles} == set(PLANTILLAS_DE_ROL)
        for rol in roles:
            permisos = set(
                identidad_repository.listar_permisos_de_rol(organizacion.id, rol.id, db_session)
            )
            assert permisos == PLANTILLAS_DE_ROL[rol.nombre]

    def test_el_usuario_administrador_puede_autenticarse_con_la_contrasena_provista(
        self, db_session: Session
    ) -> None:
        organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
        assert organizacion is not None

        admin = identidad_repository.obtener_usuario_por_nombre_usuario(
            organizacion.id, "admin", db_session
        )
        assert admin is not None
        assert admin.estado == "ACTIVO"
        assert verificar_password(PASSWORD_ADMIN_DE_PRUEBA, admin.password_hash) is True

        rol_administrador = next(
            rol
            for rol in identidad_repository.listar_roles(organizacion.id, db_session)
            if rol.nombre == ADMINISTRADOR
        )
        assert admin.rol_id == rol_administrador.id

    def test_sin_contrasena_provista_la_puesta_en_marcha_falla(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Escenario "Sin contraseña provista la puesta en marcha falla"."""
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

        with pytest.raises(AdminPasswordNoDefinidaError):
            from app.seed import _password_administrador_desde_entorno

            _password_administrador_desde_entorno()

        with pytest.raises(AdminPasswordNoDefinidaError):
            sembrar(db_session, RELOJ, password_administrador="")

        total_organizaciones = db_session.execute(
            text("SELECT COUNT(*) FROM organizacion")
        ).scalar_one()
        assert total_organizaciones == 0

    def test_repetir_la_puesta_en_marcha_no_pisa_la_contrasena_existente(
        self, db_session: Session
    ) -> None:
        """Escenario "Repetir la puesta en marcha no pisa la contraseña
        existente"."""
        organizacion = sembrar(db_session, RELOJ, password_administrador=PASSWORD_ADMIN_DE_PRUEBA)
        assert organizacion is not None
        admin = identidad_repository.obtener_usuario_por_nombre_usuario(
            organizacion.id, "admin", db_session
        )
        assert admin is not None
        hash_original = admin.password_hash

        resultado_segunda_siembra = sembrar(
            db_session, RELOJ, password_administrador="otra-contrasena-distinta-999"
        )
        assert resultado_segunda_siembra is None

        admin_despues = identidad_repository.obtener_usuario_por_nombre_usuario(
            organizacion.id, "admin", db_session
        )
        assert admin_despues is not None
        assert admin_despues.password_hash == hash_original

        cantidad_de_administradores = len(
            identidad_repository.listar_usuarios_por_rol(
                organizacion.id,
                next(
                    rol
                    for rol in identidad_repository.listar_roles(organizacion.id, db_session)
                    if rol.nombre == ADMINISTRADOR
                ).id,
                db_session,
            )
        )
        assert cantidad_de_administradores == 1
