"""Change 11b, tarea 5.1: `ORGANIZACION_CONDICION_IVA_CAMBIAR` v1 por el bus, contra
PostgreSQL real. La cobertura HTTP (403, 422, rutas) es de `test_condicion_iva_api.py`.

Reglas citadas: CST-06, TR-06 (el cambio no recalcula lo registrado), INV-01 (atomicidad
con la auditoría), INV-06 (idempotencia), AUD-01, SEG-06 y `design.md` D2, D3, D7.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from compras_utiles import MOMENTO, RELOJ, Entorno
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError
from app.commands.huella import calcular_huella
from app.core.errors import PermisoRequeridoError
from app.modules.identidad import commands as identidad_commands
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.valores import (
    CondicionIvaInvalidaError,
    CondicionIvaSinCambioError,
    ModoImpositivoIncompatibleError,
)
from app.modules.identidad.models import Auditoria
from app.modules.proveedores.models import CostoInformado
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

CAMBIAR = "ORGANIZACION_CONDICION_IVA_CAMBIAR"
ADMINISTRADOR = frozenset({"ADMIN_CONFIGURACION", "REGISTRAR_COMPRA"})


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=ADMINISTRADOR)


def _cambiar(entorno: Entorno, condicion: str, *, operation_id: UUID | None = None) -> Comando:
    sobre = entorno.sobre({"condicion_iva": condicion}, operation_id=operation_id, tipo=CAMBIAR)
    huella = calcular_huella(sobre.contenido)
    contenido = identidad_commands.OrganizacionCondicionIvaCambiarContenidoV1.model_validate(
        sobre.contenido
    )

    def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return identidad_commands.manejar_organizacion_condicion_iva_cambiar(
            sobre, contenido, sesion=sesion_protegida, reloj=RELOJ
        )

    return sync_service.procesar_comando(
        entorno.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
    )


def _condicion(entorno: Entorno) -> str | None:
    entorno.sesion.expire_all()
    return identidad_service.obtener_condicion_iva(entorno.org, entorno.sesion)


def _auditorias_del_cambio(entorno: Entorno) -> list[Auditoria]:
    """Las auditorías de la ESCRITURA (entidad `configuracion_organizacion`), no la fila
    genérica que el bus deja por cada comando (entidad `comando`)."""
    return list(
        entorno.sesion.scalars(
            select(Auditoria).where(
                Auditoria.organizacion_id == entorno.org,
                Auditoria.accion == CAMBIAR,
                Auditoria.entidad == "configuracion_organizacion",
            )
        ).all()
    )


# --- el cambio (CST-06, D7) --------------------------------------------------------------


def test_monotributista_pasa_a_responsable_inscripto_con_una_auditoria(entorno: Entorno) -> None:
    entorno.fijar_condicion_iva("MONOTRIBUTO")

    comando = _cambiar(entorno, "RESPONSABLE_INSCRIPTO")

    assert comando.estado == "ACEPTADO"
    assert _condicion(entorno) == "RESPONSABLE_INSCRIPTO"
    (auditoria,) = _auditorias_del_cambio(entorno)
    assert auditoria.antes == {"condicion_iva": "MONOTRIBUTO"}
    assert auditoria.despues == {"condicion_iva": "RESPONSABLE_INSCRIPTO"}
    assert auditoria.entidad_id == entorno.org
    assert auditoria.usuario_id == entorno.usuario_id
    assert auditoria.operation_id == comando.operation_id
    assert comando.resultado == {
        "condicion_iva": "RESPONSABLE_INSCRIPTO",
        "computa_credito_fiscal": True,
        "modo_impositivo": "A",
        "modalidad_iva_default": None,
    }


def test_responsable_inscripto_en_modo_a_sin_modalidad_pasa_a_exento(entorno: Entorno) -> None:
    entorno.sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET modo_impositivo = 'A', "
            "modalidad_iva_default = NULL WHERE organizacion_id = :o"
        ),
        {"o": entorno.org},
    )

    comando = _cambiar(entorno, "EXENTO")

    assert _condicion(entorno) == "EXENTO"
    assert comando.resultado is not None
    assert comando.resultado["computa_credito_fiscal"] is False


def test_tr06_el_cambio_no_toca_costos_ni_compras_previos(entorno: Entorno) -> None:
    """Una compra de Caja x6 como monotributista queda con su costo base y su marca aunque la
    organización pase a responsable inscripto (CST-06, TR-06)."""
    entorno.fijar_condicion_iva("MONOTRIBUTO")
    entorno.enviar(
        entorno.contenido(lineas=[entorno.linea("vino", valor="7260.00")], total_factura="72600.00")
    )

    _cambiar(entorno, "RESPONSABLE_INSCRIPTO")

    (linea,) = entorno.lineas()
    assert (linea.costo_base, linea.computa_credito_fiscal) == (Decimal("1210.000000"), False)
    assert entorno.promedio(entorno.vino_id) == Decimal("1210.000000")
    assert (
        entorno.sesion.scalars(
            select(CostoInformado).where(CostoInformado.organizacion_id == entorno.org)
        ).all()
        == []
    )


# --- rechazos (D2, D7) -------------------------------------------------------------------


def test_cambiar_al_mismo_valor_se_rechaza_y_no_audita(entorno: Entorno) -> None:
    entorno.fijar_condicion_iva("MONOTRIBUTO")

    with pytest.raises(CondicionIvaSinCambioError) as error:
        _cambiar(entorno, "MONOTRIBUTO")

    assert error.value.codigo == "CONDICION_IVA_SIN_CAMBIO"
    assert _condicion(entorno) == "MONOTRIBUTO"
    assert _auditorias_del_cambio(entorno) == []


@pytest.mark.parametrize("destino", ["MONOTRIBUTO", "EXENTO"])
def test_pasar_a_no_inscripto_con_modalidad_de_iva_se_rechaza(
    entorno: Entorno, destino: str
) -> None:
    """El entorno nace `RESPONSABLE_INSCRIPTO`, modo B y modalidad `CLIENTE` (D2)."""
    with pytest.raises(ModoImpositivoIncompatibleError) as error:
        _cambiar(entorno, destino)

    assert error.value.codigo == "MODO_IMPOSITIVO_INCOMPATIBLE"
    assert _condicion(entorno) == "RESPONSABLE_INSCRIPTO"
    assert _auditorias_del_cambio(entorno) == []


def test_pasar_a_no_inscripto_con_modo_distinto_de_a_se_rechaza(entorno: Entorno) -> None:
    entorno.sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET modo_impositivo = 'C', "
            "modalidad_iva_default = NULL WHERE organizacion_id = :o"
        ),
        {"o": entorno.org},
    )

    with pytest.raises(ModoImpositivoIncompatibleError):
        _cambiar(entorno, "MONOTRIBUTO")

    assert _condicion(entorno) == "RESPONSABLE_INSCRIPTO"


def test_un_valor_desconocido_se_rechaza_y_la_condicion_no_cambia(entorno: Entorno) -> None:
    with pytest.raises(CondicionIvaInvalidaError):
        _cambiar(entorno, "CONSUMIDOR_FINAL")

    assert _condicion(entorno) == "RESPONSABLE_INSCRIPTO"
    assert _auditorias_del_cambio(entorno) == []


def test_sin_admin_configuracion_se_rechaza_con_permiso_requerido(db_session: Session) -> None:
    entorno = Entorno(db_session, permisos=frozenset({"REGISTRAR_COMPRA"}))
    entorno.fijar_condicion_iva("MONOTRIBUTO")

    with pytest.raises(PermisoRequeridoError):
        _cambiar(entorno, "RESPONSABLE_INSCRIPTO")

    assert _condicion(entorno) == "MONOTRIBUTO"
    assert _auditorias_del_cambio(entorno) == []


# --- idempotencia y atomicidad (INV-06, INV-01) ------------------------------------------


def test_inv06_el_reenvio_devuelve_el_resultado_original_con_una_sola_auditoria(
    entorno: Entorno,
) -> None:
    entorno.fijar_condicion_iva("MONOTRIBUTO")
    operation_id = uuid4()

    primero = _cambiar(entorno, "RESPONSABLE_INSCRIPTO", operation_id=operation_id)
    segundo = _cambiar(entorno, "RESPONSABLE_INSCRIPTO", operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(_auditorias_del_cambio(entorno)) == 1


def test_inv06_el_mismo_operation_id_con_otro_valor_es_comando_inconsistente(
    entorno: Entorno,
) -> None:
    entorno.fijar_condicion_iva("MONOTRIBUTO")
    operation_id = uuid4()
    _cambiar(entorno, "RESPONSABLE_INSCRIPTO", operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        _cambiar(entorno, "EXENTO", operation_id=operation_id)

    assert _condicion(entorno) == "RESPONSABLE_INSCRIPTO"


def test_inv01_una_falla_despues_del_cambio_y_antes_de_la_auditoria_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    entorno.fijar_condicion_iva("MONOTRIBUTO")

    def _falla(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("falla inyectada antes de la auditoría")

    monkeypatch.setattr(identidad_service, "registrar_auditoria", _falla)

    with pytest.raises(RuntimeError, match="falla inyectada"):
        _cambiar(entorno, "RESPONSABLE_INSCRIPTO")

    monkeypatch.undo()
    assert _condicion(entorno) == "MONOTRIBUTO"
    assert _auditorias_del_cambio(entorno) == []


def test_el_cambio_registra_el_momento_del_reloj_inyectado(entorno: Entorno) -> None:
    entorno.fijar_condicion_iva("MONOTRIBUTO")

    _cambiar(entorno, "RESPONSABLE_INSCRIPTO")

    configuracion = identidad_service.obtener_configuracion(entorno.org, entorno.sesion)
    assert configuracion is not None
    assert configuracion.actualizado_en == MOMENTO
    assert configuracion.actualizado_por_id == entorno.usuario_id
