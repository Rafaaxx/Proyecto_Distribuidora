"""Interfaz pública de `ventas` para otros módulos (`CLAUDE.md` §4: un módulo usa a otro solo a
través de su `service.py`) y registro de sus puertos.

Expone el verificador de uso de presentaciones (INV-18, `design.md` D18) y la confirmación de la
venta (`confirmar_venta`, change 18a, grupo 7; D17). Sin `commit`: la transacción la gestiona el
bus de comandos (`ventas/commands.py`). Toda función recibe `organizacion_id` y lo usa para
filtrar.

Orden de `confirmar_venta` (D17, opción A, confirmado por el usuario el 2026-10-19):

0. validación pura del contenido y `venta_id` libre;
1. configuración, cliente y lista (`FOR SHARE`), precios (D6, D7, D9) y estado del cliente (D5);
2. nivel 1: `saldo_cuenta` del cliente `FOR UPDATE`;
3. nivel 2: productos `FOR SHARE` por identificador ascendente y, con ellos tomados, las
   presentaciones (`FOR KEY SHARE`);
4. el motor recalcula, se compara con lo esperado (D2) y se evalúa el consumidor final (D5);
5. niveles 2 a 5: egreso de stock `VENTA` por línea, que devuelve el costo (D10, D11);
6. se inserta la venta con sus líneas y el costo congelado (VTA-05);
7. débito `VENTA` por el total (el saldo ya está bloqueado);
8. cobranza `VENTA` (D12), después del débito (CC-05);
9. LO ÚLTIMO, nivel 6: el correlativo del dispositivo (`max(actual, propuesto)`, D4);
10. se devuelve el resultado y las observaciones al bus, que audita y confirma.

Sin conexión (`modo="OFFLINE"`, change 18a, tarea 11.2, `design.md` D1, alcance confirmado por el
usuario el 2026-10-20) el orden de bloqueo NO cambia; cambia qué se decide en cada paso: se
congelan la versión, el precio y las unidades que envió el dispositivo; solo se rechaza lo
malformado (`TOTALES_INCONSISTENTES`, INV-07), lo inexistente y el número repetido; todo lo demás
se acepta con una observación (SYN-05, SYN-06, SYN-07, INV-17). Con conexión nada cambia.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import DomainError, PermisoRequeridoError
from app.core.money import redondear_importe
from app.modules.catalogo import service as catalogo_service
from app.modules.clientes import service as clientes_service
from app.modules.cobranzas import service as cobranzas_service
from app.modules.cobranzas.service import MedioACobrar
from app.modules.configuracion import service as configuracion_service
from app.modules.cuentas_corrientes import service as cuentas_corrientes_service
from app.modules.identidad import service as identidad_service
from app.modules.precios import service as precios_service
from app.modules.stock import service as stock_service
from app.modules.stock.service import LineaDeMovimiento
from app.modules.ventas import repository
from app.modules.ventas.domain.auditoria import observacion_de_lista
from app.modules.ventas.domain.calculo import LineaCalculo, calcular_venta
from app.modules.ventas.domain.cliente import evaluar_cliente
from app.modules.ventas.domain.comparacion import (
    ProductoSinPrecio,
    ValoresDeLinea,
    comparar_con_esperado,
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
from app.modules.ventas.domain.errores import (
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
from app.modules.ventas.models import Venta, VentaLinea

__all__ = [
    "CobranzaDeVenta",
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


@dataclass(frozen=True)
class CobranzaDeVenta:
    """La cobranza en el acto (D12): su importe es la suma de los medios (INV-08)."""

    cobranza_id: UUID
    medios: Sequence[MedioACobrar]
    observacion: str | None


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
) -> ResultadoDeVenta:
    """`VENTA_CONFIRMAR` (VTA-12, INV-01, INV-14; `design.md` D1, D17), con conexión por defecto
    o sin ella (`modo="OFFLINE"`, tarea 11.2). Ver el orden y las diferencias en el docstring del
    módulo. Cualquier error revierte todo (lo hace el bus)."""
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
    cuentas_corrientes_service.bloquear_saldo(
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
                descuento_manual=None,
            )
        )
    calculo = calcular_venta(configuracion.modo_impositivo, lineas_de_calculo, [])
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
            calculo.total,
        )
        del_cliente = evaluar_cliente(
            cliente_id=cliente.id,
            estado=cliente.estado,
            es_consumidor_final=cliente.es_consumidor_final,
            puede_vender_suspendido=permisos.puede_vender_suspendido,
            total=calculo.total,
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
            total=calculo.total,
            cobranza=importe_cobranza,
            offline=False,
        )
        comparar_con_esperado(
            esperados,
            [
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
            ],
            datos.total,
            calculo.total,
        )

    # 5) Niveles 2 a 5: egreso de stock `VENTA`, que devuelve el costo de cada línea.
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

    # 6) La venta y sus líneas, con el costo congelado (VTA-05).
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
        total_neto=calculo.total_neto,
        total_iva=calculo.total_iva,
        total=calculo.total,
        estado="CONFIRMADA",
        estado_facturacion=(
            cliente.estado_facturacion_default or configuracion.estado_facturacion_default
        ),
        importe_facturado=_CERO,
        operation_id=operation_id,
        occurred_at=occurred_at,
        registered_at=momento,
        creado_en=momento,
    )
    lineas_guardadas: list[VentaLinea] = []
    for orden, (linea, calculada, resultado, movimiento) in enumerate(
        zip(datos.lineas, lineas_de_calculo, calculo.lineas, movimientos, strict=True)
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
                importe_descuento=resultado.descuento_total,
                importe_neto=resultado.neto,
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

    # 7) Débito `VENTA` por el total, con el saldo ya bloqueado.
    debito = cuentas_corrientes_service.registrar_movimiento(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=_CUENTA_CLIENTE,
        entidad_id=cliente.id,
        tipo=_TIPO_MOVIMIENTO_VENTA,
        sentido="AUMENTA",
        importe=calculo.total,
        origen_tipo=_ORIGEN_TIPO_VENTA,
        origen_id=venta.id,
        occurred_at=occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )
    saldo = debito.saldo

    # 8) Cobranza en el acto, después del débito (CC-05).
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

    # 9) LO ÚLTIMO, nivel 6: el correlativo del dispositivo (`max(actual, propuesto)`).
    identidad_service.registrar_correlativo_maximo(
        organizacion_id, sesion, dispositivo_id=dispositivo_id, propuesto=correlativo
    )

    # 10) Resultado al bus.
    return ResultadoDeVenta(
        venta=venta,
        lineas=tuple(lineas_guardadas),
        saldo=saldo,
        cobranza_id=cobranza_id,
        observaciones=tuple(observaciones_de_venta),
        observacion_de_lista=elegidos.observacion_de_lista,
        jornadas_tomadas=stock_service.jornadas_tomadas_de(movimientos),
    )
