"""Interfaz pública de `ventas` para otros módulos (`CLAUDE.md` §4: un módulo usa a otro solo a
través de su `service.py`) y registro de sus puertos.

Expone el verificador de uso de presentaciones (INV-18, `design.md` D18) y la confirmación de la
venta (`confirmar_venta`, change 18a, grupo 7; D17). Sin `commit`: la transacción la gestiona el
bus de comandos (`ventas/commands.py`). Toda función recibe `organizacion_id` y lo usa para
filtrar.

Orden de `confirmar_venta` con conexión (change 18b, D18 opción A, borrador aprobado por el
usuario el 2026-10-23; precedencia de rechazos: contenido -> cliente -> precio -> descuento ->
tope y motivo -> crédito -> PIN -> stock -> número):

0. validación pura del contenido, `venta_id` y número libres;
1. configuración, momento, cliente y lista (`FOR SHARE`), precios (D6, D7, D9) y estado del
   cliente (D5);
2. nivel 1: `saldo_cuenta` del cliente `FOR UPDATE`; su valor es el saldo considerado del
   crédito;
3. nivel 2: productos `FOR SHARE` por identificador ascendente y, con ellos tomados, las
   presentaciones (`FOR KEY SHARE`);
4. el motor recalcula con las reglas vigentes al `occurred_at` y se compara con lo esperado:
   primero el precio de cada línea (`PRECIO_DIFIERE`), después los descuentos
   (`DESCUENTO_DIFIERE`, D11) y por último el total; se evalúa el consumidor final (D5);
5. descuento manual, una sola vez con el mayor porcentaje (DSC-06): habilitación, permiso, motivo,
   tope y autorización (sin verificar ningún PIN);
6. crédito con el saldo del paso 2 y el total del paso 4 (CRE-02, D5, D6);
7. PIN de los autorizadores que hacen falta (solo si ni el propio usuario tiene el permiso): el
   permiso del autorizador y el bloqueo se miran antes de verificar ni contar; un fallo se cuenta
   en una transacción aparte; una persona que autoriza descuento y crédito se verifica una vez
   (D4);
8. niveles 2 a 5: egreso de stock `VENTA` por línea, que devuelve el costo (D10, D11);
9. se inserta la venta con sus líneas, el costo y el snapshot de crédito congelados (VTA-05,
   CRE-10), los descuentos de cada línea (DSC-08), el débito `VENTA` por el total (el saldo ya
   está bloqueado) y la cobranza `VENTA` (D12), después del débito (CC-05);
10. LO ÚLTIMO, nivel 6: el correlativo del dispositivo (`max(actual, propuesto)`, D4) y el
    resultado y las observaciones al bus, que audita y confirma.

Un rechazo no deja nada escrito (INV-01); lo único que sobrevive es el contador de un PIN
incorrecto, que se escribe en su propia transacción (D3).

Sin conexión (`modo="OFFLINE"`, change 18a, tarea 11.2, `design.md` D1, alcance confirmado por el
usuario el 2026-10-20) el orden de bloqueo NO cambia; cambia qué se decide en cada paso: se
congelan la versión, el precio y las unidades que envió el dispositivo; solo se rechaza lo
malformado (`TOTALES_INCONSISTENTES`, INV-07), lo inexistente y el número repetido; todo lo demás
se acepta con una observación (SYN-05, SYN-06, SYN-07, INV-17).

Descuentos, crédito y autorizaciones sin conexión (change 18b, tarea 10.1, D7, D9, D10, D17, D18,
D19; borrador aprobado por el usuario el 2026-10-23). Se congelan los descuentos y la evaluación
de crédito del dispositivo; el servidor no verifica ningún PIN (el lote no admite credenciales) y
solo lee el permiso vigente de cada autorizador. En el mismo orden de bloqueos:

0. contenido: unidades, `venta_sin_lineas`, descuentos (`TOTALES_INCONSISTENTES`) y forma del
   `credito` del dispositivo, obligatorio (`CREDITO_INCONSISTENTE`); venta y número libres;
1. a 3. igual que con conexión; las reglas referidas existen (404);
4. el motor recalcula con las reglas vigentes al `occurred_at` y los porcentajes manuales
   enviados: la diferencia con los descuentos del dispositivo es la causa `CALCULO` de una única
   `DESCUENTO_DIFIERE`; el total y el neto de cada línea son los del dispositivo;
5. el descuento manual se reevalúa con los datos de hoy (cada rechazo que tendría con conexión es
   una causa); motivo (existe y es del ámbito; uno inactivo vale) y autorizador (existe);
   `AUTORIZACION_OFFLINE` por PIN o permiso propio;
6. crédito: coherencia de la evaluación del dispositivo (`CREDITO_INCONSISTENTE`), snapshot con
   disponible y exceso calculados sobre sus números, recálculo con el saldo real del paso 2
   (`EXCESO_CREDITO_DETECTADO_SYNC` si el real da exceso y el dispositivo no) y la observación de
   su resolución; el consumidor final se congela con límite cero y no repite observaciones (D17);
7. sin verificación de PIN; 8. stock (puede quedar negativo); 9. escrituras y auditoría (las
   mismas filas que con conexión, con `modo` OFFLINE); 10. correlativo del dispositivo.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import DomainError, PermisoRequeridoError
from app.core.ids import nuevo_id
from app.core.money import redondear_importe
from app.modules.catalogo import service as catalogo_service
from app.modules.clientes import service as clientes_service
from app.modules.cobranzas import service as cobranzas_service
from app.modules.cobranzas.service import MedioACobrar
from app.modules.configuracion import service as configuracion_service
from app.modules.cuentas_corrientes import service as cuentas_corrientes_service
from app.modules.descuentos import service as descuentos_service
from app.modules.identidad import service as identidad_service
from app.modules.precios import service as precios_service
from app.modules.stock import service as stock_service
from app.modules.stock.service import LineaDeMovimiento
from app.modules.ventas import repository
from app.modules.ventas.domain.auditoria import observacion_de_lista
from app.modules.ventas.domain.calculo import (
    LineaCalculo,
    ResultadoLineaVenta,
    calcular_venta,
)
from app.modules.ventas.domain.cliente import evaluar_cliente
from app.modules.ventas.domain.comparacion import (
    ProductoSinPrecio,
    ValoresDeLinea,
    comparar_con_esperado,
    comparar_precios_de_lineas,
    observacion_lista_no_vigente,
    verificar_productos_con_precio,
    verificar_totales_offline,
    verificar_unidades_de_referencia,
    verificar_version_uniforme,
)
from app.modules.ventas.domain.composicion import (
    LineaPedida,
    cantidad_base,
    validar_lineas,
    validar_producto_y_presentacion,
)
from app.modules.ventas.domain.descuentos import DescuentoDeLinea, comparar_descuentos
from app.modules.ventas.domain.descuentos_offline import (
    LineaEnviada,
    autorizacion_declarada_de_descuento,
    causa_de_rechazo_del_manual,
    detalle_de_causa_del_manual,
    diferencias_de_calculo,
    observacion_autorizacion_offline,
    observacion_descuento_difiere,
    verificar_descuentos_offline,
)
from app.modules.ventas.domain.errores import (
    AutorizacionCreditoRequeridaError,
    AutorizacionRequeridaError,
    JornadaAjenaError,
    MotivoInvalidoError,
    NumeroDuplicadoError,
    ProductoSinCostoError,
    RecursoNoEncontradoError,
    UbicacionRequeridaError,
    VentaDuplicadaError,
    VersionNoPermitidaError,
)
from app.modules.ventas.domain.momento import validar_momento
from app.modules.ventas.domain.numero import correlativo_de
from app.modules.ventas.domain.observaciones import (
    CODIGO_UBICACION_TOMADA_AL_SINCRONIZAR,
    ObservacionDeVenta,
)
from app.modules.ventas.models import Venta, VentaLinea, VentaLineaDescuento

__all__ = [
    "CobranzaDeVenta",
    "CreditoDelDispositivo",
    "DatosDeVenta",
    "LineaDeVenta",
    "PermisosDeVenta",
    "ResultadoDeVenta",
    "confirmar_venta",
    "presentacion_usada_en_venta",
]

_CUENTA_CLIENTE = "CLIENTE"
_TIPO_MOVIMIENTO_VENTA = "VENTA"
_ORIGEN_TIPO_VENTA = "VENTA"
_MODO_ONLINE = "ONLINE"
_MODO_OFFLINE = "OFFLINE"
_AMBITO_LISTA_ANTERIOR = "LISTA_ANTERIOR"
_AMBITO_DESCUENTO_MANUAL = "DESCUENTO_MANUAL"
_ACCION_DESCUENTO_MANUAL = "DESCUENTO_MANUAL"
_ACCION_AUTORIZACION_CREDITO = "AUTORIZACION_CREDITO"
_ENTIDAD_VENTA = "venta"
_PERMISO_AUTORIZAR_DESCUENTO = "AUTORIZAR_DESCUENTO"
_PERMISO_SUPERAR_CREDITO = "SUPERAR_CREDITO"
_RESOLUCION_DESCUENTO_POR_SUPERVISOR = "AUTORIZADO_POR_SUPERVISOR"
_RESOLUCION_CREDITO_POR_PIN = "PIN_SUPERVISOR"
_RESOLUCION_CREDITO_ADVERTIDA = "ADVERTENCIA_ACEPTADA"
_RESOLUCION_CREDITO_POR_TOLERANCIA = "TOLERANCIA_OFFLINE"
_RESOLUCION_CREDITO_PROPIA = "PERMISO_PROPIO"
CODIGO_EXCESO_CREDITO_ADVERTIDO = "EXCESO_CREDITO_ADVERTIDO"
CODIGO_EXCESO_CREDITO_AUTORIZADO_OFFLINE = "EXCESO_CREDITO_AUTORIZADO_OFFLINE"
CODIGO_EXCESO_CREDITO_DETECTADO_SYNC = "EXCESO_CREDITO_DETECTADO_SYNC"
_TIPO_AUTORIZACION_DESCUENTO = "DESCUENTO"
_TIPO_AUTORIZACION_CREDITO = "CREDITO"
_PERMISO_USAR_LISTA_ANTERIOR = "USAR_LISTA_ANTERIOR"
_VERSION_VIGENTE = "VIGENTE"
CODIGO_STOCK_NEGATIVO = "STOCK_NEGATIVO"
CODIGO_VENTA_SIN_COSTO = "VENTA_SIN_COSTO"
CODIGO_JORNADA_LIBERADA = "JORNADA_LIBERADA"
_ESTADO_JORNADA_LIBERADA = "LIBERADA"
_CODIGOS_DE_PRECIO_NO_RESOLUBLE = frozenset({"SIN_LISTA_APLICABLE", "LISTA_SIN_VERSION_VIGENTE"})
_CERO = Decimal("0.00")


def presentacion_usada_en_venta(
    organizacion_id: UUID, presentacion_id: UUID, sesion: Session
) -> bool:
    """Verificador de uso del catálogo (ADR-023, INV-18): una presentación cuenta como usada si
    figura en alguna línea de venta, de cualquier estado de venta."""
    return repository.presentacion_figura_en_alguna_linea(organizacion_id, presentacion_id, sesion)


catalogo_service.registrar_verificador_uso("ventas", presentacion_usada_en_venta)


@dataclass(frozen=True)
class LineaDeVenta:
    """Una línea del comando con los valores que vio el usuario (D2)."""

    linea_id: UUID
    producto_id: UUID
    presentacion_id: UUID
    cantidad: int
    lista_version_id: UUID
    precio_referencia: Decimal
    unidades_referencia: int
    importe_bruto: Decimal
    descuento_manual: Decimal | None = None
    """El porcentaje manual propio de la línea (fracción), que reemplaza al general (DSC-05)."""
    descuentos: Sequence[DescuentoDeLinea] = ()
    """Los descuentos que vio el usuario, para compararlos con los del servidor (D11)."""


@dataclass(frozen=True)
class CobranzaDeVenta:
    """La cobranza en el acto (D12): su importe es la suma de los medios (INV-08)."""

    cobranza_id: UUID
    medios: Sequence[MedioACobrar]
    observacion: str | None


@dataclass(frozen=True)
class CreditoDelDispositivo:
    """La evaluación de crédito que hizo el dispositivo (change 18b, D7); solo la usa el camino
    sin conexión, donde es obligatoria. Todo es opcional acá porque el contenido lo es; el
    servicio rechaza (`CREDITO_INCONSISTENTE`) lo que falte."""

    limite: Decimal | None = None
    saldo_considerado: Decimal | None = None
    politica: str | None = None
    resolucion: str | None = None
    autorizador_id: UUID | None = None


@dataclass(frozen=True)
class DatosDeVenta:
    """Lo que trae `VENTA_CONFIRMAR` (D2)."""

    venta_id: UUID
    numero: str
    cliente_id: UUID
    ubicacion_id: UUID | None
    lineas: Sequence[LineaDeVenta]
    total: Decimal
    cobranza: CobranzaDeVenta | None
    lista_id: UUID | None = None
    lista_version_id: UUID | None = None
    motivo_lista_id: UUID | None = None
    descuento_manual_general: Decimal | None = None
    motivo_descuento_id: UUID | None = None
    descuento_autorizador_id: UUID | None = None
    acepta_exceso: bool = False
    credito_autorizador_id: UUID | None = None
    credito_del_dispositivo: CreditoDelDispositivo | None = None


@dataclass(frozen=True)
class PermisosDeVenta:
    """Lo que el usuario puede hacer más allá de `VENDER` (`01` §19); el handler lo arma una
    sola vez con los permisos del usuario."""

    puede_usar_lista_anterior: bool = False
    puede_stock_negativo: bool = False
    puede_vender_suspendido: bool = False
    puede_liberar_ubicacion: bool = False
    """`LIBERAR_UBICACION` (STK-09): vender desde una ubicación tomada por otra jornada, sin
    `jornada_id` y con la constancia en la auditoría (change 18a, tarea 10.1)."""
    codigos: frozenset[str] = frozenset()
    """Todos los permisos del usuario (la evaluación de crédito mira `SUPERAR_CREDITO`)."""


@dataclass(frozen=True)
class ResultadoDeVenta:
    """La venta confirmada, el saldo del cliente después de aplicarla (CC-04) y las
    observaciones que dejó."""

    venta: Venta
    lineas: tuple[VentaLinea, ...]
    saldo: Decimal
    cobranza_id: UUID | None
    observaciones: tuple[ObservacionDeVenta, ...]
    observacion_de_lista: str | None = None
    """D20: la lista y la versión usadas, si no eran las que le correspondían al cliente (otra
    lista o versión no vigente); la fila de auditoría del comando la lleva con el motivo."""
    jornadas_tomadas: tuple[UUID, ...] = ()
    """STK-09: las jornadas de las ubicaciones tomadas por las que pasó el egreso de stock
    (excepción de `LIBERAR_UBICACION`); el handler las deja como constancia en la auditoría."""


@dataclass(frozen=True)
class _PreciosElegidos:
    lista_id: UUID
    version_id: UUID
    motivo_id: UUID | None
    precios: dict[UUID, precios_service.PrecioResuelto]
    sin_precio: tuple[UUID, ...]
    observacion_de_lista: str | None
    """La lista y la versión para la auditoría (D20); `None` si son las que correspondían."""


def _validar_motivo_de_lista(
    organizacion_id: UUID, sesion: Session, motivo_id: UUID | None, *, obligatorio: bool
) -> UUID | None:
    """PRC-21, `01` §4: sin motivo solo si la organización no lo exige; con motivo, uno activo
    del ámbito `LISTA_ANTERIOR` de la organización."""
    if motivo_id is None:
        if obligatorio:
            raise MotivoInvalidoError("La organización exige un motivo para cambiar la lista.")
        return None
    motivo = configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
    if motivo is None or not motivo.activo or motivo.ambito != _AMBITO_LISTA_ANTERIOR:
        raise MotivoInvalidoError(
            f"El motivo {motivo_id} no es un motivo activo del ámbito {_AMBITO_LISTA_ANTERIOR}."
        )
    return motivo.id


def _precios_de_la_venta(
    organizacion_id: UUID,
    sesion: Session,
    *,
    lista_asignada_id: UUID | None,
    datos: DatosDeVenta,
    producto_ids: Sequence[UUID],
    momento: datetime,
    motivo_obligatorio: bool,
    permisos: PermisosDeVenta,
) -> _PreciosElegidos:
    """D6 y D7: la lista aplicable y su versión vigente al `momento`, o la lista y la versión
    que el usuario eligió (PRC-21: otra lista o una versión anterior, con `USAR_LISTA_ANTERIOR`
    y el motivo que la organización exija). La lista usada se toma `FOR SHARE` (fuera del orden
    global, ADR-047 punto 19). Lo que no se resuelve rechaza la venta entera (VTA-10)."""
    aplicable_id: UUID | None
    try:
        aplicable_id = precios_service.resolver_lista_aplicable(
            organizacion_id, sesion, lista_asignada_id=lista_asignada_id
        ).lista_id
    except DomainError as error:
        # Con lista elegida, la aplicable solo decide si la elegida es "otra" (PRC-21).
        if datos.lista_id is None or error.codigo != "SIN_LISTA_APLICABLE":
            raise
        aplicable_id = None
    lista_id = datos.lista_id if datos.lista_id is not None else aplicable_id
    if lista_id is None:  # pragma: no cover -- el `raise` de arriba lo cubre
        raise RecursoNoEncontradoError("La venta no tiene lista.")
    lista_nombre = precios_service.validar_lista_asignable(
        organizacion_id, sesion, lista_id=lista_id
    )

    if datos.lista_version_id is None:
        vigentes = precios_service.resolver_precios(
            organizacion_id,
            sesion,
            lista_id=lista_id,
            momento=momento,
            producto_ids=producto_ids,
        )
        version_id = vigentes.version_id
        precios = vigentes.precios
        sin_precio = vigentes.productos_sin_precio
        version_numero = vigentes.numero
        version_no_vigente = False
    else:
        elegida = precios_service.resolver_precios_de_version(
            organizacion_id, sesion, version_id=datos.lista_version_id, producto_ids=producto_ids
        )
        elegibles = precios_service.versiones_elegibles(
            organizacion_id, sesion, lista_id=lista_id, momento=momento
        )
        if elegida.lista_id != lista_id or elegida.version_id not in {
            version.version_id for version in elegibles
        }:
            raise VersionNoPermitidaError(
                "La versión elegida no se puede usar: es programada, está anulada o es de otra "
                "lista (PRC-21)."
            )
        vigente_id = next(
            (version.version_id for version in elegibles if version.estado == _VERSION_VIGENTE),
            None,
        )
        version_id = elegida.version_id
        precios = elegida.precios
        sin_precio = elegida.productos_sin_precio
        version_numero = elegida.numero
        version_no_vigente = version_id != vigente_id

    otra_lista = lista_id != aplicable_id
    motivo_id: UUID | None = None
    if otra_lista or version_no_vigente:
        if not permisos.puede_usar_lista_anterior:
            raise PermisoRequeridoError(f"Falta el permiso {_PERMISO_USAR_LISTA_ANTERIOR}.")
        motivo_id = _validar_motivo_de_lista(
            organizacion_id, sesion, datos.motivo_lista_id, obligatorio=motivo_obligatorio
        )
    return _PreciosElegidos(
        lista_id,
        version_id,
        motivo_id,
        precios,
        sin_precio,
        observacion_de_lista(
            lista_nombre=lista_nombre,
            version_numero=version_numero,
            otra_lista=otra_lista,
            version_no_vigente=version_no_vigente,
        ),
    )


def _precios_congelados_sin_conexion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    lista_asignada_id: UUID | None,
    datos: DatosDeVenta,
    momento: datetime,
) -> tuple[_PreciosElegidos, ObservacionDeVenta | None]:
    """D1 y D7 sin conexión: NO se resuelve ningún precio; se congela el que usó el dispositivo
    (versión, precio y unidades de cada línea). Lo único que se mira es que la versión exista en
    la organización (INV-21, SYN-06: `RECURSO_NO_ENCONTRADO` si no) y, para la observación
    `LISTA_NO_VIGENTE` (una por venta, SYN-07), cuál era la versión vigente al `occurred_at` de la
    lista aplicable al cliente. Sin lista aplicable o sin versión vigente no hay con qué comparar y
    se observa igual: nada se rechaza (SYN-05). Decisión del usuario, 2026-10-20: todas las líneas
    (y la cabecera, si la nombra) llevan la misma versión (`VERSION_NO_PERMITIDA` si no); el motivo,
    si vino, tiene que existir y ser del ámbito `LISTA_ANTERIOR` (`MOTIVO_INVALIDO` si no), pero
    puede estar inactivo: la venta ya ocurrió."""
    versiones_enviadas = [linea.lista_version_id for linea in datos.lineas]
    verificar_version_uniforme(datos.lista_version_id, versiones_enviadas)
    cabecera_id = datos.lista_version_id or versiones_enviadas[0]
    versiones = {
        version_id: precios_service.resolver_precios_de_version(
            organizacion_id, sesion, version_id=version_id, producto_ids=[]
        )
        for version_id in dict.fromkeys([cabecera_id, *versiones_enviadas])
    }
    cabecera = versiones[cabecera_id]
    if datos.lista_id is not None and datos.lista_id != cabecera.lista_id:
        raise VersionNoPermitidaError("La versión enviada es de otra lista (PRC-21).")

    aplicable_id: UUID | None
    try:
        aplicable_id = precios_service.resolver_lista_aplicable(
            organizacion_id, sesion, lista_asignada_id=lista_asignada_id
        ).lista_id
    except DomainError as error:
        if error.codigo not in _CODIGOS_DE_PRECIO_NO_RESOLUBLE:
            raise
        aplicable_id = None
    vigente_id: UUID | None = None
    if aplicable_id is not None:
        try:
            vigente_id = precios_service.resolver_precios(
                organizacion_id, sesion, lista_id=aplicable_id, momento=momento, producto_ids=[]
            ).version_id
        except DomainError as error:
            if error.codigo not in _CODIGOS_DE_PRECIO_NO_RESOLUBLE:
                raise

    motivo_id: UUID | None = None
    if datos.motivo_lista_id is not None:
        motivo = configuracion_service.obtener_motivo(
            organizacion_id, datos.motivo_lista_id, sesion
        )
        if motivo is None:
            raise RecursoNoEncontradoError(f"El motivo {datos.motivo_lista_id} no existe.")
        if motivo.ambito != _AMBITO_LISTA_ANTERIOR:
            raise MotivoInvalidoError(
                f"El motivo {motivo.id} no es del ámbito {_AMBITO_LISTA_ANTERIOR}."
            )
        motivo_id = motivo.id

    no_vigente = next((id_ for id_ in versiones if id_ != vigente_id), None)
    datos_de_lista = precios_service.datos_de_versiones(organizacion_id, sesion, [cabecera_id])
    lista_nombre = datos_de_lista[cabecera_id].lista_nombre if cabecera_id in datos_de_lista else ""
    elegidos = _PreciosElegidos(
        cabecera.lista_id,
        cabecera_id,
        motivo_id,
        {},
        (),
        observacion_de_lista(
            lista_nombre=lista_nombre,
            version_numero=cabecera.numero,
            otra_lista=cabecera.lista_id != aplicable_id,
            version_no_vigente=cabecera_id != vigente_id,
        ),
    )
    return elegidos, (
        None if no_vigente is None else observacion_lista_no_vigente(no_vigente, vigente_id)
    )


def _ubicacion_de_la_venta(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ubicacion_pedida: UUID | None,
    jornada_del_sobre: UUID | None,
    usuario_id: UUID,
    dispositivo_id: UUID,
) -> UUID:
    """D3, RUT-04: con una jornada `ABIERTA` del usuario y el dispositivo, la venta va a su
    ubicación (una distinta o una jornada de otro es `JORNADA_AJENA`); sin jornada, a la
    ubicación elegida (`UBICACION_REQUERIDA` si falta). La jornada se lee sin bloquear: el nivel 5
    lo toma después el movimiento de stock, en el orden global (D17). STK-09 (`UBICACION_TOMADA`)
    lo decide `stock`."""
    abierta = stock_service.jornada_abierta_con_ubicacion_de(
        organizacion_id, sesion, usuario_id=usuario_id, dispositivo_id=dispositivo_id
    )
    if jornada_del_sobre is not None and (
        abierta is None or abierta.jornada_id != jornada_del_sobre
    ):
        raise JornadaAjenaError(
            f"La jornada {jornada_del_sobre} no es la jornada abierta de este usuario y "
            "dispositivo."
        )
    if abierta is not None:
        if ubicacion_pedida is not None and ubicacion_pedida != abierta.ubicacion_id:
            raise JornadaAjenaError(
                "Con una jornada abierta la venta sale de la ubicación de la jornada."
            )
        return abierta.ubicacion_id
    if ubicacion_pedida is None:
        raise UbicacionRequeridaError("Sin una jornada abierta hay que elegir la ubicación.")
    return ubicacion_pedida


def _snapshot_de_credito(
    datos_de_credito: clientes_service.DatosDeCredito | None,
    evaluacion: clientes_service.ResultadoCredito | None,
    saldo_considerado: Decimal,
) -> dict[str, object]:
    """CRE-10, D12: lo que la venta congela de su evaluación de crédito. Sin límite (sin control)
    el límite, el disponible y el exceso quedan vacíos y la resolución es `SIN_EXCESO`. Sin
    evaluación (camino sin conexión, grupo 10) las columnas quedan vacías."""
    if datos_de_credito is None or evaluacion is None:
        return {}
    sin_control = datos_de_credito.limite is None
    return {
        "credito_limite": datos_de_credito.limite,
        "credito_saldo_considerado": saldo_considerado,
        "credito_disponible": evaluacion.disponible,
        "credito_exceso": None if sin_control else evaluacion.exceso,
        "credito_politica": datos_de_credito.politica,
        "credito_resolucion": evaluacion.resolucion,
        "credito_autorizador_id": (
            None if evaluacion.autorizador_id is None else UUID(evaluacion.autorizador_id)
        ),
    }


def _motivo_del_descuento(
    organizacion_id: UUID,
    sesion: Session,
    motivo_id: UUID | None,
    *,
    permitir_inactivo: bool = False,
) -> tuple[UUID, str] | None:
    """DSC-06, TR-09 (D11): el motivo del descuento manual, si vino, existe en la organización
    (404 si no, INV-21) y es un motivo activo del ámbito `DESCUENTO_MANUAL` (`MOTIVO_INVALIDO`
    si no). Sin conexión (`permitir_inactivo`, D10) uno inactivo vale: la venta ya ocurrió.
    Devuelve su identificador y su nombre, o `None` si no se envió."""
    if motivo_id is None:
        return None
    motivo = configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
    if motivo is None:
        raise RecursoNoEncontradoError(f"El motivo {motivo_id} no existe.")
    if (not motivo.activo and not permitir_inactivo) or motivo.ambito != _AMBITO_DESCUENTO_MANUAL:
        raise MotivoInvalidoError(
            f"El motivo {motivo_id} no es un motivo activo del ámbito {_AMBITO_DESCUENTO_MANUAL}."
        )
    return motivo.id, motivo.nombre


def _autorizador_vigente(
    organizacion_id: UUID, sesion: Session, autorizador_id: UUID | None
) -> clientes_service.Autorizador | None:
    """CRE-05, DSC-06 (D6, D9): el autorizador con los permisos que tiene hoy. Uno que no existe
    en la organización (o es de otra) no se encuentra (404, INV-21, SYN-06). No verifica ningún
    PIN."""
    if autorizador_id is None:
        return None
    datos = identidad_service.obtener_datos_para_descuento_manual(
        organizacion_id, autorizador_id, sesion
    )
    if datos is None:
        raise RecursoNoEncontradoError(f"El autorizador {autorizador_id} no existe.")
    return clientes_service.Autorizador(str(datos.usuario_id), datos.permisos)


def _descuentos_calculados(
    calculo_lineas: Sequence[ResultadoLineaVenta],
) -> dict[UUID, list[DescuentoDeLinea]]:
    return {
        UUID(linea.id): [
            DescuentoDeLinea(
                descuento.origen,
                None if descuento.regla_id is None else UUID(descuento.regla_id),
                descuento.porcentaje,
                descuento.importe,
            )
            for descuento in linea.descuentos
        ]
        for linea in calculo_lineas
    }


def _verificar_pins(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    requeridos: Sequence[tuple[UUID, str, DomainError]],
    credenciales: Mapping[UUID, SecretStr],
    intentante_id: UUID,
    dispositivo_id: UUID,
) -> None:
    """Paso 7 de D18: verifica el PIN de cada autorizador que hace falta, en el orden recibido
    (descuento primero). Una persona que autoriza descuento y crédito se verifica una sola vez
    (D4) con la credencial que envió. Sin credencial para un autorizador necesario se lanza el
    error de autorización requerida que se trae (`design.md` D2). El permiso del autorizador y el
    bloqueo se miran dentro de `verificar_pin_de_autorizacion`, antes de verificar ni contar."""
    verificados: set[UUID] = set()
    for autorizador_id, permiso, sin_credencial in requeridos:
        if autorizador_id in verificados:
            continue
        credencial = credenciales.get(autorizador_id)
        if credencial is None:
            raise sin_credencial
        identidad_service.verificar_pin_de_autorizacion(
            organizacion_id,
            sesion,
            reloj,
            autorizador_id=autorizador_id,
            intentante_id=intentante_id,
            pin=credencial.get_secret_value(),
            permiso=permiso,
            dispositivo_id=dispositivo_id,
        )
        verificados.add(autorizador_id)


def _auditar_descuento_manual(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    venta: Venta,
    porcentaje_maximo: Decimal | None,
    evaluado: descuentos_service.ResultadoManual | None,
    motivo_id: UUID | None,
    usuario_id: UUID,
    sin_conexion: bool = False,
) -> None:
    """AUD-01, AUD-02 (D19): la fila `DESCUENTO_MANUAL` (entidad `venta`) de una venta con
    descuento manual informado: porcentaje máximo, tope aplicado y resolución, el motivo y el
    autorizador (nulo dentro del tope). Sin descuento manual no hay fila. Sin conexión (tarea
    10.1) `despues` suma `modo = OFFLINE`; la resolución es la que declaró el dispositivo y el
    tope el de hoy."""
    if evaluado is None or porcentaje_maximo is None:
        return
    identidad_service.registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion=_ACCION_DESCUENTO_MANUAL,
        entidad=_ENTIDAD_VENTA,
        entidad_id=venta.id,
        ocurrido_en=venta.occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=venta.dispositivo_id,
        despues={
            "porcentaje_maximo": f"{porcentaje_maximo:.6f}",
            "tope_aplicado": f"{evaluado.tope_aplicado:.6f}",
            "resolucion": evaluado.resolucion,
            **({"modo": _MODO_OFFLINE} if sin_conexion else {}),
        },
        motivo_id=motivo_id,
        autorizador_id=None if evaluado.autorizador_id is None else UUID(evaluado.autorizador_id),
        operation_id=venta.operation_id,
        origen="COMANDO",
    )


def _auditar_autorizacion_de_credito(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    venta: Venta,
    evaluacion: clientes_service.ResultadoCredito | None,
    datos_de_credito: clientes_service.DatosDeCredito | None,
    saldo_considerado: Decimal,
    usuario_id: UUID,
    sin_conexion: bool = False,
) -> None:
    """AUD-01, AUD-02 (D19): la fila `AUTORIZACION_CREDITO` (entidad `venta`) de una venta cuya
    resolución de crédito no es `SIN_EXCESO`: el snapshot congelado y el autorizador (nulo si fue
    una advertencia aceptada). Sin conexión (tarea 10.1) `despues` suma `modo = OFFLINE`."""
    if evaluacion is None or datos_de_credito is None or evaluacion.resolucion == "SIN_EXCESO":
        return
    snapshot = _snapshot_de_credito(datos_de_credito, evaluacion, saldo_considerado)
    identidad_service.registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion=_ACCION_AUTORIZACION_CREDITO,
        entidad=_ENTIDAD_VENTA,
        entidad_id=venta.id,
        ocurrido_en=venta.occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=venta.dispositivo_id,
        despues={
            "limite": _texto_o_nulo(snapshot["credito_limite"]),
            "saldo_considerado": _texto_o_nulo(snapshot["credito_saldo_considerado"]),
            "disponible": _texto_o_nulo(snapshot["credito_disponible"]),
            "exceso": _texto_o_nulo(snapshot["credito_exceso"]),
            "politica": snapshot["credito_politica"],
            "resolucion": snapshot["credito_resolucion"],
            **({"modo": _MODO_OFFLINE} if sin_conexion else {}),
        },
        autorizador_id=(
            None if evaluacion.autorizador_id is None else UUID(evaluacion.autorizador_id)
        ),
        operation_id=venta.operation_id,
        origen="COMANDO",
    )


def _texto_o_nulo(valor: object) -> str | None:
    return None if valor is None else str(valor)


def _observacion_de_exceso(
    codigo: str, limite: Decimal | None, saldo_considerado: Decimal, exceso: Decimal
) -> ObservacionDeVenta:
    """El detalle común de `EXCESO_CREDITO_ADVERTIDO` y `EXCESO_CREDITO_AUTORIZADO_OFFLINE`."""
    return ObservacionDeVenta(
        codigo,
        {
            "limite": None if limite is None else str(limite),
            "saldo_considerado": str(saldo_considerado),
            "exceso": str(exceso),
        },
    )


@dataclass(frozen=True)
class _LineaFinal:
    """Lo que se guarda de una línea: sus descuentos (con conexión, los del servidor, que ya
    coincidieron con los del usuario; sin conexión, los del dispositivo) y sus importes."""

    descuentos: list[DescuentoDeLinea]
    descuento_total: Decimal
    neto: Decimal


@dataclass(frozen=True)
class _TotalesFinales:
    total_neto: Decimal
    total_iva: Decimal
    total: Decimal


@dataclass(frozen=True)
class _DescuentoSinConexion:
    """Lo que deja la revisión sin conexión del descuento manual (D10): la evaluación declarada
    (resolución del dispositivo y tope de hoy; `None` sin descuento manual), el porcentaje
    evaluado, el motivo, las causas de `DESCUENTO_DIFIERE` que salieron del descuento manual y la
    `AUTORIZACION_OFFLINE`."""

    evaluado: descuentos_service.ResultadoManual | None
    porcentaje_maximo: Decimal | None
    motivo: tuple[UUID, str] | None
    causas: list[dict[str, object]]
    autorizacion: ObservacionDeVenta | None


_SIN_DESCUENTO_MANUAL = _DescuentoSinConexion(None, None, None, [], None)
_RESOLUCION_MANUAL_DECLARADA = {
    "PIN_SUPERVISOR": _RESOLUCION_DESCUENTO_POR_SUPERVISOR,
    "PERMISO_PROPIO": "PERMISO_PROPIO",
}


def _credito_enviado_o_inconsistente(datos: DatosDeVenta) -> CreditoDelDispositivo:
    """Paso 0 de D18 sin conexión (D7, decisión del usuario del 2026-10-23): el `credito` del
    dispositivo es obligatorio y su forma tiene que ser válida (`CREDITO_INCONSISTENTE`)."""
    credito = datos.credito_del_dispositivo
    if credito is None:
        raise clientes_service.CreditoInconsistenteError(
            "Una venta sin conexión trae la evaluación de crédito del dispositivo."
        )
    clientes_service.verificar_forma_del_credito_del_dispositivo(
        limite=credito.limite,
        saldo_considerado=credito.saldo_considerado,
        politica=credito.politica,
        resolucion=credito.resolucion,
        autorizador_id=credito.autorizador_id,
    )
    return credito


def _descuento_manual_sin_conexion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    datos: DatosDeVenta,
    porcentaje_del_motor: Decimal | None,
    usuario_id: UUID,
) -> _DescuentoSinConexion:
    """D10 puntos 3 y 4, D9, paso 5 de D18: reevalúa con los datos de hoy el descuento manual que
    informó el dispositivo. NUNCA rechaza por la regla de negocio: cada rechazo que tendría con
    conexión (`TOPE`, `PERMISO`, `DESHABILITADO`, `MOTIVO`, `AUTORIZADOR_SIN_PERMISO`) es una
    causa de `DESCUENTO_DIFIERE`. Solo rechaza lo inexistente (motivo, autorizador; SYN-06) y un
    motivo de otro ámbito. Lee el permiso vigente del autorizador y no verifica ningún PIN."""
    manuales = [
        descuento
        for linea in datos.lineas
        for descuento in linea.descuentos
        if descuento.origen == "MANUAL"
    ]
    if not manuales:
        return _SIN_DESCUENTO_MANUAL
    porcentaje = porcentaje_del_motor
    if porcentaje is None:
        informados = [d.porcentaje for d in manuales if d.porcentaje is not None]
        if not informados:
            return _SIN_DESCUENTO_MANUAL
        porcentaje = max(informados)

    motivo = _motivo_del_descuento(
        organizacion_id, sesion, datos.motivo_descuento_id, permitir_inactivo=True
    )
    enviado = datos.descuento_autorizador_id
    autorizador = (
        None
        if enviado is None or enviado == usuario_id
        else _autorizador_vigente(organizacion_id, sesion, enviado)
    )
    usuario = identidad_service.obtener_datos_para_descuento_manual(
        organizacion_id, usuario_id, sesion
    )
    if usuario is None:
        raise RecursoNoEncontradoError(f"El usuario {usuario_id} no existe.")
    tope = usuario.tope_rol if usuario.tope_propio is None else usuario.tope_propio

    causas: list[dict[str, object]] = []
    for codigo in descuentos_service.rechazos_del_descuento_manual(
        organizacion_id,
        sesion,
        usuario_id=usuario_id,
        porcentaje_maximo=porcentaje,
        motivo=None if motivo is None else motivo[1],
        autorizador_id=None if autorizador is None else UUID(autorizador.usuario_id),
    ):
        causa = causa_de_rechazo_del_manual(codigo)
        if causa is None:
            raise RuntimeError(f"Rechazo ajeno al descuento manual: {codigo}.")
        causas.append(detalle_de_causa_del_manual(causa, porcentaje=porcentaje, tope=tope))

    resolucion, autorizador_declarado = autorizacion_declarada_de_descuento(
        usuario_id=usuario_id,
        autorizador_enviado=enviado,
        usuario_puede_autorizar=_PERMISO_AUTORIZAR_DESCUENTO in usuario.permisos,
        porcentaje_maximo=porcentaje,
        tope=tope,
    )
    evaluado = descuentos_service.ResultadoManual(
        tope,
        resolucion is not None,
        _RESOLUCION_MANUAL_DECLARADA.get(resolucion or "", "DENTRO_DEL_TOPE"),  # type: ignore[arg-type]
        None if autorizador_declarado is None else str(autorizador_declarado),
    )
    observacion = None
    if resolucion is not None:
        permisos_del_autorizador = usuario.permisos if autorizador is None else autorizador.permisos
        observacion = observacion_autorizacion_offline(
            tipo=_TIPO_AUTORIZACION_DESCUENTO,
            resolucion=resolucion,
            autorizador_id=autorizador_declarado,
            autorizador_con_permiso=_PERMISO_AUTORIZAR_DESCUENTO in permisos_del_autorizador,
        )
    return _DescuentoSinConexion(evaluado, porcentaje, motivo, causas, observacion)


@dataclass(frozen=True)
class _CreditoSinConexion:
    """Lo que deja la revisión sin conexión del crédito (D7): la evaluación del dispositivo
    congelada, los datos con los que se congela y las observaciones que corresponden."""

    evaluacion: clientes_service.ResultadoCredito
    datos: clientes_service.DatosDeCredito
    saldo_considerado: Decimal
    observaciones: list[ObservacionDeVenta]


def _credito_sin_conexion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    credito: CreditoDelDispositivo,
    cliente_id: UUID,
    es_consumidor_final: bool,
    total: Decimal,
    cobranza: Decimal,
    saldo_real: Decimal,
) -> _CreditoSinConexion:
    """D7, D17, pasos 6 y 7 de D18. Congela la evaluación del dispositivo (el servidor calcula
    disponible y exceso con el mismo motor sobre SUS números), recalcula con el saldo real del
    nivel 1 y la política vigente y observa; nunca rechaza por crédito (CRE-09, SYN-05). Lo único
    que rechaza es lo incoherente (`CREDITO_INCONSISTENTE`) y un autorizador inexistente (404).
    El consumidor final se congela con límite cero, sin comparar su resolución con el exceso y sin
    observaciones de crédito: su regla es `CONSUMIDOR_FINAL_CON_DEUDA` (D17)."""
    limite = _CERO if es_consumidor_final else credito.limite
    evaluacion = clientes_service.evaluar_credito_del_dispositivo(
        limite=limite,
        saldo_considerado=credito.saldo_considerado,
        total_venta=total,
        cobranza=cobranza,
        politica=credito.politica,
        resolucion=credito.resolucion,
        autorizador_id=credito.autorizador_id,
        coherencia_del_exceso=not es_consumidor_final,
    )
    assert credito.saldo_considerado is not None and credito.politica is not None
    datos = clientes_service.DatosDeCredito(limite, credito.politica, None, None)
    autorizador = None
    if evaluacion.autorizador_id is not None:
        autorizador = _autorizador_vigente(organizacion_id, sesion, credito.autorizador_id)
    if es_consumidor_final:
        return _CreditoSinConexion(evaluacion, datos, credito.saldo_considerado, [])

    observaciones: list[ObservacionDeVenta] = []
    vigentes = clientes_service.resolver_datos_de_credito(organizacion_id, cliente_id, sesion)
    real = clientes_service.calcular_exceso(
        limite=vigentes.limite, saldo_actual=saldo_real, total_venta=total, cobranza=cobranza
    )
    if real.exceso > _CERO and evaluacion.exceso == _CERO:
        # CRE-09: el real da exceso y el dispositivo no lo vio; las dos evaluaciones en el detalle.
        observaciones.append(
            ObservacionDeVenta(
                CODIGO_EXCESO_CREDITO_DETECTADO_SYNC,
                {
                    "dispositivo": {
                        "limite": _texto_o_nulo(limite),
                        "saldo_considerado": str(credito.saldo_considerado),
                        "disponible": _texto_o_nulo(evaluacion.disponible),
                        "exceso": str(evaluacion.exceso),
                        "politica": credito.politica,
                        "resolucion": evaluacion.resolucion,
                    },
                    "servidor": {
                        "limite": _texto_o_nulo(vigentes.limite),
                        "saldo_considerado": str(saldo_real),
                        "disponible": _texto_o_nulo(real.disponible),
                        "exceso": str(real.exceso),
                        "politica": vigentes.politica,
                    },
                },
            )
        )
    if evaluacion.resolucion == _RESOLUCION_CREDITO_ADVERTIDA:
        observaciones.append(
            _observacion_de_exceso(
                CODIGO_EXCESO_CREDITO_ADVERTIDO,
                limite,
                credito.saldo_considerado,
                evaluacion.exceso,
            )
        )
    elif evaluacion.resolucion == _RESOLUCION_CREDITO_POR_TOLERANCIA:
        observaciones.append(
            _observacion_de_exceso(
                CODIGO_EXCESO_CREDITO_AUTORIZADO_OFFLINE,
                limite,
                credito.saldo_considerado,
                evaluacion.exceso,
            )
        )
    elif autorizador is not None:
        observaciones.append(
            observacion_autorizacion_offline(
                tipo=_TIPO_AUTORIZACION_CREDITO,
                resolucion=evaluacion.resolucion,
                autorizador_id=UUID(autorizador.usuario_id),
                autorizador_con_permiso=_PERMISO_SUPERAR_CREDITO in autorizador.permisos,
            )
        )
    return _CreditoSinConexion(evaluacion, datos, credito.saldo_considerado, observaciones)


def confirmar_venta(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    datos: DatosDeVenta,
    permisos: PermisosDeVenta,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
    jornada_del_sobre: UUID | None,
    modo: str = _MODO_ONLINE,
    credenciales: Mapping[UUID, SecretStr] | None = None,
) -> ResultadoDeVenta:
    """`VENTA_CONFIRMAR` (VTA-12, INV-01, INV-14; `design.md` D1, D17), con conexión por defecto
    o sin ella (`modo="OFFLINE"`, tarea 11.2). Ver el orden y las diferencias en el docstring del
    módulo. Cualquier error revierte todo (lo hace el bus).

    `credenciales` es el dato efímero de D2 (change 18b): el PIN de cada autorizador, por su
    identificador. Nunca se guarda, se registra ni se incluye en el resultado."""
    sin_conexion = modo == _MODO_OFFLINE
    if sin_conexion:
        verificar_unidades_de_referencia(
            [
                ValoresDeLinea(
                    linea.linea_id,
                    linea.lista_version_id,
                    linea.precio_referencia,
                    linea.unidades_referencia,
                    linea.importe_bruto,
                )
                for linea in datos.lineas
            ]
        )
    # 0) Validación pura y venta libre.
    pedidas = [
        LineaPedida(linea.producto_id, linea.presentacion_id, linea.cantidad)
        for linea in datos.lineas
    ]
    validar_lineas(pedidas)
    credito_del_dispositivo: CreditoDelDispositivo | None = None
    if sin_conexion:
        # Change 18b, tarea 10.1 (D10 punto 1, D7 punto 1): lo malformado se rechaza antes de
        # leer nada; el `credito` del dispositivo es obligatorio.
        verificar_descuentos_offline(
            [
                LineaEnviada(linea.linea_id, linea.importe_bruto, linea.descuentos)
                for linea in datos.lineas
            ],
            datos.total,
        )
        credito_del_dispositivo = _credito_enviado_o_inconsistente(datos)
    if repository.existe_venta(organizacion_id, datos.venta_id, sesion):
        raise VentaDuplicadaError(f"El identificador de venta {datos.venta_id} ya fue usado.")

    # Número (VTA-06, D4): formato y prefijo del dispositivo de la sesión, y libre en la
    # organización. Lecturas sin candado: el último candado sigue siendo el del paso 9.
    numeracion = identidad_service.obtener_numeracion_de_dispositivo(
        organizacion_id, sesion, dispositivo_id=dispositivo_id
    )
    if numeracion is None:
        raise RecursoNoEncontradoError(f"El dispositivo {dispositivo_id} no existe.")
    correlativo = correlativo_de(datos.numero, numeracion.prefijo)
    if repository.existe_numero(organizacion_id, datos.numero, sesion):
        raise NumeroDuplicadoError(f"El número {datos.numero} ya fue usado.")

    # 1) Configuración, momento, cliente, lista y precios.
    configuracion = identidad_service.obtener_configuracion(organizacion_id, sesion)
    if configuracion is None:
        raise RecursoNoEncontradoError("La organización no tiene configuración.")
    validar_momento(
        occurred_at, reloj.now(), configuracion.desvio_reloj_max_segundos, offline=sin_conexion
    )
    cliente = clientes_service.obtener_cliente_por_id(organizacion_id, datos.cliente_id, sesion)
    if cliente is None:
        raise RecursoNoEncontradoError(f"El cliente {datos.cliente_id} no existe.")
    # El estado del cliente va en el paso 1 (D17); el contado del consumidor final, con el
    # total ya calculado (paso 4).
    importe_cobranza = (
        None
        if datos.cobranza is None
        else sum((medio.importe for medio in datos.cobranza.medios), _CERO)
    )
    observaciones_de_venta: list[ObservacionDeVenta] = []
    if not sin_conexion:
        evaluar_cliente(
            cliente_id=cliente.id,
            estado=cliente.estado,
            es_consumidor_final=False,
            puede_vender_suspendido=permisos.puede_vender_suspendido,
            total=_CERO,
            cobranza=importe_cobranza,
            offline=False,
        )
    producto_ids = sorted({linea.producto_id for linea in datos.lineas})
    if sin_conexion:
        elegidos, lista_no_vigente = _precios_congelados_sin_conexion(
            organizacion_id,
            sesion,
            lista_asignada_id=cliente.lista_precio_id,
            datos=datos,
            momento=occurred_at,
        )
        if lista_no_vigente is not None:
            observaciones_de_venta.append(lista_no_vigente)
    else:
        elegidos = _precios_de_la_venta(
            organizacion_id,
            sesion,
            lista_asignada_id=cliente.lista_precio_id,
            datos=datos,
            producto_ids=producto_ids,
            momento=occurred_at,
            motivo_obligatorio=configuracion.motivo_obligatorio_lista,
            permisos=permisos,
        )

    # 2) Nivel 1: el saldo del cliente.
    saldo_considerado = cuentas_corrientes_service.bloquear_saldo(
        organizacion_id, sesion, reloj, cuenta_tipo=_CUENTA_CLIENTE, entidad_id=cliente.id
    )

    # 3) Nivel 2: productos `FOR SHARE` por identificador ascendente y sus presentaciones.
    tomados = [
        catalogo_service.obtener_producto_para_compartir(organizacion_id, producto_id, sesion)
        for producto_id in producto_ids
    ]
    productos = {producto.id: producto for producto in tomados if producto is not None}
    faltantes = [producto_id for producto_id in producto_ids if producto_id not in productos]
    if faltantes:
        raise RecursoNoEncontradoError(f"El producto {faltantes[0]} no existe.")
    presentaciones = catalogo_service.presentaciones_para_venta(
        organizacion_id, producto_ids, sesion
    )

    # 4) El motor recalcula y se compara con lo que vio el usuario.
    if not sin_conexion:
        verificar_productos_con_precio(
            [
                ProductoSinPrecio(producto_id, productos[producto_id].nombre)
                for producto_id in elegidos.sin_precio
                if producto_id in productos
            ]
        )
    lineas_de_calculo: list[LineaCalculo] = []
    unidades: dict[UUID, int] = {}
    for linea in datos.lineas:
        producto = productos[linea.producto_id]
        presentacion = next(
            (
                p
                for p in presentaciones.get(linea.producto_id, [])
                if p.presentacion_id == linea.presentacion_id
            ),
            None,
        )
        if presentacion is None:
            raise RecursoNoEncontradoError(f"La presentación {linea.presentacion_id} no existe.")
        if not sin_conexion:  # D1 punto 5: sin conexion un desactivado se acepta sin observar
            validar_producto_y_presentacion(
                producto_activo=producto.activo,
                presentacion_activa=presentacion.activo,
                presentacion_usar_en_venta=presentacion.usar_en_venta,
            )
        unidades[linea.linea_id] = presentacion.unidades_base
        alicuota = configuracion_service.obtener_alicuota_por_id(
            organizacion_id, producto.alicuota_id, sesion
        )
        if sin_conexion:  # se congela lo que uso el dispositivo (D1 punto 4)
            precio = precios_service.PrecioResuelto(
                precio_final=linea.precio_referencia,
                unidades_referencia=linea.unidades_referencia,
            )
        else:
            precio = elegidos.precios[linea.producto_id]
        lineas_de_calculo.append(
            LineaCalculo(
                id=str(linea.linea_id),
                precio_referencia=precio.precio_final,
                unidades_referencia=precio.unidades_referencia,
                cantidad_base=cantidad_base(linea.cantidad, presentacion.unidades_base),
                alicuota=Decimal("0") if alicuota is None else alicuota.valor,
                producto_id=str(producto.id),
                categoria_id=str(producto.categoria_id),
                marca_id="" if producto.marca_id is None else str(producto.marca_id),
                descuento_manual=linea.descuento_manual,
            )
        )
    # Las reglas vigentes al momento de la operación (TR-05) y los porcentajes manuales enviados,
    # con y sin conexión. Sin conexión el resultado solo se compara con lo que registró el
    # dispositivo (causa `CALCULO`); lo que se guarda es lo del dispositivo.
    reglas = descuentos_service.reglas_aplicables(organizacion_id, sesion, occurred_at)
    calculo = calcular_venta(
        configuracion.modo_impositivo,
        lineas_de_calculo,
        reglas,
        datos.descuento_manual_general,
    )
    causas_de_descuento: list[dict[str, object]] = []
    if sin_conexion:
        # SYN-06: una regla inexistente o ajena es una dependencia inexistente.
        reglas_enviadas = {
            descuento.regla_id
            for linea in datos.lineas
            for descuento in linea.descuentos
            if descuento.regla_id is not None
        }
        existentes = descuentos_service.nombres_de_reglas(organizacion_id, reglas_enviadas, sesion)
        faltante = next((r for r in sorted(reglas_enviadas) if r not in existentes), None)
        if faltante is not None:
            raise RecursoNoEncontradoError(f"La regla de descuento {faltante} no existe.")
        causas_de_descuento = diferencias_de_calculo(
            {linea.linea_id: list(linea.descuentos) for linea in datos.lineas},
            _descuentos_calculados(calculo.lineas),
        )
        lineas_finales = [
            _LineaFinal(
                list(linea.descuentos),
                sum((d.importe for d in linea.descuentos), _CERO),
                resultado.bruto - sum((d.importe for d in linea.descuentos), _CERO),
            )
            for linea, resultado in zip(datos.lineas, calculo.lineas, strict=True)
        ]
        total_neto_final = sum((linea.neto for linea in lineas_finales), _CERO)
        totales = _TotalesFinales(
            total_neto_final, calculo.total_iva, total_neto_final + calculo.total_iva
        )
    else:
        por_linea = _descuentos_calculados(calculo.lineas)
        lineas_finales = [
            _LineaFinal(por_linea[UUID(resultado.id)], resultado.descuento_total, resultado.neto)
            for resultado in calculo.lineas
        ]
        totales = _TotalesFinales(calculo.total_neto, calculo.total_iva, calculo.total)
    esperados = [
        ValoresDeLinea(
            linea.linea_id,
            linea.lista_version_id,
            linea.precio_referencia,
            linea.unidades_referencia,
            linea.importe_bruto,
        )
        for linea in datos.lineas
    ]
    if sin_conexion:
        # D2 sin conexion: lo enviado debe ser lo que da el motor sobre lo congelado; si no, el
        # comando esta malformado (SYN-06). Recien despues, el cliente observa (nunca rechaza).
        verificar_totales_offline(
            esperados,
            {
                linea.linea_id: resultado.bruto
                for linea, resultado in zip(datos.lineas, calculo.lineas, strict=True)
            },
            datos.total,
            totales.total,
        )
        del_cliente = evaluar_cliente(
            cliente_id=cliente.id,
            estado=cliente.estado,
            es_consumidor_final=cliente.es_consumidor_final,
            puede_vender_suspendido=permisos.puede_vender_suspendido,
            total=totales.total,
            cobranza=importe_cobranza,
            offline=True,
        )
        if del_cliente is not None:
            observaciones_de_venta.insert(0, del_cliente)
    else:
        evaluar_cliente(
            cliente_id=cliente.id,
            estado=cliente.estado,
            es_consumidor_final=cliente.es_consumidor_final,
            puede_vender_suspendido=permisos.puede_vender_suspendido,
            total=totales.total,
            cobranza=importe_cobranza,
            offline=False,
        )
        resueltos = [
            ValoresDeLinea(
                linea.linea_id,
                elegidos.version_id,
                calculada.precio_referencia,
                calculada.unidades_referencia,
                resultado.bruto,
            )
            for linea, calculada, resultado in zip(
                datos.lineas, lineas_de_calculo, calculo.lineas, strict=True
            )
        ]
        # Precedencia (D18): precio -> descuento -> total.
        comparar_precios_de_lineas(esperados, resueltos, calculo.total)
        descuentos_del_servidor = _descuentos_calculados(calculo.lineas)
        comparar_descuentos(
            {linea.linea_id: list(linea.descuentos) for linea in datos.lineas},
            descuentos_del_servidor,
        )
        comparar_con_esperado(esperados, resueltos, datos.total, calculo.total)

    # 5) Descuento manual, una sola vez con el mayor porcentaje aplicado (DSC-06). Solo lee.
    descuento_evaluado: descuentos_service.ResultadoManual | None = None
    motivo_del_descuento: tuple[UUID, str] | None = None
    porcentaje_manual_maximo = calculo.porcentaje_manual_maximo
    observaciones_de_autorizacion: list[ObservacionDeVenta] = []
    if sin_conexion:
        # D10 puntos 3 y 4, D9: se reevalúa con los datos de hoy, sin rechazar por la regla de
        # negocio: cada rechazo que tendría con conexión es una causa de `DESCUENTO_DIFIERE`.
        revisado = _descuento_manual_sin_conexion(
            organizacion_id,
            sesion,
            datos=datos,
            porcentaje_del_motor=calculo.porcentaje_manual_maximo,
            usuario_id=usuario_id,
        )
        descuento_evaluado = revisado.evaluado
        motivo_del_descuento = revisado.motivo
        porcentaje_manual_maximo = revisado.porcentaje_maximo
        causas_de_descuento.extend(revisado.causas)
        if revisado.autorizacion is not None:
            observaciones_de_autorizacion.append(revisado.autorizacion)
    elif calculo.porcentaje_manual_maximo is not None:
        motivo_del_descuento = _motivo_del_descuento(
            organizacion_id, sesion, datos.motivo_descuento_id
        )
        descuento_evaluado = descuentos_service.evaluar_descuento_manual(
            organizacion_id,
            sesion,
            usuario_id=usuario_id,
            porcentaje_maximo=calculo.porcentaje_manual_maximo,
            motivo=None if motivo_del_descuento is None else motivo_del_descuento[1],
            autorizador_id=datos.descuento_autorizador_id,
        )

    # 6) Crédito con el saldo bloqueado del paso 2 y el total del paso 4 (CRE-02, D5, D6).
    credito_evaluado: clientes_service.ResultadoCredito | None = None
    datos_de_credito: clientes_service.DatosDeCredito | None = None
    saldo_del_snapshot = saldo_considerado
    if sin_conexion:
        assert credito_del_dispositivo is not None  # ya verificado en el paso 0
        revisado_de_credito = _credito_sin_conexion(
            organizacion_id,
            sesion,
            credito=credito_del_dispositivo,
            cliente_id=cliente.id,
            es_consumidor_final=cliente.es_consumidor_final,
            total=totales.total,
            cobranza=_CERO if importe_cobranza is None else importe_cobranza,
            saldo_real=saldo_considerado,
        )
        credito_evaluado = revisado_de_credito.evaluacion
        datos_de_credito = revisado_de_credito.datos
        saldo_del_snapshot = revisado_de_credito.saldo_considerado
        observaciones_de_autorizacion.extend(revisado_de_credito.observaciones)
    else:
        datos_de_credito = clientes_service.resolver_datos_de_credito(
            organizacion_id, cliente.id, sesion
        )
        credito_evaluado = clientes_service.evaluar_credito(
            limite=datos_de_credito.limite,
            saldo_actual=saldo_considerado,
            total_venta=totales.total,
            cobranza=_CERO if importe_cobranza is None else importe_cobranza,
            politica=datos_de_credito.politica,
            tolerancia_tipo=datos_de_credito.tolerancia_tipo,
            tolerancia_valor=datos_de_credito.tolerancia_valor,
            modo="CON_CONEXION",
            acepta_exceso=datos.acepta_exceso,
            usuario_id=str(usuario_id),
            permisos_usuario=permisos.codigos,
            autorizador=_autorizador_vigente(organizacion_id, sesion, datos.credito_autorizador_id),
        )

    # 7) PIN de los autorizadores que hacen falta (D2, D3, D4).
    if not sin_conexion:
        requeridos: list[tuple[UUID, str, DomainError]] = []
        if (
            descuento_evaluado is not None
            and descuento_evaluado.resolucion == _RESOLUCION_DESCUENTO_POR_SUPERVISOR
            and descuento_evaluado.autorizador_id is not None
        ):
            requeridos.append(
                (
                    UUID(descuento_evaluado.autorizador_id),
                    _PERMISO_AUTORIZAR_DESCUENTO,
                    AutorizacionRequeridaError(
                        "El descuento sobre el tope necesita el PIN del autorizador."
                    ),
                )
            )
        if (
            credito_evaluado is not None
            and credito_evaluado.resolucion == _RESOLUCION_CREDITO_POR_PIN
            and credito_evaluado.autorizador_id is not None
        ):
            requeridos.append(
                (
                    UUID(credito_evaluado.autorizador_id),
                    _PERMISO_SUPERAR_CREDITO,
                    AutorizacionCreditoRequeridaError(
                        "El exceso de crédito necesita el PIN del autorizador."
                    ),
                )
            )
        _verificar_pins(
            organizacion_id,
            sesion,
            reloj,
            requeridos=requeridos,
            credenciales=credenciales or {},
            intentante_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )

    # 8) Niveles 2 a 5: egreso de stock `VENTA`, que devuelve el costo de cada línea.
    if sin_conexion:
        # D3: sin conexion, la jornada del sobre y su ubicacion, siempre (RUT-04).
        if jornada_del_sobre is None:
            raise JornadaAjenaError("Una venta sin conexion pertenece a una jornada del sobre.")
        de_la_jornada = stock_service.ubicacion_de_jornada(
            organizacion_id, sesion, jornada_id=jornada_del_sobre
        )
        if de_la_jornada is None:
            raise RecursoNoEncontradoError(f"La jornada {jornada_del_sobre} no existe.")
        ubicacion_id = de_la_jornada
    else:
        ubicacion_id = _ubicacion_de_la_venta(
            organizacion_id,
            sesion,
            ubicacion_pedida=datos.ubicacion_id,
            jornada_del_sobre=jornada_del_sobre,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )
    movimientos = stock_service.registrar_movimientos(
        organizacion_id,
        sesion,
        reloj,
        lineas=[
            LineaDeMovimiento(
                producto_id=linea.producto_id,
                ubicacion_id=ubicacion_id,
                cantidad_base=-calculada.cantidad_base,
                tipo="VENTA",
                costo_unitario=None,
                origen_tipo=_ORIGEN_TIPO_VENTA,
                origen_id=datos.venta_id,
            )
            for linea, calculada in zip(datos.lineas, lineas_de_calculo, strict=True)
        ],
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
        occurred_at=occurred_at,
        permitir_negativo=permisos.puede_stock_negativo,
        negativo_sin_condicion=sin_conexion,
        puede_operar_ubicacion_tomada=permisos.puede_liberar_ubicacion,
        venta_sin_conexion=sin_conexion,
    )
    sin_costo = [
        linea.producto_id
        for linea, movimiento in zip(datos.lineas, movimientos, strict=True)
        if movimiento.movimiento.costo_unitario is None
    ]
    if sin_costo and not sin_conexion:
        raise ProductoSinCostoError(
            "Hay productos sin costo promedio: primero cargá una compra o el stock inicial.",
            extension={
                "productos": [
                    {"producto_id": str(producto_id), "nombre": productos[producto_id].nombre}
                    for producto_id in dict.fromkeys(sin_costo)
                ]
            },
        )

    # 9) La venta, sus líneas (costo congelado, VTA-05), su snapshot de crédito y sus descuentos.
    momento = reloj.now()
    venta = Venta(
        id=datos.venta_id,
        organizacion_id=organizacion_id,
        numero=datos.numero,
        cliente_id=cliente.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        ubicacion_id=ubicacion_id,
        jornada_id=(jornada_del_sobre if sin_conexion else movimientos[0].movimiento.jornada_id),
        lista_id=elegidos.lista_id,
        lista_version_id=elegidos.version_id,
        motivo_lista_id=elegidos.motivo_id,
        modo_impositivo=calculo.modo_impositivo,
        modo_confirmacion=modo,
        total_neto=totales.total_neto,
        total_iva=totales.total_iva,
        total=totales.total,
        estado="CONFIRMADA",
        estado_facturacion=(
            cliente.estado_facturacion_default or configuracion.estado_facturacion_default
        ),
        importe_facturado=_CERO,
        operation_id=operation_id,
        occurred_at=occurred_at,
        registered_at=momento,
        creado_en=momento,
        **_snapshot_de_credito(datos_de_credito, credito_evaluado, saldo_del_snapshot),
    )
    lineas_guardadas: list[VentaLinea] = []
    for orden, (linea, calculada, resultado, final, movimiento) in enumerate(
        zip(
            datos.lineas,
            lineas_de_calculo,
            calculo.lineas,
            lineas_finales,
            movimientos,
            strict=True,
        )
    ):
        costo_unitario = movimiento.movimiento.costo_unitario
        lineas_guardadas.append(
            VentaLinea(
                id=linea.linea_id,
                organizacion_id=organizacion_id,
                venta_id=datos.venta_id,
                orden=orden,
                producto_id=linea.producto_id,
                presentacion_id=linea.presentacion_id,
                lista_version_id=linea.lista_version_id,
                unidades_presentacion=unidades[linea.linea_id],
                cantidad=linea.cantidad,
                cantidad_base=calculada.cantidad_base,
                precio_referencia=calculada.precio_referencia,
                unidades_referencia=calculada.unidades_referencia,
                importe_bruto=resultado.bruto,
                importe_descuento=final.descuento_total,
                importe_neto=final.neto,
                alicuota=resultado.alicuota,
                importe_iva=resultado.importe_iva,
                costo_unitario=costo_unitario,
                costo_total=(
                    None
                    if costo_unitario is None
                    else redondear_importe(costo_unitario * calculada.cantidad_base)
                ),
            )
        )
    repository.insertar_venta(sesion, venta, lineas_guardadas)
    # DSC-08: cada descuento informado, con el motivo y el autorizador copiados en los `MANUAL`.
    repository.insertar_descuentos(
        sesion,
        [
            VentaLineaDescuento(
                id=nuevo_id(),
                organizacion_id=organizacion_id,
                venta_linea_id=guardada.id,
                orden=orden_del_descuento,
                origen=descuento.origen,
                regla_id=descuento.regla_id,
                porcentaje=descuento.porcentaje,
                importe=descuento.importe,
                motivo_id=(
                    motivo_del_descuento[0]
                    if descuento.origen == "MANUAL" and motivo_del_descuento is not None
                    else None
                ),
                autorizador_id=(
                    UUID(descuento_evaluado.autorizador_id)
                    if descuento.origen == "MANUAL"
                    and descuento_evaluado is not None
                    and descuento_evaluado.autorizador_id is not None
                    else None
                ),
            )
            for guardada, final in zip(lineas_guardadas, lineas_finales, strict=True)
            for orden_del_descuento, descuento in enumerate(final.descuentos)
        ],
    )
    # D19 (AUD-01, AUD-02): además de la fila genérica del bus, una fila del descuento manual
    # informado y una de la autorización de crédito, con el `operation_id` de la venta. Ninguna
    # lleva el PIN. Un rechazo revierte la transacción y no deja ninguna (INV-01).
    _auditar_descuento_manual(
        organizacion_id,
        sesion,
        reloj,
        venta=venta,
        porcentaje_maximo=porcentaje_manual_maximo,
        evaluado=descuento_evaluado,
        motivo_id=None if motivo_del_descuento is None else motivo_del_descuento[0],
        usuario_id=usuario_id,
        sin_conexion=sin_conexion,
    )
    _auditar_autorizacion_de_credito(
        organizacion_id,
        sesion,
        reloj,
        venta=venta,
        evaluacion=credito_evaluado,
        datos_de_credito=datos_de_credito,
        saldo_considerado=saldo_del_snapshot,
        usuario_id=usuario_id,
        sin_conexion=sin_conexion,
    )
    if sin_conexion:
        # D9, D10: una sola `DESCUENTO_DIFIERE` con todas las causas, y las observaciones del
        # crédito y de las autorizaciones sin conexión (tarea 10.1).
        diferencia = observacion_descuento_difiere(causas_de_descuento)
        if diferencia is not None:
            observaciones_de_venta.append(diferencia)
        observaciones_de_venta.extend(observaciones_de_autorizacion)
    elif (
        credito_evaluado is not None
        and credito_evaluado.resolucion == _RESOLUCION_CREDITO_ADVERTIDA
    ):
        # CRE-04: el exceso aceptado queda como observación sobre la venta.
        observaciones_de_venta.append(
            _observacion_de_exceso(
                CODIGO_EXCESO_CREDITO_ADVERTIDO,
                None if datos_de_credito is None else datos_de_credito.limite,
                saldo_considerado,
                credito_evaluado.exceso,
            )
        )
    observaciones_de_venta.extend(
        ObservacionDeVenta(
            CODIGO_STOCK_NEGATIVO,
            {
                "linea_id": str(guardada.id),
                "producto_id": str(guardada.producto_id),
                "ubicacion_id": str(ubicacion_id),
                "saldo_resultante": movimiento.saldo,
            },
        )
        for guardada, movimiento in zip(lineas_guardadas, movimientos, strict=True)
        if movimiento.saldo_negativo
    )
    if sin_conexion:
        # D10: sin conexion el costo queda nulo y se observa por linea (INV-10: no se completa).
        observaciones_de_venta.extend(
            ObservacionDeVenta(
                CODIGO_VENTA_SIN_COSTO,
                {"linea_id": str(guardada.id), "producto_id": str(guardada.producto_id)},
            )
            for guardada in lineas_guardadas
            if guardada.costo_unitario is None
        )
        # SYN-05, INV-17, STK-09: la ubicacion estaba tomada al sincronizar (propia en rendicion o
        # de otra jornada); la venta se acepta y la bandeja del 25 la ve. La constancia de la
        # auditoria sale de `jornadas_tomadas` (el handler).
        observaciones_de_venta.extend(
            ObservacionDeVenta(
                CODIGO_UBICACION_TOMADA_AL_SINCRONIZAR,
                {"jornada_id": str(jornada_tomada_id), "ubicacion_id": str(ubicacion_id)},
            )
            for jornada_tomada_id in stock_service.jornadas_tomadas_de(movimientos)
        )
        # RUT-09: una sola `JORNADA_LIBERADA`, sobre la venta (la cobranza en el acto no repite).
        assert jornada_del_sobre is not None  # ya validado al elegir la ubicacion
        estado_jornada = stock_service.leer_estado_de_jornada(
            organizacion_id, sesion, jornada_id=jornada_del_sobre
        )
        if estado_jornada is not None and estado_jornada.estado == _ESTADO_JORNADA_LIBERADA:
            observaciones_de_venta.append(
                ObservacionDeVenta(
                    CODIGO_JORNADA_LIBERADA,
                    {
                        "jornada_id": str(estado_jornada.jornada_id),
                        "liberada_en": (
                            None
                            if estado_jornada.liberada_en is None
                            else estado_jornada.liberada_en.isoformat()
                        ),
                    },
                )
            )

    # 9) Débito `VENTA` por el total, con el saldo ya bloqueado.
    debito = cuentas_corrientes_service.registrar_movimiento(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=_CUENTA_CLIENTE,
        entidad_id=cliente.id,
        tipo=_TIPO_MOVIMIENTO_VENTA,
        sentido="AUMENTA",
        importe=totales.total,
        origen_tipo=_ORIGEN_TIPO_VENTA,
        origen_id=venta.id,
        occurred_at=occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )
    saldo = debito.saldo

    # 9) Cobranza en el acto, después del débito (CC-05).
    cobranza_id: UUID | None = None
    if datos.cobranza is not None:
        resultado_cobranza = cobranzas_service.registrar_cobranza(
            organizacion_id,
            sesion,
            reloj,
            cobranza_id=datos.cobranza.cobranza_id,
            cliente_id=cliente.id,
            importe=importe_cobranza if importe_cobranza is not None else _CERO,
            medios=datos.cobranza.medios,
            observacion=datos.cobranza.observacion,
            jornada_del_sobre=jornada_del_sobre,
            operation_id=operation_id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=occurred_at,
            origen="VENTA",
            venta_id=venta.id,
            modo=modo,
        )
        cobranza_id = resultado_cobranza.cobranza.id
        saldo = resultado_cobranza.saldo
        # SYN-07: las observaciones de los medios recaen sobre la cobranza (como en el change 17);
        # la `JORNADA_LIBERADA` ya quedo sobre la venta, asi que la de la cobranza no se repite.
        observaciones_de_venta.extend(
            ObservacionDeVenta(observacion.codigo, observacion.detalle, sobre_cobranza=True)
            for observacion in resultado_cobranza.observaciones
            if observacion.codigo != CODIGO_JORNADA_LIBERADA
        )

    # 10) LO ÚLTIMO, nivel 6: el correlativo del dispositivo (`max(actual, propuesto)`).
    identidad_service.registrar_correlativo_maximo(
        organizacion_id, sesion, dispositivo_id=dispositivo_id, propuesto=correlativo
    )

    # Resultado al bus.
    return ResultadoDeVenta(
        venta=venta,
        lineas=tuple(lineas_guardadas),
        saldo=saldo,
        cobranza_id=cobranza_id,
        observaciones=tuple(observaciones_de_venta),
        observacion_de_lista=elegidos.observacion_de_lista,
        jornadas_tomadas=stock_service.jornadas_tomadas_de(movimientos),
    )
