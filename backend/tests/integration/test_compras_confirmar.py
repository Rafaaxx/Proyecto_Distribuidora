"""Change 11, tareas 5.1, 5.2 y 5.4: `COMPRA_CONFIRMAR` v1 (compra a crédito) por el bus,
contra PostgreSQL real.

Se procesa por `sync_service.procesar_comando`, que maneja la transacción (mismo
criterio que `test_stock_comandos.py`). La cobertura HTTP es de `test_compras_api.py`.

Reglas citadas: CMP-01, CMP-02, CMP-03, CMP-04, CMP-08, CST-11, INV-01, INV-04, INV-06,
INV-07, INV-12, INV-13, INV-18, INV-21, SYN-02, SEG-06, AUD-01, ADR-022 y `design.md`
D1, D4, D5, D6, D7, D10, D12, D14, D16.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from compras_utiles import CONFIRMAR, MOMENTO, RELOJ, Entorno
from cuentas_corrientes_utiles import (
    crear_proveedor,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_presentacion_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
    desactivar_producto_sql,
)

from app.commands.errores import ComandoInconsistenteError
from app.core.errors import DomainError, PermisoRequeridoError
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.errores import UnidadesCongeladasError
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.proveedores import service as proveedores_service
from app.modules.proveedores.domain.lote import CostoDelLote
from app.modules.proveedores.models import CostoInformado
from app.modules.stock import service as stock_service
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- escenario del criterio 2 (CMP-01, CMP-02, CMP-03) -------------------------------------


def test_compra_a_credito_de_vino_por_caja_y_cerveza_por_unidad(entorno: Entorno) -> None:
    """`00` §9 criterio 2: stock, promedio y deuda correctos."""
    comando = entorno.enviar()

    (compra,) = entorno.compras()
    assert compra.estado == "CONFIRMADA"
    assert compra.condicion == "CREDITO"
    assert compra.total_neto == Decimal("126000.00")
    assert compra.total_factura == Decimal("152460.00")
    assert compra.fecha == date(2026, 5, 10)
    assert compra.ubicacion_id == entorno.deposito_id
    assert compra.usuario_id == entorno.usuario_id
    assert compra.operation_id == comando.operation_id

    assert entorno.saldo(entorno.vino_id) == 60
    assert entorno.saldo(entorno.cerveza_id) == 60
    assert entorno.promedio(entorno.vino_id) == Decimal("1000.000000")
    assert entorno.promedio(entorno.cerveza_id) == Decimal("1100.000000")

    movimientos = entorno.movimientos_de_stock()
    assert [(m.tipo, m.cantidad_base, m.costo_unitario) for m in movimientos] == [
        ("COMPRA", 60, Decimal("1000.000000")),
        ("COMPRA", 60, Decimal("1100.000000")),
    ]
    assert {m.origen_id for m in movimientos} == {compra.id}
    assert {m.origen_tipo for m in movimientos} == {"COMPRA"}

    (movimiento_de_cuenta,) = entorno.movimientos_de_cuenta()
    assert movimiento_de_cuenta.tipo == "COMPRA"
    assert movimiento_de_cuenta.sentido == "AUMENTA"
    assert movimiento_de_cuenta.importe == Decimal("152460.00")
    assert movimiento_de_cuenta.origen_id == compra.id
    assert movimiento_de_cuenta.occurred_at == MOMENTO
    assert entorno.saldo_de_cuenta() == Decimal("152460.00")

    assert comando.resultado is not None
    assert comando.resultado["compra_id"] == str(compra.id)
    assert comando.resultado["total_neto"] == "126000.00"
    assert comando.resultado["total_factura"] == "152460.00"
    assert comando.resultado["pago_id"] is None


def test_las_lineas_congelan_unidades_alicuota_y_derivados(entorno: Entorno) -> None:
    """CMP-02, INV-18, `design.md` D12: la línea guarda lo calculado."""
    entorno.enviar()

    vino, cerveza = entorno.lineas()
    assert (vino.orden, vino.producto_id, vino.presentacion_id) == (
        1,
        entorno.vino_id,
        entorno.caja_x6_id,
    )
    assert vino.unidades_presentacion == 6
    assert vino.alicuota_aplicada == Decimal("0.210000")
    assert vino.cantidad == Decimal("10.000")
    assert vino.cantidad_base == 60
    assert vino.valor_presentacion == Decimal("6000.00")
    assert vino.costo_base == Decimal("1000.000000")
    assert vino.importe_neto == Decimal("60000.00")
    assert (cerveza.orden, cerveza.unidades_presentacion, cerveza.cantidad_base) == (2, 1, 60)
    assert cerveza.costo_base == Decimal("1100.000000")
    assert cerveza.importe_neto == Decimal("66000.00")


def test_cantidad_fraccionaria_valida_ingresa_unidades_enteras(entorno: Entorno) -> None:
    entorno.enviar(
        entorno.contenido(lineas=[entorno.linea("vino", cantidad="2.5")], total_factura="18150.00")
    )

    assert entorno.saldo(entorno.vino_id) == 15
    (linea,) = entorno.lineas()
    assert linea.cantidad == Decimal("2.500")
    assert linea.cantidad_base == 15


def test_promedio_con_stock_previo_se_recalcula_con_cst11(entorno: Entorno) -> None:
    """CST-11 (`01` §6.2): 60 a 1000 y una compra de 60 a 1100 promedian 1050."""
    entorno.sembrar_stock_inicial(entorno.cerveza_id, 60, "1000.00")

    entorno.enviar(entorno.contenido(lineas=[entorno.linea("cerveza")], total_factura="79860.00"))

    assert entorno.promedio(entorno.cerveza_id) == Decimal("1050.000000")
    assert entorno.stock_total(entorno.cerveza_id) == 120
    assert entorno.saldo(entorno.cerveza_id) == 120


def test_dos_lineas_del_mismo_producto_se_aplican_en_orden(entorno: Entorno) -> None:
    """CST-11, `design.md` D5: caja y botella del mismo producto."""
    entorno.enviar(
        entorno.contenido(
            lineas=[
                entorno.linea("vino"),
                entorno.linea(
                    "vino",
                    presentacion_id=str(entorno.botella_vino_id),
                    cantidad="60",
                    valor="1100.00",
                ),
            ],
            total_factura="152460.00",
        )
    )

    assert entorno.promedio(entorno.vino_id) == Decimal("1050.000000")
    assert entorno.stock_total(entorno.vino_id) == 120
    assert entorno.saldo(entorno.vino_id) == 120
    assert [(linea.orden, linea.cantidad_base) for linea in entorno.lineas()] == [(1, 60), (2, 60)]
    assert len(entorno.historia_de_costo()) == 2


def test_inv12_inv13_el_saldo_materializado_coincide_con_el_libro(entorno: Entorno) -> None:
    entorno.enviar()

    assert stock_service.verificar_consistencia(entorno.org, entorno.sesion) == []
    assert cuentas_service.verificar_consistencia(entorno.org, entorno.sesion) == []


def test_el_total_de_factura_informado_es_la_deuda_y_no_cambia_los_promedios(
    entorno: Entorno,
) -> None:
    """D1: deuda = total de factura (aquí con una percepción); costo y promedio, netos."""
    entorno.enviar(entorno.contenido(total_factura="153720.00"))

    assert entorno.saldo_de_cuenta() == Decimal("153720.00")
    assert entorno.promedio(entorno.vino_id) == Decimal("1000.000000")
    assert entorno.promedio(entorno.cerveza_id) == Decimal("1100.000000")
    assert entorno.compras()[0].total_neto == Decimal("126000.00")


def test_la_compra_suma_a_una_deuda_previa(entorno: Entorno) -> None:
    entorno.enviar(entorno.contenido(lineas=[entorno.linea("vino")], total_factura="72600.00"))
    entorno.enviar(entorno.contenido(lineas=[entorno.linea("cerveza")], total_factura="79860.00"))

    assert entorno.saldo_de_cuenta() == Decimal("152460.00")
    assert len(entorno.movimientos_de_cuenta()) == 2


def test_se_puede_comprar_en_una_ubicacion_de_vehiculo(entorno: Entorno) -> None:
    """D16: cualquier ubicación activa, también vehículos."""
    camioneta = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre="Camioneta", tipo="VEHICULO", requiere_toma=True
    )
    entorno.sesion.commit()

    entorno.enviar(entorno.contenido(ubicacion_id=str(camioneta)))

    assert (
        stock_service.obtener_saldo(
            entorno.org, entorno.sesion, producto_id=entorno.vino_id, ubicacion_id=camioneta
        )
        == 60
    )


def test_numero_de_comprobante_y_observacion_se_guardan(entorno: Entorno) -> None:
    """D13: opcionales e informativos."""
    entorno.enviar(
        entorno.contenido(numero_comprobante="A-0003-00012345", observacion="Entrega parcial")
    )

    (compra,) = entorno.compras()
    assert compra.numero_comprobante == "A-0003-00012345"
    assert compra.observacion == "Entrega parcial"


# --- validaciones de referencias (CAT-05, CAT-06, INV-21) ------------------------------------


def test_presentacion_solo_de_venta_se_rechaza(entorno: Entorno) -> None:
    solo_venta = crear_presentacion_sql(
        entorno.sesion,
        entorno.org,
        entorno.vino_id,
        nombre="Pack venta",
        unidades_base=3,
        usar_en_compra=False,
    )
    entorno.sesion.commit()

    with pytest.raises(DomainError) as error:
        entorno.enviar(
            entorno.contenido(lineas=[entorno.linea("vino", presentacion_id=str(solo_venta))])
        )

    assert error.value.codigo == "PRESENTACION_INVALIDA"
    assert error.value.extension == {"linea": 0}
    entorno.sin_efectos()


def test_presentacion_de_otro_producto_o_inactiva_se_rechaza(entorno: Entorno) -> None:
    inactiva = crear_presentacion_sql(
        entorno.sesion,
        entorno.org,
        entorno.vino_id,
        nombre="Vieja",
        unidades_base=2,
        activo=False,
    )
    entorno.sesion.commit()

    for presentacion_id in (entorno.botella_id, inactiva):
        with pytest.raises(DomainError) as error:
            entorno.enviar(
                entorno.contenido(
                    lineas=[entorno.linea("vino", presentacion_id=str(presentacion_id))]
                )
            )
        assert error.value.codigo == "PRESENTACION_INVALIDA"
        entorno.sin_efectos()


def test_producto_de_otro_proveedor_se_rechaza(entorno: Entorno) -> None:
    """CAT-06, D4."""
    otro = crear_proveedor(entorno.sesion, entorno.org, nombre="Distribuidora Norte")
    ajeno = crear_producto_sql(entorno.sesion, entorno.org, nombre="Vino C", proveedor_id=otro)
    presentacion = crear_presentacion_sql(
        entorno.sesion, entorno.org, ajeno, nombre="Botella", unidades_base=1, es_referencia=True
    )
    entorno.sesion.commit()

    with pytest.raises(DomainError) as error:
        entorno.enviar(
            entorno.contenido(
                lineas=[
                    entorno.linea("vino"),
                    entorno.linea(
                        "vino", producto_id=str(ajeno), presentacion_id=str(presentacion)
                    ),
                ]
            )
        )

    assert error.value.codigo == "PROVEEDOR_NO_CORRESPONDE"
    assert error.value.extension == {"linea": 1}
    entorno.sin_efectos()


def test_proveedor_inactivo_se_rechaza(entorno: Entorno) -> None:
    entorno.sesion.execute(
        text("UPDATE proveedor SET activo = false WHERE id = :id"), {"id": entorno.proveedor_id}
    )
    entorno.sesion.commit()

    with pytest.raises(DomainError) as error:
        entorno.enviar()

    assert error.value.codigo == "PROVEEDOR_INACTIVO"
    entorno.sin_efectos()


def test_producto_inactivo_se_rechaza(entorno: Entorno) -> None:
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.cerveza_id)
    entorno.sesion.commit()

    with pytest.raises(DomainError) as error:
        entorno.enviar()

    assert error.value.codigo == "PRODUCTO_INACTIVO"
    assert error.value.extension == {"linea": 1}
    entorno.sin_efectos()


def test_ubicacion_inactiva_se_rechaza(entorno: Entorno) -> None:
    inactiva = crear_ubicacion_sql(entorno.sesion, entorno.org, nombre="Cerrado", activo=False)
    entorno.sesion.commit()

    with pytest.raises(DomainError) as error:
        entorno.enviar(entorno.contenido(ubicacion_id=str(inactiva)))

    assert error.value.codigo == "UBICACION_INACTIVA"
    entorno.sin_efectos()


@pytest.mark.parametrize("referencia", ["proveedor", "ubicacion", "producto", "presentacion"])
def test_inv21_una_referencia_de_otra_organizacion_responde_404(
    db_session: Session, referencia: str
) -> None:
    """INV-21, SEG-07: un recurso ajeno es 404, nunca 403 (la presentación ajena no se
    encuentra y se informa como `PRESENTACION_INVALIDA`, igual que en el change 06)."""
    propio = Entorno(db_session)
    ajeno = Entorno(db_session)
    cambios: dict[str, Any] = {}
    linea: dict[str, Any] = propio.linea("vino")
    if referencia == "proveedor":
        cambios["proveedor_id"] = str(ajeno.proveedor_id)
    elif referencia == "ubicacion":
        cambios["ubicacion_id"] = str(ajeno.deposito_id)
    elif referencia == "producto":
        linea["producto_id"] = str(ajeno.vino_id)
    else:
        linea["presentacion_id"] = str(ajeno.caja_x6_id)

    with pytest.raises(DomainError) as error:
        propio.enviar(propio.contenido(lineas=[linea], **cambios))

    if referencia == "presentacion":
        # Mismo criterio que `COSTO_INFORMAR` (change 06): la presentación ajena no se
        # encuentra y se trata como una inválida; no confirma ni niega la fila ajena.
        assert error.value.codigo == "PRESENTACION_INVALIDA"
    else:
        assert error.value.status_http == 404
    propio.sin_efectos()


def test_fecha_posterior_a_hoy_se_rechaza(entorno: Entorno) -> None:
    """D6: mañana, en la zona de la organización."""
    with pytest.raises(DomainError) as error:
        entorno.enviar(entorno.contenido(fecha="2026-05-11"))

    assert error.value.codigo == "FECHA_INVALIDA"
    entorno.sin_efectos()


def test_una_fecha_anterior_es_valida_y_los_movimientos_usan_el_momento_del_comando(
    entorno: Entorno,
) -> None:
    """D6: la `fecha` es la del comprobante; stock y cuenta, el `occurred_at`."""
    entorno.enviar(entorno.contenido(fecha="2026-04-28"))

    assert entorno.compras()[0].fecha == date(2026, 4, 28)
    assert {m.occurred_at for m in entorno.movimientos_de_stock()} == {MOMENTO}
    assert entorno.movimientos_de_cuenta()[0].occurred_at == MOMENTO


def test_total_de_factura_con_tres_decimales_se_rechaza(entorno: Entorno) -> None:
    with pytest.raises(DomainError) as error:
        entorno.enviar(entorno.contenido(total_factura="152460.001"))

    assert error.value.codigo == "IMPORTE_INVALIDO"
    entorno.sin_efectos()


def test_inv07_compra_sin_lineas_se_rechaza_sin_efectos(entorno: Entorno) -> None:
    with pytest.raises(DomainError) as error:
        entorno.enviar(entorno.contenido(lineas=[]))

    assert error.value.codigo == "COMPRA_SIN_LINEAS"
    entorno.sin_efectos()


def test_inv04_cantidad_que_no_da_unidades_enteras_se_rechaza_con_su_linea(
    entorno: Entorno,
) -> None:
    with pytest.raises(DomainError) as error:
        entorno.enviar(
            entorno.contenido(
                lineas=[entorno.linea("cerveza"), entorno.linea("vino", cantidad="2.3")]
            )
        )

    assert error.value.codigo == "CANTIDAD_INVALIDA"
    assert error.value.extension == {"linea": 1}
    entorno.sin_efectos()


def test_valor_cero_se_rechaza_con_su_linea(entorno: Entorno) -> None:
    with pytest.raises(DomainError) as error:
        entorno.enviar(entorno.contenido(lineas=[entorno.linea("vino", valor="0.00")]))

    assert error.value.codigo == "VALOR_INVALIDO"
    assert error.value.extension == {"linea": 0}
    entorno.sin_efectos()


def test_credito_con_medios_de_pago_se_rechaza(entorno: Entorno) -> None:
    """CMP-01, D2: una compra a crédito no trae medios."""
    medio = {"medio_pago_id": str(uuid4()), "importe": "152460.00"}

    with pytest.raises(DomainError) as error:
        entorno.enviar(entorno.contenido(medios=[medio]))

    assert error.value.codigo == "CONDICION_INVALIDA"
    entorno.sin_efectos()


# --- CMP-04: diferencias de costo --------------------------------------------------------


def _informar_costo(entorno: Entorno, producto_id: UUID, presentacion_id: UUID, valor: str) -> None:
    proveedores_service.informar_costos(
        entorno.org,
        entorno.sesion,
        RELOJ,
        proveedor_id=entorno.proveedor_id,
        costos=[
            CostoDelLote(
                producto_id=producto_id,
                presentacion_id=presentacion_id,
                valor=Decimal(valor),
                incluye_iva=False,
                bonificacion=Decimal("0"),
                vigencia_desde=date(2026, 5, 1),
                observacion=None,
            )
        ],
        operation_id=uuid4(),
        actor_id=entorno.usuario_id,
    )


def test_el_resultado_informa_costos_distintos_del_vigente_sin_crear_costos(
    entorno: Entorno,
) -> None:
    """CMP-04, D7: Vino A vigente 1000, comprado a 1100; Cerveza B sin vigente."""
    _informar_costo(entorno, entorno.vino_id, entorno.caja_x6_id, "6000.00")
    # 6000 / 6 = 1000 vigente para Vino A; la compra de Vino A a 6600 sale a 1100.
    antes = entorno.sesion.scalar(select(func.count()).select_from(CostoInformado))

    comando = entorno.enviar(
        entorno.contenido(
            lineas=[entorno.linea("vino", valor="6600.00"), entorno.linea("cerveza")],
            total_factura="159720.00",
        )
    )

    assert comando.resultado is not None
    assert comando.resultado["diferencias_de_costo"] == [
        {
            "linea": 0,
            "producto_id": str(entorno.vino_id),
            "costo_base_compra": "1100.000000",
            "costo_base_vigente": "1000.000000",
        },
        {
            "linea": 1,
            "producto_id": str(entorno.cerveza_id),
            "costo_base_compra": "1100.000000",
            "costo_base_vigente": None,
        },
    ]
    assert entorno.sesion.scalar(select(func.count()).select_from(CostoInformado)) == antes


def test_un_costo_igual_al_vigente_no_aparece_en_las_diferencias(entorno: Entorno) -> None:
    _informar_costo(entorno, entorno.vino_id, entorno.caja_x6_id, "6000.00")
    _informar_costo(entorno, entorno.cerveza_id, entorno.botella_id, "1100.00")

    comando = entorno.enviar()

    assert comando.resultado is not None
    assert comando.resultado["diferencias_de_costo"] == []


def test_el_costo_vigente_se_resuelve_a_la_fecha_de_la_compra(entorno: Entorno) -> None:
    """CST-03: un costo con vigencia posterior a la fecha de la compra no cuenta."""
    _informar_costo(entorno, entorno.vino_id, entorno.caja_x6_id, "6000.00")

    comando = entorno.enviar(
        entorno.contenido(
            lineas=[entorno.linea("vino")], fecha="2026-04-28", total_factura="72600.00"
        )
    )

    assert comando.resultado is not None
    (diferencia,) = comando.resultado["diferencias_de_costo"]  # type: ignore[misc]
    assert diferencia["costo_base_vigente"] is None  # vigente desde 2026-05-01


# --- idempotencia (INV-06), modo y permiso -----------------------------------------------


def test_inv06_el_doble_envio_devuelve_el_resultado_original_y_no_duplica(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()

    primero = entorno.enviar(operation_id=operation_id)
    segundo = entorno.enviar(operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.compras()) == 1
    assert len(entorno.movimientos_de_stock()) == 2
    assert len(entorno.movimientos_de_cuenta()) == 1
    assert entorno.saldo(entorno.vino_id) == 60


def test_inv06_el_mismo_operation_id_con_otro_contenido_es_inconsistente(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()
    entorno.enviar(operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(
            entorno.contenido(lineas=[entorno.linea("vino", cantidad="11")]),
            operation_id=operation_id,
        )

    assert len(entorno.compras()) == 1


def test_cmp08_el_lote_rechaza_la_compra_enviada_sin_conexion(entorno: Entorno) -> None:
    """CMP-08, `02` §6.5: el bus real rechaza `OFFLINE` con un código estable."""
    operation_id = uuid4()
    item = ItemLote(
        operation_id=operation_id,
        tipo=CONFIRMAR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=entorno.contenido(),
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert entorno.compras() == []
    assert entorno.movimientos_de_stock() == []


def test_sin_registrar_compra_se_rechaza_con_403_y_sin_reserva(db_session: Session) -> None:
    entorno = Entorno(db_session, permisos=frozenset({"GESTIONAR_PROVEEDORES"}))
    operation_id = uuid4()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.enviar(operation_id=operation_id)

    assert error.value.status_http == 403
    entorno.sin_efectos()
    assert (
        db_session.scalar(
            select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
        )
        == 0
    )


def test_adr022_la_compra_deja_una_sola_auditoria_con_su_operation_id(entorno: Entorno) -> None:
    operation_id = uuid4()

    entorno.enviar(operation_id=operation_id)

    assert entorno.auditorias(operation_id) == 1


def test_el_contenido_no_puede_traer_la_organizacion(entorno: Entorno) -> None:
    """INV-21, TR-08: `organizacion_id` sale del token, no del cuerpo."""
    from app.commands.errores import ContenidoDeComandoInvalidoError

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(entorno.contenido(organizacion_id=str(uuid4())))

    entorno.sin_efectos()


# --- INV-01 (5.2) ----------------------------------------------------------------------


def test_inv01_una_falla_despues_de_ingresar_el_stock_y_antes_de_la_cuenta_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "INV-01 — falla después del stock": ni compra, ni línea, ni movimiento
    de stock, ni historia de costo, ni movimiento de cuenta, ni cambio de saldo."""
    ingresos: list[int] = []
    original = stock_service.registrar_movimientos

    def registrar_y_contar(*args: Any, **kwargs: Any) -> Any:
        resultado = original(*args, **kwargs)
        ingresos.append(len(resultado))
        return resultado

    def falla(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("falla inyectada después del stock y antes de la cuenta")

    monkeypatch.setattr(stock_service, "registrar_movimientos", registrar_y_contar)
    monkeypatch.setattr(cuentas_service, "registrar_movimiento", falla)
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.enviar(operation_id=operation_id)

    assert ingresos == [2]  # el stock ya se había escrito cuando falló la cuenta
    entorno.sin_efectos()
    assert entorno.saldo(entorno.vino_id) == 0
    assert entorno.promedio(entorno.vino_id) is None
    assert entorno.auditorias(operation_id) == 0


# --- INV-18 (5.4) ----------------------------------------------------------------------


def _modificar_unidades(entorno: Entorno, presentacion_id: UUID, unidades: int) -> None:
    catalogo_service.modificar_presentacion(
        entorno.org,
        entorno.sesion,
        RELOJ,
        presentacion_id=presentacion_id,
        nombre="Caja x6",
        unidades_base=unidades,
        usar_en_venta=True,
        usar_en_compra=True,
        activo=True,
        actor_id=entorno.usuario_id,
    )


def test_inv18_presentacion_usada_en_compra_es_congelada(entorno: Entorno) -> None:
    """INV-18, CAT-04, ADR-023: `Caja x6` figura en una compra y no tiene costos
    informados; sus unidades no cambian."""
    _modificar_unidades(entorno, entorno.caja_x6_id, 12)  # antes de la compra: se puede
    _modificar_unidades(entorno, entorno.caja_x6_id, 6)
    entorno.enviar()

    with pytest.raises(UnidadesCongeladasError) as error:
        _modificar_unidades(entorno, entorno.caja_x6_id, 12)

    assert error.value.codigo == "UNIDADES_CONGELADAS"
    presentacion = catalogo_service.obtener_presentacion(
        entorno.org, entorno.caja_x6_id, entorno.sesion
    )
    assert presentacion is not None
    assert presentacion.unidades_base == 6


def test_inv18_la_compra_anulada_tampoco_libera_las_unidades(entorno: Entorno) -> None:
    """TR-06: una compra anulada sigue figurando en el verificador de uso. La anulación
    se simula por SQL (el comando es del Lote 2, tarea 9.1)."""
    entorno.enviar()
    motivo = uuid4()
    entorno.sesion.execute(
        text(
            "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :org, 'ANULACION_COMPRA', 'Otro', true, :m, :m)"
        ),
        {"id": motivo, "org": entorno.org, "m": MOMENTO},
    )
    entorno.sesion.execute(
        text(
            "UPDATE compra SET estado = 'ANULADA', anulacion_motivo_id = :motivo, "
            "anulada_en = :m, anulada_por_id = :usuario WHERE organizacion_id = :org"
        ),
        {"motivo": motivo, "m": MOMENTO, "usuario": entorno.usuario_id, "org": entorno.org},
    )

    with pytest.raises(UnidadesCongeladasError):
        _modificar_unidades(entorno, entorno.caja_x6_id, 12)


def test_inv18_una_presentacion_sin_compras_ni_costos_sigue_editable(entorno: Entorno) -> None:
    entorno.enviar(entorno.contenido(lineas=[entorno.linea("cerveza")], total_factura="79860.00"))

    # `Botella` de Vino A no figura en ninguna compra: se puede cambiar.
    catalogo_service.modificar_presentacion(
        entorno.org,
        entorno.sesion,
        RELOJ,
        presentacion_id=entorno.botella_vino_id,
        nombre="Botella",
        unidades_base=2,
        usar_en_venta=True,
        usar_en_compra=True,
        activo=True,
        actor_id=entorno.usuario_id,
    )


@pytest.mark.parametrize("orden", ["vino_primero", "cerveza_primero"])
def test_el_error_informado_es_el_de_la_primera_linea_con_problema_sin_depender_del_uuid(
    entorno: Entorno, orden: str
) -> None:
    """D4: los dos productos son de otro proveedor; el error lleva siempre la línea 0,
    sea cual sea el orden de los UUID de los productos (causa raíz de una falla
    intermitente de `test_compras_api.py`: se informaba la línea del producto de menor
    UUID)."""
    otro = crear_proveedor(entorno.sesion, entorno.org, nombre="Distribuidora Norte")
    lineas = [entorno.linea("vino"), entorno.linea("cerveza")]
    if orden == "cerveza_primero":
        lineas.reverse()

    with pytest.raises(DomainError) as error:
        entorno.enviar(entorno.contenido(proveedor_id=str(otro), lineas=lineas))

    assert error.value.codigo == "PROVEEDOR_NO_CORRESPONDE"
    assert error.value.extension == {"linea": 0}
