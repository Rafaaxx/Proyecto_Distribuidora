"""Handlers de comandos de `ventas` (change 18a, grupo 7; `design.md` D1, D2, D12, D17; plantilla
D7 del change 04: un tipo de comando por escritura ya existente en `service.py`, un esquema de
contenido versión 1, un handler de pocas líneas que llama al servicio, sin `commit` propio --
lo gestiona el bus).

`VENTA_CONFIRMAR` v1, permiso `VENDER` (`01` §19). Admite `ONLINE` y `OFFLINE` (grupo 11,
CRÍTICO, D1, alcance confirmado por el usuario el 2026-10-20): sin conexión el bus compara el
permiso y el handler no lo vuelve a exigir.

Mismo criterio que el resto de los módulos: el handler NO atrapa errores de dominio, los deja
subir; el bus (`sync/service.py::procesar_comando`) revierte toda la transacción, incluida la
reserva del `operation_id`, y el comando puede reintentarse con contenido corregido.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from app.commands.auditoria import (
    DatosDeAuditoria,
    observacion_de_ubicacion_tomada,
    unir_observaciones,
)
from app.commands.catalogo import OperacionObservable, declarar_tipo
from app.commands.credenciales import CredencialDePin
from app.commands.observaciones import ObservacionProducida
from app.commands.registro import SesionDeHandler, registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.cobranzas.service import MedioACobrar
from app.modules.identidad import service as identidad_service
from app.modules.ventas import service as ventas_service
from app.modules.ventas.domain.descuentos import DescuentoDeLinea
from app.modules.ventas.service import (
    CobranzaDeVenta,
    CreditoDelDispositivo,
    DatosDeVenta,
    LineaDeVenta,
    PermisosDeVenta,
)

ResultadoHandlerConAuditoria = tuple[
    str,
    dict[str, object] | None,
    str | None,
    tuple[ObservacionProducida, ...],
    DatosDeAuditoria,
]
"""Misma convención que `sync/service.py::ResultadoHandler` con observaciones y dato de
auditoría (ver `stock/commands.py`; no se importa de `sync`, contrato `commands-no-modulos`)."""

_PATRON_DECIMAL = r"^-?\d+(\.\d+)?$"
"""Un importe viaja como string decimal: un número JSON ya degradado por `float` en el cliente
se rechaza (INV-03)."""

PERMISO_VENDER = "VENDER"


def _exigir_permiso(
    sobre: SobreComando, sesion: SesionDeHandler, codigo_permiso: str
) -> frozenset[str]:
    """Falla con 403 `PERMISO_REQUERIDO` si el usuario del sobre no tiene el permiso (SEG-06).
    Va PRIMERO: un rechazo no puede dejar nada escrito. Devuelve todos los permisos del
    usuario para armar los de la venta.

    Sin conexión (`OFFLINE`) NO lo vuelve a exigir: el bus ya comparó el permiso con los vigentes
    al sincronizar y, si falta, anota `PERMISO_REVOCADO` sin rechazar (SYN-05, SYN-10)."""
    permitidos = frozenset(
        identidad_service.listar_permisos_del_usuario(
            sobre.organizacion_id, sobre.usuario_id, sesion
        )
    )
    if sobre.modo != "OFFLINE" and codigo_permiso not in permitidos:
        raise PermisoRequeridoError(f"Falta el permiso {codigo_permiso}.")
    return permitidos


# --- VENTA_CONFIRMAR (VTA-12; D2, D12, D17) --------------------------------------------------


class DescuentoEsperadoContenidoV1(BaseModel):
    """Un descuento de la línea tal como lo vio el usuario (change 18b, D1): origen, regla
    (nula en el manual), porcentaje (nulo en una regla de importe fijo) e importe, como texto
    (INV-03). Con conexión el servidor lo compara con el que calcula (D11)."""

    model_config = ConfigDict(extra="forbid")

    origen: Literal["AUTOMATICO", "MANUAL"]
    regla_id: UUID | None = None
    porcentaje: str | None = Field(default=None, pattern=_PATRON_DECIMAL)
    importe: str = Field(pattern=_PATRON_DECIMAL)


class CreditoContenidoV1(BaseModel):
    """El crédito de la venta (change 18b, D1). Con conexión: `acepta_exceso` (ADVERTIR) y
    `autorizador_id` (AUTORIZAR); el PIN NO viaja acá (D2). `limite`, `saldo_considerado`,
    `politica` y `resolucion` son la evaluación del dispositivo, solo del camino sin conexión
    (D7)."""

    model_config = ConfigDict(extra="forbid")

    acepta_exceso: StrictBool = False
    autorizador_id: UUID | None = None
    limite: str | None = Field(default=None, pattern=_PATRON_DECIMAL)
    saldo_considerado: str | None = Field(default=None, pattern=_PATRON_DECIMAL)
    politica: Literal["ADVERTIR", "AUTORIZAR", "BLOQUEAR"] | None = None
    resolucion: (
        Literal[
            "SIN_EXCESO",
            "ADVERTENCIA_ACEPTADA",
            "PERMISO_PROPIO",
            "PIN_SUPERVISOR",
            "TOLERANCIA_OFFLINE",
        ]
        | None
    ) = None


class LineaDeVentaContenidoV1(BaseModel):
    """Una línea con lo que vio el usuario (D2). La cantidad es un entero estricto: `2.5` o un
    texto se rechazan como contenido inválido (INV-04). `descuento_manual` (fracción como texto)
    y `descuentos` (los que vio el usuario) son opcionales (change 18b, D1)."""

    model_config = ConfigDict(extra="forbid")

    linea_id: UUID
    producto_id: UUID
    presentacion_id: UUID
    cantidad: StrictInt
    lista_version_id: UUID
    precio_referencia: str = Field(pattern=_PATRON_DECIMAL)
    unidades_referencia: StrictInt
    importe_bruto: str = Field(pattern=_PATRON_DECIMAL)
    descuento_manual: str | None = Field(default=None, pattern=_PATRON_DECIMAL)
    descuentos: list[DescuentoEsperadoContenidoV1] = Field(default_factory=list)


class MedioDeVentaContenidoV1(BaseModel):
    """Un medio de la cobranza en el acto (D12)."""

    model_config = ConfigDict(extra="forbid")

    medio_pago_id: UUID
    importe: str = Field(pattern=_PATRON_DECIMAL)
    referencia: str | None = None


class CobranzaDeVentaContenidoV1(BaseModel):
    """La cobranza en el acto: identificador generado por quien la origina, de 1 a 20 medios
    (el dominio rechaza otra cantidad con su código estable) y observación opcional. El importe
    es la suma de los medios (INV-08): no hay campo aparte."""

    model_config = ConfigDict(extra="forbid")

    cobranza_id: UUID
    medios: list[MedioDeVentaContenidoV1]
    observacion: str | None = None


class VentaConfirmarContenidoV1(BaseModel):
    """`extra="forbid"`: `organizacion_id` sale del token (INV-21, TR-08). `venta_id` y `numero`
    los genera quien origina la venta (`02` §9, D4). `ubicacion_id` es opcional: con una jornada
    abierta la venta va a la de la jornada (D3)."""

    model_config = ConfigDict(extra="forbid")

    venta_id: UUID
    numero: str
    cliente_id: UUID
    ubicacion_id: UUID | None = None
    lista_id: UUID | None = None
    lista_version_id: UUID | None = None
    motivo_lista_id: UUID | None = None
    lineas: list[LineaDeVentaContenidoV1]
    total: str = Field(pattern=_PATRON_DECIMAL)
    cobranza: CobranzaDeVentaContenidoV1 | None = None
    descuento_manual_general: str | None = Field(default=None, pattern=_PATRON_DECIMAL)
    motivo_descuento_id: UUID | None = None
    descuento_autorizador_id: UUID | None = None
    credito: CreditoContenidoV1 | None = None

    @model_validator(mode="after")
    def _la_version_elegida_nombra_su_lista(self) -> VentaConfirmarContenidoV1:
        """Una versión es de una lista: elegirla sin la lista es contenido malformado (D6)."""
        if self.lista_version_id is not None and self.lista_id is None:
            raise ValueError("lista_version_id exige lista_id.")
        return self


def _decimal_o_nulo(valor: str | None) -> Decimal | None:
    return None if valor is None else Decimal(valor)


def manejar_venta_confirmar(
    sobre: SobreComando,
    contenido: VentaConfirmarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
    credenciales: tuple[CredencialDePin, ...] = (),
) -> ResultadoHandlerConAuditoria:
    """Confirma una venta con conexión (`VENDER`). El resultado se guarda y se reenvía tal cual
    ante un doble envío (INV-06): venta, número, total, saldo del cliente y cobranza, todos los
    importes como string (INV-03). Devuelve siempre el dato de auditoría (AUD-01, AUD-02, D20).

    `credenciales` es el dato efímero de D2 (change 18b): llega por clausura desde la ruta y no
    está en el contenido. Las usa la verificación del PIN de `confirmar_venta` solo si hace falta;
    nunca se guardan ni se registran."""
    permisos = _exigir_permiso(sobre, sesion, PERMISO_VENDER)
    resultado = ventas_service.confirmar_venta(
        sobre.organizacion_id,
        sesion,
        reloj,
        datos=DatosDeVenta(
            venta_id=contenido.venta_id,
            numero=contenido.numero,
            cliente_id=contenido.cliente_id,
            ubicacion_id=contenido.ubicacion_id,
            lineas=[
                LineaDeVenta(
                    linea_id=linea.linea_id,
                    producto_id=linea.producto_id,
                    presentacion_id=linea.presentacion_id,
                    cantidad=linea.cantidad,
                    lista_version_id=linea.lista_version_id,
                    precio_referencia=Decimal(linea.precio_referencia),
                    unidades_referencia=linea.unidades_referencia,
                    importe_bruto=Decimal(linea.importe_bruto),
                    descuento_manual=(
                        None if linea.descuento_manual is None else Decimal(linea.descuento_manual)
                    ),
                    descuentos=tuple(
                        DescuentoDeLinea(
                            descuento.origen,
                            descuento.regla_id,
                            None if descuento.porcentaje is None else Decimal(descuento.porcentaje),
                            Decimal(descuento.importe),
                        )
                        for descuento in linea.descuentos
                    ),
                )
                for linea in contenido.lineas
            ],
            total=Decimal(contenido.total),
            descuento_manual_general=(
                None
                if contenido.descuento_manual_general is None
                else Decimal(contenido.descuento_manual_general)
            ),
            motivo_descuento_id=contenido.motivo_descuento_id,
            descuento_autorizador_id=contenido.descuento_autorizador_id,
            acepta_exceso=contenido.credito is not None and contenido.credito.acepta_exceso,
            credito_autorizador_id=(
                None if contenido.credito is None else contenido.credito.autorizador_id
            ),
            credito_del_dispositivo=(
                None
                if contenido.credito is None
                else CreditoDelDispositivo(
                    limite=_decimal_o_nulo(contenido.credito.limite),
                    saldo_considerado=_decimal_o_nulo(contenido.credito.saldo_considerado),
                    politica=contenido.credito.politica,
                    resolucion=contenido.credito.resolucion,
                    autorizador_id=contenido.credito.autorizador_id,
                )
            ),
            lista_id=contenido.lista_id,
            lista_version_id=contenido.lista_version_id,
            motivo_lista_id=contenido.motivo_lista_id,
            cobranza=(
                None
                if contenido.cobranza is None
                else CobranzaDeVenta(
                    cobranza_id=contenido.cobranza.cobranza_id,
                    medios=[
                        MedioACobrar(
                            medio_pago_id=medio.medio_pago_id,
                            importe=Decimal(medio.importe),
                            referencia=medio.referencia,
                        )
                        for medio in contenido.cobranza.medios
                    ],
                    observacion=contenido.cobranza.observacion,
                )
            ),
        ),
        permisos=PermisosDeVenta(
            puede_usar_lista_anterior="USAR_LISTA_ANTERIOR" in permisos,
            puede_stock_negativo="PERMITIR_STOCK_NEGATIVO" in permisos,
            puede_vender_suspendido="VENDER_CLIENTE_SUSPENDIDO" in permisos,
            puede_liberar_ubicacion="LIBERAR_UBICACION" in permisos,
            codigos=permisos,
        ),
        operation_id=sobre.operation_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        occurred_at=sobre.occurred_at,
        jornada_del_sobre=sobre.jornada_id,
        modo=sobre.modo,
        credenciales={credencial.autorizador_id: credencial.pin for credencial in credenciales},
    )
    venta = resultado.venta
    cuerpo: dict[str, object] = {
        "venta_id": str(venta.id),
        "numero": venta.numero,
        "estado": venta.estado,
        "total": str(venta.total),
        "saldo": str(resultado.saldo),
        "cobranza_id": None if resultado.cobranza_id is None else str(resultado.cobranza_id),
    }
    # D20 y STK-09: la única fila de auditoría del bus lleva el motivo de la lista (si la hubo)
    # y, en su observación, la lista usada y la constancia de la ubicación tomada.
    auditoria = DatosDeAuditoria(
        motivo_id=venta.motivo_lista_id,
        observacion=unir_observaciones(
            resultado.observacion_de_lista,
            observacion_de_ubicacion_tomada(resultado.jornadas_tomadas),
        ),
    )
    return (
        "ACEPTADO",
        cuerpo,
        None,
        tuple(
            ObservacionProducida(
                codigo=observacion.codigo,
                operacion_tipo="COBRANZA" if observacion.sobre_cobranza else "VENTA",
                operacion_id=(
                    resultado.cobranza_id
                    if observacion.sobre_cobranza and resultado.cobranza_id is not None
                    else venta.id
                ),
                detalle=observacion.detalle,
            )
            for observacion in resultado.observaciones
        ),
        auditoria,
    )


registrar_handler("VENTA_CONFIRMAR", 1, VentaConfirmarContenidoV1)(manejar_venta_confirmar)
declarar_tipo(
    "VENTA_CONFIRMAR",
    admite_online=True,
    admite_offline=True,
    permisos=(PERMISO_VENDER,),
    operacion_offline=OperacionObservable("VENTA", "venta_id"),
)
