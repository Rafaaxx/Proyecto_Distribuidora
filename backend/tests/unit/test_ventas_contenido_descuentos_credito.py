"""Tarea 7.1 (change 18b; `design.md` D1, D2; spec `ventas/descuentos-en-la-venta`): el contenido
de `VENTA_CONFIRMAR` v1 acepta los campos opcionales de descuentos y crédito (importes y
porcentajes como texto, INV-03; `extra="forbid"`), y un contenido sin ellos conserva su huella.

Reglas citadas: DSC-08, DSC-09, INV-03, INV-06, SYN-02.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.commands.huella import calcular_huella
from app.modules.ventas.commands import VentaConfirmarContenidoV1
from app.modules.ventas.schemas import VentaConfirmarRequest, armar_contenido_de_venta


def _linea(**cambios: Any) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "linea_id": str(uuid4()),
        "producto_id": str(uuid4()),
        "presentacion_id": str(uuid4()),
        "cantidad": 15,
        "lista_version_id": str(uuid4()),
        "precio_referencia": "12500.00",
        "unidades_referencia": 6,
        "importe_bruto": "31250.00",
    }
    cuerpo.update(cambios)
    return cuerpo


def _contenido(**cambios: Any) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "venta_id": str(uuid4()),
        "numero": "C01-000001",
        "cliente_id": str(uuid4()),
        "lineas": [_linea()],
        "total": "31250.00",
    }
    cuerpo.update(cambios)
    return cuerpo


def test_d1_un_contenido_sin_los_campos_nuevos_sigue_valiendo() -> None:
    contenido = VentaConfirmarContenidoV1.model_validate(_contenido())

    assert contenido.descuento_manual_general is None
    assert contenido.motivo_descuento_id is None
    assert contenido.descuento_autorizador_id is None
    assert contenido.credito is None
    assert contenido.lineas[0].descuento_manual is None
    assert contenido.lineas[0].descuentos == []


def test_d1_acepta_los_descuentos_y_el_credito_como_texto() -> None:
    regla = uuid4()
    motivo = uuid4()
    autorizador = uuid4()
    contenido = VentaConfirmarContenidoV1.model_validate(
        _contenido(
            descuento_manual_general="0.050000",
            motivo_descuento_id=str(motivo),
            descuento_autorizador_id=str(autorizador),
            credito={"acepta_exceso": True, "autorizador_id": str(autorizador)},
            lineas=[
                _linea(
                    descuento_manual="0.100000",
                    descuentos=[
                        {
                            "origen": "AUTOMATICO",
                            "regla_id": str(regla),
                            "porcentaje": "0.050000",
                            "importe": "1562.50",
                        },
                        {
                            "origen": "MANUAL",
                            "regla_id": None,
                            "porcentaje": "0.100000",
                            "importe": "2968.75",
                        },
                    ],
                )
            ],
        )
    )

    assert contenido.descuento_manual_general == "0.050000"
    assert contenido.motivo_descuento_id == motivo
    assert contenido.credito is not None
    assert contenido.credito.acepta_exceso is True
    assert contenido.credito.autorizador_id == autorizador
    (linea,) = contenido.lineas
    assert linea.descuento_manual == "0.100000"
    assert [d.origen for d in linea.descuentos] == ["AUTOMATICO", "MANUAL"]
    assert linea.descuentos[0].regla_id == regla
    assert linea.descuentos[1].importe == "2968.75"


def test_d1_el_credito_sin_conexion_trae_la_evaluacion_del_dispositivo_como_texto() -> None:
    contenido = VentaConfirmarContenidoV1.model_validate(
        _contenido(
            credito={
                "limite": "200000.00",
                "saldo_considerado": "150000.00",
                "politica": "AUTORIZAR",
                "resolucion": "TOLERANCIA_OFFLINE",
            }
        )
    )

    assert contenido.credito is not None
    assert contenido.credito.limite == "200000.00"
    assert contenido.credito.saldo_considerado == "150000.00"
    assert contenido.credito.acepta_exceso is False


@pytest.mark.parametrize(
    "cambios",
    [
        pytest.param({"descuento_manual_general": 0.05}, id="porcentaje-general-como-numero"),
        pytest.param({"descuento_manual_general": "cinco"}, id="porcentaje-general-no-decimal"),
        pytest.param({"credito": {"limite": 200000.0}}, id="limite-como-numero"),
        pytest.param({"credito": {"acepta_exceso": "si"}}, id="acepta-exceso-no-booleano"),
        pytest.param({"credito": {"pin": "123456"}}, id="el-pin-no-entra-al-contenido"),
        pytest.param({"credenciales": []}, id="credenciales-fuera-del-contenido"),
        pytest.param({"autorizador_id": str(uuid4())}, id="campo-extra-de-cabecera"),
    ],
)
def test_d1_rechaza_lo_que_no_es_texto_o_no_esta_en_el_contrato(cambios: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        VentaConfirmarContenidoV1.model_validate(_contenido(**cambios))


@pytest.mark.parametrize(
    "cambios",
    [
        pytest.param({"descuento_manual": 0.1}, id="porcentaje-propio-como-numero"),
        pytest.param(
            {
                "descuentos": [
                    {"origen": "AUTOMATICO", "regla_id": None, "porcentaje": "0.05", "importe": 1.5}
                ]
            },
            id="importe-como-numero",
        ),
        pytest.param(
            {"descuentos": [{"origen": "OTRO", "regla_id": None, "importe": "1.00"}]},
            id="origen-fuera-de-catalogo",
        ),
        pytest.param(
            {"descuentos": [{"origen": "MANUAL", "regla_id": None, "importe": "1.00", "x": 1}]},
            id="campo-extra-de-descuento",
        ),
    ],
)
def test_d1_rechaza_descuentos_de_linea_mal_formados(cambios: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        VentaConfirmarContenidoV1.model_validate(_contenido(lineas=[_linea(**cambios)]))


# --- la huella de un contenido sin los campos nuevos no cambia (INV-06, SYN-02) ----------------


def test_d1_la_huella_de_un_contenido_sin_campos_nuevos_es_la_de_antes() -> None:
    cuerpo = _contenido()
    peticion = VentaConfirmarRequest.model_validate(cuerpo)

    armado = armar_contenido_de_venta(peticion)

    antes = {
        "venta_id": cuerpo["venta_id"],
        "numero": cuerpo["numero"],
        "cliente_id": cuerpo["cliente_id"],
        "ubicacion_id": None,
        "lista_id": None,
        "lista_version_id": None,
        "motivo_lista_id": None,
        "lineas": cuerpo["lineas"],
        "total": cuerpo["total"],
        "cobranza": None,
    }
    assert armado == antes
    assert calcular_huella(armado) == calcular_huella(antes)


def test_d1_con_campos_nuevos_la_huella_los_incluye_y_las_credenciales_no() -> None:
    autorizador = uuid4()
    cuerpo = _contenido(
        descuento_manual_general="0.050000",
        descuento_autorizador_id=str(autorizador),
        credito={"acepta_exceso": True},
        credenciales=[{"autorizador_id": str(autorizador), "pin": "482913"}],
    )

    armado = armar_contenido_de_venta(VentaConfirmarRequest.model_validate(cuerpo))

    assert armado["descuento_manual_general"] == "0.050000"
    assert armado["descuento_autorizador_id"] == str(autorizador)
    assert armado["credito"] == {"acepta_exceso": True}
    assert "credenciales" not in armado
    assert "482913" not in str(armado)
    VentaConfirmarContenidoV1.model_validate(armado)  # es válido para el handler (forbid)
    sin_campos = armar_contenido_de_venta(VentaConfirmarRequest.model_validate(_contenido()))
    assert calcular_huella(armado) != calcular_huella(sin_campos)


def test_d1_los_descuentos_de_linea_viajan_en_el_contenido_armado() -> None:
    regla = uuid4()
    descuento = {
        "origen": "AUTOMATICO",
        "regla_id": str(regla),
        "porcentaje": "0.050000",
        "importe": "1562.50",
    }
    cuerpo = _contenido(lineas=[_linea(descuento_manual="0.100000", descuentos=[descuento])])

    armado = armar_contenido_de_venta(VentaConfirmarRequest.model_validate(cuerpo))

    (linea,) = armado["lineas"]
    assert linea["descuento_manual"] == "0.100000"
    assert linea["descuentos"] == [descuento]
    VentaConfirmarContenidoV1.model_validate(armado)
