"""Change 16, tarea 12.4: `descuentos/service.py::evaluar_descuento_manual`, de punta a punta sobre
la base y sin HTTP (spec `descuentos/descuento-manual`, requisitos "El descuento manual exige que
la organización lo habilite y el permiso del usuario" y "El tope del rol decide si el descuento
manual necesita autorización").

El servicio resuelve por `identidad/service.py` la configuración de la organización, los permisos
vigentes y el tope aplicable del usuario, y los permisos del autorizador. Solo lee y decide: no
escribe ninguna fila, tampoco de auditoría (`design.md` D12, D20).

Reglas citadas: DSC-06, TR-10, INV-21, SEG-06, SEG-07, `design.md` D11, D12, D13, D14, D20.
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from descuentos_utiles import MOMENTO, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.modules.descuentos import service as descuentos_service
from app.modules.descuentos.domain.errores import RecursoNoEncontradoError
from app.modules.identidad import repository as identidad_repository

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

DM = "DESCUENTO_MANUAL"
AU = "AUTORIZAR_DESCUENTO"


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    e = Entorno(db_session)
    _configurar(e.sesion, e.org, habilitado=True)
    return e


def _configurar(
    sesion: Session, org: UUID, *, habilitado: bool, motivo_obligatorio: bool | None = None
) -> None:
    sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET descuento_manual_habilitado = :h, "
            "motivo_obligatorio_descuento = :m WHERE organizacion_id = :o"
        ),
        {"h": habilitado, "m": motivo_obligatorio, "o": org},
    )


def _usuario(
    entorno: Entorno,
    *,
    permisos: frozenset[str],
    tope_rol: str = "0",
    tope_propio: str | None = None,
    org: UUID | None = None,
    estado: str = "ACTIVO",
) -> UUID:
    organizacion = org or entorno.org
    rol = identidad_repository.crear_rol(
        organizacion,
        entorno.sesion,
        rol_id=nuevo_id(),
        nombre=f"Rol {uuid4().hex[:6]}",
        tope_descuento=Decimal(tope_rol),
        activo=True,
        momento=MOMENTO,
    )
    for codigo in sorted(permisos):
        identidad_repository.asignar_permiso_a_rol(
            organizacion, entorno.sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    usuario = identidad_repository.crear_usuario(
        organizacion,
        entorno.sesion,
        usuario_id=nuevo_id(),
        usuario=f"u-{uuid4().hex[:8]}",
        nombre="Persona de prueba",
        email=None,
        password_hash="hash",
        rol_id=rol.id,
        estado=estado,
        momento=MOMENTO,
        tope_descuento_override=None if tope_propio is None else Decimal(tope_propio),
    )
    return usuario.id


def _evaluar(
    entorno: Entorno,
    usuario: UUID,
    porcentaje: str,
    *,
    motivo: str | None = None,
    autorizador: UUID | None = None,
    org: UUID | None = None,
):  # type: ignore[no-untyped-def]
    return descuentos_service.evaluar_descuento_manual(
        org or entorno.org,
        entorno.sesion,
        usuario_id=usuario,
        porcentaje_maximo=Decimal(porcentaje),
        motivo=motivo,
        autorizador_id=autorizador,
    )


def _codigo_de(entorno: Entorno, *args, **kwargs) -> str:  # type: ignore[no-untyped-def]
    with pytest.raises(Exception) as error:  # noqa: B017 (se afirma el código)
        _evaluar(entorno, *args, **kwargs)
    return error.value.codigo  # type: ignore[attr-defined,no-any-return]


# --- el tope aplicable sale de la base ------------------------------------------------------------


def test_vendedor_con_el_tope_del_rol(entorno: Entorno) -> None:
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")

    resultado = _evaluar(entorno, vendedor, "0.030000")

    assert resultado.tope_aplicado == Decimal("0.050000")
    assert (resultado.requirio_autorizacion, resultado.resolucion) == (False, "DENTRO_DEL_TOPE")
    assert resultado.autorizador_id is None


def test_el_tope_propio_manda_sobre_el_del_rol(entorno: Entorno) -> None:
    vendedor = _usuario(
        entorno, permisos=frozenset({DM}), tope_rol="0.050000", tope_propio="0.080000"
    )

    resultado = _evaluar(entorno, vendedor, "0.070000")

    assert resultado.tope_aplicado == Decimal("0.080000")
    assert resultado.resolucion == "DENTRO_DEL_TOPE"


def test_supervisora_con_permiso_propio(entorno: Entorno) -> None:
    supervisora = _usuario(entorno, permisos=frozenset({DM, AU}), tope_rol="0.100000")

    resultado = _evaluar(entorno, supervisora, "0.150000")

    assert resultado.resolucion == "PERMISO_PROPIO"
    assert resultado.autorizador_id == str(supervisora)
    assert resultado.requirio_autorizacion is True


def test_administrador_sin_tope(entorno: Entorno) -> None:
    administrador = _usuario(entorno, permisos=frozenset({DM, AU}), tope_rol="1.000000")

    resultado = _evaluar(entorno, administrador, "0.400000")

    assert (resultado.tope_aplicado, resultado.requirio_autorizacion) == (Decimal("1"), False)


def test_plantilla_con_tope_cero_pide_autorizacion(entorno: Entorno) -> None:
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.000000")

    assert _codigo_de(entorno, vendedor, "0.010000") == "AUTORIZACION_REQUERIDA"


# --- autorizador ------------------------------------------------------------------------------


def test_supervisora_autoriza_y_no_la_limita_su_propio_tope(entorno: Entorno) -> None:
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")
    supervisora = _usuario(entorno, permisos=frozenset({DM, AU}), tope_rol="0.100000")

    resultado = _evaluar(entorno, vendedor, "0.200000", autorizador=supervisora)

    assert resultado.resolucion == "AUTORIZADO_POR_SUPERVISOR"
    assert resultado.autorizador_id == str(supervisora)
    assert resultado.tope_aplicado == Decimal("0.050000")


def test_autorizador_sin_permiso(entorno: Entorno) -> None:
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")
    otro = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")

    assert _codigo_de(entorno, vendedor, "0.100000", autorizador=otro) == "AUTORIZADOR_SIN_PERMISO"


def test_autorizador_de_otra_organizacion_no_se_encuentra(
    entorno: Entorno, db_session: Session
) -> None:
    """INV-21, SEG-07: la Supervisora de la organización B no existe para la A."""
    otra = Entorno(db_session)
    supervisora_b = _usuario(otra, permisos=frozenset({DM, AU}), tope_rol="0.100000")
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")

    with pytest.raises(RecursoNoEncontradoError):
        _evaluar(entorno, vendedor, "0.100000", autorizador=supervisora_b)


def test_autorizador_inexistente_no_se_encuentra(entorno: Entorno) -> None:
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")

    with pytest.raises(RecursoNoEncontradoError):
        _evaluar(entorno, vendedor, "0.100000", autorizador=uuid4())


def test_autorizador_inactivo_no_autoriza(entorno: Entorno) -> None:
    """Un usuario inactivo no tiene permisos vigentes (misma regla que la sesión)."""
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")
    supervisora = _usuario(entorno, permisos=frozenset({DM, AU}), estado="INACTIVO")

    assert (
        _codigo_de(entorno, vendedor, "0.100000", autorizador=supervisora)
        == "AUTORIZADOR_SIN_PERMISO"
    )


# --- habilitación, permiso y motivo -------------------------------------------------------------


def test_organizacion_deshabilitada(entorno: Entorno) -> None:
    _configurar(entorno.sesion, entorno.org, habilitado=False)
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")

    assert _codigo_de(entorno, vendedor, "0.030000") == "DESCUENTO_MANUAL_DESHABILITADO"


def test_usuario_sin_el_permiso(entorno: Entorno) -> None:
    administracion = _usuario(entorno, permisos=frozenset({"ADMIN_USUARIOS"}), tope_rol="0.050000")

    assert _codigo_de(entorno, administracion, "0.030000") == "PERMISO_REQUERIDO"


def test_motivo_obligatorio_y_ausente_y_presente(entorno: Entorno) -> None:
    _configurar(entorno.sesion, entorno.org, habilitado=True, motivo_obligatorio=True)
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")

    assert _codigo_de(entorno, vendedor, "0.030000") == "MOTIVO_REQUERIDO"
    assert _evaluar(entorno, vendedor, "0.030000", motivo="Cliente frecuente").resolucion == (
        "DENTRO_DEL_TOPE"
    )


def test_parametro_de_motivo_sin_definir_no_exige_motivo(entorno: Entorno) -> None:
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")

    assert _evaluar(entorno, vendedor, "0.030000").resolucion == "DENTRO_DEL_TOPE"


def test_usuario_de_otra_organizacion_no_se_encuentra(
    entorno: Entorno, db_session: Session
) -> None:
    otra = Entorno(db_session)
    vendedor_b = _usuario(otra, permisos=frozenset({DM}), tope_rol="0.050000")

    with pytest.raises(RecursoNoEncontradoError):
        _evaluar(entorno, vendedor_b, "0.030000")


# --- una evaluación por venta (D11, D12) ---------------------------------------------------


def test_una_sola_autorizacion_cubre_la_venta_con_general_y_una_linea_sobre_el_tope(
    entorno: Entorno,
) -> None:
    """General 5% y una línea propia de 10%: el máximo que entrega el motor es 10%; una sola
    llamada con una sola autorizadora resuelve toda la venta."""
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")
    supervisora = _usuario(entorno, permisos=frozenset({DM, AU}), tope_rol="0.100000")
    maximo = descuentos_service.calcular_descuentos(
        [
            descuentos_service.LineaVenta(
                "a", Decimal("135240.00"), 1, 1, "p1", "c", "m", Decimal("0.100000")
            ),
            descuentos_service.LineaVenta("b", Decimal("84280.00"), 1, 1, "p2", "c", "m", None),
        ],
        [],
        Decimal("0.050000"),
    ).porcentaje_manual_maximo
    assert maximo == Decimal("0.100000")

    assert _codigo_de(entorno, vendedor, str(maximo)) == "AUTORIZACION_REQUERIDA"
    resultado = _evaluar(entorno, vendedor, str(maximo), autorizador=supervisora)
    assert resultado.resolucion == "AUTORIZADO_POR_SUPERVISOR"


# --- solo lee (D12) -------------------------------------------------------------------------------


def test_la_evaluacion_no_escribe_ninguna_fila(entorno: Entorno) -> None:
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.050000")
    supervisora = _usuario(entorno, permisos=frozenset({DM, AU}), tope_rol="0.100000")
    entorno.sesion.flush()
    antes = _filas_de_negocio(entorno)

    _evaluar(entorno, vendedor, "0.100000", autorizador=supervisora)
    _evaluar(entorno, vendedor, "0.030000")
    for porcentaje in ("0.100000",):
        _codigo_de(entorno, vendedor, porcentaje)
    entorno.sesion.flush()

    assert _filas_de_negocio(entorno) == antes
    assert antes["auditoria"] == _auditorias(entorno)


def _auditorias(entorno: Entorno) -> int:
    return int(
        entorno.sesion.execute(
            text("SELECT count(*) FROM auditoria WHERE organizacion_id = :o"), {"o": entorno.org}
        ).scalar_one()
    )


def _filas_de_negocio(entorno: Entorno) -> dict[str, int]:
    tablas = ("auditoria", "comando", "usuario", "rol", "rol_permiso")
    return {
        tabla: int(
            entorno.sesion.execute(
                text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"),  # noqa: S608
                {"o": entorno.org},
            ).scalar_one()
        )
        for tabla in tablas
    }


def test_el_servidor_evalua_con_los_datos_vigentes_y_no_con_lo_que_dijo_el_dispositivo(
    entorno: Entorno,
) -> None:
    """Escenario "El servidor no confía en la evaluación del dispositivo" (TR-10, SEG-06): la
    evaluación no recibe ningún resultado del dispositivo y llega a su propio resultado con el
    tope vigente de la base; si el tope bajó desde que el dispositivo lo dio por permitido, el
    servidor lo rechaza."""
    vendedor = _usuario(entorno, permisos=frozenset({DM}), tope_rol="0.100000")
    assert _evaluar(entorno, vendedor, "0.080000").resolucion == "DENTRO_DEL_TOPE"

    entorno.sesion.execute(
        text(
            "UPDATE rol SET tope_descuento = 0.050000 WHERE organizacion_id = :o AND id = "
            "(SELECT rol_id FROM usuario WHERE organizacion_id = :o AND id = :u)"
        ),
        {"o": entorno.org, "u": vendedor},
    )

    assert _codigo_de(entorno, vendedor, "0.080000") == "AUTORIZACION_REQUERIDA"
    parametros = set(inspect.signature(descuentos_service.evaluar_descuento_manual).parameters)
    assert parametros == {
        "organizacion_id",
        "sesion",
        "usuario_id",
        "porcentaje_maximo",
        "motivo",
        "autorizador_id",
    }
