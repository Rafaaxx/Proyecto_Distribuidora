"""Change 16, tarea 8.2: `REGLA_DESCUENTO_MODIFICAR` v1 por el bus, contra PostgreSQL real (spec
`descuentos/reglas-de-descuento`, requisito "Una regla solo se edita mientras es borrador").

Reglas citadas: DSC-01, TR-06, INV-06, INV-21, SEG-06, SEG-07, `design.md` D15, D16.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from descuentos_utiles import (
    ACTIVAR,
    CREAR,
    MODIFICAR,
    MOMENTO,
    PAUSAR,
    Entorno,
    regla_valida,
)
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError
from app.core.errors import PermisoRequeridoError
from app.modules.descuentos.domain.errores import (
    AccionInvalidaError,
    RecursoNoEncontradoError,
    ReglaDescuentoInvalidaError,
    ReglaNoEsBorradorError,
    UmbralInvalidoError,
    VigenciaInvalidaError,
)

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

FUTURO = MOMENTO + timedelta(days=30)


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _alcance(tipo: str, entidad_id: object) -> dict[str, str]:
    return {"tipo": tipo, "entidad_id": str(entidad_id)}


def _modificar(regla_id: UUID, **cambios: Any) -> dict[str, Any]:
    """Un reemplazo completo del borrador (los campos del alta más `regla_id`)."""
    contenido = regla_valida(**cambios)
    contenido["regla_id"] = str(regla_id)
    return contenido


def _un_borrador_de_alcance(entorno: Entorno) -> UUID:
    return entorno.crear_regla_descuento(
        tipo="VOLUMEN_ALCANCE",
        alcances=[_alcance("MARCA", entorno.marca_id), _alcance("PRODUCTO", entorno.vino_id)],
    )


# --- el borrador se corrige (D15) ---------------------------------------------------------------


def test_corregir_el_umbral_de_un_borrador(entorno: Entorno) -> None:
    """Escenario "Corregir el umbral de un borrador": queda en `BORRADOR` con el umbral nuevo y
    una sola fila de auditoría."""
    regla_id = entorno.crear_regla_descuento()
    operation_id = uuid4()

    comando = entorno.enviar(
        MODIFICAR, _modificar(regla_id, umbral="24"), operation_id=operation_id
    )

    assert comando.estado == "ACEPTADO"
    assert comando.resultado == {"regla_id": str(regla_id)}
    regla = entorno.regla_de_descuento(regla_id)
    assert (regla.estado, regla.umbral) == ("BORRADOR", Decimal("24"))
    (auditoria,) = entorno.auditorias(MODIFICAR)
    assert auditoria.operation_id == operation_id


def test_corregir_un_borrador_reemplaza_todos_sus_datos_y_sus_alcances(entorno: Entorno) -> None:
    regla_id = _un_borrador_de_alcance(entorno)
    categoria_2 = entorno.crear_categoria("Espumantes")

    entorno.enviar(
        MODIFICAR,
        _modificar(
            regla_id,
            nombre="Espumantes",
            tipo="VOLUMEN_ALCANCE",
            medida="IMPORTE_BRUTO",
            operador="GT",
            umbral="200000.00",
            accion_tipo="IMPORTE_FIJO",
            accion_valor="5000.00",
            prioridad=4,
            acumulable=True,
            alcances=[_alcance("CATEGORIA", categoria_2)],
            vigencia_desde=MOMENTO.isoformat(),
            vigencia_hasta=FUTURO.isoformat(),
        ),
    )

    regla = entorno.regla_de_descuento(regla_id)
    assert (regla.nombre, regla.medida, regla.operador) == ("Espumantes", "IMPORTE_BRUTO", "GT")
    assert (regla.accion_porcentaje, regla.accion_importe) == (None, Decimal("5000.00"))
    assert (regla.prioridad, regla.acumulable) == (4, True)
    assert (regla.vigencia_desde, regla.vigencia_hasta) == (MOMENTO, FUTURO)
    assert regla.estado == "BORRADOR"
    (alcance,) = entorno.alcances_de(regla_id)
    assert (alcance.alcance_tipo, alcance.alcance_id) == ("CATEGORIA", categoria_2)


def test_corregir_un_borrador_de_alcance_a_operacion_quita_los_alcances(
    entorno: Entorno,
) -> None:
    regla_id = _un_borrador_de_alcance(entorno)

    entorno.enviar(MODIFICAR, _modificar(regla_id, tipo="VOLUMEN_OPERACION", alcances=[]))

    assert entorno.alcances_de(regla_id) == []
    assert entorno.regla_de_descuento(regla_id).tipo == "VOLUMEN_OPERACION"


def test_corregir_un_borrador_dos_veces_con_el_mismo_alcance_no_choca_con_el_unico(
    entorno: Entorno,
) -> None:
    """Los alcances se reemplazan (se borran y se insertan): reenviar el mismo conjunto no
    viola el único por regla, tipo y entidad."""
    regla_id = _un_borrador_de_alcance(entorno)
    contenido = _modificar(
        regla_id,
        tipo="VOLUMEN_ALCANCE",
        alcances=[_alcance("MARCA", entorno.marca_id), _alcance("PRODUCTO", entorno.vino_id)],
    )

    entorno.enviar(MODIFICAR, contenido)
    entorno.enviar(MODIFICAR, {**contenido, "nombre": "Otro nombre"})

    assert len(entorno.alcances_de(regla_id)) == 2
    assert entorno.regla_de_descuento(regla_id).nombre == "Otro nombre"


@pytest.mark.parametrize(
    ("cambios", "esperado"),
    [
        ({"umbral": "0"}, UmbralInvalidoError),
        ({"accion_valor": "2"}, AccionInvalidaError),
        (
            {"vigencia_desde": FUTURO.isoformat(), "vigencia_hasta": MOMENTO.isoformat()},
            VigenciaInvalidaError,
        ),
    ],
)
def test_una_correccion_invalida_se_rechaza_y_el_borrador_no_cambia(
    entorno: Entorno, cambios: dict[str, Any], esperado: type[Exception]
) -> None:
    regla_id = entorno.crear_regla_descuento()
    entorno.sesion.commit()

    with pytest.raises(esperado):
        entorno.enviar(MODIFICAR, _modificar(regla_id, **cambios))

    entorno.sesion.rollback()
    regla = entorno.regla_de_descuento(regla_id)
    assert (regla.umbral, regla.accion_porcentaje) == (Decimal("20"), Decimal("0.050000"))


def test_corregir_un_borrador_incompleto_se_rechaza(entorno: Entorno) -> None:
    regla_id = entorno.crear_regla_descuento()
    entorno.sesion.commit()

    with pytest.raises(ReglaDescuentoInvalidaError) as error:
        entorno.enviar(MODIFICAR, {"regla_id": str(regla_id), "umbral": "24"})

    assert "faltan" in str(error.value)
    entorno.sesion.rollback()
    assert entorno.regla_de_descuento(regla_id).umbral == Decimal("20")


def test_un_alcance_ajeno_en_la_correccion_responde_404_y_conserva_los_alcances(
    entorno: Entorno, db_session: Session
) -> None:
    regla_id = _un_borrador_de_alcance(entorno)
    ajena = Entorno(db_session)
    entorno.sesion.commit()

    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(
            MODIFICAR,
            _modificar(
                regla_id, tipo="VOLUMEN_ALCANCE", alcances=[_alcance("MARCA", ajena.marca_id)]
            ),
        )

    entorno.sesion.rollback()
    assert len(entorno.alcances_de(regla_id)) == 2


# --- una regla activada no se edita (D15, TR-06) -------------------------------------------------


@pytest.mark.parametrize("pausada", [False, True])
def test_intentar_cambiar_el_porcentaje_de_una_regla_activada_o_pausada_se_rechaza(
    entorno: Entorno, pausada: bool
) -> None:
    """Escenario "Intentar cambiar el porcentaje de una regla activa" y su hermano de la pausada:
    409 `REGLA_NO_ES_BORRADOR` y la regla sigue como estaba."""
    regla_id = entorno.crear_regla_descuento()
    entorno.activar_regla(regla_id)
    if pausada:
        entorno.pausar_regla(regla_id)
    entorno.sesion.commit()

    with pytest.raises(ReglaNoEsBorradorError) as error:
        entorno.enviar(MODIFICAR, _modificar(regla_id, accion_valor="0.080000"))

    assert error.value.status_http == 409
    entorno.sesion.rollback()
    regla = entorno.regla_de_descuento(regla_id)
    assert regla.accion_porcentaje == Decimal("0.050000")
    assert regla.estado == ("PAUSADA" if pausada else "ACTIVA")


def test_una_modificacion_sin_campos_de_una_regla_activa_tambien_se_rechaza(
    entorno: Entorno,
) -> None:
    regla_id = entorno.crear_regla_descuento()
    entorno.activar_regla(regla_id)
    entorno.sesion.commit()

    with pytest.raises(ReglaNoEsBorradorError):
        entorno.enviar(MODIFICAR, {"regla_id": str(regla_id)})


def test_ponerle_fin_a_una_regla_activa_conserva_todos_sus_datos(entorno: Entorno) -> None:
    """Escenario "Ponerle fin a una regla activa" (D16): solo la vigencia hasta cambia."""
    regla_id = entorno.crear_regla_descuento(
        tipo="VOLUMEN_ALCANCE", alcances=[_alcance("MARCA", entorno.marca_id)]
    )
    entorno.activar_regla(regla_id)
    antes = entorno.regla_de_descuento(regla_id)
    datos_antes = (antes.nombre, antes.umbral, antes.accion_porcentaje, antes.vigencia_desde)

    comando = entorno.enviar(
        MODIFICAR, {"regla_id": str(regla_id), "vigencia_hasta": FUTURO.isoformat()}
    )

    assert comando.estado == "ACEPTADO"
    regla = entorno.regla_de_descuento(regla_id)
    assert regla.vigencia_hasta == FUTURO
    assert (
        regla.nombre,
        regla.umbral,
        regla.accion_porcentaje,
        regla.vigencia_desde,
    ) == datos_antes
    assert regla.estado == "ACTIVA"
    assert len(entorno.alcances_de(regla_id)) == 1


def test_el_fin_de_una_regla_pausada_se_puede_mover_y_quitar(entorno: Entorno) -> None:
    regla_id = entorno.crear_regla_descuento()
    entorno.activar_regla(regla_id)
    entorno.pausar_regla(regla_id)

    entorno.enviar(MODIFICAR, {"regla_id": str(regla_id), "vigencia_hasta": FUTURO.isoformat()})
    assert entorno.regla_de_descuento(regla_id).vigencia_hasta == FUTURO

    entorno.enviar(MODIFICAR, {"regla_id": str(regla_id), "vigencia_hasta": None})
    assert entorno.regla_de_descuento(regla_id).vigencia_hasta is None


def test_un_fin_anterior_al_inicio_de_una_regla_activa_se_rechaza(entorno: Entorno) -> None:
    regla_id = entorno.crear_regla_descuento()
    entorno.activar_regla(regla_id)
    entorno.sesion.commit()

    with pytest.raises(VigenciaInvalidaError):
        entorno.enviar(
            MODIFICAR,
            {
                "regla_id": str(regla_id),
                "vigencia_hasta": (MOMENTO - timedelta(days=1)).isoformat(),
            },
        )


def test_un_fin_en_el_pasado_la_deja_vencida_sin_borrarla(entorno: Entorno) -> None:
    """Poner fin "ya": el fin posterior al inicio, pero anterior al momento actual, es válido
    cuando la regla empezó antes."""
    regla_id = entorno.crear_regla_descuento(
        vigencia_desde=(MOMENTO - timedelta(days=10)).isoformat()
    )
    entorno.activar_regla(regla_id)

    entorno.enviar(
        MODIFICAR,
        {"regla_id": str(regla_id), "vigencia_hasta": (MOMENTO - timedelta(days=1)).isoformat()},
    )

    assert entorno.regla_de_descuento(regla_id).vigencia_hasta == MOMENTO - timedelta(days=1)


# --- permisos, ajena, idempotencia ---------------------------------------------------------------


def test_inv21_modificar_la_regla_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "Regla de otra organización" (INV-21, SEG-07): la ajena no cambia."""
    ajena = Entorno(db_session)
    regla_ajena = ajena.crear_regla_descuento()
    entorno.sesion.commit()

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.enviar(MODIFICAR, _modificar(regla_ajena, umbral="24"))

    assert error.value.status_http == 404
    entorno.sesion.rollback()
    assert ajena.regla_de_descuento(regla_ajena).umbral == Decimal("20")


def test_una_regla_inexistente_responde_404(entorno: Entorno) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(MODIFICAR, _modificar(uuid4()))


def test_sin_gestionar_descuentos_modificar_se_rechaza_con_403(entorno: Entorno) -> None:
    regla_id = entorno.crear_regla_descuento()
    entorno.sesion.commit()
    entorno.actuar_con_permisos(frozenset({"GESTIONAR_LISTAS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(MODIFICAR, _modificar(regla_id, umbral="24"))

    entorno.sesion.rollback()
    assert entorno.regla_de_descuento(regla_id).umbral == Decimal("20")


def test_inv06_modificar_dos_veces_con_el_mismo_operation_id_aplica_una_vez(
    entorno: Entorno,
) -> None:
    regla_id = entorno.crear_regla_descuento()
    operation_id = uuid4()

    entorno.enviar(MODIFICAR, _modificar(regla_id, umbral="24"), operation_id=operation_id)
    entorno.enviar(MODIFICAR, _modificar(regla_id, umbral="24"), operation_id=operation_id)

    assert len(entorno.auditorias(MODIFICAR)) == 1
    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(MODIFICAR, _modificar(regla_id, umbral="30"), operation_id=operation_id)


# --- ninguna regla se borra (TR-06) --------------------------------------------------------------


def test_tr06_ningun_comando_borra_una_regla_ni_los_alcances_de_una_regla_activada(
    entorno: Entorno,
) -> None:
    """Escenario "No existe forma de borrar una regla": se ejecuta cada uno de los cuatro
    comandos (aceptados y rechazados) sobre reglas en cada estado y, después de cada uno, todas
    las reglas siguen y las activadas conservan todos sus alcances."""
    borrador = _un_borrador_de_alcance(entorno)
    activa = _un_borrador_de_alcance(entorno)
    pausada = _un_borrador_de_alcance(entorno)
    entorno.activar_regla(activa)
    entorno.activar_regla(pausada)
    entorno.pausar_regla(pausada)
    entorno.sesion.commit()
    todas = {borrador, activa, pausada}

    def _intentar(tipo: str, contenido: dict[str, Any]) -> None:
        try:
            entorno.enviar(tipo, contenido)
        except Exception:  # noqa: BLE001 (los rechazos son parte del recorrido)
            entorno.sesion.rollback()
        assert todas <= {r.id for r in entorno.reglas_de_descuento()}  # solo el alta suma
        assert len(entorno.alcances_de(activa)) == 2
        assert len(entorno.alcances_de(pausada)) == 2

    for regla_id in (borrador, activa, pausada):
        _intentar(MODIFICAR, _modificar(regla_id, tipo="VOLUMEN_OPERACION", alcances=[]))
        _intentar(MODIFICAR, {"regla_id": str(regla_id), "vigencia_hasta": FUTURO.isoformat()})
        _intentar(ACTIVAR, {"regla_id": str(regla_id)})
        _intentar(PAUSAR, {"regla_id": str(regla_id)})
    _intentar(CREAR, regla_valida())

    assert len(entorno.alcances_de(borrador)) == 0  # el borrador sí pudo reemplazar los suyos


def test_tr06_el_modulo_no_tiene_ninguna_funcion_publica_de_borrado_de_reglas() -> None:
    """La garantía de fondo: el rol de la aplicación no tiene `DELETE` sobre `regla_descuento`
    (los privilegios los fija y prueba la migración, tarea 5.2); acá se confirma que el servicio
    no tiene ninguna función pública de borrado de reglas."""
    from app.modules.descuentos import repository, service

    publicas = [
        nombre
        for modulo in (repository, service)
        for nombre in vars(modulo)
        if not nombre.startswith("_") and callable(getattr(modulo, nombre))
    ]
    borrados = [nombre for nombre in publicas if "borrar" in nombre or "eliminar" in nombre]
    assert borrados == ["borrar_alcances_de_borrador"]
