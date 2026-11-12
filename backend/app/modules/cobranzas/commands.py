"""Handlers de comandos de `cobranzas` (change 17, grupo 7; `design.md` D1 a D5, D8, D9, D10;
plantilla D7 del change 04: un tipo de comando por escritura ya existente en `service.py`, un
esquema de contenido versión 1, un handler de pocas líneas que llama al servicio, sin `commit`
propio -- lo gestiona el bus).

`COBRANZA_REGISTRAR` v1, permiso `REGISTRAR_COBRANZA` (`01` §19). Admite `ONLINE` y `OFFLINE`
(grupo 12): sin conexión el bus compara el permiso y el handler no lo vuelve a exigir.

Mismo criterio que el resto de los módulos: el handler NO atrapa errores de dominio, los deja
subir; el bus (`sync/service.py::procesar_comando`) revierte toda la transacción, incluida la
reserva del `operation_id`, y el comando puede reintentarse con contenido corregido.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.commands.auditoria import DatosDeAuditoria
from app.commands.catalogo import OperacionObservable, declarar_tipo
from app.commands.observaciones import ObservacionProducida
from app.commands.registro import SesionDeHandler, registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.cobranzas import service as cobranzas_service
from app.modules.cobranzas.domain.cobranza import MAXIMO_OBSERVACION
from app.modules.cobranzas.service import MedioACobrar
from app.modules.identidad import service as identidad_service

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
ResultadoHandlerConObservaciones = tuple[
    str, dict[str, object] | None, str | None, tuple[ObservacionProducida, ...]
]
ResultadoHandlerConAuditoria = tuple[
    str, dict[str, object] | None, str | None, tuple[()], DatosDeAuditoria
]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver `catalogo/commands.py` para la
justificación de no importarla de `sync`)."""

_PATRON_DECIMAL = r"^-?\d+(\.\d+)?$"
"""Un importe viaja como string decimal: un número JSON ya degradado por `float` en el cliente
se rechaza (INV-03)."""

PERMISO_REGISTRAR_COBRANZA = "REGISTRAR_COBRANZA"
PERMISO_ANULAR_COBRANZA = "ANULAR_COBRANZA"


def _exigir_permiso(sobre: SobreComando, sesion: SesionDeHandler, codigo_permiso: str) -> None:
    """Falla con 403 `PERMISO_REQUERIDO` si el usuario del sobre no tiene el permiso (SEG-06).
    Va PRIMERO: un rechazo no puede dejar nada escrito (mismo criterio que `proveedores`).

    Sin conexión (`OFFLINE`) NO vuelve a exigirlo: el bus ya comparó el permiso con los vigentes
    al sincronizar y, si falta, anota `PERMISO_REVOCADO` sin rechazar (SYN-05, SYN-10, D10)."""
    if sobre.modo == "OFFLINE":
        return
    permitidos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    if codigo_permiso not in permitidos:
        raise PermisoRequeridoError(f"Falta el permiso {codigo_permiso}.")


# --- COBRANZA_REGISTRAR (COB-01, COB-02, COB-03; D2 a D5, D8) -------------------------------


class MedioDeCobranzaContenidoV1(BaseModel):
    """Un medio de la cobranza (D2)."""

    model_config = ConfigDict(extra="forbid")

    medio_pago_id: UUID
    importe: str = Field(pattern=_PATRON_DECIMAL)
    referencia: str | None = None


class CobranzaRegistrarContenidoV1(BaseModel):
    """`extra="forbid"`: `organizacion_id` sale del token (INV-21, TR-08) y la cobranza nace
    `CONFIRMADA` de origen `INDEPENDIENTE` (COB-01, D1). `cobranza_id` lo genera quien origina la
    cobranza (D2, `02` §9). `medios` vacía la rechaza el dominio con `MEDIOS_INVALIDOS` y su
    código estable, no un 422 genérico de Pydantic (D2: de 1 a 20)."""

    model_config = ConfigDict(extra="forbid")

    cobranza_id: UUID
    cliente_id: UUID
    importe: str = Field(pattern=_PATRON_DECIMAL)
    medios: list[MedioDeCobranzaContenidoV1]
    observacion: str | None = Field(default=None, max_length=MAXIMO_OBSERVACION)


def manejar_cobranza_registrar(
    sobre: SobreComando,
    contenido: CobranzaRegistrarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler | ResultadoHandlerConObservaciones:
    """Registra una cobranza con o sin conexión (`REGISTRAR_COBRANZA`). El resultado se guarda y se
    reenvía tal cual ante un doble envío (INV-06): devuelve el id de la cobranza, su estado, el
    importe, el saldo resultante del cliente y la jornada, todos como string (INV-03). Sin conexión
    nunca rechaza por reglas de negocio: devuelve además las observaciones que dejó (D13)."""
    _exigir_permiso(sobre, sesion, PERMISO_REGISTRAR_COBRANZA)
    resultado = cobranzas_service.registrar_cobranza(
        sobre.organizacion_id,
        sesion,
        reloj,
        cobranza_id=contenido.cobranza_id,
        cliente_id=contenido.cliente_id,
        importe=Decimal(contenido.importe),
        medios=[
            MedioACobrar(
                medio_pago_id=medio.medio_pago_id,
                importe=Decimal(medio.importe),
                referencia=medio.referencia,
            )
            for medio in contenido.medios
        ],
        observacion=contenido.observacion,
        jornada_del_sobre=sobre.jornada_id,
        operation_id=sobre.operation_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        occurred_at=sobre.occurred_at,
        modo=sobre.modo,
    )
    cobranza = resultado.cobranza
    cuerpo: dict[str, object] = {
        "cobranza_id": str(cobranza.id),
        "estado": cobranza.estado,
        "importe": str(cobranza.importe),
        "saldo": str(resultado.saldo),
        "jornada_id": None if cobranza.jornada_id is None else str(cobranza.jornada_id),
    }
    if not resultado.observaciones:
        return "ACEPTADO", cuerpo, None
    return (
        "ACEPTADO",
        cuerpo,
        None,
        tuple(
            ObservacionProducida(
                codigo=observacion.codigo,
                operacion_tipo="COBRANZA",
                operacion_id=cobranza.id,
                detalle=observacion.detalle,
            )
            for observacion in resultado.observaciones
        ),
    )


registrar_handler("COBRANZA_REGISTRAR", 1, CobranzaRegistrarContenidoV1)(manejar_cobranza_registrar)
declarar_tipo(
    "COBRANZA_REGISTRAR",
    admite_online=True,
    admite_offline=True,
    permisos=(PERMISO_REGISTRAR_COBRANZA,),
    operacion_offline=OperacionObservable("COBRANZA", "cobranza_id"),
)


# --- COBRANZA_ANULAR (COB-05, CC-02; D6, D7, D15) --------------------------------------------


class CobranzaAnularContenidoV1(BaseModel):
    """`extra="forbid"`: `organizacion_id` sale del token (INV-21, TR-08). Anulación total: no
    hay importe. La observación es opcional y de hasta 500 caracteres (D7)."""

    model_config = ConfigDict(extra="forbid")

    cobranza_id: UUID
    motivo_id: UUID
    observacion: str | None = Field(default=None, max_length=MAXIMO_OBSERVACION)


def manejar_cobranza_anular(
    sobre: SobreComando,
    contenido: CobranzaAnularContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandlerConAuditoria:
    """Anula una cobranza (`ANULAR_COBRANZA`). Devuelve el resultado que se reenvía ante un doble
    envío (INV-06) y el motivo para la fila de auditoría del bus (AUD-02, D15)."""
    _exigir_permiso(sobre, sesion, PERMISO_ANULAR_COBRANZA)
    resultado = cobranzas_service.anular_cobranza(
        sobre.organizacion_id,
        sesion,
        reloj,
        cobranza_id=contenido.cobranza_id,
        motivo_id=contenido.motivo_id,
        observacion=contenido.observacion,
        operation_id=sobre.operation_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        occurred_at=sobre.occurred_at,
    )
    return (
        "ACEPTADO",
        {
            "cobranza_id": str(resultado.cobranza.id),
            "estado": resultado.cobranza.estado,
            "importe": str(resultado.cobranza.importe),
            "saldo": str(resultado.saldo),
        },
        None,
        (),
        DatosDeAuditoria(motivo_id=contenido.motivo_id),
    )


registrar_handler("COBRANZA_ANULAR", 1, CobranzaAnularContenidoV1)(manejar_cobranza_anular)
declarar_tipo(
    "COBRANZA_ANULAR", admite_online=True, admite_offline=False, permisos=("ANULAR_COBRANZA",)
)
