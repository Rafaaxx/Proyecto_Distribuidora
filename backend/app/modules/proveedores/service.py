"""Interfaz pública de `proveedores` (`CLAUDE.md` §4: un módulo usa a otro
solo a través de su `service.py`).

Expone alta/modificación/consulta de proveedores (tarea 8.2), informar
costos en lote (tarea 8.3, `design.md` D3/D4/D12/D14), y las lecturas que
el change 13 necesita (tarea 8.4). Sin `commit`: la transacción la
gestiona el bus de comandos (`proveedores/commands.py`, grupo 9) o quien
llame en pruebas (`CLAUDE.md` §4).

Al importarse, este módulo registra en `catalogo/service.py` el puerto de
consulta de proveedor (D9-A, ADR-025) y el verificador de uso de
`costo_informado` (D1, ADR-023) -- mismo patrón que `app/commands/
registro.py` con los handlers: alguien (`app.main`, o el propio test) debe
importar este módulo para que los puertos queden registrados."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.modules.catalogo import service as catalogo_service
from app.modules.configuracion import service as configuracion_service
from app.modules.cuentas_corrientes import service as cuentas_corrientes_service
from app.modules.identidad import service as identidad_service
from app.modules.proveedores import repository
from app.modules.proveedores.domain import pagos
from app.modules.proveedores.domain.compras import (
    CONTADO,
    CostoDeLinea,
    DiferenciaDeCosto,
    EntradaDeLinea,
    MedioDeEntrada,
    calcular_compra,
    diferencias_de_costo,
    validar_cantidad_de_lineas,
    validar_fecha,
    validar_pago,
    validar_total_factura,
)
from app.modules.proveedores.domain.costo_base import calcular_costo_base
from app.modules.proveedores.domain.errores import (
    CompraYaAnuladaError,
    CondicionInvalidaError,
    CuitInvalidoError,
    IncluyeIvaNoAplicaError,
    MedioPagoInactivoError,
    MotivoInvalidoError,
    PresentacionInvalidaError,
    ProductoInactivoError,
    ProveedorConProductosActivosError,
    ProveedorInactivoError,
    ProveedorNoCorrespondeError,
    RecursoNoEncontradoError,
    UbicacionInactivaError,
)
from app.modules.proveedores.domain.lote import (
    CostoDelLote as CostoDelLote,  # re-exportado: lo usa `importacion` (change 10)
)
from app.modules.proveedores.domain.lote import validar_lote_de_costos
from app.modules.proveedores.domain.normalizacion import normalizar_cuit, normalizar_nombre
from app.modules.proveedores.models import (
    Compra,
    CompraLinea,
    CostoInformado,
    PagoProveedor,
    Proveedor,
)
from app.modules.stock import service as stock_service
from app.modules.stock.service import LineaDeMovimiento

# --- D9/ADR-025: registro del puerto de consulta al importar este módulo --


def _consultar_estado_de_proveedor(
    organizacion_id: UUID, proveedor_id: UUID, sesion: Session
) -> catalogo_service.EstadoProveedor | None:
    proveedor = repository.obtener_proveedor_por_id_para_compartir(
        organizacion_id, proveedor_id, sesion
    )
    if proveedor is None:
        return None
    return catalogo_service.EstadoProveedor(activo=proveedor.activo, nombre=proveedor.nombre)


catalogo_service.registrar_consulta_proveedor(_consultar_estado_de_proveedor)


# --- D1/ADR-023: registro del verificador de uso de costo_informado -------


def _presentacion_tiene_costo_informado(
    organizacion_id: UUID, presentacion_id: UUID, sesion: Session
) -> bool:
    return repository.existe_costo_para_presentacion(organizacion_id, presentacion_id, sesion)


catalogo_service.registrar_verificador_uso("costo_informado", _presentacion_tiene_costo_informado)


# --- INV-18/ADR-023: registro del verificador de uso de compra_linea (change 11) --------


def _presentacion_tiene_compra(
    organizacion_id: UUID, presentacion_id: UUID, sesion: Session
) -> bool:
    return repository.existe_linea_para_presentacion(organizacion_id, presentacion_id, sesion)


catalogo_service.registrar_verificador_uso("compra_linea", _presentacion_tiene_compra)


# --- proveedor (D7, D5/ADR-026) --------------------------------------------


def _normalizar_cuit_o_rechazar(cuit: str | None) -> str | None:
    """D7: el CUIT es opcional; si se cargó un valor no vacío que no
    normaliza a 11 dígitos, se rechaza (`CUIT_INVALIDO`) -- distinto de "no
    se cargó CUIT" (`None`/cadena vacía), que no es un error."""
    if cuit is None:
        return None
    recortado = cuit.strip()
    if recortado == "":
        return None
    normalizado = normalizar_cuit(recortado)
    if normalizado is None:
        raise CuitInvalidoError(
            "El CUIT debe tener 11 dígitos (los guiones y espacios se descartan)."
        )
    return normalizado


def crear_proveedor(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    cuit: str | None,
    contacto: str | None,
    telefono: str | None,
    email: str | None,
    actor_id: UUID | None,
) -> Proveedor:
    nombre_normalizado = normalizar_nombre(nombre)
    cuit_normalizado = _normalizar_cuit_o_rechazar(cuit)
    momento = reloj.now()
    return repository.crear_proveedor(
        organizacion_id,
        sesion,
        proveedor_id=nuevo_id(),
        nombre=nombre_normalizado,
        cuit=cuit_normalizado,
        contacto=contacto,
        telefono=telefono,
        email=email,
        activo=True,
        momento=momento,
        actualizado_por_id=actor_id,
    )


def modificar_proveedor(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    proveedor_id: UUID,
    nombre: str,
    cuit: str | None,
    contacto: str | None,
    telefono: str | None,
    email: str | None,
    activo: bool,
    actor_id: UUID | None,
) -> Proveedor:
    """`PROVEEDOR_MODIFICAR` (D14: `FOR UPDATE` sobre la fila del
    proveedor, antes de decidir/escribir). D5/ADR-026: rechaza
    `PROVEEDOR_CON_PRODUCTOS_ACTIVOS` si se intenta desactivar (transición
    `True -> False`) un proveedor con productos activos -- reactivar, o
    mantener el mismo estado, no dispara la verificación (mismo criterio
    que `catalogo_service.modificar_categoria`, D11 del 05)."""
    proveedor = repository.obtener_proveedor_por_id_para_actualizar(
        organizacion_id, proveedor_id, sesion
    )
    if proveedor is None:
        raise RecursoNoEncontradoError(
            f"El proveedor {proveedor_id} no existe en esta organización."
        )

    nombre_normalizado = normalizar_nombre(nombre)
    cuit_normalizado = _normalizar_cuit_o_rechazar(cuit)

    if (
        proveedor.activo
        and not activo
        and catalogo_service.existen_productos_activos_de_proveedor(
            organizacion_id, proveedor_id, sesion
        )
    ):
        raise ProveedorConProductosActivosError(
            "No se puede desactivar un proveedor con productos activos (ADR-026)."
        )

    actualizado = repository.actualizar_proveedor(
        organizacion_id,
        sesion,
        proveedor_id=proveedor_id,
        nombre=nombre_normalizado,
        cuit=cuit_normalizado,
        contacto=contacto,
        telefono=telefono,
        email=email,
        activo=activo,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )
    assert actualizado is not None
    return actualizado


def listar_proveedores(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = repository.LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    texto: str | None = None,
    activo: bool | None = None,
) -> tuple[list[Proveedor], str | None]:
    return repository.listar_proveedores_paginado(
        organizacion_id, sesion, limite=limite, cursor=cursor, texto=texto, activo=activo
    )


def buscar_proveedores_por_nombre(
    organizacion_id: UUID, nombre: str, sesion: Session
) -> list[Proveedor]:
    """Lectura pública para la importación (change 10, `design.md` D4): proveedores de
    la organización con ese nombre, sin distinguir mayúsculas ni espacios al borde,
    activos o no (el alta de producto y de costo rechazan después uno inactivo con
    `PROVEEDOR_INACTIVO`)."""
    return repository.buscar_proveedores_por_nombre(organizacion_id, nombre, sesion)


def listar_opciones_de_proveedores(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = repository.LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> tuple[list[Proveedor], str | None]:
    """`GET /proveedores/opciones` (D8, contrato-api.md P2 aprobado
    2026-09-24): solo proveedores activos, paginados."""
    return repository.listar_opciones_de_proveedores(
        organizacion_id, sesion, limite=limite, cursor=cursor
    )


def obtener_proveedor(
    organizacion_id: UUID, proveedor_id: UUID, sesion: Session
) -> Proveedor | None:
    return repository.obtener_proveedor_por_id(organizacion_id, proveedor_id, sesion)


# --- COSTO_INFORMAR (tarea 8.3, [ALTA: cálculo de costos]) ----------------


def informar_costos(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    proveedor_id: UUID,
    costos: list[CostoDelLote],
    operation_id: UUID,
    actor_id: UUID,
) -> list[CostoInformado]:
    """`COSTO_INFORMAR` (`design.md` D3, D4, D12, D14; CST-01, CST-02,
    INV-01, INV-18).

    Orden de validación y bloqueo (D14, evita interbloqueos entre lotes
    concurrentes): 1) forma del lote (6.4, pura); 2) proveedor, `FOR SHARE`;
    3) productos referenciados, `FOR SHARE`, en orden ascendente de `id`.
    Todo el cálculo (6.3) y la resolución de presentaciones/alícuota ocurre
    ANTES de la única llamada a `repository.insertar_costos` -- si algo
    falla a mitad de camino (INV-01), no se llegó a construir ninguna fila
    para insertar."""
    validar_lote_de_costos(costos)

    # CST-06, D3: la regla vigente se lee `FOR SHARE` al inicio, así un cambio de condición
    # concurrente espera y este lote usa una sola regla de punta a punta.
    computa_credito_fiscal = identidad_service.organizacion_computa_credito_fiscal(
        organizacion_id, sesion, para_compartir=True
    )
    if computa_credito_fiscal is None:
        raise RecursoNoEncontradoError("La organización no existe.")

    proveedor = repository.obtener_proveedor_por_id_para_compartir(
        organizacion_id, proveedor_id, sesion
    )
    if proveedor is None:
        raise RecursoNoEncontradoError(
            f"El proveedor {proveedor_id} no existe en esta organización."
        )
    if not proveedor.activo:
        raise ProveedorInactivoError(f"El proveedor {proveedor_id} está inactivo (D5).")

    # contrato-api.md P9 (aprobado 2026-09-24): `fila` es el índice 0-based
    # de la PRIMERA fila del lote que referencia cada producto -- el lock de
    # productos (D14) recorre ids únicos y ordenados, no filas, pero el
    # error que puede levantar sigue siendo específico de una fila.
    primera_fila_por_producto: dict[UUID, int] = {}
    for fila, costo in enumerate(costos):
        primera_fila_por_producto.setdefault(costo.producto_id, fila)

    productos_por_id: dict[UUID, Any] = {}
    ids_productos_ordenados = sorted({costo.producto_id for costo in costos})
    for producto_id in ids_productos_ordenados:
        fila_producto = primera_fila_por_producto[producto_id]
        producto = catalogo_service.obtener_producto_para_compartir(
            organizacion_id, producto_id, sesion
        )
        if producto is None:
            raise RecursoNoEncontradoError(
                f"El producto {producto_id} no existe en esta organización.",
                extension={"fila": fila_producto},
            )
        if producto.proveedor_id != proveedor_id:
            raise ProveedorNoCorrespondeError(
                f"El producto {producto_id} no tiene a {proveedor_id} como proveedor actual (D3).",
                extension={"fila": fila_producto},
            )
        if not producto.activo:
            raise ProductoInactivoError(
                f"El producto {producto_id} está inactivo.", extension={"fila": fila_producto}
            )
        productos_por_id[producto_id] = producto

    momento = reloj.now()
    filas: list[repository.DatosCostoInformado] = []
    for fila_actual, costo in enumerate(costos):
        producto = productos_por_id[costo.producto_id]
        presentacion = catalogo_service.obtener_presentacion(
            organizacion_id, costo.presentacion_id, sesion
        )
        if (
            presentacion is None
            or presentacion.producto_id != costo.producto_id
            or not presentacion.activo
            or not presentacion.usar_en_compra
        ):
            raise PresentacionInvalidaError(
                f"La presentación {costo.presentacion_id} no es una presentación de compra "
                f"activa del producto {costo.producto_id}.",
                extension={"fila": fila_actual},
            )

        alicuota = configuracion_service.obtener_alicuota_por_id(
            organizacion_id, producto.alicuota_id, sesion
        )
        assert alicuota is not None  # la FK del producto garantiza su existencia.

        try:
            costo_base = calcular_costo_base(
                computa_credito_fiscal=computa_credito_fiscal,
                valor=costo.valor,
                incluye_iva=costo.incluye_iva,
                alicuota=alicuota.valor,
                bonificacion=costo.bonificacion,
                unidades=presentacion.unidades_base,
            )
        except IncluyeIvaNoAplicaError as error:
            error.extension = {**(error.extension or {}), "fila": fila_actual}
            raise

        filas.append(
            repository.DatosCostoInformado(
                id=nuevo_id(),
                proveedor_id=proveedor_id,
                producto_id=costo.producto_id,
                presentacion_id=costo.presentacion_id,
                valor=costo.valor,
                incluye_iva=costo.incluye_iva,
                computa_credito_fiscal=computa_credito_fiscal,
                bonificacion=costo.bonificacion,
                alicuota_aplicada=alicuota.valor,
                costo_base=costo_base,
                vigencia_desde=costo.vigencia_desde,
                observacion=costo.observacion,
                operation_id=operation_id,
                usuario_id=actor_id,
                momento=momento,
            )
        )

    return repository.insertar_costos(organizacion_id, sesion, costos=filas)


# --- lecturas para el change 13 (tarea 8.4) --------------------------------


def obtener_costo_informado_vigente(
    organizacion_id: UUID, producto_id: UUID, fecha: date, sesion: Session
) -> CostoInformado | None:
    """CST-03: el costo vigente de un producto para `fecha`, resuelto con
    SQL (D4)."""
    return repository.obtener_vigente(organizacion_id, producto_id, fecha, sesion)


def listar_historial_costos(
    organizacion_id: UUID,
    producto_id: UUID,
    sesion: Session,
    *,
    limite: int = repository.LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> tuple[list[CostoInformado], str | None]:
    return repository.listar_historial_de_producto(
        organizacion_id, producto_id, sesion, limite=limite, cursor=cursor
    )


def listar_ultimo_costo_por_presentacion(
    organizacion_id: UUID, producto_id: UUID, fecha: date, sesion: Session
) -> list[CostoInformado]:
    """P11 (`contrato-api.md`, aprobado en la verificación manual 13.5,
    opción B): el último costo informado (D4) de CADA presentación del
    producto con al menos un costo con `vigencia_desde <= fecha` -- las
    presentaciones sin costo se omiten. Informativo: el precio (PRC-11)
    sigue calculándose solo con `obtener_costo_informado_vigente`."""
    return repository.obtener_ultimo_por_presentacion(organizacion_id, producto_id, fecha, sesion)


# --- compras (change 11, CMP-01 a CMP-04) -----------------------------------------------


@dataclass(frozen=True)
class LineaDeCompra:
    """Una línea de `COMPRA_CONFIRMAR` tal como la informa el usuario (D5)."""

    producto_id: UUID
    presentacion_id: UUID
    cantidad: Decimal
    valor: Decimal
    incluye_iva: bool
    bonificacion: Decimal


@dataclass(frozen=True)
class MedioAPagar:
    """Un medio de pago (el del pago de contado de una compra, D2, o el de un pago
    independiente, PAG-01)."""

    medio_pago_id: UUID
    importe: Decimal
    referencia: str | None


@dataclass(frozen=True)
class ResultadoDeCompra:
    """La compra confirmada, sus líneas y las diferencias con el costo informado
    vigente (CMP-04, D7). `pago` es `None` en una compra a crédito."""

    compra: Compra
    lineas: list[CompraLinea]
    diferencias_de_costo: list[DiferenciaDeCosto]
    pago: PagoProveedor | None = None


_CUENTA_PROVEEDOR = "PROVEEDOR"
_TIPO_MOVIMIENTO_PAGO = "PAGO"
"""El tipo del movimiento de cuenta que aplica un pago (CC-04, PAG-02): reduce el saldo
del proveedor sin imputarse a ninguna compra."""


def _resolver_medios(
    organizacion_id: UUID, sesion: Session, medios: Sequence[MedioAPagar]
) -> list[MedioDeEntrada]:
    """D2: cada medio existe en la organización (404 si no, INV-21) y está activo
    (`MEDIO_PAGO_INACTIVO`); devuelve la entrada de validación con si el medio exige
    referencia. Los errores llevan el índice del medio en `extension["medio"]`."""
    entradas: list[MedioDeEntrada] = []
    for indice, medio in enumerate(medios):
        fila = configuracion_service.obtener_medio_pago(
            organizacion_id, medio.medio_pago_id, sesion
        )
        if fila is None:
            raise RecursoNoEncontradoError(
                f"El medio de pago {medio.medio_pago_id} no existe en esta organización.",
                extension={"medio": indice},
            )
        if not fila.activo:
            raise MedioPagoInactivoError(
                f"El medio de pago {medio.medio_pago_id} está inactivo.",
                extension={"medio": indice},
            )
        entradas.append(
            MedioDeEntrada(
                medio.importe, medio.referencia, requiere_referencia=fila.requiere_referencia
            )
        )
    return entradas


def _referencias_de_la_compra(
    organizacion_id: UUID,
    sesion: Session,
    *,
    proveedor_id: UUID,
    ubicacion_id: UUID,
    lineas: Sequence[LineaDeCompra],
    computa_credito_fiscal: bool,
) -> tuple[list[EntradaDeLinea], list[Any]]:
    """Valida las referencias y devuelve, por línea, la entrada de cálculo y la alícuota.

    Bloquea `FOR SHARE` el proveedor y los productos (en orden ascendente de id, D14 del
    change 06) y deja intacto el estado: lee, no escribe. Los errores de una línea llevan
    su índice (0-based) en `extension["linea"]`. Una referencia inexistente o de otra
    organización es 404 (INV-21)."""
    proveedor = repository.obtener_proveedor_por_id_para_compartir(
        organizacion_id, proveedor_id, sesion
    )
    if proveedor is None:
        raise RecursoNoEncontradoError(
            f"El proveedor {proveedor_id} no existe en esta organización."
        )
    if not proveedor.activo:
        raise ProveedorInactivoError(f"El proveedor {proveedor_id} está inactivo.")

    ubicacion = stock_service.obtener_ubicacion(organizacion_id, sesion, ubicacion_id)
    if ubicacion is None:
        raise RecursoNoEncontradoError(
            f"La ubicación {ubicacion_id} no existe en esta organización."
        )
    if not ubicacion.activo:
        raise UbicacionInactivaError(f"La ubicación {ubicacion_id} está inactiva.")

    primera_linea_por_producto: dict[UUID, int] = {}
    for indice, linea in enumerate(lineas):
        primera_linea_por_producto.setdefault(linea.producto_id, indice)

    # Se bloquean `FOR SHARE` en orden ascendente de id (D14 del change 06) y recién
    # después se valida en el orden de las líneas: así el error informado es siempre el
    # de la primera línea con problema, no el del producto con menor UUID.
    leidos = {
        producto_id: catalogo_service.obtener_producto_para_compartir(
            organizacion_id, producto_id, sesion
        )
        for producto_id in sorted(primera_linea_por_producto)
    }
    productos: dict[UUID, Any] = {}
    for producto_id, indice_de_linea in sorted(
        primera_linea_por_producto.items(), key=lambda par: par[1]
    ):
        extension = {"linea": indice_de_linea}
        producto = leidos[producto_id]
        if producto is None:
            raise RecursoNoEncontradoError(
                f"El producto {producto_id} no existe en esta organización.", extension=extension
            )
        if producto.proveedor_id != proveedor_id:
            raise ProveedorNoCorrespondeError(
                f"El producto {producto_id} no tiene a {proveedor_id} como proveedor actual (D4).",
                extension=extension,
            )
        if not producto.activo:
            raise ProductoInactivoError(
                f"El producto {producto_id} está inactivo.", extension=extension
            )
        productos[producto_id] = producto

    alicuotas: dict[UUID, Any] = {}
    entradas: list[EntradaDeLinea] = []
    alicuotas_de_linea: list[Any] = []
    for indice, linea in enumerate(lineas):
        presentacion = catalogo_service.obtener_presentacion(
            organizacion_id, linea.presentacion_id, sesion
        )
        if (
            presentacion is None
            or presentacion.producto_id != linea.producto_id
            or not presentacion.activo
            or not presentacion.usar_en_compra
        ):
            raise PresentacionInvalidaError(
                f"La presentación {linea.presentacion_id} no es una presentación de compra "
                f"activa del producto {linea.producto_id}.",
                extension={"linea": indice},
            )
        alicuota_id = productos[linea.producto_id].alicuota_id
        if alicuota_id not in alicuotas:
            alicuota = configuracion_service.obtener_alicuota_por_id(
                organizacion_id, alicuota_id, sesion
            )
            assert alicuota is not None  # la FK del producto garantiza su existencia.
            alicuotas[alicuota_id] = alicuota
        alicuota_de_linea = alicuotas[alicuota_id]
        alicuotas_de_linea.append(alicuota_de_linea)
        entradas.append(
            EntradaDeLinea(
                unidades_presentacion=presentacion.unidades_base,
                cantidad=linea.cantidad,
                valor=linea.valor,
                incluye_iva=linea.incluye_iva,
                computa_credito_fiscal=computa_credito_fiscal,
                alicuota=alicuota_de_linea.valor,
                bonificacion=linea.bonificacion,
            )
        )
    return entradas, alicuotas_de_linea


def confirmar_compra(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    proveedor_id: UUID,
    fecha: date,
    ubicacion_id: UUID,
    condicion: str,
    total_factura: Decimal,
    numero_comprobante: str | None,
    observacion: str | None,
    lineas: Sequence[LineaDeCompra],
    medios: Sequence[MedioAPagar],
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
) -> ResultadoDeCompra:
    """`COMPRA_CONFIRMAR` (CMP-01 a CMP-04, INV-01, INV-07; `design.md` D1 a D7, D16).

    En una sola transacción ingresa el stock de cada línea (movimiento `COMPRA` con su
    costo base, que recalcula el promedio, CST-11), registra `COMPRA` en la cuenta del
    proveedor por el total de factura y deja la compra. TODA validación y todo cálculo
    ocurren antes del primer bloqueo de saldo o escritura (INV-01). Orden de bloqueo
    (`02` §7.3): proveedor y productos `FOR SHARE` -> `saldo_cuenta` del proveedor ->
    `costo_producto` y `stock_saldo` (dentro de `stock`). Los movimientos usan el
    `occurred_at` del comando (D6); la `fecha` es la del comprobante. Nunca registra un
    costo informado (CMP-04): solo devuelve las diferencias."""
    validar_cantidad_de_lineas(len(lineas))
    # CST-06, D3: la regla vigente se lee `FOR SHARE` al inicio (antes que proveedor y
    # productos): un cambio de condición concurrente espera, y todas las líneas de la compra
    # usan la misma regla.
    computa_credito_fiscal = identidad_service.organizacion_computa_credito_fiscal(
        organizacion_id, sesion, para_compartir=True
    )
    if computa_credito_fiscal is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    hoy = identidad_service.fecha_de_negocio(organizacion_id, sesion, reloj)
    if hoy is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    validar_fecha(fecha, hoy=hoy)
    total = validar_total_factura(total_factura)
    if condicion == CONTADO:
        entradas_de_medio = _resolver_medios(organizacion_id, sesion, medios)
    else:  # el crédito no trae medios: `validar_pago` lo rechaza si los hay
        entradas_de_medio = [
            MedioDeEntrada(m.importe, m.referencia, requiere_referencia=False) for m in medios
        ]
    validar_pago(condicion, total, entradas_de_medio)

    entradas, alicuotas = _referencias_de_la_compra(
        organizacion_id,
        sesion,
        proveedor_id=proveedor_id,
        ubicacion_id=ubicacion_id,
        lineas=lineas,
        computa_credito_fiscal=computa_credito_fiscal,
    )
    totales = calcular_compra(entradas)

    vigentes: dict[UUID, Decimal | None] = {}
    for linea in lineas:
        if linea.producto_id not in vigentes:
            vigente = repository.obtener_vigente(organizacion_id, linea.producto_id, fecha, sesion)
            vigentes[linea.producto_id] = None if vigente is None else vigente.costo_base
    diferencias = diferencias_de_costo(
        [
            CostoDeLinea(
                linea=indice, producto_id=linea.producto_id, costo_base=calculada.costo_base
            )
            for indice, (linea, calculada) in enumerate(zip(lineas, totales.lineas, strict=True))
        ],
        vigentes,
    )

    compra_id = nuevo_id()
    cuentas_corrientes_service.bloquear_saldo(
        organizacion_id, sesion, reloj, cuenta_tipo=_CUENTA_PROVEEDOR, entidad_id=proveedor_id
    )
    stock_service.registrar_movimientos(
        organizacion_id,
        sesion,
        reloj,
        lineas=[
            LineaDeMovimiento(
                producto_id=linea.producto_id,
                ubicacion_id=ubicacion_id,
                cantidad_base=calculada.cantidad_base,
                tipo="COMPRA",
                costo_unitario=calculada.costo_base,
                origen_tipo="COMPRA",
                origen_id=compra_id,
            )
            for linea, calculada in zip(lineas, totales.lineas, strict=True)
        ],
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
        occurred_at=occurred_at,
    )
    cuentas_corrientes_service.registrar_movimiento(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=_CUENTA_PROVEEDOR,
        entidad_id=proveedor_id,
        tipo="COMPRA",
        sentido="AUMENTA",
        importe=total,
        origen_tipo="COMPRA",
        origen_id=compra_id,
        occurred_at=occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )
    pago_id = nuevo_id()
    if condicion == CONTADO:
        # CC-05, D2: el pago de contado entra por separado en la cuenta, así el saldo
        # no cambia y el estado de cuenta muestra los dos hechos.
        cuentas_corrientes_service.registrar_movimiento(
            organizacion_id,
            sesion,
            reloj,
            cuenta_tipo=_CUENTA_PROVEEDOR,
            entidad_id=proveedor_id,
            tipo="PAGO",
            sentido="REDUCE",
            importe=total,
            origen_tipo="PAGO",
            origen_id=pago_id,
            occurred_at=occurred_at,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
        )

    compra, filas = repository.insertar_compra(
        organizacion_id,
        sesion,
        compra=repository.DatosDeCompra(
            id=compra_id,
            proveedor_id=proveedor_id,
            ubicacion_id=ubicacion_id,
            fecha=fecha,
            condicion=condicion,
            total_neto=totales.total_neto,
            total_factura=total,
            numero_comprobante=numero_comprobante,
            observacion=observacion,
            operation_id=operation_id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=occurred_at,
            registered_at=reloj.now(),
        ),
        lineas=[
            repository.DatosDeLineaDeCompra(
                id=nuevo_id(),
                orden=indice + 1,
                producto_id=linea.producto_id,
                presentacion_id=linea.presentacion_id,
                unidades_presentacion=entrada.unidades_presentacion,
                cantidad=linea.cantidad,
                cantidad_base=calculada.cantidad_base,
                valor_presentacion=linea.valor,
                incluye_iva=linea.incluye_iva,
                computa_credito_fiscal=computa_credito_fiscal,
                bonificacion=linea.bonificacion,
                alicuota_aplicada=alicuota.valor,
                costo_base=calculada.costo_base,
                importe_neto=calculada.importe_neto,
            )
            for indice, (linea, entrada, calculada, alicuota) in enumerate(
                zip(lineas, entradas, totales.lineas, alicuotas, strict=True)
            )
        ],
    )
    pago: PagoProveedor | None = None
    if condicion == CONTADO:
        pago = repository.insertar_pago(
            organizacion_id,
            sesion,
            pago=repository.DatosDePago(
                id=pago_id,
                proveedor_id=proveedor_id,
                fecha=fecha,
                importe=total,
                origen=pagos.ORIGEN_COMPRA,
                compra_id=compra_id,
                observacion=None,
                operation_id=operation_id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                occurred_at=occurred_at,
                registered_at=reloj.now(),
            ),
            medios=[
                repository.DatosDeMedioDePago(
                    medio_pago_id=medio.medio_pago_id,
                    importe=entrada.importe,
                    referencia=medio.referencia,
                )
                for medio, entrada in zip(medios, entradas_de_medio, strict=True)
            ],
        )
    return ResultadoDeCompra(
        compra=compra, lineas=filas, diferencias_de_costo=diferencias, pago=pago
    )


# --- registro de pagos a proveedor (change 12, PAG-01 y PAG-02, D2, D3 a D6, D10) --------


@dataclass(frozen=True)
class ResultadoDePago:
    """El pago confirmado y el saldo del proveedor después de aplicarlo (CC-04)."""

    pago: PagoProveedor
    saldo: Decimal


def registrar_pago(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    proveedor_id: UUID,
    fecha: date,
    importe: Decimal,
    medios: Sequence[MedioAPagar],
    observacion: str | None,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
) -> ResultadoDePago:
    """`PAGO_PROVEEDOR_REGISTRAR` (`design.md` D2 a D6 y D10; PAG-01, PAG-02, CC-03, CC-04,
    CC-08, INV-13, INV-21, TR-04, TR-09).

    El pago nace `CONFIRMADA` y de origen `INDEPENDIENTE`: no se imputa a ninguna compra
    (PAG-02) y por eso no toca stock, costo promedio ni historia de costo (CST-14). Reduce
    el saldo del proveedor, siempre mayor que la deuda (D3, opción A: el saldo queda
    a favor de la organización sin movimiento de compensación; lo absorbe la compra
    siguiente). Se admite pagar a un proveedor inactivo con deuda (D5).

    Orden (D10, el mismo de `anular_compra`): 1) reglas puras; 2) referencias, con el
    proveedor `FOR SHARE`; 3) saldo bloqueado `FOR UPDATE`; 4) una sola escritura del
    pago con sus medios y el movimiento `PAGO`. El movimiento usa el `occurred_at` del
    comando, no la fecha del pago (D4, opción A), y `origen_id` es el id del pago.
    """
    # 1) reglas puras, antes de tocar la base (INV-01: si algo falla, no se construyó nada)
    observacion_a_guardar = pagos.validar_pago_independiente(
        importe, fecha, observacion, hoy=reloj.now().date()
    )
    entradas_de_medio = _resolver_medios(organizacion_id, sesion, medios)
    pagos.validar_medios(importe, entradas_de_medio)

    # 2) referencias: el proveedor debe existir en la organización (INV-21, 404).
    #    D5: se admite uno inactivo, así que no se mira `activo`.
    proveedor = repository.obtener_proveedor_por_id_para_compartir(
        organizacion_id, proveedor_id, sesion
    )
    if proveedor is None:
        raise RecursoNoEncontradoError(
            f"El proveedor {proveedor_id} no existe en esta organización."
        )

    # 3) saldo bloqueado: serializa dos pagos simultáneos al mismo proveedor (D10)
    cuentas_corrientes_service.bloquear_saldo(
        organizacion_id, sesion, reloj, cuenta_tipo=_CUENTA_PROVEEDOR, entidad_id=proveedor_id
    )

    # 4) una sola escritura del pago con sus medios (INV-01, INV-08)
    pago = repository.insertar_pago(
        organizacion_id,
        sesion,
        pago=repository.DatosDePago(
            id=nuevo_id(),
            proveedor_id=proveedor_id,
            fecha=fecha,
            importe=importe,
            origen=pagos.ORIGEN_INDEPENDIENTE,
            compra_id=None,
            observacion=observacion_a_guardar,
            operation_id=operation_id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=occurred_at,
            registered_at=reloj.now(),
        ),
        medios=[
            repository.DatosDeMedioDePago(
                medio_pago_id=medio.medio_pago_id,
                importe=entrada.importe,
                referencia=medio.referencia,
            )
            for medio, entrada in zip(medios, entradas_de_medio, strict=True)
        ],
    )
    cuentas_corrientes_service.registrar_movimiento(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=_CUENTA_PROVEEDOR,
        entidad_id=proveedor_id,
        tipo=_TIPO_MOVIMIENTO_PAGO,
        sentido="REDUCE",
        importe=importe,
        origen_tipo="PAGO",
        origen_id=pago.id,
        occurred_at=occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )
    return ResultadoDePago(
        pago=pago,
        saldo=cuentas_corrientes_service.obtener_saldo(
            organizacion_id, sesion, cuenta_tipo=_CUENTA_PROVEEDOR, entidad_id=proveedor_id
        ),
    )


# --- anulación de pagos a proveedor (change 12, PAG-03; `design.md` D1, D2, D5, D10) --------

_AMBITO_ANULACION_PAGO = "ANULACION_PAGO"
_TIPO_MOVIMIENTO_ANULACION_PAGO = "ANULACION_PAGO"


@dataclass(frozen=True)
class ResultadoDeAnulacionDePago:
    """El pago anulado y el saldo del proveedor después de la anulación (CC-04): el mismo
    saldo que tenía antes de registrar el pago, si no hubo movimientos intermedios."""

    pago: PagoProveedor
    saldo: Decimal


def _validar_motivo_de_anulacion_de_pago(
    organizacion_id: UUID, sesion: Session, motivo_id: UUID
) -> None:
    """D1, PAG-03, TR-09: el motivo tiene que existir en la organización (404 si no,
    INV-21) y ser activo del ámbito `ANULACION_PAGO` (`MOTIVO_INVALIDO` si no)."""
    motivo = configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
    if motivo is None:
        raise RecursoNoEncontradoError(f"El motivo {motivo_id} no existe en esta organización.")
    if not motivo.activo or motivo.ambito != _AMBITO_ANULACION_PAGO:
        raise MotivoInvalidoError(
            f"El motivo {motivo_id} no es un motivo activo de {_AMBITO_ANULACION_PAGO}."
        )


def anular_pago(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    pago_id: UUID,
    motivo_id: UUID,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
) -> ResultadoDeAnulacionDePago:
    """`PAGO_PROVEEDOR_ANULAR` (PAG-03, CC-03, CC-04, CMP-05, INV-01, INV-05;
    `design.md` D1, D2, D5, D10).

    Anula un pago `CONFIRMADA` en una sola transacción: registra `ANULACION_PAGO`
    `AUMENTA` por el importe del pago en la cuenta del proveedor (el movimiento inverso
    del `PAGO`, CC-03) y deja el pago `ANULADA` con motivo, usuario y momento. No borra ni
    edita el pago más allá de su estado, sus medios ni el movimiento original (INV-05,
    TR-06, CC-06). El movimiento usa el `occurred_at` del comando (D4).

    D5: se admite aunque el proveedor esté inactivo, así que no se mira `activo`.
    D2: un pago de una compra `CONFIRMADA` no se anula por separado
    (`PAGO_DE_COMPRA_VIGENTE`): se anula con la compra.

    Orden de bloqueo (`02` §7.3, D10): el pago se lee SIN bloquear para conocer su
    `origen`; si es de origen `COMPRA` se bloquea PRIMERO la fila de la compra y después
    la del pago (el mismo orden que `anular_compra`, así ninguna de las dos anulaciones
    queda esperando a la otra); recién entonces se revalida el estado con la fila
    bloqueada, se valida el motivo y por último se bloquea `saldo_cuenta` y se escribe.
    """
    pago_leido = repository.obtener_pago(organizacion_id, pago_id, sesion)
    if pago_leido is None:
        raise RecursoNoEncontradoError(f"El pago {pago_id} no existe en esta organización.")

    compra = None
    if pago_leido.origen == pagos.ORIGEN_COMPRA and pago_leido.compra_id is not None:
        # La compra se bloquea antes que el pago (D10): `anular_compra` ya bloquea esta
        # misma fila, y tomar los bloqueos en el mismo orden evita el interbloqueo entre
        # una anulación de compra y una de su pago simultáneas.
        compra = repository.obtener_compra_para_actualizar(
            organizacion_id, pago_leido.compra_id, sesion
        )
        if compra is None:  # la FK compuesta de `pago_proveedor` lo impide
            raise RecursoNoEncontradoError(
                f"La compra {pago_leido.compra_id} no existe en esta organización."
            )

    pago = repository.obtener_pago_para_actualizar(organizacion_id, pago_id, sesion)
    assert pago is not None  # la fila existe: recién se leyó sin bloquear.
    # Con la fila bloqueada se revalida el estado: entre la lectura sin bloqueo y este
    # punto otra sesión pudo anular el pago o su compra (D10, `02` §7.3).
    pagos.validar_pago_a_anular(
        pago.estado,
        pago.origen,
        None if compra is None else compra.estado,
    )
    _validar_motivo_de_anulacion_de_pago(organizacion_id, sesion, motivo_id)

    # Saldo bloqueado: serializa dos anulaciones simultáneas del mismo proveedor (D10).
    cuentas_corrientes_service.bloquear_saldo(
        organizacion_id, sesion, reloj, cuenta_tipo=_CUENTA_PROVEEDOR, entidad_id=pago.proveedor_id
    )
    # El pago se marca ANTES que el movimiento a propósito. INV-01 fija la atomicidad en
    # esa ventana exacta ("falla después de marcar el pago y antes del movimiento de
    # cuenta"), y solo se puede probar si la marca ocurre primero: con la fila del pago y
    # `saldo_cuenta` ya bloqueados, ninguna otra transacción puede observar el estado
    # intermedio, así que el orden de las dos escrituras no cambia el resultado observable
    # y el fallo se revierte con la transacción entera (la maneja el bus, `02` §5.2).
    repository.marcar_pago_anulado(
        organizacion_id,
        sesion,
        pago=pago,
        motivo_id=motivo_id,
        anulado_en=occurred_at,
        anulado_por_id=usuario_id,
    )
    cuentas_corrientes_service.registrar_movimiento(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=_CUENTA_PROVEEDOR,
        entidad_id=pago.proveedor_id,
        tipo=_TIPO_MOVIMIENTO_ANULACION_PAGO,
        sentido="AUMENTA",
        importe=pago.importe,
        origen_tipo=_TIPO_MOVIMIENTO_ANULACION_PAGO,
        origen_id=pago.id,
        occurred_at=occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )
    return ResultadoDeAnulacionDePago(
        pago=pago,
        saldo=cuentas_corrientes_service.obtener_saldo(
            organizacion_id, sesion, cuenta_tipo=_CUENTA_PROVEEDOR, entidad_id=pago.proveedor_id
        ),
    )


# --- anulación de compras (change 11, CMP-05 a CMP-07) ----------------------------------

_AMBITO_ANULACION_COMPRA = "ANULACION_COMPRA"
OBSERVACION_SIN_RECALCULO = "ANULACION_COMPRA_SIN_RECALCULO"
OBSERVACION_STOCK_NEGATIVO = "STOCK_NEGATIVO"


@dataclass(frozen=True)
class AvisoDeAnulacion:
    """Un hecho de la anulación que el bus registra como observación (SYN-07):
    `codigo` es `ANULACION_COMPRA_SIN_RECALCULO` o `STOCK_NEGATIVO`; `productos` lleva
    el detalle por producto."""

    codigo: str
    productos: list[dict[str, object]]


@dataclass(frozen=True)
class ResultadoDeAnulacion:
    """La compra anulada, si se anuló su pago de contado y los avisos de la anulación."""

    compra: Compra
    pago_anulado: bool
    avisos: list[AvisoDeAnulacion]


def _validar_motivo_de_anulacion(organizacion_id: UUID, sesion: Session, motivo_id: UUID) -> None:
    motivo = configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
    if motivo is None:
        raise RecursoNoEncontradoError(f"El motivo {motivo_id} no existe en esta organización.")
    if not motivo.activo or motivo.ambito != _AMBITO_ANULACION_COMPRA:
        raise MotivoInvalidoError(
            f"El motivo {motivo_id} no es un motivo activo de {_AMBITO_ANULACION_COMPRA}."
        )


def anular_compra(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    compra_id: UUID,
    motivo_id: UUID,
    devuelve_pago: bool | None,
    permitir_stock_negativo: bool,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
) -> ResultadoDeAnulacion:
    """`COMPRA_ANULAR` (CMP-05 a CMP-07, INV-01, INV-05; `design.md` D3, D9 a D12).

    Anula una compra `CONFIRMADA` en una sola transacción: egresa el stock de cada línea
    en orden inverso al de la compra (movimiento `ANULACION_COMPRA` con el costo base de
    la línea, que revierte el promedio, CMP-06), registra `ANULACION_COMPRA` en la cuenta
    del proveedor y, en una compra de contado, `devuelve_pago` decide si el pago se anula
    (`ANULACION_PAGO`) o se mantiene (saldo a favor). Orden de bloqueo (`02` §7.3):
    compra `FOR UPDATE` -> `saldo_cuenta` -> `costo_producto` -> `stock_saldo`. Admite
    maestros inactivos, salvo la ubicación (D11). Sin `permitir_stock_negativo` un egreso
    que no alcanza es `STOCK_INSUFICIENTE`. TODA validación va antes de la primera
    escritura (INV-01)."""
    compra = repository.obtener_compra_para_actualizar(organizacion_id, compra_id, sesion)
    if compra is None:
        raise RecursoNoEncontradoError(f"La compra {compra_id} no existe en esta organización.")
    if compra.estado == "ANULADA":
        raise CompraYaAnuladaError(f"La compra {compra_id} ya está anulada.")

    _validar_motivo_de_anulacion(organizacion_id, sesion, motivo_id)
    es_contado = compra.condicion == CONTADO
    if es_contado and devuelve_pago is None:
        raise CondicionInvalidaError(
            "Al anular una compra de contado hay que indicar si el proveedor devuelve el pago."
        )
    if not es_contado and devuelve_pago is not None:
        raise CondicionInvalidaError("Una compra a crédito no lleva `devuelve_pago`.")

    ubicacion = stock_service.obtener_ubicacion(organizacion_id, sesion, compra.ubicacion_id)
    if ubicacion is None:  # la FK compuesta de la compra lo impide
        raise RecursoNoEncontradoError("La ubicación de la compra no existe.")
    if not ubicacion.activo:
        raise UbicacionInactivaError(f"La ubicación {compra.ubicacion_id} está inactiva.")

    lineas = repository.listar_lineas_de_compra(organizacion_id, compra_id, sesion)
    pago = (
        repository.obtener_pago_de_compra(organizacion_id, compra_id, sesion)
        if es_contado
        else None
    )

    cuentas_corrientes_service.bloquear_saldo(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=_CUENTA_PROVEEDOR,
        entidad_id=compra.proveedor_id,
    )
    en_orden_inverso = list(reversed(lineas))
    resultados = stock_service.registrar_movimientos(
        organizacion_id,
        sesion,
        reloj,
        lineas=[
            LineaDeMovimiento(
                producto_id=linea.producto_id,
                ubicacion_id=compra.ubicacion_id,
                cantidad_base=-linea.cantidad_base,
                tipo="ANULACION_COMPRA",
                costo_unitario=linea.costo_base,
                origen_tipo="ANULACION_COMPRA",
                origen_id=compra_id,
                motivo_id=motivo_id,
            )
            for linea in en_orden_inverso
        ],
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
        occurred_at=occurred_at,
        permitir_negativo=permitir_stock_negativo,
    )

    sin_recalculo: list[dict[str, object]] = []
    en_negativo: list[dict[str, object]] = []
    for linea, resultado in zip(en_orden_inverso, resultados, strict=True):
        if resultado.promedio_recalculado is False:
            sin_recalculo.append(
                {
                    "producto_id": str(linea.producto_id),
                    "linea": linea.orden,
                    "costo_base": str(linea.costo_base),
                }
            )
        if resultado.saldo_negativo:
            en_negativo.append(
                {
                    "producto_id": str(linea.producto_id),
                    "ubicacion_id": str(compra.ubicacion_id),
                    "saldo": resultado.saldo,
                }
            )

    cuentas_corrientes_service.registrar_movimiento(
        organizacion_id,
        sesion,
        reloj,
        cuenta_tipo=_CUENTA_PROVEEDOR,
        entidad_id=compra.proveedor_id,
        tipo="ANULACION_COMPRA",
        sentido="REDUCE",
        importe=compra.total_factura,
        origen_tipo="ANULACION_COMPRA",
        origen_id=compra_id,
        occurred_at=occurred_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )
    pago_anulado = False
    if pago is not None and devuelve_pago:
        cuentas_corrientes_service.registrar_movimiento(
            organizacion_id,
            sesion,
            reloj,
            cuenta_tipo=_CUENTA_PROVEEDOR,
            entidad_id=compra.proveedor_id,
            tipo="ANULACION_PAGO",
            sentido="AUMENTA",
            importe=pago.importe,
            origen_tipo="ANULACION_PAGO",
            origen_id=pago.id,
            occurred_at=occurred_at,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
        )
        repository.marcar_pago_anulado(
            organizacion_id,
            sesion,
            pago=pago,
            motivo_id=motivo_id,
            anulado_en=occurred_at,
            anulado_por_id=usuario_id,
        )
        pago_anulado = True
    repository.marcar_compra_anulada(
        organizacion_id,
        sesion,
        compra=compra,
        motivo_id=motivo_id,
        anulada_en=occurred_at,
        anulada_por_id=usuario_id,
    )

    avisos: list[AvisoDeAnulacion] = []
    if sin_recalculo:
        avisos.append(AvisoDeAnulacion(OBSERVACION_SIN_RECALCULO, sin_recalculo))
    if en_negativo:
        avisos.append(AvisoDeAnulacion(OBSERVACION_STOCK_NEGATIVO, en_negativo))
    return ResultadoDeAnulacion(compra=compra, pago_anulado=pago_anulado, avisos=avisos)
