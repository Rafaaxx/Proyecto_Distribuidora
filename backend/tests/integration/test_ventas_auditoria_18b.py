"""Tarea 12.1 (change 18b; spec `auditoria/registro-de-auditoria`; `design.md` D19, gobernanza
ALTA), contra PostgreSQL real.

Además de la fila genérica del bus (`VENTA_CONFIRMAR`, entidad `comando`), una venta con descuento
manual informado deja una fila `DESCUENTO_MANUAL` (entidad `venta`) y una venta cuya resolución de
crédito no es `SIN_EXCESO` deja una fila `AUTORIZACION_CREDITO`, las dos con el `operation_id` de
la venta y su autorizador. Ninguna lleva el PIN. Una venta rechazada no deja ninguna. Un doble
envío no duplica filas.

Reglas citadas: AUD-01, AUD-02, AUD-03, DSC-06, CRE-05, CRE-10, INV-01, INV-06.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import EntornoVenta

from app.core.errors import DomainError
from app.modules.identidad.models import Auditoria

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PIN_DE_MARTA = "482913"
PIN_DE_LUIS = "739158"


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    e = EntornoVenta(db_session)
    e.configurar(descuento_manual_habilitado=True, politica_credito_default="AUTORIZAR")
    e.permitir("DESCUENTO_MANUAL")
    e.fijar_tope("0.05")
    db_session.commit()
    return e


def _manual(porcentaje: str, importe: str) -> dict[str, Any]:
    return {"origen": "MANUAL", "regla_id": None, "porcentaje": porcentaje, "importe": importe}


def _con_descuento(
    entorno: EntornoVenta, porcentaje: str, importe: str, total: str, **cambios: Any
) -> dict[str, Any]:
    """15 botellas de Vino A ($31.250) con un general del `porcentaje` (fracción)."""
    return entorno.contenido(
        entorno.linea(descuentos=[_manual(f"{Decimal(porcentaje):.6f}", importe)]),
        total=total,
        descuento_manual_general=porcentaje,
        **cambios,
    )


def _filas(entorno: EntornoVenta, operation_id: UUID) -> dict[str, list[Auditoria]]:
    """Las filas de la operación agrupadas por acción."""
    entorno.sesion.rollback()
    por_accion: dict[str, list[Auditoria]] = {}
    for fila in entorno.auditoria_de(operation_id):
        por_accion.setdefault(fila.accion, []).append(fila)
    return por_accion


def _texto_completo(filas: dict[str, list[Auditoria]]) -> str:
    """Todo lo que las filas guardan, en un solo texto, para buscar el PIN."""
    return json.dumps(
        [
            [
                fila.accion,
                fila.entidad,
                fila.observacion,
                fila.antes,
                fila.despues,
                str(fila.motivo_id),
                str(fila.autorizador_id),
            ]
            for grupo in filas.values()
            for fila in grupo
        ],
        default=str,
    )


def test_aud01_una_venta_con_descuento_y_credito_autorizados_por_personas_distintas_deja_tres_filas(
    entorno: EntornoVenta,
) -> None:
    """Escenario "Venta con descuento y crédito autorizados por personas distintas": 10 % sobre el
    tope de 5 % autorizado por Marta y exceso de crédito autorizado por Luis."""
    entorno.datos_de_credito(limite="160000.00", politica="AUTORIZAR")
    marta = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN_DE_MARTA)
    luis = entorno.crear_usuario(frozenset({"SUPERAR_CREDITO"}), pin=PIN_DE_LUIS)
    motivo = entorno.crear_motivo("DESCUENTO_MANUAL", "Cortesía")
    entorno.sesion.commit()

    comando = entorno.enviar(
        _con_descuento(
            entorno,
            "0.10",
            "3125.00",
            "28125.00",
            descuento_autorizador_id=str(marta),
            motivo_descuento_id=str(motivo),
            credito={"autorizador_id": str(luis)},
        ),
        credenciales=(
            entorno.credencial(marta, PIN_DE_MARTA),
            entorno.credencial(luis, PIN_DE_LUIS),
        ),
    )

    filas = _filas(entorno, comando.operation_id)
    assert set(filas) == {"VENTA_CONFIRMAR", "DESCUENTO_MANUAL", "AUTORIZACION_CREDITO"}
    assert all(len(grupo) == 1 for grupo in filas.values())
    (venta,) = entorno.ventas()
    (descuento,) = filas["DESCUENTO_MANUAL"]
    assert (descuento.entidad, descuento.entidad_id, descuento.origen) == (
        "venta",
        venta.id,
        "COMANDO",
    )
    assert descuento.autorizador_id == marta
    assert descuento.motivo_id == motivo
    assert descuento.despues == {
        "porcentaje_maximo": "0.100000",
        "tope_aplicado": "0.050000",
        "resolucion": "AUTORIZADO_POR_SUPERVISOR",
    }
    (credito,) = filas["AUTORIZACION_CREDITO"]
    assert (credito.entidad, credito.entidad_id, credito.origen) == ("venta", venta.id, "COMANDO")
    assert credito.autorizador_id == luis
    assert credito.despues == {
        "limite": "160000.00",
        "saldo_considerado": "150000.00",
        "disponible": "10000.00",
        "exceso": "18125.00",
        "politica": "AUTORIZAR",
        "resolucion": "PIN_SUPERVISOR",
    }
    # Ninguna fila lleva el PIN (SEG-05, ADR-011).
    texto = _texto_completo(filas)
    assert PIN_DE_MARTA not in texto
    assert PIN_DE_LUIS not in texto


def test_aud01_una_venta_sin_descuento_manual_ni_exceso_solo_deja_la_fila_del_comando(
    entorno: EntornoVenta,
) -> None:
    comando = entorno.vender()

    filas = _filas(entorno, comando.operation_id)

    assert set(filas) == {"VENTA_CONFIRMAR"}
    assert len(filas["VENTA_CONFIRMAR"]) == 1


def test_aud02_un_descuento_dentro_del_tope_deja_su_fila_sin_autorizador(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: 3 % con tope de 5 % -> `DESCUENTO_MANUAL` con el propio usuario sin
    autorizador y sin fila de crédito (la venta no excede el límite)."""
    comando = entorno.enviar(_con_descuento(entorno, "0.03", "937.50", "30312.50"))

    filas = _filas(entorno, comando.operation_id)

    assert set(filas) == {"VENTA_CONFIRMAR", "DESCUENTO_MANUAL"}
    (descuento,) = filas["DESCUENTO_MANUAL"]
    assert descuento.autorizador_id is None
    assert descuento.despues == {
        "porcentaje_maximo": "0.030000",
        "tope_aplicado": "0.050000",
        "resolucion": "DENTRO_DEL_TOPE",
    }


def test_aud02_el_descuento_con_permiso_propio_para_autorizar_queda_con_el_propio_usuario(
    entorno: EntornoVenta,
) -> None:
    """Triangulación: con `AUTORIZAR_DESCUENTO` propio, sobre el tope, el autorizador es quien
    vende (PERMISO_PROPIO) y no se pide ningún PIN."""
    entorno.permitir("AUTORIZAR_DESCUENTO")

    comando = entorno.enviar(_con_descuento(entorno, "0.10", "3125.00", "28125.00"))

    (descuento,) = _filas(entorno, comando.operation_id)["DESCUENTO_MANUAL"]
    assert descuento.autorizador_id == entorno.usuario_id
    assert descuento.despues is not None
    assert descuento.despues["resolucion"] == "PERMISO_PROPIO"


def test_aud01_un_exceso_advertido_deja_la_fila_de_credito_sin_autorizador(
    entorno: EntornoVenta,
) -> None:
    """Resolución `ADVERTENCIA_ACEPTADA` (no es `SIN_EXCESO`): fila `AUTORIZACION_CREDITO` sin
    autorizador."""
    entorno.datos_de_credito(limite="160000.00", politica="ADVERTIR")

    comando = entorno.enviar(
        entorno.contenido(entorno.linea(), total="31250.00", credito={"acepta_exceso": True})
    )

    filas = _filas(entorno, comando.operation_id)
    assert set(filas) == {"VENTA_CONFIRMAR", "AUTORIZACION_CREDITO"}
    (credito,) = filas["AUTORIZACION_CREDITO"]
    assert credito.autorizador_id is None
    assert credito.despues is not None
    assert credito.despues["resolucion"] == "ADVERTENCIA_ACEPTADA"
    assert credito.despues["exceso"] == "21250.00"


def test_aud01_una_venta_rechazada_no_deja_ninguna_fila(entorno: EntornoVenta) -> None:
    """Escenario "Venta rechazada" (`AUTORIZACION_REQUERIDA`, INV-01): ni la del descuento ni la
    del crédito ni la del comando."""
    entorno.datos_de_credito(limite="160000.00", politica="AUTORIZAR")
    operation_id = UUID(int=0x18B)

    with pytest.raises(DomainError) as error:
        entorno.enviar(
            _con_descuento(entorno, "0.10", "3125.00", "28125.00"), operation_id=operation_id
        )

    assert error.value.codigo == "AUTORIZACION_REQUERIDA"
    assert _filas(entorno, operation_id) == {}


def test_inv06_un_doble_envio_no_duplica_las_filas(entorno: EntornoVenta) -> None:
    marta = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN_DE_MARTA)
    contenido = _con_descuento(
        entorno, "0.10", "3125.00", "28125.00", descuento_autorizador_id=str(marta)
    )
    operation_id = UUID(int=0x18C)
    credenciales = (entorno.credencial(marta, PIN_DE_MARTA),)
    entorno.enviar(contenido, operation_id=operation_id, credenciales=credenciales)
    entorno.sesion.commit()

    entorno.enviar(contenido, operation_id=operation_id, credenciales=credenciales)

    filas = _filas(entorno, operation_id)
    assert {accion: len(grupo) for accion, grupo in filas.items()} == {
        "VENTA_CONFIRMAR": 1,
        "DESCUENTO_MANUAL": 1,
    }
