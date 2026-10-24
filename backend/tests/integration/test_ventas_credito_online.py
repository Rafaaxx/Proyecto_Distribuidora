"""Tarea 8.2 (change 18b; spec `ventas/credito-en-la-venta`; `design.md` D5, D6, D17, D18):
`VENTA_CONFIRMAR` v1 con conexión evalúa el crédito del cliente con el saldo bloqueado, aplica la
política (ADVERTIR, AUTORIZAR, BLOQUEAR) y congela la evaluación en la venta, contra PostgreSQL
real.

Ejemplo de `01` §9.2: límite $200.000, saldo $150.000, venta $80.000 con cobranza $20.000 ->
saldo resultante $210.000 y exceso $10.000. La venta son 8 unidades de un producto a $10.000.

Reglas citadas: CRE-01 a CRE-05, CRE-07, CRE-10, CLI-03, VTA-11, INV-01, INV-10.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import EntornoVenta

from app.commands.credenciales import CredencialDePin
from app.core.errors import DomainError

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

PIN = "482913"
EVALUACION_DEL_EJEMPLO = {
    "limite": "200000.00",
    "saldo_considerado": "150000.00",
    "disponible": "50000.00",
    "exceso": "10000.00",
}


@pytest.fixture
def entorno(db_session: Session) -> EntornoVenta:
    return EntornoVenta(db_session)


class Escenario:
    """El ejemplo de la regla con la política que se pida."""

    def __init__(self, entorno: EntornoVenta, politica: str, *, limite: str | None = "200000.00"):
        self.entorno = entorno
        entorno.datos_de_credito(limite=limite, politica=politica)
        self.producto_id, self.presentacion_id = entorno.producto_a("10000.00")

    def contenido(self, *, cobranza: str | None = "20000.00", **cambios: Any) -> dict[str, Any]:
        linea = self.entorno.linea(
            self.producto_id,
            self.presentacion_id,
            cantidad=8,
            precio="10000.00",
            unidades_referencia=1,
        )
        medios = (
            {}
            if cobranza is None
            else {"cobranza": self.entorno.cobranza((self.entorno.efectivo_id, cobranza, None))}
        )
        return self.entorno.contenido(linea, **medios, **cambios)

    def vender(
        self,
        *,
        cobranza: str | None = "20000.00",
        credenciales: tuple[CredencialDePin, ...] = (),
        **cambios: Any,
    ) -> Any:
        return self.entorno.enviar(
            self.contenido(cobranza=cobranza, **cambios), credenciales=credenciales
        )

    def rechazo(
        self,
        *,
        cobranza: str | None = "20000.00",
        credenciales: tuple[CredencialDePin, ...] = (),
        **cambios: Any,
    ) -> DomainError:
        with pytest.raises(DomainError) as error:
            self.vender(cobranza=cobranza, credenciales=credenciales, **cambios)
        return error.value


def _sin_efectos(entorno: EntornoVenta) -> None:
    entorno.sin_efectos_de_venta(stock_esperado=48)


# --- la evaluación (CRE-01, CRE-02, CRE-03) y lo que congela la venta (CRE-10) --------------------


def test_cre02_el_ejemplo_de_la_regla_congela_la_evaluacion_de_advertir_aceptada(
    entorno: EntornoVenta,
) -> None:
    escenario = Escenario(entorno, "ADVERTIR")

    comando = escenario.vender(credito={"acepta_exceso": True})

    assert comando.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    assert (venta.credito_limite, venta.credito_saldo_considerado) == (
        Decimal("200000.00"),
        Decimal("150000.00"),
    )
    assert (venta.credito_disponible, venta.credito_exceso) == (
        Decimal("50000.00"),
        Decimal("10000.00"),
    )
    assert (venta.credito_politica, venta.credito_resolucion) == (
        "ADVERTIR",
        "ADVERTENCIA_ACEPTADA",
    )
    assert venta.credito_autorizador_id is None
    assert "EXCESO_CREDITO_ADVERTIDO" in entorno.observaciones()
    assert entorno.saldo() == Decimal("210000.00")


def test_cre04_advertir_sin_aceptar_se_rechaza_con_la_evaluacion_del_servidor(
    entorno: EntornoVenta,
) -> None:
    escenario = Escenario(entorno, "ADVERTIR")

    error = escenario.rechazo()

    assert (error.codigo, error.status_http) == ("EXCESO_CREDITO_SIN_ACEPTAR", 409)
    assert error.extension == {**EVALUACION_DEL_EJEMPLO, "politica": "ADVERTIR"}
    _sin_efectos(entorno)


def test_cre03_la_politica_de_la_organizacion_se_hereda_si_el_cliente_no_tiene(
    entorno: EntornoVenta,
) -> None:
    """Cliente sin política propia, organización con BLOQUEAR: rige BLOQUEAR."""
    entorno.configurar(politica_credito_default="BLOQUEAR")
    escenario = Escenario(entorno, "BLOQUEAR")
    entorno.datos_de_credito(limite="200000.00", politica=None)

    error = escenario.rechazo()

    assert error.codigo == "CREDITO_EXCEDIDO"
    assert error.extension["politica"] == "BLOQUEAR"  # type: ignore[index]


def test_cre07_una_venta_cobrada_entera_de_un_cliente_excedido_no_tiene_exceso(
    db_session: Session,
) -> None:
    """Saldo $210.000 con límite $200.000 y política BLOQUEAR: una venta de $30.000 cobrada
    entera se confirma, con disponible negativo y exceso cero."""
    entorno = EntornoVenta(db_session, saldo_inicial="210000.00")
    escenario = Escenario(entorno, "BLOQUEAR")
    producto_id, presentacion_id = escenario.producto_id, escenario.presentacion_id

    entorno.enviar(
        entorno.contenido(
            entorno.linea(
                producto_id, presentacion_id, cantidad=3, precio="10000.00", unidades_referencia=1
            ),
            cobranza=entorno.cobranza((entorno.efectivo_id, "30000.00", None)),
        )
    )

    (venta,) = entorno.ventas()
    assert (venta.credito_disponible, venta.credito_exceso) == (
        Decimal("-10000.00"),
        Decimal("0.00"),
    )
    assert venta.credito_resolucion == "SIN_EXCESO"
    assert entorno.saldo() == Decimal("210000.00")


def test_cre01_un_cliente_sin_limite_no_tiene_control_y_congela_el_saldo(
    entorno: EntornoVenta,
) -> None:
    escenario = Escenario(entorno, "BLOQUEAR", limite=None)

    escenario.vender(cobranza=None)

    (venta,) = entorno.ventas()
    assert (venta.credito_limite, venta.credito_disponible, venta.credito_exceso) == (
        None,
        None,
        None,
    )
    assert venta.credito_saldo_considerado == Decimal("150000.00")
    assert (venta.credito_politica, venta.credito_resolucion) == ("BLOQUEAR", "SIN_EXCESO")
    assert entorno.saldo() == Decimal("230000.00")


def test_cre10_sin_exceso_dentro_del_limite_congela_la_evaluacion(entorno: EntornoVenta) -> None:
    """Triangula: límite holgado, sin exceso y sin autorizador."""
    escenario = Escenario(entorno, "AUTORIZAR", limite="400000.00")

    escenario.vender()

    (venta,) = entorno.ventas()
    assert (venta.credito_disponible, venta.credito_exceso) == (
        Decimal("250000.00"),
        Decimal("0.00"),
    )
    assert (venta.credito_resolucion, venta.credito_autorizador_id) == ("SIN_EXCESO", None)
    assert "EXCESO_CREDITO_ADVERTIDO" not in entorno.observaciones()


def test_cre10_el_snapshot_no_cambia_cuando_cambia_el_limite(entorno: EntornoVenta) -> None:
    escenario = Escenario(entorno, "ADVERTIR")
    escenario.vender(credito={"acepta_exceso": True})

    entorno.datos_de_credito(limite="300000.00", politica="BLOQUEAR")

    (venta,) = entorno.ventas()
    assert (venta.credito_limite, venta.credito_politica) == (Decimal("200000.00"), "ADVERTIR")


# --- AUTORIZAR (CRE-05) ----------------------------------------------------------------------


def test_cre05_autorizar_con_permiso_propio(entorno: EntornoVenta) -> None:
    entorno.permitir("SUPERAR_CREDITO")
    escenario = Escenario(entorno, "AUTORIZAR")

    escenario.vender()

    (venta,) = entorno.ventas()
    assert venta.credito_resolucion == "PERMISO_PROPIO"
    assert venta.credito_autorizador_id == entorno.usuario_id
    assert venta.credito_exceso == Decimal("10000.00")


def test_cre05_autorizar_con_el_pin_de_un_supervisor(entorno: EntornoVenta) -> None:
    marta = entorno.crear_usuario(frozenset({"SUPERAR_CREDITO"}), pin=PIN)
    escenario = Escenario(entorno, "AUTORIZAR")

    escenario.vender(
        credito={"autorizador_id": str(marta)}, credenciales=(entorno.credencial(marta, PIN),)
    )

    (venta,) = entorno.ventas()
    assert (venta.credito_resolucion, venta.credito_autorizador_id) == ("PIN_SUPERVISOR", marta)
    assert entorno.intentos_de_pin() == 0


def test_cre05_autorizar_sin_autorizacion_se_rechaza_con_la_evaluacion(
    entorno: EntornoVenta,
) -> None:
    error = Escenario(entorno, "AUTORIZAR").rechazo()

    assert (error.codigo, error.status_http) == ("AUTORIZACION_CREDITO_REQUERIDA", 403)
    assert error.extension == {**EVALUACION_DEL_EJEMPLO, "politica": "AUTORIZAR"}
    _sin_efectos(entorno)


def test_cre05_un_autorizador_sin_superar_credito_se_rechaza_sin_contar_intento(
    entorno: EntornoVenta,
) -> None:
    sin_permiso = entorno.crear_usuario(frozenset({"AUTORIZAR_DESCUENTO"}), pin=PIN)
    escenario = Escenario(entorno, "AUTORIZAR")

    error = escenario.rechazo(
        credito={"autorizador_id": str(sin_permiso)},
        credenciales=(entorno.credencial(sin_permiso, PIN),),
    )

    assert (error.codigo, error.status_http) == ("AUTORIZADOR_SIN_PERMISO", 403)
    assert entorno.intentos_de_pin() == 0
    _sin_efectos(entorno)


# --- BLOQUEAR (CRE-07) ---------------------------------------------------------------------


def test_cre07_bloquear_rechaza_aunque_se_tenga_superar_credito(entorno: EntornoVenta) -> None:
    entorno.permitir("SUPERAR_CREDITO")
    escenario = Escenario(entorno, "BLOQUEAR")

    error = escenario.rechazo()

    assert (error.codigo, error.status_http) == ("CREDITO_EXCEDIDO", 409)
    assert error.extension == {**EVALUACION_DEL_EJEMPLO, "politica": "BLOQUEAR"}
    _sin_efectos(entorno)


def test_cre07_bloquear_se_resuelve_cobrando_mas(entorno: EntornoVenta) -> None:
    escenario = Escenario(entorno, "BLOQUEAR")
    assert escenario.rechazo().codigo == "CREDITO_EXCEDIDO"

    escenario.vender(cobranza="30000.00")

    (venta,) = entorno.ventas()
    assert (venta.credito_exceso, venta.credito_resolucion) == (Decimal("0.00"), "SIN_EXCESO")
    assert entorno.saldo() == Decimal("200000.00")


# --- consumidor final (CLI-03, VTA-11, D17) --------------------------------------------------


def _consumidor_final(entorno: EntornoVenta) -> UUID:
    cliente_id = entorno.crear_cliente(nombre="Consumidor final", es_consumidor_final=True)
    entorno.datos_de_credito(cliente_id, limite="0.00", politica="AUTORIZAR")
    return cliente_id


def test_vta11_el_consumidor_final_con_deuda_se_rechaza_aunque_haya_pin_de_supervisor(
    entorno: EntornoVenta,
) -> None:
    cliente_id = _consumidor_final(entorno)
    marta = entorno.crear_usuario(frozenset({"SUPERAR_CREDITO"}), pin=PIN)
    producto_id, presentacion_id = entorno.producto_a("5000.00")
    contenido = entorno.contenido(
        entorno.linea(
            producto_id, presentacion_id, cantidad=1, precio="5000.00", unidades_referencia=1
        ),
        cliente_id=str(cliente_id),
        cobranza=entorno.cobranza((entorno.efectivo_id, "3000.00", None)),
        credito={"autorizador_id": str(marta)},
    )

    with pytest.raises(DomainError) as error:
        entorno.enviar(contenido, credenciales=(entorno.credencial(marta, PIN),))

    assert error.value.codigo == "CONSUMIDOR_FINAL_CONTADO"
    assert entorno.intentos_de_pin() == 0
    assert entorno.ventas() == []


def test_cli03_el_consumidor_final_de_contado_congela_el_limite_cero(
    entorno: EntornoVenta,
) -> None:
    cliente_id = _consumidor_final(entorno)
    producto_id, presentacion_id = entorno.producto_a("5000.00")

    entorno.enviar(
        entorno.contenido(
            entorno.linea(
                producto_id, presentacion_id, cantidad=1, precio="5000.00", unidades_referencia=1
            ),
            cliente_id=str(cliente_id),
            cobranza=entorno.cobranza((entorno.efectivo_id, "5000.00", None)),
        )
    )

    (venta,) = entorno.ventas()
    assert (venta.credito_limite, venta.credito_exceso) == (Decimal("0.00"), Decimal("0.00"))
    assert (venta.credito_saldo_considerado, venta.credito_resolucion) == (
        Decimal("0.00"),
        "SIN_EXCESO",
    )
