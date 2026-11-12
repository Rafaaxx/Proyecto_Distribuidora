"""Change 16, tarea 8.1: `REGLA_DESCUENTO_CREAR` v1 por el bus, contra PostgreSQL real (spec
`descuentos/reglas-de-descuento`, requisitos "Una regla de descuento se crea por comando como
borrador" y "El alcance de una regla es coherente con su tipo").

Reglas citadas: DSC-01, DSC-02, DSC-03, DSC-04, TR-02, INV-01, INV-02, INV-03, INV-06, INV-21,
SYN-02, SEG-06, SEG-07, `design.md` D1, D17, D18.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from descuentos_utiles import CREAR, MOMENTO, RELOJ, Entorno, regla_valida
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.commands.huella import ContenidoNoSerializableError
from app.core.errors import PermisoRequeridoError
from app.modules.descuentos import repository as descuentos_repository
from app.modules.descuentos.domain.errores import (
    AccionInvalidaError,
    AlcanceInvalidoError,
    NombreInvalidoError,
    PrioridadInvalidaError,
    RecursoNoEncontradoError,
    ReglaDescuentoInvalidaError,
    UmbralInvalidoError,
    VigenciaInvalidaError,
)
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _alcance(tipo: str, entidad_id: object) -> dict[str, str]:
    return {"tipo": tipo, "entidad_id": str(entidad_id)}


# --- el alta (DSC-01 a DSC-04) --------------------------------------------------------------


def test_regla_de_volumen_sobre_toda_la_venta(entorno: Entorno) -> None:
    """Escenario "Regla de volumen sobre toda la venta": nace en `BORRADOR`, sin alcances, con
    el porcentaje guardado como `0.050000` y una sola fila de auditoría con el `operation_id`."""
    operation_id = uuid4()

    comando = entorno.enviar(CREAR, regla_valida(), operation_id=operation_id)

    assert comando.estado == "ACEPTADO"
    (regla,) = entorno.reglas_de_descuento()
    assert comando.resultado == {"regla_id": str(regla.id)}
    assert regla.estado == "BORRADOR"
    assert (regla.tipo, regla.medida, regla.operador) == (
        "VOLUMEN_OPERACION",
        "CAJAS_EQUIVALENTES",
        "GTE",
    )
    assert regla.umbral == Decimal("20")
    assert (regla.accion_tipo, regla.accion_porcentaje, regla.accion_importe) == (
        "PORCENTAJE",
        Decimal("0.050000"),
        None,
    )
    assert (regla.prioridad, regla.acumulable) == (1, False)
    assert (regla.vigencia_desde, regla.vigencia_hasta) == (None, None)
    assert (regla.creado_en, regla.actualizado_en) == (MOMENTO, MOMENTO)
    assert regla.actualizado_por_id == entorno.usuario_id
    assert entorno.alcances_de(regla.id) == []
    (auditoria,) = entorno.auditorias(CREAR)
    assert auditoria.operation_id == operation_id


def test_regla_de_volumen_sobre_una_marca_con_importe_fijo(entorno: Entorno) -> None:
    """Escenario "Regla de volumen sobre una marca": el alcance y el importe quedan guardados."""
    regla_id = entorno.crear_regla_descuento(
        tipo="VOLUMEN_ALCANCE",
        medida="UNIDADES_BASE",
        operador="GT",
        umbral="60",
        accion_tipo="IMPORTE_FIJO",
        accion_valor="1000.00",
        alcances=[_alcance("MARCA", entorno.marca_id)],
    )

    regla = entorno.regla_de_descuento(regla_id)
    assert (regla.accion_porcentaje, regla.accion_importe) == (None, Decimal("1000.00"))
    assert (regla.estado, regla.operador, regla.umbral) == ("BORRADOR", "GT", Decimal("60"))
    (alcance,) = entorno.alcances_de(regla_id)
    assert (alcance.alcance_tipo, alcance.alcance_id, alcance.marca_id) == (
        "MARCA",
        entorno.marca_id,
        entorno.marca_id,
    )
    assert alcance.producto_id is None and alcance.categoria_id is None


def test_una_regla_acumulable_con_los_tres_tipos_de_alcance_y_vigencia(
    entorno: Entorno,
) -> None:
    regla_id = entorno.crear_regla_descuento(
        tipo="VOLUMEN_ALCANCE",
        nombre="  Vinos Norte  ",
        acumulable=True,
        prioridad=3,
        alcances=[
            _alcance("PRODUCTO", entorno.vino_id),
            _alcance("CATEGORIA", entorno.categoria_id),
            _alcance("MARCA", entorno.marca_id),
        ],
        vigencia_desde=MOMENTO.isoformat(),
        vigencia_hasta="2026-12-31T00:00:00+00:00",
    )

    regla = entorno.regla_de_descuento(regla_id)
    assert (regla.nombre, regla.acumulable, regla.prioridad) == ("Vinos Norte", True, 3)
    assert regla.vigencia_desde == MOMENTO
    assert regla.vigencia_hasta is not None
    assert {a.alcance_tipo for a in entorno.alcances_de(regla_id)} == {
        "PRODUCTO",
        "CATEGORIA",
        "MARCA",
    }


def test_sin_gestionar_descuentos_se_rechaza_con_403_y_no_se_crea_nada(entorno: Entorno) -> None:
    """Escenario "Sin permiso" (SEG-06): un usuario sin `GESTIONAR_DESCUENTOS`."""
    entorno.actuar_con_permisos(frozenset({"GESTIONAR_LISTAS"}))
    antes = len(entorno.comandos())

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.enviar(CREAR, regla_valida())

    assert error.value.status_http == 403
    entorno.sesion.rollback()
    assert entorno.reglas_de_descuento() == []
    assert len(entorno.comandos()) == antes


# --- listas cerradas y validaciones ------------------------------------------------------------


@pytest.mark.parametrize(
    "cambios",
    [{"medida": "HISTORIAL_DE_COMPRAS"}, {"accion_tipo": "BONIFICACION_EN_UNIDADES"}],
)
def test_una_medida_o_accion_desconocida_se_rechaza_con_422(
    entorno: Entorno, cambios: dict[str, str]
) -> None:
    with pytest.raises(ReglaDescuentoInvalidaError) as error:
        entorno.enviar(CREAR, regla_valida(**cambios))
    assert error.value.status_http == 422
    entorno.sesion.rollback()
    assert entorno.reglas_de_descuento() == []


@pytest.mark.parametrize(
    ("cambios", "esperado"),
    [
        ({"medida": "UNIDADES_BASE", "umbral": "10.5"}, UmbralInvalidoError),
        ({"umbral": "0"}, UmbralInvalidoError),
        ({"umbral": "-3"}, UmbralInvalidoError),
        ({"medida": "IMPORTE_BRUTO", "umbral": "100.005"}, UmbralInvalidoError),
        ({"accion_valor": "0"}, AccionInvalidaError),
        ({"accion_valor": "1.200000"}, AccionInvalidaError),
        ({"accion_valor": "0.1234567"}, AccionInvalidaError),
        ({"accion_tipo": "IMPORTE_FIJO", "accion_valor": "0"}, AccionInvalidaError),
        ({"accion_tipo": "IMPORTE_FIJO", "accion_valor": "10.001"}, AccionInvalidaError),
        ({"prioridad": 0}, PrioridadInvalidaError),
        ({"prioridad": -2}, PrioridadInvalidaError),
        ({"nombre": "   "}, NombreInvalidoError),
        (
            {"vigencia_desde": MOMENTO.isoformat(), "vigencia_hasta": MOMENTO.isoformat()},
            VigenciaInvalidaError,
        ),
    ],
)
def test_un_contenido_invalido_se_rechaza_con_su_codigo_y_no_crea_nada(
    entorno: Entorno, cambios: dict[str, Any], esperado: type[Exception]
) -> None:
    with pytest.raises(esperado) as error:
        entorno.enviar(CREAR, regla_valida(**cambios))
    assert getattr(error.value, "status_http", None) == 422
    entorno.sesion.rollback()
    assert entorno.reglas_de_descuento() == []


def test_una_prioridad_decimal_no_entra_al_bus(entorno: Entorno) -> None:
    """El contenido de un comando no admite floats (la ruta HTTP traduce un decimal a
    `PRIORIDAD_INVALIDA` antes de llegar acá, tarea 8.4)."""
    with pytest.raises(ContenidoNoSerializableError):
        entorno.enviar(CREAR, regla_valida(prioridad=1.5))


@pytest.mark.parametrize("cambios", [{"accion_valor": 0.05}, {"umbral": 20}])
def test_inv03_el_porcentaje_o_el_umbral_como_numero_json_se_rechaza(
    entorno: Entorno, cambios: dict[str, Any]
) -> None:
    """Escenario "El valor de la acción llega como número" (INV-03)."""
    entorno.sesion.commit()

    with pytest.raises(Exception) as error:  # noqa: B017 (float: huella; int: esquema)
        entorno.enviar(CREAR, regla_valida(**cambios))

    assert isinstance(error.value, ContenidoDeComandoInvalidoError | ContenidoNoSerializableError)
    entorno.sesion.rollback()
    assert entorno.reglas_de_descuento() == []


def test_el_contenido_no_acepta_la_organizacion(entorno: Entorno) -> None:
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(CREAR, regla_valida(organizacion_id=str(uuid4())))


# --- alcances (DSC-02, INV-02, INV-21) ---------------------------------------------------------


@pytest.mark.parametrize(
    "cambios",
    [
        {"tipo": "VOLUMEN_ALCANCE", "alcances": []},
        {"tipo": "VOLUMEN_OPERACION", "alcances": "CATEGORIA"},
    ],
)
def test_un_alcance_incoherente_con_el_tipo_se_rechaza(
    entorno: Entorno, cambios: dict[str, Any]
) -> None:
    contenido = regla_valida(**cambios)
    if cambios["alcances"] == "CATEGORIA":
        contenido["alcances"] = [_alcance("CATEGORIA", entorno.categoria_id)]

    with pytest.raises(AlcanceInvalidoError) as error:
        entorno.enviar(CREAR, contenido)

    assert error.value.codigo == "ALCANCE_INVALIDO"


def test_un_alcance_repetido_se_rechaza(entorno: Entorno) -> None:
    with pytest.raises(AlcanceInvalidoError):
        entorno.enviar(
            CREAR,
            regla_valida(
                tipo="VOLUMEN_ALCANCE",
                alcances=[_alcance("PRODUCTO", entorno.vino_id)] * 2,
            ),
        )


@pytest.mark.parametrize("tipo", ["PRODUCTO", "CATEGORIA", "MARCA"])
def test_inv21_la_entidad_del_alcance_de_otra_organizacion_responde_404(
    entorno: Entorno, db_session: Session, tipo: str
) -> None:
    """Escenario "Entidad del alcance de otra organización" (INV-21, SEG-07)."""
    ajena = Entorno(db_session)
    de_b = {"PRODUCTO": ajena.vino_id, "CATEGORIA": ajena.categoria_id, "MARCA": ajena.marca_id}

    with pytest.raises(RecursoNoEncontradoError) as error:
        entorno.enviar(
            CREAR, regla_valida(tipo="VOLUMEN_ALCANCE", alcances=[_alcance(tipo, de_b[tipo])])
        )

    assert error.value.status_http == 404
    db_session.rollback()
    assert entorno.reglas_de_descuento() == []


def test_una_entidad_inexistente_en_el_alcance_responde_404(entorno: Entorno) -> None:
    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(
            CREAR,
            regla_valida(tipo="VOLUMEN_ALCANCE", alcances=[_alcance("MARCA", uuid4())]),
        )


def test_inv02_la_base_rechaza_un_alcance_ajeno_escrito_por_fuera_del_servicio(
    entorno: Entorno, db_session: Session
) -> None:
    """Escenario "La base rechaza un alcance ajeno escrito por fuera del servicio" (INV-02): el
    mismo rechazo de la migración, ahora con una regla creada por el bus."""
    ajena = Entorno(db_session)
    regla_id = entorno.crear_regla_descuento(
        tipo="VOLUMEN_ALCANCE", alcances=[_alcance("PRODUCTO", entorno.vino_id)]
    )

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(
            text(
                "INSERT INTO regla_descuento_alcance (id, organizacion_id, regla_id, "
                "alcance_tipo, alcance_id, creado_en) VALUES (:id, :o, :r, 'PRODUCTO', :e, :m)"
            ),
            {"id": uuid4(), "o": entorno.org, "r": regla_id, "e": ajena.vino_id, "m": MOMENTO},
        )
    assert "fk_regla_descuento_alcance__producto" in str(error.value)


# --- atomicidad e idempotencia -------------------------------------------------------------------


def test_inv01_una_falla_a_mitad_de_la_escritura_no_deja_regla_ni_alcances(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Falla a mitad de la escritura" (INV-01): la regla se guardó y el último
    alcance no; no queda nada y el mismo `operation_id` se puede reintentar."""
    entorno.sesion.commit()
    operation_id = uuid4()
    original = descuentos_repository.insertar_alcance
    cantidad = {"n": 0}

    def _falla_en_el_ultimo(*args: Any, **kwargs: Any) -> None:
        cantidad["n"] += 1
        if cantidad["n"] == 3:
            raise RuntimeError("falla inyectada antes del último alcance")
        original(*args, **kwargs)

    monkeypatch.setattr(descuentos_repository, "insertar_alcance", _falla_en_el_ultimo)
    contenido = regla_valida(
        tipo="VOLUMEN_ALCANCE",
        alcances=[
            _alcance("PRODUCTO", entorno.vino_id),
            _alcance("CATEGORIA", entorno.categoria_id),
            _alcance("MARCA", entorno.marca_id),
        ],
    )

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.enviar(CREAR, contenido, operation_id=operation_id)

    entorno.sesion.rollback()
    assert entorno.reglas_de_descuento() == []
    assert entorno.cantidad("regla_descuento_alcance") == 0
    assert entorno.auditorias(CREAR) == []

    monkeypatch.undo()
    reintento = entorno.enviar(CREAR, contenido, operation_id=operation_id)
    assert reintento.estado == "ACEPTADO"
    assert len(entorno.reglas_de_descuento()) == 1
    assert entorno.cantidad("regla_descuento_alcance") == 3


def test_inv06_el_doble_envio_devuelve_el_resultado_original_y_no_duplica(
    entorno: Entorno,
) -> None:
    """Escenarios "Doble envío del alta" y "Mismo identificador con otro contenido" (SYN-02)."""
    operation_id = uuid4()

    primero = entorno.enviar(CREAR, regla_valida(), operation_id=operation_id)
    segundo = entorno.enviar(CREAR, regla_valida(), operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.reglas_de_descuento()) == 1
    assert len(entorno.auditorias(CREAR)) == 1
    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(CREAR, regla_valida(umbral="10"), operation_id=operation_id)
    assert entorno.reglas_de_descuento()[0].umbral == Decimal("20")


def test_el_alta_es_solo_online(entorno: Entorno) -> None:
    """Escenario "El alta no se acepta sin conexión"."""
    item = ItemLote(
        operation_id=uuid4(),
        tipo=CREAR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=regla_valida(),
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )

    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert entorno.reglas_de_descuento() == []
